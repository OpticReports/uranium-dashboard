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

    def as_dict(self) -> dict:
        return {"label": self.label, "value": self.value, "unit": self.unit,
                "status": self.status, "detail": self.detail}


@dataclass
class PinChannel:
    channel_id: str
    label: str
    status: str          # worst non-STALE part; STALE if none live
    parts: list[PinPart] = field(default_factory=list)
    basis: str = ""      # historical basis for this channel
    certainty: str = ""  # honest note on signal quality/latency

    def as_dict(self) -> dict:
        return {"channel_id": self.channel_id, "label": self.label, "status": self.status,
                "parts": [p.as_dict() for p in self.parts], "basis": self.basis,
                "certainty": self.certainty}


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
        certainty="High historical association; the proxy reads the spark in real time."))

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
        certainty="High-quality proxy; note cuts-into-weakness are the curve panel's domain."))

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
        certainty="Fast confirmation (days) rather than prediction — this is the tripwire."))

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
        certainty="The level is the loaded gun (slow, certain); the 60d premium move is the spark."))

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
        certainty="High-quality daily/weekly reads; a genuine early-warning channel."))

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
                  "not confirmation."))

    live = [ch for ch in channels if ch.status != "STALE"]
    n_red = sum(1 for ch in live if ch.status == "RED")
    n_yellow = sum(1 for ch in live if ch.status == "YELLOW")
    overall = "RED" if n_red else ("YELLOW" if n_yellow else ("GREEN" if live else "STALE"))

    return {
        "channels": [ch.as_dict() for ch in channels],
        "overall": overall, "n_red": n_red, "n_yellow": n_yellow,
        "n_live": len(live), "n_channels": len(channels),
        "framing": "The gun is the debt/vulnerability buildup (tracked across this "
                   "dashboard); the pin is the trigger. Pins are inherently hard to "
                   "predict — this board watches the channels historical pricks arrived "
                   "through, so a spark is visible in days, not hindsight.",
    }
