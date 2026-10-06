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
                  unallocated cash and never reaching the live curve (4/4
                  identified cases: ZVOL 2026-08-19, BIL 2026-08-03, TMV
                  2026-09-22, SSO 2025-12-24; a 5th, TNA 2026-06-23, was held
                  live but its credit is masked by ~$50k of account flows on
                  ex+5..ex+8); where live did NOT hold it (model-only rows,
                  below) there was no income at all and the strip reads in
                  live's favour.
    HELD_THROUGH  the credit is applied INSIDE the symphony on pay date
                  (ex+1..ex+5 bd, fund-specific) and the live curve shows a
                  +income day the model never does (HG 2026-09-04 +30.5 bps).
  The classifier is the MODEL's own continuity against a PER-FUND pay lag L
  (PAY_LAG below: OBSERVED on the fund's OWN credit in the lens-3 cash trail
  — account-cash residual + fills — not issuer documentation and never
  inherited from an issuer family: ZVOL 1, PULS 2, BIL 3, TQQQ 4, SSO 4,
  LABD 5, TMV 5 trading days). The credit lands at the open of model day
  ex+L, before that day's ~15:50 rebalance (HG BIL 09-04: the pay-date 15:53
  reinvestment buy $227.33 vs the $227.61 credit), so "held at pay-date
  open" means
      HELD_THROUGH  iff  weights[ex .. ex+L-1] (model days) are all > 0
  (weights[d] = holdings shown at the close of d); otherwise LEAKED.
  A ticker NOT in PAY_LAG (SOXL and TNA — held live into an ex-date but the
  credit is not identified; QLD/UDOW/TECL — never held live into an
  ex-date; TLT, SQQQ, any new holding) is never given a guessed lag: weights[ex] == 0 -> LEAKED
  for any lag; held ex..ex+(MAX_PAY_LAG-1) -> HELD_THROUGH for any lag up to
  the longest observed; anything between (1..MAX_PAY_LAG-1 held days from
  the ex-date) -> AMBIGUOUS. Removing those five entries (2026-10-05, panel)
  flipped no label, no AMBIGUOUS status and no primary key on the frozen
  panel (KMLM SOXL 09-22 held ex..ex+4; HG TNA sold at both ex-date closes;
  QLD/UDOW/TECL ex-dates never held into). AMBIGUOUS rows
  take the STRICT treatment in the primary gap (income kept in the model, so
  the gap reads LOWER — the safe direction for a pass/fail gate); the row
  carries both alternatives' bps, the result lists them under
  ambiguous_rows with the lenient (stripped) gap alongside, and show()
  names the ticker and the missing lag and says to check the account-cash
  residual before acting on a gate. On the frozen 2026-10-05 panel the
  per-fund table reproduces lens 3's cash-trail labels 14/14 (same labels
  as the earlier fund-agnostic ex..ex+4 rule on every valid-regime row).
  It flips ONE pre-edit row: HG BIL 2026-04-01 (the model held BIL
  ex..ex+3 >= BIL's L=3) LEAKED -> HELD_THROUGH, 28.8 bps back in the model.
  It is a proxy for the LIVE book: it is wrong when live holdings differ from
  the model around an ex-date (KMLM TLT 2026-09-01: the model held TLT, live
  had sold it the day before; its 28.5 bps is stripped from the model and
  reads +28.5 bps in live's favour — a model-only holding is not detectable
  without per-symphony live share counts, which Composer does not expose).
  Known model-only rows on the 2026-10-05 panel: KMLM TLT 09-01 (28.5 bps,
  stripped) and four pre-edit HG rows (TNA 12-23, BIL 02-02/03-02/04-01;
  live held UDOW/XLV/ANGL/UGE): the first three are stripped (62.3 bps,
  ~+0.8 %/yr on HG's full window, in live's favour); BIL 04-01 is now kept.
  CREDIT PENDING: the credit lands on model day ex+L, so a row with no exit
  inside its checked span is flagged credit_pending while the window ends
  before ex+L — fewer than L+1 model days from ex inclusive in the window
  (days_in_window_from_ex < L+1; unknown lag: L := MAX_PAY_LAG). The primary
  gap then carries live's -w*y dip with no recredit (HARV PULS 08-31, L=2:
  a window ending 09-01 reads -3.66 %/yr, -0.61 %/yr once 09-02 is in), and
  a span clipped below L (held_days_checked < held_days_required) also has a
  provisional label. show() marks every pending row. A row that already
  shows an exit inside the span is never pending (LEAKED: the income left
  the symphony; AMBIGUOUS: its held-through reading puts the credit on or
  before the exit day, inside the window).

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
      held-through credits (+1.0..+1.1 %/yr on HG/KMLM/SLEEVE, +4.6 %/yr on
      HARV at 2026-10-05) and is kept only so the bias is visible.
  AMBIGUOUS ALTERNATIVE  *_ambiguous_lenient keys: the primary with the
      AMBIGUOUS rows stripped as well (equal to the primary when there are
      none). Never the gate number; read it only to bound the unknown lag.

