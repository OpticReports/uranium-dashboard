#!/usr/bin/env python3
"""Pre-close preview (results.md addendum 49): what Composer's ~15:50 ET rebalance is about to do,
read about 35 minutes before it, so the owner can act in the Composer app if they choose to.

The daily monitor reports a session after its rebalance (17:35 ET). This runs at 15:15 ET (12:15 on
a half-day) on live prices, with the approved trees and the evaluator of the shadow runner
(shadow_runner.py, add. 48):
  GATE    HG's condition SPY > its 200-day average, on SPY's live price: the SPY price that flips it
          (the average includes today's price, as Composer reads it at the rebalance), and whether it
          flips today
  engine  holdings now -> what the approved logic holds at live prices (KMLM: only if some asset is
          more than 10pp off the target, else no trade), the dollars that move, and the smallest
          one-ticker move before the rebalance that changes at least a quarter of what it ends up
          holding, in sigmas of the move the ticker can make in the minutes left: 20-session daily
          sigma x 0.52 x sqrt(minutes / 390), the scale measured on 59 sessions of 5-minute bars
          (add. 49): <= 1 coin-flip, <= 2 could flip, else firm (3 sigma ~ the 99th percentile)
Live prices are Yahoo's latest trades. A price older than 15 minutes is stale: it is rebuilt from a
fresh fund on the same index (daily-reset leverage: previous close x (1 + L x the index's return
today)), else used as is and named in the report.

Alerts (exit 2): the gate flips today or sits within 2 sigma of flipping; SPY 2% or more off
yesterday's close (a big day: read the whole preview); no preview at all. Otherwise exit 0.
Report-only: GET from Composer and Yahoo; it never trades, edits a symphony or writes state. Each
run appends one line per engine (and one for the gate) to composer/results/monitor/
preclose-ledger.jsonl, the record of how well the preview called the rebalance.

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
SIGMA_SCALE = 0.52        # measured move to 15:50 / (daily sigma x sqrt(minutes / 390)): 0.524 at 35 min on
                          # liquid tickers, 0.52-0.57 from 10 to 50 min (add. 49); a daily sigma carries the
                          # overnight gap and the open, the last hour moves about half as much per sqrt-minute
FLIP_MAX = 3.0            # flip search radius, in sigmas of the minutes left
FLIP_MATERIAL = 0.25      # a flip changes at least this share of the holdings (half-L1)
COIN, COULD = 1.0, 2.0    # flip labels: <= 1 sigma coin-flip, <= 2 could flip, else firm
GATE_SIGMA = 2.0          # gate alert: within this many sigmas of flipping
BIG_DAY = 0.02            # SPY this far off yesterday's close -> big-day alert
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


# ------------------------------------------------------------------ pure core
def session(now, period=None):
    """today's session in ET: {'date', 'open', 'close', 'decide', 'left'} (minutes to Composer's decision),
    or None when the exchange is shut today. period: Yahoo's currentTradingPeriod.regular for today
    ({'start', 'end'} epoch seconds), else the static calendar"""
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
    """({ticker: price now}, {ticker: 'HH:MM' or 'no trade today'} stale): a price is fresh if it is
    today's bar and the last trade is at most FRESH_MIN minutes old"""
    fresh, stale = {}, {}
    for t, (adj, _, meta) in data.items():
        lt = last_trade(meta)
        if today not in adj:
            stale[t] = "no trade today"
        elif lt is None or (now - lt).total_seconds() > FRESH_MIN * 60:
            stale[t] = sr.et_now(lt).strftime("%H:%M") if lt else "no trade time"
        else:
            fresh[t] = adj[today]
    return fresh, stale


def family(t):
    return next((f for f in FAMILIES.values() if t in f), None)


