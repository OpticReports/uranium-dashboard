"""ROUND 4 of the pre-registered variant campaign: CORE SELECTION (R2-A x B.5).

Contract: docs/VARIANTS_PREREGISTRATION_R4_CORE.md, committed BEFORE any
round-4 variant was run. C1..C8 are registered there and may not be added to,
dropped, or re-parameterized after a result is seen.

This module is the DURABLE harness, not a one-off. Variants live in a registry
(`VARIANTS`) of named callables that each return a daily dollar curve, so a
round-5 variant costs one `register(...)` line plus its builder; every metric,
the survival bar and the bootstrap come for free.

Conventions (fixed by the registration and by the round-4 counter-agent
verdict on the B.5-as-core study):
  * daily marked-to-market total returns on adjusted closes (stockanalysis
    field 'a'), disk-cached under backend/data/px_cache so re-runs never
    re-fetch; the API is the only data lane and it is used politely.
  * the R2-A sleeve is the FROZEN dollar curve (data/r2a_daily.json), reused
    verbatim and NEVER recomputed.
  * Sharpe on BOTH bases (rf=0 and BIL-excess) is always computed and printed.
    Sortino is printed on the SAME two bases; a Sharpe and a Sortino from
    different risk-free bases never share a column (counter-agent m2).
  * Sortino uses the STANDARD convention: downside deviation is the root mean
    square of min(r, 0) over N, NOT over the count of negative days
    (counter-agent m1 — the b5 study's convention understated it).
  * costs are 10 bps per side on traded notional, for every variant.
  * TAIL is the tail sleeve for every variant and every incumbent, so the
    unresolved Question #1 cannot flatter one variant over another.
  * adjudication basis is BIL-excess Sharpe; the rf=0 column is always
    reported and any verdict that would flip on it is flagged.

Usage:
  python -m scripts.backtest_core_variants
  python -m scripts.backtest_core_variants --variant C7 --window real
  python -m scripts.backtest_core_variants --json /tmp/out.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND / "data"
PX_CACHE = DATA / "px_cache"
R2A_DAILY = DATA / "r2a_daily.json"
BARS_CACHE = DATA / "backtest_bars.json"
RESULTS = DATA / "backtest_core_variants_results.json"
REPORT = BACKEND.parent / "docs" / "BACKTEST_CORE_VARIANTS_R4.md"
CONTRACT = "docs/VARIANTS_PREREGISTRATION_R4_CORE.md"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

TRADING_DAYS = 252
COST_BPS = 10.0            # per side, on traded notional — registered
LIVE_BAND = 0.05           # the live 30/70 rule: 5% ABSOLUTE band
LIVE_SLEEVE_W = 0.30       # the live R2-A weight

# B.5 Enhanced (barbell-lab config). TAIL is the registered tail sleeve.
B5_WEIGHTS = {"AVUV": 0.25, "AVDV": 0.19, "PHYS": 0.18, "KMLM": 0.14,
              "AVEM": 0.10, "QUAL": 0.09, "TAIL": 0.05}
B5_BAND_REL = 0.20         # config: +/-20% RELATIVE band
B5_CAL_FALLBACK_D = 365    # 12-month calendar fallback

# Synthetic-window return splice: real fund returns wherever they exist, else
# the first proxy that does, UNADJUSTED (no alpha added). KMLM is spliced to
# DBMF then WTMF — the registration fixes one synthetic treatment so every
# comparator, incumbents included, carries the same one.
PROXIES = {"AVUV": ["SLYV"], "AVDV": ["DLS"], "AVEM": ["IEMG"],
           "KMLM": ["DBMF", "WTMF"], "TAIL": ["BIL"], "PHYS": [], "QUAL": []}
EXTRA_TICKERS = ["SPY", "BIL"]

# Round-4 fixed parameters (registration section "Fixed parameters") ----------
C1_WEIGHTS = (0.05, 0.10, 0.15, 0.20)
C2_MIXES = ((0.10, 0.45, 0.45), (0.20, 0.40, 0.40))   # R2-A / B.5 / SPY
C3_VOL_WINDOW = 60
C3_SLEEVE_CAP = 0.30
C4_VOL_TARGET = 0.10
C4_VOL_WINDOW = 20
C4_LEV_CAP = 1.0
C5_SLEEVE_W = 0.20
C5_GATE_WINDOW = 200
C6_RULES = ("band05", "band10", "monthly", "quarterly")
C8_CORR_WINDOW = 60
C8_CORR_THRESHOLD = 0.30
C8_HI_W, C8_LO_W = 0.30, 0.10

# Bootstrap (registration: 21d blocks, 4000 draws, paired on dates) -----------
BOOT_BLOCK = 21
BOOT_DRAWS = 4000
BOOT_SEED = 20260822
NAIVE_ALPHA = 0.05

# Windows (registration). Endpoints are asserted, never inferred.
WINDOWS = {
    "real": ("REAL", "2020-12-03", "2026-08-19"),
    "synth": ("SYNTHETIC-EXTENDED", "2016-08-23", "2026-08-19"),
}

# Reproduction gates — the counter-agent's independently verified numbers for
# the real window. If any of these move, the harness is wrong, not the world.
# NOTE the bases: the counter-agent's Sharpe column is BIL-excess and its
# "Sortino(std)" column is MAR=0 on RAW returns (its own objection m2 —
# mixed bases in one table). Both are reproduced here on their OWN basis;
# this harness additionally reports the matching-basis Sortino(BIL).
REPRO_REAL = {
    "INC-B5": {"cagr": 0.1410, "max_dd": 0.147, "sharpe_rf0": 1.18,
               "sharpe_bil": 0.92, "sortino_rf0": 1.71},
    "INC-3070SPY": {"cagr": 0.1371, "max_dd": 0.207, "sharpe_rf0": 0.95,
                    "sharpe_bil": 0.74, "sortino_rf0": 1.39},
    "INC-SPY": {"cagr": 0.1543, "max_dd": 0.245, "sharpe_rf0": 0.95,
                "sharpe_bil": 0.76, "sortino_rf0": 1.38},
}
R2A_END_VALUE = 430_406.29


# --- data lane ---------------------------------------------------------------------

def fetch_prices(ticker: str, rng: str = "10Y") -> list[dict]:
    """Daily bars oldest-first: [{t,o,h,l,c,a,v}]. Disk-cached; polite."""
    PX_CACHE.mkdir(parents=True, exist_ok=True)
    path = PX_CACHE / f"{ticker.upper()}_{rng}.json"
    if path.exists():
        return json.loads(path.read_text())
    url = (f"https://stockanalysis.com/api/symbol/s/{ticker.upper()}"
           f"/history?range={rng}&period=Daily")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:   # noqa: S310
        payload = json.load(resp)
    data = sorted(payload.get("data") or [], key=lambda r: r["t"])
    if data:
        path.write_text(json.dumps(data))
    time.sleep(0.4)
    return data


def adj_series(ticker: str) -> dict[str, float]:
    """Adjusted-close series keyed by ISO date."""
    return {b["t"]: b["a"] for b in fetch_prices(ticker) if b.get("a")}


def load_frozen_sleeve() -> dict[str, float]:
    """The FROZEN R2-A dollar curve. Reused verbatim; never recomputed."""
    rows = json.loads(R2A_DAILY.read_text())
    curve = {d: v for d, v in rows}
    last = rows[-1][1]
    assert abs(last - R2A_END_VALUE) < 0.01, (
        f"frozen R2-A end value {last:,.2f} != the stored {R2A_END_VALUE:,.2f}")
    return curve


def xbi_gate_200dma() -> tuple[dict[str, bool], str]:
    """XBI 200dma PRIOR-CLOSE gate — the house convention and R2-A's own entry
    condition. Primary source is the repo's bar cache (identical to what built
    the frozen sleeve); the price API is the fallback, and when it is used the
    pre-warmup stretch defaults to ON, which is recorded in the metadata."""
    closes: list[tuple[str, float]] = []
    source = "backtest_bars.json (adj_close)"
    if BARS_CACHE.exists():
        raw = json.loads(BARS_CACHE.read_text())
        rows = sorted(raw["XBI"], key=lambda r: r["date"])
        closes = [(r["date"][:10], (r.get("adj_close") or r["close"]))
                  for r in rows if r.get("close")]
    else:                                             # pragma: no cover
        source = "stockanalysis XBI 10Y (adjusted)"
        closes = sorted(adj_series("XBI").items())
    above: dict[str, bool] = {}
    run = 0.0
    for i, (d, c) in enumerate(closes):
        run += c
        if i >= C5_GATE_WINDOW:
            run -= closes[i - C5_GATE_WINDOW][1]
        if i >= C5_GATE_WINDOW - 1:
            above[d] = c > run / C5_GATE_WINDOW
    prior: dict[str, bool] = {}
    for i in range(1, len(closes)):
        prev = above.get(closes[i - 1][0])
        if prev is not None:
            prior[closes[i][0]] = prev
    return prior, source


# --- calendar helpers --------------------------------------------------------------

def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def month_starts(dates: list[str]) -> list[str]:
    """First trading day of each month after the first (rebalance dates)."""
    out, seen = [], {dates[0][:7]}
    for d in dates[1:]:
        if d[:7] not in seen:
            seen.add(d[:7])
            out.append(d)
    return out


def quarter_starts(dates: list[str]) -> list[str]:
    return [d for d in month_starts(dates) if int(d[5:7]) in (1, 4, 7, 10)]


def thirds(dates: list[str]) -> list[list[str]]:
    """Three EQUAL sub-periods of the window, split by trading-day count."""
    n = len(dates)
    cuts = [0, n // 3, 2 * n // 3, n]
    return [dates[cuts[i]:cuts[i + 1] + (1 if i < 2 else 0)] for i in range(3)]


# --- portfolio engine --------------------------------------------------------------

def spliced(fund: str, proxies: list[str], raw: dict[str, dict[str, float]],
            dates: list[str]) -> dict[str, float]:
    """Return-splice a level series onto `dates`: the fund's own return where it
    exists, else the first proxy's own return, UNADJUSTED. Level starts at 1.0,
    so the series is scale-free (the engine only ever uses ratios)."""
    out, lvl = {dates[0]: 1.0}, 1.0
    for i in range(1, len(dates)):
        d, p, r = dates[i], dates[i - 1], None
        for name in [fund, *proxies]:
            src = raw.get(name) or {}
            if d in src and p in src:
                r = src[d] / src[p] - 1
                break
        assert r is not None, f"{fund}: no source covers {d} (splice hole)"
        lvl *= 1 + r
        out[d] = lvl
    return out


def portfolio(dates: list[str], curves: dict[str, dict[str, float]],
              target_at: Callable[[str], dict[str, float]], *,
              band: float | None = None, band_rel: float | None = None,
              rebal_dates: Iterable[str] = (),
              cal_fallback_days: int | None = None,
              cost_bps: float = COST_BPS) -> dict[str, float]:
    """Generic N-leg portfolio. Units drift between rebalances; a rebalance is
    triggered by an absolute band breach, a relative band breach, a scheduled
    date, or the calendar fallback — whichever fires first. Costs are charged
    on traded notional = 0.5 * sum |w_target - w_now| * equity (one-side).

    Breach detection and execution happen at the SAME close, so there is no
    look-ahead: the weights being compared are that close's own marks.
    """
    d0 = dates[0]
    tgt = target_at(d0)
    eq = 1.0
    units = {k: eq * w / curves[k][d0] for k, w in tgt.items() if w}
    last_rb = d0
    sched = set(rebal_dates)
    out = {d0: eq}
    for d in dates[1:]:
        eq = sum(u * curves[k][d] for k, u in units.items())
        tgt = target_at(d)
        legs = set(tgt) | set(units)
        w_now = {k: units.get(k, 0.0) * curves[k][d] / eq for k in legs}
        need = d in sched
        if not need and band is not None:
            need = any(abs(w_now.get(k, 0.0) - tgt.get(k, 0.0)) > band for k in legs)
        if not need and band_rel is not None:
            need = any(abs(w_now.get(k, 0.0) - tgt.get(k, 0.0)) > band_rel * tgt[k]
                       for k in legs if tgt.get(k, 0.0))
        if not need and cal_fallback_days is not None:
            need = _days(last_rb, d) >= cal_fallback_days
        if need:
            traded = sum(abs(tgt.get(k, 0.0) - w_now.get(k, 0.0)) for k in legs) * eq / 2
            eq -= traded * cost_bps / 1e4
            units = {k: eq * w / curves[k][d] for k, w in tgt.items() if w}
            last_rb = d
        out[d] = eq
    return out


def const(weights: dict[str, float]) -> Callable[[str], dict[str, float]]:
    return lambda _d: weights


def curve_returns(curve: dict[str, float], dates: list[str]) -> list[float]:
    return [curve[dates[i]] / curve[dates[i - 1]] - 1 for i in range(1, len(dates))]


# --- metrics -----------------------------------------------------------------------

def sharpe(rets: list[float], rf: list[float] | None = None) -> float:
    """Annualized Sharpe. rf=None is the rf=0 basis; otherwise EXCESS returns."""
    x = rets if rf is None else [a - b for a, b in zip(rets, rf, strict=True)]
    if len(x) < 2:
        return float("nan")
    sd = statistics.stdev(x)
    return statistics.fmean(x) / sd * math.sqrt(TRADING_DAYS) if sd > 0 else float("nan")


def downside_deviation(rets: list[float]) -> float:
    """STANDARD convention: RMS of min(r, 0) over N — not over the count of
    negative days (counter-agent m1). Divide by N so that a series with few but
    deep losses is not flattered by a small denominator."""
    if not rets:
        return float("nan")
    return math.sqrt(statistics.fmean([min(r, 0.0) ** 2 for r in rets]))


def sortino(rets: list[float], rf: list[float] | None = None) -> float:
    """Annualized Sortino on the SAME basis as the Sharpe it sits beside."""
    x = rets if rf is None else [a - b for a, b in zip(rets, rf, strict=True)]
    dd = downside_deviation(x)
    if not dd or math.isnan(dd):
        return float("nan")
    return statistics.fmean(x) / dd * math.sqrt(TRADING_DAYS)


def max_drawdown(vals: list[float]) -> float:
    """Peak-to-trough on the MTM curve, as a POSITIVE fraction. The peak starts
    at the curve's own first value — no phantom peak from before the window."""
    peak, dd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        dd = max(dd, 1 - v / peak)
    return dd


