#!/usr/bin/env python3
"""Re-classify the shadow ledger's LIVE rows for given sessions with the current classifier (results.md
addendum 50: FMP 1-minute prices across the decision window), keeping every other field and recording
the change under 'reclassified' ({'on', 'from', 'by'}). Only rows that were a knife-edge or a mismatch
are re-read; agree, no-rebalance and unavailable rows are Composer's record or the data's, left as they
are. KMLM's corridor path uses the previous session's ledger row and the row's own deposit fields,
as the daily check did.

Usage: reclassify_live.py 2026-10-30 [--dry-run]
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import shadow_runner as sr  # noqa: E402


def main():
    days = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    now = datetime.datetime.now(datetime.timezone.utc)
    cfg_all = sr.load_manifest()
    tick = {"SPY"}
    for cfg in cfg_all.values():
        for era in cfg["eras"]:
            tick |= sr.tree_tickers(sr.load_tree(era))
    prices, raw, bad = sr.fetch_prices(tick, now)
    if bad:
        sys.exit(f"Yahoo failures: {bad}")
    minutes, bars = sr.minutes_fetcher(), sr.bars_fetcher()
    if minutes is None:
        sys.exit("FMP_API_KEY not set: the current classifier needs FMP 1-minute bars")
    out = []
    for r in sr.read_ledger(strict=True):
        if r.get("src") != "live" or r["date"] not in days or r.get("status") not in ("knife-edge", "mismatch"):
            continue
        d, eng = r["date"], r["engine"]
        cfg = cfg_all[eng]
        tree = sr.load_tree(sr.era_for(cfg, d))
        sim, target, tr = sr.run_engine(prices, tree, d)
        prev = sr.previous_rows(sr.LEDGER, d, prices).get(eng) or {}
        s = {"net_deposits": r.get("net_deposits"), "has_queued_deploy": r.get("queued"), "value": 1.0,
             "cash": r.get("cash_share") or 0.0}
        base = sr.corridor_base(cfg, prev, s, prices, d)
        st, det = sr.classify(sim, tree, d, target, tr, r["live"], cfg.get("corridor"), base,
                              lambda: sr.intraday_check(prices, raw, tree, d, minutes, bars))
        print(f"{d} {eng}: {r['status']} -> {st} {det.get('edge', {}).get('time', '')} {det.get('edge', {}).get('src', '')}")
        if st == r["status"]:
            continue
        new = {k: v for k, v in r.items() if k not in ("edge", "why", "checked", "path")}
        new.update(status=st, **det)
        new["reclassified"] = {"on": now.date().isoformat(), "from": r["status"],
                               "by": "add. 50: FMP 1-minute prices 15:44-15:56 ET"}
        out.append(new)
    if out and not dry:
        sr.write_ledger(out)
        print(f"ledger rows rewritten: {len(out)}")


if __name__ == "__main__":
    main()
