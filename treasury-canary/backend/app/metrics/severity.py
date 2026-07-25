"""Recession SEVERITY index — the gun-size gauge.

Answers "IF a recession arrives, how bad does the balance-sheet configuration
say it would be — and WHERE does the damage concentrate?" Distinct from timing
(curve/probit) and triggers (pin board).

Evidence base (each component's note cites its rationale):
  * Jorda-Schularick-Taylor: credit-boom recessions are deeper/slower.
  * Mian-Sufi-Verner: the 3-4y CHANGE in household debt/GDP predicts the bust.
  * Reinhart-Rogoff: banking-crisis recessions ~2-3x deeper.
  * Policy space bounds the rescue; structural dampeners bound the spiral.

Scoring: every component -> percentile of its full own history, oriented so
HIGHER = MORE severe conditions (0-100). Blocks average their live components.
    severity = 0.35*A + 0.25*B + 0.20*C + 0.20*F   (amplifiers)
               + 0.15*(D-50)                        (thin policy space worsens)
               - 0.15*(E-50)                        (dampeners soften)
clamped to 0-100. Class: <35 MILD · 35-60 MODERATE · >60 SEVERE.
No fitted weights — with ~5 fully-documented severe recessions, fitting would be
fiction. Weights are literature-informed and fully visible here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

Q3Y = 12   # 3 years of quarterly observations
W5Y = 260  # 5 years of weekly observations


@dataclass
class Component:
    comp_id: str
    label: str
    value: float | None
    unit: str
    score: float | None          # severity percentile, higher = worse
    note: str

    def as_dict(self) -> dict:
        return {"id": self.comp_id, "label": self.label, "value": self.value,
                "unit": self.unit, "score": self.score, "note": self.note}


@dataclass
class Block:
    block_id: str
    label: str
    components: list[Component] = field(default_factory=list)

    @property
    def score(self) -> float | None:
        live = [c.score for c in self.components if c.score is not None]
        return round(sum(live) / len(live), 1) if live else None

    def as_dict(self) -> dict:
        return {"id": self.block_id, "label": self.label, "score": self.score,
                "components": [c.as_dict() for c in self.components]}


# --- series helpers -----------------------------------------------------------

def _clean(pair) -> tuple[list[date], list[float]]:
    d, v = pair
    out_d, out_v = [], []
    for dd, vv in zip(d, v):
        if vv is not None:
            out_d.append(dd)
            out_v.append(vv)
    return out_d, out_v


def _pctile(hist: list[float], value: float | None, invert: bool = False) -> float | None:
    """Percentile of value in hist, oriented so higher = more severe."""
    if value is None or not hist:
        return None
    p = 100.0 * sum(1 for h in hist if h <= value) / len(hist)
    return round(100.0 - p if invert else p, 1)


def _ratio_series(num_pair, den_pair, num_scale: float = 1.0) -> tuple[list[date], list[float]]:
    """Align two series on nearest-not-after dates of the numerator's calendar."""
    nd, nv = _clean(num_pair)
    dd, dv = _clean(den_pair)
    if not nd or not dd:
        return [], []
    out_d, out_v = [], []
    j = 0
    for i, d in enumerate(nd):
        while j + 1 < len(dd) and dd[j + 1] <= d:
            j += 1
        if dd[j] <= d and dv[j]:
            out_d.append(d)
            out_v.append(num_scale * nv[i] / dv[j])
    return out_d, out_v


def _change_series(vals: list[float], lag: int) -> list[float]:
    return [vals[i] - vals[i - lag] for i in range(lag, len(vals))]


def _level_comp(cid, label, pair, unit, note, invert=False, scale=1.0) -> Component:
    _, v = _clean(pair)
    v = [x * scale for x in v]
    cur = v[-1] if v else None
    return Component(cid, label, round(cur, 2) if cur is not None else None, unit,
                     _pctile(v, cur, invert), note)


def _delta_comp(cid, label, series_vals, lag, unit, note, invert=False) -> Component:
    ch = _change_series(series_vals, lag) if len(series_vals) > lag else []
    cur = round(ch[-1], 2) if ch else None
    return Component(cid, label, cur, unit, _pctile(ch, cur, invert), note)


# --- the index -----------------------------------------------------------------