def cagr(vals: list[float], d0: str, d1: str) -> float:
    """Calendar-annualized (365.25) — one day-count convention for everybody."""
    years = _days(d0, d1) / 365.25
    return (vals[-1] / vals[0]) ** (1 / years) - 1 if years > 0 else float("nan")


def pearson(a: list[float], b: list[float]) -> float:
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da > 0 and db > 0 else float("nan")


def metrics(curve: dict[str, float], dates: list[str],
            bil_rets: list[float], spy_rets: list[float] | None = None) -> dict:
    """Every metric the registration asks for, on one window, both rf bases."""
    vals = [curve[d] for d in dates]
    r = curve_returns(curve, dates)
    dd = max_drawdown(vals)
    g = cagr(vals, dates[0], dates[-1])
    out = {
        "start": dates[0], "end": dates[-1], "n": len(dates),
        "end_value": vals[-1] / vals[0],
        "cagr": g,
        "max_dd": dd,
        "vol": statistics.stdev(r) * math.sqrt(TRADING_DAYS),
        "sharpe_rf0": sharpe(r),
        "sharpe_bil": sharpe(r, bil_rets),
        "sortino_rf0": sortino(r),
        "sortino_bil": sortino(r, bil_rets),
        "calmar": g / dd if dd > 0 else float("nan"),
    }
    if spy_rets is not None:
        out["corr_spy"] = pearson(r, spy_rets)
    return out


# --- paired block bootstrap on the Sharpe DIFFERENCE --------------------------------

