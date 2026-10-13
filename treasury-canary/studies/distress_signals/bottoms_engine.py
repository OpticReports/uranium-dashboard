"""Scoring machinery for studies/distress-bottoms.md (roll-over of growth as a
bottom marker). Pure functions, no data access: the run script feeds them.

Periods are consecutive integers in a series' own frequency (months, or
quarters); `release(t)` maps a period to the month index (engine.M) it was
first published. The same functions score the observed series and every
null draw.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np


@dataclass(frozen=True)
class Rule:
    w: int = 6            # trailing-sum length, periods
    lag: int = 12         # y/y comparison lag, periods
    look: int = 12        # trailing-high window, periods
    theta: float = 0.10   # armed when the trailing high >= theta
    frac: float = 1 / 3   # roll-over when g <= high - max(floor, frac * high) ...
    floor: float = 0.05
    k: int = 2            # ... for k consecutive computable periods


def growth(values: dict[int, float], rule: Rule, bad: Iterable[int] = (),
           span: tuple[int, int] | None = None) -> dict[int, float]:
    """g(t) = S_w(t) / S_w(t - lag) - 1 with S_w the trailing w-period sum.
    Computable only when all 2w input periods are present and none is in `bad`
    (masks), and - when `span` (lo, hi) is given - the whole range
    t - lag - w + 1 .. t lies inside it (one data segment)."""
    bad = set(bad)
    out: dict[int, float] = {}
    for t in sorted(values):
        lo = t - rule.lag - rule.w + 1
        if span is not None and (lo < span[0] or t > span[1]):
            continue
        cur = range(t - rule.w + 1, t + 1)
        base = range(t - rule.lag - rule.w + 1, t - rule.lag + 1)
        ins = list(cur) + list(base)
        if all(i in values and i not in bad for i in ins):
            s0 = sum(values[i] for i in base)
            if s0 > 0:
                out[t] = sum(values[i] for i in cur) / s0 - 1
    return out


TIE = 1e-12   # a decimal tie (0.07 vs 0.12 - 0.05) counts as reaching the line


def trailing_high(g: dict[int, float], t: int, look: int) -> float | None:
    vals = [g[s] for s in range(t - look + 1, t + 1) if s in g]
    return max(vals) if vals else None


def armed(g: dict[int, float], t: int, rule: Rule) -> bool:
    h = trailing_high(g, t, rule.look)
    return h is not None and h >= rule.theta - TIE


def signals(g: dict[int, float], periods: Iterable[int], rule: Rule) -> list[dict]:
    """Roll-over signals in period order. A signal fires at the first t where
    the series is armed, g(t) is computable and g(t) <= H(t) - max(floor,
    frac*H(t)) for k consecutive periods (an uncomputable period breaks the
    run). After a signal, the series re-arms only when it sets a new trailing
    high >= theta (g(s) = H(s) >= theta, s > signal): `rearmed_at` records it."""
    out: list[dict] = []
    run, live = 0, True
    for t in periods:
        gt = g.get(t)
        h = trailing_high(g, t, rule.look)
        if not live:
            if gt is not None and h is not None and gt >= rule.theta - TIE and gt >= h:
                live = True
                out[-1]["rearmed_at"] = t
            run = 0
            continue
        cond = (gt is not None and h is not None and h >= rule.theta - TIE
                and gt <= h - max(rule.floor, rule.frac * h) + TIE)
        run = run + 1 if cond else 0
        if run >= rule.k:
            out.append({"t": t, "g": gt, "high": h, "rearmed_at": None})
            live, run = False, 0
    return out


def classify(e: int | None, lo: int, hi: int) -> str:
    if e is None:
        return "MISS"
    return "HIT" if lo <= e <= hi else ("EARLY" if e < lo else "LATE")


def first_released(sigs: list[dict], release: Callable[[int], int], lo: int, hi: int) -> dict | None:
    """The first signal whose release month lies in [lo, hi]."""
    for s in sigs:
        r = release(s["t"])
        if lo <= r <= hi:
            return {**s, "release": r}
    return None


def armed_releases(g: dict[int, float], periods: Iterable[int], rule: Rule,
                   release: Callable[[int], int], lo: int, hi: int) -> list[int]:
    """Release months in [lo, hi] of periods at which a signal could fire:
    armed and g computable (the null's support)."""
    return [release(t) for t in periods
            if t in g and armed(g, t, rule) and lo <= release(t) <= hi]


def half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def loo_clock(arms: list[int | None], targets: list[int | None]) -> list[int | None]:
    """Leave-one-out clock: arm_r + median over the other scored episodes of
    (target - arm), rounded half up; None where arm_r or the target is missing."""
    out: list[int | None] = []
    for i, (a, tg) in enumerate(zip(arms, targets)):
        lags = [targets[j] - arms[j] for j in range(len(arms))
                if j != i and arms[j] is not None and targets[j] is not None]
        out.append(None if a is None or tg is None or not lags else a + half_up(float(np.median(lags))))
    return out


def null_hits(supports: list[list[int]], targets: list[int | None], lo: int, hi: int,
              draws: int, rng: np.random.Generator) -> np.ndarray:
    """HIT counts when each episode's signal is a uniform draw from its support
    (an empty support, or a missing target, is a MISS)."""
    hits = np.zeros(draws, dtype=int)
    for sup, tg in zip(supports, targets):
        if not sup or tg is None:
            continue
        e = np.asarray(sup)[rng.integers(0, len(sup), size=draws)] - tg
        hits += (e >= lo) & (e <= hi)
    return hits


def p_upper(null: np.ndarray, obs: int) -> float:
    return float((1 + np.sum(null >= obs)) / (1 + len(null)))


# ---------------------------------------------------------------- trader's view
def entry_stats(eq: dict[int, float], m: int | None, low: int | None) -> dict:
    """Equity outcomes for an entry in month m (monthly-average levels):
    returns to +6/+12/+24, the worst further drawdown within 12 months, and -
    for entries after the low - the share of the low -> low+12 rebound missed."""
    if m is None or m not in eq:
        return {}
    r = {}
    for h in (6, 12, 24):
        if m + h in eq:
            r[f"ret_{h}m"] = eq[m + h] / eq[m] - 1
    path = [eq[x] for x in range(m, m + 13) if x in eq]
    r["worst_dd_12m"] = min(path) / eq[m] - 1
    if low is not None and m > low and low in eq and low + 12 in eq and eq[low + 12] > eq[low]:
        r["rebound_missed"] = (eq[m] - eq[low]) / (eq[low + 12] - eq[low])
    return r


def drawdown_trigger(eq: dict[int, float], lo: int, hi: int, depth: float = 0.20) -> int | None:
    """First month in [lo, hi] when the index is >= depth below its trailing
    12-month high."""
    for m in range(lo, hi + 1):
        prior = [eq[x] for x in range(m - 11, m + 1) if x in eq]
        if m in eq and prior and eq[m] <= (1 - depth) * max(prior):
            return m
    return None


@dataclass
class EpisodeResult:
    peak: int
    trough: int
    target: int | None
    signal: dict | None
    e: int | None
    outcome: str
    support: list[int] = field(default_factory=list)
