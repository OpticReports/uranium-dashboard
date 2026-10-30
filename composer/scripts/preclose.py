#!/usr/bin/env python3
"""Pre-close preview (results.md addendum 49): what Composer's ~15:50 ET rebalance is about to do,
read before it happens, so the owner can act in the Composer app if they choose to.

The daily monitor reports a session after its rebalance (17:35 ET). This runs at 15:15 ET (12:15 on
a half-day) on live prices, with the approved trees and the evaluator of the shadow runner
(shadow_runner.py, add. 48):
  GATE    HG's condition SPY > its 200-day average, on SPY's live price: the SPY price that flips it
          (the average includes today's price, as Composer reads it at the rebalance), whether it
          flips today, and what HG holds on each side of the line
  engine  holdings now -> what the approved logic holds after the rebalance (KMLM: only if some
          holding is more than 10pp off the target, else no trade; a paused symphony: no trade), the
          dollars that move, and how close the call is, in sigmas of the move left before the
          decision (daily sigma x 0.6 x sqrt(minutes / 390), add. 49):
            market  the whole market moving 1 and 2 sigma either way, every fund by its 60-session
                    beta to SPY: what the symphony would hold instead
            ticker  the smallest one-ticker move that changes at least a quarter of the outcome
          close call: a 1-sigma move of either kind changes it (or KMLM's trigger is within 1pp);
          could flip: a 2-sigma market move or a 2-sigma one-ticker move does; firm: neither
Live prices are Yahoo's latest trades. A price older than 15 minutes is stale: it is rebuilt from a
fresh fund on the same index at its daily leverage (previous close x (1 + L x the index's return
today)), or from a fund on a related index (tagged approx). A stale decision ticker that cannot be
rebuilt is used as it is, named, and moved 2 sigma (sized from its last trade) to see whether the
answer depends on it.

Alerts (exit 2): the gate flips today or sits within 2 sigma of flipping; SPY 2% or more off
yesterday's close (a big day: read the whole preview); no usable preview (no live prices, the market
shows no trading today, or the run fails). Otherwise exit 0. Report-only: GET from Composer and
Yahoo; it never trades, edits a symphony or writes state. Each run appends one line per engine (and
one for the gate) to composer/results/monitor/preclose-ledger.jsonl.

Usage: preclose.py [--no-ledger]
"""
import concurrent.futures
import datetime
import json
import math
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shadow_runner as sr  # noqa: E402

LEDGER = os.path.join(HERE, "..", "results", "monitor", "preclose-ledger.jsonl")
FRESH_MIN = 15            # a last trade older than this many minutes is stale
DECIDE_BEFORE = 10        # Composer decides ~10 minutes before the close (15:50; 12:50 on a half-day)
SESSION_MIN = 390         # minutes in a full session, for scaling a daily sigma to the minutes left
SIGMA_SCALE = 0.6         # move to 15:50 / (daily sigma x sqrt(minutes / 390)): 0.52-0.57 over 59 calm
                          # sessions (add. 49); a 2-year hourly check puts that window ~13% under the
                          # 2-year level, so 0.6. A daily sigma carries the overnight gap and the open
