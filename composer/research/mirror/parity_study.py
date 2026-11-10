#!/usr/bin/env python3
"""Parity study for the IBKR mirror of the Composer book (composer/IBKR_MIRROR.md): the DRY simulator
(scripts/mirror_dry.py, which drives ibkr-executor/app/mirror_core.py unchanged) run over the shadow
ledger's history and measured against Composer's realised record.

  close mode   2026-07-15..the ledger's last session, decision = the ledger's target, fills at the close
  minute mode  from --minute-start: mirror_brain.build() at 15:45 / 15:50 / 15:55 ET, fills a minute
               later (and, for the design in IBKR_MIRROR.md, a 15:45 decision filled at the close)
  sensitivity  slippage 0 / 2 / 5 bps; the seed at Composer's own engine weights; ledger gaps filled
  edge checks  the fill-timing difference (close vs ~15:54) with a placebo; knife-edge carry; the
               replay's as-of history

Writes results/mirror/backfill-<date>.json (read by make_mirror_chart.py). Read-only: Yahoo, FMP
(key FMP_API_KEY, never printed), the shadow ledger, the monitor snapshots (git history, read-only).

Usage: parity_study.py --cache DIR [--start D] [--end D] [--minute-start D] [--minute-full] [--out FILE]
"""
import argparse
import datetime
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import mirror_dry as md  # noqa: E402
import shadow_runner as sr  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "results", "mirror")
ENGINES = ("HG", "KMLM", "SLEEVE", "HARV")
VIX_SLEEVE = {"PULS", "ZVOL", "VXZ"}              # KMLM's 25% part; everything else is the switcher's 75% leg
POLICY_BOOK = {"HG": 104.8, "KMLM": 81.8, "SLEEVE": 81.8, "HARV": 38.3}   # Composer's book 2026-11-09, $k


def stats(xs):
    n = len(xs)
    if not n:
        return {"n": 0, "mean": None, "sd": None, "t": None}
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "mean": round(m, 3), "sd": round(sd, 3), "t": round(m / (sd / math.sqrt(n)), 2) if sd > 0 else None}


def slim(par):
    """a parity block without its day-by-day series (for the variants and sensitivities)"""
    return {"decisions": par["decisions"],
            "engines": {e: {k: v for k, v in blk.items() if k not in ("series",)} for e, blk in par["engines"].items()},
            "book": {k: v for k, v in par["book"].items() if k != "series"}, "episodes": par.get("episodes")}


def headline(res):
    """one row per run for the comparison tables"""
    p = res["parity"]
    row = {"decisions": {e: {"agree": v["agree"], "n": v["n"], "share": v["share"]} for e, v in p["decisions"].items()},
           "book": {k: p["book"]["tracking"].get(k) for k in ("n_daily", "mean_bps", "sd_bps", "t", "corr", "beta", "cum_mirror",
                                                             "cum_composer", "cum_gap", "mean_abs_bps")},
           "book_ex": {k: p["book"]["tracking_ex_no_rebalance"].get(k) for k in ("n_daily", "mean_bps", "sd_bps", "cum_mirror",
                                                                                "cum_composer", "cum_gap")},
           "costs": p["book"]["costs"], "engines": {}}
    for e, blk in p["engines"].items():
        t = blk["tracking"]
        row["engines"][e] = {k: t.get(k) for k in ("n_daily", "mean_bps", "sd_bps", "t", "corr", "beta", "cum_mirror", "cum_composer",
                                                   "cum_gap")}
        row["engines"][e]["gross_cum_gap"] = blk["tracking_gross"].get("cum_gap")
        row["engines"][e]["gross_mean_bps"] = blk["tracking_gross"].get("mean_bps")
    return row


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


