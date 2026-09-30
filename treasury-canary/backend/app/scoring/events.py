"""Regime-change detection. Pure functions returning Event | None; the refresh job
persists them idempotently via a unique (event_type, dedup_key) so an alert fires
exactly once per transition.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from ..metrics.base import MetricResult, Status
from ..metrics.curve import CurveState, SpreadAnalysis


@dataclass
class Event:
    event_type: str
    severity: str          # INFO | WARN | RED | CRITICAL
    asof: date
    dedup_key: str
    rationale: str
    detail: dict

    def detail_json(self) -> str:
        return json.dumps(self.detail, default=str)


def detect_curve_events(pair: str, a: SpreadAnalysis, asof: date,
                        median_lag_months: float | None = None) -> list[Event]:
    """Re-steepening (top severity) and new-inversion events for one pair."""
    events: list[Event] = []
    if a.state is CurveState.RE_STEEPENING and a.dis_inversion_date is not None:
        lag = (f" Historically, recession onset followed prior dis-inversions by a "
               f"median of ~{median_lag_months:.0f} months." if median_lag_months else "")
        # Depth of THE episode that just ended (matched by its dis-inversion date),
        # not the deepest episode in all of history.
        ep = next((e for e in reversed(a.episodes)
                   if e.dis_inversion == a.dis_inversion_date), None)
        depth = ep.max_depth_bps if ep else (a.current_depth_bps or 0.0)
        events.append(Event(
            event_type="curve_resteepening",
            severity="CRITICAL",
            asof=asof,
            # dedup on the dis-inversion date -> fires once per episode
            dedup_key=f"{pair}:{a.dis_inversion_date.isoformat()}",
            rationale=(f"{pair} dis-inverted on {a.dis_inversion_date.isoformat()} after "
                       f"{a.days_inverted} days inverted (max depth {depth:.0f}bps)."
                       f"{lag} Framed as association, not causation; post-2000 lead times "
                       f"have been longer and noisier."),
            detail={"pair": pair, "days_inverted": a.days_inverted,
                    "dis_inversion": a.dis_inversion_date.isoformat(),
                    "max_depth_bps": depth, "current_bps": a.current_depth_bps},
        ))
    if a.state is CurveState.INVERTED and a.days_inverted == 1:
        events.append(Event(
            event_type="curve_new_inversion", severity="WARN", asof=asof,
            dedup_key=f"{pair}:{a.last_change.isoformat() if a.last_change else asof.isoformat()}",
            rationale=f"{pair} inverted (spread {a.current_depth_bps:.0f}bps).",
            detail={"pair": pair, "current_bps": a.current_depth_bps},
        ))
    return events


def detect_band_cross(prev_band: str | None, cur_band: str, score: float | None,
                      asof: date) -> Event | None:
    """Composite crossing a stress-band boundary."""
    if prev_band is None or cur_band == prev_band or cur_band == "NO_DATA":
        return None
    order = ["LOW", "ELEVATED", "HIGH", "SEVERE"]
    worse = order.index(cur_band) > order.index(prev_band) if (
        cur_band in order and prev_band in order) else False
    return Event(
        event_type="composite_band_cross",
        severity="RED" if worse and cur_band in ("HIGH", "SEVERE") else "WARN",
        asof=asof, dedup_key=f"{prev_band}->{cur_band}:{asof.isoformat()}",
        rationale=f"Treasury Stress Score moved {prev_band} -> {cur_band} ({score}).",
        detail={"prev": prev_band, "cur": cur_band, "score": score},
    )


def detect_metric_flip(metric: MetricResult, prev_status: str | None,
                       asof: date) -> Event | None:
    """Generic: a metric crossing into RED/CRITICAL (corr flip, funding spike,
    auction failure, MOVE breakout all route through this)."""
    if metric.status not in (Status.RED, Status.CRITICAL):
        return None
    if prev_status == metric.status.value:
        return None
    return Event(
        event_type=f"metric_red:{metric.metric_id}",
        severity=metric.status.value if metric.status is Status.CRITICAL else "RED",
        asof=asof, dedup_key=f"{metric.metric_id}:{asof.isoformat()}",
        rationale=f"{metric.label} -> {metric.status.value} (value {metric.value}). {metric.note}".strip(),
        detail={"metric_id": metric.metric_id, "value": metric.value, "status": metric.status.value},
    )


def detect_rate_spike(dates: list[date], d60_bp: list[float | None], asof: date, *,
                      spike_bp: float, rearm_bp: float, approach_bp: float,
                      approach_rearm_bp: float, recent_days: int,
                      spike_severity: str, approach_severity: str,
                      spike_text: str, approach_text: str) -> list[Event]:
    """Long-yield SPIKE (and approach) crossings of the 60-trading-day change.

    Stateless: replays the whole d60 history through a hysteresis state
    machine, so the answer depends only on the data — a redeploy or an empty
    event table cannot invent or lose a crossing. A crossing fires once
    (dedup on its date) and re-arms only after d60 falls back below the
    re-arm level, so a series hovering at the line cannot flood the phone.
    Only a crossing within `recent_days` of `asof` is returned: a cold start
    must not replay an old episode as news.
    """
    spike_armed = approach_armed = True
    last_spike = last_approach = None
    for d, v in zip(dates, d60_bp):
        if v is None:
            continue
        if not spike_armed and v < rearm_bp:
            spike_armed = True
        if not approach_armed and v < approach_rearm_bp:
            approach_armed = True
        if spike_armed and v >= spike_bp:
            last_spike = (d, v)
            spike_armed = False
            approach_armed = False          # the spike supersedes the approach
        elif approach_armed and approach_bp <= v < spike_bp:
            last_approach = (d, v)
            approach_armed = False
    out: list[Event] = []
    for kind, hit, sev, text in (("rate_spike", last_spike, spike_severity, spike_text),
                                 ("rate_spike_approach", last_approach,
                                  approach_severity, approach_text)):
        if hit is None or (asof - hit[0]).days > recent_days:
            continue
        d, v = hit
        out.append(Event(
            event_type=kind, severity=sev, asof=asof,
            dedup_key=f"{kind}:{d.isoformat()}",
            rationale=text.format(d60=v, date=d.isoformat()),
            detail={"crossed_on": d.isoformat(), "d60_bp": v,
                    "spike_bp": spike_bp, "approach_bp": approach_bp}))
    return out