FLIP_MAX = 3.0            # one-ticker search radius, in sigmas of the minutes left
FLIP_MATERIAL = 0.25      # a flip changes at least this share of the holdings (half-L1)
CLOSE, COULD = 1.0, 2.0   # labels: a move of <= 1 sigma changes it -> close call; <= 2 -> could flip
MARKET = (-2, -1, 1, 2)   # market scenarios, in sigmas of SPY's move left
BETA_N = 60               # sessions for each fund's beta to SPY
STALE_SIGMA = 2.0         # a stale decision ticker that cannot be rebuilt is moved this many sigmas
GATE_SIGMA = 2.0          # gate alert: within this many sigmas of flipping
BIG_DAY = 0.02            # SPY this far off yesterday's close -> big-day alert
TRADING_SHARE = 0.5       # fewer tickers than this share with a bar today -> the market is not trading
GATE = ("SPY", 200)       # HG's gate: current-price(SPY) > moving-average-price(SPY, 200)
HALF_DAYS = {"2026-11-27": "13:00", "2026-12-24": "13:00", "2027-11-26": "13:00"}   # NYSE 13:00 closes;
#             used only when Yahoo gives no trading period for today
# daily-reset funds on one index, with their leverage: a stale price is rebuilt from a fresh sibling
FAMILIES = {
    "S&P 500": {"IVV": 1, "VOO": 1, "SPY": 1, "SSO": 2, "SPXL": 3, "UPRO": 3},
    "Nasdaq-100": {"QQQ": 1, "QQQM": 1, "QLD": 2, "TQQQ": 3, "PSQ": -1, "SQQQ": -3},
    "NYSE Semiconductor": {"SOXX": 1, "SOXL": 3, "SOXS": -3},
    "Technology Select Sector": {"XLK": 1, "TECL": 3},
    "Financial Select Sector": {"XLF": 1, "FAS": 3},
    "S&P Biotechnology Select Industry": {"XBI": 1, "LABU": 3, "LABD": -3},
    "Russell 2000": {"IWM": 1, "TNA": 3},
    "Dow Jones Industrial Average": {"DIA": 1, "UDOW": 3},
    "S&P 500 VIX Short-Term Futures": {"VIXY": 1, "VXX": 1, "UVXY": 1.5, "SVIX": -1, "SVXY": -0.5},
    "S&P 500 VIX Mid-Term Futures": {"VIXM": 1, "VXZ": 1},
    "ICE US Treasury 20+ Year": {"TLT": 1, "TMF": 3, "TMV": -3},
}
# related indexes, used only when no fund on the exact index is fresh; the rebuild is tagged approx
APPROX = {
    "US semiconductors": {"SOXX": 1, "SMH": 1, "USD": 2, "SOXL": 3, "SOXS": -3},
}


# ------------------------------------------------------------------ pure core
def session(now, period=None):
    """today's session in ET: {'date', 'open', 'close', 'decide', 'now', 'left'} (minutes to Composer's
    decision), or None when the exchange is shut today. period: Yahoo's currentTradingPeriod.regular
    for today ({'start', 'end'} epoch seconds), else the static calendar"""
    e = sr.et_now(now)
    today = e.date().isoformat()
    if e.weekday() >= 5 or today in sr.NYSE_HOLIDAYS:
        return None
    opn, close = "09:30", HALF_DAYS.get(today, "16:00")
    if period and period.get("start") and period.get("end"):
        s, t = (sr.et_now(datetime.datetime.fromtimestamp(period[k], tz=datetime.timezone.utc)) for k in ("start", "end"))
        if s.date().isoformat() == today == t.date().isoformat():
            opn, close = s.strftime("%H:%M"), t.strftime("%H:%M")
    decide = sr._hm(sr._min(close) - DECIDE_BEFORE)
    return {"date": today, "open": opn, "close": close, "decide": decide,
            "now": e.strftime("%H:%M"), "left": sr._min(decide) - (e.hour * 60 + e.minute)}


def sigma_factor(minutes_left):
    """daily sigma -> sigma of the move over the minutes left (measured scale x sqrt(t); at least 5 minutes)"""
    return SIGMA_SCALE * math.sqrt(max(minutes_left, 5) / SESSION_MIN)


def last_trade(meta):
    ts = (meta or {}).get("regularMarketTime")
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc) if isinstance(ts, (int, float)) else None


def freshness(data, today, now):
    """({ticker: price now}, {ticker: (reason, minutes since the last trade or None)} stale): a price is
    fresh if it is today's bar and the last trade is at most FRESH_MIN minutes old"""
    fresh, stale = {}, {}
    for t, (adj, _, meta) in data.items():
        lt = last_trade(meta)
        age = (now - lt).total_seconds() / 60 if lt else None
        if today not in adj:
            stale[t] = ("no trade today", None)
        elif age is None:
            stale[t] = ("no trade time", None)
        elif age > FRESH_MIN:
            stale[t] = (sr.et_now(lt).strftime("%H:%M"), age)
        else:
            fresh[t] = adj[today]
    return fresh, stale


def family(t):
    return next((f for f in FAMILIES.values() if t in f), None)


def approx_family(t):
    return next((f for f in APPROX.values() if t in f), None)


