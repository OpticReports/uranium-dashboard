"""Indicator parity vs pandas reference (spec §1.2: match to 1e-9)."""
import csv
import os

import pytest

pd = pytest.importorskip("pandas")

from app.indicators import atr, rsi, sma

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "bars_4h_btcusd.csv")


def _bars():
    rows = list(csv.DictReader(open(FIX)))
    return ([float(r["open"]) for r in rows], [float(r["high"]) for r in rows],
            [float(r["low"]) for r in rows], [float(r["close"]) for r in rows],
            [float(r["volume"]) for r in rows])


def test_sma_matches_pandas():
    _, _, _, closes, vols = _bars()
    s = pd.Series(closes)
    for n in (50, 200):
        ref = s.rolling(n).mean().tolist()
        mine = sma(closes, n)
        for a, b in zip(mine, ref):
            if a is None:
                assert pd.isna(b)
            else:
                assert abs(a - b) < 1e-9
    ref20 = pd.Series(vols).rolling(20).mean().tolist()
    for a, b in zip(sma(vols, 20), ref20):
        if a is not None:
            assert abs(a - b) < 1e-9


def test_rsi_matches_pandas_wilder():
    _, _, _, closes, _ = _bars()
    s = pd.Series(closes)
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    ref = (100 - 100 / (1 + up / dn)).tolist()
    mine = rsi(closes, 14)
    for i, (a, b) in enumerate(zip(mine, ref)):
        if i == 0:
            continue
        assert abs(a - b) < 1e-9, i


def test_atr_matches_pandas_wilder():
    _, highs, lows, closes, _ = _bars()
    h, l, c = pd.Series(highs), pd.Series(lows), pd.Series(closes)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = float("nan")
    ref = tr.ewm(alpha=1 / 14, adjust=False).mean().tolist()
    mine = atr(highs, lows, closes, 14)
    for i, (a, b) in enumerate(zip(mine, ref)):
        if i == 0:
            continue
        assert abs(a - b) < 1e-9, i
