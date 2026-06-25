"""Science signal: PubMed publications + bioRxiv/medRxiv preprints.

Early R&D-direction tells. Keyless (NCBI rewards a free API key with higher
rate limits — set NCBI_API_KEY/NCBI_EMAIL to use it). Patent filings are
stubbed behind the same interface for a future source.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import httpx
from sqlmodel import Session, select

from ..config import settings
from ..models import SciencePub
from ..utils import cache
from ..utils.ratelimit import RateLimiter, with_backoff
from .base import IngestionSource

logger = logging.getLogger(__name__)
_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_BIORXIV = "https://api.biorxiv.org/details"

# NCBI: 3 req/s without key, 10 with. Be conservative.
_NCBI_RL = RateLimiter(max_calls=3, period=1.0)


class ScienceIngestion(IngestionSource):
    name = "science"

    def __init__(self, name_map: dict[str, str] | None = None) -> None:
        self.name_map = name_map or {}

    def fetch(self, symbol: str) -> dict:
        company = self.name_map.get(symbol, symbol)
        return {"pubmed": self._pubmed(company), "preprints": self._biorxiv(company)}

    def _pubmed(self, company: str) -> list[dict]:
        key = f"pubmed:{company}"

        def _producer():
            _NCBI_RL.acquire()
            params = {
                "db": "pubmed", "term": f'"{company}"[Affiliation] OR "{company}"[Text Word]',
                "retmax": "20", "retmode": "json", "sort": "date",
            }
            if settings.ncbi_api_key:
                params["api_key"] = settings.ncbi_api_key
            r = with_backoff(
                lambda: httpx.get(f"{_EUTILS}/esearch.fcgi", params=params,
                                  timeout=settings.http_timeout_seconds)
            )
            r.raise_for_status()
            ids = r.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return []
            _NCBI_RL.acquire()
            sp = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
            if settings.ncbi_api_key:
                sp["api_key"] = settings.ncbi_api_key
            r2 = with_backoff(
                lambda: httpx.get(f"{_EUTILS}/esummary.fcgi", params=sp,
                                  timeout=settings.http_timeout_seconds)
            )
            r2.raise_for_status()
            result = r2.json().get("result", {})
            out = []
            for uid in result.get("uids", []):
                item = result.get(uid, {})
                out.append({
                    "id": uid, "title": item.get("title", ""),
                    "date": item.get("pubdate", ""),
                })
            return out

        try:
            return cache.cached(key, _producer, ttl=86400)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PubMed fetch failed for %s: %s", company, exc)
            return []

    def _biorxiv(self, company: str) -> list[dict]:
        # bioRxiv has no text search; pull a recent window and filter by name.
        key = "biorxiv:recent"

        def _producer():
            end = date.today()
            start = end - timedelta(days=30)
            url = f"{_BIORXIV}/biorxiv/{start.isoformat()}/{end.isoformat()}/0"
            r = with_backoff(lambda: httpx.get(url, timeout=settings.http_timeout_seconds))
            r.raise_for_status()
            return r.json().get("collection", [])

        try:
            recent = cache.cached(key, _producer, ttl=86400)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bioRxiv fetch failed: %s", exc)
            return []
        needle = company.lower().split()[0]
        return [
            {"id": p.get("doi", ""), "title": p.get("title", ""), "date": p.get("date", "")}
            for p in recent
            if needle in (p.get("authors", "") + p.get("author_corresponding_institution", "")).lower()
        ]

    def normalize(self, symbol: str, raw: dict) -> list[SciencePub]:
        records: list[SciencePub] = []
        for item in raw.get("pubmed", []):
            d = _parse_pub_date(item.get("date"))
            if not d:
                continue
            records.append(SciencePub(
                symbol=symbol, date=d, kind="pubmed", ext_id=str(item.get("id", "")),
                title=item.get("title", "")[:300],
                url=f"https://pubmed.ncbi.nlm.nih.gov/{item.get('id')}/", source="pubmed",
            ))
        for item in raw.get("preprints", []):
            d = _parse_pub_date(item.get("date"))
            if not d:
                continue
            doi = item.get("id", "")
            records.append(SciencePub(
                symbol=symbol, date=d, kind="biorxiv", ext_id=str(doi),
                title=item.get("title", "")[:300],
                url=f"https://doi.org/{doi}" if doi else None, source="biorxiv",
            ))
        return records

    def upsert(self, session: Session, records: list[SciencePub]) -> int:
        n = 0
        for rec in records:
            exists = session.exec(
                select(SciencePub)
                .where(SciencePub.symbol == rec.symbol)
                .where(SciencePub.kind == rec.kind)
                .where(SciencePub.ext_id == rec.ext_id)
            ).first()
            if not exists:
                session.add(rec)
                n += 1
        session.commit()
        return n


def _parse_pub_date(value) -> date | None:
    if not value:
        return None
    s = str(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y %b %d", "%Y %b", "%Y"):
        try:
            return datetime.strptime(s[: len(fmt) + 4], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None
