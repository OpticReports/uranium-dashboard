#!/usr/bin/env python3
"""DRY simulator and parity measurement for the IBKR mirror of the Composer book (composer/IBKR_MIRROR.md).

Nothing here trades or holds a broker key. It drives ibkr-executor/app/mirror_core.py UNCHANGED (the
module the executor's mirror manager runs), in the executor's own order: apply_split -> dividend_
receivables -> settle_receivable -> build_plan -> apply_crosses -> book_fill each sell ->
apply_transfers -> size_buys (at each buy's limit) -> book_fill each buy -> finish. So what the dry
run measures is the code that will trade. Read-only toward everything: Yahoo daily bars, FMP 1-minute
bars and dividend / split lists (key FMP_API_KEY, never printed), the shadow ledger and the monitor's
snapshots on disk.

  backfill(mode="close")   every session since 2026-07-15: each engine's decision is the shadow
                           ledger's "target" (the approved tree on that day's CLOSE); reference and
                           fill prices are the day's closes. An engine with no ledger row that day is
                           skipped (it keeps its holdings).
  backfill(mode="minute")  from --minute-start (the book is warmed in close mode up to the session
                           before): the decision is mirror_brain.build(pinned=True) AS OF the decision
                           instant, 15:54:00 ET by default (12:54:00 on a half-day): the END of the
                           decision bar, what shadow_runner.minute_price(day, "15:54") reads. Orders
                           fill at the close of the 1-minute bar that STARTS at that instant (the bar
                           ending 15:55: the executor acts 25-40 s after the instant), or at the day's
                           close when a ticker has no such traded bar (counted); the book is valued at
                           the official close.
  daily()                  ONE session on a persistent book (results/mirror/dry-book.json), the
                           minute-mode step, then PARITY against Composer for that session: holdings
                           after its rebalance and the day's return from the monitor snapshot, and
                           the shadow ledger's status. Idempotent, atomic, never raises.

Orders, as the executor sends them. SELLS are market orders: they fill at the fill price less
slippage. BUYS are marketable LIMIT orders: mirror_core.size_buys sizes each at its limit, the
reference price x (1 + buy_cushion) floored to the venue's tick, with the sleeve's cash reserve held
back; a buy fills (at the fill price plus slippage, never above its limit) only if the fill price is
at or below that limit, else it is UNFILLED: the cash stays in the sleeve and the next session's plan
buys again. (Live, the executor re-quotes each buy after its sells and sets the limit off that later
quote, so it leaves fewer buys unfilled than this rule does; limit_at="fill" models that.)

Costs on every venue order: IBKR tiered commission $0.0035 a share, at least $0.35 an order, at most
1% of the trade's value; slippage SLIP_BPS (2) of notional against the mirror, applied in the fill
price. Internal crosses cost nothing (mirror_core books them at the reference price).

Distributions and splits are the core's accounting. A dividend (shadow_runner.corporate_actions:
Yahoo's events UNION FMP's lists, with pay dates; in minute mode the rows the brain publishes) becomes
a receivable for each sleeve that held the payer at the close before the ex-date; on the first session
on or after the pay date mirror_core.settle_receivable credits the sleeve's cash - under rule
"composer" (the executor's default) only if the sleeve still holds the payer, else the cash LEAKS to
unallocated account cash, which is what Composer's symphonies do; under rule "holder" always. A split
rescales the sleeves' shares (mirror_core.apply_split) before the plan. Each sleeve keeps two return
bases: BOOKED (its equity as the core books it, credits included when they settle; the one compared
with Composer's deposit-adjusted figure) and PRICE (each day's credit taken out of that day's return).

Composer's realised record: the monitor snapshot taken after each close (results/monitor; older ones
from the git history of last-snapshot.json, read-only). A symphony's DAILY RETURN is
deposit_adjusted_value(D) / deposit_adjusted_value(D-1) - 1, Composer's own deposit-adjusted figure,
between snapshots of consecutive sessions; where a session has no snapshot the return is a span of
several sessions and is compared as a span (never split into days). A snapshot taken during the next
session gives holdings only. Days on which a symphony's raw value moved by more than its return
(a deposit, withdrawal or transfer) are flagged.

  mirror_dry.py backfill [--mode close|minute] [--start D] [--end D] [--minute-start D] [--decide HH:MM]
                         [--rule composer|holder] [--cache DIR] [--out FILE]
  mirror_dry.py daily [--date D] [--force] [--book FILE] [--ledger FILE]
The full study (both modes, the decision-time variants, sensitivities, the exhibit's JSON) is
composer/research/mirror/parity_study.py.
"""
import datetime
import glob
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from decimal import ROUND_FLOOR, Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(ROOT, "ibkr-executor", "app"))
import mirror_core as mc  # noqa: E402  the executor's own module, unchanged
import shadow_runner as sr  # noqa: E402

SCHEMA = 2                        # the dry book's file: 2 since the core books distributions (receivables in the state)
CAPITAL = 118_000.0
FRACTIONS = {"HG": 0.29, "KMLM": 0.29, "SLEEVE": 0.27, "HARV": 0.15}       # POLICY targets
START = "2026-07-15"              # the shadow ledger's first session
MINUTE_START = "2026-10-05"
DECIDE = sr._hm(sr._min("16:00") - sr.DECISION_MINUTE)   # 15:54 ET on a full day: the END of the decision bar
VARIANTS = ("15:45", "15:50", "15:55")                   # the other decision instants the study measures
SLIP_BPS = 2.0
COMM_PER_SHARE, COMM_MIN, COMM_CAP = 0.0035, 0.35, 0.01     # IBKR tiered: per share, per order, share of value
DIVIDEND_RULE = "composer"        # the executor's default (mirror_core.DIVIDEND_RULES)
ACTIONS_DAYS = 10                 # dividends and splits read: ex-date within this many calendar days (the brain's window)
HELD_KEEP = 15                    # sessions of sleeve holdings kept, for a dividend that surfaces after its ex-date
TOL = sr.TOL_DAILY                # same holdings: half-L1 distance within 3%
PATH_TOL = sr.TOL_PATH            # a threshold engine traded: its weights moved more than this off the drifted ones
FILL_SANITY = 0.25                # a minute fill further than this from the day's close is not a fill (split, bad print)
FLOW_USD, FLOW_FRAC = 250.0, 0.002    # a raw-value move this far from the deposit-adjusted one is a deposit/transfer
FMP_RATE = 4.0                    # requests a second, at most
FMP_REFUSED = ("401", "402", "403", "429", "limit", "Limit", "unexpected answer", "suspended", "upgrade")
MONITOR_DIR = os.path.join(HERE, "..", "results", "monitor")
OUT_DIR = os.path.join(HERE, "..", "results", "mirror")
BOOK_PATH = os.path.join(OUT_DIR, "dry-book.json")
LEDGER_PATH = os.path.join(OUT_DIR, "dry-ledger.jsonl")
LAST_SNAPSHOT = "composer/results/monitor/last-snapshot.json"
NO_REBALANCE = ("2026-10-26", "2026-10-27", "2026-10-28")
ANNUAL = 252


class Refused(Exception):
    """FMP refused or rate-limited a request: the minute mode stops and keeps what it has"""


# ------------------------------------------------------------------ costs
def commission(qty, price):
    """IBKR tiered commission on one order: $0.0035 a share, at least $0.35, at most 1% of the trade's value"""
    qty = abs(int(qty))
    if qty == 0 or not price or price <= 0:
        return 0.0
    return min(max(COMM_PER_SHARE * qty, COMM_MIN), COMM_CAP * qty * price)


def slipped(side, px, slip_bps):
    """the fill price with slippage against the mirror: a sell fills lower, a buy higher"""
    k = slip_bps / 1e4
    return px * (1 - k) if side == mc.SELL else px * (1 + k)


def tick_floor(price):
    """a BUY limit on the venue's price grid, rounded DOWN ($0.01 from $1, $0.0001 below it) so the
    order can only pay less than it was sized at: the rule of the executor's
    ib_adapter.round_limit_to_tick(price, "BUY") (a gate test holds the two equal). None if unusable"""
    try:
        px = Decimal(str(float(price)))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not px.is_finite() or px <= 0:
        return None
    out = px.quantize(Decimal("0.0001") if px < 1 else Decimal("0.01"), rounding=ROUND_FLOOR)
    return float(out) if out > 0 else None


def rules_from_manifest(cfg_all=None):
    """{engine: {"rule", "corridor"}} for the engines that are not plain daily (KMLM: threshold, 10pp)"""
    cfg_all = cfg_all if cfg_all is not None else sr.load_manifest()
    return {e: {"rule": mc.RULE_THRESHOLD, "corridor": float(c["corridor"])} for e, c in cfg_all.items() if c.get("corridor")}


def seed_book(capital=CAPITAL, fractions=None, rules=None):
    return mc.Book.seed(capital, dict(fractions or FRACTIONS), rules if rules is not None else rules_from_manifest())


def decide_at(d, decide=DECIDE):
    """the decision instant on session d: `decide` is given for a 16:00 close; a half-day keeps the same
    distance to its own close (15:54 -> 12:54 on a 13:00 close)"""
    return sr._hm(sr._min(sr.session_close(d)) - (sr._min("16:00") - sr._min(decide)))


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _pos(x):
    return float(x) if _num(x) and x > 0 else None


# ------------------------------------------------------------------ prices: Yahoo daily
def _yahoo_chart(t, tries=3):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}"
           f"?range=2y&interval=1d&events=div%2Csplit")
    err = None
    for k in range(tries):
        try:
            res = sr._chart(url)
            if res.get("timestamp"):
                return res
            err = "empty series"
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(1 + k)
    raise RuntimeError(f"Yahoo {t}: {err}")


def asof_series(adj, raw, d):
    """(adjusted, raw) closes as Yahoo showed them on session d: nothing after d, and the adjusted
    series rebased so it carries no distribution paid after d (adjusted == raw on the last bar at or
    before d). A replay of d then reads its 1-minute price (raw) against the history a live run saw
    that day; left as fetched today, every bar before d sits lower by the distributions paid since,
    and the replayed day opens with a jump that never happened."""
    keep = sorted(x for x in raw if x <= d and x in adj)
    if not keep:
        return {}, {}
    last = keep[-1]
    c = adj[last] / raw[last] if raw[last] and adj[last] else 1.0
    return {x: adj[x] / c for x in keep}, {x: raw[x] for x in keep}


