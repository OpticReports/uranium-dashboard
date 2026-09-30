"""CANDIDATE B - THE MERGE-BLOCKING GATE TESTS, as they would land in
btc-executor/tests/test_executor_gates.py.

Kept OUT of tests/ deliberately: four of these must FAIL against current code
(they encode behaviour the change introduces), and a proposal must not redden a
live-money repo's suite before Casey has decided. Run from btc-executor:

    python3 -m pytest ../btc-paper-engine/research/scale/railfrac_gate_tests.py -q

Expected today: the INVARIANT tests pass (they assert things already true of
mirror.py, which is what makes the design safe to build on); the NEW-BEHAVIOUR
tests fail until the change lands. That split is the point - a gate that passes
before the change is not gating the change.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "btc-executor"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "btc-executor", "tests"))

from app import mirror                                            # noqa: E402
from test_executor_gates import Cfg, FakeVenue, mkexec            # noqa: E402

E = 100_055.0
STEP1 = dict(kelly_m=0.10, sizing_base_usd=0.0, max_notional_usd=45_000.0,
             max_account_lev=0.20, dd_halt_pct=0.175, daily_loss_halt_pct=0.03)


def _apply(ex, **kw):
    for k, v in kw.items():
        setattr(ex.cfg, k, v)
    ex.state.high_water = E
    ex.state.day_start_equity = E
    return ex


# ===================================================== INVARIANT GATES (pass now)
def test_gate_railfrac_step1_is_size_neutral(tmp_path):
    """The whole safety argument for STEP 1 is that it ships the SAME notional.
    If this drifts, the change has silently become a size increase and the
    RAMP ladder's advance criteria apply to it."""
    v = FakeVenue(equity=E, mid=83_644.5)
    before = _apply(mkexec(tmp_path, v, dry_run=True),
                    kelly_m=0.20, sizing_base_usd=50_000.0,
                    max_notional_usd=20_000.0, max_account_lev=2.0)
    g_before = before._effective_kelly_m() * 1.5 * before._base(E)
    after = _apply(mkexec(tmp_path, v, dry_run=True), **STEP1)
    g_after = after._effective_kelly_m() * 1.5 * after._base(E)
    assert abs(g_after / g_before - 1.0) < 0.001, \
        f"STEP 1 must ship today's size: {g_before:,.0f} -> {g_after:,.0f}"


def test_gate_railfrac_blast_radius_is_unchanged_at_live_equity(tmp_path):
    """cap_notional as a FRACTION of equity is the survivability number. STEP 1
    must not widen it at the equity it ships on."""
    v = FakeVenue(equity=E, mid=83_644.5)
    b = _apply(mkexec(tmp_path, v, dry_run=True), kelly_m=0.20,
               sizing_base_usd=50_000.0, max_notional_usd=20_000.0,
               max_account_lev=2.0)
    a = _apply(mkexec(tmp_path, v, dry_run=True), **STEP1)
    cb = min(b.cfg.max_notional_usd, b.cfg.max_account_lev * b._base(E))
    ca = min(a.cfg.max_notional_usd, a.cfg.max_account_lev * a._base(E))
    assert abs(ca / E - cb / E) < 0.005, \
        f"blast radius moved: {cb/E:.2%} -> {ca/E:.2%} of equity"


def test_gate_railfrac_halt_lines_unchanged_in_real_terms(tmp_path):
    """Flipping base 50,000 -> equity DOUBLES both breakers in account terms
    unless the percentages are re-cut in the SAME change. This is the gate that
    would have caught the naive flip."""
    v = FakeVenue(equity=E, mid=83_644.5)
    b = _apply(mkexec(tmp_path, v, dry_run=True), kelly_m=0.20,
               sizing_base_usd=50_000.0, dd_halt_pct=0.35,
               daily_loss_halt_pct=0.06, max_notional_usd=20_000.0,
               max_account_lev=2.0)
    a = _apply(mkexec(tmp_path, v, dry_run=True), **STEP1)
    for fld in ("dd_halt_pct", "daily_loss_halt_pct"):
        lb = getattr(b.cfg, fld) * b._base(b.state.high_water) / E
        la = getattr(a.cfg, fld) * a._base(a.state.high_water) / E
        assert abs(la - lb) < 0.005, \
            f"{fld} moved from {lb:.2%} to {la:.2%} of the real account"


