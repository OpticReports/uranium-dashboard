"""Dalio / Bridgewater economic environments.

Two views, both supported:

1. The 2x2 JOINT quadrant of a month: growth rising/falling x inflation
   rising/falling RELATIVE TO EXPECTATIONS.  Expectations are not observed, so
   the default definition proxies them with the trailing trend:
       growth_yoy_t    = INDPRO_t / INDPRO_{t-12} - 1        (FRED INDPRO, real activity)
       inflation_yoy_t = CPIAUCSL_t / CPIAUCSL_{t-12} - 1    (FRED CPIAUCSL)
       trend_t         = mean(yoy_{t-W}, ..., yoy_{t-1})       (W = 36 months, strictly trailing)
       surprise_t      = yoy_t - trend_t ;  rising <=> surprise_t > 0
   then shifted by ``release_lag`` months (default 1) so month m's label uses
   only data published by the end of month m.  FRED serves LATEST-VINTAGE data
   (revisions included), not real-time vintages (ALFRED): honest caveat.

2. The four All Weather BOXES (growth up, growth down, inflation up,
   inflation down), each meant to carry 25% of portfolio risk.  Streams map to
   boxes manually (stream.environments) or via the canonical asset-class map
   below, or empirically from betas to the surprises.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import percent_risk_contributions, validate_covariance
from .errors import ValidationError
from .streams import ENVIRONMENT_BOXES

BOXES = ENVIRONMENT_BOXES
QUADRANTS = ("growth_up_inflation_up", "growth_up_inflation_down",
             "growth_down_inflation_up", "growth_down_inflation_down")

#: All Weather canonical mapping (Bridgewater, "The All Weather Story", 2012;
#: spec mapping).  Corporate credit = rising growth; EM credit = rising growth
#: and rising inflation.  Crypto, private assets, cash: no canonical mapping.
CANONICAL_MAP = {
    "equity": ("growth_up", "inflation_down"),
    "nominal_bond": ("growth_down", "inflation_down"),
    "ilb": ("growth_down", "inflation_up"),
    "gold": ("inflation_up",),
    "commodity": ("growth_up", "inflation_up"),
    "credit": ("growth_up",),
    "em_credit": ("growth_up", "inflation_up"),
}
CANONICAL_SOURCE = "Bridgewater 'The All Weather Story' (2012) asset/environment map"


@dataclass(frozen=True)
class RegimeDefinition:
    """Parameters of the surprise classifier (see module docstring)."""
    growth_series: str = "INDPRO"
    inflation_series: str = "CPIAUCSL"
    yoy_periods: int = 12
    trend_window: int = 36
    release_lag: int = 1

    def describe(self) -> str:
        """One-line statement of the regime definition (printed with every environment table)."""
        return (f"growth = {self.growth_series} YoY vs its trailing {self.trend_window}m mean; "
                f"inflation = {self.inflation_series} YoY vs its trailing {self.trend_window}m mean; "
                f"rising = above trend; labels lagged {self.release_lag}m for publication; "
                "latest-vintage FRED data (revisions not real-time)")


def _monthly(s: pd.Series, what: str) -> pd.Series:
    s = pd.Series(s, dtype=float).dropna().sort_index()
    if not isinstance(s.index, pd.DatetimeIndex) or s.empty:
        raise ValidationError(f"{what}: need a non-empty dated series")
    return s.resample("ME").last().dropna()


def macro_surprises(growth_level: pd.Series, inflation_level: pd.Series,
                    definition: RegimeDefinition = RegimeDefinition()) -> pd.DataFrame:
    """Monthly YoY, trailing trend and surprise for growth and inflation
    (definition in the module docstring), lagged by release_lag."""
    d = definition
    out = {}
    for key, lv in (("growth", growth_level), ("inflation", inflation_level)):
        m = _monthly(lv, key)
        if (m <= 0).any():
            raise ValidationError(f"{key} level must be > 0")
        yoy = m / m.shift(d.yoy_periods) - 1.0
        trend = yoy.shift(1).rolling(d.trend_window, min_periods=d.trend_window).mean()
        out[f"{key}_yoy"] = yoy
        out[f"{key}_trend"] = trend
        out[f"{key}_surprise"] = yoy - trend
    df = pd.DataFrame(out).shift(d.release_lag).dropna()
    if df.empty:
        raise ValidationError("not enough macro history for the trend window")
    return df


def classify_regimes(surprises: pd.DataFrame) -> pd.Series:
    """Joint quadrant label per month from growth/inflation surprises
    (> 0 = rising; exactly 0 counts as falling)."""
    g = np.where(surprises["growth_surprise"] > 0, "growth_up", "growth_down")
    i = np.where(surprises["inflation_surprise"] > 0, "inflation_up", "inflation_down")
    return pd.Series([f"{a}_{b}" for a, b in zip(g, i)], index=surprises.index, name="quadrant")


def regimes_from_fred(loader, definition: RegimeDefinition = RegimeDefinition()) -> tuple[pd.DataFrame, dict]:
    """Fetch the two FRED series via ``loader`` and return (surprises with a
    'quadrant' column, provenance)."""
    g = loader.fred(definition.growth_series)
    i = loader.fred(definition.inflation_series)
    s = macro_surprises(g.values, i.values, definition)
    s["quadrant"] = classify_regimes(s)
    return s, {"growth": g.provenance.to_dict(), "inflation": i.provenance.to_dict(),
               "definition": definition.describe()}


def monthly_returns(levels: pd.DataFrame) -> pd.DataFrame:
    """Month-end-to-month-end simple returns from daily levels."""
    m = levels.resample("ME").last()
    return (m / m.shift(1) - 1.0).iloc[1:]


def quadrant_table(monthly: pd.DataFrame, regimes: pd.Series, *, rf_monthly: pd.Series | float = 0.0,
                   min_months: int = 6) -> pd.DataFrame:
    """Per stream x joint quadrant: months, annualised mean (mean x 12), vol
    (std x sqrt 12), excess-return Sharpe and hit rate.  Month m's return is
    paired with month m's label.  Cells with < min_months are reported with
    NaN statistics (too thin to read)."""
    reg = regimes.reindex(monthly.index)
    rf = rf_monthly if np.isscalar(rf_monthly) else pd.Series(rf_monthly).reindex(monthly.index)
    rows = []
    for col in monthly.columns:
        r = monthly[col]
        for q in QUADRANTS:
            sel = (reg == q) & r.notna()
            x = r[sel]
            ex = x - (rf if np.isscalar(rf) else rf[sel])
            n = int(sel.sum())
            ok = n >= min_months
            rows.append({
                "stream": col, "quadrant": q, "months": n,
                "ann_mean": float(x.mean() * 12) if ok else np.nan,
                "ann_vol": float(x.std(ddof=1) * np.sqrt(12)) if ok and n > 1 else np.nan,
                "sharpe": float(ex.mean() / ex.std(ddof=1) * np.sqrt(12)) if ok and n > 1 and ex.std(ddof=1) > 0 else np.nan,
                "hit_rate": float((x > 0).mean()) if ok else np.nan,
            })
    return pd.DataFrame(rows)


def environment_betas(monthly: pd.DataFrame, surprises: pd.DataFrame, min_months: int = 36) -> pd.DataFrame:
    """OLS per stream: r_t = a + b_g z_g,t + b_i z_i,t + e_t with z the
    STANDARDISED growth and inflation surprises (so betas are comparable: the
    return per 1-sd surprise).  Reports betas, t-stats (OLS SEs), R^2, months."""
    z = surprises[["growth_surprise", "inflation_surprise"]]
    z = (z - z.mean()) / z.std(ddof=1)
    rows = []
    for col in monthly.columns:
        df = pd.concat([monthly[col].rename("y"), z], axis=1, sort=True).dropna()
        n = len(df)
        if n < min_months:
            rows.append({"stream": col, "months": n, "beta_growth": np.nan, "t_growth": np.nan,
                         "beta_inflation": np.nan, "t_inflation": np.nan, "r2": np.nan})
            continue
        X = np.column_stack([np.ones(n), df["growth_surprise"], df["inflation_surprise"]])
        y = df["y"].to_numpy()
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ coef
        s2 = resid @ resid / (n - 3)
        se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
        r2 = 1 - resid @ resid / np.sum((y - y.mean()) ** 2)
        rows.append({"stream": col, "months": n, "beta_growth": coef[1], "t_growth": coef[1] / se[1],
                     "beta_inflation": coef[2], "t_inflation": coef[2] / se[2], "r2": r2})
    return pd.DataFrame(rows)


def exposures_from_mapping(names: list, mapping: dict) -> tuple[np.ndarray, list]:
    """(N x 4) box-exposure matrix over BOXES: a stream mapped to k boxes puts
    1/k of its risk in each.  Unmapped streams get a zero row and are returned
    in the second element."""
    M = np.zeros((len(names), len(BOXES)))
    unmapped = []
    for i, n in enumerate(names):
        boxes = mapping.get(n)
        if not boxes:
            unmapped.append(n)
            continue
        bad = [b for b in boxes if b not in BOXES]
        if bad:
            raise ValidationError(f"{n}: unknown boxes {bad}; use {BOXES}")
        for b in boxes:
            M[i, BOXES.index(b)] += 1.0 / len(boxes)
    return M, unmapped


def exposures_from_betas(betas: pd.DataFrame, names: list) -> tuple[np.ndarray, list]:
    """Empirical box exposures from environment_betas: the growth axis gets
    |b_g|/(|b_g|+|b_i|) of the stream's risk, in growth_up if b_g > 0 else
    growth_down; likewise inflation.  Heuristic: assumes a stream's risk is
    driven by the two surprises in proportion to its standardised betas."""
    M = np.zeros((len(names), len(BOXES)))
    unmapped = []
    b = betas.set_index("stream")
    for i, n in enumerate(names):
        if n not in b.index or not np.isfinite(b.loc[n, "beta_growth"]):
            unmapped.append(n)
            continue
        bg, bi = float(b.loc[n, "beta_growth"]), float(b.loc[n, "beta_inflation"])
        tot = abs(bg) + abs(bi)
        if tot == 0:
            unmapped.append(n)
            continue
        M[i, BOXES.index("growth_up" if bg > 0 else "growth_down")] += abs(bg) / tot
        M[i, BOXES.index("inflation_up" if bi > 0 else "inflation_down")] += abs(bi) / tot
    return M, unmapped


def stream_box_mapping(universe, names: list) -> tuple[dict, dict]:
    """Box mapping for streams from metadata: manual ``environments`` first,
    else CANONICAL_MAP[asset_class].  Returns (mapping, source_by_stream)."""
    mapping, src = {}, {}
    for n in names:
        s = universe[n]
        if s.environments:
            mapping[n], src[n] = tuple(s.environments), "manual"
        elif s.asset_class in CANONICAL_MAP:
            mapping[n], src[n] = CANONICAL_MAP[s.asset_class], f"canonical ({s.asset_class})"
    return mapping, src


def environment_balance(w, S, exposures, *, mu=None) -> dict:
    """Share of portfolio RISK (and, if mu given, expected RETURN) in each
    All Weather box.
        risk_share_k   = sum_i PRC_i M_ik          (PRC = percent risk contribution)
        return_share_k = sum_i w_i mu_i M_ik / sum_i w_i mu_i
    Unmapped streams' risk is reported as 'unmapped'.  Balance score vs the
    All Weather target of 25% per box, on the MAPPED risk renormalised:
        score = 1 - TV / 0.75,  TV = 1/2 sum_k |s_k - 1/4|
    (1 = perfectly balanced, 0 = all risk in one box)."""
    S = validate_covariance(S)
    w = np.asarray(w, float)
    M = np.asarray(exposures, float)
    if M.shape != (len(w), len(BOXES)):
        raise ValidationError(f"exposures must be (N, {len(BOXES)})")
    prc = percent_risk_contributions(w, S)
    risk = M.T @ prc
    mapped_risk = float(prc[M.sum(axis=1) > 0].sum())
    unmapped = 1.0 - mapped_risk
    s = risk / mapped_risk if mapped_risk > 0 else np.full(len(BOXES), np.nan)
    tv = 0.5 * float(np.nansum(np.abs(s - 0.25)))
    out = {
        "boxes": list(BOXES),
        "risk_share": dict(zip(BOXES, risk.tolist())),
        "risk_share_of_mapped": dict(zip(BOXES, s.tolist())),
        "unmapped_risk_share": unmapped,
        "target": 0.25,
        "balance_score": 1.0 - tv / 0.75 if mapped_risk > 0 else np.nan,
    }
    if mu is not None:
        mu = np.asarray(mu, float)
        contrib = w * mu
        tot = contrib.sum()
        out["return_share"] = dict(zip(BOXES, (M.T @ contrib / tot).tolist())) if tot != 0 else None
    return out
