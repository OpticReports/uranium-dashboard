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
  than it has (no borrowing, whatever the account type allows).
- A venue order is booked exactly once, at its terminal state, and split across the sleeves that
  asked for it by largest remainder.

Invariants (check(); tests/test_mirror_core.py)
- every share is owned by exactly one sleeve: the sleeves' shares per symbol sum to the book's
- cash moves only by fills (qty x price), commissions, crosses (zero-sum) and transfers (zero-sum)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

SCHEMA = 1
RULE_DAILY, RULE_THRESHOLD = "daily", "threshold"
SELL, BUY = "SELL", "BUY"
TARGET_SUM_TOL = 0.002           # a target vector must sum to 1 within this


class MirrorError(Exception):
    """A request the core refuses: a booking that would corrupt the book."""


@dataclass
class Config:
    cash_reserve_frac: float = 0.003   # share of a sleeve's equity kept uninvested
    buy_cushion: float = 0.003         # buys are costed at ref x (1 + cushion) when sized
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
    "weights", "deltas": {symbol: signed whole shares}}. equity_adj: capital arriving (+) or leaving
    (-) through a transfer in this plan; force: trade whatever the corridor says (a transfer)."""
    eq = equity(sleeve, prices)
    held = weights(sleeve, prices)
    gap = max_gap(target, held)
    base = {"gap": gap, "weights": held, "equity": eq}
    if sleeve.rule == RULE_THRESHOLD and sleeve.corridor and sleeve.shares and not force and gap <= sleeve.corridor:
        return dict(base, action="hold", reason=f"inside the corridor: largest gap {gap:.1%} vs {sleeve.corridor:.0%}",
                    deltas={})
    investable = (eq + equity_adj) * (1.0 - cfg.cash_reserve_frac)
    want = _desired(investable, target, prices)
    floor_usd = max(cfg.min_trade_usd, cfg.min_trade_frac * max(eq, 0.0))
    deltas = {}
    for sym in sorted(set(want) | set(sleeve.shares)):
        have, w = sleeve.shares.get(sym, 0), want.get(sym, 0)
        d = w - have
        if d == 0:
            continue
        if have > 0 and w > 0 and abs(d) * _need(prices, sym) < floor_usd:
            continue                                # a drift trim too small to trade
        deltas[sym] = d
    if not deltas:
        return dict(base, action="hold", reason="at target", deltas={})
    return dict(base, action="trade", reason="to target", deltas=deltas)


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
            plan["sleeves"][name] = {"action": "skip", "reason": f"brain: {why}", "deltas": {}}
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


def size_buys(book: Book, plan: dict, prices: dict | None = None, cfg: Config | None = None) -> list:
    """The venue BUY orders, sized once the sells are booked: each sleeve's asks are scaled down to
    the cash it actually has (costed at ref x (1 + cushion)), then all of them together to the book's
    cash, so the mirror never spends money it does not hold. Stores and returns plan['buys']."""
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
    cost = lambda sym, q: q * _need(px, sym) * (1.0 + cfg.buy_cushion)  # noqa: E731
    sized = {}
    for name, asks in plan["buy_asks"].items():
        want = {s: int(q) for s, q in asks.items() if int(q) > 0}
        need = sum(cost(s, q) for s, q in want.items())
        have = max(book.sleeves[name].cash, 0.0)
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
                     "asks": asks, "ref": _need(px, sym), "applied": False} for sym, asks in sorted(by_sym.items())]
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
