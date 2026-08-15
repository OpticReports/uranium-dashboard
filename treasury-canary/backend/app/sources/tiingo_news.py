"""Tiingo News API — themed feed + article-velocity pulse for the dashboards.

HONESTY CONTRACT (standing): everything served from here is DESCRIPTIVE
context. No news-derived number feeds any composite, state machine, or
sizing rule anywhere — a news-based SIGNAL would first need its own
pre-registered study + counter-agent pass (none exists). Tiingo news
history is also shallow (~2014+), far too short for our episode studies.

Key: TIINGO_API_KEY env (paid news add-on on Casey's account). Absent key
=> {"available": False} — graceful, never a crash. The token is scrubbed
from any exception text before it can reach logs (pattern from
barbell-lab/ingest/tiingo.py).
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

_API = "https://api.tiingo.com/tiingo/news"
_CACHE: dict = {}
_CACHE_TTL_S = 900

# Themes mapped to the products that already exist. Tickers are Tiingo news
# ticker filters; kw are title/description keyword filters applied on top
# (Tiingo tags are noisy — keywords keep themes honest).
THEMES: dict[str, dict] = {
    "rates_fed": {"tickers": [], "kw": ("fed", "fomc", "rate cut", "rate hike",
                                        "powell", "treasury yield", "inflation")},
    "btc": {"tickers": ["btcusd"], "kw": ()},
    "gold_gde": {"tickers": ["gld", "gde", "gdx"], "kw": ()},
    "brokers_margin": {"tickers": ["schw", "hood", "ms", "gs"],
                       "kw": ("margin", "leverage", "brokerage")},
    "uranium": {"tickers": ["ccj", "urnm", "uec", "leu"], "kw": ()},
}


def _redact(msg: str) -> str:
    return re.sub(r"(token=)[A-Za-z0-9]+", r"\1<redacted>", msg)


def _key() -> str | None:
    return os.environ.get("TIINGO_API_KEY") or None


def fetch_articles(tickers: list[str] | None, start: str,
                   limit: int = 1000) -> list[dict]:
    """Raw normalized articles since `start` (YYYY-MM-DD)."""
    key = _key()
    if not key:
        raise RuntimeError("TIINGO_API_KEY unset")
    params = {"token": key, "startDate": start, "limit": limit,
              "sortBy": "publishedDate"}
    if tickers:
        params["tickers"] = ",".join(tickers)
    try:
        r = httpx.get(_API, params=params, timeout=30.0)
        r.raise_for_status()
        raw = r.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"tiingo news failed: {_redact(str(exc))}") from exc
    out = []
    for a in raw:
        out.append({"id": a.get("id"),
                    "ts": a.get("publishedDate"),
                    "title": a.get("title") or "",
                    "source": a.get("source") or "",
                    "url": a.get("url") or "",
                    "tickers": a.get("tickers") or [],
                    "tags": a.get("tags") or [],
                    "description": (a.get("description") or "")[:280]})
    return out


def _kw_match(a: dict, kw: tuple) -> bool:
    if not kw:
        return True
    text = f"{a['title']} {a['description']}".lower()
    return any(w in text for w in kw)


def theme_pulse(articles: list[dict], kw: tuple, now: datetime,
                baseline_days: int = 30) -> dict:
    """Article-velocity pulse: last-24h count vs trailing-30d daily baseline
    (z uses Poisson-ish sd = sqrt(mean), floored at 1 — descriptive only).
    The current partial day never enters the baseline."""
    sel = [a for a in articles if _kw_match(a, kw)]
    days: Counter = Counter()
    n24 = 0
    for a in sel:
        try:
            ts = datetime.fromisoformat(a["ts"].replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            continue
        days[ts.date().isoformat()] += 1
        if (now - ts) <= timedelta(hours=24):
            n24 += 1
    today = now.date().isoformat()
    hist = [c for d, c in days.items() if d != today]
    base = sum(hist) / max(len(hist), 1) if hist else 0.0
    sd = max(base ** 0.5, 1.0)
    return {"n_24h": n24, "baseline_per_day": round(base, 2),
            "velocity_z": round((n24 - base) / sd, 2),
            "n_days_baseline": len(hist),
            "latest": [{"ts": a["ts"], "title": a["title"],
                        "source": a["source"], "url": a["url"]}
                       for a in sel[:5]]}


def news_pulse(now: datetime | None = None) -> dict:
    """All themes; cached 15 min. {'available': False} without a key."""
    if not _key():
        return {"available": False,
                "note": "TIINGO_API_KEY unset on this service"}
    hit = _CACHE.get("pulse")
    if hit and time.time() - hit[0] < _CACHE_TTL_S:
        return hit[1]
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=35)).date().isoformat()
    themes = {}
    for name, spec in THEMES.items():
        try:
            arts = fetch_articles(spec["tickers"] or None, start)
            themes[name] = theme_pulse(arts, spec["kw"], now)
        except Exception as exc:  # noqa: BLE001
            logger.warning("news pulse %s failed: %s", name, _redact(str(exc)))
            themes[name] = {"error": _redact(str(exc))}
    out = {"available": True, "asof": now.isoformat(), "themes": themes,
           "note": "DESCRIPTIVE context only - article velocity vs 30d "
                   "baseline; no backtested signal, feeds nothing downstream. "
                   "Tiingo history ~2014+ is too shallow for episode studies."}
    _CACHE["pulse"] = (time.time(), out)
    return out
