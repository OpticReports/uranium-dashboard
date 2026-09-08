"""Attention-top detector for a Google Trends interest-over-time series.

Why this exists (Casey, 2026-09-08): search interest spiking to a record and
then rolling over marked the silver blow-off top. The same fingerprint shows
up at the bitcoin 2017 top, the GME squeeze and the ARKG mania. This module
turns that intuition into three explicit, testable flags on a WEEKLY series.

Design constraints:
- Google Trends is a 0-100 index RENORMALISED PER REQUEST WINDOW. Every rule
  here is a RATIO (vs the prior record, vs the trailing median, vs four
  weeks ago), so it gives the same answer whether the 100 sits in 2021 or
  2026. The only absolute threshold is a noise floor (values under 10 on a
  5-year window are rounding noise).
- Pure Python, no pandas (the genomics backend does not ship pandas).
- No look-ahead: every quantity at index t uses values at indices <= t only.
  Gate-tested in tests/test_trends_detector.py.

The flags (all weekly):
  CLIMAX      interest is a multi-year record (>= max of the prior 156 wks),
              >= 2x its trailing-52wk median and >= 2x its value 4 wks ago
              (a parabolic spike, not a plateau). With a price series it
              also requires price within 10% of its 52wk high - a record in
              attention during a crash is capitulation, not a blow-off.
  FADING      a CLIMAX fired within the last 8 wks, 3-wk smoothed interest
              has dropped >= 35% from its post-climax peak, and price is
              still within 15% of its post-climax high. "The crowd left,
              the price has not yet." This is the actionable warning.
  DIVERGENCE  price is at/near a 52wk high while smoothed interest is
              <= 60% of its own 52wk peak, and that peak was itself a
              (near-)record. New price high on much less attention -
              the bitcoin Nov-2021 pattern.
  COOLED      a CLIMAX fired within 8 wks, interest faded >= 35% AND price
              fell >= 15% from the post-climax high. Confirmation only.
  stage       on a CLIMAX week: 1 if it is the first climax episode in the
              last 52 wks, 2+ if the run already produced one. In the study
              the FIRST climax of a run usually came early (price went on to
              double); the tops were stage-2+ climaxes. Found post hoc on
              eight stage-2+ episodes - treat as a hypothesis, not a rule.

Parameters are frozen in PARAMS and were chosen on the eleven series in the
study (in-sample; see the honesty box in the study doc).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from statistics import median
from typing import Optional, Sequence

PARAMS = {
    "record_window": 156,      # weeks of prior history the record is taken over
    "record_min_history": 52,  # need at least this many prior weeks to call a record
    "noise_floor": 10.0,       # 0-100 index; below this a "record" is rounding noise
    "median_window": 52,
    "median_mult": 2.0,
    "parabolic_weeks": 4,
    "parabolic_mult": 2.0,
    "smooth": 3,
    "price_high_window": 52,
    "climax_price_within": 0.10,   # price >= 90% of 52wk high
    "post_window": 8,              # weeks after a climax the FADING/COOLED logic looks
    "fade_drop": 0.35,             # smoothed interest down >= 35% from post-climax peak
    "fading_price_within": 0.15,   # price still >= 85% of post-climax high
    "diverge_price_within": 0.03,  # price >= 97% of 52wk high
    "diverge_interest_max": 0.60,  # smoothed interest <= 60% of its 52wk peak
    "diverge_peak_vs_record": 0.80,  # ...and that 52wk peak >= 80% of the prior record
}


@dataclass
class Point:
    date: str
    interest: float
    close: Optional[float] = None
    smooth: Optional[float] = None
    prior_record: Optional[float] = None
    intensity: Optional[float] = None    # interest / prior_record
    climax: bool = False
    fading: bool = False
    divergence: bool = False
    cooled: bool = False
    stage: Optional[int] = None          # CLIMAX only: 1 = first climax in 52 wks, 2+ = a re-climax on a hot run
    state: str = "QUIET"                 # CLIMAX | FADING | DIVERGENCE | COOLED | ELEVATED | QUIET
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def compute(dates: Sequence[str], interest: Sequence[float],
            close: Optional[Sequence[Optional[float]]] = None,
            params: dict | None = None) -> list[Point]:
    """Run the detector over a weekly series. Returns one Point per week.

    `close` is optional (a keyword with no traded proxy still gets CLIMAX
    without the price condition, and never FADING/DIVERGENCE/COOLED).
    Values at index t depend only on indices <= t.
    """
    p = dict(PARAMS)
    if params:
        p.update(params)
    n = len(interest)
    if len(dates) != n or (close is not None and len(close) != n):
        raise ValueError("dates/interest/close length mismatch")
    vals = [float(v) for v in interest]
    px: list[Optional[float]] = list(close) if close is not None else [None] * n
    out: list[Point] = []
    sm: list[float] = []
    last_climax: Optional[int] = None
    climax_starts: list[int] = []        # first week of each climax episode (8-wk merge)

    for t in range(n):
        v = vals[t]
        s = _mean(vals[max(0, t - p["smooth"] + 1): t + 1])
        sm.append(s)
        pt = Point(date=dates[t], interest=v, close=px[t], smooth=round(s, 2))

        # --- record vs prior history (excludes t itself) --------------------
        lo = max(0, t - p["record_window"])
        prior = vals[lo:t]
        rec = max(prior) if len(prior) >= p["record_min_history"] else None
        pt.prior_record = rec
        if rec:
            pt.intensity = round(v / rec, 3) if rec > 0 else None
        med = median(vals[max(0, t - p["median_window"]):t]) if t >= 26 else None
        back = vals[t - p["parabolic_weeks"]] if t >= p["parabolic_weeks"] else None

        # --- price context --------------------------------------------------
        c = px[t]
        ph52 = None
        if c is not None:
            window = [x for x in px[max(0, t - p["price_high_window"] + 1): t + 1] if x is not None]
            ph52 = max(window) if len(window) >= 26 else None

        # --- CLIMAX ---------------------------------------------------------
        is_record = rec is not None and v >= rec and v >= p["noise_floor"]
        spike = med is not None and v >= p["median_mult"] * max(med, 1.0)
        parabolic = back is not None and v >= p["parabolic_mult"] * max(back, 1.0)
        price_ok = True if c is None or ph52 is None else c >= (1 - p["climax_price_within"]) * ph52
        if ph52 is None and c is not None:
            price_ok = False   # have price but not enough of it: stay quiet
        if is_record and spike and parabolic and price_ok:
            pt.climax = True
            if last_climax is None or t - last_climax > p["post_window"]:
                climax_starts.append(t)
            pt.stage = 1 + sum(1 for s0 in climax_starts[:-1] if t - s0 <= 52)
            pt.notes.append(f"record attention {v:.0f} vs prior {rec:.0f} "
                            f"({v / rec:.2f}x), {v / max(back, 1.0):.1f}x 4wk ago; "
                            f"stage {pt.stage}")
            last_climax = t

        # --- post-climax: FADING / COOLED -----------------------------------
        if last_climax is not None and not pt.climax and t - last_climax <= p["post_window"]:
            post_sm_peak = max(sm[last_climax:t + 1])
            faded = s <= (1 - p["fade_drop"]) * post_sm_peak
            post_px = [x for x in px[last_climax:t + 1] if x is not None]
            if faded and c is not None and post_px:
                post_high = max(post_px)
                if c >= (1 - p["fading_price_within"]) * post_high:
                    pt.fading = True
                    pt.notes.append(f"interest -{100 * (1 - s / post_sm_peak):.0f}% from climax, "
                                    f"price {100 * (c / post_high - 1):+.0f}% vs post-climax high")
                else:
                    pt.cooled = True
                    pt.notes.append(f"interest -{100 * (1 - s / post_sm_peak):.0f}%, "
                                    f"price {100 * (c / post_high - 1):+.0f}% - top confirmed")

        # --- DIVERGENCE -----------------------------------------------------
        if c is not None and ph52 is not None and not pt.climax and t >= 26:
            sm52 = sm[max(0, t - p["price_high_window"] + 1): t + 1]
            sm_peak = max(sm52)
            near_high = c >= (1 - p["diverge_price_within"]) * ph52
            low_interest = sm_peak > 0 and s <= p["diverge_interest_max"] * sm_peak
            peak_was_record = (rec is not None and sm_peak >= p["diverge_peak_vs_record"] * rec
                               and sm_peak >= p["noise_floor"])
            if near_high and low_interest and peak_was_record:
                pt.divergence = True
                pt.notes.append(f"price at 52wk high on {100 * s / sm_peak:.0f}% of peak attention")

        # --- state ----------------------------------------------------------
        if pt.climax:
            pt.state = "CLIMAX"
        elif pt.fading:
            pt.state = "FADING"
        elif pt.cooled:
            pt.state = "COOLED"
        elif pt.divergence:
            pt.state = "DIVERGENCE"
        elif rec and v >= 0.7 * rec and v >= p["noise_floor"]:
            pt.state = "ELEVATED"
        out.append(pt)
    return out


def episodes(points: Sequence[Point], flag: str, gap: int = 8) -> list[int]:
    """Indices where `flag` first fires, merging re-fires within `gap` weeks."""
    idx: list[int] = []
    last = None
    for i, pt in enumerate(points):
        if getattr(pt, flag):
            if last is None or i - last > gap:
                idx.append(i)
            last = i
    return idx


def summary(points: Sequence[Point]) -> dict:
    """Latest state plus the most recent firing of each flag (for the API)."""
    if not points:
        return {"state": "NO_DATA"}
    last = points[-1]
    def _last(flag):
        for pt in reversed(points):
            if getattr(pt, flag):
                return pt.date
        return None
    return {
        "asof": last.date,
        "state": last.state,
        "interest": last.interest,
        "smooth": last.smooth,
        "close": last.close,
        "intensity": last.intensity,
        "prior_record": last.prior_record,
        "notes": last.notes,
        "last_climax": _last("climax"),
        "last_fading": _last("fading"),
        "last_divergence": _last("divergence"),
        "last_cooled": _last("cooled"),
        "weeks": len(points),
    }
