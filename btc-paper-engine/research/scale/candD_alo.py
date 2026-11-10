"""CANDIDATE D: WHY is post-only rejected? -- phase 1's open question.

mirror.py:4486 names the mechanism: the engine prices signals off SPOT, the
venue is a PERP.  This quantifies it against the second candidate cause,
latency, and reports which one dominates.

The limit is `pend["limit"]` = the SIGNAL BAR'S SPOT CLOSE (core.py:370), sent
by hl.place_limit rounded AWAY from the market (down for BUY, up for SELL), so
rounding makes it strictly LESS marketable -- it cannot explain a rejection.

Marketability at placement, with half-spread h and post-placement drift d
(both in bps of price), basis b in bps:
    BUY  at C_s crosses if  C_s >= perp_ask  <=>  b + d <= -h
    SELL at C_s crosses if  C_s <= perp_bid  <=>  b + d >= +h
h is the MEASURED half-spread (book_calm.json: 0.119 bp spread -> h = 0.0595).

Latency: the paper engine polls at POLL_SECONDS=60 (render.yaml) and the
executor at poll_seconds=20 (config.py:76), so the order reaches the venue
0-80 s after the 4h bar close.  Drift is scaled from the MEASURED 1-minute
sigma (twap.py: 4.17 bp) by sqrt(t/60).

Run: python3 research/scale/candD_alo.py
"""
from __future__ import annotations
import csv, dataclasses, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

SPOT = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
BASIS = os.path.join(HERE, "candD_perp_4h.csv")
OUT = os.path.join(HERE, "candD_alo.json")

HALF_SPREAD_BPS = 0.119 / 2.0        # measured, book_calm.json
SIGMA_1MIN_BPS = 4.17               # measured, twap.py
P_BOOKS = [b for b in RESEARCH_BOOKS if b.name == "S3"]


def phi(z):                          # standard normal CDF
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def main() -> None:
    bars = []
    with open(SPOT) as f:
        for r in csv.DictReader(f):
            bars.append(Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                            high=float(r["high"]), low=float(r["low"]),
                            close=float(r["close"]), volume=float(r["volume"])))
    bc = {}
    with open(BASIS) as f:
        for r in csv.DictReader(f):
            bc[int(r["ts"])] = float(r["basis_close_bps"])

    tc = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=4.32)
    res = run_replay(bars, P_BOOKS, RESEARCH_SIGNAL, tc,
                     start_ts=min(bc), cash_apy=0.0)
    trades = res.books["S3"].trades
    # Every pullback ENTRY the executor would have placed, with the basis that
    # applied to the price it placed at.
    ents = [(t.side, bc[t.signal_ts]) for t in trades if t.signal_ts in bc]
    print(f"pullback entries in the basis window: {len(ents)} "
          f"({sum(1 for s,_ in ents if s=='L')} L / "
          f"{sum(1 for s,_ in ents if s=='S')} S)")

    h = HALF_SPREAD_BPS
    # ---- zero-latency, pure basis: MEASURED ----
    cross0 = [1 if ((s == "L" and b <= -h) or (s == "S" and b >= h)) else 0
              for s, b in ents]
    rate0 = sum(cross0) / len(cross0)

    out = {"n_entries": len(ents), "half_spread_bps": h,
           "sigma_1min_bps": SIGMA_1MIN_BPS,
           "measured_basis_only": {
               "cross_rate": rate0,
               "cross_rate_long": (sum(1 for (s, b), c in zip(ents, cross0)
                                       if s == "L" and c) /
                                   max(1, sum(1 for s, _ in ents if s == "L"))),
               "cross_rate_short": (sum(1 for (s, b), c in zip(ents, cross0)
                                        if s == "S" and c) /
                                    max(1, sum(1 for s, _ in ents if s == "S"))),
               "note": "basis alone, no latency drift"},
           "latency_model": {}}
    print(f"\nMEASURED, basis alone (zero latency): cross rate "
          f"{rate0:.1%}  (long {out['measured_basis_only']['cross_rate_long']:.1%}, "
          f"short {out['measured_basis_only']['cross_rate_short']:.1%})")

    # ---- with latency drift: DERIVED (basis measured, drift modelled) ----
    for secs in (0, 20, 40, 60, 80):
        sd = SIGMA_1MIN_BPS * math.sqrt(secs / 60.0) if secs else 0.0
        tot = 0.0
        for s, b in ents:
            if sd == 0.0:
                p = 1.0 if ((s == "L" and b <= -h) or (s == "S" and b >= h)) else 0.0
            elif s == "L":
                p = phi((-h - b) / sd)          # P(b + d <= -h)
            else:
                p = 1.0 - phi((h - b) / sd)     # P(b + d >= +h)
            tot += p
        out["latency_model"][str(secs)] = {
            "drift_sd_bps": sd, "expected_cross_rate": tot / len(ents),
            "p_all_four_cross": (tot / len(ents)) ** 4}
        print(f"  latency {secs:>2}s (drift sd {sd:4.2f} bps): expected cross "
              f"rate {tot/len(ents):.1%}   P(4 of 4 cross) = "
              f"{(tot/len(ents))**4:.3f}")

    # ---- counterfactual: what if the limit were BASIS-TRANSLATED? ----
    # Limit becomes C_s*(1+b) so it sits exactly at the perp's own last price:
    # the basis term vanishes and only latency drift can make it marketable.
    print("\nFIX: basis-translate the limit (limit := C_s * (1 + b_now))")
    out["fix_basis_translated"] = {}
    for secs in (0, 20, 40, 60, 80):
        sd = SIGMA_1MIN_BPS * math.sqrt(secs / 60.0) if secs else 0.0
        # b is removed, so P(cross) = P(d <= -h) or P(d >= h); symmetric
        p = phi(-h / sd) if sd > 0 else 0.0
        out["fix_basis_translated"][str(secs)] = {
            "drift_sd_bps": sd, "expected_cross_rate": p}
        print(f"  latency {secs:>2}s: expected cross rate {p:.1%}")

    # ---- and with a re-price-to-touch retry, bounded ----
    print("\nFIX+: on rejection, re-price to the live touch and re-send Alo")
    out["fix_reprice_retry"] = {}
    for secs in (40, 80):
        sd = SIGMA_1MIN_BPS * math.sqrt(secs / 60.0)
        p1 = phi(-h / sd)
        out["fix_reprice_retry"][str(secs)] = {
            "p_cross_after_1_retry": p1 ** 2, "p_cross_after_2_retries": p1 ** 3,
            "note": "each retry re-prices to the CURRENT touch, so the basis "
                    "term is gone and only fresh drift inside the retry "
                    "round-trip can cross; retries are independent only if "
                    "drift is, which is the optimistic reading"}
        print(f"  latency {secs}s: residual cross after 1 retry "
              f"{p1**2:.2%}, after 2 retries {p1**3:.3%}")

    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
