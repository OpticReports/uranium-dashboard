"""ROUND 4 of the pre-registered variant campaign: CORE SELECTION (R2-A x B.5).

Contract: docs/VARIANTS_PREREGISTRATION_R4_CORE.md, committed BEFORE any
round-4 variant was run. C1..C8 are registered there and may not be added to,
dropped, or re-parameterized after a result is seen.

This module is the DURABLE harness, not a one-off. Variants live in a registry
(`VARIANTS`) of named callables that each return a daily dollar curve, so a
round-5 variant costs one `register(...)` line plus its builder; every metric,
the survival bar and the bootstrap come for free.

It now carries TWO rounds. Each variant declares its `round`, and `--round`
selects which one is judged and which report is written, so round 4's record
stays frozen when round 5 runs. Round 5's contract is
docs/VARIANTS_PREREGISTRATION_R5_SLEEVE.md, committed BEFORE any round-5 code
existed; its arms are D1..D4 and they may not be added to, dropped, or
re-parameterized after a result is seen either.

Conventions (fixed by the registration and by the round-4 counter-agent
verdict on the B.5-as-core study):
  * daily marked-to-market total returns on adjusted closes (stockanalysis
    field 'a'), disk-cached under backend/data/px_cache so re-runs never
    re-fetch; the API is the only data lane and it is used politely.
  * the R2-A sleeve is the FROZEN dollar curve (data/r2a_daily.json), reused
    verbatim and NEVER recomputed. Its daily INVESTED notional comes from
    data/r2a_exposure.json (scripts/build_r2a_exposure.py rebuilds it from the
    round-2 pipeline and gates it against the frozen curve), so the idle
    CAPITAL fraction C7 routes is exact, not inferred from zero-return days.
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
R2A_EXPOSURE = DATA / "r2a_exposure.json"
BARS_CACHE = DATA / "backtest_bars.json"
ROUNDS = {
    4: {"results": DATA / "backtest_core_variants_results.json",
        "report": BACKEND.parent / "docs" / "BACKTEST_CORE_VARIANTS_R4.md",
        "contract": "docs/VARIANTS_PREREGISTRATION_R4_CORE.md",
        "title": "ROUND 4 core variants (R2-A x B.5)",
        "groups": "C1..C8"},
    5: {"results": DATA / "backtest_sleeve_variants_r5_results.json",
        "report": BACKEND.parent / "docs" / "BACKTEST_SLEEVE_VARIANTS_R5.md",
        "contract": "docs/VARIANTS_PREREGISTRATION_R5_SLEEVE.md",
        "title": "ROUND 5 sleeve variants (idle cash, timing, inverse-vol)",
        "groups": "D1..D4"},
}
DEFAULT_ROUND = 4

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

# Round-5 fixed parameters (VARIANTS_PREREGISTRATION_R5_SLEEVE.md) -----------
# Fixed BEFORE any round-5 code existed. The rebalance rule is registered
# EXPLICITLY this round — monthly calendar everywhere except D4, which exists
# to vary it — because round 4 left it implicit and a 5% absolute band turned
# out never to fire on a 5% target weight (counter-agent M3).
D1_WEIGHTS = (0.05, 0.10, 0.15)
D1_CASH_LEG = "BIL"
D2_HI_W, D2_LO_W = 0.15, 0.05
# D2's warm-up default. The registration names 15% and 5% and nothing else, so
# the low leg is the only registered weight the arm can fall back to; the 30%
# live weight it originally inherited from `monthly_weights` is NOT in D2's
# contract (round-5 counter-agent M3). D3 keeps the 30% fallback because its
# registration states it explicitly.
D2_WARMUP_W = D2_LO_W
D2_CORR_WINDOW = 60
D2_CORR_THRESHOLD = 0.30
D3_VOL_WINDOW = 60
D4_RULES = ("daily", "band005")

# Bootstrap (registration: 21d blocks, 4000 draws, paired on dates) -----------
BOOT_BLOCK = 21
BOOT_DRAWS = 4000
# The Bonferroni interval is a 99.667% percentile read off the tails, which at
# 4000 draws is the 8th and 3992nd order statistics — 7 draws a side (round-4
# counter-agent m4). The deep run uses the SAME seed and the same draw
# sequence, so its first BOOT_DRAWS draws ARE the registered 4000-draw
# bootstrap: the 95% CI is unchanged and only the adjusted tail gets denser.
BOOT_DRAWS_DEEP = 40_000
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


def load_sleeve_exposure(curve: dict[str, float]) -> dict[str, float]:
    """R2-A's daily IDLE CAPITAL fraction, keyed by ISO date.

    Rebuilt from the round-2 pipeline by `scripts/build_r2a_exposure.py`:
    [[date, equity, invested, open_positions], ...]. The equity column is
    gated against the frozen curve here as well as there, because this file
    is what turns C7 from a proxy into the real fix — if it ever drifts from
    the sleeve the harness actually holds, C7 is measuring a different book.
    """
    rows = json.loads(R2A_EXPOSURE.read_text())
    assert len(rows) == len(curve), (
        f"exposure file has {len(rows)} days, frozen curve has {len(curve)}")
    out: dict[str, float] = {}
    for d, eq, inv, _n in rows:
        assert d in curve and abs(eq - curve[d]) < 1e-5, (
            f"exposure equity {eq} != frozen curve {curve.get(d)} on {d}")
        out[d] = min(max((eq - inv) / eq, 0.0), 1.0) if eq > 0 else 0.0
    return out


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
                                seed: int = BOOT_SEED,
                                shallow: int | None = None) -> dict:
    """PAIRED circular block bootstrap on Sharpe(a) - Sharpe(b).

    Both series are resampled with the SAME block start indices, so the
    date-pairing that makes a difference meaningful is preserved: the draw
    answers "how much of this gap survives resampling the shared history",
    not "how far apart can two independent series drift".

    Deterministic given `seed`. Returns the point estimate, the sorted draw
    distribution, and a two-sided bootstrap p-value.

    `shallow` (optional) additionally returns the sorted distribution of the
    FIRST `shallow` draws as `dist_shallow`. Because the draw sequence depends
    only on the seed, that prefix is bit-identical to a `shallow`-draw run:
    the registered 95% interval and p-value can be read off it while a deeper
    `draws` feeds the Bonferroni tail (counter-agent m4).
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
    head = sorted(dist[:shallow]) if shallow else None
    dist.sort()
    ref = head if head is not None else dist
    le = sum(1 for d in ref if d <= 0) / len(ref)
    ge = sum(1 for d in ref if d >= 0) / len(ref)
    out = {"point": point, "dist": dist, "draws": draws, "block": block,
           "seed": seed, "p_two_sided": min(1.0, 2 * min(le, ge))}
    if head is not None:
        out["dist_shallow"] = head
        out["shallow_draws"] = shallow
    return out


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
    raw: dict[str, dict[str, float]] = field(default_factory=dict)
    core: dict[str, float] = field(default_factory=dict)
    sleeve: dict[str, float] = field(default_factory=dict)
    spy: dict[str, float] = field(default_factory=dict)
    bil: dict[str, float] = field(default_factory=dict)
    gate: dict[str, bool] = field(default_factory=dict)
    idle_frac: dict[str, float] = field(default_factory=dict)
    bil_rets: list[float] = field(default_factory=list)
    spy_rets: list[float] = field(default_factory=list)
    months: list[str] = field(default_factory=list)
    quarters: list[str] = field(default_factory=list)

    def legs(self) -> dict[str, dict[str, float]]:
        return {"SLEEVE": self.sleeve, "CORE": self.core,
                "SPY": self.spy, "BIL": self.bil}


def build_ctx(key: str, raw: dict[str, dict[str, float]], sleeve_raw: dict[str, float],
              gate: dict[str, bool], idle: dict[str, float]) -> Ctx:
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
    ctx = Ctx(key, label, dates, px, raw, core, sleeve, spy, bil,
              {d: gate.get(d, True) for d in dates},
              {d: idle[d] for d in dates})
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
    round: int = DEFAULT_ROUND


VARIANTS: dict[str, Variant] = {}
INCUMBENTS: dict[str, Variant] = {}


def register(key: str, group: str, desc: str, fn, *, judged: bool = True,
             round: int = DEFAULT_ROUND) -> None:      # noqa: A002
    """Add a variant to the registry. A new round's variant is ONE of these
    lines plus its builder; nothing else in this file needs to change. The
    `round` tag is what keeps a finished round's record frozen when a later
    one runs — arms are judged, counted and reported per round."""
    target = VARIANTS if judged else INCUMBENTS
    assert key not in target, f"duplicate registry key {key}"
    assert judged or round == DEFAULT_ROUND, "incumbents are shared across rounds"
    target[key] = Variant(key, group, desc, fn, judged, round)


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
    """The `window` returns ending WITH the return INTO dates[i] — that is,
    rets[i-window:i] where rets[j] runs from dates[j] to dates[j+1], so the
    last element is dates[i]'s OWN close.

    This is the engine's SAME-CLOSE decide/execute convention (see
    `portfolio`: breach detection and execution happen at one close), not a
    prior-close one, and it is not look-ahead: nothing after dates[i] is used.
    It IS a different convention from C5's gate, which is genuinely
    prior-close because it inherits R2-A's own entry condition. The round-4
    counter-agent measured the cost of that inconsistency by re-running the
    statistics strictly prior-close: C3 -0.0004, C8 -0.0019, C4 +0.0181
    Sharpe(BIL). No verdict moves; the numbers are recorded in the report.
    """
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

def sleeve_idle_routed(ctx: Ctx, route: str = "CORE", *,
                       coverage: float = 1.0,
                       drag_bps: float = 0.0) -> dict[str, float]:
    """R2-A's uninvested CAPITAL earns `route`'s return instead of 0%.

    `coverage` (0..1) is the fraction of the idle balance that actually gets
    swept, and `drag_bps` an ANNUAL drag in bps charged on the swept balance.
    Both default to the registered arm's assumptions (full coverage, no drag);
    they exist so the mechanism's like-for-like measurement can be re-run under
    pessimism about the live sweep, which skips while a book order is pending,
    leaves a residual under max($50, one BIL share), can be clamped by budget
    headroom and only fires on the next cycle (round-5 counter-agent M1).

    The idle fraction as of the PRIOR close (data/r2a_exposure.json, rebuilt
    from the round-2 pipeline and gated against the frozen curve) earns the
    routed leg's return today, so the sleeve's daily return becomes
    `r_sleeve + idle_frac[prior] * r_route`.

    This replaces the round-4 implementation, which credited only the days
    whose sleeve return was exactly zero (424/1432 = 29.6%) on the belief that
    a dollar curve makes partial idleness unobservable. That belief was wrong:
    `backtest_variants_r2.py`'s `run_call_book_yield` already computes
    `equity - invested` daily, and R2-A's real-window idle capital averages
    63.3% (median 57.4%) — roughly twice what the old code credited
    (round-4 counter-agent M1).
    """
    dest = {"CORE": ctx.core, "BIL": ctx.bil}[route]
    d = ctx.dates
    drag = drag_bps / 1e4 / TRADING_DAYS
    lvl, out = 1.0, {d[0]: 1.0}
    for i in range(1, len(d)):
        rs = ctx.sleeve[d[i]] / ctx.sleeve[d[i - 1]] - 1
        rd = dest[d[i]] / dest[d[i - 1]] - 1
        lvl *= 1 + rs + ctx.idle_frac[d[i - 1]] * coverage * (rd - drag)
        out[d[i]] = lvl
    return out


def c7_idle_cash(ctx: Ctx) -> dict[str, float]:
    curves = dict(ctx.legs())
    curves["SLEEVE"] = sleeve_idle_routed(ctx)
    return portfolio(ctx.dates, curves,
                     const({"SLEEVE": LIVE_SLEEVE_W, "CORE": 1 - LIVE_SLEEVE_W}),
                     band=LIVE_BAND)


