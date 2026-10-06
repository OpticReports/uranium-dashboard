"""Command line: python -m holygrail curve|score|backtest|forward|stress|envs ...

Every command prints a compact markdown summary and writes JSON/CSV rows and
PNG charts under --out (default ./results/<command>).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import report
from .allocate import ALLOCATORS, get_allocator, target_vol_gearing
from .backtest import BacktestConfig, run_backtest
from .book import load_book
from .core import dalio_table, effective_bets
from .data import DataLoader, tbill_period_returns
from .environments import (RegimeDefinition, environment_betas, monthly_returns, quadrant_table,
                           regimes_from_fred)
from .errors import HolyGrailError, ValidationError
from .estimate import align_levels, aligned_returns, infer_periods_per_year, levels_to_returns
from .forward import SCENARIOS, SimConfig, book_terms, replay_scenario, run_forward, stress_look_through
from .scorecard import ScoreSettings, prepare_moments, scorecard, scorecard_markdown
from .streams import MarketStream, Universe


# --------------------------------------------------------------------------- #
# shared plumbing
# --------------------------------------------------------------------------- #
def _loader(a) -> DataLoader:
    return DataLoader(a.cache_dir, offline=a.offline, max_age_hours=a.max_age_hours)


def _out(a, cmd: str) -> Path:
    p = Path(a.out) if a.out else Path("results") / cmd
    p.mkdir(parents=True, exist_ok=True)
    return p


def _universe_and_names(a, book=None):
    if book is not None:
        v = book.view(a.view, include_tags=a.include_tags, exclude_tags=a.exclude_tags, sleeves=a.sleeves)
        return book.universe, v.streams, v
    if not a.tickers:
        raise ValidationError("give --book or --tickers")
    syms = [s.strip() for s in a.tickers.split(",") if s.strip()]
    return Universe([MarketStream(name=s, symbol=s) for s in syms]), syms, None


def _daily_stream_returns(universe, names, loader, rf_daily: pd.Series | None = None):
    """Daily returns of each named stream on the active-intersection calendar
    (composites built from daily leaf returns = daily-reset model; their
    annual constants -- fees, financing spreads -- accrue by calendar days)."""
    levels, prov = loader.stream_levels(universe, names)
    lv = align_levels(levels, "D")
    leaf = levels_to_returns(lv)
    yf = pd.Series(pd.Series(lv.index).diff().dt.days.to_numpy()[1:] / 365.25, index=leaf.index)
    cols = {}
    for n in names:
        if n in leaf.columns:
            cols[n] = leaf[n]
        else:
            rf = rf_daily if rf_daily is not None else pd.Series(0.0, index=leaf.index)
            cols[n] = universe.series_returns(n, leaf, rf.reindex(leaf.index).fillna(0.0), 252, year_fraction=yf)
    return pd.DataFrame(cols), prov


def _rf_daily(a, loader, index) -> tuple[pd.Series, dict]:
    """Per-period cash return on ``index``: FRED rate (actual/360) or an annual
    constant accrued by calendar days (actual/365.25), so it earns its stated
    rate per year on a 5-day or a 7-day calendar alike."""
    if a.rf.startswith("fred:"):
        ds = loader.fred(a.rf[5:])
        return tbill_period_returns(ds.values, index), {"source": f"FRED {a.rf[5:]}", "basis": "measured",
                                                         "fetched_at": ds.provenance.fetched_at}
    v = float(a.rf)
    idx = pd.DatetimeIndex(index)
    r = tbill_period_returns(pd.Series([100.0 * v], index=idx[:1]), idx, day_count=365.25)
    return r, {"source": "--rf constant", "basis": "assumption", "value": v, "accrual": "actual/365.25"}


def _add_common(p, book=True):
    p.add_argument("--out", help="output directory (default ./results/<command>)")
    p.add_argument("--cache-dir", default=None, help="data cache directory (default holygrail-engine/data/cache)")
    p.add_argument("--offline", action="store_true", help="read cached data only; fail if missing")
    p.add_argument("--max-age-hours", type=float, default=18.0, help="refetch cached feeds older than this")
    if book:
        p.add_argument("--book", help="YAML book file")
        p.add_argument("--view", default="investable", choices=["whole", "investable", "liquid"])
        p.add_argument("--include-tags", nargs="*", default=None)
        p.add_argument("--exclude-tags", nargs="*", default=None)
        p.add_argument("--sleeves", nargs="*", default=None)
        p.add_argument("--tickers", help="comma-separated Yahoo symbols (instead of --book)")


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_curve(a) -> int:
    """`curve`: Dalio table + sigma_p-vs-N and N_eff-vs-rho charts (pure math)."""
    out = _out(a, "curve")
    rhos = [float(x) for x in a.rhos.split(",")]
    files = report.dalio_curve(out, sigma=a.sigma, mu=a.mu, n_max=a.n_max, rhos=rhos)
    files_n = report.neff_vs_rho(out)
    rows = dalio_table(a.sigma, a.mu, (1, 5, 10, 15), (0.0,))
    print(f"# Dalio curve (sigma {a.sigma:.0%}, mu {a.mu:.0%}, rho = 0)\n")
    print(report.markdown_table(rows, ["n", "sigma_p", "return_to_risk", "improvement", "neff"],
                                {"sigma_p": ".3%", "return_to_risk": ".4f", "improvement": ".3f", "neff": ".2f"}))
    print(f"\nwrote {files['png']}, {files_n['png']} (+ rows)")
    return 0


def cmd_score(a) -> int:
    """`score`: Holy Grail scorecard for a book view (JSON, markdown, rows, risk-vs-dollar chart)."""
    if not a.book:
        raise ValidationError("score needs --book")
    book = load_book(a.book)
    loader = _loader(a)
    st = ScoreSettings.from_book(book, target_vol=a.target_vol, freq=a.freq, window_years=a.window_years,
                                 estimator=a.estimator, halflife=a.halflife, end=a.end)
    v = book.view(a.view, include_tags=a.include_tags, exclude_tags=a.exclude_tags, sleeves=a.sleeves)
    m, prov, rf_info, sp_info, _ = prepare_moments(book, v, loader, st)
    sc = scorecard(book, v, m, st, rf_info=rf_info, spread_info=sp_info, provenance=prov)
    out = _out(a, "score")
    report.write_json(sc, out / "scorecard.json")
    report.write_rows(sc["streams"], out / "streams")
    report.write_rows(sc["positions"], out / "positions")
    report.write_rows(sc["effective_bets"]["rows"], out / "effective_bets")
    report.risk_vs_dollar(out, sc["streams"])
    md = scorecard_markdown(sc)
    (out / "scorecard.md").write_text(md)
    print(md)
    print(f"wrote {out}/scorecard.json, scorecard.md, risk_vs_dollar.png (+ rows)")
    return 0


def cmd_backtest(a) -> int:
    """`backtest`: walk-forward run_backtest on tickers or a book's streams; equity/drawdown charts + metrics."""
    loader = _loader(a)
    book = load_book(a.book) if a.book else None
    uni, all_names, view = _universe_and_names(a, book)
    # cash streams (no leaf exposure) are the backtest's own cash leg c = 1 - sum(w):
    # never an asset for the allocator, never scaled by the vol target
    cash_names = [n for n in all_names if not uni.exposure(n).coefs]
    names = [n for n in all_names if n not in cash_names]
    if not names:
        raise ValidationError("nothing to backtest: every stream in the selection is cash")
    probe, _ = _daily_stream_returns(uni, names, loader)
    rf_d, rf_info = _rf_daily(a, loader, probe.index)
    R, prov = _daily_stream_returns(uni, names, loader, rf_d)
    if a.start:
        R = R.loc[R.index >= pd.Timestamp(a.start)]
    if a.end:
        R = R.loc[R.index <= pd.Timestamp(a.end)]
    rf_d = rf_d.reindex(R.index)
    # annualise on the calendar actually used: ~252/yr for exchange days,
    # ~365/yr for a crypto-only 7-day calendar (vol, Sharpe, vol targeting)
    ppy = infer_periods_per_year(R.index)
    if ppy < 180:
        raise ValidationError(f"the aligned daily calendar has only {ppy:.0f} periods/yr: a stream prints too rarely "
                              "for a daily backtest")
    if a.allocator == "book":
        if view is None:
            raise ValidationError("--allocator book needs --book")
        wb = view.weights()
        fixed = np.array([wb[n] for n in names])  # non-cash weights; the view's cash share stays cash
        alloc = lambda S: fixed  # noqa: E731 - constant-mix of the current book
        alloc.__name__ = "book_weights"
    else:
        alloc = a.allocator
    cfg = BacktestConfig(allocator=alloc, window=a.window, estimator=a.estimator, halflife=a.halflife,
                         rebalance=int(a.rebalance) if a.rebalance.isdigit() else a.rebalance, band=a.band,
                         cost_bps=a.cost_bps, financing_spread=a.spread, target_vol=a.target_vol,
                         max_leverage=a.max_leverage, periods_per_year=ppy)
    bench = None
    if a.benchmark:
        bds = loader.yahoo(a.benchmark)
        prov[f"benchmark:{a.benchmark}"] = bds.provenance.to_dict()
        bl = bds.values
        # benchmark LEVELS as-of each strategy date, then returns: a move on a
        # date the strategy calendar skips (weekend, foreign holiday, missing
        # print) compounds into the next strategy date instead of vanishing
        lvl = bl.reindex(bl.index.union(R.index)).ffill().reindex(R.index)
        lvl[lvl.index > bl.index[-1]] = np.nan
        bench = lvl / lvl.shift(1) - 1.0
    res = run_backtest(R, cfg, rf=rf_d, benchmark=bench if bench is not None else None)
    out = _out(a, "backtest")
    curves = {"strategy": res.equity}
    if bench is not None:
        b = (1 + bench.loc[res.returns.index]).cumprod()
        curves[a.benchmark] = pd.concat([pd.Series([1.0], index=[res.equity.index[0]]), b])
    report.equity_curves(out, curves, title="Walk-forward equity (log scale, MTM daily)")
    report.drawdowns(out, curves)
    report.write_rows(res.targets.reset_index().rename(columns={"index": "date"}), out / "targets")
    hindsight = a.allocator == "book"
    if hindsight:
        res.notes.append("allocator 'book': constant mix of TODAY's book weights replayed over history (hindsight: "
                         "chosen knowing the whole sample); not walk-forward")
    summary = {"metrics": res.metrics, "benchmark": res.benchmark, "config": res.config, "notes": res.notes,
               "rf": rf_info, "provenance": prov, "avg_turnover_per_rebalance": float(res.turnover[res.turnover > 0].mean()),
               "avg_gross_leverage": float(res.leverage.mean()), "cash_streams": cash_names}
    report.write_json(summary, out / "backtest.json")
    m = res.metrics
    print(f"# Backtest: {cfg.allocator if isinstance(cfg.allocator, str) else 'book weights'} on {', '.join(names)}\n")
    if cash_names:
        rated = [n for n in cash_names if getattr(uni[n], "rate", None) is not None]
        print(f"cash streams {cash_names} -> the backtest cash leg (earns {rf_info['source']}; borrowing pays the "
              f"spread)" + (f"; stated cash rates of {rated} not used" if rated else ""))
    print(f"{m['start']}..{m['end']} | CAGR {m['cagr']:.2%} | vol {m['vol']:.2%} | Sharpe {m['sharpe']:.2f} | "
          f"max DD {m['max_drawdown']:.1%} | worst yr {m['worst_year']:.1%} | P(loss yr) {m['p_loss_year']:.0%} "
          f"| avg gross {summary['avg_gross_leverage']:.2f}x")
    if res.benchmark:
        bm = res.benchmark["benchmark"]
        print(f"benchmark {a.benchmark}: CAGR {bm['cagr']:.2%} | vol {bm['vol']:.2%} | Sharpe {bm['sharpe']:.2f} | "
              f"max DD {bm['max_drawdown']:.1%}")
    if hindsight:
        print("basis: daily MTM; constant mix of TODAY's book weights over history (hindsight, NOT out-of-sample); "
              "IN-SAMPLE; holdings chosen ex post (survivorship/selection bias); not a forecast")
    else:
        print("basis: daily MTM, walk-forward weights, IN-SAMPLE history; tickers chosen ex post "
              "(survivorship/selection bias); not a forecast")
    print("\n".join(report.provenance_lines(prov)))
    print(f"wrote {out}")
    return 0


