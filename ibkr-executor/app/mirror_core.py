"""Composer mirror core: virtual sleeves, the rebalance rule, netting and fill booking.

Pure and deterministic: no I/O, no clock, no broker types, stdlib only. The executor's mirror
manager (app/mirror.py) and the DRY simulator on the research side
(composer/scripts/mirror_dry.py) both import THIS module, so what the dry run measures is what the
executor does.

Model
- The mirror book is N sleeves, one per Composer symphony. A sleeve owns cash and whole shares.
- Each session the brain publishes a target weight vector per sleeve. A 'daily' sleeve trades to
  its target; a 'threshold' sleeve trades only when some asset's weight sits more than its corridor
  away from the target (Composer's threshold rebalance), or when it holds nothing.
- Orders are NETTED across sleeves per symbol. Opposite-direction legs cross internally at the
  reference price; only the net goes to the venue: at most one SELL or one BUY per symbol per
  session.
- Two phases. SELLS first. When the sells are booked, BUYS are sized from each sleeve's ACTUAL
  cash, never from expected proceeds, and scaled so the book as a whole never spends more cash
  than it has (no borrowing, whatever the account type allows). A buy is a LIMIT order and is
  sized AT ITS LIMIT (the price it can never fill above), with the sleeve's cash reserve held
  back for commissions: quantity x limit never exceeds the cash of the sleeve, nor of the book.
- A venue order is booked exactly once, at its terminal state, and split across the sleeves that
  asked for it by largest remainder.
- The corridor of a threshold sleeve is read on INVESTED weights (each holding over the sleeve's
  holdings value, cash excluded), which is how Composer measures it. A sleeve in debt (negative
  cash) is never inside its corridor and is exempt from the dust rule until it is repaired; a
  threshold sleeve idling more than MAX_IDLE_CASH_FRAC of its equity in cash trades too (a state
  Composer never reaches, e.g. after a refused buy).
  KNOWN LIMIT of that cash rule (measured by the review, not changed): a target holding a share
  worth more than MAX_IDLE_CASH_FRAC of the sleeve leaves more than that in cash by whole-share
  rounding alone, so such a sleeve trades inside its corridor (979 of 5,000 random sessions at a
  $3,000 sleeve, 6 of 5,000 at $34,000). Keep threshold sleeves well above 20 x their dearest share.
- Distributions and splits are accounting, and live here so the research-side paper simulator
  applies the same rules: dividend_receivables() / settle_receivable() and apply_split(). A
  dividend whose PAY DATE is not known yet keeps it unknown (None): it is taken from a later
  listing, and only PAY_DATE_GIVE_UP_DAYS after the ex-date is ex + DEFAULT_PAY_LAG_DAYS assumed.
- The cash reserve (cash_reserve_frac, 0.1% of a sleeve) is what pays commissions. It is below
  IBKR's $0.005 a share for a name under about $5 a share; the cheapest holdable names are above $6.

Invariants (check(); tests/test_mirror_core.py)
- every share is owned by exactly one sleeve: the sleeves' shares per symbol sum to the book's
- cash moves only by fills (qty x price), commissions, crosses (zero-sum) and transfers (zero-sum)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction

SCHEMA = 1
RULE_DAILY, RULE_THRESHOLD = "daily", "threshold"
SELL, BUY = "SELL", "BUY"
TARGET_SUM_TOL = 0.002           # a target vector must sum to 1 within this
MAX_IDLE_CASH_FRAC = 0.05        # a threshold sleeve holding more cash than this share of its equity trades
DEBT_TOL_USD = 0.005             # cash below minus this is a debt (float dust is not)
DIVIDEND_RULES = ("composer", "holder")
DEFAULT_PAY_LAG_DAYS = 7         # a dividend whose pay date never became known is taken to pay this long after its ex-date
PAY_DATE_GIVE_UP_DAYS = 10       # ... but only once this many calendar days have passed since the ex-date
RECEIVABLE_EXPIRE_DAYS = 30      # a receivable still unpaid this long after its pay date is closed


class MirrorError(Exception):
    """A request the core refuses: a booking that would corrupt the book."""


@dataclass
class Config:
    cash_reserve_frac: float = 0.001   # share of a sleeve's equity kept uninvested (it pays the commissions)
    buy_cushion: float = 0.005         # a buy's limit is its price x (1 + cushion); it is sized at that limit
    min_trade_frac: float = 0.005      # a drift trim smaller than this share of sleeve equity
    min_trade_usd: float = 25.0        # ... or this many dollars is skipped (entries/exits never)


@dataclass
class Sleeve:
    name: str
    cash: float = 0.0
    shares: dict = field(default_factory=dict)      # symbol -> whole shares (> 0)
    rule: str = RULE_DAILY
    corridor: float | None = None                   # threshold sleeves: e.g. 0.10
    version: str | None = None                      # tree version of the last plan it traded on
    last_trade: str | None = None                   # session of its last trade

    def to_dict(self) -> dict:
        return {"name": self.name, "cash": self.cash, "shares": dict(self.shares), "rule": self.rule,
                "corridor": self.corridor, "version": self.version, "last_trade": self.last_trade}

    @classmethod
    def from_dict(cls, d: dict) -> "Sleeve":
        shares = {}
        for sym, q in (d.get("shares") or {}).items():
            if not _is_whole(q) or int(q) < 0:
                raise MirrorError(f"sleeve {d.get('name')}: {sym} holds a non-whole or negative quantity {q!r}")
            if int(q) > 0:
                shares[str(sym)] = int(q)
        cash = float(d.get("cash", 0.0))
        if not math.isfinite(cash):
            raise MirrorError(f"sleeve {d.get('name')}: cash is not finite")
        rule = d.get("rule", RULE_DAILY)
        if rule not in (RULE_DAILY, RULE_THRESHOLD):
            raise MirrorError(f"sleeve {d.get('name')}: unknown rule {rule!r}")
        return cls(name=str(d["name"]), cash=cash, shares=shares, rule=rule, corridor=d.get("corridor"),
                   version=d.get("version"), last_trade=d.get("last_trade"))


@dataclass
class Book:
    sleeves: dict = field(default_factory=dict)     # name -> Sleeve (insertion order is the report order)

    @classmethod
    def seed(cls, capital: float, fractions: dict, rules: dict | None = None) -> "Book":
        """A fresh all-cash book: capital split by `fractions` (must sum to 1). rules: {name:
        {"rule": ..., "corridor": ...}} for the sleeves that are not plain daily."""
        if not (math.isfinite(capital) and capital > 0):
            raise MirrorError("seed capital must be positive")
        tot = sum(fractions.values())
        if abs(tot - 1.0) > 1e-9 or any((not math.isfinite(f)) or f <= 0 for f in fractions.values()):
            raise MirrorError(f"seed fractions must be positive and sum to 1 (got {tot})")
        book = cls()
        for name, f in fractions.items():
            r = (rules or {}).get(name) or {}
            book.sleeves[name] = Sleeve(name=name, cash=capital * f, rule=r.get("rule", RULE_DAILY),
                                        corridor=r.get("corridor"))
        return book

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "sleeves": [s.to_dict() for s in self.sleeves.values()]}

    @classmethod
    def from_dict(cls, d: dict) -> "Book":
        if d.get("schema") != SCHEMA:
            raise MirrorError(f"mirror book schema {d.get('schema')!r} is not {SCHEMA}")
        book = cls()
        for row in d.get("sleeves") or []:
            s = Sleeve.from_dict(row)
            if s.name in book.sleeves:
                raise MirrorError(f"duplicate sleeve {s.name}")
            book.sleeves[s.name] = s
        return book

    def positions(self) -> dict:
        """the book's total shares per symbol (the sum over sleeves)"""
        out: dict = {}
        for s in self.sleeves.values():
            for sym, q in s.shares.items():
                out[sym] = out.get(sym, 0) + q
        return {k: v for k, v in sorted(out.items()) if v}

    def cash(self) -> float:
        return sum(s.cash for s in self.sleeves.values())


