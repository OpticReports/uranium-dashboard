"""Catalyst lane: ClinicalTrials.gov API v2 alias-union scanner + manual events.

Lessons baked in from the 2026-08-19 MRNA miss (genomics tracker):
  * query.spons matches the REGISTERED sponsor/collaborator string, not the
    brand: "Moderna" returns ~1 trial, "ModernaTX" returns ~40. Every radar
    entry therefore carries explicit ctgov_names aliases; this scanner queries
    the UNION of all aliases and dedups by NCT id. query.spons matches lead
    sponsor AND collaborators (the V940 melanoma trial is Merck-led with
    Moderna as collaborator — the alias union still finds it).
  * Undated phase-3 trials in ACTIVE_NOT_RECRUITING with a primary completion
    date far out are exactly where surprise interim analyses come from
    (V940-001 PCD 2029, interim readout 2026-08-19). Those become watch=True
    catalysts with NO fabricated date.

Dated events map primary completion dates to readout event types with the
same phase -> event mapping and impact weights as the genomics tracker
(engine.yaml impact_weights). PDUFA/AdComm/conference dates and known interim
analyses are operator-curated via POST /catalysts (optionally with a
direction_lean — the only path to a directional structure).
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import httpx
from sqlmodel import Session, select

from ..config import engine_config, settings
from ..engine.signals import detect_interim_watch
from ..models import Catalyst
from ..utils import cached, with_backoff

logger = logging.getLogger(__name__)

_CT_BASE = "https://clinicaltrials.gov/api/v2/studies"

_PHASE_EVENT = {
    "PHASE3": "phase3_readout",
    "PHASE2": "phase2_readout",
    "PHASE1": "phase1_readout",
}


def _impact_weights() -> dict:
    return (engine_config().get("impact_weights") or {})


def fetch_studies(alias: str) -> list[dict]:
    """All open studies where `alias` is sponsor or collaborator. [] on failure."""
    key = f"ctgov:{alias}"

    def _producer():
        params = {
            "query.spons": alias,
            "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING|ENROLLING_BY_INVITATION",
            "fields": "NCTId|BriefTitle|Phase|PrimaryCompletionDate|OverallStatus|LeadSponsorName",
            "pageSize": "100",
        }
        resp = with_backoff(lambda: httpx.get(
            _CT_BASE, params=params, timeout=settings.http_timeout_seconds))
        resp.raise_for_status()
        return resp.json().get("studies", [])

    try:
        return cached(key, _producer, ttl=86400)
    except Exception as exc:  # noqa: BLE001
        logger.warning("catalyst lane DARK for alias %r: %s", alias, exc)
        return []


def union_studies(aliases: list[str]) -> list[dict]:
    """Union of studies across all aliases, deduped by NCT id."""
    seen: dict[str, dict] = {}
    for alias in aliases:
        for study in fetch_studies(alias):
            nct = (study.get("protocolSection", {})
                   .get("identificationModule", {}).get("nctId"))
            if nct and nct not in seen:
                seen[nct] = study
    return list(seen.values())


def normalize(symbol: str, studies: list[dict], asof: date) -> list[Catalyst]:
    """Studies -> Catalyst records: dated readouts from future PCDs + undated
    interim-watch rows (never a fabricated date)."""
    weights = _impact_weights()
    records: list[Catalyst] = []
    for study in studies:
        ps = study.get("protocolSection", {})
        ident = ps.get("identificationModule", {})
        status = ps.get("statusModule", {})
        design = ps.get("designModule", {})
        nct = ident.get("nctId", "")
        title = ident.get("briefTitle", "")
        phases = design.get("phases", []) or []
        overall = status.get("overallStatus", "")
        pcd = _parse_loose_date(
            (status.get("primaryCompletionDateStruct", {}) or {}).get("date"))
        url = f"https://clinicaltrials.gov/study/{nct}" if nct else None

        event_type = "data_presentation"
        for ph in phases:
            if ph in _PHASE_EVENT:
                event_type = _PHASE_EVENT[ph]
                break

        if detect_interim_watch(overall, pcd, asof, phases):
            records.append(Catalyst(
                symbol=symbol, date=None, event_type="interim_watch",
                title=f"[interim watch] {title} ({nct})"[:200],
                impact_weight=weights.get("interim_watch", 0.85),
                watch=True, confirmed=False, url=url, source="clinicaltrials"))
            continue

        if pcd is None or pcd < asof:
            continue
        records.append(Catalyst(
            symbol=symbol, date=pcd, event_type=event_type,
            title=f"{title} ({nct})"[:200],
            impact_weight=weights.get(event_type, weights.get("other", 0.2)),
            watch=False, confirmed=False, url=url, source="clinicaltrials"))
    return records


def scan_symbol(symbol: str, aliases: list[str], asof: date) -> list[Catalyst]:
    return normalize(symbol, union_studies(aliases), asof)


def upsert(session: Session, records: list[Catalyst]) -> int:
    """Insert new catalysts; refresh auto fields on existing ones. Manual rows
    (source='manual') are never touched by the scanner."""
    n = 0
    for rec in records:
        exists = session.exec(
            select(Catalyst)
            .where(Catalyst.symbol == rec.symbol)
            .where(Catalyst.event_type == rec.event_type)
            .where(Catalyst.title == rec.title)
        ).first()
        if exists:
            exists.date = rec.date
            exists.impact_weight = rec.impact_weight
            exists.url = rec.url or exists.url
            session.add(exists)
        else:
            session.add(rec)
            n += 1
    session.commit()
    return n


def _parse_loose_date(value) -> date | None:
    """CT.gov dates can be 'YYYY-MM' or 'YYYY-MM-DD' (YYYY-MM -> mid-month)."""
    if not value:
        return None
    s = str(value)[:10]
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            dt = datetime.strptime(s if fmt == "%Y-%m-%d" else s[:7], fmt)
            return dt.date() if fmt == "%Y-%m-%d" else dt.date().replace(day=15)
        except ValueError:
            continue
    return None