def _forward_inputs(a, loader):
    """Leaf-level inputs for forward: r_book = x'r_leaf + c exactly, with x the
    look-through leaf weights and c the annual non-leaf return (rf legs of
    cash/composites, fees, composite financing spreads, stated cash rates)."""
    book = load_book(a.book) if a.book else None
    if book is not None:
        st = ScoreSettings.from_book(book, freq="M" if a.method == "bootstrap" else None)
        v = book.view(a.view, include_tags=a.include_tags, exclude_tags=a.exclude_tags, sleeves=a.sleeves)
        m, prov, rf_info, sp_info, rets = prepare_moments(book, v, loader, st)
        vals = v.stream_values()
        w = np.array([vals[n] / v.total_usd for n in v.streams])
        x, _ = m.look_through(w)
        return {"labels": m.base_names, "x": x, "moments": m, "w": w, "mu": m.base_mu, "cov": m.base_diffusive_cov(),
                "full_cov": m.base_cov, "rf": rf_info["value"], "spread": sp_info["value"], "jumps": m.jumps,
                "history": rets, "basis": m.mu_basis, "provenance": prov}
    uni, names, _ = _universe_and_names(a, None)
    levels, prov = loader.stream_levels(uni, names)
    rets = aligned_returns(levels, "M").dropna()
    from .estimate import estimate_cov
    est = estimate_cov(rets, "lw_cc", freq="M")
    w = get_allocator(a.allocator)(est.annual)
    rf = float(a.rf) if not a.rf.startswith("fred:") else float(loader.fred(a.rf[5:]).values.iloc[-1]) / 100.0
    return {"labels": names, "x": w, "moments": None, "mu": est.annual_mean, "cov": est.annual, "full_cov": est.annual,
            "rf": rf, "spread": a.spread, "jumps": [], "history": rets,
            "basis": {n: "historical_in_sample" for n in names}, "provenance": prov}


