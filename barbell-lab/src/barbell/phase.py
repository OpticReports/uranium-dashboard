"""Phase-aware allocation — SERVING side of PHASE_BARBELL_SPEC.md.

The study lives in research/phase_barbell.py; this module is the small
frozen core the dashboard needs: the pre-registered mapping table and the
weight rule (equity scaled by the risk slider, bonds absorb, never short,
gold only post-1971 — irrelevant live but kept for parity). A gate pins
MAPPING to the spec markdown AND to the research module.

SUGGESTION ONLY: nothing here places orders or talks to an executor. It
renders what the frozen study says today's phase implies.
"""
from __future__ import annotations

import time

import httpx

from .win_scores import WIN_SCORES
from .win_scores_industries import INDUSTRY_WIN_SCORES

INDUSTRY_ORDER = ["NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq",
                  "Telcm", "Utils", "Shops", "Hlth", "Money", "Other"]

CANARY = "https://treasury-canary.onrender.com"

MAPPING = {
    "EXPANSION":   {"stocks": 70, "bonds": 20, "gold": 5,  "cash": 5},
    "LATE_CYCLE":  {"stocks": 55, "bonds": 30, "gold": 10, "cash": 5},
    "STALL":       {"stocks": 45, "bonds": 35, "gold": 10, "cash": 10},
    "SLOWDOWN":    {"stocks": 30, "bonds": 45, "gold": 15, "cash": 10},
    "CONTRACTION": {"stocks": 20, "bonds": 50, "gold": 15, "cash": 15},
}
RISK_LEVELS = {"defensive": 0.5, "balanced": 1.0, "aggressive": 1.5}

# verifier-mandated captions (2026-08-11) for cells where the episode
# convention is >15pp sensitive or the story needs saying
CELL_NOTES = {
    "STALL|stocks|12": ("Convention-sensitive: 70% of 20 episode starts "
                        "beat cash, but 85% of all STALL months did - long "
                        "stalls mostly won; a fresh STALL signal's first "
                        "month won 14 of 20 times."),
    "CONTRACTION|stocks|6": ("50% is the first-signal-month rate; 13 of 14 "
                             "contraction episodes had a majority of "
                             "winning months. The signal fires "
                             "mid-drawdown, so 6-month windows from the "
                             "first month often sit inside the crash."),
    "CONTRACTION|stocks|12": ("Mostly recession-bottom rebounds (1958, "
                              "1982, 1990, 2020). The 3 losses came when "
                              "the signal fired early in a long bear "
                              "(1974, 2001, 2008). Descriptive, not a "
                              "bottom-timing forecast."),
    "LATE_CYCLE|bonds|12": ("10 of 12 late-cycle onsets came with rising "
                            "yields, mostly pre-1982; counting all episode "
                            "months gives 42%, and the base rate leans on "
                            "the post-1982 bond bull."),
}

# corrected, panel-approved study numbers (PHASE_BARBELL.md, 2026-08-11)
STUDY = {
    "window": "1935-01 → 2026-06 (91.5y, monthly, 10bp costs)",
    "rows": [
        ["Phase balanced", 8.39, -20.9, 0.71, -14.3],
        ["Phase aggressive", 9.67, -31.7, 0.70, -23.7],
        ["Phase defensive", 6.70, -15.7, 0.65, -6.1],
        ["60/40", 8.89, -27.1, 0.67, -14.5],
        ["S&P 500 total return", 11.34, -49.0, 0.64, -38.7],
    ],
    "caveat": ("Monthly-average (Shiller-convention) prices understate "
               "volatility and drawdowns for strategy and benchmarks alike. "
               "The Sharpe edge over 60/40 is thin and concentrated in "
               "1937, 1973-74, 2000-02 and 2008; over 1940-1981 (rising "
               "rates) the strategy UNDERPERFORMED 60/40 on CAGR and "
               "Sharpe, and its worst modern episode (2022, -16%) came "
               "when bonds - its main defensive sleeve - crashed. Labels "
               "use revised data; bond returns are synthetic; the "
               "2023-2026 defensive miss is included. Sequence-risk claim, "
               "not return alpha; does not cover bond-hostile inflationary "
               "regimes."),
}