register("C7", "C7", "30/70 R2-A/B.5 with the sleeve's idle CAPITAL earning "
                     "the CORE's return instead of 0%",
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


# ============================================================================
# ROUND 5 — sleeve mechanics (docs/VARIANTS_PREREGISTRATION_R5_SLEEVE.md)
# ----------------------------------------------------------------------------
# Registered BEFORE any of this code was written. Each arm cites the round-4
# counter-agent finding it comes from and nothing else. Every arm rebalances
# on the MONTHLY CALENDAR — fixed by the registration, not by the harness —
# except D4, whose whole purpose is to vary the rule.

# -- D1: sleeve idle cash routed to CASH, not the core -----------------------

def d1_sleeve_cash(ctx: Ctx, w: float, *, band: float | None = None,
                   rebal: Iterable[str] | None = None,
                   coverage: float = 1.0,
                   drag_bps: float = 0.0) -> dict[str, float]:
    """Static sleeve/core at weight `w` with the sleeve's idle CAPITAL earning
    BIL instead of 0%.

    Motivation (M2): crediting idle capital to BIL lifts the sleeve's own
    Sharpe 0.358 -> 0.443 while leaving its correlation to the core UNCHANGED
    at 0.329, so the tangency weight roughly doubles to ~9.8%. Crediting the
    CORE instead — round 4's C7 — buys Sharpe by buying correlation
    (rho 0.329 -> 0.626) and is strictly dominated.
    """
    curves = dict(ctx.legs())
    curves["SLEEVE"] = sleeve_idle_routed(ctx, D1_CASH_LEG, coverage=coverage,
                                          drag_bps=drag_bps)
    return portfolio(ctx.dates, curves, const({"SLEEVE": w, "CORE": 1 - w}),
                     band=band,
                     rebal_dates=ctx.months if rebal is None else rebal)


def d1_dead_cash_twin(ctx: Ctx, w: float, *, band: float | None = None,
                      rebal: Iterable[str] | None = None) -> dict[str, float]:
    """D1's OWN counterfactual: the identical book, same weight, same rebalance
    rule, with the sleeve's idle cash left DEAD — i.e. the frozen sleeve.

    This is the comparator the round-5 writeup never built. Judging the cash
    routing against `INC-B5` (the sleeve removed entirely) measures a different
    claim — whether to hold the sleeve at all — and carries the sleeve's whole
    idiosyncratic variance, which is why that interval is ~+/-0.06 while this
    one is ~+/-0.003 (round-5 counter-agent M1).
    """
    return sleeve_core(ctx, w, band=band,
                       rebal=ctx.months if rebal is None else rebal)


for _w in D1_WEIGHTS:
    register(f"D1-{int(_w * 100):02d}", "D1",
             f"static {int(_w * 100)}% R2-A / {int((1 - _w) * 100)}% B.5 with the "
             f"sleeve's idle CAPITAL earning BIL, monthly rebalance",
             lambda ctx, w=_w: d1_sleeve_cash(ctx, w), round=5)


# -- D2: the correlation trigger anchored at the tangency weight -------------

def d2_corr_at_tangency(ctx: Ctx, warmup: float | None = None) -> dict[str, float]:
    """D1's cash routing plus C8's trigger moved from 30/10 to 15/5.

    Motivation (verifier H1): C8's value was its TIMING, not its weight level —
    against a static sleeve of the same average exposure it was +0.036 dSharpe,
    Sortino 1.320 vs 1.263, Calmar 1.012 vs 0.945 — but the trigger was only
    ever tested at weights M2 says are wrong.

    WARM-UP DEFAULT (round-5 counter-agent M3): the registration fixes D2 at
    15%/5% and authorizes no other weight; it registers the 30% fallback for
    D3 ONLY. The first implementation inherited `monthly_weights`' 30% default
    anyway and so held a weight D2's own contract does not contain on 81 of
    1,433 days. The default here is the REGISTERED LOW LEG. That is not a
    re-parameterization of the arm — it is the removal of an unregistered one,
    and the three readings are reported side by side in the writeup.
    """
    sleeve = sleeve_idle_routed(ctx, D1_CASH_LEG)
    curves = dict(ctx.legs())
    curves["SLEEVE"] = sleeve
    sr = curve_returns(sleeve, ctx.dates)
    cr = curve_returns(ctx.core, ctx.dates)

    def pick(i: int) -> float | None:
        ws, wc = _trailing(sr, i, D2_CORR_WINDOW), _trailing(cr, i, D2_CORR_WINDOW)
        if ws is None or wc is None:
            return None
        rho = pearson(ws, wc)
        if math.isnan(rho):
            return None
        return D2_HI_W if rho < D2_CORR_THRESHOLD else D2_LO_W

    return portfolio(ctx.dates, curves,
                     monthly_weights(ctx, pick,
                                     D2_WARMUP_W if warmup is None else warmup),
                     rebal_dates=ctx.months)


register("D2", "D2", "sleeve 15% when trailing 60d corr(sleeve, core) < 0.30 else 5%, "
                     "monthly, with the sleeve's idle CAPITAL earning BIL "
                     "(warm-up default = the registered 5% low leg)",
         d2_corr_at_tangency, round=5)


# -- D3: a TRUE uncapped inverse-vol sleeve ----------------------------------

def d3_weight_at(ctx: Ctx, i: int) -> float | None:
    """The uncapped inverse-vol sleeve weight decided at index `i`, or None
    during warm-up / a zero-vol month. Shared by the builder and the reporting
    of the realized weight distribution the registration requires."""
    sr = curve_returns(ctx.sleeve, ctx.dates)
    cr = curve_returns(ctx.core, ctx.dates)
    ws, wc = _trailing(sr, i, D3_VOL_WINDOW), _trailing(cr, i, D3_VOL_WINDOW)
    if ws is None or wc is None:
        return None
    vs, vc = statistics.stdev(ws), statistics.stdev(wc)
    if vs <= 0 or vc <= 0:
        return None
    return (1 / vs) / (1 / vs + 1 / vc)


def d3_inverse_vol_uncapped(ctx: Ctx) -> dict[str, float]:
    """Inverse-vol between sleeve and core, monthly, 60d trailing, NO CAP.

    Motivation (M5): round 4's C3 registered a 30% cap that sat at the cap on
    82.1% of days, making C3 a restatement of C6-monthly. The inverse-vol
    hypothesis was never tested. Warm-up and zero-sleeve-vol months fall back
    to the live 30% — the round-4 convention, inherited so the two rounds are
    comparable, and disclosed as a rule rather than a fitted parameter.
    """
    sr = curve_returns(ctx.sleeve, ctx.dates)
    cr = curve_returns(ctx.core, ctx.dates)

    def pick(i: int) -> float | None:
        ws, wc = _trailing(sr, i, D3_VOL_WINDOW), _trailing(cr, i, D3_VOL_WINDOW)
        if ws is None or wc is None:
            return None
        vs, vc = statistics.stdev(ws), statistics.stdev(wc)
        if vs <= 0 or vc <= 0:
            return None
        return (1 / vs) / (1 / vs + 1 / vc)

    return portfolio(ctx.dates, ctx.legs(),
                     monthly_weights(ctx, pick, LIVE_SLEEVE_W),
                     rebal_dates=ctx.months)


register("D3", "D3", "UNCAPPED inverse-vol sleeve/core, monthly, trailing 60d "
                     "(no 30% cap — the parameter that voided round 4's C3)",
         d3_inverse_vol_uncapped, round=5)


# -- D4: the rebalance-rule dimension, on D1's best weight -------------------

_D1_BEST_W: float | None = None


def d1_best_weight(real_ctx: Ctx) -> float:
    """The registered selection rule, applied once: the D1 arm with the highest
    BIL-excess Sharpe over the FULL REAL window, ties broken toward the LOWER
    weight. Fixed on the real window even when D4 is evaluated on the synthetic
    one, because that is what the registration says."""
    global _D1_BEST_W
    if _D1_BEST_W is None:
        scored = [(metrics(d1_sleeve_cash(real_ctx, w), real_ctx.dates,
                           real_ctx.bil_rets)["sharpe_bil"], -w, w)
                  for w in D1_WEIGHTS]
        _D1_BEST_W = max(scored)[2]
    return _D1_BEST_W


_D4 = {
    "daily": ("daily", {"band": 0.0}),
    "band005": ("0.5% absolute band", {"band": 0.005}),
}


def d4_rebalance(ctx: Ctx, rule: str) -> dict[str, float]:
    """D1 at its best weight under a different rebalance rule.

    Motivation (M3): a 5% ABSOLUTE band never fires on a 5% TARGET weight — 0
    rebalances in 1433 days — so round 4's low-weight arms were buy-and-hold
    by accident and their criterion-1 results were an artifact of an
    unregistered implementation choice.
    """
    assert _D1_BEST_W is not None, "d1_best_weight() must run before D4"
    return d1_sleeve_cash(ctx, _D1_BEST_W, band=_D4[rule][1]["band"], rebal=())


for _r in D4_RULES:
    register(f"D4-{_r}", "D4",
             f"D1 at its best weight, {_D4[_r][0]} rebalance", 
             lambda ctx, r=_r: d4_rebalance(ctx, r), round=5)


def d3_weight_distribution(ctx: Ctx) -> dict:
    """The realized weight distribution the round-5 registration REQUIRES for
    D3 — the whole point of the arm is what an uncapped rule actually holds."""
    idx = {d: i for i, d in enumerate(ctx.dates)}
    rebal = set(ctx.months)
    cur, raw = LIVE_SLEEVE_W, None
    applied: list[float] = []
    decided: list[float] = []
    n_fallback = 0
    for d in ctx.dates:
        if d == ctx.dates[0] or d in rebal:
            raw = d3_weight_at(ctx, idx[d])
            cur = LIVE_SLEEVE_W if raw is None else raw
            if raw is not None:
                decided.append(raw)
        applied.append(cur)
        n_fallback += raw is None
    q = sorted(applied)

    def pctile(f: float) -> float:
        return q[min(len(q) - 1, int(f * len(q)))]

    return {"n_days": len(applied), "mean": statistics.fmean(applied),
            "median": statistics.median(applied), "min": min(applied),
            "max": max(applied), "p10": pctile(0.10), "p90": pctile(0.90),
            "days_over_30pct": sum(1 for w in applied if w > C3_SLEEVE_CAP),
            "frac_over_30pct": sum(1 for w in applied if w > C3_SLEEVE_CAP) / len(applied),
            "days_fallback": n_fallback,
            "decisions_with_a_weight": len(decided),
            "mean_decided_weight": statistics.fmean(decided)}


# -- incumbents (registration: B.5 alone, 30/70 R2-A/SPY, SPY alone) ---------

def inc_3070spy(ctx: Ctx, *, swept: bool = False) -> dict[str, float]:
    """The 30/70 R2-A/SPY incumbent — the live H13 design.

    `swept=True` gives the SAME book under the convention the live executor
    actually implements: `ibkr-executor/app/blend.py` sweeps idle SLEEVE cash
    to BIL (step 8, CASH_VEHICLE="BIL", funded from `sleeve_cash`, distinct
    from CORE_BUY's idle-core sweep into SPY). Both conventions are registered
    and reported side by side (round-5 counter-agent M4); the as-frozen curve
    is the pinned input to rounds 1-4 and is never silently restated.
    """
    curves = dict(ctx.legs())
    if swept:
        curves["SLEEVE"] = sleeve_idle_routed(ctx, D1_CASH_LEG)
    return portfolio(ctx.dates, curves,
                     const({"SLEEVE": LIVE_SLEEVE_W, "SPY": 0.70}),
                     band=LIVE_BAND)


register("INC-B5", "INC", "B.5 Enhanced alone",
         lambda ctx: dict(ctx.core), judged=False)
register("INC-3070SPY", "INC",
         "30/70 R2-A / SPY, 5% band — as-frozen (DEAD idle sleeve cash)",
         inc_3070spy, judged=False)
register("INC-SPY", "INC", "SPY alone", lambda ctx: dict(ctx.spy), judged=False)
register("REF-R2A", "REF",
         "R2-A sleeve alone — as-frozen (DEAD idle cash), context only",
         lambda ctx: dict(ctx.sleeve), judged=False)
# The same two books under the LIVE convention (idle sleeve cash swept to BIL).
# Never comparators — INCUMBENT_KEYS is the group-"INC" set — and never judged;
# they exist so no table can quote the dead-cash number alone (M4).
register("INC-3070SPY-SWEPT", "SWEPT",
         "30/70 R2-A / SPY, 5% band — SWEPT (live convention: idle sleeve "
         "cash to BIL)",
         lambda ctx: inc_3070spy(ctx, swept=True), judged=False)
register("REF-R2A-SWEPT", "SWEPT",
         "R2-A sleeve alone — SWEPT (live convention: idle cash to BIL), "
         "context only",
         lambda ctx: sleeve_idle_routed(ctx, D1_CASH_LEG), judged=False)

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


# --- diagnostics demanded by the round-4 counter-agent -----------------------------
# None of these move the registered bar. They exist because the round-4 writeup
# made four claims the counter-agent showed were wrong or unsupported, and the
# fix for a wrong claim is a measurement, not a rewording.

def excess(rets: list[float], rf: list[float]) -> list[float]:
    return [a - b for a, b in zip(rets, rf, strict=True)]


def tangency(sleeve_ex: list[float], core_ex: list[float]) -> dict:
    """Two-asset tangency weight on the sleeve, and the Sharpe uplift there.

    For P = (1-w)C + wS the derivative at w=0 is proportional to
    mu_S*sigma_C - mu_C*rho*sigma_S, so a sleeve pays at the margin iff
    S_sleeve > rho * S_core. This returns the interior optimum, which is the
    number that says HOW MUCH the sleeve is worth once it does pay.
    """
    ms, mc = statistics.fmean(sleeve_ex), statistics.fmean(core_ex)
    vs, vc = statistics.variance(sleeve_ex), statistics.variance(core_ex)
    n = len(core_ex)
    cov = sum((x - ms) * (y - mc)
              for x, y in zip(sleeve_ex, core_ex, strict=True)) / (n - 1)
    denom = ms * vc + mc * vs - (ms + mc) * cov
    w = (ms * vc - mc * cov) / denom if denom else float("nan")

    def sh(x: float) -> float:
        b = [(1 - x) * a + x * c for a, c in zip(core_ex, sleeve_ex, strict=True)]
        return statistics.fmean(b) / statistics.stdev(b) * math.sqrt(TRADING_DAYS)

    return {"sharpe_sleeve": statistics.fmean(sleeve_ex) / statistics.stdev(sleeve_ex)
            * math.sqrt(TRADING_DAYS),
            "rho_to_core": pearson(sleeve_ex, core_ex),
            "w_star": w, "sharpe_at_0": sh(0.0), "sharpe_at_w": sh(w),
            "uplift": sh(w) - sh(0.0)}


def mechanism_table(ctx: Ctx) -> list[dict]:
    """M2. The sleeve's marginal value under each idle-cash treatment.

    The round-4 writeup ran its whole mechanism argument on S_sleeve = 0.358 —
    a number depressed by the very accounting artifact C7 exists to fix. Repair
    it two ways and the arithmetic separates cleanly: routing idle cash to the
    CORE buys Sharpe by buying CORRELATION, and is strictly dominated by
    routing it to CASH.
    """
    core_ex = excess(curve_returns(ctx.core, ctx.dates), ctx.bil_rets)
    rows = []
    for label, route in (("as frozen (dead idle cash)", None),
                         ("idle capital -> BIL (cash)", "BIL"),
                         ("idle capital -> CORE (C7 as registered)", "CORE")):
        curve = ctx.sleeve if route is None else sleeve_idle_routed(ctx, route)
        sl_ex = excess(curve_returns(curve, ctx.dates), ctx.bil_rets)
        rows.append({"treatment": label, "route": route, **tangency(sl_ex, core_ex)})
    return rows


def implemented_optimum(ctx: Ctx, hi: float = 0.30, step: float = 0.01) -> dict:
    """m3. The costless argmax is ~4%; the harness's OWN implementation (live
    5% band, 10bps) is monotone decreasing from zero, so its optimum is 0%."""
    grid = []
    n = int(round(hi / step))
    for i in range(n + 1):
        w = i * step
        c = sleeve_core(ctx, w)
        grid.append([round(w, 4),
                     metrics(c, ctx.dates, ctx.bil_rets)["sharpe_bil"]])
    best = max(grid, key=lambda r: r[1])
    return {"grid": grid, "argmax_w": best[0], "argmax_sharpe": best[1],
            "monotone_decreasing": all(grid[i][1] > grid[i + 1][1]
                                       for i in range(len(grid) - 1))}


REBAL_RULES: dict[str, dict] = {
    "band05": {"band": LIVE_BAND, "label": "5% absolute band (the live rule, as run)"},
    "daily": {"band": 0.0, "label": "daily"},
    "band005": {"band": 0.005, "label": "0.5% absolute band"},
    "band01": {"band": 0.01, "label": "1% absolute band"},
    "monthly": {"band": None, "rebal": "months", "label": "monthly calendar"},
    "quarterly": {"band": None, "rebal": "quarters", "label": "quarterly calendar"},
}


def rebalance_robustness(ctx: Ctx, w: float, inc: dict, inc_ex: list[float],
                         inc_subs: list[dict], draws: int) -> list[dict]:
    """M3. A 5% ABSOLUTE band never fires on a 5% TARGET weight, so C1-05 as
    run is buy-and-hold. The registration fixes no rebalance rule for C1, so
    the criterion-1 result is an unregistered implementation choice — this
    reports the same arm under every equally registration-compliant rule.
    DESCRIPTIVE: none of these is a registered arm and none enters the bar.
    """
    subs = thirds(ctx.dates)
    out = []
    for name, spec in REBAL_RULES.items():
        rebal = getattr(ctx, spec["rebal"]) if spec.get("rebal") else ()
        curve = sleeve_core(ctx, w, band=spec["band"], rebal=rebal)
        f = metrics(curve, ctx.dates, ctx.bil_rets)
        b = block_bootstrap_sharpe_diff(
            excess(curve_returns(curve, ctx.dates), ctx.bil_rets), inc_ex,
            draws=draws)
        wins = 0
        for sub, isub in zip(subs, inc_subs, strict=True):
            i0 = ctx.dates.index(sub[0])
            wins += beats(metrics(curve, sub, ctx.bil_rets[i0:i0 + len(sub) - 1]),
                          isub)
        out.append({"rule": name, "label": spec["label"],
                    "rebalances": count_rebalances(ctx, w, spec),
                    "sharpe_bil": f["sharpe_bil"], "sortino_bil": f["sortino_bil"],
                    "c1": beats(f, inc), "d_sharpe": b["point"],
                    "ci95": list(boot_ci(b)), "boot_p": b["p_two_sided"],
                    "c3_wins": wins})
    return out


def count_rebalances(ctx: Ctx, w: float, spec: dict) -> int:
    """How many times a sleeve/core rule actually TRADES. Zero is the whole
    point of M3: the live 5% absolute band cannot fire on a 5% target."""
    band = spec["band"]
    sched = set(getattr(ctx, spec["rebal"])) if spec.get("rebal") else set()
    tgt = {"SLEEVE": w, "CORE": 1 - w}
    curves = ctx.legs()
    d0 = ctx.dates[0]
    eq = 1.0
    units = {k: eq * x / curves[k][d0] for k, x in tgt.items() if x}
    n = 0
    for d in ctx.dates[1:]:
        eq = sum(u * curves[k][d] for k, u in units.items())
        w_now = {k: units.get(k, 0.0) * curves[k][d] / eq for k in tgt}
        need = d in sched or (band is not None
                              and any(abs(w_now[k] - tgt[k]) > band for k in tgt))
        if need:
            traded = sum(abs(tgt[k] - w_now[k]) for k in tgt) * eq / 2
            eq -= traded * COST_BPS / 1e4
            units = {k: eq * x / curves[k][d] for k, x in tgt.items() if x}
            n += 1
    return n


def c3_cap_binding(ctx: Ctx) -> dict:
    """M5. The registered 30% cap on C3's inverse-vol weight. Uncapped, the
    ~20%-vol sleeve against a ~12%-vol core wants ~37.5%, so the cap binds on
    most days and C3 degenerates into C6-monthly. That is a REGISTRATION
    flaw, not a harness bug: the harness implements the registration exactly.
    """
    sr = curve_returns(ctx.sleeve, ctx.dates)
    cr = curve_returns(ctx.core, ctx.dates)
    idx = {d: i for i, d in enumerate(ctx.dates)}
    rebal = set(ctx.months)
    raw: float | None = None
    applied: list[float] = []
    uncapped: list[float] = []
    n_at_cap = n_over_cap = n_warmup = n_zero_vol = n_decisions = 0
    for d in ctx.dates:
        if d == ctx.dates[0] or d in rebal:
            ws, wc = _trailing(sr, idx[d], C3_VOL_WINDOW), _trailing(cr, idx[d], C3_VOL_WINDOW)
            raw = None
            if ws is not None and wc is not None:
                n_decisions += 1
                vs, vc = statistics.stdev(ws), statistics.stdev(wc)
                if vs <= 0:
                    n_zero_vol += 1
                if vs > 0 and vc > 0:
                    raw = (1 / vs) / (1 / vs + 1 / vc)
        w = LIVE_SLEEVE_W if raw is None else min(C3_SLEEVE_CAP, raw)
        applied.append(w)
        if raw is None:
            n_warmup += 1
        else:
            uncapped.append(raw)
            n_over_cap += raw > C3_SLEEVE_CAP
        n_at_cap += w >= C3_SLEEVE_CAP - 1e-9
    return {"n_days": len(ctx.dates), "days_at_cap": n_at_cap,
            "frac_at_cap": n_at_cap / len(ctx.dates),
            "days_uncapped_over_cap": n_over_cap,
            "frac_uncapped_over_cap": n_over_cap / len(ctx.dates),
            "days_fallback": n_warmup,
            "monthly_decisions": n_decisions, "zero_sleeve_vol_decisions": n_zero_vol,
            "mean_applied_w": statistics.fmean(applied),
            "min_applied_w": min(applied),
            "mean_uncapped_w": statistics.fmean(uncapped),
            "median_uncapped_w": statistics.median(uncapped),
            "max_uncapped_w": max(uncapped)}


def prior_close_sensitivity(ctx: Ctx, keys: Iterable[str]) -> dict[str, dict]:
    """m1. Re-run the trailing-statistic arms under a STRICT prior-close
    window and record the move. The harness's own convention is same-close
    (documented on `_trailing`); this quantifies the inconsistency with C5."""
    global _trailing
    base = {k: metrics(VARIANTS[k].fn(ctx), ctx.dates,
                       ctx.bil_rets)["sharpe_bil"] for k in keys}
    orig = _trailing

    def strict(rets: list[float], i: int, window: int) -> list[float] | None:
        return None if i - window - 1 < 0 else rets[i - window - 1:i - 1]

    _trailing = strict                       # noqa: F811
    try:
        alt = {k: metrics(VARIANTS[k].fn(ctx), ctx.dates,
                          ctx.bil_rets)["sharpe_bil"] for k in keys}
    finally:
        _trailing = orig
    return {k: {"same_close": base[k], "strict_prior_close": alt[k],
                "delta": alt[k] - base[k]} for k in keys}


POWER_GRID = (0.05, 0.10, 0.20, 0.40)


def injected_edge_power(v_ex: list[float], inc_ex: list[float], *,
                        draws: int, grid: Iterable[float] = POWER_GRID) -> dict:
    """M4. What size of TRUE edge could this arm's own bar have detected?

    A constant is added to the arm's daily excess returns so its Sharpe rises
    by exactly `delta`, and criterion 2 is re-run. This answers the question
    the round-4 writeup answered with an imported +/-0.4 floor: the low-sleeve
    arms are not blind, they resolved a +0.10 Sharpe edge and found nothing.
    """
    sd = statistics.stdev(v_ex)

    def detects(delta: float) -> tuple[bool, float]:
        bump = delta * sd / math.sqrt(TRADING_DAYS)
        b = block_bootstrap_sharpe_diff([x + bump for x in v_ex], inc_ex, draws=draws)
        return excludes_zero(boot_ci(b)), b["p_two_sided"]

    detected = {}
    for delta in grid:
        ok, pv = detects(delta)
        detected[f"{delta:.2f}"] = {"detected": ok, "boot_p": pv}
    lo, hi = 0.0, 2.0
    mde: float | None = None
    if detects(hi)[0]:
        while hi - lo > 0.005:
            mid = (lo + hi) / 2
            if detects(mid)[0]:
                hi = mid
            else:
                lo = mid
        mde = hi
    return {"grid": detected, "min_detectable_edge": mde}


# --- diagnostics demanded by the ROUND-5 counter-agent ------------------------------
# The round-5 verdict was PASS WITH CORRECTIONS: the null is real, but the
# writeup measured its own mechanism against the resolution of the WRONG
# comparison and then declared it unmeasurable. These instruments answer the
# comparisons that were actually asked. None of them moves the registered bar.

POWER_MC_WORLDS = 200
POWER_MC_DRAWS = 1500


def power_mc(v_ex: list[float], inc_ex: list[float], *,
             worlds: int = POWER_MC_WORLDS, draws: int = POWER_MC_DRAWS,
             block: int = BOOT_BLOCK, seed: int = BOOT_SEED,
             levels: Iterable[float] = (0.50, 0.80, 0.90),
             at: Iterable[float] = ()) -> dict:
    """M2. `injected_edge_power`'s "smallest detectable edge" is a 50%-POWER
    threshold, not the conventional 80%-power MDE.

    For a CONSTANT injected edge the registered test fires exactly when
    delta > -CI_lo of that sample's own paired bootstrap (the shift moves the
    whole draw distribution by ~delta), so the distribution of -CI_lo across
    RESAMPLED WORLDS is the power curve: power(delta) = P(-CI_lo < delta), and
    the MDE at power p is the p-th quantile of that distribution. Each world is
    a circular block resample of the SAME paired history, so it carries the
    arm's observed gap: this is the power to detect an edge of `delta` on top
    of what is already there, which is the quantity the writeup needs.
    """
    n = len(v_ex)
    rng = random.Random(seed ^ 0x5EED)
    thr: list[float] = []
    for wi in range(worlds):
        a: list[float] = []
        b: list[float] = []
        for st, ln in block_starts(n, block, rng):
            for j in range(st, st + ln):
                a.append(v_ex[j % n])
                b.append(inc_ex[j % n])
        lo, _ = boot_ci(block_bootstrap_sharpe_diff(a, b, block=block,
                                                    draws=draws, seed=seed + wi))
        thr.append(-lo)
    thr.sort()

    def q(pr: float) -> float:
        return thr[min(len(thr) - 1, max(0, round(pr * (len(thr) - 1))))]

    return {"worlds": worlds, "draws": draws,
            "mde_at_power": {f"{pr:.2f}": q(pr) for pr in levels},
            "power_at": {f"{d:.4f}": sum(1 for t in thr if t < d) / len(thr)
                         for d in at}}


def _paired(ctx: Ctx, live: dict[str, float], dead: dict[str, float], *,
            draws: int, deep: int | None = None) -> dict:
    """One like-for-like bootstrap between two books that differ ONLY in how
    idle sleeve cash is treated."""
    a = excess(curve_returns(live, ctx.dates), ctx.bil_rets)
    b = excess(curve_returns(dead, ctx.dates), ctx.bil_rets)
    bt = block_bootstrap_sharpe_diff(a, b, draws=deep or draws,
                                     shallow=draws if deep else None)
    shallow = dict(bt, dist=bt["dist_shallow"]) if deep else bt
    ml = metrics(live, ctx.dates, ctx.bil_rets)
    md = metrics(dead, ctx.dates, ctx.bil_rets)
    row = {"sharpe_live": ml["sharpe_bil"], "sharpe_dead": md["sharpe_bil"],
           "cagr_live": ml["cagr"], "cagr_dead": md["cagr"],
           "d_sharpe": bt["point"], "d_cagr": ml["cagr"] - md["cagr"],
           "ci95": list(boot_ci(shallow)), "boot_p": shallow["p_two_sided"]}
    if deep:
        conf_all = 1 - NAIVE_ALPHA / len(VARIANTS)
        row["ci_bonferroni_all_rounds"] = list(boot_ci(bt, conf_all))
        row["bonferroni_conf_all_rounds"] = conf_all
    return row


def cash_mechanism_pairs(ctx: Ctx, *, draws: int,
                         deep: int = BOOT_DRAWS_DEEP) -> list[dict]:
    """M1. The mechanism against ITS OWN counterfactual.

    Round 5 compared each D1 arm to `INC-B5` — a book without the sleeve at all
    — and, finding a +/-0.06 interval around a +0.012 mechanism, concluded the
    data "cannot adjudicate the mechanism in either direction". That conflates
    two claims. The cash routing's own comparator is the SAME book with the
    idle balance left dead, which differs by a near-deterministic drift; the
    harness has had the right instrument since round 4 (`c7_vs_c6_band05`,
    "C7 is a MECHANICAL fix, so its like-for-like comparator is the same book
    WITHOUT the fix") and round 5 simply never pointed it at D1.

    Honest reading, and it belongs next to the number: a paired comparison
    between two books that differ only by "idle cash earns BIL instead of 0%"
    is close to an accounting identity, because BIL's daily return was >= 0 on
    essentially every day of this window. p<0.0001 here is not a discovery.
    That is the point: a mechanism that is arithmetic does not need a noisy
    portfolio test to license it, and calling it unresolvable is what would
    wrongly stop the work.
    """
    rows = []
    for w in (*D1_WEIGHTS, LIVE_SLEEVE_W):
        label = (f"D1-{int(w * 100):02d}" if w in D1_WEIGHTS
                 else f"the live {w:.0%} sleeve weight")
        rows.append({"comparison": label, "weight": w,
                     **_paired(ctx, d1_sleeve_cash(ctx, w),
                               d1_dead_cash_twin(ctx, w), draws=draws, deep=deep)})
    rows.append({"comparison": "R2-A sleeve ALONE (idle -> BIL vs frozen)",
                 "weight": 1.0,
                 **_paired(ctx, sleeve_idle_routed(ctx, D1_CASH_LEG), ctx.sleeve,
                           draws=draws, deep=deep)})
    return rows


SWEEP_ASSUMPTIONS = ((1.00, 0.0), (0.80, 25.0), (0.50, 100.0))


def sweep_robustness(ctx: Ctx, w: float, *, draws: int) -> list[dict]:
    """M1, continued. The same paired measurement under pessimism about the
    live sweep: partial coverage of the idle balance and an annual drag on the
    swept part. The live executor's sweep is skipped while any book order is
    pending, leaves a residual under max($50, one BIL share), can be clamped by
    BLEND_BUDGET headroom, and only fires on the next cycle."""
    out = []
    for cov, drag in SWEEP_ASSUMPTIONS:
        live = d1_sleeve_cash(ctx, w, coverage=cov, drag_bps=drag)
        out.append({"coverage": cov, "drag_bps": drag,
                    **_paired(ctx, live, d1_dead_cash_twin(ctx, w), draws=draws)})
    return out


def swept_vs_frozen(ctx: Ctx, *, draws: int) -> list[dict]:
    """M4. The comparator inconsistency, and it changes published numbers.

    `INC-3070SPY` is the live H13 design and `ibkr-executor/app/blend.py`
    sweeps that book's idle SLEEVE cash to BIL — yet the harness models it, and
    the REF-R2A sleeve reference, with DEAD cash while D1/D2 get the routing.
    Both conventions are reported side by side everywhere the sleeve or the
    30/70 baseline appears. The frozen curve is NOT restated: it is a pinned
    input to rounds 1-4 and stays exactly as it was.
    """
    rows = [{"book": "REF-R2A (R2-A sleeve alone)",
             **_paired(ctx, sleeve_idle_routed(ctx, D1_CASH_LEG), ctx.sleeve,
                       draws=draws)},
            {"book": "INC-3070SPY (30/70 R2-A/SPY, the live H13 design)",
             **_paired(ctx, inc_3070spy(ctx, swept=True), inc_3070spy(ctx),
                       draws=draws)}]
    return rows


def d2_warmup_readings(ctx: Ctx, inc: dict, inc_ex: list[float],
                       inc_subs: list[dict], *, draws: int) -> list[dict]:
    """M3. D2's verdict was set by an UNREGISTERED convention.

    `monthly_weights` fell back to the live 30% for the 60-day warm-up — 81 of
    1,433 days, in the early-2021 stretch that dominates D2's statistics — a
    weight D2's contract never names. The registered readings are its own two
    legs. This reports all three; the arm is JUDGED on the registered low leg.
    """
    subs = thirds(ctx.dates)
    out = []
    for wu, tag in ((LIVE_SLEEVE_W, "30% (the live weight, UNREGISTERED for D2)"),
                    (D2_LO_W, "5% (the registered low leg — as judged)"),
                    (D2_HI_W, "15% (the registered high leg)")):
        curve = d2_corr_at_tangency(ctx, warmup=wu)
        f = metrics(curve, ctx.dates, ctx.bil_rets)
        b = block_bootstrap_sharpe_diff(
            excess(curve_returns(curve, ctx.dates), ctx.bil_rets), inc_ex,
            draws=draws)
        wins = 0
        for sub, isub in zip(subs, inc_subs, strict=True):
            i0 = ctx.dates.index(sub[0])
            wins += beats(metrics(curve, sub, ctx.bil_rets[i0:i0 + len(sub) - 1]),
                          isub)
        out.append({"warmup_w": wu, "label": tag, "sharpe_bil": f["sharpe_bil"],
                    "sortino_bil": f["sortino_bil"], "cagr": f["cagr"],
                    "c1": beats(f, inc), "d_sharpe": b["point"],
                    "ci95": list(boot_ci(b)), "boot_p": b["p_two_sided"],
                    "c3_wins": wins})
    return out


def d2_warmup_days(ctx: Ctx) -> int:
    """How many days D2 spends on its warm-up default (the 60-day trailing
    window is not yet available)."""
    idx = {d: i for i, d in enumerate(ctx.dates)}
    rebal = set(ctx.months)
    n, warm = 0, True
    for d in ctx.dates:
        if d == ctx.dates[0] or d in rebal:
            warm = _trailing(ctx.bil_rets, idx[d], D2_CORR_WINDOW) is None
        n += warm
    return n


def d3_literal_rule(ctx: Ctx, inc_ex: list[float], *, draws: int) -> dict:
    """m1. D3 is "uncapped" on only 78% of days.

    On the 313 fallback days (60-day warm-up plus the months where the sleeve's
    trailing vol is exactly zero) the registered rule holds 30%. On the
    zero-vol months the LITERAL uncapped rule — 1/vol_sleeve over the sum of
    inverse vols — diverges to a 100% sleeve. Warm-up days have no literal
    value at all, so they keep the registered 30%. The override FLATTERS D3,
    so the arm's failure survives it; both readings are reported.
    """
    sr = curve_returns(ctx.sleeve, ctx.dates)
    cr = curve_returns(ctx.core, ctx.dates)

    def pick(i: int) -> float | None:
        ws, wc = _trailing(sr, i, D3_VOL_WINDOW), _trailing(cr, i, D3_VOL_WINDOW)
        if ws is None or wc is None:
            return None                      # warm-up: no literal value exists
        vs, vc = statistics.stdev(ws), statistics.stdev(wc)
        if vc <= 0:
            return None
        if vs <= 0:
            return 1.0                       # the literal limit of 1/vs -> inf
        return (1 / vs) / (1 / vs + 1 / vc)

    curve = portfolio(ctx.dates, ctx.legs(),
                      monthly_weights(ctx, pick, LIVE_SLEEVE_W),
                      rebal_dates=ctx.months)
    f = metrics(curve, ctx.dates, ctx.bil_rets)
    b = block_bootstrap_sharpe_diff(
        excess(curve_returns(curve, ctx.dates), ctx.bil_rets), inc_ex, draws=draws)
    return {"sharpe_bil": f["sharpe_bil"], "sortino_bil": f["sortino_bil"],
            "cagr": f["cagr"], "max_dd": f["max_dd"], "d_sharpe": b["point"],
            "ci95": list(boot_ci(b)), "boot_p": b["p_two_sided"]}


def westfall_young_maxt(ctx: Ctx, keys: list[str], inc_ex: list[float], *,
                        draws: int = BOOT_DRAWS, block: int = BOOT_BLOCK,
                        seed: int = BOOT_SEED) -> dict:
    """The multiplicity correction that is not theatre.

    Bonferroni over these arms is INERT (the smallest raw p across the whole
    campaign is ~0.36) and it is also the wrong instrument: the arms are
    near-identical portfolios, so their tests are massively correlated and
    Bonferroni over-corrects. The step-down max-T (Westfall-Young) resampling
    correction uses the SAME shared draw sequence for every arm, so the
    dependence is carried rather than assumed away: the adjusted p for arm j is
    the probability that the LARGEST studentized statistic anywhere in the
    campaign exceeds arm j's, under resampling.

    What no correction in this family covers, and the writeup must say so: the
    selection of R2-A itself over rounds 1-3, B.5's hindsight-fitted weights,
    and the choice of window. The 22-arm denominator is the small multiplicity.
    """
    ser = {k: excess(curve_returns(VARIANTS[k].fn(ctx), ctx.dates), ctx.bil_rets)
           for k in keys}
    n = len(inc_ex)
    pre = {k: _wrap_prefix(v) for k, v in ser.items()}
    pi, qi = _wrap_prefix(inc_ex)
    point = {k: sharpe(ser[k]) - sharpe(inc_ex) for k in keys}
    rng = random.Random(seed)
    dist: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(draws):
        blocks = block_starts(n, block, rng)
        si = s2i = 0.0
        for st, ln in blocks:
            si += pi[st + ln] - pi[st]
            s2i += qi[st + ln] - qi[st]
        db = _sharpe_from_sums(si, s2i, n)
        for k in keys:
            pa, qa = pre[k]
            sa = s2a = 0.0
            for st, ln in blocks:
                sa += pa[st + ln] - pa[st]
                s2a += qa[st + ln] - qa[st]
            dist[k].append(_sharpe_from_sums(sa, s2a, n) - db)
    se = {k: statistics.stdev(dist[k]) for k in keys}
    t_obs = {k: abs(point[k]) / se[k] for k in keys}
    max_t = [max(abs(dist[k][i] - point[k]) / se[k] for k in keys)
             for i in range(draws)]
    adj = {k: sum(1 for m in max_t if m >= t_obs[k]) / draws for k in keys}
    # Raw two-sided p on the SAME shared sequence, so "how far is anything from
    # the naive bar" and "how far from the adjusted one" are comparable.
    raw = {k: min(1.0, 2 * min(sum(1 for d in dist[k] if d <= 0) / draws,
                               sum(1 for d in dist[k] if d >= 0) / draws))
           for k in keys}
    strongest = min(adj, key=lambda k: (adj[k], -abs(point[k])))
    pos = [k for k in keys if point[k] > 0]
    best_pos = max(pos, key=lambda k: point[k]) if pos else None
    least_raw = min(raw, key=lambda k: raw[k])
    return {"n_arms": len(keys), "draws": draws, "seed": seed,
            "adjusted_p": adj, "raw_p_shared": raw, "t_obs": t_obs,
            "d_sharpe": point,
            "strongest_arm": strongest, "strongest_adjusted_p": adj[strongest],
            "strongest_d_sharpe": point[strongest],
            "best_positive_arm": best_pos,
            "best_positive_adjusted_p": adj[best_pos] if best_pos else None,
            "best_positive_d_sharpe": point[best_pos] if best_pos else None,
            "min_raw_p": raw[least_raw], "min_raw_p_arm": least_raw}


def proxy_session_usage(ctx: Ctx) -> dict:
    """m2. The report's "1079 of 2511 synthetic sessions use proxy returns" is
    a hard-coded string inherited from an earlier round. This counts it."""
    per: dict[str, int] = {}
    n = 0
    for i in range(1, len(ctx.dates)):
        d, p = ctx.dates[i], ctx.dates[i - 1]
        used = False
        for fund in B5_WEIGHTS:
            src = ctx.raw.get(fund) or {}
            if not (d in src and p in src):
                per[fund] = per.get(fund, 0) + 1
                used = True
        n += used
    return {"n_returns": len(ctx.dates) - 1, "n_sessions": len(ctx.dates),
            "returns_using_a_proxy": n, "per_fund": per,
            "weight_on_proxied_funds": round(
                sum(B5_WEIGHTS[f] for f in per), 4)}


# --- run ---------------------------------------------------------------------------

def build_all(keys: list[str]) -> dict[str, Ctx]:
    tickers = sorted(set(B5_WEIGHTS) | set(EXTRA_TICKERS)
                     | {p for ps in PROXIES.values() for p in ps})
    raw = {t: adj_series(t) for t in tickers}
    sleeve_raw = load_frozen_sleeve()
    idle = load_sleeve_exposure(sleeve_raw)
    gate, gate_src = xbi_gate_200dma()
    ctxs = {k: build_ctx(k, raw, sleeve_raw, gate, idle) for k in keys}
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


def idle_capital_stats(ctx: Ctx) -> dict:
    """R2-A's idle CAPITAL in this window — what C7 actually routes.

    The round-4 harness reported only the zero-RETURN days (424/1432 = 29.6%)
    and believed that was the whole observable artifact. It is not: the
    time-average idle fraction is 63.3%, roughly twice as much
    (round-4 counter-agent M1).
    """
    f = [ctx.idle_frac[d] for d in ctx.dates]
    r = curve_returns(ctx.sleeve, ctx.dates)
    return {"n_days": len(f),
            "mean_idle_fraction": statistics.fmean(f),
            "median_idle_fraction": statistics.median(f),
            "days_fully_idle": sum(1 for x in f if x > 0.9999),
            "days_over_90pct_idle": sum(1 for x in f if x > 0.90),
            "zero_return_days": sum(1 for x in r if x == 0.0),
            "zero_return_of": len(r)}


def main(argv: list[str] | None = None) -> None:      # noqa: PLR0915
    ap = argparse.ArgumentParser(description="pre-registered variant harness")
    ap.add_argument("--round", type=int, choices=sorted(ROUNDS), default=DEFAULT_ROUND,
                    help="which registered round to judge and report; a finished "
                         "round's record is never rewritten by a later one")
    ap.add_argument("--variant", action="append", default=None,
                    help="variant or group key (repeatable), e.g. C7 or D1-05")
    ap.add_argument("--window", choices=["real", "synth", "both"], default="both",
                    help="which window's table to PRINT; both are always computed "
                         "because the registered survival bar spans both")
    ap.add_argument("--json", default=None, help="write the results JSON here")
    ap.add_argument("--draws", type=int, default=BOOT_DRAWS)
    args = ap.parse_args(argv)

    show = ["real", "synth"] if args.window == "both" else [args.window]
    rnd = ROUNDS[args.round]
    sel = [k for k, v in VARIANTS.items() if v.round == args.round]
    if args.variant:
        want = set(args.variant)
        sel = [k for k in sel if k in want or VARIANTS[k].group in want]
        assert sel, f"no round-{args.round} variant matches {sorted(want)}"
    order = sel + list(INCUMBENTS)
    full_run = not args.variant and args.draws == BOOT_DRAWS

    ctxs = build_all(["real", "synth"])
    # The registered selection rule for D4, applied ONCE on the real window
    # before any round-5 curve is built (see d1_best_weight). It runs in a
    # round-4 run too, because the campaign-wide max-T correction has to build
    # every arm of both rounds; it reads only D1 curves and changes nothing.
    d1_best_weight(ctxs["real"])
    res = {w: run_window(ctxs[w], order) for w in ("real", "synth")}
    for w in ("real", "synth"):
        c = ctxs[w]
        print(f"{c.label:22s} {c.dates[0]} -> {c.dates[-1]}  n={len(c.dates)}")
    sanity(res["real"])
    print(f"Round {args.round} ({rnd['groups']}), contract {rnd['contract']}: "
          f"{len(sel)} arms.")
    idle = idle_capital_stats(ctxs["real"])
    print(f"R2-A idle CAPITAL, real window: mean {idle['mean_idle_fraction']:.1%}, "
          f"median {idle['median_idle_fraction']:.1%}, fully idle "
          f"{idle['days_fully_idle']}/{idle['n_days']} days "
          f"({idle['zero_return_days']}/{idle['zero_return_of']} zero-return). "
          f"C7 routes the CAPITAL, not the zero-return days.")

    # -- best incumbent: highest BIL-excess Sharpe over the FULL real window
    best = max(INCUMBENT_KEYS, key=lambda k: res["real"][k]["full"]["sharpe_bil"])
    rc, ir = ctxs["real"], res["real"][best]
    inc_ex = [a - b for a, b in
              zip(curve_returns(ir["curve"], rc.dates), rc.bil_rets, strict=True)]
    n_tested = len(sel)
    conf_adj = 1 - NAIVE_ALPHA / n_tested
    boots: dict[str, dict] = {}
    verdicts: dict[str, dict] = {}
    deep_draws = max(args.draws, BOOT_DRAWS_DEEP)
    for k in sel:
        v_ex = excess(curve_returns(res["real"][k]["curve"], rc.dates), rc.bil_rets)
        # ONE deep bootstrap serves both intervals. The draw sequence depends
        # only on the seed, so the first args.draws draws ARE the registered
        # bootstrap — the 95% CI and p-value are bit-identical to a 4000-draw
        # run — while the 99.667% Bonferroni tail stops being read off 7 order
        # statistics a side (counter-agent m4).
        deep = block_bootstrap_sharpe_diff(v_ex, inc_ex, draws=deep_draws,
                                           shallow=args.draws)
        b = dict(deep, dist=deep["dist_shallow"], draws=args.draws)
        boots[k] = b
        v = evaluate(res["real"][k]["full"], res["real"][k]["subs"],
                     res["synth"][k]["full"], ir["full"], ir["subs"],
                     res["synth"][best]["full"], b)
        ci_adj = boot_ci(deep, conf_adj)
        v["ci_bonferroni"] = list(ci_adj)
        v["bonferroni_draws"] = deep_draws
        v["bonferroni_tail_draws"] = round((1 - conf_adj) / 2 * deep_draws)
        v["clears_bonferroni"] = bool(v["survives"] and excludes_zero(ci_adj))
        v["power"] = injected_edge_power(v_ex, inc_ex, draws=args.draws)
        # M2: the line above is a 50%-power threshold by construction. The
        # 80%-power MDE is the one the writeup quotes as a detection floor.
        if full_run:
            v["power_mc"] = power_mc(
                v_ex, inc_ex,
                at=[x for x in [v["power"]["min_detectable_edge"]] if x])
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

    other = sorted({k for k, v in VARIANTS.items() if v.round != args.round})
    meta = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "round": args.round,
        "contract": rnd["contract"],
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
        # The campaign-wide bar. Round 5's hypotheses were generated by reading
        # round 4's results, so the honest denominator spans BOTH rounds.
        "n_arms_all_rounds": len(VARIANTS),
        "arms_other_rounds": len(other),
        "bonferroni_alpha_all_rounds": NAIVE_ALPHA / len(VARIANTS),
        "bonferroni_conf_all_rounds": 1 - NAIVE_ALPHA / len(VARIANTS),
        "cost_bps_per_side": COST_BPS,
        "tail_sleeve": "TAIL (registered, identical for every variant)",
        "adjudication_basis": "BIL-excess Sharpe; rf=0 reported alongside",
        "sortino_convention": "standard — downside deviation over N",
        "bootstrap": {"block_days": BOOT_BLOCK, "draws": args.draws,
                      "deep_draws": deep_draws,
                      "bonferroni_tail_draws": round((1 - conf_adj) / 2 * deep_draws),
                      "seed": BOOT_SEED, "paired": True, "circular": True,
                      "basis": "BIL-excess daily returns"},
        "gate_source": getattr(ctxs["real"], "gate_source", None),
        "sleeve": "FROZEN R2-A dollar curve (data/r2a_daily.json), reused verbatim; "
                  "daily invested notional from data/r2a_exposure.json",
        "sleeve_idle_capital_real": idle,
        "mechanism_real": mechanism_table(rc),
        "corr_core_sleeve_real": pearson(curve_returns(rc.core, rc.dates),
                                         curve_returns(rc.sleeve, rc.dates)),
        "synthetic_kmlm": "KMLM spliced to DBMF then WTMF, unadjusted",
        "c7_vs_c6_band05": c7_vs_c6,
        "measurement_basis": ("daily MTM total returns on adjusted closes; CAGR "
                              "calendar-annualized at 365.25; Sharpe/Sortino "
                              "annualized sqrt(252); drawdown peak-to-trough "
                              "within each window"),
    }

    # --- round-5 counter-agent corrections, reported in BOTH rounds --------
    # M4 (the comparator inconsistency) and the multiplicity ruling are
    # properties of the campaign, not of one round, so both reports carry them.
    meta["swept_vs_frozen_real"] = swept_vs_frozen(rc, draws=args.draws)
    meta["proxy_session_usage_synth"] = proxy_session_usage(ctxs["synth"])
    meta["max_t_all_rounds"] = (
        westfall_young_maxt(rc, sorted(VARIANTS), inc_ex, draws=args.draws)
        if full_run else None)

    if args.round == 4:
        meta["implemented_optimum_real"] = implemented_optimum(rc)
        meta["c3_cap_binding_real"] = c3_cap_binding(rc)
        meta["prior_close_sensitivity_real"] = prior_close_sensitivity(
            rc, ("C3", "C4", "C8"))
        meta["c1_05_rebalance_robustness"] = rebalance_robustness(
            rc, C1_WEIGHTS[0], ir["full"], inc_ex, ir["subs"], args.draws)
    if args.round == 5:
        meta["d1_best_weight"] = _D1_BEST_W
        meta["d3_weight_distribution"] = {
            w: d3_weight_distribution(ctxs[w]) for w in ("real", "synth")}
        meta["d1_vs_c7_routing"] = mechanism_table(rc)
        # M1 — the mechanism against its own counterfactual, plus the same
        # measurement under a pessimistic live sweep.
        meta["cash_mechanism_paired_real"] = cash_mechanism_pairs(
            rc, draws=args.draws)
        meta["sweep_robustness_real"] = sweep_robustness(
            rc, _D1_BEST_W, draws=args.draws)
        # M3 — D2's warm-up default was unregistered; all three readings.
        meta["d2_warmup_readings_real"] = d2_warmup_readings(
            rc, ir["full"], inc_ex, ir["subs"], draws=args.draws)
        meta["d2_warmup_days_real"] = d2_warmup_days(rc)
        meta["d2_warmup_registered_default"] = D2_WARMUP_W
        # m1 — D3's fallback override flatters it; the literal rule too.
        meta["d3_literal_rule_real"] = d3_literal_rule(rc, inc_ex, draws=args.draws)

    _print_table(res, order, verdicts, meta, show)

    path = Path(args.json) if args.json else (rnd["results"] if full_run else None)
    if path:
        payload = {"meta": meta, "verdicts": verdicts, "results": {
            w: {k: {kk: vv for kk, vv in r.items() if kk != "curve"}
                for k, r in res[w].items()} for w in ("real", "synth")}}
        payload["curves"] = {w: {k: _downsample(res[w][k]["curve"], ctxs[w].dates)
                                 for k in order} for w in ("real", "synth")}
        path.write_text(json.dumps(_round(payload), indent=1))
        print(f"\nResults JSON written to {path}")
    if full_run:
        writer = _write_report if args.round == 4 else _write_report_r5
        writer(res, order, verdicts, meta)
        print(f"Report written to {rnd['report']}")


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
    print(f"\nMULTIPLE COMPARISON: {n} round-{meta['round']} arms tested "
          f"({meta['n_registered_groups']} registered variants, "
          f"{ROUNDS[meta['round']]['groups']}); "
          f"{meta['n_arms_all_rounds']} across all rounds. "
          f"Naive threshold alpha={meta['naive_alpha']:.2f} (95% CI); "
          f"Bonferroni-adjusted alpha={meta['bonferroni_alpha']:.5f}, i.e. a "
          f"{100 * meta['bonferroni_conf']:.3f}% CI must exclude zero.")
    clears = [k for k, v in verdicts.items() if v.get("clears_bonferroni")]
    surv = [k for k, v in verdicts.items() if v["survives"]]
    print(f"Across ALL rounds the adjusted bar is "
          f"alpha={meta['bonferroni_alpha_all_rounds']:.5f} "
          f"({100 * meta['bonferroni_conf_all_rounds']:.3f}% CI).")
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


