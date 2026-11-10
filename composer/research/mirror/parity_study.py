#!/usr/bin/env python3
"""Parity study for the IBKR mirror of the Composer book (composer/IBKR_MIRROR.md): the DRY simulator
(scripts/mirror_dry.py, which drives ibkr-executor/app/mirror_core.py unchanged) run over the shadow
ledger's history and measured against Composer's realised record.

  primary      the whole window in minute mode: mirror_brain.build(pinned=True) as of 15:54:00 ET (the
               end of the decision bar), sells at market and buys as limit orders at the bar ending
               15:55, dividends and splits through the core under rule "composer"
  timing       the same with the decision at 15:55 (the first run's instant), 15:50 and 15:45; fills at
               the official close instead; and close mode (the ledger's target, fills at the close).
               Every run is also made with the buy limit re-quoted at the fill, so that every buy fills
               and the timing comparison is not decided by which buys a fixed limit happened to miss
  sensitivity  dividend rule "holder"; the buy limit re-quoted at the fill, and no limit at all;
               slippage 0 / 2 / 5 bps; the seed at Composer's own engine weights; ledger gaps filled
  edge checks  what a later (or earlier) fill minute was worth on Composer's rotation days, with a
               placebo; knife-edge carry
  cross-checks the simulator's as-of history against the brain's own replay path on every session
               (offline, the same bars), and against `mirror_brain.py --at "D 15:54"` on the days given

Writes results/mirror/backfill-<date>.json (read by make_mirror_chart.py). Read-only: Yahoo, FMP
(key FMP_API_KEY, never printed), the shadow ledger, the monitor snapshots (git history, read-only).

Usage: parity_study.py --cache DIR [--start D] [--end D] [--cross-check D,D] [--out FILE]
"""
import argparse
import datetime
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "..", "scripts")
sys.path.insert(0, SCRIPTS)
import mirror_dry as md  # noqa: E402
import shadow_runner as sr  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "results", "mirror")
ENGINES = ("HG", "KMLM", "SLEEVE", "HARV")
VIX_SLEEVE = {"PULS", "ZVOL", "VXZ"}              # KMLM's 25% part; everything else is the switcher's 75% leg
POLICY_BOOK = {"HG": 104.8, "KMLM": 81.8, "SLEEVE": 81.8, "HARV": 38.3}   # Composer's book 2026-11-09, $k
PRIMARY = "15:54"
RUNS = ((PRIMARY, md.DECIDE, "next"), ("15:55", "15:55", "next"), ("15:50", "15:50", "next"), ("15:45", "15:45", "next"),
        ("15:45 -> close", "15:45", "close"), ("15:54 -> close", md.DECIDE, "close"))
LATER = ("+1", "+2", "+3", "+4", "+5", "close")       # the 15:54 decisions filled at the bar ending 15:55 .. 15:59, and at the close
FILL_MINUTES = ("15:50", "15:51", "15:52", "15:53", "15:54", "15:55", "15:56", "15:57", "15:58", "15:59", "16:00")
FILL_BASE = "15:53"                               # Composer's median fill minute (results/slippage-ledger.json)


def stats(xs):
    n = len(xs)
    if not n:
        return {"n": 0, "mean": None, "sd": None, "t": None}
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "mean": round(m, 3), "sd": round(sd, 3), "t": round(m / (sd / math.sqrt(n)), 2) if sd > 0 else None}


def headline(res):
    """one row per run for the comparison tables"""
    p = res["parity"]
    b = p["book"]
    ks = ("n_daily", "mean_bps", "sd_bps", "t", "corr", "beta", "cum_mirror", "cum_composer", "cum_gap", "mean_abs_bps")
    pick = lambda t: {k: t.get(k) for k in ks}   # noqa: E731
    row = {"decisions": {e: {"agree": v["agree"], "n": v["n"], "share": v["share"], "classes": v["classes"]}
                         for e, v in p["decisions"].items()},
           "book": pick(b["tracking"]), "book_ex": pick(b["tracking_ex_no_rebalance"]),
           "book_gross": pick(b["tracking_gross"]), "book_gross_ex": pick(b["tracking_gross_ex_no_rebalance"]),
           "book_px": pick(b["tracking_price_basis"]), "book_px_ex": pick(b["tracking_price_basis_ex_no_rebalance"]),
           "costs": b["costs"], "cash": b["cash"], "limit_buys": b["limit_buys"], "distributions": b["distributions"],
           "overspent": b["overspent"], "book_cash_low": b["book_cash_low"], "problems": len(b["problems"]),
           "noise_floor": noise_floor(p), "engines": {},
           "book_worst": [{k: w.get(k) for k in ("d0", "date", "n", "diff_bps", "cause")}
                          for w in b["tracking"].get("worst", [])[:5]]}
    for e, blk in p["engines"].items():
        row["engines"][e] = dict(pick(blk["tracking"]), ex_cum_gap=blk["tracking_ex_no_rebalance"].get("cum_gap"),
                                 gross_cum_gap=blk["tracking_gross"].get("cum_gap"),
                                 gross_mean_bps=blk["tracking_gross"].get("mean_bps"),
                                 px_cum_gap=blk["tracking_price_basis"].get("cum_gap"))
    return row