def fill_timing(shadow, market, minutes, hhmm="15:55", stale=30):
    """Composer fills near 15:54; a market-on-close order fills at the close. On every engine-day Composer
    rotated (holdings moved more than 1.5% off yesterday's, drifted), the close-fill's advantage is
    -(sum over tickers of the weight traded x the ticker's move from the 15:54 bar's close to the
    official close): positive when what Composer bought fell into the close (or what it sold rose).
    Placebo: the same weights on the PREVIOUS session's last minutes, when that rotation did not happen."""
    cal = market.calendar()
    rows = []

    def tail(t, d):
        bars = minutes.get(t, d)
        end = sr._min(sr.session_close(d)) - (sr._min("16:00") - sr._min(hhmm)) - 1
        ks = [k for k in bars if end - stale <= sr._min(k) <= end]
        c = market.raw.get(t, {}).get(d)
        return (c / bars[max(ks, key=sr._min)] - 1) if ks and c else None

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
        adv = plc = 0.0
        missing = []
        for t, x in dw.items():
            if abs(x) < 1e-4:
                continue
            r, r0 = tail(t, d), tail(t, prev)
            if r is None or r0 is None:
                missing.append(t)
                continue
            adv -= x * r
            plc -= x * r0
        spy = market.raw["SPY"][d] / market.raw["SPY"][prev] - 1
        rows.append({"date": d, "engine": e, "turnover": round(turn, 4), "adv_bps": round(adv * 1e4, 2),
                     "placebo_bps": round(plc * 1e4, 2), "spy_day": round(spy, 5), "status": led.get("status"),
                     "unpriced": missing, "bought": sorted(t for t, x in dw.items() if x > 0.03),
                     "sold": sorted(t for t, x in dw.items() if x < -0.03)})
    return rows


def timing_summary(rows, diffs=None):
    out = {"all": dict(stats([r["adv_bps"] for r in rows]), placebo=stats([r["placebo_bps"] for r in rows]),
                       sum_bps=round(sum(r["adv_bps"] for r in rows), 1))}
    for e in ENGINES:
        xs = [r for r in rows if r["engine"] == e]
        out[e] = dict(stats([r["adv_bps"] for r in xs]), placebo=stats([r["placebo_bps"] for r in xs]),
                      sum_bps=round(sum(r["adv_bps"] for r in xs), 1))
    for lab, pick in (("spy_down_day", lambda r: r["spy_day"] < 0), ("spy_up_day", lambda r: r["spy_day"] >= 0),
                      ("spy_move_over_1pct", lambda r: abs(r["spy_day"]) >= 0.01), ("spy_move_under_1pct", lambda r: abs(r["spy_day"]) < 0.01)):
        xs = [r for r in rows if pick(r)]
        out[lab] = dict(stats([r["adv_bps"] for r in xs]), placebo=stats([r["placebo_bps"] for r in xs]))
    top = sorted(rows, key=lambda r: -abs(r["adv_bps"]))[:3]
    rest = [r["adv_bps"] for r in rows if r not in top]
    out["without_top3"] = dict(stats(rest), dropped=[(r["date"], r["engine"], r["adv_bps"]) for r in top])
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r["adv_bps"])
    out["by_day_mean"] = stats([sum(v) / len(v) for v in by_day.values()])     # engines on one day are not independent
    if diffs:
        pairs = [(r["adv_bps"], diffs[(r["date"], r["engine"])]) for r in rows if (r["date"], r["engine"]) in diffs]
        if len(pairs) > 3:
            xa, xb = [p[0] for p in pairs], [p[1] for p in pairs]
            ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
            va, vb = sum((x - ma) ** 2 for x in xa), sum((x - mb) ** 2 for x in xb)
            cov = sum((x - ma) * (y - mb) for x, y in pairs)
            out["vs_realised"] = {"n": len(pairs), "corr": round(cov / math.sqrt(va * vb), 3) if va and vb else None,
                                  "realised_mean_bps": round(mb, 2), "timing_mean_bps": round(ma, 2),
                                  "residual": stats([y - x for x, y in pairs])}
    return out


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


def asof_check(sessions, yahoo, minutes, log):
    """how many replayed decisions change when the history is NOT rebased to the replayed day (what
    mirror_brain.build does when it fetches for itself): engine-days whose target moves by more than 3%"""
    import mirror_brain as mb
    changed, n = [], 0
    for d in sessions:
        hh = md.decide_at(d)
        a = md.brain_payload(d, hh, yahoo, minutes)
        b = mb.build(mb.parse_at(f"{d} {hh}"), quotes=minutes.quotes(), fetch=lambda t: yahoo.live(t, asof=None))
        for e in ENGINES:
            ta, tb = (a["engines"].get(e) or {}).get("target"), (b["engines"].get(e) or {}).get("target")
            n += 1
            if (ta is None) != (tb is None) or (ta and sr.distance(ta, tb)[0] > md.TOL):
                changed.append({"date": d, "engine": e, "as_of": ta, "as_fetched_today": tb})
        log(f"as-of check {d}: {len(changed)} changed so far")
    return {"engine_days": n, "changed": changed}


