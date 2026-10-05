#!/usr/bin/env python3
"""Live-vs-backtest divergence for an invested symphony (distribution-aware).

MEASUREMENT BASIS (results.md addendum 38, 2026-10-05; revised after the
adversarial panel the same day)

  The live deposit-adjusted curve is a PRICE path: it drops by w*D/P on every
  ex-date (confirmed to <=0.3 bps on the clean cases, lens 1). The Composer
  backtest is a TOTAL-RETURN path (adjusted closes). On each ex-date the model
  earned the distribution term
      term_i(t) = w_i(t-1) * D_i / P_i(t-1) * (1 + r_i^adj(t))
  (multiplicative / Yahoo-adjclose convention, w(t-1) = the holdings Composer
  shows for the PREVIOUS trading day — both verified against the backtest to
  <0.4 bps, lens 2 and the model-reproduction gate in tests/).

  Where that income goes on the LIVE side depends on whether the payer was
  held continuously from the ex-date through the pay-date credit (lens 3,
  reconciled against account cash and fills):
    LEAKED        the position was closed before the credit -> where live held
                  the payer, the cash was observed landing in ACCOUNT
                  unallocated cash and never reaching the live curve (3/3
                  observed cases: ZVOL 2026-08-19, BIL 2026-08-03, TMV
                  2026-09-22); where live did NOT hold it (model-only rows,
                  below) there was no income at all and the strip reads in
                  live's favour.
    HELD_THROUGH  the credit is applied INSIDE the symphony on pay date
                  (ex+1..ex+5 bd, fund-specific) and the live curve shows a
                  +income day the model never does (HG 2026-09-04 +30.5 bps).
  The classifier here is the MODEL's own continuity: a row is HELD_THROUGH
  when the model holds the payer on every model day from the ex-date through
  ex+4 (HELD_THROUGH_DAYS; the longest pay lag observed is 5 bd). On the
  frozen 2026-10-05 panel it reproduces lens 3's cash-trail labels 14/14.
  It is a proxy for the LIVE book: it is wrong when live holdings differ from
  the model around an ex-date (KMLM TLT 2026-09-01: the model held TLT, live
  had sold it the day before; its 28.5 bps is stripped from the model and
  reads +28.5 bps in live's favour — a model-only holding is not detectable
  without per-symphony live share counts, which Composer does not expose).
  Known model-only rows on the 2026-10-05 panel: KMLM TLT 09-01 (28.5 bps)
  and four pre-edit HG rows (TNA 12-23, BIL 02-02/03-02/04-01; live held
  UDOW/XLV/ANGL/UGE; 91 bps together, ~+1.1 %/yr on HG's full window).
  The rule is fund-agnostic: a fast payer (ZVOL pays ex+1, PULS ex+2, BIL
  ex+3) the model holds for fewer than 5 days across an ex-date would be
  labelled LEAKED although live was credited inside the symphony — no such
  case exists on the frozen panel; it is the classifier's forward risk.
  Rows whose ex-date falls in the last HELD_THROUGH_DAYS model days are
  classified on a clipped span (held_days_checked < 5) and show() marks
  them "credit pending": the label can flip and the primary gap carries
  -w*y until the pay date lands inside the window.

  PRIMARY GAP (cumulative, mean/annualized, worst/best day — what Op2/Op3 read)
      live price path  vs  model with the LEAKED terms removed.
      Leaked income is gone from live for good, so it is removed from the
      model; held-through income re-enters live within <=5 bd, so the model
      keeps it and the mean gap is unbiased — live's ex-date dip and pay-date
      recovery cancel inside the window (a +-w*y wobble on two days remains in
      the daily series and can be the worst/best day for a 100%-weight payer).
  SECOND MOMENTS (corr, beta, vol-ratio — the monitor's gauge-RED checks)
      live + ALL terms (live total return on an ex-date basis)  vs  model
      total return. Subtracting the term from the model instead turns every
      ex-date into a shared manufactured outlier: on HARV that one point
      (ZVOL 08-19) lifted corr 0.857 -> 0.946, beta 0.84 -> 1.14, vol-ratio
      0.97 -> 1.20 (lens 1). On this pair the only unmodeled artefacts are the
      pay-date recredits (live-only +w*y days on held-through rows).
  SECONDARY  the add.-36/37 comparison (live price path vs model total
      return), kept under *_total_return_basis keys. It false-failed HARV.
  REFERENCE  annualized_gap_all_exdates_stripped: the gap with EVERY term
      removed from the model (the first add.-38 build). It is lenient by the
      held-through credits (+0.6..+1.0 %/yr on HG/KMLM/SLEEVE, +4.6 %/yr on
      HARV at 2026-10-05) and is kept only so the bias is visible.

NOT MODELED (stated so the gap is read correctly)
  - intraday fill timing: live trades ~15:50, the model marks at the close.
    After the fix HARV 2026-08-19 still shows ~-61 bps = ZVOL sold at 7.4502
    vs the 7.55 close; that is the genuine shortfall the gates measure.
  - pay dates themselves: the recredit day is not placed; its +w*y stays in
    the daily series. Pay lags are inferred (lens 3), not sourced.
  - live share counts: the ledger's expected_income_usd is MODEL entitlement
    (w(t-1) x live $ value x yield) — live's own only where live matched the
    model that morning.
  - Composer's own cash yield, and the ~10.3 bps x one-way-turnover friction
    the backtest charges itself (lens 2): the gap nets live fill shortfall
    against that modeled cost.
  - decision-divergence days (live trades a day before the model, or the model
    does a 1-day round trip live never did) are NOT a distribution effect and
    remain in every statistic.
  - strategy edits: the backtest is the CURRENT version; HG/SLEEVE were edited
    live on 2026-07-30/31, so their full-window numbers mix two strategies.

HONEST FAILURE: if Yahoo cannot be fetched for a ticker the model held, or a
model weight is keyed on a date that is not on the backtest calendar (the term
could not be applied), the result carries distribution_data = "INCOMPLETE"
plus the ticker/date list and show() says the primary numbers are not
distribution-adjusted. monitor.py treats INCOMPLETE as "diagnostic
unavailable". Never a silent fall-back to the old number.

Read-only. Usage:
  divergence.py <symphony-id> [--account UUID] [--name divergence-<x>]
  divergence.py --all          # every invested symphony
"""