# ------------------------------------------------------------------ small pure helpers
def _is_whole(q) -> bool:
    if isinstance(q, bool):
        return False
    if isinstance(q, int):
        return True
    return isinstance(q, float) and math.isfinite(q) and q == int(q)


def _px(prices: dict, sym: str) -> float | None:
    p = prices.get(sym)
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0:
        return None
    return float(p)


def missing_prices(symbols, prices: dict) -> list:
    return sorted(s for s in set(symbols) if _px(prices, s) is None)


def holdings_value(sleeve: Sleeve, prices: dict) -> float:
    return sum(q * _need(prices, sym) for sym, q in sleeve.shares.items())


def _need(prices: dict, sym: str) -> float:
    p = _px(prices, sym)
    if p is None:
        raise MirrorError(f"no usable price for {sym}")
    return p


def equity(sleeve: Sleeve, prices: dict) -> float:
    return sleeve.cash + holdings_value(sleeve, prices)


def weights(sleeve: Sleeve, prices: dict) -> dict:
    """holdings as shares of the sleeve's equity (cash is the remainder); {} when equity <= 0"""
    eq = equity(sleeve, prices)
    if eq <= 0:
        return {}
    return {sym: q * _need(prices, sym) / eq for sym, q in sorted(sleeve.shares.items())}


