"""Yield-curve metrics — spreads, inversion state, and the RE-STEEPENING canary.

The headline analytical feature: recessions have historically begun AFTER the
curve re-steepens (dis-inverts) following a sustained inversion — not while it is
inverted. `analyze_spread` runs a per-pair state machine

    NORMAL -> INVERTED (sustained >= N days) -> RE_STEEPENING (crossed back above 0)

and records every episode (depth, days inverted, dis-inversion date) so the UI can
shade history, annotate lags to NBER recessions, and alert live on the transition.

All spread values are in percentage points (FRED convention); depth is reported in
bps (value * 100). Inputs are pre-aligned parallel lists of dates/values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

# spread = long-tenor yield minus short-tenor yield; inverted when < 0.
PAIRS: dict[str, tuple[str, str]] = {
    "2s10s": ("2y", "10y"),
    "3m10y": ("3mo", "10y"),
    "5s30s": ("5y", "30y"),
    "2s5s": ("2y", "5y"),
    "3m2y": ("3mo", "2y"),
    "5s10s": ("5y", "10y"),
}
# Best single recession predictors — treated as co-equal top signals.
PRIMARY_PAIRS = ("3m10y", "2s10s")


class CurveState(str, Enum):
    NORMAL = "NORMAL"
    INVERTED = "INVERTED"
    RE_STEEPENING = "RE_STEEPENING"


@dataclass
class InversionEpisode:
    start: date               # first day spread < 0
    trough: date              # day of deepest (most negative) spread
    max_depth_bps: float      # most negative depth, in bps (negative number)
    days_inverted: int        # count of days spread < 0 in the episode
    sustained: bool           # days_inverted >= min_inversion_days
    dis_inversion: date | None = None   # first day back >= 0 (None if still inverted)

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(), "trough": self.trough.isoformat(),
            "max_depth_bps": self.max_depth_bps, "days_inverted": self.days_inverted,
            "sustained": self.sustained,
            "dis_inversion": self.dis_inversion.isoformat() if self.dis_inversion else None,
        }


@dataclass
class SpreadAnalysis:
    pair: str
    current_value: float | None          # latest spread (pct pts)
    current_depth_bps: float | None      # latest * 100
    state: CurveState
    days_inverted: int                   # current run if inverted, else last episode's
    last_change: date | None             # date of the most recent state transition
    dis_inversion_date: date | None      # set when state == RE_STEEPENING
    episodes: list[InversionEpisode] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pair": self.pair, "current_value": self.current_value,
            "current_depth_bps": self.current_depth_bps, "state": self.state.value,
            "days_inverted": self.days_inverted,
            "last_change": self.last_change.isoformat() if self.last_change else None,
            "dis_inversion_date": self.dis_inversion_date.isoformat() if self.dis_inversion_date else None,
            "episodes": [e.as_dict() for e in self.episodes],
        }


def build_spread(dates_a, vals_a, dates_b, vals_b) -> tuple[list[date], list[float | None]]:
    """long (b) minus short (a), aligned on common dates. Missing either side -> None."""
    map_a = dict(zip(dates_a, vals_a))
    map_b = dict(zip(dates_b, vals_b))
    common = sorted(set(map_a) & set(map_b))
    out = []
    for d in common:
        a, b = map_a[d], map_b[d]
        out.append(b - a if (a is not None and b is not None) else None)
    return common, out


def analyze_spread(
    dates: list[date],
    values: list[float | None],
    *,
    min_inversion_days: int = 10,
    steepen_persist_days: int = 60,
) -> SpreadAnalysis:
    """Run the inversion / re-steepening state machine over a daily spread series.

    - An episode is a maximal run of days with spread < 0.
    - It is `sustained` once it has >= `min_inversion_days` inverted days.
    - The day the spread crosses from < 0 back to >= 0 ending a SUSTAINED episode is
      a dis-inversion → the pair enters RE_STEEPENING and stays there for up to
      `steepen_persist_days` trading days (or until it re-inverts), then NORMAL.
    - Brief, non-sustained dips that revert are treated as noise (no re-steepen).
    """
    pair_dates = [d for d, v in zip(dates, values) if v is not None]
    pair_vals = [v for v in values if v is not None]

    episodes: list[InversionEpisode] = []
    cur_start: date | None = None
    cur_days = 0
    cur_trough: date | None = None
    cur_min = 0.0

    for d, v in zip(pair_dates, pair_vals):
        if v < 0:
            if cur_start is None:            # open a new inversion episode
                cur_start, cur_days, cur_trough, cur_min = d, 0, d, v
            cur_days += 1
            if v < cur_min:
                cur_min, cur_trough = v, d
        else:
            if cur_start is not None:         # close the episode on dis-inversion
                episodes.append(InversionEpisode(
                    start=cur_start, trough=cur_trough or cur_start,
                    max_depth_bps=round(cur_min * 100, 1), days_inverted=cur_days,
                    sustained=cur_days >= min_inversion_days, dis_inversion=d,
                ))
                cur_start = None
    # tail: still inverted at the end of the series
    if cur_start is not None:
        episodes.append(InversionEpisode(
            start=cur_start, trough=cur_trough or cur_start,
            max_depth_bps=round(cur_min * 100, 1), days_inverted=cur_days,
            sustained=cur_days >= min_inversion_days, dis_inversion=None,
        ))

    cur_val = pair_vals[-1] if pair_vals else None
    cur_depth = round(cur_val * 100, 1) if cur_val is not None else None

    # Determine live state from the tail.
    state = CurveState.NORMAL
    days_inv = 0
    last_change: date | None = None
    dis_date: date | None = None

    if not pair_vals:
        return SpreadAnalysis("", None, None, state, 0, None, None, episodes)

    open_ep = episodes[-1] if episodes and episodes[-1].dis_inversion is None else None
    if open_ep is not None:
        state = CurveState.INVERTED
        days_inv = open_ep.days_inverted
        # last change = the day it went inverted (episode start)
        last_change = open_ep.start
    else:
        # not currently inverted: was the most recent sustained dis-inversion recent?
        last_sustained = next((e for e in reversed(episodes) if e.sustained and e.dis_inversion), None)
        if last_sustained is not None:
            idx_dis = pair_dates.index(last_sustained.dis_inversion)
            trading_days_since = len(pair_dates) - 1 - idx_dis
            if trading_days_since <= steepen_persist_days:
                state = CurveState.RE_STEEPENING
                days_inv = last_sustained.days_inverted
                last_change = last_sustained.dis_inversion
                dis_date = last_sustained.dis_inversion
        # else remain NORMAL

    return SpreadAnalysis(
        pair="", current_value=cur_val, current_depth_bps=cur_depth, state=state,
        days_inverted=days_inv, last_change=last_change, dis_inversion_date=dis_date,
        episodes=episodes,
    )


def lag_months_to_recession(
    episode: InversionEpisode, recession_starts: list[date]
) -> int | None:
    """Months from an episode's dis-inversion to the next NBER recession onset.

    Used to annotate the canary chart from data ("dis-inverted → recession +N mo").
    `recession_starts` are the first days of USREC==1 runs.
    """
    if episode.dis_inversion is None:
        return None
    after = [r for r in recession_starts if r >= episode.dis_inversion]
    if not after:
        return None
    onset = min(after)
    return (onset.year - episode.dis_inversion.year) * 12 + (onset.month - episode.dis_inversion.month)