def rebuild(t, data, today, fresh):
    """t's price now from a fresh fund on the same index (else a related one): t's previous close x
    (1 + L_t x R), R the index's return today (the sibling's return / its leverage), both returns from
    the same previous session. (price, sibling, approx) or None"""
    if t not in data:
        return None
    prev_t = [d for d in data[t][0] if d < today]
    if not prev_t:
        return None
    for fam, approx in ((family(t), False), (approx_family(t), True)):
        for s in fam or {}:
            if s == t or s not in fresh:
                continue
            prev_s = [d for d in data[s][0] if d < today]
            if not prev_s or prev_s[-1] != prev_t[-1]:
                continue
            r = (fresh[s] / data[s][0][prev_s[-1]] - 1) / fam[s]
            return data[t][0][prev_t[-1]] * (1 + fam[t] * r), s, approx
    return None


def live_prices(data, today, now):
    """({ticker: {date: adjusted close, today: price now}}, {ticker: note}, {ticker: minutes stale}):
    fresh prices as they are; stale ones rebuilt from a sibling where one is fresh, else the last price
    carried, with how long ago it traded (the third dict, carried tickers only)"""
    fresh, stale = freshness(data, today, now)
    prices, notes, carried = {}, {}, {}
    for t, (adj, _, _) in data.items():
        p = dict(adj)
        if t in stale:
            why, age = stale[t]
            rb = rebuild(t, data, today, fresh)
            if rb:
                p[today] = rb[0]
                notes[t] = f"{t} {why} -> via {rb[1]}" + (" (approx)" if rb[2] else "")
            else:
                prev = [d for d in adj if d <= today]
                if prev:
                    p[today] = adj[prev[-1]]
                notes[t] = f"{t} {why} (no fresh sibling: last price used)"
                carried[t] = age
        prices[t] = p
    return prices, notes, carried


def daily_sd(s, d, n=20):
    """population sigma of the n daily returns to d"""
    ds = [x for x in sorted(s) if x <= d][-(n + 1):]
    if len(ds) < n + 1:
        return None
    r = [s[ds[i]] / s[ds[i - 1]] - 1 for i in range(1, len(ds))]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / n)


def beta(s, m, d, n=BETA_N):
    """slope of s's daily returns on m's over the n sessions to d (shared dates); None if under half"""
    ds = sorted(x for x in s if x <= d and x in m)[-(n + 1):]
    if len(ds) < n // 2 + 1:
        return None
    rs = [s[ds[i]] / s[ds[i - 1]] - 1 for i in range(1, len(ds))]
    rm = [m[ds[i]] / m[ds[i - 1]] - 1 for i in range(1, len(ds))]
    ms, mm = sum(rs) / len(rs), sum(rm) / len(rm)
    var = sum((x - mm) ** 2 for x in rm)
    return sum((a - ms) * (b - mm) for a, b in zip(rs, rm)) / var if var else None


def gate(spy, today, factor):
    """HG's gate on SPY's live price: the 200-day average includes today's price, so the gate is open
    iff the price exceeds the average of the other 199 closes (the flip price)"""
    ds = sorted(d for d in spy if d <= today)
    n = GATE[1]
    if not ds or ds[-1] != today or len(ds) < n + 21:
        return None
    px = [spy[d] for d in ds]
    p, thr = px[-1], sum(px[-n:-1]) / (n - 1)
    sma = (sum(px[-n:-1]) + p) / n
    prev_open = px[-2] > sum(px[-n - 1:-1]) / n
    sd = daily_sd(spy, ds[-2])
    dist = thr / p - 1
    return {"spy": round(p, 2), "sma": round(sma, 2), "flip_at": round(thr, 2), "flip_exact": thr, "open": p > thr,
            "open_prev": prev_open, "dist": round(dist, 5), "day": round(p / px[-2] - 1, 5),
            "sigma": round(abs(dist) / (sd * factor), 2) if sd else None}


def gate_in(tree):
    """True if the tree asks current-price(SPY) > moving-average-price(SPY, 200)"""
    t, w = GATE

    def walk(n):
        if n.get("lhs-fn") == "current-price" and n.get("lhs-val") == t and n.get("rhs-fn") == "moving-average-price" \
                and n.get("rhs-val") == t and n.get("comparator") == "gt" and sr.window(n, "rhs") == w:
            return True
        return any(walk(k) for k in n.get("children") or [])
    return walk(tree)


def gate_sides(prices, tree, d, thr):
    """the tree's target with SPY just above and just below the flip price, all else as now"""
    out = []
    for k in (1 + 1e-4, 1 - 1e-4):
        p = {t: prices[t] for t in sr.tree_tickers(tree)}
        p["SPY"] = dict(prices["SPY"])
        p["SPY"][d] = thr * k
        out.append(sr.run_engine(p, tree, d)[1])
    return out