def noise_floor(par):
    """the daily difference on sessions when neither side traded (same holdings in, no rotation): what
    the comparison itself adds (Composer's snapshot marks vs official closes, the mirror's idle cash)"""
    out, pooled = {}, []
    for e, blk in par["engines"].items():
        xs = [s["diff_bps"] for s in blk["series"] if s["n"] == 1 and (s.get("cause") or "").startswith("no trade")]
        out[e] = stats(xs)
        pooled += xs
    out["all"] = stats(pooled)
    return out


def composer_fills(path=None):
    """when Composer's own fills happened (results/slippage-ledger.json, add. 14b): counts by ET minute"""
    path = path or os.path.join(HERE, "..", "..", "results", "slippage-ledger.json")
    try:
        with open(path) as f:
            fills = list(json.load(f)["fills"].values())
    except (OSError, ValueError, KeyError):
        return None
    by = {}
    for f in fills:
        by[f["hhmm"]] = by.get(f["hhmm"], 0) + 1
    big = [f for f in fills if f.get("notional", 0) > 1000]
    w = sum(f["notional"] for f in big)
    return {"n": len(fills), "from": min(f["d"] for f in fills), "to": max(f["d"] for f in fills), "by_minute": dict(sorted(by.items())),
            "slip_bps_notional_weighted": round(sum(f["slip_bps"] * f["notional"] for f in big) / w, 2) if w else None}


def composer_own_book(composer, cal, since):
    """Composer's own book: each span's engine returns at COMPOSER's engine values at the span's start
    (its real weights, deposits and transfers included in the weights, not in the returns)"""
    spans = {e: {(s["d0"], s["d1"]): s for s in md.composer_spans(composer.get(e) or {}, cal)} for e in ENGINES}
    keys = sorted({k for e in spans for k in spans[e] if k[0] >= since})
    out = []
    for k in keys:
        es = [e for e in ENGINES if k in spans[e]]
        if len(es) != len([e for e in ENGINES if any(a <= k[0] for a, _ in spans[e])]):
            continue
        vals = {e: composer[e][k[0]]["value"] for e in es}
        tot = sum(vals.values())
        out.append({"d0": k[0], "d1": k[1], "n": spans[es[0]][k]["n"], "ret": sum(vals[e] / tot * spans[e][k]["ret"] for e in es),
                    "weights": {e: round(vals[e] / tot, 4) for e in es}})
    return out


