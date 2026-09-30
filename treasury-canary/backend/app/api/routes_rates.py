"""GET /rates/shock — long-yield shock x stock-bond-correlation regime.

Answers "the 30y just moved X bp — what did that historically mean for stocks
and recession odds?" with the regime nuance the folk model misses: whether
rising yields hurt stocks depends on whether bonds currently hedge stocks
(the correlation regime), and the validated signal turns out to be yield
PLUNGES, not spikes.

Study (RATE_SHOCK.md): pre-registered, weekly obs 1977-2026 (2,480), long
yield = DGS30 spliced with DGS20 over the 2002-06 discontinuation, shock =
60-business-day change, corr regime = rolling 60d corr of SPX returns vs
bond-price returns. Stats FROZEN from one evaluation; bootstrap evidence per
cell (BH-FDR q=0.10 over the 9 matrix cells).
"""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.crossasset import _aligned_returns, _rolling_corr
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["rates"])

RATE_THRESHOLDS = {"spike_bp": 75.0, "plunge_bp": -75.0, "window_bdays": 60,
                   "corr_pos": 0.2, "corr_neg": -0.2,
                   # alert hysteresis (studies/rate-spike-recession.md, A6):
                   # WARN fires on a crossing up through +75 and re-arms only
                   # below +60; the untested "approaching" INFO at +60 carries
                   # no odds claim and re-arms below +45.
                   "rearm_bp": 60.0, "approach_bp": 60.0, "approach_rearm_bp": 45.0}

# The recession evidence behind the +75bp line, re-tested 2026-09-30
# (studies/rate-spike-recession.md: pre-registered, power measured first, two
# independent verifiers). Unit = the spike EPISODE (alerts < 26 weeks apart are
# one episode — the same unit the alert uses for "re-crossing"); outcome = a
# recession beginning within 12 months that a real-time reader could not yet
# have known about. It REPLACES RATE_SHOCK's "44% vs 21%": of the 68 spike
# weeks that figure scored as hits, 64 were 1979-82 and 4 fell inside the
# already-announced 2008-09 recession; the other 83 spike weeks had none (vs a
# 14% base). Per ALERT the record is 10 of 33 (8 onsets after the alert, 2
# inside the 1981 recession before it was announced) — 8 of those 10 are
# repeat crossings within two Volcker episodes, which is why the episode is
# the unit quoted.
RATE_SPIKE_RECESSION = {
    "episodes": 20, "episode_hits": 3, "episode_rate_pct": 15, "base_pct": 20,
    "hits_by": "1990",
    "since_1990": {"from": "1990-04", "episodes": 13, "hits": 0},
    "alerts": {"n": 33, "hits": 10, "lead": 8, "late": 2},
    "gate_2x": "fail",
    "ex_volcker_ratio": 0.53,
    "beyond_curve": "inseparable",     # spike term p=0.49 once the curve is in
    "power_note": "with 6 recessions since 1977 even a true tripling of "
                  "recession risk after a spike would be confirmed ~1 time in 9",
}
SAME_EPISODE_DAYS = 182


def _curve_clause(curve_prob_pct: float | None) -> str:
    if curve_prob_pct is None:
        return " Yield-curve recession model: unavailable right now."
    return (f" Yield-curve recession model: {curve_prob_pct:.0f}% for the next 12 "
            f"months — that is the number to weigh.")


def spike_alert_template(curve_prob_pct: float | None) -> str:
    """spike_alert_text as a str.format template with {d60} — the event
    detector fills in the value AT THE CROSSING, not today's."""
    return spike_alert_text(None, curve_prob_pct)