def rebuild(t, data, today, fresh):
    """t's price now from a fresh fund on the same index: t's previous close x (1 + L_t x R), R the
    index's return today (the sibling's return / its leverage). (price, sibling) or None"""
    fam = family(t)
    if not fam or t not in data:
        return None
    prev_t = [d for d in data[t][0] if d < today]
    if not prev_t:
        return None
    for s in fam:
        if s == t or s not in fresh:
            continue
        prev_s = [d for d in data[s][0] if d < today]
        if not prev_s:
            continue
        r = (fresh[s] / data[s][0][prev_s[-1]] - 1) / fam[s]
        return data[t][0][prev_t[-1]] * (1 + fam[t] * r), s
    return None


def live_prices(data, today, now):
    """({ticker: {date: adjusted close, today: price now}}, {ticker: note}): fresh prices as they are,
    stale ones rebuilt from a sibling where one is fresh, else the last price carried (noted)"""
    fresh, stale = freshness(data, today, now)
    prices, notes = {}, {}
    for t, (adj, _, _) in data.items():
        p = dict(adj)
        if t in stale:
            rb = rebuild(t, data, today, fresh)
            if rb:
                p[today] = rb[0]
                notes[t] = f"{t} {stale[t]} -> via {rb[1]}"
            else:
                prev = [d for d in adj if d <= today]
                if prev:
                    p[today] = adj[prev[-1]]
                notes[t] = f"{t} {stale[t]} (no fresh sibling: last price used)"
        prices[t] = p
    return prices, notes


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
    r = [px[i] / px[i - 1] - 1 for i in range(len(px) - 21, len(px) - 1)]     # 20 sessions to yesterday
    m = sum(r) / len(r)
    sd = math.sqrt(sum((x - m) ** 2 for x in r) / len(r))
    dist = thr / p - 1
    return {"spy": round(p, 2), "sma": round(sma, 2), "flip_at": round(thr, 2), "open": p > thr,
            "open_prev": prev_open, "dist": round(dist, 5), "day": round(p / px[-2] - 1, 5),
            "sigma": round(abs(dist) / (sd * factor), 2) if sd else None}


def gate_in(tree):
    """True if the tree reads current-price(SPY) against moving-average-price(SPY, 200)"""
    t, w = GATE

    def walk(n):
        if n.get("lhs-fn") == "current-price" and n.get("lhs-val") == t and n.get("rhs-fn") == "moving-average-price" \
                and n.get("rhs-val") == t and sr.window(n, "rhs") == w:
            return True
        return any(walk(k) for k in n.get("children") or [])
    return walk(tree)


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


def flip(sim, tree, d, sd_day, trace, outcome, live, corridor, factor):
    """the smallest one-ticker move before the rebalance, in sigmas of the minutes left, that changes
    at least FLIP_MATERIAL of what Composer ends up holding: {'ticker', 'move', 'sigma', 'instead'}, or
    None within FLIP_MAX"""
    trials = []
    for t in sr.trace_tickers(trace, tree):
        sg = sim.sigma(t, sd_day)
        if not sg or d not in sim.p.get(t, {}):
            continue
        sl = sg * factor
        k = 0
        while 1e-4 * 1.25 ** k <= FLIP_MAX * sl:
            x = 1e-4 * 1.25 ** k
            trials += [(x / sl, t, x), (x / sl, t, -x)]
            k += 1
    for ratio, t, x in sorted(trials):
        alt = after(sim.what_if(tree, d, t, x), live, corridor)
        if sr.distance(alt, outcome)[0] >= FLIP_MATERIAL:
            return {"ticker": t, "move": round(x, 5), "sigma": round(ratio, 2), "instead": alt}
    return None


def label(fl):
    if fl is None:
        return "firm"
    return "coin-flip" if fl["sigma"] <= COIN else "could flip" if fl["sigma"] <= COULD else "firm"


