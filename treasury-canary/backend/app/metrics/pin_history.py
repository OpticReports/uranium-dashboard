"""Pin-channel history — monthly severity hindcast + damage-window overlap.

Extends the pin board through time. Every channel's severity score (same
anchors as the live board) is recomputed over the full history of its sources
and sampled as the MONTHLY MAX, so fast spikes (Mar-2020 HY gap, Aug-2024 yen
leg) survive the sampling instead of being averaged away. Contiguous months at
RED (score >= 80) form an EPISODE; each episode casts a channel-specific
DAMAGE WINDOW — the documented historical lag between that spark firing and
the macro pain landing (e.g. Hamilton's 3-12 months for oil). The collective
series counts how many windows are open each month, including months still
ahead of us: one red spark is a data point; several open windows at once is a
regime.

Methodology guarantees (same contract as the live board):
  - Percentile parts use EXPANDING percentiles — each date's value is ranked
    only against history known AT that date, so the hindcast has no lookahead.
    The latest point closely tracks the live board; it can legitimately read
    HIGHER than today's board when a spike earlier in the current month has
    since faded (monthly-max sampling keeps the spike; the board shows now).
  - Anchors and lag windows are documented/episode-calibrated, never fitted.
  - Where a source is shallow (FMP dailies, NDFI 2015+, FRED SP500 ~10y) the
    line is simply shorter; a per-channel note says so. The demand-strike
    channel hindcasts from weekly Fed custody only (auction tape is too short
    a window to hindcast) — also noted.
"""
from __future__ import annotations

import bisect
from datetime import date

from .pins import ANCHORS, _pscore

# (lag_min_months, lag_max_months, documented basis) per channel. These size
# the gray band drawn after a red episode: "when the pain from this spark has
# historically landed". Ranges mirror each channel's SPEED attribute.
LAG_WINDOWS: dict[str, tuple[int, int, str]] = {
    "oil_shock": (3, 12, "Hamilton: recessions followed oil shocks by 3-12 months"),
    "policy_shock": (12, 24, "long and variable lags — tightening bites 12-24 months out"),
    "credit_event": (0, 3, "credit accidents transmit in days-weeks"),
    "fiscal": (3, 18, "term-premium repricings compound over quarters"),
    "plumbing": (0, 2, "funding seizures force a response within days-weeks"),
    "basis_trade": (0, 2, "Mar-2020: unwind to Fed rescue in under a month"),
    "private_credit": (1, 6, "marks lag; funding stress lands over weeks-months"),
    "carry_unwind": (0, 2, "Aug-2024: global deleveraging inside days"),
    "uncertainty": (1, 12, "uncertainty bites via delayed capex/hiring decisions"),
    "demand_strike": (1, 6, "auction stress compounds across the issuance cycle"),
    "concentration": (1, 6, "rotations play out over weeks"),
    "vol_supply": (0, 2, "vol events resolve or cascade within weeks"),
}

RED_LINE = 80.0


# --- series plumbing ---------------------------------------------------------

def _series(bundle: dict, key: str) -> tuple[list[date], list[float]]:
    """Clean (dates, values) for a bundle key: Nones dropped, aligned."""
    d, v = bundle.get(key, ([], []))
    pairs = [(x, y) for x, y in zip(d, v) if y is not None]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _align(a: tuple[list[date], list[float]], b: tuple[list[date], list[float]]
           ) -> tuple[list[date], list[float], list[float]]:
    """Intersect two clean series on date."""
    bm = dict(zip(b[0], b[1]))
    dates, av, bv = [], [], []
    for d, v in zip(a[0], a[1]):
        if d in bm:
            dates.append(d)
            av.append(v)
            bv.append(bm[d])
    return dates, av, bv


def _roll_change(dates: list[date], vals: list[float], window: int, scale: float = 1.0
                 ) -> tuple[list[date], list[float]]:
    out_d, out_v = [], []
    for i in range(window, len(vals)):
        out_d.append(dates[i])
        out_v.append((vals[i] - vals[i - window]) * scale)
    return out_d, out_v


def _roll_pct_change(dates: list[date], vals: list[float], window: int
                     ) -> tuple[list[date], list[float]]:
    out_d, out_v = [], []
    for i in range(window, len(vals)):
        if vals[i - window]:
            out_d.append(dates[i])
            out_v.append((vals[i] - vals[i - window]) / vals[i - window] * 100.0)
    return out_d, out_v


