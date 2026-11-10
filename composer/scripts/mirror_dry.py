#!/usr/bin/env python3
"""DRY simulator and parity measurement for the IBKR mirror of the Composer book (composer/IBKR_MIRROR.md).

Nothing here trades or holds a broker key. It drives ibkr-executor/app/mirror_core.py UNCHANGED (the
module the executor's mirror manager runs: build_plan -> apply_crosses -> book_fill each sell ->
apply_transfers -> size_buys -> book_fill each buy -> finish), on public prices, so what the dry run
measures is the code that will trade. Read-only toward everything: Yahoo daily bars, FMP 1-minute
bars (key FMP_API_KEY, never printed), the shadow ledger and the monitor's snapshots on disk.

  backfill(mode="close")   every session since 2026-07-15: each engine's decision is the shadow
                           ledger's "target" (the approved tree on that day's CLOSE); reference and
                           fill prices are the day's raw closes. An engine with no ledger row that
                           day is skipped (it keeps its holdings).
  backfill(mode="minute")  the recent sessions (from --minute-start; the book is warmed in close
                           mode up to the session before): the decision is mirror_brain.build() at
                           the decision time (15:55 ET by default: bars ending at or before it, i.e.
                           the bar that starts 15:54); orders fill at the close of the 1-minute bar
                           that STARTS at the decision time (about a minute later), or at the day's
                           close when a ticker has no such traded bar (counted); the book is valued
                           at the official close.
  daily()                  ONE session on a persistent book (results/mirror/dry-book.json), the
                           minute-mode step, then PARITY against Composer for that session: holdings
                           after its rebalance and the day's return from the monitor snapshot, and
                           the shadow ledger's status. Idempotent, atomic, never raises.

Costs on every venue order: IBKR tiered commission $0.0035 a share, at least $0.35 an order, at most
1% of the trade's value; slippage SLIP_BPS (2) of notional against the mirror, applied in the fill
price. Internal crosses cost nothing (mirror_core books them at the reference price).

Distributions: on an ex-date each sleeve's cash is credited with the shares it held at the prior
close x the per-share amount (Yahoo's dividend events). Two return bases are kept per sleeve and for
the book: TOTAL (with those credits) and PRICE (the day's credit taken out of that day's return).
Composer's symphony figures are close to a price return: a distribution lands in ACCOUNT cash unless
the payer is held through to its pay date, when it is credited inside the symphony 1-5 sessions later
(divergence.py, add. 38). The price basis is the one compared with Composer; the pay-date credits
are listed, not modelled.

Composer's realised record: the monitor snapshot taken after each close (results/monitor; older ones
from the git history of last-snapshot.json, read-only). A symphony's DAILY RETURN is
deposit_adjusted_value(D) / deposit_adjusted_value(D-1) - 1, Composer's own deposit-adjusted figure,
between snapshots of consecutive sessions; where a session has no snapshot the return is a span of
several sessions and is compared as a span (never split into days). A snapshot taken during the next
session gives holdings only. Days on which a symphony's raw value moved by more than its return
(a deposit, withdrawal or transfer) are flagged.

  mirror_dry.py backfill [--mode close|minute] [--start D] [--end D] [--minute-start D] [--decide HH:MM]
                         [--cache DIR] [--out FILE]
  mirror_dry.py daily [--date D] [--force]
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(ROOT, "ibkr-executor", "app"))
import mirror_core as mc  # noqa: E402  the executor's own module, unchanged
import shadow_runner as sr  # noqa: E402

SCHEMA = 1
CAPITAL = 118_000.0
FRACTIONS = {"HG": 0.29, "KMLM": 0.29, "SLEEVE": 0.27, "HARV": 0.15}       # POLICY targets
START = "2026-07-15"              # the shadow ledger's first session
MINUTE_START = "2026-10-05"
DECIDE = "15:55"                  # ET on a full day: reads the bar that starts 15:54
VARIANTS = ("15:45", "15:50", "15:55")
SLIP_BPS = 2.0
COMM_PER_SHARE, COMM_MIN, COMM_CAP = 0.0035, 0.35, 0.01     # IBKR tiered: per share, per order, share of value
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


def rules_from_manifest(cfg_all=None):
    """{engine: {"rule", "corridor"}} for the engines that are not plain daily (KMLM: threshold, 10pp)"""
    cfg_all = cfg_all if cfg_all is not None else sr.load_manifest()
    return {e: {"rule": mc.RULE_THRESHOLD, "corridor": float(c["corridor"])} for e, c in cfg_all.items() if c.get("corridor")}


def seed_book(capital=CAPITAL, fractions=None, rules=None):
    return mc.Book.seed(capital, dict(fractions or FRACTIONS), rules if rules is not None else rules_from_manifest())


def decide_at(d, decide=DECIDE):
    """the decision time on session d: `decide` is given for a 16:00 close; a half-day keeps the same
    distance to its own close (15:55 -> 12:55 on a 13:00 close)"""
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
    on disk, for a study that is rerun). daily(t) -> (adjusted, raw, dividends {ex-date: amount},
    splits); live(t, asof) -> the (adjusted, raw, meta) contract of preclose.fetch_live for
    mirror_brain.build's `fetch` seam, as of session `asof` (see asof_series). The meta is the chart's
    own, so a replay still drops the final-close bar of its day (its last-trade stamp is later than the
    replay) exactly as the live code does."""

    def __init__(self, cache_dir=None, fetch=None):
        self.cache_dir, self._fetch = cache_dir, fetch or _yahoo_chart
        self.res, self.parsed, self.lock = {}, {}, threading.Lock()

    def chart(self, t):
        with self.lock:
            if t in self.res:
                return self.res[t]
        path = os.path.join(self.cache_dir, "yahoo", f"{t}.json") if self.cache_dir else None
        res = None
        if path and os.path.isfile(path):
            try:
                with open(path) as f:
                    res = json.load(f)
            except (OSError, ValueError):
                res = None
        if res is None:
            res = self._fetch(t)
            if path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                _write_atomic(path, json.dumps(res))
        with self.lock:
            self.res[t] = res
        return res

    def daily(self, t):
        if t not in self.parsed:
            res = self.chart(t)
            adj, raw = sr.parse_daily(res)
            ev = res.get("events") or {}
            divs = {}
            for v in (ev.get("dividends") or {}).values():
                if _pos(v.get("amount")):
                    d = sr._utc_date(v["date"])
                    divs[d] = divs.get(d, 0.0) + float(v["amount"])
            splits = sorted((sr._utc_date(v["date"]), v.get("numerator"), v.get("denominator"))
                            for v in (ev.get("splits") or {}).values())
            self.parsed[t] = (adj, raw, divs, splits)
        return self.parsed[t]

    def live(self, t, asof=None):
        adj, raw, _, _ = self.daily(t)
        if not adj:
            raise RuntimeError(f"Yahoo {t}: empty series")
        if asof:
            adj, raw = asof_series(adj, raw, asof)
        return dict(adj), dict(raw), dict(self.chart(t).get("meta") or {})