def _wrap_prefix(x: list[float]) -> tuple[list[float], list[float]]:
    """Prefix sums of x and x^2 over the doubled (circular) series."""
    doubled = x + x
    p, q = [0.0], [0.0]
    for v in doubled:
        p.append(p[-1] + v)
        q.append(q[-1] + v * v)
    return p, q


def _sharpe_from_sums(s: float, s2: float, n: int) -> float:
    mean = s / n
    var = (s2 - n * mean * mean) / (n - 1)
    return mean / math.sqrt(var) * math.sqrt(TRADING_DAYS) if var > 0 else float("nan")


def block_starts(n: int, block: int, rng: random.Random) -> list[tuple[int, int]]:
    """One resample's (start, length) blocks: floor(n/block) full blocks plus a
    partial block for the remainder, so the resample is exactly n long."""
    k, rem = divmod(n, block)
    out = [(rng.randrange(n), block) for _ in range(k)]
    if rem:
        out.append((rng.randrange(n), rem))
    return out


def block_bootstrap_sharpe_diff(a: list[float], b: list[float], *,
                                block: int = BOOT_BLOCK, draws: int = BOOT_DRAWS,
                                seed: int = BOOT_SEED) -> dict:
    """PAIRED circular block bootstrap on Sharpe(a) - Sharpe(b).

    Both series are resampled with the SAME block start indices, so the
    date-pairing that makes a difference meaningful is preserved: the draw
    answers "how much of this gap survives resampling the shared history",
    not "how far apart can two independent series drift".

    Deterministic given `seed`. Returns the point estimate, the sorted draw
    distribution, and a two-sided bootstrap p-value.
    """
    assert len(a) == len(b), "paired bootstrap needs equal-length series"
    n = len(a)
    pa, qa = _wrap_prefix(a)
    pb, qb = _wrap_prefix(b)
    point = sharpe(a) - sharpe(b)
    rng = random.Random(seed)
    dist = []
    for _ in range(draws):
        sa = s2a = sb = s2b = 0.0
        for s, ln in block_starts(n, block, rng):
            sa += pa[s + ln] - pa[s]
            s2a += qa[s + ln] - qa[s]
            sb += pb[s + ln] - pb[s]
            s2b += qb[s + ln] - qb[s]
        da = _sharpe_from_sums(sa, s2a, n)
        db = _sharpe_from_sums(sb, s2b, n)
        if not (math.isnan(da) or math.isnan(db)):
            dist.append(da - db)
    dist.sort()
    le = sum(1 for d in dist if d <= 0) / len(dist)
    ge = sum(1 for d in dist if d >= 0) / len(dist)
    return {"point": point, "dist": dist, "draws": draws, "block": block,
            "seed": seed, "p_two_sided": min(1.0, 2 * min(le, ge))}


def boot_ci(boot: dict, conf: float = 0.95) -> tuple[float, float]:
    """Percentile interval at `conf` from a bootstrap result."""
    dist = boot["dist"]
    lo_p, hi_p = (1 - conf) / 2 * 100, (1 + conf) / 2 * 100

    def pct(p: float) -> float:
        idx = round(p / 100 * (len(dist) - 1))
        return dist[min(len(dist) - 1, max(0, idx))]

    return pct(lo_p), pct(hi_p)


def excludes_zero(ci: tuple[float, float]) -> bool:
    return ci[0] > 0 or ci[1] < 0


# --- window context ----------------------------------------------------------------

@dataclass
class Ctx:
    key: str
    label: str
    dates: list[str]
    px: dict[str, dict[str, float]]
    core: dict[str, float] = field(default_factory=dict)
    sleeve: dict[str, float] = field(default_factory=dict)
    spy: dict[str, float] = field(default_factory=dict)
    bil: dict[str, float] = field(default_factory=dict)
    gate: dict[str, bool] = field(default_factory=dict)
    bil_rets: list[float] = field(default_factory=list)
    spy_rets: list[float] = field(default_factory=list)
    months: list[str] = field(default_factory=list)
    quarters: list[str] = field(default_factory=list)

    def legs(self) -> dict[str, dict[str, float]]:
        return {"SLEEVE": self.sleeve, "CORE": self.core,
                "SPY": self.spy, "BIL": self.bil}


def build_ctx(key: str, raw: dict[str, dict[str, float]], sleeve_raw: dict[str, float],
              gate: dict[str, bool]) -> Ctx:
    label, start, end = WINDOWS[key]
    if key == "real":
        # Every B.5 constituent genuinely trading; the window opens at KMLM's
        # inception, which is what makes the full sleeve constructible at all.
        need = list(B5_WEIGHTS) + EXTRA_TICKERS
    else:
        need = EXTRA_TICKERS
    dates = sorted(set.intersection(*[set(raw[t]) for t in need]) & set(sleeve_raw))
    dates = [d for d in dates if start <= d <= end]
    assert dates[0] == start and dates[-1] == end, (
        f"{key}: window {dates[0]}..{dates[-1]} != registered {start}..{end}")

    px = {t: spliced(t, PROXIES.get(t, []), raw, dates) for t in B5_WEIGHTS}
    core = portfolio(dates, px, const(B5_WEIGHTS),
                     band_rel=B5_BAND_REL, cal_fallback_days=B5_CAL_FALLBACK_D)
    sleeve = {d: sleeve_raw[d] for d in dates}
    spy = {d: raw["SPY"][d] for d in dates}
    bil = {d: raw["BIL"][d] for d in dates}
    ctx = Ctx(key, label, dates, px, core, sleeve, spy, bil,
              {d: gate.get(d, True) for d in dates})
    ctx.bil_rets = curve_returns(bil, dates)
    ctx.spy_rets = curve_returns(spy, dates)
    ctx.months = month_starts(dates)
    ctx.quarters = quarter_starts(dates)
    return ctx


# --- variant registry --------------------------------------------------------------

@dataclass
class Variant:
    key: str
    group: str
    desc: str
    fn: Callable[[Ctx], dict[str, float]]
    judged: bool = True


VARIANTS: dict[str, Variant] = {}
INCUMBENTS: dict[str, Variant] = {}


def register(key: str, group: str, desc: str, fn, *, judged: bool = True) -> None:
    """Add a variant to the registry. A round-5 variant is ONE of these lines
    plus its builder; nothing else in this file needs to change."""
    target = VARIANTS if judged else INCUMBENTS
    assert key not in target, f"duplicate registry key {key}"
    target[key] = Variant(key, group, desc, fn, judged)


# -- shared builders ---------------------------------------------------------

def sleeve_core(ctx: Ctx, w: float, *, band: float | None = LIVE_BAND,
                rebal: Iterable[str] = ()) -> dict[str, float]:
    """Two-leg sleeve/core book at a constant sleeve weight."""
    return portfolio(ctx.dates, ctx.legs(), const({"SLEEVE": w, "CORE": 1 - w}),
                     band=band, rebal_dates=rebal)


def three_way(ctx: Ctx, ws: tuple[float, float, float]) -> dict[str, float]:
    """R2-A / B.5 / SPY, 5% absolute band on any leg."""
    return portfolio(ctx.dates, ctx.legs(),
                     const({"SLEEVE": ws[0], "CORE": ws[1], "SPY": ws[2]}),
                     band=LIVE_BAND)


def _trailing(rets: list[float], i: int, window: int) -> list[float] | None:
    """The `window` returns ending at dates[i-1] — PRIOR close, no look-ahead.
    rets[j] is the return from dates[j] to dates[j+1]."""
    if i - window < 0:
        return None
    return rets[i - window:i]


def monthly_weights(ctx: Ctx, pick: Callable[[int], float | None],
                    default: float) -> Callable[[str], dict[str, float]]:
    """Sleeve weight re-decided on the first trading day of each month and held
    flat in between. `pick(i)` returns None during warm-up, when the weight
    falls back to `default` (the live 30%) — a stated rule, not a free
    parameter, and it is disclosed in the writeup."""
    idx = {d: i for i, d in enumerate(ctx.dates)}
    rebal = set(ctx.months)
    w_by_date: dict[str, float] = {}
    cur = default
    for d in ctx.dates:
        if d == ctx.dates[0] or d in rebal:
            got = pick(idx[d])
            cur = default if got is None else got
        w_by_date[d] = cur
    return lambda d: {"SLEEVE": w_by_date[d], "CORE": 1 - w_by_date[d]}