def fill_profile(shadow, market, minutes, times=FILL_MINUTES, base=FILL_BASE, stale=30):
    """Composer's fills cluster at 15:52-15:53 ET (258 of the 328 fills in results/slippage-ledger.json).
    On every engine-day Composer rotated (holdings moved more than 1.5% off yesterday's, drifted), what
    filling at minute X instead of at `base` was worth: -(sum over tickers of the weight traded x
    (price at X / price at base - 1)), in bps of the sleeve; positive when what Composer bought was
    cheaper at X (or what it sold dearer). Price at hh:mm: the close of the last traded 1-minute bar
    ENDING at or before it; 16:00 is the official close. Placebo: the same weights on the PREVIOUS
    session's same minutes, when that rotation did not happen."""
    cal = market.calendar()
    rows = []

    def px(t, d, hhmm):
        if hhmm == "16:00":
            return market.raw.get(t, {}).get(d)
        bars = minutes.get(t, d)
        end = sr._min(sr.session_close(d)) - (sr._min("16:00") - sr._min(hhmm)) - 1
        ks = [k for k in bars if end - stale <= sr._min(k) <= end]
        return bars[max(ks, key=sr._min)] if ks else None

    for (d, e), led in sorted(shadow.items()):
        prev = market.prev(d)
        a = shadow.get((prev, e)) if prev else None
        if not a or not a.get("live") or not led.get("live") or led.get("status") == "no-rebalance" or led.get("live_asof", d) != d:
            continue
        if led.get("snapshot") and md.snapshot_session(led["snapshot"], cal)[1] == "next-day":
            continue
        if a.get("snapshot") and md.snapshot_session(a["snapshot"], cal)[1] == "next-day":
            continue
        drifted = sr.drift(a["live"], market.raw, prev, d)
        if drifted is None:
            continue
        dw = {t: led["live"].get(t, 0.0) - drifted.get(t, 0.0) for t in set(drifted) | set(led["live"])}
        turn = 0.5 * sum(abs(x) for x in dw.values())
        if turn <= md.PATH_TOL:
            continue
        gain, plc, ok = {x: 0.0 for x in times}, {x: 0.0 for x in times}, True
        for t, w in dw.items():
            if abs(w) < 1e-4:
                continue
            p0, q0 = px(t, d, base), px(t, prev, base)
            ps, qs = {x: px(t, d, x) for x in times}, {x: px(t, prev, x) for x in times}
            if not p0 or not q0 or not all(ps.values()) or not all(qs.values()):
                ok = False
                break
            for x in times:
                gain[x] -= w * (ps[x] / p0 - 1)
                plc[x] -= w * (qs[x] / q0 - 1)
        if not ok:
            continue
        rows.append({"date": d, "engine": e, "turnover": round(turn, 4), "status": led.get("status"),
                     "gain_bps": {x: round(v * 1e4, 2) for x, v in gain.items()},
                     "placebo_bps": {x: round(v * 1e4, 2) for x, v in plc.items()},
                     "bought": sorted(t for t, x in dw.items() if x > 0.03), "sold": sorted(t for t, x in dw.items() if x < -0.03)})
    summary = {}
    for x in times:
        g, p = [r["gain_bps"][x] for r in rows], [r["placebo_bps"][x] for r in rows]
        by_day = {}
        for r in rows:
            by_day.setdefault(r["date"], []).append(r["gain_bps"][x])
        top = sorted(g, key=abs)[:-3] if len(g) > 3 else g
        summary[x] = dict(stats(g), placebo=stats(p), sum_bps=round(sum(g), 1), without_top3=stats(top),
                          by_day_mean=stats([sum(v) / len(v) for v in by_day.values()]),     # engines on one day are not independent
                          per_traded_bps=stats([r["gain_bps"][x] / (2 * r["turnover"]) for r in rows]),
                          by_engine={e: stats([r["gain_bps"][x] for r in rows if r["engine"] == e]) for e in ENGINES})
    return {"base": base, "times": list(times), "rows": rows, "summary": summary,
            "basis": "Composer's rotation engine-days; bar closes (no spread); the gain of filling at each minute instead of at "
                     f"{base}, in bps of the sleeve; per_traded_bps divides by the notional traded (both legs)"}


def knife_carry(par):
    """the session after a knife-edge: the mirror (close logic) minus Composer (its ~15:54 logic), per engine"""
    out = {}
    for e, blk in par["engines"].items():
        diffs = {s["date"]: s["diff_bps"] for s in blk["series"] if s["n"] == 1}
        days = sorted({s["date"] for s in blk["series"]} | {x["date"] for x in par["disagreements"]})
        xs = []
        for x in par["disagreements"]:
            if x["engine"] != e or x["class"] != "knife-edge":
                continue
            nxt = [d for d in days if d > x["date"]]
            if nxt and nxt[0] in diffs:
                xs.append({"date": x["date"], "next": nxt[0], "diff_bps": diffs[nxt[0]]})
        out[e] = dict(stats([x["diff_bps"] for x in xs]), days=xs)
    allx = [x["diff_bps"] for e in out for x in out[e]["days"]]
    out["all"] = stats(allx)
    return out


def kmlm_path(rows, shadow):
    out = []
    for r in rows:
        if r["engine"] != "KMLM":
            continue
        led = shadow.get((r["date"], "KMLM")) or {}
        live = led.get("live") or {}
        leg = lambda w: round(sum(x for t, x in w.items() if t not in VIX_SLEEVE), 4)   # noqa: E731
        top = lambda w: max((t for t in w if t not in VIX_SLEEVE), key=lambda t: w[t], default=None)   # noqa: E731
        out.append({"date": r["date"], "mirror_leg": leg(r["weights"]) if r["weights"] else None, "mirror_top": top(r["weights"]),
                    "composer_leg": leg(live) if live else None, "composer_top": top(live), "action": r["action"],
                    "gap": r.get("gap"), "status": led.get("status"),
                    "dist": round(sr.distance(r["weights"], live)[0], 4) if live else None,
                    "mirror": r["weights"], "composer": live or None})
    return out