NOT MODELED (stated so the gap is read correctly)
  - intraday fill timing: live trades ~15:50, the model marks at the close.
    After the fix HARV 2026-08-19 still shows ~-61 bps = ZVOL sold at 7.4502
    vs the 7.55 close; that is the genuine shortfall the gates measure.
  - pay dates themselves: the recredit day is not placed; its +w*y stays in
    the daily series. Pay lags are OBSERVED on each fund's own credit (lens
    3; 1-3 events per fund), not sourced from issuer calendars; a lag that
    moves (holiday, issuer change) or exceeds MAX_PAY_LAG is not modeled,
    and every unlisted payer takes the unknown-lag path.
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
    --start restricts the comparison (POLICY Op2 reads the sleeve with
    --start 2026-08-01).
  - pre-window credits (--start only): a held-through row whose ex-date
    return is at or before the base close has its term outside the window,
    but its pay-date recredit (+w*y on live) can land inside it with no model
    counterpart, so the gap reads HIGH. Not modeled; flagged instead
    (pre_window_credit_rows, the bound pre_window_credit_bias_annualized_max
    and annualized_gap_pre_window_credits_offset; show() prints a !! line).
    HARV/KMLM from 2026-08-01: PULS 07-31 (credit 08-04), +2.0 / +0.5 %/yr.
    SLEEVE (Op2) has none.