class Yahoo:
    """Yahoo's 2-year daily chart per ticker, fetched once per run and reused (cache_dir: also kept
    on disk, for a study that is rerun), with FMP's dividend and split lists for the same ticker
    (shadow_runner.fmp_actions; None without a key: Yahoo's events alone).
    daily(t) -> (adjusted, raw, corporate actions): shadow_runner.parse_daily and corporate_actions,
    what preclose.fetch_live gives the brain. live(t, asof) -> the (adjusted, raw, meta) contract of
    preclose.fetch_live for mirror_brain.build's `fetch` seam, as of session `asof` (see asof_series);
    meta carries the chart's own fields and 'corporateActions' (nothing dated after `asof`)."""

    def __init__(self, cache_dir=None, fetch=None, actions=None):
        self.cache_dir, self._fetch = cache_dir, fetch or _yahoo_chart
        # a chart source of the caller's own (a test, a study) never reaches for FMP unless told to
        self._actions = actions if actions is not None else (sr.fmp_actions if fetch is None else (lambda t: None))
        self.res, self.parsed, self.acts, self.lock = {}, {}, {}, threading.Lock()

    def _cached(self, kind, t, get, keep=lambda x: True):
        path = os.path.join(self.cache_dir, kind, f"{t}.json") if self.cache_dir else None
        if path and os.path.isfile(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        got = get(t)
        if path and keep(got):
            _write_atomic(path, json.dumps(got))
        return got

    def chart(self, t):
        with self.lock:
            if t in self.res:
                return self.res[t]
        res = self._cached("yahoo", t, self._fetch)
        with self.lock:
            self.res[t] = res
        return res

    def actions(self, t):
        """FMP's dividend and split lists for t (shadow_runner.parse_actions' shape), or None"""
        with self.lock:
            if t in self.acts:
                return self.acts[t]
        got = self._cached("actions", t, lambda x: {"ticker": x, "actions": self._actions(x)},
                           keep=lambda g: g.get("actions") is not None)        # a failure is asked again next run
        with self.lock:
            self.acts[t] = got.get("actions") if isinstance(got, dict) else None
        return self.acts[t]

    def daily(self, t):
        if t not in self.parsed:
            res, acts = self.chart(t), self.actions(t)
            adj, raw = sr.parse_daily(res, acts)
            ca = sr.corporate_actions(res.get("events") or {}, acts, max(raw)) if raw else {"dividends": [], "splits": [], "fmp": False}
            self.parsed[t] = (adj, raw, ca)
        return self.parsed[t]

    def live(self, t, asof=None):
        adj, raw, ca = self.daily(t)
        if not adj:
            raise RuntimeError(f"Yahoo {t}: empty series")
        if asof:
            adj, raw = asof_series(adj, raw, asof)
            ca = {"dividends": [x for x in ca["dividends"] if x["ex_date"] <= asof],
                  "splits": [x for x in ca["splits"] if x["date"] <= asof], "fmp": ca["fmp"]}
        return dict(adj), dict(raw), dict(self.chart(t).get("meta") or {}, corporateActions=ca)


class Market:
    """closes, corporate actions and the session calendar the simulator runs on. raw: {ticker: {date:
    close}} as the source restates them for later splits; divs: {ticker: {ex-date: amount per share, or
    (amount, pay date)}}; splits: {ticker: [(date, numerator, denominator)]} (new shares per old =
    numerator / denominator). With a Yahoo source, tickers load on demand, with shadow_runner's
    corporate actions (Yahoo's events UNION FMP's lists)."""

    def __init__(self, raw=None, divs=None, calendar=None, yahoo=None, cal_ticker="SPY", splits=None):
        self.raw, self.yahoo, self.cal_ticker = dict(raw or {}), yahoo, cal_ticker
        self._cal, self.bad, self.events = (sorted(calendar) if calendar else None), {}, {}
        for t, by in (divs or {}).items():
            rows = [{"ex_date": x, "pay_date": None if _num(v) else v[1], "amount": float(v if _num(v) else v[0])}
                    for x, v in sorted(by.items())]
            self.events.setdefault(t, {"dividends": [], "splits": []})["dividends"] = rows
        for t, rows in (splits or {}).items():
            self.events.setdefault(t, {"dividends": [], "splits": []})["splits"] = [
                {"date": x, "numerator": float(n), "denominator": float(m)} for x, n, m in sorted(rows)]

    def need(self, tickers):
        for t in sorted(set(tickers)):
            if t in self.raw or t in self.bad or self.yahoo is None:
                continue
            try:
                _, raw, ca = self.yahoo.daily(t)
                self.raw[t], self.events[t] = raw, ca
            except Exception as e:  # noqa: BLE001
                self.bad[t] = " ".join(str(e).split())[:120]

    def calendar(self):
        if self._cal is None:
            self.need([self.cal_ticker])
            src = self.raw.get(self.cal_ticker) or {}
            self._cal = sorted(src) if src else sorted({d for s in self.raw.values() for d in s})
        return self._cal

    def sessions(self, start, end):
        return [d for d in self.calendar() if start <= d <= end]

    def prev(self, d):
        before = [x for x in self.calendar() if x < d]
        return before[-1] if before else None

    def traded_factor(self, t, d):
        """what turns t's price on d, as the source restates it today, into the price it TRADED at:
        new shares per old over the splits after d that the series already carries (dated up to its
        last bar; a split announced for later is not in any price yet). 1.0 without one"""
        k, last = 1.0, max(self.raw.get(t) or {"": 0})
        for x in (self.events.get(t) or {}).get("splits") or []:
            if d < x["date"] <= last:
                k *= x["numerator"] / x["denominator"]
        return k

    def closes(self, d):
        """{ticker: the close it traded at on d} (what shares bought that day were paid for at)"""
        return {t: s[d] * self.traded_factor(t, d) for t, s in self.raw.items() if _pos(s.get(d))}

    def actions(self, d, days=ACTIONS_DAYS):
        """(dividends, splits) of the loaded tickers dated within `days` calendar days up to d, in the
        shape the brain publishes: [{"ticker", "ex_date", "pay_date" | None, "amount"}] (cash per share as
        paid) and [{"ticker", "date", "ratio"}] (new shares per old)"""
        lo = (datetime.date.fromisoformat(d) - datetime.timedelta(days=days)).isoformat()
        divs, splits = [], []
        for t in sorted(self.events):
            for x in self.events[t].get("dividends") or []:
                if lo <= x["ex_date"] <= d:
                    divs.append({"ticker": t, "ex_date": x["ex_date"], "pay_date": x.get("pay_date"),
                                 "amount": round(float(x["amount"]), 6)})
            for x in self.events[t].get("splits") or []:
                if lo <= x["date"] <= d:
                    splits.append({"ticker": t, "date": x["date"],
                                   "ratio": round(float(x["numerator"]) / float(x["denominator"]), 8)})
        return sorted(divs, key=lambda x: (x["ex_date"], x["ticker"])), sorted(splits, key=lambda x: (x["date"], x["ticker"]))


# ------------------------------------------------------------------ prices: FMP 1-minute bars
class Minutes:
    """FMP's 1-minute bars WITH VOLUME (trades) for a ticker-day, one request each: kept in memory,
    and on disk under cache_dir so a rerun costs nothing; throttled to FMP_RATE requests a second.
    A refusal or rate limit raises Refused and is remembered in .refused (the caller stops cleanly);
    any other failure is remembered in .errors. The key never appears in a message."""

    def __init__(self, key=None, cache_dir=None, rate=FMP_RATE, fetch=None, budget=600, clock=time.time, sleep=time.sleep,
                 now=None):
        self.key = key if key is not None else os.environ.get("FMP_API_KEY")
        self.cache_dir, self.rate, self.budget = cache_dir, rate, budget
        self._fetch = fetch or (lambda t, d, k: sr.fetch_minutes(t, d, k, traded=True))
        self.clock, self.sleep, self._now = clock, sleep, now
        self.mem, self.errors, self.refused, self.requests = {}, {}, None, 0
        self.lock, self.tlock, self.next_at = threading.Lock(), threading.Lock(), 0.0

    def _path(self, t, d):
        return os.path.join(self.cache_dir, "fmp", d, f"{t}.json") if self.cache_dir else None

    def _final(self, d):
        """the session d is over (its bars will not change): only then is a day written to disk"""
        now = self._now() if self._now else datetime.datetime.now(datetime.timezone.utc)
        e = sr.et_now(now)
        return d < e.date().isoformat() or e.strftime("%H:%M") >= sr._hm(sr._min(sr.session_close(d)) + 30)

    def get(self, t, d):
        with self.lock:
            if (t, d) in self.mem:
                return self.mem[(t, d)]
        path = self._path(t, d)
        if path and os.path.isfile(path):
            try:
                with open(path) as f:
                    bars = {k: float(v) for k, v in json.load(f)["bars"].items()}
                with self.lock:
                    self.mem[(t, d)] = bars
                return bars
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if self.refused:
            raise Refused(self.refused)
        if not self.key:
            raise Refused("FMP_API_KEY not set")
        with self.tlock:
            now = self.clock()
            wait = self.next_at - now
            self.next_at = max(now, self.next_at) + 1.0 / self.rate
        if wait > 0:
            self.sleep(wait)
        self.requests += 1
        try:
            bars = self._fetch(t, d, self.key)
        except Exception as e:  # noqa: BLE001
            msg = " ".join(str(e).replace(self.key, "***").split())[:160]
            if any(x in msg for x in FMP_REFUSED):
                self.refused = msg
                raise Refused(msg) from None
            self.errors[(t, d)] = msg
            raise RuntimeError(msg) from None
        bars = {k: float(v) for k, v in (bars or {}).items() if not k.startswith("_") and _pos(v)}
        with self.lock:
            self.mem[(t, d)] = bars
        if path and self._final(d):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _write_atomic(path, json.dumps({"ticker": t, "date": d, "bars": bars}, separators=(",", ":")))
        return bars

    def quotes(self):
        """the `quotes` seam of mirror_brain.build / preclose.preview: preclose.minute_quotes itself, on
        this store's cached fetch (None without a key and without a cache: no FMP)"""
        if not self.key and not self.cache_dir:
            return None
        import preclose as pc
        return lambda tickers, now: pc.minute_quotes(tickers, now, self.key or "-", fetch=lambda t, d, k: self.get(t, d),
                                                     budget=self.budget)

    def price_at(self, t, d, hhmm):
        """the last traded price at hh:mm: the close of the latest bar ending at or before it (None if none)"""
        bars = self.get(t, d)
        end = sr._min(hhmm) - 1
        ks = [k for k in bars if sr._min(k) <= end]
        return bars[max(ks, key=sr._min)] if ks else None

    def bar(self, t, d, hhmm):
        """the close of the traded bar that STARTS at hh:mm (None if the ticker did not trade that minute)"""
        return self.get(t, d).get(hhmm)


def _write_atomic(path, text):
    """temp file in the same directory + os.replace: a crash cannot leave a half-written file"""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + ".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


# ------------------------------------------------------------------ the simulator
class Sim:
    """A mirror book stepped one session at a time through mirror_core, with costs, limit buys,
    distributions and splits, in the executor's order.

    rule: the dividend rule (mirror_core.DIVIDEND_RULES; "composer" is the executor's default).
    limit_buys: a buy fills only at or below its limit (False: it fills whatever the price, the
    counterfactual that measures what the rule costs). limit_at: "ref" - the limit is the plan's
    reference price x (1 + cushion), floored to the tick (the paper rule, and the live fallback);
    "fill" - off the fill price itself (the live executor re-quotes each buy after its sells).

    state (persisted by daily()): prev_eq {sleeve: equity at the last close}; idx / idx_gross (booked
    basis, net and before costs) and idx_px / idx_px_gross (price basis) per sleeve, book_idx for the
    book; last_px {ticker: last close seen}; venue {ticker: shares the 'account' holds, kept
    independently of the book so mc.check has something to check against}; receivables (open ones,
    and the last 200 closed); div_seen / splits_applied (ids); unallocated (account cash no sleeve
    owns: leaked distributions, cash in lieu); held {session: {sleeve: {ticker: shares}}} of the last
    HELD_KEEP sessions; last (the last session run)."""

    def __init__(self, book, slip_bps=SLIP_BPS, cfg=None, state=None, rule=DIVIDEND_RULE, limit_buys=True, limit_at="ref"):
        if rule not in mc.DIVIDEND_RULES:
            raise ValueError(f"unknown dividend rule {rule!r}")
        if limit_at not in ("ref", "fill"):
            raise ValueError(f"limit_at must be 'ref' or 'fill', not {limit_at!r}")
        self.book, self.slip_bps, self.cfg = book, float(slip_bps), cfg or mc.Config()
        self.rule, self.limit_buys, self.limit_at = rule, bool(limit_buys), limit_at
        st = state or {}
        one = {n: 1.0 for n in book.sleeves}
        self.prev_eq = dict(st["prev_eq"]) if st.get("prev_eq") else {n: s.cash for n, s in book.sleeves.items() if not s.shares}
        self.idx, self.idx_gross = dict(st.get("idx") or one), dict(st.get("idx_gross") or one)
        self.idx_px, self.idx_px_gross = dict(st.get("idx_px") or one), dict(st.get("idx_px_gross") or one)
        self.book_idx = dict(st.get("book_idx") or {"ret": 1.0, "gross": 1.0, "px": 1.0, "px_gross": 1.0})
        self.last_px = dict(st.get("last_px") or {})
        self.venue = dict(st.get("venue") or book.positions())
        self.cash_low = st.get("cash_low", 0.0)
        self.receivables = [dict(r) for r in st.get("receivables") or []]
        self.div_seen, self.splits_applied = list(st.get("div_seen") or []), list(st.get("splits_applied") or [])
        self.unallocated = float(st.get("unallocated") or 0.0)
        self.held = {d: {n: dict(w) for n, w in by.items()} for d, by in (st.get("held") or {}).items()}
        self.last = st.get("last")

    def state(self):
        closed = [r for r in self.receivables if r.get("status") != "open"]
        return {"prev_eq": dict(self.prev_eq), "idx": dict(self.idx), "idx_gross": dict(self.idx_gross),
                "idx_px": dict(self.idx_px), "idx_px_gross": dict(self.idx_px_gross), "book_idx": dict(self.book_idx),
                "last_px": dict(self.last_px), "venue": dict(self.venue), "cash_low": self.cash_low,
                "receivables": [dict(r) for r in self.receivables if r.get("status") == "open"] + [dict(r) for r in closed[-200:]],
                "div_seen": self.div_seen[-500:], "splits_applied": self.splits_applied[-300:],
                "unallocated": self.unallocated, "last": self.last,
                "held": {d: {n: dict(w) for n, w in by.items()} for d, by in sorted(self.held.items())[-HELD_KEEP:]}}

    # ---- corporate actions: the executor's _apply_splits and _dividends, on the same core calls
    def _splits(self, d, splits, prices, problems):
        """every listed split dated up to d that this book has not applied: the sleeves' shares rescaled
        by mc.apply_split, the 'account' with them; the fractional share's cash in lieu is account cash
        no sleeve owns (the executor books it only when told to). A split dated on or before a session
        the book already ran is NOT applied (it ran on post-split prices): reported, as the executor does"""
        out = []
        for row in splits or []:
            if not isinstance(row, dict):
                continue
            ticker, day, ratio = row.get("ticker"), mc.parse_day(row.get("date")), row.get("ratio")
            if not isinstance(ticker, str) or not ticker or day is None or not _pos(ratio):
                continue
            day = day.isoformat()
            key = mc.split_key(ticker, day)
            if day > d or key in self.splits_applied:
                continue
            self.splits_applied.append(key)
            held = self.book.positions().get(ticker, 0)
            if not held or abs(ratio - 1.0) < 1e-9:
                continue
            if self.last is not None and self.last >= day:
                problems.append(f"split {ticker} x{ratio:g} dated {day} surfaced after the book ran {self.last} on "
                                f"post-split prices: not applied ({held} shares held)")
                continue
            res = mc.apply_split(self.book, ticker, float(ratio))
            if res["total_after"]:
                self.venue[ticker] = res["total_after"]
            else:
                self.venue.pop(ticker, None)
            if _pos(self.last_px.get(ticker)):
                self.last_px[ticker] = self.last_px[ticker] / float(ratio)
            px = _pos((prices or {}).get(ticker)) or _pos(self.last_px.get(ticker)) or 0.0
            owed = res["fraction"] * px
            self.unallocated += owed
            out.append(dict(res, id=key, date=day, cash_in_lieu=round(owed, 4)))
        return out

    def _holdings_before(self, ex_date):
        """{sleeve: {ticker: shares}} at the last recorded close before ex_date ({} when none is kept)"""
        before = [x for x in sorted(self.held) if x < ex_date]
        return self.held[before[-1]] if before else {}

    def _dividends(self, d, dividends, acct):
        """new receivables for every dividend not seen before (shares held at the close before the
        ex-date: the sleeves as they stand before this session's plan when the ex-date is after the
        last session run, else the holdings kept for that day), then the settlement of every open
        receivable due, BEFORE the plan, under self.rule. A paper account's cash always arrives.
        Returns the cash credited to the sleeves"""
        for row in dividends or []:
            dv = mc.clean_dividend(row)
            if dv is None or dv["ex_date"] > d:
                continue
            key = mc.dividend_key(dv["ticker"], dv["ex_date"])
            if key in self.div_seen:
                continue
            self.div_seen.append(key)
            if self.last is None or dv["ex_date"] > self.last:
                holdings = {n: dict(s.shares) for n, s in self.book.sleeves.items()}
            else:
                holdings = self._holdings_before(dv["ex_date"])
            for r in mc.dividend_receivables(holdings, dv):
                r.update(status="open", seen=d, pay_date_given=dv["pay_date_given"])
                self.receivables.append(r)
                a = acct.get(r["sleeve"])
                if a is not None:
                    a["accrued"] += r["total"]
                    a["accrued_by"][r["ticker"]] = round(a["accrued_by"].get(r["ticker"], 0.0) + r["total"], 4)
        credited = 0.0
        for r in self.receivables:
            if r.get("status") != "open" or str(r.get("pay_date") or "9") > d:
                continue
            out = mc.settle_receivable(self.book, r, d, self.rule, cash_arrived=True)
            if isinstance(out.get("held"), bool):
                r["held"] = out["held"]
            act, a = out["action"], acct.get(r["sleeve"])
            if act == "credited":
                r.update(status="credited", settled=d)
                credited += out["amount"]
                if a is not None:
                    a["div"] += out["amount"]
                    a["div_by"][r["ticker"]] = round(a["div_by"].get(r["ticker"], 0.0) + out["amount"], 4)
            elif act == "leaked":
                r.update(status="leaked", settled=d)
                self.unallocated += float(r["total"])
                if a is not None:
                    a["leak"] += float(r["total"])
                    a["leak_by"][r["ticker"]] = round(a["leak_by"].get(r["ticker"], 0.0) + float(r["total"]), 4)
            elif act in ("void", "expired"):
                r.update(status=act, settled=d)
        return credited

    def session(self, d, targets, ref, fills, closes, dividends=None, splits=None, mode="close", fallbacks=None):
        """One session. targets: the brain's {sleeve: {"status", "target", "version"}}; ref: reference
        prices the plan is sized on; fills: {ticker: price before slippage} each venue order fills at;
        closes: the official closes the book is valued at; dividends / splits: the rows the brain
        publishes ([{"ticker", "ex_date", "pay_date", "amount"}], [{"ticker", "date", "ratio"}]); rows
        seen before are ignored. Returns (engine rows, book row)."""
        book, slip = self.book, self.slip_bps
        names = list(book.sleeves)
        acct = {n: {"div": 0.0, "leak": 0.0, "accrued": 0.0, "comm": 0.0, "slip": 0.0, "venue": 0.0, "cross": 0.0,
                    "div_by": {}, "leak_by": {}, "accrued_by": {}} for n in names}
        problems = []
        # 1. corporate actions first, as the executor: splits, new receivables, the settlements due
        split_rows = self._splits(d, splits, ref, problems)
        cash0, unalloc0 = book.cash(), self.unallocated
        credited = self._dividends(d, dividends, acct)
        # 2. the plan, exactly as the executor builds it
        plan = mc.build_plan(book, targets, ref, d, self.cfg)
        mc.apply_crosses(book, plan)
        for c in plan["crosses"]:
            for side in ("sellers", "buyers"):
                for n, q in c[side].items():
                    acct[n]["cross"] += q * c["price"]
        flow, orders = 0.0, []
        for o in plan["sells"]:
            flow += self._fill(o, fills, slip, acct, problems, orders)
        mc.apply_transfers(book, plan)
        limits = {}
        for asks in plan["buy_asks"].values():
            for sym in asks:
                base = (_pos(fills.get(sym)) if self.limit_at == "fill" else None) or _pos(plan["prices"].get(sym))
                lim = tick_floor(mc.buy_limit(base, self.cfg)) if base else None
                if lim:
                    limits[sym] = lim                  # the venue's grid; without one the core's own limit applies
        for o in mc.size_buys(book, plan, cfg=self.cfg, limits=limits):
            flow += self._fill(o, fills, slip, acct, problems, orders)
        mc.finish(book, plan)
        # 3. invariants: every share owned once, the venue agrees, cash moved only by what was booked
        problems += mc.check(book, self.venue)
        want_cash = cash0 + credited + flow
        if not math.isclose(book.cash(), want_cash, rel_tol=0, abs_tol=1e-6):
            problems.append(f"cash {book.cash():.6f} is not the {want_cash:.6f} the fills and credits account for")
        low = min(s.cash for s in book.sleeves.values())
        self.cash_low = min(self.cash_low, low)
        # not a broken invariant, but worth seeing: a sleeve whose cash went below zero (a limit buy cannot do it)
        overspent = {n: round(s.cash, 2) for n, s in book.sleeves.items() if mc.in_debt(s)}
        # 4. value at the official close, on both bases
        self.last_px.update({t: p for t, p in closes.items() if _pos(p)})
        px = self.last_px
        stale = sorted(t for t in book.positions() if not _pos(closes.get(t)))
        if stale:
            problems.append(f"no close on {d} for {', '.join(stale)}: valued at the last close seen")
        open_by = {}
        for r in self.receivables:
            if r.get("status") == "open":
                open_by[r["sleeve"]] = open_by.get(r["sleeve"], 0.0) + float(r["total"])
        unfilled = [o for o in orders if not o["filled"] and o.get("why") == "above its limit"]
        rows, tot, tot_prev, tot_div, tot_cost = [], 0.0, 0.0, 0.0, 0.0
        for n in names:
            s, dec, a = book.sleeves[n], plan["sleeves"].get(n) or {}, acct[n]
            eq = mc.equity(s, px)
            prev = self.prev_eq.get(n, eq)
            cost = a["comm"] + a["slip"]
            ret, ret_gross, ret_px, ret_px_gross = [(x / prev - 1 if prev > 0 else 0.0)
                                                    for x in (eq, eq + cost, eq - a["div"], eq - a["div"] + cost)]
            self.idx[n] = self.idx.get(n, 1.0) * (1 + ret)
            self.idx_gross[n] = self.idx_gross.get(n, 1.0) * (1 + ret_gross)
            self.idx_px[n] = self.idx_px.get(n, 1.0) * (1 + ret_px)
            self.idx_px_gross[n] = self.idx_px_gross.get(n, 1.0) * (1 + ret_px_gross)
            missed = {o["symbol"]: o["asks"][n] for o in unfilled if n in (o.get("asks") or {})}
            rows.append({"date": d, "engine": n, "mode": mode, "action": dec.get("action"), "reason": dec.get("reason"),
                         "gap": _r(dec.get("gap"), 5), "target": dec.get("target"), "version": dec.get("version"),
                         "weights": {t: round(w, 6) for t, w in mc.weights(s, px).items()},
                         "cash_share": _r(s.cash / eq if eq > 0 else None, 5),
                         "equity": round(eq, 2), "equity_prev": round(prev, 2),
                         "index": round(self.idx[n], 8), "index_gross": round(self.idx_gross[n], 8),
                         "index_px": round(self.idx_px[n], 8), "index_px_gross": round(self.idx_px_gross[n], 8),
                         "ret": _r(ret), "ret_gross": _r(ret_gross), "ret_px": _r(ret_px), "ret_px_gross": _r(ret_px_gross),
                         "div": round(a["div"], 2), "div_by": a["div_by"], "div_leaked": round(a["leak"], 2),
                         "leaked_by": a["leak_by"], "div_accrued": round(a["accrued"], 2), "accrued_by": a["accrued_by"],
                         "receivable_open": round(open_by.get(n, 0.0), 2),
                         "commission": round(a["comm"], 4), "slippage": round(a["slip"], 4),
                         "traded": round(a["venue"], 2), "crossed": round(a["cross"], 2), "unfilled": missed})
            self.prev_eq[n] = eq
            tot, tot_prev, tot_div, tot_cost = tot + eq, tot_prev + prev, tot_div + a["div"], tot_cost + cost
        rb = [(x / tot_prev - 1 if tot_prev > 0 else 0.0) for x in (tot, tot + tot_cost, tot - tot_div, tot - tot_div + tot_cost)]
        bi = self.book_idx
        self.book_idx = {"ret": bi["ret"] * (1 + rb[0]), "gross": bi["gross"] * (1 + rb[1]), "px": bi["px"] * (1 + rb[2]),
                         "px_gross": bi["px_gross"] * (1 + rb[3])}
        buys = [o for o in orders if o["side"] == mc.BUY]
        brow = {"date": d, "engine": "BOOK", "mode": mode, "equity": round(tot, 2), "equity_prev": round(tot_prev, 2),
                "ret": _r(rb[0]), "ret_gross": _r(rb[1]), "ret_px": _r(rb[2]), "ret_px_gross": _r(rb[3]),
                "index": round(self.book_idx["ret"], 8), "index_gross": round(self.book_idx["gross"], 8),
                "index_px": round(self.book_idx["px"], 8), "index_px_gross": round(self.book_idx["px_gross"], 8),
                "div": round(tot_div, 2), "div_leaked": round(sum(a["leak"] for a in acct.values()), 2),
                "div_accrued": round(sum(a["accrued"] for a in acct.values()), 2),
                "receivable_open": round(sum(open_by.values()), 2),
                "unallocated": round(self.unallocated, 2), "unallocated_change": round(self.unallocated - unalloc0, 2),
                "commission": round(sum(a["comm"] for a in acct.values()), 4),
                "slippage": round(sum(a["slip"] for a in acct.values()), 4),
                "traded": round(sum(a["venue"] for a in acct.values()), 2),
                "crossed": round(sum(c["qty"] * c["price"] for c in plan["crosses"]), 2),
                "orders": sum(1 for o in orders if o["filled"]), "crosses": len(plan["crosses"]),
                "buys": len(buys), "buys_unfilled": len(unfilled),
                "unfilled": [{k: o.get(k) for k in ("symbol", "qty", "ref", "limit", "px", "asks")} for o in unfilled],
                "splits": split_rows,
                "cash": round(book.cash(), 2), "cash_low": round(low, 2), "overspent": overspent, "order_list": orders,
                "problems": problems}
        if fallbacks is not None:
            brow["fill_fallbacks"] = fallbacks
        self.held[d] = {n: dict(s.shares) for n, s in book.sleeves.items()}
        for old in sorted(self.held)[:-HELD_KEEP]:
            del self.held[old]
        self.last = d
        return rows, brow

    def _fill(self, o, fills, slip, acct, problems, orders):
        """book one venue order at its terminal state and return the cash flow. A SELL is a market order:
        whole, at the fill price less slippage. A BUY is a limit order: whole at the fill price plus
        slippage (never above its limit) when the fill price is at or below the limit, else unfilled"""
        sym, qty, side = o["symbol"], int(o["qty"]), o["side"]
        px = _pos(fills.get(sym))
        limit = _pos(o.get("limit")) if side == mc.BUY and self.limit_buys else None
        rec = {"id": o["id"], "side": side, "symbol": sym, "qty": qty, "filled": 0, "ref": o.get("ref"),
               "px": _r(px, 6), "limit": o.get("limit") if side == mc.BUY else None}
        why = None
        if qty <= 0:
            why = "nothing to fill"
        elif px is None:
            why = "no fill price"
            problems.append(f"no fill price for {sym}: the {side} of {qty} was left unfilled")
        elif limit is not None and px > limit + 1e-9:
            why = "above its limit"
        if why:
            mc.book_fill(self.book, o, 0, None, 0.0)
            orders.append(dict(rec, why=why, asks={k: int(v) for k, v in o["asks"].items()}))
            return 0.0
        price = slipped(side, px, slip)
        if limit is not None:
            price = min(price, limit)
        fee = commission(qty, price)
        split = mc.book_fill(self.book, o, qty, price, fee)
        sign = -1 if side == mc.SELL else 1
        self.venue[sym] = self.venue.get(sym, 0) + sign * qty
        if not self.venue[sym]:
            self.venue.pop(sym)
        names, spent = sorted(split), 0.0
        for i, n in enumerate(names):
            part = fee - spent if i == len(names) - 1 else fee * split[n] / qty
            spent += part
            acct[n]["comm"] += part
            acct[n]["slip"] += split[n] * abs(price - px)
            acct[n]["venue"] += split[n] * price
        orders.append(dict(rec, filled=qty, price=round(price, 6), commission=round(fee, 4)))
        return -sign * qty * price - fee


def _r(x, n=8):
    return round(x, n) if _num(x) else None


# ------------------------------------------------------------------ decisions
def read_shadow(path=None):
    """{(date, engine): row} of the shadow ledger; a later row for the same date and engine supersedes"""
    return {(r["date"], r["engine"]): r for r in sr.read_ledger(path or sr.LEDGER)}


def ledger_targets(shadow, d, engines):
    """close mode: each engine's decision on d is the ledger's target (absent -> no target published)"""
    out = {}
    for e in engines:
        r = shadow.get((d, e))
        if r and isinstance(r.get("target"), dict) and r["target"]:
            out[e] = {"status": "ok", "target": dict(r["target"]), "version": r.get("version")}
    return out


def tree_targets(market_adj, d, engines, cfg_all=None):
    """the approved trees on d's closes (the ledger's own method), for a session the ledger has no row
    for; market_adj: {ticker: {date: adjusted close}}"""
    cfg_all = cfg_all or sr.load_manifest()
    out = {}
    for e in engines:
        era = sr.era_for(cfg_all[e], d) if e in cfg_all else None
        if not era:
            continue
        try:
            _, target, _ = sr.run_engine(market_adj, sr.load_tree(era), d)
        except Exception:  # noqa: BLE001
            target = None
        if target:
            out[e] = {"status": "ok", "target": dict(target), "version": era["version"][:8], "src": "tree"}
    return out


def brain_payload(d, hhmm, yahoo, minutes, build=None):
    """mirror_brain.build(pinned=True): the decision AS OF hh:mm:00 ET on session d, from FMP's traded
    1-minute bars ending at or before that instant (through this store) and Yahoo's history as it stood
    that day (Yahoo.live: nothing after d, FMP's dividend and split lists applied as the brain applies them)"""
    import mirror_brain as mb
    now = mb.parse_at(f"{d} {hhmm}")
    return (build or mb.build)(now, quotes=minutes.quotes() if minutes is not None else None,
                               fetch=lambda t: yahoo.live(t, asof=d), pinned=True)


def minute_prices(d, hhmm, symbols, minutes, market, fill="next", brain_prices=None):
    """(reference prices at the decision instant, fill prices, fallbacks) for the symbols a plan may touch.
    Reference: the brain's own `prices` when its payload carries them (the executor sizes on exactly
    those, so a symbol the brain does not price takes its sleeve out of the plan here too); otherwise
    the last traded minute at or before hh:mm, else the previous close. Fill ("next"): the close of
    the traded bar that starts at hh:mm; a ticker without one, or with a print more than FILL_SANITY
    from the day's close, fills at the day's close and is listed in fallbacks. fill "close": every
    order fills at the official close. Every price is the one the fund TRADED at that day: a replay's
    bars are restated for later splits exactly as the closes are (Market.traded_factor undoes both)."""
    closes, prev = market.closes(d), market.prev(d)
    prev_closes = market.closes(prev) if prev else {}
    ref, fills, fallbacks = {}, {}, []
    published = {t: float(p) for t, p in (brain_prices or {}).items() if _pos(p)} if isinstance(brain_prices, dict) else {}
    for t in sorted(set(symbols)):
        c, k = _pos(closes.get(t)), market.traded_factor(t, d)
        try:
            p_ref, p_bar = minutes.price_at(t, d, hhmm), minutes.bar(t, d, hhmm)
        except Refused:
            raise
        except Exception:  # noqa: BLE001
            p_ref = p_bar = None
        p_ref, p_bar = (p_ref * k if p_ref else None), (p_bar * k if p_bar else None)
        if p_ref is not None and c and abs(p_ref / c - 1) > FILL_SANITY:
            p_ref = None
        r = published[t] * k if t in published else (None if published else (p_ref or _pos(prev_closes.get(t)) or c))
        if r:
            ref[t] = r
        if fill == "close":
            if c:
                fills[t] = c
            continue
        if p_bar is not None and c and abs(p_bar / c - 1) > FILL_SANITY:
            p_bar = None
        if p_bar is not None:
            fills[t] = p_bar
        elif c:
            fills[t] = c
            fallbacks.append(t)
    return ref, fills, fallbacks


def later_fill(t, d, hhmm, limit, minutes, market):
    """would a buy left unfilled at the bar starting hh:mm have filled while it kept working? The
    executor cancels 60 s before the close: the first later traded bar ENDING by then whose close is at
    or below the limit -> {"at": its end "HH:MM", "px"}; None when there is none (or no bars)"""
    try:
        bars = minutes.get(t, d)
    except Exception:  # noqa: BLE001
        return None
    k, lo, hi = market.traded_factor(t, d), sr._min(hhmm) + 1, sr._min(sr.session_close(d)) - 2
    for hm in sorted((x for x in bars if lo <= sr._min(x) <= hi), key=sr._min):
        if bars[hm] * k <= limit + 1e-9:
            return {"at": sr._hm(sr._min(hm) + 1), "px": round(bars[hm] * k, 6)}
    return None


# ------------------------------------------------------------------ Composer's record
def load_snapshots(directory=None, history=False, root=None):
    """the monitor's snapshots, oldest first, one per taken_at: snapshot-*.json and last-snapshot.json
    on disk; history=True adds every committed version of last-snapshot.json (git log / git show,
    read-only)"""
    directory = directory or MONITOR_DIR
    out = {}
    for path in sorted(glob.glob(os.path.join(directory, "snapshot-*.json"))) + [os.path.join(directory, "last-snapshot.json")]:
        try:
            with open(path) as f:
                j = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(j, dict) and isinstance(j.get("taken_at"), str):
            out[j["taken_at"]] = j
    if history:
        root = root or ROOT
        try:
            shas = subprocess.run(["git", "-C", root, "log", "--format=%H", "--", LAST_SNAPSHOT], capture_output=True,
                                  text=True, timeout=60, check=True).stdout.split()
        except Exception:  # noqa: BLE001
            shas = []
        for sha in shas:
            try:
                txt = subprocess.run(["git", "-C", root, "show", f"{sha}:{LAST_SNAPSHOT}"], capture_output=True, text=True,
                                     timeout=60, check=True).stdout
                j = json.loads(txt)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(j, dict) and isinstance(j.get("taken_at"), str):
                out.setdefault(j["taken_at"], j)
    return [out[k] for k in sorted(out)]


def snapshot_session(taken_at, calendar):
    """(session, kind) a snapshot speaks for. 'close': taken on a session day at or after its close;
    'late': taken before the next session opens (evening, weekend, holiday, pre-market) - both carry
    the session's closing values. 'next-day': taken during the next session - holdings only (those
    held since the previous close; the values are intraday). calendar: sorted session dates"""
    try:
        e = sr.et_now(datetime.datetime.fromisoformat(taken_at))
    except (TypeError, ValueError):
        return None, None
    d, hm = e.date().isoformat(), e.strftime("%H:%M")
    cal = set(calendar)
    is_session = d in cal or (not calendar or d > calendar[-1]) and e.weekday() < 5 and d not in sr.NYSE_HOLIDAYS
    if is_session and hm >= sr.session_close(d):
        return d, "close"
    before = [x for x in calendar if x < d]
    prev = before[-1] if before else None
    if prev is None:
        x = e.date()
        while True:
            x -= datetime.timedelta(days=1)
            if x.weekday() < 5 and x.isoformat() not in sr.NYSE_HOLIDAYS:
                prev = x.isoformat()
                break
    return prev, ("next-day" if is_session and hm >= "09:30" else "late")


def composer_record(snaps, calendar, cfg_all=None):
    """{engine: {session: {"dav", "value", "holdings" (weights summing to 1), "taken_at", "kind", "lpc"}}}
    from the monitor's snapshots: per session the last 'close' snapshot, else the first 'late' one, else
    a 'next-day' one (holdings only: "dav" and "value" are None)"""
    cfg_all = cfg_all or sr.load_manifest()
    by_id = {c["symphony"]: e for e, c in cfg_all.items()}
    rank = {"close": 0, "late": 1, "next-day": 2}
    out = {e: {} for e in cfg_all}
    for j in sorted(snaps, key=lambda j: j.get("taken_at") or ""):
        d, kind = snapshot_session(j.get("taken_at"), calendar)
        if not d:
            continue
        for sid, s in (j.get("symphonies") or {}).items():
            e = by_id.get(sid)
            if not e or not isinstance(s, dict):
                continue
            hs = s.get("holdings") or {}
            hs = hs if isinstance(hs, dict) else {x.get("ticker"): x.get("allocation") for x in hs if isinstance(x, dict)}
            hs = {t: float(w) for t, w in hs.items() if isinstance(t, str) and _pos(w)}
            tot = sum(hs.values())
            row = {"dav": _pos(s.get("deposit_adjusted_value")) if kind != "next-day" else None,
                   "value": _pos(s.get("value")) if kind != "next-day" else None,
                   "holdings": {t: round(w / tot, 6) for t, w in sorted(hs.items())} if tot else {},
                   "taken_at": j["taken_at"], "kind": kind,
                   "lpc": s.get("last_percent_change") if _num(s.get("last_percent_change")) and kind == "close" else None}
            old = out[e].get(d)
            if old is None or rank[kind] < rank[old["kind"]] or (kind == old["kind"] == "close"):
                out[e][d] = row                         # close: the latest; late: the first seen stays
    return out


def composer_spans(rec, calendar):
    """[{"d0", "d1", "n" sessions, "ret", "flow"}]: Composer's deposit-adjusted return between each pair of
    successive sessions that have closing values; n == 1 is a daily return. flow: the raw value's move
    beyond that return, when it is large enough to be a deposit, withdrawal or transfer (else 0)"""
    pos = {d: i for i, d in enumerate(calendar)}
    ds = [d for d in sorted(rec) if rec[d].get("dav") and d in pos]
    out = []
    for a, b in zip(ds, ds[1:]):
        r = rec[b]["dav"] / rec[a]["dav"] - 1
        v0, v1 = rec[a].get("value"), rec[b].get("value")
        flow = v1 - v0 * (1 + r) if v0 and v1 else 0.0
        big = abs(flow) > max(FLOW_USD, FLOW_FRAC * (v0 or 0.0))
        out.append({"d0": a, "d1": b, "n": pos[b] - pos[a], "ret": r, "flow": round(flow, 2) if big else 0.0})
    return out


# ------------------------------------------------------------------ parity: decisions
def composer_traded(shadow, raw, d, prev_d, e):
    """did Composer's holdings of engine e change at d's rebalance? True / False, or None when the
    previous session has no holdings on record. Yesterday's holdings drifted to today's closes vs
    today's: more than PATH_TOL apart is a trade"""
    a, b = shadow.get((prev_d, e)) if prev_d else None, shadow.get((d, e))
    if not a or not b or not a.get("live") or not b.get("live") or b.get("live_asof", d) != d:
        return None
    drifted = sr.drift(a["live"], raw, prev_d, d)
    if drifted is None:
        return None
    return sr.distance(drifted, b["live"])[0] > PATH_TOL


def classify_day(row, led, corridor, traded_c, late, apart_prev, stood=()):
    """(agree, dist, class, note) for one engine-day: the mirror's post-trade weights vs Composer's holdings.
    class of a disagreement, in this order: composer-no-rebalance and knife-edge (the ledger says so),
    mirror-skip, decision-minute (minute mode: the mirror's own decision minute gave a different
    answer from the logic on the close: a knife-edge the ledger does not see), corridor-path (a
    threshold engine: one side rebalanced and the other did not, both
    held on different paths since an earlier split, or the mirror stood still on the sessions `stood`
    the ledger has no row for), late-snapshot (Composer's holdings were read
    during the next session, drifted), whole-share (Composer holds the target; the mirror is off it
    by sizing alone), other"""
    live, target = led.get("live") or {}, row.get("target") or led.get("target") or {}
    dist = sr.distance(row.get("weights") or {}, live)[0]
    if dist <= TOL:
        return True, dist, "agree", ""
    status = led.get("status")
    if status == "no-rebalance":
        return False, dist, "composer-no-rebalance", ("Composer made no rebalance attempt (holdings of "
                                                      f"{led.get('live_asof') or 'an earlier day'})")
    if status == "knife-edge":
        edge = led.get("edge") or {}
        return False, dist, "knife-edge", ("the call flips inside the decision window "
                                           f"({edge.get('time') or edge.get('basis') or 'intraday'})")
    if row.get("action") == "skip":
        return False, dist, "mirror-skip", f"the mirror had no decision ({row.get('reason')})"
    own, on_close = row.get("target"), led.get("target")
    if row.get("mode") == "minute" and own and on_close and sr.distance(own, on_close)[0] > TOL:
        return False, dist, "decision-minute", (f"at {row.get('decide') or 'its decision minute'} the logic said {sr.fmt_w(own)} "
                                                f"({row.get('label') or 'no label'}); on the close it said {sr.fmt_w(on_close)}")
    if corridor:
        m_traded = row.get("action") == "trade"
        if traded_c is not None and m_traded != traded_c:
            who = "the mirror rebalanced, Composer did not" if m_traded else "Composer rebalanced, the mirror did not"
            return False, dist, "corridor-path", (f"{who} (mirror gap {100 * (row.get('gap') or 0):.1f}pp vs the "
                                                  f"{100 * corridor:.0f}pp corridor)")
        if apart_prev and not m_traded and traded_c is False:
            return False, dist, "corridor-path", f"both held inside the corridor on the paths split on {apart_prev}"
        if stood and not m_traded and traded_c is None:
            return False, dist, "corridor-path", (f"the mirror stood still on {', '.join(x[5:] for x in stood)} (no ledger row), Composer "
                                                  f"rebalanced meanwhile, and today's target is inside the mirror's corridor")
    if late:
        return False, dist, "late-snapshot", "Composer's holdings were read during the next session (drifted by its moves)"
    if target and sr.distance(target, live)[0] <= TOL:
        return False, dist, "whole-share", ("Composer holds the target; the mirror is off it by whole shares, its cash "
                                            "reserve or a skipped trim")
    return False, dist, "other", (f"mirror {sr.fmt_w(row.get('weights') or {})} vs Composer {sr.fmt_w(live)}; ledger status {status}")


def decision_parity(rows, shadow, market, cfg_all=None, composer=None):
    """Per engine-day: same holdings or not, every disagreement classified; per engine and overall the
    share that agree; the threshold engines' corridor episodes (runs of sessions apart)."""
    cfg_all = cfg_all or sr.load_manifest()
    cal = market.calendar()
    days, apart, out_rows, stood = {}, {}, [], {}
    for r in sorted(rows, key=lambda r: (r["date"], r["engine"])):
        e, d = r["engine"], r["date"]
        led = shadow.get((d, e))
        if not led or not led.get("live"):
            if r.get("action") == "skip" and r.get("weights"):
                stood.setdefault(e, []).append(d)      # invested, and no decision that session
            continue
        corridor = (cfg_all.get(e) or {}).get("corridor")
        prev_d = market.prev(d)
        traded_c = composer_traded(shadow, market.raw, d, prev_d, e)
        snap = ((composer or {}).get(e) or {}).get(d) or {}
        late = snap.get("kind") == "next-day" or (led.get("snapshot") and snapshot_session(led["snapshot"], cal)[1] == "next-day")
        ok, dist, cls, note = classify_day(r, led, corridor, traded_c, late, apart.get(e), stood.pop(e, ()))
        if ok:
            apart.pop(e, None)
        else:
            apart.setdefault(e, d)
        out_rows.append({"date": d, "engine": e, "agree": ok, "dist": round(dist, 4), "class": cls, "note": note,
                         "mirror": r.get("weights"), "composer": led.get("live"), "target": r.get("target"),
                         "action": r.get("action"), "composer_traded": traded_c, "ledger_status": led.get("status"),
                         "apart_since": apart.get(e)})
        days.setdefault(e, []).append(out_rows[-1])
    summary = {}
    order = sorted(days, key=lambda e: (sr.ORDER.index(e) if e in sr.ORDER else len(sr.ORDER), e))
    for e, xs in [(e, days[e]) for e in order] + [("ALL", out_rows)]:
        cls = {}
        for x in xs:
            cls[x["class"]] = cls.get(x["class"], 0) + 1
        n = len(xs)
        summary[e] = {"n": n, "agree": cls.get("agree", 0), "share": round(cls.get("agree", 0) / n, 4) if n else None,
                      "classes": dict(sorted(cls.items()))}
    return {"summary": summary, "days": out_rows, "disagreements": [x for x in out_rows if not x["agree"]]}


def episodes(par_days, diffs, engine):
    """runs of consecutive ledger sessions on which `engine`'s mirror and Composer held different books:
    [{"start", "end" (last session apart), "sessions", "origin" class, "classes", "cost_bps": the sum of the
    daily return differences (mirror - Composer, price basis) on the sessions that followed a session
    apart, "returns_known": how many of those sessions have a Composer daily return}]"""
    xs = [x for x in par_days if x["engine"] == engine]
    out, cur = [], None
    for i, x in enumerate(xs):
        if not x["agree"]:
            if cur is None:
                cur = {"start": x["date"], "origin": x["class"], "classes": [], "sessions": 0, "after": []}
            cur["sessions"] += 1
            cur["end"] = x["date"]
            cur["classes"].append(x["class"])
            if i + 1 < len(xs):
                cur["after"].append(xs[i + 1]["date"])
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    for ep in out:
        known = [diffs[d] for d in ep.pop("after") if d in diffs]
        ep["cost_bps"] = round(sum(known) * 1e4, 1)
        ep["returns_known"] = len(known)
        ep["classes"] = sorted(set(ep["classes"]))
    return out


# ------------------------------------------------------------------ parity: returns
def _stats(xs):
    n = len(xs)
    if not n:
        return {"n": 0, "mean": None, "sd": None, "t": None}
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "mean": m, "sd": sd, "t": m / (sd / math.sqrt(n)) if sd > 0 else None}