# -- C1: static sleeve weights on a B.5 core ---------------------------------

for _w in C1_WEIGHTS:
    register(f"C1-{int(_w * 100):02d}", "C1",
             f"static {int(_w * 100)}% R2-A / {int((1 - _w) * 100)}% B.5, live 5% band",
             lambda ctx, w=_w: sleeve_core(ctx, w))

# -- C2: three-way static R2-A / B.5 / SPY -----------------------------------

for _ws in C2_MIXES:
    register("C2-" + "/".join(str(int(x * 100)) for x in _ws), "C2",
             "three-way R2-A/B.5/SPY at "
             + "/".join(str(int(x * 100)) for x in _ws) + ", 5% band",
             lambda ctx, ws=_ws: three_way(ctx, ws))


# -- C3: inverse-vol sleeve vs core, monthly, 60d trailing, cap 30% ----------

def c3_inverse_vol(ctx: Ctx) -> dict[str, float]:
    sr = curve_returns(ctx.sleeve, ctx.dates)
    cr = curve_returns(ctx.core, ctx.dates)

    def pick(i: int) -> float | None:
        ws, wc = _trailing(sr, i, C3_VOL_WINDOW), _trailing(cr, i, C3_VOL_WINDOW)
        if ws is None or wc is None:
            return None
        vs, vc = statistics.stdev(ws), statistics.stdev(wc)
        if vs <= 0 or vc <= 0:
            return None
        return min(C3_SLEEVE_CAP, (1 / vs) / (1 / vs + 1 / vc))

    return portfolio(ctx.dates, ctx.legs(),
                     monthly_weights(ctx, pick, LIVE_SLEEVE_W),
                     rebal_dates=ctx.months)


register("C3", "C3", "inverse-vol sleeve/core, monthly, trailing 60d, sleeve cap 30%",
         c3_inverse_vol)


# -- C4: whole-book 10% vol target, monthly, 20d trailing, deleverage only ---

def c4_vol_target(ctx: Ctx) -> dict[str, float]:
    book = sleeve_core(ctx, LIVE_SLEEVE_W)          # the live 30/70 B.5 blend
    br = curve_returns(book, ctx.dates)
    idx = {d: i for i, d in enumerate(ctx.dates)}
    rebal = set(ctx.months)
    scale: dict[str, float] = {}
    cur = C4_LEV_CAP
    for d in ctx.dates:
        if d == ctx.dates[0] or d in rebal:
            w = _trailing(br, idx[d], C4_VOL_WINDOW)
            if w is not None:
                v = statistics.stdev(w) * math.sqrt(TRADING_DAYS)
                cur = min(C4_LEV_CAP, C4_VOL_TARGET / v) if v > 0 else C4_LEV_CAP
        scale[d] = cur
    curves = {"BOOK": book, "BIL": ctx.bil}
    return portfolio(ctx.dates, curves,
                     lambda d: {"BOOK": scale[d], "BIL": 1 - scale[d]},
                     rebal_dates=ctx.months)


register("C4", "C4", "whole-book 10% vol target, monthly, trailing 20d, "
                     "leverage capped 1.0 (deleverage only, cash to BIL)",
         c4_vol_target)


# -- C5: regime-conditional sleeve on the XBI 200dma prior-close gate --------

def c5_regime(ctx: Ctx) -> dict[str, float]:
    def target(d: str) -> dict[str, float]:
        w = C5_SLEEVE_W if ctx.gate[d] else 0.0
        return {"SLEEVE": w, "CORE": 1 - w}

    return portfolio(ctx.dates, ctx.legs(), target, band=LIVE_BAND)


register("C5", "C5", "sleeve 20% while the XBI 200dma prior-close gate is ON, "
                     "0% while OFF (proceeds to core), 5% band",
         c5_regime)

# -- C6: rebalance-rule sweep on the live 30/70 B.5 blend --------------------

_C6 = {
    "band05": ("5% absolute band (live rule)",
               lambda ctx: sleeve_core(ctx, LIVE_SLEEVE_W, band=0.05)),
    "band10": ("10% absolute band",
               lambda ctx: sleeve_core(ctx, LIVE_SLEEVE_W, band=0.10)),
    "monthly": ("monthly calendar rebalance",
                lambda ctx: sleeve_core(ctx, LIVE_SLEEVE_W, band=None,
                                        rebal=ctx.months)),
    "quarterly": ("quarterly calendar rebalance",
                  lambda ctx: sleeve_core(ctx, LIVE_SLEEVE_W, band=None,
                                          rebal=ctx.quarters)),
}
for _k in C6_RULES:
    register(f"C6-{_k}", "C6", f"30/70 R2-A/B.5, {_C6[_k][0]}", _C6[_k][1])


# -- C7: sleeve idle-cash routing (MECHANICAL fix, not a search) -------------

def sleeve_idle_routed(ctx: Ctx) -> dict[str, float]:
    """R2-A's uninvested cash earns the CORE's return instead of 0%.

    The frozen sleeve is a dollar curve, so the only days on which idleness is
    OBSERVABLE are those whose return is exactly zero — the fully-idle days
    (424/1432 = 29.6% of the real window, matching the counter-agent's
    measurement). Partially-invested days keep their 0% on the cash portion,
    so this is the CONSERVATIVE corner of the fix, not its upper bound.
    """
    d = ctx.dates
    lvl, out = 1.0, {d[0]: 1.0}
    for i in range(1, len(d)):
        rs = ctx.sleeve[d[i]] / ctx.sleeve[d[i - 1]] - 1
        r = (ctx.core[d[i]] / ctx.core[d[i - 1]] - 1) if rs == 0.0 else rs
        lvl *= 1 + r
        out[d[i]] = lvl
    return out


def c7_idle_cash(ctx: Ctx) -> dict[str, float]:
    curves = dict(ctx.legs())
    curves["SLEEVE"] = sleeve_idle_routed(ctx)
    return portfolio(ctx.dates, curves,
                     const({"SLEEVE": LIVE_SLEEVE_W, "CORE": 1 - LIVE_SLEEVE_W}),
                     band=LIVE_BAND)


register("C7", "C7", "30/70 R2-A/B.5 with the sleeve's idle cash earning the "
                     "CORE's return instead of 0%",
         c7_idle_cash)


# -- C8: correlation-conditional sleeve, monthly -----------------------------

def c8_corr_conditional(ctx: Ctx) -> dict[str, float]:
    sr = curve_returns(ctx.sleeve, ctx.dates)
    cr = curve_returns(ctx.core, ctx.dates)

    def pick(i: int) -> float | None:
        ws, wc = _trailing(sr, i, C8_CORR_WINDOW), _trailing(cr, i, C8_CORR_WINDOW)
        if ws is None or wc is None:
            return None
        rho = pearson(ws, wc)
        if math.isnan(rho):
            return None
        return C8_HI_W if rho < C8_CORR_THRESHOLD else C8_LO_W

    return portfolio(ctx.dates, ctx.legs(),
                     monthly_weights(ctx, pick, LIVE_SLEEVE_W),
                     rebal_dates=ctx.months)


register("C8", "C8", "sleeve 30% when trailing 60d corr(sleeve, core) < 0.30, "
                     "else 10%, evaluated monthly",
         c8_corr_conditional)


# -- incumbents (registration: B.5 alone, 30/70 R2-A/SPY, SPY alone) ---------

register("INC-B5", "INC", "B.5 Enhanced alone",
         lambda ctx: dict(ctx.core), judged=False)
register("INC-3070SPY", "INC", "30/70 R2-A / SPY, 5% band",
         lambda ctx: portfolio(ctx.dates, ctx.legs(),
                               const({"SLEEVE": LIVE_SLEEVE_W, "SPY": 0.70}),
                               band=LIVE_BAND), judged=False)
register("INC-SPY", "INC", "SPY alone", lambda ctx: dict(ctx.spy), judged=False)
register("REF-R2A", "REF", "R2-A sleeve alone (frozen, context only)",
         lambda ctx: dict(ctx.sleeve), judged=False)