def engine(eng, cfg, tree, prices, today, s, factor, notes, drifted=False):
    """one engine's preview (pure): its symphony record s from Composer (None if unavailable)"""
    era = sr.era_for(cfg, today)
    row = {"engine": eng, "version": era["version"][:8]}
    sim, target, tr = sr.run_engine(prices, tree, today)
    if target is None:
        return dict(row, status="unavailable", note=tr)
    live = sr.live_weights(s) if s else {}
    corridor = cfg.get("corridor")
    out = after(target, live, corridor) if live else target
    prev = [d for d in prices["SPY"] if d < today]
    fl = flip(sim, tree, today, prev[-1], tr, out, live, corridor, factor) if prev else None
    path = set(sr.trace_tickers(tr, tree))
    row.update(status="ok", target=target, after=out, flip=fl, label=label(fl),
               stale=sorted(n for t, n in notes.items() if t in path))
    if s:
        value = float(s.get("value") or 0)
        turn = sr.distance(out, live)[0] if live else None
        row.update(live=live, value=round(value, 2), turnover=round(turn, 4) if turn is not None else None,
                   moves=round(turn * value) if turn is not None else None)
        if corridor and live:
            row["max_gap"] = round(sr.distance(target, live)[1], 4)
        if s.get("is_paused"):
            row["caveat"] = "paused in Composer: no rebalance"
        att = s.get("last_rebalance_attempted_on")
        if isinstance(att, str) and prev and att < prev[-1]:
            row["caveat"] = f"Composer's last rebalance attempt was {att}"
    if drifted:
        row["caveat"] = "Composer's live logic differs from the approved version: this preview may not apply"
    return row