def invested_weights(sleeve: Sleeve, prices: dict) -> dict:
    """holdings as shares of the sleeve's HOLDINGS value (cash excluded; they sum to 1): the weights
    Composer's threshold rule reads. {} when it holds nothing"""
    hv = holdings_value(sleeve, prices)
    if hv <= 0:
        return {}
    return {sym: q * _need(prices, sym) / hv for sym, q in sorted(sleeve.shares.items())}


def in_debt(sleeve: Sleeve) -> bool:
    return sleeve.cash < -DEBT_TOL_USD


def max_gap(target: dict, held: dict) -> float:
    """the largest single-asset distance between two weight vectors (Composer's corridor measure)"""
    keys = set(target) | set(held)
    return max((abs(held.get(k, 0.0) - target.get(k, 0.0)) for k in keys), default=0.0)


def clean_target(target) -> tuple:
    """(normalized target or None, problem). A usable target: a non-empty dict of symbol -> finite
    non-negative weight summing to 1 within TARGET_SUM_TOL; zero weights are dropped."""
    if not isinstance(target, dict) or not target:
        return None, "no target"
    out = {}
    for sym, w in target.items():
        if not isinstance(sym, str) or not sym or isinstance(w, bool) or not isinstance(w, (int, float)) \
                or not math.isfinite(w) or w < 0:
            return None, f"bad weight for {sym!r}: {w!r}"
        if w > 0:
            out[sym] = float(w)
    tot = sum(out.values())
    if not out or abs(tot - 1.0) > TARGET_SUM_TOL:
        return None, f"target weights sum to {tot:.4f}, not 1"
    return {s: w / tot for s, w in sorted(out.items())}, None


def allocate(total: int, asks: dict) -> dict:
    """split `total` whole units across `asks` ({name: whole units asked}) in proportion, by largest
    remainder (ties by name), never giving anyone more than they asked. total <= sum(asks)."""
    asks = {k: int(v) for k, v in asks.items() if int(v) > 0}
    whole = sum(asks.values())
    total = int(total)
    if total < 0 or total > whole:
        raise MirrorError(f"cannot allocate {total} across asks totalling {whole}")
    if total == 0 or not asks:
        return {k: 0 for k in asks}
    out, rema = {}, []
    for k in sorted(asks):
        exact_num = total * asks[k]            # exact share = exact_num / whole, in integers
        out[k] = exact_num // whole
        rema.append((-(exact_num % whole), k))
    left = total - sum(out.values())
    for _, k in sorted(rema)[:left]:
        out[k] += 1
    return out


def order_id(session: str, side: str, symbol: str) -> str:
    """the deterministic idempotency key of the one venue order per symbol, side and session"""
    return f"mirror-{session}-{'S' if side == SELL else 'B'}-{symbol}"


# ------------------------------------------------------------------ the plan
def _desired(investable: float, target: dict, prices: dict) -> dict:
    return {sym: int(math.floor(max(investable, 0.0) * w / _need(prices, sym) + 1e-9)) for sym, w in target.items()}


def decide_sleeve(sleeve: Sleeve, target: dict, prices: dict, cfg: Config, equity_adj: float = 0.0,
                  force: bool = False) -> dict:
    """one sleeve's decision at the reference prices: {"action": "trade" | "hold", "reason", "gap",
    "weights", "invested", "deltas": {symbol: signed whole shares}}. equity_adj: capital arriving (+)
    or leaving (-) through a transfer in this plan; force: trade whatever the corridor says, every
    share of it (a transfer: the dust rule would otherwise leave the giver short of what it owes).
    gap is measured on INVESTED weights (Composer's measure)."""
    eq = equity(sleeve, prices)
    held = invested_weights(sleeve, prices)
    gap = max_gap(target, held)
    debt = in_debt(sleeve)
    idle = sleeve.cash / eq if eq > 0 else 0.0
    base = {"gap": gap, "weights": weights(sleeve, prices), "invested": held, "equity": eq}
    if sleeve.rule == RULE_THRESHOLD and sleeve.corridor and sleeve.shares and not force and not debt \
            and idle <= MAX_IDLE_CASH_FRAC and gap <= sleeve.corridor:
        return dict(base, action="hold", reason=f"inside the corridor: largest gap {gap:.1%} vs {sleeve.corridor:.0%}",
                    deltas={})
    investable = (eq + equity_adj) * (1.0 - cfg.cash_reserve_frac)
    want = _desired(investable, target, prices)
    floor_usd = max(cfg.min_trade_usd, cfg.min_trade_frac * max(eq, 0.0))
    every = force or debt                           # no trim is too small for a transfer or a debt
    deltas = {}
    for sym in sorted(set(want) | set(sleeve.shares)):
        have, w = sleeve.shares.get(sym, 0), want.get(sym, 0)
        d = w - have
        if d == 0:
            continue
        if not every and have > 0 and w > 0 and abs(d) * _need(prices, sym) < floor_usd:
            continue                                # a drift trim too small to trade
        deltas[sym] = d
    if not deltas:
        return dict(base, action="hold", reason="at target", deltas={})
    why = "to target" + (" (repairing a cash debt)" if debt else "")
    return dict(base, action="trade", reason=why, deltas=deltas)