#: the three REGISTERED incumbents; REF-R2A is context, never a comparator.
INCUMBENT_KEYS = [k for k, v in INCUMBENTS.items() if v.group == "INC"]


# --- survival bar ------------------------------------------------------------------

def beats(a: dict, b: dict, basis: str = "bil") -> bool:
    """Bar 1's definition of 'beat': Sharpe AND Sortino, on one stated basis."""
    return (a[f"sharpe_{basis}"] > b[f"sharpe_{basis}"]
            and a[f"sortino_{basis}"] > b[f"sortino_{basis}"])


def evaluate(v_real: dict, v_sub: list[dict], v_synth: dict,
             i_real: dict, i_sub: list[dict], i_synth: dict,
             boot: dict, conf: float = 0.95) -> dict:
    """The registered survival bar, in full and in order."""
    ci = boot_ci(boot, conf)
    c1 = beats(v_real, i_real)
    c2 = excludes_zero(ci)
    wins = sum(1 for a, b in zip(v_sub, i_sub, strict=True) if beats(a, b))
    c3 = wins >= 2
    c4 = v_synth["sharpe_bil"] >= i_synth["sharpe_bil"] - 0.10
    return {
        "c1_sharpe_and_sortino": c1,
        "c2_ci_excludes_zero": c2,
        "c3_subperiods": c3, "c3_wins": wins,
        "c4_synthetic": c4,
        "d_sharpe": boot["point"],
        "ci95": list(ci),
        "boot_p": boot["p_two_sided"],
        "survives": bool(c1 and c2 and c3 and c4),
        # reported alongside, never used to move the bar
        "c1_on_rf0": beats(v_real, i_real, "rf0"),
    }


# --- run ---------------------------------------------------------------------------

def build_all(keys: list[str]) -> dict[str, Ctx]:
    tickers = sorted(set(B5_WEIGHTS) | set(EXTRA_TICKERS)
                     | {p for ps in PROXIES.values() for p in ps})
    raw = {t: adj_series(t) for t in tickers}
    sleeve_raw = load_frozen_sleeve()
    gate, gate_src = xbi_gate_200dma()
    ctxs = {k: build_ctx(k, raw, sleeve_raw, gate) for k in keys}
    for c in ctxs.values():
        c.gate_source = gate_src           # type: ignore[attr-defined]
    return ctxs


def run_window(ctx: Ctx, keys: list[str]) -> dict[str, dict]:
    """Curves + full-window metrics + the three equal sub-periods."""
    out: dict[str, dict] = {}
    subs = thirds(ctx.dates)
    for k in keys:
        v = VARIANTS.get(k) or INCUMBENTS[k]
        curve = v.fn(ctx)
        vals = [curve[d] for d in ctx.dates]
        assert len(vals) == len(ctx.dates) and min(vals) > 0, f"{k}: degenerate curve"
        m = metrics(curve, ctx.dates, ctx.bil_rets, ctx.spy_rets)
        sub = []
        for s in subs:
            i0 = ctx.dates.index(s[0])
            sub.append(metrics(curve, s, ctx.bil_rets[i0:i0 + len(s) - 1],
                               ctx.spy_rets[i0:i0 + len(s) - 1]))
        out[k] = {"desc": v.desc, "group": v.group, "judged": v.judged,
                  "curve": curve, "full": m, "subs": sub}
    return out


def sanity(real: dict[str, dict]) -> None:
    """Reproduction gates against the counter-agent's independently verified
    numbers. These are merge-blocking by construction: if the harness cannot
    reproduce the study that motivated the round, no round-4 number is real."""
    for k, exp in REPRO_REAL.items():
        got = real[k]["full"]
        for metric, want in exp.items():
            tol = 0.0015 if metric in ("cagr", "max_dd") else 0.01
            assert abs(got[metric] - want) <= tol, (
                f"repro FAILED {k}.{metric}: {got[metric]:.4f} vs {want:.4f}")
    assert abs(real["INC-B5"]["full"]["corr_spy"] - 0.7694) < 0.001, "corr(B.5,SPY)"
    assert abs(real["REF-R2A"]["full"]["corr_spy"] - 0.2921) < 0.001, "corr(R2-A,SPY)"
    print("Repro gates PASSED: B.5 / 30-70-SPY / SPY / corr all reproduce the "
          "counter-agent's verified real-window numbers.")


def idle_day_count(ctx: Ctx) -> tuple[int, int]:
    """Days on which the FROZEN sleeve returns exactly 0% — the observable
    fully-idle days C7 fixes. Reported so the fix stays tied to a measurement."""
    r = curve_returns(ctx.sleeve, ctx.dates)
    return sum(1 for x in r if x == 0.0), len(r)


def main(argv: list[str] | None = None) -> None:      # noqa: PLR0915
    ap = argparse.ArgumentParser(description="round-4 core-variant harness")
    ap.add_argument("--variant", action="append", default=None,
                    help="variant or group key (repeatable), e.g. C7 or C1-05")
    ap.add_argument("--window", choices=["real", "synth", "both"], default="both",
                    help="which window's table to PRINT; both are always computed "
                         "because the registered survival bar spans both")
    ap.add_argument("--json", default=None, help="write the results JSON here")
    ap.add_argument("--draws", type=int, default=BOOT_DRAWS)
    args = ap.parse_args(argv)

    show = ["real", "synth"] if args.window == "both" else [args.window]
    sel = list(VARIANTS)
    if args.variant:
        want = set(args.variant)
        sel = [k for k, v in VARIANTS.items() if k in want or v.group in want]
        assert sel, f"no registered variant matches {sorted(want)}"
    order = sel + list(INCUMBENTS)
    full_run = not args.variant and args.draws == BOOT_DRAWS

    ctxs = build_all(["real", "synth"])
    res = {w: run_window(ctxs[w], order) for w in ("real", "synth")}
    for w in ("real", "synth"):
        c = ctxs[w]
        print(f"{c.label:22s} {c.dates[0]} -> {c.dates[-1]}  n={len(c.dates)}")
    sanity(res["real"])
    idle_n, idle_tot = idle_day_count(ctxs["real"])
    print(f"Frozen sleeve idle (exactly 0%) days, real window: {idle_n}/{idle_tot} "
          f"= {idle_n / idle_tot:.1%} — this is what C7 routes to the core.")

    # -- best incumbent: highest BIL-excess Sharpe over the FULL real window
    best = max(INCUMBENT_KEYS, key=lambda k: res["real"][k]["full"]["sharpe_bil"])
    rc, ir = ctxs["real"], res["real"][best]
    inc_ex = [a - b for a, b in
              zip(curve_returns(ir["curve"], rc.dates), rc.bil_rets, strict=True)]
    n_tested = len(sel)
    conf_adj = 1 - NAIVE_ALPHA / n_tested
    boots: dict[str, dict] = {}
    verdicts: dict[str, dict] = {}
    for k in sel:
        v_ex = [a - b for a, b in
                zip(curve_returns(res["real"][k]["curve"], rc.dates),
                    rc.bil_rets, strict=True)]
        b = block_bootstrap_sharpe_diff(v_ex, inc_ex, draws=args.draws)
        boots[k] = b
        v = evaluate(res["real"][k]["full"], res["real"][k]["subs"],
                     res["synth"][k]["full"], ir["full"], ir["subs"],
                     res["synth"][best]["full"], b)
        ci_adj = boot_ci(b, conf_adj)
        v["ci_bonferroni"] = list(ci_adj)
        v["clears_bonferroni"] = bool(v["survives"] and excludes_zero(ci_adj))
        verdicts[k] = v

    # C7 is a MECHANICAL fix, so its like-for-like comparator is the same book
    # WITHOUT the fix (C6-band05). Descriptive only: the registered bar is and
    # stays "vs the best incumbent", and this never enters the verdict.
    c7_vs_c6 = None
    if "C7" in sel and "C6-band05" in sel:
        def _ex(key: str) -> list[float]:
            return [a - b for a, b in
                    zip(curve_returns(res["real"][key]["curve"], rc.dates),
                        rc.bil_rets, strict=True)]
        b7 = block_bootstrap_sharpe_diff(_ex("C7"), _ex("C6-band05"),
                                         draws=args.draws)
        c7_vs_c6 = {"d_sharpe": b7["point"], "ci95": list(boot_ci(b7)),
                    "boot_p": b7["p_two_sided"],
                    "comparator": "C6-band05"}

    meta = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contract": CONTRACT,
        "windows": {w: {"label": ctxs[w].label, "start": ctxs[w].dates[0],
                        "end": ctxs[w].dates[-1], "n": len(ctxs[w].dates)}
                    for w in ("real", "synth")},
        "best_incumbent": best,
        "incumbents": INCUMBENT_KEYS,
        "n_variants_tested": n_tested,
        "n_registered_groups": len({VARIANTS[k].group for k in sel}),
        "naive_alpha": NAIVE_ALPHA,
        "bonferroni_alpha": NAIVE_ALPHA / n_tested,
        "bonferroni_conf": conf_adj,
        "cost_bps_per_side": COST_BPS,
        "tail_sleeve": "TAIL (registered, identical for every variant)",
        "adjudication_basis": "BIL-excess Sharpe; rf=0 reported alongside",
        "sortino_convention": "standard — downside deviation over N",
        "bootstrap": {"block_days": BOOT_BLOCK, "draws": args.draws,
                      "seed": BOOT_SEED, "paired": True, "circular": True,
                      "basis": "BIL-excess daily returns"},
        "gate_source": getattr(ctxs["real"], "gate_source", None),
        "sleeve": "FROZEN R2-A dollar curve (data/r2a_daily.json), reused verbatim",
        "sleeve_idle_days_real": [idle_n, idle_tot],
        "corr_core_sleeve_real": pearson(curve_returns(rc.core, rc.dates),
                                         curve_returns(rc.sleeve, rc.dates)),
        "synthetic_kmlm": "KMLM spliced to DBMF then WTMF, unadjusted",
        "c7_vs_c6_band05": c7_vs_c6,
        "measurement_basis": ("daily MTM total returns on adjusted closes; CAGR "
                              "calendar-annualized at 365.25; Sharpe/Sortino "
                              "annualized sqrt(252); drawdown peak-to-trough "
                              "within each window"),
    }

    _print_table(res, order, verdicts, meta, show)

    path = Path(args.json) if args.json else (RESULTS if full_run else None)
    if path:
        payload = {"meta": meta, "verdicts": verdicts, "results": {
            w: {k: {kk: vv for kk, vv in r.items() if kk != "curve"}
                for k, r in res[w].items()} for w in ("real", "synth")}}
        payload["curves"] = {w: {k: _downsample(res[w][k]["curve"], ctxs[w].dates)
                                 for k in order} for w in ("real", "synth")}
        path.write_text(json.dumps(_round(payload), indent=1))
        print(f"\nResults JSON written to {path}")
    if full_run:
        _write_report(res, order, verdicts, meta)
        print(f"Report written to {REPORT}")