def tracking(index, spans, exclude=(), label_of=None, worst=8):
    """Return tracking of a mirror index ({date: level}) against Composer's spans. Daily statistics use
    the one-session spans (difference = mirror - Composer, in bps); the cumulative return of each side
    chains every span, so a gap in the snapshots costs daily observations, not the total. exclude: a
    span touching any of these sessions (after its start, through its end) is left out of both."""
    used, daily = [], []
    for s in spans:
        if s["d0"] not in index or s["d1"] not in index:
            continue
        if any(s["d0"] < x <= s["d1"] for x in exclude):
            continue
        m = index[s["d1"]] / index[s["d0"]] - 1
        row = dict(s, mirror=m, diff=m - s["ret"])
        used.append(row)
        if s["n"] == 1:
            daily.append(row)
    if not used:
        return {"n_daily": 0, "n_spans": 0}
    cum_m = math.prod(1 + x["mirror"] for x in used) - 1
    cum_c = math.prod(1 + x["ret"] for x in used) - 1
    d = [x["diff"] * 1e4 for x in daily]
    st = _stats(d)
    out = {"from": used[0]["d0"], "to": used[-1]["d1"], "n_spans": len(used), "n_daily": len(daily),
           "sessions": sum(x["n"] for x in used),
           "mean_bps": _r(st["mean"], 3), "sd_bps": _r(st["sd"], 3), "t": _r(st["t"], 2),
           "median_bps": _r(sorted(d)[len(d) // 2], 3) if d else None,
           "mean_abs_bps": _r(sum(abs(x) for x in d) / len(d), 3) if d else None,
           "cum_mirror": _r(cum_m, 6), "cum_composer": _r(cum_c, 6), "cum_gap": _r(cum_m - cum_c, 6)}
    if len(daily) > 2:
        a, b = [x["mirror"] for x in daily], [x["ret"] for x in daily]
        ma, mb_ = sum(a) / len(a), sum(b) / len(b)
        va, vb = sum((x - ma) ** 2 for x in a), sum((x - mb_) ** 2 for x in b)
        cov = sum((x - ma) * (y - mb_) for x, y in zip(a, b))
        out["corr"] = _r(cov / math.sqrt(va * vb), 5) if va > 0 and vb > 0 else None
        out["beta"] = _r(cov / vb, 5) if vb > 0 else None
    ranked = sorted(used, key=lambda x: -abs(x["diff"]))[:worst]
    out["worst"] = [{"d0": x["d0"], "date": x["d1"], "n": x["n"], "mirror": _r(x["mirror"], 6), "composer": _r(x["ret"], 6),
                     "diff_bps": round(x["diff"] * 1e4, 1), "cause": label_of(x) if label_of else None} for x in ranked]
    out["series"] = [{"d0": x["d0"], "date": x["d1"], "n": x["n"], "mirror": _r(x["mirror"], 6), "composer": _r(x["ret"], 6),
                      "diff_bps": round(x["diff"] * 1e4, 2), "flow": x.get("flow") or 0.0,
                      "cause": label_of(x) if label_of else None} for x in used]
    return out


def expected_credits(rows, market, engine, receivables=None):
    """Each distribution the mirror sleeve became entitled to, with BOTH readings of where its cash goes:
    the core's (the receivable's own outcome: credited, leaked or still open, and the day it settled)
    and Composer's as OBSERVED (divergence.PAY_LAG, add. 38: the payer held through the fund's pay lag
    -> Composer credits it INSIDE the symphony on session ex+L; else it lands in account cash).
    [{"ex", "pay", "ticker", "usd", "bps", "core", "settled", "treatment", "pay_lag", "credit_on", "pending"}];
    a fund with no observed lag is never given a guessed day"""
    import divergence as dv
    xs = [r for r in rows if r["engine"] == engine]
    dates = [r["date"] for r in xs]
    recs = {(r.get("ticker"), r.get("ex_date")): r for r in receivables or [] if r.get("sleeve") == engine}
    out = []
    for i, r in enumerate(xs):
        for t, usd in (r.get("accrued_by") or {}).items():
            wt = {x["date"]: (x["weights"] or {}).get(t, 0.0) for x in xs[i:i + dv.MAX_PAY_LAG + 1]}
            wt[r["date"]] = max(wt.get(r["date"], 0.0), 0.0)
            # held at the prior close and through the ex-date: the ex-date's own row is after its trade
            treatment, _, need, pending, _, _ = dv.classify_hold(t, wt, dates[i:i + dv.MAX_PAY_LAG + 1])
            lag = dv.PAY_LAG.get(t)
            on = dates[i + lag[0]] if lag and treatment == "HELD_THROUGH" and i + lag[0] < len(dates) else None
            rec = recs.get((t, r["date"])) or {}
            out.append({"ex": r["date"], "pay": rec.get("pay_date"), "ticker": t, "usd": round(usd, 2),
                        "bps": round(usd / r["equity_prev"] * 1e4, 1), "core": rec.get("status"), "settled": rec.get("settled"),
                        "treatment": treatment, "pay_lag": lag[0] if lag else None, "credit_on": on, "pending": bool(pending)})
    return out


def cause_labeller(par_days, rows, engine, credits=None, skipped=()):
    """a one-line cause for a span's return difference, from what is known about its sessions"""
    by = {x["date"]: x for x in par_days if x["engine"] == engine}
    acts = {r["date"]: r for r in rows if r["engine"] == engine}
    cred, ours = {}, {}
    for c in credits or []:
        if c.get("credit_on"):
            cred.setdefault(c["credit_on"], []).append(c)
        if c.get("core") == "credited" and c.get("settled"):
            ours.setdefault(c["settled"], []).append(c)
    order = sorted(acts)

    def label(s):
        inside = [d for d in order if s["d0"] < d <= s["d1"]]
        before = [d for d in order if s["d0"] <= d < s["d1"]]
        why = []
        gaps = [d for d in inside if d in skipped]
        if gaps:
            why.append(f"no ledger row on {', '.join(x[5:] for x in gaps)}: the mirror stood still")
        apart = [(d, by[d]["class"]) for d in before if d in by and not by[d]["agree"]]
        if apart:
            kinds = sorted({c for _, c in apart})
            why.append(f"different holdings into the day ({', '.join(kinds)} on {', '.join(d[5:] for d, _ in apart[:3])})")
        theirs = {(c["ticker"], c["ex"]): c for d in inside for c in cred.get(d, [])}
        mine = {(c["ticker"], c["ex"]): c for d in inside for c in ours.get(d, [])}
        only = [("Composer books", c) for k, c in theirs.items() if k not in mine] + \
               [("the mirror books", c) for k, c in mine.items() if k not in theirs]
        if only:
            why.append("pay-date credit on one side only in the span ("
                       + ", ".join(f"{who} {c['ticker']} ~{c['bps']:.0f} bps" for who, c in only) + ")")
        if s.get("flow"):
            why.append(f"Composer deposit/transfer in the span (${s['flow']:+,.0f})")
        missed = sorted({t for d in before for t in (acts[d].get("unfilled") or {})})
        if missed:
            why.append(f"a limit buy left unfilled into the day ({', '.join(missed)})")
        today = [(d, by[d]["class"]) for d in inside if d in by and not by[d]["agree"]]
        if not why and today:
            why.append(f"the holdings split at this rebalance ({', '.join(sorted({c for _, c in today}))})")
        if not why:
            def rotated(d):
                a = acts.get(d) or {}
                big = (a.get("traded") or 0.0) + (a.get("crossed") or 0.0) > TOL * (a.get("equity_prev") or 0.0) > 0
                return big or bool((by.get(d) or {}).get("composer_traded"))
            if any(rotated(d) for d in inside):
                why.append("rotation day: Composer fills ~15:52-15:53, the mirror at its own fill price")
            else:
                why.append("no trade on either side: Composer's snapshot marks vs official closes")
        return "; ".join(why)
    return label


def _slim(t, drop=("series", "worst")):
    return {k: v for k, v in t.items() if k not in drop}


def engine_parity(rows, book_rows, shadow, market, composer, cfg_all=None, exclude=NO_REBALANCE, skipped=None, since=None,
                  receivables=None):
    """the whole parity block for one simulation: decisions, returns (booked basis: net and before
    costs, with and without the excluded sessions; and the price basis), corridor episodes,
    distributions, costs, idle cash. since: measure from this session on (rows before it only give the
    first return its base). receivables: the simulator's (their outcomes label the distributions)"""
    cfg_all = cfg_all or sr.load_manifest()
    cal = market.calendar()
    engines = sorted({r["engine"] for r in rows}, key=lambda e: sr.ORDER.index(e) if e in sr.ORDER else 9)
    base = max((r["date"] for r in rows if since and r["date"] < since), default=None)
    rows = [r for r in rows if not since or r["date"] >= (base or since)]
    live = [r for r in rows if not since or r["date"] >= since]
    book_live = [b for b in book_rows if not since or b["date"] >= since]
    dec = decision_parity(live, shadow, market, cfg_all, composer)
    out = {"since": since, "decisions": dec["summary"], "disagreements": dec["disagreements"], "engines": {}, "episodes": {}}
    n_sessions = len({r["date"] for r in live})
    yr = ANNUAL / max(n_sessions, 1)
    spans_all, idx_all, idx_gross_all, idx_px_all, w_prev, idle = {}, {}, {}, {}, {}, {}
    for e in engines:
        xs_all = [r for r in rows if r["engine"] == e]
        xs = [r for r in live if r["engine"] == e]
        idx = {r["date"]: r["index"] for r in xs_all}
        idx_g = {r["date"]: r["index_gross"] for r in xs_all}
        idx_px = {r["date"]: r["index_px"] for r in xs_all}
        spans = [s for s in composer_spans((composer or {}).get(e) or {}, cal) if s["d0"] in idx and s["d1"] in idx]
        try:
            credits = [c for c in expected_credits(rows, market, e, receivables) if not since or c["ex"] >= since]
        except Exception:  # noqa: BLE001
            credits = []
        lab = cause_labeller(dec["days"], rows, e, credits, skipped or ())
        net = tracking(idx, spans, label_of=lab)
        ex = tracking(idx, spans, exclude=exclude)
        gross = tracking(idx_g, spans)
        price = tracking(idx_px, spans)
        flows = [s["d1"] for s in spans if s.get("flow")]
        noflow = tracking(idx, spans, exclude=flows)
        diffs = {s["date"]: s["diff_bps"] / 1e4 for s in net.get("series") or [] if s["n"] == 1}
        eq = [r["equity"] for r in xs]
        avg_eq = sum(eq) / len(eq) if eq else 0.0
        comm, slip = sum(r["commission"] for r in xs), sum(r["slippage"] for r in xs)
        traded, crossed = sum(r["traded"] for r in xs), sum(r["crossed"] for r in xs)
        acts = {}
        for r in xs:
            acts[r["action"]] = acts.get(r["action"], 0) + 1
        # idle cash: what the sleeve's uninvested share would have earned at the sleeve's own return
        drag, prev_row = {}, None
        for r in xs_all:
            c = (prev_row or {}).get("cash_share")
            if prev_row is not None and r in xs and c is not None and c < 0.5:
                drag[r["date"]] = (c / (1 - c) * (r["ret"] or 0.0), prev_row["equity"])
            prev_row = r
        shares = [r["cash_share"] for r in xs if r.get("cash_share") is not None]
        idle[e] = drag
        agree = {(c["core"], c["treatment"]): 0 for c in credits}
        for c in credits:
            agree[(c["core"], c["treatment"])] += 1
        usd = lambda pick: round(sum(c["usd"] for c in credits if pick(c)), 2)   # noqa: E731
        out["engines"][e] = {
            "tracking": _slim(net, ("series",)),
            "tracking_ex_no_rebalance": _slim(ex), "tracking_gross": _slim(gross),
            "tracking_price_basis": _slim(price), "tracking_ex_flow_days": _slim(noflow),
            "flow_days": flows, "series": net.get("series") or [],
            "actions": acts, "avg_equity": round(avg_eq, 2), "final_equity": eq[-1] if eq else None,
            "costs": {"commission": round(comm, 2), "slippage": round(slip, 2),
                      "commission_bps_yr": _r(comm / avg_eq * yr * 1e4, 2) if avg_eq else None,
                      "slippage_bps_yr": _r(slip / avg_eq * yr * 1e4, 2) if avg_eq else None,
                      "drag_bps_yr": _r((comm + slip) / avg_eq * yr * 1e4, 2) if avg_eq else None,
                      "turnover_venue_x_yr": _r(traded / avg_eq * yr, 2) if avg_eq else None,
                      "turnover_with_crosses_x_yr": _r((traded + crossed) / avg_eq * yr, 2) if avg_eq else None,
                      "traded": round(traded, 2), "crossed": round(crossed, 2)},
            "cash": {"mean_share": _r(sum(shares) / len(shares), 5) if shares else None,
                     "max_share": _r(max(shares), 5) if shares else None,
                     "drag_bps": _r(sum(v for v, _ in drag.values()) * 1e4, 2),
                     "drag_bps_yr": _r(sum(v for v, _ in drag.values()) * 1e4 * yr, 2)},
            "distributions": {"accrued_usd": round(sum(r["div_accrued"] for r in xs), 2),
                              "credited_usd": round(sum(r["div"] for r in xs), 2),
                              "leaked_usd": round(sum(r["div_leaked"] for r in xs), 2),
                              "open_usd": xs[-1]["receivable_open"] if xs else 0.0,
                              "pct_of_sleeve": _r(sum(r["div_accrued"] for r in xs) / avg_eq, 6) if avg_eq else None,
                              "events": credits,
                              # Composer's own booking as observed (the pay-lag model), for the same entitlements
                              "observed_in_symphony_usd": usd(lambda c: c["treatment"] == "HELD_THROUGH"),
                              "observed_account_cash_usd": usd(lambda c: c["treatment"] == "LEAKED"),
                              "observed_ambiguous_usd": usd(lambda c: c["treatment"] == "AMBIGUOUS"),
                              "core_vs_observed": {f"{k[0]}|{k[1]}": v for k, v in sorted(agree.items(), key=str)}},
            "by_cause": _by_cause(net.get("series") or [])}
        if (cfg_all.get(e) or {}).get("corridor"):
            out["episodes"][e] = episodes(dec["days"], diffs, e)
        spans_all[e], idx_all[e], idx_gross_all[e], idx_px_all[e] = spans, idx, idx_g, idx_px
        w_prev[e] = {r["date"]: r["equity"] for r in xs_all}
    causes = {e: {(x["d0"], x["date"]): x for x in out["engines"][e]["series"]} for e in engines}
    out["book"] = book_parity(book_live, spans_all, idx_all, w_prev, cal, exclude, causes)
    gross = book_parity(book_live, spans_all, idx_gross_all, w_prev, cal, exclude)
    out["book"]["tracking_gross"] = _slim(gross["tracking"], ("worst", "series"))
    out["book"]["tracking_gross_ex_no_rebalance"] = gross["tracking_ex_no_rebalance"]
    price = book_parity(book_live, spans_all, idx_px_all, w_prev, cal, exclude)
    out["book"]["tracking_price_basis"] = _slim(price["tracking"], ("worst", "series"))
    out["book"]["tracking_price_basis_ex_no_rebalance"] = price["tracking_ex_no_rebalance"]
    by_day = {}
    for e, drag in idle.items():
        for d, (v, w) in drag.items():
            a = by_day.setdefault(d, [0.0, 0.0])
            a[0], a[1] = a[0] + v * w, a[1] + w
    tot = sum(a[0] / a[1] for a in by_day.values() if a[1] > 0)
    cs = [b["cash"] / b["equity"] for b in book_live if b["equity"] > 0]
    out["book"]["cash"] = {"mean_share": _r(sum(cs) / len(cs), 5) if cs else None, "max_share": _r(max(cs), 5) if cs else None,
                           "drag_bps": _r(tot * 1e4, 2), "drag_bps_yr": _r(tot * 1e4 * yr, 2)}
    return out


def _by_cause(series):
    """the cumulative return difference split by the first cause named for each span (bps, summed)"""
    out = {}
    for s in series:
        key = (s.get("cause") or "unlabelled").split(";")[0].split(" (")[0].split(":")[0]
        b = out.setdefault(key, {"n": 0, "sum_bps": 0.0, "abs_bps": 0.0})
        b["n"] += 1
        b["sum_bps"] = round(b["sum_bps"] + s["diff_bps"], 2)
        b["abs_bps"] = round(b["abs_bps"] + abs(s["diff_bps"]), 2)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["abs_bps"]))


