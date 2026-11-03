"""SPEC v1 §3.6: exact operating characteristics of the final D-3 design (after the v1 reviews).

Equal p_u across units (the true p_u is unknown and not computed). The state at the firing is pinned by the
zero-drift p_u (0.30 or 0.50); the frozen GARCH-t then gives p_u at -1%/yr (PASS), 0 (reported) and +1%/yr
(FAIL) for that same state. A PASS needs S_n >= c_j, c_j from the exact alpha-spending recursion on p_u(-1%/yr);
a FAIL needs the 98.3% upper bound on the edge, computed on p_u(+1%/yr), below +0.10. True hit probability =
p_u(true drift) + delta. Synthetic: no data beyond the frozen fit.

    python3 -I d3_power_v1.py <freeze.json> [N]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import d3  # noqa: E402

DRIFTS = {"minus1": -1.0 / 250, "zero": 0.0, "plus1": 1.0 / 250, "plus09": 0.9 / 250, "minus2": -2.0 / 250}


def state_table(params: dict, n: int) -> tuple[np.ndarray, dict]:
    hu = params["omega"] / (1 - params["alpha"] - params["beta"])
    mult = np.exp(np.linspace(np.log(0.25), np.log(25.0), 13))
    tab = {k: [] for k in DRIFTS}
    for i, m in enumerate(mult):
        res = d3.p_u(params, m * hu, n_paths=n, seed=20261103 + i, drifts=DRIFTS)["by_drift"]
        for k in DRIFTS:
            tab[k].append(res[k]["p_u"])
    return mult, {k: np.array(v) for k, v in tab.items()}


def at_zero_drift(p0: float, mult, tab) -> dict:
    """p_u at every drift for the state whose zero-drift p_u is p0 (p_u(0) falls with h: interpolate on it)."""
    z = tab["zero"][::-1]
    x = np.log(mult)[::-1]
    lh = float(np.interp(p0, z, x))
    return {k: float(np.interp(lh, np.log(mult), v)) for k, v in tab.items()} | {"h_over_uncond": float(np.exp(lh))}


def binpmf(m: int, q: float) -> np.ndarray:
    return d3.pb_pmf([q] * m)


def oc(p: dict, delta: float, true_drift: str = "zero") -> dict:
    """P(PASS) by look 1/2/3, P(FAIL by 3), P(INCONCLUSIVE), and the critical values."""
    q = min(1.0, p[true_drift] + delta)
    crit, st, prev = [], np.array([1.0]), 0
    pass_by, fail = [], 0.0
    P = 0.0
    for j, n in enumerate(d3.LOOKS):
        blocks = [[p["minus1"]] * (d3.LOOKS[i] - (d3.LOOKS[i - 1] if i else 0)) for i in range(j + 1)]
        c = d3.critical_value(blocks, crit, d3.ALPHA_CUM[j])
        crit.append(c)
        st = np.convolve(st, binpmf(n - prev, q))
        nxt = st.copy()
        for s in range(len(st)):
            if st[s] == 0:
                continue
            if s >= c:
                P += st[s]
                nxt[s] = 0.0
            elif d3.delta_upper(s, [p["plus1"]] * n) < d3.FAIL_EDGE:
                fail += st[s]
                nxt[s] = 0.0
        st, prev = nxt, n
        pass_by.append(round(P, 3))
    return {"pass_by_look": pass_by, "fail_by_3": round(fail, 3), "inconclusive": round(float(st.sum()), 3), "critical_values": crit}


if __name__ == "__main__":
    params = json.load(open(sys.argv[1], encoding="utf-8"))["d3"]["garch_fit"]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100_000
    mult, tab = state_table(params, n)
    out = {"basis": __doc__.split("\n\n")[0], "n_paths_per_state": n, "states": {}, "table": {}}
    for p0 in (0.30, 0.50):
        p = at_zero_drift(p0, mult, tab)
        out["states"][str(p0)] = {k: round(v, 4) for k, v in p.items()}
        rows = {}
        for delta in (0.0, 0.10, 0.20, 0.30, 0.40):
            rows[f"{delta:+.2f}"] = {"true drift 0": oc(p, delta, "zero")}
        rows["+0.00"]["true drift -1%/yr"] = oc(p, 0.0, "minus1")
        rows["+0.00"]["true drift -2%/yr"] = oc(p, 0.0, "minus2")
        rows["+0.00"]["true drift +1%/yr"] = oc(p, 0.0, "plus1")
        for delta in (0.20, 0.30):
            rows[f"{delta:+.2f}"]["true drift +0.9%/yr"] = oc(p, delta, "plus09")
        out["table"][str(p0)] = rows
    print(json.dumps(out, indent=1))
