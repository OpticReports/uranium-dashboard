"""Scan orchestration: discovery -> registry sweep -> rollup -> ladder -> alert.

Three lanes, because DEX Screener has no "list every new pair on chain X"
endpoint and pretending otherwise would silently miss launches:

  1. DISCOVERY grows the registry of tokenized equities from cheap sources —
     the boosted-token feed, the "stonks" meta, and a "Robinhood Token" name
     search that enumerates the official wrappers directly.
  2. ROLLING UNIVERSE SWEEP walks the ~10.4k SEC tickers a slice at a time
     with a persisted cursor, so full coverage is reached in about a day
     without ever spending more than one slice of rate budget per pass. This
     is the lane that would have found the UNOFFICIAL Farmmi wrapper, which
     no boost or meta feed carried.
  3. REGISTRY SWEEP walks every equity token we already know via
     /token-pairs/v1 and finds the memes pooled against it. This is the lane
     that actually detects launches.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import httpx
from sqlmodel import Session, select

from . import alerts
from .config import screener_config, settings
from .engine import detect, ladder, registry, scoring
from .lanes import dexscreener, equity as equity_lane, fundamentals
from .models import (Candidate, EquityToken, MemeLaunch, PoolSnapshot,
                     ScanState, StageEvent)

logger = logging.getLogger(__name__)

_CURSOR_KEY = "universe_sweep_cursor"
_PRIORITY_CURSOR_KEY = "priority_sweep_cursor"


def _cfg() -> dict:
    return screener_config()


def _markers() -> list[registry.IssuerMarker]:
    return registry.markers_from_config(_cfg().get("issuer_markers", []))


def _base_assets() -> set[str]:
    return {str(s).upper() for s in _cfg().get("base_assets", [])}


def _chains() -> set[str]:
    return {str(c).lower() for c in _cfg().get("scan", {}).get("chains", [])}


def _get_state(session: Session, key: str, default: str = "") -> str:
    row = session.get(ScanState, key)
    return row.value if row else default


def _set_state(session: Session, key: str, value: str) -> None:
    row = session.get(ScanState, key)
    if row is None:
        row = ScanState(key=key, value=value)
    else:
        row.value = value
        row.updated_at = datetime.utcnow()
    session.add(row)


# --------------------------------------------------------------------------
# 1 + 2. Registry growth
# --------------------------------------------------------------------------

def _deepest_pair_urls(pairs: list[dict]) -> dict[str, str]:
    """Deepest pool per token address — the link that lands on that token.
    DEX Screener's token-address pages refuse non-browser requests, so a pair
    URL is the only one that reliably resolves."""
    best: dict[str, tuple[float, str]] = {}
    for p in pairs or []:
        url = str(p.get("url") or "")
        if not url:
            continue
        liq = float((p.get("liquidity") or {}).get("usd") or 0.0)
        for side in ("baseToken", "quoteToken"):
            addr = str((p.get(side) or {}).get("address") or "").lower()
            if addr and (addr not in best or liq > best[addr][0]):
                best[addr] = (liq, url)
    return {a: u for a, (_, u) in best.items()}


def _upsert_equity_tokens(session: Session, views: list[registry.EquityTokenView],
                          pair_times: dict[str, datetime | None],
                          token_urls: dict[str, str] | None = None) -> list[EquityToken]:
    fresh: list[EquityToken] = []
    for v in views:
        if v.chain_id.lower() not in _chains():
            continue
        row = session.exec(
            select(EquityToken).where(EquityToken.chain_id == v.chain_id,
                                      EquityToken.address == v.address)).first()
        created = pair_times.get(v.address.lower())
        url = (token_urls or {}).get(v.address.lower(), "")
        if row is None:
            row = EquityToken(
                chain_id=v.chain_id, address=v.address, symbol=v.symbol,
                token_name=v.token_name, ticker=v.ticker, company=v.company,
                issuer_class=v.issuer_class, first_pair_at=created, url=url)
            session.add(row)
            fresh.append(row)
            logger.info("registry: NEW tokenized equity %s (%s) on %s [%s]",
                        v.ticker, v.token_name, v.chain_id, v.issuer_class)
        else:
            row.issuer_class = v.issuer_class
            row.token_name = v.token_name
            if url:
                row.url = url
            if created and (row.first_pair_at is None or created < row.first_pair_at):
                row.first_pair_at = created
            session.add(row)
    return fresh


def _pair_creation_times(pairs: list[dict]) -> dict[str, datetime | None]:
    """Earliest pairCreatedAt per token address — proxies deployment time."""
    out: dict[str, datetime | None] = {}
    for p in pairs or []:
        created = detect._ts(p.get("pairCreatedAt"))
        if created is None:
            continue
        for side in ("baseToken", "quoteToken"):
            addr = str((p.get(side) or {}).get("address") or "").lower()
            if not addr:
                continue
            if out.get(addr) is None or created < out[addr]:
                out[addr] = created
    return out


def discovery_sweep(session: Session) -> dict:
    """Cheap lanes: boosted tokens, the stonks meta, official-wrapper search."""
    universe = equity_lane.sec_universe()
    if not universe:
        logger.warning("SEC universe dark — discovery sweep skipped this pass")
        return {"registry_new": 0, "universe_dark": True}

    markers, bases, chains = _markers(), _base_assets(), _chains()
    pairs: list[dict] = []
    pairs += dexscreener.meta_pairs("stonks")
    for m in markers:
        pairs += dexscreener.search(m.marker)
    for boost in dexscreener.token_boosts_latest():
        chain = str(boost.get("chainId") or "").lower()
        addr = str(boost.get("tokenAddress") or "")
        if chain in chains and addr:
            pairs += dexscreener.token_pairs(chain, addr)

    views = detect.equity_tokens_in(pairs, universe, markers, bases)
    fresh = _upsert_equity_tokens(session, views, _pair_creation_times(pairs),
                                  _deepest_pair_urls(pairs))
    session.commit()
    return {"registry_new": len(fresh), "pairs_seen": len(pairs)}


def universe_sweep(session: Session, slice_size: int | None = None) -> dict:
    """Walk the SEC ticker list a slice at a time with a persisted cursor."""
    universe = equity_lane.sec_universe()
    if not universe:
        return {"registry_new": 0, "universe_dark": True}

    tickers = sorted(universe)
    n = slice_size or int(_cfg().get("scan", {}).get("seed_tickers_top_n", 250))
    try:
        cursor = int(_get_state(session, _CURSOR_KEY, "0"))
    except ValueError:
        cursor = 0
    cursor %= max(len(tickers), 1)
    slice_ = tickers[cursor:cursor + n]

    markers, bases = _markers(), _base_assets()
    pairs: list[dict] = []
    for ticker in slice_:
        pairs += dexscreener.search(ticker)

    views = detect.equity_tokens_in(pairs, universe, markers, bases)
    fresh = _upsert_equity_tokens(session, views, _pair_creation_times(pairs),
                                  _deepest_pair_urls(pairs))
    _set_state(session, _CURSOR_KEY, str((cursor + n) % max(len(tickers), 1)))
    session.commit()
    return {"registry_new": len(fresh), "swept": len(slice_),
            "cursor": cursor, "universe_size": len(tickers)}


def priority_sweep(session: Session, slice_size: int | None = None) -> dict:
    """Sweep the SMALLEST US listings first, cursored.

    The alphabetical universe sweep is the completeness backstop; this is the
    one that finds anything worth looking at on day one. Ordered by market cap
    ascending, so the Farmmi shape - an unofficial wrapper on a nanocap nobody
    would tokenize by accident - is reached in the first pass rather than the
    fortieth. Falls back to a no-op (the alphabetical sweep still runs) when no
    FMP key is configured.
    """
    universe = equity_lane.sec_universe()
    if not universe:
        return {"registry_new": 0, "universe_dark": True}
    cfg = _cfg().get("scan", {})
    tickers = fundamentals.microcap_universe()
    if not tickers:
        return {"registry_new": 0, "priority_dark": True,
                "note": "no FMP key - alphabetical sweep covers this"}

    n = int(slice_size or cfg.get("priority_slice", 250))
    try:
        cursor = int(_get_state(session, _PRIORITY_CURSOR_KEY, "0"))
    except ValueError:
        cursor = 0
    cursor %= max(len(tickers), 1)
    slice_ = tickers[cursor:cursor + n]

    markers, bases = _markers(), _base_assets()
    pairs: list[dict] = []
    for ticker in slice_:
        pairs += dexscreener.search(ticker)

    views = detect.equity_tokens_in(pairs, universe, markers, bases)
    fresh = _upsert_equity_tokens(session, views, _pair_creation_times(pairs),
                                  _deepest_pair_urls(pairs))
    _set_state(session, _PRIORITY_CURSOR_KEY,
               str((cursor + n) % max(len(tickers), 1)))
    session.commit()
    return {"registry_new": len(fresh), "swept": len(slice_),
            "cursor": cursor, "microcap_universe": len(tickers)}


# --------------------------------------------------------------------------
# 3. Launch detection
# --------------------------------------------------------------------------

def registry_sweep(session: Session) -> dict:
    """For every known tokenized equity, find the memes pooled against it."""
    universe = equity_lane.sec_universe()
    markers, bases = _markers(), _base_assets()
    cap = int(_cfg().get("scan", {}).get("max_registry_tokens", 400))

    tokens = session.exec(
        select(EquityToken).order_by(EquityToken.first_seen_at.desc()).limit(cap)
    ).all()

    seen_launches = 0
    new_launches = 0
    for tok in tokens:
        pairs = dexscreener.token_pairs(tok.chain_id, tok.address)
        if not pairs:
            continue
        # Registry can grow from here too — a meme's OTHER pools may quote a
        # wrapper we have not met.
        if universe:
            _upsert_equity_tokens(
                session, detect.equity_tokens_in(pairs, universe, markers, bases),
                _pair_creation_times(pairs), _deepest_pair_urls(pairs))
        for launch in detect.detect_launches(pairs, universe, markers, bases):
            seen_launches += 1
            if _upsert_launch(session, launch):
                new_launches += 1
    session.commit()
    return {"tokens_swept": len(tokens), "launches_seen": seen_launches,
            "launches_new": new_launches}


def hot_registry_sweep(session: Session) -> dict:
    """Sweep ONLY the wrappers whose underlying is a plausible nanocap, fast.

    Cadence is the whole value of the RAMPING rung. The JINQIAN pool was
    created at 09:32 ET and FAMI cleared +12.8% at 09:45 — a 13-minute window.
    A 30-minute sweep resolves that to "sometime after it happened", so the
    names that could actually move are swept on a much tighter loop. There are
    few of them, which is exactly why this is affordable.
    """
    cfg = _cfg()
    universe = equity_lane.sec_universe()
    markers, bases = _markers(), _base_assets()
    floor = float(cfg.get("alert", {}).get("min_tokenized_pumpability", 60.0))
    cap = int(cfg.get("scan", {}).get("max_hot_tokens", 60))

    hot_tickers = set(session.exec(
        select(Candidate.ticker).where(Candidate.pumpability >= floor)).all())
    if not hot_tickers:
        return {"hot_tickers": 0, "launches_new": 0}

    tokens = session.exec(
        select(EquityToken).where(EquityToken.ticker.in_(hot_tickers)).limit(cap)).all()
    new = 0
    for tok in tokens:
        pairs = dexscreener.token_pairs(tok.chain_id, tok.address, ttl=30)
        for launch in detect.detect_launches(pairs, universe, markers, bases):
            if _upsert_launch(session, launch):
                new += 1
    session.commit()
    return {"hot_tickers": len(hot_tickers), "tokens_swept": len(tokens),
            "launches_new": new}


def _record_snapshot(session: Session, launch: detect.LaunchView,
                     now: datetime) -> float | None:
    """Append a throttled pool reading and return the liquidity trend.

    Throttled because the hot lane runs every 2 minutes: without it a single
    pool would write 30 rows an hour and the table would carry no more
    information than one row every ten minutes does.
    """
    cfg = _cfg()
    window = timedelta(minutes=int(cfg.get("scan", {}).get("snapshot_minutes", 10)))
    recent = session.exec(
        select(PoolSnapshot)
        .where(PoolSnapshot.pair_address == launch.pair_address)
        .order_by(PoolSnapshot.at.desc()).limit(1)).first()
    if recent is None or (now - recent.at) >= window:
        session.add(PoolSnapshot(
            pair_address=launch.pair_address, ticker=launch.equity.ticker,
            at=now, liquidity_usd=launch.liquidity_usd,
            volume_h1=launch.volume_h1, fdv=launch.fdv,
            buys_h1=launch.buys_h1, sells_h1=launch.sells_h1))

    retention = float(cfg.get("scan", {}).get("snapshot_retention_hours", 168))
    earliest = session.exec(
        select(PoolSnapshot)
        .where(PoolSnapshot.pair_address == launch.pair_address,
               PoolSnapshot.at >= now - timedelta(hours=retention))
        .order_by(PoolSnapshot.at)).first()
    if earliest is None or earliest.liquidity_usd <= 0:
        return None
    if (now - earliest.at) < timedelta(minutes=5):
        return None                      # one reading is not a trajectory
    return (launch.liquidity_usd - earliest.liquidity_usd) / earliest.liquidity_usd * 100.0


def _upsert_launch(session: Session, launch: detect.LaunchView) -> bool:
    cfg = _cfg()
    trend = _record_snapshot(session, launch, datetime.utcnow())
    cred, _ = scoring.credibility(launch, cfg, liquidity_trend_pct=trend)
    ht, _ = scoring.heat(launch, cfg)

    row = session.exec(
        select(MemeLaunch).where(MemeLaunch.chain_id == launch.chain_id,
                                 MemeLaunch.pair_address == launch.pair_address)).first()
    is_new = row is None
    if row is None:
        row = MemeLaunch(chain_id=launch.chain_id, pair_address=launch.pair_address,
                         ticker=launch.equity.ticker)
        logger.info("launch: %s pooled against %s (%s) — liq $%.0f, 24h vol $%.0f",
                    launch.meme_symbol, launch.equity.ticker,
                    launch.equity.issuer_class, launch.liquidity_usd, launch.volume_h24)
    row.dex_id = launch.dex_id
    row.base_address = launch.meme_address
    row.base_symbol = launch.meme_symbol
    row.base_name = launch.meme_name
    row.ticker = launch.equity.ticker
    row.equity_token_address = launch.equity.address
    row.pair_created_at = launch.pair_created_at
    row.last_seen_at = datetime.utcnow()
    row.liquidity_usd = launch.liquidity_usd
    row.volume_h24 = launch.volume_h24
    row.volume_h1 = launch.volume_h1
    row.volume_m5 = launch.volume_m5
    row.fdv = launch.fdv
    row.price_change_h1 = launch.price_change_h1
    row.price_change_h24 = launch.price_change_h24
    row.buys_h1 = launch.buys_h1
    row.sells_h1 = launch.sells_h1
    row.credibility = cred
    row.heat = ht
    row.url = launch.url
    row.liquidity_trend_pct = trend
    session.add(row)
    return is_new


# --------------------------------------------------------------------------
# Rollup + ladder + alert
# --------------------------------------------------------------------------

def _equity_view(ticker: str) -> scoring.EquityView:
    q = equity_lane.quote(ticker)
    if not q or q.get("price") is None:
        return scoring.EquityView(dark=True)
    # 2 YEARS, not 3 months: squeeze history is the point of these bars, and a
    # quarter-long window misses it entirely — WHLR's +97.8% session is ~2y old,
    # and a 3M read scored its squeeze history at +10%. average_volume only
    # looks at the last 20 bars, so one long fetch serves both.
    bars = equity_lane.history(ticker, range_="2Y")
    # Median of recent daily bars is the primary baseline because it cannot be
    # dragged by the very spike we are hunting; FMP's averageVolume is only a
    # fallback for names with too little history.
    avg_volume = equity_lane.average_volume(bars)
    stats = equity_lane.price_stats(bars)
    prof = fundamentals.profile(ticker)
    if avg_volume is None:
        avg_volume = prof.get("avg_volume")
    flt = fundamentals.shares_float(ticker)
    return scoring.EquityView(
        price=q.get("price"), prev_close=q.get("prev_close"),
        change_pct=q.get("change_pct"), volume=q.get("volume"),
        avg_volume=avg_volume, high_52w=q.get("high_52w"),
        low_52w=q.get("low_52w"), market_cap=prof.get("market_cap"),
        float_shares=flt.get("float_shares"),
        dollar_volume=stats.get("dollar_volume"),
        max_1d_gain_pct=stats.get("max_1d_gain_pct"),
        days_over_30=stats.get("days_over_30"),
        daily_vol_pct=stats.get("daily_vol_pct"), dark=False)


def rollup(session: Session, now: datetime | None = None) -> list[dict]:
    """One Candidate per ticker; advance the ladder; emit alerts."""
    cfg = _cfg()
    now = now or datetime.utcnow()
    fired: list[dict] = []

    tickers = set(session.exec(select(EquityToken.ticker)).all())
    for ticker in sorted(tickers):
        tokens = session.exec(
            select(EquityToken).where(EquityToken.ticker == ticker)).all()
        launches = session.exec(
            select(MemeLaunch).where(MemeLaunch.ticker == ticker)).all()

        cand = session.exec(
            select(Candidate).where(Candidate.ticker == ticker)).first()
        previous_stage = cand.stage if cand else None
        if cand is None:
            cand = Candidate(ticker=ticker)

        cand.company = tokens[0].company if tokens else cand.company
        # An official wrapper anywhere in the registry is the transmission path.
        cand.issuer_class = next(
            (t.issuer_class for t in tokens if t.issuer_class.startswith("OFFICIAL")),
            tokens[0].issuer_class if tokens else "")
        cand.chains = ",".join(sorted({t.chain_id for t in tokens}))
        cand.first_tokenized_at = min(
            [t.first_pair_at or t.first_seen_at for t in tokens], default=None)

        # Only pools with real depth count toward the cascade signature —
        # otherwise a handful of empty copycat pools fake a CLUSTER.
        liq_floor = float(cfg.get("ladder", {}).get("min_cluster_liquidity_usd", 2500))
        live = [l for l in launches if l.liquidity_usd >= liq_floor]
        cand.meme_count = len({l.base_address.lower() for l in live})
        cand.onchain_liquidity_usd = sum(l.liquidity_usd for l in launches)
        cand.onchain_volume_h24 = sum(l.volume_h24 for l in launches)
        cand.onchain_volume_h1 = sum(l.volume_h1 for l in launches)

        top = max(launches, key=lambda l: l.heat, default=None)
        cand.top_meme_symbol = top.base_symbol if top else ""
        cand.top_meme_url = top.url if top else ""
        cand.credibility = max((l.credibility for l in launches), default=0.0)
        cand.heat = max((l.heat for l in launches), default=0.0)
        if launches and cand.first_paired_at is None:
            cand.first_paired_at = min(
                (l.pair_created_at or l.first_seen_at) for l in launches)

        eq = _equity_view(ticker)
        cand.equity_dark = eq.dark
        cand.equity_price = eq.price
        cand.equity_prev_close = eq.prev_close
        cand.equity_change_pct = eq.change_pct
        cand.equity_volume = eq.volume
        cand.equity_avg_volume = eq.avg_volume
        cand.equity_rvol = ((eq.volume / eq.avg_volume)
                            if (eq.volume and eq.avg_volume) else None)
        cand.equity_market_cap = eq.market_cap
        cand.equity_float_shares = eq.float_shares
        cand.equity_float_turnover = eq.float_turnover
        dil = fundamentals.dilution(ticker)
        cand.dilution_flag = fundamentals.dilution_flag(dil)
        cand.share_growth_x = dil.get("share_growth_x")
        cand.runway_months = dil.get("runway_months")
        cand.cash = dil.get("cash")

        pump, pump_factors, pump_r = scoring.pumpability_factors(eq, cfg)
        cand.pump_factors = pump_factors
        early, early_r = scoring.earliness(eq, cand.first_tokenized_at, now, cfg)
        cand.pumpability, cand.earliness = pump, early

        new_stage_probe = ladder.decide_stage(
            cand.stage, ladder.LadderInput(cand.meme_count, cand.heat, eq), cfg)
        if new_stage_probe == "TOKENIZED":
            # No memes yet, so there is no pool to score. This rung is graded
            # on the equity alone — and on the Farmmi timeline it was the only
            # one with real lead (see scoring.cold_tokenization_score).
            score, alert_r = scoring.cold_tokenization_score(
                pump, early, cand.issuer_class, cfg)
        else:
            score, alert_r = scoring.alert_score(
                cand.credibility, cand.heat, pump, early, cand.issuer_class,
                cand.meme_count, cfg)
        cand.alert_score = score

        reasons = list(alert_r)
        if top is not None:
            _, cred_r = scoring.credibility(_launch_view_from_row(top), cfg)
            _, heat_r = scoring.heat(_launch_view_from_row(top), cfg)
            reasons += heat_r + cred_r
        cand.reasons = reasons + pump_r + early_r

        new_stage = new_stage_probe

        if ladder.is_upgrade(previous_stage, new_stage):
            _record_stage(session, cand, new_stage, now, score)
        cand.stage = new_stage

        fire, why = ladder.should_alert(new_stage, previous_stage, score, eq,
                                        cfg, pumpability=pump)
        if fire:
            cand.alerted_at = now
            fired.append({"ticker": ticker, "company": cand.company,
                          "stage": new_stage, "score": round(score, 1),
                          "why": why, "meme": cand.top_meme_symbol,
                          "url": cand.top_meme_url,
                          "equity_price": eq.price,
                          "equity_change_pct": eq.change_pct,
                          "equity_rvol": cand.equity_rvol,
                          "float_shares": eq.float_shares,
                          "float_turnover": eq.float_turnover,
                          "issuer_class": cand.issuer_class,
                          "dilution_flag": cand.dilution_flag,
                          "pump_factors": pump_factors,
                          "wrapper_url": next((t.url for t in tokens if t.url), ""),
                          "pools": pools_payload(launches, cfg),
                          "reasons": cand.reasons[:6]})

        cand.updated_at = now
        session.add(cand)

    session.commit()
    for alert in fired:
        _push_alert(alert)
    return fired


def pools_payload(launches: list[MemeLaunch], cfg: dict) -> list[dict]:
    """The pools themselves, deepest first — what is actually trading against
    this ticker, with a link to each. A ticker with no way to look at the pool
    is not an actionable alert."""
    n = int((cfg or {}).get("scan", {}).get("pools_in_alert", 5))
    ordered = sorted(launches, key=lambda l: l.liquidity_usd, reverse=True)[:n]
    out = []
    for l in ordered:
        trend = l.liquidity_trend_pct
        out.append({
            "symbol": l.base_symbol, "name": l.base_name, "url": l.url,
            "chain": l.chain_id, "dex": l.dex_id,
            "liquidity_usd": l.liquidity_usd, "volume_h24": l.volume_h24,
            "fdv": l.fdv, "credibility": round(l.credibility, 1),
            "heat": round(l.heat, 1),
            "liquidity_trend_pct": trend,
            "trend": ("" if trend is None
                      else f"liq {trend:+.0f}% since first seen"),
            "created": l.pair_created_at.isoformat() if l.pair_created_at else None,
        })
    return out


def _launch_view_from_row(row: MemeLaunch) -> detect.LaunchView:
    """Re-hydrate just enough of a LaunchView to re-run the reason strings."""
    return detect.LaunchView(
        chain_id=row.chain_id, pair_address=row.pair_address, dex_id=row.dex_id,
        url=row.url,
        equity=registry.EquityTokenView(
            chain_id=row.chain_id, address=row.equity_token_address, symbol="",
            token_name="", ticker=row.ticker, company="", issuer_class="",
            issuer=""),
        meme_address=row.base_address, meme_symbol=row.base_symbol,
        meme_name=row.base_name, pair_created_at=row.pair_created_at,
        liquidity_usd=row.liquidity_usd, fdv=row.fdv, volume_h24=row.volume_h24,
        volume_h6=row.volume_h24, volume_h1=row.volume_h1, volume_m5=row.volume_m5,
        buys_h1=row.buys_h1, sells_h1=row.sells_h1, buys_h24=row.buys_h1,
        sells_h24=row.sells_h1, price_change_h1=row.price_change_h1,
        price_change_h24=row.price_change_h24)


def _record_stage(session: Session, cand: Candidate, stage: str,
                  now: datetime, score: float) -> None:
    """Append the ladder transition — the lead-lag measurement substrate."""
    setattr_map = {
        "PAIRED": "first_paired_at", "RAMPING": "first_ramping_at",
        "CLUSTER": "first_cluster_at", "EQUITY_MOVING": "first_equity_move_at",
    }
    attr = setattr_map.get(stage)
    if attr and getattr(cand, attr) is None:
        setattr(cand, attr, now)
    session.add(StageEvent(
        ticker=cand.ticker, stage=stage, at=now,
        hours_since_tokenized=ladder.hours_since(cand.first_tokenized_at, now),
        detail={"score": round(score, 1), "meme_count": cand.meme_count,
                "heat": round(cand.heat, 1), "issuer_class": cand.issuer_class,
                "equity_change_pct": cand.equity_change_pct,
                "equity_rvol": cand.equity_rvol}))


def _push_alert(alert: dict) -> None:
    """Best-effort push. A failed push never fails a scan.

    Two independent channels: the shared Telegram bot (same token/chat as
    treasury-canary and the executors) and an optional generic webhook.
    """
    logger.warning("ALERT %s (%s) stage=%s score=%.0f meme=%s — %s",
                   alert["ticker"], alert["company"], alert["stage"],
                   alert["score"], alert["meme"], alert["why"])
    try:
        alerts.push(alert)
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram push failed: %s", exc)

    url = settings.alert_webhook_url
    if not url:
        return
    text = alerts.format_alert(alert)
    try:
        httpx.post(url, json={"content": text, "text": text},
                   timeout=settings.http_timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("alert webhook failed: %s", exc)


def full_scan(session: Session) -> dict:
    """Everything, in dependency order. Used by POST /scan and the boot job."""
    out = {"discovery": discovery_sweep(session)}
    out["priority"] = priority_sweep(session)
    out["universe"] = universe_sweep(session)
    out["registry"] = registry_sweep(session)
    out["alerts"] = rollup(session)
    logger.info("scan complete: %s", json.dumps(out, default=str)[:600])
    return out