def spike_alert_text(d60_bp: float | None, curve_prob_pct: float | None) -> str:
    """Words on the phone for the FIRST crossing of an episode. Every clause is
    a measured fact from RATE_SPIKE_RECESSION — no 'odds doubled', and nothing
    implying spikes now LOWER the odds (that would be a post-hoc subsample).
    d60_bp=None returns a template with a {d60} field."""
    r = RATE_SPIKE_RECESSION
    move = "{d60:+.0f}" if d60_bp is None else f"{d60_bp:+.0f}"
    return (f"The 30-year yield rose {move}bp in 60 trading days, past the +75bp "
            f"spike line. History: a recession began within 12 months after "
            f"{r['episode_hits']} of {r['episodes']} past spike episodes "
            f"({r['episode_rate_pct']}%, vs {r['base_pct']}% for a random day), all by "
            f"{r['hits_by']}; none of the {r['since_1990']['episodes']} since. Too few "
            f"recessions to confirm or rule out a link.{_curve_clause(curve_prob_pct)}")


def spike_recross_template(curve_prob_pct: float | None) -> str:
    """A crossing within SAME_EPISODE_DAYS of the previous one (A6): no history
    line repeated as fresh news. Fields: {d60}, {prev}."""
    return ("Re-crossing in the same spike episode (first crossed {prev}): the "
            "30-year is up {d60:+.0f}bp in 60 trading days. Nothing new in the "
            "historical record." + _curve_clause(curve_prob_pct))


def spike_line_label() -> str:
    r = RATE_SPIKE_RECESSION
    return (f"spike +75bp · recession followed {r['episode_hits']}/{r['episodes']} "
            f"episodes, all ≤{r['hits_by']}")


# Frozen study output. Baseline (all 2,480 weeks): recession within 12m 21%;
# fwd12m median +12.0% / 79% positive / worst -46.3.
RATE_BASELINE = {"n": 2480, "rec_12m_pct": 21,
                 "fwd1m": {"median": 1.2, "pct_pos": 63, "worst": -28.8},
                 "fwd3m": {"median": 3.0, "pct_pos": 69, "worst": -41.8},
                 "fwd12m": {"median": 12.0, "pct_pos": 79, "worst": -46.3}}

RATE_SHOCK_STATS = {
    # rec_12m_pct is RATE_SHOCK's week-level ANY12 figure, kept as the frozen
    # record; the alert and copy use RATE_SPIKE_RECESSION instead.
    "SPIKE": {"n": 151, "episodes": 24, "rec_12m_pct": 44,
              "fwd12m": {"median": 12.1, "pct_pos": 64, "worst": -16.9},
              "label": "long yield +75bp or more in 60 trading days",
              "rec_note": "week-level count (64 of its 68 hit-weeks are "
                          "1979-82); re-tested per episode: 3 of 20, all by "
                          "1990, none of 13 since"},
    "PLUNGE": {"n": 154, "episodes": 22, "rec_12m_pct": 32,
               "fwd12m": {"median": 22.1, "pct_pos": 97, "worst": -25.0},
               "label": "long yield -75bp or more in 60 trading days"},
    "NEUTRAL": {"n": 2175, "episodes": 30, "rec_12m_pct": 19,
                "fwd12m": {"median": 11.2, "pct_pos": 79, "worst": -46.3},
                "label": "no large long-yield move"},
}