def book_parity(book_rows, spans, idx, equity, cal, exclude=NO_REBALANCE, causes=None):
    """Book level, like for like: over each stretch between sessions where every engine with a Composer
    record has closing values, both sides' engine returns are combined at the MIRROR's sleeve weights
    at the start of the stretch (so the difference is tracking, not allocation). Composer's own book
    held different engine weights; that comparison is made by the seed sensitivity."""
    by = {e: {(s["d0"], s["d1"]): s for s in ss} for e, ss in spans.items()}
    keys = sorted({k for e in by for k in by[e]})
    used = []
    for k in keys:
        es = [e for e in by if k in by[e] and k[0] in equity[e]]
        if len(es) != sum(1 for e in by if any(a <= k[0] for a, _ in by[e])):
            continue                                   # an engine with a record has no value at this pair: skip it
        tot = sum(equity[e][k[0]] for e in es)
        if tot <= 0:
            continue
        m = sum(equity[e][k[0]] / tot * (idx[e][k[1]] / idx[e][k[0]] - 1) for e in es)
        c = sum(equity[e][k[0]] / tot * by[e][k]["ret"] for e in es)
        part = {e: equity[e][k[0]] / tot * (idx[e][k[1]] / idx[e][k[0]] - 1 - by[e][k]["ret"]) for e in es}
        top = max(part, key=lambda e: abs(part[e]))
        why = ((causes or {}).get(top) or {}).get(k) or {}
        used.append({"d0": k[0], "d1": k[1], "n": by[es[0]][k]["n"], "ret": c, "mirror": m, "engines": len(es),
                     "cause": f"{top} ({part[top] * 1e4:+.0f} bps of the book): {why.get('cause')}" if why.get("cause") else None,
                     "parts_bps": {e: round(v * 1e4, 1) for e, v in part.items()}})
    level, index, chain = 1.0, {}, used
    for u in used:                                     # a break in the chain restarts at the running level
        level = index.setdefault(u["d0"], level) * (1 + u["mirror"])
        index[u["d1"]] = level
    spans_b = [{"d0": u["d0"], "d1": u["d1"], "n": u["n"], "ret": u["ret"]} for u in chain]
    why = {(u["d0"], u["d1"]): u.get("cause") for u in chain}
    parts = {(u["d0"], u["d1"]): u["parts_bps"] for u in chain}
    t = tracking(index, spans_b, label_of=lambda x: why.get((x["d0"], x["d1"])))
    for x in t.get("series") or []:
        x["parts_bps"] = parts.get((x["d0"], x["date"]))
    tx = tracking(index, spans_b, exclude=exclude)
    eq = [r["equity"] for r in book_rows]
    avg = sum(eq) / len(eq) if eq else 0.0
    yr = ANNUAL / max(len(book_rows), 1)
    comm, slip = sum(r["commission"] for r in book_rows), sum(r["slippage"] for r in book_rows)
    traded, crossed = sum(r["traded"] for r in book_rows), sum(r["crossed"] for r in book_rows)
    missed = [dict(u, date=r["date"]) for r in book_rows for u in r.get("unfilled") or []]
    return {"tracking": _slim(t, ("series",)),
            "tracking_ex_no_rebalance": _slim(tx),
            "series": t.get("series") or [], "sessions": len(book_rows), "avg_equity": round(avg, 2),
            "final_equity": eq[-1] if eq else None,
            "mirror_cum": _r(book_rows[-1]["index"] / book_rows[0]["index"] * (1 + book_rows[0]["ret"]) - 1, 6) if eq else None,
            "mirror_cum_px": _r(book_rows[-1]["index_px"] / book_rows[0]["index_px"] * (1 + book_rows[0]["ret_px"]) - 1, 6) if eq else None,
            "mirror_cum_gross": _r(book_rows[-1]["index_gross"] / book_rows[0]["index_gross"] * (1 + book_rows[0]["ret_gross"]) - 1, 6)
            if eq else None,
            "costs": {"commission": round(comm, 2), "slippage": round(slip, 2),
                      "commission_bps_yr": _r(comm / avg * yr * 1e4, 2) if avg else None,
                      "slippage_bps_yr": _r(slip / avg * yr * 1e4, 2) if avg else None,
                      "drag_bps_yr": _r((comm + slip) / avg * yr * 1e4, 2) if avg else None,
                      "turnover_venue_x_yr": _r(traded / avg * yr, 2) if avg else None,
                      "turnover_with_crosses_x_yr": _r((traded + crossed) / avg * yr, 2) if avg else None,
                      "orders": sum(r["orders"] for r in book_rows),
                      "orders_per_session": _r(sum(r["orders"] for r in book_rows) / max(len(book_rows), 1), 2),
                      "sessions_with_a_cross": sum(1 for r in book_rows if r["crosses"]),
                      "crosses": sum(r["crosses"] for r in book_rows), "crossed": round(crossed, 2), "traded": round(traded, 2)},
            "limit_buys": {"buy_orders": sum(r.get("buys") or 0 for r in book_rows), "unfilled_orders": len(missed),
                           "unfilled_legs": sum(len(u.get("asks") or {}) for u in missed),
                           "sessions": len({u["date"] for u in missed}),
                           "unfilled_usd": round(sum(u["qty"] * (u.get("px") or 0.0) for u in missed), 2),
                           "share_of_buy_orders": _r(len(missed) / max(sum(r.get("buys") or 0 for r in book_rows), 1), 5)},
            "distributions": {"accrued_usd": round(sum(r["div_accrued"] for r in book_rows), 2),
                              "credited_usd": round(sum(r["div"] for r in book_rows), 2),
                              "leaked_usd": round(sum(r["div_leaked"] for r in book_rows), 2),
                              "open_usd": book_rows[-1]["receivable_open"] if book_rows else 0.0,
                              "unallocated_usd": book_rows[-1]["unallocated"] if book_rows else 0.0,
                              "accrued_bps_yr": _r(sum(r["div_accrued"] for r in book_rows) / avg * yr * 1e4, 2) if avg else None,
                              "leaked_bps_yr": _r(sum(r["div_leaked"] for r in book_rows) / avg * yr * 1e4, 2) if avg else None},
            "problems": [f"{r['date']}: {p}" for r in book_rows for p in r["problems"]],
            "overspent": [{"date": r["date"], **r["overspent"]} for r in book_rows if r.get("overspent")],
            "cash_low": min((r["cash_low"] for r in book_rows), default=None),
            "book_cash_low": min((r["cash"] for r in book_rows), default=None)}


