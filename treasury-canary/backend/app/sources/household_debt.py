"""Household debt/GDP extended back with the Fed's Z.1 (Casey, 2026-09-30).

The severity index's "THE severity predictor" (household debt/GDP, 3-year
change) reads FRED HDTGPDUSQ163N (IMF FSI), which now starts in 2005 — so the index
ranked today's change against only ~18 years, and any history before 2016
had to run without it. Z.1 household and nonprofit debt (FRED CMDEBT, $mm) over
nominal GDP ($bn, SAAR) covers the same sector back to 1945.

Measured overlap 2005Q1-2025Q2 (82 quarters): 3-year changes correlate 0.97,
mean gap +0.14pp (sd 1.34pp); the level runs ~2.3pp apart (the published
series is the IMF's Financial Soundness Indicator; its definition and GDP
basis are not documented on FRED, and a 4-quarter-average GDP denominator
fits the changes worse). Only the 3-year change is used, so the level matters
only where a 3-year window crosses the join.

Splice rule (like ice_reference): the published series wins wherever it has
data; before its first observation, the Z.1 ratio is shifted by the gap at
that first quarter so the join is continuous. The shift uses one overlapping
point, never later data. Either input missing -> the published series is
returned unchanged, so a failed fetch still shows as STALE rather than
silently becoming a different series.
"""
from __future__ import annotations

from datetime import date

Series = tuple[list[date], list[float | None]]


def z1_ratio(z1_debt: Series, gdp: Series) -> dict[date, float]:
    g = {d: v for d, v in zip(*gdp) if v}
    return {d: 0.1 * v / g[d] for d, v in zip(*z1_debt) if v is not None and d in g}


def extend_household_debt(published: Series, z1_debt: Series, gdp: Series) -> Series:
    pub = [(d, v) for d, v in zip(*published) if v is not None]
    if not pub:
        return published
    z = z1_ratio(z1_debt, gdp)
    first_d, first_v = pub[0]
    if first_d not in z:
        return published
    shift = first_v - z[first_d]
    back = [(d, round(v + shift, 4)) for d, v in sorted(z.items()) if d < first_d]
    out = back + pub
    return [d for d, _ in out], [v for _, v in out]