def build_severity(bundle: dict) -> dict:
    g = bundle.get

    # Block A — private leverage excess
    _, hh = _clean(g("hh_debt_gdp", ([], [])))
    _, pc_ratio = _ratio_series(g("priv_credit", ([], [])), g("gdp", ([], [])), 1.0)
    _, corp_ratio = _ratio_series(g("corp_debt", ([], [])), g("gdp", ([], [])), 100.0)
    # Margin debt: prefer FINRA's monthly stats (both $mm, ~one quarter timelier)
    # over the quarterly Z.1 security-credit series; fall back if unavailable.
    finra_margin = g("margin_debit", ([], []))
    margin_monthly = bool(finra_margin[0])
    margin_pair = finra_margin if margin_monthly else g("margin_debt", ([], []))
    _, margin_ratio = _ratio_series(margin_pair, g("gdp", ([], [])), 0.1)
    _, b50_ratio = _ratio_series(g("bottom50_nw", ([], [])), g("gdp", ([], [])), 0.1)
    A = Block("A", "Private leverage excess", [
        _delta_comp("hh_debt_3y", "Household debt/GDP, 3y change", hh, Q3Y, "pp",
                    "Mian-Sufi-Verner: THE severity predictor — the buildup rate, not the level."),
        _delta_comp("corp_debt_3y", "Corporate debt/GDP, 3y change", corp_ratio, Q3Y, "pp",
                    "JST credit-boom channel, corporate leg (milder than household unless it hits banks)."),
        _delta_comp("priv_credit_3y", "Private credit/GDP, 3y change", pc_ratio, Q3Y, "pp",
                    "Total private-sector credit impulse (BIS)."),
        _level_comp("dsr", "Household debt-service ratio", g("dsr", ([], [])), "% DPI",
                    "The FLOW burden that forces deleveraging. 2007: record high. Low = firewall."),
        _level_comp("saving_rate", "Personal saving rate", g("saving_rate", ([], [])), "%",
                    "The shock absorber: low savings = consumption cuts transmit 1:1.", invert=True),
        _delta_comp("margin_3y", "Margin debt/GDP, 3y change", margin_ratio,
                    36 if margin_monthly else Q3Y, "pp",
                    "Speculative leverage on the equity stock (FINRA margin debt; "
                    "Z.1 security credit as fallback)."),
        _delta_comp("bottom50_3y", "Bottom-50% net worth/GDP, 3y change", b50_ratio, Q3Y, "pp",
                    "Distributional buffer: the marginal consumer's balance sheet.", invert=True),
    ])

    # Block B — wealth at risk
    _, capgdp = _ratio_series(g("equity_liab", ([], [])), g("gdp", ([], [])), 0.1)
    _, px_inc = _ratio_series(g("med_house_px", ([], [])), g("med_income", ([], [])), 1.0)
    B = Block("B", "Asset overvaluation (wealth at risk)", [
        Component("equity_gdp", "Equity market cap / GDP",
                  round(capgdp[-1], 1) if capgdp else None, "%",
                  _pctile(capgdp, capgdp[-1] if capgdp else None),
                  "Buffett indicator: the wealth destroyed in a de-rating scales with this."),
        Component("house_px_inc", "Median house price / median income",
                  round(px_inc[-1], 2) if px_inc else None, "x",
                  _pctile(px_inc, px_inc[-1] if px_inc else None),
                  "Housing overvaluation vs the incomes that must service it."),
    ])

    # Block C — amplification (adds to SLOOS/HY/discount-window on the main tab)
    _, hy = _clean(g("hy_oas", ([], [])))
    C = Block("C", "Amplification", [
        _level_comp("delinq_cc", "Credit-card delinquency", g("delinq_cc", ([], [])), "%",
                    "Cracks already forming at the marginal borrower."),
        _level_comp("delinq_cre", "CRE delinquency", g("delinq_cre", ([], [])), "%",
                    "The 1990-recession channel; banks' concentrated exposure."),
        Component("hy_complacency", "HY spread complacency",
                  round(hy[-1] * 100, 0) if hy else None, "bps",
                  _pctile(hy, hy[-1] if hy else None, invert=True),
                  "TIGHT spreads = maximal repricing room when the cycle turns (loaded spring)."),
    ])

    # Block D — policy space (higher score = LESS space = worse)
    _, effr = _clean(g("effr", ([], [])))
    _, pce = _clean(g("core_pce", ([], [])))
    infl_yoy = (pce[-1] / pce[-13] - 1) * 100 if len(pce) > 13 else None
    infl_gap_hist = [max(0.0, (pce[i] / pce[i - 13] - 1) * 100 - 2.0)
                     for i in range(13, len(pce))]
    infl_gap = max(0.0, infl_yoy - 2.0) if infl_yoy is not None else None
    D = Block("D", "Policy space (divisor)", [
        _level_comp("fed_debt", "Federal debt / GDP", g("fed_debt_gdp", ([], [])), "%",
                    "Fiscal capacity for the rescue; Dalio's core constraint."),
        _level_comp("deficit", "Federal deficit / GDP", g("deficit_gdp", ([], [])), "%",
                    "Starting deficit: stimulus stacks on top of this.", invert=True),
        Component("mon_space", "Monetary space (fed funds level)",
                  round(effr[-1], 2) if effr else None, "%",
                  _pctile(effr, effr[-1] if effr else None, invert=True),
                  "Distance to zero = conventional cutting room. Low rate = thin space."),
        Component("infl_constraint", "Inflation constraint (core PCE − 2%)",
                  round(infl_gap, 2) if infl_gap is not None else None, "pp",
                  _pctile(infl_gap_hist, infl_gap),
                  "Above-target inflation handcuffs the Fed's response (the 2022 problem)."),
    ])

    # Block E — structural dampeners (higher score = MORE dampening = milder)
    _, mtg = _clean(g("mtg30", ([], [])))
    lock_gap_hist = [mtg[i] - sorted(mtg[max(0, i - W5Y):i + 1])[len(mtg[max(0, i - W5Y):i + 1]) // 2]
                     for i in range(len(mtg))] if mtg else []
    lock_gap = round(lock_gap_hist[-1], 2) if lock_gap_hist else None
    E = Block("E", "Structural dampeners", [
        _level_comp("inv_sales", "Inventories / sales", g("inv_sales", ([], [])), "x",
                    "The classic old-economy amplifier — low = less inventory-cycle fuel.",
                    invert=True),
        _level_comp("months_supply", "New-home months' supply", g("months_supply", ([], [])), "mo",
                    "2006 had an overhang; a shortage puts a floor under construction.",
                    invert=True),
        _level_comp("vac_rental", "Rental vacancy", g("vac_rental", ([], [])), "%",
                    "Low vacancies = housing demand floor.", invert=True),
        _level_comp("vac_owner", "Homeowner vacancy", g("vac_owner", ([], [])), "%",
                    "Ditto, owner stock.", invert=True),
        Component("lock_in", "Mortgage rate lock-in gap", lock_gap, "pp",
                  _pctile(lock_gap_hist, lock_gap),
                  "Current 30y rate minus trailing 5y median: high gap = outstanding stock "
                  "financed below market -> rate shocks transmit slowly (proxy)."),
    ])

    # Block F — boom concentration
    _, info_r = _ratio_series(g("capex_info", ([], [])), g("gdp", ([], [])), 100.0)
    _, soft_r = _ratio_series(g("capex_soft", ([], [])), g("gdp", ([], [])), 100.0)
    tech_share = ([a + b for a, b in zip(info_r, soft_r)]
                  if info_r and soft_r and len(info_r) == len(soft_r) else [])
    F = Block("F", "Boom concentration", [
        Component("tech_capex", "Info-processing + software capex / GDP",
                  round(tech_share[-1], 2) if tech_share else None, "%",
                  _pctile(tech_share, tech_share[-1] if tech_share else None),
                  "When one sector's capex IS the expansion, its stop IS the recession "
                  "(telecom 2001; AI/data centers now)."),
        _delta_comp("tech_capex_3y", "Tech capex share, 3y change", tech_share, Q3Y, "pp",
                    "The boom's acceleration — 2001's tell was the surge, not the level."),
    ])

    blocks = [A, B, C, D, E, F]

    # --- composite ---
    amp = {bl.block_id: bl.score for bl in (A, B, C, F)}
    live_amp = {k: v for k, v in amp.items() if v is not None}
    weights = {"A": 0.35, "B": 0.25, "C": 0.20, "F": 0.20}
    if live_amp:
        wsum = sum(weights[k] for k in live_amp)
        base = sum(weights[k] * v for k, v in live_amp.items()) / wsum
    else:
        base = None
    d_adj = 0.15 * ((D.score or 50) - 50)
    e_adj = -0.15 * ((E.score or 50) - 50)
    score = max(0.0, min(100.0, base + d_adj + e_adj)) if base is not None else None
    cls = (None if score is None else
           "MILD" if score < 35 else "MODERATE" if score < 60 else "SEVERE")

    # --- composition / impact-type match (transparent rules) ---
    def comp_score(block: Block, ids: list[str]) -> float | None:
        vals = [c.score for c in block.components if c.comp_id in ids and c.score is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    type_scores = {
        "household_leverage": comp_score(A, ["hh_debt_3y", "dsr", "for_ratio", "saving_rate",
                                             "bottom50_3y"]),
        "valuation_corporate": (lambda xs: round(sum(x for x in xs if x is not None) /
                                                 max(1, len([x for x in xs if x is not None])), 1)
                                if any(x is not None for x in xs) else None)(
            [B.score, comp_score(A, ["corp_debt_3y", "margin_3y"]), F.score]),
        "inflation_rates": comp_score(D, ["infl_constraint"]),
        "fiscal_constrained": comp_score(D, ["fed_debt", "deficit", "infl_constraint"]),
    }
    live_types = {k: v for k, v in type_scores.items() if v is not None}
    matched = max(live_types, key=live_types.get) if live_types else None

    return {
        "blocks": [bl.as_dict() for bl in blocks],
        "severity_score": round(score, 1) if score is not None else None,
        "severity_class": cls,
        "formula": {"base_amplifiers": round(base, 1) if base is not None else None,
                    "policy_space_adj": round(d_adj, 1), "dampener_adj": round(e_adj, 1),
                    "weights": weights,
                    "text": "0.35A + 0.25B + 0.20C + 0.20F + 0.15(D-50) - 0.15(E-50)"},
        "composition": {"type_scores": type_scores, "matched_type": matched},
        "note": "Conditional severity IF a recession arrives — not a probability. "
                "Structured prior from the credit-boom literature; ~5 well-documented "
                "severe events exist, so no weights are fitted. Exogenous shocks "
                "(2020) bypass this index by design.",
    }