RATE_MATRIX = {
    "SPIKE": {
        "POS": {"n": 112, "episodes": 15, "rec_12m_pct": 47,
                "fwd12m": {"median": 11.5, "pct_pos": 62, "worst": -16.5},
                "evidence": "NOT significant for stocks (p=0.21): returns near "
                            "baseline with a milder worst case. The recession "
                            "column (47%) counts overlapping weeks, nearly all "
                            "1979-82; re-tested per episode, a recession followed "
                            "3 of 20 spike episodes, all by 1990, none of 13 since."},
        "MIXED": {"n": 32, "episodes": 9, "rec_12m_pct": 28,
                  "fwd12m": {"median": 9.4, "pct_pos": 66, "worst": -16.9},
                  "evidence": "small sample, not significant"},
        "NEG": {"n": 7, "episodes": 2, "rec_12m_pct": 71,
                "fwd12m": {"median": 42.7, "pct_pos": 100, "worst": 19.2},
                "evidence": "passes FDR but rests on 2 Volcker-era episodes — "
                            "treat as historical curiosity, not a rule"},
    },
    "PLUNGE": {
        "POS": {"n": 102, "episodes": 13, "rec_12m_pct": 25,
                "fwd12m": {"median": 21.2, "pct_pos": 100, "worst": 0.1},
                "evidence": "VALIDATED (p<0.001, FDR-pass, 13 episodes): every "
                            "one of 102 weeks saw the S&P higher 12 months on — "
                            "yield relief in a no-hedge regime is the study's "
                            "strongest buy configuration"},
        "MIXED": {"n": 20, "episodes": 6, "rec_12m_pct": 60,
                  "fwd12m": {"median": 13.8, "pct_pos": 85, "worst": -25.0},
                  "evidence": "not significant; note the 60% recession rate — a "
                              "plunge here is often the recession arriving"},
        "NEG": {"n": 32, "episodes": 7, "rec_12m_pct": 38,
                "fwd12m": {"median": 25.1, "pct_pos": 97, "worst": -2.8},
                "evidence": "validated (p=0.029, FDR-pass): flight-to-quality "
                            "resolutions favored stocks strongly"},
    },
    "NEUTRAL": {
        "POS": {"n": 837, "episodes": 44, "rec_12m_pct": 16,
                "fwd12m": {"median": 12.6, "pct_pos": 84, "worst": -23.7},
                "evidence": "baseline-like (p=0.35)"},
        "MIXED": {"n": 501, "episodes": 63, "rec_12m_pct": 14,
                  "fwd12m": {"median": 8.9, "pct_pos": 78, "worst": -34.3},
                  "evidence": "baseline"},
        "NEG": {"n": 837, "episodes": 28, "rec_12m_pct": 24,
                "fwd12m": {"median": 10.9, "pct_pos": 74, "worst": -46.3},
                "evidence": "baseline-like; the deep tails (2008) lived here"},
    },
}


def shock_state(d60_bp: float | None) -> str | None:
    if d60_bp is None:
        return None
    if d60_bp >= RATE_THRESHOLDS["spike_bp"]:
        return "SPIKE"
    if d60_bp <= RATE_THRESHOLDS["plunge_bp"]:
        return "PLUNGE"
    return "NEUTRAL"


def corr_regime(c: float | None) -> str | None:
    if c is None:
        return None
    if c >= RATE_THRESHOLDS["corr_pos"]:
        return "POS"
    if c <= RATE_THRESHOLDS["corr_neg"]:
        return "NEG"
    return "MIXED"


def _summary(level, d60_bp, state, regime, cell) -> list[str]:
    """The written analytic — plain-English paragraphs for the panel."""
    out = []
    if level is None or state is None:
        return ["Long-yield data unavailable — the panel resumes when the "
                "30y series refreshes."]
    move = (f"risen {d60_bp:+.0f}bp" if d60_bp >= 0 else
            f"fallen {d60_bp:+.0f}bp")
    regime_txt = {
        "POS": "POSITIVE stock-bond correlation — bonds are NOT hedging "
               "stocks, so yield moves transmit straight into equity "
               "valuations (the 2022-style regime)",
        "NEG": "NEGATIVE stock-bond correlation — bonds are hedging stocks, "
               "so yield swings partly reflect growth news and rotations",
        "MIXED": "a MIXED stock-bond correlation regime",
    }.get(regime, "an unknown correlation regime")
    out.append(
        f"The 30y sits at {level:.2f}% and has {move} over the last 60 "
        f"trading days -> {state}. The market is in {regime_txt}.")
    if cell:
        f12 = cell["fwd12m"]
        out.append(
            f"Historically ({cell['episodes']} episodes, n={cell['n']} weeks "
            f"since 1977): this configuration saw the S&P higher 12 months "
            f"later {f12['pct_pos']}% of the time (median "
            f"{f12['median']:+.1f}%, worst {f12['worst']:+.1f}%) vs baseline "
            f"79% / +12.0%. Evidence: {cell['evidence']}.")
    r = RATE_SPIKE_RECESSION
    out.append(
        "The folk model — 'yields rise, so sell stocks and buy bonds' — does "
        "not hold up. SPIKES were not a reliable stock-sell signal: 12-month "
        "returns after them ran near baseline, with milder worst cases. Nor are "
        "they a demonstrated recession signal on their own: a recession began "
        f"within 12 months after {r['episode_hits']} of {r['episodes']} spike "
        f"episodes ({r['episode_rate_pct']}% vs {r['base_pct']}% for a random day), all "
        f"by {r['hits_by']}, none of the {r['since_1990']['episodes']} since — too few "
        "recessions to confirm or rule out a link, and it can't be separated from "
        "what the yield curve already says. The validated signal points the other "
        "way: yield PLUNGES — rate relief, especially in the no-hedge regime — "
        "preceded rising stocks almost without exception.")
    return out