def build_plan(book: Book, targets: dict, prices: dict, session: str, cfg: Config | None = None,
               transfers: list | None = None) -> dict:
    """The session's plan at the reference prices. targets: {sleeve: {"status": "ok", "target": {...},
    "version": ...}}. A sleeve with no usable target or a missing price is SKIPPED whole (it keeps its
    holdings); nothing is ever planned on a guess. transfers: [{"from", "to", "amount"}] of capital
    between sleeves, funded by the giver's sells and invested by the taker's buys in this plan.

    Returns a JSON-serializable dict: sleeves (decisions), crosses (internal, at the reference price),
    sells (venue orders with their per-sleeve asks) and buy_asks (what each sleeve still wants from
    the venue; sized into orders by size_buys() once the sells are booked)."""
    cfg = cfg or Config()
    plan = {"schema": SCHEMA, "session": session, "prices": {}, "sleeves": {}, "crosses": [], "sells": [],
            "buy_asks": {}, "buys": None, "transfers": [], "crosses_applied": False, "transfers_applied": False}
    usable = {}
    for name, sleeve in book.sleeves.items():
        row = targets.get(name) if isinstance(targets, dict) else None
        if not isinstance(row, dict) or row.get("status") != "ok":
            why = (row or {}).get("note") or (row or {}).get("status") or "no target published"
            # skip_reason: the CALLER holds the sleeve back (the executor's own gate), in its own words
            plan["sleeves"][name] = {"action": "skip", "reason": (row or {}).get("skip_reason") or f"brain: {why}",
                                     "deltas": {}}
            continue
        target, problem = clean_target(row.get("target"))
        if problem:
            plan["sleeves"][name] = {"action": "skip", "reason": problem, "deltas": {}}
            continue
        miss = missing_prices(set(target) | set(sleeve.shares), prices)
        if miss:
            plan["sleeves"][name] = {"action": "skip", "reason": f"no price for {', '.join(miss)}", "deltas": {}}
            continue
        usable[name] = (target, row.get("version"))
    adj = {name: 0.0 for name in usable}
    for t in transfers or []:
        src, dst, amt = t.get("from"), t.get("to"), t.get("amount")
        ok = (src in usable and dst in usable and src != dst and isinstance(amt, (int, float))
              and not isinstance(amt, bool) and math.isfinite(amt) and amt > 0)
        if ok and amt > equity(book.sleeves[src], prices) + adj[src]:
            ok = False
        if not ok:
            plan["transfers"].append({"from": src, "to": dst, "amount": amt, "status": "refused"})
            continue
        adj[src] -= float(amt)
        adj[dst] += float(amt)
        plan["transfers"].append({"from": src, "to": dst, "amount": float(amt), "status": "planned", "moved": 0.0})
    moved = {t["from"] for t in plan["transfers"] if t["status"] == "planned"} | \
            {t["to"] for t in plan["transfers"] if t["status"] == "planned"}
    asks_sell, asks_buy = {}, {}                    # symbol -> {sleeve: whole shares}
    for name, (target, version) in usable.items():
        dec = decide_sleeve(book.sleeves[name], target, prices, cfg, adj[name], force=name in moved)
        dec.update(target=target, version=version)
        plan["sleeves"][name] = dec
        for sym, d in dec["deltas"].items():
            (asks_buy if d > 0 else asks_sell).setdefault(sym, {})[name] = abs(d)
    used = set()
    for sym in sorted(set(asks_sell) | set(asks_buy)):
        sellers, buyers = asks_sell.get(sym, {}), asks_buy.get(sym, {})
        s_tot, b_tot = sum(sellers.values()), sum(buyers.values())
        cross = min(s_tot, b_tot)
        cs, cb = allocate(cross, sellers), allocate(cross, buyers)
        if cross:
            plan["crosses"].append({"symbol": sym, "qty": cross, "price": _need(prices, sym),
                                    "sellers": {k: v for k, v in cs.items() if v},
                                    "buyers": {k: v for k, v in cb.items() if v}})
        ext_sell = {k: sellers[k] - cs.get(k, 0) for k in sellers if sellers[k] - cs.get(k, 0) > 0}
        ext_buy = {k: buyers[k] - cb.get(k, 0) for k in buyers if buyers[k] - cb.get(k, 0) > 0}
        if ext_sell:
            plan["sells"].append({"id": order_id(session, SELL, sym), "side": SELL, "symbol": sym,
                                  "qty": sum(ext_sell.values()), "asks": ext_sell, "ref": _need(prices, sym),
                                  "applied": False})
        for k, q in ext_buy.items():
            plan["buy_asks"].setdefault(k, {})[sym] = q
        used.add(sym)
    for name, dec in plan["sleeves"].items():
        used |= set(dec.get("deltas") or {})
        used |= set(book.sleeves[name].shares) if dec.get("action") != "skip" else set()
    plan["prices"] = {s: _need(prices, s) for s in sorted(used) if _px(prices, s) is not None}
    return plan