def after(target, live, corridor=None):
    """what Composer holds after today's rebalance: the target; for a threshold engine, the target only
    if some holding is more than `corridor` off it, else today's holdings (no trade)"""
    if corridor and live and sr.distance(target, live)[1] <= corridor:
        return dict(live)
    return dict(target)


def same(a, b):
    return sr.distance(a, b)[0] <= sr.TOL_DAILY


def one_line(e, n=160):
    """an error as one short line (composerlib's HTTP errors carry the response body on new lines)"""
    return " ".join(str(e).split())[:n]


def flip(sim, tree, d, sd_day, trace, outcome, end, factor):
    """the smallest one-ticker move before the rebalance, in sigmas of the minutes left, that changes at
    least FLIP_MATERIAL of what Composer ends up holding (end: target -> holdings): {'ticker', 'move',
    'sigma', 'instead'}, or None within FLIP_MAX. A 25% grid, then bisection for every ticker and side
    whose first flip lies within one grid step of the nearest"""
    trials = []
    for t in sr.trace_tickers(trace, tree):
        sg = sim.sigma(t, sd_day)
        if not sg or d not in sim.p.get(t, {}):
            continue
        sl = sg * factor
        grid, x = [], 1e-4
        while x < FLIP_MAX * sl:
            grid.append(x)
            x *= 1.25
        grid.append(FLIP_MAX * sl)                                    # the edge of the radius itself
        for lo, x in zip([0.0] + grid, grid):
            trials += [(x / sl, t, x, sl, lo), (x / sl, t, -x, sl, -lo)]
    trials.sort()

    def moved(t, x):
        alt = end(sim.what_if(tree, d, t, x))
        return alt if sr.distance(alt, outcome)[0] >= FLIP_MATERIAL else None
    best, cut, done = None, None, set()
    for ratio, t, x, sl, lo in trials:
        if cut is not None and ratio > cut:
            break
        if (t, x > 0) in done:
            continue
        alt = moved(t, x)
        if alt is None:
            continue
        done.add((t, x > 0))
        hi = x                                                        # lo, the grid step before, did not flip
        for _ in range(12):
            mid = (lo + hi) / 2
            a = moved(t, mid)
            if a is None:
                lo = mid
            else:
                hi, alt = mid, a
        cand = {"ticker": t, "move": round(hi, 5), "sigma": round(abs(hi) / sl, 2), "instead": alt}
        if best is None or cand["sigma"] < best["sigma"]:
            best = cand
        if cut is None:
            cut = ratio * 1.25
    return best


def market(prices, tree, d, m, betas):
    """the tree's target had the market moved m (a SPY return) before the decision: each ticker's price
    today moved by its beta x m (no beta: unmoved)"""
    p = {}
    for t in sr.tree_tickers(tree):
        p[t] = dict(prices[t])
        p[t][d] = prices[t][d] * (1 + (betas.get(t) or 0.0) * m)
    return sr.run_engine(p, tree, d)[1]


def uncertainty(sim, tree, d, sd_day, trace, outcome, prices, end, left, betas, spy_sd, carried=None, paused=False):
    """how close the call is: {'flip', 'market': {k: holdings}, 'stale_dep', 'label'}. market: the market
    scenarios whose outcome differs by FLIP_MATERIAL or more; stale_dep: carried stale decision tickers
    whose STALE_SIGMA move (sigma over the minutes since they traded plus the minutes left) does that"""
    if paused:
        return {"flip": None, "market": {}, "stale_dep": [], "label": "firm"}
    factor = sigma_factor(left)
    fl = flip(sim, tree, d, sd_day, trace, outcome, end, factor)
    mk = {}
    if spy_sd:
        for k in MARKET:
            tgt = market(prices, tree, d, k * spy_sd * factor, betas)
            if tgt is not None and sr.distance(end(tgt), outcome)[0] >= FLIP_MATERIAL:
                mk[k] = end(tgt)
    dep = []
    for t, age in sorted((carried or {}).items()):
        sg = sim.sigma(t, sd_day)
        if not sg or d not in sim.p.get(t, {}):
            continue
        x = STALE_SIGMA * sg * sigma_factor((age if age is not None else SESSION_MIN) + max(left, 0))
        if any(sr.distance(end(sim.what_if(tree, d, t, s * x)), outcome)[0] >= FLIP_MATERIAL for s in (1, -1)):
            dep.append(t)
    close = (fl and fl["sigma"] <= CLOSE) or any(abs(k) <= 1 for k in mk)
    could = (fl and fl["sigma"] <= COULD) or mk or dep
    return {"flip": fl, "market": mk, "stale_dep": dep, "label": "close call" if close else "could flip" if could else "firm"}


