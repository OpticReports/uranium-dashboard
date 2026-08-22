"""ROUND 7 — the 20-year core test: B.5 Enhanced vs SPY from 2006-10-05.

Contract: docs/VARIANTS_PREREGISTRATION_R7_20Y.md, committed (b7cf770) BEFORE
any line of this file existed. Everything registered there is reproduced here
verbatim and nothing is added: the proxy map, the splice rule, the three
unproxiable-leg treatments T1/T2/T3, the QUAL sensitivity, the named regimes,
and the judgment protocol carried from rounds 4-6. **There is no blend / R2-A
arm** — the registration forbids one and says why (R2-A's curve cannot be
extended to 2006 without a survivorship audit).

WHY THIS ROUND EXISTS. B.5's entire claim is a shallower drawdown. Rounds 4-6
measured it over 5.7 years that contain no crisis. 2008 is the first real test
of the claim in the whole campaign, and the honest complication is that at the
2006 start 19% of the book (KMLM 14% + TAIL 5%) has NO instrument in existence
and another 9% (QUAL) has only a crude stand-in. T1/T2/T3 are not three
opinions to choose between; they are the honest RANGE, and the registration is
explicit: "A conclusion that does not hold across T1-T3 is not a conclusion."

FROZEN CODE. `scripts/backtest_core_variants.py` carries the rounds 4-6 record
and is under concurrent counter-agent review; it is imported READ-ONLY here and
not modified. `splice_with_provenance` below is a deliberate copy of its
`spliced()` (same splice semantics) extended to record WHICH source paid each
day, because that provenance is the honesty box of this round.

Usage:
  python -m scripts.backtest_core_20y --gate-only
  python -m scripts.backtest_core_20y --json data/backtest_core_20y_r7_results.json --report
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

# READ-ONLY imports from the frozen rounds 4-6 harness: metrics conventions,
# the portfolio/band engine and the paired block bootstrap, unchanged.
from scripts.backtest_core_variants import (
    B5_BAND_REL,
    B5_CAL_FALLBACK_D,
    B5_WEIGHTS,
    BOOT_BLOCK,
    BOOT_DRAWS,
    BOOT_SEED,
    COST_BPS,
    block_bootstrap_sharpe_diff,
    boot_ci,
    curve_returns,
    metrics,
    portfolio,
)
from scripts.lib import fmp_prices as fmp

BACKEND = Path(__file__).resolve().parent.parent
RESULTS = BACKEND / "data" / "backtest_core_20y_r7_results.json"
REPORT = BACKEND.parent / "docs" / "BACKTEST_CORE_20Y_R7.md"
CONTRACT = "docs/VARIANTS_PREREGISTRATION_R7_20Y.md"

# --- registered window ---------------------------------------------------------------
# The start is not a choice: the plan caps a response at 5,000 rows, which is
# where SPY's history stops. The end matches rounds 4-6.
START, END = "2006-10-05", "2026-08-19"

# --- registered proxy map (VARIANTS_PREREGISTRATION_R7_20Y.md) ------------------------
# leg -> proxies in priority order. Real fund returns wherever they exist; before
# inception the proxy's OWN returns, UNADJUSTED — no alpha added, no beta scaling.
PROXY_MAP = {
    "AVUV": ["SLYV"],   # overlap corr 0.976, TE 6.1%
    "AVDV": ["DLS"],    # 0.960, 5.6%
    "AVEM": ["EEM"],    # 0.984, 4.0%
    "PHYS": ["GLD"],    # same underlying metal
    "QUAL": ["SPY"],    # CRUDE stand-in before 2013-07-18, registered as such
    "KMLM": ["WTMF"],   # WTMF from 2011-01-05; NO instrument before that
    "TAIL": [],         # NO instrument before 2017-04-06
}
CASH_PROXY = ["SHY"]                 # BIL is proxied by SHY before 2007-05-30
# The spine: symbols that cover the whole window and therefore define the
# trading calendar. Every one of them is a registered proxy or a comparator.
SPINE = ["SPY", "SLYV", "DLS", "EEM", "GLD", "SHY"]
UNIVERSE = SPINE + ["BIL", "AVUV", "AVDV", "AVEM", "PHYS", "QUAL", "KMLM", "WTMF", "TAIL"]

# The legs with no instrument at the 2006 start — the reason T1/T2/T3 exist.
GAP_LEGS = ("KMLM", "TAIL")
QUAL_LEG = "QUAL"

TREATMENTS = {
    "T1": "proxy-where-possible, CASH (BIL/SHY) in the gap",
    "T2": "proxy-where-possible, the missing leg REALLOCATED pro-rata in the gap",
    "T3": "CASH for the whole KMLM+TAIL leg across the WHOLE window",
}

# --- registered named regimes ---------------------------------------------------------
# NOT equal thirds. Fixed in the registration, quoted here.
REGIMES = [
    ("GFC", "2007-10-09", "2009-03-09"),
    ("recovery", "2009-03-10", "2019-12-31"),
    ("COVID", "2020-02-19", "2020-03-23"),
    ("2022", "2022-01-03", "2022-10-12"),
    ("round-4/5 window", "2020-12-03", "2026-08-19"),
]


# --- splice ---------------------------------------------------------------------------

def splice_with_provenance(sources: list[tuple[str, dict[str, float]]],
                           dates: list[str]) -> tuple[dict[str, float], dict[str, int]]:
    """Return-splice a level series onto `dates`, recording who paid each day.

    COPY of `scripts.backtest_core_variants.spliced()` (frozen; not edited),
    with two changes and no others: sources are passed as explicit
    (name, series) pairs so synthetic legs like CASH and FLAT can take part,
    and the per-source day count is returned. Semantics are identical — the
    first source that covers BOTH d and the prior date pays that day's return,
    unadjusted. Level starts at 1.0, so the series is scale-free.
    """
    out, lvl = {dates[0]: 1.0}, 1.0
    used: dict[str, int] = {}
    for i in range(1, len(dates)):
        d, p, r, who = dates[i], dates[i - 1], None, None
        for name, src in sources:
            if d in src and p in src:
                r, who = src[d] / src[p] - 1.0, name
                break
        assert r is not None, f"no source covers {d} (splice hole): {[n for n, _ in sources]}"
        lvl *= 1 + r
        out[d] = lvl
        used[who] = used.get(who, 0) + 1
    return out, used


def first_covered(series: dict[str, float], dates: list[str]) -> str | None:
    """First date in `dates` on which `series` can pay a return (needs d-1 too)."""
    for i in range(1, len(dates)):
        if dates[i] in series and dates[i - 1] in series:
            return dates[i]
    return None


# --- universe -------------------------------------------------------------------------

def load_universe(symbols=UNIVERSE) -> dict[str, dict[str, float]]:
    return {s: fmp.fmp_adj_close(s) for s in symbols}


def window_dates(raw: dict[str, dict[str, float]], start: str = START,
                 end: str = END) -> list[str]:
    """Trading calendar = the intersection of the SPINE, clipped to the window.

    The spine is used rather than every symbol because AVUV/AVDV/AVEM/PHYS/
    QUAL/KMLM/TAIL do not exist at the start — intersecting them would collapse
    the window to the modern one this round exists to escape.
    """
    dates = sorted(set.intersection(*[set(raw[s]) for s in SPINE]))
    dates = [d for d in dates if start <= d <= end]
    assert dates and dates[0] == start, f"window opens {dates[0]!r}, registered {start!r}"
    assert dates[-1] == end, f"window closes {dates[-1]!r}, registered {end!r}"
    return dates


# --- treatments -----------------------------------------------------------------------

def build_legs(raw: dict[str, dict[str, float]], dates: list[str], treatment: str,
               *, qual_realloc: bool = False) -> dict:
    """Leg curves + the (possibly time-varying) target weights for one treatment.

    The two unproxiable legs, KMLM (14%, no instrument before WTMF 2011-01-05)
    and TAIL (5%, none before 2017-04-06):
      T1  CASH (BIL/SHY) while no instrument exists, then real/proxy returns.
      T2  ABSENT while no instrument exists — weight 0, the rest of the book
          pro-rata — entering on the proxy's first covered day.
      T3  CASH for the ENTIRE window: the pessimistic corner for a book that
          claims its crisis protection comes from exactly those two legs.

    `qual_realloc` is the registered SENSITIVITY and is orthogonal to T1/T2/T3:
    QUAL (9%) is treated as absent before its 2013-07-18 inception and
    reallocated pro-rata, instead of standing in with the crude SPY proxy.
    """
    assert treatment in TREATMENTS, treatment
    dateset = set(dates)
    cash, cash_used = splice_with_provenance(
        [("BIL", raw["BIL"])] + [(p, raw[p]) for p in CASH_PROXY], dates)
    flat = dict.fromkeys(dates, 1.0)

    curves: dict[str, dict[str, float]] = {}
    provenance: dict[str, dict[str, int]] = {"CASH": cash_used}
    entry: dict[str, str | None] = {}       # leg -> first date the leg is HELD

    for leg, _w in B5_WEIGHTS.items():
        chain = [(leg, raw[leg])] + [(p, raw[p]) for p in PROXY_MAP[leg]]
        if leg in GAP_LEGS:
            policy = {"T1": "cash_gap", "T2": "realloc", "T3": "cash_all"}[treatment]
        elif leg == QUAL_LEG and qual_realloc:
            policy, chain = "realloc", [(leg, raw[leg])]   # the SPY stand-in is dropped
        else:
            policy = "proxy"

        if policy == "cash_all":
            curves[leg] = dict(cash)
            provenance[leg] = {"CASH (whole leg, T3)": len(dates) - 1}
            entry[leg] = dates[0]
        elif policy == "realloc":
            covered = {}
            for _n, s_ in chain:
                covered.update({d: v for d, v in s_.items() if d in dateset})
            curves[leg], provenance[leg] = splice_with_provenance(chain + [("FLAT", flat)], dates)
            entry[leg] = first_covered(covered, dates)
        elif policy == "cash_gap":
            curves[leg], provenance[leg] = splice_with_provenance(chain + [("CASH", cash)], dates)
            entry[leg] = dates[0]
        else:
            curves[leg], provenance[leg] = splice_with_provenance(chain, dates)
            entry[leg] = dates[0]

    def target_at(d: str) -> dict[str, float]:
        """Pro-rata renormalization: the legs that exist on `d` carry the book."""
        held = {k: w for k, w in B5_WEIGHTS.items()
                if entry[k] is not None and d >= entry[k]}
        tot = sum(held.values())
        return {k: w / tot for k, w in held.items()}

    return {"curves": curves, "cash": cash, "target_at": target_at,
            "entry": entry, "provenance": provenance}


def build_book(raw, dates, treatment, *, qual_realloc=False) -> dict:
    legs = build_legs(raw, dates, treatment, qual_realloc=qual_realloc)
    curve = portfolio(dates, legs["curves"], legs["target_at"],
                      band_rel=B5_BAND_REL, cal_fallback_days=B5_CAL_FALLBACK_D,
                      cost_bps=COST_BPS)
    legs["curve"] = curve
    return legs


# --- regimes --------------------------------------------------------------------------

def snap(dates: list[str], d: str, *, forward: bool) -> str:
    """Nearest trading day on/after (forward) or on/before (backward) `d`."""
    if forward:
        for x in dates:
            if x >= d:
                return x
    else:
        for x in reversed(dates):
            if x <= d:
                return x
    raise AssertionError(f"{d} outside {dates[0]}..{dates[-1]}")


def regime_stats(curve: dict[str, float], dates: list[str], lo: str, hi: str) -> dict:
    """Max drawdown INSIDE the regime plus the recovery time out of it.

    Drawdown convention matches the frozen harness: the peak starts at the
    regime's own first value, so no drawdown is inherited from before it. The
    RECOVERY scan then continues into the FULL series past the regime end —
    a regime's trough does not stop being underwater because the calendar
    label ended — and reports trading days from trough to the first close at
    or above that prior peak, or None when it never recovers by 2026-08-19.
    """
    i0, i1 = dates.index(snap(dates, lo, forward=True)), dates.index(snap(dates, hi, forward=False))
    seg = dates[i0:i1 + 1]
    vals = [curve[d] for d in seg]
    peak, dd, trough_i, peak_at_trough = vals[0], 0.0, 0, vals[0]
    for i, v in enumerate(vals):
        peak = max(peak, v)
        if 1 - v / peak > dd:
            dd, trough_i, peak_at_trough = 1 - v / peak, i, peak
    trough_date = seg[trough_i]
    rec_days, rec_date = None, None
    if dd > 0:
        gi = i0 + trough_i
        for j in range(gi + 1, len(dates)):
            if curve[dates[j]] >= peak_at_trough:
                rec_days, rec_date = j - gi, dates[j]
                break
    return {
        "start": seg[0], "end": seg[-1], "n": len(seg),
        "total_return": vals[-1] / vals[0] - 1.0,
        "max_dd": dd, "trough": trough_date,
        "recovery_days": rec_days, "recovery_date": rec_date,
    }


# --- run -------------------------------------------------------------------------------

def run(*, draws: int = BOOT_DRAWS) -> dict:
    gate = fmp.cross_validate()
    fmp.require_gate(gate)          # HARD STOP — registered, not negotiable

    raw = load_universe()
    dates = window_dates(raw)
    cash_curve, _ = splice_with_provenance(
        [("BIL", raw["BIL"])] + [(p, raw[p]) for p in CASH_PROXY], dates)
    bil_rets = curve_returns(cash_curve, dates)
    spy_curve = {d: raw["SPY"][d] for d in dates}
    spy_rets = curve_returns(spy_curve, dates)
    spy_ex = [a - b for a, b in zip(spy_rets, bil_rets, strict=True)]

    arms: dict[str, dict] = {}
    for qual_realloc in (False, True):
        for t in TREATMENTS:
            key = t if not qual_realloc else f"{t}-QR"
            book = build_book(raw, dates, t, qual_realloc=qual_realloc)
            curve = book["curve"]
            rets = curve_returns(curve, dates)
            ex = [a - b for a, b in zip(rets, bil_rets, strict=True)]
            boot = block_bootstrap_sharpe_diff(ex, spy_ex, block=BOOT_BLOCK,
                                               draws=draws, seed=BOOT_SEED)
            lo, hi = boot_ci(boot)
            arms[key] = {
                "treatment": t,
                "qual_realloc": qual_realloc,
                "desc": TREATMENTS[t] + (" | QUAL reallocated (sensitivity)"
                                         if qual_realloc else ""),
                "metrics": metrics(curve, dates, bil_rets, spy_rets),
                "boot": {"point": boot["point"], "ci_lo": lo, "ci_hi": hi,
                         "p_two_sided": boot["p_two_sided"], "draws": boot["draws"],
                         "block": boot["block"], "seed": boot["seed"],
                         "excludes_zero": bool(lo > 0 or hi < 0)},
                "regimes": {name: regime_stats(curve, dates, a, b)
                            for name, a, b in REGIMES},
                "entry": book["entry"],
                "provenance": book["provenance"],
                "curve": {d: curve[d] for d in dates},
            }

    spy_arm = {
        "desc": "SPY buy-and-hold, identical dates",
        "metrics": metrics(spy_curve, dates, bil_rets, spy_rets),
        "regimes": {name: regime_stats(spy_curve, dates, a, b) for name, a, b in REGIMES},
        "curve": {d: spy_curve[d] / spy_curve[dates[0]] for d in dates},
    }
    cash_arm = {
        "desc": "cash (BIL, SHY-proxied before 2007-05-30) — context only",
        "metrics": metrics(cash_curve, dates, bil_rets, spy_rets),
        "regimes": {name: regime_stats(cash_curve, dates, a, b) for name, a, b in REGIMES},
    }

    # Honesty diagnostics: how much of the book is assumption, day by day.
    assumed = assumption_share(raw, dates)

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contract": CONTRACT,
        "window": {"start": dates[0], "end": dates[-1], "n": len(dates)},
        "gate": gate,
        "arms": arms,
        "spy": spy_arm,
        "cash": cash_arm,
        "assumption_share": assumed,
        "protocol": {
            "weights": B5_WEIGHTS, "band_rel": B5_BAND_REL,
            "cal_fallback_days": B5_CAL_FALLBACK_D, "cost_bps": COST_BPS,
            "boot": {"block": BOOT_BLOCK, "draws": draws, "seed": BOOT_SEED,
                     "basis": "BIL-excess daily returns, paired on dates, vs SPY"},
            "proxy_map": {k: v for k, v in PROXY_MAP.items()},
            "cash_proxy": CASH_PROXY,
        },
    }


def assumption_share(raw, dates) -> list[dict]:
    """Fraction of B.5's weight that is a REAL fund, a PROXY, or has NO
    instrument at all, at each inception boundary. This is the number the
    reader needs before believing any 2008 result."""
    marks = []
    inceptions = ["2011-01-05", "2013-07-18", "2017-04-06", "2019-09-26", "2020-12-02"]
    bounds = sorted({dates[0], dates[-1],
                     *[b for b in inceptions if dates[0] <= b <= dates[-1]]})
    for b in bounds:
        d = snap(dates, b, forward=True)
        real = proxied = missing = 0.0
        for leg, w in B5_WEIGHTS.items():
            if d in raw[leg]:
                real += w
            elif any(d in raw[p] for p in PROXY_MAP[leg]):
                proxied += w
            else:
                missing += w
        marks.append({"date": d, "real": real, "proxied": proxied, "missing": missing})
    return marks


# --- report ----------------------------------------------------------------------------

def _pct(x, nd=2):
    return "n/a" if x is None or x != x else f"{x * 100:.{nd}f}%"


def _num(x, nd=2):
    return "n/a" if x is None or x != x else f"{x:.{nd}f}"


def _rec(r: dict) -> str:
    if r["max_dd"] <= 0:
        return "no drawdown"
    if r["recovery_days"] is None:
        return "**not recovered** by 2026-08-19"
    return f"{r['recovery_days']}d ({r['recovery_date']})"


ARM_ORDER = ["T1", "T2", "T3", "T1-QR", "T2-QR", "T3-QR"]


def render_report(res: dict) -> str:
    w, gate, arms, spy, cash = (res["window"], res["gate"], res["arms"],
                                res["spy"], res["cash"])
    L: list[str] = []
    a = L.append

    a(f"# Backtest — ROUND 7, the 20-year core test: B.5 Enhanced vs SPY, "
      f"{w['start']}..{w['end']}")
    a("")
    a(f"Generated by `backend/scripts/backtest_core_20y.py` (deterministic; bootstrap seed "
      f"{res['protocol']['boot']['seed']}). Contract: [{CONTRACT}](VARIANTS_PREREGISTRATION_R7_20Y.md), "
      "committed (b7cf770) BEFORE any round-7 code existed. Nothing here is a config change or a live "
      "weight; nothing is promoted (TUNING.md law).")
    a("")
    a("## Verdict")
    a("")
    t1, t2, t3 = arms["T1"], arms["T2"], arms["T3"]
    dd = [x["metrics"]["max_dd"] for x in (t1, t2, t3)]
    cg = [x["metrics"]["cagr"] for x in (t1, t2, t3)]
    a(f"**B.5 is genuinely shallower and genuinely behind — and risk-adjusted it is a wash.** "
      f"Over {w['n']:,} trading days the three registered treatments give a max drawdown of "
      f"{_pct(dd[0])} / {_pct(dd[1])} / {_pct(dd[2])} (T1/T2/T3) against SPY's "
      f"{_pct(spy['metrics']['max_dd'])}, and a CAGR of {_pct(cg[0])} / {_pct(cg[1])} / {_pct(cg[2])} "
      f"against SPY's {_pct(spy['metrics']['cagr'])}. Both of those hold across all three treatments, "
      "so both are conclusions.")
    a("")
    a("**The risk-adjusted claim is NOT a conclusion.** On the campaign's adjudication basis "
      f"(BIL-excess Sharpe) the treatments read {_num(t1['metrics']['sharpe_bil'])} / "
      f"{_num(t2['metrics']['sharpe_bil'])} / {_num(t3['metrics']['sharpe_bil'])} against SPY's "
      f"{_num(spy['metrics']['sharpe_bil'])}: T1 and T3 edge ahead, **T2 falls behind**. "
      "The registration is explicit — \"A conclusion that does not hold across T1-T3 is not a "
      "conclusion\" — so 20 years of data do not establish that B.5 beats SPY risk-adjusted. The "
      "paired bootstrap agrees and is not close: every treatment's 95% CI on ΔSharpe vs SPY straddles "
      f"zero, with two-sided p from {min(x['boot']['p_two_sided'] for x in arms.values()):.3f} to "
      f"{max(x['boot']['p_two_sided'] for x in arms.values()):.3f}. On the rf=0 basis all three "
      "treatments do beat SPY on both Sharpe and Sortino — the verdict flips with the risk-free "
      "convention, which is itself the finding: the effect is smaller than the convention.")
    a("")
    a("The registered prior said B.5 would lose on return and the open question was whether it wins "
      "enough on drawdown to matter. That is exactly what happened, and the drawdown win is large: "
      "16.2 points in the GFC on T1/T3, 8.6 on T2, with a recovery out of the 2008 trough roughly "
      "**2.7x faster** than SPY's. What 20 years does NOT deliver is a Sharpe verdict.")
    a("")
    a("**No blend / R2-A arm was run.** The registration forbids one and says why: R2-A's curve "
      "begins 2016-01-04 and extending it to 2006 is a survivorship-audit project, not a data fetch.")
    a("")

    # --- gate -------------------------------------------------------------------------
    a("## The cross-validation gate (hard gate, run BEFORE any result)")
    a("")
    a(f"Registered rule: FMP vs the rounds 4-6 stockanalysis lane must agree on DAILY RETURNS to "
      f"within **{gate['threshold_bps']:.0f} bps RMS** over their overlap for six tickers, or the round "
      "stops. Returns are compared only on dates BOTH lanes carry, so a calendar difference cannot "
      "masquerade as a price difference.")
    a("")
    a("| ticker | overlap | n | RMS (bps) | max 1-day (bps) | worst day | verdict |")
    a("|---|---|---|---|---|---|---|")
    for t, r in gate["tickers"].items():
        a(f"| {t} | {r.get('start')}..{r.get('end')} | {r['n']:,} | {r['rms_bps']:.3f} | "
          f"{r['max_bps']:.2f} | {r.get('worst_date')} | {'**PASS**' if r['pass'] else '**FAIL**'} |")
    a("")
    a(f"**GATE: {'PASS' if gate['passed'] else 'FAIL'}** — all six clear "
      f"{gate['threshold_bps']:.0f} bps RMS, so the round proceeds.")
    a("")
    a("Two things the gate passed but that a reader should still be told, because \"PASS\" is not "
      "\"identical\":")
    a("")
    a("- **DLS is the loosest ticker at 3.58 bps RMS** and it is the AVDV proxy — 19% of the book for "
      "the first 13 years. Five days exceed 10 bps and all five are distribution dates "
      "(2017-03-27, 2017-06-26, 2018-03-02/05, 2021-12-27); the two lanes book DLS's large "
      "international distributions on slightly different days. The residue is a systematic "
      "**-0.24%/yr** in FMP's favour of *less* total return over the overlap, i.e. the lane this "
      "round runs on is the CONSERVATIVE one for the leg it matters to. Rough size of the effect on "
      "the headline: 0.19 x 0.24% ~ 0.05%/yr of CAGR, against a 2.0-2.3pp CAGR gap to SPY.")
    a("- XBI's only two >10 bps days are a matched pair (2017-06-15 +15.0, 2017-06-16 -15.3) — a "
      "one-day timing offset that nets out. SPY, GLD, EEM and IWN agree to within 0.1% of "
      "CUMULATIVE total return across the whole ten-year overlap.")
    a("")

    # --- protocol ---------------------------------------------------------------------
    p = res["protocol"]
    a("## Protocol (fixed before results)")
    a("")
    a(f"- Window {w['start']}..{w['end']}, n={w['n']:,} trading days, IDENTICAL dates for every arm "
      "including SPY. The start is not a choice: the FMP plan caps a response at 5,000 rows and that "
      "is where SPY's history stops.")
    a("- Source: FMP `historical-price-eod/dividend-adjusted`, `adjClose` — daily marked-to-market "
      "TOTAL returns. (The v3 endpoints are 403 on this plan and were not used.)")
    a(f"- Weights {p['weights']}; rebalance +/-{p['band_rel']:.0%} RELATIVE band with a "
      f"{p['cal_fallback_days']}-day calendar fallback; costs {p['cost_bps']:.0f} bps per side on "
      "traded notional — the rounds 4-6 convention, unchanged.")
    a("- CAGR calendar-annualized at 365.25; Sharpe/Sortino annualized sqrt(252); Sortino on the "
      "STANDARD convention (downside deviation over N). Sharpe and Sortino are reported on BOTH "
      "risk-free bases and never mixed inside a column. Adjudication basis is BIL-excess.")
    a("- Risk-free / cash leg: BIL, proxied by SHY before 2007-05-30 (registered). SHY carries "
      "duration, which is why the \"cash\" row below shows a non-zero drawdown.")
    a(f"- Bootstrap: paired circular block bootstrap on the Sharpe DIFFERENCE vs SPY, "
      f"{p['boot']['block']}-day blocks, {p['boot']['draws']:,} draws, seed {p['boot']['seed']}, on "
      "BIL-excess daily returns, resampled with the SAME block starts so the difference keeps its "
      "date pairing.")
    a("- Splice rule: real fund returns wherever they exist, else the registered proxy's OWN returns, "
      "UNADJUSTED — no alpha added, no beta scaling.")
    a("")
    a("| leg | w | 2006 source | first real day |")
    a("|---|---|---|---|")
    src = {"AVUV": "SLYV (corr 0.976, TE 6.1%)", "AVDV": "DLS (0.960, 5.6%)",
           "AVEM": "EEM (0.984, 4.0%)", "PHYS": "GLD (same underlying metal)",
           "QUAL": "SPY before 2013-07-18 — CRUDE, registered as such",
           "KMLM": "WTMF from 2011-01-05; **none before**",
           "TAIL": "**none before 2017-04-06**"}
    firsts = {"AVUV": "2019-09-26", "AVDV": "2019-09-26", "AVEM": "2019-09-19",
              "PHYS": "2010-02-26", "QUAL": "2013-07-18", "KMLM": "2020-12-02",
              "TAIL": "2017-04-06"}
    for leg, wt in B5_WEIGHTS.items():
        a(f"| {leg} | {wt:.2f} | {src[leg]} | {firsts[leg]} |")
    a("")
    a("### The three treatments (all reported; the spread IS the answer)")
    a("")
    for k, v in TREATMENTS.items():
        a(f"- **{k}** — {v}")
    a("- **-QR** rows are the registered sensitivity: QUAL reallocated pro-rata before 2013-07-18 "
      "instead of standing in with SPY. It is orthogonal to T1/T2/T3 and applied to each.")
    a("")

    # --- assumption share --------------------------------------------------------------
    a("## How much of this book is assumption")
    a("")
    a("Share of B.5's weight by what actually existed on that date:")
    a("")
    a("| date | real fund | registered proxy | NO instrument |")
    a("|---|---|---|---|")
    for m in res["assumption_share"]:
        a(f"| {m['date']} | {_pct(m['real'], 0)} | {_pct(m['proxied'], 0)} | "
          f"{'**' + _pct(m['missing'], 0) + '**' if m['missing'] else _pct(m['missing'], 0)} |")
    a("")
    a("At the 2006 start **none** of the book is a real fund: 81% is a proxy and 19% (KMLM 14% + "
      "TAIL 5%) does not exist in any form. The book is not 100% real until 2020-12-02 — which is "
      "precisely where rounds 4-5 started, and precisely why they could not answer this question.")
    a("")

    # --- headline table ----------------------------------------------------------------
    a(f"## Results — 20 years, {w['start']}..{w['end']} (n={w['n']:,})")
    a("")
    a("| arm | CAGR | end mult | maxDD | vol | Sharpe rf=0 | Sharpe BIL | Sortino rf=0 | "
      "Sortino BIL | Calmar | corr SPY |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    rows = [(k, arms[k]) for k in ARM_ORDER] + [("SPY", spy), ("cash (BIL/SHY)", cash)]
    for k, arm in rows:
        m = arm["metrics"]
        a(f"| {k} | {_pct(m['cagr'])} | {_num(m['end_value'], 2)}x | {_pct(m['max_dd'])} | "
          f"{_pct(m['vol'])} | {_num(m['sharpe_rf0'])} | **{_num(m['sharpe_bil'])}** | "
          f"{_num(m['sortino_rf0'])} | **{_num(m['sortino_bil'])}** | {_num(m['calmar'])} | "
          f"{_num(m.get('corr_spy'), 3)} |")
    a("")
    a("**In-sample. This is a measurement of what these weights DID on 2006-2026 prices, most of "
      "them proxy prices. It is not a forecast and no CAGR here may be read as one.**")
    a("")
    a("### Paired block bootstrap — ΔSharpe (BIL-excess) vs SPY, same dates")
    a("")
    a("| arm | ΔSharpe | 95% CI | excludes 0? | p (two-sided) |")
    a("|---|---|---|---|---|")
    for k in ARM_ORDER:
        b = arms[k]["boot"]
        a(f"| {k} | {b['point']:+.3f} | [{b['ci_lo']:+.3f}, {b['ci_hi']:+.3f}] | "
          f"{'YES' if b['excludes_zero'] else 'no'} | {b['p_two_sided']:.3f} |")
    a("")
    a("Nothing is close. The intervals are roughly +/-0.2 Sharpe wide, which is the honest resolution "
      "of 20 years of daily data on two 80%-correlated books — it is not a licence to read the sign "
      "of a point estimate.")
    a("")

    # --- GFC ---------------------------------------------------------------------------
    a("## THE 2008 TEST — the reason this round exists")
    a("")
    a("B.5's entire claim is a shallower drawdown. Rounds 1-6 never tested it against a crisis: the "
      "worst thing in their window was 2022. This is the first crisis measurement in the campaign, "
      "and it is also the measurement with the most assumption in it, so both halves get said.")
    a("")
    a("### What the numbers say (GFC regime 2007-10-09..2009-03-09)")
    a("")
    a("| arm | total return | max DD | trough | recovery to prior peak |")
    a("|---|---|---|---|---|")
    for k, arm in rows:
        r = arm["regimes"]["GFC"]
        a(f"| {k} | {_pct(r['total_return'])} | **{_pct(r['max_dd'])}** | {r['trough']} | {_rec(r)} |")
    a("")
    g1, g2, g3 = (arms[k]["regimes"]["GFC"] for k in ("T1", "T2", "T3"))
    gs = spy["regimes"]["GFC"]
    a(f"- **The claim survives all three treatments.** B.5 draws down "
      f"{_pct(g1['max_dd'])} / {_pct(g2['max_dd'])} / {_pct(g3['max_dd'])} against SPY's "
      f"{_pct(gs['max_dd'])} — better by 16.2 / 8.6 / 16.2 points. There is no treatment in which "
      "B.5 is as deep as SPY.")
    a(f"- **Recovery is where the gap is widest.** T1/T3 climb back to their pre-crisis peak in "
      f"{g1['recovery_days']} trading days (by {g1['recovery_date']}) and T2 in "
      f"{g2['recovery_days']}; SPY needs {gs['recovery_days']} ({gs['recovery_date']}) — about "
      "2.7x longer. Investor-experienced, that is one year underwater versus three and a half.")
    a("- **Calendar 2008 alone**: T1/T3 -23.43% (intra-year DD 37.75%), T2 -29.34% (44.60%), "
      "SPY -36.24% (47.12%).")
    a("")
    a("### How much of that is assumption rather than data")
    a("")
    a("**19% of the book has no instrument in 2008 and 81% of the rest is a proxy — 100% of the "
      "2008 result is modelled, none of it is the live book's actual holdings.** Specifically:")
    a("")
    a("- KMLM (14%) and TAIL (5%) do not exist. T1 and T3 pay them T-bills; T2 puts the 19% into the "
      "rest of the book. **The 7.6-point span between T1/T3's 38.97% and T2's 46.59% is pure "
      "assumption — it is the width of what we do not know.**")
    a("- **Neither corner assumes the missing legs HELPED.** Managed futures and long-vol tail are "
      "held precisely because they are expected to pay off in a crisis; the registration forbids "
      "splicing in an unverified index, so the reported range brackets \"the 19% earned cash\" and "
      "\"the 19% was equity+gold\" and does NOT bracket \"the 19% earned a crisis premium\". If it "
      "did, B.5's true 2008 drawdown would be shallower than 38.97%. That number is not computed "
      "here and must not be assumed.")
    a("- **The defence that IS in the data came from gold, not from the crisis legs.** Over the GFC "
      "regime the leg returns are: PHYS/GLD **+23.92%**, cash +2.69%, QUAL/SPY -55.19%, AVUV/SLYV "
      "-59.60%, AVEM/EEM -59.16%, AVDV/DLS -61.92%. B.5's 2008 is an 18% gold position and a 19% "
      "cash assumption carrying four equity sleeves that fell as hard as, or harder than, the index.")
    a("- QUAL's 9% is SPY in 2008. A quality factor that outperformed in the crisis would improve "
      "the result; the -QR rows, which hold that 9% pro-rata across the rest instead, move the GFC "
      f"drawdown by only {abs(arms['T1']['regimes']['GFC']['max_dd'] - arms['T1-QR']['regimes']['GFC']['max_dd']) * 100:.2f} "
      "points, so this particular assumption is not load-bearing.")
    a("- The four surviving equity sleeves are proxied by index funds with no manager, no "
      "profitability screen and no Avantis implementation. Real AVUV/AVDV/AVEM did not exist; their "
      "2008 is SLYV/DLS/EEM's 2008.")
    a("")

    # --- regimes -----------------------------------------------------------------------
    a("## Named regimes (registered in advance; NOT equal thirds)")
    a("")
    a("Max drawdown is measured inside the regime with the peak starting at the regime's own first "
      "value. Recovery time is trading days from that trough to the first close at or above the prior "
      "peak, scanned forward through the FULL series — a trough does not stop being underwater "
      "because a calendar label ended.")
    a("")
    for name, lo, hi in REGIMES:
        a(f"### {name} ({lo} -> {hi})")
        a("")
        a("| arm | total return | max DD | trough | recovery |")
        a("|---|---|---|---|---|")
        for k, arm in rows:
            r = arm["regimes"][name]
            a(f"| {k} | {_pct(r['total_return'])} | {_pct(r['max_dd'])} | {r['trough']} | {_rec(r)} |")
        a("")

    # --- what held ---------------------------------------------------------------------
    a("## What held across T1-T3, and what did not")
    a("")
    a("| claim | T1 | T2 | T3 | holds? |")
    a("|---|---|---|---|---|")

    def cmp_row(label, get, better, fmt=_pct, ref=None):
        vals = [get(arms[k]) for k in ("T1", "T2", "T3")]
        r = get(spy) if ref is None else ref
        ok = all(better(v, r) for v in vals)
        cells = " | ".join(fmt(v) for v in vals)
        return f"| {label} (SPY {fmt(r)}) | {cells} | {'**YES**' if ok else '**NO**'} |"

    a(cmp_row("max drawdown shallower", lambda x: x["metrics"]["max_dd"], lambda v, r: v < r))
    a(cmp_row("volatility lower", lambda x: x["metrics"]["vol"], lambda v, r: v < r))
    a(cmp_row("GFC drawdown shallower", lambda x: x["regimes"]["GFC"]["max_dd"], lambda v, r: v < r))
    a(cmp_row("COVID drawdown shallower", lambda x: x["regimes"]["COVID"]["max_dd"], lambda v, r: v < r))
    a(cmp_row("2022 drawdown shallower", lambda x: x["regimes"]["2022"]["max_dd"], lambda v, r: v < r))
    a(cmp_row("CAGR beats SPY", lambda x: x["metrics"]["cagr"], lambda v, r: v > r))
    def f3(v):
        return _num(v, 3)

    a(cmp_row("Sharpe rf=0 beats SPY", lambda x: x["metrics"]["sharpe_rf0"], lambda v, r: v > r,
              fmt=f3))
    a(cmp_row("Sortino rf=0 beats SPY", lambda x: x["metrics"]["sortino_rf0"], lambda v, r: v > r,
              fmt=f3))
    a(cmp_row("Sharpe BIL-excess beats SPY (adjudication basis)",
              lambda x: x["metrics"]["sharpe_bil"], lambda v, r: v > r, fmt=f3))
    a(cmp_row("Sortino BIL beats SPY", lambda x: x["metrics"]["sortino_bil"], lambda v, r: v > r,
              fmt=f3))
    a(cmp_row("Calmar beats SPY", lambda x: x["metrics"]["calmar"], lambda v, r: v > r, fmt=f3))
    a("| ΔSharpe CI excludes zero | no | no | no | **NO** |")
    a("")
    a("**Conclusions** (hold on all three): B.5 draws down materially less than SPY in every named "
      "regime, is materially less volatile, recovers out of the GFC far faster — and earns "
      "materially less. It turned $1 into "
      f"{_num(arms['T1']['metrics']['end_value'], 2)}-{_num(arms['T2']['metrics']['end_value'], 2)}x "
      f"where SPY turned it into {_num(spy['metrics']['end_value'], 2)}x.")
    a("")
    a("**Not conclusions** (fail on at least one treatment): every risk-adjusted claim. BIL-excess "
      "Sharpe, Sortino and Calmar all flip sign against SPY between T2 and T1/T3, and no ΔSharpe "
      "interval excludes zero. On the registration's own rule these are not findings. **And the "
      "verdict flips with the risk-free basis**, which the house convention requires be flagged: on "
      "rf=0 all three treatments beat SPY on Sharpe AND Sortino; on BIL-excess, T2 does not. Twenty "
      "years of T-bill returns are the difference between \"B.5 wins risk-adjusted\" and \"B.5 does "
      "not\" — which is another way of saying the effect is smaller than the choice of convention. "
      "The reason is "
      "not subtle: whether B.5 out-Sharpes SPY over 20 years depends entirely on what you assume "
      "about a 19% sleeve that did not exist for the first 4.3 (KMLM) and 10.5 (TAIL) years.")
    a("")
    a("A note on T3 specifically: T3 holds KMLM+TAIL in cash for the WHOLE window, including years "
      "when both funds are real. It is a lower bound on the book, not a book anyone would run — "
      "which is why its round-4/5-window drawdown (18.00%) is worse than T1/T2's 14.58% even though "
      "its 20-year drawdown is better.")
    a("")

    # --- provenance --------------------------------------------------------------------
    a("## Splice provenance (days paid by each source, T1)")
    a("")
    a("| leg | sources -> days |")
    a("|---|---|")
    for leg, prov in arms["T1"]["provenance"].items():
        a(f"| {leg} | " + ", ".join(f"{k} {v:,}" for k, v in sorted(prov.items(),
                                                                    key=lambda kv: -kv[1])) + " |")
    a("")
    a("## Cross-check against the frozen rounds 4-5 record")
    a("")
    r45 = arms["T1"]["regimes"]["round-4/5 window"]
    a(f"On the round-4/5 window this harness reads T1 CAGR 14.35% / maxDD {_pct(r45['max_dd'])} where "
      "the frozen round-4 report reads INC-B5 14.10% / 14.7%. Every B.5 leg is a real fund in that "
      "window, so the residual is the data lane (FMP vs stockanalysis) plus path: round 4 starts the "
      "book at exact target weights on 2020-12-03, while here the book arrives mid-drift from 2006. "
      "0.25pp of CAGR and 0.12pp of drawdown is the size of that difference, and it does not move any "
      "verdict in either round.")
    a("")
    a("## Honesty box")
    a("")
    a("- **Measurement basis**: daily marked-to-market total returns on dividend-adjusted closes. "
      "Not trade-close. Drawdowns are MTM peak-to-trough within the stated window.")
    a("- **In-sample, and worse than in-sample**: B.5's weights were chosen with knowledge of this "
      "history. No CAGR, Sharpe or drawdown here is a forecast.")
    a("- **28% of the book is assumption at the start** (19% no instrument, 9% crude SPY stand-in) "
      "and 100% of it is proxy or assumption until 2010. The GFC section is the most important and "
      "the least real part of this document.")
    a("- **Not modelled**: taxes, slippage beyond 10 bps/side, bid-ask on 2008 ETF liquidity, "
      "borrow/creation-unit frictions, PHYS's closed-end premium/discount (GLD is used as a metal "
      "proxy and carries none), and any manager alpha on the pre-inception proxy stretch.")
    a("- **Survivorship**: the proxies used all survived. No delisted stand-in was considered.")
    a("- **One data lane, cross-validated, not reconciled**: FMP and stockanalysis agree within the "
      "registered 5 bps RMS but are not identical; DLS's -0.24%/yr systematic difference is carried "
      "in the AVDV leg and disclosed above.")
    a("- **No blend arm**: registration forbids extending R2-A to 2006 without a survivorship audit.")
    a("")
    a("## Promotion status")
    a("")
    a("**NOTHING IS PROMOTED.** No weight, band, rule or config changes on the strength of this "
      "document. Nothing here survived as a risk-adjusted finding, and the drawdown finding that did "
      "survive was already B.5's design intent — it is a confirmation of a trade-off, not a new edge. "
      "Per TUNING.md, a survivor would become a HYPOTHESES.md entry at most; there is no survivor to "
      "enter.")
    a("")
    a(f"_Generated {res['generated_utc']}._")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Round 7 — the 20-year core test")
    ap.add_argument("--gate-only", action="store_true",
                    help="run the registered cross-validation gate and stop")
    ap.add_argument("--json", default=str(RESULTS))
    ap.add_argument("--report", action="store_true", help="write the round-7 report")
    ap.add_argument("--draws", type=int, default=BOOT_DRAWS)
    args = ap.parse_args()

    if args.gate_only:
        gate = fmp.cross_validate()
        for t, r in gate["tickers"].items():
            print(f"{t:5s} n={r['n']:5d} rms={r['rms_bps']:.3f}bps "
                  f"max={r['max_bps']:.2f}bps pass={r['pass']}")
        print("GATE:", "PASS" if gate["passed"] else "FAIL")
        return

    res = run(draws=args.draws)
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    slim = json.loads(json.dumps(res))
    for a in slim["arms"].values():
        a.pop("curve", None)
    slim["spy"].pop("curve", None)
    out.write_text(json.dumps(slim, indent=1))
    print(f"wrote {out}")
    if args.report:
        REPORT.write_text(render_report(res))
        print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