def test_gate_railfrac_coherence_invariant_max_account_lev_ge_dd_halt(tmp_path):
    """DERIVED, then gated: with base = equity, guard2 is silent iff
    min(MAX_NOTIONAL_USD/base, MAX_ACCOUNT_LEV) >= DD_HALT_PCT. Verified against
    the guard itself rather than asserted."""
    v = FakeVenue(equity=E, mid=83_644.5)
    ex = _apply(mkexec(tmp_path, v, dry_run=False),
                **{**STEP1, "max_account_lev": 0.10})     # 0.10 < 0.175 -> must warn
    ex._check_halts(E)
    msgs = [e["msg"] for e in ex.state.events if e["kind"] == "halt_config"]
    assert any("DRAWDOWN" in m for m in msgs), \
        "MAX_ACCOUNT_LEV below DD_HALT_PCT must trip the coherence guard"
    assert ex.state.halted is None, "the guard warns, it does not halt"


def test_gate_railfrac_step1_config_is_coherent(tmp_path):
    """Fence for the one above: the PROPOSED config must be silent."""
    v = FakeVenue(equity=E, mid=83_644.5)
    ex = _apply(mkexec(tmp_path, v, dry_run=False), **STEP1)
    ex._check_halts(E)
    assert not [e for e in ex.state.events if e["kind"] == "halt_config"], \
        [e["msg"] for e in ex.state.events if e["kind"] == "halt_config"]


def test_gate_railfrac_naive_base_flip_is_caught(tmp_path):
    """THE REGRESSION GATE. Flipping SIZING_BASE_USD to 0 while leaving
    MAX_NOTIONAL_USD at 20,000 and DD_HALT_PCT at 0.35 is the tempting
    one-line version of this change. It must be loud on BOTH counts."""
    v = FakeVenue(equity=E, mid=83_644.5)
    ex = _apply(mkexec(tmp_path, v, dry_run=False), kelly_m=0.20,
                sizing_base_usd=0.0, max_notional_usd=20_000.0,
                max_account_lev=2.0, dd_halt_pct=0.35, daily_loss_halt_pct=0.06)
    ex._check_halts(E)
    msgs = [e["msg"] for e in ex.state.events if e["kind"] == "halt_config"]
    assert any("DRAWDOWN" in m for m in msgs), \
        "the naive flip leaves a drawdown line no single position can reach"
    want = 0.20 * 1.5 * E
    cap = min(ex.cfg.max_notional_usd, ex.cfg.max_account_lev * E)
    assert cap < want, "the naive flip must be visibly clamped, not silent"


def test_gate_railfrac_proportionality_holds_across_equity(tmp_path):
    """Casey's premise, gated: under STEP 1 the gross/equity ratio is invariant
    over the range the absolute ceiling authorises."""
    ratios = []
    for eq in (100_055.0, 125_000.0, 150_000.0, 200_000.0, 225_000.0):
        v = FakeVenue(equity=eq, mid=83_644.5)
        ex = _apply(mkexec(tmp_path, v, dry_run=True), **STEP1)
        ex.state.high_water = eq
        gross = min(ex._effective_kelly_m() * 1.5 * ex._base(eq),
                    ex.cfg.max_notional_usd, ex.cfg.max_account_lev * eq)
        ratios.append(gross / eq)
    assert max(ratios) - min(ratios) < 1e-9, \
        f"gross/equity drifted across the authorised range: {ratios}"