# ------------------------------------------------------------------ backfill
def backfill(start=START, end=None, mode="close", *, minute_start=MINUTE_START, decide=DECIDE, fill="next",
             slip_bps=SLIP_BPS, capital=CAPITAL, fractions=None, shadow=None, market=None, yahoo=None, minutes=None,
             build=None, composer=None, snapshots=None, cfg=None, cache=None, fill_gaps=False, parity=True, parity_from=None,
             rule=DIVIDEND_RULE, limit_buys=True, limit_at="ref", log=None):
    """Replay the mirror over [start, end] and measure it against Composer.

    mode "close": the decision is the shadow ledger's target for the engine-day, at the day's closes.
    mode "minute": close mode up to the session before minute_start (the book arrives invested, its
    corridor state included), then mirror_brain.build(pinned=True) AS OF `decide` ET (the instant: bars
    ending at or before it) with minute fills (fill "next": the bar starting at that instant; "close":
    the official close). rule: the dividend rule ("composer", the executor's default, or "holder").
    limit_buys / limit_at: the buy-limit rule (see Sim). fill_gaps: on a session the ledger has no row
    for, decide from the approved tree on that day's closes instead of standing still. Seams (tests,
    studies): shadow {(date, engine): row}, market, yahoo, minutes, build, composer (composer_record's
    shape) or snapshots; cache: a directory for Yahoo and FMP responses. Returns {"rows", "book",
    "parity", "book_final", "sessions", "minute", "receivables", "unfilled", ...}."""
    log = log or (lambda *_: None)
    cfg_all = sr.load_manifest()
    shadow = shadow if shadow is not None else read_shadow()
    end = end or max((d for d, _ in shadow), default=start)
    if market is None:
        yahoo = yahoo or Yahoo(cache)
        market = Market(yahoo=yahoo)
    yahoo = yahoo or market.yahoo
    if yahoo is None and (fill_gaps or (mode == "minute" and build is None)):
        raise ValueError("the brain and the gap fill read Yahoo's history: pass yahoo, or a market built on one")
    fractions = dict(fractions or FRACTIONS)
    engines = list(fractions)
    held = {t for (d, e), r in shadow.items() if start <= d <= end for k in ("target", "live") for t in (r.get(k) or {})}
    market.need(held)
    sessions = market.sessions(start, end)
    if not sessions:
        raise ValueError(f"no sessions between {start} and {end}")
    if mode == "minute" and minutes is None:
        minutes = Minutes(cache_dir=cache)
    adj = None
    sim = Sim(seed_book(capital, fractions, rules_from_manifest(cfg_all)), slip_bps, cfg, rule=rule, limit_buys=limit_buys,
              limit_at=limit_at)
    rows, book_rows, skipped, unfilled = [], [], [], []
    info = {"start": minute_start, "decide": decide, "fill": fill, "covered": 0, "fallbacks": 0, "fallback_tickers": {},
            "orders": 0, "stopped": None, "unavailable": [], "unpriced_skips": [], "labels": {},
            "events_from_the_brain": 0, "events_the_brain_lacked": []} if mode == "minute" else None
    for d in sessions:
        minute = mode == "minute" and d >= minute_start
        fallbacks, hh = None, None
        if minute:
            hh = decide_at(d, decide)
            try:
                before = dict(getattr(minutes, "errors", None) or {})
                payload = brain_payload(d, hh, yahoo, minutes, build)
                if getattr(minutes, "refused", None):
                    raise Refused(minutes.refused)
                if (getattr(minutes, "errors", None) or {}) != before:   # a transient failure: once more on the cached day
                    payload = brain_payload(d, hh, yahoo, minutes, build)
                targets = payload.get("engines") or {}
                syms = set(sim.book.positions())
                for r in targets.values():
                    syms |= set((r or {}).get("target") or {})
                market.need(syms)
                ref, fills, fallbacks = minute_prices(d, hh, syms, minutes, market, fill, payload.get("prices"))
            except Refused as e:
                info["stopped"] = f"FMP refused on {d}: {e}"
                log(f"minute mode stopped on {d}: {e}")
                break
            bad = [e for e in engines if (targets.get(e) or {}).get("status") != "ok"]
            if bad:
                info["unavailable"].append({"date": d, "engines": bad, "why": (targets.get(bad[0]) or {}).get("note")
                                            or (payload.get("problems") or [None])[0]})
            for e in engines:
                lab = (targets.get(e) or {}).get("label")
                if lab:
                    info["labels"].setdefault(e, {}).setdefault(lab, 0)
                    info["labels"][e][lab] += 1
        else:
            targets = ledger_targets(shadow, d, engines)
            missing = [e for e in engines if e not in targets and any((x, e) in shadow for x in sessions if x < d)]
            if missing and fill_gaps:
                if adj is None:
                    adj = _adjusted(yahoo, cfg_all, sessions)
                targets.update(tree_targets(adj, d, missing, cfg_all))
            if not targets:
                skipped.append(d)
            ref = fills = None
        closes = market.closes(d)
        if not minute:
            ref = fills = closes
        divs, splits = market.actions(d)
        if minute and isinstance(payload.get("dividends"), list):      # the rows the executor is given
            mine, held_now = divs, set(sim.book.positions())
            divs, splits = payload["dividends"], payload.get("splits") or []
            have = {(x.get("ticker"), x.get("ex_date")) for x in divs if isinstance(x, dict)}
            info["events_from_the_brain"] += 1
            info["events_the_brain_lacked"] += [dict(x, session=d) for x in mine
                                                if x["ticker"] in held_now and (x["ticker"], x["ex_date"]) not in have]
        er, br = sim.session(d, targets, ref, fills, closes, divs, splits, "minute" if minute else "close", fallbacks)
        for u in br["unfilled"]:
            over = (u["px"] / u["limit"] - 1) * 1e4 if u.get("px") and u.get("limit") else None
            unfilled.append(dict(u, date=d, usd=round(u["qty"] * (u.get("px") or 0.0), 2), over_limit_bps=_r(over, 1),
                                 ref_to_fill_bps=_r((u["px"] / u["ref"] - 1) * 1e4, 1) if u.get("px") and u.get("ref") else None,
                                 later=later_fill(u["symbol"], d, hh, u["limit"], minutes, market) if minute and fill == "next" else None))
        if minute:
            info["covered"] += 1
            used = [o["symbol"] for o in br["order_list"] if o["filled"] and o["symbol"] in (fallbacks or [])]
            info["fallbacks"] += len(used)
            info["orders"] += br["orders"]
            for t in used:
                info["fallback_tickers"][t] = info["fallback_tickers"].get(t, 0) + 1
            br["fill_fallbacks"] = used
            for r in er:
                p = (payload.get("engines") or {}).get(r["engine"]) or {}
                r.update(label=p.get("label"), brain=p.get("status"), decide=hh)
                if r["action"] == "skip" and p.get("status") == "ok":
                    info["unpriced_skips"].append({"date": d, "engine": r["engine"], "reason": r["reason"]})
        rows += er
        book_rows.append(br)
        log(f"{d} {'minute' if minute else 'close'}: " + " ".join(f"{r['engine']}:{r['action']}" for r in er)
            + (f" UNFILLED {','.join(u['symbol'] for u in br['unfilled'])}" if br["unfilled"] else ""))
    out = {"mode": mode, "start": start, "end": sim.last, "sessions": [b["date"] for b in book_rows], "slip_bps": slip_bps,
           "capital": capital, "fractions": fractions, "fill_gaps": fill_gaps, "skipped_sessions": skipped,
           "rule": rule, "limit_buys": limit_buys, "limit_at": limit_at, "buy_cushion": sim.cfg.buy_cushion,
           "cash_reserve_frac": sim.cfg.cash_reserve_frac,
           "rows": rows, "book": book_rows, "book_final": sim.book.to_dict(), "state": sim.state(),
           "receivables": [dict(r) for r in sim.receivables], "unallocated": round(sim.unallocated, 2), "unfilled": unfilled,
           "splits_applied": [x for b in book_rows for x in b["splits"]],
           "minute": info, "unpriced": dict(market.bad)}
    if parity and book_rows:
        if composer is None:
            snaps = snapshots if snapshots is not None else load_snapshots(history=True)
            composer = composer_record(snaps, market.calendar(), cfg_all)
        since = parity_from or (minute_start if mode == "minute" else None)
        out["parity"] = engine_parity(rows, book_rows, shadow, market, composer, cfg_all, skipped=skipped, since=since,
                                      receivables=sim.receivables)
    return out


