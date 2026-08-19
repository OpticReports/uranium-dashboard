"""Tests for the OBSERVE-ONLY quiet_before_catalyst flag + drift_z math.

The MRNA/INTerpath setup: a high-impact binary approaching while the price is
NOT already running (|drift_z| small vs the name's own vol).
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from app.models import Catalyst, Security
from app.scoring.components import drift_zscore_raw
from app.scoring.flags import evaluate_flags


def _sec(symbol="TEST"):
    return Security(symbol=symbol, name=symbol, active=True)


def _base_raw(**over):
    raw = {
        "mention_accel_z": None, "mention_z": None, "iv_z": None, "runway": None,
        "pullback_pct": None, "last_close": None, "atr14": None,
        "above_50dma": None, "volume_z": None, "last_dollar_volume": None,
        "drift_z": None, "realized_vol_20d": None,
        "insider_buys": [],
        "evidence": {"catalysts": [], "revisions": [], "mentions": []},
    }
    raw.update(over)
    return raw


def _catalyst(days_out, impact=0.9, asof=None):
    asof = asof or date.today()
    return Catalyst(symbol="TEST", date=asof + timedelta(days=days_out),
                    event_type="phase3_readout", title="P3", impact_weight=impact)


def _quiet_flags(raw, asof=None):
    asof = asof or date.today()
    return [f for f in evaluate_flags(_sec(), asof, raw, {})
            if f.flag_type == "quiet_before_catalyst"]


def test_fires_on_imminent_high_impact_catalyst_with_low_drift():
    asof = date.today()
    raw = _base_raw(
        drift_z=0.20, realized_vol_20d=0.85,
        evidence={"catalysts": [_catalyst(20, asof=asof)], "revisions": []},
    )
    flags = _quiet_flags(raw, asof)
    assert len(flags) == 1
    f = flags[0]
    assert f.severity == "info"  # observe-only lane
    assert "20 days" in f.message and "+0.20" in f.message
    assert f.evidence["drift_z"] == 0.20
    assert f.evidence["realized_vol_20d"] == 0.85
    assert f.evidence["window_days"] == 10
    assert f.evidence["catalysts"][0]["days_until"] == 20


def test_negative_drift_within_threshold_also_fires():
    asof = date.today()
    raw = _base_raw(
        drift_z=-0.50,
        evidence={"catalysts": [_catalyst(20, asof=asof)], "revisions": []},
    )
    assert len(_quiet_flags(raw, asof)) == 1


def test_does_not_fire_when_drift_high():
    # The name is already running into the event — priced, not quiet.
    asof = date.today()
    raw = _base_raw(
        drift_z=1.60,
        evidence={"catalysts": [_catalyst(20, asof=asof)], "revisions": []},
    )
    assert _quiet_flags(raw, asof) == []


def test_does_not_fire_when_catalyst_too_far_or_too_near():
    asof = date.today()
    far = _base_raw(
        drift_z=0.10,
        evidence={"catalysts": [_catalyst(60, asof=asof)], "revisions": []},
    )
    assert _quiet_flags(far, asof) == []
    near = _base_raw(
        drift_z=0.10,
        evidence={"catalysts": [_catalyst(2, asof=asof)], "revisions": []},
    )
    assert _quiet_flags(near, asof) == []


def test_does_not_fire_on_low_impact_catalyst():
    asof = date.today()
    raw = _base_raw(
        drift_z=0.10,
        evidence={"catalysts": [_catalyst(20, impact=0.5, asof=asof)],
                  "revisions": []},
    )
    assert _quiet_flags(raw, asof) == []


def test_does_not_fire_when_drift_z_is_none():
    # No data is None, never a silent zero — and None must never fire.
    asof = date.today()
    raw = _base_raw(
        drift_z=None,
        evidence={"catalysts": [_catalyst(20, asof=asof)], "revisions": []},
    )
    assert _quiet_flags(raw, asof) == []


# --- drift_z math -----------------------------------------------------------

def test_drift_zscore_none_on_insufficient_or_flat_data():
    assert drift_zscore_raw([100.0] * 5, 10) == (None, None)      # too short
    assert drift_zscore_raw([100.0] * 40, 10) == (None, None)     # zero vol
    assert drift_zscore_raw([], 10) == (None, None)


def test_drift_zscore_known_values():
    # Alternating ±2% series: real vol, ~zero 10-bar return => dz near zero.
    closes = [100.0 * math.exp(0.02 * ((-1) ** i)) for i in range(40)]
    dz, vol = drift_zscore_raw(closes, 10)
    assert dz is not None and vol is not None and vol > 0
    # Alternating series: 10-bar return ~0 => drift_z near zero.
    assert abs(dz) < 0.75


def test_drift_zscore_scales_with_window_return():
    flat_then_run = [100.0] * 30 + [100.0 * (1.03 ** i) for i in range(1, 11)]
    dz, _ = drift_zscore_raw(flat_then_run, 10)
    quiet = [100.0 + (0.5 * ((-1) ** i)) for i in range(40)]
    dz_quiet, _ = drift_zscore_raw(quiet, 10)
    assert dz is not None and dz_quiet is not None
    assert dz > abs(dz_quiet)  # running into the window >> quiet drift