import argparse
import datetime as _dt
import json as _json
import statistics
import urllib.request

import composerlib as cl

CASH_TICKER = "$USD"           # Composer's cash pseudo-ticker (never a payer)
HELD_THROUGH_DAYS = 4          # model must hold the payer on ex..ex+4 model
                               # days to count as HELD_THROUGH (pay lag <=5 bd)
_YAHOO_CACHE = {}              # ticker -> chart dict; --all must not refetch
_YAHOO_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{t}"
                "?period1=1680000000&period2=4102444800&interval=1d&events=div")


# --------------------------------------------------------------------------
# I/O: Composer live + backtest + Yahoo, then hand off to the pure math
# --------------------------------------------------------------------------

def analyze(acct, sym_id, sym_name, detail=False):
    pos = cl.get(f"/portfolio/accounts/{acct}/symphonies/{sym_id}")
    dates = [cl.epoch_ms_to_date(ms).isoformat() for ms in pos["epoch_ms"]]
    live_vals = pos.get("deposit_adjusted_series")
    live_raw = pos.get("series")
    if not live_vals:
        # never fall back to the raw $ series: deposits/redeploys (08-25 was
        # >60 bps) would read as live return. Error -> monitor treats the
        # diagnostic as unavailable (panel finding, lens 1).
        return {"symphony": sym_id, "name": sym_name,
                "error": "deposit_adjusted_series missing from Composer response "
                         "— raw series is not comparable (deposits); not analyzed"}
    if len(dates) < 5:
        return {"symphony": sym_id, "name": sym_name,
                "error": f"only {len(dates)} live days — too new to compare"}

    bt = cl.backtest_by_id(sym_id, start=dates[0], end=dates[-1])
    days, vals = cl.equity_curve(bt)
    model_dates = [cl.epoch_day_to_date(d).isoformat() for d in days]
    weights = weights_to_iso(bt.get("tdvm_weights") or {})

    # one Yahoo chart per held ticker; a failed fetch is LEFT OUT so the
    # result is flagged INCOMPLETE rather than silently unadjusted
    dists = {}
    for t in sorted(_held_tickers(weights)):
        chart = fetch_yahoo_chart(t)
        if chart is not None:
            dists[t] = dists_from_chart(chart)

    return analyze_series(dates, live_vals, model_dates, vals, weights, dists,
                          live_raw=live_raw, symphony=sym_id, name=sym_name,
                          detail=detail)