class Market:
    """raw closes, distributions and the session calendar the simulator runs on. raw: {ticker: {date:
    close}}; divs: {ticker: {ex-date: amount per share}}. With a Yahoo source, tickers load on demand."""

    def __init__(self, raw=None, divs=None, calendar=None, yahoo=None, cal_ticker="SPY"):
        self.raw, self.divs, self.yahoo, self.cal_ticker = dict(raw or {}), dict(divs or {}), yahoo, cal_ticker
        self._cal, self.bad, self.splits = (sorted(calendar) if calendar else None), {}, {}

    def need(self, tickers):
        for t in sorted(set(tickers)):
            if t in self.raw or t in self.bad or self.yahoo is None:
                continue
            try:
                _, raw, divs, splits = self.yahoo.daily(t)
                self.raw[t], self.divs[t], self.splits[t] = raw, divs, splits
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

    def closes(self, d):
        return {t: s[d] for t, s in self.raw.items() if _pos(s.get(d))}

    def dividends(self, after, d):
        """{ticker: amount per share} with an ex-date in (after, d]; after None: on d alone"""
        out = {}
        for t, s in self.divs.items():
            amt = sum(a for x, a in s.items() if x <= d and (x > after if after else x == d))
            if amt > 0:
                out[t] = amt
        return out


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
    """A mirror book stepped one session at a time through mirror_core, with costs and distributions.

    state (persisted by daily()): prev_eq {sleeve: equity at the last close}, idx {sleeve: price-basis
    index, net}, idx_gross (before costs), last_px {ticker: last close seen}, venue {ticker: shares the
    'account' holds, kept independently of the book so mc.check has something to check against}."""

    def __init__(self, book, slip_bps=SLIP_BPS, cfg=None, state=None):
        self.book, self.slip_bps, self.cfg = book, float(slip_bps), cfg or mc.Config()
        st = state or {}
        self.prev_eq = dict(st["prev_eq"]) if st.get("prev_eq") else {n: s.cash for n, s in book.sleeves.items() if not s.shares}
        self.idx = dict(st.get("idx") or {n: 1.0 for n in book.sleeves})
        self.idx_gross = dict(st.get("idx_gross") or {n: 1.0 for n in book.sleeves})
        self.book_idx = dict(st.get("book_idx") or {"px": 1.0, "gross": 1.0})
        self.last_px = dict(st.get("last_px") or {})
        self.venue = dict(st.get("venue") or book.positions())
        self.cash_low = st.get("cash_low", 0.0)

    def state(self):
        return {"prev_eq": dict(self.prev_eq), "idx": dict(self.idx), "idx_gross": dict(self.idx_gross),
                "book_idx": dict(self.book_idx), "last_px": dict(self.last_px), "venue": dict(self.venue),
                "cash_low": self.cash_low}

    def session(self, d, targets, ref, fills, closes, divs=None, mode="close", fallbacks=None):
        """One session. targets: the brain's {sleeve: {"status", "target", "version"}}; ref: reference
        prices the plan is sized on; fills: {ticker: price before slippage} each venue order fills at;
        closes: the official closes the book is valued at; divs: {ticker: amount per share} going
        ex today, credited on the shares held coming into the session. Returns (engine rows, book row)."""
        book, slip = self.book, self.slip_bps
        names = list(book.sleeves)
        acct = {n: {"div": 0.0, "comm": 0.0, "slip": 0.0, "venue": 0.0, "cross": 0.0, "div_by": {}} for n in names}
        problems = []
        cash0 = book.cash()
        # 1. distributions on the shares held at the prior close
        for n, s in book.sleeves.items():
            for sym, q in sorted(s.shares.items()):
                amt = (divs or {}).get(sym)
                if _pos(amt):
                    s.cash += q * amt
                    acct[n]["div"] += q * amt
                    acct[n]["div_by"][sym] = round(q * amt, 4)
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
        for o in mc.size_buys(book, plan, cfg=self.cfg):
            flow += self._fill(o, fills, slip, acct, problems, orders)
        mc.finish(book, plan)
        # 3. invariants: every share owned once, the venue agrees, cash moved only by what was booked
        problems += mc.check(book, self.venue)
        want_cash = cash0 + sum(a["div"] for a in acct.values()) + flow
        if not math.isclose(book.cash(), want_cash, rel_tol=0, abs_tol=1e-6):
            problems.append(f"cash {book.cash():.6f} is not the {want_cash:.6f} the fills account for")
        low = min(s.cash for s in book.sleeves.values())
        self.cash_low = min(self.cash_low, low)
        # not a broken invariant, but worth seeing: mirror_core sizes buys at the reference x (1 + cushion);
        # a fill further above the reference than that spends cash the sleeve does not have
        overspent = {n: round(s.cash, 2) for n, s in book.sleeves.items() if s.cash < -0.005}
        # 4. value at the official close, on both bases
        self.last_px.update({t: p for t, p in closes.items() if _pos(p)})
        px = self.last_px
        stale = sorted(t for t in book.positions() if not _pos(closes.get(t)))
        if stale:
            problems.append(f"no close on {d} for {', '.join(stale)}: valued at the last close seen")
        rows, tot, tot_prev, tot_div, tot_cost = [], 0.0, 0.0, 0.0, 0.0
        for n in names:
            s, dec, a = book.sleeves[n], plan["sleeves"].get(n) or {}, acct[n]
            eq = mc.equity(s, px)
            prev = self.prev_eq.get(n, eq)
            cost = a["comm"] + a["slip"]
            ret = eq / prev - 1 if prev > 0 else 0.0
            ret_px = (eq - a["div"]) / prev - 1 if prev > 0 else 0.0
            ret_gross = (eq - a["div"] + cost) / prev - 1 if prev > 0 else 0.0
            self.idx[n] = self.idx.get(n, 1.0) * (1 + ret_px)
            self.idx_gross[n] = self.idx_gross.get(n, 1.0) * (1 + ret_gross)
            rows.append({"date": d, "engine": n, "mode": mode, "action": dec.get("action"), "reason": dec.get("reason"),
                         "gap": _r(dec.get("gap"), 5), "target": dec.get("target"), "version": dec.get("version"),
                         "weights": {t: round(w, 6) for t, w in mc.weights(s, px).items()},
                         "cash_share": _r(s.cash / eq if eq > 0 else None, 5),
                         "equity": round(eq, 2), "index_px": round(self.idx[n], 8), "index_px_gross": round(self.idx_gross[n], 8),
                         "ret": _r(ret), "ret_px": _r(ret_px), "ret_px_gross": _r(ret_gross),
                         "div": round(a["div"], 2), "div_by": a["div_by"], "commission": round(a["comm"], 4),
                         "slippage": round(a["slip"], 4), "traded": round(a["venue"], 2), "crossed": round(a["cross"], 2),
                         "equity_prev": round(prev, 2)})
            self.prev_eq[n] = eq
            tot, tot_prev, tot_div, tot_cost = tot + eq, tot_prev + prev, tot_div + a["div"], tot_cost + cost
        r_px = (tot - tot_div) / tot_prev - 1 if tot_prev > 0 else 0.0
        r_gross = (tot - tot_div + tot_cost) / tot_prev - 1 if tot_prev > 0 else 0.0
        self.book_idx = {"px": self.book_idx["px"] * (1 + r_px), "gross": self.book_idx["gross"] * (1 + r_gross)}
        brow = {"date": d, "engine": "BOOK", "mode": mode, "equity": round(tot, 2), "equity_prev": round(tot_prev, 2),
                "ret": _r(tot / tot_prev - 1 if tot_prev > 0 else 0.0), "ret_px": _r(r_px), "ret_px_gross": _r(r_gross),
                "index_px": round(self.book_idx["px"], 8), "index_px_gross": round(self.book_idx["gross"], 8),
                "div": round(tot_div, 2), "commission": round(sum(a["comm"] for a in acct.values()), 4),
                "slippage": round(sum(a["slip"] for a in acct.values()), 4),
                "traded": round(sum(a["venue"] for a in acct.values()), 2),
                "crossed": round(sum(c["qty"] * c["price"] for c in plan["crosses"]), 2),
                "orders": sum(1 for o in orders if o["filled"]), "crosses": len(plan["crosses"]),
                "cash": round(book.cash(), 2), "cash_low": round(low, 2), "overspent": overspent, "order_list": orders,
                "problems": problems}
        if fallbacks is not None:
            brow["fill_fallbacks"] = fallbacks
        return rows, brow

    def _fill(self, o, fills, slip, acct, problems, orders):
        """book one venue order whole at its fill price with slippage and commission; returns the cash flow"""
        sym, qty = o["symbol"], int(o["qty"])
        px = _pos(fills.get(sym))
        if px is None or qty <= 0:
            mc.book_fill(self.book, o, 0, None, 0.0)
            if qty > 0:
                problems.append(f"no fill price for {sym}: the {o['side']} of {qty} was left unfilled")
            orders.append({"id": o["id"], "side": o["side"], "symbol": sym, "qty": qty, "filled": 0})
            return 0.0
        price = slipped(o["side"], px, slip)
        fee = commission(qty, price)
        split = mc.book_fill(self.book, o, qty, price, fee)
        sign = -1 if o["side"] == mc.SELL else 1
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
        orders.append({"id": o["id"], "side": o["side"], "symbol": sym, "qty": qty, "filled": qty, "ref": o.get("ref"),
                       "px": round(px, 6), "price": round(price, 6), "commission": round(fee, 4)})
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
    """mirror_brain.build() replayed at hh:mm ET on session d: FMP's traded minutes through this store,
    Yahoo's history as it stood that day"""
    import mirror_brain as mb
    now = mb.parse_at(f"{d} {hhmm}")
    return (build or mb.build)(now, quotes=minutes.quotes() if minutes is not None else None,
                               fetch=lambda t: yahoo.live(t, asof=d))