def apply_crosses(book: Book, plan: dict) -> None:
    """Book the plan's internal crosses at the reference price (zero-sum across sleeves). A buyer's
    cash may go negative here until its own sells are booked; size_buys never spends a negative."""
    if plan.get("crosses_applied"):
        raise MirrorError("crosses already applied")
    for c in plan["crosses"]:
        sym, px = c["symbol"], float(c["price"])
        for name, q in c["sellers"].items():
            _move(book.sleeves[name], sym, -int(q), px)
        for name, q in c["buyers"].items():
            _move(book.sleeves[name], sym, int(q), px)
    plan["crosses_applied"] = True


def _move(sleeve: Sleeve, sym: str, qty: int, px: float, commission: float = 0.0) -> None:
    """qty signed (+ buys, - sells) at px; never lets a sleeve sell shares it does not own"""
    have = sleeve.shares.get(sym, 0)
    if have + qty < 0:
        raise MirrorError(f"sleeve {sleeve.name} would sell {-qty} {sym} but owns {have}")
    if have + qty:
        sleeve.shares[sym] = have + qty
    else:
        sleeve.shares.pop(sym, None)
    sleeve.cash -= qty * px + commission


def book_fill(book: Book, order: dict, filled_qty: int, avg_price: float | None, commission: float = 0.0) -> dict:
    """Book ONE venue order at its terminal state: `filled_qty` (0..order qty) at `avg_price`, split
    across the sleeves that asked by largest remainder; commission split by filled shares. Returns the
    per-sleeve split. Raises if the order was booked before or the fill is impossible."""
    if order.get("applied"):
        raise MirrorError(f"order {order.get('id')} already booked")
    if not _is_whole(filled_qty) or int(filled_qty) < 0 or int(filled_qty) > int(order["qty"]):
        raise MirrorError(f"order {order.get('id')}: filled {filled_qty!r} outside 0..{order['qty']}")
    filled_qty = int(filled_qty)
    if filled_qty and (avg_price is None or not math.isfinite(avg_price) or avg_price <= 0):
        raise MirrorError(f"order {order.get('id')}: {filled_qty} filled with no usable price")
    if not math.isfinite(commission) or commission < 0:
        raise MirrorError(f"order {order.get('id')}: bad commission {commission!r}")
    split = allocate(filled_qty, order["asks"])
    sign = -1 if order["side"] == SELL else 1
    spent = 0.0
    names = [k for k in sorted(split) if split[k]]
    for name in names:                              # all or nothing: refuse BEFORE any sleeve is touched
        if name not in book.sleeves:
            raise MirrorError(f"order {order.get('id')}: the book has no sleeve {name}")
        if sign < 0 and book.sleeves[name].shares.get(order["symbol"], 0) < split[name]:
            raise MirrorError(f"sleeve {name} would sell {split[name]} {order['symbol']} but owns "
                              f"{book.sleeves[name].shares.get(order['symbol'], 0)}")
    for i, name in enumerate(names):
        fee = commission - spent if i == len(names) - 1 else commission * split[name] / filled_qty
        spent += fee
        _move(book.sleeves[name], order["symbol"], sign * split[name], float(avg_price), fee)
    order.update(applied=True, filled=filled_qty, price=float(avg_price) if filled_qty else None,
                 commission=float(commission), split={k: v for k, v in split.items() if v})
    return order["split"]


def apply_transfers(book: Book, plan: dict) -> None:
    """Move the planned capital between sleeves once the sells are booked: each giver hands over what
    it planned, capped by the cash it actually has (a short sell-fill makes the transfer partial)."""
    if plan.get("transfers_applied"):
        raise MirrorError("transfers already applied")
    for t in plan["transfers"]:
        if t["status"] != "planned":
            continue
        src, dst = book.sleeves[t["from"]], book.sleeves[t["to"]]
        amt = min(float(t["amount"]), max(src.cash, 0.0))
        src.cash -= amt
        dst.cash += amt
        t.update(moved=amt, status="moved" if amt >= float(t["amount"]) - 0.005 else "partial")
    plan["transfers_applied"] = True