def weights_to_iso(tdvm_weights):
    """Composer keys tdvm_weights by epoch DAY; the math wants ISO dates."""
    out = {}
    for t, dd in (tdvm_weights or {}).items():
        conv = {}
        for d, w in (dd or {}).items():
            key = (cl.epoch_day_to_date(int(d)).isoformat()
                   if str(d).lstrip("-").isdigit() else str(d))
            conv[key] = w
        out[t] = conv
    return out


def fetch_yahoo_chart(ticker):
    """{dates, close, adjclose, divs:[(ex_date, amount)]} or None on failure.

    Cached at module level so `--all` and the monitor's gauge-RED sweep hit
    Yahoo once per ticker. Failures are NOT cached (a retry on the next
    symphony is cheap and may succeed)."""
    if ticker in _YAHOO_CACHE:
        return _YAHOO_CACHE[ticker]
    try:
        rq = urllib.request.Request(_YAHOO_CHART.format(t=ticker.replace(".", "-")),
                                    headers={"user-agent": "Mozilla/5.0"})
        res = _json.load(urllib.request.urlopen(rq, timeout=30))["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
        chart = {"dates": [], "close": [], "adjclose": [], "divs": []}
        for i, ts in enumerate(res["timestamp"]):
            if q["close"][i] is None:
                continue
            chart["dates"].append(_dt.datetime.fromtimestamp(
                int(ts), tz=_dt.timezone.utc).date().isoformat())
            chart["close"].append(float(q["close"][i]))
            chart["adjclose"].append(float(adj[i] if adj[i] is not None else q["close"][i]))
        for v in ((res.get("events") or {}).get("dividends") or {}).values():
            d = _dt.datetime.fromtimestamp(int(v["date"]),
                                           tz=_dt.timezone.utc).date().isoformat()
            chart["divs"].append((d, float(v["amount"])))
        chart["divs"].sort()
    except Exception:  # noqa: BLE001 — caller flags INCOMPLETE
        return None
    _YAHOO_CACHE[ticker] = chart
    return chart


def dists_from_chart(chart):
    """{ex_date: {amount, prev_close, adj_ret, px_ret}} from a Yahoo chart.

    Yahoo convention: adjclose_{t-1} = close_{t-1} - D on an ex-date, so
    adj_ret = P_t/(P_{t-1}-D) - 1 and the distribution term the model earned
    is D/P_{t-1} * (1 + adj_ret) = adj_ret - px_ret exactly (add. 38 lens 2).
    An ex-date Yahoo has no bar for is attached to the next bar."""
    dates, close, adj = chart["dates"], chart["close"], chart["adjclose"]
    idx = {d: i for i, d in enumerate(dates)}
    out = {}
    for d, amt in chart.get("divs") or []:
        j = idx.get(d)
        if j is None:
            later = [i for i, x in enumerate(dates) if x >= d]
            if not later:
                continue
            j = later[0]
        if j < 1 or close[j - 1] <= 0 or adj[j - 1] <= 0:
            continue
        out[d] = {"amount": float(amt), "prev_close": close[j - 1],
                  "adj_ret": adj[j] / adj[j - 1] - 1.0,
                  "px_ret": close[j] / close[j - 1] - 1.0}
    return out


# --------------------------------------------------------------------------
# pure math — no network, no Composer; fully exercised by tests/test_divergence
# --------------------------------------------------------------------------

def _held_tickers(bt_or_weights):
    """Tickers the model actually held over the window (cash excluded).
    Accepts a backtest dict (tdvm_weights inside) or a weights dict."""
    w = bt_or_weights
    if isinstance(w, dict) and "tdvm_weights" in w:
        w = w.get("tdvm_weights") or {}
    return {t for t, dd in (w or {}).items()
            if t != CASH_TICKER and any(v and v > 1e-6 for v in (dd or {}).values())}


def weight_dates_off_calendar(weights, model_dates):
    """In-window weight dates (w > 0, cash excluded) that are NOT model days.
    A term keyed on such a date would silently not apply, so the caller
    flags the result INCOMPLETE (panel finding, lens 1)."""
    if not model_dates:
        return []
    md = set(model_dates)
    first, last = model_dates[0], model_dates[-1]
    return sorted({(t, d) for t, dd in (weights or {}).items() if t != CASH_TICKER
                   for d, w in (dd or {}).items()
                   if w and w > 1e-6 and first <= d <= last and d not in md})


def price_only_model_returns(model_dates, model_vals, weights, dists, live_raw=None,
                             held_through_days=HELD_THROUGH_DAYS):
    """Strip distribution income from the model's daily returns.

    Returns (ret_tr, ret_px, ledger): lists aligned with model_dates (index 0
    is None — no return into the first day) and the per-ex-date ledger rows.
    ret_px has EVERY term removed (the all-stripped, price-only model);
    ret_px[i] IS ret_tr[i] (same float object) on every day without a term,
    so the invariance test can check bit-for-bit equality. The PRIMARY model
    (leaked terms only) is built from the ledger by leak_adjusted_returns().

    Timing: Composer's weights shown for date t-1 are the holdings that EARN
    date t's return, so the payer weight on ex-date t is weights[t-1]
    (lag test, add. 38 lens 2: w(t-1) fits to 0.01-0.14 bps, w(t) to 34-372).
    Classification: HELD_THROUGH when weights[ex..ex+held_through_days] are
    all > 0 (clipped at the window end; held_days_checked says how many days
    were available), else LEAKED.
    live_raw ({date: live $ value}) only feeds expected_income_usd."""
    n = len(model_dates)
    ret_tr = [None] + [model_vals[i] / model_vals[i - 1] - 1.0 for i in range(1, n)]
    ret_px = list(ret_tr)
    ledger = []
    if n < 2:
        return ret_tr, ret_px, ledger

    # map each ex-date to the model day whose return contains it (the ex-date
    # itself, or the next model day when the ex-date is not on the calendar)
    first, last = model_dates[0], model_dates[-1]
    terms = {}                                       # model index -> summed term
    for t in sorted(dists or {}):
        wt = weights.get(t) or {}
        for ex in sorted(dists[t] or {}):
            if ex <= first or ex > last:
                continue
            i = next(k for k, d in enumerate(model_dates) if d >= ex)
            if i < 1:
                continue
            w_prev = wt.get(model_dates[i - 1]) or 0.0
            if w_prev <= 1e-9:
                continue                             # model did not hold the payer
            row = dists[t][ex]
            y = row["amount"] / row["prev_close"]
            term = w_prev * y * (1.0 + row["adj_ret"])
            terms[i] = terms.get(i, 0.0) + term
            prev_val = (live_raw or {}).get(model_dates[i - 1])
            span = model_dates[i:i + held_through_days + 1]
            held = all((wt.get(d) or 0.0) > 1e-9 for d in span)
            ledger.append({
                "date": ex, "applied_on": model_dates[i], "ticker": t,
                "amount": row["amount"], "prev_close": row["prev_close"],
                "yield": y, "adj_ret": row["adj_ret"],
                "weight": w_prev, "weight_date": model_dates[i - 1],
                "term_bps": term * 1e4,
                "treatment": "HELD_THROUGH" if held else "LEAKED",
                "held_days_checked": len(span),
                # removed from the PRIMARY model: leaked rows only
                "subtracted_bps": 0.0 if held else term * 1e4,
                # MODEL entitlement: shares x D = w x $value / P_prev x D.
                # Equals live's only where live matched the model that morning.
                "expected_income_usd": (w_prev * prev_val * y
                                        if prev_val is not None else None),
            })
    for i, term in terms.items():
        ret_px[i] = ret_tr[i] - term
    ledger.sort(key=lambda r: (r["date"], r["ticker"]))
    return ret_tr, ret_px, ledger


def leak_adjusted_returns(ret_tr, model_dates, ledger):
    """Model daily returns with ONLY the leaked terms removed (the PRIMARY
    model). Days without a leaked row keep the same float object."""
    idx = {d: i for i, d in enumerate(model_dates)}
    terms = {}
    for r in ledger:
        if r["treatment"] == "LEAKED":
            i = idx[r["applied_on"]]
            terms[i] = terms.get(i, 0.0) + r["term_bps"] / 1e4
    out = list(ret_tr)
    for i, term in terms.items():
        out[i] = ret_tr[i] - term
    return out


def _rebuild(start, rets):
    """Equity curve from a start value and returns (rets[0] is None)."""
    out = [start]
    for r in rets[1:]:
        out.append(out[-1] * (1.0 + r))
    return out


def _on_calendar(model_dates, rets, common):
    """Model returns re-expressed on the common (live) calendar: a single
    model day passes through untouched (bit-for-bit); a run of model days the
    live calendar skips is compounded."""
    idx = {d: i for i, d in enumerate(model_dates)}
    out = []
    for k in range(1, len(common)):
        seg = rets[idx[common[k - 1]] + 1: idx[common[k]] + 1]
        if len(seg) == 1:
            out.append(seg[0])
        else:
            f = 1.0
            for r in seg:
                f *= 1.0 + r
            out.append(f - 1.0)
    return out


def _pair_stats(lr, mr, lr_mom=None, mr_mom=None):
    """Daily-gap statistics on (lr, mr) = live minus model; second-moment
    statistics (corr, beta, vol-ratio) on (lr_mom, mr_mom) when given, else
    on the same pair. See the module docstring for why the primary result
    uses two pairs."""
    gaps = [a - b for a, b in zip(lr, mr)]           # live minus model, daily
    n = len(gaps)
    mean_gap = sum(gaps) / n
    worst = min(range(n), key=lambda i: gaps[i])
    best = max(range(n), key=lambda i: gaps[i])
    a = lr if lr_mom is None else lr_mom
    b = mr if mr_mom is None else mr_mom
    return {
        "mean_daily_gap_bps": round(mean_gap * 1e4, 2),
        "annualized_gap": round(mean_gap * 252, 4),
        "worst_daily_gap_bps": round(gaps[worst] * 1e4, 1),
        "best_daily_gap_bps": round(gaps[best] * 1e4, 1),
        "daily_return_correlation": round(cl.pearson(a, b) or 0.0, 3),
        # earn-back fat-tail detectors (results.md addendum 21): live beta to
        # model, live/model vol ratio
        "live_beta_to_model": round(_beta(a, b), 3),
        "live_model_vol_ratio": round(_vol_ratio(a, b), 3),
        "_worst_i": worst, "_best_i": best,
    }


def analyze_series(live_dates, live_vals, model_dates, model_vals, weights, dists,
                   live_raw=None, symphony="", name="", detail=False):
    """Full divergence result from in-memory series (no I/O).

    live_dates/live_vals : live deposit-adjusted curve (ISO dates)
    model_dates/model_vals: Composer backtest equity curve, same window
    weights : {ticker: {ISO date: weight}} — Composer tdvm_weights (sparse;
              a missing date is 0; holdings shown for t earn t+1)
    dists   : {ticker: {ex_date: {amount, prev_close, adj_ret}}} for EVERY
              ticker the model held ({} if it paid nothing). A held ticker
              absent from dists marks the result INCOMPLETE.
    live_raw: optional live raw $ series aligned with live_dates (for the
              ledger's expected_income_usd)
    detail  : add a per-day table (tests / chart work)."""
    live = dict(zip(live_dates, live_vals))
    if len(live) < 5:
        return {"symphony": symphony, "name": name,
                "error": f"only {len(live)} live days — too new to compare"}
    model = dict(zip(model_dates, model_vals))
    common = sorted(set(live) & set(model))
    if len(common) < 5:
        return {"symphony": symphony, "name": name,
                "error": f"only {len(common)} overlapping days"}

    raw_by_date = dict(zip(live_dates, live_raw)) if live_raw else None
    held = _held_tickers(weights)
    missing = sorted(held - set(dists or {}))
    off_cal = weight_dates_off_calendar(weights, model_dates)
    ret_tr, ret_px, ledger = price_only_model_returns(
        model_dates, model_vals, weights, dists or {}, live_raw=raw_by_date)
    ledger = [r for r in ledger if common[0] < r["applied_on"] <= common[-1]]
    ret_adj = leak_adjusted_returns(ret_tr, model_dates, ledger)
    model_adj = dict(zip(model_dates, _rebuild(model_vals[0], ret_adj)))
    model_px = dict(zip(model_dates, _rebuild(model_vals[0], ret_px)))

    lv = [live[d] for d in common]
    lr = [lv[i] / lv[i - 1] - 1.0 for i in range(1, len(lv))]
    mr_adj = _on_calendar(model_dates, ret_adj, common)   # leaked terms removed
    mr_px = _on_calendar(model_dates, ret_px, common)     # every term removed
    mr_tr = _on_calendar(model_dates, ret_tr, common)     # total return
    # live total return on an ex-date basis: every term added back to live.
    # Identity: lr - mr_px == lr_tr - mr_tr day by day (side-invariant gaps).
    lr_tr = [a + (b - c) for a, b, c in zip(lr, mr_tr, mr_px)]
    mv_tr = [model[d] for d in common]
    mv_adj = [model_adj[d] for d in common]
    mv_px = [model_px[d] for d in common]

    live_cum = lv[-1] / lv[0] - 1.0
    model_cum_adj = mv_adj[-1] / mv_adj[0] - 1.0
    model_cum_px = mv_px[-1] / mv_px[0] - 1.0
    model_cum_tr = mv_tr[-1] / mv_tr[0] - 1.0
    prim = _pair_stats(lr, mr_adj, lr_tr, mr_tr)
    allpx = _pair_stats(lr, mr_px, lr_tr, mr_tr)
    sec = _pair_stats(lr, mr_tr)

    ex_dates = sorted((ex, t, float(v["amount"]))
                      for t in held if t in (dists or {})
                      for ex, v in (dists[t] or {}).items()
                      if common[0] <= ex <= common[-1])
    inc = [r["expected_income_usd"] for r in ledger]
    leaked = [r for r in ledger if r["treatment"] == "LEAKED"]
    held_rows = [r for r in ledger if r["treatment"] == "HELD_THROUGH"]
    n_days = len(lr)
    r = {
        "symphony": symphony, "name": name,
        "window": [common[0], common[-1]], "n_days": n_days,
        "measurement_basis": (
            "gap: live deposit-adjusted PRICE path vs model with LEAKED "
            "distribution terms removed (w(t-1) x D/P_prev x (1+r_adj) on the "
            "ex-date; held-through rows stay in the model because their income "
            "re-enters live on pay date); corr/beta/vol: live + every term vs "
            "model total return; add. 38 (panel-revised)"),
        # ---- PRIMARY: what Op2/Op3 and monitor.py read ----
        "live_cumulative_return": round(live_cum, 4),
        "model_cumulative_return": round(model_cum_adj, 4),
        "cumulative_gap": round(live_cum - model_cum_adj, 4),
        "mean_daily_gap_bps": prim["mean_daily_gap_bps"],
        "annualized_gap": prim["annualized_gap"],
        "worst_daily_gap_bps": prim["worst_daily_gap_bps"],
        "worst_daily_gap_date": common[prim["_worst_i"] + 1],
        "best_daily_gap_bps": prim["best_daily_gap_bps"],
        "best_daily_gap_date": common[prim["_best_i"] + 1],
        "daily_return_correlation": prim["daily_return_correlation"],
        "live_beta_to_model": prim["live_beta_to_model"],
        "live_model_vol_ratio": prim["live_model_vol_ratio"],
        "live_max_drawdown": round(cl.max_drawdown(lv), 4),
        # ---- REFERENCE: every term stripped (first add.-38 build; lenient by
        #      the held-through credits — kept so the bias is visible) ----
        "model_cumulative_return_all_exdates_stripped": round(model_cum_px, 4),
        "annualized_gap_all_exdates_stripped": allpx["annualized_gap"],
        "held_through_credit_bias_annualized": round(
            allpx["annualized_gap"] - prim["annualized_gap"], 4),
        # ---- SECONDARY (add. 36/37 basis: live price path vs model total return) ----
        "model_total_return_cumulative": round(model_cum_tr, 4),
        "cumulative_gap_total_return_basis": round(live_cum - model_cum_tr, 4),
        "mean_daily_gap_bps_total_return_basis": sec["mean_daily_gap_bps"],
        "annualized_gap_total_return_basis": sec["annualized_gap"],
        "daily_return_correlation_total_return_basis": sec["daily_return_correlation"],
        "live_beta_to_model_total_return_basis": sec["live_beta_to_model"],
        "live_model_vol_ratio_total_return_basis": sec["live_model_vol_ratio"],
        # ---- distribution ledger ----
        "distribution_data": "INCOMPLETE" if (missing or off_cal) else "COMPLETE",
        "distribution_missing_tickers": missing,
        "weight_dates_off_calendar": [list(x) for x in off_cal],
        "distribution_ledger": [
            {k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()}
            for row in ledger],
        "distribution_totals": {
            "n_rows": len(ledger),
            "n_leaked": len(leaked),
            "n_held_through": len(held_rows),
            "term_bps": round(sum(x["term_bps"] for x in ledger), 2),
            "subtracted_bps": round(sum(x["subtracted_bps"] for x in ledger), 2),
            "held_through_bps": round(sum(x["term_bps"] for x in held_rows), 2),
            "expected_income_usd": (round(sum(inc), 2)
                                    if ledger and all(x is not None for x in inc)
                                    else None),
            "expected_income_usd_basis": ("MODEL entitlement (w(t-1) x live $ x "
                                          "yield); live's own only where live "
                                          "matched the model that morning"),
        },
        "ex_dates": ex_dates,
    }
    if detail:
        r["daily"] = [{"date": common[i + 1], "live_ret": lr[i],
                       "live_ret_total_return": lr_tr[i],
                       "model_ret": mr_adj[i],
                       "model_ret_price_only": mr_px[i],
                       "model_ret_total_return": mr_tr[i],
                       "gap_bps": (lr[i] - mr_adj[i]) * 1e4,
                       "gap_bps_price_only_basis": (lr[i] - mr_px[i]) * 1e4,
                       "gap_bps_total_return_basis": (lr[i] - mr_tr[i]) * 1e4}
                      for i in range(n_days)]
    return r


def ex_dates_in_window(tickers, start, end):
    """Distribution ex-dates for tickers inside [start, end] (informational,
    kept from add. 37; now served from the shared Yahoo cache)."""
    out = []
    for t in sorted(tickers):
        chart = fetch_yahoo_chart(t)
        for d, amt in (chart or {}).get("divs") or []:
            if start <= d <= end:
                out.append((d, t, float(amt)))
    return sorted(out)


def _beta(lr, mr):
    n = len(mr)
    if n < 3:
        return 0.0
    ma = sum(lr) / n
    mb = sum(mr) / n
    var = sum((y - mb) ** 2 for y in mr) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(lr, mr)) / n
    return cov / var if var else 0.0


