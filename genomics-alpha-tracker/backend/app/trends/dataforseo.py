"""DataForSEO Google Trends client (keywords_data/google_trends/explore/live).

Docs: https://docs.dataforseo.com/v3/keywords_data/google_trends/explore/live/
- POST, Basic auth (DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD), $0.009 per request.
- 1-5 keywords per request; we send ONE so each keyword's 0-100 scale is
  its own (a multi-keyword request normalises them against each other).
- Response: tasks[0].result[0].items[type == "google_trends_graph"].data[]
  with {date_from, date_to, timestamp, missing_data, values[]}.
- past_5_years returns WEEKLY points (week starts Sunday); that is the
  granularity the detector and the study are built on.

The index is renormalised per request window, so a refresh replaces the
whole stored series for that keyword (see ingestion/trends.py).
"""
from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

API_URL = "https://api.dataforseo.com/v3/keywords_data/google_trends/explore/live"
COST_PER_REQUEST_USD = 0.009


class TrendsError(RuntimeError):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


def redact(msg: str) -> str:
    """Scrub anything that looks like credentials from exception text."""
    msg = re.sub(r"(Authorization[:=]\s*Basic\s+)[A-Za-z0-9+/=]+", r"\1<redacted>", msg, flags=re.I)
    return re.sub(r"(password[\"']?\s*[:=]\s*[\"']?)[^\s\"',]+", r"\1<redacted>", msg, flags=re.I)


def parse_graph(payload: dict) -> list[dict]:
    """Extract [{date, value, missing}] from an explore/live response body.

    Raises TrendsError on an API-level failure (status_code != 20000 at the
    top level or on the task) so the caller can trip its breaker.
    """
    top = payload.get("status_code")
    if top != 20000:
        raise TrendsError(f"dataforseo status {top}: {payload.get('status_message')}", status=top)
    tasks = payload.get("tasks") or []
    if not tasks:
        raise TrendsError("dataforseo: no tasks in response")
    task = tasks[0]
    if task.get("status_code") != 20000:
        raise TrendsError(f"dataforseo task status {task.get('status_code')}: "
                          f"{task.get('status_message')}", status=task.get("status_code"))
    out: list[dict] = []
    for res in task.get("result") or []:
        for item in res.get("items") or []:
            if item.get("type") != "google_trends_graph":
                continue
            for d in item.get("data") or []:
                vals = d.get("values") or []
                v = vals[0] if vals else None
                if v is None or d.get("date_from") is None:
                    continue
                out.append({"date": d["date_from"], "value": float(v),
                            "missing": bool(d.get("missing_data", False))})
    out.sort(key=lambda r: r["date"])
    return out


def fetch_interest(keyword: str, login: str, password: str, *,
                   time_range: str = "past_5_years", search_type: str = "web",
                   location_code: int | None = None, timeout: float = 60.0,
                   client: httpx.Client | None = None) -> tuple[list[dict], float]:
    """One live request for one keyword. Returns (points, cost_usd)."""
    body: dict = {"keywords": [keyword], "time_range": time_range, "type": search_type,
                  "item_types": ["google_trends_graph"], "tag": "attention-top-detector"}
    if location_code is not None:
        body["location_code"] = location_code
    c = client or httpx.Client(timeout=timeout)
    try:
        r = c.post(API_URL, json=[body], auth=(login, password))
        if r.status_code in (401, 402, 403):
            raise TrendsError(f"dataforseo HTTP {r.status_code}", status=r.status_code)
        r.raise_for_status()
        payload = r.json()
    finally:
        if client is None:
            c.close()
    points = parse_graph(payload)
    cost = float(payload.get("cost") or 0.0)
    return points, cost
