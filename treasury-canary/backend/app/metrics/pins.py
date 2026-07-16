"""Pin board — Dalio's gun vs. trigger, made measurable.

The GUN is accumulated vulnerability (debt load, rich valuations, fragile
plumbing) — most of it already tracked elsewhere on this dashboard. The PIN is
whatever pricks the bubble. Pins are inherently hard to predict — that is
Dalio's own point — so this board does NOT forecast the prick. It monitors the
channels through which historical pricks actually arrived, scored GREEN/YELLOW/
RED from measurable proxies, so a spark is visible within days, not in
hindsight. Each channel carries an honest certainty note.

Channels (proxy -> historical basis):
  OIL SHOCK       12m WTI change      Hamilton: oil spikes preceded ~10 of 11
                                      postwar recessions.
  POLICY SHOCK    12m Fed-hike pace   Every deep tightening cycle has broken
                                      something; pace matters more than level.
  CREDIT EVENT    HY OAS 20d velocity Sudden spread gaps + banks hitting the
                  + discount window   Fed's window (SVB lit WLCFLPCL in days).
  FISCAL PIN      interest/GDP level  The debt-service spiral Dalio warns on,
                  + term-prem 60d Δ   plus the market starting to charge for it.
  PLUMBING        SOFR-IORB + reserve Repo Sept-2019 / gilt-LDI style seizures;
                  drain + RRP buffer  RRP≈0 means the shock absorber is gone.
  UNCERTAINTY     EPU 30d percentile  Exogenous shocks (wars, tariffs, standoffs)
                                      show up as policy-uncertainty spikes first.
  PRIVATE CREDIT  CCC pctile + CCC-BBB  This cycle's untested leverage (~$3T);
                  dispersion + NDFI     public CCC + bank NDFI funding are the
                  loan growth           real-time windows into opaque marks.
  CARRY UNWIND    JPY 1m change +     Aug 2024: yen surge -> global deleveraging
                  JGB 10y 12m change  in days. FX is the trigger, JGB the cushion.

Each channel also carries researched static attributes (mass / speed / kill
rate) — documented exposure sizes and episode counts, never fitted weights.
"""
from __future__ import annotations

from dataclasses import dataclass, field

RANK = {"GREEN": 0, "YELLOW": 1, "RED": 2}


@dataclass
class PinPart:
    label: str
    value: float | None
    unit: str
    status: str          # GREEN | YELLOW | RED | STALE
    detail: str = ""
    score: float | None = None   # 0-100 severity through documented anchors

    def as_dict(self) -> dict:
        return {"label": self.label, "value": self.value, "unit": self.unit,
                "status": self.status, "detail": self.detail, "score": self.score}


@dataclass
class PinChannel:
    channel_id: str
    label: str
    status: str          # worst non-STALE part; STALE if none live
    parts: list[PinPart] = field(default_factory=list)
    basis: str = ""      # historical basis for this channel
    certainty: str = ""  # honest note on signal quality/latency
    # Researched static attributes — documented exposure sizes and episode
    # counts, NEVER fitted (with ~11 recessions and 9 channels, fitted weights
    # would be data-snooping). They size a red: a fast, multi-trillion,
    # high-kill-rate channel firing reads differently than a noisy slow one.
    mass: str = ""       # systemic exposure behind the channel
    speed: str = ""      # transmission speed once it fires
    kill_rate: str = ""  # documented historical record as a recession trigger

    score: float | None = None   # max live part score (0-100)

    def as_dict(self) -> dict:
        return {"channel_id": self.channel_id, "label": self.label, "status": self.status,
                "parts": [p.as_dict() for p in self.parts], "basis": self.basis,
                "certainty": self.certainty, "mass": self.mass, "speed": self.speed,
                "kill_rate": self.kill_rate, "score": self.score}


def _grade(value: float | None, yellow: float, red: float, higher_is_worse: bool = True) -> str:
    if value is None:
        return "STALE"
    if higher_is_worse:
        return "RED" if value >= red else "YELLOW" if value >= yellow else "GREEN"
    return "RED" if value <= red else "YELLOW" if value <= yellow else "GREEN"


def _worst(parts: list[PinPart]) -> str:
    live = [p.status for p in parts if p.status != "STALE"]
    if not live:
        return "STALE"
    return max(live, key=lambda s: RANK[s])