class YahooAsFetched(md.Yahoo):
    """Yahoo's history as it is today, never truncated or rebased: what mirror_brain.build reads when it
    fetches for itself (it then scales the minute price by the day's own adjusted/raw factor)"""

    def __init__(self, inner):
        super().__init__()
        self.res, self.parsed, self.acts = inner.res, inner.parsed, inner.acts
        self.cache_dir, self._fetch, self._actions = inner.cache_dir, inner._fetch, inner._actions

    def live(self, t, asof=None):
        return super().live(t, asof=None)


def replay_paths(sessions, yahoo, minutes, shadow, market, build, log):
    """The two replay paths on the same bars, every session: the simulator's (Yahoo's history as it
    stood that day: nothing after it, rebased) and the brain's own offline one (the history as fetched
    today, the minute price scaled onto it by the day's factor, preclose.merge_quotes). Engine-sessions
    whose targets differ by more than 3%; and each path's targets against Composer's holdings on the
    engine-sessions Composer rebalanced: "same" by the shadow runner's own rule (shadow_runner.agrees:
    a threshold engine may also hold its drifted holdings, each within 1.5%), "same_or_within_3pct"
    also counting a target within 3% half-L1 (the brain's own figure for its replay: 292 of 296)."""
    plain = YahooAsFetched(yahoo)
    cfg_all = sr.load_manifest()
    changed, n, vs = [], 0, {"as_of": [0, 0, 0], "as_fetched": [0, 0, 0]}
    worst_px = (0.0, None, None)
    for d in sessions:
        hh = md.decide_at(d)
        a = md.brain_payload(d, hh, yahoo, minutes, build)
        b = md.brain_payload(d, hh, plain, minutes)
        for t, p in (a.get("prices") or {}).items():
            q = (b.get("prices") or {}).get(t)
            if q and abs(q / p - 1) > worst_px[0]:
                worst_px = (abs(q / p - 1), t, d)
        for e in ENGINES:
            ta, tb = (a["engines"].get(e) or {}).get("target"), (b["engines"].get(e) or {}).get("target")
            n += 1
            if (ta is None) != (tb is None) or (ta and sr.distance(ta, tb)[0] > md.TOL):
                changed.append({"date": d, "engine": e, "as_of": ta, "as_fetched_today": tb})
            led = shadow.get((d, e)) or {}
            if led.get("live") and led.get("status") != "no-rebalance":
                cor, prev = (cfg_all.get(e) or {}).get("corridor"), market.prev(d)
                was = shadow.get((prev, e)) if prev else None
                drifted = sr.drift(was["live"], market.raw, prev, d) if cor and was and was.get("live") and \
                    was.get("live_asof", prev) == prev else None
                for key, tgt in (("as_of", ta), ("as_fetched", tb)):
                    ok = bool(tgt) and bool(sr.agrees(tgt, led["live"], cor, drifted))
                    vs[key][1] += 1
                    vs[key][0] += ok
                    vs[key][2] += ok or (bool(tgt) and sr.distance(tgt, led["live"])[0] <= md.TOL)
        log(f"replay paths {d}: {len(changed)} differ so far")
    return {"sessions": len(sessions), "engine_sessions": n, "differ": changed,
            "largest_price_difference": {"rel": round(worst_px[0], 8), "ticker": worst_px[1], "date": worst_px[2]},
            "targets_vs_composer_holdings": {k: {"same": v[0], "same_or_within_3pct": v[2], "of": v[1]} for k, v in vs.items()}}


