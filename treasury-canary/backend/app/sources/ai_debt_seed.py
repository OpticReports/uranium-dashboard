"""Frozen AI-debt issuance tally (studies/ai-debt-flows.md rev 1) and the
aggregations the AI-debt tab draws from it.

The seed is ai_debt_seed.json, written by studies/ai_debt_flows/export_seed.py
from the study's deals.csv; nothing here fetches. Numbers are $bn gross at
pricing, non-USD legs at trade-date FX (each record's fx_basis names the
FRED series). A bucket x year or bucket x month cell with no included deal
is a true zero of the tally, not missing data; the share functions use USD
legs only over SIFMA's US-only denominator (memo C10: an all-currency
numerator over that denominator is not a share of anything).
"""
from __future__ import annotations

import json
import os
import re
import threading

_PATH = os.path.join(os.path.dirname(__file__), "ai_debt_seed.json")
_cache: dict[str, dict | None] = {"seed": None}
_lock = threading.Lock()


def load_seed(force: bool = False) -> dict:
    """The seed JSON, read once per process."""
    with _lock:
        if _cache["seed"] is None or force:
            with open(_PATH, encoding="utf-8") as f:
                _cache["seed"] = json.load(f)
        return _cache["seed"]  # type: ignore[return-value]


def included(seed: dict | None = None) -> list[dict]:
    seed = seed or load_seed()
    return [d for d in seed["deals"] if d["included"]]


def years(seed: dict | None = None) -> list[str]:
    return sorted({d["date"][:4] for d in included(seed)})


def _r(x: float) -> float:
    return round(x + 0.0, 2)


def totals_by_year(seed: dict | None = None) -> dict[str, float]:
    """{'2024': 39.73, '2025': 242.8, '2026': 399.97} — $bn, all currencies at FX."""
    out = {y: 0.0 for y in years(seed)}
    for d in included(seed):
        out[d["date"][:4]] += d["size_usd_bn"]
    return {y: _r(v) for y, v in out.items()}


def by_bucket_year(seed: dict | None = None) -> dict[str, dict[str, float]]:
    """{bucket: {year: $bn}} over every bucket in the seed's list (memo §3a)."""
    seed = seed or load_seed()
    ys = years(seed)
    out = {b: {y: 0.0 for y in ys} for b in seed["buckets"]}
    for d in included(seed):
        out[d["bucket"]][d["date"][:4]] += d["size_usd_bn"]
    return {b: {y: _r(v) for y, v in row.items()} for b, row in out.items()}


def by_rating_year(seed: dict | None = None) -> dict[str, dict[str, float]]:
    """{rating bucket: {year: $bn}} (memo §3b); an included deal with no rating
    concept at all would land in 'not-captured' rather than vanish."""
    seed = seed or load_seed()
    ys = years(seed)
    out = {rb: {y: 0.0 for y in ys} for rb in seed["rating_buckets"]}
    for d in included(seed):
        out[d["rating_bucket"] or "not-captured"][d["date"][:4]] += d["size_usd_bn"]
    return {rb: {y: _r(v) for y, v in row.items()} for rb, row in out.items()}


def _months(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def by_month(seed: dict | None = None, key: str = "bucket") -> list[dict]:
    """[{month: 'YYYY-MM', <category>: $bn, ...}] for every month from the first
    deal to the seed's as-of month, categories = buckets (default) or rating
    buckets (key='rating_bucket'); the stacked-bar input."""
    seed = seed or load_seed()
    if key not in ("bucket", "rating_bucket"):
        raise ValueError(f"by_month key must be 'bucket' or 'rating_bucket', got {key!r}")
    cats = seed["buckets"] if key == "bucket" else seed["rating_buckets"]
    # the axis runs to the LATER of the as-of month and the last deal's month, so a
    # seed whose exporter forgot to bump ASOF can never KeyError the payload build
    last = max(seed["asof"][:7], seed["last_deal_date"][:7])
    rows = {m: {c: 0.0 for c in cats} for m in _months(seed["first_deal_date"][:7], last)}
    for d in included(seed):
        rows.setdefault(d["date"][:7], {c: 0.0 for c in cats})[d[key] or "not-captured"] += d["size_usd_bn"]
    return [{"month": m, **{c: _r(v) for c, v in row.items()}} for m, row in rows.items()]


def hyperscaler_usd_share(seed: dict | None = None) -> dict[str, dict]:
    """Memo §3c: USD legs over SIFMA US corporate issuance, per denominator year.
    pct_hyperscaler = Meta/Alphabet/Amazon/Oracle USD legs; pct_all = every
    included USD leg. all_ai_bn (all currencies) is reported for context only
    and never divided by the US-only denominator."""
    seed = seed or load_seed()
    den = seed["share_denominators"]
    out: dict[str, dict] = {}
    for y, sifma in den["sifma_us_corp_bn"].items():
        inc = [d for d in included(seed) if d["date"][:4] == y]
        hyper_usd = sum(d["size_usd_bn"] for d in inc if d["bucket"] == "hyperscaler" and d["ccy"] == "USD")
        all_usd = sum(d["size_usd_bn"] for d in inc if d["ccy"] == "USD")
        all_ccy = sum(d["size_usd_bn"] for d in inc)
        out[y] = {
            "hyperscaler_usd_bn": _r(hyper_usd),
            "all_ai_usd_bn": _r(all_usd),
            "all_ai_bn": _r(all_ccy),
            "sifma_us_corp_bn": sifma,
            "pct_hyperscaler": round(100.0 * hyper_usd / sifma, 2) if sifma else None,
            "pct_all": round(100.0 * all_usd / sifma, 2) if sifma else None,
            "basis": "USD legs / SIFMA US corporate issuance; " + den["basis"][y],
            "src": den["src"][y],
        }
    return out


def verif_mix(seed: dict | None = None) -> dict:
    """Share of included dollars by provenance: P fetched primary filing,
    R fetched press, S search snippet only."""
    tot = sum(d["size_usd_bn"] for d in included(seed))
    out = {k: 0.0 for k in ("P", "R", "S")}
    for d in included(seed):
        out[d["verif"]] += d["size_usd_bn"]
    return {k: round(100.0 * v / tot, 1) for k, v in out.items()} | {"basis": "% of included $bn"}


_SIZE_RE = re.compile(r"(?:C\$|US\$|\$|€|£|¥)\s?(\d+(?:\.\d+)?)\s?B\b", re.I)


def tranche_sizes(tranches: str | None) -> list[float]:
    """Per-tranche sizes (bn, in the deal's own currency) from the seed's
    free-text tranches field, e.g. '6: 2031 $3.0B 4.55%; ...' -> [3.0, ...].
    Used by the gate test that re-derives each parsed FWP headline."""
    return [float(m.group(1)) for m in _SIZE_RE.finditer(tranches or "")]


def find_deal(date: str, issuer: str, seed: dict | None = None) -> dict | None:
    seed = seed or load_seed()
    for d in seed["deals"]:
        if d["date"] == date and d["issuer"] == issuer:
            return d
    return None


def spread_at_issue_30y(seed: dict | None = None) -> list[dict]:
    """Frozen 30y-tranche spreads at issue (bp over UST) with their FWP URLs."""
    return list((seed or load_seed())["spread_at_issue_30y"])


def share_denominators(seed: dict | None = None) -> dict:
    return dict((seed or load_seed())["share_denominators"])
