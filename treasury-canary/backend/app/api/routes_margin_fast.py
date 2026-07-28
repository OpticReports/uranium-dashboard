"""GET /margin/fast — the fast-leverage nowcast strip.

The Leverage Cycle chart (FINRA, monthly, ~3-4 week lag) answers "where are we
in the leverage CYCLE?". This endpoint answers "is leverage being forced out
RIGHT NOW?" from three faster legs:

  COT   weekly  hedge-fund net e-mini S&P positioning (%OI z-score, 3-day lag)
  VIX   daily   20-business-day change — the forced-deleveraging stress leg
  BTC   hourly  perp funding + open interest — same speculative money, visible
                in near-real-time (plus HY OAS daily, display-only: FRED now
                caps ICE BofA history at ~3y, too short to backtest honestly)

Composite state rules were PRE-REGISTERED, then evaluated once on 2006-2026
weekly data (no tuning loop — one variant, trial count 1, MARGIN_DEBT.md §fast).
The playbook stats below are FROZEN from that single evaluation.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from ..sources.cftc import fetch_emini_leveraged
from ..sources.deribit import fetch_btc_perp, fetch_funding_history
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["margin"])

# Pre-registered thresholds (fixed before forward returns were computed)
FAST_THRESHOLDS = {"flush_vix20": 8.0, "flush_dz4": -0.5, "washed_z": -1.0,
                   "washed_vix20": 0.0, "build_z": 1.0, "build_vix20": 4.0,
                   "z_window_weeks": 156, "z_min_weeks": 52}

# FROZEN study output (2006-06..2026-07, 995 weekly obs, fwd S&P returns).
# Baseline all-weeks: 1m median +1.4% (65% pos) · 3m +3.7% (71%) · 12m +13.1% (81%).
FAST_PLAYBOOK = {
    "FLUSH": {
        "label": "Forced deleveraging underway — VIX spiking while funds dump exposure",
        "stats": {
            "fwd1m": {"n": 5, "median": 7.4, "pct_pos": 100, "worst": 0.8},
            "fwd3m": {"n": 5, "median": 2.2, "pct_pos": 60, "worst": -4.0},
            "fwd12m": {"n": 5, "median": 7.5, "pct_pos": 60, "worst": -7.5},
        },
        "episodes": 3,
        "read": "Rare (3 episodes: Sep-2015, Mar-2022, Apr-2025) and LATE — by the "
                "time both legs confirm, the flush is climaxing. All 5 historical "
                "weeks resolved HIGHER 1 month out (median +7.4%); 3-12 months mixed.",
        "action": "Do not panic-sell the climax week — forced selling exhausts fast. "
                  "If you must de-risk, use the bounce. Watch for WASHED_OUT next: "
                  "that is the re-entry state.",
    },
    "WASHED_OUT": {
        "label": "Positioning flushed, vol stabilized — the fast re-entry zone",
        "stats": {
            "fwd1m": {"n": 115, "median": 2.0, "pct_pos": 63, "worst": -9.4},
            "fwd3m": {"n": 109, "median": 2.5, "pct_pos": 65, "worst": -17.5},
            "fwd12m": {"n": 99, "median": 15.6, "pct_pos": 95, "worst": -12.5},
        },
        "episodes": 22,
        "read": "Best state in the study: 95% of weeks saw the S&P HIGHER 12 months "
                "later (median +15.6%, 22 distinct episodes). The weekly analog of "
                "the FINRA SQUEEZE re-entry signal, arriving 1-2 months sooner.",
        "action": "Historically the zone to scale risk back IN — staged, not all at "
                  "once (worst 12m still -12.5%).",
    },
    "RISK_BUILD": {
        "label": "Crowded leverage, calm vol — fragility building",
        "stats": {
            "fwd1m": {"n": 134, "median": 1.5, "pct_pos": 70, "worst": -18.6},
            "fwd3m": {"n": 134, "median": 3.7, "pct_pos": 78, "worst": -15.9},
            "fwd12m": {"n": 133, "median": 12.9, "pct_pos": 78, "worst": -40.3},
        },
        "episodes": 16,
        "read": "NOT a sell signal — momentum usually continues (78% positive 3m). "
                "But this state owns the study's worst left tail (-40.3% worst 12m): "
                "when crowded positioning breaks, it breaks hard.",
        "action": "Don't ADD leverage here. Keep position sizes honest and stops "
                  "live; the payoff for chasing this state is baseline returns with "
                  "a fatter tail.",
    },
    "CALM": {
        "label": "No leverage stress signal either direction",
        "stats": {
            "fwd1m": {"n": 737, "median": 1.3, "pct_pos": 64, "worst": -28.8},
            "fwd3m": {"n": 734, "median": 3.7, "pct_pos": 71, "worst": -36.1},
            "fwd12m": {"n": 706, "median": 13.1, "pct_pos": 80, "worst": -46.3},
        },
        "episodes": 23,
        "read": "Baseline returns. Note 2008 began from CALM — this gauge reads "
                "flow stress, it does not predict slow-building tops (that is the "
                "monthly chart's job).",
        "action": "Defer to the monthly Leverage Cycle state below for positioning.",
    },
}

# One-liners for fast-state x slow-state (monthly FINRA) combinations. The
# frontend picks [fast][slow]; these are interpretation, not backtested stats.
CROSS_READ = {
    "FLUSH": {
        "BLOWOFF": "The unwind of a blowoff has begun — fast money is being forced "
                   "out first. Expect the monthly line to print SQUEEZE within 1-2 "
                   "prints; don't sell the climax week itself.",
        "ELEVATED": "Elevated leverage meeting forced selling — the fast gauge is "
                    "doing the monthly gauge's de-risking for it.",
        "NEUTRAL": "A flow shock without a leverage cycle behind it — historically "
                   "these resolve up quickly.",
        "SQUEEZE": "Monthly squeeze plus active flushing: late-stage capitulation.",
        "WASHOUT": "Full-cycle washout climax — historically bottom territory.",
    },
    "WASHED_OUT": {
        "BLOWOFF": "Divergence: weekly positioning already flushed while the monthly "
                   "gauge still reads BLOWOFF — the monthly is lagging (it usually "
                   "does by 1-2 months). The fast gauge front-runs the SQUEEZE print.",
        "ELEVATED": "Fast leverage already reset while the monthly cycle cools — "
                    "constructive divergence.",
        "NEUTRAL": "Fast positioning washed in a neutral cycle — historically the "
                   "best forward-return configuration in the study.",
        "SQUEEZE": "Both clocks agree the leverage is OUT — historically the "
                   "re-entry configuration.",
        "WASHOUT": "Both gauges at maximum washout — where cycle bottoms form.",
    },
    "RISK_BUILD": {
        "BLOWOFF": "The dangerous combo: the monthly cycle blowing off AND weekly "
                   "positioning crowded long. Both dials at max — this is where the "
                   "study's worst tails live. Tighten first, before the crowd.",
        "ELEVATED": "Leverage building on both clocks — fragility compounding.",
        "NEUTRAL": "Fast money crowding in early — watch the monthly gauge for the "
                   "cycle to follow.",
        "SQUEEZE": "Fast money re-crowding while the monthly squeeze completes — "
                   "early-cycle re-leveraging, historically benign.",
        "WASHOUT": "Speculative re-entry into a washed-out cycle — how recoveries "
                   "start.",
    },
    "CALM": {
        "BLOWOFF": "The monthly cycle reads BLOWOFF but nothing is being forced yet "
                   "— the build-up is real, the break hasn't started. The strip's "
                   "job now is to catch the FIRST week it starts (watch for FLUSH).",
        "ELEVATED": "Cycle elevated, flows quiet — watch, don't act.",
        "NEUTRAL": "Nothing to see on either clock.",
        "SQUEEZE": "Cycle resetting quietly — constructive.",
        "WASHOUT": "Washout complete, flows stabilized — bottoms form here.",
    },
}

RELATIONSHIP = (
    "Same leverage animal, three clocks. The monthly chart below (FINRA, ~3-4 "
    "week lag) reads the CYCLE: how much borrowed money the whole market has "
    "built up. This strip reads the FLOW: whether leverage is being forced out "
    "right now — hedge-fund futures positioning (weekly), vol shock (daily), "
    "crypto perp funding/open interest (hourly). In a fast washout the sequence "
    "runs: crypto funding flips (hours) -> futures positioning unwinds (weeks) "
    "-> the FINRA line confirms (1-2 months later). The strip states are "
    "mean-reversion signals at weeks-to-months horizons; the monthly states "
    "are regime signals at quarters. When they disagree, the strip is early "
    "and the monthly is confirming."
)


def _z_series(vals: list[float], window: int = 156, min_n: int = 52
              ) -> list[float | None]:
    """Trailing z-score per point (window incl. current), None until min_n."""
    from statistics import mean, pstdev
    out: list[float | None] = []
    for i in range(len(vals)):
        w = vals[max(0, i - window + 1):i + 1]
        if len(w) < min_n:
            out.append(None)
            continue
        sd = pstdev(w)
        out.append(round((vals[i] - mean(w)) / sd, 2) if sd > 1e-9 else 0.0)
    return out


def _d20(dates: list[date], vals: list[float | None]) -> float | None:
    """Change over the last 20 non-None observations (~20 business days)."""
    pts = [v for v in vals if v is not None]
    return round(pts[-1] - pts[-21], 2) if len(pts) >= 21 else None


def fast_state(z: float | None, dz4: float | None, vix20: float | None
               ) -> str | None:
    """Pre-registered composite rules — order matters."""
    t = FAST_THRESHOLDS
    if z is None or dz4 is None or vix20 is None:
        return None
    if vix20 >= t["flush_vix20"] and dz4 <= t["flush_dz4"]:
        return "FLUSH"
    if z <= t["washed_z"] and vix20 <= t["washed_vix20"]:
        return "WASHED_OUT"
    if z >= t["build_z"] and vix20 <= t["build_vix20"]:
        return "RISK_BUILD"
    return "CALM"


def _persist_oi_snapshot(oi_usd: float | None) -> list[dict]:
    """Upsert today's BTC perp OI into SeriesObs and return the accrued daily
    history. Survives restarts; resets only if the DB does."""
    from ..store.db import SessionLocal
    from ..store.models import SeriesObs
    today = date.today()
    out: list[dict] = []
    try:
        with SessionLocal() as s:
            if oi_usd is not None:
                row = (s.query(SeriesObs)
                       .filter_by(series_id="deribit_btc_oi", date=today).first())
                if row is None:
                    s.add(SeriesObs(series_id="deribit_btc_oi", source="deribit",
                                    date=today, value=oi_usd))
                else:
                    row.value = oi_usd
                s.commit()
            rows = (s.query(SeriesObs).filter_by(series_id="deribit_btc_oi")
                    .order_by(SeriesObs.date).all())
            out = [{"date": r.date.isoformat(), "oi_usd": r.value} for r in rows]
    except Exception:  # noqa: BLE001 — a broken DB must not take the strip down
        if oi_usd is not None:
            out = [{"date": today.isoformat(), "oi_usd": oi_usd}]
    return out


@router.get("/margin/fast")
def margin_fast():
    bundle = fetch_bundle()

    # --- COT leg (weekly) ----------------------------------------------------
    cd, cv = fetch_emini_leveraged()
    zs = _z_series(cv, FAST_THRESHOLDS["z_window_weeks"], FAST_THRESHOLDS["z_min_weeks"])
    cot_series = [{"date": d.isoformat(), "pct": round(p, 1), "z": z}
                  for d, p, z in zip(cd, cv, zs)][-104:]  # 2y of weeks
    cot_z = next((z for z in reversed(zs) if z is not None), None)
    known_z = [z for z in zs if z is not None]
    cot_dz4 = (round(known_z[-1] - known_z[-5], 2) if len(known_z) >= 5 else None)

    # --- VIX leg (daily) -----------------------------------------------------
    vd, vv = bundle.get("vix", ([], []))
    vix_pts = [(d, v) for d, v in zip(vd, vv) if v is not None]
    vix20 = (round(vix_pts[-1][1] - vix_pts[-21][1], 1)
             if len(vix_pts) >= 21 else None)
    vix_series = [{"date": d.isoformat(), "vix": v} for d, v in vix_pts[-252:]]

    # --- HY OAS (daily, display-only: FRED caps ICE BofA history at ~3y) -----
    hd, hv = bundle.get("hy_oas", ([], []))
    hy_pts = [(d, v * 100.0) for d, v in zip(hd, hv) if v is not None]  # bp
    hy20 = (round(hy_pts[-1][1] - hy_pts[-21][1]) if len(hy_pts) >= 21 else None)
    hy_series = [{"date": d.isoformat(), "bp": round(v)} for d, v in hy_pts[-252:]]

    # --- BTC leg (hourly funding, OI snapshots) ------------------------------
    perp = fetch_btc_perp()
    fdates, fvals = fetch_funding_history(days=30)
    funding_series = [{"date": d.isoformat(), "ann_pct": v}
                      for d, v in zip(fdates, fvals)]
    oi_series = _persist_oi_snapshot(perp["oi_usd"] if perp else None)

    state = fast_state(cot_z, cot_dz4, vix20)
    return {
        "state": state,
        "playbook": FAST_PLAYBOOK,
        "cross_read": CROSS_READ,
        "relationship": RELATIONSHIP,
        "thresholds": FAST_THRESHOLDS,
        "cot": {"series": cot_series, "z": cot_z, "dz4": cot_dz4,
                "pct": round(cv[-1], 1) if cv else None,
                "date": cd[-1].isoformat() if cd else None,
                "cadence": "weekly (Tue data, Fri release)"},
        "vix": {"series": vix_series, "d20": vix20,
                "current": vix_pts[-1][1] if vix_pts else None,
                "date": vix_pts[-1][0].isoformat() if vix_pts else None,
                "cadence": "daily (EOD)"},
        "hy": {"series": hy_series, "d20_bp": hy20,
               "current_bp": round(hy_pts[-1][1]) if hy_pts else None,
               "date": hy_pts[-1][0].isoformat() if hy_pts else None,
               "cadence": "daily (EOD, display-only)"},
        "btc": {"perp": perp, "funding_series": funding_series,
                "oi_series": oi_series,
                "cadence": "hourly funding; OI snapshot per refresh"},
        "baseline": {"fwd1m": {"median": 1.4, "pct_pos": 65},
                     "fwd3m": {"median": 3.7, "pct_pos": 71},
                     "fwd12m": {"median": 13.1, "pct_pos": 81}},
        "note": "Composite state uses COT + VIX only (both have 2006+ history; "
                "rules pre-registered, single evaluation, no tuning loop — "
                "MARGIN_DEBT.md). BTC funding/OI and HY OAS are display legs: "
                "faster confirmation, no backtested stats. Weekly-obs stats "
                "overlap; episode counts are the honest sample size.",
    }