def brain_cross_check(days, yahoo, minutes, build, cache, log):
    """`mirror_brain.py --at "D 15:54"` (the brain's own pinned replay: its live fetch of Yahoo and FMP)
    against the simulator's payload for the same instant (cached bars, as-of history): targets, prices,
    dividends, splits. The CLI's answer is kept under <cache>/brain_at/ so a rerun reads it back."""
    out = []
    for d in days:
        hh = md.decide_at(d)
        path = os.path.join(cache, "brain_at", f"{d}.json")
        rec = {"date": d, "at": f"{d} {hh}"}
        try:
            if not os.path.isfile(path):
                log(f"cross-check {d}: running mirror_brain.py --at")
                r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "mirror_brain.py"), "--at", f"{d} {hh}"],
                                   capture_output=True, text=True, timeout=300)
                json.loads(r.stdout)
                md._write_atomic(path, r.stdout)
            with open(path) as f:
                theirs = json.load(f)
        except Exception as e:  # noqa: BLE001
            key = os.environ.get("FMP_API_KEY") or "\x00"
            out.append(dict(rec, error=" ".join(str(e).replace(key, "***").split())[:160]))
            continue
        mine = md.brain_payload(d, hh, yahoo, minutes, build)
        engines, same = {}, 0
        for e in ENGINES:
            a, b = mine["engines"].get(e) or {}, theirs["engines"].get(e) or {}
            ok = a.get("status") == b.get("status") and (a.get("target") or {}).keys() == (b.get("target") or {}).keys() and \
                (not a.get("target") or sr.distance(a["target"], b["target"])[0] < 1e-9)
            same += ok
            engines[e] = {"same": ok, "simulator": a.get("target") or a.get("note"), "brain": b.get("target") or b.get("note"),
                          "label": [a.get("label"), b.get("label")]}
        both = sorted(set(mine["prices"]) & set(theirs["prices"]))
        diffs = sorted(((abs(theirs["prices"][t] / mine["prices"][t] - 1), t) for t in both), reverse=True)
        rk = lambda x: (x["ticker"], x.get("ex_date") or x.get("date"), x.get("pay_date"), x.get("amount") or x.get("ratio"))   # noqa: E731
        out.append(dict(rec, pinned=theirs.get("pinned"), decision_bar=theirs.get("decision_bar"), engines=engines,
                        engines_same=same, prices={"both": len(both), "simulator": len(mine["prices"]), "brain": len(theirs["prices"]),
                                                   "identical": sum(1 for x, _ in diffs if x < 1e-9),
                                                   "largest_rel_diff": round(diffs[0][0], 8) if diffs else None,
                                                   "largest_on": diffs[0][1] if diffs else None},
                        dividends={"simulator": len(mine["dividends"]), "brain": len(theirs["dividends"]),
                                   "same": sorted(map(rk, mine["dividends"]), key=str) == sorted(map(rk, theirs["dividends"]), key=str)},
                        splits={"simulator": len(mine["splits"]), "brain": len(theirs["splits"]),
                                "same": sorted(map(rk, mine["splits"]), key=str) == sorted(map(rk, theirs["splits"]), key=str)}))
    return out


def slim_rows(res):
    keys = ("date", "engine", "action", "reason", "gap", "weights", "cash_share", "equity", "index", "index_px", "ret", "ret_px",
            "div", "div_leaked", "div_accrued", "commission", "slippage", "traded", "crossed", "unfilled", "label", "decide")
    bkeys = ("date", "equity", "ret", "ret_px", "index", "index_px", "div", "div_leaked", "div_accrued", "unallocated", "commission",
             "slippage", "traded", "crossed", "orders", "crosses", "buys", "buys_unfilled", "cash", "fill_fallbacks", "overspent")
    return ([{k: r.get(k) for k in keys} for r in res["rows"]], [{k: b.get(k) for k in bkeys} for b in res["book"]])


def detail(res):
    par = res["parity"]
    rows, book_rows = slim_rows(res)
    return {"decide": (res.get("minute") or {}).get("decide"), "fill": (res.get("minute") or {}).get("fill"), "mode": res["mode"],
            "rule": res["rule"], "limit_at": res["limit_at"], "info": res.get("minute"), "headline": headline(res),
            "decisions": par["decisions"], "disagreements": par["disagreements"], "episodes": par["episodes"],
            "engines": par["engines"], "book": par["book"], "rows": rows, "book_rows": book_rows,
            "unfilled": res["unfilled"], "receivables": res["receivables"], "unallocated": res["unallocated"],
            "splits_applied": res["splits_applied"]}