def engine(eng, cfg, tree, prices, today, s, left, notes, carried, betas, spy_sd, drifted=False):
    """one engine's preview (pure): its symphony record s from Composer (None if unavailable)"""
    era = sr.era_for(cfg, today)
    row = {"engine": eng, "version": era["version"][:8]}
    sim, target, tr = sr.run_engine(prices, tree, today)
    if target is None:
        return dict(row, status="unavailable", note=tr)
    live = sr.live_weights(s) if s else {}
    corridor = cfg.get("corridor")
    paused = bool((s or {}).get("is_paused"))

    def end(w):
        if paused:
            return dict(live)
        return after(w, live, corridor) if live else dict(w)
    out = end(target)
    cal = sr.common_days(prices, sr.tree_tickers(tree), today)
    sd_day = cal[-2] if len(cal) > 1 else today
    dec = sr.decision_tickers(tree)
    unc = uncertainty(sim, tree, today, sd_day, tr, out, prices, end, left, betas, spy_sd,
                      {t: a for t, a in carried.items() if t in dec}, paused)
    row.update(status="ok", target=target, after=out, flip=unc["flip"], market={str(k): v for k, v in unc["market"].items()},
               stale_dep=unc["stale_dep"], label=unc["label"], stale=sorted(notes[t] for t in dec if t in notes))
    caveats = []
    if s is not None:
        row["value"] = round(float(s.get("value") or 0), 2)
        if live:
            turn = sr.distance(out, live)[0]
            row.update(live=live, turnover=round(turn, 4), moves=round(turn * row["value"]))
        else:
            caveats.append("Composer reports no holdings")
        if paused:
            caveats.append("paused in Composer: no rebalance")
        elif corridor and live:
            gap = sr.distance(target, live)[1]
            row["max_gap"] = round(gap, 4)
            if abs(gap - corridor) <= sr.CORRIDOR_SLACK:
                caveats.append(f"its {corridor:.0%} trigger is on the line (largest gap {gap:.1%}): trade or no trade")
                row["label"] = "close call"
        att = s.get("last_rebalance_attempted_on")
        if not paused and isinstance(att, str) and len(cal) > 1 and att < cal[-2]:
            caveats.append(f"Composer's last rebalance attempt was {att}")
    if drifted:
        caveats.append("Composer's live logic differs from the approved version: this preview may not apply")
    if unc["stale_dep"]:
        caveats.append("depends on stale " + ", ".join(unc["stale_dep"]))
    if caveats:
        row["caveats"] = caveats
    return row


def fmt_market(mk, spy_move):
    """'market +1/+2 sigma (SPY +0.15/+0.30%) -> X', one per distinct outcome on each side"""
    parts = []
    for sign in (1, -1):
        groups = []
        for k in sorted((int(k) for k in mk if int(k) * sign > 0), key=abs):
            if groups and same(mk[str(groups[-1][-1])], mk[str(k)]):
                groups[-1].append(k)
            else:
                groups.append([k])
        for g in groups:
            parts.append(f"market {'/'.join(f'{k:+d}' for k in g)} sigma (SPY {'/'.join(f'{100 * k * spy_move:+.2f}' for k in g)}%)"
                         f" -> {sr.fmt_w(mk[str(g[0])])}")
    return parts


def sides_text(sides):
    above, below = sides if sides else (None, None)
    if above is None or below is None:
        return ""
    if same(above, below):
        return f"HG holds {sr.fmt_w(below)} on either side of the line today (its branch today does not read the gate)"
    return f"HG holds {sr.fmt_w(above)} above the line and {sr.fmt_w(below)} below it"


