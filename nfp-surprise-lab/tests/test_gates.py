"""Merge-blocking gates for the NFP surprise study.

Two jobs:
  (1) data integrity — the frozen dataset must stay clean and first-print;
  (2) honesty — the study's headline claim is "there is NO tradeable edge".
      These gates fail if anyone later edits the numbers to claim one without
      the statistics actually supporting it.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from nfp_surprise_study import (  # noqa: E402
    COVID_END,
    COVID_START,
    anchoring_rule,
    binom_p,
    load,
    ref_gap_weeks,
    report,
    walk_forward_month_rule,
)

ROWS = load()
CORE = [r for r in ROWS if not (COVID_START <= r["rel"] <= COVID_END)]


# --------------------------------------------------------------- data ----
def test_gate_sample_size_and_span():
    assert len(ROWS) >= 150, "dataset shrank; re-pull before trusting any stat"
    assert ROWS[0]["rel"] <= dt.date(2013, 12, 31)
    assert ROWS[-1]["rel"] >= dt.date(2026, 6, 1)


def test_gate_no_nulls_and_surprise_consistent():
    for r in ROWS:
        assert r["consensus"] is not None and r["actual"] is not None
        assert abs((r["actual"] - r["consensus"]) - r["surprise"]) < 0.05


def test_gate_releases_unique_and_ordered():
    dates = [r["rel"] for r in ROWS]
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)


# NFP normally prints the first Friday. Documented exceptions, all verified:
#   * Thursday releases in the week of July 4 (holiday shift).
#   * 2013-10-22: Sep-2013 report, delayed by the Oct 2013 shutdown.
#   * 2025-11-20 / 2025-12-16 / 2026-02-11: delayed by the 2025 and 2026
#     lapses in appropriations (BLS revised release-date schedule).
KNOWN_OFF_SCHEDULE = {
    dt.date(2013, 10, 22), dt.date(2025, 11, 20),
    dt.date(2025, 12, 16), dt.date(2026, 2, 11),
}


def test_gate_release_day_is_friday_or_a_documented_exception():
    """Catches a calendar/timezone bug silently shifting month-of-year buckets.
    A NEW off-schedule date must be researched and added deliberately."""
    for r in ROWS:
        if r["rel"].weekday() == 4 or r["rel"] in KNOWN_OFF_SCHEDULE:
            continue
        assert r["rel"].weekday() == 3 and r["rel"].month == 7 and r["rel"].day <= 7, (
            f"{r['release']} ({r['rel']:%A}) is off-schedule and undocumented")


def test_gate_reference_months_are_continuous_except_oct_2025():
    """Oct-2025 has no standalone Employment Situation release: establishment
    data for it was published with November on 2025-12-16. Any OTHER gap means
    the pull dropped a month and every hit rate here is computed on a hole."""
    missing = []
    for a, b in zip(ROWS, ROWS[1:]):
        nxt = (a["ref"].replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        if b["ref"].replace(day=1) != nxt:
            missing.append((a["ref_month"], b["ref_month"]))
    assert missing == [("2025-09", "2025-11")] or missing == [], (
        f"unexpected reference-month gap(s): {missing}")


def test_gate_sept_2025_reference_month_override_applied():
    """The 2025-11-20 release was the SEPTEMBER report (+119k), not October.
    Guards the override that FMP's naive month labelling gets wrong."""
    row = next(r for r in ROWS if r["release"] == "2025-11-20")
    assert row["ref_month"] == "2025-09" and row["actual"] == 119.0


def test_gate_ref_gap_is_four_or_five_weeks():
    assert {ref_gap_weeks(r["ref"]) for r in ROWS} <= {4, 5}


