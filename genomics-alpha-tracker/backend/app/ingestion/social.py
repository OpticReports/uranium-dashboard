"""Social / hype ingestion: X/Twitter, Reddit, StockTwits.

Aggregates daily mention VOLUME + mean SENTIMENT per platform. The scoring
engine derives velocity, acceleration (2nd derivative) and price-vs-chatter
divergence from this series.

Graceful degradation is central here:
  * X requires a PAID tier (X_BEARER_TOKEN). Absent -> log + skip, never crash.
  * Reddit requires app creds. Absent -> skip.
  * StockTwits has a keyless public endpoint (rate-limited) -> default on.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime

import httpx
from sqlmodel import Session, select

from ..config import settings
from ..models import SocialMention
from ..utils import sentiment
from ..utils.ratelimit import with_backoff
from .base import IngestionSource

logger = logging.getLogger(__name__)


class SocialIngestion(IngestionSource):
    name = "social"

    def available(self) -> bool:
        # At least one platform must be usable.
        return any([
            bool(settings.x_bearer_token),
            bool(settings.reddit_client_id and settings.reddit_client_secret),
            settings.stocktwits_enabled,
        ])

    def fetch(self, symbol: str) -> dict:
        return {
            "stocktwits": self._stocktwits(symbol) if settings.stocktwits_enabled else [],
            "x": self._x(symbol) if settings.x_bearer_token else self._skip("x", "X_BEARER_TOKEN"),
            "reddit": self._reddit(symbol)
            if (settings.reddit_client_id and settings.reddit_client_secret)
            else self._skip("reddit", "REDDIT_CLIENT_ID/SECRET"),
        }

    @staticmethod
    def _skip(platform: str, key: str) -> list:
        logger.info("Social platform '%s' skipped (%s not set)", platform, key)
        return []

    def _stocktwits(self, symbol: str) -> list[dict]:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
        try:
            r = with_backoff(lambda: httpx.get(url, timeout=settings.http_timeout_seconds))
            if r.status_code == 404:
                return []
            r.raise_for_status()
            out = []
            for msg in r.json().get("messages", []):
                created = msg.get("created_at", "")
                body = msg.get("body", "")
                # Use StockTwits' own bull/bear tag when present, else lexicon.
                tag = (msg.get("entities", {}) or {}).get("sentiment") or {}
                basic = tag.get("basic")
                s = 1.0 if basic == "Bullish" else (-1.0 if basic == "Bearish" else None)
                out.append({"date": created[:10], "text": body, "sentiment": s})
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("StockTwits fetch failed for %s: %s", symbol, exc)
            return []

    def _x(self, symbol: str) -> list[dict]:
        url = "https://api.twitter.com/2/tweets/search/recent"
        headers = {"Authorization": f"Bearer {settings.x_bearer_token}"}
        params = {"query": f"${symbol} -is:retweet lang:en", "max_results": "100",
                  "tweet.fields": "created_at"}
        try:
            r = with_backoff(
                lambda: httpx.get(url, headers=headers, params=params,
                                  timeout=settings.http_timeout_seconds)
            )
            r.raise_for_status()
            return [{"date": t.get("created_at", "")[:10], "text": t.get("text", ""),
                     "sentiment": None}
                    for t in r.json().get("data", [])]
        except Exception as exc:  # noqa: BLE001
            logger.warning("X fetch failed for %s: %s", symbol, exc)
            return []

    def _reddit(self, symbol: str) -> list[dict]:
        try:
            token = self._reddit_token()
            if not token:
                return []
            headers = {"Authorization": f"bearer {token}",
                       "User-Agent": settings.reddit_user_agent}
            out = []
            for sub in ("biotech", "stocks", "wallstreetbets"):
                url = f"https://oauth.reddit.com/r/{sub}/search"
                params = {"q": symbol, "restrict_sr": "true", "sort": "new", "limit": "50"}
                r = with_backoff(
                    lambda: httpx.get(url, headers=headers, params=params,
                                      timeout=settings.http_timeout_seconds)
                )
                r.raise_for_status()
                for child in r.json().get("data", {}).get("children", []):
                    d = child.get("data", {})
                    created = datetime.utcfromtimestamp(d.get("created_utc", 0)).date()
                    out.append({"date": created.isoformat(),
                                "text": f"{d.get('title','')} {d.get('selftext','')}",
                                "sentiment": None})
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reddit fetch failed for %s: %s", symbol, exc)
            return []

    def _reddit_token(self) -> str | None:
        try:
            auth = httpx.BasicAuth(settings.reddit_client_id, settings.reddit_client_secret)
            r = httpx.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth, data={"grant_type": "client_credentials"},
                headers={"User-Agent": settings.reddit_user_agent},
                timeout=settings.http_timeout_seconds,
            )
            r.raise_for_status()
            return r.json().get("access_token")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reddit auth failed: %s", exc)
            return None

    def normalize(self, symbol: str, raw: dict) -> list[SocialMention]:
        # Aggregate per (platform, day): count + mean sentiment.
        buckets: dict[tuple[str, date], list[float]] = defaultdict(list)
        counts: dict[tuple[str, date], int] = defaultdict(int)
        for platform in ("stocktwits", "x", "reddit"):
            for item in raw.get(platform, []):
                d = _parse_day(item.get("date"))
                if not d:
                    continue
                key = (platform, d)
                counts[key] += 1
                s = item.get("sentiment")
                if s is None:
                    s = sentiment.score_text(item.get("text", ""))
                buckets[key].append(s)
        records = []
        for (platform, d), count in counts.items():
            sents = buckets[(platform, d)]
            mean_s = sum(sents) / len(sents) if sents else None
            records.append(SocialMention(
                symbol=symbol, date=d, platform=platform, volume=count,
                sentiment=mean_s, source=platform,
            ))
        return records

    def upsert(self, session: Session, records: list[SocialMention]) -> int:
        n = 0
        for rec in records:
            exists = session.exec(
                select(SocialMention)
                .where(SocialMention.symbol == rec.symbol)
                .where(SocialMention.platform == rec.platform)
                .where(SocialMention.date == rec.date)
            ).first()
            if exists:
                exists.volume = rec.volume
                exists.sentiment = rec.sentiment
                session.add(exists)
            else:
                session.add(rec)
                n += 1
        session.commit()
        return n


def _parse_day(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