def cmd_forward(a) -> int:
    """`forward`: Monte Carlo of the (optionally geared) book at leaf level; fan chart + horizon stats."""
    loader = _loader(a)
    fi = _forward_inputs(a, loader)
    x = fi["x"]
    L = 1.0
    if a.target_vol:
        L = target_vol_gearing(x, fi["full_cov"], a.target_vol, max_leverage=a.max_leverage).leverage
    ppy = 12
    cfg = SimConfig(years=a.years, periods_per_year=ppy, n_paths=a.paths, seed=a.seed, method=a.method, df=a.df)
    hist = None
    if a.method == "bootstrap":
        h = fi["history"]
        if h is None or any(l not in h.columns for l in fi["labels"]):
            raise ValidationError("bootstrap needs history for every leaf (parametric streams have none)")
        hist = h[fi["labels"]].dropna()
    # the NON-CASH book is geared L x; the book's own cash funds the extra
    # exposure first and only new borrowing pays rf + spread (forward.book_terms,
    # the scorecard's convention); composite-internal financing is inside const
    if fi["moments"] is not None:
        t = book_terms(fi["moments"], fi["w"], leverage=L, spread=fi["spread"], include_own_mu=a.method != "bootstrap")
    else:
        cw = 1.0 - L * float(np.sum(x))
        t = {"x": L * np.asarray(x), "const": 0.0, "cash_weight": cw, "spread_weight": max(-cw, 0.0),
             "cash_share": 1.0 - float(np.sum(x)), "own_mu_ignored": []}
        t["expected_return"] = float(t["x"] @ fi["mu"]) + cw * fi["rf"] - t["spread_weight"] * fi["spread"]
    if a.method == "bootstrap":  # the simulated drift is the replayed history's mean
        t["expected_return"] = (float(t["x"] @ (hist.mean().to_numpy() * ppy)) + t["const"]
                                + t["cash_weight"] * fi["rf"] - t["spread_weight"] * fi["spread"])
    res = run_forward(t["x"], cfg, mu=fi["mu"], cov=fi["cov"], history=hist, rf=fi["rf"], spread=fi["spread"],
                      const=t["const"], cash_weight=t["cash_weight"], spread_weight=t["spread_weight"],
                      jumps=fi["jumps"] or None)
    if t["own_mu_ignored"]:
        res.notes.append(f"bootstrap replays history: own expected_return assumptions of {t['own_mu_ignored']} "
                         "are not used (neither are the leaves' assumptions)")
    out = _out(a, "forward")
    bands = res.stats.pop("_wealth_bands")
    report.forward_fan(out, bands, ppy)
    report.write_json({"stats": res.stats, "config": res.config, "notes": res.notes, "labels": fi["labels"],
                       "leaf_weights": t["x"].tolist(), "book_leverage": L, "mu_basis": fi["basis"],
                       "expected_return_annual": t["expected_return"], "cash_share": t["cash_share"],
                       "cash_weight": t["cash_weight"], "new_borrowing": t["spread_weight"],
                       "provenance": fi["provenance"]},
                      out / "forward.json")
    s = res.stats
    q = s["cagr_quantiles"]
    print(f"# Forward MC ({a.method}, {a.paths} paths, {a.years:g}y, seed {a.seed}, non-cash leverage {L:.2f}x, "
          f"new borrowing {t['spread_weight']:.1%} of NAV)\n")
    print(f"simulated expected return {t['expected_return']:.2%}/yr (arithmetic drift of the model)")
    print(f"CAGR p5 {q['0.05']:.2%} | p50 {q['0.5']:.2%} | p95 {q['0.95']:.2%} | P(loss over horizon) "
          f"{s['p_loss_horizon']:.1%} | P(losing year) {s.get('p_losing_year', float('nan')):.1%} | "
          f"median max DD {s['median_max_dd']:.1%} | CVaR5 CAGR {s['cvar_0.05_cagr']:.2%}")
    print("basis: simulated under stated assumptions; expected returns marked historical are in-sample means")
    print("\n".join(report.provenance_lines(fi["provenance"])))
    print(f"wrote {out}")
    return 0


