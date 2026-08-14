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
        "evidence": "UNPROVEN: 3 episodes — bootstrap CI90 spans 20-100%. Direction only; the 5/5 one-month bounce is an anecdote, not a statistic.",
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
        "evidence": "VALIDATED — the one fully-proven claim in either monitor: episode bootstrap p=0.011 (CI90 87-99% vs 81% baseline), stable across split halves (94% pre-2017, 95% after).",
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
        "evidence": "Stats not distinguishable from baseline (p=0.84; halves disagree on direction). BUT the mechanical rule built on it — trim to 75% exposure in this state — improved MAR 0.156->0.164 and cut max drawdown 56.8%->53.6% (2007-2026): useful as sizing discipline, not prediction.",
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
        "evidence": "Baseline by construction.",
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

# ── 75-year stress-cycle x leverage-cycle study (MARGIN_DEBT.md §deep) ───────
# The positioning leg can't extend past 2006 (leveraged-fund COT starts there;
# equity futures 1982). The STRESS leg can: realized 20d vol of daily ^GSPC
# proxies the VIX leg back to 1951. States pre-registered to mirror the modern
# thresholds, evaluated once, crossed with the monthly leverage state.
# 3,803 weekly obs 1951-2026. Baseline: 12m median +10.3% / 74% pos / worst
# -46.3; 1m median +1.1% / 62%.
DEEP_THRESHOLDS = {"shock_dv20": 8.0, "aftershock_vz": 1.0, "aftershock_dv20": 0.0,
                   "complacent_vz": -0.75, "complacent_dv20": 2.0,
                   "vz_window_days": 756, "vz_min_days": 252}

DEEP_STATES = {
    "SHOCK": {"label": "vol spiking — deleveraging shock in progress",
              "fwd1m": {"n": 202, "median": 1.6, "pct_pos": 65, "worst": -20.9},
              "fwd12m": {"n": 201, "median": 14.5, "pct_pos": 76, "worst": -44.0},
              "episodes": 76},
    "AFTERSHOCK": {"label": "vol elevated but fading — stress clearing",
                   "fwd1m": {"n": 144, "median": 2.3, "pct_pos": 69, "worst": -14.0},
                   "fwd12m": {"n": 144, "median": 17.1, "pct_pos": 72, "worst": -46.3},
                   "episodes": 45},
    "COMPLACENT": {"label": "vol bottom-decile quiet — leverage builds silently",
                   "fwd1m": {"n": 895, "median": 0.7, "pct_pos": 60, "worst": -14.4},
                   "fwd12m": {"n": 889, "median": 7.7, "pct_pos": 72, "worst": -33.5},
                   "episodes": 139},
    "NORMAL": {"label": "vol unremarkable",
               "fwd1m": {"n": 2558, "median": 1.1, "pct_pos": 62, "worst": -28.8},
               "fwd12m": {"n": 2519, "median": 10.9, "pct_pos": 75, "worst": -42.6},
               "episodes": 107},
}

