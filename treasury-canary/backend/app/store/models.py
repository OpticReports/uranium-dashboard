"""ORM models — history from day one. All timestamps stored UTC."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, Float, Index, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class SeriesObs(Base):
    """One raw observation of an upstream series (e.g. a FRED datapoint)."""
    __tablename__ = "series_obs"
    __table_args__ = (
        UniqueConstraint("series_id", "date", name="uq_series_date"),
        Index("ix_series_obs_series", "series_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[str] = mapped_column(String, nullable=False)   # e.g. "DGS10"
    source: Mapped[str] = mapped_column(String, nullable=False)      # fred|treasury|nyfed|ofr
    date: Mapped["Date"] = mapped_column(Date, nullable=False)       # observation date (value date)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MetricSnapshot(Base):
    """A computed metric value + status at a refresh run (the traffic-light rows)."""
    __tablename__ = "metric_snapshot"
    __table_args__ = (
        UniqueConstraint("metric_id", "asof", name="uq_metric_asof"),
        Index("ix_metric_snapshot_metric", "metric_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_id: Mapped[str] = mapped_column(String, nullable=False)   # e.g. "curve.3m10y"
    category: Mapped[str] = mapped_column(String, nullable=False)    # A..I group key
    asof: Mapped["Date"] = mapped_column(Date, nullable=False)       # value date of the metric
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)      # GREEN|YELLOW|RED|CRITICAL|STALE
    percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PredictionLog(Base):
    """One row per day: the dashboard's own headline predictions, logged so the
    system can be scored against reality later (calibration / Brier). Truth for
    'recession within 12m' resolves from USREC once 12 months have elapsed."""
    __tablename__ = "prediction_log"
    __table_args__ = (UniqueConstraint("asof", name="uq_prediction_asof"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asof: Mapped["Date"] = mapped_column(Date, nullable=False)
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite_band: Mapped[str | None] = mapped_column(String, nullable=True)
    coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    rec_prob_12m: Mapped[float | None] = mapped_column(Float, nullable=True)
    rec_prob_adj_12m: Mapped[float | None] = mapped_column(Float, nullable=True)
    curve_state: Mapped[str | None] = mapped_column(String, nullable=True)   # 3m10y
    pins_overall: Mapped[str | None] = mapped_column(String, nullable=True)
    sahm: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EventLog(Base):
    """Regime-change / alert events. Idempotent per (event_type, dedup_key)."""
    __tablename__ = "event_log"
    __table_args__ = (
        UniqueConstraint("event_type", "dedup_key", name="uq_event_dedup"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)    # INFO|WARN|RED|CRITICAL
    asof: Mapped["Date"] = mapped_column(Date, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)   # e.g. "3m10y:2026-06-30"
    rationale: Mapped[str] = mapped_column(String, nullable=False)
    detail_json: Mapped[str | None] = mapped_column(String, nullable=True)
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
