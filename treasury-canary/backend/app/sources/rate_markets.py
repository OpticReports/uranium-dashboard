"""Fed-decision probability ensemble: Polymarket + Kalshi, blended with
accuracy-earned weights.

Concept (Casey's "contribution margin"): each source's weight in the blend is
proportional to its demonstrated forecast skill — Brier score of its price at
T-7d before each resolved FOMC meeting vs the realized outcome. Weights are
the OUTPUT of a backtest, not an opinion.

FROZEN BACKTEST (2026-08-07, T-7d prices, buckets cut50p/cut25/hold/hike25p):
  Polymarket  n=12 resolved meetings (2025-03 .. 2026-07)  mean Brier 0.0114
  Kalshi      n=2  resolved meetings (2026-06, 2026-07)    mean Brier 0.0602
  futures     n=0  (expired ZQ contracts unfetchable — prior weight)
Weight-sweep note (2026-08-07): on the n=2 PM/KA overlap the measured
optimum is 100% PM (both sources erred hawkish into the Jul-2026 hold, PM
less; no diversification benefit visible yet) — the shrinkage prior is what
keeps KA/futures alive against overfitting a 2-meeting sample, exactly the
c*-style discipline used in the Kelly engine.
Weights: inverse shrunk-Brier (0.05 prior x 2 pseudo-meetings) -> PM ~61%,
futures ~21%, KA ~19%.
Every fetch snapshots forecasts to disk; after each meeting resolves the
archive re-scores and the weights update — the blend keeps earning itself.

NOT modeled: CME FedWatch (no keyless feed — futures-implied probabilities
would be a third column if a data path appears). Prediction markets carry
their own microstructure (fees, longshot bias at <2c); T-7d is one horizon,
not a curve.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

BUCKETS = ["cut50p", "cut25", "hold", "hike25p"]
LABELS = {"cut50p": "Cut ≥50", "cut25": "Cut 25", "hold": "Hold",
          "hike25p": "Hike ≥25"}

# frozen backtest constants (see module docstring). futures = FedWatch-style
# ZQ-implied probabilities (fed_futures.py): expired contracts aren't
# fetchable so it has NO backtest history — it enters at the shrinkage prior
# (n=0) and earns weight as meetings resolve.
PRIOR_BRIER, PRIOR_N = 0.05, 2
BACKTEST = {"polymarket": {"brier": 0.0114, "n": 12},
            "kalshi": {"brier": 0.0602, "n": 2},
            "futures": {"brier": None, "n": 0}}

_STORE = os.path.join(os.environ.get("CACHE_DIR", "./data"), "rate_ensemble.json")
_UA = {"User-Agent": "optic-research canary tool (casey.rondin@gmail.com)"}


def _load_store() -> dict:
    try:
        return json.load(open(_STORE))
    except Exception:  # noqa: BLE001
        return {"snapshots": {}, "scored": {}}


def _save_store(d: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        json.dump(d, open(_STORE, "w"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("rate_ensemble store save failed: %s", exc)


# ---------- fetchers (None-degrading) ----------

def fetch_polymarket() -> dict[str, dict]:
    """{meeting_iso_date: {bucket: prob}} for open fed-decision events."""
    out: dict[str, dict] = {}
    try:
        with httpx.Client(timeout=25, headers=_UA) as c:
            evs: list = []
            try:
                r = c.get("https://gamma-api.polymarket.com/events",
                          params={"tag_slug": "fed-rates", "closed": "false",
                                  "limit": 50}).json()
                if isinstance(r, list):
                    evs.extend(r)
            except Exception:  # noqa: BLE001
                pass
            try:
                r = c.get("https://gamma-api.polymarket.com/public-search",
                          params={"q": "fed decision"}).json()
                evs.extend(r.get("events") or [])
            except Exception:  # noqa: BLE001
                pass
            seen: set[str] = set()
            for ev in evs:
                slug = ev.get("slug") or ""
                if "fed-decision" not in slug or slug in seen:
                    continue
                seen.add(slug)
                if ev.get("closed"):
                    continue
                # search/list results carry slim market objects (no prices):
                # always refetch the full event by slug
                full = c.get("https://gamma-api.polymarket.com/events",
                             params={"slug": slug}).json()
                if not full:
                    continue
                ev = full[0]
                end = ev.get("endDate")
                if not end:
                    continue
                markets = ev.get("markets") or []
                probs: dict[str, float] = {}
                for m in markets:
                    b = _bucket_pm(m.get("question", ""))
                    if not b:
                        continue
                    try:
                        px = json.loads(m.get("outcomePrices") or "[]")
                        probs[b] = probs.get(b, 0.0) + float(px[0])
                    except Exception:  # noqa: BLE001
                        continue
                probs = _norm(probs)
                if probs:
                    out[end[:10]] = probs
    except Exception as exc:  # noqa: BLE001
        logger.warning("polymarket fed fetch failed: %s", exc)
    return out


def _bucket_pm(q: str) -> str | None:
    """Matches both phrasings: 'Fed decreases ... by 25 bps' (2024-25) and
    'Will the Fed decrease ... by 25 bps' (2026+). All hike sizes fold into
    hike25p (our schema's '25 or more')."""
    q = q.lower()
    if "no change" in q:
        return "hold"
    if "decrease" in q:
        return "cut50p" if "50" in q else ("cut25" if "25 bps" in q else None)
    if "increase" in q:
        return "hike25p"
    return None


def _bucket_kalshi(strike) -> str | None:
    if not isinstance(strike, dict):
        return None
    if "Cut" in strike:
        return "cut50p" if ">" in str(strike["Cut"]) else "cut25"
    if "Hike" in strike:
        return "hold" if str(strike["Hike"]) == "0" else "hike25p"
    return None


def fetch_kalshi() -> dict[str, dict]:
    """{meeting_iso_date: {bucket: prob}} from open KXFEDDECISION markets."""
    out: dict[str, dict] = {}
    try:
        with httpx.Client(timeout=25, headers=_UA) as c:
            d = c.get("https://api.elections.kalshi.com/trade-api/v2/markets",
                      params={"series_ticker": "KXFEDDECISION",
                              "status": "open", "limit": 200}).json()
            evs: dict[str, list] = {}
            for m in d.get("markets", []):
                evs.setdefault(m["event_ticker"], []).append(m)
            for et, ms in evs.items():
                probs: dict[str, float] = {}
                close = None
                for m in ms:
                    b = _bucket_kalshi(m.get("custom_strike"))
                    if not b:
                        continue
                    close = m.get("close_time") or close
                    try:
                        probs[b] = probs.get(b, 0.0) + float(m["last_price_dollars"])
                    except Exception:  # noqa: BLE001
                        continue
                probs = _norm(probs)
                if probs and close:
                    out[close[:10]] = probs
    except Exception as exc:  # noqa: BLE001
        logger.warning("kalshi fed fetch failed: %s", exc)
    return out


def _norm(p: dict[str, float]) -> dict[str, float]:
    tot = sum(p.values())
    if tot <= 0 or len(p) < 3:
        return {}
    return {k: round(v / tot, 4) for k, v in p.items()}


# ---------- scoring / weights ----------

def brier(probs: dict, outcome: str) -> float:
    return sum((probs.get(b, 0.0) - (1.0 if b == outcome else 0.0)) ** 2
               for b in BUCKETS)


def source_weights(scored: dict | None = None) -> dict:
    """Inverse-Brier weights with shrinkage: each source's Brier pooled with
    PRIOR_N pseudo-meetings at PRIOR_BRIER, then w ∝ 1/shrunk. `scored` may
    extend the frozen backtest with archive-scored meetings."""
    stats = {}
    for src, base in BACKTEST.items():
        extra = (scored or {}).get(src, [])
        n = base["n"] + len(extra)
        tot = (base["brier"] or 0.0) * base["n"] + sum(extra)
        shrunk = (tot + PRIOR_BRIER * PRIOR_N) / (n + PRIOR_N)
        stats[src] = {"n": n, "brier": round(tot / n, 4) if n else None,
                      "shrunk": shrunk}
    inv = {s: 1.0 / v["shrunk"] for s, v in stats.items()}
    z = sum(inv.values())
    return {s: {"weight": round(inv[s] / z, 3), "n": stats[s]["n"],
                "brier": stats[s]["brier"]} for s in stats}


def blend(per_source: dict[str, dict], weights: dict) -> dict:
    """Weighted average across sources for one meeting, renormalized."""
    acc = {b: 0.0 for b in BUCKETS}
    wtot = 0.0
    for src, probs in per_source.items():
        w = weights.get(src, {}).get("weight", 0.0)
        if not probs or w <= 0:
            continue
        wtot += w
        for b in BUCKETS:
            acc[b] += w * probs.get(b, 0.0)
    if wtot <= 0:
        return {}
    return {b: round(v / wtot, 4) for b, v in acc.items()}


# ---------- shift detection (feeds the canary event log) ----------

SHIFT_WARN_PP = 0.10     # any front-meeting bucket moves >=10pp -> WARN event
SHIFT_RED_PP = 0.20      # >=20pp -> RED


def detect_shifts(prev: dict | None, cur: dict | None) -> list[dict]:
    """Compare the current front-meeting blend to the last ALERTED one.
    Returns [{severity, bucket, from, to, meeting}] — empty when quiet.
    Levels are quantized in the dedup key upstream so a slow drift alerts
    once per 10pp band, not once per refresh."""
    if not cur or not cur.get("blend"):
        return []
    if prev is None or prev.get("date") != cur.get("date"):
        return []          # cold start / meeting rollover: reset baseline
                           # quietly (caller re-anchors via mark_alerted)
    pb = prev.get("blend") or {}
    out = []
    for b in BUCKETS:
        new = cur["blend"].get(b, 0.0)
        old = pb.get(b, 0.0)
        d = abs(new - old)
        if d < SHIFT_WARN_PP:
            continue
        sev = "RED" if d >= SHIFT_RED_PP else "WARN"
        out.append({"severity": sev, "bucket": b, "from": round(old, 3),
                    "to": round(new, 3), "meeting": cur.get("date")})
    return out


def shift_state() -> tuple[dict | None, dict]:
    """(last_alerted_front_meeting, store) for the caller to update."""
    store = _load_store()
    return store.get("last_alerted_front"), store


def mark_alerted(store: dict, front: dict) -> None:
    store["last_alerted_front"] = {"date": front.get("date"),
                                   "blend": front.get("blend")}
    _save_store(store)


# ---------- assembly ----------

def ensemble(now: float | None = None) -> dict:
    """Full payload: upcoming meetings x sources x blend + weights + method."""
    now = now or time.time()
    pm, ka = fetch_polymarket(), fetch_kalshi()
    store = _load_store()
    today = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
    # snapshot today's forecasts for future re-scoring
    day = store["snapshots"].setdefault(today, {})
    day["polymarket"], day["kalshi"] = pm, ka
    store["snapshots"] = dict(sorted(store["snapshots"].items())[-400:])
    _save_store(store)

    scored_extra = store.get("scored", {})
    weights = source_weights({k: [s["brier"] for s in v]
                              for k, v in scored_extra.items()}
                             if scored_extra else None)
    # merge meetings across sources by date proximity (PM's endDate and
    # Kalshi's close_time can differ by a day around the same FOMC meeting)
    def _ord(d: str) -> int:
        return datetime.fromisoformat(d).toordinal()

    merged: list[dict] = []
    for src, table in (("kalshi", ka), ("polymarket", pm)):
        for d, probs in table.items():
            hit = next((m for m in merged if abs(_ord(d) - _ord(m["date"])) <= 3),
                       None)
            if hit is None:
                merged.append({"date": d, "sources": {src: probs}})
            else:
                hit["sources"][src] = probs
                hit["date"] = min(hit["date"], d)
    upcoming = sorted(m["date"] for m in merged if m["date"] >= today)
    try:
        from .fed_futures import implied_probs
        fut = implied_probs(upcoming[:6])
    except Exception as exc:  # noqa: BLE001
        logger.warning("futures-implied probs failed: %s", exc)
        fut = {}
    meetings = []
    for m in sorted(merged, key=lambda x: x["date"]):
        if m["date"] < today:
            continue
        per = {"polymarket": m["sources"].get("polymarket") or {},
               "kalshi": m["sources"].get("kalshi") or {},
               "futures": fut.get(m["date"]) or {}}
        meetings.append({"date": m["date"], "sources": per,
                         "blend": blend(per, weights)})
    return {"meetings": meetings[:6], "weights": weights,
            "buckets": BUCKETS, "labels": LABELS,
            "backtest": {**BACKTEST, "asof": "2026-08-05",
                         "basis": "Brier of T-7d price vs realized outcome, "
                                  "resolved FOMC meetings; shrinkage prior "
                                  f"{PRIOR_BRIER} x {PRIOR_N} pseudo-meetings"},
            "display_only": True}