--start YYYY-MM-DD (every target; default = full live window, bit-for-bit):
  live and the backtest are still fetched over the FULL live window, so the
  model path, w(t-1) and hold continuity across the start are exactly what
  the full-window read sees (a backtest refetched from start would be a
  different path: fresh buy-in from cash, no pre-start holding). The window
  BASE is the last common close BEFORE start, so the first counted return
  is the one dated on the first trading day >= start. Op2 (--start
  2026-08-01): base 07-31, first return 08-03. That return is earned on the
  07-31 close holdings, which are already the edited strategy (fills: BOXX
  bought 07-31 15:53 to 0.75 of the sleeve = the model's BOXX 0.75 / LABD
  0.25; LABD -> BOXX on 08-03 15:53 = the model's move), so it belongs in
  the read; its -9.3 bps is mostly LABD fill timing (~-12 bps: sold 9.245
  at 15:53 vs the 9.29 close, w 0.25; ~+2.7 bps unexplained) — the shortfall
  Op2 measures.
  Every statistic (gap, corr, beta, vol-ratio, live maxDD, cumulative
  returns), the ledger and ex_dates are computed from the base close on.
  window = [base, end]; window_first_return_date; window_start_requested
  echoes the flag; n_trading_days = trading days on/after start (Op2's
  ">= 120 trading days": 08-03 = day 1, 2027-01-22 = day 120) = n_days.
  Without a common date before start the first date >= start is the base,
  as in the full-window read (n_days = n_trading_days - 1). distribution_data
  completeness is still judged over every ticker the model held in the full
  fetched window (conservative). A non-ISO start raises (ValueError in
  analyze_series, an error exit in the CLI).

HONEST FAILURE: if Yahoo cannot be fetched for a ticker the model held, or a
model weight is keyed on a date that is not on the backtest calendar (the term
could not be applied), the result carries distribution_data = "INCOMPLETE"
plus the ticker/date list and show() says the primary numbers are not
distribution-adjusted. monitor.py treats INCOMPLETE as "diagnostic
unavailable". Never a silent fall-back to the old number.

Read-only. Usage:
  divergence.py <symphony-id> [--account UUID] [--name divergence-<x>]
                [--start YYYY-MM-DD]
  divergence.py --all [--start YYYY-MM-DD]   # every invested symphony
  divergence.py nNdBk7hc5NiBzeRvbI5T --start 2026-08-01   # POLICY Op2
"""

import argparse
import datetime as _dt
import json as _json
import statistics
import urllib.request

import composerlib as cl

CASH_TICKER = "$USD"           # Composer's cash pseudo-ticker (never a payer)
# Pay lag (TRADING days, ex-date -> pay-date credit) per fund, as OBSERVED on
# that ticker's OWN credit in the add.-38 lens-3 cash trail (account-cash
# residual = account value minus the sum of symphonies, reconciled with the
# fills; 2025-12..2026-10). NOT issuer documentation, and NO family
# inheritance: {ticker: (lag_td, n_own_events_observed)}, n >= 1 always (a
# merge-blocking test pins this and finds each event below in the fixtures).
# A ticker absent here is never guessed (unknown-lag path, see AMBIGUOUS).
PAY_LAG = {
    "ZVOL": (1, 1),  # ex 2026-08-19 -> account cash +1,969.44 on 08-20 (ex+1)
    "PULS": (2, 3),  # 3 live-held events; IDENTIFIED (gate standard: the
                     # unique +term day within 3 bps) only 08-31 -> 09-02
                     # in-symphony on HARV (+34.8 vs 35.6 bps) and KMLM
                     # (+8.6 vs 8.9), ex+2. 07-31 is consistent with ex+2 but
                     # not identified (HARV +42.5 vs 34.4); 09-30 is noisy
                     # (HARV ex+1 +60.1; KMLM ex+2 the wrong sign)
    "BIL":  (3, 2),  # 08-03 -> 08-06 account cash +230.77; 09-01 -> 09-04
                     # in-symphony +30.5 bps on HG (fills: pay-date 15:53
                     # reinvestment buy $227.33 vs credit $227.61)
    "TQQQ": (4, 1),  # 09-23 -> 09-29 in-symphony recredit on HG (ex+4)
    "SSO":  (4, 1),  # 2025-12-24 -> 2025-12-31 account cash +2.00: live held
                     # 17.393 sh at the 12-24 open (bought 12-23 15:53, sold
                     # 12-24 12:52), 17.393 x $0.116 = $2.02; ex+4 trading days
                     # across Christmas (12-26, 12-29, 12-30, 12-31)
    "LABD": (5, 1),  # 09-22 -> 09-29 in-symphony +$184.18 vs $184.87 (SLEEVE)
    "TMV":  (5, 1),  # 09-22 -> 09-29 account cash +97.10 vs $96.97
    # NOT here (unknown-lag path):
    #  SOXL — 09-22 held live, credit not identified: its 2.6 bps term is
    #    inside the 3-bps match tolerance of quiet days (KMLM ex+2 and ex+3
    #    both 'match'; ex+4 misses by 0.03 bps), and the candidate days ex+1
    #    (+6.8 bps) and ex+5 = 09-29 (+7.5 bps, unexplained) are noisy. The
    #    model's SOXL -> TECL swap was at the 09-29 CLOSE, so it earns the
    #    09-30 return, not 09-29's.
    #  TNA — 2026-06-23 held live (bought 3,068.76 sh 06-18, sold 06-23
    #    15:52; entitlement ~$270), credit not identified: ex+5..ex+8 carry
    #    ~$50k of account flows (largest residual jump +51,696.77 on ex+8).
    #    Start here if TNA's lag is ever added.
    #  QLD, UDOW, TECL — never held live into an ex-date (an issuer-family
    #    lag is a guess). TLT, SQQQ and any new holding — never observed.
}
MAX_PAY_LAG = max(lag for lag, _ in PAY_LAG.values())   # 5: longest observed
_YAHOO_CACHE = {}            # ticker -> chart dict; --all must not refetch
_YAHOO_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{t}"
                "?period1=1680000000&period2=4102444800&interval=1d&events=div")


# --------------------------------------------------------------------------
# I/O: Composer live + backtest + Yahoo, then hand off to the pure math
# --------------------------------------------------------------------------

def analyze(acct, sym_id, sym_name, detail=False, start=None):
    """start ('YYYY-MM-DD' or None): restrict the COMPARISON window to the
    trading days >= start, read from the last close before start (see
    analyze_series). Live and the backtest are still fetched over the full
    live window and sliced afterwards — never a backtest refetched
    from start, which would be a different model path (fresh buy-in from
    cash, no pre-start holding for w(t-1) on the first window day)."""
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
                          detail=detail, start=start)


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
    symphony is cheap and may succeed).

    No price-only fall-back: a response without the adjclose series, or a bar
    with a close but no adjclose (or vice versa), returns None -> the caller
    flags INCOMPLETE. Substituting close would make adj_ret == px_ret on every
    ex-date and silently re-create the add.-36 false alarm (panel C3).
    The success path is gated by T16 (wire-format round trip + mutants)."""
    if ticker in _YAHOO_CACHE:
        return _YAHOO_CACHE[ticker]
    try:
        rq = urllib.request.Request(_YAHOO_CHART.format(t=ticker.replace(".", "-")),
                                    headers={"user-agent": "Mozilla/5.0"})
        res = _json.load(urllib.request.urlopen(rq, timeout=30))["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        ts_all, close = res["timestamp"], q["close"]
        adj = ((res["indicators"].get("adjclose") or [{}])[0] or {}).get("adjclose")
        if not adj or len(adj) != len(ts_all) or len(close) != len(ts_all):
            return None                    # no adjclose series: never price-only
        chart = {"dates": [], "close": [], "adjclose": [], "divs": []}
        for i, ts in enumerate(ts_all):
            if close[i] is None and adj[i] is None:
                continue
            if close[i] is None or adj[i] is None:
                return None                # half a bar: refuse, don't patch
            chart["dates"].append(_dt.datetime.fromtimestamp(
                int(ts), tz=_dt.timezone.utc).date().isoformat())
            chart["close"].append(float(close[i]))
            chart["adjclose"].append(float(adj[i]))
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


def classify_hold(ticker, wt, fwd_dates, pay_lag=None):
    """HELD_THROUGH / LEAKED / AMBIGUOUS for one ledger row.

    wt        : {ISO date: weight} for the payer (holdings at the close of d)
    fwd_dates : model days from the ex-date's model day onward, clipped at
                the window end (the caller passes up to MAX_PAY_LAG + 1)
    pay_lag   : {ticker: (lag_td, n_events)}; None -> PAY_LAG

    Returns (treatment, held_days_checked, held_days_required, credit_pending,
    held_run, days_in_window_from_ex) where held_run = consecutive held model
    days from the ex-date within the checked span and days_in_window_from_ex
    = model days from ex inclusive inside the window (capped at L + 1).

    Label. Known lag L: HELD_THROUGH iff weights[ex..ex+L-1] all > 0 (the
    credit lands at the open of model day ex+L, before that day's ~15:50
    rebalance). Unknown lag (L := MAX_PAY_LAG for the checks): LEAKED if
    weights[ex] == 0, HELD_THROUGH if held ex..ex+MAX_PAY_LAG-1, else
    AMBIGUOUS (never a guessed lag). A span clipped by the window end with no
    exit seen is provisionally HELD_THROUGH (known lag) / AMBIGUOUS (unknown).

    credit_pending. The CREDIT lands on model day ex+L, so a row with no
    exit inside the checked span is pending while the window ends before
    ex+L, i.e. while fewer than L + 1 model days from ex inclusive are in the
    window; the primary gap still carries live's -w*y dip with no recredit.
    A row that shows an exit inside the checked span is never pending: a
    LEAKED row's income left the symphony, and an AMBIGUOUS row's
    held-through reading (true lag <= the observed hold) puts the credit on
    or before the exit day, which is inside the window."""
    table = PAY_LAG if pay_lag is None else pay_lag
    known = ticker in table
    need = table[ticker][0] if known else MAX_PAY_LAG
    span = fwd_dates[:need]
    held = [(wt.get(d) or 0.0) > 1e-9 for d in span]
    run = next((k for k, h in enumerate(held) if not h), len(held))
    exited = run < len(span)
    if not exited and len(span) == need:
        treatment = "HELD_THROUGH"
    elif run == 0:
        treatment = "LEAKED"                               # exited at the ex-date close
    elif known:
        treatment = "LEAKED" if exited else "HELD_THROUGH"  # clipped: provisional
    else:
        treatment = "AMBIGUOUS"                            # label depends on the unknown lag
    avail = min(len(fwd_dates), need + 1)
    pending = not exited and avail < need + 1              # credit day ex+L not in window
    return treatment, len(span), need, pending, run, avail


def price_only_model_returns(model_dates, model_vals, weights, dists, live_raw=None,
                             pay_lag=None):
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
    Classification: classify_hold() against the per-fund pay lag (pay_lag,
    default PAY_LAG; the window end is the model calendar's last day —
    held_days_checked of held_days_required, credit_pending while the credit
    day ex+L is not yet in the window). AMBIGUOUS rows are kept in the model
    (strict) and carry both alternatives' bps.
    live_raw ({date: live $ value}) only feeds expected_income_usd."""
    table = PAY_LAG if pay_lag is None else pay_lag
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
            treatment, checked, need, pending, run, avail = classify_hold(
                t, wt, model_dates[i:i + MAX_PAY_LAG + 1], table)
            lag = table.get(t)
            out = {
                "date": ex, "applied_on": model_dates[i], "ticker": t,
                "amount": row["amount"], "prev_close": row["prev_close"],
                "yield": y, "adj_ret": row["adj_ret"],
                "weight": w_prev, "weight_date": model_dates[i - 1],
                "term_bps": term * 1e4,
                "treatment": treatment,
                "pay_lag_bd": lag[0] if lag else None,
                "pay_lag_events_observed": lag[1] if lag else 0,
                "held_days_from_ex": run,
                "held_days_checked": checked,
                "held_days_required": need,
                "days_in_window_from_ex": avail,
                "credit_pending": pending,
                # removed from the PRIMARY model: leaked rows only (AMBIGUOUS
                # is kept — the strict treatment)
                "subtracted_bps": term * 1e4 if treatment == "LEAKED" else 0.0,
                # MODEL entitlement: shares x D = w x $value / P_prev x D.
                # Equals live's only where live matched the model that morning.
                "expected_income_usd": (w_prev * prev_val * y
                                        if prev_val is not None else None),
            }
            if treatment == "AMBIGUOUS":
                out["strict_subtracted_bps"] = 0.0             # kept (primary)
                out["lenient_subtracted_bps"] = term * 1e4     # if it leaked
            ledger.append(out)
    for i, term in terms.items():
        ret_px[i] = ret_tr[i] - term
    ledger.sort(key=lambda r: (r["date"], r["ticker"]))
    return ret_tr, ret_px, ledger


def leak_adjusted_returns(ret_tr, model_dates, ledger, strip=("LEAKED",)):
    """Model daily returns with ONLY the rows whose treatment is in `strip`
    removed: the PRIMARY model by default (leaked only; AMBIGUOUS kept =
    strict); strip=("LEAKED", "AMBIGUOUS") gives the lenient alternative.
    Days without a stripped row keep the same float object."""
    idx = {d: i for i, d in enumerate(model_dates)}
    terms = {}
    for r in ledger:
        if r["treatment"] in strip:
            i = idx[r["applied_on"]]
            terms[i] = terms.get(i, 0.0) + r["term_bps"] / 1e4
    out = list(ret_tr)
    for i, term in terms.items():
        out[i] = ret_tr[i] - term
    return out


def pre_window_credit_rows(ledger, model_dates, common, pay_lag=None):
    """Ledger rows (full-window ledger) whose ex-date return is NOT in the
    window (applied_on <= the base close common[0]) but whose pay-date
    credit can land inside it (common[0] < day <= common[-1]): known lag L ->
    model day ex+L; unknown lag -> any of ex+1..ex+MAX_PAY_LAG (never a
    guessed day). LEAKED rows are excluded: their income left the symphony.
    The live curve shows the +w*y recredit in the window; the model side has
    no counterpart, so the gap reads high by up to term_bps."""
    table = PAY_LAG if pay_lag is None else pay_lag
    idx = {d: i for i, d in enumerate(model_dates)}
    out = []
    for r in ledger:
        if r["treatment"] == "LEAKED" or r["applied_on"] > common[0]:
            continue
        i = idx[r["applied_on"]]
        lag = table.get(r["ticker"])
        steps = [lag[0]] if lag else list(range(1, MAX_PAY_LAG + 1))
        days = [model_dates[i + k] for k in steps if i + k < len(model_dates)
                and common[0] < model_dates[i + k] <= common[-1]]
        if days:
            out.append({"date": r["date"], "ticker": r["ticker"],
                        "treatment": r["treatment"],
                        "term_bps": round(r["term_bps"], 6),
                        "pay_lag_bd": lag[0] if lag else None,
                        "credit_day": days[0] if lag else None,
                        "credit_days_possible": days})
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
                   live_raw=None, symphony="", name="", detail=False, pay_lag=None,
                   start=None):
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
    detail  : add a per-day table (tests / chart work)
    pay_lag : {ticker: (lag_td, n_events)} override; None -> PAY_LAG.
    start   : 'YYYY-MM-DD' or None (anything else raises ValueError). The
              inputs stay the FULL live window (model path, w(t-1) and hold
              continuity exactly as the full-window read sees them). The
              window's BASE is the last common close BEFORE start, so the
              first counted daily return is the one dated on the first
              trading day >= start (with --start 2026-08-01: base 07-31, first
              return 08-03 — the edit-day close holdings are already the new
              strategy). Every statistic, the ledger and ex_dates are computed
              from the base close on. No common date before start -> the
              first date >= start is the base (= the full-window rule).
              None = the full window, bit-for-bit."""
    if start is not None:
        try:
            ok = _dt.date.fromisoformat(start).isoformat() == start
        except (TypeError, ValueError):
            ok = False
        if not ok:
            raise ValueError(f"start {start!r} is not YYYY-MM-DD")
    live = dict(zip(live_dates, live_vals))
    if len(live) < 5:
        return {"symphony": symphony, "name": name,
                "error": f"only {len(live)} live days — too new to compare"}
    model = dict(zip(model_dates, model_vals))
    common = sorted(set(live) & set(model))
    in_window = len(common)                  # trading days on/after start
    if start is not None:
        pre = [d for d in common if d < start]
        common = pre[-1:] + [d for d in common if d >= start]   # base + window
        in_window = len(common) - len(pre[-1:])
    if len(common) < 5:
        return {"symphony": symphony, "name": name,
                "error": (f"only {len(common)} overlapping days"
                          + (f" from the last close before {start}"
                             if start is not None else ""))}

    raw_by_date = dict(zip(live_dates, live_raw)) if live_raw else None
    held = _held_tickers(weights)
    missing = sorted(held - set(dists or {}))
    off_cal = weight_dates_off_calendar(weights, model_dates)
    ret_tr, ret_px, ledger = price_only_model_returns(
        model_dates, model_vals, weights, dists or {}, live_raw=raw_by_date,
        pay_lag=pay_lag)
    pre_credit = pre_window_credit_rows(ledger, model_dates, common, pay_lag)
    ledger = [r for r in ledger if common[0] < r["applied_on"] <= common[-1]]
    ret_adj = leak_adjusted_returns(ret_tr, model_dates, ledger)
    ret_len = leak_adjusted_returns(ret_tr, model_dates, ledger,
                                    strip=("LEAKED", "AMBIGUOUS"))
    model_adj = dict(zip(model_dates, _rebuild(model_vals[0], ret_adj)))
    model_len = dict(zip(model_dates, _rebuild(model_vals[0], ret_len)))
    model_px = dict(zip(model_dates, _rebuild(model_vals[0], ret_px)))

    lv = [live[d] for d in common]
    lr = [lv[i] / lv[i - 1] - 1.0 for i in range(1, len(lv))]
    mr_adj = _on_calendar(model_dates, ret_adj, common)   # leaked terms removed
    mr_px = _on_calendar(model_dates, ret_px, common)     # every term removed
    mr_tr = _on_calendar(model_dates, ret_tr, common)     # total return
    mr_len = _on_calendar(model_dates, ret_len, common)   # + AMBIGUOUS removed
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
    model_cum_len = model_len[common[-1]] / model_len[common[0]] - 1.0
    prim = _pair_stats(lr, mr_adj, lr_tr, mr_tr)
    allpx = _pair_stats(lr, mr_px, lr_tr, mr_tr)
    sec = _pair_stats(lr, mr_tr)
    lenient = _pair_stats(lr, mr_len, lr_tr, mr_tr)

    ex_dates = sorted((ex, t, float(v["amount"]))
                      for t in held if t in (dists or {})
                      for ex, v in (dists[t] or {}).items()
                      if common[0] <= ex <= common[-1])
    inc = [r["expected_income_usd"] for r in ledger]
    leaked = [r for r in ledger if r["treatment"] == "LEAKED"]
    held_rows = [r for r in ledger if r["treatment"] == "HELD_THROUGH"]
    amb = [r for r in ledger if r["treatment"] == "AMBIGUOUS"]
    n_days = len(lr)
    r = {
        "symphony": symphony, "name": name,
        # window = [base close, last close]; every return and cumulative is
        # read from the base. requested --start (None = full live window);
        # n_trading_days = live trading days on/after start, what Op2's
        # ">= 120 trading days" reads (start=None: every live day, the first
        # being the base, so n_days = n_trading_days - 1; with a pre-start
        # base, n_days = n_trading_days)
        "window": [common[0], common[-1]],
        "window_start_requested": start,
        "window_first_return_date": common[1],
        "n_trading_days": in_window, "n_days": n_days,
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
        # ---- AMBIGUOUS rows (payer's pay lag not in PAY_LAG and the model's
        #      hold across the ex-date is too short to decide): the primary
        #      keeps them (strict); these keys give the lenient alternative.
        #      Equal to the primary when there are none. ----
        "ambiguous_rows": [
            {"date": x["date"], "ticker": x["ticker"],
             "term_bps": round(x["term_bps"], 6),
             "held_days_from_ex": x["held_days_from_ex"],
             "credit_pending": x["credit_pending"],
             "missing_input": (f"pay lag for {x['ticker']} not observed "
                               f"(not in PAY_LAG)")} for x in amb],
        "cumulative_gap_ambiguous_lenient": round(live_cum - model_cum_len, 4),
        "annualized_gap_ambiguous_lenient": lenient["annualized_gap"],
        "mean_daily_gap_bps_ambiguous_lenient": lenient["mean_daily_gap_bps"],
        # ---- PRE-WINDOW CREDITS (--start only): a held-through / ambiguous
        #      row whose ex-date return is at or before the base close (term
        #      not in the window) but whose pay-date credit can land inside
        #      it. Live's +w*y recredit is then in the window with nothing
        #      on the model side: the primary gap is biased UP (live's
        #      favour) by up to the listed bps. Not modeled; the offset key
        #      is the gap with that bound removed (strict). [] without
        #      --start on these inputs. ----
        "pre_window_credit_rows": pre_credit,
        "pre_window_credit_bias_annualized_max": round(
            sum(x["term_bps"] for x in pre_credit) / 1e4 / n_days * 252, 4),
        "annualized_gap_pre_window_credits_offset": round(
            prim["annualized_gap"]
            - sum(x["term_bps"] for x in pre_credit) / 1e4 / n_days * 252, 4),
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
            "n_ambiguous": len(amb),
            "term_bps": round(sum(x["term_bps"] for x in ledger), 2),
            "subtracted_bps": round(sum(x["subtracted_bps"] for x in ledger), 2),
            "held_through_bps": round(sum(x["term_bps"] for x in held_rows), 2),
            "ambiguous_bps": round(sum(x["term_bps"] for x in amb), 2),
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
    if r.get("window_start_requested"):
        print(f"      window {r['window'][0]} (base close) .. {r['window'][1]}: "
              f"{r['n_trading_days']} trading days on/after "
              f"{r['window_start_requested']}, first counted return "
              f"{r['window_first_return_date']}, {r['n_days']} daily returns  "
              f"[--start {r['window_start_requested']}: base = last close before "
              f"start; model path and holds read over the full live window]")
    else:
        print(f"      window {r['window'][0]} .. {r['window'][1]} "
              f"({r['n_trading_days']} trading days, {r['n_days']} daily returns)")
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
              + (f"; {tot['n_ambiguous']} AMBIGUOUS -> {tot['ambiguous_bps']:+.1f} bps "
                 f"kept (strict)" if tot.get("n_ambiguous") else "")
              + (f"; ~${tot['expected_income_usd']:,.0f} model entitlement"
                 if tot["expected_income_usd"] is not None else "") + "):")
        pending = 0
        for x in r["distribution_ledger"]:
            inc = (f"  ~${x['expected_income_usd']:,.0f}"
                   if x["expected_income_usd"] is not None else "")
            lag = (f"L={x['pay_lag_bd']}" if x.get("pay_lag_bd") is not None
                   else "L=?")
            prov = ""
            if x.get("credit_pending"):
                prov = (f"  [credit pending: window ends ex+"
                        f"{x['days_in_window_from_ex'] - 1}, credit lands ex+"
                        f"{x['held_days_required']}"
                        + ("" if x.get("pay_lag_bd") is not None else " at the latest")
                        + "; gap carries -w*y, label provisional]")
                pending += 1
            print(f"        {x['date']} {x['ticker']:5s} ${x['amount']:.4f}/sh  "
                  f"yield {x['yield']*1e4:6.1f} bps  w(t-1) {x['weight']:.3f}  "
                  f"term {x['term_bps']:6.1f} bps  {x['treatment']:12s} {lag}"
                  f"{inc}{prov}")
        print(f"      note: LEAKED = model exited before the payer's pay-date credit. "
              f"Where live held the payer the cash was observed landing in "
              f"ACCOUNT unallocated cash (4/4 identified cases; TNA 06-23 masked "
              f"by account flows); where live did not "
              f"hold it (model-only rows: KMLM TLT 09-01, pre-edit HG TNA 12-23 / "
              f"BIL 02-02, 03-02) the strip reads in live's favour. "
              f"Classified from MODEL continuity against the pay lag L OBSERVED "
              f"on the fund's own credit (PAY_LAG: ZVOL 1, PULS 2, BIL 3, TQQQ 4, "
              f"SSO 4, LABD 5, TMV 5 trading days): HELD_THROUGH iff held "
              f"ex..ex+L-1. Any other payer (no observed lag, never guessed): "
              f"LEAKED if sold at the ex-date close, HELD_THROUGH if held "
              f"ex..ex+{MAX_PAY_LAG - 1}, else AMBIGUOUS (kept = strict).")
        for a in r.get("ambiguous_rows") or []:
            print(f"      !! AMBIGUOUS: {a['ticker']} {a['date']} — pay lag for "
                  f"{a['ticker']} is MISSING (not in PAY_LAG; no identified own "
                  f"credit) and the "
                  f"model held it {a['held_days_from_ex']} day(s) from the ex-date, so "
                  f"the label depends on it. Primary keeps its {a['term_bps']:.1f} bps "
                  f"(strict: ann {r['annualized_gap']:+.1%}/yr, cum "
                  f"{r['cumulative_gap']:+.2%}); if it leaked (lenient) the gap reads "
                  f"ann {r['annualized_gap_ambiguous_lenient']:+.1%}/yr, cum "
                  f"{r['cumulative_gap_ambiguous_lenient']:+.2%}. Check the "
                  f"account-cash residual (account value minus the sum of symphonies, "
                  f"ex+1..ex+8) before acting on a gate, then add the observed lag "
                  f"to PAY_LAG.")
        if pending:
            print(f"      !! {pending} ledger row(s) credit pending (the window ends "
                  f"before model day ex+L, the pay-date credit): the primary gap "
                  f"carries live's -w*y dip with no recredit yet and the label is "
                  f"provisional; re-read once ex+L is inside the window "
                  f"(days_in_window_from_ex = L+1) before acting on a gate.")
    skipped = [f"{t} {d}" for d, t, _ in r.get("ex_dates") or []
               if d > r["window"][0]
               and not any(x["date"] == d and x["ticker"] == t
                           for x in r["distribution_ledger"])]
    if skipped:
        print(f"      ex-dates the model did NOT hold into (nothing to remove): "
              + ", ".join(skipped))
    on_base = [f"{t} {d}" for d, t, _ in r.get("ex_dates") or [] if d <= r["window"][0]]
    if on_base:
        print(f"      ex-dates on the base close (their return is not in the window): "
              + ", ".join(on_base))
    pre = r.get("pre_window_credit_rows") or []
    if pre:
        rows = "; ".join(
            f"{x['ticker']} {x['date']} {x['treatment']} {x['term_bps']:.1f} bps, credit "
            + (f"{x['credit_day']} (L={x['pay_lag_bd']})" if x["pay_lag_bd"] is not None
               else f"one of {', '.join(x['credit_days_possible'])} (L unknown)")
            for x in pre)
        print(f"      !! PRE-WINDOW CREDIT: {rows} — the ex-date return is before the "
              f"window but the pay-date credit lands inside it; live's +w*y recredit "
              f"has no model counterpart, so the gap reads HIGH by up to "
              f"{r['pre_window_credit_bias_annualized_max']:+.1%}/yr (offset: ann "
              f"{r['annualized_gap_pre_window_credits_offset']:+.1%}/yr). Not modeled; "
              f"read a gate on the offset number or move --start.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("symphony_id", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--account")
    p.add_argument("--name", default="divergence")
    p.add_argument("--start", metavar="YYYY-MM-DD", default=None,
                   help="restrict the comparison window to trading days >= start, "
                        "read from the last close before start (every target); "
                        "live and backtest are still fetched over the full live "
                        "window")
    a = p.parse_args()
    if not a.all and not a.symphony_id:
        raise SystemExit("error: pass a symphony id or --all")
    if a.start is not None:
        try:
            a.start = _dt.date.fromisoformat(a.start).isoformat()
        except ValueError:
            raise SystemExit(f"error: --start {a.start!r} is not YYYY-MM-DD")

    acct = a.account or cl.default_account()
    meta = {s["id"]: s["name"] for s in
            cl.get(f"/portfolio/accounts/{acct}/symphony-stats-meta")["symphonies"]}
    targets = list(meta) if a.all else [a.symphony_id]

    results = []
    print("live vs backtest divergence (deposit-adjusted; distribution-aware, add. 38)"
          + (f" — comparison window from {a.start}" if a.start else "") + "\n")
    for sid in targets:
        if sid not in meta:
            raise SystemExit(f"error: {sid} is not an invested symphony in this account")
        r = analyze(acct, sid, meta[sid], start=a.start)
        results.append(r)
        show(r)

    cl.write_json(f"composer/results/{a.name}.json", {"results": results})


if __name__ == "__main__":
    main()
