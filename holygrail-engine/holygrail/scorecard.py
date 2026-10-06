"""The Holy Grail scorecard for a book view.

Answers Dalio's four questions for the book as held:
  1. GOOD?          expected excess return > 0 and Sharpe >= threshold, per stream
  2. UNCORRELATED?  every N_eff measure, DR, implied average correlation
  3. RISK-BALANCED? risk share vs dollar share, concentration flags
  4. GEARED?        current vol vs target, leverage needed, Kelly
plus environment (All Weather box) balance and a mandatory HONESTY block.

``scorecard`` is pure (book + moments in, dict out); ``score_book`` adds the
data fetch.  The scorecard is a mean-variance snapshot: it is not a forecast.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .core import (cash_deployed, cash_premium_terms, effective_bets, geared_return, kelly_leverage, log_growth,
                   new_borrowing, percent_risk_contributions, prob_loss, risk_contributions, sharpe_ratio)
from .environments import BOXES, environment_balance, exposures_from_mapping, stream_box_mapping
from .errors import ValidationError
from .estimate import FREQ_PPY, aligned_returns, infer_periods_per_year
from .streams import Assumption, CashStream, CompositeStream, ParametricStream, build_moments

DALIO_TARGET_BETS = 15

NOT_MODELLED = [
    "taxes and trading costs (the scorecard is a static snapshot)",
    "fat tails, skew and jumps beyond the covariance (mean-variance view; forward.py simulates Student-t, bootstrap and default jumps)",
    "liquidity / lock-ups / redemption gates: illiquid positions are treated as tradable at their marks",
    "time variation of volatility and correlation: one estimation window (see robustness.py for regime and rolling views)",
    "currency risk: every value is USD",
    "path dependency of daily-reset leveraged composites (volatility decay) in arithmetic moments; the backtest compounds daily",
]


@dataclass
class ScoreSettings:
    """Scorecard knobs (book.settings keys of the same name override defaults)."""
    target_vol: float = 0.10
    position_flag: float = 0.10
    stream_risk_flag: float = 0.25
    good_sharpe: float = 0.20
    freq: str = "W"
    window_years: float = 5.0
    estimator: str = "lw_cc"
    halflife: float | None = None     # periods; required by estimator 'ewma'
    history: str = "common"
    end: str | None = None
    max_leverage: float = 3.0
    mu_mode: str = "assumption_or_history"
    min_obs: int = 52

    @classmethod
    def from_book(cls, book, **overrides) -> "ScoreSettings":
        """Defaults <- book.settings (matching keys) <- non-None overrides."""
        kw = {k: v for k, v in (book.settings or {}).items() if k in cls.__dataclass_fields__}
        kw.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**kw)


def resolve_rate(value, loader=None, what: str = "risk_free") -> dict:
    """An annual rate from an Assumption, or 'fred:<ID>' (percent; latest
    observation) via the loader.  Returns {value, basis, source, confidence|as_of}."""
    if value is None:
        raise ValidationError(f"settings.{what} is required (an assumption or 'fred:DTB3')")
    if isinstance(value, Assumption):
        return {"value": value.value, "basis": "assumption", "source": value.source, "confidence": value.confidence}
    if isinstance(value, str) and value.startswith("fred:"):
        if loader is None:
            raise ValidationError(f"{what}={value} needs a data loader")
        ds = loader.fred(value[5:])
        s = ds.values
        return {"value": float(s.iloc[-1]) / 100.0, "basis": "measured", "source": f"FRED {value[5:]}",
                "as_of": str(s.index[-1].date()), "fetched_at": ds.provenance.fetched_at}
    raise ValidationError(f"settings.{what}: expected an assumption mapping or 'fred:<ID>', got {value!r}")


def prepare_moments(book, view, loader, settings: ScoreSettings):
    """Fetch history for the view's empirical leaves, align at settings.freq,
    keep the last window_years (ending settings.end), and build Moments.
    Returns (moments, provenance, rf_info, spread_info, returns_window)."""
    names = view.streams
    if settings.estimator == "ewma" and not settings.halflife:
        raise ValidationError("estimator 'ewma' needs a halflife in periods of settings.freq "
                              "(--halflife, or settings.halflife in the book)")
    rf_info = resolve_rate(book.settings.get("risk_free"), loader, "risk_free")
    sp = book.settings.get("financing_spread")
    spread_info = resolve_rate(sp, loader, "financing_spread") if sp is not None else {
        "value": 0.0, "basis": "not provided (0 assumed)", "source": "none", "confidence": "placeholder"}
    levels, prov = loader.stream_levels(book.universe, names)
    rets = None
    if not levels.empty:
        rets = aligned_returns(levels, settings.freq)
        end = pd.Timestamp(settings.end) if settings.end else rets.index[-1]
        start = end - pd.DateOffset(months=int(round(settings.window_years * 12)))
        rets = rets.loc[(rets.index > start) & (rets.index <= end)]
    ppy = FREQ_PPY[settings.freq.upper()]
    if settings.freq.upper() == "D" and rets is not None:
        # daily: annualise on the observed calendar (~252 exchange days, ~365
        # crypto-only), measured on the rows the estimator uses (history
        # 'common' = every stream present), so a 7-day crypto stretch before a
        # business-day stream starts does not inflate it
        cal = rets.dropna(how="any").index if settings.history == "common" else rets.index
        if len(cal) >= 3:
            ppy = infer_periods_per_year(cal)
    m = build_moments(book.universe, names, returns=rets, periods_per_year=ppy, rf=rf_info["value"],
                      method=settings.estimator, history=settings.history, mu_mode=settings.mu_mode,
                      min_periods=settings.min_obs, halflife=settings.halflife)
    return m, prov, rf_info, spread_info, rets


def _assumption_rows(book, names) -> list:
    rows = []
    for k, a in (book.assumptions or {}).items():
        rows.append({"item": f"assumptions.{k}", **a.to_dict()})
    seen = set()
    for n in names:
        stack = [n]
        while stack:
            s_name = stack.pop()
            if s_name in seen:
                continue
            seen.add(s_name)
            s = book.universe[s_name]
            if s.expected_return is not None:
                rows.append({"item": f"{s_name}.expected_return", **s.expected_return.to_dict()})
            if isinstance(s, ParametricStream):
                for lab, a in s.assumptions().items():
                    if lab != "expected_return":
                        rows.append({"item": f"{s_name}.{lab}", **a.to_dict()})
                stack.extend(s.factors)
            if isinstance(s, CompositeStream):
                for lab in ("financing_spread", "fee"):
                    a = getattr(s, lab)
                    if a is not None:
                        rows.append({"item": f"{s_name}.{lab}", **a.to_dict()})
                stack.extend(s.components)
            if isinstance(s, CashStream) and s.rate is not None:
                rows.append({"item": f"{s_name}.rate", **s.rate.to_dict()})
    return rows


def scorecard(book, view, moments, settings: ScoreSettings, *, rf_info: dict, spread_info: dict | None = None,
              provenance: dict | None = None) -> dict:
    """Build the scorecard dict for ``view`` from ``moments`` (whose names must
    equal view.streams).  Pure: no I/O."""
    names = view.streams
    if list(moments.names) != list(names):
        raise ValidationError("moments.names must match view.streams (same order)")
    spread_info = spread_info or {"value": 0.0, "basis": "not provided (0 assumed)", "source": "none",
                                  "confidence": "placeholder"}
    rf, spread = rf_info["value"], spread_info["value"]
    vals = view.stream_values()
    w = np.array([vals[n] / view.total_usd for n in names])
    mu, S = moments.mu, moments.cov
    port_mu = float(w @ mu + (1 - w.sum()) * rf)
    port_var = float(w @ S @ w)
    if port_var <= 0:
        raise ValidationError("view has zero risk (all cash?)")
    port_vol = math.sqrt(port_var)
    eb = effective_bets(w, S, n_obs=moments.estimate.n_obs if moments.estimate is not None else None)
    prc = percent_risk_contributions(w, S)
    rc = risk_contributions(w, S)
    vol = moments.vol
    # ---- per stream -----------------------------------------------------
    pos_by_stream: dict[str, list] = {}
    for p in view.positions:
        pos_by_stream.setdefault(p.stream, []).append(p)
    stream_rows = []
    for i, n in enumerate(names):
        s = book.universe[n]
        ex = float(mu[i] - rf)
        sh = ex / vol[i] if vol[i] > 0 else None
        good = None if isinstance(s, CashStream) else bool(ex > 0 and sh is not None and sh >= settings.good_sharpe)
        stream_rows.append({
            "stream": n, "kind": s.kind, "usd": vals[n], "dollar_share": float(w[i]), "risk_share": float(prc[i]),
            "risk_contribution_vol": float(rc[i]), "exp_return": float(mu[i]), "mu_basis": moments.mu_basis[n],
            "vol": float(vol[i]), "sharpe": sh, "good": good,
            "liquidity": sorted({p.liquidity for p in pos_by_stream[n]}),
            "mark_basis": sorted({p.mark_basis for p in pos_by_stream[n]}),
        })
    stream_rows.sort(key=lambda r: -abs(r["risk_share"]))
    # ---- per position ---------------------------------------------------
    pos_rows = []
    for p in view.positions:
        i = names.index(p.stream)
        share_in_stream = p.value_usd / vals[p.stream] if vals[p.stream] != 0 else 0.0
        pos_rows.append({"position": p.name, "stream": p.stream, "sleeve": p.sleeve, "usd": p.value_usd,
                         "dollar_share": p.value_usd / view.total_usd, "risk_share": float(prc[i] * share_in_stream),
                         "liquidity": p.liquidity, "mark_basis": p.mark_basis, "tags": list(p.tags)})
    pos_rows.sort(key=lambda r: -abs(r["risk_share"]))
    # ---- sleeves --------------------------------------------------------
    sleeves: dict[str, dict] = {}
    for r in pos_rows:
        d = sleeves.setdefault(r["sleeve"], {"sleeve": r["sleeve"], "usd": 0.0, "dollar_share": 0.0, "risk_share": 0.0})
        d["usd"] += r["usd"]; d["dollar_share"] += r["dollar_share"]; d["risk_share"] += r["risk_share"]
    # ---- look-through ---------------------------------------------------
    x, c = moments.look_through(w)
    Sb = moments.base_cov
    vb = float(x @ Sb @ x)
    lt_prc = x * (Sb @ x) / vb if vb > 0 else np.zeros_like(x)
    look = [{"leaf": moments.base_names[j], "exposure": float(x[j]), "risk_share": float(lt_prc[j])}
            for j in range(len(x))]
    look.sort(key=lambda r: -abs(r["risk_share"]))
    rf_exposure = float(w @ moments.rf_coef)
    # ---- flags ----------------------------------------------------------
    flags = []
    for r in stream_rows:
        if r["risk_share"] > settings.stream_risk_flag:
            flags.append({"type": "stream_risk_concentration", "item": r["stream"],
                          "detail": f"{r['risk_share']:.0%} of risk (> {settings.stream_risk_flag:.0%})"})
        if r["risk_share"] < -1e-9:
            flags.append({"type": "hedge", "item": r["stream"], "detail": f"negative risk share {r['risk_share']:.1%}"})
        if r["good"] is False:
            flags.append({"type": "not_good_stream", "item": r["stream"],
                          "detail": f"excess {r['exp_return'] - rf:+.1%}, Sharpe "
                                    f"{(r['sharpe'] if r['sharpe'] is not None else float('nan')):.2f} "
                                    f"(< {settings.good_sharpe}) [{r['mu_basis']}]"})
    for r in pos_rows:
        if r["dollar_share"] > settings.position_flag:
            flags.append({"type": "position_concentration", "item": r["position"],
                          "detail": f"{r['dollar_share']:.0%} of NAV (> {settings.position_flag:.0%})"})
    if eb.dr_warnings:
        flags.append({"type": "neff_unreliable", "item": "book", "detail": "; ".join(eb.dr_warnings)})
    if eb.dr2 < DALIO_TARGET_BETS:
        flags.append({"type": "few_bets", "item": "book",
                      "detail": f"N_eff (DR^2) {eb.dr2:.1f} vs Dalio's {DALIO_TARGET_BETS} good uncorrelated bets"})
    # ---- environments ---------------------------------------------------
    mapping, msrc = stream_box_mapping(book.universe, names)
    M, unmapped = exposures_from_mapping(names, mapping)
    env = environment_balance(w, S, M, mu=mu)
    env["mapping"] = {n: {"boxes": list(mapping[n]), "source": msrc[n]} for n in mapping}
    env["unmapped_streams"] = [n for n in unmapped if not isinstance(book.universe[n], CashStream)]
    # ---- gearing --------------------------------------------------------
    # Gearing scales the NON-CASH streams by L; the book's own cash (streams
    # with no leaf exposure: CashStream) funds the extra exposure first and
    # only the excess is borrowed at rf + spread (core.new_borrowing).  A
    # composite's internal cash remainder is part of that instrument and is
    # geared with it.  Deployed cash costs its OWN rate: positive cash is
    # deployed pro rata and forgoes its blended premium over rf on the amount
    # put to work (core.cash_deployed / cash_premium_terms); liabilities, and
    # every cash line of a net-liability book, keep their premium at every L.
    cash = np.array([not book.universe.exposure(n).coefs for n in names])
    u = float(w[~cash].sum())
    cash_share = 1.0 - u
    cash_premium, cash_prem_rate = cash_premium_terms(w[cash], mu[cash], rf, cash_share)
    mu_rf_cash = port_mu - cash_premium            # book mean with its cash at rf
    tv = settings.target_vol
    L_need = tv / port_vol
    gk = {"cash_share": cash_share, "cash_premium_rate": cash_prem_rate}
    L_star = kelly_leverage(mu_rf_cash, port_vol, rf, spread, **gk)
    g_mu = geared_return(mu_rf_cash, rf, L_need, spread, **gk) + cash_premium
    gross_now = float(np.abs(w[~cash]).sum())
    gearing = {
        "current_vol": port_vol, "target_vol": tv, "vol_gap": port_vol - tv,
        "leverage_to_target": L_need, "cash_share": cash_share,
        "gross_exposure_now": gross_now, "gross_exposure_at_target": L_need * gross_now,
        "look_through_gross_at_target": L_need * float(np.abs(x).sum()),
        "new_borrowing_at_target": new_borrowing(L_need, cash_share),
        "cash_deployed_at_target": cash_deployed(L_need, cash_share),
        "cash_premium_rate": cash_prem_rate,
        "exceeds_max_leverage": bool(L_need * gross_now > settings.max_leverage),
        "kelly_leverage": L_star, "fraction_of_kelly_at_target": (L_need / L_star) if L_star > 0 else None,
        "fraction_of_kelly_now": (1.0 / L_star) if L_star > 0 else None,
        "exp_return_now": port_mu, "exp_return_at_target": g_mu,
        "log_growth_now": log_growth(mu_rf_cash, port_vol, rf, 1.0, spread, **gk) + cash_premium,
        "log_growth_at_target": log_growth(mu_rf_cash, port_vol, rf, L_need, spread, **gk) + cash_premium,
        "p_loss_year_now": {"normal": prob_loss(port_mu, port_vol), "lognormal": prob_loss(port_mu, port_vol, model="lognormal")},
        "p_loss_year_at_target": {"normal": prob_loss(g_mu, tv), "lognormal": prob_loss(g_mu, tv, model="lognormal")},
        "financing_spread": spread_info,
        "note": ("leverage L scales the non-cash streams; geared return = rf + L(mu_rf - rf) - B(L) spread "
                 "- D(L) d + cash premium, with mu_rf the book mean with its cash at rf, B(L) = new borrowing "
                 "beyond the book's own cash (max(L(1-cash_share) - 1, 0)), D(L) = own cash deployed "
                 "(min(L(1-cash_share), 1) - (1-cash_share); 0 for a net-liability book) and d = the blended "
                 "premium over rf of the book's positive cash, so deployed cash costs its own rate; max_leverage "
                 "caps gross non-cash exposure L x sum|w_noncash|"),
    }
    # ---- honesty --------------------------------------------------------
    basis_counts: dict[str, float] = {}
    for i, n in enumerate(names):
        b = moments.mu_basis[n]
        basis_counts[b] = basis_counts.get(b, 0.0) + float(w[i])
    mark: dict[str, float] = {}
    liq: dict[str, float] = {}
    for p in view.positions:
        mark[p.mark_basis] = mark.get(p.mark_basis, 0.0) + p.value_usd / view.total_usd
        liq[p.liquidity] = liq.get(p.liquidity, 0.0) + p.value_usd / view.total_usd
    est = moments.estimate
    not_mod = list(NOT_MODELLED)
    if any(p.mark_basis in ("appraisal", "model", "cost", "round") for p in view.positions):
        not_mod.append("stale / smoothed marks: model-, appraisal-, cost- or round-marked positions understate "
                       "volatility and correlation unless de-smoothed (estimate.geltner_desmooth)")
    coarse = {k: v.get("native_median_gap_days") for k, v in (provenance or {}).items()
              if isinstance(v, dict) and (v.get("native_median_gap_days") or 0) > 4}
    if coarse:
        not_mod.append("streams marked less often than daily (median days between marks: "
                       + ", ".join(f"{k} {g:.0f}" for k, g in coarse.items())
                       + f"): their risk and correlations are measured only at those marks (freq {settings.freq})")
    if moments.jumps:
        not_mod.append("default jumps enter the scorecard as variance only; forward.py simulates them as at most one "
                       "default per year (annual two-point model)")
    honesty = {
        "measurement_basis": {
            "expected_returns_by_dollar_share": basis_counts,
            "warning": ("historical means are IN-SAMPLE and are NOT forecasts"
                        if any("historical" in b for b in basis_counts) else ""),
            "covariance": None if est is None else {
                "estimator": est.method, "history": est.history, "freq": settings.freq,
                "start": str(est.start.date()) if est.start is not None else None,
                "end": str(est.end.date()) if est.end is not None else None,
                "n_obs": est.n_obs, "shrinkage": est.shrinkage,
                "annualisation": f"x{est.periods_per_year:g} (IID scaling)"},
            "parametric_rows": "factor model from assumptions x measured factor covariance" if moments.parametric else None,
            "risk_free": rf_info,
        },
        "assumptions": _assumption_rows(book, names),
        "mark_basis_share": mark,
        "liquidity_share": liq,
        "non_market_marks": [{"position": p.name, "usd": p.value_usd, "mark_basis": p.mark_basis}
                             for p in view.positions if p.mark_basis != "market"],
        "native_sampling_days": coarse,
        "not_modelled": not_mod,
        "provenance": provenance or {},
        "notes": list(moments.notes) + list(book.warnings),
    }
    return {
        "book": book.name, "as_of": book.as_of, "view": view.label, "nav_usd": view.total_usd,
        "settings": asdict(settings),
        "portfolio": {"exp_return": port_mu, "vol": port_vol, "rf": rf, "excess_return": port_mu - rf,
                      "sharpe": sharpe_ratio(port_mu, port_vol, rf), "rf_exposure": rf_exposure},
        "effective_bets": {"rows": eb.rows(), "n_streams_with_risk": eb.n, "dr": eb.dr, "dr2": eb.dr2,
                           "dr_warnings": eb.dr_warnings,
                           "implied_avg_corr": eb.implied_avg_corr, "rho_bar": eb.rho_bar,
                           "dalio_target": DALIO_TARGET_BETS},
        "streams": stream_rows, "positions": pos_rows, "sleeves": list(sleeves.values()),
        "look_through": look, "flags": flags, "environment": env, "gearing": gearing, "honesty": honesty,
        "correlation": {"names": names, "matrix": moments.corr().tolist()},
    }


def score_book(book, loader, settings: ScoreSettings | None = None, *, view: str = "investable", **filters) -> dict:
    """Fetch data, build moments and return the scorecard for a view."""
    settings = settings or ScoreSettings.from_book(book)
    v = book.view(view, **filters)
    m, prov, rf_info, sp_info, _ = prepare_moments(book, v, loader, settings)
    return scorecard(book, v, m, settings, rf_info=rf_info, spread_info=sp_info, provenance=prov)


def _pct(x) -> str:
    return "n/a" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.1%}"


def scorecard_markdown(sc: dict) -> str:
    """Compact markdown rendering (results first, honesty last)."""
    p, g, eb = sc["portfolio"], sc["gearing"], sc["effective_bets"]
    L = [f"# Dalio Holy Grail scorecard: {sc['book']} ({sc['view']})", "",
         f"NAV ${sc['nav_usd']:,.0f} | exp. return {_pct(p['exp_return'])} | vol {_pct(p['vol'])} | "
         f"Sharpe {p['sharpe']:.2f} | N_eff (DR^2) {eb['dr2']:.1f} of {eb['n_streams_with_risk']} risky streams "
         + (f"[UNRELIABLE: {'; '.join(eb['dr_warnings'])}] " if eb.get("dr_warnings") else "") +
         f"(Dalio target {eb['dalio_target']}) | vol target {_pct(g['target_vol'])} -> leverage {g['leverage_to_target']:.2f}x "
         f"(Kelly {g['kelly_leverage']:.2f}x)", "", "## Effective number of bets", "",
         "| measure | value | class | flag |", "|---|---|---|---|"]
    for r in eb["rows"]:
        L.append(f"| {r['label']} | {r['value']:.2f} | {r['class']} | {r['flag']} |")
    L += ["", f"DR {eb['dr']:.2f} | implied avg corr {eb['implied_avg_corr']:.2f} | mean pairwise corr {eb['rho_bar']:.2f}",
          "", "## Risk share vs dollar share (streams)", "",
          "| stream | $ share | risk share | exp ret | basis | vol | Sharpe | good |", "|---|---|---|---|---|---|---|---|"]
    for r in sc["streams"]:
        sh = "n/a" if r["sharpe"] is None else f"{r['sharpe']:.2f}"
        L.append(f"| {r['stream']} | {_pct(r['dollar_share'])} | {_pct(r['risk_share'])} | {_pct(r['exp_return'])} | "
                 f"{r['mu_basis']} | {_pct(r['vol'])} | {sh} | {r['good']} |")
    L += ["", "## Flags", ""] + ([f"- **{f['type']}** {f['item']}: {f['detail']}" for f in sc["flags"]] or ["- none"])
    env = sc["environment"]
    L += ["", "## Environment balance (All Weather target 25% risk per box)", "",
          "| box | risk share | of mapped |", "|---|---|---|"]
    for b in BOXES:
        L.append(f"| {b} | {_pct(env['risk_share'][b])} | {_pct(env['risk_share_of_mapped'][b])} |")
    L += [f"", f"balance score {env['balance_score']:.2f} (1 = balanced) | unmapped risk {_pct(env['unmapped_risk_share'])}"
          + (f" ({', '.join(env['unmapped_streams'])})" if env["unmapped_streams"] else ""),
          "", "## Gearing", "",
          f"current vol {_pct(g['current_vol'])} vs target {_pct(g['target_vol'])}; leverage needed {g['leverage_to_target']:.2f}x "
          f"on the non-cash book (gross {g['gross_exposure_at_target']:.2f}x of NAV, new borrowing "
          f"{_pct(g['new_borrowing_at_target'])} of NAV after using {_pct(g['cash_share'])} cash)"
          + (" **exceeds max_leverage**" if g["exceeds_max_leverage"] else "") + "; "
          f"exp return now {_pct(g['exp_return_now'])} -> at target {_pct(g['exp_return_at_target'])}; "
          f"P(losing year) now {_pct(g['p_loss_year_now']['normal'])} -> at target {_pct(g['p_loss_year_at_target']['normal'])} (normal)",
          "", "## Honesty", ""]
    h = sc["honesty"]
    mb = h["measurement_basis"]
    L.append(f"- expected-return basis by $ share: " + ", ".join(f"{k} {_pct(v)}" for k, v in mb["expected_returns_by_dollar_share"].items()))
    if mb["warning"]:
        L.append(f"- **{mb['warning']}**")
    if mb["covariance"]:
        c = mb["covariance"]
        L.append(f"- covariance: {c['estimator']} ({c['history']}), {c['freq']} {c['start']}..{c['end']}, n={c['n_obs']}, shrinkage {c['shrinkage']}")
    L.append(f"- risk-free: {mb['risk_free']['value']:.2%} ({mb['risk_free']['basis']}, {mb['risk_free']['source']})")
    L.append("- mark basis: " + ", ".join(f"{k} {_pct(v)}" for k, v in h["mark_basis_share"].items()))
    L.append(f"- assumptions: {len(h['assumptions'])} (" + ", ".join(
        f"{c} {sum(1 for a in h['assumptions'] if a['confidence'] == c)}" for c in ("high", "medium", "low", "placeholder")) + ")")
    L += ["- NOT modelled:"] + [f"  - {x}" for x in h["not_modelled"]]
    from .report import provenance_lines  # local: keeps the scorecard importable without matplotlib state
    pl = provenance_lines(h.get("provenance") or {})
    L += [f"- {pl[0]}"] + [f"  {x}" for x in pl[1:]]
    return "\n".join(L) + "\n"