def render(ss, g, rows, notes, failures):
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
        lines.append(f"GATE   {state} ({was}): SPY {g['spy']:.2f} vs 200-day {g['sma']:.2f}; flips at {g['flip_at']:.2f} "
                     f"({g['dist']:+.2%}, {g['sigma']:.1f} sigma)" + (f"; stale: {g['stale']}" if g.get("stale") else ""))
        if g["open"] != g["open_prev"]:
            alerts.append(f"GATE {'REOPENS' if g['open'] else 'CLOSES'} AT TODAY'S REBALANCE — SPY {g['spy']:.2f} is "
                          f"{'above' if g['open'] else 'below'} its 200-day average {g['sma']:.2f} at {ss['now']} ET; "
                          f"HG {'returns to its own logic' if g['open'] else 'moves to BIL'} at ~{ss['decide']} unless SPY "
                          f"crosses {g['flip_at']:.2f} first ({g['dist']:+.2%}).")
        elif g["sigma"] is not None and g["sigma"] <= GATE_SIGMA:
            alerts.append(f"GATE ON THE LINE — SPY {g['spy']:.2f}, {g['dist']:+.2%} from the {g['flip_at']:.2f} that "
                          f"{'closes' if g['open'] else 'reopens'} HG's gate at ~{ss['decide']} ({g['sigma']} sigma of the "
                          f"minutes left).")
        if abs(g["day"]) >= BIG_DAY:
            alerts.append(f"BIG DAY — SPY {g['day']:+.2%} at {ss['now']} ET. What the rebalance at ~{ss['decide']} will do "
                          f"is in the preview; overrides are the owner's call in the Composer app.")
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
        how = (f"{r['label']}: {fl['ticker']} {fl['move']:+.2%} ({fl['sigma']:.1f} sigma) -> {sr.fmt_w(fl['instead'])}"
               if fl else f"firm (no one-ticker move within {FLIP_MAX:g} sigma)")
        extra = "".join(f"; {x}" for x in [r.get("caveat")] if x)
        if r.get("max_gap") is not None:
            extra += f"; largest gap {r['max_gap']:.1%} vs the {r.get('corridor', 0.1):.0%} trigger"
        if r.get("stale"):
            extra += f"; stale: {', '.join(r['stale'])}"
        lines.append(f"{r['engine']:6s} {val}{what}. {how}{extra}")
    if failures:
        lines.append("unavailable: " + "; ".join(failures))
    rest = [n for n in notes.values() if not any(n in r.get("stale", []) for r in rows)]
    if rest:
        lines.append(f"({len(rest)} more stale price(s), none on today's decision paths)")
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
    get_drift(cfg_all) -> set of engines whose live logic differs from the approved (may raise)"""
    cfg_all = sr.load_manifest()
    trees = {e: sr.load_tree(sr.era_for(c, sr.et_now(now).date().isoformat()) or c["eras"][-1]) for e, c in cfg_all.items()}
    tick = {GATE[0]}
    for t in trees.values():
        tick |= sr.tree_tickers(t)
    data, bad = fetch_all(tick, fetch)
    period = ((data.get("SPY") or (None, None, {}))[2].get("currentTradingPeriod") or {}).get("regular")
    ss = session(now, period)
    if ss is None:
        return [f"PRE-CLOSE: no session today ({sr.et_now(now):%Y-%m-%d})"], [], []
    if ss["now"] < ss["open"]:
        return [f"PRE-CLOSE {ss['date']}: the session opens at {ss['open']} ET; nothing to preview yet"], [], []
    if ss["now"] >= ss["close"]:
        return [f"PRE-CLOSE {ss['date']}: the session closed at {ss['close']} ET; today's rebalance has run "
                f"(the post-close check reports it)"], [], []
    today = ss["date"]
    _, stale = freshness(data, today, now)
    need = set()
    for t in stale:
        need |= set(family(t) or {}) - set(data)
    if need:
        more, bad2 = fetch_all(need, fetch)
        data.update(more)
        bad.update({t: e for t, e in bad2.items() if t in tick})
    prices, notes = live_prices(data, today, now)
    factor = sigma_factor(ss["left"])
    failures = [f"Yahoo {t}: {one_line(e)}" for t, e in sorted(bad.items())]
    g = gate(prices["SPY"], today, factor) if "SPY" in prices else None
    if g and "SPY" in notes:
        g["stale"] = notes["SPY"]
    try:
        meta = {s.get("id"): s for s in get_meta() if isinstance(s, dict)}
    except (Exception, SystemExit) as e:  # noqa: BLE001
        meta = None
        failures.append(f"Composer holdings: {one_line(e)}")
    drift = set()
    if get_drift:
        try:
            drift = get_drift(cfg_all)
        except (Exception, SystemExit) as e:  # noqa: BLE001
            failures.append(f"logic-drift check: {one_line(e)}")
    rows = []
    for eng, cfg in cfg_all.items():
        try:
            if any(t not in prices for t in sr.tree_tickers(trees[eng])):
                miss = sorted(t for t in sr.tree_tickers(trees[eng]) if t not in prices)
                rows.append({"engine": eng, "status": "unavailable", "note": f"no prices for {', '.join(miss)}"})
                continue
            s = meta.get(cfg["symphony"]) if meta is not None else None
            r = engine(eng, cfg, trees[eng], prices, today, s, factor, notes, eng in drift)
            if cfg.get("corridor"):
                r["corridor"] = cfg["corridor"]
            rows.append(r)
        except Exception as e:  # noqa: BLE001
            rows.append({"engine": eng, "status": "unavailable", "note": f"preview error: {e!r}"})
    if g and not gate_in(trees["HG"]):
        failures.append("HG's approved tree has no SPY 200-day condition; the gate line is SPY's alone")
    lines, alerts = render(ss, g, rows, notes, failures)
    if g is None or all(r["status"] != "ok" for r in rows):
        alerts.append("PRE-CLOSE UNAVAILABLE — " + ("; ".join(failures) or "no live prices") +
                      ". Today's rebalance runs at ~" + ss["decide"] + " ET unpreviewed.")
    stamp = {"date": today, "time": ss["now"], "left": ss["left"], "src": "preclose"}
    led = [dict(stamp, engine="GATE", **g)] if g else []
    led += [dict(stamp, **{k: v for k, v in r.items() if k not in ("corridor",)}) for r in rows]
    return lines, alerts, led


def main():
    import composerlib as cl
    now = datetime.datetime.now(datetime.timezone.utc)

    def get_meta():
        return cl.get(f"/portfolio/accounts/{cl.default_account()}/symphony-stats-meta")["symphonies"]

    def get_drift(cfg_all):
        out = set()
        for eng, cfg in cfg_all.items():
            a, _ = sr.check_drift({eng: cfg}, cl.get, {}, sr.et_now(now))
            if a:
                out.add(eng)
        return out
    lines, alerts, led = preview(now, get_meta, get_drift)
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