def _clean(vals: list) -> list[float]:
    return [v for v in vals if v is not None]


def _change(vals: list, window: int) -> float | None:
    c = _clean(vals)
    if len(c) <= window:
        return None
    return c[-1] - c[-1 - window]


def _pct_change(vals: list, window: int) -> float | None:
    c = _clean(vals)
    if len(c) <= window or not c[-1 - window]:
        return None
    return round((c[-1] - c[-1 - window]) / c[-1 - window] * 100.0, 1)


def _percentile(vals: list, value: float | None) -> float | None:
    c = _clean(vals)
    if value is None or not c:
        return None
    return round(100.0 * sum(1 for v in c if v <= value) / len(c), 1)


# --- continuous severity scoring (0-100) --------------------------------------
# Every part maps to documented anchors: BENIGN -> 0, the existing YELLOW
# threshold -> 50, the existing RED threshold -> 80, and a documented
# historical-episode EXTREME -> 100 (piecewise linear, clamped). Colors are
# derived from the same bands (<50 GREEN, 50-79 YELLOW, >=80 RED), so the
# score can never disagree with the pill. Cushion/pressure-gauge legs carry
# cap=79 — they can push a channel to the top of YELLOW but never to RED,
# preserving the original cap semantics. Anchors are episode-calibrated and
# cited, never fitted.
def _pscore(value: float | None, benign: float, yellow: float, red: float,
            extreme: float, higher_is_worse: bool = True, cap: float = 100.0
            ) -> float | None:
    if value is None:
        return None
    v, b, y, r, e = ((value, benign, yellow, red, extreme) if higher_is_worse
                     else (-value, -benign, -yellow, -red, -extreme))
    if v <= b:
        sc = 0.0
    elif v <= y:
        sc = 50.0 * (v - b) / (y - b) if y != b else 50.0
    elif v <= r:
        sc = 50.0 + 30.0 * (v - y) / (r - y) if r != y else 80.0
    elif v <= e:
        sc = 80.0 + 20.0 * (v - r) / (e - r) if e != r else 100.0
    else:
        sc = 100.0
    return round(min(sc, cap), 1)


def _status_from_score(score: float | None) -> str:
    if score is None:
        return "STALE"
    return "RED" if score >= 80.0 else "YELLOW" if score >= 50.0 else "GREEN"


# (benign, yellow, red, extreme, higher_is_worse, cap) per part label.
# Extreme anchors cite the episode that printed them.
ANCHORS: dict[str, tuple] = {
    "WTI, 12-month change": (0, 25, 50, 100, True, 100),                 # 1973/79/2022 ~ +100%
    "Fed funds, 12-month change": (0, 200, 300, 450, True, 100),         # 2022-23 pace ~ +450bps
    "HY OAS, 20d change": (0, 75, 150, 350, True, 100),                  # Mar-2020 ~ +350bps/20d
    "Discount-window borrowing": (0, 10, 50, 155, True, 100),            # Mar-2023 peak ~$153B
    "Federal interest / GDP": (2.0, 3.0, 4.0, 5.0, True, 100),           # >1990s peak
    "Term premium, 60d change": (0, 40, 75, 150, True, 100),             # 2023-Q3 repricing scale
    "SOFR − IORB": (-8, 5, 15, 50, True, 100),                      # Sep-2019 sustained prints
    "Reserves, 26-week change": (0, -8, -15, -25, False, 100),           # beyond-2019 drain pace
    "RRP buffer": (600, 100, 20, 0, False, 79),                          # cushion leg: caps YELLOW
    "Leveraged-fund net short, UST futures": (2, 4, 5.5, 8, True, 100),  # ~2x the 2020 book
    "Positioning percentile (vs 2010+)": (50, 85, 95, 100, True, 100),
    "CCC spread percentile (vs 1996+)": (50, 85, 95, 100, True, 100),
    "CCC−BBB dispersion percentile": (50, 85, 95, 100, True, 100),
    "Bank loans to NDFIs, m/m ann. growth": (10, 5, 0, -10, False, 100),
    "USD/JPY, 1-month change": (0, -4, -7, -12, False, 100),             # Aug-2024 ~ -8%/1m
    "10y JGB yield, 12-month change": (0, 50, 100, 150, True, 79),       # cushion leg: caps YELLOW
    "EPU index, 30d avg (percentile)": (50, 90, 97.5, 100, True, 100),
    # Demand-strike channel (Dalio): auction demand + foreign custody flows.
    "Coupon bid-to-cover, last 4 auctions": (2.6, 2.35, 2.2, 2.0, False, 100),  # <2.2 = weak tape
    "Indirect (foreign) share, last 4 auctions": (65, 56, 50, 42, False, 100),  # 53% = weakest since Mar-23
    "Foreign custody holdings, 13-week change": (0.5, -1.5, -4.0, -8.0, False, 100),
    # Passive-concentration channel (Burry): crowding gauge + unwind trigger.
    "SPY/RSP ratio percentile (vs 2010+)": (50, 90, 97, 100, True, 79),  # crowding gauge: caps YELLOW
    "Mega-cap vs equal-weight, 20d relative": (0, -2.5, -4.5, -8.0, False, 100),  # Jul-2024 rotation ~ -4.5%
    # Vol-supply channel (Volmageddon): crowding gauge + the spike trigger.
    "Vol-risk premium percentile (VIX − realized)": (50, 15, 5, 0, False, 79),  # crowded short-vol: caps YELLOW
    "VIX, 5-day change": (0, 8, 15, 25, True, 100),                      # Feb-2018 +20, Aug-2024 spike
}


