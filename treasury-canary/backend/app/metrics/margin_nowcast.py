"""FINRA margin-debt NOWCAST — display-only estimate of the months FINRA
hasn't printed yet (~4-7 week publication lag).

Two legs, precision-weighted when both exist:
  price model    dlog(margin)_t ~ a + b*spx_ret_t + c*spx_ret_{t-1} + d*dRV_t,
                 fit on the full FINRA history at runtime (~29y monthly)
  Schwab anchor  dlog(margin_finra)_t ~ a2 + b2*dlog(margin_schwab)_t, fit on
                 the EDGAR-parsed overlap; Schwab's Monthly Activity Report
                 files ~2-3 weeks before FINRA prints, so the anchor month
                 usually exists exactly when the nowcast matters

HONESTY CONTRACT: the nowcast is an estimate. It never feeds the composite,
the corroboration flags, or the leverage playbook — those run on confirmed
prints only. The frozen pseudo-out-of-sample backtest (expanding-window,
every month predicted with only prior data) ships with the payload and is
rendered on the panel:
  OOS R2 0.49 - direction 74% - state 86% overall - but state-TRANSITION
  months only 55% (18/33): it catches about half of regime turns a month
  early and its misses cluster at band boundaries. YoY-line error sd 3.1pp.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np

from .crossasset import leverage_state

FROZEN_BACKTEST = {
    "asof": "2026-08-03",
    "design": "pseudo-OOS, expanding-window fit, 140 scored months (~2007-2026); "
              "every month predicted using only data available before it",
    "oos_r2": 0.49, "direction_hit_pct": 74.3,
    "state_hit_pct": 86.4, "transition_hit_pct": 54.5, "transitions": "18/33",
    "yoy_err_sd_pp": 3.1, "monthly_resid_sd_pct": 2.83,
    "note": "misses cluster at band boundaries (SQUEEZE/NEUTRAL); treat the "
            "nowcast state as an estimate with the band, never a hard call",
}
MIN_FIT_MONTHS = 120
MIN_SCHWAB_OVERLAP = 18
MAX_NOWCAST_MONTHS = 3
MIN_PARTIAL_DAYS = 6


def _mk(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    idx = y * 12 + (m - 1) + k
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _spx_monthly(spx_pair) -> tuple[dict, dict, dict]:
    """month -> (last close, realized vol %ann, n_days)."""
    daily: dict[str, list[float]] = {}
    for d, v in zip(*spx_pair):
        if v is not None:
            daily.setdefault(_mk(d) if isinstance(d, date) else str(d)[:7], []).append(float(v))
    me, rv, nd = {}, {}, {}
    for ym, vs in daily.items():
        me[ym] = vs[-1]
        nd[ym] = len(vs)
        rets = [math.log(b / a) for a, b in zip(vs, vs[1:]) if a > 0]
        rv[ym] = float(np.std(rets) * math.sqrt(252) * 100) if len(rets) >= 5 else None
    return me, rv, nd


def build_margin_nowcast(margin_pair, spx_pair, schwab: dict | None = None,
                         today: date | None = None) -> dict | None:
    """margin_pair: FINRA (dates, $M values), spx_pair: daily (dates, closes),
    schwab: {\"YYYY-MM\": $bn} or None. Returns the nowcast payload or None
    when there is nothing to estimate / not enough history."""
    today = today or date.today()
    pts = [(d, float(v)) for d, v in zip(*margin_pair) if v is not None]
    if len(pts) < MIN_FIT_MONTHS + 14:
        return None
    me, rv, nd = _spx_monthly(spx_pair)
    m_by = { _mk(d): v for d, v in pts }
    months = sorted(m_by)

    # --- fit the price model on full FINRA history -------------------------
    X, y = [], []
    for i in range(2, len(months)):
        a, b, c = months[i - 2], months[i - 1], months[i]
        if not all(k in me and rv.get(k) is not None for k in (a, b, c)):
            continue
        X.append([1.0, math.log(me[c] / me[b]), math.log(me[b] / me[a]),
                  rv[c] - rv[b]])
        y.append(math.log(m_by[c] / m_by[b]))
    if len(y) < MIN_FIT_MONTHS:
        return None
    X, y = np.asarray(X), np.asarray(y)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    price_sd = float((y - X @ beta).std())

    # --- fit the Schwab anchor on the overlap ------------------------------
    anchor = None
    if schwab:
        xs, ys = [], []
        for i in range(1, len(months)):
            p, c = months[i - 1], months[i]
            if p in schwab and c in schwab and schwab[p] > 0:
                xs.append([1.0, math.log(schwab[c] / schwab[p])])
                ys.append(math.log(m_by[c] / m_by[p]))
        if len(ys) >= MIN_SCHWAB_OVERLAP:
            A, r = np.asarray(xs), np.asarray(ys)
            b2, *_ = np.linalg.lstsq(A, r, rcond=None)
            anchor = {"beta": b2, "sd": float((r - A @ b2).std()),
                      "n_overlap": len(ys)}

    # --- nowcast the unprinted months --------------------------------------
    last = months[-1]
    out_rows = []
    m_hat = m_by[last]
    prev = last
    cur = _month_add(last, 1)
    while cur <= _mk(today) and len(out_rows) < MAX_NOWCAST_MONTHS:
        if cur not in me or nd.get(cur, 0) < MIN_PARTIAL_DAYS:
            break
        p2 = _month_add(cur, -2)
        ret = math.log(me[cur] / me[prev]) if prev in me else 0.0
        ret_l1 = math.log(me[prev] / me[p2]) if (prev in me and p2 in me) else 0.0
        drv = (rv[cur] - rv[prev]) if (rv.get(cur) is not None
                                       and rv.get(prev) is not None) else 0.0
        dlm_p = float(np.dot(beta, [1.0, ret, ret_l1, drv]))
        basis, sd = "price-model", price_sd
        if anchor and cur in schwab and prev in schwab and schwab[prev] > 0:
            dls = math.log(schwab[cur] / schwab[prev])
            dlm_s = float(np.dot(anchor["beta"], [1.0, dls]))
            wp, ws = 1 / price_sd ** 2, 1 / anchor["sd"] ** 2
            dlm_p = (wp * dlm_p + ws * dlm_s) / (wp + ws)
            sd = math.sqrt(1 / (wp + ws))
            basis = f"schwab-anchored (n={anchor['n_overlap']})"
        m_hat = m_hat * math.exp(dlm_p)
        base_m = _month_add(cur, -12)
        y12 = _month_add(cur, -12)
        row = {"month": cur, "margin_bn": round(m_hat / 1000, 1), "basis": basis}
        if base_m in m_by and y12 in me:
            yoy = (m_hat / m_by[base_m] - 1) * 100
            spx_yoy = (me[cur] / me[y12] - 1) * 100
            excess = yoy - spx_yoy
            band = max(1.0, FROZEN_BACKTEST["yoy_err_sd_pp"] if basis == "price-model"
                       else sd * 100)
            st = leverage_state(yoy, excess)
            near = any(leverage_state(yoy + dy, excess + dx) != st
                       for dy, dx in ((band, band), (-band, -band),
                                      (band, -band), (-band, band)))
            row.update({"yoy_pct": round(yoy, 1), "excess_pp": round(excess, 1),
                        "band_pp": round(band, 1), "state_est": st,
                        "near_boundary": bool(near),
                        "partial_month": nd.get(cur, 0) < 15})
        out_rows.append(row)
        prev = cur
        cur = _month_add(cur, 1)
    if not out_rows:
        return None

    sch_note = None
    if schwab:
        latest = max(schwab)
        base = _month_add(latest, -12)
        sch_note = {"latest_month": latest, "margin_bn": schwab[latest],
                    "yoy_pct": (round((schwab[latest] / schwab[base] - 1) * 100, 1)
                                if base in schwab and schwab[base] > 0 else None)}
    return {"months": out_rows, "last_print": last,
            "schwab": sch_note, "backtest": FROZEN_BACKTEST,
            "display_only": "estimate — never feeds the composite, the "
                            "corroboration flags or the playbook"}
