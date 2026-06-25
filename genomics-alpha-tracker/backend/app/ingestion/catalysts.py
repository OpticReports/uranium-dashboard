"""Catalyst / pipeline calendar — the core alpha engine.

Sources (all keyless / graceful):
  * ClinicalTrials.gov API v2  -> trial milestone (primary completion) dates,
    mapped to readout event types + impact weights by phase.
  * yfinance earnings calendar  -> upcoming earnings dates.
  * Manual catalysts (PDUFA / AdComm / conferences ASH/ASCO/AGBT/JPM/ASGCT) are
    added via the API (POST /catalysts) with manual impact overrides — these are
    hard to scrape reliably and are explicitly operator-curated.

Each catalyst gets an auto impact_weight (overridable). Gene-editing and dx
names live and die on these, so they carry the heaviest default weights.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import httpx
from sqlmodel import Session, select

from ..config import scoring_config, settings
from ..models import Catalyst
from ..utils import cache
from ..utils.ratelimit import with_backoff
from .base import IngestionSource

logger = logging.getLogger(__name__)
_CT_BASE = "https://clinicaltrials.gov/api/v2/studies"

_PHASE_EVENT = {
    "PHASE3": ("phase3_readout", "phase3_readout"),
    "PHASE2": ("phase2_readout", "phase2_readout"),
    "PHASE1": ("phase1_readout", "phase1_readout"),
}


class CatalystIngestion(IngestionSource):
    name = "catalysts"

    def __init__(self, name_map: dict[str, str] | None = None) -> None:
        self.name_map = name_map or {}
        self._impact = scoring_config()["components"]["catalyst_score"]["impact_weights"]

    def fetch(self, symbol: str) -> dict:
        company = self.name_map.get(symbol, symbol)
        trials = self._fetch_trials(company)
        earnings = self._fetch_earnings(symbol)
        return {"trials": trials, "earnings": earnings}

    def _fetch_trials(self, company: str) -> list[dict]:
        key = f"ctgov:{company}"

        def _producer():
            params = {
                "query.spons": company,
                "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING|ENROLLING_BY_INVITATION",
                "fields": "NCTId|BriefTitle|Phase|PrimaryCompletionDate|OverallStatus|LeadSponsorName",
                "pageSize": "50",
            }
            resp = with_backoff(
                lambda: httpx.get(_CT_BASE, params=params, timeout=settings.http_timeout_seconds)
            )
            resp.raise_for_status()
            return resp.json().get("studies", [])

        try:
            return cache.cached(key, _producer, ttl=86400)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ClinicalTrials fetch failed for %s: %s", company, exc)
            return []

    def _fetch_earnings(self, symbol: str) -> list[str]:
        try:
            import yfinance as yf

            t = yf.Ticker(symbol)
            dates: list[str] = []
            try:
                df = t.get_earnings_dates(limit=8)
                if df is not None and not df.empty:
                    for idx in df.index:
                        d = idx.date() if hasattr(idx, "date") else None
                        if d and d >= date.today():
                            dates.append(d.isoformat())
            except Exception:  # noqa: BLE001
                cal = getattr(t, "calendar", None)
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if isinstance(ed, list):
                        dates += [d.isoformat() for d in ed if hasattr(d, "isoformat")]
            return dates
        except Exception as exc:  # noqa: BLE001
            logger.warning("earnings fetch failed for %s: %s", symbol, exc)
            return []

    def normalize(self, symbol: str, raw: dict) -> list[Catalyst]:
        records: list[Catalyst] = []
        for study in raw.get("trials", []):
            ps = study.get("protocolSection", {})
            ident = ps.get("identificationModule", {})
            status = ps.get("statusModule", {})
            design = ps.get("designModule", {})
            nct = ident.get("nctId", "")
            title = ident.get("briefTitle", "")
            phases = design.get("phases", []) or []
            pcd = (status.get("primaryCompletionDateStruct", {}) or {}).get("date")
            d = _parse_loose_date(pcd)
            if not d or d < date.today():
                continue
            event_type = "data_presentation"
            for ph in phases:
                if ph in _PHASE_EVENT:
                    event_type = _PHASE_EVENT[ph][0]
                    break
            records.append(
                Catalyst(
                    symbol=symbol, date=d, event_type=event_type,
                    title=f"{title} ({nct})"[:200],
                    impact_weight=self._impact.get(event_type, self._impact.get("other", 0.2)),
                    confirmed=False,
                    url=f"https://clinicaltrials.gov/study/{nct}" if nct else None,
                    source="clinicaltrials",
                )
            )
        for ed in raw.get("earnings", []):
            d = _parse_loose_date(ed)
            if not d or d < date.today():
                continue
            records.append(
                Catalyst(
                    symbol=symbol, date=d, event_type="earnings",
                    title="Earnings", impact_weight=self._impact.get("earnings", 0.35),
                    confirmed=True, source="yfinance",
                )
            )
        return records

    def upsert(self, session: Session, records: list[Catalyst]) -> int:
        n = 0
        for rec in records:
            exists = session.exec(
                select(Catalyst)
                .where(Catalyst.symbol == rec.symbol)
                .where(Catalyst.event_type == rec.event_type)
                .where(Catalyst.date == rec.date)
                .where(Catalyst.title == rec.title)
            ).first()
            if exists:
                # Refresh auto impact but PRESERVE any manual override.
                exists.impact_weight = rec.impact_weight
                exists.url = rec.url or exists.url
                session.add(exists)
            else:
                session.add(rec)
                n += 1
        session.commit()
        return n


def _parse_loose_date(value) -> date | None:
    """ClinicalTrials dates can be 'YYYY-MM' or 'YYYY-MM-DD'."""
    if not value:
        return None
    s = str(value)[:10]
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            dt = datetime.strptime(s if fmt == "%Y-%m-%d" else s[:7], fmt)
            # For YYYY-MM assume mid-month as the estimated date.
            return dt.date() if fmt == "%Y-%m-%d" else dt.date().replace(day=15)
        except ValueError:
            continue
    return None