def buy_limit(price: float, cfg: Config | None = None) -> float:
    """the limit of a buy priced at `price`: price x (1 + cushion). (A venue rounds it DOWN to its
    price grid before it is passed to size_buys; a paper fill needs no grid.)"""
    return round(float(price) * (1.0 + (cfg or Config()).buy_cushion), 6)   # 600 x 1.005 is 603, not 602.9999999999999


def size_buys(book: Book, plan: dict, prices: dict | None = None, cfg: Config | None = None,
              limits: dict | None = None) -> list:
    """The venue BUY orders, sized once the sells are booked. Each is a LIMIT order and is costed at
    its limit - limits[symbol] when given (the caller's venue-quoted, grid-rounded limit), else
    buy_limit(reference price) - so it can never cost more than it was sized at. Each sleeve's asks
    are scaled down to the cash it actually has less its reserve (cash_reserve_frac of its equity:
    what pays the commissions), then all of them together to the book's cash, so the mirror never
    spends money it does not hold. prices: overrides of the reference prices (the orders' "ref").
    Stores and returns plan['buys']; every order carries its "limit"."""
    if plan.get("buys") is not None:
        raise MirrorError("buys already sized")
    if any(not o.get("applied") for o in plan["sells"]):
        raise MirrorError("size_buys before every sell is booked")
    if plan["crosses"] and not plan.get("crosses_applied"):
        raise MirrorError("size_buys before the crosses are applied")
    if any(t["status"] == "planned" for t in plan["transfers"]) and not plan.get("transfers_applied"):
        raise MirrorError("size_buys before the transfers are applied")
    cfg = cfg or Config()
    px = dict(plan["prices"])
    px.update({k: v for k, v in (prices or {}).items() if _px(prices, k) is not None})
    lim: dict = {}

    def limit_of(sym: str) -> float:
        if sym not in lim:
            given = _px(limits or {}, sym)
            lim[sym] = given if given is not None else buy_limit(_need(px, sym), cfg)
        return lim[sym]
    cost = lambda sym, q: q * limit_of(sym)  # noqa: E731
    sized = {}
    for name, asks in plan["buy_asks"].items():
        sleeve = book.sleeves[name]
        want = {s: int(q) for s, q in asks.items() if int(q) > 0}
        need = sum(cost(s, q) for s, q in want.items())
        try:
            reserve = cfg.cash_reserve_frac * max(equity(sleeve, px), 0.0)
        except MirrorError:                         # a holding the plan did not price: keep no less than all of it
            reserve = cfg.cash_reserve_frac * max(sleeve.cash, 0.0)
        have = max(sleeve.cash - reserve, 0.0)
        if need > have:
            k = have / need if need > 0 else 0.0
            want = {s: int(math.floor(q * k)) for s, q in want.items()}
        sized[name] = {s: q for s, q in want.items() if q > 0}
    total = sum(cost(s, q) for w in sized.values() for s, q in w.items())
    cap = max(book.cash(), 0.0)
    if total > cap:
        k = cap / total if total > 0 else 0.0
        sized = {n: {s: int(math.floor(q * k)) for s, q in w.items()} for n, w in sized.items()}
        sized = {n: {s: q for s, q in w.items() if q > 0} for n, w in sized.items()}
    by_sym: dict = {}
    for name, w in sized.items():
        for sym, q in w.items():
            by_sym.setdefault(sym, {})[name] = q
    session = plan["session"]
    plan["buys"] = [{"id": order_id(session, BUY, sym), "side": BUY, "symbol": sym, "qty": sum(asks.values()),
                     "asks": asks, "ref": _need(px, sym), "limit": limit_of(sym), "applied": False}
                    for sym, asks in sorted(by_sym.items())]
    return plan["buys"]


def finish(book: Book, plan: dict) -> None:
    """Stamp the sleeves that traded in this plan (any booked share or cross) with the session and the
    tree version they traded on."""
    touched = set()
    for c in plan["crosses"]:
        touched |= set(c["sellers"]) | set(c["buyers"])
    for o in plan["sells"] + (plan.get("buys") or []):
        touched |= {k for k, v in (o.get("split") or {}).items() if v}
    for name in touched:
        s = book.sleeves[name]
        s.last_trade = plan["session"]
        s.version = plan["sleeves"][name].get("version") or s.version


# ------------------------------------------------------------------ distributions and splits
def _day(text) -> date | None:
    try:
        y, m, d = str(text).split("-")
        return date(int(y), int(m), int(d))
    except (TypeError, ValueError):
        return None