def _vol_ratio(lr, mr):
    sm = statistics.pstdev(mr)
    return statistics.pstdev(lr) / sm if sm else 0.0


# --------------------------------------------------------------------------
# display
# --------------------------------------------------------------------------

def show(r):
    print(f"  {r['name'][:60]} [{r['symphony'][:8]}]")
    if "error" in r:
        print(f"      {r['error']}")
        return
    print(f"      window {r['window'][0]} .. {r['window'][1]} ({r['n_days']} days)")
    print(f"      basis: live PRICE path vs model with LEAKED distributions removed "
          f"(held-through income re-enters live; corr/beta/vol on the "
          f"total-return pair) — add. 38, panel-revised")
    print(f"      cumulative: live {r['live_cumulative_return']:+7.2%}  "
          f"model {r['model_cumulative_return']:+7.2%}  "
          f"gap {r['cumulative_gap']:+7.2%}   "
          f"[total-return basis: model {r['model_total_return_cumulative']:+7.2%} "
          f"gap {r['cumulative_gap_total_return_basis']:+7.2%}]")
    print(f"      beta {r['live_beta_to_model']:.2f}  vol-ratio "
          f"{r['live_model_vol_ratio']:.2f}  live maxDD {r['live_max_drawdown']:.1%}")
    print(f"      daily gap: mean {r['mean_daily_gap_bps']:+6.1f} bps "
          f"(~{r['annualized_gap']:+.1%}/yr)  "
          f"range [{r['worst_daily_gap_bps']:+.0f} {r['worst_daily_gap_date']}, "
          f"{r['best_daily_gap_bps']:+.0f} {r['best_daily_gap_date']}] bps")
    if r["held_through_credit_bias_annualized"]:
        print(f"      (stripping EVERY ex-date would read "
              f"{r['annualized_gap_all_exdates_stripped']:+.1%}/yr — lenient by "
              f"{r['held_through_credit_bias_annualized']:+.1%}/yr of held-through "
              f"pay-date credits; not the gate number)")
    print(f"      daily return correlation live~model: {r['daily_return_correlation']:+.3f}"
          f" (total-return basis {r['daily_return_correlation_total_return_basis']:+.3f})"
          + ("   <- LOW: check rebalance timing/fills"
             if abs(r["daily_return_correlation"]) < 0.9 else ""))
    if r["distribution_data"] != "COMPLETE":
        why = []
        if r["distribution_missing_tickers"]:
            why.append(f"Yahoo unavailable for {', '.join(r['distribution_missing_tickers'])}")
        if r.get("weight_dates_off_calendar"):
            why.append("model weights keyed off the backtest calendar: "
                       + ", ".join(f"{t} {d}" for t, d in r["weight_dates_off_calendar"]))
        print(f"      !! DISTRIBUTION DATA INCOMPLETE: {'; '.join(why)} — the PRIMARY "
              f"numbers above are NOT distribution-adjusted for those; any ex-date "
              f"they paid in the window is still a spurious gap. Do not read a gate "
              f"verdict off this run.")
    tot = r["distribution_totals"]
    if r["distribution_ledger"]:
        print(f"      distribution ledger ({tot['n_rows']} ex-dates: {tot['n_leaked']} "
              f"leaked -> {tot['subtracted_bps']:+.1f} bps removed from the model; "
              f"{tot['n_held_through']} held-through -> {tot['held_through_bps']:+.1f} bps "
              f"kept (re-enters live on pay date)"
              + (f"; ~${tot['expected_income_usd']:,.0f} model entitlement"
                 if tot["expected_income_usd"] is not None else "") + "):")
        pending = 0
        for x in r["distribution_ledger"]:
            inc = (f"  ~${x['expected_income_usd']:,.0f}"
                   if x["expected_income_usd"] is not None else "")
            prov = ""
            if x.get("held_days_checked", HELD_THROUGH_DAYS + 1) < HELD_THROUGH_DAYS + 1:
                prov = (f"  [credit pending: {x['held_days_checked']}/{HELD_THROUGH_DAYS + 1} "
                        f"days in window; label provisional]")
                pending += 1
            print(f"        {x['date']} {x['ticker']:5s} ${x['amount']:.4f}/sh  "
                  f"yield {x['yield']*1e4:6.1f} bps  w(t-1) {x['weight']:.3f}  "
                  f"term {x['term_bps']:6.1f} bps  {x['treatment']:12s}"
                  f"{inc}{prov}")
        print(f"      note: LEAKED = model exited within {HELD_THROUGH_DAYS} days of the "
              f"ex-date. Where live held the payer the cash was observed landing in "
              f"ACCOUNT unallocated cash (3/3 cases, lens 3); where live did not "
              f"hold it (model-only rows: KMLM TLT 09-01, pre-edit HG TNA 12-23 / "
              f"BIL 02-02, 03-02, 04-01) the strip reads in live's favour. "
              f"Classified from MODEL continuity (fund-agnostic ex..ex+{HELD_THROUGH_DAYS}).")
        if pending:
            print(f"      !! {pending} ledger row(s) classified on a clipped window span "
                  f"(ex-date within the last {HELD_THROUGH_DAYS} model days): the "
                  f"primary gap carries -w*y until the pay-date credit lands; re-read "
                  f"after {HELD_THROUGH_DAYS + 1} trading days before acting on a gate.")
    skipped = [f"{t} {d}" for d, t, _ in r.get("ex_dates") or []
               if d > r["window"][0]
               and not any(x["date"] == d and x["ticker"] == t
                           for x in r["distribution_ledger"])]
    if skipped:
        print(f"      ex-dates the model did NOT hold into (nothing to remove): "
              + ", ".join(skipped))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("symphony_id", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--account")
    p.add_argument("--name", default="divergence")
    a = p.parse_args()
    if not a.all and not a.symphony_id:
        raise SystemExit("error: pass a symphony id or --all")

    acct = a.account or cl.default_account()
    meta = {s["id"]: s["name"] for s in
            cl.get(f"/portfolio/accounts/{acct}/symphony-stats-meta")["symphonies"]}
    targets = list(meta) if a.all else [a.symphony_id]

    results = []
    print("live vs backtest divergence (deposit-adjusted; distribution-aware, add. 38)\n")
    for sid in targets:
        if sid not in meta:
            raise SystemExit(f"error: {sid} is not an invested symphony in this account")
        r = analyze(acct, sid, meta[sid])
        results.append(r)
        show(r)

    cl.write_json(f"composer/results/{a.name}.json", {"results": results})


if __name__ == "__main__":
    main()