def cmd_stress(a) -> int:
    """`stress`: historical scenario replay of today's weights + uniform correlation stress (vol, DR^2)."""
    loader = _loader(a)
    book = load_book(a.book) if a.book else None
    uni, names, view = _universe_and_names(a, book)
    out = _out(a, "stress")
    from .estimate import estimate_cov
    from .streams import ParametricStream
    # streams with no history (parametric leaves) enter the replay as all-NaN
    # columns, so the declared --missing policy applies to them explicitly
    hist_names = [n for n in names if not any(isinstance(uni[l], ParametricStream) for l in uni.exposure(n).coefs)]
    no_hist = [n for n in names if n not in hist_names]
    probe, _ = _daily_stream_returns(uni, hist_names, loader) if hist_names else (pd.DataFrame(), {})
    rf_d, rf_info = _rf_daily(a, loader, probe.index)
    R, prov = _daily_stream_returns(uni, hist_names, loader, rf_d) if hist_names else (pd.DataFrame(), {})
    for n in no_hist:
        R[n] = np.nan
    if view is not None:
        wmap = view.weights()
        st = ScoreSettings.from_book(book)
        m, _, rf_m, _, _ = prepare_moments(book, view, loader, st)
        S = m.cov
        w = np.array([wmap[n] for n in m.names])
        A_lt, S_leaf = m.A, m.base_cov
    else:
        est = estimate_cov(aligned_returns(loader.stream_levels(uni, names)[0], "W").dropna(), "lw_cc", freq="W")
        w = get_allocator(a.allocator)(est.annual)
        S = est.annual
        wmap = dict(zip(names, w))
        A_lt, S_leaf = np.eye(len(names)), S
    scen = {}
    for s in a.scenarios.split(","):
        s = s.strip()
        if s in SCENARIOS:
            scen[s] = SCENARIOS[s][:2]
        elif ":" in s:
            st_, en = s.split(":")
            scen[f"{st_}..{en}"] = (st_, en)
        else:
            raise ValidationError(f"unknown scenario {s!r}; use {sorted(SCENARIOS)} or START:END")
    rows = []
    for lab, (st_, en) in scen.items():
        try:
            r = replay_scenario(R, wmap, st_, en, missing=a.missing, label=lab, rf_period=rf_d.reindex(R.index).fillna(0.0))
            r.pop("path")
            rows.append({"scenario": lab, **{k: r[k] for k in ("start", "end", "days", "cum_return", "max_drawdown",
                                                               "worst_day")}, "notes": "; ".join(r["notes"])})
        except ValidationError as e:
            rows.append({"scenario": lab, "start": st_, "end": en, "error": str(e)})
    report.write_rows(rows, out / "scenarios")
    print(f"# Stress: {', '.join(names)}\n")
    if no_hist:
        print(f"no history (parametric): {no_hist} -> --missing {a.missing}")
    for r in rows:
        if "error" in r:
            print(f"- {r['scenario']}: NOT RUN - {r['error']}")
        else:
            print(f"- {r['scenario']} ({r['start']}..{r['end']}): {r['cum_return']:+.1%}, max DD {r['max_drawdown']:.1%}"
                  + (f" [{r['notes']}]" if r["notes"] else ""))
    if a.corr_rho is not None:
        # floor every LEAF correlation at rho (never lowers one), then rebuild
        # the streams through the look-through map
        S2, sinfo = stress_look_through(A_lt, S_leaf, method="floor", rho=a.corr_rho, return_info=True)
        base, st2 = effective_bets(w, S), effective_bets(w, S2)
        crow = {"rho_stress": a.corr_rho, "method": sinfo["method"], "lift": sinfo["lift"],
                "vol_base": math.sqrt(w @ S @ w), "vol_stress": math.sqrt(w @ S2 @ w),
                "dr2_base": base.dr2, "dr2_stress": st2.dr2}
        report.write_rows([crow], out / "corr_stress")
        how = ("floor" if sinfo["method"] == "floor" else
               f"floor not PSD -> common-factor lift a={sinfo['lift']:.3f}, every rho moved toward 1")
        print(f"- correlation stress (every leaf pairwise rho floored at {a.corr_rho}, never lowered [{how}], vols "
              f"kept): vol {crow['vol_base']:.1%} -> {crow['vol_stress']:.1%}, N_eff (DR^2) {crow['dr2_base']:.1f} -> "
              f"{crow['dr2_stress']:.1f}")
        if crow["vol_stress"] < crow["vol_base"] - 1e-12:
            print("  WARNING: stressed vol is BELOW base - the book has short/hedge exposures that gain when "
                  "correlations rise; read the stress per stream")
    print(f"basis: historical replay of today's weights (buy-and-hold; cash leg at {rf_info['source']}); "
          "not a forecast")
    print("\n".join(report.provenance_lines(prov)))
    print(f"wrote {out}")
    return 0


