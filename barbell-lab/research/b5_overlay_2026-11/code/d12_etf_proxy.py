"""D12: rerun the near-pass per-leg rules with ETF proxies (SCZ, EFA before SCZ; EEM) in place of the
stale-priced mutual-fund NAVs DISVX / DFEMX. Writes ../d12_etf_proxy.json."""
import copy, json, os
import numpy as np
import common as C, arms as A, engine as E, run as RUN

p = C.load_panel(); q = copy.copy(p); q["ret"] = p["ret"].copy()
q["ret"]["DISVX"] = np.where(p["ret"]["SCZ"].notna(), p["ret"]["SCZ"], p["ret"]["EFA"])
q["ret"]["DFEMX"] = p["ret"]["EEM"]
out = {}
for name, panel in (("mutual_fund_proxies", p), ("etf_proxies", q)):
    tp = RUN.Tape(panel, "T1"); arms, _ = A.build(panel, tp.t, tp.nav)
    res = {"live": {w: tp.met(tp.base, w) for w in ("EXT", "DISC")}}
    for k in ("A1", "A2", "A6", "A7", "A8", "A10", "A15"):
        e = RUN.eval_arm(tp, arms[k]["mult"], wins=("EXT", "DISC")); e0 = RUN.eval_arm(tp, arms[k]["mult"], lag=0, wins=("EXT", "DISC"))
        a0, a1 = tp.win["EXT"]; offs = np.arange(63, (a1 - a0) - 63, dtype=np.int64)
        pl = E.placebo_shift(tp.R, np.ascontiguousarray(e["W"][a0:a1]), C.BASE.copy(), tp.cost, tp.me, C.BAND, C.CAL_DAYS, 1e-9, True,
                             RUN.NOMASK, 0.0, a0, a1, offs, tp.c)
        res[k] = {w: dict(d=e["win"][w]["d"], arm=e["win"][w]["arm"], ctrl=e["win"][w]["ctrl"], d_lag0=e0["win"][w]["d"]) for w in ("EXT", "DISC")}
        res[k]["placebo_pct_maxdd_EXT"] = float((pl[:, 1] < e["win"]["EXT"]["arm"]["maxdd"]).mean() * 100)
        res[k]["placebo_pct_sharpe_EXT"] = float((pl[:, 0] < e["win"]["EXT"]["arm"]["sharpe"]).mean() * 100)
    out[name] = res
json.dump(out, open(os.path.join(C.STUDY, "d12_etf_proxy.json"), "w"), indent=1)
for k in ("A1", "A2", "A6", "A7", "A8", "A10", "A15"):
    for n in out:
        x = out[n][k]
        print(f"{k:4s} {n:20s} EXT dS {x['EXT']['d']['d_sharpe']:+.3f} dDD {x['EXT']['d']['d_maxdd']*100:+5.1f} dCAGR {x['EXT']['d']['d_cagr']*100:+5.2f} dUlc {x['EXT']['d']['d_ulcer']*100:+5.2f} | DISC dS {x['DISC']['d']['d_sharpe']:+.3f} dDD {x['DISC']['d']['d_maxdd']*100:+5.1f} dUlc {x['DISC']['d']['d_ulcer']*100:+5.2f} | lag0 EXT dS {x['EXT']['d_lag0']['d_sharpe']:+.3f} | plc DD {x['placebo_pct_maxdd_EXT']:.1f} Sh {x['placebo_pct_sharpe_EXT']:.1f} | arm DD {x['EXT']['arm']['maxdd']*100:.1f} CAGR {x['EXT']['arm']['cagr']*100:.2f}")
print({n: {w: (round(out[n]['live'][w]['cagr']*100,2), round(out[n]['live'][w]['maxdd']*100,1), round(out[n]['live'][w]['sharpe'],2)) for w in ('EXT','DISC')} for n in out})