# matrix[stress][slow] — fwd S&P from each weekly obs; episode counts are the
# honest n. Headline cells: COMPLACENT x BLOWOFF (calm vol on a blown-off cycle
# = the fragile combo, 49% pos 12m vs 74% baseline over 30 episodes),
# COMPLACENT x WASHOUT (bear-market lull — 11% pos, median -19.6%),
# AFTERSHOCK x SQUEEZE (the re-entry cell — 89% pos, median +22.7%),
# SHOCK x BLOWOFF (climax weeks: 3m was positive in all 18).
DEEP_MATRIX = {
    "SHOCK": {
        "BLOWOFF": {"n": 18, "episodes": 10, "evidence": "DEMOTED: 12m p=0.87 and split halves flip (100% vs 58%) — the 3m 18/18 is descriptive of a small sample, not a validated edge", "fwd3m": {"median": 6.2, "pct_pos": 100, "worst": 0.1}, "fwd12m": {"median": 19.3, "pct_pos": 71, "worst": -12.5}},
        "ELEVATED": {"n": 20, "episodes": 9, "fwd3m": {"median": 3.5, "pct_pos": 60, "worst": -11.3}, "fwd12m": {"median": 13.1, "pct_pos": 70, "worst": -44.0}},
        "NEUTRAL": {"n": 75, "episodes": 32, "fwd3m": {"median": 4.6, "pct_pos": 72, "worst": -13.5}, "fwd12m": {"median": 13.6, "pct_pos": 80, "worst": -43.1}},
        "SQUEEZE": {"n": 42, "episodes": 19, "fwd3m": {"median": 3.8, "pct_pos": 69, "worst": -26.4}, "fwd12m": {"median": 16.1, "pct_pos": 76, "worst": -40.7}},
        "WASHOUT": {"n": 47, "episodes": 17, "fwd3m": {"median": 3.7, "pct_pos": 70, "worst": -14.7}, "fwd12m": {"median": 13.0, "pct_pos": 72, "worst": -32.6}},
    },
    "AFTERSHOCK": {
        "BLOWOFF": {"n": 13, "episodes": 8, "fwd3m": {"median": 2.1, "pct_pos": 77, "worst": -6.4}, "fwd12m": {"median": 8.5, "pct_pos": 54, "worst": -24.9}},
        "ELEVATED": {"n": 20, "episodes": 7, "fwd3m": {"median": 2.0, "pct_pos": 60, "worst": -6.9}, "fwd12m": {"median": -3.1, "pct_pos": 50, "worst": -46.3}},
        "NEUTRAL": {"n": 39, "episodes": 15, "fwd3m": {"median": 8.7, "pct_pos": 87, "worst": -10.4}, "fwd12m": {"median": 18.5, "pct_pos": 79, "worst": -40.9}},
        "SQUEEZE": {"n": 36, "episodes": 15, "evidence": "suggestive: p=0.067; above baseline in half 1 (100% vs 69), roughly at baseline in half 2 (78% vs 80)", "fwd3m": {"median": 7.0, "pct_pos": 81, "worst": -30.1}, "fwd12m": {"median": 22.7, "pct_pos": 89, "worst": -38.3}},
        "WASHOUT": {"n": 36, "episodes": 9, "fwd3m": {"median": 3.9, "pct_pos": 61, "worst": -19.6}, "fwd12m": {"median": 14.2, "pct_pos": 64, "worst": -26.8}},
    },
    "COMPLACENT": {
        "BLOWOFF": {"n": 152, "episodes": 30, "evidence": "suggestive: p=0.06 (misses FDR q=0.10) but below baseline in BOTH split halves (47% vs 69; 56% vs 80), and the sizing rule using it edged out buy-and-hold", "fwd3m": {"median": 0.5, "pct_pos": 55, "worst": -13.9}, "fwd12m": {"median": -0.2, "pct_pos": 49, "worst": -33.5}},
        "ELEVATED": {"n": 129, "episodes": 29, "fwd3m": {"median": 0.3, "pct_pos": 52, "worst": -15.1}, "fwd12m": {"median": 3.9, "pct_pos": 71, "worst": -20.3}},
        "NEUTRAL": {"n": 454, "episodes": 77, "fwd3m": {"median": 2.8, "pct_pos": 70, "worst": -23.9}, "fwd12m": {"median": 9.6, "pct_pos": 81, "worst": -17.6}},
        "SQUEEZE": {"n": 141, "episodes": 34, "fwd3m": {"median": 2.6, "pct_pos": 68, "worst": -18.6}, "fwd12m": {"median": 12.6, "pct_pos": 78, "worst": -23.4}},
        "WASHOUT": {"n": 19, "episodes": 6, "evidence": "the only FDR-significant cell (p=0.002) — but all 6 episodes post-1989: no out-of-sample half exists", "fwd3m": {"median": -2.4, "pct_pos": 32, "worst": -20.1}, "fwd12m": {"median": -19.6, "pct_pos": 11, "worst": -24.3}},
    },
    "NORMAL": {
        "BLOWOFF": {"n": 396, "episodes": 34, "evidence": "UNSTABLE across halves: above baseline 1951-88 (75% vs 69), well below after 1989 (45% vs 80) — the cautionary read rests entirely on the modern era", "fwd3m": {"median": 2.7, "pct_pos": 71, "worst": -11.8}, "fwd12m": {"median": 6.6, "pct_pos": 64, "worst": -41.0}},
        "ELEVATED": {"n": 279, "episodes": 46, "fwd3m": {"median": 3.1, "pct_pos": 68, "worst": -15.5}, "fwd12m": {"median": 12.6, "pct_pos": 87, "worst": -40.3}},
        "NEUTRAL": {"n": 983, "episodes": 94, "fwd3m": {"median": 3.1, "pct_pos": 70, "worst": -28.3}, "fwd12m": {"median": 9.8, "pct_pos": 74, "worst": -41.2}},
        "SQUEEZE": {"n": 599, "episodes": 48, "fwd3m": {"median": 3.0, "pct_pos": 68, "worst": -41.8}, "fwd12m": {"median": 14.3, "pct_pos": 83, "worst": -39.1}},
        "WASHOUT": {"n": 305, "episodes": 17, "fwd3m": {"median": -0.8, "pct_pos": 46, "worst": -28.6}, "fwd12m": {"median": 10.1, "pct_pos": 64, "worst": -42.6}},
    },
}

