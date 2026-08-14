#!/usr/bin/env python3
"""Offline data layer + backtest engine for the SOXL-dispersion study.

Reads ONLY fixtures/market_data.json. No network calls anywhere below.

Engine design notes that matter for honesty
-------------------------------------------
1. SHARE-LEVEL ACCOUNTING. Positions are held as share counts between
   rebalances, so exposures DRIFT with prices. This is not cosmetic: a short
   leveraged-ETF position grows in notional as the ETF rallies, which is the
   whole negative-convexity story. A weight-based engine that silently
   re-marks to constant weights every day would hide the strategy's dominant
   risk and quietly assume free daily rebalancing.

2. FINANCING IS EXPLICIT. Equity, long market value, short proceeds and the
   resulting cash balance are tracked separately. Credit balances earn
   (benchmark - spread); debit balances pay (benchmark + spread); the short
   pays a borrow fee on its market value. IBKR's actual tiered structure.

3. TOTAL-RETURN SERIES ON BOTH LEGS. Dividend-adjusted closes mean the long
   leg receives dividends and the short leg PAYS the ETF's distributions
   automatically. No separate (and usually forgotten) dividend-liability term.

4. NO LOOKAHEAD IN SELECTION. Rebalance date t ranks names by market cap
   observed at t, from a candidate set that includes companies that later
   died. Names that delist mid-period are liquidated at their last observed
   price and the proceeds redistributed at the next rebalance.
"""
import bisect
import json
import math
import os

import numpy as np

from universe import (CAP_REST, CAP_TOP5, DEAD_TICKERS, INDEX_SIZE,
                      INSTRUMENTS, modified_cap_weights)

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
TRADING_DAYS = 252


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
class Data:
    """Aligned panel of prices, market caps and rates."""

    def __init__(self, path=None):
        with open(path or os.path.join(FIX, "market_data.json")) as f:
            raw = json.load(f)
        self.meta = raw["meta"]
        self.raw_prices = raw["prices"]
        self.ohlc = raw["ohlc"]
        self.mcaps = raw["mcaps"]
        self.treasury = raw["treasury_3m"]
        self.live_holdings = raw["soxx_holdings_live"]
        self.vix_raw = raw.get("vix", {})

        # master calendar = SOXX trading days (the index we care about)
        self.dates = sorted(raw["prices"]["SOXX"])
        self.di = {d: i for i, d in enumerate(self.dates)}
        n = len(self.dates)

        # price matrix, NaN where a name is not trading
        self.tickers = sorted(raw["prices"])
        self.px = {}
        for t in self.tickers:
            arr = np.full(n, np.nan)
            for d, p in raw["prices"][t].items():
                i = self.di.get(d)
                if i is not None and p:
                    arr[i] = p
            self.px[t] = arr

        # forward-filled 3m T-bill (annual %, e.g. 5.31)
        rate = np.full(n, np.nan)
        for d, v in self.treasury.items():
            i = self.di.get(d)
            if i is not None:
                rate[i] = v
        self.rf = _ffill(rate) / 100.0
        self.rf[np.isnan(self.rf)] = 0.0

        # VIX and VIX3M aligned to the master calendar (term-structure gate)
        self.vix = {}
        for sym, series in self.vix_raw.items():
            arr = np.full(n, np.nan)
            for dd, v in series.items():
                i = self.di.get(dd)
                if i is not None and v:
                    arr[i] = v
            self.vix[sym] = _ffill(arr)

        # month-end market caps, as {YYYY-MM: {ticker: cap}}
        self.mcap_by_month = {}
        for t, series in raw["mcaps"].items():
            for d, c in series.items():
                self.mcap_by_month.setdefault(d[:7], {})[t] = c

    # -- returns ----------------------------------------------------------
    def ret(self, ticker):
        """Daily simple total return; NaN where undefined."""
        p = self.px[ticker]
        r = np.full(len(p), np.nan)
        r[1:] = p[1:] / p[:-1] - 1.0
        return r

    def slice_idx(self, start, end):
        lo = bisect.bisect_left(self.dates, start)
        hi = bisect.bisect_right(self.dates, end)
        return lo, hi


def _ffill(a):
    out = a.copy()
    last = np.nan
    for i in range(len(out)):
        if not np.isnan(out[i]):
            last = out[i]
        else:
            out[i] = last
    return out


# --------------------------------------------------------------------------
# point-in-time universe reconstruction
# --------------------------------------------------------------------------
def month_ends(dates):
    """Last trading day of each month in the calendar."""
    out, cur = [], None
    for i, d in enumerate(dates):
        m = d[:7]
        if cur is not None and m != cur[0]:
            out.append(cur[1])
        cur = (m, i)
    if cur:
        out.append(cur[1])
    return out