def _expanding_percentile(dates: list[date], vals: list[float], min_obs: int
                          ) -> tuple[list[date], list[float]]:
    """Percentile of each value vs history up to AND INCLUDING that date (the
    live board's _percentile is <=-inclusive, so the last point matches it)."""
    out_d, out_v, seen = [], [], []
    for d, v in zip(dates, vals):
        bisect.insort(seen, v)
        if len(seen) >= min_obs:
            out_d.append(d)
            out_v.append(100.0 * bisect.bisect_right(seen, v) / len(seen))
    return out_d, out_v


def _expanding_pctl_vs_raw(dates: list[date], vals: list[float], window: int,
                           min_obs: int) -> tuple[list[date], list[float]]:
    """Rolling mean ranked against the RAW series' expanding history — the
    live board's uncertainty definition (_percentile(epu_v, epu30)), so the
    hindcast's latest point agrees with the board."""
    out_d, out_v, seen = [], [], []
    run = 0.0
    for i, (d, v) in enumerate(zip(dates, vals)):
        bisect.insort(seen, v)
        run += v
        if i >= window:
            run -= vals[i - window]
        if i >= window - 1 and len(seen) >= min_obs:
            avg = run / window
            out_d.append(d)
            out_v.append(100.0 * bisect.bisect_right(seen, avg) / len(seen))
    return out_d, out_v


def _roll_mean(dates: list[date], vals: list[float], window: int
               ) -> tuple[list[date], list[float]]:
    out_d, out_v = [], []
    run = 0.0
    for i, v in enumerate(vals):
        run += v
        if i >= window:
            run -= vals[i - window]
        if i >= window - 1:
            out_d.append(dates[i])
            out_v.append(run / window)
    return out_d, out_v


# --- month helpers -----------------------------------------------------------