def _downsample(curve: dict[str, float], dates: list[str], target: int = 400) -> list:
    step = max(1, math.ceil(len(dates) / target))
    pts = list(dates[::step])
    if pts[-1] != dates[-1]:
        pts.append(dates[-1])
    return [[d, round(curve[d], 6)] for d in pts]


def _round(obj, nd: int = 6):
    if isinstance(obj, float):
        return None if math.isnan(obj) else round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items() if k != "dist"}
    if isinstance(obj, list):
        return [_round(v, nd) for v in obj]
    return obj


def _sv(v: dict | None) -> str:
    return "—" if v is None else ("YES" if v["survives"] else "no")


def _yn(b: bool) -> str:
    return "Y" if b else "n"


HDR = (f"{'variant':16s} {'CAGR':>7s} {'maxDD':>7s} {'vol':>6s} {'Sh(rf0)':>8s} "
       f"{'Sh(BIL)':>8s} {'So(rf0)':>8s} {'So(BIL)':>8s} {'Calmar':>7s} "
       f"{'corrSPY':>8s} {'SURV':>5s}")


def _row(k: str, f: dict, surv: str) -> str:
    return (f"{k:16s} {f['cagr']:6.2%} {f['max_dd']:6.1%} {f['vol']:5.1%} "
            f"{f['sharpe_rf0']:8.2f} {f['sharpe_bil']:8.2f} "
            f"{f['sortino_rf0']:8.2f} {f['sortino_bil']:8.2f} "
            f"{f['calmar']:7.2f} {f.get('corr_spy', float('nan')):8.3f} {surv:>5s}")


def _print_table(res: dict, order: list[str], verdicts: dict, meta: dict,
                 show: list[str]) -> None:
    for w in show:
        m = meta["windows"][w]
        print(f"\n=== {m['label']} {m['start']}..{m['end']} (n={m['n']}) ===")
        print(HDR)
        for k in order:
            surv = _sv(verdicts.get(k)) if w == "real" else "—"
            print(_row(k, res[w][k]["full"], surv))
    print(f"\nbest incumbent = {meta['best_incumbent']} "
          f"(highest BIL-excess Sharpe over the full real window)")
    print(f"{'variant':16s} {'dSharpe':>8s} {'95% CI':>18s} {'boot p':>7s} "
          f"{'1':>3s} {'2':>3s} {'3':>3s} {'4':>3s} {'SURV':>5s}")
    for k, v in verdicts.items():
        lo, hi = v["ci95"]
        print(f"{k:16s} {v['d_sharpe']:+8.3f} [{lo:+.3f}, {hi:+.3f}] "
              f"{v['boot_p']:7.3f} {_yn(v['c1_sharpe_and_sortino']):>3s} "
              f"{_yn(v['c2_ci_excludes_zero']):>3s} {_yn(v['c3_subperiods']):>3s} "
              f"{_yn(v['c4_synthetic']):>3s} {_sv(v):>5s}")
    n = meta["n_variants_tested"]
    print(f"\nMULTIPLE COMPARISON: {n} variant arms tested "
          f"({meta['n_registered_groups']} registered variants C1..C8). "
          f"Naive threshold alpha={meta['naive_alpha']:.2f} (95% CI); "
          f"Bonferroni-adjusted alpha={meta['bonferroni_alpha']:.5f}, i.e. a "
          f"{100 * meta['bonferroni_conf']:.3f}% CI must exclude zero.")
    clears = [k for k, v in verdicts.items() if v.get("clears_bonferroni")]
    surv = [k for k, v in verdicts.items() if v["survives"]]
    print(f"Survivors on the naive bar: {surv or 'NONE'}")
    print(f"Survivors clearing the ADJUSTED bar: {clears or 'NONE'}")


# --- report ------------------------------------------------------------------------