def pit_members(data, idx, index_size=INDEX_SIZE, min_price_history=60):
    """Market caps at calendar index `idx`, for names tradeable AT that date.

    Tradeable = has a price on/near `idx` and at least `min_price_history`
    prior observations (avoids ranking a name on its IPO week). Uses the
    market-cap snapshot from the month of `idx` only -> no lookahead.
    """
    d = data.dates[idx]
    caps = data.mcap_by_month.get(d[:7], {})
    live = {}
    for t, c in caps.items():
        if t in INSTRUMENTS or c is None or c <= 0:
            continue
        p = data.px.get(t)
        if p is None or np.isnan(p[idx]):
            continue
        hist = np.count_nonzero(~np.isnan(p[max(0, idx - 400):idx]))
        if hist < min_price_history:
            continue
        live[t] = c
    return dict(sorted(live.items(), key=lambda kv: -kv[1])[:index_size])


def build_index_proxy(data, index_size=INDEX_SIZE):
    """Reconstructed PIT modified-cap semiconductor index (SOXX proxy).

    Monthly reconstitution, daily drift between reconstitutions. Returns
    (dates_idx, daily_returns, members_by_rebal) for validation against SOXX.
    """
    mes = month_ends(data.dates)
    n = len(data.dates)
    rets = np.full(n, np.nan)
    members = {}
    for k, me in enumerate(mes[:-1]):
        caps = pit_members(data, me, index_size)
        if len(caps) < 10:
            continue
        w = modified_cap_weights(caps, index_size)
        members[data.dates[me]] = w
        nxt = mes[k + 1]
        # hold shares fixed -> weights drift with price
        shares = {t: w[t] / data.px[t][me] for t in w}
        prev_val = sum(shares[t] * data.px[t][me] for t in w)
        for i in range(me + 1, nxt + 1):
            val = 0.0
            for t in w:
                p = data.px[t][i]
                if np.isnan(p):                      # delisted mid-month
                    p = _last_valid(data.px[t], i)
                val += shares[t] * p
            rets[i] = val / prev_val - 1.0
            prev_val = val
    return rets, members


def _last_valid(arr, i):
    j = i
    while j >= 0 and np.isnan(arr[j]):
        j -= 1
    return arr[j] if j >= 0 else np.nan


def build_basket(data, idx, n_names, scheme="cap", index_size=INDEX_SIZE,
                 mom_lookback=126):
    """Top-N selection from the PIT index membership at `idx`.

    scheme: 'cap' (pure cap-weighted within the top N), 'ew' (equal weight),
            'mom' (rank by trailing `mom_lookback`-day return, equal weight),
            'cap_iceclip' (cap-weighted then clipped by the index's own
            8%/4% caps, renormalized -- used to test whether the basket's
            alpha is stock selection or merely the absence of index caps).
    """
    caps = pit_members(data, idx, index_size)
    if not caps:
        return {}
    if scheme == "mom":
        scored = []
        for t in caps:
            p = data.px[t]
            j = idx - mom_lookback
            if j < 0 or np.isnan(p[j]) or np.isnan(p[idx]):
                continue
            scored.append((p[idx] / p[j] - 1.0, t))
        scored.sort(reverse=True)
        picks = [t for _, t in scored[:n_names]]
        return {t: 1.0 / len(picks) for t in picks} if picks else {}

    picks = list(caps)[:n_names]
    if scheme == "ew":
        return {t: 1.0 / len(picks) for t in picks}
    sub = {t: caps[t] for t in picks}
    if scheme == "cap_iceclip":
        # index-style caps expressed relative to the N-name sleeve: the index
        # caps at 8%/4% of the WHOLE index, so within a top-N sleeve the
        # equivalent clip is those caps scaled by the sleeve's index weight.
        full = modified_cap_weights(caps, index_size)
        sleeve = sum(full.get(t, 0.0) for t in picks)
        if sleeve <= 0:
            return {}
        return {t: full[t] / sleeve for t in picks if t in full}
    tot = sum(sub.values())
    return {t: c / tot for t, c in sub.items()}