def _ym(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = (y * 12 + (m - 1)) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def _month_range(start: str, end: str) -> list[str]:
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur = _add_months(cur, 1)
    return out


def _monthly_max(dates: list[date], scores: list[float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for d, s in zip(dates, scores):
        k = _ym(d)
        if k not in out or s > out[k]:
            out[k] = s
    return out


# --- per-channel part builders -------------------------------------------------
# Each builder returns [(anchor_label, (dates, values)), ...] — the same parts
# the live board scores, computed as full-history series. Percentile parts use
# expanding percentiles (min_obs = warmup before the first honest rank).

def _parts_for_channel(cid: str, bundle: dict) -> list[tuple[str, tuple[list[date], list[float]]]]:
    if cid == "oil_shock":
        d, v = _series(bundle, "oil")
        return [("WTI, 12-month change", _roll_pct_change(d, v, 252))]

    if cid == "policy_shock":
        d, v = _series(bundle, "effr")
        return [("Fed funds, 12-month change", _roll_change(d, v, 252, scale=100.0))]

    if cid == "credit_event":
        hd, hv = _series(bundle, "hy_oas")
        dd, dv = _series(bundle, "discount_window")
        return [
            ("HY OAS, 20d change", _roll_change(hd, hv, 20, scale=100.0)),
            ("Discount-window borrowing", (dd, [x / 1000.0 for x in dv])),
        ]

    if cid == "fiscal":
        gd, gv = _series(bundle, "interest_gdp")
        td, tv = _series(bundle, "acm_tp10")
        return [
            ("Federal interest / GDP", (gd, gv)),
            ("Term premium, 60d change", _roll_change(td, tv, 60, scale=100.0)),
        ]

    if cid == "plumbing":
        dts, sv, iv = _align(_series(bundle, "sofr"), _series(bundle, "iorb"))
        rd, rv = _series(bundle, "reserves")
        pd_, pv = _series(bundle, "rrp")
        return [
            ("SOFR − IORB", (dts, [(a - b) * 100.0 for a, b in zip(sv, iv)])),
            ("Reserves, 26-week change", _roll_pct_change(rd, rv, 26)),
            ("RRP buffer", (pd_, pv)),
        ]

    if cid == "basis_trade":
        d, v = _series(bundle, "cot_net_short")
        return [
            ("Leveraged-fund net short, UST futures", (d, v)),
            ("Positioning percentile (vs 2010+)", _expanding_percentile(d, v, 104)),
        ]

    if cid == "private_credit":
        cd, cv = _series(bundle, "ccc_oas")
        dd, av, bv = _align(_series(bundle, "ccc_oas"), _series(bundle, "bbb_oas"))
        disp = [a - b for a, b in zip(av, bv)]
        nd, nv = _series(bundle, "ndfi_loans")
        return [
            ("CCC spread percentile (vs 1996+)", _expanding_percentile(cd, cv, 504)),
            ("CCC−BBB dispersion percentile", _expanding_percentile(dd, disp, 504)),
            ("Bank loans to NDFIs, m/m ann. growth", (nd, nv)),
        ]

    if cid == "carry_unwind":
        jd, jv = _series(bundle, "jpy")
        gd, gv = _series(bundle, "jgb10")
        return [
            ("USD/JPY, 1-month change", _roll_pct_change(jd, jv, 21)),
            ("10y JGB yield, 12-month change", _roll_change(gd, gv, 12, scale=100.0)),
        ]

    if cid == "uncertainty":
        d, v = _series(bundle, "epu")
        return [("EPU index, 30d avg (percentile)",
                 _expanding_pctl_vs_raw(d, v, 30, 1260))]

    if cid == "demand_strike":
        d, v = _series(bundle, "custody")
        return [("Foreign custody holdings, 13-week change", _roll_pct_change(d, v, 13))]

    if cid == "concentration":
        dts, sv, rv = _align(_series(bundle, "spy"), _series(bundle, "rsp"))
        ratio = [a / b for a, b in zip(sv, rv)]
        rel_d, rel_v = [], []
        for i in range(22, len(dts)):
            rel_d.append(dts[i])
            rel_v.append((sv[i] / sv[i - 22] - rv[i] / rv[i - 22]) * 100.0)
        return [
            ("SPY/RSP ratio percentile (vs 2010+)", _expanding_percentile(dts, ratio, 252)),
            ("Mega-cap vs equal-weight, 20d relative", (rel_d, rel_v)),
        ]

    if cid == "vol_supply":
        xd, xv = _series(bundle, "sp500")
        rv_d, rv_v = [], []
        rets = [(xv[i] / xv[i - 1] - 1.0) for i in range(1, len(xv))]
        for i in range(20, len(rets)):
            w = rets[i - 20:i]
            mu = sum(w) / 20.0
            var = sum((x - mu) ** 2 for x in w) / 19.0
            rv_d.append(xd[i + 1])
            rv_v.append((var ** 0.5) * (252 ** 0.5) * 100.0)
        vd, vv, rr = _align(_series(bundle, "vix"), (rv_d, rv_v))
        vrp = [a - b for a, b in zip(vv, rr)]
        v5 = _roll_change(*_series(bundle, "vix"), 5)
        return [
            ("Vol-risk premium percentile (VIX − realized)", _expanding_percentile(vd, vrp, 252)),
            ("VIX, 5-day change", v5),
        ]

    return []


# Channels whose hindcast is knowingly shallower/narrower than the live board.
HISTORY_NOTES: dict[str, str] = {
    "demand_strike": "Hindcast from weekly Fed custody only — the auction tape "
                     "is too short a history to hindcast.",
    "vol_supply": "FRED's SP500 series is ~10y deep, so the VRP leg starts late; "
                  "the VIX-spike leg covers 1990+.",
    "private_credit": "NDFI loan series starts 2015; CCC/BBB percentiles warm up "
                      "through 1998.",
    "concentration": "Depth limited by FMP daily history for SPY/RSP.",
    "basis_trade": "CFTC TFF disaggregation begins 2006; percentile warms up "
                   "through 2008.",
}


# --- assembly ------------------------------------------------------------------

def _score_series(label: str, dates: list[date], vals: list[float]
                  ) -> tuple[list[date], list[float]]:
    a = ANCHORS.get(label)
    if a is None:
        return [], []
    out_d, out_v = [], []
    for d, v in zip(dates, vals):
        s = _pscore(v, *a[:4], higher_is_worse=a[4], cap=a[5])
        if s is not None:
            out_d.append(d)
            out_v.append(s)
    return out_d, out_v


def _episodes(months: list[str], scores: list[float], cid: str) -> list[dict]:
    """Contiguous calendar-month runs at RED, casting the lag-window envelope.

    Damage can land [lag_lo, lag_hi] months after ANY red month in the run, so
    the window spans peak+lag_lo .. last_red_month+lag_hi. Anchoring the end to
    the LAST red month (not the peak) keeps the window open while an episode is
    still firing — a channel red today is never shown with an expired window.
    """
    lag_lo, lag_hi, _basis = LAG_WINDOWS[cid]
    eps: list[dict] = []
    run: list[tuple[str, float]] = []

    def flush():
        if not run:
            return
        peak_m, peak_s = max(run, key=lambda t: t[1])
        eps.append({
            "start": run[0][0], "end": run[-1][0],
            "peak_date": peak_m, "peak_score": round(peak_s, 1),
            "window_start": _add_months(peak_m, lag_lo),
            "window_end": _add_months(run[-1][0], lag_hi),
        })
        run.clear()

    prev = None
    for m, s in zip(months, scores):
        if s >= RED_LINE:
            if run and prev is not None and _add_months(prev, 1) != m:
                flush()  # data gap breaks the run
            run.append((m, s))
            prev = m
        else:
            flush()
            prev = None
    flush()
    return eps


def build_pin_history(bundle: dict) -> dict:
    """Monthly severity hindcast per channel + collective overlap series."""
    channels_out: list[dict] = []
    all_months: set[str] = set()
    per_channel_monthly: dict[str, dict[str, float]] = {}
    all_episodes: list[tuple[str, dict]] = []

    for cid, (lag_lo, lag_hi, lag_basis) in LAG_WINDOWS.items():
        monthly: dict[str, float] = {}
        for label, (dts, vals) in _parts_for_channel(cid, bundle):
            sd, sv = _score_series(label, dts, vals)
            for m, s in _monthly_max(sd, sv).items():
                if m not in monthly or s > monthly[m]:
                    monthly[m] = s
        months = sorted(monthly)
        scores = [round(monthly[m], 1) for m in months]
        eps = _episodes(months, scores, cid)
        per_channel_monthly[cid] = monthly
        all_months.update(months)
        all_episodes.extend((cid, e) for e in eps)
        channels_out.append({
            "channel_id": cid,
            "lag_months": [lag_lo, lag_hi],
            "lag_basis": lag_basis,
            "series": [{"date": m, "score": s} for m, s in zip(months, scores)],
            "episodes": eps,
            "note": HISTORY_NOTES.get(cid),
        })

    recessions = _recession_spans(*bundle.get("recession", ([], [])))
    drawdowns = _drawdown_spans(*bundle.get("spx_monthly", ([], [], [])))

    if not all_months:
        return {"channels": channels_out,
                "collective": {"series": [], "last_data_month": None},
                "confluence": None, "recessions": recessions,
                "drawdowns": drawdowns}

    last_data = max(all_months)
    # extend through the farthest projected window so convergence AHEAD of us
    # is visible (that is the point of the graph)
    horizon = max([last_data] + [e["window_end"] for _, e in all_episodes])
    collective = []
    for m in _month_range(min(all_months), horizon):
        live = [mm[m] for mm in per_channel_monthly.values() if m in mm]
        open_windows = [cid for cid, e in all_episodes
                        if e["window_start"] <= m <= e["window_end"]]
        collective.append({
            "date": m,
            "n_red": sum(1 for s in live if s >= RED_LINE) if live else None,
            "pressure": round(sum(live) / len(live), 1) if live else None,
            "windows_open": len(open_windows),
            "window_channels": sorted(set(open_windows)),
            "projected": m > last_data,
        })

    _annotate_outcomes(channels_out, recessions, drawdowns, last_data)

    return {
        "channels": channels_out,
        "collective": {"series": collective, "last_data_month": last_data},
        "confluence": _confluence(collective, last_data, bundle),
        "recessions": recessions,
        "drawdowns": drawdowns,
        "framing": "Each channel's severity, recomputed monthly over full source "
                   "history (monthly max, expanding percentiles — no lookahead). "
                   "A red episode casts that channel's documented damage window "
                   "forward; the bottom series counts overlapping open windows. "
                   "One spark is a data point — several open windows is a regime.",
        # Static, dated conclusion of studies/pin-rule-hindcast.md (re-run the
        # script there to refresh). Kept as documented text, like kill rates —
        # never auto-fitted into a probability.
        "measured_roles": (
            "Measured division of labor (hindcast 1981–2026, "
            "studies/pin-rule-hindcast v2): recession onsets belong to the "
            "yield curve — 31% precision, 4/4 onsets caught — and nothing "
            "built from pin reds reliably improved on it; raw convergence "
            "counts scored BELOW base rate (6% vs 12%). Pin reds earn their "
            "keep on market accidents: fast-channel red on a flat/inverted "
            "curve preceded a ≥15% drawdown start within 12m in 44% of months "
            "vs a 20% base (5 of 11 signal-clusters hit: 1998 LTCM 4m early, "
            "2007 up to 12m, 2019 11m, 2025 12m; missed 2018 and 2021). "
            "Oil/policy-window+curve scores the same within noise — ~11 "
            "clusters is a small sample; treat as context. Read the curve "
            "model for recession odds; read this board as an accident radar."
        ),
    }


def _drawdown_spans(dates: list[date], closes: list[float | None],
                    lows: list[float | None], threshold_pct: float = 15.0) -> list[dict]:
    """SPX peak-to-trough drawdowns deeper than threshold, as {start, trough,
    depth_pct} month spans. The market's own ground truth — half these channels
    historically produced violent drawdowns WITHOUT recessions (1987, 2018 Q4,
    Aug 2024), so judging them against NBER bands alone undercounts real hits.

    start = the peak month (decline begins), trough = the depth month. Depth is
    measured running-peak-of-closes vs monthly LOWS so intra-month troughs keep
    their real size — the low is evaluated BEFORE the close can reset the peak,
    so a crash-and-recover month still registers. An episode closes when the
    close regains the prior peak. Known definitional choice: a correction
    nested inside a longer underwater stretch (2011's -21% inside the
    2007->2013 recovery) is absorbed into the parent episode, not listed twice.
    """
    spans: list[dict] = []
    peak: float | None = None
    peak_d: date | None = None
    active: dict | None = None
    depth_max = 0.0
    for d, c, l in zip(dates, closes, lows):
        if c is None:
            continue
        # evaluate this month's low against the PRIOR peak first, so a deep
        # intra-month dip is never erased by a same-month recovery close
        if peak is not None and peak > 0:
            low = l if l is not None else c
            depth = (peak - low) / peak * 100.0
            if depth >= threshold_pct:
                if active is None:
                    active = {"start": _ym(peak_d), "trough": _ym(d),
                              "depth_pct": round(depth, 1)}
                    depth_max = depth
                elif depth > depth_max:
                    active["trough"] = _ym(d)
                    active["depth_pct"] = round(depth, 1)
                    depth_max = depth
        if peak is None or c >= peak:
            if active is not None:
                spans.append(active)
                active = None
                depth_max = 0.0
            peak, peak_d = c, d
    if active is not None:
        spans.append(active)
    return spans


def _annotate_outcomes(channels_out: list[dict], recessions: list[dict],
                       drawdowns: list[dict], last_data: str) -> None:
    """Judge every red episode against its own window: did a recession onset OR
    the START of a >=15% drawdown land inside it? hit / miss / open (window
    still running). A hit requires the event to BEGIN inside the window — a red
    that fires mid-collapse gets no credit for "catching" the crash it is
    reacting to. With no ground truth available at all (both source fetches
    failed), episodes stay unjudged rather than being scored as misses."""
    if not recessions and not drawdowns:
        for ch in channels_out:
            ch["outcomes"] = None
        return
    onsets = [r["start"] for r in recessions]
    dd_starts = [dd["start"] for dd in drawdowns]
    for ch in channels_out:
        counts = {"hit": 0, "miss": 0, "open": 0}
        for e in ch["episodes"]:
            ws, we = e["window_start"], e["window_end"]
            if any(ws <= o <= we for o in onsets):
                e["outcome"] = "hit_recession"
                counts["hit"] += 1
            elif any(ws <= s <= we for s in dd_starts):
                e["outcome"] = "hit_drawdown"
                counts["hit"] += 1
            elif we > last_data:
                e["outcome"] = "open"
                counts["open"] += 1
            else:
                e["outcome"] = "miss"
                counts["miss"] += 1
        ch["outcomes"] = counts if ch["episodes"] else None


def _recession_spans(dates: list[date], vals: list[float | None]) -> list[dict]:
    """NBER recession spans as {start, end} months, from the USREC series.
    Ground truth the charts annotate — did the windows line up with the pain?"""
    spans: list[dict] = []
    start: date | None = None
    prev, prev_d = 0.0, None
    for d, v in zip(dates, vals):
        cur = v or 0.0
        if cur == 1.0 and prev != 1.0:
            start = d
        elif cur != 1.0 and prev == 1.0 and start is not None and prev_d is not None:
            spans.append({"start": _ym(start), "end": _ym(prev_d)})
            start = None
        prev, prev_d = cur, d
    if prev == 1.0 and start is not None and prev_d is not None:
        spans.append({"start": _ym(start), "end": _ym(prev_d)})
    return spans


# --- confluence: the refined forward window ------------------------------------
# Two deliberately different kinds of statement, kept apart:
#   1. The FORWARD WINDOW is arithmetic, not statistics: the months from now on
#      where the most already-cast damage windows overlap. Documented lags in,
#      an intersection out — nothing is estimated.
#   2. The HINDCAST VALIDATION is descriptive: for each overlap level k, how
#      often a month like that was followed by an NBER recession onset within
#      12 months, vs. the unconditional base rate. With ~7 onsets inside the
#      collective's coverage and serially-correlated months, this is CONTEXT
#      for reading the chart — never a calibrated probability (the same reason
#      the transmission note is worded, not numbered).

def _confluence(collective: list[dict], last_data: str, bundle: dict) -> dict:
    ahead = [r for r in collective if r["date"] >= last_data]
    now_row = next((r for r in collective if r["date"] == last_data), None)
    peak = max((r["windows_open"] for r in ahead), default=0)
    peak_months = [r["date"] for r in ahead if r["windows_open"] == peak] if peak else []
    return {
        "open_now": now_row["windows_open"] if now_row else 0,
        "channels_now": now_row["window_channels"] if now_row else [],
        "peak_ahead": peak,
        "peak_window": [peak_months[0], peak_months[-1]] if peak_months else None,
        "peak_channels": sorted({c for r in ahead for c in r["window_channels"]
                                 if r["windows_open"] == peak}) if peak else [],
        "validation": _overlap_validation(collective, bundle),
        "caveat": "The forward window is set arithmetic over documented lags, "
                  "not a forecast. The hindcast hit rates are descriptive context "
                  "from a handful of recessions with serially-correlated months — "
                  "never a calibrated probability. Channel coverage also grows "
                  "over time (1 channel reporting in 1977 vs 12 now), so "
                  "high-overlap months cluster in the modern era and the "
                  "threshold rows are era-confounded, not like-for-like.",
    }


def _overlap_validation(collective: list[dict], bundle: dict) -> dict | None:
    """Descriptive hindcast: P(NBER onset within 12m | windows_open >= k)."""
    from ..sources.fred import recession_start_dates

    rec_d, rec_v = bundle.get("recession", ([], []))
    if not rec_d:
        return None
    onsets = sorted(_ym(d) for d in recession_start_dates(rec_d, rec_v))
    if not onsets:
        return None
    # only months whose 12m-forward outcome is fully observable — with a
    # further 12m haircut because NBER declares onsets up to ~a year late,
    # so trailing USREC zeros are "undeclared", not confirmed non-recessions
    last_cov = _add_months(_ym(max(rec_d)), -12)
    rows = [r for r in collective
            if not r["projected"] and _add_months(r["date"], 12) <= last_cov]
    if len(rows) < 24:
        return None

    def hit(m: str) -> bool:
        h = _add_months(m, 12)
        return any(m < o <= h for o in onsets)

    base_hits = sum(1 for r in rows if hit(r["date"]))
    # onsets inside the outcome coverage: any onset a row could have "hit"
    onsets_covered = sum(1 for o in onsets
                         if rows[0]["date"] < o <= _add_months(rows[-1]["date"], 12))
    thresholds = []
    for k in (1, 2, 3, 4):
        sel = [r for r in rows if r["windows_open"] >= k]
        if len(sel) < 3:
            continue
        thresholds.append({
            "k": k,
            "n_months": len(sel),
            "hit_rate": round(sum(1 for r in sel if hit(r["date"])) / len(sel), 3),
        })
    return {
        "n_months": len(rows),
        "n_onsets_covered": onsets_covered,
        "base_rate": round(base_hits / len(rows), 3),
        "horizon_months": 12,
        "thresholds": thresholds,
    }
