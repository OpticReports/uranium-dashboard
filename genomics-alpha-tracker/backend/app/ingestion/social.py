"""Social / hype ingestion: ApeWisdom, FMP social, X/Twitter, Reddit, StockTwits.

Aggregates daily mention VOLUME + mean SENTIMENT per platform. The scoring
engine derives velocity, acceleration (2nd derivative) and price-vs-chatter
divergence from this series (it sums volume across ALL platforms per day).

Sources, strongest first:
  * ApeWisdom — FREE, no key. Aggregates ~15 stock subreddits and returns real
    daily mention counts (hundreds for active names) + a 24h-ago baseline. This
    is the robust primary; it fixes the "low/incorrect for major firms" problem
    the StockTwits-only setup had. One snapshot covers the whole watchlist.
  * FMP social — uses the FMP key (StockTwits+Twitter, with history). Best-effort:
    it's a legacy endpoint and some tiers 403 it, in which case we skip silently.
  * X requires a PAID tier (X_BEARER_TOKEN). Absent -> skip.
  * Reddit (official API) requires app creds. Absent -> skip.
  * StockTwits public endpoint (keyless, rate-limited, ~30-msg cap, often 403 on
    cloud IPs) -> best-effort secondary.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

import httpx
from sqlmodel import Session, select

from ..config import settings
from ..models import SocialMention
from ..utils import sentiment
from ..utils.ratelimit import with_backoff
from .base import IngestionSource

logger = logging.getLogger(__name__)

# ApeWisdom returns a market-wide ranking, so we fetch it ONCE and reuse it for
# every symbol in the cycle rather than hammering it 32x. Cached by a short TTL.
_APE_TTL_SECONDS = 1200  # 20 min
_ape_cache: dict[str, object] = {"ts": 0.0, "by_ticker": {}}


def _apewisdom_snapshot() -> dict[str, dict]:
    """Market-wide {TICKER: row} from ApeWisdom (all stock subreddits). Cached."""
    now = time.monotonic()
    cached = _ape_cache["by_ticker"]
    if cached and now - float(_ape_cache["ts"]) < _APE_TTL_SECONDS:
        return cached  # type: ignore[return-value]
    by_ticker: dict[str, dict] = {}
    try:
        page, pages = 1, 1
        while page <= pages and page <= 12:  # safety cap; ~9 pages today
            url = f"https://apewisdom.io/api/v1.0/filter/all-stocks/page/{page}"
            r = with_backoff(lambda u=url: httpx.get(u, timeout=settings.http_timeout_seconds))
            r.raise_for_status()
            j = r.json()
            pages = int(j.get("pages", 1) or 1)
            for row in j.get("results", []):
                t = (row.get("ticker") or "").upper()
                if t:
                    by_ticker[t] = row
            page += 1
        _ape_cache["by_ticker"] = by_ticker
        _ape_cache["ts"] = now
        logger.info("ApeWisdom snapshot: %d tickers across %d pages", len(by_ticker), pages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ApeWisdom snapshot fetch failed: %s", exc)
        return cached  # type: ignore[return-value]
    return by_ticker


class SocialIngestion(IngestionSource):
    name = "social"

    def available(self) -> bool:
        # At least one platform must be usable.
        return any([
            settings.apewisdom_enabled,
            bool(settings.fmp_social_enabled and settings.fmp_api_key),
            bool(settings.x_bearer_token),
            bool(settings.twitterapi_io_key),
            bool(settings.reddit_client_id and settings.reddit_client_secret),
            settings.stocktwits_enabled,
        ])

    def fetch(self, symbol: str) -> dict:
        return {
            # message-list platforms (counted per day in normalize)
            "stocktwits": self._stocktwits(symbol) if settings.stocktwits_enabled else [],
            "x": self._x_source(symbol),
            "reddit": self._reddit(symbol)
            if (settings.reddit_client_id and settings.reddit_client_secret)
            else self._skip("reddit", "REDDIT_CLIENT_ID/SECRET"),
            # pre-aggregated platforms (already daily counts; passed through)
            "aggregates": (
                (self._apewisdom(symbol) if settings.apewisdom_enabled else [])
                + (self._fmp_social(symbol)
                   if (settings.fmp_social_enabled and settings.fmp_api_key) else [])
            ),
        }

    def _apewisdom(self, symbol: str) -> list[dict]:
        """Today's aggregated Reddit mention count for `symbol` from ApeWisdom."""
        row = _apewisdom_snapshot().get(symbol.upper())
        if not row:
            return []  # genuinely little Reddit chatter for this name today
        today = date.today()
        recs = [{"platform": "reddit_apewisdom", "date": today.isoformat(),
                 "volume": int(row.get("mentions") or 0), "sentiment": None}]
        # Seed yesterday from the 24h-ago baseline so acceleration works on day one
        # (upsert is idempotent; a later real fetch for that day overwrites it).
        prev = row.get("mentions_24h_ago")
        if prev is not None:
            recs.append({"platform": "reddit_apewisdom",
                         "date": (today - timedelta(days=1)).isoformat(),
                         "volume": int(prev), "sentiment": None})
        return recs

    def _fmp_social(self, symbol: str) -> list[dict]:
        """Best-effort FMP historical social sentiment (StockTwits + Twitter).

        Legacy v4 endpoint — some FMP tiers 403/402 it; we skip silently then.
        Hourly rows are aggregated per day: summed posts, mean sentiment (0-1 -> -1..1).
        """
        url = "https://financialmodelingprep.com/api/v4/historical/social-sentiment"
        try:
            r = with_backoff(lambda: httpx.get(
                url, params={"symbol": symbol.upper(), "page": 0,
                             "apikey": settings.fmp_api_key},
                timeout=settings.http_timeout_seconds))
            if r.status_code in (401, 402, 403):
                logger.info("FMP social unavailable (HTTP %s) for %s — skipping",
                            r.status_code, symbol)
                return []
            r.raise_for_status()
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("FMP social fetch failed for %s: %s", symbol, exc)
            return []
        if not isinstance(data, list):
            return []
        # day -> {platform: {"posts": int, "sent": [floats]}}
        agg: dict[str, dict[str, dict]] = defaultdict(
            lambda: {"stocktwits_fmp": {"posts": 0, "sent": []},
                     "twitter_fmp": {"posts": 0, "sent": []}})
        for row in data:
            d = str(row.get("date") or "")[:10]
            if not d:
                continue
            for plat, posts_k, sent_k in (
                ("stocktwits_fmp", "stocktwitsPosts", "stocktwitsSentiment"),
                ("twitter_fmp", "twitterPosts", "twitterSentiment"),
            ):
                posts = row.get(posts_k)
                if posts:
                    agg[d][plat]["posts"] += int(posts)
                s = row.get(sent_k)
                if s is not None:
                    agg[d][plat]["sent"].append(float(s))
        out = []
        for d, plats in agg.items():
            for plat, vals in plats.items():
                if vals["posts"]:
                    mean_s = (sum(vals["sent"]) / len(vals["sent"]) * 2 - 1
                              if vals["sent"] else None)  # 0..1 -> -1..1
                    out.append({"platform": plat, "date": d,
                                "volume": vals["posts"], "sentiment": mean_s})
        return out

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

    def _x_source(self, symbol: str) -> list[dict]:
        """Pick the X feed: official API if a bearer token is set, else twitterapi.io."""
        if settings.x_bearer_token:
            return self._x(symbol)
        if settings.twitterapi_io_key:
            return self._twitterapi_io(symbol)
        return self._skip("x", "X_BEARER_TOKEN or TWITTERAPI_IO_KEY")

    def _twitterapi_io(self, symbol: str) -> list[dict]:
        """Recent $TICKER posts via twitterapi.io (3rd-party X data, pay-per-tweet).

        Spend is bounded: only the last `lookback_days` of posts, capped at
        `max_posts` per symbol per run. Cashtag query, English, no retweets.
        """
        base = "https://api.twitterapi.io/twitter/tweet/advanced_search"
        headers = {"X-API-Key": settings.twitterapi_io_key}
        since_unix = int((datetime.utcnow()
                          - timedelta(days=settings.twitterapi_io_lookback_days)).timestamp())
        query = f"${symbol} lang:en -filter:retweets since_time:{since_unix}"
        out: list[dict] = []
        cursor: str | None = None
        try:
            for _page in range(10):  # hard page cap (safety); max_posts is the real bound
                params = {"query": query, "queryType": "Latest"}
                if cursor:
                    params["cursor"] = cursor
                r = with_backoff(lambda p=dict(params): httpx.get(
                    base, headers=headers, params=p,
                    timeout=settings.http_timeout_seconds))
                if r.status_code in (401, 403):
                    logger.warning("twitterapi.io auth failed (HTTP %s) — check TWITTERAPI_IO_KEY",
                                   r.status_code)
                    break
                r.raise_for_status()
                j = r.json()
                tweets = j.get("tweets") or []
                for tw in tweets:
                    d = _x_created_date(tw.get("created_at"))
                    if d:
                        out.append({"date": d, "text": tw.get("text", ""), "sentiment": None})
                cursor = j.get("next_cursor")
                has_next = j.get("has_next_page", bool(cursor))
                if not tweets or not has_next or not cursor or len(out) >= settings.twitterapi_io_max_posts:
                    break
            return out[: settings.twitterapi_io_max_posts]
        except Exception as exc:  # noqa: BLE001
            logger.warning("twitterapi.io fetch failed for %s: %s", symbol, exc)
            return out

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
        # Pre-aggregated platforms (ApeWisdom, FMP social) already carry daily
        # counts — pass them straight through.
        for item in raw.get("aggregates", []):
            d = _parse_day(item.get("date"))
            if not d or not item.get("volume"):
                continue
            records.append(SocialMention(
                symbol=symbol, date=d, platform=item["platform"],
                volume=int(item["volume"]), sentiment=item.get("sentiment"),
                source=item["platform"],
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


def _x_created_date(value) -> str | None:
    """Twitter timestamps come as 'Wed Oct 10 20:19:24 +0000 2018' or ISO. -> YYYY-MM-DD."""
    if not value:
        return None
    s = str(value)
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").date().isoformat()
    except ValueError:
        pass
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None
