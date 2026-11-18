"""D12: rerun the near-pass per-leg rules with ETF proxies (SCZ, EFA before SCZ; EEM) in place of the
stale-priced mutual-fund NAVs DISVX / DFEMX. Writes ../d12_etf_proxy.json."""
import copy, json, os
import numpy as np
import common as C, arms as A, engine as E, run as RUN

p = C.load_panel(); q = copy.copy(p); q["ret"] = p["ret"].copy()
q["ret"]["DISVX"] = np.where(p["ret"]["SCZ"].notna(), p["ret"]["SCZ"], p["ret"]["EFA"])
q["ret"]["DFEMX"] = p["ret"]["EEM"]
KEYS = ("A1", "A2", "A6", "A7", "A8", "A10", "A15")
out = {}
for v in ("T1", "T2"):
    res, _ = RUN.run_tape(q, v)
    A_ = res["arms"]
    out[v] = dict(live=res["live"], n_survive=sum(a["verdict"]["survives"]["pass"] for a in A_.values()),
                  n_drawdown_tool=sum(a["verdict"]["drawdown_tool"]["pass"] for a in A_.values()),
                  arms={k: dict(verdict=A_[k]["verdict"], d={w: A_[k]["win"][w]["d"] for w in ("EXT", "DISC", "CONF")},
                                arm={w: A_[k]["win"][w]["arm"] for w in ("EXT", "DISC", "CONF")},
                                lag0_conf=A_[k]["stress"]["lag0"]["CONF"],
                                placebo={kk: vv for kk, vv in A_[k]["win"]["EXT"]["placebo"].items()}) for k in KEYS})
    print(v, "passes: sharpe", out[v]["n_survive"], "drawdown tool", out[v]["n_drawdown_tool"])
    for k in KEYS:
        x = out[v]["arms"][k]; dt = x["verdict"]["drawdown_tool"]
        print(f"  {k:4s} dDD EXT {x['d']['EXT']['d_maxdd']*100:+5.1f} DISC {x['d']['DISC']['d_maxdd']*100:+5.1f} CONF {x['d']['CONF']['d_maxdd']*100:+5.1f} | dUlc DISC {x['d']['DISC']['d_ulcer']*100:+5.2f} CONF {x['d']['CONF']['d_ulcer']*100:+5.2f} | dS EXT {x['d']['EXT']['d_sharpe']:+.3f} | p_fw {dt['p_fw']:.3f} pz53 {x['placebo']['pz_fw53_maxdd']:.3f} | fails: {[c for c in ('dd2_both','ulcer_both','cagr_within','p_fw_lt_10','lag2') if not dt[c]]}")
json.dump(RUN._rnd(json.loads(json.dumps(out, default=float))), open(os.path.join(C.STUDY, "d12_etf_proxy.json"), "w"), separators=(",", ":"))
