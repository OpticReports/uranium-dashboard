"""Merge-blocking gate: a STALE row is not a flip baseline.

A failed fetch persists a STALE row dated the refresh day (asof falls back to
today), and it sorts AFTER the metric's real rows until a newer print
overtakes its date. As the flip baseline it re-paged every metric still RED
on its real data, once a day: foreign.custody_26w, flight-to-quality and
stock-bond corr re-sent the same RED alert every day from 2026-10-22 (live
/events), each with a STALE row dated 2026-10-22 behind its 2026-10-21 print.
These replay that store through the real run_refresh, offline."""
from __future__ import annotations

import types
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.jobs.refresh as refresh
from app.metrics.base import MetricResult, Status
from app.scoring.composite import compute_composite
from app.scoring.events import detect_metric_flip
from app.store.models import Base, EventLog, MetricSnapshot

NOW = datetime(2026, 10, 26, 9, 26, tzinfo=timezone.utc)   # the 5th re-page


def _session_factory(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'canary.db'}",
                        connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    # same configuration as app.store.db.SessionLocal
    return sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)


def _row(s, mid, asof, status, value):
    s.add(MetricSnapshot(metric_id=mid, category="F", asof=asof, value=value,
                         status=status))


def _m(mid, value, status, asof):
    return MetricResult(metric_id=mid, category="F", label=mid, value=value,
                        status=status, asof=asof)


def _offline_refresh(monkeypatch, metrics):
    """run_refresh with the board fixed to `metrics` and every network-backed
    section failing the way an outage does (each is try/except-wrapped).
    Returns the list of Telegram texts sent."""
    monkeypatch.setattr(refresh, "fetch_bundle", lambda: {})
    monkeypatch.setattr(refresh, "compute_all", lambda bundle, auctions=None: (
        metrics, {}, compute_composite(metrics), []))
    monkeypatch.setattr(refresh, "utcnow", lambda: NOW)

    def offline(*a, **k):
        raise RuntimeError("offline")
    for target in ("app.sources.rate_markets.ensemble", "app.api.routes_cycle.cycle",
                   "app.api.routes_labor._board_series",
                   "app.api.routes_squeeze.assemble_radar",
                   "app.metrics.recession_model.cached_models_and_spread",
                   "app.metrics.recession_model.cached_adjusted"):
        monkeypatch.setattr(target, offline)
    sent: list[str] = []
    monkeypatch.setattr("app.alerts.send", sent.append)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.delenv("TELEGRAM_MIN_SEVERITY", raising=False)
    return sent


def _metric_red_events(SL):
    with SL() as s:
        return [(e.event_type, e.asof) for e in s.execute(select(EventLog)).scalars()
                if e.event_type.startswith("metric_red:")]


def test_gate_a_stale_row_does_not_re_page_a_metric_still_red(tmp_path, monkeypatch):
    """The 2026-10-26 replay: custody RED on its 2026-10-21 print, a STALE row
    dated 2026-10-22 behind it, the board still RED on the same print."""
    SL = _session_factory(tmp_path)
    with SL() as s:
        _row(s, "foreign.custody_26w", date(2026, 10, 14), "RED", -5.71)
        _row(s, "foreign.custody_26w", date(2026, 10, 21), "RED", -5.7)
        _row(s, "foreign.custody_26w", date(2026, 10, 22), "STALE", None)
        s.commit()
    sent = _offline_refresh(monkeypatch, [
        _m("foreign.custody_26w", -5.7, Status.RED, date(2026, 10, 21))])
    with SL() as s:
        refresh.run_refresh(s)
    assert _metric_red_events(SL) == []
    assert not any("custody" in t.lower() for t in sent)


def test_gate_a_real_flip_survives_a_stale_interlude(tmp_path, monkeypatch):
    """GREEN -> STALE (an outage) -> RED is a real flip and still pages once."""
    SL = _session_factory(tmp_path)
    with SL() as s:
        _row(s, "crossasset.flight_to_quality", date(2026, 10, 21), "GREEN", 0.4)
        _row(s, "crossasset.flight_to_quality", date(2026, 10, 22), "STALE", None)
        s.commit()
    board = [_m("crossasset.flight_to_quality", 0.2, Status.RED, date(2026, 10, 23))]
    sent = _offline_refresh(monkeypatch, board)
    with SL() as s:
        refresh.run_refresh(s)
    assert _metric_red_events(SL) == [("metric_red:crossasset.flight_to_quality",
                                       date(2026, 10, 26))]
    assert len([t for t in sent if "flight_to_quality" in t or "Flight" in t
                or "crossasset" in t]) == 1
    with SL() as s:                                   # the next day: no re-page
        monkeypatch.setattr(refresh, "utcnow", lambda: NOW.replace(day=27))
        refresh.run_refresh(s)
    assert len(_metric_red_events(SL)) == 1