# --------------------------------------------------------------------------
# cost model
# --------------------------------------------------------------------------
class Costs:
    """IBKR-shaped cost stack. All rates annualized decimals, all frictions bps.

    borrow_soxl / borrow_soxs are the study's dominant unknown: no vendor
    borrow history was available, so they are SWEPT, never assumed. See
    breakeven_borrow() and the sensitivity grids.
    """

    def __init__(self, commission_bps=0.5, slip_etf_bps=2.0,
                 slip_stock_bps=3.0, borrow_soxl=0.01, borrow_soxs=0.03,
                 credit_spread=0.005, debit_spread=0.015,
                 short_credit_haircut=0.0):
        self.commission_bps = commission_bps
        self.slip_etf_bps = slip_etf_bps
        self.slip_stock_bps = slip_stock_bps
        self.borrow_soxl = borrow_soxl
        self.borrow_soxs = borrow_soxs
        self.credit_spread = credit_spread
        self.debit_spread = debit_spread
        self.short_credit_haircut = short_credit_haircut

    def trade_cost(self, notional, is_etf):
        slip = self.slip_etf_bps if is_etf else self.slip_stock_bps
        return abs(notional) * (self.commission_bps + slip) / 1e4


ZERO_COSTS = Costs(commission_bps=0.0, slip_etf_bps=0.0, slip_stock_bps=0.0,
                   borrow_soxl=0.0, borrow_soxs=0.0,
                   credit_spread=0.0, debit_spread=0.0)

# Maintenance margin. Leveraged ETFs are the reason this matters: FINRA
# requires the standard maintenance requirement to be MULTIPLIED by the
# fund's leverage factor, so a short 3x ETF carries 3 x 30% = 90% of its
# market value under Reg-T. Portfolio Margin replaces this with a stress
# test; the PM numbers below are a conservative approximation of the
# usual +/-15% semis shock and are flagged as such in the report.
MARGIN_REGT = {"long_stock": 0.25, "short_stock": 0.30, "short_lev3": 0.90,
               "long_lev3": 0.75}
MARGIN_PM = {"long_stock": 0.15, "short_stock": 0.15, "short_lev3": 0.45,
             "long_lev3": 0.45}
LEV3 = {"SOXL", "SOXS"}


def margin_requirement(data, book, i, regime="PM"):
    """Maintenance margin required for the current book, as a $ amount."""
    m = MARGIN_PM if regime == "PM" else MARGIN_REGT
    req = 0.0
    for t, q in book.shares.items():
        if q == 0:
            continue
        v = abs(q * _px(data, t, i))
        lev = t in LEV3
        if q > 0:
            req += v * (m["long_lev3"] if lev else m["long_stock"])
        else:
            req += v * (m["short_lev3"] if lev else m["short_stock"])
    return req


# --------------------------------------------------------------------------
# backtest engine
# --------------------------------------------------------------------------
class Book:
    """Share-level long/short book with explicit cash and financing."""

    def __init__(self, equity=1.0):
        self.equity = equity
        self.cash = equity
        self.shares = {}          # ticker -> signed share count

    def market_value(self, data, i):
        long_mv = short_mv = 0.0
        for t, q in self.shares.items():
            if q == 0:
                continue
            p = data.px[t][i]
            if np.isnan(p):
                p = _last_valid(data.px[t], i)
            v = q * p
            if v > 0:
                long_mv += v
            else:
                short_mv += -v
        return long_mv, short_mv

    def nav(self, data, i):
        long_mv, short_mv = self.market_value(data, i)
        return self.cash + long_mv - short_mv


