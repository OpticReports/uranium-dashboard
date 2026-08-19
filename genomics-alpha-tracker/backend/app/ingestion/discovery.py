"""Dynamic universe discovery — finds candidate companies instead of waiting
for a human to remember they exist.

MOTIVATION: the universe was static. MRNA's +130% readout day (2026-08-19) was
missed partly because nobody thought to add the name. This pipeline proposes
candidates into a visible, auditable queue (UniverseCandidate) with evidence;
a conservative, hard-gated auto-promote (config/discovery.yaml, togglable,
weekly-capped) can add names to the live universe. Promotion is reversible:
a promoted Security deactivates like any other, history retained.

Keyless lanes:
  * movers   — Nasdaq healthcare screener census (~1,100 US-listed names,
               cached 24h): big single-day moves on names NOT in the universe.
               This is the miss-detector.
  * catalyst — deterministic daily rotation over the census: ClinicalTrials.gov
               sweep (cached 7 days) for near phase-3 primary completion dates
               and genomics keyword matches.
  * (future lane) news co-mention — not built: wire RSS is blocked from this
    environment and Tiingo is budget-constrained.

Pure scoring/parsing helpers are separated from I/O (same philosophy as
scoring/components.py) so the math is unit-testable with known inputs. Parsers
return None for missing data ("--", "", "NA") — never a silent zero.
"""
from __future__ import annotations

import logging
import zlib
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlmodel import Session, select

from ..config import discovery_config, settings
from ..models import Security, UniverseCandidate
from ..utils import cache
from ..utils.ratelimit import with_backoff

logger = logging.getLogger(__name__)

_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
_CT_BASE = "https://clinicaltrials.gov/api/v2/studies"
# Nasdaq's API rejects default client UAs; a browser UA + JSON accept works.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "application/json",
}

# Config defaults — discovery.yaml overrides any of these (see get_cfg()).
_DEFAULTS: dict[str, Any] = {
    "mover_min_pct": 10.0,
    "min_market_cap": 300e6,
    "rotation_days": 10,
    "catalyst_horizon_days": 240,
    "dismissed_refire_days": 90,
    "auto_promote": True,
    "auto_promote_min_score": 70.0,
    "auto_promote_min_mcap": 2e9,
    "auto_promote_pcd_days": 90,
    "auto_promote_mover_pct": 15.0,
    "auto_promote_fastpath_mcap": 10e9,
    "auto_promote_fastpath_mover_pct": 10.0,
    "auto_promote_per_week": 3,
}

# keyword (matched case-insensitively in company name + trial titles) -> theme
# tag. Tags feed genomics_tags, the relevance term of the score, and become
# the promoted Security's subsector. No match is fine (tags []).
GENOMICS_KEYWORDS: dict[str, str] = {
    "mrna": "mrna",
    "gene therapy": "gene-therapy",
    "gene editing": "gene-editing",
    "crispr": "gene-editing",
    "base editing": "gene-editing",
    "rnai": "rna",
    "sirna": "rna",
    "antisense": "rna",
    "oligonucleotide": "rna",
    "sequencing": "sequencing",
    "genomic": "sequencing",
    "proteomic": "proteomics",
    "cell therapy": "cell-therapy",
    "car-t": "cell-therapy",
    "neoantigen": "oncology-vaccine",
    "cancer vaccine": "oncology-vaccine",
    "liquid biopsy": "liquid-biopsy",
}


def get_cfg() -> dict[str, Any]:
    """Defaults overlaid with config/discovery.yaml (hot-reloaded)."""
    cfg = dict(_DEFAULTS)
    cfg.update(discovery_config())
    return cfg


# --- Pure helpers (unit-tested; no I/O, no ORM) --------------------------------