def test_flip_baseline_is_the_latest_non_stale_row(tmp_path):
    SL = _session_factory(tmp_path)
    d1, d2, d3 = date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)
    with SL() as s:
        _row(s, "a", d2, "RED", 1.0)         # RED, then a STALE interlude
        _row(s, "a", d3, "STALE", None)
        _row(s, "b", d1, "YELLOW", 1.0)      # an ordinary change: latest real row wins
        _row(s, "b", d2, "RED", 2.0)
        _row(s, "c", d3, "STALE", None)      # never seen live
        s.commit()
    with SL() as s:
        base = refresh._prev_status_map(s)
    assert base == {"a": "RED", "b": "RED"}
    red = _m("c", 2.0, Status.RED, d3)
    # a metric whose only history is STALE still pages on its first RED
    assert detect_metric_flip(red, base.get("c"), d3) is not None
    assert detect_metric_flip(_m("a", 1.0, Status.RED, d2), base.get("a"), d3) is None


# --- a failed read never erases a real row (counter-agent, 2026-10-26) --------
# The baseline skips STALE rows, so a STALE write that OVERWROTE a real row
# (same metric_id and asof) erased the state the baseline needed and could
# swallow a real RED re-entry. Both shapes it took, replayed through run_refresh.

def _run(SL, monkeypatch, when, board, composite=None):
    comp = composite or compute_composite(board)
    monkeypatch.setattr(refresh, "compute_all",
                        lambda bundle, auctions=None: (board, {}, comp, []))
    monkeypatch.setattr(refresh, "utcnow", lambda: when)
    with SL() as s:
        refresh.run_refresh(s)


def _at(day, hour=4):
    return datetime(2026, 10, day, hour, 28, tzinfo=timezone.utc)


def test_gate_a_same_day_outage_does_not_swallow_a_red_reentry(tmp_path, monkeypatch):
    """A metric with no asof (vol.move_vix) is dated the refresh day: RED on
    10-20, YELLOW at 10-21's first refresh, an outage at its second, RED on
    10-22. The outage overwrote 10-21's YELLOW, the baseline fell back to
    10-20's RED, and the re-entry never paged."""
    SL = _session_factory(tmp_path)
    _offline_refresh(monkeypatch, [])
    mid = "vol.move_vix"
    _run(SL, monkeypatch, _at(20), [_m(mid, 50.0, Status.RED, None)])
    _run(SL, monkeypatch, _at(21), [_m(mid, 30.0, Status.YELLOW, None)])
    _run(SL, monkeypatch, _at(21, 16), [_m(mid, None, Status.STALE, None)])
    with SL() as s:
        row = s.execute(select(MetricSnapshot).where(
            MetricSnapshot.metric_id == mid,
            MetricSnapshot.asof == date(2026, 10, 21))).scalars().one()
    assert (row.status, row.value) == ("YELLOW", 30.0)
    _run(SL, monkeypatch, _at(22), [_m(mid, 50.0, Status.RED, None)])
    assert _metric_red_events(SL) == [(f"metric_red:{mid}", date(2026, 10, 20)),
                                      (f"metric_red:{mid}", date(2026, 10, 22))]


def test_gate_a_valueless_read_does_not_overwrite_the_print(tmp_path, monkeypatch):
    """Builders that keep the data's asof with no value (labor, leading,
    recession) wrote STALE over the print itself: GREEN on its 10-20 print,
    then a valueless read dated 10-20, then RED - the re-entry never paged."""
    SL = _session_factory(tmp_path)
    _offline_refresh(monkeypatch, [])
    mid = "recession.prob"
    _run(SL, monkeypatch, _at(20), [_m(mid, 60.0, Status.RED, date(2026, 10, 19))])
    _run(SL, monkeypatch, _at(21), [_m(mid, 20.0, Status.GREEN, date(2026, 10, 20))])
    _run(SL, monkeypatch, _at(22), [_m(mid, None, Status.STALE, date(2026, 10, 20))])
    _run(SL, monkeypatch, _at(23), [_m(mid, 60.0, Status.RED, date(2026, 10, 22))])
    assert len(_metric_red_events(SL)) == 2
    with SL() as s:
        row = s.execute(select(MetricSnapshot).where(
            MetricSnapshot.metric_id == mid,
            MetricSnapshot.asof == date(2026, 10, 20))).scalars().one()
    assert (row.status, row.value) == ("GREEN", 20.0)     # the print survives


def _comp(score, band):
    return types.SimpleNamespace(score=score, band=band, contributions={},
                                 coverage=0.0 if score is None else 1.0)


def _band_events(SL):
    with SL() as s:
        return [e.dedup_key for e in s.execute(select(EventLog)).scalars()
                if e.event_type == "composite_band_cross"]


def test_gate_a_full_outage_does_not_page_a_band_cross(tmp_path, monkeypatch):
    """The composite's own interlude: a refresh with no data at all stores
    band NO_DATA, and the next good refresh paged "NO_DATA -> LOW". The band
    baseline skips NO_DATA, a same-day NO_DATA keeps the day's real band, and
    a real change across the outage still pages once."""
    SL = _session_factory(tmp_path)
    _offline_refresh(monkeypatch, [])
    _run(SL, monkeypatch, _at(20), [], _comp(20.0, "LOW"))
    _run(SL, monkeypatch, _at(21), [], _comp(None, "NO_DATA"))
    _run(SL, monkeypatch, _at(22), [], _comp(21.0, "LOW"))
    _run(SL, monkeypatch, _at(22, 16), [], _comp(None, "NO_DATA"))
    assert _band_events(SL) == []
    _run(SL, monkeypatch, _at(23), [], _comp(30.0, "ELEVATED"))
    assert _band_events(SL) == ["LOW->ELEVATED:2026-10-23"]
