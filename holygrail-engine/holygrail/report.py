"""Charts (matplotlib PNG) + the rows behind every chart (CSV + JSON) +
markdown summaries.  Rows are the source of truth: charts are re-drawn later
in a docs tool from them.

Palette: the dataviz reference instance (light mode), categorical hues in a
FIXED order (never cycled), blue<->red diverging with a gray midpoint, 2px
lines, hairline solid grid, text in ink tokens (never series colours).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator, NullFormatter  # noqa: E402

from .core import dalio_table, neff_equal_rho  # noqa: E402
from .errors import ValidationError  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
DIVERGING = LinearSegmentedColormap.from_list("hg_div", ["#d03b3b", "#f0efec", "#2a78d6"])


def _style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)


def _jsonable(v):
    if isinstance(v, (np.floating, float)):
        return None if not math.isfinite(float(v)) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (pd.Timestamp,)):
        return str(v.date())
    if isinstance(v, np.ndarray):
        return [_jsonable(x) for x in v.tolist()]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, pd.DataFrame):
        return _jsonable(v.reset_index().to_dict(orient="records"))
    if isinstance(v, pd.Series):
        return {str(k.date()) if isinstance(k, pd.Timestamp) else str(k): _jsonable(x) for k, x in v.items()}
    return v


def write_json(obj, path: str | Path) -> Path:
    """Write ``obj`` as JSON (NaN/inf -> null, numpy/pandas converted)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_jsonable(obj), indent=1, default=str))
    return p


def write_rows(rows, stem: str | Path) -> dict:
    """Write chart rows (list of dicts or DataFrame) to <stem>.csv and <stem>.json."""
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(stem.with_suffix(".csv"), index=False)
    write_json(df.to_dict(orient="records"), stem.with_suffix(".json"))
    return {"csv": str(stem.with_suffix(".csv")), "json": str(stem.with_suffix(".json"))}


def _save(fig, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return str(path)


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def dalio_curve(out_dir: str | Path, *, sigma: float = 0.18, mu: float = 0.06, n_max: int = 20,
                rhos=(0.0, 0.1, 0.2, 0.3, 0.4, 0.6)) -> dict:
    """Dalio curve: sigma_p = sigma sqrt((1+(N-1)rho)/N) vs N for each rho,
    with the sqrt(rho) floors.  Writes dalio_curve.png + rows."""
    if len(rhos) > len(SERIES):
        raise ValidationError(f"at most {len(SERIES)} rho series")
    out = Path(out_dir)
    rows = dalio_table(sigma, mu, range(1, n_max + 1), rhos)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for i, rho in enumerate(rhos):
        sub = [r for r in rows if r["rho"] == rho]
        ax.plot([r["n"] for r in sub], [100 * r["sigma_p"] for r in sub], color=SERIES[i], lw=2,
                solid_capstyle="round", label=f"rho = {rho:g}")
        ax.text(n_max + 0.3, 100 * sub[-1]["sigma_p"], f"{rho:g}", color=INK2, fontsize=8, va="center")
    for n_mark in (5, 10, 15):
        ax.axvline(n_mark, color=GRID, lw=1)
    _style(ax, f"Portfolio vol vs number of equal bets (each {sigma:.0%} vol)", "number of streams N", "portfolio vol (%)")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, title="pairwise correlation", title_fontsize=8)
    ax.set_xlim(1, n_max + 1.2)
    ax.set_ylim(0, 100 * sigma * 1.05)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    png = _save(fig, out / "dalio_curve.png")
    return {"png": png, **write_rows(rows, out / "dalio_curve")}


def neff_vs_rho(out_dir: str | Path, *, ns=(5, 10, 15, 25), rhos=None) -> dict:
    """Closed-form N_eff = N/(1+(N-1)rho) vs rho for several N (equal-weight,
    equal-vol): shows how fast correlation eats bets."""
    out = Path(out_dir)
    rhos = np.linspace(0, 0.8, 81) if rhos is None else np.asarray(rhos)
    rows = [{"n": n, "rho": float(r), "neff": neff_equal_rho(n, float(r))} for n in ns for r in rhos]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for i, n in enumerate(ns):
        sub = [r for r in rows if r["n"] == n]
        ax.plot([r["rho"] for r in sub], [r["neff"] for r in sub], color=SERIES[i], lw=2, label=f"N = {n}")
    _style(ax, "Effective bets vs average correlation", "average pairwise correlation", "N_eff")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
    png = _save(fig, out / "neff_vs_rho.png")
    return {"png": png, **write_rows(rows, out / "neff_vs_rho")}