def parse_money(raw: Any) -> float | None:
    """Nasdaq screener number strings -> float.

    Handles '$1,268.815', '10,588,934,649', '-6.025'. Returns None (no data,
    NEVER silent zero) for '', '--', 'NA', 'N/A', None or garbage.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace("$", "").replace(",", "")
    if s in ("", "--", "NA", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_pct(raw: Any) -> float | None:
    """'2.547%' -> 2.547; '-1.529%' -> -1.529; '--'/''/'NA'/None -> None."""
    if raw is None:
        return None
    return parse_money(str(raw).replace("%", ""))


_STRIP_PHRASES = (
    "american depositary shares", "american depositary share",
    "common stock", "ordinary shares", "ordinary share",
    "depositary shares", "class a", "class b",
)
_STRIP_TRAILING = {
    "inc", "corp", "corporation", "incorporated", "ltd", "limited", "plc",
    "holdings", "holding", "company", "co", "sa", "nv", "ag", "and", "&",
}


def clean_company_name(name: str) -> str:
    """Screener display name -> a plausible CT.gov sponsor query.

    'Moderna, Inc. Common Stock' -> 'Moderna'. Imperfect matching is accepted
    by design (0 CT.gov results is a valid outcome — evidence just lacks
    trials); this only needs to strip the listing boilerplate.
    """
    s = name.replace(",", " ").replace(".", " ")
    low = s.lower()
    for phrase in _STRIP_PHRASES:
        idx = low.find(phrase)
        if idx != -1:
            s, low = s[:idx], low[:idx]
    words = s.split()
    while words and words[-1].lower() in _STRIP_TRAILING:
        words.pop()
    return " ".join(words) or name.strip()


def genomics_tags_for(texts: list[str]) -> list[str]:
    """Deduped, sorted theme tags keyword-matched across the given texts."""
    blob = " ".join(t.lower() for t in texts if t)
    return sorted({tag for kw, tag in GENOMICS_KEYWORDS.items() if kw in blob})


def rotation_bucket(symbol: str, rotation_days: int) -> int:
    """Deterministic bucket for the rotating CT.gov sweep.

    crc32, NOT builtin hash(): str hash is salted per process
    (PYTHONHASHSEED), which would reshuffle the rotation on every restart and
    defeat both the 'every name checked once per rotation' guarantee and the
    7-day CT.gov cache. Same symbol -> same bucket, always.
    """
    return zlib.crc32(symbol.upper().encode("utf-8")) % rotation_days


def score_candidate(
    mcap: float | None,
    nearest_pcd_days: int | None,
    n_genomics_tags: int,
    mover_pct: float | None,
    mover_age_days: int | None,
    mover_min_pct: float = 10.0,
) -> float:
    """Candidate priority score, 0-100. Additive bands, clamped:

      market cap        >=$10B: 25 | >=$2B: 20 | >=$1B: 15 | >=$300M: 10 | else 0
      catalyst proximity nearest phase-3 PCD <=60d: 35 | <=120d: 25 | <=240d: 15 | none: 0
      genomics relevance min(n_tags, 3) * 8   (0-24)
      mover recency      |move| >= mover_min_pct within 7d: 16 | within 30d: 8 | else 0

    None inputs mean "no data for that term" and contribute 0 points — the
    score ranks queue priority; it never fabricates a signal.
    """
    score = 0.0
    if mcap is not None:
        if mcap >= 10e9:
            score += 25
        elif mcap >= 2e9:
            score += 20
        elif mcap >= 1e9:
            score += 15
        elif mcap >= 300e6:
            score += 10
    if nearest_pcd_days is not None and nearest_pcd_days >= 0:
        if nearest_pcd_days <= 60:
            score += 35
        elif nearest_pcd_days <= 120:
            score += 25
        elif nearest_pcd_days <= 240:
            score += 15
    score += min(max(n_genomics_tags, 0), 3) * 8
    if (mover_pct is not None and mover_age_days is not None
            and abs(mover_pct) >= mover_min_pct):
        if mover_age_days <= 7:
            score += 16
        elif mover_age_days <= 30:
            score += 8
    return max(0.0, min(100.0, score))


def _evidence_inputs(evidence: dict, today: date) -> tuple[int | None, float | None, int | None]:
    """(nearest_pcd_days, mover_pct, mover_age_days) derived from stored
    evidence, so re-scoring an existing candidate sees ALL retained signals."""
    pcd_days = None
    if evidence.get("nearest_pcd"):
        try:
            pcd_days = (date.fromisoformat(evidence["nearest_pcd"]) - today).days
        except ValueError:
            pcd_days = None
    mover_pct = evidence.get("move_pct")
    mover_age = None
    if evidence.get("date"):
        try:
            mover_age = (today - date.fromisoformat(evidence["date"])).days
        except ValueError:
            mover_age = None
    return pcd_days, mover_pct, mover_age


# --- Census fetch ---------------------------------------------------------------

def fetch_census() -> list[dict]:
    """Full US-listed healthcare census from the Nasdaq screener.

    ~1,100 names, paginated 100/page (~11 calls), cached 24h so one sweep per
    day hits the network. Returns [{symbol, name, last, pct_change,
    market_cap}] with string fields parsed robustly ('--', '', 'NA', '$',
    commas -> None/float). On failure the lane goes dark for the run (logged
    warning, []) — discovery never crashes ingestion.
    """
    def _producer() -> list[dict]:
        rows: list[dict] = []
        offset, total = 0, None
        while total is None or offset < total:
            params = {"tableonly": "true", "limit": "100", "offset": str(offset),
                      "sector": "health_care"}
            resp = with_backoff(
                lambda: httpx.get(_SCREENER_URL, params=params, headers=_HEADERS,
                                  timeout=settings.http_timeout_seconds),
                retries=2,
            )
            resp.raise_for_status()
            data = (resp.json() or {}).get("data") or {}
            total = int(data.get("totalrecords") or 0)
            page = (data.get("table") or {}).get("rows") or []
            if not page:
                break
            rows.extend(page)
            offset += 100
            if offset > 5000:  # hard guard against a runaway totalrecords
                break
        if not rows:
            # Never cache an empty census: a transient API hiccup would
            # otherwise blind the movers lane for a full 24h TTL.
            raise RuntimeError("census returned 0 rows")
        return rows

    try:
        raw = cache.cached("discovery:census", _producer, ttl=86400)
    except Exception as exc:  # noqa: BLE001
        logger.warning("discovery census fetch failed: %s — movers/catalyst lanes dark this run", exc)
        return []

    out = []
    for row in raw or []:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "name": str(row.get("name") or sym).strip(),
            "last": parse_money(row.get("lastsale")),
            "pct_change": parse_pct(row.get("pctchange")),
            "market_cap": parse_money(row.get("marketCap")),
        })
    return out


def _fetch_ctgov_trials(cleaned_name: str) -> list[dict]:
    """Active trials sponsored by (a fuzzy match of) the company. Cached 7
    days per name — with the 10-day rotation, each name costs ~1 CT.gov call
    per cycle. [] (a valid outcome: no trials found) is cached too."""
    key = f"discovery:ctgov:{cleaned_name}"

    def _producer():
        params = {
            "query.spons": cleaned_name,
            "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING|ENROLLING_BY_INVITATION",
            # Big sponsors run hundreds of active trials (Merck: ~700); an
            # unsorted first page corrupts nearest-PCD. Restrict to future
            # PCDs and sort ascending so page 1 IS the nearest horizon. The
            # range start staleness is bounded by the 7d cache TTL; past
            # PCDs are re-filtered downstream anyway.
            "filter.advanced": f"AREA[PrimaryCompletionDate]RANGE[{date.today().isoformat()},MAX]",
            "sort": "PrimaryCompletionDate:asc",
            "fields": "NCTId|BriefTitle|Phase|PrimaryCompletionDate|OverallStatus|LeadSponsorName",
            "pageSize": "50",
        }
        # NO browser UA here: ClinicalTrials.gov's WAF 403s a Chrome UA sent
        # from a non-browser client (verified live 2026-08-19); the plain
        # httpx default passes. The browser UA is a Nasdaq-only requirement.
        resp = with_backoff(
            lambda: httpx.get(_CT_BASE, params=params,
                              timeout=settings.http_timeout_seconds),
            retries=2,
        )
        resp.raise_for_status()
        return resp.json().get("studies", [])

    try:
        return cache.cached(key, _producer, ttl=7 * 86400)
    except Exception as exc:  # noqa: BLE001
        logger.warning("discovery CT.gov fetch failed for %s: %s", cleaned_name, exc)
        return []


_DRUG_INTERVENTIONS = {"DRUG", "BIOLOGICAL", "GENETIC"}


def _has_drug_trial(cleaned_name: str) -> bool | None:
    """Clinical-stage discriminator for the auto-promote fast-path.

    True when the company sponsors/collaborates on ANY active trial with a
    DRUG/BIOLOGICAL/GENETIC intervention. Verified live 2026-08-19:
    UnitedHealth 0 trials -> blocked; HCA 2 DEVICE-only trials -> blocked;
    Moderna's single "Moderna"-matched trial is DRUG -> passes. Residual: a
    device maker with one drug-arm trial (Intuitive Surgical) can still slip —
    bounded by the weekly cap and one-click deactivation, documented in
    discovery.yaml. None = lane dark; the CALLER MUST FAIL CLOSED (a fast-path
    promotion is never made on missing evidence)."""
    key = f"discovery:drugtrial:{cleaned_name}"

    def _producer():
        params = {
            "query.spons": cleaned_name,
            "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING|ENROLLING_BY_INVITATION",
            "fields": "NCTId|InterventionType",
            "pageSize": "30",
        }
        # NO browser UA here: ClinicalTrials.gov's WAF 403s a Chrome UA sent
        # from a non-browser client (verified live 2026-08-19); the plain
        # httpx default passes. The browser UA is a Nasdaq-only requirement.
        resp = with_backoff(
            lambda: httpx.get(_CT_BASE, params=params,
                              timeout=settings.http_timeout_seconds),
            retries=2,
        )
        resp.raise_for_status()
        for study in resp.json().get("studies", []) or []:
            arms = ((study.get("protocolSection", {}) or {})
                    .get("armsInterventionsModule", {}) or {})
            for iv in arms.get("interventions", []) or []:
                if str(iv.get("type") or "").upper() in _DRUG_INTERVENTIONS:
                    return True
        return False

    try:
        return cache.cached(key, _producer, ttl=7 * 86400)
    except Exception as exc:  # noqa: BLE001
        logger.warning("discovery drug-trial check failed for %s: %s — fast-path fails closed",
                       cleaned_name, exc)
        return None


def _summarize_trials(studies: list[dict], today: date) -> list[dict]:
    """CT.gov studies -> compact evidence rows {nct, phase, pcd, title}."""
    rows = []
    for study in studies or []:
        ps = study.get("protocolSection", {}) or {}
        ident = ps.get("identificationModule", {}) or {}
        status = ps.get("statusModule", {}) or {}
        design = ps.get("designModule", {}) or {}
        pcd_raw = (status.get("primaryCompletionDateStruct") or {}).get("date")
        pcd = _parse_loose_date(pcd_raw)
        rows.append({
            "nct": ident.get("nctId", ""),
            "phase": "/".join(design.get("phases") or []),
            "pcd": pcd.isoformat() if pcd else None,
            "title": (ident.get("briefTitle") or "")[:120],
        })
    # Nearest completion first; undated trials last.
    rows.sort(key=lambda r: r["pcd"] or "9999-12-31")
    return rows


def _parse_loose_date(value) -> date | None:
    """CT.gov dates are 'YYYY-MM' or 'YYYY-MM-DD' (mid-month for the former)."""
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


# --- Candidate lanes -------------------------------------------------------------

def movers_lane(census: list[dict], universe_symbols: set[str], cfg: dict,
                today: date) -> dict[str, dict]:
    """The MISS-DETECTOR: census names with a big same-day move that are NOT
    in the universe (any active state). A move the desk can't explain from
    coverage is exactly the MRNA-shaped gap this pipeline exists to close."""
    out: dict[str, dict] = {}
    for row in census:
        if row["symbol"] in universe_symbols:
            continue
        pct, mcap = row["pct_change"], row["market_cap"]
        if pct is None or mcap is None:  # no data is not a zero — skip, don't guess
            continue
        if abs(pct) < cfg["mover_min_pct"] or mcap < cfg["min_market_cap"]:
            continue
        out[row["symbol"]] = {
            "name": row["name"],
            "market_cap": mcap,
            "last_price": row["last"],
            "sources": {"mover"},
            "genomics_tags": set(genomics_tags_for([row["name"]])),
            "evidence": {"move_pct": pct, "date": today.isoformat(), "market_cap": mcap},
        }
    return out


def catalyst_lane(census: list[dict], universe_symbols: set[str], cfg: dict,
                  today: date) -> tuple[dict[str, dict], int]:
    """ROTATING CT.gov sweep over the census (today's deterministic bucket).

    A name is a candidate if it has a phase-3 trial completing within
    catalyst_horizon_days, OR any active PHASE2/PHASE3 trial plus a genomics
    keyword match. Returns (candidates, names_checked)."""
    rotation_days = int(cfg["rotation_days"])
    bucket_today = today.toordinal() % rotation_days
    out: dict[str, dict] = {}
    checked = 0
    for row in census:
        if row["symbol"] in universe_symbols:
            continue
        mcap = row["market_cap"]
        if mcap is None or mcap < cfg["min_market_cap"]:
            continue
        if rotation_bucket(row["symbol"], rotation_days) != bucket_today:
            continue
        checked += 1
        cleaned = clean_company_name(row["name"])
        trials = _summarize_trials(_fetch_ctgov_trials(cleaned), today)

        p3_pcds = [t["pcd"] for t in trials
                   if "PHASE3" in t["phase"] and t["pcd"] and t["pcd"] >= today.isoformat()]
        nearest_pcd = min(p3_pcds) if p3_pcds else None
        near_p3 = (nearest_pcd is not None and
                   (date.fromisoformat(nearest_pcd) - today).days <= cfg["catalyst_horizon_days"])
        active_p23 = any("PHASE3" in t["phase"] or "PHASE2" in t["phase"] for t in trials)
        tags = set(genomics_tags_for([row["name"]] + [t["title"] for t in trials]))

        if not (near_p3 or (active_p23 and tags)):
            continue
        out[row["symbol"]] = {
            "name": row["name"],
            "market_cap": mcap,
            "last_price": row["last"],
            "sources": {"catalyst"},
            "genomics_tags": tags,
            "evidence": {"trials": trials[:5], "nearest_pcd": nearest_pcd},
        }
    return out, checked


def _merge_lanes(*lanes: dict[str, dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for lane in lanes:
        for sym, cand in lane.items():
            if sym not in merged:
                merged[sym] = {**cand, "sources": set(cand["sources"]),
                               "genomics_tags": set(cand["genomics_tags"]),
                               "evidence": dict(cand["evidence"])}
            else:
                m = merged[sym]
                m["sources"] |= cand["sources"]
                m["genomics_tags"] |= cand["genomics_tags"]
                m["evidence"].update(cand["evidence"])
                if m.get("market_cap") is None:
                    m["market_cap"] = cand.get("market_cap")
                if m.get("last_price") is None:
                    m["last_price"] = cand.get("last_price")
    return merged


# --- Persistence ------------------------------------------------------------------

def upsert_candidates(session: Session, candidates: dict[str, dict], cfg: dict,
                      today: date | None = None) -> tuple[int, int]:
    """Write lane output into the queue. Returns (new, updated).

    Dedupe rules:
      * anything already a Security (active OR inactive) never enters —
        inactive means the desk deliberately parked it, not that it's unknown;
      * a dismissed candidate is suppressed for dismissed_refire_days, then a
        fresh signal may resurface it as "new" with status_reason cleared;
      * existing non-dismissed candidates get last_seen/score/evidence
        refreshed and sources/tags unioned — status is the desk's, we keep it.
    """
    today = today or date.today()
    universe = {s.symbol for s in session.exec(select(Security)).all()}
    n_new = n_updated = 0
    for sym, cand in sorted(candidates.items()):
        if sym in universe:
            continue
        existing = session.get(UniverseCandidate, sym)
        merged_evidence = dict((existing.evidence if existing else {}) or {})
        merged_evidence.update(cand["evidence"])
        tags = sorted(set((existing.genomics_tags if existing else []) or []) | cand["genomics_tags"])
        pcd_days, mover_pct, mover_age = _evidence_inputs(merged_evidence, today)
        score = score_candidate(cand.get("market_cap"), pcd_days, len(tags),
                                mover_pct, mover_age,
                                mover_min_pct=cfg["mover_min_pct"])
        if existing is None:
            session.add(UniverseCandidate(
                symbol=sym, name=cand["name"], market_cap=cand.get("market_cap"),
                last_price=cand.get("last_price"), score=score, status="new",
                sources=sorted(cand["sources"]), genomics_tags=tags,
                evidence=merged_evidence, first_seen=today, last_seen=today,
            ))
            n_new += 1
            continue
        if existing.status == "dismissed":
            age = (today - existing.status_changed_at.date()).days
            if age < cfg["dismissed_refire_days"]:
                continue  # dismissal window still holds — do not resurface
            existing.status = "new"          # fresh signal after the window
            existing.status_reason = None    # old dismissal reason no longer applies
            existing.status_changed_at = datetime.utcnow()
        existing.name = cand["name"] or existing.name
        if cand.get("market_cap") is not None:
            existing.market_cap = cand["market_cap"]
        if cand.get("last_price") is not None:
            existing.last_price = cand["last_price"]
        existing.score = score
        existing.sources = sorted(set(existing.sources or []) | cand["sources"])
        existing.genomics_tags = tags
        existing.evidence = merged_evidence
        existing.last_seen = today
        session.add(existing)
        n_updated += 1
    session.commit()
    return n_new, n_updated


def promote_candidate(session: Session, cand: UniverseCandidate, reason: str) -> Security:
    """Shared promote path (auto + manual): add to the live universe and stamp
    the candidate. NO backfill kick here — the scheduler's normal ingestion
    cycle picks the new name up within the hour, and promotion must stay cheap
    and side-effect-light so it is trivially reversible (deactivate)."""
    from ..universe import manager

    sec = manager.upsert_security(
        session, symbol=cand.symbol, name=clean_company_name(cand.name),
        subsector=list(cand.genomics_tags) or ["discovery"], active=True,
    )
    cand.status = "promoted"
    cand.status_reason = reason
    cand.status_changed_at = datetime.utcnow()
    session.add(cand)
    session.commit()
    return sec


def auto_promote(session: Session, cfg: dict | None = None,
                 today: date | None = None) -> list[str]:
    """Config-gated, hard-gated, weekly-capped auto-promotion.

    Two ways in (see discovery.yaml for the MRNA-in-June calibration):

    Standard path — ALL gates must hold:
      score >= auto_promote_min_score
      AND market_cap >= auto_promote_min_mcap
      AND (nearest phase-3 PCD <= auto_promote_pcd_days
           OR |latest mover move| >= auto_promote_mover_pct)

    Mega-cap mover fast-path — the score gate is skipped:
      market_cap >= auto_promote_fastpath_mcap
      AND |move| >= auto_promote_fastpath_mover_pct within the last 7 days
      AND the company sponsors at least one active DRUG/BIOLOGICAL/GENETIC
          trial (_has_drug_trial; FAILS CLOSED when CT.gov is dark — without
          this gate a +-10% day on an insurer or hospital system would
          auto-add it to a genomics universe).
    Rationale: the score leans on CT.gov catalyst/tag data, which under-detects
    names whose registered sponsor differs from the screener name (the
    Moderna/ModernaTX problem hits discovery too — "Moderna" returns one
    partnered CF trial). A double-digit day on a $10B+ healthcare name is rare,
    information-dense, and coverage is near-free; replayed on 2026-06-17 MRNA
    ($23.8B, +11.6%) the standard path scores 41 and FAILS — only this path
    would have added it two months before the readout.

    Ordering: fast-path candidates are considered FIRST — they are the rarest
    and most information-dense signal, and by construction they score low, so
    score ordering would starve them of scarce weekly slots.

    Only status "new" is considered: "watch" is the desk's deliberate holding
    judgment and auto-promote never overrides it.

    Cap: at most auto_promote_per_week promotions per rolling 7 days — auto
    and manual both count (simplest honest reading; the desk's own adds also
    grow the universe). The fast-path respects the cap too.
    Returns promoted symbols."""
    cfg = cfg or get_cfg()
    today = today or date.today()
    if not cfg["auto_promote"]:
        return []

    week_ago = datetime.utcnow() - timedelta(days=7)
    promoted_this_week = len(session.exec(
        select(UniverseCandidate)
        .where(UniverseCandidate.status == "promoted")
        .where(UniverseCandidate.status_changed_at >= week_ago)
    ).all())
    slots = int(cfg["auto_promote_per_week"]) - promoted_this_week
    if slots <= 0:
        return []

    queue = session.exec(
        select(UniverseCandidate)
        .where(UniverseCandidate.status == "new")
    ).all()

    def _fast_precheck(c: UniverseCandidate) -> bool:
        pcd_days, mover_pct, mover_age = _evidence_inputs(c.evidence or {}, today)
        return (
            c.market_cap is not None
            and c.market_cap >= cfg["auto_promote_fastpath_mcap"]
            and mover_pct is not None
            and abs(mover_pct) >= cfg["auto_promote_fastpath_mover_pct"]
            and mover_age is not None
            and mover_age <= 7
        )

    # Fast-path eligibles first (they score low by construction and would be
    # starved by score ordering), then standard by score.
    queue.sort(key=lambda c: (not _fast_precheck(c), -(c.score or 0.0)))

    promoted: list[str] = []
    for cand in queue:
        if len(promoted) >= slots:
            break
        score = cand.score
        mcap = cand.market_cap
        pcd_days, mover_pct, mover_age = _evidence_inputs(cand.evidence or {}, today)

        # Mega-cap mover fast-path (score gate skipped — see docstring).
        if _fast_precheck(cand):
            drug_trial = _has_drug_trial(clean_company_name(cand.name))
            ev = dict(cand.evidence or {})
            ev["drug_trial_check"] = {"result": drug_trial, "date": today.isoformat()}
            cand.evidence = ev
            session.add(cand)
            if drug_trial is True:
                reason = (
                    f"auto: mega-cap mover fast-path — mcap ${mcap / 1e9:.1f}B>="
                    f"${cfg['auto_promote_fastpath_mcap'] / 1e9:.0f}B, move "
                    f"{mover_pct:+.1f}%>={cfg['auto_promote_fastpath_mover_pct']:.0f}% "
                    f"({mover_age}d ago), active drug/biologic trial confirmed"
                )
                promote_candidate(session, cand, reason)
                logger.info("discovery auto-promote: %s (%s) — %s", cand.symbol, cand.name, reason)
                promoted.append(cand.symbol)
                continue
            logger.info(
                "discovery fast-path declined for %s: drug-trial check = %s (fails closed)",
                cand.symbol, drug_trial,
            )
            session.commit()
            # falls through to the standard path (which its low score usually fails)

        if score is None or score < cfg["auto_promote_min_score"]:
            continue
        if mcap is None or mcap < cfg["auto_promote_min_mcap"]:
            continue
        near_p3 = pcd_days is not None and 0 <= pcd_days <= cfg["auto_promote_pcd_days"]
        # A mover print only satisfies the standard gate while it is fresh —
        # stale evidence must not promote weeks after the move.
        big_move = (mover_pct is not None
                    and abs(mover_pct) >= cfg["auto_promote_mover_pct"]
                    and mover_age is not None and mover_age <= 7)
        if not (near_p3 or big_move):
            continue
        gates = [f"score {score:.0f}>={cfg['auto_promote_min_score']:.0f}",
                 f"mcap ${mcap / 1e9:.1f}B>=${cfg['auto_promote_min_mcap'] / 1e9:.0f}B"]
        if near_p3:
            gates.append(f"phase-3 PCD in {pcd_days}d<={cfg['auto_promote_pcd_days']}d")
        if big_move:
            gates.append(f"move {mover_pct:+.1f}% >= {cfg['auto_promote_mover_pct']:.0f}%")
        reason = "auto: " + ", ".join(gates)
        promote_candidate(session, cand, reason)
        logger.info("discovery auto-promote: %s (%s) — %s", cand.symbol, cand.name, reason)
        promoted.append(cand.symbol)
    return promoted


# --- Orchestrator ------------------------------------------------------------------

def run_discovery(session: Session) -> dict:
    """One discovery sweep: census -> lanes -> queue upsert -> auto-promote.

    Returns {census, movers, catalyst_checked, candidates_new,
    candidates_updated, auto_promoted}. Any dark lane contributes zeros —
    the sweep itself never raises."""
    cfg = get_cfg()
    today = date.today()
    census = fetch_census()
    universe = {s.symbol for s in session.exec(select(Security)).all()}

    movers = movers_lane(census, universe, cfg, today)
    cats, checked = catalyst_lane(census, universe, cfg, today)
    merged = _merge_lanes(movers, cats)
    n_new, n_updated = upsert_candidates(session, merged, cfg, today)
    promoted = auto_promote(session, cfg, today)

    summary = {
        "census": len(census),
        "movers": len(movers),
        "catalyst_checked": checked,
        "candidates_new": n_new,
        "candidates_updated": n_updated,
        "auto_promoted": promoted,
    }
    # Last-run breadcrumb for GET /discovery/summary (file cache survives the
    # process; a huge TTL read makes it effectively "most recent run").
    cache.set("discovery:last_run", {**summary, "at": datetime.utcnow().isoformat()})
    logger.info("discovery sweep: %s", summary)
    return summary