def _live_curve_prob() -> float | None:
    """The dashboard's 12-month yield-curve recession probability, quoted next
    to every spike statement (spec A4)."""
    try:
        from ..metrics.recession_model import cached_models_and_spread, predict
        m, sp = cached_models_and_spread()
        if m.get(12) and sp is not None:
            return round(predict(m[12]["b0"], m[12]["b1"], m[12]["cov"], sp)
                         ["probability_pct"], 1)
    except Exception:  # noqa: BLE001
        pass
    return None


@router.get("/rates/shock")
def rates_shock():
    bundle = fetch_bundle()
    ld, lval = bundle.get("30y", ([], []))
    pts = [(d, v) for d, v in zip(ld, lval) if v is not None]
    level = pts[-1][1] if pts else None
    w = RATE_THRESHOLDS["window_bdays"]
    d60_bp = (round((pts[-1][1] - pts[-1 - w][1]) * 100, 0)
              if len(pts) > w else None)
    state = shock_state(d60_bp)

    cdates, sp_ret, bond_ret = _aligned_returns(
        bundle.get("sp500", ([], [])), bundle.get("10y", ([], [])))
    corr = _rolling_corr(sp_ret, bond_ret)
    cur_corr = next((c for c in reversed(corr) if c is not None), None)
    regime = corr_regime(cur_corr)

    cell = (RATE_MATRIX.get(state, {}).get(regime)
            if state and regime else None)

    # chart series: ~3y of long yield + the rolling 60-bday change
    series = []
    for i in range(max(0, len(pts) - 780), len(pts)):
        d, v = pts[i]
        series.append({"date": d.isoformat(), "yield": v,
                       "d60_bp": round((v - pts[i - w][1]) * 100)
                       if i >= w else None})

    return {
        "current": {"yield_30y": level, "d60_bp": d60_bp, "state": state,
                    "corr": round(cur_corr, 2) if cur_corr is not None else None,
                    "regime": regime,
                    "date": pts[-1][0].isoformat() if pts else None},
        "cell": cell,
        "summary": _summary(level, d60_bp, state, regime, cell),
        "series": series,
        "baseline": RATE_BASELINE,
        "shock_stats": RATE_SHOCK_STATS,
        "matrix": RATE_MATRIX,
        "thresholds": RATE_THRESHOLDS,
        "spike_recession": RATE_SPIKE_RECESSION,
        "curve_prob_pct": _live_curve_prob(),
        "spike_label": spike_line_label(),
        "note": "Frozen pre-registered study, 1977-2026 (RATE_SHOCK.md): "
                "weekly obs overlap; episode counts are the honest n; "
                "bootstrap evidence per cell with BH-FDR over 9 cells. Long "
                "yield spliced DGS30/DGS20; live state uses the same 60-bday "
                "window on the bundle's 30y series.",
    }
