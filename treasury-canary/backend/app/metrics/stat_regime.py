"""Statistical regime — unsupervised Treasury-market state (EXPERIMENTAL).

A 3-state Gaussian HMM on daily 10y-yield changes + 10d realized vol — the
validated survivor of the Wang-2020 regime research (composer/research/
wang2020-regime-hmm.md, B1-T: 7/9 known Treasury stress episodes flagged
across 49 years, ~zero false alarms in calm years). It is the board's one
HYPOTHESIS-FREE lens: it can flag the Treasury market statistically behaving
like past stress periods even when the stress arrives through a channel no
pin threshold anticipates. The mean-change sign splits STRESS into SELLOFF
flavor (1994/2022/2023 — debasement/fiscal, hurts duration havens) vs RALLY
flavor (2008/2020 — accident/flight-to-quality).

HARD GUARDRAILS (design contract):
  - DESCRIPTIVE ONLY. This module must never feed alerts, severity, the
    accident composite, or any traded decision until a live stability record
    exists (state-flapping is the known failure mode of refit HMMs).
  - The 49-year hindcast ships as STATIC data (computed walk-forward offline,
    script composer/research/b1t_hmm.py) — the free-tier container only fits
    the CURRENT state (one fit, cached 24h). B1 also proved these states
    carry no forward mean-return edge — regime description, not prediction.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_HINDCAST_PATH = os.path.join(os.path.dirname(__file__), "..", "data",
                              "stat_regime_hindcast.json")
_WINDOW = 1890          # trailing obs for the current-state fit (~7.5y)
_TTL = 24 * 3600
_cache: dict[str, object] = {"ts": 0.0, "data": None}
_lock = threading.Lock()


def load_hindcast() -> list[dict]:
    try:
        return json.load(open(_HINDCAST_PATH))
    except Exception as exc:  # noqa: BLE001
        logger.warning("stat-regime hindcast unavailable: %s", exc)
        return []


def _fit_current(dates, vals) -> dict | None:
    """One walk-forward-consistent fit on the trailing window. None if the
    tape is short/stale or the optional ML deps are absent."""
    try:
        import numpy as np
        from hmmlearn.hmm import GaussianHMM
    except Exception as exc:  # noqa: BLE001
        logger.warning("stat-regime deps unavailable: %s", exc)
        return None
    pairs = [(d, v) for d, v in zip(dates, vals) if v is not None]
    if len(pairs) < _WINDOW + 11:
        return None
    pairs = pairs[-(_WINDOW + 10):]
    y = np.array([v for _, v in pairs])
    chg = np.diff(y) * 100.0                      # bp/day
    vol = np.array([chg[max(0, i - 9):i + 1].std() for i in range(len(chg))])
    X = np.column_stack([chg, vol])[-_WINDOW:]
    best = None
    for seed in (1, 7):
        try:
            m = GaussianHMM(n_components=3, covariance_type="full",
                            n_iter=75, random_state=seed)
            m.fit(X)
            s = m.score(X)
            if best is None or s > best[0]:
                best = (s, m)
        except Exception:  # noqa: BLE001
            continue
    if best is None:
        return None
    m = best[1]
    post = m.predict_proba(X)[-1]
    state = int(post.argmax())
    vorder = m.means_[:, 1].argsort()             # sort states by mean vol
    label = {int(vorder[0]): "CALM", int(vorder[1]): "ELEVATED",
             int(vorder[2]): "STRESS"}[state]
    direction = ("selloff" if m.means_[state, 0] > 0 else "rally") \
        if label == "STRESS" else ""
    return {"state": label, "direction": direction,
            "confidence": round(float(post.max()), 2),
            "asof": pairs[-1][0].isoformat(), "n_obs": int(len(X))}


def build_stat_regime(bundle: dict) -> dict:
    now = time.time()
    if _cache["data"] is not None and now - float(_cache["ts"]) < _TTL:
        current = _cache["data"]
    else:
        with _lock:
            now = time.time()
            if _cache["data"] is not None and now - float(_cache["ts"]) < _TTL:
                current = _cache["data"]
            else:
                d, v = bundle.get("10y", ([], []))
                current = _fit_current(d, v)
                # cache even None briefly via short-circuit: only cache real fits
                if current is not None:
                    _cache["data"] = current
                    _cache["ts"] = time.time()
    return {
        "current": current,          # None => STALE (no data / deps / short tape)
        "hindcast": load_hindcast(),
        "validated": ("Walk-forward 1977-2026: flagged 7/9 known Treasury "
                      "stress episodes at STRESS (1994, 1998 LTCM, 2003, 2008, "
                      "2020, the full 2022 bond bear, 2023-Q3) with 2 false "
                      "alarms in nine calm years — both the real early-1996 "
                      "selloff. 2013 taper and 2025-April read ELEVATED only."),
        "framing": ("EXPERIMENTAL / unsupervised / descriptive. The one "
                    "hypothesis-free lens on the board: flags the Treasury "
                    "market statistically behaving like past stress periods "
                    "regardless of which pin channel the stress arrives "
                    "through. SELLOFF-stress (1994/2022/2023 flavor) hurts "
                    "duration havens; RALLY-stress (2008/2020) is the "
                    "flight-to-quality/accident flavor. States describe the "
                    "present — measured to carry NO forward return edge — and "
                    "never feed alerts or the accident composite."),
    }