def render(ss, g, rows, notes, failures, spy_move=None, sides=None):
    """(report lines, alert lines)"""
    lines, alerts = [], []
    left = ss["left"]
    when = (f"Composer decides ~{ss['decide']} ({left} min)" if left > 0 else
            f"Composer's rebalance window is open ({ss['decide']}); this read is for the record")
    day = f"; SPY {g['day']:+.2%} today" if g else ""
    lines.append(f"PRE-CLOSE {ss['date']} {ss['now']} ET: {when}{day}")
    if g:
        state = "open" if g["open"] else "CLOSED"
        was = "as at yesterday's close" if g["open"] == g["open_prev"] else f"{'CLOSED' if g['open'] else 'open'} at yesterday's close"
        sig = f"{g['sigma']:.1f} sigma" if g["sigma"] is not None else "sigma n/a"
        st = sides_text(sides)
        lines.append(f"GATE   {state} ({was}): SPY {g['spy']:.2f} vs 200-day {g['sma']:.2f}; flips at {g['flip_at']:.2f} "
                     f"({g['dist']:+.2%}, {sig})" + (f"; stale: {g['stale']}" if g.get("stale") else ""))
        if g["open"] != g["open_prev"]:
            alerts.append(f"GATE {'REOPENS' if g['open'] else 'CLOSES'} AT TODAY'S REBALANCE — SPY {g['spy']:.2f} is "
                          f"{'above' if g['open'] else 'below'} its 200-day average {g['sma']:.2f} at {ss['now']} ET, "
                          f"{'open' if g['open'] else 'closed'} for the ~{ss['decide']} rebalance unless SPY crosses "
                          f"{g['flip_at']:.2f} first ({g['dist']:+.2%})." + (f" {st}." if st else ""))
        elif g["sigma"] is not None and g["sigma"] <= GATE_SIGMA:
            alerts.append(f"GATE ON THE LINE — SPY {g['spy']:.2f}, {g['dist']:+.2%} from the {g['flip_at']:.2f} that "
                          f"{'closes' if g['open'] else 'reopens'} HG's gate at ~{ss['decide']} ({g['sigma']:.1f} sigma of the "
                          f"minutes left)." + (f" {st}." if st else ""))
        if abs(g["day"]) >= BIG_DAY:
            alerts.append(f"BIG DAY — SPY {g['day']:+.2%} at {ss['now']} ET. What the rebalance at ~{ss['decide']} will do "
                          f"is in the preview; overrides are the owner's call in the Composer app.")
    shown = set()
    for r in rows:
        if r["status"] != "ok":
            lines.append(f"{r['engine']:6s} unavailable: {r.get('note')}")
            continue
        val = f"${r['value']:,.0f} " if r.get("value") is not None else ""
        if "live" not in r:
            what = f"logic {sr.fmt_w(r['after'])} (Composer holdings unavailable)"
        elif same(r["after"], r["live"]):
            what = f"no change ({sr.fmt_w(r['live'])})"
        else:
            what = f"{sr.fmt_w(r['live'])} -> {sr.fmt_w(r['after'])} (${r['moves']:,} moves)"
        fl = r["flip"]
        parts = fmt_market(r.get("market") or {}, spy_move or 0.0)
        if fl:
            parts.append(f"{fl['ticker']} {fl['move']:+.2%} ({fl['sigma']:.1f} sigma) -> {sr.fmt_w(fl['instead'])}")
        how = (f"{r['label']}: " + "; ".join(parts) if parts else
               f"{r['label']}: no 2-sigma market move or {FLIP_MAX:g}-sigma one-ticker move changes a quarter of it")
        extra = "".join(f"; {x}" for x in r.get("caveats") or [])
        if r.get("max_gap") is not None and not any("trigger" in x for x in r.get("caveats") or []):
            extra += f"; largest gap {r['max_gap']:.1%} vs the {r.get('corridor', 0.1):.0%} trigger"
        weak = [n for n in r.get("stale") or [] if "approx" in n or "last price used" in n]
        if weak:
            extra += f"; stale: {', '.join(weak)}"
        shown |= {n.split()[0] for n in r.get("stale") or []}
        lines.append(f"{r['engine']:6s} {val}{what}. {how}{extra}")
    if failures:
        lines.append("unavailable: " + "; ".join(failures))
    via = {}
    for t, n in sorted(notes.items()):
        if " -> via " in n and "approx" not in n:
            via.setdefault(n.split(" -> via ")[1], []).append(t)
    if via:
        lines.append("stale quotes rebuilt from same-index funds: " + "; ".join(f"{', '.join(ts)} via {s}" for s, ts in sorted(via.items())))
    rest = [t for t in notes if t not in shown and not (g and t == "SPY")]
    if rest:
        lines.append(f"({len(rest)} more stale price(s), on tickers no decision reads today: {', '.join(sorted(rest))})")
    return lines, alerts