def study(start, end, minute_start, cache, log, minute_full=False):
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

    def build(now, quotes=None, fetch=None):
        key = now.isoformat()
        if key not in memo:
            memo[key] = mb.build(now, quotes=quotes, fetch=fetch)
        return memo[key]
    common = dict(shadow=shadow, market=market, yahoo=yahoo, composer=composer, cache=cache)
    # ---- close mode, the primary run
    close = md.backfill(start, end, "close", **common)
    log(md._summary(close))
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "window": {"start": start, "end": close["end"], "sessions": len(close["sessions"]),
                      "ledger_engine_days": len([1 for (d, e) in shadow if start <= d <= end]),
                      "ledger_gaps": close["skipped_sessions"]},
           "capital": md.CAPITAL, "fractions": md.FRACTIONS, "slip_bps": md.SLIP_BPS,
           "commission": {"per_share": md.COMM_PER_SHARE, "min": md.COMM_MIN, "cap_share_of_value": md.COMM_CAP},
           "composer_book_2026_11_09_usd_k": POLICY_BOOK}
    par = close["parity"]
    out["close"] = {"decisions": par["decisions"], "disagreements": par["disagreements"], "episodes": par["episodes"],
                    "engines": par["engines"], "book": par["book"], "headline": headline(close),
                    "rows": [{k: r[k] for k in ("date", "engine", "action", "reason", "gap", "weights", "equity", "index_px",
                                                "index_px_gross", "ret", "ret_px", "div", "commission", "slippage", "traded", "crossed")}
                             for r in close["rows"]],
                    "book_rows": [{k: b[k] for k in ("date", "equity", "ret", "ret_px", "index_px", "index_px_gross", "div", "commission",
                                                     "slippage", "traded", "crossed", "orders", "crosses", "cash")} for b in close["book"]]}
    out["kmlm_path"] = kmlm_path(close["rows"], shadow)
    out["composer_record"] = {e: [{"date": d, "dav": v["dav"], "value": v["value"], "kind": v["kind"]} for d, v in sorted(by.items())
                                  if start <= d <= end] for e, by in composer.items()}
    # ---- sensitivities (close mode)
    sens = {"slip_bps": {}}
    for s in (0.0, 2.0, 5.0):
        r = close if s == md.SLIP_BPS else md.backfill(start, end, "close", slip_bps=s, **common)
        sens["slip_bps"][str(int(s))] = headline(r)
    gf = md.backfill(start, end, "close", fill_gaps=True, **common)
    sens["ledger_gaps_filled_from_the_tree"] = headline(gf)
    first4 = min(d for d in market.sessions(start, end) if all((composer.get(e) or {}).get(d, {}).get("value") for e in ENGINES)
                 and all((d, e) in shadow for e in ENGINES))
    vals = {e: composer[e][first4]["value"] for e in ENGINES}
    fr = {e: vals[e] / sum(vals.values()) for e in ENGINES}
    own = composer_own_book(composer, market.calendar(), first4)
    seed = {"from": first4, "composer_weights": {e: round(x, 4) for e, x in fr.items()}, "runs": {}}
    for lab, fractions in (("policy 29/29/27/15", dict(md.FRACTIONS)), ("Composer's weights that day", fr)):
        r = md.backfill(first4, end, "close", fractions=fractions, **common)
        idx = {r["book"][0]["date"]: 1.0}
        for b in r["book"][1:]:
            idx[b["date"]] = idx[max(idx)] * (1 + b["ret_px"])
        t = md.tracking(idx, [s for s in own if s["d0"] in idx and s["d1"] in idx])
        tx = md.tracking(idx, [s for s in own if s["d0"] in idx and s["d1"] in idx], exclude=md.NO_REBALANCE)
        seed["runs"][lab] = {"vs_composer_own_book": {k: v for k, v in t.items() if k not in ("series", "worst")},
                             "vs_composer_own_book_ex_no_rebalance": {k: v for k, v in tx.items() if k not in ("series", "worst")},
                             "like_for_like": headline(r)["book"]}
    seed["composer_weights_end"] = own[-1]["weights"] if own else None
    sens["seed"] = seed
    out["sensitivity"] = sens
    log("sensitivities done")
    # ---- minute mode
    ms = start if minute_full else minute_start
    mins = {"start": ms, "variants": {}}
    full = None
    for lab, decide, fill in (("15:55", "15:55", "next"), ("15:50", "15:50", "next"), ("15:45", "15:45", "next"),
                              ("15:45 -> close (MOC)", "15:45", "close"), ("15:55 -> close", "15:55", "close")):
        r = md.backfill(start, end, "minute", minute_start=ms, decide=decide, fill=fill, minutes=minutes, build=build, **common)
        log(f"minute {lab}: covered {r['minute']['covered']} stopped {r['minute']['stopped']}")
        log(md._summary(r))
        blk = {"decide": decide, "fill": fill, "info": r["minute"], "headline": headline(r),
               "disagreements": r["parity"]["disagreements"], "episodes": r["parity"]["episodes"]}
        if lab == "15:55":
            full = r
            blk.update(engines=r["parity"]["engines"], book=r["parity"]["book"],
                       rows=[{k: x.get(k) for k in ("date", "engine", "mode", "action", "reason", "gap", "weights", "equity", "index_px",
                                                    "ret", "ret_px", "label", "decide")} for x in r["rows"] if x["date"] >= ms],
                       book_rows=[{k: b.get(k) for k in ("date", "equity", "ret", "ret_px", "index_px", "orders", "crosses", "commission",
                                                         "slippage", "fill_fallbacks", "overspent", "cash_low")}
                                  for b in r["book"] if b["date"] >= ms])
        else:
            blk["engines_tracking"] = {e: v for e, v in headline(r)["engines"].items()}
            blk["overspent"] = r["parity"]["book"]["overspent"]
        mins["variants"][lab] = blk
        if r["minute"]["stopped"]:
            break
    same = md.backfill(start, end, "close", parity_from=ms, **common)
    mins["close_same_sessions"] = {"headline": headline(same), "disagreements": same["parity"]["disagreements"]}
    out["minute"] = mins
    out["kmlm_path_minute"] = kmlm_path([x for x in (full or {}).get("rows", []) if x["date"] >= ms], shadow)
    # ---- edge checks
    edge = {}
    try:
        rows = fill_timing({k: v for k, v in shadow.items() if start <= k[0] <= end}, market, minutes)
        diffs = {(s["date"], e): s["diff_bps"] for e, blk in par["engines"].items() for s in blk["series"] if s["n"] == 1}
        gross = {}
        for e in ENGINES:
            xs = {r["date"]: r for r in close["rows"] if r["engine"] == e}
            for (d, ee), v in diffs.items():
                if ee == e and d in xs:
                    gross[(d, e)] = v + (xs[d]["ret_px_gross"] - xs[d]["ret_px"]) * 1e4
        edge["fill_timing"] = {"rows": rows, "summary": timing_summary(rows, gross),
                               "basis": "Composer's rotation engine-days; price at the close of the bar starting 15:54 vs the official close"}
    except md.Refused as e:
        edge["fill_timing"] = {"error": f"FMP refused: {e}"}
    edge["knife_edge_carry"] = knife_carry(par)
    try:
        sess = [d for d in market.sessions(ms, end) if d in (full or {}).get("sessions", [])]
        edge["replay_as_of"] = asof_check(sess, yahoo, minutes, log)
    except md.Refused as e:
        edge["replay_as_of"] = {"error": f"FMP refused: {e}"}
    out["edge"] = edge
    out["fmp"] = {"requests_this_run": minutes.requests, "errors": len(minutes.errors), "refused": minutes.refused}
    out["splits_in_window"] = {t: [s for s in sp if start <= s[0] <= end] for t, sp in market.splits.items()
                               if any(start <= s[0] <= end for s in sp)}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True, help="directory for Yahoo and FMP responses")
    ap.add_argument("--start", default=md.START)
    ap.add_argument("--end")
    ap.add_argument("--minute-start", default=md.MINUTE_START)
    ap.add_argument("--minute-full", action="store_true", help="minute mode over the whole window")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = study(a.start, a.end, a.minute_start, a.cache, lambda m: print(m, file=sys.stderr, flush=True), a.minute_full)
    out = a.out or os.path.join(OUT, f"backfill-{datetime.date.today().isoformat()}.json")
    md._write_atomic(out, json.dumps(res, separators=(",", ":")))
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
