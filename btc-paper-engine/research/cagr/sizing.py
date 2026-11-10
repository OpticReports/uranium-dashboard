"""Job 2 - the largest size the $100k can carry at a -30% drawdown.

For each construction, sizing multiple k (in baseline units: legs 1.125k
pullback / 0.375k trend; live KELLY_M == k when SIZING_BASE_USD == equity)
by START YEAR, because the audit showed the binding drawdown moves with it:
thin 2013 Bitstamp markets alone set the full-sample answer.

Reports per start year: k_at_dd (realised MTM DD = 30%), k_safe (bootstrap
P(maxDD>30% over 2y) <= 10%), and k_use = min of the two (audit a8: neither
is reliably the conservative one). Then the CAGR, peak concurrent gross and
live settings at k_use. Writes sizing.json.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import candidates as C                                              # noqa: E402
import harness as H                                                 # noqa: E402

STARTS = ["2013-01-01", "2014-01-01", "2015-01-01", "2016-01-01",
          "2017-01-01", "2018-01-01", "2019-01-01", "2020-01-01"]
END = "2026-07-31"
BUILDS = ["baseline", "H5a H1+H2a", "H5b H1+H2b"]
EQUITY = 100_000.0


def main():
    W = C.World()
    out = {}
    for b in BUILDS:
        out[b] = {}
        for s in STARTS:
            t0, t1 = H.ts_of(s), H.ts_of(END) + 86399
            legs, closes = C.CANDIDATES[b](W, t0, t1)
            r1 = H.simulate(legs, closes, k=1.0, start_ts=t0, end_ts=t1)
            path = np.concatenate([[r1.start_equity], r1.equity])
            ks, meta = H.k_safe(np.diff(path) / path[:-1])
            kd = H.k_at_dd(legs, closes, 0.30, start_ts=t0, end_ts=t1)
            ku = min(ks, kd)
            ru = H.simulate(legs, closes, k=ku, start_ts=t0, end_ts=t1)
            st = H.stats(ru)
            peak_gross = float(np.nanmax(ru.gross_lev))
            p99_gross = float(np.nanpercentile(ru.gross_lev, 99))
            out[b][s] = dict(k_safe=ks, k_dd=kd, k_use=ku,
                             cagr=st["cagr"], maxdd=st["maxdd"],
                             sharpe=st["sharpe"], peak_gross_x=peak_gross,
                             p99_gross_x=p99_gross, n=st["n"])
            print(f"{b:12s} from {s[:4]}  k_safe {ks:.3f}  k_dd {kd:.3f}  "
                  f"k_use {ku:.3f}  CAGR {st['cagr']*100:5.1f}%  "
                  f"DD {st['maxdd']*100:6.1f}%  peak gross {peak_gross:.2f}x",
                  flush=True)
    with open(os.path.join(HERE, "sizing.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