def run_backtest(data, start, end, target_fn, costs=None, rebalance="M",
                 drift_band=None, gate_fn=None, vol_target=None,
                 vol_lookback=60, max_leverage=3.0, label="",
                 margin_regime="PM", margin_call=True):
    """Daily engine.

    target_fn(data, i) -> {ticker: target_weight_of_equity}. Negative weights
        are shorts. Called only on rebalance dates.
    rebalance: 'D' | 'W' | 'M' | 'Q'
    drift_band: if set, additionally rebalance whenever any leg's weight
        drifts more than `drift_band` (absolute, e.g. 0.05) from target.
    gate_fn(data, i) -> float in [0,1]: scales the whole book (regime gate).
    vol_target: annualized vol target; book scaled by target/realized.
    margin_call: if True, a book whose maintenance requirement exceeds its
        equity is FORCIBLY rebalanced to target that day (and terminated if
        equity goes non-positive). Without this the engine happily runs a
        drifted short at 100x leverage on 5% equity and reports a Sharpe for
        it -- a path no broker would ever allow to exist.
    """
    costs = costs or Costs()
    lo, hi = data.slice_idx(start, end)
    lo = max(lo, 1)
    book = Book(1.0)
    navs, dates_out = [], []
    turnover_total = 0.0
    cost_ledger = {"commission_slippage": 0.0, "borrow": 0.0,
                   "financing": 0.0, "n_trades": 0}
    n_rebals = 0
    n_margin_calls = 0
    blown_up = False
    cur_target = {}
    trade_days = []
    margin_regt, margin_pm, gross_exp, net_exp = [], [], [], []

    mes = set(month_ends(data.dates))
    weekly = {i for i in range(len(data.dates))
              if i + 1 < len(data.dates)
              and data.dates[i + 1][:4] + _week(data.dates[i + 1])
              != data.dates[i][:4] + _week(data.dates[i])}
    quarterly = {i for i in mes if data.dates[i][5:7] in ("03", "06", "09", "12")}

    for i in range(lo, hi):
        # ---- 1. accrue financing/borrow on yesterday's positions ---------
        long_mv, short_mv = book.market_value(data, i - 1)
        rf = data.rf[i]
        # cash earns/pays; short proceeds sit in cash already
        if book.cash > 0:
            fin = book.cash * max(rf - costs.credit_spread, 0.0) / TRADING_DAYS
        else:
            fin = book.cash * (rf + costs.debit_spread) / TRADING_DAYS
        borrow = 0.0
        for t, q in book.shares.items():
            if q >= 0:
                continue
            p = _px(data, t, i - 1)
            rate = (costs.borrow_soxs if t == "SOXS" else costs.borrow_soxl)
            borrow += -q * p * rate / TRADING_DAYS
        book.cash += fin - borrow
        cost_ledger["financing"] += -fin
        cost_ledger["borrow"] += borrow

        # ---- 2. mark to market (prices move) -----------------------------
        nav = book.nav(data, i)
        if nav <= 0:                      # wiped out; stop honestly
            navs.append(0.0)
            dates_out.append(data.dates[i])
            gross_exp.append(np.nan)
            net_exp.append(np.nan)
            margin_regt.append(np.nan)
            margin_pm.append(np.nan)
            blown_up = True
            break

        # ---- 3. rebalance? ----------------------------------------------
        due = (rebalance == "D" or (rebalance == "M" and i in mes)
               or (rebalance == "W" and i in weekly)
               or (rebalance == "Q" and i in quarterly))
        # forced de-risk: maintenance requirement has eaten the equity
        if margin_call and not due:
            if margin_requirement(data, book, i, margin_regime) > nav:
                due = True
                n_margin_calls += 1
        if not due and drift_band and cur_target:
            for t, wt in cur_target.items():
                p = _px(data, t, i)
                actual = book.shares.get(t, 0.0) * p / nav
                if abs(actual - wt) > drift_band:
                    due = True
                    break
        if due:
            tgt = target_fn(data, i)
            if tgt:
                scale = 1.0
                if gate_fn is not None:
                    scale *= gate_fn(data, i)
                if vol_target is not None:
                    scale *= _vol_scale(data, i, tgt, vol_target, vol_lookback,
                                        max_leverage)
                tgt = {t: w * scale for t, w in tgt.items()}
                turnover_total += _apply(book, data, i, tgt, costs,
                                         cost_ledger)
                cur_target = tgt
                n_rebals += 1
                trade_days.append(i)

        nav_i = book.nav(data, i)
        navs.append(nav_i)
        dates_out.append(data.dates[i])
        lmv, smv = book.market_value(data, i)
        gross_exp.append((lmv + smv) / nav_i if nav_i > 0 else np.nan)
        net_exp.append((lmv - smv) / nav_i if nav_i > 0 else np.nan)
        margin_regt.append(margin_requirement(data, book, i, "RegT") / nav_i
                           if nav_i > 0 else np.nan)
        margin_pm.append(margin_requirement(data, book, i, "PM") / nav_i
                         if nav_i > 0 else np.nan)

    return {
        "label": label, "dates": dates_out,
        "nav": np.array(navs),
        "turnover": turnover_total, "n_rebals": n_rebals,
        "costs": cost_ledger, "trade_days": trade_days,
        "margin_regt": np.array(margin_regt), "margin_pm": np.array(margin_pm),
        "gross_exposure": np.array(gross_exp), "net_exposure": np.array(net_exp),
        "n_margin_calls": n_margin_calls, "blown_up": blown_up,
    }


def _week(d):
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    import datetime as _dt
    return str(_dt.date(y, m, day).isocalendar()[1])


def _px(data, t, i):
    p = data.px[t][i]
    return p if not np.isnan(p) else _last_valid(data.px[t], i)