# ------------------------------------------------------------ honesty ----
def test_gate_precovid_consensus_is_unbiased():
    """The load-bearing claim: on the clean 2013-2019 sample, 'bet above
    consensus' is a coin flip. If this ever becomes significant, the writeup's
    conclusion must be rewritten -- not the test."""
    pre = [r for r in CORE if r["rel"] < dt.date(2020, 1, 1)]
    up = sum(1 for r in pre if r["surprise"] > 0)
    tot = up + sum(1 for r in pre if r["surprise"] < 0)
    assert binom_p(up, tot) > 0.05, (
        f"pre-COVID bet-above is now significant ({up}/{tot}); revisit the study")


def test_gate_no_out_of_sample_rule_beats_chance():
    """Every rule we shipped must fail out-of-sample. A rule that starts
    passing is a finding that requires a fresh counter-agent review before it
    is presented as an edge."""
    for name, fn in [("month-of-year", walk_forward_month_rule),
                     ("anchoring", anchoring_rule)]:
        hits, tot = fn(CORE)
        assert binom_p(hits, tot) > 0.05, (
            f"{name} rule now significant OOS ({hits}/{tot}) -- re-review")


def test_gate_seasonality_dies_under_multiple_testing():
    """12 month-buckets are 12 shots at a false positive; the Sidak-corrected
    best month must stay insignificant."""
    out = report()
    assert out["month_sidak_p"] > 0.05, "seasonal effect survived correction"


def test_gate_surprise_has_no_usable_persistence():
    out = report()
    assert abs(out["lag1_autocorr"]) < 0.2, "surprise persistence appeared"


def test_gate_edge_is_smaller_than_transaction_costs_claim():
    """A 55-56% hit rate on a ~50c binary is ~5-6c gross. The writeup claims
    that is inside typical Kalshi spread+fee. Gate the input to that claim."""
    up = sum(1 for r in CORE if r["surprise"] > 0)
    tot = up + sum(1 for r in CORE if r["surprise"] < 0)
    assert up / tot < 0.60, "core hit rate rose above 60%; cost argument changes"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ------------------------------------------------- signal-study gates ----
def test_gate_no_leading_indicator_survives_rank_correlation():
    """The follow-up study's load-bearing claim: every candidate signal that
    looks significant on Pearson collapses under Spearman, i.e. it was
    outlier-driven. Sidak-corrected across the candidates tested, nothing
    survives. A signal that starts passing is a finding, not a green light --
    it needs a fresh counter-agent review before anyone acts on it."""
    from signal_study import CANDIDATES, load_signals, main  # noqa: PLC0415

    results = main()
    assert results, "signal study produced no results"
    k = len(results)
    for res in results:
        sidak = 1 - (1 - res["p_spearman"]) ** k
        assert sidak > 0.05, (
            f"{res['label']} now survives rank correlation "
            f"(Spearman {res['spearman']:+.3f}, Sidak p={sidak:.4f}) -- re-review")


def test_gate_no_signal_beats_chance_on_sign():
    from signal_study import main  # noqa: PLC0415

    results = main()
    k = len(results)
    for res in results:
        sidak = 1 - (1 - res["p_hit"]) ** k
        assert sidak > 0.05, (
            f"{res['label']} sign hit rate now significant "
            f"({res['hits']}/{res['tot']}, Sidak p={sidak:.4f}) -- re-review")


def test_gate_misalignment_terciles_are_not_monotonic():
    """'Consensus is misaligned with the freshest hard read' would show up as a
    monotonic tercile gradient. It does not -- it is flat/U-shaped."""
    from signal_study import load as _load  # noqa: PLC0415
    from signal_study import misalignment  # noqa: PLC0415

    nfp = [r for r in _load() if not (COVID_START <= r["rel"] <= COVID_END)]
    mis = misalignment(nfp, pathlib.Path(__file__).resolve().parents[1]
                       / "data" / "signals_raw.json")
    lo, mid, hi = (t["rate"] for t in mis["terciles"])
    assert not (lo < mid < hi or lo > mid > hi), (
        f"tercile gradient became monotonic ({lo:.2f}/{mid:.2f}/{hi:.2f}) -- re-review")
    assert mis["p_hit"] > 0.05