DEEP_BASELINE = {"n": 3803,
                 "fwd1m": {"median": 1.1, "pct_pos": 62, "worst": -28.8},
                 # fwd3m corrected by adversarial QA: the first shipped values
                 # were transcribed from the unrestricted 1929+ run.
                 "fwd3m": {"median": 2.6, "pct_pos": 66, "worst": -41.8},
                 "fwd12m": {"median": 10.3, "pct_pos": 74, "worst": -46.3}}

DEEP_NOTE = (
    "USEFULNESS EVAL 2026-07 (MARGIN_DEBT.md): of 20 matrix cells, only "
    "COMPLACENT x WASHOUT survives FDR; COMPLACENT x BLOWOFF and AFTERSHOCK x "
    "SQUEEZE are suggestive with stable direction; SHOCK x BLOWOFF and the "
    "current NORMAL x BLOWOFF cell did not replicate across halves. Cell "
    "evidence fields carry the verdicts. "
    "75y stress-cycle proxy (1951-2026): realized 20d vol of daily S&P stands "
    "in for the VIX/positioning legs, which don't exist before 1990/2006. "
    "States pre-registered mirroring the modern thresholds, evaluated once; "
    "weekly obs overlap — episode counts are the honest n. On the 2007-2026 "
    "overlap the proxy agrees with the modern COT+VIX composite 53% of weeks "
    "(it reads the stress half, not the positioning half) — treat the two as "
    "complementary, not interchangeable."
)


def stress_state(closes: list[float]) -> dict | None:
    """Live 75y-study stress state from daily closes (needs ~300+, uses last
    ~1100). Returns {state, rvol, vz, dv20} or None if too short."""
    from math import log, sqrt
    from statistics import mean, pstdev
    t = DEEP_THRESHOLDS
    px = [c for c in closes if c is not None][-1100:]
    if len(px) < t["vz_min_days"] + 42:
        return None
    rets = [log(px[i] / px[i - 1]) for i in range(1, len(px))]
    rvol = [None] * len(px)
    for i in range(21, len(px)):
        rvol[i] = pstdev(rets[i - 20:i]) * sqrt(252) * 100
    known = [v for v in rvol if v is not None]
    w = known[-t["vz_window_days"]:]
    if len(w) < t["vz_min_days"]:
        return None
    sd = pstdev(w)
    vz = (rvol[-1] - mean(w)) / sd if sd > 1e-9 else 0.0
    dv20 = rvol[-1] - rvol[-21]
    if dv20 >= t["shock_dv20"]:
        st = "SHOCK"
    elif vz >= t["aftershock_vz"] and dv20 <= t["aftershock_dv20"]:
        st = "AFTERSHOCK"
    elif vz <= t["complacent_vz"] and dv20 <= t["complacent_dv20"]:
        st = "COMPLACENT"
    else:
        st = "NORMAL"
    return {"state": st, "rvol": round(rvol[-1], 1), "vz": round(vz, 2),
            "dv20": round(dv20, 1)}


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


def _display_z(vals: list[float]) -> list[float | None]:
    """Full-sample z per point — the combined chart's shared sigma scale.

    Display normalization only (mean/sd of the whole served series); the COT
    signal z stays trailing-window and is computed separately."""
    from statistics import mean, pstdev
    if len(vals) < 2:
        return [None] * len(vals)
    m, sd = mean(vals), pstdev(vals)
    if sd <= 1e-9:
        return [0.0] * len(vals)
    return [round((v - m) / sd, 2) for v in vals]


