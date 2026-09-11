"""Duration Squeeze Radar — the pre-registered fuel/trigger scorecard.

REGISTERED SPEC: docs/research/tlt-squeeze-2026/scorecard_spec.md v2
(frozen 2026-08-25, counter-agent reviewed). The thresholds below are that
registration; retuning them requires a new pre-registration commit, never a
quiet edit. Design finding the card exists to encode: positioning is FUEL,
never ignition — 0 of 22 large long-bond rallies since 1986 were identified
as positioning-caused (and the design cannot rule such episodes out), so the
card separates fuel from triggers and pushes the operator's attention to the
trigger CALENDAR, which is mostly scheduled dates.

Honesty carried on the payload itself: the conditional edge of crowded
shorts is WITHIN NOISE (~22 independent episodes); the trigger side scored
2/5 the day before the Nov-2023 rally — near-zero anticipatory power for
ignition events. This card classifies the state; it does not forecast dates.

Pure build function: every input injected, no I/O here (gate-testable).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

# ── the registration (spec v2) ───────────────────────────────────────────────
F1_PCTILE_MAX = 0.10          # lev-fund UST net %OI, trailing-10y percentile
F1_WINDOW_WEEKS = 520
F2_SI_PCT_SO_MIN = 20.0       # TLT short interest as % of shares outstanding
F3_TP_PCTILE_MIN = 0.75       # ACM 10y TP percentile since 2015
F3_SINCE = date(2015, 1, 1)
T1_CUTS_PRICED_BP = -50.0     # ZQ-implied 6m change; STRICT < (spec: ">50bp")
T2_PAYROLLS_3M_AVG = 0.0      # < 0k, OR
T2_SAHM_MIN = 0.50            # >= 0.50
T3_CORE_PCE_3M_ANN = 2.5      # < 2.5% 3m annualized
T5_MOVE_MIN = 120.0           # AND HY OAS wider than 3m ago
T5_OAS_LOOKBACK_D = 91

# T4 (supply pivot: QRA coupon cuts or long-end buybacks >$25B/qtr) is a
# policy-event judgment, not a feed. It changes ONLY by commit, with the
# rationale and as-of date carried to the UI. Registered threshold unchanged.
T4_MANUAL = {
    "state": "PARTIAL",
    "asof": "2026-08-25",
    "rationale": ("Coupon auction sizes frozen ~2yrs (Aug 2026 QRA: 'at least "
                  "the next several quarters'); long-end buybacks doubled to "
                  ">=$4B/op Sep-Nov (~$8B/qtr long-end) — intent without "
                  "scale vs the >$25B/qtr registered bar."),
}

# T1's FIRST leg ("first cut after >=6-mo hold") is an FOMC-day event, not
# a feed. Like T4 it changes ONLY by commit, on the day it happens, with
# rationale and as-of carried to the UI. False until a first cut lands.
T1_MANUAL_FIRST_CUT = {
    "confirmed": False,
    "asof": "2026-08-25",
    "rationale": ("no 2026 cut has occurred (Warsh FOMC: zero cuts YTD, "
                  "Sept-hike odds priced); flip by commit on the FOMC day a "
                  "first cut after a >=6-month hold lands"),
}

# F4 (borrow stress: fee >1% or utilization >90%) has no free live feed —
# Ortex/Fintel are paywalled. The condition stays on the card as UNVERIFIED
# (counted 0, like NOT MET) with DTC shown as context; wiring a licensed
# feed later changes the source, not the registration.

MET, PARTIAL, NOT_MET, UNVERIFIED, STALE = ("MET", "PARTIAL", "NOT_MET",
                                            "UNVERIFIED", "STALE")
_SCORE = {MET: 1.0, PARTIAL: 0.5, NOT_MET: 0.0, UNVERIFIED: 0.0, STALE: 0.0}


@dataclass
class Condition:
    id: str
    label: str
    threshold: str
    state: str
    value: float | None = None
    unit: str = ""
    detail: str = ""
    asof: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _pctile(hist: list[float], v: float) -> float:
    """Fraction of history strictly below v (the study's convention)."""
    if not hist:
        return 0.5
    return sum(1 for h in hist if h < v) / len(hist)


def _last(dates: list, vals: list) -> tuple[date | None, float | None]:
    for d, v in zip(reversed(dates), reversed(vals)):
        if v is not None:
            return d, v
    return None, None


# ── conditions ───────────────────────────────────────────────────────────────

def cond_f1(cot_dates: list[date], cot_pct_oi: list[float]) -> Condition:
    c = Condition("F1", "Futures short extreme",
                  "lev-fund UST net %OI ≤10th pctile (10y window)", STALE)
    if not cot_dates:
        return c
    cur = cot_pct_oi[-1]
    hist = cot_pct_oi[-F1_WINDOW_WEEKS:]
    p = _pctile(hist, cur)
    c.value, c.unit, c.asof = round(cur, 1), "%OI", cot_dates[-1].isoformat()
    c.detail = f"{p:.0%} pctile of trailing 10y"
    c.state = MET if p <= F1_PCTILE_MAX else NOT_MET
    return c


def cond_f2(si_rows: list[dict], shares_outstanding: float | None) -> Condition:
    c = Condition("F2", "ETF short base",
                  f"TLT SI ≥{F2_SI_PCT_SO_MIN:.0f}% of shares outstanding", STALE)
    if not si_rows:
        return c
    last = si_rows[-1]
    c.asof = last["settlement_date"]
    if not shares_outstanding or shares_outstanding <= 0:
        c.detail = (f"{last['shares_short']/1e6:.0f}M shares short; shares "
                    f"outstanding unavailable — %SO not computable")
        return c
    pct = 100.0 * last["shares_short"] / shares_outstanding
    prev = (100.0 * si_rows[-2]["shares_short"] / shares_outstanding
            if len(si_rows) > 1 else None)
    c.value, c.unit = round(pct, 1), "%SO"
    c.detail = (f"{last['shares_short']/1e6:.0f}M short / "
                f"{shares_outstanding/1e6:.0f}M out"
                + (f"; prior settlement {prev:.1f}%" if prev is not None else "")
                + " — SO is TODAY'S (creations shift the denominator)")
    c.state = MET if pct >= F2_SI_PCT_SO_MIN else NOT_MET
    return c


def cond_f3(tp_dates: list, tp_vals: list) -> Condition:
    c = Condition("F3", "Term-premium cushion",
                  "ACM 10y TP ≥75th pctile since 2015", STALE)
    pairs = [(d, v) for d, v in zip(tp_dates, tp_vals)
             if v is not None and d >= F3_SINCE]
    if not pairs:
        return c
    hist = [v for _, v in pairs]
    d, cur = pairs[-1]
    p = _pctile(hist, cur)
    c.value, c.unit, c.asof = round(cur, 2), "pp", d.isoformat()
    c.detail = f"{p:.0%} pctile since 2015"
    c.state = MET if p >= F3_TP_PCTILE_MIN else NOT_MET
    return c


def cond_f4(si_rows: list[dict]) -> Condition:
    c = Condition("F4", "Borrow stress", "fee >1% or utilization >90%",
                  UNVERIFIED)
    if si_rows:
        last = si_rows[-1]
        c.asof = last["settlement_date"]
        if last.get("dtc") is not None:
            c.value, c.unit = last["dtc"], "DTC"
    c.detail = ("no free borrow feed (Ortex/Fintel paywalled) — UNVERIFIED, "
                "scored 0; days-to-cover shown as context")
    return c


def cond_t1(chg_6m_bp: float | None, today: date | None = None) -> Condition:
    c = Condition("T1", "Fed pivot",
                  "first cut after ≥6-mo hold, or >50bp cuts priced 6m", STALE)
    manual = bool(T1_MANUAL_FIRST_CUT["confirmed"])
    if chg_6m_bp is None and not manual:
        c.detail = ("first-cut leg is MANUAL (by commit, T4 pattern) and "
                    f"unconfirmed as of {T1_MANUAL_FIRST_CUT['asof']}; "
                    "priced-cuts leg STALE")
        return c
    if chg_6m_bp is not None:
        c.value, c.unit = chg_6m_bp, "bp/6m"
    c.asof = (today or date.today()).isoformat()
    c.detail = ("ZQ-implied 6m path (first-order). The first-cut-after-hold "
                "leg is MANUAL — flipped by commit on the FOMC day it "
                f"happens (unconfirmed as of {T1_MANUAL_FIRST_CUT['asof']}), "
                "NOT scored automatically")
    priced = chg_6m_bp is not None and chg_6m_bp < T1_CUTS_PRICED_BP
    c.state = MET if (manual or priced) else NOT_MET
    return c


def cond_t2(pay_dates: list, pay_vals: list,
            sahm_dates: list, sahm_vals: list) -> Condition:
    c = Condition("T2", "Labor break",
                  "payrolls 3-mo avg chg <0k or Sahm ≥0.50", STALE)
    lvls = [(d, v) for d, v in zip(pay_dates, pay_vals) if v is not None]
    sd, sv = _last(sahm_dates, sahm_vals)
    if len(lvls) < 4 and sv is None:
        return c
    avg3 = None
    if len(lvls) >= 4:
        span = (lvls[-1][0] - lvls[-4][0]).days
        if span > 100:
            # a gap makes a "monthly" change span 2+ months — a silent basis
            # shift. Refuse the payrolls leg rather than mislabel it.
            c.detail = (f"payrolls STALE: last 4 prints span {span}d "
                        f"(missing months)")
            sd2, sv2 = _last(sahm_dates, sahm_vals)
            if sv2 is not None:
                c.detail += f"; Sahm {sv2:+.2f} ({sd2})"
                c.state = MET if sv2 >= T2_SAHM_MIN else NOT_MET
            return c
        chgs = [lvls[i][1] - lvls[i - 1][1] for i in range(len(lvls) - 3, len(lvls))]
        avg3 = sum(chgs) / 3.0
        c.value, c.unit, c.asof = round(avg3, 0), "k/mo", lvls[-1][0].isoformat()
    c.detail = (f"3m avg {avg3:+.0f}k" if avg3 is not None else "payrolls STALE") + \
               (f"; Sahm {sv:+.2f} ({sd})" if sv is not None else "; Sahm STALE")
    met = (avg3 is not None and avg3 < T2_PAYROLLS_3M_AVG) or \
          (sv is not None and sv >= T2_SAHM_MIN)
    c.state = MET if met else NOT_MET
    return c


def cond_t3(pce_dates: list, pce_vals: list) -> Condition:
    c = Condition("T3", "Inflation runway",
                  "core PCE 3-mo annualized <2.5%", STALE)
    lvls = [(d, v) for d, v in zip(pce_dates, pce_vals) if v is not None]
    if len(lvls) < 4:
        return c
    if (lvls[-1][0] - lvls[-4][0]).days > 100:
        c.detail = (f"STALE: last 4 prints span "
                    f"{(lvls[-1][0] - lvls[-4][0]).days}d (missing months) — "
                    f"3m-annualized basis would silently shift")
        return c
    ann = ((lvls[-1][1] / lvls[-4][1]) ** 4 - 1) * 100.0
    c.value, c.unit, c.asof = round(ann, 2), "%3m-ann", lvls[-1][0].isoformat()
    c.detail = "single-gauge fragility: core CPI momentum can disagree (Aug-26: it did)"
    c.state = MET if ann < T3_CORE_PCE_3M_ANN else NOT_MET
    return c


def cond_t4() -> Condition:
    return Condition("T4", "Supply pivot",
                     "QRA coupon cuts or long-end buybacks >$25B/qtr",
                     T4_MANUAL["state"],
                     detail=f"manual (by commit): {T4_MANUAL['rationale']}",
                     asof=T4_MANUAL["asof"])


def cond_t5(move_dates: list, move_vals: list,
            oas_dates: list, oas_vals: list) -> Condition:
    c = Condition("T5", "Vol/dislocation",
                  "MOVE >120 and HY OAS wider than 3m ago", STALE)
    md, mv = _last(move_dates, move_vals)
    od, ov = _last(oas_dates, oas_vals)
    if mv is None or ov is None:
        return c
    prior = [v for d, v in zip(oas_dates, oas_vals)
             if v is not None and d <= od - timedelta(days=T5_OAS_LOOKBACK_D)]
    c.value, c.unit, c.asof = round(mv, 0), "MOVE", md.isoformat()
    if not prior:
        # the widening leg is UNVERIFIABLE — that is a STALE, not a verdict
        c.detail = f"HY OAS {ov:.2f}; no 3m-ago reading — widening leg unverifiable"
        return c
    c.detail = (f"HY OAS {ov:.2f} vs {prior[-1]:.2f} 3m ago — fires on "
                f"duration capitulation too, not only flight-to-quality")
    c.state = MET if (mv > T5_MOVE_MIN and ov > prior[-1]) else NOT_MET
    return c


# ── calendar (the "get in earlier" mechanism) ────────────────────────────────
# FOMC dates are the Fed's published 2026 schedule; verify against
# federalreserve.gov when 2027 is added. Everything estimated is flagged.
FOMC_2026 = ["2026-09-15", "2026-09-16", "2026-10-27", "2026-10-28",
             "2026-12-08", "2026-12-09"]


def _next_qra(today: date) -> date:
    """Refunding statement lands the Wednesday of the first week of
    Feb/May/Aug/Nov (estimated — Treasury publishes exact dates ~a week out)."""
    for months in range(0, 13):
        y = today.year + (today.month - 1 + months) // 12
        m = (today.month - 1 + months) % 12 + 1
        if m in (2, 5, 8, 11):
            d = date(y, m, 1)
            d += timedelta(days=(2 - d.weekday()) % 7)     # first Wednesday
            if d >= today:
                return d
    return today  # unreachable


def build_calendar(today: date, horizon_days: int = 45) -> list[dict]:
    out: list[dict] = []
    q = _next_qra(today)
    if (q - today).days <= horizon_days:
        out.append({"event": "QRA refunding statement", "date": q.isoformat(),
                    "estimated": True})
    fomc_days = [date.fromisoformat(d) for d in FOMC_2026]
    for i in range(0, len(fomc_days), 2):
        if today <= fomc_days[i + 1] and (fomc_days[i] - today).days <= horizon_days:
            out.append({"event": "FOMC decision", "date": fomc_days[i + 1].isoformat(),
                        "estimated": False})
    if not any(today <= d for d in fomc_days):
        # the hardcoded table has run out — the "get in earlier" mechanism
        # must fail LOUDLY, not by silently dropping FOMC coverage
        out.append({"event": ("FOMC schedule table EXHAUSTED — add next "
                              "year's published dates to metrics/squeeze.py"),
                    "date": today.isoformat(), "estimated": True,
                    "warning": True})
    for months in (0, 1):
        y = today.year + (today.month - 1 + months) // 12
        m = (today.month - 1 + months) % 12 + 1
        cpi = date(y, m, 12)
        if today <= cpi and (cpi - today).days <= horizon_days:
            out.append({"event": "CPI release", "date": cpi.isoformat(),
                        "estimated": True})
        auct = date(y, m, 12)
        if today <= auct and (auct - today).days <= horizon_days:
            out.append({"event": "30y auction (watch tail/bid-to-cover)",
                        "date": auct.isoformat(), "estimated": True})
        eom = (date(y, m, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        while eom.weekday() >= 5:
            eom -= timedelta(days=1)
        if today <= eom and (eom - today).days <= horizon_days:
            out.append({"event": "PCE release", "date": eom.isoformat(),
                        "estimated": True})
    out.sort(key=lambda e: e["date"])
    return out


# ── assembly ─────────────────────────────────────────────────────────────────

def build_squeeze_radar(*, cot: tuple, si_rows: list[dict],
                        shares_outstanding: float | None,
                        tp: tuple, fed_chg_6m_bp: float | None,
                        payrolls: tuple, sahm: tuple, core_pce: tuple,
                        move: tuple, hy_oas: tuple,
                        today: date | None = None) -> dict:
    today = today or date.today()
    fuel = [cond_f1(*cot), cond_f2(si_rows, shares_outstanding),
            cond_f3(*tp), cond_f4(si_rows)]
    trig = [cond_t1(fed_chg_6m_bp, today), cond_t2(*payrolls, *sahm),
            cond_t3(*core_pce), cond_t4(), cond_t5(*move, *hy_oas)]
    return {
        "asof": today.isoformat(),
        "fuel": [c.to_dict() for c in fuel],
        "triggers": [c.to_dict() for c in trig],
        "fuel_score": sum(_SCORE[c.state] for c in fuel),
        "trigger_score": sum(_SCORE[c.state] for c in trig),
        "calendar": build_calendar(today),
        "spec": "docs/research/tlt-squeeze-2026/scorecard_spec.md v2 (frozen 2026-08-25)",
        "honesty": [
            "Positioning is fuel, never ignition: 0/22 large long-bond rallies "
            "since 1986 identified as positioning-caused (design cannot rule out).",
            "Crowded-short conditional edge is WITHIN NOISE (~22 independent "
            "episodes); the robust finding is NO directional edge.",
            "Trigger side scored 2/5 the day before the Nov-2023 +21% rally — "
            "this card classifies state, it does not forecast ignition dates.",
            "Estimated calendar dates are approximations; verify official schedules.",
        ],
    }
