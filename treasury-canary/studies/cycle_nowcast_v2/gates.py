"""Cycle nowcast v2 — merge-blocking gates (SPEC v1 §7.1 reproduction gate on F1,
§7.1 scoring-mode delta row, §2.3 identity gates, legacy deployed outputs, and
the §7.2 engine gates on F3 / F4). Writes gate_report_F1.json.

RULES (task B1): every row carries the computed value, the target, the
tolerance and pass/fail; a miss is REPORTED with its month-level diff, never
widened. NOTHING outside these named gate rows is scored: no v2 member (ENS_HH,
CLAIMS_HH, completion-error band) is aggregated over the evaluation window on
any fixture in this stage; the scored run is a separate, later invocation.

Run:  python3 gates.py            (from this directory; writes gate_report_F1.json)
      python3 -c "import gates; gates.run_all(write=False)"
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import engine as E   # noqa: E402
import metrics as X  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))          # treasury-canary
F1_PATH = os.path.join(REPO, "backend", "tests", "fixtures_cycle_fred.json")
SPEC_JSON = os.path.join(REPO, "backend", "app", "sources", "cycle_nowcast_spec.json")
F3_DIR = os.path.join(HERE, "data", "fred_2026-10-20")
F4_DIR = os.path.join(HERE, "data", "alfred_shutdown")
REPORT_PATH = os.path.join(HERE, "gate_report_F1.json")
BACKEND = os.path.join(REPO, "backend")
DEPLOYED_SERIES = ["PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL", "PERMIT", "ICSA", "AWHMAN",
                   "UMCSENT", "T10Y3M", "BAA10YM", "GS10", "TB3MS", "USREC"]
F4_DATES = ("2025-11-20", "2025-12-16", "2026-01-09", "2026-02-06")
ICSA_LIST = os.path.join(HERE, "data", "vintage_lists", "vd_ICSA.txt")        # F8 (B2)
# v1 §2.4 expected F4 outputs, written before the engine ran. "claims": the claims
# half is a value (CLAIMS_HH and ENS_HH finite, fit rows ending at K(d)) on every
# date once the ICSA vintage is in F4 — written 2026-10-20 before the _g rows ran
# with the three added ICSA vintages (v1 §2.4 'F4 gains the ICSA vintages at
# 2025-11-20, 2025-12-16 and 2026-02-06').
F4_EXPECTED = {
    "2025-11-20": {"target": "2025-09", "IS": "A", "lags": {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 2}, "dropped": [], "claims": True},
    "2025-12-16": {"target": "2025-11", "IS": "A", "lags": {"PAYEMS": 0, "INDPRO": 2, "W875RX1": 2, "CMRMTSPL": 4}, "dropped": ["CMRMTSPL"], "claims": True},
    "2026-01-09": {"target": "2025-12", "IS": "A", "lags": {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 3, "CMRMTSPL": 3}, "dropped": [], "claims": True},
    "2026-02-06": {"target": "2025-12", "IS": "B", "lags": {"PAYEMS": 0, "INDPRO": 0, "W875RX1": 1, "CMRMTSPL": 2}, "dropped": [], "claims": True},
}
F3_EXPECTED = {"target": "2026-09", "IS": "B", "lags": {"PAYEMS": 0, "INDPRO": 0, "W875RX1": 1, "CMRMTSPL": 2}}
# August table values quoted by v0 §7.1 (CYCLE_NOWCAST.md / cycle_nowcast_spec.json)
ENS_ONSETS = ["1974-03", "1979-10", "1981-06", "1990-10", "2001-03", "2008-03", "2020-03"]
CLAIMS_ONSETS = ["1974-02", "1979-10", "1981-06", "1990-10", "2001-02", "2007-12", "2020-03"]


# ----------------------------------------------------------------------------
def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _py(v):
    """numpy -> JSON-safe python."""
    if isinstance(v, (np.floating, float)):
        return None if not math.isfinite(float(v)) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, np.ndarray):
        return [_py(x) for x in v.tolist()]
    if isinstance(v, (list, tuple)):
        return [_py(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _py(x) for k, x in v.items()}
    return v


def row(rid: str, section: str, quantity: str, computed, target, tolerance, kind: str,
        spec: str = "", detail=None, soft: bool = False, not_run_reason: str | None = None) -> dict:
    """kind: 'abs' |computed-target|<=tol; 'exact' ==; 'le' computed<=tol;
    'bool' computed==target; 'info' (no pass/fail)."""
    status = "INFO"
    if not_run_reason is not None:
        status = "NOT_RUN"
    elif kind == "abs":
        status = "PASS" if (computed is not None and math.isfinite(float(computed))
                            and abs(float(computed) - float(target)) <= tolerance) else "FAIL"
    elif kind == "exact":
        status = "PASS" if computed == target else "FAIL"
    elif kind == "le":
        status = "PASS" if (computed is not None and float(computed) <= tolerance) else "FAIL"
    elif kind == "bool":
        status = "PASS" if bool(computed) == bool(target) else "FAIL"
    r = {"id": rid, "section": section, "quantity": quantity, "computed": _py(computed),
         "target": _py(target), "tolerance": _py(tolerance), "kind": kind, "status": status,
         "pass": None if status in ("INFO", "NOT_RUN") else status == "PASS", "spec": spec}
    if soft:
        r["soft"] = True
    if detail is not None:
        r["detail"] = _py(detail)
    if not_run_reason:
        r["not_run_reason"] = not_run_reason
    return r


def r6(x):
    return None if x is None or not math.isfinite(float(x)) else round(float(x), 6)


# ----------------------------------------------------------------------------
def deployed_module():
    """The deployed business_cycle module (read-only use: legacy outputs, F3 None).
    Returns None when the backend cannot be imported (rows become NOT_RUN)."""
    try:
        if BACKEND not in sys.path:
            sys.path.insert(0, BACKEND)
        from app.sources import business_cycle as bc  # type: ignore
        return bc
    except Exception as exc:  # noqa: BLE001
        return None


def _table(sim, y, p, m, ex, p90):
    """the August-table statistics for one simulation (bridge/claims/ens arrays)."""
    out = {}
    for k in ("bridge", "claims", "ens"):
        e = sim[k] - y
        out[k] = {"rmse": X.rmse(e), "rmse_1990": X.rmse(e, p90), "rmse_ex2020": X.rmse(e, ex)}
    out["ens"].update({
        "dir": X.directional_accuracy(sim["ens"], y, p),
        "phase": X.phase_accuracy(sim["ens"], y),
        "trans": X.transition_accuracy(sim["ens"], y, p),
        "dm": X.dm_test(sim["ens"] - y, p - y),
        "dm_ex2020": X.dm_test(sim["ens"] - y, p - y, mask=ex),
        "onsets": X.onset_table(m, y, sim["ens"], E.ONSETS),
        "false_alarms": X.false_alarms(m, y, sim["ens"]),
    })
    out["claims"].update({"onsets": X.onset_table(m, y, sim["claims"], E.ONSETS),
                          "false_alarms": X.false_alarms(m, y, sim["claims"])})
    return out


def _count_diffs(m, y, p, a, b, name_a, name_b):
    """month-level diff of exact counts between two ENS series (v1 §7.1):
    transition calls that flip, onset crossings that move, false alarms that change."""
    lab = X.label3
    tr = X.transitions(y, p)
    flips = [{"month": mm, name_a: r6(va), name_b: r6(vb), "realized": r6(t),
              "called_" + name_a: lab(va) == lab(t), "called_" + name_b: lab(vb) == lab(t)}
             for mm, va, vb, t, f in zip(m, a, b, y, tr) if f and (lab(va) == lab(t)) != (lab(vb) == lab(t))]
    oa = X.onset_table(m, y, a, E.ONSETS)["nowcast_cross_months"]
    ob = X.onset_table(m, y, b, E.ONSETS)["nowcast_cross_months"]
    onset_moves = [{"onset": on, name_a: x, name_b: z} for on, x, z in zip(E.ONSETS, oa, ob) if x != z]
    fa, fb = X.false_alarms(m, y, a), X.false_alarms(m, y, b)
    return {"transition_flips": flips, "onset_moves": onset_moves,
            "false_alarms": {name_a: fa, name_b: fb}, "any_change": bool(flips or onset_moves or fa != fb)}


# ----------------------------------------------------------------------------
def run_f1(rows: list, diag: dict):
    series = E.load_fixture_json(F1_PATH)
    ds = E.build(series)
    tg = E.eval_targets(ds)
    rep = E.simulate(ds, E.PATTERNS["A"], "reproduction", tg, "original")
    m, y, p = rep["months"], rep["y"], rep["pers_real"]
    ex, p90 = X.ex2020_mask(m), X.since_mask(m, "1990-01")
    S = "F1_reproduction"
    sp = "v0 §7.1 / v1 §7.1 (reproduction_mode)"
    # --- window and axis facts
    rows.append(row("W01", S, "eval window n (targets 1972-01..2026-06)", len(tg), 654, 0, "exact", sp,
                    {"first": m[0], "last": m[-1]}))
    rows.append(row("W02", S, "eval window n 1990-01+", int(p90.sum()), 438, 0, "exact", sp))
    rows.append(row("W03", S, "first COIN month (1959 start, 120 warm-up)", ds.months[int(np.flatnonzero(np.isfinite(ds.coin))[0])],
                    "1969-06", 0, "exact", "v0 §1"))
    rows.append(row("W04", S, "realized COIN 2026-06 (3-member partial on F1)", r6(ds.coin[ds.i("2026-06")]), -0.4917, 0.0005, "abs",
                    "v1 §1 row 1 (−0.4917; doc −0.492)"))
    rows.append(row("W05", S, "PAYEMS-only partial COIN 2026-07", r6(ds.coin[ds.i("2026-07")]), -0.4485, 0.0005, "abs",
                    "verify_R1 F1 (−0.4485; doc −0.448)"))
    rows.append(row("W06", S, "NBER onsets from USREC (1972-01+)", E.onsets_from_usrec(ds), list(E.ONSETS), 0, "exact", "v0 §1"))
    # --- PERS
    e = p - y
    rows.append(row("P01", S, "PERS RMSE full", r6(X.rmse(e)), 0.4674, 0.0001, "abs", sp))
    rows.append(row("P02", S, "PERS RMSE 1990+", r6(X.rmse(e, p90)), 0.5316, 0.0001, "abs", sp))
    rows.append(row("P03", S, "PERS RMSE ex-2020 (population; n−1 would be 0.2582)", r6(X.rmse(e, ex)), 0.2580, 0.0001, "abs", sp,
                    {"n_ex2020": int(ex.sum()), "n_minus_1_form": r6(math.sqrt(np.sum(e[ex] ** 2) / (ex.sum() - 1)))}))
    pa = X.phase_accuracy(p, y)
    rows.append(row("P04", S, "PERS phase accuracy %", round(pa["accuracy_pct"], 3), 82.6, 0.1, "abs", sp, pa))
    ta, ta90 = X.transition_accuracy(p, y, p), X.transition_accuracy(p, y, p, p90)
    rows.append(row("P05", S, "realized transitions full", ta["n_transitions"], 114, 0, "exact", sp))
    rows.append(row("P06", S, "realized transitions 1990+", ta90["n_transitions"], 75, 0, "exact", sp))
    ot_real = X.onset_table(m, y, y, E.ONSETS)
    rows.append(row("P07", S, "realized −0.75 crossing months (window [onset−6, onset+12])",
                    ot_real["realized_cross_months"], list(E.REALIZED_CROSS), 0, "exact", sp))
    # --- BRIDGE / CLAIMS / ENS (August forms, reproduction mode)
    T = _table(rep, y, p, m, ex, p90)
    i7 = ds.i("2026-07")
    live_b = E.complete_month(ds, i7, E.PATTERNS["A"], "reproduction")
    rows.append(row("B01", S, "BRIDGE RMSE full", r6(T["bridge"]["rmse"]), 0.3348, 0.002, "abs", sp,
                    {"n_nan": int(np.isnan(rep["bridge"]).sum()),
                     "note": "1977-06/07: CMRMTSPL L2 history < 120 → skipped and re-meaned (v1 §2.2)"}))
    rows.append(row("B02", S, "BRIDGE RMSE 1990+", r6(T["bridge"]["rmse_1990"]), 0.3656, 0.002, "abs", sp))
    rows.append(row("B03", S, "BRIDGE live 2026-07", r6(live_b["value"]), -0.347, 0.002, "abs", sp,
                    {c: {"n": f["n_fit"], "coef": [round(b, 7) for b in f["beta"]]} for c, f in live_b["fits"].items()}))
    spec = json.load(open(SPEC_JSON))
    for c in E.BRIDGED_MEMBERS:
        sc = spec["components"]["BRIDGE"]["projections"][c]
        rows.append(row(f"B04_{c}", S, f"BRIDGE {c} full-history coefficients vs spec (max |Δ|)",
                        r6(max(abs(a - b) for a, b in zip(live_b["fits"][c]["beta"], sc["coef"]))), 0, 1e-6, "le",
                        "cycle_nowcast_spec.json", {"n": live_b["fits"][c]["n_fit"], "spec_n": sc["n"]}))
    rows.append(row("C01", S, "CLAIMS (expanding-z, original form) RMSE full", r6(T["claims"]["rmse"]), 0.3930, 0.003, "abs", sp,
                    {"rmse_1990": r6(T["claims"]["rmse_1990"]), "fallback_months": rep["claims_status"].count("fallback")}))
    design = E.claims_design(ds, ds.coin, False, "real")
    lv, lst, ln, lbeta = E.claims_value(ds, i7, i7 - 1, design, ds.coin[i7 - 1])
    rows.append(row("C02", S, "CLAIMS live 2026-07 (walk-forward fit rows t ≤ 2026-06)", r6(lv), -0.429, 0.003, "abs", sp,
                    {"n_fit": ln, "coef": [round(float(b), 7) for b in lbeta]}))
    b587, n587, r0, r1 = E.claims_fit(ds, design, i7)
    scoef = spec["components"]["CLAIMS"]["coef"]
    rows.append(row("C03", S, "CLAIMS full-history coefficients vs spec (max |Δ|, rows t ≤ 2026-07 incl. partial targets)",
                    r6(max(abs(float(a) - b) for a, b in zip(b587, scoef))), 0, 1e-3, "le", sp,
                    {"coef": [round(float(b), 7) for b in b587], "spec": scoef, "rows": [r0, r1]}))
    rows.append(row("C04", S, "CLAIMS n (full-history fit incl. 2026-06 3-member and 2026-07 PAYEMS-only partial rows)",
                    int(n587), 587, 0, "exact", sp + " / verify_R1 F9"))
    rows.append(row("C05", S, "CLAIMS live with spec coefficients on the same features", r6(scoef[0] + sum(
        b * x for b, x in zip(scoef[1:], E.claims_features(ds, i7, ds.coin[i7 - 1])))), -0.429, 0.003, "abs", sp))
    en = T["ens"]
    rows.append(row("E01", S, "ENS_BC RMSE full", r6(en["rmse"]), 0.3344, 0.002, "abs", sp))
    rows.append(row("E02", S, "ENS_BC RMSE 1990+", r6(en["rmse_1990"]), 0.3692, 0.002, "abs", sp))
    rows.append(row("E03", S, "ENS_BC RMSE ex-2020", r6(en["rmse_ex2020"]), 0.2202, 0.002, "abs", sp))
    rows.append(row("E04", S, "ENS_BC directional accuracy % (realized COIN(M−1) both sides, ties wrong)",
                    round(en["dir"]["accuracy_pct"], 3), 69.8, 0.5, "abs", sp + "; v1 §1 A8", en["dir"]))
    rows.append(row("E05", S, "ENS_BC phase accuracy %", round(en["phase"]["accuracy_pct"], 3), 83.8, 0.3, "abs", sp, en["phase"]))
    rows.append(row("E06", S, "ENS_BC transitions called / realized", [en["trans"]["hits"], en["trans"]["n_transitions"]], [29, 114], 0, "exact", sp))
    rows.append(row("E07", S, "ENS_BC DM vs PERS (NW-6 Bartlett)", round(en["dm"]["t"], 4), -1.63, 0.1, "abs", sp + "; v1 §1 F08",
                    {k: en["dm"][k] for k in ("n", "mean_d", "se")}))
    rows.append(row("E08", S, "ENS_BC DM ex-2020", round(en["dm_ex2020"]["t"], 4), -5.33, 0.3, "abs", sp, {"n": en["dm_ex2020"]["n"]}))
    rows.append(row("E09", S, "ENS_BC onset crossing months", en["onsets"]["nowcast_cross_months"], ENS_ONSETS, 0, "exact", sp,
                    en["onsets"]))
    rows.append(row("E10", S, "CLAIMS onset crossing months", T["claims"]["onsets"]["nowcast_cross_months"], CLAIMS_ONSETS, 0, "exact", sp,
                    T["claims"]["onsets"]["summary"]))
    rows.append(row("E11", S, "ENS_BC false alarms", en["false_alarms"], ["1981-06"], 0, "exact", sp))
    rows.append(row("E12", S, "CLAIMS false alarms", T["claims"]["false_alarms"], ["1981-06", "1981-07"], 0, "exact", sp))
    # --- ENS_GRID_REPRO
    ar2 = E.ar2_series(ds, tg)
    rows.append(row("G01", S, "AR2 RMSE full / 1990+ (August table 0.4692 / 0.5383; pins the AR2 reading)",
                    [r6(X.rmse(ar2 - y)), r6(X.rmse(ar2 - y, p90))], [0.4692, 0.5383], 0.0005, "info", "v0 §1 method 2"))
    lm60, lead60, _ = E.leading_composite(series, start="1960-01")
    lm59, lead59, _ = E.leading_composite(series, start="1959-01")
    lr60 = E.leadreg_series(ds, lm60, lead60, tg)
    # (the walk-forward cache keys carry a content hash of the design, so the two LEAD
    # starts never alias; no cache clearing is needed between the two calls)
    lr59 = E.leadreg_series(ds, lm59, lead59, tg)
    rows.append(row("G02", S, "LEADREG RMSE full / 1990+ with 1959-start LEAD (August table 0.4511 / 0.5179)",
                    [r6(X.rmse(lr59 - y)), r6(X.rmse(lr59 - y, p90))], [0.4511, 0.5179], 0.0005, "info", "v0 §1 method 3",
                    {"with_1960_start_LEAD": [r6(X.rmse(lr60 - y)), r6(X.rmse(lr60 - y, p90))],
                     "reading": "the August harness built LEAD on the 1959 axis; ENS_GRID_REPRO uses it; the board's leading composite keeps 1960 (v1 §2.1)"}))
    members = {"PERS": p, "AR2": ar2, "LEADREG": lr59, "BRIDGE": rep["bridge"], "CLAIMS": rep["claims"]}
    grid = E.ens_grid(members, y, selector_lag=1, warmup=24, default="pers")
    c5050 = grid["count_by_label"].get("0.5*BRIDGE+0.5*CLAIMS", 0)
    rows.append(row("G03", S, "ENS_GRID_REPRO RMSE (selector errors through M−1; 24-month warm-up; PERS before selection starts)",
                    r6(X.rmse(grid["forecast"] - y)), 0.3319, 0.003, "abs", "v1 §1 ENS_GRID (F21/DT-22)",
                    {"rmse_1990": r6(X.rmse(grid["forecast"] - y, p90)), "n_selected": grid["n_selected"],
                     "default_equal_weight_instead": r6(X.rmse(E.ens_grid(members, y, 1, 24, "equal")["forecast"] - y))}))
    rows.append(row("G04", S, "ENS_GRID_REPRO: months choosing exactly 0.5·BRIDGE + 0.5·CLAIMS (of 630 selections)",
                    c5050, 354, 5, "abs", "v1 §1 ENS_GRID",
                    {"n_selected": grid["n_selected"],
                     "top_combos": sorted(grid["count_by_label"].items(), key=lambda kv: -kv[1])[:6]}))
    # diagnostics for the G04 miss (not gates): variants of the unpinned conventions
    gd = {}
    for lbl, mem in (("LEAD_1959", members), ("LEAD_1960", {**members, "LEADREG": lr60})):
        for wu in (12, 24, 36):
            g = E.ens_grid(mem, y, 1, wu, "pers")
            gd[f"{lbl}|warmup{wu}"] = {"rmse": r6(X.rmse(g["forecast"] - y)), "n_selected": g["n_selected"],
                                      "count_5050": g["count_by_label"].get("0.5*BRIDGE+0.5*CLAIMS", 0)}
    # near-tie count: runner-up within 1% of the best cumulative MSE
    names = list(members)
    P = np.column_stack([members[k] for k in names])
    C = np.array([w for _, w in E.grid_dictionary(names)])
    E2 = ((P @ C.T) - y[:, None]) ** 2
    cum = np.cumsum(E2, 0)
    near = sum(1 for k in range(24, len(y)) if (lambda s: (s[1] - s[0]) / s[0] < 0.01)(np.sort(cum[k - 1] / k)))
    gd["near_ties_within_1pct_mse"] = int(near)
    diag["ens_grid_repro_variants"] = gd
    rows.append(row("G05", S, "leading composite (1960 start) == deployed compute()['leading'] (max |Δ| at 3 dp)",
                    None, 0, 1e-9, "le", "v1 §2.1 DT-10", not_run_reason="deployed module not imported"))
    return ds, series, tg, rep, T, members, grid


def run_scoring_delta(rows, diag, ds, tg, rep, T):
    """v1 §7.1 second gate row: scoring_mode on the same fixture; deltas recorded."""
    m, y, p = rep["months"], rep["y"], rep["pers_real"]
    ex, p90 = X.ex2020_mask(m), X.since_mask(m, "1990-01")
    S = "F1_scoring_mode_delta"
    sp = "v1 §7.1 (D1 rows t ≤ M−L; D2/D6 rows t ≤ K(d), no partial targets; D3)"
    # (b) literal: D1 + D2 (CLAIMS rows t <= K = M-2 at the IS-A pattern) + D6
    sco = E.simulate(ds, E.PATTERNS["A"], "scoring", tg, "original")
    Ts = _table(sco, y, p, m, ex, p90)
    # (a) D1 + D6 only: CLAIMS rows t <= M-1 without partial targets (the reading under which the spec's own 1980-11 expectation was computed)
    d1 = dict(rep)
    sim_d1_claims = E.simulate(ds, E.PATTERNS["A"], "reproduction", tg, "original")
    # CLAIMS with D6 only: rows t <= M-1, complete targets only
    dsg = E.claims_design(ds, ds.coin, True, "real")
    cl_d6 = np.full(len(tg), np.nan)
    for k, i in enumerate(tg):
        cl_d6[k] = E.claims_value(ds, i, i - 1, dsg, ds.coin[i - 1])[0]
    d1["bridge"] = sco["bridge"]
    d1["claims"] = cl_d6
    d1["ens"] = 0.5 * sco["bridge"] + 0.5 * cl_d6
    Td = _table(d1, y, p, m, ex, p90)
    for tag, Tv, sim, label in (("S", Ts, sco, "literal: D1+D2+D6 (CLAIMS rows t ≤ K = M−2)"),
                                ("D", Td, d1, "diagnostic: D1+D6 (CLAIMS rows t ≤ M−1, partial targets excluded)")):
        for k in ("bridge", "claims", "ens"):
            d = Tv[k]["rmse"] - T[k]["rmse"]
            rows.append(row(f"{tag}01_{k}", S, f"|ΔRMSE| {k.upper()} full — {label}", r6(abs(d)), 0, 0.003, "le", sp,
                            {"reproduction": r6(T[k]["rmse"]), "scoring": r6(Tv[k]["rmse"]), "signed_delta": r6(d),
                             "delta_ex2020": r6(Tv[k]["rmse_ex2020"] - T[k]["rmse_ex2020"]),
                             "delta_1990": r6(Tv[k]["rmse_1990"] - T[k]["rmse_1990"]),
                             "rmse_2020_only": {"reproduction": r6(X.rmse(rep[k] - y, ~ex)), "scoring": r6(X.rmse(sim[k] - y, ~ex))}}))
        dd = Tv["ens"]["dir"]["accuracy_pct"] - T["ens"]["dir"]["accuracy_pct"]
        rows.append(row(f"{tag}02", S, f"|Δ directional accuracy| ENS pp — {label}", round(abs(dd), 4), 0, 1.0, "le", sp,
                        {"reproduction": round(T["ens"]["dir"]["accuracy_pct"], 4), "scoring": round(Tv["ens"]["dir"]["accuracy_pct"], 4)}))
        cd = _count_diffs(m, y, p, rep["ens"], sim["ens"], "reproduction", "scoring")
        rows.append(row(f"{tag}03", S, f"exact-count changes logged (transitions / onsets / false alarms) — {label}",
                        {"transitions": [T["ens"]["trans"]["hits"], Tv["ens"]["trans"]["hits"]],
                         "flip_months": [f["month"] for f in cd["transition_flips"]],
                         "onset_moves": cd["onset_moves"], "false_alarms": cd["false_alarms"]},
                        "expected: 1980-11, one transition", None, "info", sp, cd))
        rows.append(row(f"{tag}04", S, f"exact-count change == expected {{1980-11}} only — {label}",
                        [f["month"] for f in cd["transition_flips"]] == ["1980-11"] and not cd["onset_moves"]
                        and cd["false_alarms"]["reproduction"] == cd["false_alarms"]["scoring"], True, None, "bool", sp))
        rows.append(row(f"{tag}05", S, f"DM / DM ex-2020 under scoring rows — {label}",
                        [round(Tv["ens"]["dm"]["t"], 4), round(Tv["ens"]["dm_ex2020"]["t"], 4)],
                        [round(T["ens"]["dm"]["t"], 4), round(T["ens"]["dm_ex2020"]["t"], 4)], None, "info", sp))
    diag["scoring_mode_largest_claims_moves"] = sorted(
        [(r6(abs(a - b)), mm, r6(a), r6(b)) for mm, a, b in zip(m, rep["claims"], sco["claims"])], reverse=True)[:6]


def run_identity(rows, diag, ds):
    S = "identity"
    i05 = ds.i("2026-05")
    d_real = E.claims_design(ds, ds.coin, True, "id_real")
    b_o, n_o, r0, r1 = E.claims_fit(ds, d_real, i05)
    histC = E.coin_hh_history(ds, E.PREV_PATTERNS["C"], "scoring")
    d_C = E.claims_design(ds, histC, True, "id_C")
    b_C, n_C, r0c, r1c = E.claims_fit(ds, d_C, i05)
    rows.append(row("I01", S, "IS-C CLAIMS_HH coefficients == original CLAIMS on rows t ≤ 2026-05 (max |Δ|)",
                    float(np.max(np.abs(b_o - b_C))), 0, 1e-9, "le", "v1 §2.3 identity (DT-16)",
                    {"n_original": n_o, "n_hh_C": n_C, "rows": [r0, r1], "coef": [round(float(b), 9) for b in b_C]}))
    fin = np.isfinite(histC) & np.isfinite(ds.coin) & ds.complete
    rows.append(row("I02", S, "IS-C completed COIN(M−1) == realized on months with L_CMRMTSPL = 1 (max |Δ|)",
                    float(np.max(np.abs(histC[fin] - ds.coin[fin]))), 0, 1e-12, "le", "v1 §2.3 identity (DT-2)",
                    {"n": int(fin.sum()), "first": ds.months[int(np.flatnonzero(fin)[0])], "last": ds.months[int(np.flatnonzero(fin)[-1])]}))
    histA = E.coin_hh_history(ds, E.PREV_PATTERNS["A"], "scoring")
    cp = E.complete_month(ds, ds.i("2026-06"), E.PREV_PATTERNS["A"], "scoring")
    rows.append(row("I03", S, "completed COIN(2026-06), 1-bridged (CMRMTSPL L1) on F1 — deterministic coincident_completed bound",
                    r6(cp["value"]), -0.3221, 0.0015, "abs", "v1 §7.2 (bound from the deterministic algorithm; verify_R1 F4 −0.3221)",
                    {"pattern": cp["bridged"], "fit": cp["fits"].get("CMRMTSPL")}))
    c77 = E.complete_month(ds, ds.i("1977-06"), E.PREV_PATTERNS["A"], "scoring")
    rows.append(row("I04", S, "1977-06 1-bridged completion: CMRMTSPL history < 120 → skipped and re-meaned (flag)",
                    c77["skipped"], ["CMRMTSPL"], 0, "exact", "v1 §2.2", {"value_3_member": r6(c77["value"]),
                                                                            "realized_4_member": r6(ds.coin[ds.i("1977-06")])}))
    rows.append(row("I05", S, "stored 1-bridged completion history defined months (D4)", int(np.isfinite(histA).sum()),
                    None, None, "info", "v1 §2.3 D4", {"first": ds.months[int(np.flatnonzero(np.isfinite(histA))[0])]}))


# Once the deployed module carries cycle-nowcast-v2 (panel wiring after the scored run, 2026-10-28),
# the August fixed-lag form is no longer importable from it: the legacy rows L01-L03 / F3_01 go
# NOT_RUN with this reason; the engine-emulation rows (L04-L06, F3_02, F4_*_h) keep the August pins.
LEGACY_RETIRED = ("deployed module carries cycle-nowcast-v2 (wired 2026-10-28 after the scored run); the August "
                  "fixed-lag form is pinned by the engine emulation rows L04-L06 / F3_02 / F4_*_h")


def deployed_is_v2(bc) -> bool:
    return bc is not None and getattr(bc, "NOWCAST_STATS", None) is not None


def run_legacy(rows, diag, ds, series, bc):
    S = "legacy_deployed"
    sp = "v0 §7.1 'Legacy deployed output on the fixture'"
    if bc is None or deployed_is_v2(bc):
        why = "deployed module not imported" if bc is None else LEGACY_RETIRED
        for rid, q in (("L01", "deployed bridge"), ("L02", "deployed claims"), ("L03", "deployed ens")):
            rows.append(row(rid, S, q, None, None, 0.005, "abs", sp, not_run_reason=why))
    else:
        FIX = json.load(open(F1_PATH))
        b = bc.compute(raw_override=FIX)
        nc = b["nowcast"]
        rows.append(row("L01", S, "deployed nowcast bridge on F1", nc["bridge"], -0.347, 0.005, "abs", sp, {"month": nc["month"]}))
        rows.append(row("L02", S, "deployed nowcast claims on F1 (full-sample z, rows from 1970-07)", nc["claims"], -0.449, 0.005, "abs", sp))
        rows.append(row("L03", S, "deployed nowcast ens on F1", nc["value"], -0.398, 0.005, "abs", sp, {"phase": nc["phase"]}))
    if bc is not None:
        FIX = json.load(open(F1_PATH))
        b = bc.compute(raw_override=FIX)
        lm, lead, _ = E.leading_composite(series)
        dep = dict(zip(b["months"], b["leading"]))
        dmax = max(abs(round(float(v), 3) - dep[mm]) for mm, v in zip(lm, lead) if dep.get(mm) is not None and np.isfinite(v))
        for r in rows:
            if r["id"] == "G05":
                r.update(row("G05", r["section"], r["quantity"], dmax, 0, 1e-9, "le", r["spec"],
                             {"n": len(lm), "axis": [lm[0], lm[-1]]}))
    i7 = ds.i("2026-07")
    cm = E.complete_month(ds, i7, E.PATTERNS["A"], "reproduction")
    dsg = E.claims_design(ds, ds.coin, False, "real")
    v, st, n, beta = E.claims_value(ds, i7, i7 - 1, dsg, ds.coin[i7 - 1])
    rows.append(row("L04", S, "spec form live bridge 2026-07", r6(cm["value"]), -0.347, 0.005, "abs", sp))
    rows.append(row("L05", S, "spec form live claims 2026-07", r6(v), -0.429, 0.005, "abs", sp))
    rows.append(row("L06", S, "spec form live ens 2026-07", r6(0.5 * (cm["value"] + v)), -0.388, 0.005, "abs", sp))


def run_soft(rows, diag, ds, tg, rep):
    """v0 §7.1 SOFT row. ENS_BC_S (the deployed estimator's own QA numbers) is
    computed; ENS_BC_HH is NOT: it is the D-1 primary quantity (ENS_HH at IS-A
    vs PERS) and computing it on F1 before the single scored run would break the
    pre-registration (task rule: nothing scored in this stage)."""
    S = "F1_soft"
    sp = "v0 §7.1 SOFT (QA harness not recoverable; ±1 pp; a miss is raised, never widened)"
    m, y, p = rep["months"], rep["y"], rep["pers_real"]
    ex = X.ex2020_mask(m)
    simS = E.simulate(ds, E.PATTERNS["A"], "reproduction", tg, "S")
    eS, eP = simS["ens"] - y, p - y
    ot = X.onset_table(m, y, simS["ens"], E.ONSETS)
    rows.append(row("Q01", S, "ENS_BC_S RMSE vs PERS % (serve-time regressor = available 3-member COIN(M−1); August training)",
                    round(X.pct_change(X.rmse(eS), X.rmse(eP)), 3), -24.2, 1.0, "abs", sp, {"rmse": r6(X.rmse(eS))}, soft=True))
    rows.append(row("Q02", S, "ENS_BC_S RMSE vs PERS % ex-2020", round(X.pct_change(X.rmse(eS, ex), X.rmse(eP, ex)), 3), -7.0, 1.0, "abs", sp, soft=True))
    rows.append(row("Q03", S, "ENS_BC_S DM ex-2020 (QA −2.76; no tolerance stated)", round(X.dm_test(eS, eP, mask=ex)["t"], 4), -2.76, None, "info", sp, soft=True))
    rows.append(row("Q04", S, "ENS_BC_S onsets earlier/tie/later (QA 5-1-1)", [ot["summary"]["earlier"], ot["summary"]["tie"], ot["summary"]["later"]],
                    [5, 1, 1], 0, "exact", sp, ot["nowcast_cross_months"], soft=True))
    rows.append(row("Q05", S, "ENS_BC_HH −29.8% / −12.5% / transitions 30.7% / onsets 4-1-2", None, [-29.8, -12.5, 30.7, [4, 1, 2]], 1.0, "abs", sp, soft=True,
                    not_run_reason="ENS_BC_HH is the v2 primary quantity (D-1); not computed on any fixture before the single scored run (task rule: nothing scored in this stage); report it in the scored run's honesty box on F1 and F5 (Q4)"))


def _f3_state_and_raw():
    S3 = E.load_fred_csv_dir(F3_DIR, DEPLOYED_SERIES)
    raw3 = {}
    for s in DEPLOYED_SERIES:
        _, rows_ = E.read_fred_csv(os.path.join(F3_DIR, s + ".csv"), s)
        raw3[s] = [[d, v] for d, v in rows_ if v.strip() not in ("", ".") and d >= "1959-01-01"]
    return S3, raw3


def run_f3(rows, diag, bc):
    S = "engine_F3"
    sp = "v1 §7.2 / v1 §1 row 2 (F3 = 2026-10-20 pull)"
    S3, raw3 = _f3_state_and_raw()
    if bc is None or deployed_is_v2(bc):
        rows.append(row("F3_01", S, "deployed compute(F3) nowcast is None", None, True, None, "bool", sp,
                        not_run_reason="deployed module not imported" if bc is None else LEGACY_RETIRED))
    else:
        b3 = bc.compute(raw_override=raw3)
        rows.append(row("F3_01", S, "deployed compute(F3) nowcast is None", b3["nowcast"] is None, True, None, "bool", sp,
                        {"current": b3["current"]}))
    ok, why = E.legacy_form_would_issue(S3)
    rows.append(row("F3_02", S, "engine emulation of the deployed gates on F3 would issue", ok, False, None, "bool", sp, {"reason": why}))
    r3 = E.issue(S3, "2026-10-20")
    rows.append(row("F3_03", S, "v2 issue(F3): target month", r3["target_month"], F3_EXPECTED["target"], 0, "exact", sp))
    rows.append(row("F3_04", S, "v2 issue(F3): information set", r3["info_set"], F3_EXPECTED["IS"], 0, "exact", sp))
    rows.append(row("F3_05", S, "v2 issue(F3): lags", r3["lags"], F3_EXPECTED["lags"], 0, "exact", sp))
    rows.append(row("F3_06", S, "v2 issue(F3): a value (BRIDGE_HH, CLAIMS_HH, ENS_HH all finite; reason None)",
                    all(r3[k] is not None for k in ("bridge_hh", "claims_hh", "ens_hh")) and r3["reason"] is None, True, None, "bool", sp,
                    {"bridge_hh": r6(r3["bridge_hh"]), "claims_hh": r6(r3["claims_hh"]), "ens_hh": r6(r3["ens_hh"]), "phase": r3["phase"],
                     "K": r3["K"], "claims_fit": r3["claims_fit"], "members_bridged": r3["members_bridged"],
                     "completed_prev": r3["completed_prev"], "persistence": r3["persistence"]}))
    rows.append(row("F3_07", S, "v2 issue(F3): dropped members", r3["dropped"], [], 0, "exact", sp))
    rows.append(row("F3_08", S, "v2 issue(F3): CLAIMS_HH training rows end at K(d) = 2026-07", r3["claims_fit"]["rows"][1] if r3["claims_fit"] else None,
                    "2026-07", 0, "exact", "v1 §2.3 D2"))


def run_f4(rows, diag):
    S = "engine_F4"
    sp = "v1 §2.4 expected F4 outputs (written before the engine ran) / v1 §7.2"
    S3, raw3 = _f3_state_and_raw()
    for d in F4_DATES:
        # ICSA (weekly, Thursday vintages): the vintage in hand at d is the latest LISTED
        # vintage <= d (v1 §4.4), stored as alf_ICSA_<listed date>.csv; the research-pass
        # file alf_ICSA_2026-01-09.csv (header echo of a non-listed date, body == the
        # listed 2026-01-08 vintage) is used only when no listed-date file exists.
        icsa_listed = E.latest_listed_vintage(ICSA_LIST, d) if os.path.exists(ICSA_LIST) else None
        vdates = {}
        if icsa_listed and os.path.exists(os.path.join(F4_DIR, f"alf_ICSA_{icsa_listed}.csv")):
            vdates["ICSA"] = icsa_listed
        st = E.load_alfred_state(F4_DIR, d, ["PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL", "ICSA", "T10Y3M", "UMCSENT"],
                                 vintage_dates=vdates)
        have = sorted(st)
        src = {"ICSA": (f"alf_ICSA_{vdates['ICSA']}.csv (listed vintage <= {d})" if "ICSA" in vdates
                        else f"alf_ICSA_{d}.csv (research-pass file; header echoes the requested date)")
               if "ICSA" in st else None}
        if "T10Y3M" not in st:
            # v1 §4.1 / §2.4 'T10Y3M may be current': the curve is taken from the 2026-10-20
            # pull restricted to days <= d (no observation after the issue date enters)
            st["T10Y3M"] = E.monthly_from_pairs([(dd, v) for dd, v in raw3["T10Y3M"] if dd <= d], "mean")
            src["T10Y3M"] = f"current (2026-10-20 pull, days <= {d}) per v1 §4.1"
        else:
            src["T10Y3M"] = f"alf_T10Y3M_{d}.csv (listed vintage)"
        # pre-1982 curve = GS10 - TB3MS, taken current (H.15 rates are not revised; v1 §4.1 treats T10Y3M/BAA10YM as current)
        st["GS10"], st["TB3MS"] = S3["GS10"], S3["TB3MS"]
        r = E.issue(st, d)
        exp = F4_EXPECTED[d]
        pre = f"F4_{d}"
        rows.append(row(pre + "_a", S, f"{d}: vintages in F4", have, None, None, "info", sp,
                        {"last_months": {s: max(st[s]) for s in have}, "sources": src}))
        rows.append(row(pre + "_b", S, f"{d}: target month", r["target_month"], exp["target"], 0, "exact", sp))
        rows.append(row(pre + "_c", S, f"{d}: information set", r["info_set"], exp["IS"], 0, "exact", sp))
        rows.append(row(pre + "_d", S, f"{d}: lags", r["lags"], exp["lags"], 0, "exact", sp))
        rows.append(row(pre + "_e", S, f"{d}: dropped (lag ≥ 4 → dropped and re-meaned)", r["dropped"], exp["dropped"], 0, "exact", sp))
        # bridge half: a value, and no bridge-side reason (the top-level reason also names a
        # failed claims half, v1 §2.4 'every None carries a reason' — that is gated in _g)
        rows.append(row(pre + "_f", S, f"{d}: BRIDGE_HH is a value (bridge half; no bridge-side reason)",
                        r["bridge_hh"] is not None and not str(r["reason"] or "").startswith("BRIDGE_HH undefined"), True, None, "bool", sp,
                        {"bridge_hh": r6(r["bridge_hh"]), "members_bridged": r["members_bridged"], "members_skipped": r["members_skipped"],
                         "K": r["K"], "completed_prev": r["completed_prev"], "persistence": r["persistence"], "reason": r["reason"]}))
        if "ICSA" in st:
            rows.append(row(pre + "_g", S, f"{d}: CLAIMS_HH / ENS_HH from the ICSA vintage (claims half; fit rows end at K(d); reason None)",
                            r["claims_hh"] is not None and r["ens_hh"] is not None and r["reason"] is None
                            and bool(r["claims_fit"]) and r["claims_fit"]["rows"][1] == r["K"], exp["claims"], None, "bool", sp,
                            {"claims_hh": r6(r["claims_hh"]), "ens_hh": r6(r["ens_hh"]), "phase": r["phase"], "claims_fit": r["claims_fit"],
                             "claims_reason": r["claims_reason"], "reason": r["reason"], "icsa_source": src["ICSA"], "t10y3m_source": src["T10Y3M"],
                             "curve_pre1982_source": "GS10-TB3MS from the 2026-10-20 pull (unrevised rates)"}))
        else:
            rows.append(row(pre + "_g", S, f"{d}: CLAIMS_HH / ENS_HH", None, exp["claims"], None, "bool", sp,
                            not_run_reason="no ICSA vintage for this date in F4; the bridge half is gated above"))
        rows.append(row(pre + "_h", S, f"{d}: deployed-form emulation would issue", r["legacy_form_issues"], d == "2025-11-20", None, "bool",
                        "v1 §1 row 5: the deployed engine returns None on 2025-12-16, 2026-01-09, 2026-02-06", {"reason": E.legacy_form_would_issue(st)[1]}))
        rows.append(row(pre + "_i", S, f"{d}: band", r["completed_target"]["band"], None, None, "info", "v1 §2.2 / §2.4",
                        {"basis": r["completed_target"]["band_basis"], "pattern_key": r["completed_target"]["pattern_key"],
                         "note": "'wide band' for the dropped-member case is asserted structurally in test_engine.py; the p10–p90 values come from the scored lag simulation"}))


def run_engine_f1(rows, diag, series):
    """v1 §7.2: the inverted stale-input test, partial-month invariance, lag-3 / lag-4 cases on F1."""
    S = "engine_F1"
    sp = "v1 §7.2 (test_gate_nowcast_bails_on_stale_bridge_inputs inverted; test_gate_partial_month_invariance kept)"
    base = E.issue(series, "2026-08-07")
    rows.append(row("X01", S, "F1 (2026-08-07, IS-A): v2 issue lags / IS / K", {"lags": base["lags"], "IS": base["info_set"], "K": base["K"]},
                    {"lags": {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 2}, "IS": "A", "K": "2026-05"}, 0, "exact", sp,
                    {"bridge_hh": r6(base["bridge_hh"]), "claims_hh": r6(base["claims_hh"]), "ens_hh": r6(base["ens_hh"]), "claims_fit": base["claims_fit"]}))
    stale3 = E.truncate_series(series, "2026-04", ["CMRMTSPL"])
    r3 = E.issue(stale3, "2026-08-07")
    rows.append(row("X02", S, "F1 with CMRMTSPL at lag 3: value with lags (bridged at L3, not None)",
                    {"lag": r3["lags"]["CMRMTSPL"], "bridged": r3["members_bridged"].get("CMRMTSPL"), "value": r3["bridge_hh"] is not None, "dropped": r3["dropped"]},
                    {"lag": 3, "bridged": 3, "value": True, "dropped": []}, 0, "exact", sp, {"bridge_hh": r6(r3["bridge_hh"]), "K": r3["K"]}))
    stale4 = E.truncate_series(series, "2026-03", ["CMRMTSPL"])
    r4 = E.issue(stale4, "2026-08-07")
    rows.append(row("X03", S, "F1 with CMRMTSPL at lag 4: dropped and re-meaned (value, flagged)",
                    {"lag": r4["lags"]["CMRMTSPL"], "dropped": r4["dropped"], "value": r4["bridge_hh"] is not None},
                    {"lag": 4, "dropped": ["CMRMTSPL"], "value": True}, 0, "exact", sp, {"bridge_hh": r6(r4["bridge_hh"]), "K": r4["K"]}))
    part = dict(series)
    part["ICSA"] = {m: v for m, v in series["ICSA"].items() if m < "2026-08"}
    part["T10Y3M"] = {m: v for m, v in series["T10Y3M"].items() if m < "2026-08"}
    rp = E.issue(part, "2026-08-07")
    rows.append(row("X04", S, "partial-month invariance: dropping the 2026-08 ICSA week / August T10Y3M days changes nothing",
                    [rp["bridge_hh"], rp["claims_hh"], rp["ens_hh"]] == [base["bridge_hh"], base["claims_hh"], base["ens_hh"]], True, None, "bool", sp))
    full = E.truncate_series(series, "2026-06")
    full["CMRMTSPL"] = dict(series["CMRMTSPL"])
    # all four members published for the last PAYEMS month -> None with reason
    all_published = {s: {m: v for m, v in d.items() if m <= "2026-05"} for s, d in series.items()}
    rn = E.issue(all_published, "2026-07-31")
    rows.append(row("X05", S, "all four members published for the last PAYEMS month → nowcast None with reason",
                    rn["nowcast"] is None and bool(rn["reason"]), True, None, "bool", "v1 §2.4", {"reason": rn["reason"], "target": rn["target_month"]}))


# ----------------------------------------------------------------------------
def run_all(write: bool = True, report_path: str = REPORT_PATH) -> dict:
    rows: list = []
    diag: dict = {}
    bc = deployed_module()
    ds, series, tg, rep, T, members, grid = run_f1(rows, diag)
    run_scoring_delta(rows, diag, ds, tg, rep, T)
    run_identity(rows, diag, ds)
    run_legacy(rows, diag, ds, series, bc)
    run_soft(rows, diag, ds, tg, rep)
    run_engine_f1(rows, diag, series)
    run_f3(rows, diag, bc)
    run_f4(rows, diag)
    counts = {"PASS": 0, "FAIL": 0, "INFO": 0, "NOT_RUN": 0}
    for r in rows:
        counts[r["status"]] += 1
    hard_fail = [r["id"] for r in rows if r["status"] == "FAIL" and not r.get("soft")]
    soft_fail = [r["id"] for r in rows if r["status"] == "FAIL" and r.get("soft")]
    fixtures = {"F1": {"path": os.path.relpath(F1_PATH, REPO), "sha256": sha256(F1_PATH)},
                "F3": {"dir": os.path.relpath(F3_DIR, REPO),
                       "sha256": {fn: sha256(os.path.join(F3_DIR, fn)) for fn in sorted(os.listdir(F3_DIR)) if fn.endswith(".csv")}},
                "F4": {"dir": os.path.relpath(F4_DIR, REPO),
                       "sha256": {fn: sha256(os.path.join(F4_DIR, fn)) for fn in sorted(os.listdir(F4_DIR)) if fn.endswith(".csv")}},
                "spec_json": {"path": os.path.relpath(SPEC_JSON, REPO), "sha256": sha256(SPEC_JSON)}}
    report = {
        "study": "cycle nowcast v2 — stage B1 gate report",
        "spec": "studies/cycle-nowcast-v2.md SPEC v1 §7.1 (reproduction gate, scoring-mode delta row), §2.3 identities, §7.2 engine gates (F3/F4)",
        "date": "2026-10-20",
        "scored": False,
        "scoring_statement": "No v2 metric (ENS_HH / CLAIMS_HH / completion-error band) was aggregated over the evaluation window on any fixture; the named gate rows above are the only metric computations.",
        "modes": {"reproduction": "bridge rows t < M; CLAIMS rows t ≤ M−1 incl. partial targets; selector errors through M−1",
                  "scoring": "bridge rows t ≤ M−L (D1); CLAIMS rows t ≤ K(d) and complete targets (D2/D6); selector errors through M−2 (D3)"},
        "fixtures": fixtures,
        "summary": {**counts, "n_rows": len(rows), "hard_fail_ids": hard_fail, "soft_fail_ids": soft_fail,
                    "deployed_module_imported": bc is not None},
        "rows": rows,
        "diagnostics": _py(diag),
    }
    if write:
        with open(report_path, "w") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)
    return report


if __name__ == "__main__":
    rep = run_all(write=True)
    s = rep["summary"]
    print(f"rows {s['n_rows']}: PASS {s['PASS']} FAIL {s['FAIL']} INFO {s['INFO']} NOT_RUN {s['NOT_RUN']}")
    print("hard FAIL:", s["hard_fail_ids"], " soft FAIL:", s["soft_fail_ids"])
    for r in rep["rows"]:
        if r["status"] == "FAIL":
            print(f"  {r['id']} {r['quantity']}: computed {r['computed']} target {r['target']} tol {r['tolerance']}")
    print("written:", REPORT_PATH)
