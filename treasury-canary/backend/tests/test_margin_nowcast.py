"""Margin nowcast (display-only) + Schwab EDGAR parser. Offline: the parser
fixture is frozen from Schwab's real June-2026 Monthly Activity Report 8-K
(filed 2026-07-21); the model tests use synthetic series with a known
margin<->SPX relationship."""
import math
from datetime import date, timedelta

import numpy as np

from app.metrics.margin_nowcast import (FROZEN_BACKTEST, _month_add,
                                        build_margin_nowcast)
from app.sources.schwab_margin import parse_activity_text

# frozen from the real filing text (flattened HTML)
REAL_SNIPPET = (
    "The Charles Schwab Corporation Monthly Activity Report For June 2026 "
    "... Margin Balances at month end (in billions of dollars) (4) "
    "83.4 88.3 92.4 97.2 105.6 110.1 112.3 116.3 120.6 126.7 136.0 154.6 165.1 "
    "7% 98% Schwab Trading Activity Index TM (STAX) (5) 40.7 41.8"
)


def test_parser_real_filing_snippet():
    out = parse_activity_text(REAL_SNIPPET)
    assert out is not None and len(out) == 13
    assert out["2026-06"] == 165.1 and out["2025-06"] == 83.4
    assert out["2026-05"] == 154.6                         # newest-last ordering
    assert 4.0 not in out.values()                         # footnote (4) skipped
    assert parse_activity_text("Quarterly earnings release ...") is None
    assert parse_activity_text(
        "Monthly Activity Report For June 2026 no margin table here") is None


def test_month_add():
    assert _month_add("2026-12", 1) == "2027-01"
    assert _month_add("2027-01", -12) == "2026-01"
    assert _month_add("2026-06", -2) == "2026-04"


def _synth(n_months=200, beta=0.5, hold_back=1, seed=3):
    """Margin follows dlog(margin) = beta*spx_ret exactly; the last
    `hold_back` FINRA months are withheld for the nowcast to estimate."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.004, 0.03, n_months)
    spx_d, spx_v, m_d, m_v = [], [], [], []
    level, margin = 1000.0, 500000.0
    d0 = date(2008, 1, 1)
    truth = []
    for i in range(n_months):
        y, m = (d0.year * 12 + d0.month - 1 + i) // 12, (d0.month - 1 + i) % 12 + 1
        first = date(y, m, 1)
        target = level * math.exp(rets[i])
        for k in range(21):
            spx_d.append(first + timedelta(days=k))
            spx_v.append(level * math.exp(rets[i] * (k + 1) / 21))
        level = target
        margin = margin * math.exp(beta * rets[i])
        m_d.append(first)
        m_v.append(margin)
        truth.append(margin)
    keep = n_months - hold_back
    return (m_d[:keep], m_v[:keep]), (spx_d, spx_v), truth, m_d


def test_nowcast_recovers_known_relationship():
    margin_pair, spx_pair, truth, m_d = _synth()
    last_held = m_d[-1]
    nc = build_margin_nowcast(margin_pair, spx_pair, schwab=None,
                              today=last_held + timedelta(days=27))
    assert nc is not None and len(nc["months"]) == 1
    row = nc["months"][0]
    assert row["month"] == f"{last_held.year:04d}-{last_held.month:02d}"
    est, real = row["margin_bn"] * 1000, truth[-1]
    assert abs(est / real - 1) < 0.02                      # exact model, ~exact fit
    assert row["basis"] == "price-model"
    assert "yoy_pct" in row and "excess_pp" in row and "state_est" in row
    assert row["band_pp"] == FROZEN_BACKTEST["yoy_err_sd_pp"]
    assert nc["display_only"]


def test_nowcast_schwab_anchor_wins_precision():
    margin_pair, spx_pair, truth, m_d = _synth()
    last_held = m_d[-1]
    # Schwab book = half the FINRA aggregate, in $bn, INCLUDING the held month
    schwab = {f"{d.year:04d}-{d.month:02d}": (v / 2) / 1000
              for d, v in zip(m_d, truth)}
    nc = build_margin_nowcast(margin_pair, spx_pair, schwab=schwab,
                              today=last_held + timedelta(days=27))
    row = nc["months"][0]
    assert row["basis"].startswith("schwab-anchored")
    assert abs(row["margin_bn"] * 1000 / truth[-1] - 1) < 0.02
    assert nc["schwab"]["latest_month"] == row["month"]
    # anchored band is at least as tight as the pure price-model band
    assert row["band_pp"] <= FROZEN_BACKTEST["yoy_err_sd_pp"] + 1e-9


def test_nowcast_degrades_gracefully():
    margin_pair, spx_pair, _, m_d = _synth(n_months=60)    # too short to fit
    assert build_margin_nowcast(margin_pair, spx_pair,
                                today=m_d[-1] + timedelta(days=27)) is None
    # nothing to nowcast: FINRA fully caught up
    margin_pair, spx_pair, _, m_d = _synth(hold_back=0)
    assert build_margin_nowcast(margin_pair, spx_pair,
                                today=m_d[-1] + timedelta(days=5)) is None