def cmd_envs(a) -> int:
    """`envs`: FRED growth x inflation regimes, per-stream quadrant table, betas, heatmap."""
    loader = _loader(a)
    book = load_book(a.book) if a.book else None
    uni, names, _ = _universe_and_names(a, book)
    d = RegimeDefinition(trend_window=a.trend_window, release_lag=a.release_lag)
    surpr, prov = regimes_from_fred(loader, d)
    levels, _ = loader.stream_levels(uni, names)
    emp = [n for n in names if n in levels.columns]
    mret = monthly_returns(levels[emp])
    rf_m, rf_info = _rf_daily(a, loader, mret.index)  # per-month cash return on the month-end dates
    qt = quadrant_table(mret, surpr["quadrant"], rf_monthly=rf_m)
    bt = environment_betas(mret, surpr)
    out = _out(a, "envs")
    report.environment_heatmap(out, qt)
    report.write_rows(bt, out / "environment_betas")
    report.write_rows(surpr.reset_index().rename(columns={"index": "month"}).assign(
        month=lambda x: x.iloc[:, 0].dt.strftime("%Y-%m")), out / "regimes")
    counts = surpr["quadrant"].value_counts().to_dict()
    print(f"# Environments ({d.describe()})\n")
    print("months per quadrant: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print()
    print(report.markdown_table(qt.to_dict(orient="records"), ["stream", "quadrant", "months", "ann_mean", "sharpe"],
                                {"ann_mean": ".1%", "sharpe": ".2f"}))
    print(f"\nsharpe = excess return over cash ({rf_info['source']}) / vol, annualised from monthly returns")
    print(f"\nlatest month {surpr.index[-1]:%Y-%m}: {surpr['quadrant'].iloc[-1]}")
    print(f"wrote {out}")
    return 0


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    """argparse parser for all subcommands (each has --help)."""
    p = argparse.ArgumentParser(prog="python -m holygrail",
                                description="Dalio Holy Grail engine: 15 good, uncorrelated, risk-balanced bets, "
                                            "geared to a target volatility.  (Not the Composer HG symphony.)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("curve", help="Dalio curve: portfolio vol vs number of equal bets (pure math, no data)")
    c.add_argument("--sigma", type=float, default=0.18)
    c.add_argument("--mu", type=float, default=0.06)
    c.add_argument("--n-max", type=int, default=20)
    c.add_argument("--rhos", default="0,0.1,0.2,0.3,0.4,0.6")
    c.add_argument("--out")
    c.set_defaults(func=cmd_curve)

    s = sub.add_parser("score", help="Holy Grail scorecard for a book view")
    _add_common(s)
    s.add_argument("--target-vol", type=float, default=None)
    s.add_argument("--freq", default=None, choices=["D", "W", "M"])
    s.add_argument("--window-years", type=float, default=None)
    s.add_argument("--estimator", default=None, choices=["sample", "lw", "lw_cc", "ewma"])
    s.add_argument("--halflife", type=float, default=None, help="EWMA halflife in periods of --freq (ewma only)")
    s.add_argument("--end", default=None, help="estimation window end date")
    s.set_defaults(func=cmd_score)

    b = sub.add_parser("backtest", help="walk-forward backtest of an allocator")
    _add_common(b)
    b.add_argument("--allocator", default="erc", choices=sorted(ALLOCATORS) + ["book"])
    b.add_argument("--window", type=int, default=252)
    b.add_argument("--estimator", default="sample", choices=["sample", "ewma", "lw", "lw_cc"])
    b.add_argument("--halflife", type=float, default=None)
    b.add_argument("--rebalance", default="M", help="D|W|M|Q|A or an integer every-k-days")
    b.add_argument("--band", type=float, default=None)
    b.add_argument("--cost-bps", type=float, default=5.0)
    b.add_argument("--spread", type=float, default=0.005, help="annual financing spread over rf on borrowing")
    b.add_argument("--target-vol", type=float, default=None)
    b.add_argument("--max-leverage", type=float, default=1.0)
    b.add_argument("--rf", default="fred:DTB3", help="'fred:DTB3' or an annual constant")
    b.add_argument("--start")
    b.add_argument("--end")
    b.add_argument("--benchmark", default=None, help="Yahoo symbol, e.g. SPY")
    b.set_defaults(func=cmd_backtest)

    f = sub.add_parser("forward", help="Monte Carlo forward distribution (mvn | t | bootstrap)")
    _add_common(f)
    f.add_argument("--method", default="mvn", choices=["mvn", "t", "bootstrap"])
    f.add_argument("--years", type=float, default=10.0)
    f.add_argument("--paths", type=int, default=10_000)
    f.add_argument("--seed", type=int, default=7)
    f.add_argument("--df", type=float, default=5.0)
    f.add_argument("--target-vol", type=float, default=None)
    f.add_argument("--max-leverage", type=float, default=3.0)
    f.add_argument("--allocator", default="erc", choices=sorted(ALLOCATORS), help="weights for --tickers mode")
    f.add_argument("--rf", default="0.04", help="annual rf for --tickers mode")
    f.add_argument("--spread", type=float, default=0.005)
    f.set_defaults(func=cmd_forward)

    t = sub.add_parser("stress", help="historical scenario replay + correlation stress")
    _add_common(t)
    t.add_argument("--scenarios", default="gfc,covid,inflation_2022", help=f"names {sorted(SCENARIOS)} or START:END")
    t.add_argument("--missing", default="raise", choices=["raise", "cash"])
    t.add_argument("--corr-rho", type=float, default=None,
                   help="also stress correlations: floor every leaf pairwise correlation at this value (never lowers one)")
    t.add_argument("--allocator", default="erc", choices=sorted(ALLOCATORS), help="weights for --tickers mode")
    t.add_argument("--rf", default="fred:DTB3", help="cash-leg rate in replays: 'fred:DTB3' or an annual constant")
    t.set_defaults(func=cmd_stress)

    e = sub.add_parser("envs", help="growth x inflation environments from FRED + per-stream quadrant tables")
    _add_common(e)
    e.add_argument("--trend-window", type=int, default=36)
    e.add_argument("--release-lag", type=int, default=1)
    e.add_argument("--rf", default="fred:DTB3", help="cash rate for the excess-return Sharpe: 'fred:DTB3' or an annual constant")
    e.set_defaults(func=cmd_envs)
    return p


def main(argv=None) -> int:
    """CLI entry: run a subcommand; engine errors print to stderr and return exit code 2."""
    p = build_parser()
    a = p.parse_args(argv)
    try:
        return a.func(a)
    except HolyGrailError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