def _apply_scores(channels: list["PinChannel"]) -> None:
    """Assign part scores from ANCHORS and derive channel score/status.

    Status is recomputed from the score bands, which reproduces the original
    threshold colors exactly (yellow anchor -> 50, red anchor -> 80). Parts
    with no anchor entry keep their existing status and get no score.
    """
    for ch in channels:
        for p in ch.parts:
            a = ANCHORS.get(p.label)
            if a is None or p.value is None:
                continue
            p.score = _pscore(p.value, *a[:4], higher_is_worse=a[4], cap=a[5])
            p.status = _status_from_score(p.score)
        live = [p.score for p in ch.parts if p.score is not None]
        ch.score = round(max(live), 1) if live else None
        statuses = [p.status for p in ch.parts if p.status != "STALE"]
        if statuses:
            ch.status = max(statuses, key=lambda x: RANK[x])
        else:
            ch.status = "STALE"


# Channels that transmit in DAYS with multi-trillion mass — the ones where an
# active red on an already-elevated curve model historically mattered (2008)
# vs. fizzled on a calm backdrop (1998, 2019, Aug 2024). Slow channels
# (private_credit: weeks-months; fiscal: quarters) give time and speak through
# the composite instead.
FAST_HIGH_MASS = {"credit_event", "plumbing", "basis_trade", "carry_unwind"}


def transmission_note(board: dict, prob_12m_pct: float | None,
                      prob_threshold: float = 30.0) -> dict:
    """Qualitative pins->dial link. Deliberately WORDED, never numbered: with
    ~11 recessions there is no data to estimate P(recession | pin config), and
    the NFCI horse race showed conditions indices add nothing to onset
    prediction — so the calibrated probability is never adjusted."""
    red_fast = [c["label"] for c in board["channels"]
                if c["channel_id"] in FAST_HIGH_MASS and c["status"] == "RED"]
    active = bool(red_fast) and prob_12m_pct is not None and prob_12m_pct >= prob_threshold
    return {
        "active": active,
        "fast_red_channels": red_fast,
        "prob_12m_pct": prob_12m_pct,
        "prob_threshold_pct": prob_threshold,
        "message": (
            "Trigger channels active on a loaded gun: "
            + ", ".join(red_fast)
            + f" flashing red while the 12-month curve model reads "
              f"{prob_12m_pct:.0f}%. Accidents that became recessions fired on "
              "exactly this configuration (2008); on a calm macro backdrop they "
              "stayed contained (1998, 2019, Aug 2024)."
        ) if active else "",
    }