def risk_vs_dollar(out_dir: str | Path, stream_rows: list, *, top: int = 15) -> dict:
    """Paired horizontal bars: dollar share vs risk share per stream (top by
    |risk share|).  Rows are the scorecard's stream rows."""
    out = Path(out_dir)
    rows = [{"stream": r["stream"], "dollar_share": r["dollar_share"], "risk_share": r["risk_share"]}
            for r in sorted(stream_rows, key=lambda r: -abs(r["risk_share"]))[:top]]
    rows = rows[::-1]
    y = np.arange(len(rows))
    h = min(0.36, 0.8 / 2)
    fig, ax = plt.subplots(figsize=(7.5, 0.42 * len(rows) + 1.4))
    ax.barh(y + h / 2 + 0.01, [100 * r["dollar_share"] for r in rows], height=h, color=SERIES[0], label="dollar share")
    ax.barh(y - h / 2 - 0.01, [100 * r["risk_share"] for r in rows], height=h, color=SERIES[1], label="risk share")
    ax.set_yticks(y, [r["stream"] for r in rows])
    ax.axvline(0, color=INK2, lw=0.8)
    _style(ax, "Where the money is vs where the risk is", "% of book", "")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower right")
    png = _save(fig, out / "risk_vs_dollar.png")
    return {"png": png, **write_rows(rows[::-1], out / "risk_vs_dollar")}