def _vol_scale(data, i, tgt, vol_target, lookback, max_leverage):
    """Scale so the *proposed* book's trailing realized vol hits target."""
    r = np.zeros(lookback)
    for t, w in tgt.items():
        p = data.px[t]
        seg = p[i - lookback:i + 1]
        if np.isnan(seg).any():
            continue
        r += w * (seg[1:] / seg[:-1] - 1.0)
    sd = r.std(ddof=1) * math.sqrt(TRADING_DAYS)
    if sd <= 1e-9:
        return 1.0
    gross = sum(abs(w) for w in tgt.values())
    return min(vol_target / sd, max_leverage / max(gross, 1e-9))


def _apply(book, data, i, tgt, costs, ledger):
    """Trade the book to target weights of current NAV. Returns turnover $."""
    nav = book.nav(data, i)
    turnover = 0.0
    names = set(tgt) | {t for t, q in book.shares.items() if q != 0}
    for t in names:
        p = _px(data, t, i)
        if np.isnan(p) or p <= 0:
            continue
        want_q = tgt.get(t, 0.0) * nav / p
        have_q = book.shares.get(t, 0.0)
        dq = want_q - have_q
        if abs(dq * p) < 1e-9:
            continue
        notional = dq * p
        c = costs.trade_cost(notional, t in INSTRUMENTS)
        book.cash -= notional + c
        book.shares[t] = want_q
        turnover += abs(notional)
        if ledger is not None:
            ledger["commission_slippage"] += c
            ledger["n_trades"] += 1
    return turnover


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def metrics(nav, dates, bench_ret=None, rf=None):
    nav = np.asarray(nav, dtype=float)
    nav = nav[np.isfinite(nav)]
    if len(nav) < 30 or nav[0] <= 0:
        return {}
    r = nav[1:] / nav[:-1] - 1.0
    r = r[np.isfinite(r)]
    yrs = len(r) / TRADING_DAYS
    total = nav[-1] / nav[0]
    cagr = total ** (1 / yrs) - 1 if total > 0 and yrs > 0 else float("nan")
    vol = r.std(ddof=1) * math.sqrt(TRADING_DAYS)
    excess = r - (np.asarray(rf)[:len(r)] / TRADING_DAYS if rf is not None else 0.0)
    sharpe = (excess.mean() / r.std(ddof=1) * math.sqrt(TRADING_DAYS)
              if r.std(ddof=1) > 0 else float("nan"))
    downside = r[r < 0]
    sortino = (excess.mean() * TRADING_DAYS /
               (downside.std(ddof=1) * math.sqrt(TRADING_DAYS))
               if len(downside) > 2 and downside.std(ddof=1) > 0 else float("nan"))
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1.0
    mdd = dd.min()
    calmar = cagr / abs(mdd) if mdd < 0 else float("nan")
    out = {
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino,
        "MaxDD": mdd, "Calmar": calmar, "TotalReturn": total - 1,
        "WinRate": float((r > 0).mean()), "Years": yrs,
        "WorstDay": float(r.min()),
    }
    # monthly + rolling-12m stats
    mret = _to_monthly(nav, dates)
    if len(mret) > 12:
        out["WorstMonth"] = float(min(mret))
        roll = [np.prod([1 + x for x in mret[k:k + 12]]) - 1
                for k in range(len(mret) - 12)]
        out["WorstRoll12m"] = float(min(roll)) if roll else float("nan")
        out["BestRoll12m"] = float(max(roll)) if roll else float("nan")
    if bench_ret is not None:
        b = np.asarray(bench_ret)[:len(r)]
        ok = np.isfinite(b) & np.isfinite(r)
        if ok.sum() > 30 and b[ok].std() > 0:
            out["Beta"] = float(np.cov(r[ok], b[ok])[0, 1] / np.var(b[ok], ddof=1))
            out["Corr"] = float(np.corrcoef(r[ok], b[ok])[0, 1])
    return out


def _to_monthly(nav, dates):
    out, start_v, cur = [], nav[0], dates[0][:7]
    for k in range(1, len(nav)):
        if dates[k][:7] != cur:
            out.append(nav[k - 1] / start_v - 1.0)
            start_v = nav[k - 1]
            cur = dates[k][:7]
    return out


def rolling_beta(x, y, window=60):
    """Rolling OLS beta of x on y."""
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(window, n):
        a, b = x[i - window:i], y[i - window:i]
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() > window // 2 and b[ok].std() > 0:
            out[i] = np.cov(a[ok], b[ok])[0, 1] / np.var(b[ok], ddof=1)
    return out