parse_day = _day


def dividend_key(ticker: str, ex_date: str) -> str:
    """the id of one distribution of one fund (what 'seen before' is keyed on)"""
    return f"div-{ticker}-{ex_date}"


def split_key(ticker: str, day: str) -> str:
    return f"split-{ticker}-{day}"


def clean_dividend(row) -> dict | None:
    """a usable dividend row {"ticker", "ex_date", "pay_date" | None, "amount"} or None: a ticker, a
    real ex-date, a positive finite cash amount per share. pay_date is None while it is not known
    (absent, unreadable, or before the ex-date): it is never guessed here."""
    if not isinstance(row, dict):
        return None
    ticker, ex, amt = row.get("ticker"), _day(row.get("ex_date")), row.get("amount")
    if not isinstance(ticker, str) or not ticker or ex is None:
        return None
    if isinstance(amt, bool) or not isinstance(amt, (int, float)) or not math.isfinite(amt) or amt <= 0:
        return None
    pay = _day(row.get("pay_date")) if row.get("pay_date") is not None else None
    if pay is not None and pay < ex:
        pay = None
    return {"ticker": ticker, "ex_date": ex.isoformat(), "pay_date": pay.isoformat() if pay else None,
            "amount": float(amt)}


def dividend_receivables(holdings: dict, dividend: dict) -> list:
    """What one distribution owes each sleeve. holdings: {sleeve: {ticker: whole shares}} AS OF THE
    CLOSE BEFORE THE EX-DATE (the shares that carry the entitlement). dividend: {"ticker", "ex_date",
    "pay_date" | None, "amount" (cash per share)}. Returns one row per sleeve that held the ticker:
    [{"id": "div-{ticker}-{ex_date}-{sleeve}", "sleeve", "ticker", "ex_date", "pay_date" (None while
    unknown), "shares", "amount", "total"}]; [] for an unusable row or when nobody held it. Pure:
    books nothing."""
    d = clean_dividend(dividend)
    if d is None or not isinstance(holdings, dict):
        return []
    out = []
    for name in sorted(holdings):
        q = (holdings.get(name) or {}).get(d["ticker"], 0)
        if not _is_whole(q) or int(q) <= 0:
            continue
        out.append({"id": f"{dividend_key(d['ticker'], d['ex_date'])}-{name}", "sleeve": name, "ticker": d["ticker"],
                    "ex_date": d["ex_date"], "pay_date": d["pay_date"], "shares": int(q), "amount": d["amount"],
                    "total": round(int(q) * d["amount"], 6)})
    return out


def receivable_pay_date(receivable: dict, session: str) -> str | None:
    """the date a receivable is due from, as known on `session`: its pay date; while that is unknown,
    None - until PAY_DATE_GIVE_UP_DAYS calendar days after the ex-date, when ex + DEFAULT_PAY_LAG_DAYS
    is assumed (by then the brain no longer lists the dividend, so no later listing can supply it)."""
    pay = _day(receivable.get("pay_date")) if receivable.get("pay_date") else None
    if pay is not None:
        return pay.isoformat()
    ex, day = _day(receivable.get("ex_date")), _day(session)
    if ex is None or day is None or (day - ex).days < PAY_DATE_GIVE_UP_DAYS:
        return None
    return (ex + timedelta(days=DEFAULT_PAY_LAG_DAYS)).isoformat()


def settle_receivable(book: Book, receivable: dict, session: str, rule: str = "composer",
                      cash_arrived: bool = True) -> dict:
    """Settle ONE receivable against the book on `session` (YYYY-MM-DD). Returns what it did:
    {"action": "not_due" | "credited" | "leaked" | "wait" | "expired" | "void", "amount", "held": bool}.
      not_due   the session is before the pay date, or the pay date is not known yet (receivable_pay_date)
      void      its sleeve is no longer in the book
      leaked    rule "composer" and the sleeve no longer held the ticker on the first session on or
                after the pay date: the cash stays unallocated (what Composer's symphonies do)
      credited  the sleeve's cash was raised by the receivable's total (the ONLY case the book changes)
      wait      due, but the cash has not arrived (cash_arrived False: a live account's own check)
      expired   still not arrived RECEIVABLE_EXPIRE_DAYS after the pay date
    rule "holder" credits whoever held the shares at the ex-date, whatever it holds now. The holding
    test is made once: receivable["held"] (set by the caller from an earlier answer) is honoured, so
    a credit that waits for its cash is not lost to a later sale."""
    if rule not in DIVIDEND_RULES:
        raise MirrorError(f"unknown dividend rule {rule!r}")
    day = _day(session)
    total = receivable.get("total")
    if day is None or _day(receivable.get("ex_date")) is None or isinstance(total, bool) \
            or not isinstance(total, (int, float)) or not math.isfinite(total) or total <= 0:
        raise MirrorError(f"receivable {receivable.get('id')!r} cannot be settled: bad dates or total")
    pay = _day(receivable_pay_date(receivable, session))
    if pay is None or day < pay:
        return {"action": "not_due", "amount": 0.0, "held": None}
    sleeve = book.sleeves.get(receivable.get("sleeve"))
    if sleeve is None:
        return {"action": "void", "amount": 0.0, "held": None}
    held = receivable.get("held")
    if not isinstance(held, bool):
        held = sleeve.shares.get(receivable.get("ticker"), 0) > 0
    if rule == "composer" and not held:
        return {"action": "leaked", "amount": 0.0, "held": False}
    if not cash_arrived:
        if (day - pay).days >= RECEIVABLE_EXPIRE_DAYS:
            return {"action": "expired", "amount": 0.0, "held": held}
        return {"action": "wait", "amount": 0.0, "held": held}
    sleeve.cash += float(total)
    return {"action": "credited", "amount": float(total), "held": held}