def _adjusted(yahoo, cfg_all, sessions):
    """{ticker: {date: adjusted close}} for every ticker the approved trees read over the sessions"""
    tick = set()
    for cfg in cfg_all.values():
        for era in sr.eras_between(cfg, sessions[0], sessions[-1]):
            tick |= sr.tree_tickers(sr.load_tree(era))
    out = {}
    for t in sorted(tick):
        try:
            out[t] = yahoo.daily(t)[0]
        except Exception:  # noqa: BLE001
            continue
    return out


# ------------------------------------------------------------------ the daily DRY step
def _load_json(path):
    with open(path) as f:
        return json.load(f)


def read_dry_ledger(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get("date"), str):
                    out.append(r)
    except FileNotFoundError:
        pass
    return out


def composer_day(d, calendar, directory=None, cfg_all=None, snaps=None):
    """Composer on session d from the snapshots ON DISK: {engine: {"holdings", "ret", "basis"}} or {} when
    no snapshot speaks for d. ret: deposit-adjusted value against the previous session's snapshot
    ("dav"); without that snapshot, Composer's own last_percent_change ("lpc", rounded to 1 bp)."""
    snaps = snaps if snaps is not None else load_snapshots(directory)
    cal = sorted(set(calendar) | {d})
    rec = composer_record(snaps, cal, cfg_all)
    prev = [x for x in cal if x < d]
    out = {}
    for e, by in rec.items():
        s = by.get(d)
        if not s:
            continue
        p = by.get(prev[-1]) if prev else None
        if s.get("dav") and p and p.get("dav"):
            ret, basis = s["dav"] / p["dav"] - 1, "dav"
        elif s.get("lpc") is not None:
            ret, basis = float(s["lpc"]), "lpc"
        else:
            ret, basis = None, None
        out[e] = {"holdings": s["holdings"], "ret": ret, "basis": basis, "kind": s["kind"], "taken_at": s["taken_at"]}
    return out