# ------------------------------------------------------------------ I/O
def fetch_live(t, rng="2y", tries=2):
    """({date: adjusted close}, {date: raw close}, chart meta) from Yahoo daily bars; in a session the
    last bar is today's, at the latest trade (meta['regularMarketTime'])"""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}"
           f"?range={rng}&interval=1d&events=div%2Csplit")
    err = None
    for k in range(tries):
        try:
            res = sr._chart(url)
            adj, raw = sr.parse_daily(res)
            if adj:
                return adj, raw, res.get("meta") or {}
            err = "empty series"
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(1 + k)
    raise RuntimeError(f"Yahoo {t}: {err}")


def fetch_all(tickers, fetch=None):
    fetch = fetch or fetch_live
    out, bad = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch, t): t for t in sorted(tickers)}
        for f in concurrent.futures.as_completed(futs):
            try:
                out[futs[f]] = f.result()
            except Exception as e:  # noqa: BLE001
                bad[futs[f]] = str(e)[:120]
    return out, bad


def append_ledger(rows, path=None):
    path = path or LEDGER
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a") as f:
        f.write("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))


def preview(now, get_meta, get_drift=None, fetch=None):
    """(lines, alerts, ledger rows); get_meta() -> Composer's symphony-stats-meta list (may raise);
    get_drift(cfg_all) -> (engines whose live logic differs from the approved, failure notes)"""
    cfg_all = sr.load_manifest()
    day0 = sr.et_now(now).date().isoformat()
    trees = {e: sr.load_tree(sr.era_for(c, day0) or c["eras"][-1]) for e, c in cfg_all.items()}
    tick = {GATE[0]}
    for t in trees.values():
        tick |= sr.tree_tickers(t)
    data, bad = fetch_all(tick, fetch)
    period = ((data.get("SPY") or (None, None, {}))[2].get("currentTradingPeriod") or {}).get("regular")
    ss = session(now, period)
    if ss is None:
        return [f"PRE-CLOSE: no session today ({day0})"], [], []
    if ss["now"] < ss["open"]:
        return [f"PRE-CLOSE {ss['date']}: the session opens at {ss['open']} ET; nothing to preview yet"], [], []
    if ss["now"] >= ss["close"]:
        return [f"PRE-CLOSE {ss['date']}: the session closed at {ss['close']} ET; today's rebalance has run "
                f"(the post-close check reports it)"], [], []
    today = ss["date"]
    head = [f"PRE-CLOSE {today} {ss['now']} ET: Composer decides ~{ss['decide']} ({ss['left']} min)"]
    if not data:
        return head, [f"PRE-CLOSE UNAVAILABLE — no prices from Yahoo ({'; '.join(f'{t}: {one_line(e)}' for t, e in sorted(bad.items())[:3])}). "
                      f"Today's rebalance runs at ~{ss['decide']} ET unpreviewed."], []
    trading = sum(today in a for a, _, _ in data.values())
    if trading < TRADING_SHARE * len(data):
        return head, [f"PRE-CLOSE UNAVAILABLE — only {trading} of {len(data)} tickers show a trade today: the market may "
                      f"be shut or the feed stalled. Nothing previewed; check before ~{ss['decide']} ET."], []
    _, stale = freshness(data, today, now)
    need = set()
    for t in stale:
        need |= (set(family(t) or {}) | set(approx_family(t) or {})) - set(data)
    if need:
        more, _ = fetch_all(need, fetch)
        data.update(more)
    prices, notes, carried = live_prices(data, today, now)
    failures = [f"Yahoo {t}: {one_line(e)}" for t, e in sorted(bad.items())]
    if int(today[:4]) > max(int(d[:4]) for d in sr.NYSE_HOLIDAYS):
        failures.append("the NYSE holiday and half-day lists end before this year: extend shadow_runner.NYSE_HOLIDAYS "
                        "and preclose.HALF_DAYS")
    factor = sigma_factor(ss["left"])
    g = gate(prices["SPY"], today, factor) if "SPY" in prices else None
    spy_prev = sorted(d for d in prices.get("SPY", {}) if d < today)
    spy_sd = daily_sd(prices["SPY"], spy_prev[-1]) if spy_prev else None
    betas = {t: beta(prices[t], prices["SPY"], spy_prev[-1]) for t in prices} if spy_prev else {}
    if g and "SPY" in notes:
        g["stale"] = notes["SPY"]
    sides = None
    if g and gate_in(trees["HG"]) and all(t in prices for t in sr.tree_tickers(trees["HG"])):
        try:
            sides = gate_sides(prices, trees["HG"], today, g["flip_exact"])
        except Exception as e:  # noqa: BLE001
            failures.append(f"gate sides: {one_line(e)}")
    elif g:
        failures.append("HG's approved tree has no SPY 200-day condition; the gate line is SPY's alone")
    try:
        meta = {s.get("id"): s for s in get_meta() if isinstance(s, dict)}
    except (Exception, SystemExit) as e:  # noqa: BLE001
        meta = None
        failures.append(f"Composer holdings: {one_line(e)}")
    drift = set()
    if get_drift:
        try:
            drift, dn = get_drift(cfg_all)
            failures += dn
        except (Exception, SystemExit) as e:  # noqa: BLE001
            failures.append(f"logic-drift check: {one_line(e)}")
    rows = []
    for eng, cfg in cfg_all.items():
        try:
            miss = sorted(t for t in sr.tree_tickers(trees[eng]) if t not in prices)
            if miss:
                rows.append({"engine": eng, "status": "unavailable", "note": f"no prices for {', '.join(miss)}"})
                continue
            s = meta.get(cfg["symphony"]) if meta is not None else None
            if meta is not None and s is None:
                failures.append(f"{eng} is not in Composer's symphony list")
            r = engine(eng, cfg, trees[eng], prices, today, s, ss["left"], notes, carried, betas, spy_sd, eng in drift)
            if cfg.get("corridor"):
                r["corridor"] = cfg["corridor"]
            rows.append(r)
        except Exception as e:  # noqa: BLE001
            rows.append({"engine": eng, "status": "unavailable", "note": f"preview error: {one_line(repr(e))}"})
    spy_move = spy_sd * factor if spy_sd else None
    lines, alerts = render(ss, g, rows, {t: n for t, n in notes.items() if t in tick}, failures, spy_move, sides)
    if g is None or all(r["status"] != "ok" for r in rows):
        alerts.append("PRE-CLOSE UNAVAILABLE — " + ("; ".join(failures) or "no live SPY price") +
                      ". Today's rebalance runs at ~" + ss["decide"] + " ET unpreviewed.")
    stamp = {"date": today, "time": ss["now"], "left": ss["left"], "src": "preclose"}
    led = [dict(stamp, engine="GATE", **{k: v for k, v in g.items() if k != "flip_exact"},
                sides=sides)] if g else []
    led += [dict(stamp, **{k: v for k, v in r.items() if k != "corridor"}) for r in rows]
    return lines, alerts, led


def main():
    import composerlib as cl
    now = datetime.datetime.now(datetime.timezone.utc)

    def get_meta():
        return cl.get(f"/portfolio/accounts/{cl.default_account()}/symphony-stats-meta", timeout=30)["symphonies"]

    def get_drift(cfg_all):
        """engines whose live tree differs from the approved one, in parallel with a short timeout"""
        def one(item):
            eng, cfg = item
            return eng, sr.check_drift({eng: cfg}, lambda p: cl.get(p, timeout=20), {}, sr.et_now(now))
        out, notes = set(), []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            for eng, (a, n) in ex.map(one, cfg_all.items()):
                if a:
                    out.add(eng)
                notes += [x.replace("shadow: ", "") for x in n if "unavailable" in x]
        return out, notes
    try:
        lines, alerts, led = preview(now, get_meta, get_drift)
    except (Exception, SystemExit) as e:  # noqa: BLE001  the routine must hear about a failed preview
        lines, alerts, led = [], [f"PRE-CLOSE UNAVAILABLE — the preview failed: {one_line(repr(e))}"], []
    print("\n".join(lines))
    if alerts:
        print(f"\n{len(alerts)} ALERT(S):")
        for a in alerts:
            print(f"  !! {a}")
    if led and "--no-ledger" not in sys.argv:
        try:
            append_ledger(led)
        except OSError as e:
            print(f"(preclose ledger not written: {e})")
    sys.exit(2 if alerts else 0)


if __name__ == "__main__":
    main()