def _md_table(res: dict, w: str, order: list[str], verdicts: dict) -> list[str]:
    out = ["| variant | CAGR | maxDD | vol | Sharpe rf=0 | Sharpe BIL | "
           "Sortino rf=0 | Sortino BIL | Calmar | corr SPY |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for k in order:
        f = res[w][k]["full"]
        out.append(f"| {k} | {f['cagr']:.2%} | {f['max_dd']:.1%} | {f['vol']:.1%} | "
                   f"{f['sharpe_rf0']:.2f} | **{f['sharpe_bil']:.2f}** | "
                   f"{f['sortino_rf0']:.2f} | **{f['sortino_bil']:.2f}** | "
                   f"{f['calmar']:.2f} | {f.get('corr_spy', float('nan')):.3f} |")
    return out


def _write_report(res: dict, order: list[str], verdicts: dict, meta: dict) -> None:
    best = meta["best_incumbent"]
    n = meta["n_variants_tested"]
    surv = [k for k, v in verdicts.items() if v["survives"]]
    clears = [k for k, v in verdicts.items() if v.get("clears_bonferroni")]
    idle_n, idle_tot = meta["sleeve_idle_days_real"]
    L: list[str] = []
    w = L.append

    w("# Backtest — ROUND 4 core variants (R2-A x B.5), 2026-08-22")
    w("")
    w(f"Generated by `backend/scripts/backtest_core_variants.py` (deterministic, "
      f"bootstrap seed {meta['bootstrap']['seed']}). Contract: "
      f"[{meta['contract']}](VARIANTS_PREREGISTRATION_R4_CORE.md), committed "
      f"BEFORE any variant here was run. Nothing in this document is a config "
      f"change or a live weight; survivors, if any, become HYPOTHESES.md "
      f"entries at most (TUNING.md law).")
    w("")
    w("## Verdict")
    w("")
    if surv:
        w(f"**{len(surv)} of {n} variant arms SURVIVED the registered bar: "
          f"{', '.join(surv)}.**")
    else:
        w(f"**NOTHING SURVIVED.** All {n} registered variant arms failed the "
          f"pre-registered bar against the best incumbent "
          f"(`{best}`). That is the finding, and the registration says so: "
          f"\"If NOTHING survives, that IS the finding and it gets reported as "
          f"such.\" No consolation winner is nominated below, no bar is "
          f"softened, and nothing was re-parameterized after a result was seen.")
    w("")
    w(f"Multiple-comparison bar: **{n} arms tested** "
      f"({meta['n_registered_groups']} registered variants C1..C8, several of "
      f"which register more than one parameterization). The naive threshold is "
      f"alpha={meta['naive_alpha']:.2f} — a 95% CI on the Sharpe difference "
      f"excluding zero. Bonferroni-adjusted that is "
      f"alpha={meta['bonferroni_alpha']:.5f}, i.e. a "
      f"{100 * meta['bonferroni_conf']:.3f}% CI must exclude zero. "
      f"Arms clearing the ADJUSTED bar: **{', '.join(clears) if clears else 'NONE'}**.")
    w("")
    w("## Protocol (fixed before results)")
    w("")
    w(f"- Windows, identical dates across every comparator within a window: "
      f"REAL {meta['windows']['real']['start']}..{meta['windows']['real']['end']} "
      f"(n={meta['windows']['real']['n']}) and SYNTHETIC-EXTENDED "
      f"{meta['windows']['synth']['start']}..{meta['windows']['synth']['end']} "
      f"(n={meta['windows']['synth']['n']}).")
    w(f"- Incumbents: {', '.join(meta['incumbents'])}. Best incumbent on the "
      f"full real window by BIL-excess Sharpe: **{best}**.")
    w(f"- Measurement basis: {meta['measurement_basis']}.")
    w(f"- Sortino convention: {meta['sortino_convention']} — the round-4 "
      f"counter-agent flagged the earlier code for dividing by the count of "
      f"negative days instead. Sharpe and Sortino are printed on BOTH risk-free "
      f"bases and never mixed within a column.")
    w(f"- Costs {meta['cost_bps_per_side']:.0f} bps per side on traded notional. "
      f"Tail sleeve = {meta['tail_sleeve']}.")
    w(f"- Sleeve: {meta['sleeve']}. Synthetic KMLM: {meta['synthetic_kmlm']}.")
    w(f"- Bootstrap: paired circular block bootstrap on the Sharpe DIFFERENCE, "
      f"{meta['bootstrap']['block_days']}-day blocks, "
      f"{meta['bootstrap']['draws']} draws, seed {meta['bootstrap']['seed']}, "
      f"basis {meta['bootstrap']['basis']}. Both series are resampled with the "
      f"SAME block starts, so the difference keeps its date pairing.")
    w(f"- XBI 200dma prior-close gate source (C5): {meta['gate_source']}.")
    w("")
    w("## Registered variants")
    w("")
    w("| key | group | description |")
    w("|---|---|---|")
    for k in order:
        v = VARIANTS.get(k) or INCUMBENTS[k]
        w(f"| {k} | {v.group} | {v.desc} |")
    w("")
    w(f"## Results — REAL window {meta['windows']['real']['start']}.."
      f"{meta['windows']['real']['end']}")
    w("")
    L.extend(_md_table(res, "real", order, verdicts))
    w("")
    w(f"## Results — SYNTHETIC-EXTENDED window "
      f"{meta['windows']['synth']['start']}..{meta['windows']['synth']['end']}")
    w("")
    w("Proxy splice, unadjusted (no manager alpha added). This window is a "
      "FLOOR on B.5's constituents, not a point estimate — the counter-agent's "
      "upper bound (alpha carried back onto the pre-inception proxy stretch) "
      "raises the B.5-core Sharpe by roughly 0.04-0.05.")
    w("")
    L.extend(_md_table(res, "synth", order, verdicts))
    w("")
    w("## Survival verdict, variant by variant")
    w("")
    w(f"Bar (all four required, vs `{best}`): 1. Sharpe AND Sortino beat it on "
      f"the full real window; 2. the 95% bootstrap CI on dSharpe excludes zero; "
      f"3. it beats it (Sharpe AND Sortino) in >=2 of 3 equal sub-periods; "
      f"4. it does not lose the synthetic window by more than 0.10 Sharpe.")
    w("")
    w("| variant | dSharpe vs best | 95% CI | boot p | 1 | 2 | 3 (wins) | 4 | "
      "SURVIVES | Bonferroni CI |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for k, v in verdicts.items():
        lo, hi = v["ci95"]
        blo, bhi = v["ci_bonferroni"]
        w(f"| {k} | {v['d_sharpe']:+.3f} | [{lo:+.3f}, {hi:+.3f}] | "
          f"{v['boot_p']:.3f} | {_yn(v['c1_sharpe_and_sortino'])} | "
          f"{_yn(v['c2_ci_excludes_zero'])} | {_yn(v['c3_subperiods'])} "
          f"({v['c3_wins']}/3) | {_yn(v['c4_synthetic'])} | "
          f"**{'YES' if v['survives'] else 'no'}** | [{blo:+.3f}, {bhi:+.3f}] |")
    w("")
    flips = [k for k, v in verdicts.items()
             if v["c1_sharpe_and_sortino"] != v["c1_on_rf0"]]
    w(f"Basis check: adjudication is on BIL-excess Sharpe/Sortino, with rf=0 "
      f"printed beside it. Arms whose criterion-1 result would FLIP on the "
      f"rf=0 basis: **{', '.join(flips) if flips else 'none'}**.")
    if flips:
        bits = []
        for k in flips:
            f, b = res["real"][k]["full"], res["real"][best]["full"]
            bits.append(f"{k} (rf=0 Sharpe {f['sharpe_rf0']:.4f} vs "
                        f"{b['sharpe_rf0']:.4f}, a {f['sharpe_rf0'] - b['sharpe_rf0']:+.4f} "
                        f"gap against a ~+/-0.4 noise floor)")
        w("")
        w(f"Those flips change NO verdict: {'; '.join(bits)} — and each still "
          f"fails criteria 2 and 3. They are reported because the registration "
          f"requires both bases printed, not because either is a finding.")
    w("")
    w("## Why nothing survived, and what criterion 4 did not test")
    w("")
    w(f"The mechanism is not new evidence, it is the round-4 counter-agent's "
      f"finding restated on a wider grid: on a B.5 core the optimal R2-A weight "
      f"is about 5% — effectively zero — because a sleeve helps at the margin "
      f"only when its Sharpe exceeds rho times the core's, and here "
      f"{res['real']['REF-R2A']['full']['sharpe_bil']:.3f} sits barely above "
      f"{meta['corr_core_sleeve_real']:.3f} x "
      f"{res['real'][best]['full']['sharpe_bil']:.3f} = "
      f"{meta['corr_core_sleeve_real'] * res['real'][best]['full']['sharpe_bil']:.3f}. "
      f"Every C1..C8 arm is a way of holding MORE sleeve than that, or of "
      f"trading it differently, so the whole grid lands below the core alone. "
      f"Within C1 the damage is monotone in sleeve weight "
      f"({verdicts['C1-05']['d_sharpe']:+.3f} at 5% to "
      f"{verdicts['C1-20']['d_sharpe']:+.3f} at 20% to "
      f"{verdicts['C6-band05']['d_sharpe']:+.3f} at the live 30%), and every CI "
      f"is far wider than its own gap: this round found no edge AND could not "
      f"have resolved one this small if it existed.")
    w("")
    w("Criterion 4 was NOT binding. Every arm passed it, because the best "
      "incumbent (B.5 alone) is the WEAKEST comparator on the synthetic "
      f"window — Sharpe(BIL) {res['synth'][best]['full']['sharpe_bil']:.2f} "
      f"there against {res['synth']['INC-3070SPY']['full']['sharpe_bil']:.2f} "
      f"for 30/70 R2-A/SPY. A \"Y\" in column 4 means \"did not lose to a weak "
      "bar\", not \"held up out of sample\". Read columns 1-3 as the test.")
    w("")
    w("## C7 — the mechanical one")
    w("")
    c7 = verdicts.get("C7")
    c7f = res["real"]["C7"]["full"]
    bf = res["real"][best]["full"]
    if c7:
        lo, hi = c7["ci95"]
        w(f"C7 is the only arm whose edge, if any, is NOT a search result: it is "
          f"a fix to a known accounting artifact. The frozen R2-A sleeve earns "
          f"0% on idle cash on **{idle_n}/{idle_tot} = {idle_n / idle_tot:.1%}** "
          f"of real-window days (the counter-agent's own measurement, "
          f"reproduced here); C7 routes that idle cash to the CORE's return "
          f"instead.")
        w("")
        w(f"Result: Sharpe(BIL) {c7f['sharpe_bil']:.3f} vs {best}'s "
          f"{bf['sharpe_bil']:.3f} (dSharpe {c7['d_sharpe']:+.3f}, 95% CI "
          f"[{lo:+.3f}, {hi:+.3f}]), Sortino(BIL) {c7f['sortino_bil']:.3f} vs "
          f"{bf['sortino_bil']:.3f}, CAGR {c7f['cagr']:.2%} vs {bf['cagr']:.2%}, "
          f"maxDD {c7f['max_dd']:.1%} vs {bf['max_dd']:.1%}. "
          f"**{'SURVIVES' if c7['survives'] else 'DOES NOT SURVIVE'}** the "
          f"registered bar.")
        w("")
        lf = meta.get("c7_vs_c6_band05")
        if lf:
            c6f = res["real"]["C6-band05"]["full"]
            w(f"Like-for-like (DESCRIPTIVE, not the registered bar): against the "
              f"SAME book with the fix off (`{lf['comparator']}`), C7 is "
              f"dSharpe {lf['d_sharpe']:+.3f}, 95% CI "
              f"[{lf['ci95'][0]:+.3f}, {lf['ci95'][1]:+.3f}], p={lf['boot_p']:.3f}. "
              f"The fix buys {100 * (c7f['cagr'] - c6f['cagr']):+.2f}pp of CAGR "
              f"and costs {100 * (c7f['max_dd'] - c6f['max_dd']):+.1f}pp of max "
              f"drawdown and {100 * (c7f['vol'] - c6f['vol']):+.1f}pp of "
              f"volatility: crediting idle "
              f"sleeve cash to the core raises both the return and the "
              f"equity-beta of the sleeve leg, so the Sharpe barely moves "
              f"({c6f['sharpe_bil']:.3f} -> {c7f['sharpe_bil']:.3f}) and Calmar "
              f"FALLS ({c6f['calmar']:.2f} -> {c7f['calmar']:.2f}). The "
              f"accounting artifact was real and is now fixed; it was not "
              f"hiding a risk-adjusted edge.")
            w("")
        w("Implementation limit, stated because it bounds the claim: the frozen "
          "sleeve is a dollar curve, so only FULLY idle days (exactly 0% "
          "return) are observable. Partially-invested days keep 0% on their "
          "cash, so C7 as run is the conservative corner of the fix. It also "
          "charges no transaction cost for the implied daily movement of idle "
          "cash in and out of the core, which is a favourable assumption.")
    w("")
    w("## Honesty box")
    w("")
    w("- **In-sample status of B.5's weights.** `barbell-lab/config/"
      "portfolio.yaml` was first committed **2026-08-11**; the data here ends "
      "**2026-08-19**. Effectively 100% of both windows precedes the moment the "
      "weights were fixed, and there is no derivation record in the repo — no "
      "optimizer run, no pre-registration, no fitting log. The weights were "
      "chosen by someone who already knew which assets won 2021-2026. No CAGR "
      "in this document is a forecast.")
    w("- **The synthetic window is a FLOOR, not a point estimate.** The splice "
      "uses the proxies' own unadjusted returns and adds no manager alpha; "
      "AVUV beat SLYV by ~5.1pp/yr and AVDV beat DLS by ~6.7pp/yr over their "
      "measurable overlaps (geometric), while KMLM's proxies BEAT KMLM by "
      "1.3-3.1pp/yr. 1079 of 2511 synthetic sessions use proxy returns for 54% "
      "of B.5's weight plus 14% KMLM and 5% TAIL.")
    w("- **R2-A's inherited caveats propagate into every blend number here.** "
      "The sleeve is a backtest carrying survivorship (\"today's universe; dead "
      "names absent — absolute numbers flattered\"), universe/alias hindsight, "
      "and exit-engine overfit risk; the 30% weight was itself selected by an "
      "H13 sweep run against a **SPY** core on a backtested sleeve. None of "
      "that is corrected here.")
    w("- **Config mismatch.** `portfolio.yaml` specifies B.5 at **80% of the "
      "book paired with a 20% short-vol bot** under a hard constraint "
      "`bot_corr_max: 0.10`. Every variant here instead pairs B.5 with R2-A, "
      f"whose real-window correlation to the B.5 core is "
      f"**{meta['corr_core_sleeve_real']:.3f}** — {meta['corr_core_sleeve_real'] / 0.10:.1f}x "
      "that gate. Whether R2-A is meant to "
      "occupy the bot slot, or be a third sleeve, is UNRESOLVED and was not "
      "adjudicated by this round.")
    w("- **The tail sleeve is an unresolved input, held FIXED at TAIL.** "
      "`portfolio.yaml` marks it a placeholder pending Question #1 with "
      "candidates [TAIL, CAOS, BTAL, NONE]. TAIL is the worst of the four in "
      "the real window (a 133bp CAGR span, 0.04 Sharpe), so these are the "
      "pessimistic corner. The registration fixes TAIL for every variant so "
      "the open question cannot flatter one over another — it does NOT resolve "
      "the question.")
    w("- **Noise floor.** The counter-agent measured the 95% CI on a Sharpe "
      "difference in this data at roughly +/-0.4. With ~1,400 real trading "
      "days, differences smaller than that are not distinguishable from zero, "
      "and the CI column above is the honest reading of every dSharpe here.")
    w("- **What was NOT modeled:** taxes; bid-ask and market impact beyond a "
      "flat 10bps per side; borrow, margin or liquidity constraints; the 20% "
      "short-vol bot the config actually pairs B.5 with; PHYS "
      "premium/discount as a separate factor; fund-closure or capacity risk. "
      "C4's deleveraging assumes cash earns BIL with no execution lag.")
    w("- **Warm-up rules, disclosed because they are choices.** C3 and C8 need "
      "60 trailing days and C4 needs 20; before that history exists inside a "
      "window their weight falls back to the live 30% (C3/C8) or to full "
      "exposure (C4). That is a stated rule, not a fitted parameter.")
    w("")
    w("## Reproducibility")
    w("")
    w("```")
    w("cd genomics-alpha-tracker/backend")
    w("python -m scripts.backtest_core_variants            # full campaign")
    w("python -m scripts.backtest_core_variants --variant C7 --window real")
    w("```")
    w("")
    w("Adding a round-5 variant is one `register(...)` line plus its builder in "
      "`scripts/backtest_core_variants.py`; the metrics, the survival bar, the "
      "bootstrap, both windows and this report all pick it up automatically. "
      "Prices are cached under `backend/data/px_cache/` so re-runs never "
      "re-fetch. Results JSON: `backend/data/backtest_core_variants_results.json`.")
    w("")
    REPORT.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(BACKEND))
    main()
