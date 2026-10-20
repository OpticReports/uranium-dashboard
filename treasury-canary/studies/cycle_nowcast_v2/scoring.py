"""Cycle nowcast v2 — study computations (SPEC v1 + v1.1) as pure functions over the
engine / metrics / pipeline outputs. Every reported quantity is a TAGGED record
{"tag": "DECISION" | "DESCRIPTIVE", "value", "basis", "n", "window", "spec"} (v1 §8:
"every column of every results table carries the tag").

THE GUARD (task B3, "no real number is scored"): every section takes a StudyInputs.
A StudyInputs with provenance "real" can be constructed ONLY after arm_real_run() has
accepted CNV2_SCORED_RUN=1 and a frozen freeze.json (run_study.py --real is the one
caller); a StudyInputs with provenance "synthetic" must carry the synthetic bundle's
manifest (marker + the sha256 of the F5 series it was generated with), re-verified on
every section call. Hand-built inputs over real series therefore raise RealDataGuard.

Sections (spec section in the docstring of each):
  section_windows          v1 §1 Windows: scored window, n
  section_lag_simulation   v0/v1 §3: per-IS walk-forward ENS_HH / BRIDGE_HH / CLAIMS_HH, three
                           persistence forms, completed COIN(M-1), metrics vs realized,
                           RMSE_A >= RMSE_B >= RMSE_C diagnostic, ENS_GRID_D3 (no-hindsight check)
  section_bands            v1 §2.2 / §2.4: per-pattern completion-error distributions, dropped-
                           member bands, walk-forward coverage; the D-2 inputs
  decide_d1 / d2 / d3      v1 §8 decisions with consequence text and leave-one-year-out ranges
  section_regime_i         v1 §4.1 / §4.3: true real-time replay at the dated issue points
  section_regime_ii        v1 §4.2: the lag simulation at list-proxy issue points (2000-01..2013-05)
  section_comparator       v1 §5: calibrated real-time ADS vs calibrated ENS_HH, sensitivities
  section_availability     v1 §3 (F15): days per month with a reading, deployed vs v2 vs ADS
  section_chauvet_piger    v1 §6: real-time release path, rules, declaration clocks, glitch flag
  section_honesty          v1 §7.3 / §9: F1-vs-F5 drift, ENS_HH on F1, shutdown counts, hashes,
                           recessions per regime, the D-3 calibration warm-up
numpy + the study modules only; no network; deterministic (no seeds).
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
import ads as A        # noqa: E402
import engine as E     # noqa: E402
import metrics as X    # noqa: E402
import piger as PG     # noqa: E402
import vintages as V   # noqa: E402

DECISION, DESCRIPTIVE = "DECISION", "DESCRIPTIVE"
SYNTHETIC_MARKER = "CNV2-SYNTHETIC-BUNDLE"
ENV_FLAG = "CNV2_SCORED_RUN"
PERS_NAME = "PERS = realized COIN(M-1) (v1 §1 F08)"
BAND_LABEL = "completion error only, final-vintage data; first-print revision not included (v1 §2.2)"
# regime (i) shutdown windows named by v1 §4.1 (month ranges); the synthetic bundle supplies its own
REAL_SHUTDOWN_WINDOWS = (("2013-10", "2013-10"), ("2018-12", "2019-02"), ("2025-10", "2026-01"))
AVAIL_SHUTDOWN_WINDOW = ("2025-10", "2026-04")          # v1 §3 availability table
REGIME_II_WINDOW = ("2000-01", "2013-05")
REGIME_I_START = "2013-06-14"
W875_OWN_DATES_FROM = "2010-05-28"                     # v1 §4.2: W875RX1's own dates from here
MIN_CAL_ROWS = 24                                      # v1 §5 calibration
SPEC_D3_EXPECTED_N_EX2020 = 145                        # v1 §8 D-3 power note: "n ≈ 145" ex-2020 at IS-A
# S1/D1 (fix pass): the calibration store as built. Both sides of the §5 comparison are calibrated on the
# STORED regime-(i) real-time readings at the same IS on identical rows (v1 §5 Symmetry), so the first
# calibrated reading comes >= 24 stored regime-(i) months after the first row — NOT ">= 2011 on the 2008-12+
# archive" (v1 §5). The spec's two clauses cannot both hold; Q16 was RULED by the spec owner (SPEC v1.2, 2026-10-20): the symmetric store stands, and the
# freeze must carry the answer before --real (validate_freeze).
CAL_STORE_IMPLEMENTED = "regime_i_stored_readings_symmetric_rows"
CAL_STORE_NOTE = ("calibration store = regime (i) stored real-time readings only (ADS_avg and ENS_HH at the same IS), "
                  "identical rows for both sides (v1 §5 Symmetry); the first calibrated reading therefore comes >= 24 stored "
                  "regime-(i) months after the first row at that IS, not '>= 2011 on the 2008-12+ archive' (v1 §5): the spec is "
                  "resolved by SPEC v1.2 (Q16 ruled: symmetric regime-(i) store; the ADS side is NOT seeded from the 2008-12+ archive) "
                  "at list-proxy IS points against vintage-consistent COIN(t), with a labelled pseudo ENS side")
TARGET_FIRST_READINGS = ("sign_of_r_minus_1", "same_outcome_class")   # Q17 (P1): v1 §8 D-3 "target_first must agree in sign"
DIAG_TOL = 1e-6                                        # numerical tie tolerance for RMSE_A >= RMSE_B >= RMSE_C
# patterns that can occur on the board (v1 §2.2 / §2.4): canonical targets and completions,
# the lag-3 variants and the dropped-member variants seen in F4; regime (i) adds what it meets
BOARD_PATTERNS = (
    {"CMRMTSPL": 1}, {"W875RX1": 1, "CMRMTSPL": 2}, {"INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 2},          # canonical A/B/C targets & completions
    {"CMRMTSPL": 2}, {"CMRMTSPL": 3}, {"W875RX1": 1, "CMRMTSPL": 3}, {"INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 3},   # lag-3 variants
    {"W875RX1": 2, "CMRMTSPL": 2}, {"INDPRO": 1, "W875RX1": 3, "CMRMTSPL": 3}, {"INDPRO": 2, "W875RX1": 2, "CMRMTSPL": 3},  # F4 2026-01-09 / 2025-12-16
    {"CMRMTSPL": 4}, {"INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 4}, {"INDPRO": 2, "W875RX1": 2, "CMRMTSPL": 4},     # dropped-member variants
)


# ----------------------------------------------------------------------------- guard
class RealDataGuard(RuntimeError):
    """Raised when a scoring function would touch real panels outside the single armed run."""


_ARM: dict = {"token": None}
FREEZE_REQUIRED = ("X_pct", "Y_pct", "regime_scope", "shutdown_rule", "fixture_policy",
                   "harness_status", "comparator_calibration_store", "target_first_agreement",
                   "status", "answered_by", "answered_on", "spec_version")
FREEZE_SUPPORTED = {"regime_scope": ("two_regimes_never_pooled", "regime_i_only"),
                    "shutdown_rule": ("drop_and_remean",),
                    "fixture_policy": ("gate_F1_score_F5_both_reported",),
                    "harness_status": ("not_retrievable",),
                    # Q16 (P1): only the symmetric regime-(i) store is implemented; the seeded-archive answer needs an
                    # engine change (a pseudo ENS side at list-proxy IS points 2008-12..2013-05) and a SPEC amendment
                    "comparator_calibration_store": (CAL_STORE_IMPLEMENTED,),
                    # Q17 (P1): both readings of "target_first must agree in sign" are implemented (decide_d3)
                    "target_first_agreement": TARGET_FIRST_READINGS}


class InputIntegrityError(RuntimeError):
    """A raw vintage read through as_of() does not match the hash-verified F6 vintage table."""


def validate_freeze(freeze: dict, require_frozen: bool) -> list[str]:
    """Problems with a freeze.json (empty list = acceptable). Unsupported answers name what
    must change before the run (an engine or spec amendment), never a silent default."""
    problems = []
    for k in FREEZE_REQUIRED:
        if k not in freeze:
            problems.append(f"missing field {k!r}")
    if problems:
        return problems
    try:
        x, y = float(freeze["X_pct"]), float(freeze["Y_pct"])
        if not (0 < x < y):
            problems.append(f"need 0 < X_pct < Y_pct, got X={x} Y={y}")
    except (TypeError, ValueError):
        problems.append("X_pct / Y_pct must be numbers")
    for k, ok in FREEZE_SUPPORTED.items():
        if freeze[k] not in ok:
            problems.append(f"{k}={freeze[k]!r} is not implemented by this harness (supported: {ok}); "
                            "a different answer needs an engine change and a SPEC amendment before the run")
    if require_frozen:
        if freeze["status"] != "FROZEN":
            problems.append(f"status must be 'FROZEN' for a scored run, got {freeze['status']!r}")
        if not str(freeze.get("answered_by", "")).strip():
            problems.append("answered_by is empty: the freeze must carry Casey's answers")
    return problems


def arm_real_run(freeze_path: str, env: dict | None = None) -> dict:
    """The ONLY way to make StudyInputs(provenance='real') constructible. Refuses unless
    CNV2_SCORED_RUN=1 is set in the environment AND freeze.json exists AND validates as FROZEN."""
    env = os.environ if env is None else env
    if env.get(ENV_FLAG) != "1":
        raise RealDataGuard(f"{ENV_FLAG}=1 is not set: the scored run is gated on Casey; nothing real is scored")
    if not freeze_path or not os.path.isfile(freeze_path):
        raise RealDataGuard(f"freeze.json with Casey's answers not found at {freeze_path!r}; the scored run is refused")
    with open(freeze_path) as f:
        freeze = json.load(f)
    problems = validate_freeze(freeze, require_frozen=True)
    if problems:
        raise RealDataGuard("freeze.json is not a valid frozen answer set: " + "; ".join(problems))
    tok = {"freeze_path": os.path.abspath(freeze_path), "freeze_sha256": sha256_file(freeze_path)}
    _ARM["token"] = tok
    return tok


def disarm() -> None:
    _ARM["token"] = None


def armed() -> bool:
    return _ARM["token"] is not None


def series_hash(series: dict) -> str:
    """sha256 of the canonical JSON of a {series: {month: value}} dict (the bundle identity)."""
    canon = json.dumps({s: {m: float(v) for m, v in sorted(d.items())} for s, d in sorted(series.items())},
                       sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class StudyInputs:
    """Everything a section may read. provenance 'real' needs arm_real_run(); 'synthetic'
    needs manifest = {'synthetic_marker': SYNTHETIC_MARKER, 'bundle_sha256': series_hash(f5)}."""

    def __init__(self, provenance: str, f5: dict, *, manifest: dict | None = None, freeze: dict | None = None,
                 f5_daily: dict | None = None, f1: dict | None = None, as_of=None, issue_rows=None,
                 issue_dates_rows=None, vintage_table=None, vintage_lists=None, ads_panel=None,
                 ads_matrix=None, piger_releases=None, piger_alfred=None, nber=None, unrevised=None,
                 hashes=None, shutdown_windows=None, regime_i_start: str | None = None,
                 regime_ii_window=None, labels=None):
        if provenance not in ("real", "synthetic"):
            raise ValueError(provenance)
        self.provenance = provenance
        self.manifest = manifest or {}
        self.f5 = f5
        self._verify(construct=True)
        self.freeze = freeze or {}
        self.f5_daily = f5_daily or {}
        self.f1 = f1
        self.as_of = as_of
        self.issue_rows = list(issue_rows or [])
        self.issue_dates_rows = list(issue_dates_rows or [])
        self.vintage_table = list(vintage_table or [])
        self.vintage_lists = dict(vintage_lists or {})
        self.ads_panel = list(ads_panel or [])
        self.ads_matrix = ads_matrix
        self.piger_releases = list(piger_releases or [])
        self.piger_alfred = piger_alfred
        self.nber = nber or {}
        self.unrevised = list(unrevised or [])
        self.hashes = hashes or {}
        self.shutdown_windows = tuple(shutdown_windows) if shutdown_windows else REAL_SHUTDOWN_WINDOWS
        self.regime_i_start = regime_i_start or REGIME_I_START
        self.regime_ii_window = tuple(regime_ii_window) if regime_ii_window else REGIME_II_WINDOW
        self.labels = labels or {}
        self._ds5 = None
        self._cache: dict = {}

    def _verify(self, construct: bool = False) -> None:
        if self.provenance == "real":
            if not armed():
                raise RealDataGuard("StudyInputs(provenance='real') outside an armed scored run: "
                                    "real panels are never scored in this stage")
            return
        m = self.manifest
        if m.get("synthetic_marker") != SYNTHETIC_MARKER:
            raise RealDataGuard("synthetic inputs without the synthetic bundle marker")
        if m.get("bundle_sha256") != series_hash(self.f5):
            raise RealDataGuard("synthetic manifest hash does not match the series handed to scoring "
                                "(these are not the series synthetic.py generated)")

    @property
    def ds5(self) -> E.Dataset:
        self._verify()
        if self._ds5 is None:
            self._ds5 = E.build(self.f5)
        return self._ds5


def _check(inp: StudyInputs) -> None:
    if not isinstance(inp, StudyInputs):
        raise RealDataGuard("scoring sections take a StudyInputs, never raw panels")
    inp._verify()


# ----------------------------------------------------------------------------- tagging / json
def _py(v):
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


def T(value, tag: str, basis: str, n=None, window=None, spec: str = "") -> dict:
    """A tagged record (v1 §8). value may be a scalar, list or dict of plain numbers."""
    if tag not in (DECISION, DESCRIPTIVE):
        raise ValueError(tag)
    return {"tag": tag, "value": _py(value), "basis": basis, "n": _py(n), "window": _py(window), "spec": spec}


def D(value, basis, n=None, window=None, spec=""):
    return T(value, DESCRIPTIVE, basis, n, window, spec)


def r6(x):
    return None if x is None or not math.isfinite(float(x)) else round(float(x), 6)


def _month_in_windows(m: str, windows) -> bool:
    return any(lo <= m <= hi for lo, hi in windows)


def _state_from_asof(inp: StudyInputs, d: str) -> tuple[dict, dict]:
    """The series as known at d (v1 §4.1): replay members and ICSA from the latest listed
    vintage <= d; T10Y3M / BAA10YM / GS10 / TB3MS taken current (F5 daily or monthly rows)
    restricted to observation dates <= d. Returns (monthly state, vintage record per series)."""
    key = ("state", d)
    if key in inp._cache:
        return inp._cache[key]
    vin = inp.as_of(d)
    vt = _vt_lookup(inp)
    state, used = {}, {}
    for sid, rec in vin.items():
        if rec is None:
            continue
        # M4 (fix pass): the bytes as_of() read must be the hash-verified F6 row for (series, vintage date);
        # a --cache directory is otherwise unverified
        exp = vt.get((sid, rec["vintage_date"]))
        if exp is None or exp != rec["sha256"]:
            raise InputIntegrityError(f"raw vintage {sid} {rec['vintage_date']} read at d={d}: sha256 {rec['sha256'][:16]}... "
                                      f"{'is not in' if exp is None else 'differs from'} the verified F6 vintage table"
                                      + (f" ({exp[:16]}...)" if exp else ""))
        state[sid] = E.monthly_from_pairs(rec["obs"], "mean" if sid in E.MEAN_COLLAPSE else "last")
        used[sid] = {"vintage_date": rec["vintage_date"], "sha256": rec["sha256"], "last_obs_month": rec["last_obs_month"],
                     "f6_verified": True}
    for sid in ("T10Y3M", "BAA10YM", "GS10", "TB3MS"):
        if sid in inp.f5_daily:
            if sid in E.MEAN_COLLAPSE:
                # daily rate: observation dates <= d (the month of d is a partial mean, beyond the PAYEMS axis)
                pairs = [(dd, v) for dd, v in inp.f5_daily[sid] if dd <= d]
                rule = "observation dates <= d (daily; the month of d is a partial-month mean, beyond the PAYEMS axis)"
            else:
                # D7 (fix pass): a monthly average dated the 1st is unknown inside its month; admit months strictly
                # before the month of d (changes no number: the PAYEMS axis ends before the month of d)
                pairs = [(dd, v) for dd, v in inp.f5_daily[sid] if dd[:7] < d[:7]]
                rule = "monthly averages of months strictly before the month of d (a full-month mean is unknown inside its month)"
            state[sid] = E.monthly_from_pairs(pairs, "mean" if sid in E.MEAN_COLLAPSE else "last")
            used[sid] = {"vintage_date": "current", "basis": f"unrevised, taken current (v1 §4.1); {rule}"}
    inp._cache[key] = (state, used)
    return state, used


def _vt_lookup(inp: StudyInputs) -> dict:
    """{(series, vintage date): sha256} from the hash-verified F6 vintage table (M4)."""
    key = ("vt_lookup",)
    if key not in inp._cache:
        if not inp.vintage_table:
            raise InputIntegrityError("no F6 vintage table: raw vintages cannot be verified")
        inp._cache[key] = {(r["series"], r["vintage_date"]): r["sha256"] for r in inp.vintage_table}
    return inp._cache[key]


def _dm_descriptive(dm: dict) -> dict:
    """A DM record for a DESCRIPTIVE table: t / n / mean_d / se / p-values only, no pass or kill verdict (M7)."""
    return {k: v for k, v in dm.items() if k not in ("primary_pass_cand_better", "kill_cand_worse")}


# ----------------------------------------------------------------------------- windows (v1 §1)
def section_windows(inp: StudyInputs) -> dict:
    """v1 §1 Windows: scored window = 1972-01..the last month in which all four members are
    published in F5; n reported; the F1 reproduction window stays 1972-01..2026-06."""
    _check(inp)
    ds = inp.ds5
    hi = E.scored_window_end(ds)
    targets = E.eval_targets(ds, ("1972-01", hi))
    months = [ds.months[i] for i in targets]
    out = {"scored_window": D([months[0], months[-1]], "1972-01..last complete COIN month on F5", len(months), [months[0], months[-1]], "v1 §1 Windows"),
           "n_targets": D(len(months), "targets with COIN(M) and COIN(M-1) finite", len(months), [months[0], months[-1]], "v1 §1"),
           "n_1990plus": D(int(X.since_mask(months, "1990-01").sum()), "targets 1990-01+", None, None, "v0 §1"),
           "n_ex2020": D(int(X.ex2020_mask(months).sum()), "targets ex 2020-01..2020-12 (gap closed)", None, None, "v1 §1"),
           "first_coin_month": D(ds.months[int(np.flatnonzero(np.isfinite(ds.coin))[0])], "first COIN month on F5 (1959 start, 120 warm-up)", None, None, "v0 §1"),
           "last_payems_month": D(ds.months[-1], "last PAYEMS month in F5", None, None, "v0 §1"),
           "onsets": D(E.onsets_from_usrec(ds), "NBER onsets from USREC in F5, 1972-01+", None, None, "v0 §1 A6"),
           "_targets": targets, "_months": months, "_hi": hi}
    return out


# ----------------------------------------------------------------------------- lag simulation (v0/v1 §3)
def _metrics_vs_realized(months, y, p_real, yhat, onsets, pers_e=None):
    """The §3 metric block for one series vs realized COIN(M); PERS = realized COIN(M-1)."""
    e = yhat - y
    ep = (p_real - y) if pers_e is None else pers_e
    # N3 (fix pass): one common finite mask for the candidate and PERS, so every RMSE ratio is on the same rows
    # (PERS is finite on every target by eval_targets' construction, so the candidate's rows decide)
    m = np.isfinite(e) & np.isfinite(ep)
    ex, p90 = X.ex2020_mask(months) & m, X.since_mask(months, "1990-01") & m
    ot = X.onset_table(months, y, yhat, onsets)
    return {"rmse": X.rmse(e, m), "rmse_1990": X.rmse(e, p90), "rmse_ex2020": X.rmse(e, ex),
            "rmse_2020_only": X.rmse(e, m & ~X.ex2020_mask(months)), "n": int(m.sum()),
            "n_common_rows": int(m.sum()), "n_common_ex2020": int(ex.sum()),
            "pct_vs_pers": X.pct_change(X.rmse(e, m), X.rmse(ep, m)),
            "pct_vs_pers_1990": X.pct_change(X.rmse(e, p90), X.rmse(ep, p90)),
            "pct_vs_pers_ex2020": X.pct_change(X.rmse(e, ex), X.rmse(ep, ex)),
            "directional": X.directional_accuracy(yhat, y, p_real),
            "phase": X.phase_accuracy(yhat, y),
            "transitions": X.transition_accuracy(yhat, y, p_real),
            "transitions_1990": X.transition_accuracy(yhat, y, p_real, p90),
            "dm_vs_pers": X.dm_test(e, ep), "dm_vs_pers_ex2020": X.dm_test(e, ep, mask=ex),
            "onsets": ot, "false_alarms": X.false_alarms(months, y, yhat),
            "loyo_vs_pers": X.loyo_ratio(e, ep, months, m), "loyo_vs_pers_ex2020": X.loyo_ratio(e, ep, months, ex)}


def section_lag_simulation(inp: StudyInputs, win: dict) -> dict:
    """v0 §3 / v1 §3 on F5, scoring_mode, claims form 'hh': for each canonical pattern the
    walk-forward ENS_HH / BRIDGE_HH / CLAIMS_HH, the three persistence forms (D5), the
    completed COIN(M-1); metrics vs realized COIN(M) with PERS = realized COIN(M-1); the
    RMSE_A >= RMSE_B >= RMSE_C diagnostic on the full / 1990+ / ex-2020 aggregates (v1 §3);
    ENS_GRID_D3 at IS-A / IS-B (v1 §1 F21, no-hindsight check, DESCRIPTIVE)."""
    _check(inp)
    ds, targets, months = inp.ds5, win["_targets"], win["_months"]
    onsets = E.onsets_from_usrec(ds)
    W = [months[0], months[-1]]
    sims, per_is = {}, {}
    for IS in ("A", "B", "C"):
        sim = E.simulate(ds, E.PATTERNS[IS], "scoring", targets, "hh", window=("1972-01", win["_hi"]))
        sims[IS] = sim
        y, p = sim["y"], sim["pers_real"]
        block = {}
        for name, arr in (("ENS_HH", sim["ens"]), ("BRIDGE_HH", sim["bridge"]), ("CLAIMS_HH", sim["claims"])):
            block[name] = _metrics_vs_realized(months, y, p, arr, onsets)
        # completion error of COIN_HH(M-1 | IS) vs realized COIN(M-1) (the headline band's source)
        ec = p - sim["comp_prev"]
        ex = X.ex2020_mask(months)
        block["completion_prev"] = {"rmse": X.rmse(ec), "rmse_ex2020": X.rmse(ec, ex),
                                    "band_all": X.band_percentiles(ec), "n": int(np.isfinite(ec).sum()),
                                    "pattern": sim["prev_pattern"]}
        # BASELINES (descriptive): available-members and HH-completed persistence vs realized
        block["baselines"] = {"PERS_realized": {"rmse": X.rmse(p - y), "rmse_ex2020": X.rmse(p - y, ex)},
                              "PERS_available": {"rmse": X.rmse(sim["pers_avail"] - y), "rmse_ex2020": X.rmse(sim["pers_avail"] - y, ex),
                                                 "n": int(np.isfinite(sim["pers_avail"]).sum())},
                              "PERS_HH": {"rmse": X.rmse(sim["pers_hh"] - y), "rmse_ex2020": X.rmse(sim["pers_hh"] - y, ex)}}
        block["claims_fallback_months"] = int(sim["claims_status"].count("fallback"))
        block["claims_n_last"] = int(sim["claims_n"][-1])
        block["pattern_keys_target"] = sorted({f["key"] for f in sim["bridge_flags"]})
        per_is[IS] = block
    # diagnostic (v1 §3): RMSE_A >= RMSE_B >= RMSE_C on the aggregates only
    diag = {}
    for agg in ("rmse", "rmse_1990", "rmse_ex2020"):
        a, b, c = (per_is[k]["ENS_HH"][agg] for k in "ABC")
        diag[agg] = {"A": a, "B": b, "C": c, "holds": bool(a + DIAG_TOL >= b and b + DIAG_TOL >= c), "tie_tolerance": DIAG_TOL}
    diag_holds = all(v["holds"] for v in diag.values())
    # ENS_GRID_D3 (v1 §1 F21 / DT-22): reported, selector errors through M-2; member forms per notes_B1 N
    grid = {}
    y = sims["A"]["y"]
    for IS in ("A", "B"):
        mem = E.ens_grid_d3_members(ds, targets, inp.f5, IS)
        g = E.ens_grid(mem, y, selector_lag=2, warmup=24, default="pers")
        e = g["forecast"] - y
        grid[IS] = {"rmse": X.rmse(e), "rmse_1990": X.rmse(e, X.since_mask(months, "1990-01")),
                    "rmse_ex2020": X.rmse(e, X.ex2020_mask(months)), "n_selected": g["n_selected"],
                    "count_5050_bridge_claims": g["count_by_label"].get("0.5*BRIDGE+0.5*CLAIMS", 0),
                    "top_combos": sorted(g["count_by_label"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]}
    out = {"basis": D({"mode": "scoring", "claims_form": "hh", "data": inp.labels.get("f5", "F5"), "patterns": E.PATTERNS},
                      "final-vintage data; historical publication calendars not modelled (v1 §3 honesty)", len(months), W, "v0 §3 / v1 §3"),
           "per_is": {}, "diagnostic_rmse_A_ge_B_ge_C": T({"aggregates": diag, "holds": diag_holds},
                                                          DESCRIPTIVE, "ENS_HH RMSE on full / 1990+ / ex-2020 aggregates; a violation halts the read-out (bug hunt), neither pass nor fail",
                                                          len(months), W, "v1 §3 (F11, F15)"),
           "ens_grid_d3": D(grid, "ENS_GRID_D3: members PERS_HH / AR2_HH / LEADREG_HH / BRIDGE_HH / CLAIMS_HH (forms confirmed, SPEC v1.2), selector errors through M-2, 24 warm-up, PERS before selection", len(months), W, "v1 §1 F21 / DT-22"),
           "_sims": sims, "_diag_holds": diag_holds}
    for IS, block in per_is.items():
        sec = {}
        for name in ("ENS_HH", "BRIDGE_HH", "CLAIMS_HH"):
            b = block[name]
            tag = DECISION if (IS == "A" and name == "ENS_HH") else DESCRIPTIVE
            sec[name] = {
                "rmse_full_1990_ex2020": T([b["rmse"], b["rmse_1990"], b["rmse_ex2020"]], tag, f"population RMSE vs realized COIN(M) on the rows where the candidate and PERS are both finite; 2020-only {r6(b['rmse_2020_only'])}", b["n"], W, "v0 §3"),
                "pct_vs_pers_full_1990_ex2020": T([b["pct_vs_pers"], b["pct_vs_pers_1990"], b["pct_vs_pers_ex2020"]], tag, f"100*(RMSE/RMSE_PERS - 1) on one common finite mask (n {b['n_common_rows']} full, {b['n_common_ex2020']} ex-2020); {PERS_NAME}", b["n"], W, "v1 §8 D-1" if tag == DECISION else "v1 §8 secondary"),
                "dm_vs_pers_t_full_ex2020": T([b["dm_vs_pers"]["t"], b["dm_vs_pers_ex2020"]["t"]], tag, "DM NW-6 Bartlett, d = e_cand^2 - e_PERS^2, negative = better; primary two-sided |t| >= 1.645", [b["dm_vs_pers"]["n"], b["dm_vs_pers_ex2020"]["n"]], W, "v1 §1 F08"),
                "loyo_ratio_full": D(b["loyo_vs_pers"], "leave-one-calendar-year-out RMSE ratio vs PERS", b["n"], W, "v1 §8"),
                "loyo_ratio_ex2020": D(b["loyo_vs_pers_ex2020"], "leave-one-calendar-year-out RMSE ratio vs PERS, ex-2020", None, W, "v1 §8"),
                "directional_pct": D(b["directional"]["accuracy_pct"], f"sign(yhat - COIN_real(M-1)) == sign(COIN_real(M) - COIN_real(M-1)); ties wrong ({b['directional']['ties']})", b["directional"]["n"], W, "v1 §1 A8/F07"),
                "phase_pct": D(b["phase"]["accuracy_pct"], "3-phase label match", b["phase"]["n"], W, "v0 §1"),
                "transitions_called_of_realized": D([b["transitions"]["hits"], b["transitions"]["n_transitions"]], f"realized transitions; 1990+ {b['transitions_1990']['hits']}/{b['transitions_1990']['n_transitions']}; secondary bar >= 20%", b["transitions"]["n_transitions"], W, "v1 §8 secondary"),
                "transitions_pct": D(b["transitions"]["accuracy_pct"], "share of realized transitions called", b["transitions"]["n_transitions"], W, "v1 §8 secondary"),
                "onsets": D({"summary": b["onsets"]["summary"], "rows": b["onsets"]["rows"]}, "window [onset-6, onset+12], calendar advantage (m_c - m_n) + 1; missed = no nowcast crossing", len(b["onsets"]["rows"]), W, "v0 §1 A6"),
                "false_alarms": D(b["false_alarms"], "nowcast < -0.75 with no realized < -0.75 within +/-3 calendar months", len(b["false_alarms"]), W, "v0 §3"),
                "claims_fallback_months": D(block["claims_fallback_months"], "targets where the CLAIMS_HH fit had < 24 rows or undefined features (regressor in hand used)", None, W, "notes_B1 E"),
            }
        c = block["completion_prev"]
        sec["completed_COIN_prev"] = {
            "rmse_vs_realized_full_ex2020": D([c["rmse"], c["rmse_ex2020"]], f"COIN_HH(M-1 | {c['pattern']}) vs realized COIN(M-1); IS-C secondary bar < 0.126 is vacuous on identity rows (F02)", c["n"], W, "v1 §2.2 / §8 secondary"),
            "band_p10_p50_p90_all": D(c["band_all"], "percentiles of e = realized - completed over the scored window (all months; the board bands are in section bands)", c["n"], W, "v1 §2.2")}
        sec["baselines_descriptive"] = D(block["baselines"], "BASELINES table: realized / available-members / HH-completed persistence vs realized COIN(M); enter no criterion", None, W, "v1 §1 F08 / v0 §2.3 D5")
        sec["pattern_keys_seen"] = D(block["pattern_keys_target"], "bridged-pattern keys of the target month under this IS (skip rule keys 1977-06/07)", None, W, "v1 §2.2")
        sec["claims_n_last_target"] = D(block["claims_n_last"], "CLAIMS_HH training rows at the last target (rows t <= K = M - max lag)", None, W, "v1 §2.3 D2")
        out["per_is"][IS] = sec
    return out


# ----------------------------------------------------------------------------- bands (v1 §2.2 / §2.4) and D-2 inputs
def _band_windows(months):
    ex = X.ex2020_mask(months)
    m90 = X.since_mask(months, "1990-01")
    m77 = X.since_mask(months, "1977-07")
    return {"primary_1990_ex2020": m90 & ex, "sens_1977_ex2020": m77 & ex, "sens_1990_with2020": m90, "sens_1977_with2020": m77}


def _pattern_errors(ds, pattern, mode="scoring"):
    """e(m) = realized COIN(m) - COIN_HH(m | pattern) for every month, with the pattern key per month."""
    n = ds.n
    e = np.full(n, np.nan)
    keys = [None] * n
    nb = np.zeros(n, int)
    for i in range(n):
        if not np.isfinite(ds.coin[i]) or not ds.complete[i]:
            continue
        cm = E.complete_month(ds, i, pattern, mode)
        keys[i] = cm["pattern_key"]
        nb[i] = len(cm["bridged"]) + len(cm["dropped"])
        e[i] = ds.coin[i] - cm["value"]
    return e, keys, nb


def section_bands(inp: StudyInputs, win: dict, extra_patterns=()) -> dict:
    """v1 §2.2 (F03, F12, DT-19) and §2.4: for every board pattern the distribution of
    e = realized - COIN_HH(P) keyed by the pattern key actually bridged/dropped in that month.
    PRIMARY band: targets 1990-01+ ex-2020 where >= 1 member is bridged (bridged patterns),
    1977-07+ ex-2020 for a dropped set (v1 §2.4); the other windows are sensitivities. Also the
    walk-forward (expanding) coverage of the p10-p90 band and the D-2 inputs."""
    _check(inp)
    ds = inp.ds5
    hi = win["_hi"]
    months = ds.months
    in_win = np.array([m <= hi for m in months], bool)
    wins = {k: v & in_win for k, v in _band_windows(months).items()}
    pats = list(BOARD_PATTERNS) + [p for p in extra_patterns if p not in BOARD_PATTERNS]
    table, seen = {}, set()
    for pat in pats:
        key_req = tuple(sorted(pat.items()))
        if key_req in seen:
            continue
        seen.add(key_req)
        e, keys, nb = _pattern_errors(ds, pat)
        for key in sorted({k for k in keys if k}):
            sel = np.array([k == key for k in keys], bool) & (nb > 0)
            if not sel.any() or key in table:
                continue
            dropped = key.split("|dropped[")[1].split("]")[0] != ""
            prim = "sens_1977_ex2020" if dropped else "primary_1990_ex2020"
            entry = {"requested_pattern": pat, "primary_window": prim, "dropped_set": dropped,
                     "basis": BAND_LABEL}
            for wname, mask in wins.items():
                entry[wname] = X.band_percentiles(e, (10, 50, 90), sel & mask)
            # walk-forward coverage (DT-19): band from errors dated before the point, 1990+ ex-2020
            cover, nn = 0, 0
            for i in np.flatnonzero(sel & wins["primary_1990_ex2020"]):
                b = X.expanding_band(months, e, months[i], (10, 90), sel & wins[prim])
                if b is None:
                    continue
                nn += 1
                cover += int(b["p10"] <= e[i] <= b["p90"])
            entry["walk_forward_coverage_1990_ex2020"] = {"covered": cover, "n": nn, "share": (cover / nn) if nn else None}
            table[key] = entry
    # board dict in the engine's band_lookup form (p10/p90 from the primary window)
    board = {k: {"p10": v[v["primary_window"]]["p10"], "p90": v[v["primary_window"]]["p90"],
                 "n": v[v["primary_window"]]["n"], "basis": f"{BAND_LABEL}; window {v['primary_window']}"}
             for k, v in table.items() if v[v["primary_window"]].get("n", 0) >= MIN_CAL_ROWS}
    # D-2 inputs (v1 §8): 1-bridged completion vs the partial 3-member mean on the SAME months 1977-07+
    e1, keys1, nb1 = _pattern_errors(ds, {"CMRMTSPL": 1})
    partial = np.array([ds.available_mean(i, ("PAYEMS", "INDPRO", "W875RX1")) for i in range(ds.n)])
    ep = ds.coin - partial
    k1 = E.pattern_key({"CMRMTSPL": 1})
    m77 = X.since_mask(months, "1977-07") & in_win & np.array([k == k1 for k in keys1], bool) & np.isfinite(e1) & np.isfinite(ep)
    d2 = {"months_mask": m77, "months": [m for m, ok in zip(months, m77) if ok], "e_completed": e1, "e_partial": ep}
    out = {"basis": D({"label": BAND_LABEL, "windows": list(wins), "n_patterns": len(table)},
                      "per-pattern error distributions e = realized - COIN_HH(P), keyed by the bridged/dropped pattern of the month", None, ["1977-07", hi], "v1 §2.2 / §2.4"),
           "patterns": {k: D(v, f"{'dropped-member band (v1 §2.4)' if v['dropped_set'] else 'completion band (v1 §2.2)'}; PRIMARY = {v['primary_window']}",
                             v[v["primary_window"]].get("n"), None, "v1 §2.2 / §2.4") for k, v in table.items()},
           "board_bands": D(board, "the dict engine.issue(bands=...) consumes: p10/p90 of the PRIMARY window per pattern key (patterns with >= 24 errors)", len(board), None, "v1 §2.2"),
           "_d2": d2, "_board": board}
    return out


# ----------------------------------------------------------------------------- decisions (v1 §8)
def decide_d1(lag: dict, win: dict) -> dict:
    """D-1 primary: IS-A ENS_HH RMSE <= -25% vs PERS full AND <= -8% ex-2020 AND DM ex-2020
    <= -1.645 (conjunction). Consequence text per v1 §8."""
    simA = lag["_sims"]["A"]
    months, y, p = simA["months"], simA["y"], simA["pers_real"]
    e, ep = simA["ens"] - y, p - y
    m = np.isfinite(e) & np.isfinite(ep)                  # N3: one common finite mask for both RMSEs
    ex = X.ex2020_mask(months) & m
    pct_full = X.pct_change(X.rmse(e, m), X.rmse(ep, m))
    pct_ex = X.pct_change(X.rmse(e, ex), X.rmse(ep, ex))
    dm = X.dm_test(e, ep, mask=ex)
    c1, c2, c3 = bool(pct_full <= -25.0), bool(pct_ex <= -8.0), bool(np.isfinite(dm["t"]) and dm["t"] <= -X.DM_TWO_SIDED_10PCT)
    outcome = "PASS" if (c1 and c2 and c3) else "FAIL"
    missed = [name for ok, name in ((c1, "full-sample -25%"), (c2, "ex-2020 -8%"), (c3, "DM ex-2020 <= -1.645")) if not ok]
    cons = {"PASS": "ENS_HH at the IS in force is the one-month-ahead reading on the board with the v2 numbers in its stats block.",
            "FAIL": "The v2 engine still ships for availability (no better candidate exists; the deployed fixed-lag gate is strictly worse); the panel text drops the August accuracy claim and shows the v2 numbers with the missed bar named: "
                    + ", ".join(missed) + ". No re-tuning, no alternative ensemble is tried in this study."}[outcome]
    W = [months[0], months[-1]]
    return {"outcome": T(outcome, DECISION, "conjunction of the three conditions", int(ex.sum()), W, "v1 §8 D-1"),
            "conditions": T({"rmse_pct_vs_pers_full": pct_full, "bar_full": -25.0, "pass_full": c1,
                             "rmse_pct_vs_pers_ex2020": pct_ex, "bar_ex2020": -8.0, "pass_ex2020": c2,
                             "dm_t_ex2020": dm["t"], "bar_dm": -X.DM_TWO_SIDED_10PCT, "pass_dm": c3, "dm_n": dm["n"],
                             "n_common_rows": int(m.sum()), "n_common_ex2020": int(ex.sum())},
                            DECISION, f"IS-A, scoring_mode, {PERS_NAME}; RMSE_ENS and RMSE_PERS on one common finite mask", len(months), W, "v1 §8 D-1"),
            "loyo_full": D(X.loyo_ratio(e, ep, months, m), "leave-one-calendar-year-out RMSE ratio ENS_HH/PERS", len(months), W, "v1 §8"),
            "loyo_ex2020": D(X.loyo_ratio(e, ep, months, ex), "leave-one-calendar-year-out RMSE ratio ENS_HH/PERS, ex-2020", int(ex.sum()), W, "v1 §8"),
            "consequence": T(cons, DECISION, "pre-registered consequence text", None, W, "v1 §8 D-1"),
            "missed_bars": D(missed, "bars not met (empty on PASS)", len(missed), W, "v1 §8 D-1")}


def decide_d2(bands: dict, win: dict) -> dict:
    """D-2: on 1977-07+ months where the 1-bridged completion bridges CMRMTSPL at L1, RMSE of
    (realized - COIN_HH) < RMSE of (realized - partial 3-member mean), full AND ex-2020."""
    d2 = bands["_d2"]
    months = d2["months"]
    mk = d2["months_mask"]
    ec, ep = d2["e_completed"][mk], d2["e_partial"][mk]
    ex = X.ex2020_mask(months)
    rc, rp = X.rmse(ec), X.rmse(ep)
    rcx, rpx = X.rmse(ec, ex), X.rmse(ep, ex)
    ok_full, ok_ex = bool(rc < rp), bool(rcx < rpx)
    outcome = "PASS" if (ok_full and ok_ex) else "FAIL"
    cons = {"PASS": "coincident_completed is shown as the headline value with its band (Q6 default keeps the partial as the gate/alert quantity).",
            "FAIL": "The completed value is shown as a secondary line; the partial mean stays the headline."}[outcome]
    W = [months[0], months[-1]] if months else None
    return {"outcome": T(outcome, DECISION, "completed RMSE < partial RMSE on the same months, full AND ex-2020", len(months), W, "v1 §8 D-2"),
            "rmse": T({"completed_full": rc, "partial_full": rp, "completed_ex2020": rcx, "partial_ex2020": rpx,
                       "pass_full": ok_full, "pass_ex2020": ok_ex, "ratio_full": rc / rp if rp else None, "ratio_ex2020": rcx / rpx if rpx else None},
                      DECISION, "1-bridged completion [PAYEMS, INDPRO, W875RX1 actual; CMRMTSPL L1] vs partial 3-member mean; the QA gap 0.126 is context only", len(months), W, "v1 §8 D-2"),
            "distribution_completed": D(X.band_percentiles(ec), "p10/p50/p90, bias, RMSE of realized - completed", len(months), W, "v1 §8 D-2"),
            "distribution_partial": D(X.band_percentiles(ep), "p10/p50/p90, bias, RMSE of realized - partial 3-member mean", len(months), W, "v1 §8 D-2"),
            "distribution_completed_ex2020": D(X.band_percentiles(ec, mask=ex), "ex-2020", int(ex.sum()), W, "v1 §8 D-2"),
            "distribution_partial_ex2020": D(X.band_percentiles(ep, mask=ex), "ex-2020", int(ex.sum()), W, "v1 §8 D-2"),
            "loyo_ratio_full": D(X.loyo_ratio(ec, ep, months), "leave-one-year-out RMSE ratio completed/partial", len(months), W, "v1 §8"),
            "loyo_ratio_ex2020": D(X.loyo_ratio(ec, ep, months, ex), "leave-one-year-out RMSE ratio completed/partial, ex-2020", int(ex.sum()), W, "v1 §8"),
            "consequence": T(cons, DECISION, "pre-registered consequence text", None, W, "v1 §8 D-2")}


# ----------------------------------------------------------------------------- regime (i): true real-time replay (v1 §4.1, §4.3)
def _vstar_map(inp: StudyInputs) -> dict:
    """v*(M) = max over the four members of the first vintage date containing M (v1 §4.3 a)."""
    fc = {}
    for r in inp.issue_dates_rows:
        if r["series"] in E.COIN_MEMBERS and r.get("first_vintage_containing"):
            fc[(r["series"], r["month"])] = r["first_vintage_containing"]
    out = {}
    for M in sorted({m for _, m in fc}):
        dates = [fc.get((c, M)) for c in E.COIN_MEMBERS]
        if all(dates):
            out[M] = max(dates)
    return out


def _target_first(inp: StudyInputs, M: str, vstar: dict) -> dict:
    key = ("tf", M)
    if key in inp._cache:
        return inp._cache[key]
    d = vstar.get(M)
    res = {"month": M, "vintage_date": d, "value": None, "complete": False, "n_members": 0}
    if d is not None:
        state, used = _state_from_asof(inp, d)
        if all(state.get(c) for c in E.COIN_MEMBERS):
            ds = E.build(state)
            i = ds.idx.get(M)
            if i is not None and np.isfinite(ds.coin[i]):
                res.update({"value": float(ds.coin[i]) if ds.complete[i] else None, "complete": bool(ds.complete[i]),
                            "n_members": int(ds.nmem[i]), "vintages": {s: u.get("vintage_date") for s, u in used.items() if s in E.COIN_MEMBERS}})
    inp._cache[key] = res
    return res


def _regime_i_rows(inp: StudyInputs) -> list:
    rows = [r for r in inp.issue_rows if r.get("row_kind") in ("nowcast", "completion") and r["issue_date"] >= inp.regime_i_start]
    order = {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 2}
    rows.sort(key=lambda r: (r["issue_date"], order.get(r.get("trigger"), 9), r.get("trigger_month", "")))
    return rows


def section_regime_i(inp: StudyInputs, win: dict) -> dict:
    """v1 §4.1 / §4.3: at every dated issue point (nowcast and completion rows of the issue
    panel), EVERYTHING from the vintages in hand (axis, z histories, bridge fits, CLAIMS_HH
    training targets t <= K(d), persistence). The only objects carried across issue dates
    are the stored completions COIN_HH(t-1 | IS) at t's own issue date (D4); months without
    a stored value use the canonical-lag completion recomputed walk-forward on the vintage
    in hand at d ('spliced history'). Targets: target_first(M) from the vintage v*(M),
    target_latest(M) from F5. Per-IS scorecards with lag-pattern and shutdown flags."""
    _check(inp)
    if inp.as_of is None or not inp.issue_rows:
        return {"status": D("not run: no issue panel / as_of provider", "regime (i) needs the F6 panel", None, None, "v1 §4.1")}
    ds5 = inp.ds5
    vstar = _vstar_map(inp)
    store = {"A": {}, "B": {}, "C": {}}
    store_src = {"A": {}, "B": {}, "C": {}}
    scorecards, completions, mismatches, skipped = [], [], [], []
    for row in _regime_i_rows(inp):
        d, kind = row["issue_date"], row["row_kind"]
        state, used = _state_from_asof(inp, d)
        if not all(state.get(c) for c in E.COIN_MEMBERS):
            # D5 (fix pass): a bare reason row never enters the per-IS arrays; reported separately
            skipped.append({"issue_date": d, "IS": row.get("IS"), "row_kind": kind, "trigger": row.get("trigger"),
                            "reason": "a member has no vintage <= d", "missing": [c for c in E.COIN_MEMBERS if not state.get(c)]})
            continue
        ds = E.build(state)
        st = E.information_state(ds)
        IS = st["IS"]
        if IS != row.get("IS"):
            mismatches.append({"issue_date": d, "panel_IS": row.get("IS"), "engine_IS": IS})
        hist = E.coin_hh_history(ds, E.PREV_PATTERNS[IS], "scoring")
        spliced = {ds.months[j]: float(hist[j]) for j in np.flatnonzero(np.isfinite(hist))}
        n_recomputed = len(spliced)
        n_stored = 0
        for m, v in store[IS].items():
            if m in ds.idx:
                spliced[m] = v
                n_stored += 1
        r = E.issue(state, d, "scoring", stored_completions={IS: spliced})
        M = r["target_month"]
        cp, ct = r["completed_prev"], r["completed_target"]
        rec = {"issue_date": d, "trigger": row.get("trigger"), "trigger_month": row.get("trigger_month"), "row_kind": kind,
               "IS": IS, "M": M, "K": r["K"], "lags": r["lags"], "dropped": r["dropped"],
               "members_bridged": r["members_bridged"], "members_skipped": r["members_skipped"],
               "pattern_key_target": ct["pattern_key"] if ct else None,
               "pattern_key_prev": cp["pattern_key"] if cp else None,
               "flags": {"lag_ge3": r["flags"].get("lag_ge3", []), "dropped": bool(r["dropped"]),
                         "is_c_cmrmtspl_lag2": bool(r["flags"].get("is_c_cmrmtspl_lag2")),
                         "nonstandard_prev_pattern": bool(cp and cp.get("nonstandard_pattern")),
                         "canonical": r["lags"] == {"PAYEMS": 0, **E.PATTERNS[IS]},
                         "in_shutdown_window": _month_in_windows(d[:7], inp.shutdown_windows),
                         "w875_ahead_of_indpro": bool(r["flags"].get("w875_ahead_of_indpro"))},
               "bridge_hh": r["bridge_hh"], "claims_hh": r["claims_hh"], "ens_hh": r["ens_hh"], "phase": r["phase"],
               "reason": r["reason"], "claims_reason": r["claims_reason"],
               "completed_prev": {"month": cp["month"], "value": cp["value"], "pattern": cp["pattern"], "dropped": cp["dropped"]} if cp else None,
               "completed_target": {"month": ct["month"], "value": ct["value"], "pattern": ct["pattern"], "dropped": ct["dropped"]} if ct else None,
               "persistence_in_hand": r["persistence"],
               "claims_fit": {k: r["claims_fit"][k] for k in ("n", "rows", "rows_through")} if r["claims_fit"] else None,
               "regressor_history": {"basis": "spliced history (v1 §4.1): stored per-issue-date completions where they exist, canonical-lag completions recomputed walk-forward on the vintage in hand otherwise",
                                     "n_stored_used": n_stored, "n_recomputed": n_recomputed - n_stored},
               "vintages": {s: u.get("vintage_date") for s, u in used.items()},
               "legacy_form_issues": r["legacy_form_issues"]}
        if kind == "nowcast":
            if cp and cp["value"] is not None and cp["month"] not in store[IS]:
                store[IS][cp["month"]] = float(cp["value"])
                store_src[IS][cp["month"]] = d
            tf = _target_first(inp, M, vstar)
            i5 = ds5.idx.get(M)
            tl = float(ds5.coin[i5]) if (i5 is not None and ds5.complete[i5] and np.isfinite(ds5.coin[i5])) else None
            ip = ds5.idx.get(E.madd(M, -1))
            pl = float(ds5.coin[ip]) if (ip is not None and ds5.complete[ip] and np.isfinite(ds5.coin[ip])) else None
            rec.update({"target_first": tf["value"], "target_first_vintage": tf["vintage_date"], "target_first_complete": tf["complete"],
                        "target_latest": tl, "pers_realized_latest": pl,
                        "err_latest": (r["ens_hh"] - tl) if (r["ens_hh"] is not None and tl is not None) else None,
                        "err_first": (r["ens_hh"] - tf["value"]) if (r["ens_hh"] is not None and tf["value"] is not None) else None,
                        "_coin_in_hand": {ds.months[j]: float(ds.coin[j]) for j in np.flatnonzero(ds.complete & np.isfinite(ds.coin)) if j <= st["K_i"]}})
            scorecards.append(rec)
        else:
            completions.append(rec)
    # per-IS metrics (DESCRIPTIVE: reported, no pass/fail — one recession)
    onsets = [o for o in E.onsets_from_usrec(ds5) if o >= inp.regime_i_start[:7]]
    per_is = {}
    for IS in ("A", "B", "C"):
        rs = [s for s in scorecards if s.get("IS") == IS and s.get("row_kind") == "nowcast"]
        months = [s["M"] for s in rs]
        ens = np.array([np.nan if s["ens_hh"] is None else s["ens_hh"] for s in rs], float)
        bridge = np.array([np.nan if s["bridge_hh"] is None else s["bridge_hh"] for s in rs], float)
        claims = np.array([np.nan if s["claims_hh"] is None else s["claims_hh"] for s in rs], float)
        tl = np.array([np.nan if s["target_latest"] is None else s["target_latest"] for s in rs], float)
        tf = np.array([np.nan if s["target_first"] is None else s["target_first"] for s in rs], float)
        pl = np.array([np.nan if s["pers_realized_latest"] is None else s["pers_realized_latest"] for s in rs], float)
        ex = X.ex2020_mask(months) if months else np.zeros(0, bool)
        blk = {"n_rows": len(rs), "n_scored_latest": int(np.isfinite(ens - tl).sum()), "n_scored_first": int(np.isfinite(ens - tf).sum()),
               "months_first_last": [months[0], months[-1]] if months else None,
               "rmse_vs_latest": {"ENS_HH": X.rmse(ens - tl), "BRIDGE_HH": X.rmse(bridge - tl), "CLAIMS_HH": X.rmse(claims - tl), "PERS_realized_latest": X.rmse(pl - tl)},
               "rmse_vs_latest_ex2020": {"ENS_HH": X.rmse(ens - tl, ex), "BRIDGE_HH": X.rmse(bridge - tl, ex), "CLAIMS_HH": X.rmse(claims - tl, ex), "PERS_realized_latest": X.rmse(pl - tl, ex)},
               "rmse_vs_first": {"ENS_HH": X.rmse(ens - tf), "BRIDGE_HH": X.rmse(bridge - tf), "CLAIMS_HH": X.rmse(claims - tf)},
               "rmse_vs_first_ex2020": {"ENS_HH": X.rmse(ens - tf, ex)},
               "pct_vs_pers_latest": {"full": X.pct_change(X.rmse(ens - tl), X.rmse(pl - tl)), "ex2020": X.pct_change(X.rmse(ens - tl, ex), X.rmse(pl - tl, ex))},
               "dm_vs_pers_latest": {"full": _dm_descriptive(X.dm_test(ens - tl, pl - tl)), "ex2020": _dm_descriptive(X.dm_test(ens - tl, pl - tl, mask=ex))},
               "directional_vs_latest": X.directional_accuracy(ens, tl, pl) if months else None,
               "phase_vs_latest": X.phase_accuracy(ens, tl) if months else None,
               "onsets_vs_latest": X.onset_table(months, tl, ens, onsets) if months else None,
               "false_alarms_vs_latest": X.false_alarms(months, tl, ens) if months else [],
               "flag_counts": {"lag_ge3": sum(1 for s in rs if s["flags"]["lag_ge3"]), "dropped": sum(1 for s in rs if s["flags"]["dropped"]),
                               "is_c_cmrmtspl_lag2": sum(1 for s in rs if s["flags"]["is_c_cmrmtspl_lag2"]),
                               "nonstandard_prev_pattern": sum(1 for s in rs if s["flags"]["nonstandard_prev_pattern"]),
                               "non_canonical": sum(1 for s in rs if not s["flags"]["canonical"]),
                               "in_shutdown_window": sum(1 for s in rs if s["flags"]["in_shutdown_window"]),
                               "no_nowcast": sum(1 for s in rs if s["ens_hh"] is None)},
               "lag_pattern_frequency": _count(["|".join(f"{c}:{s['lags'][c]}" for c in E.COIN_MEMBERS) for s in rs]),
               "store": {"n_stored": len(store[IS]), "first": min(store[IS]) if store[IS] else None, "last": max(store[IS]) if store[IS] else None},
               "ens_crossing_date": next((s["issue_date"] for s in rs if s["ens_hh"] is not None and s["ens_hh"] < E.COIN_RECESSION), None)}
        per_is[IS] = blk
    W = [inp.regime_i_start, scorecards[-1]["issue_date"] if scorecards else None]
    out = {"basis": D({"regime": "(i) true real-time", "start": inp.regime_i_start, "n_issue_points": len(scorecards) + len(completions),
                       "n_nowcast_rows": len(scorecards), "n_completion_rows": len(completions), "shutdown_windows": list(inp.shutdown_windows),
                       "unrevised_taken_current": ["T10Y3M", "BAA10YM", "GS10", "TB3MS"], "is_label_mismatches_panel_vs_engine": mismatches,
                       "rows_skipped_no_vintage": skipped, "n_rows_skipped_no_vintage": len(skipped),
                       "raw_vintages_verified_against_f6_table": True},
                      "every quantity from the vintages dated <= d; stored completions (D4) spliced with walk-forward recomputation; "
                      "rows whose members have no vintage <= d are skipped and listed, never scored", len(scorecards), W, "v1 §4.1 / §4.3"),
           "per_is": {IS: D(blk, "regime (i) per-IS scorecard summary; reported, no pass/fail (one recession). PERS_realized_latest = F5 COIN(M-1): "
                                 "the FINAL-VINTAGE (hindsight) persistence baseline in the F08 form, not a real-time quantity; the in-hand "
                                 "persistence forms are in each scorecard row (persistence_in_hand). DM records carry t / p only, no verdict (M7)",
                            blk["n_rows"], W, "v1 §8 real-time / v1 §4.1") for IS, blk in per_is.items()},
           "scorecards": D([{k: v for k, v in s.items() if not k.startswith("_")} for s in scorecards], "one row per (issue date, IS) nowcast; target_first = COIN(M) from the vintage v*(M), target_latest = COIN(M) on F5", len(scorecards), W, "v1 §4.3"),
           "completions": D(completions, "trigger-month != M rows: COIN_HH(M-1) completion table (never a second nowcast row)", len(completions), W, "v1 §4.3 / notes_B2"),
           "stores": D({IS: {m: {"value": v, "issue_date": store_src[IS][m]} for m, v in sorted(store[IS].items())} for IS in store},
                       "stored per-issue-date completions COIN_HH(t-1 | IS) (D4)", sum(len(v) for v in store.values()), W, "v1 §2.3 D4 / §4.1"),
           "target_first_vintages": D({M: vstar[M] for M in sorted(vstar) if any(s.get("M") == M for s in scorecards)}, "v*(M) = max over members of the first vintage containing M", None, W, "v1 §4.3 (a)"),
           "_scorecards": scorecards, "_store": store}
    return out


def _count(items) -> dict:
    out: dict = {}
    for k in items:
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


# ----------------------------------------------------------------------------- regime (ii): the lag simulation at dated issue points (v1 §4.2)
def section_regime_ii(inp: StudyInputs, lag: dict, win: dict) -> dict:
    """v1 §4.2: the §3 lag simulation (canonical patterns, final-vintage data) evaluated at
    ACTUAL issue dates taken from the vintage LISTS only (vintages.list_proxy_issue_dates):
    IS-A PAYEMS, IS-B INDPRO, IS-C BEA PI as the PI&O-day proxy, W875RX1's own dates from
    2010-05-28. Used only to align the ADS (2009-01+), Chauvet-Piger and NBER-announcement
    comparisons; never pooled with regime (i)."""
    _check(inp)
    if inp.freeze.get("regime_scope") == "regime_i_only":
        return {"status": D("not run: freeze regime_scope = regime_i_only (Q2)", "Casey's answer", None, None, "v1 §4.2 / Q2")}
    lo, hi = inp.regime_ii_window
    sims = lag["_sims"]
    idx = {m: k for k, m in enumerate(sims["A"]["months"])}
    months = [m for m in sims["A"]["months"] if lo <= m <= hi]
    L = inp.vintage_lists
    pts = {"A": V.list_proxy_issue_dates(L.get("PAYEMS", []), months, "PAYEMS"),
           "B": V.list_proxy_issue_dates(L.get("INDPRO", []), months, "INDPRO")}
    pi = V.list_proxy_issue_dates(L.get(V.PI_SERIES, []), months, V.PI_SERIES)
    w8 = V.list_proxy_issue_dates(L.get("W875RX1", []), months, "W875RX1")
    pts["C"], src_c = {}, {}
    for M in months:
        # W875RX1's own dates only for months whose PI&O day (in M+1) falls on/after the list's first
        # entry (2010-05-28 = the April-2010 release): earlier months would otherwise snap to it
        if w8.get(M) and w8[M] >= W875_OWN_DATES_FROM and E.madd(M, 1) >= W875_OWN_DATES_FROM[:7]:
            pts["C"][M], src_c[M] = w8[M], "W875RX1 list"
        else:
            pts["C"][M], src_c[M] = pi.get(M), "PI list (PI&O-day proxy)"
    tables = {}
    for IS in ("A", "B", "C"):
        sim = sims[IS]
        rows = []
        for M in months:
            k = idx[M]
            rows.append({"M": M, "issue_date": pts[IS][M], "source": (src_c[M] if IS == "C" else {"A": "PAYEMS list", "B": "INDPRO list"}[IS]) + " (list-only proxy)",
                         "ens_hh": r6(sim["ens"][k]), "bridge_hh": r6(sim["bridge"][k]), "claims_hh": r6(sim["claims"][k]),
                         "realized": r6(sim["y"][k]), "pers_real": r6(sim["pers_real"][k]), "completed_prev": r6(sim["comp_prev"][k])})
        tables[IS] = rows
    # crossings on the calendar-date clock (v1 §6): realized -0.75 crossing of m_c dated by the
    # IS-C point of m_c + 1 (the PI&O release that carried CMRMTSPL(m_c)); ENS_HH crossing of m_n
    # (IS-A) dated by the payrolls day of m_n + 1 = the IS-A point of target m_n
    ds5 = inp.ds5
    onsets = [o for o in E.onsets_from_usrec(ds5) if lo <= o <= hi]
    simA = sims["A"]
    otA = X.onset_table(simA["months"], simA["y"], simA["ens"], onsets)
    cross = []
    for r in otA["rows"]:
        mc, mn = r["realized_cross"], r["nowcast_cross"]
        cross.append({"onset": r["onset"], "realized_cross_month": mc,
                      "realized_cross_date": pts["C"].get(E.madd(mc, 1)) if mc else None,
                      "realized_cross_date_basis": "IS-C point (list proxy) of m_c + 1: the release that first printed COIN(m_c) in full",
                      "ens_hh_cross_month_IS_A": mn, "ens_hh_cross_date": pts["A"].get(mn) if mn else None,
                      "ens_hh_cross_date_basis": "IS-A point (list proxy) of m_n: payrolls day of m_n + 1",
                      "calendar_advantage_months": r["calendar_advantage_months"], "class": r["class"], "regime": "(ii) pseudo-real-time, labelled"})
    # ADS alignment 2009-01+ (ADS true real-time, v2 pseudo): the ADS_avg(M | d_A(M)) reading only
    ads_rows = []
    if inp.ads_panel:
        for M in months:
            d = pts["A"].get(M)
            if M < "2009-01" or not d:
                continue
            a = A.ads_avg(inp.ads_panel, M, d)
            if a and a.get("value") is not None:
                ads_rows.append({"M": M, "issue_date": d, "ads_avg": a["value"], "ads_vintage": a["vintage_date"], "complete": a["complete"],
                                 "ens_hh": r6(simA["ens"][idx[M]]), "realized": r6(simA["y"][idx[M]])})
    corr = None
    if len(ads_rows) >= 3:
        aa = np.array([[r["ads_avg"], r["realized"]] for r in ads_rows], float)
        corr = float(np.corrcoef(aa[:, 0], aa[:, 1])[0, 1])
    W = [months[0], months[-1]] if months else list(inp.regime_ii_window)
    missing = {IS: [M for M in months if pts[IS].get(M) is None] for IS in pts}
    # M1 (fix pass): the proxy's evidence — list-proxy dates vs the content-decided F6 issue dates (status 'issue') per
    # trigger series over the regime-(i) months where both exist; every mismatch listed with both dates
    content = {}
    for r in inp.issue_dates_rows:
        if r.get("status") == "issue" and r.get("series") in ("PAYEMS", "INDPRO", "W875RX1") and r.get("issue_date"):
            content.setdefault(r["series"], {})[r["month"]] = r["issue_date"]
    agreement = {}
    for sid in ("PAYEMS", "INDPRO", "W875RX1"):
        ms = sorted(m for m in content.get(sid, {}) if m >= inp.regime_i_start[:7])
        px = V.list_proxy_issue_dates(L.get(sid, []), ms, sid) if (ms and L.get(sid)) else {}
        mism = [{"M": m, "content_decided": content[sid][m], "list_proxy": px.get(m)} for m in ms if px.get(m) != content[sid][m]]
        agreement[sid] = {"n_months": len(ms), "n_agree": len(ms) - len(mism), "n_mismatch": len(mism), "mismatches": mism[:60],
                          "window": [ms[0], ms[-1]] if ms else None, "list_present": bool(L.get(sid))}
    return {"basis": D({"regime": "(ii) pseudo-real-time", "window": W, "issue_points": "vintage lists only (content not consulted) — list-only proxy",
                        "rules": V.LIST_PROXY_MIN_DAY, "proxy_window": "earliest listed d with <M+1>-<min_day> <= d <= <M+3>-01",
                        "n_months": len(months), "months_without_point": missing,
                        "lists_present": {k: len(v) for k, v in L.items()},
                        "list_proxy_vs_content_decided_regime_i_months": agreement},
                       "the §3 simulation with dated issue points; never pooled with regime (i); labelled pseudo. The list-proxy's evidence is the "
                       "agreement table against the content-decided F6 issue dates over the regime-(i) months (M1)", len(months), W, "v1 §4.2 / §4.3"),
            "tables": {IS: D(rows, f"IS-{IS} rows: lag-simulation values at the dated point", len(rows), W, "v1 §4.2") for IS, rows in tables.items()},
            "crossings_calendar_clock": D(cross, "realized and ENS_HH -0.75 crossings dated on the calendar clock (pseudo-real-time)", len(cross), W, "v1 §6"),
            "ads_alignment_2009plus": D({"rows": ads_rows, "corr_ads_avg_vs_realized": corr, "n": len(ads_rows)}, "ADS_avg(M | d_A(M)) at the IS-A points, ADS true real-time, v2 pseudo (raw readings, no calibration)", len(ads_rows), W, "v1 §5 Months"),
            "_points": pts, "_months": months}


# ----------------------------------------------------------------------------- comparator: calibrated real-time ADS (v1 §5)
COMPARATOR_VARIANTS = ("primary", "strict_lt_d", "excl_claims_only", "smoothed_fit")


def _ads_matrix_avg(matrix: dict, col_index: int, month: str):
    """Monthly average of `month` in the vintage at matrix column col_index (1-based, the
    panel's col_index) from the F7 monthly sum/count matrix; None when absent."""
    if matrix is None:
        return None
    mi = matrix["_midx"].get(month)
    j = int(col_index) - 1
    if mi is None or j < 0 or j >= matrix["sums"].shape[1]:
        return None
    c = matrix["counts"][mi, j]
    return float(matrix["sums"][mi, j] / c) if c > 0 else None


def _affine_fit(xs, ys):
    x, y = np.asarray(xs, float), np.asarray(ys, float)
    b = E.ols(x[:, None], y)
    return float(b[0]), float(b[1])


def section_comparator(inp: StudyInputs, reg1: dict, variant: str = "primary") -> dict:
    """v1 §5 (F06, DT-3, DT-6, DT-18, DT-21). Readings: ADS_avg(M | d) (THE comparator reading)
    and ADS_last(d) (descriptive) from the latest archived vintage dated <= d (same-day
    included; variant 'strict_lt_d' = the '< d' sensitivity). Calibration PRIMARY: at each
    (d, IS) the vintage-consistent COIN(t) (from the state at d, complete rows) regressed on
    the STORED real-time reading issued for t at the same IS, rows t <= K(d), >= 24 rows;
    the IDENTICAL affine step on the same rows applied to ENS_HH (stored values). Variant
    'smoothed_fit' regresses on the issue-date vintage's own monthly averages instead
    ('smoothed-fit, filtered-apply'); variant 'excl_claims_only' drops rows whose ADS vintage
    is a claims-only update from the accuracy comparison. Metrics on the intersection of
    months where both sides have a calibrated reading."""
    _check(inp)
    if variant not in COMPARATOR_VARIANTS:
        raise ValueError(variant)
    cards = [s for s in reg1.get("_scorecards", []) if s.get("row_kind") == "nowcast" and s.get("M")]
    if not inp.ads_panel or not cards:
        return {"status": D("not run: no ADS panel or no regime (i) scorecards", "", None, None, "v1 §5")}
    if variant == "smoothed_fit" and inp.ads_matrix is None:
        return {"status": D("NOT_RUN: the F7 monthly sum/count matrix (ads_monthly_matrix.npz, outside git) was not supplied", "pass --ads-matrix to run the smoothed-fit sensitivity", None, None, "v1 §5 SENSITIVITY")}
    strict = variant == "strict_lt_d"
    panel = inp.ads_panel
    stored_ads = {"A": {}, "B": {}, "C": {}}
    stored_last = {"A": {}, "B": {}, "C": {}}
    stored_ens = {"A": {}, "B": {}, "C": {}}
    stored_smooth_src = {"A": {}, "B": {}, "C": {}}
    rows = []
    for s in cards:
        d, IS, M, K = s["issue_date"], s["IS"], s["M"], s["K"]
        a = A.ads_avg(panel, M, d, strict)
        last = A.ads_last(panel, d, strict)
        a_val = a["value"] if a else None
        rec = {"issue_date": d, "IS": IS, "M": M, "K": K, "ads_vintage": a["vintage_date"] if a else None,
               "ads_avg": a_val, "ads_avg_n_days": a.get("n_days") if a else None, "ads_avg_complete": a.get("complete") if a else None,
               "ads_claims_only": bool(a and a.get("claims_only")), "ads_shutdown_partial": bool(a and a.get("shutdown_partial")),
               "ads_last": last["value"] if last else None, "ads_last_date": last["last_date"] if last else None,
               "ens_hh": s["ens_hh"], "target_latest": s["target_latest"], "target_first": s["target_first"]}
        if a_val is not None and M not in stored_ads[IS]:
            stored_ads[IS][M] = a_val
        if last and last["value"] is not None and M not in stored_last[IS]:
            stored_last[IS][M] = last["value"]
        if s["ens_hh"] is not None and M not in stored_ens[IS]:
            stored_ens[IS][M] = s["ens_hh"]
        coin = s["_coin_in_hand"]
        # calibration rows: same t for both sides (stored ADS reading AND stored ENS, t <= K, COIN(t) complete in the vintage at d)
        if variant == "smoothed_fit":
            v = A.select_vintage(panel, d, strict)
            ts = [t for t in stored_ens[IS] if t <= K and t in coin and _ads_matrix_avg(inp.ads_matrix, v["col_index"], t) is not None] if v else []
            xa = [_ads_matrix_avg(inp.ads_matrix, v["col_index"], t) for t in ts]
        else:
            ts = [t for t in stored_ads[IS] if t <= K and t in coin and t in stored_ens[IS]]
            xa = [stored_ads[IS][t] for t in ts]
        ts = sorted(ts)
        if variant == "smoothed_fit":
            xa = [_ads_matrix_avg(inp.ads_matrix, v["col_index"], t) for t in ts]
        else:
            xa = [stored_ads[IS][t] for t in ts]
        xe = [stored_ens[IS][t] for t in ts]
        yy = [coin[t] for t in ts]
        rec.update({"cal_n": len(ts), "cal_rows_through": ts[-1] if ts else None})
        if len(ts) >= MIN_CAL_ROWS and a_val is not None and s["ens_hh"] is not None:
            a0, a1 = _affine_fit(xa, yy)
            e0, e1 = _affine_fit(xe, yy)
            rec.update({"ads_cal": a0 + a1 * a_val, "ads_cal_coef": [a0, a1], "ens_cal": e0 + e1 * s["ens_hh"], "ens_cal_coef": [e0, e1]})
        else:
            rec.update({"ads_cal": None, "ads_cal_coef": None, "ens_cal": None, "ens_cal_coef": None,
                        "no_cal_reason": "fewer than 24 calibration rows" if len(ts) < MIN_CAL_ROWS else "reading or ENS_HH missing"})
        tl = [t for t in stored_last[IS] if t <= K and t in coin]
        if len(tl) >= MIN_CAL_ROWS and rec["ads_last"] is not None:
            l0, l1 = _affine_fit([stored_last[IS][t] for t in tl], [coin[t] for t in tl])
            rec["ads_last_cal"] = l0 + l1 * rec["ads_last"]
        else:
            rec["ads_last_cal"] = None
        rows.append(rec)
    per_is = {}
    for IS in ("A", "B", "C"):
        all_is = [r for r in rows if r["IS"] == IS]
        rs = [r for r in all_is if r["ads_cal"] is not None and r["ens_cal"] is not None and r["target_latest"] is not None]
        if variant == "excl_claims_only":
            rs = [r for r in rs if not r["ads_claims_only"]]
        months = [r["M"] for r in rs]
        # S1/D1 (fix pass): the calibration warm-up, stated per IS
        first_cal = next((r["M"] for r in all_is if r["ads_cal"] is not None and r["ens_cal"] is not None), None)
        warm = {"first_row_month": all_is[0]["M"] if all_is else None, "first_calibrated_month": first_cal,
                "n_rows_at_is": len(all_is), "n_rows_without_calibration": sum(1 for r in all_is if r["ads_cal"] is None or r["ens_cal"] is None),
                "calibration_store": CAL_STORE_IMPLEMENTED, "spec_expected_n_ex2020": SPEC_D3_EXPECTED_N_EX2020 if IS == "A" else None}
        tl = np.array([r["target_latest"] for r in rs], float)
        tf = np.array([np.nan if r["target_first"] is None else r["target_first"] for r in rs], float)
        ca = np.array([r["ads_cal"] for r in rs], float)
        ce = np.array([r["ens_cal"] for r in rs], float)
        raw = np.array([r["ens_hh"] for r in rs], float)
        ex = X.ex2020_mask(months) if months else np.zeros(0, bool)
        blk = {"n_intersection": len(rs), "months_first_last": [months[0], months[-1]] if months else None,
               "n_ex2020": int(ex.sum()), "n_claims_only_rows_in_intersection": sum(1 for r in rs if r["ads_claims_only"]), **warm}
        if len(rs) >= 3:
            eA, eE, eR = ca - tl, ce - tl, raw - tl
            blk.update({"rmse_ens_cal": {"ex2020": X.rmse(eE, ex), "with2020": X.rmse(eE)},
                        "rmse_ads_cal": {"ex2020": X.rmse(eA, ex), "with2020": X.rmse(eA)},
                        "rmse_ens_raw": {"ex2020": X.rmse(eR, ex), "with2020": X.rmse(eR)},
                        "r_ens_over_ads": {"ex2020": X.rmse(eE, ex) / X.rmse(eA, ex) if X.rmse(eA, ex) > 0 else None,
                                           "with2020": X.rmse(eE) / X.rmse(eA) if X.rmse(eA) > 0 else None},
                        "loyo_r_ex2020": X.loyo_ratio(eE, eA, months, ex) if ex.sum() >= 3 and X.rmse(eA, ex) > 0 else None,
                        "dm_one_sided_ens_worse": {"ex2020": _dm_descriptive(X.dm_test(eE, eA, mask=ex)), "with2020": _dm_descriptive(X.dm_test(eE, eA))},
                        "vs_target_first": {"rmse_ens_cal_ex2020": X.rmse(ce - tf, ex & np.isfinite(tf)), "rmse_ads_cal_ex2020": X.rmse(ca - tf, ex & np.isfinite(tf)),
                                            "r_ex2020": (X.rmse(ce - tf, ex) / X.rmse(ca - tf, ex)) if X.rmse(ca - tf, ex) > 0 else None,
                                            "n": int(np.isfinite(ce - tf).sum()),
                                            "dm_one_sided_ens_worse_ex2020": _dm_descriptive(X.dm_test(ce - tf, ca - tf, mask=ex))},
                        "onset_timing": {"onsets": X.onset_table(months, tl, ce, [o for o in E.onsets_from_usrec(inp.ds5) if o >= inp.regime_i_start[:7]])["rows"],
                                         "ens_cal_cross_date": next((r["issue_date"] for r in rs if r["ens_cal"] < E.COIN_RECESSION), None),
                                         "ads_cal_cross_date": next((r["issue_date"] for r in rs if r["ads_cal"] < E.COIN_RECESSION), None)},
                        "ads_last_cal_rmse_ex2020": X.rmse(np.array([np.nan if r["ads_last_cal"] is None else r["ads_last_cal"] for r in rs], float) - tl, ex),
                        "mean_cal_coef_ads": [float(np.mean([r["ads_cal_coef"][0] for r in rs])), float(np.mean([r["ads_cal_coef"][1] for r in rs]))],
                        "last_cal_coef_ads": rs[-1]["ads_cal_coef"], "last_cal_coef_ens": rs[-1]["ens_cal_coef"], "last_cal_n": rs[-1]["cal_n"]})
        per_is[IS] = blk
    W = [cards[0]["issue_date"], cards[-1]["issue_date"]]
    label = {"primary": "PRIMARY: ADS_avg(M | d), vintage <= d (same day included), calibration on stored real-time readings",
             "strict_lt_d": "SENSITIVITY: ADS vintage dated < d",
             "excl_claims_only": "SENSITIVITY: ADS claims-only vintages excluded from the accuracy comparison",
             "smoothed_fit": "SENSITIVITY: smoothed-fit (in-vintage monthly averages), filtered-apply"}[variant]
    return {"basis": D({"variant": variant, "label": label, "min_rows": MIN_CAL_ROWS, "n_rows": len(rows),
                        "n_with_calibration": sum(1 for r in rows if r["ads_cal"] is not None),
                        "n_claims_only_readings": sum(1 for r in rows if r["ads_claims_only"]),
                        "calibration_store": CAL_STORE_IMPLEMENTED,
                        "calibration_warmup_per_is": {IS: {k: blk.get(k) for k in ("first_row_month", "first_calibrated_month", "n_rows_at_is", "n_rows_without_calibration", "n_intersection", "n_ex2020")} for IS, blk in per_is.items()},
                        "ads_post_2023_09_28_regime": "ADS parameters re-estimated excluding COVID from 2023-09-28 (stated; pre-2023 end-points untouched)"},
                       "calibrated-vs-calibrated; raw ENS_HH also reported. " + CAL_STORE_NOTE, len(rows), W, "v1 §5"),
            "per_is": {IS: D(blk, f"IS-{IS}: intersection months with both calibrated readings; ex-2020 decisive, with-2020 reported; "
                                  f"first calibrated month {blk.get('first_calibrated_month')} after {blk.get('n_rows_without_calibration')} regime-(i) rows "
                                  f"without a calibrated reading (warm-up, {CAL_STORE_IMPLEMENTED}); DM records carry t / p only, no verdict",
                             blk["n_intersection"], W, "v1 §5 / §8 D-3") for IS, blk in per_is.items()},
            "rows": D(rows, "per (issue date, IS): readings, calibration coefficients, calibrated values", len(rows), W, "v1 §5"),
            "_per_is": per_is, "_variant": variant}


def _d3_class(r, X_pct: float, Y_pct: float, kill_dm: bool):
    """The D-3 outcome class of a ratio under the pre-registered thresholds (None when r is undefined)."""
    if r is None or not np.isfinite(r):
        return None
    if r <= 1.0 + X_pct / 100.0:
        return "SUCCESS"
    if r > 1.0 + Y_pct / 100.0 and kill_dm:
        return "KILL"
    return "MIDDLE"


def _kill_dm(dm: dict) -> bool:
    """One-sided DM verdict recomputed here from t (the DESCRIPTIVE tables carry no verdict, M7)."""
    t = (dm or {}).get("t")
    return bool(t is not None and np.isfinite(t) and t >= X.DM_ONE_SIDED_10PCT)


def decide_d3(comp: dict, freeze: dict) -> dict:
    """D-3 (v1 §8): IS-A, regime (i), target_latest PRIMARY, ADS_avg calibrated vs ENS_HH calibrated,
    ex-2020 decisive. r = RMSE_ENS / RMSE_ADS. SUCCESS r <= 1 + X/100; KILL r > 1 + Y/100 AND one-sided
    DM (H1 mean d > 0, NW-6, p < 0.10); MIDDLE otherwise. X, Y from freeze.json (Q1).
    "target_first must agree ... or the decision is deferred": the reading comes from the freeze
    (Q17): 'sign_of_r_minus_1' (sign(r_first - 1) == sign(r_latest - 1)) or 'same_outcome_class'
    (the class under r_first with the same thresholds equals the class under r_latest); the reading
    used, both classes and the calibration warm-up (S1/D1) are recorded in the outcome basis."""
    X_pct, Y_pct = float(freeze["X_pct"]), float(freeze["Y_pct"])
    reading = freeze.get("target_first_agreement", TARGET_FIRST_READINGS[0])
    if reading not in TARGET_FIRST_READINGS:
        raise ValueError(f"target_first_agreement={reading!r}")
    blk = comp.get("_per_is", {}).get("A", {})
    r = (blk.get("r_ens_over_ads") or {}).get("ex2020")
    n = blk.get("n_ex2020", 0)
    dm = (blk.get("dm_one_sided_ens_worse") or {}).get("ex2020", {}) or {}
    vf = blk.get("vs_target_first") or {}
    rf = vf.get("r_ex2020")
    rf_ok = rf is not None and np.isfinite(rf)
    r_ok = r is not None and np.isfinite(r)
    kill_dm = _kill_dm(dm)
    cls_latest = _d3_class(r, X_pct, Y_pct, kill_dm)
    cls_first = _d3_class(rf, X_pct, Y_pct, _kill_dm(vf.get("dm_one_sided_ens_worse_ex2020"))) if rf_ok else None
    W = blk.get("months_first_last")
    warm = {k: blk.get(k) for k in ("first_row_month", "first_calibrated_month", "n_rows_at_is", "n_rows_without_calibration",
                                    "n_intersection", "n_ex2020", "spec_expected_n_ex2020", "calibration_store")}
    warm_txt = (f"calibration warm-up (S1/D1): first IS-A row {warm['first_row_month']}, first calibrated reading {warm['first_calibrated_month']}, "
                f"{warm['n_rows_without_calibration']} regime-(i) IS-A rows without a calibrated reading; decisive n_ex2020 = {n} vs the v1 §8 "
                f"power-note expectation n ≈ {SPEC_D3_EXPECTED_N_EX2020} (the ~30% MSE minimum detectable difference quoted there gets worse); "
                + CAL_STORE_NOTE)
    if not rf_ok:
        first_txt = "target_first check: n/a (no target_first rows in the intersection: the agreement condition could not be evaluated)"   # N4
    else:
        first_txt = (f"target_first agreement reading = {reading} (Q17): r_first = {rf:.4f} -> class {cls_first}; "
                     f"r_latest = {r:.4f} -> class {cls_latest}" if r_ok else f"target_first r_first = {rf:.4f}; r_latest undefined")
    cons = {"SUCCESS": "The home-built ENS_HH stays the headline; calibrated ADS is reported as the comparator (within X).",
            "MIDDLE": "Keep the home-built headline, add calibrated ADS as a second line labelled with the measured gap, re-decide at the next R2 calibration.",
            "KILL": "Calibrated ADS becomes the dashboard headline and ENS_HH the explainable cross-check line.",
            "DEFERRED": "target_first disagrees with target_latest under the frozen reading: the decision is deferred to the next R2 (v1 §8 D-3).",
            "NOT_DECIDABLE": "No calibrated intersection on IS-A (fewer than 24 calibration rows or no readings): no decision is taken."}
    if not r_ok or n < 3:
        outcome, why = "NOT_DECIDABLE", "r undefined"
    elif rf_ok and reading == "sign_of_r_minus_1" and np.sign(rf - 1.0) != np.sign(r - 1.0) and abs(r - 1.0) > 1e-12:
        outcome, why = "DEFERRED", f"sign(r_first - 1) = {np.sign(rf - 1.0):+.0f} vs sign(r_latest - 1) = {np.sign(r - 1.0):+.0f}"
    elif rf_ok and reading == "same_outcome_class" and cls_first != cls_latest:
        outcome, why = "DEFERRED", f"class under target_first {cls_first} != class under target_latest {cls_latest}"
    elif cls_latest == "SUCCESS":
        outcome, why = "SUCCESS", f"r = {r:.4f} <= {1 + X_pct / 100:.4f}"
    elif cls_latest == "KILL":
        outcome, why = "KILL", f"r = {r:.4f} > {1 + Y_pct / 100:.4f} and one-sided DM t = {dm.get('t'):.3f} >= {X.DM_ONE_SIDED_10PCT}"
    else:
        outcome, why = "MIDDLE", f"r = {r:.4f}; DM t = {dm.get('t')}"
    return {"outcome": T(outcome, DECISION, f"{why}; {first_txt}; {warm_txt}", n, W, "v1 §8 D-3"),
            "r_ex2020": T(r, DECISION, "RMSE_ENS_cal / RMSE_ADS_cal, ex-2020, IS-A, target_latest", n, W, "v1 §8 D-3"),
            "margins": T({"X_pct": X_pct, "Y_pct": Y_pct, "success_if_r_le": 1 + X_pct / 100, "kill_if_r_gt": 1 + Y_pct / 100,
                          "freeze_source": freeze.get("_source", "freeze.json")}, DECISION, "read from freeze.json (Q1)", None, W, "v1 §8 / Q1"),
            "dm_one_sided_ex2020": T({**{k: dm.get(k) for k in ("t", "n", "mean_d", "p_one_sided_cand_worse")}, "kill_cand_worse": kill_dm}, DECISION,
                                     f"d = e_ENS^2 - e_ADS^2, H1 mean d > 0, NW-6, one-sided t >= {X.DM_ONE_SIDED_10PCT} (verdict computed here from t)", dm.get("n"), W, "v1 §1 F08"),
            "calibration_warmup": D(warm, "S1/D1: months at IS-A before the first calibrated reading (the store holds regime-(i) readings only); n vs the v1 §8 expectation; Q16 ruled (SPEC v1.2: symmetric store, n recorded)", warm.get("n_rows_at_is"), W, "v1 §5 / §8 D-3"),
            "class_under_target_first": D({"reading_used": reading, "class_latest": cls_latest, "class_first": cls_first, "r_first_ex2020": rf,
                                           "dm_first_t": (vf.get("dm_one_sided_ens_worse_ex2020") or {}).get("t"), "n_first": vf.get("n")},
                                          "D6: the outcome class under target_first with the same thresholds, beside the class under target_latest; the frozen reading (Q17) decides DEFERRED",
                                          vf.get("n"), W, "v1 §8 D-3"),
            "loyo_r_ex2020": D(blk.get("loyo_r_ex2020"), "leave-one-calendar-year-out range of r", n, W, "v1 §8"),
            "r_with2020_reported_never_decides": D((blk.get("r_ens_over_ads") or {}).get("with2020"), "with-2020 numbers are reported and never decide", blk.get("n_intersection"), W, "v1 §8 D-3"),
            "r_vs_target_first": D(blk.get("vs_target_first"), f"agreement check under the frozen reading ({reading}); DEFERRED on disagreement; n/a when target_first is unavailable", None, W, "v1 §8 D-3"),
            "raw_ens_rmse_ex2020": D((blk.get("rmse_ens_raw") or {}).get("ex2020"), "uncalibrated ENS_HH on the same months", n, W, "v1 §5 Symmetry"),
            "onset_timing_2013plus": D(blk.get("onset_timing"), "one event (2020): calibrated crossings on the issue-date clock; expected tie", None, W, "v1 §8 D-3"),
            "consequence": T(cons[outcome], DECISION, "pre-registered consequence text", None, W, "v1 §8 D-3"),
            "scope_note": D("tracking-accuracy decision on expansion-dominated months; says nothing about recession-timing skill; no claim of an edge over persistence ex-2020 in the real-time regime", "v1 §8 D-3 text", None, W, "v1 §8")}


# ----------------------------------------------------------------------------- availability (v1 §3, F15)
def _days(lo: str, hi: str):
    import datetime as dt
    d = dt.date.fromisoformat(lo)
    end = dt.date.fromisoformat(hi)
    while d <= end:
        yield d.isoformat()
        d += dt.timedelta(days=1)


def section_availability(inp: StudyInputs, reg1: dict) -> dict:
    """v1 §3 availability (descriptive): days per calendar month with a reading for the latest
    PAYEMS month — deployed fixed-lag gate vs v2 vs ADS — 2013-06+ and the 2025-10..2026-04
    shutdown window separately, plus the frequency of each lag pattern and of dropped members.
    Structural: the lag state per day comes from the vintage table (vintage date -> last
    observation month) and the ADS panel; no composite is computed per day."""
    _check(inp)
    import bisect
    vt = inp.vintage_table
    if not vt:
        return {"status": D("not run: no vintage table", "", None, None, "v1 §3")}
    by = {}
    for r in vt:
        by.setdefault(r["series"], []).append((r["vintage_date"], r["last_obs_month"], r.get("last_obs")))
    for k in by:
        by[k].sort()
    keys = {k: [v[0] for v in by[k]] for k in by}
    panel = inp.ads_panel or []
    pdates = [r["vintage_date"] for r in panel]
    cards = reg1.get("_scorecards", [])
    hi = max([s["issue_date"] for s in cards] + [v[0] for k in by for v in by[k]])
    per_month: dict = {}
    pat_days: dict = {}
    for d in _days(inp.regime_i_start, hi):
        st = {}
        for c in E.COIN_MEMBERS + ("ICSA",):
            if c not in keys:
                st[c] = None
                continue
            j = bisect.bisect_right(keys[c], d) - 1
            st[c] = by[c][j] if j >= 0 else None
        m = d[:7]
        pm = per_month.setdefault(m, {"days": 0, "v2": 0, "deployed": 0, "ads": 0, "ads_claims_only": 0, "dropped": 0, "lag_ge3": 0})
        pm["days"] += 1
        if any(st[c] is None for c in E.COIN_MEMBERS):
            continue
        M = st["PAYEMS"][1]
        lags = {c: V.month_diff(M, st[c][1]) for c in E.COIN_MEMBERS}
        complete = all(L <= 0 for L in lags.values())
        icsa_ok = st["ICSA"] is not None and st["ICSA"][1] >= M
        v2 = (not complete) and icsa_ok
        dep = lags == {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 2}
        pm["v2"] += int(v2)
        pm["deployed"] += int(dep)
        pm["dropped"] += int(any(L >= 4 for L in lags.values()))
        pm["lag_ge3"] += int(any(L >= 3 for L in lags.values()))
        k = "|".join(f"{c}:{lags[c]}" for c in E.COIN_MEMBERS)
        pat_days[k] = pat_days.get(k, 0) + 1
        if pdates:
            j = bisect.bisect_right(pdates, d) - 1
            if j >= 0:
                v = panel[j]
                has = any(v[kk] == M and v[f"{kk}_n"] for kk in ("m0", "m1", "m2"))
                pm["ads"] += int(has)
                pm["ads_claims_only"] += int(has and v["claims_only"])

    def agg(months):
        rows = [per_month[m] for m in months]
        n = len(rows)
        tot = sum(r["days"] for r in rows) or 1
        return {"n_months": n, "days": sum(r["days"] for r in rows),
                "v2_days_per_month": sum(r["v2"] for r in rows) / n if n else None,
                "deployed_days_per_month": sum(r["deployed"] for r in rows) / n if n else None,
                "ads_days_per_month": sum(r["ads"] for r in rows) / n if n else None,
                "share_days": {"v2": sum(r["v2"] for r in rows) / tot, "deployed": sum(r["deployed"] for r in rows) / tot, "ads": sum(r["ads"] for r in rows) / tot},
                "ads_claims_only_days": sum(r["ads_claims_only"] for r in rows),
                "days_with_dropped_member": sum(r["dropped"] for r in rows), "days_with_lag_ge3": sum(r["lag_ge3"] for r in rows)}
    months = sorted(per_month)
    sw = [m for m in months if AVAIL_SHUTDOWN_WINDOW[0] <= m <= AVAIL_SHUTDOWN_WINDOW[1]]
    W = [months[0], months[-1]] if months else None
    issue_pat = _count(["|".join(f"{c}:{s['lags'][c]}" for c in E.COIN_MEMBERS) for s in cards if s.get("lags")])
    return {"basis": D({"method": "structural: lag state per calendar day from (vintage date -> last observation month) of the latest listed vintage <= d per series; "
                                  "v2 reading = a PAYEMS month beyond the last complete COIN with ICSA covering it (the engine issues on every such state; "
                                  "lag >= 4 members dropped); deployed = lags exactly {INDPRO 1, W875RX1 1, CMRMTSPL 2}; ADS = archived vintage <= d with days in M",
                        "shutdown_window": list(AVAIL_SHUTDOWN_WINDOW)}, "descriptive table (v1 §3)", len(months), W, "v1 §3 / F15"),
            "all_2013_06plus": D(agg(months), "days per calendar month with a reading, all months", len(months), W, "v1 §3"),
            "shutdown_2025_10_to_2026_04": D(agg(sw) if sw else None, "the 2025-26 shutdown window separately", len(sw), list(AVAIL_SHUTDOWN_WINDOW), "v1 §3"),
            "per_month": D(per_month, "per calendar month: days, v2, deployed, ads, ads_claims_only, dropped, lag_ge3", len(months), W, "v1 §3"),
            "lag_pattern_frequency_days": D(pat_days, "calendar days per lag pattern PAYEMS|INDPRO|W875RX1|CMRMTSPL", sum(pat_days.values()), W, "v1 §3"),
            "lag_pattern_frequency_issue_rows": D(issue_pat, "regime (i) nowcast rows per lag pattern", sum(issue_pat.values()), W, "v1 §3"),
            "dropped_member_frequency_issue_rows": D(_count([",".join(s["dropped"]) or "none" for s in cards if s.get("lags")]), "regime (i) nowcast rows by dropped set", len(cards), W, "v1 §2.4")}


# ----------------------------------------------------------------------------- Chauvet-Piger (v1 §6)
def _month_end_iso(m: str) -> str:
    return PG.month_end(m).isoformat()


def _days_between(a: str, b: str) -> int | None:
    import datetime as dt
    if not a or not b:
        return None
    return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days


def section_chauvet_piger(inp: StudyInputs, lag: dict, reg1: dict, reg2: dict) -> dict:
    """v1 §6 (F09, DT-15), DESCRIPTIVE throughout: the first-release path by RELEASE DATE
    (value vectors from the §6 ALFRED rule where available), the published 3x80%/3x20% rule
    with peak dating, the 1-month >= 50% sensitivity, declaration dates vs NBER peaks and
    announcements and vs our realized / ENS_HH crossings on the calendar-date clock, the
    largest non-recession real-time print, the ALFRED back-history glitch flags."""
    _check(inp)
    if not inp.piger_releases:
        return {"status": D("not run: no Piger release history", "", None, None, "v1 §6")}
    rows, summary = PG.build_path(inp.piger_releases, inp.piger_alfred)
    tps = inp.nber.get("turning_points", [])
    spans = inp.nber.get("recession_spans_usrec_1960plus", [])
    peaks = {t["month"]: t for t in tps if t["type"] == "peak"}
    troughs = {t["month"]: t for t in tps if t["type"] == "trough"}
    usrec = inp.f5.get("USREC", {})
    simA = lag["_sims"]["A"]
    otA = X.onset_table(simA["months"], simA["y"], simA["ens"], E.onsets_from_usrec(inp.ds5))
    cross_by_onset = {r["onset"]: r for r in otA["rows"]}
    pts2 = reg2.get("_points", {}) if reg2 else {}
    cards = reg1.get("_scorecards", []) if reg1 else []
    vfirst = {s["M"]: s.get("target_first_vintage") for s in cards if s.get("row_kind") == "nowcast"}
    isa_date = {}
    for s in cards:
        if s.get("row_kind") == "nowcast" and s["IS"] == "A" and s["M"] not in isa_date:
            isa_date[s["M"]] = s["issue_date"]
    ri_month = inp.regime_i_start[:7]

    def our_dates(onset):
        r = cross_by_onset.get(onset)
        if not r:
            return None
        mc, mn = r["realized_cross"], r["nowcast_cross"]
        pseudo = (mc or onset) < ri_month
        if pseudo:
            rc_date = pts2.get("C", {}).get(E.madd(mc, 1)) if mc else None
            en_date = pts2.get("A", {}).get(mn) if mn else None
            basis = "regime (ii) list-proxy points: realized = IS-C point of m_c + 1; ENS_HH = IS-A point of m_n (pseudo-real-time, labelled)"
        else:
            rc_date = vfirst.get(mc) if mc else None
            en_date = isa_date.get(mn) if mn else None
            basis = "regime (i): realized = v*(m_c); ENS_HH = the IS-A issue date of m_n"
        return {"realized_cross_month": mc, "realized_cross_date": rc_date, "ens_hh_cross_month": mn, "ens_hh_cross_date": en_date,
                "pseudo_real_time": pseudo, "basis": basis}

    decl = []
    for e in summary["rule_3x80"]["events"]:
        if e["kind"] == "recession_start":
            span = next((s for s in reversed(spans) if s["peak"] <= e["first_recession_month"]), None)
            peak = span["peak"] if span else None
            ann = peaks.get(peak, {}).get("announcement_date") if peak else None
            ours = our_dates(span["onset"]) if span else None
            decl.append({"kind": "start", "release_date": e["release_date"], "model_peak_month": e["peak_month"],
                         "model_first_recession_month": e["first_recession_month"], "trigger_months": e["trigger_months"],
                         "nber_peak_month": peak, "nber_onset_month": span["onset"] if span else None, "nber_announcement_date": ann,
                         "days_after_nber_peak_month_end": _days_between(e["release_date"], _month_end_iso(peak)) if peak else None,
                         "months_after_nber_peak": V.month_diff(e["release_date"][:7], peak) if peak else None,
                         "days_vs_nber_announcement": _days_between(e["release_date"], ann) if ann else None,
                         "ours": ours,
                         "days_vs_our_realized_crossing": _days_between(e["release_date"], ours["realized_cross_date"]) if ours and ours["realized_cross_date"] else None,
                         "days_vs_our_ens_hh_crossing": _days_between(e["release_date"], ours["ens_hh_cross_date"]) if ours and ours["ens_hh_cross_date"] else None})
        else:
            cands = [s for s in spans if s["onset"] <= e["trigger_months"][0]]
            span = max(cands, key=lambda s: s["onset"]) if cands else None       # the recession the start event opened
            tr = span["end"] if span else None
            ann = troughs.get(tr, {}).get("announcement_date") if tr else None
            decl.append({"kind": "end", "release_date": e["release_date"], "model_trough_month": e["trough_month"], "trigger_months": e["trigger_months"],
                         "nber_trough_month": tr, "nber_announcement_date": ann,
                         "months_after_nber_trough": V.month_diff(e["release_date"][:7], tr) if tr else None,
                         "days_vs_nber_announcement": _days_between(e["release_date"], ann) if ann else None})
    # onsets never declared by the 3x80% rule in the release window
    first_rel = inp.piger_releases[0]["release_date"][:7]
    undeclared = [s["onset"] for s in spans if s["onset"] >= first_rel and not any(d["kind"] == "start" and d.get("nber_onset_month") == s["onset"] for d in decl)]
    # largest non-recession real-time print (latest month with USREC = 0)
    nonrec = [(r["latest_prob"], r["release_date"], r["latest_month"]) for r in inp.piger_releases if usrec.get(r["latest_month"]) == 0]
    largest = max(nonrec) if nonrec else None
    path = [{"release_date": r["release_date"], "latest_month": r["latest_month"], "pct": float(r["piger_latest_pct"]),
             "source": r["value_source"], "state_3x80": r["rule_3x80_state"], "event": r["rule_3x80_event"], "fires_1m50": bool(int(r["rule_1m50_fires"]))} for r in rows]
    W = [summary["first_release"], summary["last_release"]]
    return {"basis": D({"n_releases": summary["n_releases"], "release_lag_days": summary["release_lag_days"], "rule": summary["rule_3x80"],
                        "same_inputs_note": "the same four inputs (a different model, not independent data); the 2020-12-23 re-basing of Mar-Jul 2020; no MS-DFM fitted here",
                        "alfred_coverage": summary.get("alfred_coverage"), "header_corrections": summary["header_corrections"]},
                       "real-time path by release date; descriptive, no grade (two recessions)", summary["n_releases"], W, "v1 §6"),
            "path": D(path, "first-release path (percent); value vectors per the §6 ALFRED rule where chosen", len(path), W, "v1 §6"),
            "declarations_3x80": D(decl, "3x80% / 3x20% declarations with peak dating (month before the first >= 50% month of the chain); clocks: NBER peak month end, NBER announcement, our crossings (calendar dates)", len(decl), W, "v1 §6"),
            "onsets_never_declared_3x80": D(undeclared, "NBER onsets inside the release history with no 3x80% declaration", len(undeclared), W, "v1 §6"),
            "sensitivity_1m50": D(summary["rule_1m50"], "1-month >= 50% on each release's latest month; episodes of consecutive firing releases", len(summary["rule_1m50"]["firing_releases"]), W, "v1 §6 / Q8"),
            "largest_non_recession_print": D({"pct": 100 * largest[0], "release_date": largest[1], "latest_month": largest[2]} if largest else None,
                                             "max latest-month probability among releases whose latest month has USREC = 0", len(nonrec), W, "v1 §6"),
            "alfred_glitch_flags": D({"anomalies_gt_1pp": summary.get("alfred_anomalies_gt_1pp"), "fallback_releases_after_first_alfred": (summary.get("alfred_coverage") or {}).get("fallback_releases_after_first_alfred")},
                                     "ALFRED vintages whose back-history differs from Piger's column by > 1 pp (a chart from ALFRED vectors must mark them); releases on the Piger-column fallback", None, W, "v1.1 §6 amendment"),
            "known_event_checks": D(summary["known_event_checks"], "piger.known_event_checks (real-history expectations; the 2008-02 peak label is ruled: peak 2008-01 under the rule as written)", None, W, "v1.1")}


# ----------------------------------------------------------------------------- honesty box (v1 §7.3, §9, v1.1 Q05)
def section_honesty(inp: StudyInputs, win: dict, lag: dict, reg1: dict, comp: dict | None = None) -> dict:
    """F1-vs-F5 realized-target drift (RMS, max, label flips); ENS_HH IS-A on F1 beside the
    August soft numbers (v1.1 Q05 ruling); the August PERS / ENS_BC forms re-run on F5 (Q4:
    both reported); shutdown-window counts per IS; n per IS; the unrevised re-check; hashes;
    which recessions each regime contains (v0 §4.1, D11); the D-3 calibration warm-up (S1/D1)."""
    _check(inp)
    ds5 = inp.ds5
    out = {}
    # D11: which recessions each regime contains (v0 §4.1 "the honesty box says which recessions each regime contains")
    onsets_all = E.onsets_from_usrec(ds5)
    lo2, hi2 = inp.regime_ii_window
    out["recessions_per_regime"] = D({"lag_simulation": [o for o in onsets_all if o <= win["_hi"]],
                                      "regime_ii_pseudo_real_time": [o for o in onsets_all if lo2 <= o <= hi2],
                                      "regime_i_true_real_time": [o for o in onsets_all if o >= inp.regime_i_start[:7]],
                                      "windows": {"lag_simulation": ["1972-01", win["_hi"]], "regime_ii": [lo2, hi2], "regime_i": [inp.regime_i_start, None]}},
                                     "NBER onsets (USREC 0 -> 1 in F5) inside each regime's window; the regimes are never pooled", len(onsets_all), None, "v0 §4.1 / v1 §9")
    # S1/D1: the D-3 calibration warm-up named in the honesty box
    cper = (comp or {}).get("_per_is") or {}
    out["d3_calibration_warmup"] = D({IS: {k: blk.get(k) for k in ("first_row_month", "first_calibrated_month", "n_rows_at_is", "n_rows_without_calibration", "n_intersection", "n_ex2020", "spec_expected_n_ex2020")}
                                      for IS, blk in cper.items()} if cper else None,
                                     CAL_STORE_NOTE, None, None, "v1 §5 / §8 D-3")
    if inp.f1:
        ds1 = E.build(inp.f1)
        hi = min(E.scored_window_end(ds1), win["_hi"])
        common = [m for m in ds1.months if "1972-01" <= m <= hi and m in ds5.idx and ds1.complete[ds1.idx[m]] and ds5.complete[ds5.idx[m]]]
        c1 = np.array([ds1.coin[ds1.idx[m]] for m in common])
        c5 = np.array([ds5.coin[ds5.idx[m]] for m in common])
        diff = c5 - c1
        flips = [{"month": m, "F1": r6(a), "F5": r6(b), "label_F1": X.label3(a), "label_F5": X.label3(b)} for m, a, b in zip(common, c1, c5) if X.label3(a) != X.label3(b)]
        imax = int(np.argmax(np.abs(diff))) if len(diff) else None
        out["f1_vs_f5_realized_drift"] = D({"rms": float(np.sqrt(np.mean(diff ** 2))) if len(diff) else None,
                                            "max_abs": float(np.abs(diff).max()) if len(diff) else None, "max_abs_month": common[imax] if imax is not None else None,
                                            "label_flips_n": len(flips), "label_flips": flips[:40], "n_common": len(common),
                                            "last_months": {m: {"F1": r6(ds1.coin[ds1.idx[m]]), "F5": r6(ds5.coin[ds5.idx[m]])} for m in common[-6:]}},
                                           "realized COIN on F1 vs F5 over the common complete months (the target itself moved: NIPA 2026-09-30)", len(common), ["1972-01", hi], "v1 §1 Windows / §9")
        tg1 = E.eval_targets(ds1, ("1972-01", E.scored_window_end(ds1)))
        s1 = E.simulate(ds1, E.PATTERNS["A"], "scoring", tg1, "hh")
        e, ep = s1["ens"] - s1["y"], s1["pers_real"] - s1["y"]
        ex = X.ex2020_mask(s1["months"])
        ot = X.onset_table(s1["months"], s1["y"], s1["ens"], E.onsets_from_usrec(ds1))
        tr = X.transition_accuracy(s1["ens"], s1["y"], s1["pers_real"])
        out["ens_hh_IS_A_on_F1"] = D({"pct_vs_pers_full": X.pct_change(X.rmse(e), X.rmse(ep)), "pct_vs_pers_ex2020": X.pct_change(X.rmse(e, ex), X.rmse(ep, ex)),
                                      "transitions_pct": tr["accuracy_pct"], "transitions": [tr["hits"], tr["n_transitions"]],
                                      "onsets_earlier_tie_later": [ot["summary"]["earlier"], ot["summary"]["tie"], ot["summary"]["later"]],
                                      "dm_ex2020_t": X.dm_test(e, ep, mask=ex)["t"], "window": [s1["months"][0], s1["months"][-1]],
                                      "august_soft_reference": {"pct_full": -29.8, "pct_ex2020": -12.5, "transitions_pct": 30.7, "onsets": [4, 1, 2]}},
                                     "ENS_HH at IS-A on F1 (honesty box; v1.1 Q05 ruling: computed once, in the scored run, beside the August soft numbers; not a decision)", len(tg1), [s1["months"][0], s1["months"][-1]], "v0 §7.1 SOFT / v1.1")
    # August forms on F5 (Q4: gate on F1, score on F5, both reported)
    tg5 = win["_targets"]
    rep5 = E.simulate(ds5, E.PATTERNS["A"], "reproduction", tg5, "original")
    y, p, m = rep5["y"], rep5["pers_real"], rep5["months"]
    ex5, p90 = X.ex2020_mask(m), X.since_mask(m, "1990-01")
    out["august_forms_on_f5"] = D({"PERS_rmse_full_1990_ex2020": [X.rmse(p - y), X.rmse(p - y, p90), X.rmse(p - y, ex5)],
                                   "ENS_BC_rmse_full_1990_ex2020": [X.rmse(rep5["ens"] - y), X.rmse(rep5["ens"] - y, p90), X.rmse(rep5["ens"] - y, ex5)],
                                   "august_targets_on_F1": {"PERS": [0.4674, 0.5316, 0.2580], "ENS_BC": [0.3344, 0.3692, 0.2202]},
                                   "realized_last_months": {mm: r6(ds5.coin[ds5.idx[mm]]) for mm in m[-4:]}},
                                  "the August estimator (reproduction_mode, original CLAIMS form) re-run on F5 over the scored window: the August numbers are not expected to reproduce on F5 (CMRMTSPL 2026-06 published; NIPA revision)", len(m), [m[0], m[-1]], "v0 §7.3 Q4")
    per_is = reg1.get("_scorecards", [])
    out["regime_i_counts_per_is"] = D({IS: {"n_rows": sum(1 for s in per_is if s.get("IS") == IS),
                                            "in_shutdown_window": sum(1 for s in per_is if s.get("IS") == IS and s["flags"]["in_shutdown_window"]),
                                            "lag_ge3_or_dropped": sum(1 for s in per_is if s.get("IS") == IS and (s["flags"]["lag_ge3"] or s["flags"]["dropped"]))}
                                       for IS in ("A", "B", "C")}, "shutdown-window and over-lag counts per IS (v1 §4.1)", len(per_is), None, "v1 §4.1 / §9")
    out["unrevised_recheck"] = D(inp.unrevised, "T10Y3M / BAA10YM taken current: changed values between an archived vintage and the run-day pull", len(inp.unrevised), None, "v1 §4.1")
    out["input_hashes"] = D(inp.hashes, "sha256 of F1-F8 and F5 inputs (recorded by run_study.py)", None, None, "v1 §7.3")
    out["statements"] = D(["Final-vintage data for the lag simulation and regime (ii) (seasonal factors, benchmark and definition revisions, final z-score histories; v1 §9)",
                           "True real-time only from 2013-06 (one recession); regime (i) shutdown windows flagged",
                           "Pre-2009 claims on final seasonal factors (CLAIMS half); W875RX1 first prints revise by 0.47 sd with a +0.9 pp bias",
                           "ADS end-point revises by 0.36 mean-abs; post-2023 vintages embed a COVID-exclusion regime",
                           "Chauvet-Piger shares the inputs; its real-time record is two recessions, one declared 13 months late, one never",
                           "The QA variants' numbers are soft; their harness is not recoverable",
                           "UMCSENT is ~M-2 on the live board since September 2026 (FRED delay); the replay is unaffected",
                           "Bands: completion error only, final-vintage data; first-print revision not included until the real-time band is scored"],
                          "v1 §9 honesty statements carried verbatim into results", None, None, "v1 §9")
    return out


# ----------------------------------------------------------------------------- order
SECTION_ORDER = ("windows", "lag_simulation", "regime_i", "bands", "decision_D1", "decision_D2", "regime_ii",
                 "comparator", "comparator_sensitivities", "decision_D3", "availability", "chauvet_piger", "honesty")


def strip_private(obj):
    if isinstance(obj, dict):
        return {k: strip_private(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [strip_private(v) for v in obj]
    return obj


def run_all_sections(inp: StudyInputs, log=lambda *_: None) -> dict:
    """Runs every section in SECTION_ORDER. Returns {'results': {...}, 'diagnostic_holds': bool,
    'private': {...}}. The caller (run_study.py) halts the read-out when the §3 diagnostic
    fails. Nothing here writes a file."""
    _check(inp)
    R: dict = {}
    log("windows"); win = section_windows(inp); R["windows"] = win
    log("lag_simulation"); lag = section_lag_simulation(inp, win); R["lag_simulation"] = lag
    log("regime_i"); reg1 = section_regime_i(inp, win); R["regime_i"] = reg1
    extra = []
    for s in reg1.get("_scorecards", []):
        for key in ("members_bridged",):
            pat = dict(s.get(key) or {})
            for c in s.get("dropped", []):
                pat[c] = 4
            if pat and pat not in extra:
                extra.append(pat)
        cp = s.get("completed_prev")
        if cp:
            pat = dict(cp.get("pattern") or {})
            for c in cp.get("dropped", []):
                pat[c] = 4
            if pat and pat not in extra:
                extra.append(pat)
    log("bands"); bands = section_bands(inp, win, extra); R["bands"] = bands
    log("decisions D1/D2"); R["decision_D1"] = decide_d1(lag, win); R["decision_D2"] = decide_d2(bands, win)
    log("regime_ii"); reg2 = section_regime_ii(inp, lag, win); R["regime_ii"] = reg2
    log("comparator"); comp = section_comparator(inp, reg1, "primary"); R["comparator"] = comp
    R["comparator_sensitivities"] = {v: section_comparator(inp, reg1, v) for v in COMPARATOR_VARIANTS if v != "primary"}
    R["decision_D3"] = decide_d3(comp, inp.freeze) if "_per_is" in comp else {"outcome": T("NOT_DECIDABLE", DECISION, comp.get("status", {}).get("value", "comparator not run"), None, None, "v1 §8 D-3")}
    log("availability"); R["availability"] = section_availability(inp, reg1)
    log("chauvet_piger"); R["chauvet_piger"] = section_chauvet_piger(inp, lag, reg1, reg2)
    log("honesty"); R["honesty"] = section_honesty(inp, win, lag, reg1, comp)
    return {"results": strip_private(R), "diagnostic_holds": bool(lag["_diag_holds"]),
            "diagnostic": lag["diagnostic_rmse_A_ge_B_ge_C"], "private": {"board_bands": bands["_board"]}}