def fast_state(z: float | None, dz4: float | None, vix20: float | None
               ) -> str | None:
    """Pre-registered composite rules (mutually exclusive given the
    thresholds; checked in study order for faithfulness)."""
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
    # Full history goes to the client (2006+, ~1050 pts): the combined chart
    # offers 2y windows and custom ranges. z here is the TRAILING signal z.
    cd, cv = fetch_emini_leveraged()
    zs = _z_series(cv, FAST_THRESHOLDS["z_window_weeks"], FAST_THRESHOLDS["z_min_weeks"])
    cot_series = [{"date": d.isoformat(), "pct": round(p, 1), "z": z}
                  for d, p, z in zip(cd, cv, zs)]
    cot_z = next((z for z in reversed(zs) if z is not None), None)
    known_z = [z for z in zs if z is not None]
    cot_dz4 = (round(known_z[-1] - known_z[-5], 2) if len(known_z) >= 5 else None)

    # --- VIX leg (daily) -----------------------------------------------------
    # ~3y so daily legs cover the same windows HY can (its history cap). Chart z
    # is full-sample (vs the whole fetched history) — a display normalization,
    # distinct from the COT trailing signal z.
    vd, vv = bundle.get("vix", ([], []))
    vix_pts = [(d, v) for d, v in zip(vd, vv) if v is not None]
    vix20 = (round(vix_pts[-1][1] - vix_pts[-21][1], 1)
             if len(vix_pts) >= 21 else None)
    vix_series = [{"date": d.isoformat(), "vix": v, "z": z}
                  for (d, v), z in zip(vix_pts[-780:],
                                       _display_z([v for _, v in vix_pts[-780:]]))]

    # --- HY OAS (daily, display-only: FRED caps ICE BofA history at ~3y) -----
    hd, hv = bundle.get("hy_oas", ([], []))
    hy_pts = [(d, v * 100.0) for d, v in zip(hd, hv) if v is not None]  # bp
    hy20 = (round(hy_pts[-1][1] - hy_pts[-21][1]) if len(hy_pts) >= 21 else None)
    hy_series = [{"date": d.isoformat(), "bp": round(v), "z": z}
                 for (d, v), z in zip(hy_pts[-780:],
                                      _display_z([v for _, v in hy_pts[-780:]]))]

    # --- BTC leg (hourly funding, OI snapshots) ------------------------------
    perp = fetch_btc_perp()
    fdates, fvals = fetch_funding_history(days=180)
    funding_series = [{"date": d.isoformat(), "ann_pct": v, "z": z}
                      for (d, v), z in zip(zip(fdates, fvals), _display_z(fvals))]
    oi_series = _persist_oi_snapshot(perp["oi_usd"] if perp else None)

    # --- 75y stress-cycle leg (live state + frozen matrix) -------------------
    from ..sources.fmp import fetch_spx_long
    spx_d, spx_v = fetch_spx_long()
    if not spx_d:  # no FMP key -> FRED's ~10y SP500 still feeds the live state
        spx_d, spx_v = bundle.get("sp500", ([], []))
    deep_live = stress_state(spx_v)
    deep = {
        "live": (dict(deep_live, date=spx_d[-1].isoformat()) if deep_live else None),
        "states": DEEP_STATES,
        "matrix": DEEP_MATRIX,
        "baseline": DEEP_BASELINE,
        "thresholds": DEEP_THRESHOLDS,
        "note": DEEP_NOTE,
    }

    # Historical composite state per COT week — the chart shades these bands
    # (FLUSH can't be drawn as a level line: it triggers on 20d CHANGES).
    vix_days = [d for d, _ in vix_pts]
    state_series = []
    import bisect as _bisect
    for i, d in enumerate(cd):
        if zs[i] is None or i < 4 or zs[i - 4] is None:
            continue
        vi = _bisect.bisect_right(vix_days, d) - 1
        if vi < 20:
            continue
        v20 = vix_pts[vi][1] - vix_pts[vi - 20][1]
        st_i = fast_state(zs[i], round(zs[i] - zs[i - 4], 2), round(v20, 1))
        if st_i:
            state_series.append({"date": d.isoformat(), "state": st_i})

    state = fast_state(cot_z, cot_dz4, vix20)
    return {
        "state": state,
        "state_series": state_series,
        "playbook": FAST_PLAYBOOK,
        "cross_read": CROSS_READ,
        "deep": deep,
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