def build_pin_board(bundle: dict) -> dict:
    channels: list[PinChannel] = []

    # --- OIL SHOCK -----------------------------------------------------------
    oil = bundle.get("oil", ([], []))[1]
    oil_12m = _pct_change(oil, 252)
    channels.append(PinChannel(
        "oil_shock", "Oil / energy shock",
        _grade(oil_12m, 25.0, 50.0),
        [PinPart("WTI, 12-month change", oil_12m, "%", _grade(oil_12m, 25.0, 50.0),
                 "Sustained +25-50% squeezes real incomes and forces the Fed's hand.")],
        basis="Hamilton: oil price shocks preceded ~10 of 11 postwar recessions.",
        certainty="High historical association; the proxy reads the spark in real time.",
        mass="Household real income (~$20T consumption base)",
        speed="3–12 months",
        kill_rate="Preceded ~10 of 11 postwar recessions (Hamilton)"))

    # --- POLICY SHOCK --------------------------------------------------------
    effr = bundle.get("effr", ([], []))[1]
    hike_12m_bps = None
    ch = _change(effr, 252)
    if ch is not None:
        hike_12m_bps = round(ch * 100.0, 0)
    channels.append(PinChannel(
        "policy_shock", "Central-bank overtightening",
        _grade(hike_12m_bps, 200.0, 300.0),
        [PinPart("Fed funds, 12-month change", hike_12m_bps, "bps",
                 _grade(hike_12m_bps, 200.0, 300.0),
                 "Fast hiking cycles break the weakest balance sheet in the system.")],
        basis="Nearly every modern recession followed a tightening cycle; PACE is the pin.",
        certainty="High-quality proxy; note cuts-into-weakness are the curve panel's domain.",
        mass="The entire economy — rates reprice everything",
        speed="12–24 months (long and variable lags)",
        kill_rate="Nearly every modern recession followed a tightening cycle"))

    # --- CREDIT EVENT --------------------------------------------------------
    hy = bundle.get("hy_oas", ([], []))[1]
    hy_vel = None
    chy = _change(hy, 20)
    if chy is not None:
        hy_vel = round(chy * 100.0, 0)  # pct-pts -> bps
    dw = bundle.get("discount_window", ([], []))[1]
    dw_bil = (_clean(dw)[-1] / 1000.0) if _clean(dw) else None  # H.4.1 is $mm
    if dw_bil is not None:
        dw_bil = round(dw_bil, 1)
    parts = [
        PinPart("HY OAS, 20d change", hy_vel, "bps", _grade(hy_vel, 75.0, 150.0),
                "A spread GAP (not level) is how credit accidents announce themselves."),
        PinPart("Discount-window borrowing", dw_bil, "$B", _grade(dw_bil, 10.0, 50.0),
                "Banks pay the stigma price only under real duress — lit up within days of SVB."),
    ]
    channels.append(PinChannel(
        "credit_event", "Credit / banking accident", _worst(parts), parts,
        basis="2008 subprime, 1998 LTCM, 2023 SVB: credit events announce via spread gaps "
              "and emergency borrowing, not levels.",
        certainty="Fast confirmation (days) rather than prediction — this is the tripwire.",
        mass="Banking system (~$24T assets)",
        speed="Days–weeks once firing",
        kill_rate="High conditional on firing: 2008 (recession), 1998 + 2023 (contained)"))

    # --- FISCAL PIN ----------------------------------------------------------
    ig = bundle.get("interest_gdp", ([], []))[1]
    ig_now = _clean(ig)[-1] if _clean(ig) else None
    tp = bundle.get("acm_tp10", ([], []))[1]
    tp_60d = None
    ctp = _change(tp, 60)
    if ctp is not None:
        tp_60d = round(ctp * 100.0, 0)
    parts = [
        PinPart("Federal interest / GDP", ig_now, "%", _grade(ig_now, 3.0, 4.0),
                "The debt-service spiral: past ~3% of GDP, interest crowds the budget."),
        PinPart("Term premium, 60d change", tp_60d, "bps", _grade(tp_60d, 40.0, 75.0),
                "The market STARTING to charge for fiscal risk — the actual trigger to watch."),
    ]
    channels.append(PinChannel(
        "fiscal", "Fiscal / debt-service pin", _worst(parts), parts,
        basis="Dalio's core scenario: supply overwhelms demand for Treasuries -> term "
              "premium reprices. The flow compass's DEBASEMENT regime is its market symptom.",
        certainty="The level is the loaded gun (slow, certain); the 60d premium move is the spark.",
        mass="$28T+ Treasury market — the world's risk-free anchor",
        speed="Quarters (slow burn, fast finale)",
        kill_rate="No US precedent — the genuinely unprecedented channel"))

    # --- PLUMBING ------------------------------------------------------------
    sofr = bundle.get("sofr", ([], []))[1]
    iorb = bundle.get("iorb", ([], []))[1]
    si = None
    if _clean(sofr) and _clean(iorb):
        si = round((_clean(sofr)[-1] - _clean(iorb)[-1]) * 100.0, 1)
    res = bundle.get("reserves", ([], []))[1]
    res_26w = _pct_change(res, 26)
    rrp = bundle.get("rrp", ([], []))[1]
    rrp_bil = round(_clean(rrp)[-1], 1) if _clean(rrp) else None  # already $B
    parts = [
        PinPart("SOFR − IORB", si, "bps", _grade(si, 5.0, 15.0),
                "Repo trading above the reserves floor = collateral/cash scarcity."),
        PinPart("Reserves, 26-week change", res_26w, "%", _grade(res_26w, -8.0, -15.0, False),
                "QT draining reserves toward the system's unknown minimum."),
        PinPart("RRP buffer", rrp_bil, "$B",
                "STALE" if rrp_bil is None else ("GREEN" if rrp_bil > 100 else "YELLOW"),
                "The shock absorber: when RRP ≈ 0, further QT bites reserves directly."),
    ]
    channels.append(PinChannel(
        "plumbing", "Funding-plumbing seizure", _worst(parts), parts,
        basis="Sept-2019 repo spasm; 2022 gilt/LDI. Plumbing breaks fast and forces the Fed.",
        certainty="High-quality daily/weekly reads; a genuine early-warning channel.",
        mass="Repo/reserves core (~$5T daily funding)",
        speed="Days",
        kill_rate="Forces Fed response (2019 repo) — no recession from plumbing alone yet"))

    # --- BASIS-TRADE UNWIND ----------------------------------------------------
    cot = bundle.get("cot_net_short", ([], []))[1]
    cot_clean = _clean(cot)
    cot_now = cot_clean[-1] if cot_clean else None
    cot_pctl = _percentile(cot, cot_now)
    parts = [
        PinPart("Leveraged-fund net short, UST futures", cot_now, "M contracts",
                _grade(cot_now, 4.0, 5.5),
                "Hedge funds' aggregate net short across the Treasury futures complex — "
                "the cash-futures basis trade. Bigger book = bigger forced unwind."),
        PinPart("Positioning percentile (vs 2010+)", cot_pctl, "%ile",
                _grade(cot_pctl, 85.0, 95.0),
                "How crowded today's book is versus its own history."),
    ]
    channels.append(PinChannel(
        "basis_trade", "Basis-trade unwind", _worst(parts), parts,
        basis="March 2020: the basis trade unwound violently and broke the Treasury "
              "market until the Fed intervened. THIS cycle's known loaded spring.",
        certainty="Weekly CFTC data with a few days' lag; crowding is measurable but the "
                  "unwind trigger (a margin/vol spike) arrives via the other channels.",
        mass="~$1–2T notional cash-futures basis book",
        speed="Days",
        kill_rate="0-for-2 as sole trigger (2019, 2020) — both forced Fed rescue"))

    # --- CORPORATE & PRIVATE CREDIT ------------------------------------------
    # This cycle's untested leverage: ~$1.7T private credit + ~$1.3T of bank
    # loans funding it. Private marks lag; public CCC is the real-time window.
    ccc_d, ccc_v = bundle.get("ccc_oas", ([], []))
    bbb_d, bbb_v = bundle.get("bbb_oas", ([], []))
    ccc_clean = _clean(ccc_v)
    ccc_now = ccc_clean[-1] if ccc_clean else None
    ccc_pctl = _percentile(ccc_v, ccc_now)
    # CCC minus BBB, date-aligned: the distress-vs-perfection bifurcation.
    cm = {d: v for d, v in zip(ccc_d, ccc_v) if v is not None}
    bm = {d: v for d, v in zip(bbb_d, bbb_v) if v is not None}
    disp_series = [cm[d] - bm[d] for d in sorted(set(cm) & set(bm))]
    disp_now = round(disp_series[-1], 2) if disp_series else None
    disp_pctl = _percentile(disp_series, disp_now)
    ndfi = bundle.get("ndfi_loans", ([], []))[1]
    ndfi_now = _clean(ndfi)[-1] if _clean(ndfi) else None
    parts = [
        PinPart("CCC spread percentile (vs 1996+)", ccc_pctl, "%ile",
                _grade(ccc_pctl, 85.0, 95.0),
                f"CCC-and-lower OAS now {ccc_now if ccc_now is not None else 'n/a'}% — "
                "where refinancing distress prices first; private-credit marks follow with a lag."),
        PinPart("CCC−BBB dispersion percentile", disp_pctl, "%ile",
                _grade(disp_pctl, 85.0, 95.0),
                f"Gap now {disp_now if disp_now is not None else 'n/a'}pp. IG priced for "
                "perfection while the distress tier cracks = bifurcation an aggregate HY level hides."),
        PinPart("Bank loans to NDFIs, m/m ann. growth", ndfi_now, "%",
                _grade(ndfi_now, 5.0, 0.0, False),
                "Banks bankroll private-credit funds (H.8 breakout). A stall here is the "
                "private-credit margin call arriving via its funding."),
    ]
    channels.append(PinChannel(
        "private_credit", "Corporate & private credit", _worst(parts), parts,
        basis="This cycle's leverage grew OUTSIDE banks: ~$1.7T private credit, record "
              "maturity wall. No prior recession had this structure — past-bubble "
              "channels alone would miss it.",
        certainty="Public CCC is a real-time proxy; private marks themselves are opaque "
                  "and lag by quarters. NDFI series starts 2015 (young history).",
        mass="~$3T (private credit ~$1.7T + ~$1.3T bank NDFI loans)",
        speed="Weeks–months",
        kill_rate="Untested at this size — no prior cycle carried it"))

    # --- CARRY-TRADE UNWIND ----------------------------------------------------
    jpy = bundle.get("jpy", ([], []))[1]
    jpy_1m = _pct_change(jpy, 21)   # negative = yen appreciating = carry stress
    jgb = bundle.get("jgb10", ([], []))[1]
    jgb_clean = _clean(jgb)
    jgb_now = jgb_clean[-1] if jgb_clean else None
    jgb_12m = None
    cj = _change(jgb, 12)           # monthly series -> 12 obs = 12 months
    if cj is not None:
        jgb_12m = round(cj * 100.0, 0)
    parts = [
        PinPart("USD/JPY, 1-month change", jpy_1m, "%",
                _grade(jpy_1m, -4.0, -7.0, False),
                "Falling = yen appreciating = levered carry positions forced to unwind "
                "(Aug 2024: ~8% appreciation in a month cascaded into global risk assets)."),
        # Cushion leg, not the trigger: caps at YELLOW (like plumbing's RRP
        # buffer) — only the FX leg actually firing can take the channel RED.
        PinPart("10y JGB yield, 12-month change", jgb_12m, "bps",
                "STALE" if jgb_12m is None else ("YELLOW" if jgb_12m >= 50.0 else "GREEN"),
                f"JGB 10y now {jgb_now if jgb_now is not None else 'n/a'}% — rising Japanese "
                "yields compress the carry cushion and pull capital home. Pressure gauge: "
                "caps at YELLOW; the yen leg is the trigger."),
    ]
    channels.append(PinChannel(
        "carry_unwind", "Yen-carry unwind", _worst(parts), parts,
        basis="August 2024 demonstrated the mechanism: BoJ hike -> yen surge -> multi-day "
              "global deleveraging. The funding leg of trillions in global positions.",
        certainty="FX read is daily and clean; JGB series is monthly with ~2-month lag. "
                  "Historically produces vol shocks, not recessions — so far.",
        mass="Multi-$T yen-funded carry complex",
        speed="Days",
        kill_rate="Vol shocks only (Aug 2024) — no recession attributed yet"))

    # --- UNCERTAINTY / GEOPOLITICS -------------------------------------------
    epu_d, epu_v = bundle.get("epu", ([], []))
    epu30 = None
    c = _clean(epu_v)
    if len(c) >= 30:
        epu30 = round(sum(c[-30:]) / 30.0, 1)
    epu_pctl = _percentile(epu_v, epu30)
    channels.append(PinChannel(
        "uncertainty", "Uncertainty / geopolitical shock",
        _grade(epu_pctl, 90.0, 97.5),
        [PinPart("EPU index, 30d avg (percentile)", epu_pctl, "%ile",
                 _grade(epu_pctl, 90.0, 97.5),
                 f"30d avg {epu30 if epu30 is not None else 'n/a'} vs full history since 1985.")],
        basis="Wars, embargoes, tariff shocks, standoffs — exogenous pins show up as "
              "policy-uncertainty spikes before they show up in earnings.",
        certainty="Noisiest channel: elevated uncertainty often resolves benignly. Context, "
                  "not confirmation.",
        mass="Unbounded (exogenous shocks)",
        speed="Fast to spike, often slow to bite",
        kill_rate="Noisiest channel — most spikes resolve benignly"))

    # --- DEMAND STRIKE (Dalio) ----------------------------------------------
    # The Big-Debt-Cycle trigger in its literal form: more Treasury supply than
    # demand at prevailing prices. Auction tape (bid-to-cover, foreign share)
    # + the Fed custody account (weekly read on foreign official selling).
    auctions = bundle.get("auctions") or []
    coupons = [a for a in auctions if a.get("bid_to_cover") is not None]
    b2c_4 = ind_4 = None
    if len(coupons) >= 4:
        last4 = coupons[-4:]
        b2c_4 = round(sum(a["bid_to_cover"] for a in last4) / 4.0, 2)
        ind = [a.get("indirect_pct") for a in last4 if a.get("indirect_pct") is not None]
        ind_4 = round(sum(ind) / len(ind), 1) if ind else None
    cust = bundle.get("custody", ([], []))[1]
    cust_13w = _pct_change(cust, 13)
    parts = [
        PinPart("Coupon bid-to-cover, last 4 auctions", b2c_4, "x", "STALE",
                "Demand insufficient at the prevailing price shows up here first — "
                "sub-2.2x coupon tapes are what a buyer's strike looks like."),
        PinPart("Indirect (foreign) share, last 4 auctions", ind_4, "%", "STALE",
                "Foreign central banks/SWFs stepping back from auctions — the demand "
                "side of Dalio's supply/demand imbalance."),
        PinPart("Foreign custody holdings, 13-week change", cust_13w, "%", "STALE",
                "Fed custody account (H.4.1): the cleanest weekly read on whether "
                "foreign officials are net sellers between auctions."),
    ]
    channels.append(PinChannel(
        "demand_strike", "Treasury demand strike", "STALE", parts,
        basis="Dalio's Big Debt Cycle end-game: debt sales exceed demand -> price falls "
              "or the central bank prints. Auction tails/weak bid-to-cover are the tape "
              "of that imbalance forming.",
        certainty="Auction data is exact but episodic (per-auction); custody is weekly. "
                  "A weak single auction is noise — a weak RUN of them is the signal.",
        mass="$28T+ Treasury market; ~$3.3T foreign-official custody",
        speed="Weeks (auction cycle), fast finale if it compounds",
        kill_rate="No full US precedent; UK gilts Sept-2022 is the modern template"))

    # --- PASSIVE CONCENTRATION (Burry) ----------------------------------------
    # Cap-weight concentration is the gun (top-10 ~34% of S&P vs 18% in 2010);
    # the pin is the rotation OUT — mega-caps underperforming equal-weight fast
    # forces de-facto passive selling of the biggest names.
    spy = bundle.get("spy", ([], []))[1]
    rsp = bundle.get("rsp", ([], []))[1]
    ratio_pctl = rel_20d = None
    cs, cr = _clean(spy), _clean(rsp)
    if len(cs) > 300 and len(cr) > 300:
        n = min(len(cs), len(cr))
        ratio = [cs[-n + i] / cr[-n + i] for i in range(n)]
        ratio_pctl = _percentile(ratio, ratio[-1])
        if n > 21:
            rel_20d = round(((cs[-1] / cs[-22]) - (cr[-1] / cr[-22])) * 100.0, 2)
    parts = [
        PinPart("SPY/RSP ratio percentile (vs 2010+)", ratio_pctl, "%ile", "STALE",
                "Cap-weight vs equal-weight: how concentrated the index bid is versus "
                "its own history. Crowding gauge — caps at YELLOW."),
        PinPart("Mega-cap vs equal-weight, 20d relative", rel_20d, "%", "STALE",
                "The trigger: mega-caps underperforming the average stock FAST "
                "(Jul-2024 rotation ~ -4.5%/20d) is the passive bid reversing."),
    ]
    channels.append(PinChannel(
        "concentration", "Passive-concentration unwind", "STALE", parts,
        basis="Burry's index thesis made measurable: top-10 weight ~34% of the S&P "
              "(vs 18% in 2010). Flows into cap-weight funds are price-insensitive on "
              "the way in — and on the way out.",
        certainty="Ratio is a clean daily proxy for concentration, not a direct flow "
                  "read. Rotations can be benign (2024) absent leverage.",
        mass="~$12T+ indexed to cap-weight S&P vehicles",
        speed="Weeks",
        kill_rate="Untested at current concentration — 2000 tech unwind is the analog"))

    # --- VOL SUPPLY / GAMMA (Volmageddon) --------------------------------------
    # Crowded short-vol + thin realized vol = the spring; a fast VIX repricing
    # is the release (Feb-2018: XIV -90% overnight; 0DTE now ~59% of SPX volume).
    vix = bundle.get("vix", ([], []))[1]
    spx = bundle.get("sp500", ([], []))[1]
    vrp_pctl = vix_5d = None
    cv, cx = _clean(vix), _clean(spx)
    if len(cv) > 300 and len(cx) > 300:
        rets = [(cx[i] / cx[i - 1] - 1) for i in range(1, len(cx))]
        import math as _m
        rv = []
        for i in range(20, len(rets)):
            w = rets[i - 20:i]
            mu = sum(w) / 20
            rv.append(_m.sqrt(sum((x - mu) ** 2 for x in w) / 19) * _m.sqrt(252) * 100)
        n = min(len(cv), len(rv))
        vrp = [cv[-n + i] - rv[-n + i] for i in range(n)]
        vrp_pctl = _percentile(vrp, vrp[-1])
        vix_5d = round(_change(vix, 5) or 0.0, 1) if _change(vix, 5) is not None else None
    parts = [
        PinPart("Vol-risk premium percentile (VIX − realized)", vrp_pctl, "%ile", "STALE",
                "Compressed premium = short-vol sellers crowded in for thin carry. "
                "Crowding gauge — caps at YELLOW."),
        PinPart("VIX, 5-day change", vix_5d, "pts", "STALE",
                "The release: a fast repricing forces dealer/ETP rebalancing into "
                "the move (Feb-2018 +20pts; Aug-2024 spike)."),
    ]
    channels.append(PinChannel(
        "vol_supply", "Vol-supply unwind", "STALE", parts,
        basis="Volmageddon mechanism: short-vol products + dealer hedging turn a vol "
              "spike into forced selling. 0DTE is now ~59% of SPX option volume — the "
              "vol-supply complex is bigger than 2018, differently structured.",
        certainty="VRP from VIX minus 20d realized is a standard but coarse crowding "
                  "proxy; dealer gamma positioning itself is not freely observable.",
        mass="SPX options ~4M contracts/day; multi-$B vol-selling ETPs",
        speed="Days",
        kill_rate="Vol shocks, not recessions (Feb-2018, Aug-2024) — but margin "
                  "spirals are how other channels get triggered"))

    _apply_scores(channels)

    live = [ch for ch in channels if ch.status != "STALE"]
    n_red = sum(1 for ch in live if ch.status == "RED")
    n_yellow = sum(1 for ch in live if ch.status == "YELLOW")
    overall = "RED" if n_red else ("YELLOW" if n_yellow else ("GREEN" if live else "STALE"))
    scores = [ch.score for ch in channels if ch.score is not None]
    pressure = round(sum(scores) / len(scores), 1) if scores else None
    hottest = max((ch for ch in channels if ch.score is not None),
                  key=lambda c: c.score, default=None)

    return {
        "channels": [ch.as_dict() for ch in channels],
        "overall": overall, "n_red": n_red, "n_yellow": n_yellow,
        "n_live": len(live), "n_channels": len(channels),
        "pressure": pressure,
        "hottest": {"channel_id": hottest.channel_id, "label": hottest.label,
                    "score": hottest.score} if hottest else None,
        "framing": "The gun is the debt/vulnerability buildup (tracked across this "
                   "dashboard); the pin is the trigger. Pins are inherently hard to "
                   "predict — this board watches the channels historical pricks arrived "
                   "through, so a spark is visible in days, not hindsight.",
    }