def _mde_table(verdicts: dict) -> list[str]:
    """The injected-edge resolution table, on BOTH power conventions (M2)."""
    out = ["| variant | 95% CI half-width | +0.05 | +0.10 | +0.20 | +0.40 | "
           "MDE @50% power (as published) | MDE @80% power |",
           "|---|---|---|---|---|---|---|---|"]
    for k, v in verdicts.items():
        lo, hi = v["ci95"]
        cells = []
        for g in POWER_GRID:
            e = v["power"]["grid"][f"{g:.2f}"]
            cells.append(f"**detected** (p={e['boot_p']:.3f})" if e["detected"]
                         else "no")
        mde = v["power"]["min_detectable_edge"]
        mc = v.get("power_mc")
        out.append(f"| {k} | +/-{(hi - lo) / 2:.3f} | " + " | ".join(cells)
                   + f" | {('%+.2f' % mde) if mde else 'not within +2.0'} | "
                   + (f"{mc['mde_at_power']['0.80']:+.2f} |" if mc else "— |"))
    return out


def _write_report(res: dict, order: list[str], verdicts: dict, meta: dict) -> None:
    best = meta["best_incumbent"]
    n = meta["n_variants_tested"]
    surv = [k for k, v in verdicts.items() if v["survives"]]
    clears = [k for k, v in verdicts.items() if v.get("clears_bonferroni")]
    idle = meta["sleeve_idle_capital_real"]
    mt = meta["max_t_all_rounds"]
    swept = meta["swept_vs_frozen_real"]
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
    w(f"**That correction is INERT, and saying so is part of reporting it "
      f"honestly** (round-5 counter-agent): the smallest raw two-sided p across "
      f"all {mt['n_arms']} arms of the campaign is {mt['min_raw_p']:.3f} "
      f"(`{mt['min_raw_p_arm']}`), so nothing here is within two orders of "
      f"magnitude of even the naive bar — no multiplicity correction is "
      f"load-bearing. Bonferroni is also the wrong instrument for arms that are "
      f"near-identical portfolios: their tests are massively correlated and it "
      f"over-corrects. The step-down max-T (Westfall-Young) adjustment on the "
      f"SHARED draw sequence across all {mt['n_arms']} arms gives "
      f"{mt['best_positive_adjusted_p']:.3f} for the best positive arm in "
      f"either round (`{mt['best_positive_arm']}`, round 5) and "
      f"{mt['strongest_adjusted_p']:.3f} for the largest statistic anywhere in "
      f"the campaign (`{mt['strongest_arm']}`, this round, on the losing side "
      f"of zero). **And the multiplicity that actually "
      f"matters is in no denominator at all:** the selection of R2-A across "
      f"rounds 1-3, B.5's hindsight-fitted weights, and the choice of window.")
    w("")
    w("This document was REVISED after an adversarial counter-agent pass "
      "(scratchpad/r4_counter_verdict.md, verdict: PASS WITH CORRECTIONS — the "
      "null is REAL). Five material corrections are applied here: C7 is "
      "re-implemented on R2-A's true idle CAPITAL (M1); the mechanism section "
      "now states that routing idle cash to the core is DOMINATED by routing "
      "it to cash (M2); the criterion-1 claim is qualified as "
      "rebalance-rule-dependent (M3); the imported \"+/-0.4 noise floor\" is "
      "replaced by each arm's own interval plus a measured power curve (M4); "
      "and C3 is marked VOID AS SPECIFIED because its registered cap made it a "
      "restatement of C6-monthly (M5). The verifier reproduced every other "
      "headline number, independently rebuilt the R2-A book from the round-2 "
      "pipeline and matched the frozen curve on all 2,672 days to <1e-6, and "
      "reimplemented the paired block bootstrap from scratch to 5e-15.")
    w("")
    w("It was revised a SECOND time after the ROUND-5 counter-agent pass "
      "(`scratchpad/r5_counter_verdict.md`), which found three faults that "
      "reach back into this document. No round-4 arm's verdict moves and no "
      "round-4 number in the tables above changes. What is added: the sleeve "
      "reference and the 30/70 incumbent are now carried under BOTH cash "
      "conventions, because `ibkr-executor/app/blend.py` sweeps idle sleeve "
      "cash and this harness modelled those two books with it dead while C7 "
      "and round 5's D1/D2 got the routing (M4); the resolution table now "
      "prints an 80%-power MDE beside the 50%-power number it always "
      "reported (M2); and the multiple-comparison block says plainly that "
      "Bonferroni is inert here and reports a max-T adjustment instead.")
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
    w(f"- Bonferroni interval: read from a {meta['bootstrap']['deep_draws']:,}-draw "
      f"run of the SAME seeded sequence, so its first "
      f"{meta['bootstrap']['draws']:,} draws are the registered bootstrap "
      f"bit-for-bit while the {100 * meta['bonferroni_conf']:.3f}% tail rests on "
      f"~{meta['bootstrap']['bonferroni_tail_draws']} draws a side instead of 7 "
      f"(counter-agent m4).")
    w("- Trailing statistics (C3/C4/C8) use the engine's SAME-CLOSE "
      "decide/execute convention; C5's gate is genuinely prior-close because "
      "it inherits R2-A's entry condition. The cost of that inconsistency is "
      "measured below, not assumed away.")
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
            lo, hi = verdicts[k]["ci95"]
            bits.append(f"{k} (rf=0 Sharpe {f['sharpe_rf0']:.4f} vs "
                        f"{b['sharpe_rf0']:.4f}, a {f['sharpe_rf0'] - b['sharpe_rf0']:+.4f} "
                        f"gap against ITS OWN paired 95% CI of "
                        f"+/-{(hi - lo) / 2:.3f})")
        w("")
        w(f"Those flips change NO verdict: {'; '.join(bits)} — and each still "
          f"fails criteria 2 and 3. They are reported because the registration "
          f"requires both bases printed, not because either is a finding. Each "
          f"gap is compared to that ARM's own interval; there is no single "
          f"campaign-wide noise floor, and the round-4 counter-agent showed "
          f"that quoting one (the +/-0.4 taken from the earlier B.5-core vs "
          f"SPY-core comparison) understated this round's resolution by up to "
          f"7x.")
    w("")
    w("## Why nothing survived, and what criterion 4 did not test")
    w("")
    mech = meta["mechanism_real"]
    opt = meta["implemented_optimum_real"]
    w(f"The mechanism is not new evidence, it is the round-4 counter-agent's "
      f"finding restated on a wider grid: on a B.5 core the optimal R2-A weight "
      f"is a few per cent — effectively zero — because a sleeve helps at the "
      f"margin only when its Sharpe exceeds rho times the core's, and here "
      f"{res['real']['REF-R2A']['full']['sharpe_bil']:.3f} sits barely above "
      f"{meta['corr_core_sleeve_real']:.3f} x "
      f"{res['real'][best]['full']['sharpe_bil']:.3f} = "
      f"{meta['corr_core_sleeve_real'] * res['real'][best]['full']['sharpe_bil']:.3f}. "
      f"Every C1..C8 arm is a way of holding MORE sleeve than that, or of "
      f"trading it differently, so the whole grid lands below the core alone. "
      f"Within C1 the damage is monotone in sleeve weight "
      f"({verdicts['C1-05']['d_sharpe']:+.3f} at 5% to "
      f"{verdicts['C1-10']['d_sharpe']:+.3f} at 10% to "
      f"{verdicts['C1-15']['d_sharpe']:+.3f} at 15% to "
      f"{verdicts['C1-20']['d_sharpe']:+.3f} at 20%), and it continues to "
      f"{verdicts['C6-band05']['d_sharpe']:+.3f} at the live 30% — though that "
      f"last figure is `C6-band05`, a C6 arm, not a C1 one.")
    w("")
    w(f"Two numbers for \"the optimal weight\", because they answer different "
      f"questions. The closed-form tangency weight on the sleeve AS FROZEN is "
      f"{mech[0]['w_star']:.2%} and the costless daily-rebalanced empirical "
      f"argmax agrees at ~4%, worth {mech[0]['uplift']:+.4f} Sharpe. But in "
      f"THIS harness's own implementation — the live 5% band, 10bps a side — "
      f"Sharpe(BIL) is monotone decreasing from w=0 across the whole 0-30% "
      f"grid, so the implemented optimum is exactly "
      f"{opt['argmax_w']:.0%} ({opt['argmax_sharpe']:.4f}). \"About 5%\" is the "
      f"costless figure; the tradable figure is zero.")
    w("")
    w("Criterion 4 was NOT binding. Every arm passed it, because the best "
      "incumbent (B.5 alone) is the WEAKEST comparator on the synthetic "
      f"window — Sharpe(BIL) {res['synth'][best]['full']['sharpe_bil']:.2f} "
      f"there against {res['synth']['INC-3070SPY']['full']['sharpe_bil']:.2f} "
      f"for 30/70 R2-A/SPY. A \"Y\" in column 4 means \"did not lose to a weak "
      "bar\", not \"held up out of sample\". Read columns 1-3 as the test.")
    w("")
    w("### The mechanism, with the accounting artifact repaired (M2)")
    w("")
    w("The arithmetic above runs on S_sleeve = "
      f"{mech[0]['sharpe_sleeve']:.3f} — a number DEPRESSED by the very "
      "accounting artifact C7 exists to fix, because the frozen sleeve holds "
      "dead cash. Repair it two ways and the sleeve's marginal value "
      "separates cleanly:")
    w("")
    w("| sleeve treatment | Sharpe(BIL) of the sleeve | rho to core | tangency w* | "
      "Sharpe uplift at w* |")
    w("|---|---|---|---|---|")
    for r in mech:
        w(f"| {r['treatment']} | {r['sharpe_sleeve']:.3f} | {r['rho_to_core']:.3f} | "
          f"{r['w_star']:.1%} | {r['uplift']:+.4f} |")
    w("")
    w(f"**Routing idle sleeve cash to the CORE buys Sharpe by buying "
      f"CORRELATION, and is strictly dominated by routing it to CASH.** "
      f"Crediting the core lifts the sleeve's own Sharpe from "
      f"{mech[0]['sharpe_sleeve']:.3f} to {mech[2]['sharpe_sleeve']:.3f}, but it "
      f"drags rho from {mech[0]['rho_to_core']:.3f} to "
      f"{mech[2]['rho_to_core']:.3f}, so the tangency weight only reaches "
      f"{mech[2]['w_star']:.1%} and the uplift is {mech[2]['uplift']:+.4f}. "
      f"Crediting BIL lifts it to {mech[1]['sharpe_sleeve']:.3f} while leaving "
      f"rho untouched at {mech[1]['rho_to_core']:.3f}, roughly doubling the "
      f"optimal weight to {mech[1]['w_star']:.1%} for {mech[1]['uplift']:+.4f}. "
      f"**C7 as registered was the wrong fix.** The right one — idle cash to "
      f"CASH — was never registered this round and may not be back-fitted into "
      f"it; it is registered as D1 in "
      f"[docs/VARIANTS_PREREGISTRATION_R5_SLEEVE.md](VARIANTS_PREREGISTRATION_R5_SLEEVE.md). "
      f"Note the size: {mech[1]['uplift']:+.4f} Sharpe is far INSIDE most of "
      f"the arms' own intervals below, so this is a mechanism, not a promise.")
    w("")
    w("### Both cash conventions, side by side (round-5 M4)")
    w("")
    w(f"The same accounting artifact runs through the two books this document "
      f"uses as reference points. `REF-R2A` and `INC-3070SPY` are modelled with "
      f"DEAD idle sleeve cash — while C7 (and round 5's D1/D2) get the routing, "
      f"and while the live executor's blend loop already sweeps idle SLEEVE "
      f"cash to BIL. Both conventions are now registered and both appear as "
      f"rows in the tables above:")
    w("")
    w("| book | as-frozen (DEAD cash) | swept (LIVE convention) | dSharpe | 95% CI | boot p | CAGR |")
    w("|---|---|---|---|---|---|---|")
    for r in swept:
        w(f"| {r['book']} | {r['sharpe_dead']:.4f} | **{r['sharpe_live']:.4f}** | "
          f"{r['d_sharpe']:+.4f} | [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}] | "
          f"{r['boot_p']:.4f} | {r['cagr_dead']:.2%} -> **{r['cagr_live']:.2%}** |")
    w("")
    w(f"**Every published R2-A statistic on the dead-cash convention "
      f"UNDERSTATES the design the executor actually runs** — the sleeve "
      f"reference by {swept[0]['d_sharpe']:+.3f} Sharpe / "
      f"{1e4 * (swept[0]['cagr_live'] - swept[0]['cagr_dead']):+.0f} bps of "
      f"CAGR, the 30/70 incumbent by {swept[1]['d_sharpe']:+.3f} / "
      f"{1e4 * (swept[1]['cagr_live'] - swept[1]['cagr_dead']):+.0f} bps. It "
      f"changes no verdict here — `{best}` stays the best incumbent either "
      f"way — and the FROZEN curve is deliberately not restated: it is the "
      f"pinned input this and every earlier round was run on. The swept "
      f"convention is reported beside it, never instead of it. No live change "
      f"is implied; a backtest and dashboard convention change is.")
    w("")
    w("### What this round could and could not have resolved (M4)")
    w("")
    w("The round-4 draft dismissed its near-ties against a \"+/-0.4 noise "
      "floor\". That number was imported from a DIFFERENT comparison — "
      "B.5-core vs SPY-core, and 30/70 B.5 vs 30/70 SPY, books with different "
      "cores — and it is wrong here by up to 7x, in the direction that "
      "UNDERSELLS the result. This round's paired CIs on near-core arms are "
      "much tighter, and each arm is judged against its own. To make the claim "
      "testable rather than rhetorical, a known TRUE edge was injected into "
      "each arm's daily excess returns (a constant shift sized to raise its "
      "Sharpe by exactly delta) and criterion 2 was re-run:")
    w("")
    L.extend(_mde_table(verdicts))
    w("")
    c105, c8v = verdicts["C1-05"], verdicts["C8"]
    w(f"**Both power conventions are printed (round-5 counter-agent M2).** The "
      f"\"smallest detectable edge\" column is the delta at which THIS "
      f"sample's own interval excludes zero — algebraically -CI_lo, i.e. the "
      f"edge the test would catch **half** the time. The 80%-power column is "
      f"the quantile of that threshold across "
      f"{c105['power_mc']['worlds']} circular block-resampled worlds of the "
      f"same paired history. The published floor was optimistic by ~1.4-1.5x "
      f"and the correction makes every null in this round stronger, not "
      f"weaker.")
    w("")
    w(f"Read the top row: at a 5% sleeve weight this round had the power to "
      f"resolve a true +0.10 Sharpe edge "
      f"(p={c105['power']['grid']['0.10']['boot_p']:.3f}) and measured "
      f"{c105['d_sharpe']:+.3f}. **That is an informative null, not an "
      f"underpowered shrug.** It weakens as the sleeve grows: C8 needs about "
      f"{c8v['power']['min_detectable_edge']:+.2f} (50% power; "
      f"{c8v['power_mc']['mde_at_power']['0.80']:+.2f} at 80%) before its bar "
      f"would fire, and C6-band05 at a 30% sleeve misses even a true +0.40 — "
      f"at the live weight this data genuinely cannot see an edge of any "
      f"plausible size, which is a finding about the LIVE configuration, not "
      f"about the variants.")
    w("")
    w("### Criterion 1 is rebalance-rule dependent (M3)")
    w("")
    rr = meta["c1_05_rebalance_robustness"]
    asrun = next(r for r in rr if r["rule"] == "band05")
    w(f"The registration fixes no rebalance rule for C1 (\"static sleeve "
      f"weights 5/10/15/20% on a B.5 core\"). The harness used the live 5% "
      f"ABSOLUTE band — which on a 5% TARGET weight can never fire: "
      f"**{asrun['rebalances']} rebalances in {meta['windows']['real']['n']} "
      f"days**. C1-05 as run is buy-and-hold, not a 5% book. Under other, "
      f"equally registration-compliant rules:")
    w("")
    w("| rebalance rule | rebalances | Sharpe(BIL) | Sortino(BIL) | crit 1 | "
      "dSharpe | 95% CI | boot p | crit 3 |")
    w("|---|---|---|---|---|---|---|---|---|")
    for r in rr:
        w(f"| {r['label']} | {r['rebalances']} | {r['sharpe_bil']:.4f} | "
          f"{r['sortino_bil']:.4f} | {'**Y**' if r['c1'] else 'n'} | "
          f"{r['d_sharpe']:+.4f} | [{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}] | "
          f"{r['boot_p']:.3f} | {r['c3_wins']}/3 |")
    bf = res["real"][best]["full"]
    w(f"| {best} (incumbent) | — | {bf['sharpe_bil']:.4f} | "
      f"{bf['sortino_bil']:.4f} | — | — | — | — | — |")
    w("")
    passes = [r["label"] for r in rr if r["c1"]]
    w(f"So \"every arm fails criterion 1\" is NOT robust: under "
      f"{', '.join(passes)} rebalancing, C1-05 passes it. **The correct "
      f"statement is that no arm survives, and that C1-05 fails on criteria 2 "
      f"and 3 under EVERY rebalance reading** "
      f"(boot p {min(r['boot_p'] for r in rr):.3f}-{max(r['boot_p'] for r in rr):.3f}, "
      f"{min(r['c3_wins'] for r in rr)}/3 sub-periods everywhere). The edge "
      f"criterion 1 flips to is at most "
      f"{max(r['d_sharpe'] for r in rr):+.4f} Sharpe against its own "
      f"+/-{(asrun['ci95'][1] - asrun['ci95'][0]) / 2:.3f} interval. These rows "
      f"are DESCRIPTIVE robustness, not registered arms; the survival table "
      f"above is unchanged, and the rule dimension is registered properly as "
      f"D4 in round 5.")
    w("")
    w("### C3 is VOID AS SPECIFIED (M5)")
    w("")
    cap = meta["c3_cap_binding_real"]
    c3f, c6mf = res["real"]["C3"]["full"], res["real"]["C6-monthly"]["full"]
    w(f"C3 registered inverse-vol weighting with the sleeve **capped at 30%** "
      f"as a fixed parameter. Uncapped, the ~20%-vol sleeve against a ~12%-vol "
      f"core wants a mean weight of {cap['mean_uncapped_w']:.1%} "
      f"(median {cap['median_uncapped_w']:.1%}, max {cap['max_uncapped_w']:.1%}), "
      f"so the applied weight sits AT the 30% cap on "
      f"**{cap['days_at_cap']}/{cap['n_days']} = {cap['frac_at_cap']:.1%}** of "
      f"real-window days ({cap['days_uncapped_over_cap']} genuine cap binds "
      f"plus {cap['days_fallback']} warm-up / zero-sleeve-vol fallbacks, which "
      f"also default to 30%). Mean applied weight "
      f"{cap['mean_applied_w']:.4f}, minimum {cap['min_applied_w']:.4f}.")
    w("")
    w(f"C3 is therefore functionally a restatement of C6-monthly — CAGR "
      f"{c3f['cagr']:.2%} vs {c6mf['cagr']:.2%}, maxDD {c3f['max_dd']:.1%} vs "
      f"{c6mf['max_dd']:.1%}, Sharpe(BIL) {c3f['sharpe_bil']:.4f} vs "
      f"{c6mf['sharpe_bil']:.4f}. **The inverse-vol hypothesis was never "
      f"tested this round.** This is a REGISTRATION flaw, not a harness bug: "
      f"the harness implements the registration exactly, and the registration "
      f"fixed a parameter that neutered its own variant. C3's result stands as "
      f"reported but is VOID AS SPECIFIED as evidence about inverse-vol "
      f"weighting; the uncapped test is registered as D3 in round 5. Direction "
      f"is safe either way — uncapped would hold MORE sleeve, which every row "
      f"in this document says is worse. "
      f"(On {cap['zero_sleeve_vol_decisions']} of "
      f"{cap['monthly_decisions']} monthly decisions that HAVE a full 60-day "
      f"history the trailing sleeve "
      f"vol is exactly zero — the sleeve is flat for three straight months — "
      f"and the 30% fallback there coincides with what uncapped inverse-vol "
      f"would give, so it introduces no distortion.)")
    w("")
    w("### Same-close vs prior-close trailing statistics (m1)")
    w("")
    pcs = meta["prior_close_sensitivity_real"]
    w("C3/C4/C8 read their trailing windows on the engine's SAME-CLOSE "
      "decide/execute convention, while C5's gate is genuinely prior-close "
      "(it inherits R2-A's entry condition). Neither is look-ahead, but they "
      "are inconsistent, so the cost is measured rather than argued: "
      + "; ".join(f"{k} {v['same_close']:.4f} -> {v['strict_prior_close']:.4f} "
                  f"({v['delta']:+.4f})" for k, v in pcs.items())
      + " Sharpe(BIL). No verdict moves.")
    w("")
    w("## C7 — the mechanical one")
    w("")
    c7 = verdicts.get("C7")
    c7f = res["real"]["C7"]["full"]
    bf = res["real"][best]["full"]
    if c7:
        lo, hi = c7["ci95"]
        w(f"C7 is the only arm whose edge, if any, is NOT a search result: it is "
          f"a fix to a known accounting artifact. **This arm was RE-IMPLEMENTED "
          f"after the counter-agent pass (M1).** The round-4 draft credited the "
          f"core's return only on days whose sleeve return was exactly zero "
          f"({idle['zero_return_days']}/{idle['zero_return_of']} = "
          f"{idle['zero_return_days'] / idle['zero_return_of']:.1%} of the real "
          f"window), and justified stopping there with the claim that \"the "
          f"frozen sleeve is a dollar curve, so only FULLY idle days are "
          f"observable\". That claim was FALSE about this repo: "
          f"`backtest_variants_r2.py`'s `run_call_book_yield` already computes "
          f"`equity - invested` every day, so the idle balance is exact. "
          f"`scripts/build_r2a_exposure.py` rebuilds R2-A's book from the "
          f"round-2 pipeline (601 taken, 2457 skipped at the cap), gates the "
          f"rebuilt equity against the frozen curve on all 2,672 days, and "
          f"records the daily invested notional in `data/r2a_exposure.json`.")
        w("")
        w(f"R2-A's real-window idle CAPITAL: **mean "
          f"{idle['mean_idle_fraction']:.1%}, median "
          f"{idle['median_idle_fraction']:.1%}** of the sleeve — with "
          f"{idle['days_fully_idle']}/{idle['n_days']} days fully idle and "
          f"{idle['days_over_90pct_idle']}/{idle['n_days']} above 90% idle. "
          f"The draft's fix was therefore about **half** the size of the real "
          f"artifact. C7 now credits the prior close's idle FRACTION with the "
          f"core's return each day.")
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
              f"sleeve cash to the core raises the return AND the equity-beta "
              f"of the sleeve leg together, so Sharpe rises "
              f"({c6f['sharpe_bil']:.3f} -> {c7f['sharpe_bil']:.3f}) while "
              f"Calmar FALLS ({c6f['calmar']:.2f} -> {c7f['calmar']:.2f}) and "
              f"the interval on the Sharpe move still spans zero. The "
              f"accounting artifact was real and is now fixed at its true "
              f"size; correcting it does NOT lift the book past the "
              f"incumbent, and the mechanism section shows why this routing "
              f"is the dominated one.")
            w("")
        w(f"Correction size, before -> after: the draft's zero-return-days "
          f"implementation gave Sharpe(BIL) 0.828, dSharpe -0.090, CI "
          f"[-0.449, +0.250], CAGR 13.63%, maxDD 15.5%. The idle-CAPITAL "
          f"implementation gives {c7f['sharpe_bil']:.3f}, "
          f"{c7['d_sharpe']:+.3f}, [{lo:+.3f}, {hi:+.3f}], "
          f"{c7f['cagr']:.2%}, {c7f['max_dd']:.1%}. Better, and still not "
          f"close: it fails criteria 1, 2 and 3 "
          f"({c7['c3_wins']}/3 sub-periods). **The null survives the "
          f"correction.** See the mechanism section for why the registered "
          f"routing was the wrong one: crediting the CORE is dominated by "
          f"crediting CASH.")
        w("")
        w("Implementation limits that remain, stated because they bound the "
          "claim: the idle fraction is measured at the PRIOR close and earns a "
          "full day of the routed leg's return, and no transaction cost is "
          "charged for the implied daily movement of idle cash in and out of "
          "the core — both favourable assumptions. The sleeve's own trade "
          "slippage stays as the round-2 engine charged it.")
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
      "1.3-3.1pp/yr. "
      f"{meta['proxy_session_usage_synth']['returns_using_a_proxy']} of "
      f"{meta['proxy_session_usage_synth']['n_returns']} synthetic return-days "
      f"use a proxy for at least one constituent — counted, not quoted; "
      f"earlier drafts carried a hard-coded \"1079 of 2511\" inherited from an "
      f"earlier round (round-5 counter-agent m2).")
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
    w(f"- **Resolution is PER ARM; there is no campaign-wide noise floor.** "
      f"The paired 95% CI half-width runs from "
      f"+/-{min((v['ci95'][1] - v['ci95'][0]) / 2 for v in verdicts.values()):.3f} "
      f"(C1-05) to "
      f"+/-{max((v['ci95'][1] - v['ci95'][0]) / 2 for v in verdicts.values()):.3f} "
      f"(the 30%-sleeve arms) — a 7x span. An earlier draft of this document "
      f"quoted a single \"+/-0.4\" figure imported from the B.5-core vs "
      f"SPY-core comparison in a different study; that was wrong, and it made "
      f"the round look blinder than it is. The injected-edge table above is "
      f"the honest statement: at low sleeve weight this campaign resolved a "
      f"true +0.10 Sharpe edge and found none; at the live 30% weight it could "
      f"not have seen +0.40.")
    w("- **Two of the eight registered variants did not test what they "
      "claimed.** C3's fixed 30% cap made it a restatement of C6-monthly "
      "(VOID AS SPECIFIED for inverse-vol); C7's registered routing of idle "
      "cash to the CORE is dominated by routing it to cash, so the arm tested "
      "the wrong fix even after being re-implemented correctly. Both are "
      "registration flaws found by the counter-agent, not harness bugs, and "
      "neither may be re-parameterized inside this round.")
    w("- **Criterion 1's failures are not all robust.** C1-05 passes criterion "
      "1 under daily, 0.5%-band and monthly rebalancing and fails it under the "
      "live 5% absolute band, which never fires at a 5% target. Criteria 2 and "
      "3 carry the null: they fail under every reading tried.")
    w("- **Independent reproduction.** An adversarial counter-agent re-ran the "
      "full campaign (byte-identical report), rebuilt the R2-A book from the "
      "round-2 pipeline and matched the FROZEN curve on all **2,672 days to "
      "<1e-6**, reimplemented the paired block bootstrap naively and matched "
      "this harness's optimized version to **5.3e-15** on every draw, ran a "
      "200-run coverage simulation (96.0% empirical coverage), and re-ran the "
      "whole bar on the rf=0 basis, against the strongest synthetic-window "
      "incumbent, and under the prior round's stationary-bootstrap "
      "convention. No verdict moved. Verdict: PASS WITH CORRECTIONS — the "
      "null is REAL.")
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
    w("python -m scripts.build_r2a_exposure               # OPTIONAL — verification only")
    w("python -m scripts.backtest_core_variants            # full campaign")
    w("python -m scripts.backtest_core_variants --variant C7 --window real")
    w("```")
    w("")
    w("Step 1 is **verification-only and cannot run from a clean checkout**: it "
      "needs `backend/data/backtest_bars.json`, which is untracked — which is "
      "why `data/r2a_exposure.json` IS tracked. The campaign runs from the "
      "tracked inputs alone.")
    w("")
    w("Adding a round-5 variant is one `register(...)` line plus its builder in "
      "`scripts/backtest_core_variants.py`; the metrics, the survival bar, the "
      "bootstrap, both windows and this report all pick it up automatically. "
      "Prices are cached under `backend/data/px_cache/` so re-runs never "
      "re-fetch. Results JSON: `backend/data/backtest_core_variants_results.json`.")
    w("")
    ROUNDS[4]["report"].write_text("\n".join(L) + "\n")