def daily(date=None, book_path=BOOK_PATH, ledger_path=LEDGER_PATH, force=False, *, now=None, yahoo=None, minutes=None,
          build=None, market=None, snapshot_dir=None, shadow_path=None, decide=DECIDE, slip_bps=SLIP_BPS, capital=CAPITAL,
          fractions=None, cfg=None, rule=DIVIDEND_RULE):
    """ONE session's DRY step on the persistent book, then parity against Composer. To be run after the
    session's close (the day's official closes value the book). The decision is the brain's pinned build
    AS OF `decide` (15:54:00 ET; 12:54:00 on a half-day), the fills the bar ending a minute later, buys
    as limit orders, dividends and splits from the rows the brain publishes, settled under `rule`.
    Returns (lines, alerts): 2-3 short report lines, and an alert for every MISMATCH (the mirror's
    post-trade weights more than 3% half-L1 from Composer's holdings with no knife-edge or no-rebalance
    in the shadow ledger to explain it) or failure to run. A date already in the ledger is skipped
    unless force (which re-runs the book's LAST session from the state saved before it). Never raises."""
    try:
        return _daily(date, book_path, ledger_path, force, now, yahoo, minutes, build, market, snapshot_dir, shadow_path,
                      decide, slip_bps, capital, fractions, cfg, rule)
    except BaseException as e:  # noqa: BLE001  the monitor must go on
        if isinstance(e, KeyboardInterrupt):
            raise
        why = " ".join(str(e).split())[:200] or type(e).__name__
        key = os.environ.get("FMP_API_KEY")
        if key:
            why = why.replace(key, "***")
        msg = f"MIRROR DRY FAILED — {date or 'today'}: {type(e).__name__}: {why}. The dry book was left as it was."
        return [f"mirror dry {date or ''}: failed ({type(e).__name__})".replace("  ", " ")], [msg]


