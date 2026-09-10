"""Scores. All pure functions; every weight comes from config/screener.yaml.

Four ORTHOGONAL axes, kept separate on purpose because they answer different
questions and blending them early hides which one failed:

  credibility  Is this pool real? Depth, two-sidedness, breadth of
               participation, and turnover that is high but not absurd.
               NOTE ON THE LIMIT OF THIS SCORE: DEX Screener's public API does
               not expose the deployer wallet, LP lock state, or the holder
               distribution, so this is a POOL-quality proxy and explicitly not
               a judgement about the person who deployed it. A screen cannot
               tell an organic launch from a well-funded one.
  heat         Is attention accelerating right now, versus already spent?
  pumpability  Would the underlying listing actually move if it got bid — is
               it small, cheap and thinly traded enough?
  earliness    How much of the move is still ahead? This is the axis that
               decides whether an alert is actionable or an obituary.

The composite deliberately multiplies earliness rather than adding it: a
setup that is perfect on every other axis but has already run is worth zero,
not "still pretty good".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from ..utils import clamp
from .detect import LaunchView


def _shares_or_money(x: float, prefix: str = "") -> str:
    """Sub-million counts must not render as "0.0M" — WHLR's float is 21,783
    shares and that is the most interesting thing about it."""
    if x >= 1e9:
        return f"{prefix}{x/1e9:,.1f}B"
    if x >= 1e6:
        return f"{prefix}{x/1e6:,.1f}M"
    return f"{prefix}{x:,.0f}"


def _ramp(x: float, lo: float, hi: float) -> float:
    """0 below `lo`, 100 above `hi`, linear between."""
    if hi <= lo:
        return 0.0
    return clamp((x - lo) / (hi - lo) * 100.0)


def _log_ramp(x: float, lo: float, hi: float) -> float:
    """As _ramp but on a log10 scale — for money amounts spanning decades."""
    if x <= 0 or hi <= lo:
        return 0.0
    return _ramp(math.log10(max(x, 1e-9)), math.log10(lo), math.log10(hi))


def _band(x: float, lo: float, good_lo: float, good_hi: float, hi: float) -> float:
    """100 inside [good_lo, good_hi], falling to 0 at `lo` and `hi`."""
    if x < good_lo:
        return _ramp(x, lo, good_lo)
    if x > good_hi:
        return 100.0 - _ramp(x, good_hi, hi)
    return 100.0


def credibility(launch: LaunchView, cfg: dict,
                liquidity_trend_pct: float | None = None) -> tuple[float, list[str]]:
    """`liquidity_trend_pct` is the change in pool liquidity since the earliest
    snapshot held. A single reading cannot distinguish a pool being built from
    one being drained; the change between readings can, and it applies as a
    MULTIPLIER so a pool whose LP is walking out cannot score well on depth."""
    c = (cfg or {}).get("credibility", {})
    reasons: list[str] = []

    depth = _log_ramp(launch.liquidity_usd,
                      c.get("liq_floor_usd", 1_000), c.get("liq_full_usd", 1_000_000))
    # Liquidity as a share of fully-diluted value: a $60M "valuation" sitting on
    # $4k of liquidity is a price print, not a market.
    lf_ratio = launch.liquidity_usd / launch.fdv if launch.fdv > 0 else 0.0
    float_q = _ramp(lf_ratio, c.get("liq_fdv_floor", 0.01), c.get("liq_fdv_full", 0.15))

    buys, sells = launch.buys_h24, launch.sells_h24
    total = buys + sells
    two_sided = _ramp(min(buys, sells) / max(buys, sells), 0.15, 0.5) if max(buys, sells) else 0.0
    breadth = _log_ramp(total, c.get("txn_floor", 25), c.get("txn_full", 2_000))

    turnover = launch.volume_h24 / launch.liquidity_usd if launch.liquidity_usd > 0 else 0.0
    turn_q = _band(turnover, 0.0, c.get("turnover_good_lo", 0.5),
                   c.get("turnover_good_hi", 40.0), c.get("turnover_absurd", 400.0))

    w = c.get("weights", {})
    score = (depth * w.get("depth", 0.35) + float_q * w.get("float", 0.20)
             + two_sided * w.get("two_sided", 0.15) + breadth * w.get("breadth", 0.15)
             + turn_q * w.get("turnover", 0.15))

    # ALIVENESS. Displayed liquidity is a number anyone can manufacture: seed a
    # pool so the USD figure is enormous and never trade it. Real examples on
    # Ethereum, 2026-09-02 — tokens named "Micron Technology Inc. Common Stock"
    # and "Dell Technologies Inc." showing $852M and $302M of liquidity against
    # WETH, each with ONE trade and $0.01 of 24h volume. Scored on depth alone
    # they reached ~55 and cleared the credibility gate.
    #
    # So depth only counts to the extent something trades against it. This
    # multiplies rather than subtracts: no amount of posted liquidity earns
    # credibility in a pool nobody touches.
    alive = _ramp(float(total), c.get("dead_txns_24h", 2), c.get("alive_txns_24h", 40))
    if alive < 100.0:
        score *= alive / 100.0
        if total <= c.get("dead_txns_24h", 2) and launch.liquidity_usd > 10_000:
            reasons.append(
                f"${launch.liquidity_usd:,.0f} posted against {total} trades in 24h "
                "— liquidity is not being traded, treat the depth as fiction")
        elif alive < 60.0:
            reasons.append(f"only {total} trades in 24h — pool barely alive")

    if depth < 25:
        reasons.append(f"thin pool (${launch.liquidity_usd:,.0f} liquidity)")
    if lf_ratio and lf_ratio < 0.02:
        reasons.append(f"liquidity is {lf_ratio:.1%} of FDV — price is not marketable size")
    if turnover > c.get("turnover_absurd", 400.0) * 0.5:
        reasons.append(f"turnover {turnover:,.0f}x liquidity in 24h — wash-trading risk")
    if launch.socials or launch.websites:
        reasons.append("has listed socials/site")

    if liquidity_trend_pct is not None:
        drain_full = c.get("drain_full_pct", -60.0)
        drain_floor = c.get("drain_floor_pct", -10.0)
        if liquidity_trend_pct <= drain_floor:
            span = max(drain_floor - drain_full, 1e-9)
            severity = min(1.0, (drain_floor - liquidity_trend_pct) / span)
            factor = 1.0 - severity * (1.0 - c.get("drain_worst_factor", 0.45))
            score *= factor
            reasons.append(
                f"liquidity {liquidity_trend_pct:+.0f}% since first seen — "
                "LP is leaving, not arriving")
        elif liquidity_trend_pct >= c.get("build_pct", 25.0):
            reasons.append(f"liquidity {liquidity_trend_pct:+.0f}% since first "
                           "seen — depth is being added")
    return clamp(score), reasons


def heat(launch: LaunchView, cfg: dict) -> tuple[float, list[str]]:
    """Acceleration, not level. A pair that did $90M yesterday and $80k in the
    last hour is cooling, and must not outrank one going the other way."""
    h = (cfg or {}).get("heat", {})
    reasons: list[str] = []

    # h24 and h6 are equal for pairs younger than 6h, so derive the baseline
    # from the longest window that is actually populated.
    hourly_baseline = (launch.volume_h24 / 24.0) if launch.volume_h24 > 0 else 0.0
    accel = (launch.volume_h1 / hourly_baseline) if hourly_baseline > 0 else 0.0
    burst = (launch.volume_m5 * 12.0 / launch.volume_h1) if launch.volume_h1 > 0 else 0.0

    accel_q = _ramp(accel, h.get("accel_floor", 0.4), h.get("accel_full", 3.0))
    burst_q = _ramp(burst, h.get("burst_floor", 0.5), h.get("burst_full", 3.0))
    size_q = _log_ramp(launch.volume_h1, h.get("vol_h1_floor", 2_000),
                       h.get("vol_h1_full", 2_000_000))
    mom_q = _ramp(launch.price_change_h1, h.get("mom_floor", -10.0),
                  h.get("mom_full", 60.0))

    w = h.get("weights", {})
    score = (accel_q * w.get("accel", 0.35) + burst_q * w.get("burst", 0.15)
             + size_q * w.get("size", 0.30) + mom_q * w.get("momentum", 0.20))

    if accel < 0.5 and launch.volume_h24 > 0:
        reasons.append(f"cooling: last hour is {accel:.2f}x the 24h run-rate")
    elif accel >= 2.0:
        reasons.append(f"accelerating: last hour is {accel:.1f}x the 24h run-rate")
    return clamp(score), reasons


@dataclass
class EquityView:
    price: float | None = None
    prev_close: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    avg_volume: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    market_cap: float | None = None      # only when the FMP enrichment is on
    float_shares: float | None = None    # ditto
    # Behavioural stats from daily bars (keyless) — see equity.price_stats.
    dollar_volume: float | None = None
    max_1d_gain_pct: float | None = None
    days_over_30: int | None = None
    daily_vol_pct: float | None = None
    dark: bool = False

    @property
    def float_turnover(self) -> float | None:
        """Today's volume as a multiple of the free float. The single most
        direct read on whether meme flow can actually move this listing."""
        if not (self.volume and self.float_shares) or self.float_shares <= 0:
            return None
        return self.volume / self.float_shares


def pumpability(eq: EquityView, cfg: dict) -> tuple[float, list[str]]:
    """Wrapper kept for callers that only want the number and the reasons."""
    score, _factors, reasons = pumpability_factors(eq, cfg)
    return score, reasons


def pumpability_factors(eq: EquityView, cfg: dict
                        ) -> tuple[float, list[dict], list[str]]:
    """How violently would this listing respond to being bid?

    Float alone is not enough. Six factors, each scored 0-100 and reported
    individually so the number can be argued with rather than trusted:

      cost to move   median DOLLAR volume. Sharper than share count by orders
                     of magnitude — MU trades $26.6B a day against FAMI's
                     $950K on share volumes only ~4x apart.
      float          free float. Small float, violent moves.
      squeeze past   has this name ALREADY done a violent up-day? Names that
                     squeeze tend to squeeze again; WHLR has printed +97.8%
                     in a session and two days over +30% in two years.
      capable        realized daily volatility. The control case for why cheap
                     and illiquid is not enough: NTIC has the smallest dollar
                     volume on the board and a 1.6% daily vol — it is illiquid
                     but DEAD, and no amount of flow has ever moved it.
      cheap          price level. Sub-$1 names travel in bigger percentages.
      size           market cap, when the FMP enrichment is on.

    Every absent input is dropped and the remaining weights renormalised, so a
    dark lane lowers CONFIDENCE rather than silently scoring a name as if the
    missing factor were bad. The factor list names what was missing.
    """
    p = (cfg or {}).get("pumpability", {})
    reasons: list[str] = []
    if eq.dark or eq.price is None:
        return 0.0, [], ["equity lane dark — pumpability unscored"]

    w = p.get("weights", {})
    factors: list[dict] = []

    def add(key, label, score, weight, display):
        factors.append({"key": key, "label": label, "score": round(score, 1),
                        "weight": weight, "display": display})

    # cost to move — the dominant factor
    if eq.dollar_volume and eq.dollar_volume > 0:
        cost = 100.0 - _log_ramp(eq.dollar_volume, p.get("dollarvol_full", 2e5),
                                 p.get("dollarvol_floor", 5e8))
        add("cost", "cost to move", cost, w.get("cost", 0.28),
            f"${eq.dollar_volume:,.0f}/day")
        if eq.dollar_volume < 5e6:
            reasons.append(f"only ${eq.dollar_volume:,.0f} of stock trades a day")
    else:
        reasons.append("no dollar-volume reading")

    if eq.float_shares and eq.float_shares > 0:
        tight = 100.0 - _log_ramp(eq.float_shares, p.get("float_full", 5e6),
                                  p.get("float_floor", 3e8))
        add("float", "float", tight, w.get("tight", 0.22),
            f"{_shares_or_money(eq.float_shares)} shares")
        turn = eq.float_turnover
        if turn is not None and turn >= p.get("float_turnover_notable", 1.0):
            reasons.append(f"float has turned over {turn:,.1f}x today")
    else:
        reasons.append("float dark")

    if eq.max_1d_gain_pct is not None:
        best = _ramp(eq.max_1d_gain_pct, p.get("squeeze_floor_pct", 15.0),
                     p.get("squeeze_full_pct", 80.0))
        streak = _ramp(float(eq.days_over_30 or 0), 0.0, p.get("squeeze_days_full", 3.0))
        hist = max(best, streak)
        add("squeeze", "squeeze history", hist, w.get("squeeze", 0.18),
            f"best +{eq.max_1d_gain_pct:.0f}% · {eq.days_over_30 or 0} days >30%")
        if eq.max_1d_gain_pct >= 50:
            reasons.append(f"has printed +{eq.max_1d_gain_pct:.0f}% in a session before")
    else:
        reasons.append("no squeeze history")

    if eq.daily_vol_pct is not None:
        capable = _ramp(eq.daily_vol_pct, p.get("vol_dead_pct", 2.0),
                        p.get("vol_live_pct", 12.0))
        add("capable", "capable of moving", capable, w.get("capable", 0.12),
            f"{eq.daily_vol_pct:.1f}% daily")
        if eq.daily_vol_pct < p.get("vol_dead_pct", 2.0) * 1.25:
            reasons.append(f"{eq.daily_vol_pct:.1f}% daily vol — this name does not move")

    cheap = 100.0 - _ramp(eq.price, p.get("price_full", 1.0), p.get("price_floor", 20.0))
    add("cheap", "price", cheap, w.get("cheap_f", 0.10), f"${eq.price:,.4f}")
    if eq.price < 1.0:
        reasons.append(f"${eq.price:.4f} — sub-$1, the Nasdaq bid-price band")

    # A market cap of 0 is a DATA GAP, not a $0 company — treating it as tiny
    # handed WHLR a free 100/100 on size. So is an IMPLAUSIBLE one: FMP reports
    # a $13,605 cap for WHLR, a NASDAQ-listed REIT, which is stale share data
    # after repeated reverse splits, not a $13k company. Nasdaq's own continued-
    # listing standards make a sub-$250k market value impossible, so a reading
    # under that floor is a data error and is dropped rather than rewarded.
    mcap_floor_real = p.get("mcap_implausible_below", 250_000)
    if eq.market_cap and eq.market_cap >= mcap_floor_real:
        small = 100.0 - _log_ramp(eq.market_cap, p.get("mcap_full", 1e7),
                                  p.get("mcap_floor", 2e9))
        add("size", "market cap", small, w.get("small_f", 0.10),
            _shares_or_money(eq.market_cap, "$"))
    elif eq.market_cap and eq.market_cap > 0:
        reasons.append(
            f"market cap reads ${eq.market_cap:,.0f} — implausible for a US listing, "
            "treated as stale data and dropped from the score")
    else:
        reasons.append("market cap missing — dropped from the score, not scored as tiny")

    if not factors:
        return 0.0, [], reasons + ["no pumpability inputs available"]

    # Renormalise over the factors we actually have: a missing input must not
    # read as a bad one.
    total_w = sum(f["weight"] for f in factors) or 1.0
    score = sum(f["score"] * f["weight"] for f in factors) / total_w
    for f in factors:
        f["contribution"] = round(f["score"] * f["weight"] / total_w, 1)
    factors.sort(key=lambda f: -f["contribution"])
    if len(factors) < 6:
        reasons.append(f"scored on {len(factors)} of 6 factors")
    return clamp(score), factors, reasons


def earliness(eq: EquityView, first_tokenized_at: datetime | None,
              now: datetime, cfg: dict) -> tuple[float, list[str]]:
    """How much of the equity move is still ahead.

    This is the axis that separates a trade from a screenshot. It is driven by
    the EQUITY's own state, not the token's: once the stock is up 300% on 90x
    volume the on-chain signal has already been paid out.
    """
    e = (cfg or {}).get("earliness", {})
    reasons: list[str] = []
    if eq.dark or eq.change_pct is None:
        return 50.0, ["equity lane dark — earliness defaulted to neutral"]

    # Not-yet-moved: 100 at flat, 0 once the move is done.
    move = 100.0 - _ramp(abs(eq.change_pct), e.get("move_flat_pct", 3.0),
                         e.get("move_spent_pct", 60.0))

    rvol = (eq.volume / eq.avg_volume) if (eq.volume and eq.avg_volume) else None
    if rvol is None:
        quiet = 50.0
    else:
        quiet = 100.0 - _log_ramp(rvol, e.get("rvol_quiet", 1.5), e.get("rvol_spent", 40.0))
        if rvol > 10:
            reasons.append(f"equity already at {rvol:.0f}x normal volume — crowd has arrived")

    # Freshness of the on-chain setup MULTIPLIES the equity read rather than
    # adding to it. As an additive term it propped up earliness on names that
    # had demonstrably already run: a stock up 321% on 144x volume still scored
    # 20/100 purely because the token was deployed two hours ago. Freshness can
    # discount a stale setup; it can never manufacture runway that the tape
    # says is gone.
    if first_tokenized_at is not None:
        age_h = max(0.0, (now - first_tokenized_at).total_seconds() / 3600.0)
        fresh = 100.0 - _ramp(age_h, e.get("fresh_hours", 6.0), e.get("stale_hours", 72.0))
    else:
        fresh = 50.0

    w = e.get("weights", {})
    w_move, w_quiet = w.get("move", 0.55), w.get("quiet", 0.45)
    equity_part = (move * w_move + quiet * w_quiet) / max(w_move + w_quiet, 1e-9)
    floor = float(e.get("fresh_multiplier_floor", 0.7))
    score = equity_part * (floor + (1.0 - floor) * (fresh / 100.0))
    if eq.change_pct is not None and abs(eq.change_pct) < 3.0:
        reasons.append(f"equity still flat ({eq.change_pct:+.1f}%) — window may be open")
    return clamp(score), reasons


def alert_score(cred: float, ht: float, pump: float, early: float,
                issuer_class: str, meme_count: int, cfg: dict) -> tuple[float, list[str]]:
    """The ranked composite.

    Earliness MULTIPLIES rather than adds: a setup that has already run scores
    near zero however good it looks on every other axis.

    An OFFICIAL wrapper gets a transmission bonus because it has a mint/redeem
    path, so on-chain buying can actually reach the tape. An UNOFFICIAL wrapper
    — the Farmmi case — has no redemption mechanism at all, so the only channel
    to the stock is people SEEING it and buying the listing themselves. That is
    a weaker and far more reflexive link, and it is scored as one.
    """
    a = (cfg or {}).get("alert", {})
    reasons: list[str] = []

    gates = a.get("gates", {})
    if cred < gates.get("min_credibility", 30.0):
        return 0.0, [f"gated: credibility {cred:.0f} < {gates.get('min_credibility', 30.0):.0f}"]
    if pump < gates.get("min_pumpability", 35.0):
        return 0.0, [f"gated: pumpability {pump:.0f} < {gates.get('min_pumpability', 35.0):.0f}"]

    w = a.get("weights", {})
    core = (ht * w.get("heat", 0.40) + pump * w.get("pumpability", 0.35)
            + cred * w.get("credibility", 0.25))

    # Cluster: several distinct memes against ONE ticker inside a day is the
    # cascade signature (FAMI drew JINQIAN, FORASEN, JINCHAN, YUANBAO,
    # MUSHROOMCOIN and PENNYSTOCK within three hours).
    cluster_bonus = min(meme_count - 1, a.get("cluster_cap", 5)) * a.get("cluster_step", 4.0)
    if meme_count >= a.get("cluster_min", 3):
        reasons.append(f"{meme_count} distinct memes pooled against this ticker — cascade")

    if issuer_class.startswith("OFFICIAL"):
        transmission = a.get("official_bonus", 8.0)
        reasons.append("official wrapper — mint/redeem can transmit flow to the tape")
    else:
        transmission = 0.0
        reasons.append("unofficial wrapper — no redemption path; attention-only link")

    score = (core + cluster_bonus + transmission) * (early / 100.0)
    return clamp(score), reasons


def cold_tokenization_score(pump: float, early: float, issuer_class: str,
                            cfg: dict) -> tuple[float, list[str]]:
    """Score the TOKENIZED rung, which has no memes and therefore no heat or
    pool credibility to score at all.

    This rung exists because of what the Farmmi timeline actually shows. Lead
    times from each rung to the first 5-minute bar that cleared +12.8%
    (2026-09-02 09:45 ET), measured from DEX Screener pairCreatedAt:

        wrapper pool seeded  ..............  +15.8 h
        first meme pair (JINQIAN) .........  +0.2 h  (13 minutes)
        second meme (FORASEN) .............  -1.0 h
        cluster complete ..................  -1.9 h

    So the cascade rungs this service also tracks are, on that sample,
    COINCIDENT OR LAGGING. The only comfortably tradable rung was the dullest
    one: somebody had wrapped a $5.7M nanocap on Robinhood Chain the previous
    evening, and no meme existed yet. That is what this scores — an equity
    small and cheap enough to move, with a wrapper that has just appeared and
    nothing built on it yet.

    n=1. It is a hypothesis with one supporting observation, not an edge.
    """
    a = (cfg or {}).get("alert", {})
    reasons: list[str] = []
    floor = a.get("min_tokenized_pumpability", 60.0)
    if pump < floor:
        return 0.0, [f"not a nanocap: pumpability {pump:.0f} < {floor:.0f}"]

    score = (pump * 0.65 + early * 0.35)
    reasons.append("wrapper exists for a nanocap with no meme on it yet — "
                   "the earliest rung, ~16h of lead in the one case observed")
    if not issuer_class.startswith("OFFICIAL"):
        reasons.append("unofficial wrapper on a nanocap — nobody wraps one of "
                       "these by accident")
    return clamp(score), reasons