def study(start, end, cache, log, cross_check=()):
    import mirror_brain as mb
    yahoo = md.Yahoo(cache)
    market = md.Market(yahoo=yahoo)
    minutes = md.Minutes(cache_dir=cache)
    shadow = md.read_shadow()
    end = end or max(d for d, _ in shadow)
    cfg_all = sr.load_manifest()
    snaps = md.load_snapshots(history=True)
    composer = md.composer_record(snaps, market.calendar(), cfg_all)
    memo = {}

    def build(now, quotes=None, fetch=None, pinned=False):
        key = (now.isoformat(), pinned)
        if key not in memo:
            memo[key] = mb.build(now, quotes=quotes, fetch=fetch, pinned=pinned)
        return memo[key]
    common = dict(shadow=shadow, market=market, yahoo=yahoo, composer=composer, cache=cache)
    minute = dict(common, minute_start=start, minutes=minutes, build=build)
    cfg = md.mc.Config()
    out = {"schema": 2, "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "capital": md.CAPITAL, "fractions": md.FRACTIONS, "slip_bps": md.SLIP_BPS,
           "commission": {"per_share": md.COMM_PER_SHARE, "min": md.COMM_MIN, "cap_share_of_value": md.COMM_CAP},
           "core": {"buy_cushion": cfg.buy_cushion, "cash_reserve_frac": cfg.cash_reserve_frac, "min_trade_frac": cfg.min_trade_frac,
                    "min_trade_usd": cfg.min_trade_usd, "max_idle_cash_frac": md.mc.MAX_IDLE_CASH_FRAC,
                    "dividend_rule": md.DIVIDEND_RULE, "decide": md.DECIDE, "decision_minute": sr.DECISION_MINUTE},
           "composer_book_2026_11_09_usd_k": POLICY_BOOK, "composer_fills": composer_fills(), "primary": PRIMARY}
    # ---- the primary run and its timing variants (whole window, minute mode), each under both limit rules
    runs, first, filled = {}, None, {}
    brief = lambda xs: [{k: x[k] for k in ("date", "engine", "class", "dist")} for x in xs]   # noqa: E731
    for lab, decide, fill in RUNS:
        rf = md.backfill(start, end, "minute", decide=decide, fill=fill, limit_at="fill", **minute)
        # a fill at the close has no fixed limit worth testing (it would be set 6 to 15 minutes early): re-quoted only
        r = rf if fill == "close" else md.backfill(start, end, "minute", decide=decide, fill=fill, **minute)
        log(md._summary(r))
        if r["minute"]["stopped"]:
            raise SystemExit(f"minute mode stopped: {r['minute']['stopped']}")
        if first is None:
            first = r
            out["primary_run"] = detail(r)
        filled[lab] = headline(rf)
        runs[lab] = {"decide": decide, "fill": fill, "mode": "minute", "limit_at": r["limit_at"], "headline": headline(r),
                     "every_buy_fills": filled[lab],
                     "info": {k: r["minute"][k] for k in ("covered", "fallbacks", "fallback_tickers", "orders", "unavailable",
                                                         "unpriced_skips", "labels", "events_from_the_brain")},
                     "events_the_brain_lacked": len(r["minute"]["events_the_brain_lacked"]),
                     "unfilled": r["unfilled"], "disagreements": brief(r["parity"]["disagreements"])}
    close = md.backfill(start, end, "close", **common)
    log(md._summary(close))
    runs["close"] = {"decide": "close", "fill": "close", "mode": "close", "limit_at": "ref", "headline": headline(close),
                     "every_buy_fills": headline(close), "unfilled": close["unfilled"],
                     "disagreements": brief(close["parity"]["disagreements"])}
    out["runs"] = runs
    out["run_order"] = [PRIMARY, "close", "15:55", "15:50", "15:45", "15:45 -> close", "15:54 -> close"]
    out["window"] = {"start": start, "end": first["end"], "sessions": len(first["sessions"]),
                     "ledger_engine_days": len([1 for (d, e) in shadow if start <= d <= end]),
                     "ledger_gaps": close["skipped_sessions"], "no_rebalance": list(md.NO_REBALANCE),
                     "ledger_status": {}, "annual_factor": md.ANNUAL / len(first["sessions"])}
    for (d, e), row in shadow.items():
        if start <= d <= end:
            out["window"]["ledger_status"][row.get("status")] = out["window"]["ledger_status"].get(row.get("status"), 0) + 1
    out["window"]["composer_snapshots"] = {e: sum(1 for d, v in by.items() if start <= d <= end and v.get("dav"))
                                           for e, by in composer.items()}
    out["kmlm_path"] = kmlm_path(first["rows"], shadow)
    out["composer_record"] = {e: [{"date": d, "dav": v["dav"], "value": v["value"], "kind": v["kind"]} for d, v in sorted(by.items())
                                  if start <= d <= end] for e, by in composer.items()}
    # ---- sensitivities, all on the primary run
    base = headline(first)
    gap = lambda h: h["book"]["cum_gap"]   # noqa: E731
    sens = {}
    holder = md.backfill(start, end, "minute", rule="holder", **minute)
    sens["dividend_rule"] = {"composer": {"headline": base, "engines": {e: first["parity"]["engines"][e]["distributions"] for e in ENGINES}},
                             "holder": {"headline": headline(holder), "unallocated": holder["unallocated"],
                                        "engines": {e: {k: v for k, v in holder["parity"]["engines"][e]["distributions"].items()
                                                        if k != "events"} for e in ENGINES}},
                             "holder_minus_composer_bps": round((gap(headline(holder)) - gap(base)) * 1e4, 1)}
    requote = md.backfill(start, end, "minute", limit_at="fill", **minute)
    nolimit = md.backfill(start, end, "minute", limit_buys=False, **minute)
    sens["buy_limit"] = {"at_the_reference": base, "requoted_at_the_fill": headline(requote), "no_limit": headline(nolimit),
                         "unfilled_cost_bps": round((gap(base) - gap(headline(nolimit))) * 1e4, 1),
                         "vs_requoted_bps": round((gap(base) - gap(headline(requote))) * 1e4, 1),
                         "no_limit_overspent": nolimit["parity"]["book"]["overspent"]}
    sens["slip_bps"] = {str(int(s)): (base if s == md.SLIP_BPS else headline(md.backfill(start, end, "minute", slip_bps=s, **minute)))
                        for s in (0.0, 2.0, 5.0)}
    sens["ledger_gaps_filled_from_the_tree"] = headline(md.backfill(start, end, "close", fill_gaps=True, **common))
    first4 = min(d for d in market.sessions(start, end) if all((composer.get(e) or {}).get(d, {}).get("value") for e in ENGINES)
                 and all((d, e) in shadow for e in ENGINES))
    vals = {e: composer[e][first4]["value"] for e in ENGINES}
    fr = {e: vals[e] / sum(vals.values()) for e in ENGINES}
    own = composer_own_book(composer, market.calendar(), first4)
    seed = {"from": first4, "composer_weights": {e: round(x, 4) for e, x in fr.items()}, "runs": {}}
    for lab, fractions in (("policy 29/29/27/15", dict(md.FRACTIONS)), ("Composer's weights that day", fr)):
        r = md.backfill(first4, end, "minute", fractions=fractions, **dict(minute, minute_start=first4))
        idx = {r["book"][0]["date"]: 1.0}
        for b in r["book"][1:]:
            idx[b["date"]] = idx[max(idx)] * (1 + b["ret"])
        spans = [s for s in own if s["d0"] in idx and s["d1"] in idx]
        t, tx = md.tracking(idx, spans), md.tracking(idx, spans, exclude=md.NO_REBALANCE)
        seed["runs"][lab] = {"vs_composer_own_book": {k: v for k, v in t.items() if k not in ("series", "worst")},
                             "vs_composer_own_book_ex_no_rebalance": {k: v for k, v in tx.items() if k not in ("series", "worst")},
                             "like_for_like": headline(r)["book"]}
    seed["composer_weights_end"] = own[-1]["weights"] if own else None
    sens["seed"] = seed
    out["sensitivity"] = sens
    log("sensitivities done")
    # ---- what running on IBKR costs (the exhibit's third panel), all from the primary run
    b = first["parity"]["book"]
    late = [u for u in first["unfilled"] if u.get("later")]
    out["costs"] = {"commission_bps_yr": b["costs"]["commission_bps_yr"], "slippage_bps_yr": b["costs"]["slippage_bps_yr"],
                    "commission_usd": b["costs"]["commission"], "slippage_usd": b["costs"]["slippage"],
                    "turnover_x_yr": b["costs"]["turnover_venue_x_yr"], "orders": b["costs"]["orders"],
                    "orders_per_session": b["costs"]["orders_per_session"], "avg_equity": b["avg_equity"],
                    "unfilled": dict(b["limit_buys"], cost_bps=sens["buy_limit"]["unfilled_cost_bps"],
                                     cost_bps_yr=round(sens["buy_limit"]["unfilled_cost_bps"] * out["window"]["annual_factor"], 1),
                                     would_have_filled_by_the_cancel=len(late),
                                     by_decision_minute={lab: {"buy_orders": runs[lab]["headline"]["limit_buys"]["buy_orders"],
                                                               "unfilled_orders": len(runs[lab]["unfilled"]),
                                                               "sessions": len({u["date"] for u in runs[lab]["unfilled"]}),
                                                               "usd": round(sum(u["usd"] for u in runs[lab]["unfilled"])),
                                                               "largest_usd": round(max((u["usd"] for u in runs[lab]["unfilled"]), default=0)),
                                                               "back_under_the_limit_by_the_cancel": sum(1 for u in runs[lab]["unfilled"]
                                                                                                         if u.get("later")),
                                                               "worst_day_bps": (runs[lab]["headline"]["book_worst"] or [{}])[0].get("diff_bps"),
                                                               "sd_bps": runs[lab]["headline"]["book"]["sd_bps"],
                                                               "sd_bps_every_buy_fills": runs[lab]["every_buy_fills"]["book"]["sd_bps"]}
                                                         for lab, dec, fill in RUNS if fill == "next"}),
                    "cash": b["cash"],
                    "distributions": dict(b["distributions"], holder_minus_composer_bps=sens["dividend_rule"]["holder_minus_composer_bps"],
                                          observed_in_symphony_usd=round(sum(first["parity"]["engines"][e]["distributions"][
                                              "observed_in_symphony_usd"] for e in ENGINES), 2),
                                          observed_account_cash_usd=round(sum(first["parity"]["engines"][e]["distributions"][
                                              "observed_account_cash_usd"] for e in ENGINES), 2),
                                          observed_ambiguous_usd=round(sum(first["parity"]["engines"][e]["distributions"][
                                              "observed_ambiguous_usd"] for e in ENGINES), 2))}
    # ---- edge checks
    edge = {}
    try:
        edge["fill_minute"] = fill_profile({k: v for k, v in shadow.items() if start <= k[0] <= end}, market, minutes)
    except md.Refused as e:
        edge["fill_minute"] = {"error": f"FMP refused: {e}"}
    later = {}
    for f in LATER:                                    # the SAME 15:54 decisions, every buy filled, only the fill bar moves
        h = filled[PRIMARY] if f == "+1" else filled["15:54 -> close"] if f == "close" else \
            headline(md.backfill(start, end, "minute", fill=f, limit_at="fill", **minute))
        later[f] = {"fill_et": "close" if f == "close" else sr._hm(sr._min(md.DECIDE) + int(f)), "cum_gap": gap(h),
                    "cum_gap_ex": h["book_ex"]["cum_gap"], "gross_ex": h["book_gross_ex"]["cum_gap"], "mean_bps": h["book"]["mean_bps"],
                    "sd_bps": h["book"]["sd_bps"], "t": h["book"]["t"], "agree": h["decisions"]["ALL"]["agree"],
                    "vs_first_bps": round((gap(h) - gap(filled[PRIMARY])) * 1e4, 1)}
    edge["later_fill_same_decisions"] = {"rows": later, "note": "the 15:54:00 decisions, every buy filled (limit re-quoted at the fill), "
                                         "sells and buys filled at the bar ending at fill_et; vs_first_bps: the cumulative gap against "
                                         "the bar ending 15:55, bps of the book over the window"}
    edge["fill_at_the_close_vs_a_minute_later"] = {
        "same_decisions_15_54": round((gap(filled["15:54 -> close"]) - gap(filled[PRIMARY])) * 1e4, 1),
        "same_decisions_15_45": round((gap(filled["15:45 -> close"]) - gap(filled["15:45"])) * 1e4, 1),
        "note": "cumulative gap, fills at the official close minus fills a minute after the decision, every buy filled, bps of the "
                "book over the window"}
    edge["knife_edge_carry"] = knife_carry(close["parity"])
    out["edge"] = edge
    # ---- cross-checks of the replay itself
    out["replay_paths"] = replay_paths(first["sessions"], yahoo, minutes, shadow, market, build, log)
    out["brain_cross_check"] = brain_cross_check(list(cross_check), yahoo, minutes, build, cache, log) if cross_check else []
    out["fmp"] = {"requests_this_run": minutes.requests, "errors": len(minutes.errors), "refused": minutes.refused}
    out["splits_in_window"] = {t: [x for x in ev.get("splits") or [] if start <= x["date"] <= end] for t, ev in market.events.items()
                               if any(start <= x["date"] <= end for x in ev.get("splits") or [])}
    out["events"] = {"tickers": len(market.events), "fmp_lists_read": sum(1 for ev in market.events.values() if ev.get("fmp")),
                     "dividends_in_window": sum(1 for ev in market.events.values() for x in ev.get("dividends") or []
                                                if start <= x["ex_date"] <= end),
                     "fmp_only": sorted((t, x["ex_date"]) for t, ev in market.events.items() for x in ev.get("dividends") or []
                                        if start <= x["ex_date"] <= end and x.get("src") == "fmp"),
                     "without_pay_date": sum(1 for ev in market.events.values() for x in ev.get("dividends") or []
                                             if start <= x["ex_date"] <= end and not x.get("pay_date"))}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True, help="directory for Yahoo and FMP responses")
    ap.add_argument("--start", default=md.START)
    ap.add_argument("--end")
    ap.add_argument("--cross-check", default="", help="sessions to check against mirror_brain.py --at, comma-separated")
    ap.add_argument("--out")
    a = ap.parse_args()
    days = [d for d in a.cross_check.split(",") if d]
    res = study(a.start, a.end, a.cache, lambda m: print(m, file=sys.stderr, flush=True), days)
    out = a.out or os.path.join(OUT, f"backfill-{datetime.date.today().isoformat()}.json")
    md._write_atomic(out, json.dumps(res, separators=(",", ":")))
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