def apply_split(book: Book, ticker: str, ratio) -> dict:
    """Rescale every sleeve's shares of `ticker` for a split. ratio = new shares per old share (2:1
    -> 2.0; a 1:5 reverse split -> 0.2). The book's total becomes floor(total x ratio), split across
    the sleeves by largest remainder of their exact entitlements (ties by name); cash is untouched.
    Returns {"ticker", "ratio", "before": {sleeve: shares}, "after": {sleeve: shares}, "total_before",
    "total_after", "fraction": the fractional share the floor dropped (the broker pays cash in lieu
    of it: the caller records it, this books nothing)}."""
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or ratio <= 0:
        raise MirrorError(f"split of {ticker}: bad ratio {ratio!r}")
    r = Fraction(repr(float(ratio))).limit_denominator(10_000)
    if r <= 0:
        raise MirrorError(f"split of {ticker}: bad ratio {ratio!r}")
    before = {n: s.shares[ticker] for n, s in book.sleeves.items() if s.shares.get(ticker)}
    total = sum(before.values())
    exact = {n: q * r for n, q in before.items()}
    new_total = int(sum(exact.values(), Fraction(0)))            # floor of the book's exact entitlement
    after = {n: int(e) for n, e in exact.items()}
    left = new_total - sum(after.values())
    order = sorted(exact, key=lambda n: (-(exact[n] - int(exact[n])), n))
    for n in order[:left]:
        after[n] += 1
    for n, q in after.items():
        if q > 0:
            book.sleeves[n].shares[ticker] = q
        else:
            book.sleeves[n].shares.pop(ticker, None)
    return {"ticker": ticker, "ratio": float(ratio), "before": dict(sorted(before.items())),
            "after": dict(sorted(after.items())), "total_before": total, "total_after": new_total,
            "fraction": float(total * r - new_total)}


# ------------------------------------------------------------------ checks and reports
def check(book: Book, venue_positions: dict | None = None, exact: bool = True) -> list:
    """problems with the book, [] when sound. venue_positions: what the account holds per symbol; with
    exact=True the book must equal it on every symbol either side holds, else the venue must hold AT
    LEAST the book (an account shared with something else)."""
    out = []
    for s in book.sleeves.values():
        if not math.isfinite(s.cash):
            out.append(f"{s.name}: cash is not finite")
        for sym, q in s.shares.items():
            if not _is_whole(q) or q <= 0:
                out.append(f"{s.name}: {sym} quantity {q!r} is not a positive whole number")
    if venue_positions is not None:
        mine = book.positions()
        for sym in sorted(set(mine) | {k for k, v in venue_positions.items() if v}):
            b, v = mine.get(sym, 0), int(venue_positions.get(sym, 0) or 0)
            if (exact and b != v) or (not exact and v < b):
                out.append(f"{sym}: the book holds {b}, the venue {v}")
    return out


def snapshot(book: Book, prices: dict) -> dict:
    """per-sleeve equity, cash, weights and share of the book at `prices` (MirrorError on a missing price)"""
    rows, total = {}, 0.0
    for name, s in book.sleeves.items():
        eq = equity(s, prices)
        total += eq
        rows[name] = {"equity": eq, "cash": s.cash, "weights": weights(s, prices), "shares": dict(sorted(s.shares.items())),
                      "version": s.version, "last_trade": s.last_trade}
    for r in rows.values():
        r["share_of_book"] = r["equity"] / total if total > 0 else None
    return {"equity": total, "cash": book.cash(), "sleeves": rows}