def minute_prices(d, hhmm, symbols, minutes, market, fill="next"):
    """(reference prices at the decision time, fill prices, fallbacks) for the symbols a plan may touch.
    Reference: the last traded minute at or before hh:mm, else the previous close. Fill ("next"): the
    close of the traded bar that starts at hh:mm; a ticker without one, or with a print more than
    FILL_SANITY from the day's close, fills at the day's close and is listed in fallbacks. fill
    "close": every order fills at the official close (a market-on-close order)."""
    closes, prev = market.closes(d), market.prev(d)
    prev_closes = market.closes(prev) if prev else {}
    ref, fills, fallbacks = {}, {}, []
    for t in sorted(set(symbols)):
        c = _pos(closes.get(t))
        try:
            p_ref, p_bar = minutes.price_at(t, d, hhmm), minutes.bar(t, d, hhmm)
        except Refused:
            raise
        except Exception:  # noqa: BLE001
            p_ref = p_bar = None
        if p_ref is not None and c and abs(p_ref / c - 1) > FILL_SANITY:
            p_ref = None
        r = p_ref or _pos(prev_closes.get(t)) or c
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
    mirror-skip, corridor-path (a threshold engine: one side rebalanced and the other did not, both
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
        return False, dist, "composer-no-rebalance", f"Composer made no rebalance attempt (holdings of {led.get('live_asof') or 'an earlier day'})"
    if status == "knife-edge":
        edge = led.get("edge") or {}
        return False, dist, "knife-edge", f"the call flips inside the decision window ({edge.get('time') or edge.get('basis') or 'intraday'})"
    if row.get("action") == "skip":
        return False, dist, "mirror-skip", f"the mirror had no decision ({row.get('reason')})"
    if corridor:
        m_traded = row.get("action") == "trade"
        if traded_c is not None and m_traded != traded_c:
            who = "the mirror rebalanced, Composer did not" if m_traded else "Composer rebalanced, the mirror did not"
            return False, dist, "corridor-path", f"{who} (mirror gap {100 * (row.get('gap') or 0):.1f}pp vs the {100 * corridor:.0f}pp corridor)"
        if apart_prev and not m_traded and traded_c is False:
            return False, dist, "corridor-path", f"both held inside the corridor on the paths split on {apart_prev}"
        if stood and not m_traded and traded_c is None:
            return False, dist, "corridor-path", (f"the mirror stood still on {', '.join(x[5:] for x in stood)} (no ledger row), Composer "
                                                  f"rebalanced meanwhile, and today's target is inside the mirror's corridor")
    if late:
        return False, dist, "late-snapshot", "Composer's holdings were read during the next session (drifted by its moves)"
    if target and sr.distance(target, live)[0] <= TOL:
        return False, dist, "whole-share", "Composer holds the target; the mirror is off it by whole shares, its cash reserve or a skipped trim"
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
    for e, xs in list(days.items()) + [("ALL", out_rows)]:
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


def expected_credits(rows, market, engine):
    """Composer's pay-date credits the price basis leaves out: for each distribution the mirror sleeve
    collected, whether the payer was then held through its pay lag (divergence.PAY_LAG, observed per
    fund) - if so Composer credits it INSIDE the symphony on session ex+L. [{"ex", "ticker", "usd",
    "bps", "treatment", "credit_on"}]; a fund with no observed lag is never given a guessed day"""
    import divergence as dv
    xs = [r for r in rows if r["engine"] == engine]
    dates = [r["date"] for r in xs]
    out = []
    for i, r in enumerate(xs):
        for t, usd in (r.get("div_by") or {}).items():
            wt = {x["date"]: (x["weights"] or {}).get(t, 0.0) for x in xs[i:i + dv.MAX_PAY_LAG + 1]}
            wt[r["date"]] = max(wt.get(r["date"], 0.0), 0.0)
            # held at the prior close and through the ex-date: the ex-date's own row is after its trade
            treatment, _, need, pending, _, _ = dv.classify_hold(t, wt, dates[i:i + dv.MAX_PAY_LAG + 1])
            lag = dv.PAY_LAG.get(t)
            on = dates[i + lag[0]] if lag and treatment == "HELD_THROUGH" and i + lag[0] < len(dates) else None
            out.append({"ex": r["date"], "ticker": t, "usd": round(usd, 2), "bps": round(usd / r["equity_prev"] * 1e4, 1),
                        "treatment": treatment, "pay_lag": lag[0] if lag else None, "credit_on": on, "pending": bool(pending)})
    return out


def cause_labeller(par_days, rows, engine, credits=None, skipped=()):
    """a one-line cause for a span's return difference, from what is known about its sessions"""
    by = {x["date"]: x for x in par_days if x["engine"] == engine}
    acts = {r["date"]: r for r in rows if r["engine"] == engine}
    cred = {}
    for c in credits or []:
        if c.get("credit_on"):
            cred.setdefault(c["credit_on"], []).append(c)
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
        cr = [c for d in inside for c in cred.get(d, [])]
        if cr:
            why.append("Composer pay-date credit inside the symphony (" + ", ".join(f"{c['ticker']} ~{c['bps']:+.0f} bps" for c in cr) + ")")
        if s.get("flow"):
            why.append(f"Composer deposit/transfer in the span (${s['flow']:+,.0f})")
        today = [(d, by[d]["class"]) for d in inside if d in by and not by[d]["agree"]]
        if not why and today:
            why.append(f"the holdings split at this rebalance ({', '.join(sorted({c for _, c in today}))}): the old book to ~15:54 vs to the close")
        if not why:
            def rotated(d):
                a = acts.get(d) or {}
                big = (a.get("traded") or 0.0) + (a.get("crossed") or 0.0) > TOL * (a.get("equity_prev") or 0.0) > 0
                return big or bool((by.get(d) or {}).get("composer_traded"))
            if any(rotated(d) for d in inside):
                why.append("rotation day: Composer fills ~15:54, the mirror at its own fill price")
            else:
                why.append("no trade on either side: Composer's snapshot marks vs official closes")
        return "; ".join(why)
    return label


def engine_parity(rows, book_rows, shadow, market, composer, cfg_all=None, exclude=NO_REBALANCE, skipped=None, since=None):
    """the whole parity block for one simulation: decisions, returns (net and gross, with and without
    the excluded sessions), corridor episodes, distributions, costs. since: measure from this session
    on (rows before it only give the first return its base)"""
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
    spans_all, idx_all, w_prev = {}, {}, {}
    for e in engines:
        xs_all = [r for r in rows if r["engine"] == e]
        xs = [r for r in live if r["engine"] == e]
        idx = {r["date"]: r["index_px"] for r in xs_all}
        idx_g = {r["date"]: r["index_px_gross"] for r in xs_all}
        idx_tr, level = ({xs_all[0]["date"]: 1.0} if xs_all else {}), 1.0
        for r in xs_all[1:]:
            level *= 1 + (r["ret"] or 0.0)
            idx_tr[r["date"]] = level
        spans = [s for s in composer_spans((composer or {}).get(e) or {}, cal) if s["d0"] in idx and s["d1"] in idx]
        try:
            credits = [c for c in expected_credits(rows, market, e) if not since or c["ex"] >= since]
        except Exception:  # noqa: BLE001
            credits = []
        lab = cause_labeller(dec["days"], rows, e, credits, skipped or ())
        paid, idx_cc, lvl = {}, {}, None
        for c in credits:
            if c.get("credit_on"):
                paid[c["credit_on"]] = paid.get(c["credit_on"], 0.0) + c["bps"] / 1e4
        for r in xs_all:                               # price basis + the pay-date credits Composer books inside
            lvl = 1.0 if lvl is None else lvl * (1 + (r["ret_px"] or 0.0) + paid.get(r["date"], 0.0))
            idx_cc[r["date"]] = lvl
        net = tracking(idx, spans, label_of=lab)
        conv = tracking(idx_cc, spans)
        ex = tracking(idx, spans, exclude=exclude)
        gross = tracking(idx_g, spans)
        total = tracking(idx_tr, spans)
        flows = [s["d1"] for s in spans if s.get("flow")]
        noflow = tracking(idx, spans, exclude=flows)
        diffs = {s["date"]: s["diff_bps"] / 1e4 for s in net.get("series") or [] if s["n"] == 1}
        eq = [r["equity"] for r in xs]
        avg_eq = sum(eq) / len(eq) if eq else 0.0
        comm, slip = sum(r["commission"] for r in xs), sum(r["slippage"] for r in xs)
        traded, crossed, div = sum(r["traded"] for r in xs), sum(r["crossed"] for r in xs), sum(r["div"] for r in xs)
        acts = {}
        for r in xs:
            acts[r["action"]] = acts.get(r["action"], 0) + 1
        slim = ("series", "worst")
        out["engines"][e] = {
            "tracking": {k: v for k, v in net.items() if k != "series"},
            "tracking_ex_no_rebalance": {k: v for k, v in ex.items() if k not in slim},
            "tracking_gross": {k: v for k, v in gross.items() if k not in slim},
            "tracking_total_basis": {k: v for k, v in total.items() if k not in slim},
            "tracking_ex_flow_days": {k: v for k, v in noflow.items() if k not in slim},
            "tracking_with_pay_date_credits": {k: v for k, v in conv.items() if k not in slim},
            "flow_days": flows, "series": net.get("series") or [],
            "actions": acts, "avg_equity": round(avg_eq, 2), "final_equity": eq[-1] if eq else None,
            "costs": {"commission": round(comm, 2), "slippage": round(slip, 2),
                      "commission_bps_yr": _r(comm / avg_eq * yr * 1e4, 2) if avg_eq else None,
                      "slippage_bps_yr": _r(slip / avg_eq * yr * 1e4, 2) if avg_eq else None,
                      "drag_bps_yr": _r((comm + slip) / avg_eq * yr * 1e4, 2) if avg_eq else None,
                      "turnover_venue_x_yr": _r(traded / avg_eq * yr, 2) if avg_eq else None,
                      "turnover_with_crosses_x_yr": _r((traded + crossed) / avg_eq * yr, 2) if avg_eq else None,
                      "traded": round(traded, 2), "crossed": round(crossed, 2)},
            "distributions": {"usd": round(div, 2), "pct_of_sleeve": _r(div / avg_eq, 6) if avg_eq else None,
                              "events": credits,
                              "held_through_usd": round(sum(c["usd"] for c in credits if c["treatment"] == "HELD_THROUGH"), 2),
                              "leaked_usd": round(sum(c["usd"] for c in credits if c["treatment"] == "LEAKED"), 2),
                              "ambiguous_usd": round(sum(c["usd"] for c in credits if c["treatment"] == "AMBIGUOUS"), 2)},
            "by_cause": _by_cause(net.get("series") or [])}
        if (cfg_all.get(e) or {}).get("corridor"):
            out["episodes"][e] = episodes(dec["days"], diffs, e)
        spans_all[e], idx_all[e] = spans, idx
        w_prev[e] = {r["date"]: r["equity"] for r in xs_all}
    causes = {e: {(x["d0"], x["date"]): x for x in out["engines"][e]["series"]} for e in engines}
    out["book"] = book_parity(book_live, spans_all, idx_all, w_prev, cal, exclude, causes)
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
    t = tracking(index, spans_b, label_of=lambda x: why.get((x["d0"], x["d1"])))
    tx = tracking(index, spans_b, exclude=exclude)
    eq = [r["equity"] for r in book_rows]
    avg = sum(eq) / len(eq) if eq else 0.0
    yr = ANNUAL / max(len(book_rows), 1)
    comm, slip = sum(r["commission"] for r in book_rows), sum(r["slippage"] for r in book_rows)
    traded, crossed = sum(r["traded"] for r in book_rows), sum(r["crossed"] for r in book_rows)
    return {"tracking": {k: v for k, v in t.items() if k != "series"},
            "tracking_ex_no_rebalance": {k: v for k, v in tx.items() if k not in ("series", "worst")},
            "series": t.get("series") or [], "sessions": len(book_rows), "avg_equity": round(avg, 2),
            "final_equity": eq[-1] if eq else None,
            "mirror_cum_total": _r(eq[-1] / book_rows[0]["equity_prev"] - 1, 6) if eq else None,
            "mirror_cum_px": _r(book_rows[-1]["index_px"] - 1, 6) if eq else None,
            "mirror_cum_px_gross": _r(book_rows[-1]["index_px_gross"] - 1, 6) if eq else None,
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
            "distributions_usd": round(sum(r["div"] for r in book_rows), 2),
            "problems": [f"{r['date']}: {p}" for r in book_rows for p in r["problems"]],
            "overspent": [{"date": r["date"], **r["overspent"]} for r in book_rows if r.get("overspent")],
            "cash_low": min((r["cash_low"] for r in book_rows), default=None)}


# ------------------------------------------------------------------ backfill
def backfill(start=START, end=None, mode="close", *, minute_start=MINUTE_START, decide=DECIDE, fill="next",
             slip_bps=SLIP_BPS, capital=CAPITAL, fractions=None, shadow=None, market=None, yahoo=None, minutes=None,
             build=None, composer=None, snapshots=None, cfg=None, cache=None, fill_gaps=False, parity=True, parity_from=None,
             log=None):
    """Replay the mirror over [start, end] and measure it against Composer.

    mode "close": the decision is the shadow ledger's target for the engine-day, at the day's raw closes.
    mode "minute": close mode up to the session before minute_start (the book arrives invested, its
    corridor state included), then mirror_brain.build() at `decide` ET with minute fills (fill "next":
    the bar starting at the decision time; "close": the official close, a market-on-close order).
    fill_gaps: on a session the ledger has no row for, decide from the approved tree on that day's
    closes instead of standing still. Seams (tests, studies): shadow {(date, engine): row}, market,
    yahoo, minutes, build, composer (composer_record's shape) or snapshots; cache: a directory for
    Yahoo and FMP responses. Returns {"rows", "book", "parity", "book_final", "sessions", "minute", ...}."""
    log = log or (lambda *_: None)
    cfg_all = sr.load_manifest()
    shadow = shadow if shadow is not None else read_shadow()
    end = end or max((d for d, _ in shadow), default=start)
    if market is None:
        yahoo = yahoo or Yahoo(cache)
        market = Market(yahoo=yahoo)
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
    sim = Sim(seed_book(capital, fractions, rules_from_manifest(cfg_all)), slip_bps, cfg)
    rows, book_rows, skipped, last = [], [], [], None
    info = {"start": minute_start, "decide": decide, "fill": fill, "covered": 0, "fallbacks": 0, "fallback_tickers": {},
            "orders": 0, "stopped": None, "unavailable": [], "labels": {}} if mode == "minute" else None
    payloads = {}
    for d in sessions:
        minute = mode == "minute" and d >= minute_start
        fallbacks = None
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
                ref, fills, fallbacks = minute_prices(d, hh, syms, minutes, market, fill)
            except Refused as e:
                info["stopped"] = f"FMP refused on {d}: {e}"
                log(f"minute mode stopped on {d}: {e}")
                break
            payloads[d] = payload
            bad = [e for e in engines if (targets.get(e) or {}).get("status") != "ok"]
            if bad:
                info["unavailable"].append({"date": d, "engines": bad, "why": (payload.get("problems") or [None])[0]
                                            or (targets.get(bad[0]) or {}).get("note")})
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
        er, br = sim.session(d, targets, ref, fills, closes, market.dividends(last, d) if last else market.dividends(None, d),
                             "minute" if minute else "close", fallbacks)
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
        rows += er
        book_rows.append(br)
        last = d
        log(f"{d} {'minute' if minute else 'close'}: " + " ".join(f"{r['engine']}:{r['action']}" for r in er))
    out = {"mode": mode, "start": start, "end": last, "sessions": [b["date"] for b in book_rows], "slip_bps": slip_bps,
           "capital": capital, "fractions": fractions, "fill_gaps": fill_gaps, "skipped_sessions": skipped,
           "rows": rows, "book": book_rows, "book_final": sim.book.to_dict(), "state": sim.state(),
           "minute": info, "unpriced": dict(market.bad)}
    if parity and book_rows:
        if composer is None:
            snaps = snapshots if snapshots is not None else load_snapshots(history=True)
            composer = composer_record(snaps, market.calendar(), cfg_all)
        since = parity_from or (minute_start if mode == "minute" else None)
        out["parity"] = engine_parity(rows, book_rows, shadow, market, composer, cfg_all, skipped=skipped, since=since)
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
          fractions=None, cfg=None):
    """ONE session's DRY step on the persistent book, then parity against Composer. Returns (lines,
    alerts): 1-3 short report lines, and an alert for every MISMATCH (the mirror's post-trade weights
    more than 3% half-L1 from Composer's holdings with no knife-edge or no-rebalance in the shadow
    ledger to explain it) or failure to run. A date already in the ledger is skipped unless force
    (which re-runs the book's LAST session from the state saved before it). Never raises."""
    try:
        return _daily(date, book_path, ledger_path, force, now, yahoo, minutes, build, market, snapshot_dir, shadow_path,
                      decide, slip_bps, capital, fractions, cfg)
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
           slip_bps, capital, fractions, cfg):
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
    before = {"book": book.to_dict(), "state": Sim(book, slip_bps, cfg, state).state(), "session": (saved or {}).get("session")}
    sim = Sim(book, slip_bps, cfg, state)
    last = (saved or {}).get("session")
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
    ref, fills, fallbacks = minute_prices(d, hh, syms, minutes, market, "next")
    er, br = sim.session(d, targets, ref, fills, market.closes(d), market.dividends(last, d) if last else market.dividends(None, d),
                         "minute", fallbacks)
    used = [o["symbol"] for o in br["order_list"] if o["filled"] and o["symbol"] in fallbacks]
    br["fill_fallbacks"] = used
    # parity against Composer for this session
    shadow = read_shadow(shadow_path)
    comp = composer_day(d, cal, snapshot_dir, cfg_all)
    alerts, same, n_cmp, diffs = [], 0, 0, []
    unavailable = [e for e in engines if (targets.get(e) or {}).get("status") != "ok"]
    if unavailable:
        why = (payload.get("problems") or [None])[0] or (targets.get(unavailable[0]) or {}).get("note") or "no decision"
        alerts.append(f"MIRROR DRY NO DECISION — {d} {hh} ET: {', '.join(unavailable)} had no target from the brain "
                      f"({' '.join(str(why).split())[:160]}); those sleeves stood still.")
    for r in er:
        e = r["engine"]
        p, c, s = targets.get(e) or {}, comp.get(e), shadow.get((d, e)) or {}
        r.update(decide=hh, label=p.get("label"), brain=p.get("status"), shadow=s.get("status"))
        if not c:
            r["parity"] = "no Composer snapshot"
            continue
        dist = sr.distance(r["weights"], c["holdings"])[0]
        n_cmp += 1
        r.update(composer=c["holdings"], composer_ret=_r(c["ret"]), composer_ret_basis=c["basis"], dist=round(dist, 4))
        if c["ret"] is not None and c["kind"] != "next-day":
            r["diff_bps"] = round((r["ret_px"] - c["ret"]) * 1e4, 1)
            diffs.append((e, r["diff_bps"]))
        if dist <= TOL:
            r["parity"] = "same"
            same += 1
        elif s.get("status") in ("knife-edge", "no-rebalance"):
            r["parity"] = f"explained ({s['status']})"
        else:
            r["parity"] = "MISMATCH"
            alerts.append(f"MIRROR MISMATCH — {e} on {d}: the mirror ({r['action']}, decided {hh} ET) holds "
                          f"{sr.fmt_w(r['weights'])}; Composer holds {sr.fmt_w(c['holdings'])} (half-L1 {dist:.1%}). The shadow "
                          f"ledger says {s.get('status') or 'nothing for this session'}: no knife-edge or no-rebalance explains "
                          f"it. DRY only; no order exists.")
    if br["problems"]:
        alerts.append(f"MIRROR DRY BOOK PROBLEM — {d}: " + "; ".join(br["problems"])[:300])
    br.update(decide=hh, seeded_on=seeded, brain={"asof_et": payload.get("asof_et"), "replay": payload.get("replay"),
                                                   "quotes": payload.get("quotes"), "problems": payload.get("problems")},
              parity={"compared": n_cmp, "same": same}, alerts=len(alerts))
    # the book first (it remembers the state before this session), then the ledger
    _write_atomic(book_path, json.dumps({"schema": SCHEMA, "kind": "composer-mirror-dry-book", "capital": capital,
                                         "fractions": fractions, "seeded_on": seeded, "session": d, "book": book.to_dict(),
                                         "state": sim.state(), "before": before}, indent=1))
    keep = [r for r in led if r["date"] != d]
    _write_atomic(ledger_path, "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in keep + er + [br]))
    acts = " | ".join(f"{r['engine']} {r['action']}" + (f" -> {sr.fmt_w(r['weights'])}" if r["action"] == "trade" else "")
                      for r in er)
    lines = [f"MIRROR DRY {d} (decided {hh} ET): {acts}; {br['orders']} order(s), {br['crosses']} cross(es), costs "
             f"${br['commission'] + br['slippage']:.2f}" + (f", {len(used)} fill(s) at the close ({', '.join(used)})" if used else ""),
             f"book ${br['equity']:,.0f} ({br['ret']:+.2%} day; price basis {br['ret_px']:+.2%}"
             + (f"; distributions ${br['div']:,.2f}" if br["div"] else "") + ")"
             + ("; cash below zero after the buys (a fill past the buy cushion): "
                + ", ".join(f"{n} ${v:,.2f}" for n, v in br["overspent"].items()) if br["overspent"] else "")]
    if n_cmp:
        lines.append(f"parity vs Composer: {same} of {n_cmp} engines hold the same"
                     + ("; day return, mirror - Composer: " + ", ".join(f"{e} {x:+.0f} bps" for e, x in diffs) if diffs else ""))
    else:
        lines.append(f"parity vs Composer: no snapshot for {d} on disk yet")
    return lines, alerts


# ------------------------------------------------------------------ CLI
def _summary(res):
    p = res.get("parity") or {}
    lines = [f"{res['mode']} mode {res['start']}..{res['end']}: {len(res['sessions'])} sessions"]
    for e, s in (p.get("decisions") or {}).items():
        t = ((p.get("engines") or {}).get(e) or {}).get("tracking") or (p.get("book") or {}).get("tracking") if e == "ALL" else \
            ((p.get("engines") or {}).get(e) or {}).get("tracking") or {}
        lines.append(f"  {e:6s} same holdings {s['agree']}/{s['n']} ({(s['share'] or 0):.1%}) {s['classes']}"
                     + (f"; tracking mean {t.get('mean_bps')} sd {t.get('sd_bps')} bps/day over {t.get('n_daily')} days; "
                        f"cum mirror {t.get('cum_mirror')} vs Composer {t.get('cum_composer')}" if t else ""))
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
    b.add_argument("--cache", help="a directory for Yahoo and FMP responses (a rerun then costs nothing)")
    b.add_argument("--out")
    dly = sub.add_parser("daily")
    dly.add_argument("--date")
    dly.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "daily":
        lines, alerts = daily(a.date, force=a.force)
        print("\n".join(lines))
        for x in alerts:
            print(f"  !! {x}")
        return 2 if alerts else 0
    res = backfill(a.start, a.end, a.mode, minute_start=a.minute_start, decide=a.decide, slip_bps=a.slip_bps, cache=a.cache,
                   log=lambda m: print(m, file=sys.stderr))
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