def _daily(date, book_path, ledger_path, force, now, yahoo, minutes, build, market, snapshot_dir, shadow_path, decide,
           slip_bps, capital, fractions, cfg, rule):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cfg_all = sr.load_manifest()
    d = date or sr.expected_session(now)
    datetime.date.fromisoformat(d)
    fractions = dict(fractions or FRACTIONS)
    engines = list(fractions)
    led = read_dry_ledger(ledger_path)
    done = {r["date"] for r in led}
    saved = _load_json(book_path) if os.path.isfile(book_path) else None
    if saved is not None and saved.get("schema") != SCHEMA:
        raise ValueError(f"dry book schema {saved.get('schema')!r} is not {SCHEMA}")
    at = (saved or {}).get("session")
    if d in done and (at or "") >= d and not force:
        return [f"mirror dry {d}: already in the ledger; nothing done"], []
    if saved is not None and at and d < at:
        return [f"mirror dry {d}: the book is already at {at}"], \
               [f"MIRROR DRY NOT RUN — {d} is before the book's last session {at}; an older session cannot be re-run."]
    if saved is not None and at == d:                 # force, or a run that died between the book and the ledger
        base = saved.get("before")
        if base is None:
            saved = None
        else:
            saved = dict(saved, book=base["book"], state=base["state"], session=base.get("session"))
    if saved is None:
        book, state, seeded = seed_book(capital, fractions, rules_from_manifest(cfg_all)), None, d
    else:
        book, state, seeded = mc.Book.from_dict(saved["book"]), saved.get("state"), saved.get("seeded_on")
    before = {"book": book.to_dict(), "state": Sim(book, slip_bps, cfg, state, rule=rule).state(),
              "session": (saved or {}).get("session")}
    sim = Sim(book, slip_bps, cfg, state, rule=rule)
    last = (saved or {}).get("session")
    sim.last = sim.last or last
    if market is None:
        yahoo = yahoo or Yahoo()
        market = Market(yahoo=yahoo)
    minutes = minutes if minutes is not None else Minutes()
    market.need(set(book.positions()) | {market.cal_ticker})
    cal = market.calendar()
    if d not in cal:
        raise RuntimeError(f"Yahoo has no close for {d} yet (latest {cal[-1] if cal else 'none'})")
    hh = decide_at(d, decide)
    payload = brain_payload(d, hh, yahoo, minutes, build)
    if getattr(minutes, "refused", None):
        raise Refused(f"FMP refused: {minutes.refused}")
    targets = payload.get("engines") or {}
    syms = set(book.positions())
    for r in targets.values():
        syms |= set((r or {}).get("target") or {})
    market.need(syms)
    ref, fills, fallbacks = minute_prices(d, hh, syms, minutes, market, "next", payload.get("prices"))
    divs, splits = market.actions(d)
    if isinstance(payload.get("dividends"), list):     # the rows the executor is given (every era's tickers)
        divs, splits = payload["dividends"], payload.get("splits") or []
    er, br = sim.session(d, targets, ref, fills, market.closes(d), divs, splits, "minute", fallbacks)
    used = [o["symbol"] for o in br["order_list"] if o["filled"] and o["symbol"] in fallbacks]
    br["fill_fallbacks"] = used
    # parity against Composer for this session
    shadow = read_shadow(shadow_path)
    comp = composer_day(d, cal, snapshot_dir, cfg_all)
    alerts, same, n_cmp, diffs = [], 0, 0, []
    unavailable = [e for e in engines if (targets.get(e) or {}).get("status") != "ok"]
    if unavailable:
        why = (targets.get(unavailable[0]) or {}).get("note") or (payload.get("problems") or [None])[0] or "no decision"
        alerts.append(f"MIRROR DRY NO DECISION — {d} {hh} ET: {', '.join(unavailable)} had no target from the brain "
                      f"({' '.join(str(why).split())[:160]}); those sleeves stood still.")
    for r in er:
        e = r["engine"]
        p, c, s = targets.get(e) or {}, comp.get(e), shadow.get((d, e)) or {}
        r.update(decide=hh, label=p.get("label"), brain=p.get("status"), shadow=s.get("status"))
        if r["action"] == "skip" and p.get("status") == "ok":
            alerts.append(f"MIRROR DRY SLEEVE LEFT OUT — {e} on {d}: the brain decided ({sr.fmt_w(p.get('target') or {})}) but the "
                          f"plan skipped the sleeve: {r['reason']}. The executor would skip it the same way, every session, "
                          f"until that is fixed.")
        if not c:
            r["parity"] = "no Composer snapshot"
            continue
        dist = sr.distance(r["weights"], c["holdings"])[0]
        n_cmp += 1
        r.update(composer=c["holdings"], composer_ret=_r(c["ret"]), composer_ret_basis=c["basis"], dist=round(dist, 4))
        if c["ret"] is not None and c["kind"] != "next-day" and last is not None and last == market.prev(d):
            # one session on both sides only: not on the seeding day (the book was cash until its fills),
            # nor after a session the dry step did not run
            r["diff_bps"] = round((r["ret"] - c["ret"]) * 1e4, 1)      # booked basis: credits in when they settle
            diffs.append((e, r["diff_bps"]))
        if dist <= TOL:
            r["parity"] = "same"
            same += 1
        elif s.get("status") in ("knife-edge", "no-rebalance"):
            r["parity"] = f"explained ({s['status']})"
        else:
            r["parity"] = "MISMATCH"
            flip = ""
            if r.get("target") and s.get("target") and sr.distance(r["target"], s["target"])[0] > TOL:
                flip = (f" At {hh} the logic said {sr.fmt_w(r['target'])} ({p.get('label') or 'no label'}); on the close it "
                        f"says {sr.fmt_w(s['target'])}: the call flipped after the mirror's decision minute.")
            if r["action"] == "hold" and "corridor" in (r.get("reason") or ""):
                flip += f" The mirror's sleeve held {r['reason']}: the two books may be on different corridor paths."
            alerts.append(f"MIRROR MISMATCH — {e} on {d}: the mirror ({r['action']}, decided {hh} ET) holds "
                          f"{sr.fmt_w(r['weights'])}; Composer holds {sr.fmt_w(c['holdings'])} (half-L1 {dist:.1%}). The shadow "
                          f"ledger says {s.get('status') or 'nothing for this session'}: no knife-edge or no-rebalance explains "
                          f"it.{flip} DRY only; no order exists.")
    if br["problems"]:
        alerts.append(f"MIRROR DRY BOOK PROBLEM — {d}: " + "; ".join(br["problems"])[:300])
    br.update(decide=hh, seeded_on=seeded, rule=rule,
              brain={"asof_et": payload.get("asof_et"), "pinned": payload.get("pinned"), "replay": payload.get("replay"),
                     "decision_bar": payload.get("decision_bar"), "quotes": payload.get("quotes"),
                     "problems": payload.get("problems")},
              parity={"compared": n_cmp, "same": same}, alerts=len(alerts))
    # the book first (it remembers the state before this session), then the ledger
    _write_atomic(book_path, json.dumps({"schema": SCHEMA, "kind": "composer-mirror-dry-book", "capital": capital,
                                         "fractions": fractions, "rule": rule, "seeded_on": seeded, "session": d,
                                         "book": book.to_dict(), "state": sim.state(), "before": before}, indent=1))
    keep = [r for r in led if r["date"] != d]
    _write_atomic(ledger_path, "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in keep + er + [br]))
    acts = " | ".join(f"{r['engine']} {r['action']}" + (f" -> {sr.fmt_w(r['weights'])}" if r["action"] == "trade" else "")
                      for r in er)
    missed = [f"{u['symbol']} x{u['qty']} (limit {u['limit']:.2f}, bar {u['px']:.2f})" for u in br["unfilled"]]
    lines = [f"MIRROR DRY {d} (decided {hh} ET): {acts}; {br['orders']} order(s), {br['crosses']} cross(es), costs "
             f"${br['commission'] + br['slippage']:.2f}" + (f", {len(used)} fill(s) at the close ({', '.join(used)})" if used else "")
             + (f"; {len(missed)} limit buy(s) UNFILLED, cash kept: {', '.join(missed)}" if missed else ""),
             f"book ${br['equity']:,.0f} ({br['ret']:+.2%} day"
             + (f"; distributions credited ${br['div']:,.2f}" if br["div"] else "")
             + (f"; ${br['div_leaked']:,.2f} left unallocated (payer no longer held on the pay date)" if br["div_leaked"] else "")
             + (f"; ${br['receivable_open']:,.2f} receivable" if br["receivable_open"] else "") + ")"
             + ("; a sleeve's cash is below zero: "
                + ", ".join(f"{n} ${v:,.2f}" for n, v in br["overspent"].items()) if br["overspent"] else "")]
    if n_cmp:
        lines.append(f"parity vs Composer: {same} of {n_cmp} engines hold the same"
                     + ("; day return, mirror - Composer: " + ", ".join(f"{e} {x:+.0f} bps" for e, x in diffs) if diffs else "")
                     + ("; seeded today, so no day return to compare" if last is None else ""))
    else:
        lines.append(f"parity vs Composer: no snapshot for {d} on disk yet")
    return lines, alerts


# ------------------------------------------------------------------ CLI
def _summary(res):
    p = res.get("parity") or {}
    m = res.get("minute") or {}
    lines = [f"{res['mode']} mode {res['start']}..{res['end']}: {len(res['sessions'])} sessions"
             + (f"; decided on minute bars at {m['decide']} ET from {m['start']} ({m['covered']} sessions, parity measured from there; "
                f"{m['fallbacks']} of {m['orders']} orders filled at the close instead"
                + (f"; STOPPED: {m['stopped']}" if m.get("stopped") else "") + ")" if m else "")]
    for e, s in (p.get("decisions") or {}).items():
        t = ((p.get("engines") or {}).get(e) or {}).get("tracking") or (p.get("book") or {}).get("tracking") if e == "ALL" else \
            ((p.get("engines") or {}).get(e) or {}).get("tracking") or {}
        lines.append(f"  {e:6s} same holdings {s['agree']}/{s['n']} ({(s['share'] or 0):.1%}) {s['classes']}"
                     + (f"; tracking mean {t.get('mean_bps')} sd {t.get('sd_bps')} bps/day over {t.get('n_daily')} days; "
                        f"cum mirror {t.get('cum_mirror')} vs Composer {t.get('cum_composer')}" if t else ""))
    b = p.get("book") or {}
    lb, dv = b.get("limit_buys") or {}, b.get("distributions") or {}
    if lb:
        lines.append(f"  limit buys: {lb['unfilled_orders']} of {lb['buy_orders']} buy orders unfilled ({lb['unfilled_legs']} sleeve "
                     f"legs, {lb['sessions']} sessions, ${lb['unfilled_usd']:,.0f})")
    if dv:
        lines.append(f"  distributions (rule {res.get('rule')}): accrued ${dv['accrued_usd']:,.2f}, credited ${dv['credited_usd']:,.2f}, "
                     f"leaked ${dv['leaked_usd']:,.2f}, open ${dv['open_usd']:,.2f}")
    return "\n".join(lines)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--mode", choices=("close", "minute"), default="close")
    b.add_argument("--start", default=START)
    b.add_argument("--end")
    b.add_argument("--minute-start", default=MINUTE_START)
    b.add_argument("--decide", default=DECIDE)
    b.add_argument("--slip-bps", type=float, default=SLIP_BPS)
    b.add_argument("--rule", choices=mc.DIVIDEND_RULES, default=DIVIDEND_RULE, help="where a dividend's cash goes on its pay date")
    b.add_argument("--cache", help="a directory for Yahoo and FMP responses (a rerun then costs nothing)")
    b.add_argument("--out")
    dly = sub.add_parser("daily")
    dly.add_argument("--date")
    dly.add_argument("--force", action="store_true")
    dly.add_argument("--book", default=BOOK_PATH)
    dly.add_argument("--ledger", default=LEDGER_PATH)
    a = ap.parse_args(argv)
    if a.cmd == "daily":
        lines, alerts = daily(a.date, a.book, a.ledger, a.force)
        print("\n".join(lines))
        for x in alerts:
            print(f"  !! {x}")
        return 2 if alerts else 0
    res = backfill(a.start, a.end, a.mode, minute_start=a.minute_start, decide=a.decide, slip_bps=a.slip_bps, cache=a.cache,
                   rule=a.rule, log=lambda m: print(m, file=sys.stderr))
    print(_summary(res))
    if a.out:
        _write_atomic(a.out, json.dumps(res, separators=(",", ":")))
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code or 0)                             # FMP fetches past a budget may still be in flight