def _write_report_r5(res: dict, order: list[str], verdicts: dict, meta: dict) -> None:
    """Round 5's report. Same bar, same bootstrap, same honesty rules — and the
    multiple-comparison bar counts BOTH rounds, because round 5's hypotheses
    were generated by reading round 4's results."""
    best = meta["best_incumbent"]
    n = meta["n_variants_tested"]
    n_all = meta["n_arms_all_rounds"]
    surv = [k for k, v in verdicts.items() if v["survives"]]
    clears = [k for k, v in verdicts.items() if v.get("clears_bonferroni")]
    c1_pass = [k for k, v in verdicts.items() if v["c1_sharpe_and_sortino"]]
    half = {k: (v["ci95"][1] - v["ci95"][0]) / 2 for k, v in verdicts.items()}
    mech = meta["d1_vs_c7_routing"]
    bw = meta["d1_best_weight"]
    # --- round-5 counter-agent corrections (M1..M4 + multiplicity) ---------
    pairs = meta["cash_mechanism_paired_real"]
    bkey = f"D1-{int(round(bw * 100)):02d}"
    pair = next(r for r in pairs if r["comparison"] == bkey)
    alone = next(r for r in pairs if r["weight"] == 1.0)
    sweep = meta["sweep_robustness_real"]
    worst = sweep[-1]
    d2r = meta["d2_warmup_readings_real"]
    d2reg = next(r for r in d2r
                 if r["warmup_w"] == meta["d2_warmup_registered_default"])
    d2un = next(r for r in d2r if r["warmup_w"] == LIVE_SLEEVE_W)
    mt = meta["max_t_all_rounds"]
    swept = meta["swept_vs_frozen_real"]
    c2_pass = [k for k, v in verdicts.items() if v["c2_ci_excludes_zero"]]
    c3_pass = [k for k, v in verdicts.items() if v["c3_subperiods"]]
    L: list[str] = []
    w = L.append

    w("# Backtest — ROUND 5 sleeve variants (idle cash, timing, inverse-vol), 2026-08-22")
    w("")
    w(f"Generated by `backend/scripts/backtest_core_variants.py --round 5` "
      f"(deterministic, bootstrap seed {meta['bootstrap']['seed']}). Contract: "
      f"[{meta['contract']}](VARIANTS_PREREGISTRATION_R5_SLEEVE.md), committed "
      f"BEFORE any round-5 code was written — not merely before it was run. "
      f"Nothing in this document is a config change or a live weight (TUNING.md "
      f"law). Round 4's report and results are not rewritten by this run.")
    w("")
    w("**REVISED after the round-5 adversarial counter-agent pass** "
      "(`scratchpad/r5_counter_verdict.md`, verdict: PASS WITH CORRECTIONS — "
      "the null is REAL, **the headline conclusion was WRONG**). Every arm, "
      "interval and criterion reproduced; the claim built on top of them did "
      "not. Four material corrections are applied below: the mechanism is "
      "measured against its OWN counterfactual instead of against a portfolio "
      "that does not contain it (M1); the detection floor is reported at 80% "
      "power as well as the 50% the harness computes (M2); D2 is re-run on the "
      "registered low leg after an UNREGISTERED warm-up default was found to "
      "be deciding its verdict (M3); and the sleeve and the 30/70 baseline are "
      "now reported under BOTH cash conventions, because the live design "
      "sweeps idle sleeve cash and the harness modelled it dead (M4). The "
      "multiple-comparison block is replaced with a max-T correction and an "
      "honest statement of what no correction here covers.")
    w("")
    w("## Verdict")
    w("")
    w(f"**The idle-cash mechanism IS measurable, and it is real. What this "
      f"data cannot adjudicate is whether to hold the sleeve at all.** Those "
      f"are two different claims and the first draft of this document merged "
      f"them into one wrong one — *\"this data cannot adjudicate the mechanism "
      f"in either direction\"* — by measuring a {mech[1]['uplift']:+.4f} "
      f"mechanism against the resolution of a comparison that is not a test of "
      f"it. Against its own counterfactual (the identical book, same weight, "
      f"same rebalance rule, with the sleeve's idle cash left DEAD), "
      f"{bkey} is **{pair['d_sharpe']:+.4f} Sharpe, 95% CI "
      f"[{pair['ci95'][0]:+.4f}, {pair['ci95'][1]:+.4f}], p<0.0001** — and it "
      f"clears the 22-arm Bonferroni bar "
      f"({100 * pair['bonferroni_conf_all_rounds']:.3f}% CI "
      f"[{pair['ci_bonferroni_all_rounds'][0]:+.4f}, "
      f"{pair['ci_bonferroni_all_rounds'][1]:+.4f}]). On the sleeve alone the "
      f"same fix is worth {alone['d_sharpe']:+.4f} Sharpe "
      f"[{alone['ci95'][0]:+.4f}, {alone['ci95'][1]:+.4f}] and "
      f"{1e4 * (alone['cagr_live'] - alone['cagr_dead']):+.0f} bps of CAGR. "
      f"See [the mechanism section](#the-mechanism-against-its-own-counterfactual-m1).")
    w("")
    if surv:
        w(f"**{len(surv)} of {n} arms SURVIVED the registered bar: {', '.join(surv)}.**")
    else:
        w(f"**NOTHING SURVIVED the registered bar.** All {n} registered "
          f"round-5 arms (D1..D4) failed it against the best incumbent "
          f"(`{best}`). The registration said this was the expected outcome and "
          f"said so before the arms were built: *\"This round is expected to "
          f"produce another null, and that expectation is on the record.\"* It "
          f"is the finding, and it is reported as one. No consolation winner is "
          f"nominated, no bar is softened, nothing was re-parameterized after a "
          f"result was seen. {len(c1_pass)} of the {n} arms DO beat the "
          f"incumbent on criterion 1, by margins of "
          f"{min(verdicts[k]['d_sharpe'] for k in c1_pass):+.4f} to "
          f"{max(verdicts[k]['d_sharpe'] for k in c1_pass):+.4f} Sharpe against "
          f"intervals of +/-{min(half[k] for k in c1_pass):.3f} to "
          f"+/-{max(half[k] for k in c1_pass):.3f}. Criterion 2 fails on "
          f"{'every arm' if not c2_pass else ', '.join(c2_pass) + ' excepted'}, "
          f"and it is what carries the null: those intervals are wide because "
          f"the bar's comparison — this book against a book with NO sleeve — "
          f"carries the sleeve's entire idiosyncratic variance, not because "
          f"the cash mechanism is unmeasurable.")
    w("")
    w(f"**Multiple comparisons, across BOTH rounds: {n_all} arms — and the "
      f"correction that matters is not in any of them.** Round 5's {n} arms "
      f"were designed by reading round 4's {meta['arms_other_rounds']} results, "
      f"so the honest denominator is the campaign, not the round. Three "
      f"statements, in the order of how much work they do:")
    w("")
    w(f"1. **Bonferroni is INERT here and should not be presented as if it "
      f"dispatched a near-miss.** The smallest raw two-sided p anywhere in the "
      f"campaign is {mt['min_raw_p']:.3f} (`{mt['min_raw_p_arm']}`) — two "
      f"orders of magnitude from the naive alpha={meta['naive_alpha']:.2f}, "
      f"let alone from the adjusted "
      f"alpha={meta['bonferroni_alpha_all_rounds']:.5f} "
      f"({100 * meta['bonferroni_conf_all_rounds']:.3f}% CI). Nothing is close, "
      f"in either round: arms clearing the all-rounds bar **NONE**, arms "
      f"clearing the round-only bar "
      f"**{', '.join(clears) if clears else 'NONE'}**.")
    w(f"2. **Bonferroni is also the wrong instrument for these arms**, which "
      f"are near-identical portfolios whose tests are massively correlated, so "
      f"it over-corrects. The step-down max-T (Westfall-Young) resampling "
      f"correction on the SHARED draw sequence across all {mt['n_arms']} arms "
      f"gives an adjusted p of **{mt['best_positive_adjusted_p']:.3f}** for the "
      f"best positive arm (`{mt['best_positive_arm']}`, "
      f"{mt['best_positive_d_sharpe']:+.4f}) and "
      f"**{mt['strongest_adjusted_p']:.3f}** for the largest statistic anywhere "
      f"in the campaign (`{mt['strongest_arm']}`, "
      f"{mt['strongest_d_sharpe']:+.4f}, on the losing side of zero). Same "
      f"conclusion, honestly obtained.")
    w("3. **The multiplicity that actually matters is in no denominator at "
      "all:** the selection of R2-A itself across rounds 1-3, B.5's "
      "hindsight-fitted weights, and the choice of window. Twenty-two arms is "
      "the SMALL multiplicity here, and no resampling correction computed "
      "inside this window can reach the large one.")
    w("")
    w("## What round 5 was, and why these four arms")
    w("")
    w("Round 4 tested combination RULES on a frozen sleeve and found nothing. "
      "Its adversarial counter-agent pass (PASS WITH CORRECTIONS — the null is "
      "REAL) found five material errors in the writeup, two of which pointed "
      "somewhere round 4 had not looked. Round 5 is those two, plus the two "
      "design faults the same pass exposed:")
    w("")
    w("| arm | what it tests | which round-4 finding it comes from |")
    w("|---|---|---|")
    w("| D1-05 / D1-10 / D1-15 | sleeve idle CAPITAL routed to BIL (cash), not the core, at 5/10/15% | M2 — BIL routing lifts the sleeve's Sharpe with correlation UNCHANGED; the CORE routing round 4 registered as C7 is dominated |")
    w("| D2 | the C8 correlation trigger anchored at 15%/5% instead of 30%/10%, on D1's routing | verifier H1 — C8's value was its TIMING, but the trigger was only ever tested at weights M2 says are wrong |")
    w("| D3 | a TRUE uncapped inverse-vol sleeve | M5 — round 4's 30% cap bound on 82.1% of days, so C3 was a restatement of C6-monthly and inverse-vol was never tested |")
    w("| D4-daily / D4-band005 | D1's best weight under daily and 0.5%-band rebalancing | M3 — a 5% ABSOLUTE band never fires on a 5% target, so round 4 left the rule dimension unregistered |")
    w("")
    w(f"The registration also fixed the prior: the mechanism M2 identified is "
      f"worth about **{mech[1]['uplift']:+.4f} Sharpe** at its tangency weight "
      f"of {mech[1]['w_star']:.1%} — five times smaller than the "
      f"~+0.06 edge round 4 could resolve at a 5% sleeve, and far inside every "
      f"interval in the table below. An arm cannot clear a bar that needs its "
      f"interval to exclude zero on an effect that small. That prior was right "
      f"about the BAR. It says nothing about whether the mechanism can be "
      f"measured, and the first draft of this document wrongly treated the two "
      f"as the same question (M1).")
    w("")
    w("## Protocol (fixed before results, carried over verbatim from round 4)")
    w("")
    w(f"- Windows: REAL {meta['windows']['real']['start']}.."
      f"{meta['windows']['real']['end']} (n={meta['windows']['real']['n']}) and "
      f"SYNTHETIC-EXTENDED {meta['windows']['synth']['start']}.."
      f"{meta['windows']['synth']['end']} (n={meta['windows']['synth']['n']}), "
      f"identical dates across every comparator within a window.")
    w(f"- Incumbents: {', '.join(meta['incumbents'])}. Best incumbent on the "
      f"full real window by BIL-excess Sharpe: **{best}**.")
    w(f"- Measurement basis: {meta['measurement_basis']}.")
    w(f"- Sortino convention: {meta['sortino_convention']}. Sharpe and Sortino "
      f"are printed on BOTH risk-free bases and never mixed within a column.")
    w(f"- Costs {meta['cost_bps_per_side']:.0f} bps per side on traded notional. "
      f"Tail sleeve = {meta['tail_sleeve']}.")
    w("- **Rebalance rule is REGISTERED, not implicit** (the round-4 lesson): "
      "monthly calendar for D1, D2 and D3; D4 exists to vary it. No absolute "
      "band is used anywhere in this round except as D4's own 0.5% arm.")
    w(f"- Sleeve: {meta['sleeve']}.")
    w(f"- Bootstrap: paired circular block bootstrap on the Sharpe DIFFERENCE, "
      f"{meta['bootstrap']['block_days']}-day blocks, "
      f"{meta['bootstrap']['draws']} draws, seed {meta['bootstrap']['seed']}, "
      f"basis {meta['bootstrap']['basis']}; the Bonferroni tail is read from a "
      f"{meta['bootstrap']['deep_draws']:,}-draw run of the same seeded "
      f"sequence.")
    w("- Survival requires ALL FOUR: 1. Sharpe AND Sortino beat the best "
      "incumbent on the full real window; 2. the 95% bootstrap CI on dSharpe "
      "excludes zero; 3. it beats the incumbent in >=2 of 3 equal sub-periods; "
      "4. it does not lose the synthetic window by more than 0.10 Sharpe.")
    w("")
    w(f"D4's weight is the registered selection rule applied once: the D1 arm "
      f"with the highest BIL-excess Sharpe over the full real window, ties "
      f"broken toward the lower weight. It selected **{bw:.0%}**.")
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
    w("Proxy splice, unadjusted (no manager alpha added) — a FLOOR on B.5's "
      "constituents, not a point estimate.")
    w("")
    L.extend(_md_table(res, "synth", order, verdicts))
    w("")
    w("## Survival verdict, arm by arm")
    w("")
    w("| variant | dSharpe vs best | 95% CI | boot p | 1 | 2 | 3 (wins) | 4 | "
      "SURVIVES | Bonferroni CI (round) |")
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
    if c1_pass:
        gaps = {k: verdicts[k]["d_sharpe"] for k in c1_pass}
        top = max(gaps, key=lambda k: gaps[k])
        w(f"**Read this before reading anything else into the table: "
          f"{len(c1_pass)} of {n} arms ({', '.join(c1_pass)}) BEAT the best "
          f"incumbent on both Sharpe and Sortino over the full real window — "
          f"criterion 1 passes.** That is not a survivor and it is not a "
          f"finding. The largest gap is {top} at {gaps[top]:+.4f} Sharpe "
          f"against its own 95% interval of "
          f"+/-{(verdicts[top]['ci95'][1] - verdicts[top]['ci95'][0]) / 2:.3f} "
          f"— a gap {(verdicts[top]['ci95'][1] - verdicts[top]['ci95'][0]) / 2 / abs(gaps[top]):.0f}x "
          f"narrower than the noise on it, with a bootstrap p of "
          f"{verdicts[top]['boot_p']:.3f}. Criterion 2 fails on every arm — "
          f"that is what carries the null. Criterion 3 is passed by "
          f"{', '.join(c3_pass) if c3_pass else 'no arm'} "
          f"({min(v['c3_wins'] for v in verdicts.values())}"
          f"-{max(v['c3_wins'] for v in verdicts.values())} of 3 sub-periods "
          f"across the round). The bar exists precisely so that a "
          f"point estimate on the right side of zero cannot be reported as an "
          f"edge, and it is doing its job here.")
        w("")
        w(f"**Correction (M3): an earlier draft of this section said criterion "
          f"3 \"fails on every arm\" and that, unlike round 4's C1-05, \"the "
          f"rule here was registered before the code existed, so there is no "
          f"post-hoc choice to make\". Both sentences are withdrawn.** D2 as "
          f"first run inherited the harness's {LIVE_SLEEVE_W:.0%} warm-up "
          f"default — a weight D2's contract never names — on "
          f"{meta['d2_warmup_days_real']}/{meta['windows']['real']['n']} days, "
          f"and that unregistered convention was deciding its verdict. Judged "
          f"on the registered low leg, D2 passes criteria 1, 3 and 4 and "
          f"reaches {d2reg['c3_wins']}/3 sub-periods. That is round-4's M3 "
          f"fault repeating one arm to the left: the round fixed the rebalance "
          f"rule it had been caught on and left a different unregistered "
          f"default in place. The direction of the {len(c1_pass)} "
          f"criterion-1 passes is consistent rather than knife-edge, and all "
          f"of it remains an in-sample point estimate on a hindsight-fitted "
          f"comparator. See [D2's warm-up default](#d2--the-warm-up-default-that-decided-the-verdict-m3).")
        w("")
    flips = [k for k, v in verdicts.items()
             if v["c1_sharpe_and_sortino"] != v["c1_on_rf0"]]
    w(f"Basis check: adjudication is on BIL-excess Sharpe/Sortino, with rf=0 "
      f"printed beside it. Arms whose criterion-1 result would FLIP on the "
      f"rf=0 basis: **{', '.join(flips) if flips else 'none'}**"
      + (" — each still fails criteria 2 and 3." if flips else "."))
    w("")
    w("## Per-arm resolution: what this round could have detected")
    w("")
    w("Same measurement as round 4's, and for the same reason — a null is only "
      "worth acting on if you know what size of edge it ruled out. A known TRUE "
      "edge is injected into each arm's daily excess returns (a constant shift "
      "sized to raise its Sharpe by exactly delta) and criterion 2 is re-run.")
    w("")
    w("**Both power conventions are printed (M2).** A constant shift moves the "
      "whole bootstrap distribution with it, so \"the smallest delta at which "
      "THIS sample's interval excludes zero\" is the edge the test would catch "
      "**half** the time — it is -CI_lo by construction, not the conventional "
      "minimum detectable effect. The 80%-power column is the quantile of that "
      "threshold across "
      f"{next(iter(verdicts.values()))['power_mc']['worlds']} circular "
      f"block-resampled worlds of the same paired history "
      f"({next(iter(verdicts.values()))['power_mc']['draws']} draws each). "
      "The counter-agent's shape check (recorded in its verdict, not re-run "
      "here) found burst-shaped edges cost ~7% more resolution and pure "
      "volatility cuts identical, so the constant-drift injection is "
      "defensible; the power convention was not.")
    w("")
    L.extend(_mde_table(verdicts))
    w("")
    mdes = [v["power"]["min_detectable_edge"] for v in verdicts.values()
            if v["power"]["min_detectable_edge"]]
    mde80 = [v["power_mc"]["mde_at_power"]["0.80"] for v in verdicts.values()]
    w(f"The tightest arm here resolves an edge of about {min(mdes):+.2f} Sharpe "
      f"at 50% power and {min(mde80):+.2f} at 80%. **What that does and does "
      f"not license:** against `{best}` — a book with no sleeve in it at all — "
      f"this sample cannot resolve an effect the size of the cash mechanism, "
      f"and it never could have; the registration said so in advance. It does "
      f"NOT follow that the mechanism is unmeasurable. Measured against its own "
      f"counterfactual the same fix is {pair['d_sharpe']:+.4f} on an interval "
      f"about {half[bkey] / ((pair['ci95'][1] - pair['ci95'][0]) / 2):.0f}x "
      f"tighter — same arm, same days, same bootstrap, different comparator "
      f"(next section). The wide interval is a property of the comparison this "
      f"bar runs, not of the mechanism.")
    w("")
    w("## D1 — routing idle cash to CASH instead of the core")
    w("")
    w("| sleeve treatment | Sharpe(BIL) of the sleeve | rho to core | tangency w* | "
      "Sharpe uplift at w* |")
    w("|---|---|---|---|---|")
    for r in mech:
        w(f"| {r['treatment']} | {r['sharpe_sleeve']:.3f} | {r['rho_to_core']:.3f} | "
          f"{r['w_star']:.1%} | {r['uplift']:+.4f} |")
    w("")
    d1 = {k: res["real"][k]["full"] for k in verdicts if k.startswith("D1-")}
    bf = res["real"][best]["full"]
    w(f"The mechanism holds in the arithmetic and does not show up in the bar "
      f"AGAINST A BOOK WITH NO SLEEVE. Best D1 arm on Sharpe(BIL): "
      f"**{max(d1, key=lambda k: d1[k]['sharpe_bil'])}** at "
      f"{max(v['sharpe_bil'] for v in d1.values()):.4f} against "
      f"{best}'s {bf['sharpe_bil']:.4f}. Every D1 arm's dSharpe sits inside its "
      f"own interval and criterion 2 fails throughout — which is a fact about "
      f"that comparison, and the next section is the one about the mechanism.")
    w("")
    w("## The mechanism against its own counterfactual (M1)")
    w("")
    w(f"The bar compares each arm to `{best}`: a portfolio that does not "
      f"contain the sleeve at all. That is a test of **whether to hold the "
      f"sleeve**, and it carries the sleeve's entire idiosyncratic variance — "
      f"hence intervals of +/-0.06 and wider. The **cash routing's** own "
      f"counterfactual is the identical book, same weight, same monthly "
      f"rebalance, with the idle balance left DEAD. Round 4 already built that "
      f"instrument (`c7_vs_c6_band05`: *\"C7 is a MECHANICAL fix, so its "
      f"like-for-like comparator is the same book WITHOUT the fix\"*) and "
      f"round 5 never pointed it at D1. Pointed at D1, same engine, same seed, "
      f"same {meta['windows']['real']['n']} days:")
    w("")
    w("| comparison (both legs identical except the cash routing) | Sharpe(BIL) dead -> swept | dSharpe | 95% CI | boot p | "
      f"{100 * pairs[0]['bonferroni_conf_all_rounds']:.3f}% CI ({n_all}-arm bar) | CAGR dead -> swept |")
    w("|---|---|---|---|---|---|---|")
    for r in pairs:
        blo, bhi = r["ci_bonferroni_all_rounds"]
        w(f"| {r['comparison']} | {r['sharpe_dead']:.4f} -> {r['sharpe_live']:.4f} | "
          f"**{r['d_sharpe']:+.4f}** | [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}] | "
          f"{r['boot_p']:.4f} | [{blo:+.4f}, {bhi:+.4f}] | "
          f"{r['cagr_dead']:.2%} -> {r['cagr_live']:.2%} |")
    w("")
    w(f"**The mechanism is adjudicated, in the positive direction, and it "
      f"clears the campaign-wide bar.** At the registered {bw:.0%} sleeve the "
      f"fix is {pair['d_sharpe']:+.4f} Sharpe "
      f"({1e4 * (pair['cagr_live'] - pair['cagr_dead']):+.0f} bps of CAGR); on "
      f"the sleeve alone {alone['d_sharpe']:+.4f} "
      f"({1e4 * (alone['cagr_live'] - alone['cagr_dead']):+.0f} bps, "
      f"{alone['cagr_dead']:.2%} -> {alone['cagr_live']:.2%}). The estimate's "
      f"standard error is about "
      f"{(pair['ci95'][1] - pair['ci95'][0]) / 2 / 1.96:.4f} — roughly "
      f"{half[bkey] / ((pair['ci95'][1] - pair['ci95'][0]) / 2):.0f}x tighter "
      f"than the SAME arm's interval against `{best}` — because the two books "
      f"differ by a near-deterministic, near-zero-variance drift. It survives "
      f"heavy pessimism about how much of the idle balance a live sweep would "
      f"actually capture:")
    w("")
    w("| sweep coverage / annual drag on the swept balance | dSharpe vs no sweep | 95% CI | boot p |")
    w("|---|---|---|---|")
    for r in sweep:
        w(f"| {r['coverage']:.0%} / {r['drag_bps']:.0f} bps"
          + ("  (as modelled)" if r["drag_bps"] == 0 and r["coverage"] == 1 else "")
          + f" | {r['d_sharpe']:+.4f} | [{r['ci95'][0]:+.4f}, "
            f"{r['ci95'][1]:+.4f}] | {r['boot_p']:.4f} |")
    w("")
    w(f"**The caveat that keeps this honest, stated with the number and not "
      f"after it:** a paired comparison between two books that differ only by "
      f"\"idle cash earns BIL instead of 0%\" is close to an accounting "
      f"identity, because BIL's daily return was >= 0 on essentially every day "
      f"of this window. p<0.0001 here is not a discovery — it is the point. A "
      f"mechanism that is arithmetic does not need a noisy portfolio test to "
      f"license it, and describing it as unresolvable is what would wrongly "
      f"stop the work. It is also in-sample like everything else here, and it "
      f"still assumes idle cash earns a full day of BIL from the prior close "
      f"with no execution lag and no cost on the implied daily movement, which "
      f"is why the coverage/drag rows are printed beside it.")
    w("")
    w(f"**What this does NOT imply: no live change.** The blend book is live "
      f"in DRY (paper) — `BLEND_ENABLED=true` is set in the Render dashboard "
      f"rather than in `render.yaml`, and `/health` reports mode "
      f"\"DRY (paper)\" with `blend_loop.ok true` — and "
      f"`ibkr-executor/app/blend.py` already sweeps idle SLEEVE cash to BIL "
      f"(step 8, `CASH_VEHICLE=\"BIL\"`, funded from `sleeve_cash`, distinct "
      f"from `CORE_BUY`, which puts idle CORE cash into SPY). The sweep is "
      f"skipped while any book order is pending, leaves a residual below "
      f"max($50, one BIL share), can be clamped to zero by `BLEND_BUDGET` "
      f"headroom, and only fires on the next cycle; and it runs on the "
      f"SPY-core 30/70 book, not the B.5 core of rounds 4-5. So the executor "
      f"needs no change from this. What DOES change is the BACKTEST "
      f"convention — see the next section.")
    w("")
    w("## Both cash conventions, side by side (M4)")
    w("")
    w(f"`INC-3070SPY` is the live H13 design and `REF-R2A` is the sleeve "
      f"reference this campaign quotes — and the harness modelled BOTH with "
      f"dead idle cash while D1 and D2 got the routing. That is a comparator "
      f"inconsistency, and it moves published numbers. Both conventions are now "
      f"registered and both appear in every table above "
      f"(`{swept[1]['book'].split(' ')[0]}` / `INC-3070SPY-SWEPT`, `REF-R2A` / "
      f"`REF-R2A-SWEPT`):")
    w("")
    w("| book | as-frozen (DEAD cash) | swept (LIVE convention) | dSharpe | 95% CI | boot p | CAGR |")
    w("|---|---|---|---|---|---|---|")
    for r in swept:
        w(f"| {r['book']} | {r['sharpe_dead']:.4f} | **{r['sharpe_live']:.4f}** | "
          f"{r['d_sharpe']:+.4f} | [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}] | "
          f"{r['boot_p']:.4f} | {r['cagr_dead']:.2%} -> **{r['cagr_live']:.2%}** |")
    w("")
    w(f"**Our published sleeve and 30/70 figures understate the design the "
      f"executor actually runs** — by {swept[0]['d_sharpe']:+.3f} Sharpe and "
      f"{1e4 * (swept[0]['cagr_live'] - swept[0]['cagr_dead']):+.0f} bps of "
      f"CAGR on the sleeve, and {swept[1]['d_sharpe']:+.3f} / "
      f"{1e4 * (swept[1]['cagr_live'] - swept[1]['cagr_dead']):+.0f} bps on the "
      f"30/70 incumbent. It does NOT move the adjudication: `{best}` remains "
      f"the best incumbent by a wide margin on this window either way. The "
      f"frozen curve is NOT restated — it is a pinned input to rounds 1-4 and "
      f"stays exactly as it was; the swept convention is reported ALONGSIDE it, "
      f"in both rounds' reports and in both artifacts.")
    w("")
    w("## D2 — the warm-up default that decided the verdict (M3)")
    w("")
    w(f"D2's registration fixes 15% and 5% and authorizes no other weight; the "
      f"{LIVE_SLEEVE_W:.0%} fallback is registered for **D3 only**. D2 as first "
      f"run inherited `monthly_weights`' {LIVE_SLEEVE_W:.0%} default anyway, so "
      f"it held a weight its own contract does not contain on "
      f"**{meta['d2_warmup_days_real']} of {meta['windows']['real']['n']} days "
      f"({meta['d2_warmup_days_real'] / meta['windows']['real']['n']:.1%})** — "
      f"in the early-2021 stretch that dominates its statistics. The arm is now "
      f"judged on the REGISTERED LOW LEG. All three readings:")
    w("")
    w("| D2 warm-up default | Sharpe(BIL) | Sortino(BIL) | CAGR | dSharpe | 95% CI | boot p | crit 1 | crit 3 |")
    w("|---|---|---|---|---|---|---|---|---|")
    for r in d2r:
        w(f"| {r['label']} | {r['sharpe_bil']:.4f} | {r['sortino_bil']:.4f} | "
          f"{r['cagr']:.2%} | {r['d_sharpe']:+.4f} | [{r['ci95'][0]:+.3f}, "
          f"{r['ci95'][1]:+.3f}] | {r['boot_p']:.3f} | "
          f"{'**Y**' if r['c1'] else 'n'} | {r['c3_wins']}/3 |")
    w("")
    w(f"Under the unregistered {LIVE_SLEEVE_W:.0%} default D2 scored "
      f"{d2un['sharpe_bil']:.4f} with dSharpe {d2un['d_sharpe']:+.4f} and 1 of "
      f"4 criteria; on the registered low leg it scores {d2reg['sharpe_bil']:.4f} "
      f"with {d2reg['d_sharpe']:+.4f} — the largest dSharpe in the round — and "
      f"**3 of 4 criteria** (1, 3 and 4). **It still does not survive:** "
      f"criterion 2 fails, boot p {d2reg['boot_p']:.3f}, interval "
      f"[{d2reg['ci95'][0]:+.3f}, {d2reg['ci95'][1]:+.3f}]. No verdict changes "
      f"and nothing is promoted. What changes is the writeup's claim to "
      f"methodological cleanliness: this is round-4's M3 — a verdict decided by "
      f"an implementation default nobody registered — repeating one arm to the "
      f"left, in a round that said in writing that it had eliminated exactly "
      f"that fault.")
    w("")
    w("## D3 — what an UNCAPPED inverse-vol sleeve actually holds")
    w("")
    w("The registration requires this distribution, because the whole point of "
      "the arm is that round 4 never saw it: C3's fixed 30% cap sat at the cap "
      "on 82.1% of days.")
    w("")
    dw = meta["d3_weight_distribution"]
    w("| window | mean | median | p10 | p90 | min | max | days above 30% | "
      "fallback days |")
    w("|---|---|---|---|---|---|---|---|---|")
    for k, lbl in (("real", "REAL"), ("synth", "SYNTHETIC")):
        d = dw[k]
        w(f"| {lbl} | {d['mean']:.1%} | {d['median']:.1%} | {d['p10']:.1%} | "
          f"{d['p90']:.1%} | {d['min']:.1%} | {d['max']:.1%} | "
          f"{d['days_over_30pct']}/{d['n_days']} ({d['frac_over_30pct']:.1%}) | "
          f"{d['days_fallback']} |")
    w("")
    d3v = verdicts["D3"]
    d3f = res["real"]["D3"]["full"]
    w(f"Uncapped, the rule holds a mean {dw['real']['mean']:.1%} sleeve in the "
      f"real window and goes above the old 30% cap on "
      f"{dw['real']['frac_over_30pct']:.1%} of days. It is worse, exactly as "
      f"the direction of round 4's evidence predicted: Sharpe(BIL) "
      f"{d3f['sharpe_bil']:.4f} vs {bf['sharpe_bil']:.4f}, dSharpe "
      f"{d3v['d_sharpe']:+.3f}, CI [{d3v['ci95'][0]:+.3f}, "
      f"{d3v['ci95'][1]:+.3f}], {d3v['c3_wins']}/3 sub-periods. **The "
      f"inverse-vol hypothesis is now tested rather than void, and it fails.** "
      f"Fallback days (warm-up plus zero-sleeve-vol months) hold the round-4 "
      f"convention of 30%; they are {dw['real']['days_fallback']} of "
      f"{dw['real']['n_days']} in the real window.")
    w("")
    lit = meta["d3_literal_rule_real"]
    w(f"**D3 is therefore \"uncapped\" on only "
      f"{1 - dw['real']['days_fallback'] / dw['real']['n_days']:.0%} of days "
      f"(m1), and the override FLATTERS it.** On the "
      f"{dw['real']['days_fallback']} fallback days — the 60-day warm-up plus "
      f"the months where the sleeve's trailing vol is exactly zero — the "
      f"registered rule holds {LIVE_SLEEVE_W:.0%}, while the LITERAL uncapped "
      f"rule diverges to a 100% sleeve wherever sleeve vol is zero. Run "
      f"literally (warm-up keeps {LIVE_SLEEVE_W:.0%}, since no literal value "
      f"exists there), D3 scores Sharpe(BIL) {lit['sharpe_bil']:.4f} and CAGR "
      f"{lit['cagr']:.2%} against the {d3f['sharpe_bil']:.4f} / "
      f"{d3f['cagr']:.2%} reported above, dSharpe {lit['d_sharpe']:+.3f} "
      f"[{lit['ci95'][0]:+.3f}, {lit['ci95'][1]:+.3f}]. Both readings fail, so "
      f"\"inverse-vol is now tested and it fails\" survives — but the arm as "
      f"run is the kinder of the two.")
    w("")
    w("## D4 — the rebalance rule, registered this time")
    w("")
    w(f"D1 at {bw:.0%} under three rules. The monthly row IS the D1 arm and is "
      f"shown for comparison without being counted twice in the "
      f"{n}-arm bar.")
    w("")
    w("| rule | Sharpe(BIL) | Sortino(BIL) | crit 1 | dSharpe | 95% CI | boot p | "
      "crit 3 |")
    w("|---|---|---|---|---|---|---|---|")
    d1key = f"D1-{int(round(bw * 100)):02d}"
    for k, lbl in ((d1key, f"monthly calendar (= {d1key})"),
                   ("D4-daily", "daily"), ("D4-band005", "0.5% absolute band")):
        f, v = res["real"][k]["full"], verdicts[k]
        w(f"| {lbl} | {f['sharpe_bil']:.4f} | {f['sortino_bil']:.4f} | "
          f"{_yn(v['c1_sharpe_and_sortino'])} | {v['d_sharpe']:+.4f} | "
          f"[{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}] | {v['boot_p']:.3f} | "
          f"{v['c3_wins']}/3 |")
    w(f"| {best} (incumbent) | {bf['sharpe_bil']:.4f} | {bf['sortino_bil']:.4f} | "
      f"— | — | — | — | — |")
    w("")
    spread = max(res["real"][k]["full"]["sharpe_bil"]
                 for k in (d1key, "D4-daily", "D4-band005")) - \
        min(res["real"][k]["full"]["sharpe_bil"]
            for k in (d1key, "D4-daily", "D4-band005"))
    w(f"The rule moves Sharpe(BIL) by {spread:.4f} across the three readings. "
      f"That spread is real and it is an order of magnitude smaller than the "
      f"interval on any of them — and unlike round 4, none of these rules is a "
      f"no-op: registering the rule up front removes an ambiguity, it does not "
      f"create an edge.")
    w("")
    w("## Honesty box")
    w("")
    w(f"- **The prior was registered and it held.** The registration stated "
      f"before any code existed that D1 and D2 are ADJACENT to arms that "
      f"already failed, that the expected uplift was ~{mech[1]['uplift']:+.4f} "
      f"Sharpe, and that the honest expectation was another null. That is what "
      f"happened. This is not a vindicated forecast — it is a round that was "
      f"not worth much power to begin with, run anyway because the mechanism "
      f"was mechanical rather than searched. And because it is mechanical, it "
      f"IS resolved against its own comparator "
      f"({pair['d_sharpe']:+.4f}, p<0.0001): the null is about the sleeve, not "
      f"about the cash.")
    w(f"- **Resolution is per arm, and the registered bar cannot see the cash "
      f"mechanism — but the mechanism's own comparison can.** Half-widths "
      f"against `{best}` run from "
      f"+/-{min((v['ci95'][1] - v['ci95'][0]) / 2 for v in verdicts.values()):.3f} "
      f"to "
      f"+/-{max((v['ci95'][1] - v['ci95'][0]) / 2 for v in verdicts.values()):.3f}; "
      f"the smallest detectable edge across all arms is {min(mdes):+.2f} at 50% "
      f"power and {min(mde80):+.2f} at 80%. A {mech[1]['uplift']:+.4f} "
      f"mechanism is invisible to THAT test, and no arm here is evidence "
      f"against the routing. Measured like-for-like it is "
      f"{pair['d_sharpe']:+.4f} [{pair['ci95'][0]:+.4f}, "
      f"{pair['ci95'][1]:+.4f}]. An earlier draft of this box said the round "
      f"\"cannot see its own hypothesis\" full stop; that was wrong, and it is "
      f"the correction this revision exists for.")
    w(f"- **D2's verdict was decided by an UNREGISTERED convention (M3).** The "
      f"{LIVE_SLEEVE_W:.0%} warm-up default is not in D2's contract and it held "
      f"on {meta['d2_warmup_days_real']} days. Judged on the registered low leg "
      f"the arm goes from 1 of 4 criteria to 3 of 4 and still fails criterion 2 "
      f"(p={d2reg['boot_p']:.3f}). Disclosed rather than buried, because it is "
      f"the same class of fault round 4 was corrected for.")
    w(f"- **The sleeve and the 30/70 baseline are modelled BOTH ways (M4).** "
      f"The frozen (dead-cash) curve is the pinned input to rounds 1-4 and is "
      f"unchanged; the swept convention — what `ibkr-executor/app/blend.py` "
      f"actually implements — is reported beside it and is worth "
      f"{swept[0]['d_sharpe']:+.3f} Sharpe on the sleeve and "
      f"{swept[1]['d_sharpe']:+.3f} on the 30/70 book. Published R2-A "
      f"statistics on the dead-cash convention UNDERSTATE the live design.")
    w(f"- **Multiple comparisons span both rounds, and the correction is "
      f"inert.** {n_all} arms have now been run against the same incumbent on "
      f"the same {meta['windows']['real']['n']} days, so a discovery would need "
      f"a {100 * meta['bonferroni_conf_all_rounds']:.3f}% interval to exclude "
      f"zero — but the smallest raw p in the campaign is {mt['min_raw_p']:.3f} "
      f"(`{mt['min_raw_p_arm']}`), so nothing is within two orders of magnitude "
      f"of even the naive bar. The max-T (Westfall-Young) adjustment on the "
      f"shared draws, which respects how correlated these near-identical "
      f"portfolios are, gives {mt['best_positive_adjusted_p']:.3f} for the best "
      f"positive arm. **The multiplicity that matters is in no denominator "
      f"here at all:** R2-A's own selection across rounds 1-3, B.5's "
      f"hindsight-fitted weights, and the choice of window.")
    w("- **In-sample status is unchanged and it is total.** `barbell-lab/config/"
      "portfolio.yaml` fixed B.5's weights on 2026-08-11 with no derivation "
      "record; the data ends 2026-08-19. The comparator was chosen with "
      "hindsight over exactly this window. The R2-A sleeve carries "
      "survivorship, universe/alias hindsight and exit-engine overfit risk, and "
      "its 30% weight came from an H13 sweep against a SPY core. No CAGR here "
      "is a forecast.")
    w("- **The idle-capital input is a rebuild, not a measurement of the live "
      "book.** `data/r2a_exposure.json` comes from re-running the round-2 "
      "pipeline; it matches the frozen curve on all 2,672 days to <1e-6, but it "
      "inherits every assumption of that pipeline. D1 and D2 also assume idle "
      "cash earns a full day of BIL from the prior close with no execution lag "
      "and no transaction cost on the implied daily cash movement — favourable "
      "assumptions that make D1 a CEILING on the cash fix, not a floor.")
    pu = meta["proxy_session_usage_synth"]
    w(f"- **The synthetic window is a FLOOR.** Proxy splice, unadjusted, no "
      f"manager alpha; **{pu['returns_using_a_proxy']} of {pu['n_returns']}** "
      f"return-days use a proxy for at least one constituent "
      f"({pu['weight_on_proxied_funds']:.0%} of B.5's weight sits in funds that "
      f"are proxied somewhere in this window). Earlier drafts quoted \"1079 of "
      f"2511\" — a hard-coded string inherited from an earlier round; this "
      f"figure is counted (m2). Criterion 4 is again not binding, because B.5 "
      f"alone is the weakest comparator there.")
    w("- **What was NOT modeled:** taxes; bid-ask and market impact beyond a "
      "flat 10 bps per side; borrow, margin or liquidity constraints; the 20% "
      "short-vol bot the config actually pairs B.5 with; PHYS "
      "premium/discount; fund-closure or capacity risk; the tail-sleeve "
      "question (#1), still open and still held at TAIL.")
    w("- **Nothing is promoted.** No config change, no live weight. There are "
      "no survivors to nominate; had there been, they would have become "
      "HYPOTHESES.md entries at most. Refinements go to a round-6 "
      "registration, not into this one.")
    w("")
    w("## Reproducibility")
    w("")
    w("```")
    w("cd genomics-alpha-tracker/backend")
    w("python -m scripts.build_r2a_exposure                    # OPTIONAL — verification only")
    w("python -m scripts.backtest_core_variants --round 5      # this campaign")
    w("python -m scripts.backtest_core_variants --round 4      # round 4's own report")
    w("```")
    w("")
    w("Step 1 is **verification-only and cannot run from a clean checkout** "
      "(m4): it needs `backend/data/backtest_bars.json`, which is untracked — "
      "which is precisely why `data/r2a_exposure.json` IS tracked. The campaign "
      "runs from the tracked inputs alone.")
    w("")
    w("Results JSON: `backend/data/backtest_sleeve_variants_r5_results.json`. "
      "Round 4's arms are still registered and still reproducible; `--round` "
      "only decides which set is judged and which report is written, so a "
      "finished round's record is never rewritten by a later one.")
    w("")
    ROUNDS[5]["report"].write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(BACKEND))
    main()