_cache: dict = {}
_TTL = 6 * 3600


def weights_for(phase: str, risk: float) -> dict:
    row = MAPPING[phase]
    eq = min(95.0, max(0.0, row["stocks"] * risk),
             row["stocks"] + row["bonds"])
    bonds = row["bonds"] + (row["stocks"] - eq)
    gold, cash = row["gold"], row["cash"]
    tot = eq + bonds + gold + cash
    return {"stocks": round(eq / tot * 100, 1),
            "bonds": round(bonds / tot * 100, 1),
            "gold": round(gold / tot * 100, 1),
            "cash": round(cash / tot * 100, 1)}


def _get(path: str) -> dict | None:
    hit = _cache.get(path)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    try:
        r = httpx.get(f"{CANARY}{path}", timeout=60)
        r.raise_for_status()
        _cache[path] = (time.time(), r.json())
        return r.json()
    except Exception:  # noqa: BLE001
        return hit[1] if hit else None        # stale beats nothing


def board() -> dict:
    """Live phase + nowcast from the canary, the analog top-5 for the
    scenario toggle, and per-risk suggested weights."""
    cyc = _get("/cycle")
    ana = _get("/cycle/analog")
    cur = (cyc or {}).get("current") or {}
    phase = cur.get("phase")
    nowcast = (cyc or {}).get("nowcast") or {}
    out = {
        "phase": phase,
        "phase_month": cur.get("month"),
        "coincident": cur.get("coincident"),
        "leading": cur.get("leading"),
        "nowcast_phase": nowcast.get("phase"),
        "nowcast_month": nowcast.get("month"),
        "weights": {name: weights_for(phase, rv)
                    for name, rv in RISK_LEVELS.items()} if phase else None,
        "analogs": [
            {"month": a["month"], "phase_then": a["phase_then"],
             "closer_than_pct": a["closer_than_pct"],
             "weights": {name: weights_for(a["phase_then"], rv)
                         for name, rv in RISK_LEVELS.items()}
             if a.get("phase_then") else None,
             "recession_within_12m": a.get("recession_within_12m")}
            for a in (ana or {}).get("analogs", [])],
        "analog_caveats": {
            "episodes": (ana or {}).get("episodes"),
            "recent_calibration": (ana or {}).get("recent_calibration"),
        },
        "study": STUDY,
        "win_scores": {
            f"{a}|{h}": WIN_SCORES.get(f"{phase}|{a}|{h}")
            for a in ("stocks", "bonds", "gold") for h in (6, 12)
        } if phase else None,
        "win_score_caveat": ("Conditional win rates are descriptive "
                             "statistics of a small number of historical "
                             "episodes, not forecasts. Episode rate = the "
                             "FIRST month of each label spell (what a "
                             "decision-maker traded on); in 10 of 30 cells "
                             "it differs >15pp from counting every episode "
                             "month, so read it with its range, never "
                             "alone. Base rate is month-counted - compare "
                             "it with the month rate (the edge column "
                             "does); episode rates use a different "
                             "denominator and can sit on the other side "
                             "of base. Shiller monthly-average "
                             "total-return basis."),
        "win_score_notes": CELL_NOTES,
        "industry_win_scores": sorted(
            [{"industry": n, **INDUSTRY_WIN_SCORES[f"{phase}|{n}|12"],
              "h6": INDUSTRY_WIN_SCORES[f"{phase}|{n}|6"]}
             for n in INDUSTRY_ORDER],
            key=lambda c: -(c["month_pct"] - c["base_pct"]))
        if phase else None,
        "industry_caveat": ("Ken French 12-industry value-weighted "
                            "portfolios 1935-2026 (~XL tickers are "
                            "approximate modern equivalents, NOT tradeable "
                            "parity). Same conventions and caveats as the "
                            "asset table; ranked by month-counted edge vs "
                            "each industry's own base rate."),
        "canary_reachable": cyc is not None,
    }
    return out