def equity_curves(out_dir: str | Path, curves: dict, *, name: str = "equity", title: str = "Equity (log scale)") -> dict:
    """Log-scale equity curves {label: Series}; each rebased to 1 at its first date."""
    out = Path(out_dir)
    if len(curves) > len(SERIES):
        raise ValidationError("too many series for a fixed-order palette; facet instead")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    frames = []
    for i, (lab, s) in enumerate(curves.items()):
        s = pd.Series(s, dtype=float).dropna()
        s = s / s.iloc[0]
        ax.plot(s.index, s.to_numpy(), color=SERIES[i], lw=2 if i == 0 else 1.6, label=lab)
        frames.append(s.rename(lab))
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    _style(ax, title, "", "growth of $1 (log)")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
    png = _save(fig, out / f"{name}.png")
    df = pd.concat(frames, axis=1)
    df.index.name = "date"
    return {"png": png, **write_rows(df.reset_index().assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d")), out / name)}


def drawdowns(out_dir: str | Path, curves: dict, *, name: str = "drawdown") -> dict:
    """Drawdown profiles DD_t = E_t / max E - 1 for each equity curve."""
    out = Path(out_dir)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    frames = []
    for i, (lab, s) in enumerate(curves.items()):
        s = pd.Series(s, dtype=float).dropna()
        dd = s / s.cummax() - 1.0
        ax.plot(dd.index, 100 * dd.to_numpy(), color=SERIES[i], lw=1.6, label=lab)
        if i == 0:
            ax.fill_between(dd.index, 100 * dd.to_numpy(), 0, color=SERIES[i], alpha=0.10, lw=0)
        frames.append(dd.rename(lab))
    _style(ax, "Drawdown from prior peak", "", "drawdown (%)")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower left")
    png = _save(fig, out / f"{name}.png")
    df = pd.concat(frames, axis=1)
    df.index.name = "date"
    return {"png": png, **write_rows(df.reset_index().assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d")), out / name)}


def environment_heatmap(out_dir: str | Path, quadrant_rows: pd.DataFrame, *, value: str = "ann_mean",
                        name: str = "environment_heatmap") -> dict:
    """Stream x joint-quadrant heatmap of ``value`` (default annualised mean
    return), diverging around 0; cell labels in ink chosen by luminance."""
    out = Path(out_dir)
    piv = quadrant_rows.pivot(index="stream", columns="quadrant", values=value)
    cols = [c for c in ("growth_up_inflation_up", "growth_up_inflation_down", "growth_down_inflation_up",
                        "growth_down_inflation_down") if c in piv.columns]
    piv = piv[cols]
    vals = 100 * piv.to_numpy(dtype=float)
    lim = np.nanmax(np.abs(vals)) if np.isfinite(vals).any() else 1.0
    fig, ax = plt.subplots(figsize=(1.6 * len(cols) + 2.5, 0.45 * len(piv) + 1.6))
    im = ax.imshow(vals, cmap=DIVERGING, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    ax.set_xticks(range(len(cols)), [c.replace("_inflation", "\ninflation").replace("_", " ") for c in cols], fontsize=8)
    ax.set_yticks(range(len(piv)), piv.index, fontsize=8)
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = vals[i, j]
            txt = "n/a" if not np.isfinite(v) else f"{v:.0f}%"
            ink = "#ffffff" if np.isfinite(v) and abs(v) > 0.6 * lim else INK
            ax.text(j, i, txt, ha="center", va="center", fontsize=8, color=ink)
    ax.set_title(f"Annualised return by economic environment ({value})", color=INK, fontsize=11, loc="left")
    ax.figure.set_facecolor(SURFACE)
    ax.tick_params(colors=INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.ax.tick_params(labelsize=7, colors=INK2)
    cb.outline.set_edgecolor(GRID)
    png = _save(fig, out / f"{name}.png")
    return {"png": png, **write_rows(quadrant_rows, out / name)}


def forward_fan(out_dir: str | Path, bands: dict, periods_per_year: float, *, name: str = "forward_fan") -> dict:
    """Wealth percentile bands over the horizon from forward.horizon_stats['_wealth_bands']."""
    out = Path(out_dir)
    keys = sorted(bands, key=float)
    H = len(bands[keys[0]])
    t = np.arange(1, H + 1) / periods_per_year
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    lo, hi = bands[keys[0]], bands[keys[-1]]
    ax.fill_between(t, lo, hi, color=SERIES[0], alpha=0.10, lw=0, label=f"{float(keys[0]):.0%}-{float(keys[-1]):.0%}")
    if len(keys) >= 4:
        ax.fill_between(t, bands[keys[1]], bands[keys[-2]], color=SERIES[0], alpha=0.20, lw=0,
                        label=f"{float(keys[1]):.0%}-{float(keys[-2]):.0%}")
    mid = keys[len(keys) // 2]
    ax.plot(t, bands[mid], color=SERIES[0], lw=2, label="median")
    ax.axhline(1.0, color=INK2, lw=0.8)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    _style(ax, "Simulated wealth (growth of $1)", "years", "wealth (log)")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper left")
    png = _save(fig, out / f"{name}.png")
    rows = [{"year": float(t[i]), **{f"q{k}": float(bands[k][i]) for k in keys}} for i in range(H)]
    return {"png": png, **write_rows(rows, out / name)}


def provenance_lines(prov: dict, now=None) -> list[str]:
    """Human-readable data-provenance block for CLI and markdown summaries:
    declared splices, price-only (total_return=False) series, cache use and
    age, coarse native sampling and every provenance warning (identical
    warnings grouped).  ``prov`` maps stream -> Provenance.to_dict() (as
    DataLoader.stream_levels returns it)."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    items = {k: v for k, v in (prov or {}).items() if isinstance(v, dict)}
    if not items:
        return ["data provenance: none recorded"]
    out = []
    for k, v in items.items():
        for px in v.get("proxies") or []:
            out.append(f"- {k}: SPLICED onto proxy {px.get('proxy')} before {px.get('used_before')}"
                       + (f" ({px['note']})" if px.get("note") else ""))
        if v.get("total_return") is False:
            out.append(f"- {k}: price-only (total_return=False): dividends/distributions missing")
        g = v.get("native_median_gap_days")
        if g is not None and g > 4:
            out.append(f"- {k}: marked every ~{g:.0f} days (not daily)")
    cached = {k: v.get("fetched_at") for k, v in items.items() if v.get("from_cache")}
    if cached:
        ages = {}
        for k, f in cached.items():
            try:
                t = pd.Timestamp(f)
                t = t.tz_localize("UTC") if t.tzinfo is None else t
                ages[k] = (now - t).total_seconds() / 86400.0
            except (TypeError, ValueError):
                ages[k] = float("nan")
        known = {k: a for k, a in ages.items() if math.isfinite(a)}
        if known:
            oldest = max(known, key=known.get)
            a = known[oldest]
            age = f"{a * 24:.1f} hours" if a < 2 else f"{a:.0f} days"
            out.append(f"- {len(cached)} series served from cache; oldest {oldest} fetched {cached[oldest]} ({age} old)")
        else:
            out.append(f"- {len(cached)} series served from cache (fetch time unknown)")
    groups: dict[str, list] = {}
    for k, v in items.items():
        for w in v.get("warnings") or []:
            groups.setdefault(str(w), []).append(k)
    for w, ks in groups.items():
        out.append(f"- warning: {w} [{', '.join(ks)}]")
    head = f"data provenance ({len(items)} series):"
    return [head] + (out or ["- all total-return, no proxies, no warnings"])


def markdown_table(rows: list, cols: list, fmt: dict | None = None) -> str:
    """Render rows as a markdown table (fmt: column -> format string)."""
    fmt = fmt or {}
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c)
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                cells.append("n/a")
            elif c in fmt:
                cells.append(format(v, fmt[c]))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)