def test_gate_railfrac_absolute_ceiling_still_bites(tmp_path):
    """The ceiling is not decoration: past MAX_NOTIONAL_USD / MAX_ACCOUNT_LEV
    the book MUST under-size rather than keep scaling unattended."""
    eq = 400_000.0
    v = FakeVenue(equity=eq, mid=83_644.5)
    ex = _apply(mkexec(tmp_path, v, dry_run=True), **STEP1)
    ex.state.high_water = eq
    gross = min(ex._effective_kelly_m() * 1.5 * ex._base(eq),
                ex.cfg.max_notional_usd, ex.cfg.max_account_lev * eq)
    assert gross == pytest.approx(STEP1["max_notional_usd"]), \
        "the absolute ceiling must bound notional above the ratchet point"
    assert gross / eq < 0.15, "and the book must be visibly under-sized there"


# ================================= NEW-BEHAVIOUR GATES (must FAIL until shipped)
def test_gate_railfrac_equity_sanity_clamp_bounds_a_bad_read(tmp_path):
    """NEW. With base = equity, mirror.py:2182's unbounded read sizes the trade.
    A read above EQUITY_SANITY_MULT x high_water must be clamped and paged.
    Precedents: 2026-08-06 transient bad balance, 2026-08-29 venue mismatch."""
    assert hasattr(mirror, "EQUITY_SANITY_MULT"), \
        "EQUITY_SANITY_MULT not implemented"
    bad = E * 10
    v = FakeVenue(equity=bad, mid=83_644.5)
    ex = _apply(mkexec(tmp_path, v, dry_run=True), **STEP1)
    ex.state.high_water = E
    base = ex._sizing_base(bad)
    assert base <= mirror.EQUITY_SANITY_MULT * E + 1e-6, \
        f"a 10x equity read sized on {base:,.0f}"
    assert any(e["kind"] == "equity_read_clamped" for e in ex.state.events), \
        "a clamped equity read must page - a silent clamp is the same defect"


def test_gate_railfrac_sanity_clamp_never_touches_the_halt_path(tmp_path):
    """NEW, and the fence for the one above. The HALT path must keep the RAW
    read: it has HALT_CONFIRM_POLLS for bad reads, and clamping there would
    mask a real loss."""
    assert hasattr(mirror, "EQUITY_SANITY_MULT")
    v = FakeVenue(equity=E * 0.5, mid=83_644.5)
    ex = _apply(mkexec(tmp_path, v, dry_run=False), **STEP1)
    ex.state.high_water = E
    assert ex._breach_for(E * 0.5) is not None, \
        "a genuine -50% must still breach; the clamp must not mask it"


def test_gate_railfrac_cap_clamp_names_the_binding_rail(tmp_path):
    """NEW. cap_clamp currently says '(cap)'. With three rails in the min() an
    unnamed clamp is exactly the cap_coherence failure again - a month of
    under-sizing that every health surface called green."""
    eq = 400_000.0
    v = FakeVenue(equity=eq, mid=83_644.5)
    ex = _apply(mkexec(tmp_path, v, dry_run=True), **STEP1)
    ex.state.high_water = eq
    ex._leg_qty("pullback", {"lev": 1.5, "w_trend": 0.25}, 83_644.5, eq)
    msgs = [e["msg"] for e in ex.state.events if e["kind"] == "cap_clamp"]
    assert msgs, "no clamp fired where one was expected"
    assert any("MAX_NOTIONAL_USD" in m or "MAX_ACCOUNT_LEV" in m for m in msgs), \
        f"cap_clamp must name which rail bound: {msgs}"


def test_gate_railfrac_ramp_ladder_is_restated(tmp_path):
    """NEW, and it is a DOC gate because the failure is a doc failure. Every
    rung in EXECUTOR.md is a KELLY_M at base 50,000; base = equity re-values
    all of them 2.001x. An un-restated table says 'rung A' while the book is
    at THE CEILING."""
    here = os.path.dirname(os.path.abspath(__file__))
    doc = open(os.path.join(here, "..", "..", "..", "btc-executor",
                            "EXECUTOR.md")).read()
    assert "gross/equity" in doc or "fraction of equity" in doc.lower(), \
        "the ramp ladder must be restated in equity-fraction terms"
    assert "SIZING_BASE_USD=50000" not in doc.replace(" ", ""), \
        "the ladder still quotes sizes at the retired fixed base"
