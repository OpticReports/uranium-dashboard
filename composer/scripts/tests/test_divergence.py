"""Merge-blocking gate tests for divergence.py (results.md addendum 38,
revised after the adversarial panel of 2026-10-05).

House rule: a gate that cannot fail is not a gate. Every gate here is paired
with a BROKEN-INPUT counterpart that must land on the other side of the
threshold. The broken variants are INPUT transforms only (ex-dates shifted a
day, weights timed on the same day, amounts zeroed or scaled, a payer left out
of the distribution data, the raw $ series fed in place of deposit-adjusted,
the model's holdings edited around an ex-date, a pay-lag table forced or
shifted, a Yahoo wire response mutated) — no code switches, so the same
production path is judged.

What the panel found missing and what now covers it:
  - consumer keys never pinned          -> T8 (per-engine values, tight)
  - primary/secondary swap invisible    -> T8 (HARV corr 0.857 vs 0.118)
  - live side (raw vs deposit-adjusted) -> T8 broken: raw series fed in
  - analyze() I/O path never exercised  -> T15 (composerlib mocked in the
                                           real wire format; Yahoo failure)
  - corr/beta/vol carried by one shared
    ex-date artefact                    -> T9 (one-point robustness)
  - held-through pay-date credits bias  -> T10 (leak/held classifier vs the
                                           cash trail), primary unbiased
  - additive convention passes          -> T11 (model reproduction < 1 bps)
  - _on_calendar compounding dead       -> T12
  - cumulative/daily consistency        -> T13
  - weight date off the model calendar  -> T14
Second panel round (open conditions C2/C3, 2026-10-05):
  - Yahoo parser success path ungated   -> T16 (fixture -> Yahoo wire JSON ->
    (5/5 mutants survived)                 patched urlopen -> REAL
                                           fetch_yahoo_chart; 7 wire mutants
                                           incl. adjclose missing -> INCOMPLETE)
  - fund-agnostic ex..ex+4 classifier   -> T17 (per-fund PAY_LAG vs the fixture
                                           cash/recredit days; no cash-trail
                                           label flips; ZVOL short hold;
                                           unknown lag -> AMBIGUOUS, strict;
                                           window-end clip = credit pending)
Third panel round (part 1 review, 2026-10-05):
  - credit_pending off by one (span < L;
    the credit lands on ex+L)           -> T17d literal hand-derived profiles
                                           (PULS L=2, BIL L=3, ZVOL L=1);
                                           broken: the part-1 rule. This one
                                           broken counterpart is a RULE mutant
                                           (classify_hold swapped for the
                                           part-1 body): the rule is the thing
                                           under test.
  - family-inherited / unidentified lags
    in PAY_LAG (n=0 rows, SOXL)         -> T17 LAG_EVIDENCE: every entry n>=1
                                           and its OWN event identified in the
                                           fixtures on ex+L; broken: SOXL
                                           re-added at lag 1/3/5, n=0 entries
  - Op2 reads the sleeve from 2026-08-01 -> T18 --start: SLEEVE pins, an
                                           independent recomputation from the
                                           fixture, broken: start ignored, one
                                           leg sliced, refetch simulated
Fourth panel round (part 2 review, 2026-10-06):
  - --start dropped the first post-start
    return (base = first date >= start;
    the 07-31 -> 08-03 return is earned
    on the edited strategy's holdings)  -> T18 base = last close BEFORE start;
                                           gate_t18_start derives the calendar
                                           from POLICY (first counted return =
                                           first trading day >= start), not
                                           from the code's convention; broken:
                                           the old boundary (base 08-03)
  - pre-start held-through credit landing
    inside the window (gap biased up)   -> T18b flagged + bounded; broken: flag
                                           dropped
  - unknown-lag boundary / pending on
    exited rows / unknown-lag pending /
    days_in_window cap unpinned         -> T17e literal classify_hold cases
  - non-ISO --start silently full window-> T18c analyze_series raises, CLI exits

Fixtures (frozen 2026-10-05, pure JSON, no API):
  divergence-panel-2026-10-05.json   per engine: live dates/raw/adj, model
                                     dates/curve, Composer tdvm_weights (ISO)
  divergence-yahoo-2026-10-05.json   per ticker: dates/close/adjclose/divs/
                                     splits (open/high/low dropped: unread)
  divergence-account-2026-10-05.json account value history + total_stats

Run from the repo root:
  python3 -m unittest composer.scripts.tests.test_divergence -v
  python3 -m pytest composer/scripts/tests/test_divergence.py   (if installed)
"""

import contextlib
import datetime as dt
import io
import json
import math
import os
import statistics
import sys
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
if SCRIPTS not in sys.path:               # import exactly as monitor.py does
    sys.path.insert(0, SCRIPTS)
import divergence as dv  # noqa: E402
import composerlib as cl  # noqa: E402

PANEL = os.path.join(FIX, "divergence-panel-2026-10-05.json")
YAHOO = os.path.join(FIX, "divergence-yahoo-2026-10-05.json")
ACCOUNT = os.path.join(FIX, "divergence-account-2026-10-05.json")

# keys monitor.py run_diagnostic()/gauge-RED sweep and POLICY Op2/Op3 read
CONSUMER_KEYS = ["daily_return_correlation", "live_beta_to_model",
                 "live_model_vol_ratio", "live_max_drawdown", "annualized_gap",
                 "cumulative_gap", "mean_daily_gap_bps", "live_cumulative_return",
                 "model_cumulative_return", "worst_daily_gap_bps",
                 "best_daily_gap_bps"]
SECONDARY_KEYS = ["model_total_return_cumulative", "cumulative_gap_total_return_basis",
                  "annualized_gap_total_return_basis",
                  "daily_return_correlation_total_return_basis",
                  "live_beta_to_model_total_return_basis",
                  "live_model_vol_ratio_total_return_basis"]

# Frozen add.-38 (panel-revised) numbers on the 2026-10-05 fixture. These ARE
# the Op2/Op3 inputs; any change here is a methodology change and must be
# re-derived, not re-pinned. Tolerances: 0.0015 on corr/beta/vol (keys are
# rounded to 3 dp), 0.0006 on gaps/returns (4 dp), 0.06 bps on daily gaps.
#
# HG re-derived 2026-10-05 for the per-fund PAY_LAG classifier (panel C2):
# exactly one row flips — HG BIL 2026-04-01 (pre-edit, model-only; the model
# held BIL ex..ex+3 >= BIL's observed L=3) LEAKED -> HELD_THROUGH, so its
# 28.8 bps stays in the model. Old (fund-agnostic) HG pins in
# PINNED_FUND_AGNOSTIC_HG; T17a proves the delta is that row and nothing else.
# corr/beta/vol (total-return pair) and KMLM/SLEEVE/HARV do not move.
PINNED = {
    #           corr   beta   volr   maxDD   ann_gap  cum_gap  mean_bps  live_cum  model_cum
    "HG":     (0.960, 0.979, 1.019, 0.2105, 0.0871, 0.1258, 3.46, 0.8923, 0.7665),
    "KMLM":   (0.988, 0.990, 1.003, 0.1475, 0.0354, 0.0112, 1.41, 0.3130, 0.3019),
    "SLEEVE": (0.969, 1.036, 1.068, 0.0481, 0.0794, 0.0220, 3.15, 0.1797, 0.1576),
    "HARV":   (0.857, 0.835, 0.974, 0.0403, 0.0308, 0.0059, 1.22, -0.0152, -0.0212),
}
PIN_KEYS = ["daily_return_correlation", "live_beta_to_model", "live_model_vol_ratio",
            "live_max_drawdown", "annualized_gap", "cumulative_gap",
            "mean_daily_gap_bps", "live_cumulative_return", "model_cumulative_return"]
PIN_TOL = [0.0015, 0.0015, 0.0015, 0.0006, 0.0006, 0.0006, 0.06, 0.0006, 0.0006]
PINNED_FUND_AGNOSTIC_HG = (0.960, 0.979, 1.019, 0.2105, 0.0906, 0.1309, 3.60, 0.8923, 0.7614)

# add.-36 total-return-basis numbers (the ones that false-failed HARV)
PINNED_TR = {"HG": (0.960, 0.072), "KMLM": (0.989, -0.0094),
             "SLEEVE": (0.969, 0.0741), "HARV": (0.118, -0.1311)}

# Lens 3 (cash trail: account residual + fills) classification of every
# valid-regime ledger row. Independent of the model-continuity rule under test.
LENS3_HELD = {("HG", "2026-09-01", "BIL"), ("HG", "2026-09-23", "TQQQ"),
              ("KMLM", "2026-07-31", "PULS"), ("KMLM", "2026-08-31", "PULS"),
              ("KMLM", "2026-09-30", "PULS"), ("KMLM", "2026-09-22", "SOXL"),
              ("SLEEVE", "2026-09-22", "LABD"), ("HARV", "2026-07-31", "PULS"),
              ("HARV", "2026-08-31", "PULS"), ("HARV", "2026-09-30", "PULS")}
LENS3_LEAKED = {("HARV", "2026-08-19", "ZVOL"), ("KMLM", "2026-08-19", "ZVOL"),
                ("HG", "2026-08-03", "BIL"), ("SLEEVE", "2026-09-22", "TMV")}
# model-only holding: the model held TLT into 09-01, live had sold it on
# 08-31. No live entitlement, no cash jump. Classified LEAKED (documented miss;
# TLT has no observed lag, but weights[ex] == 0 makes it LEAKED for any lag).
MODEL_ONLY = {("KMLM", "2026-09-01", "TLT")}

# Labels the add.-38 fund-agnostic rule (ex..ex+4) gave every valid-regime
# row the cash trail determined (committed results JSON
# divergence-2026-10-05-distaware.json, eb87d9b). The per-fund table must not
# flip any of them (panel C2 condition: "nothing flips on the frozen panel").
OLD_RULE_LABELS = {
    ("HG", "2026-08-03", "BIL"): "LEAKED",        ("HG", "2026-09-01", "BIL"): "HELD_THROUGH",
    ("HG", "2026-09-23", "TQQQ"): "HELD_THROUGH", ("KMLM", "2026-07-31", "PULS"): "HELD_THROUGH",
    ("KMLM", "2026-08-19", "ZVOL"): "LEAKED",     ("KMLM", "2026-08-31", "PULS"): "HELD_THROUGH",
    ("KMLM", "2026-09-22", "SOXL"): "HELD_THROUGH", ("KMLM", "2026-09-30", "PULS"): "HELD_THROUGH",
    ("SLEEVE", "2026-09-22", "LABD"): "HELD_THROUGH", ("SLEEVE", "2026-09-22", "TMV"): "LEAKED",
    ("HARV", "2026-07-31", "PULS"): "HELD_THROUGH", ("HARV", "2026-08-19", "ZVOL"): "LEAKED",
    ("HARV", "2026-08-31", "PULS"): "HELD_THROUGH", ("HARV", "2026-09-30", "PULS"): "HELD_THROUGH",
}
# The one row the per-fund table flips on the whole panel (pre-edit, model-only)
EXPECTED_FLIPS = {("HG", "2026-04-01", "BIL"): ("LEAKED", "HELD_THROUGH")}

# Physical pay-lag evidence in the fixtures: each PAY_LAG entry's OWN credit
# (lens 3 + panel re-derivation 2026-10-05). Two kinds:
#   ("cash", ex, engines)     live held the payer at the ex-date open and sold
#                             it before the credit -> the account-cash residual
#                             (account value minus the sum of live symphonies)
#                             jumps on ex+L by the engines' entitlement (+-3%)
#   ("recredit", engine, ex)  the model held through -> the live-only +w*y day
#                             in the primary gap; identified only if EXACTLY
#                             ONE day in ex+1..ex+MAX_PAY_LAG+1 matches +term
#                             within RECREDIT_TOL bps, and it is ex+L
# Not every PAY_LAG event is identifiable in these fixtures (PULS 07-31 and
# 09-30 are too noisy on HARV/KMLM); each entry needs >= 1 that is.
LAG_EVIDENCE = {
    "ZVOL": [("cash", "2026-08-19", ("HARV", "KMLM"))],
    "PULS": [("recredit", "HARV", "2026-08-31"), ("recredit", "KMLM", "2026-08-31")],
    "BIL":  [("cash", "2026-08-03", ("HG",)), ("recredit", "HG", "2026-09-01")],
    "TQQQ": [("recredit", "HG", "2026-09-23")],
    "SSO":  [("cash", "2025-12-24", ("HG",))],
    "LABD": [("recredit", "SLEEVE", "2026-09-22")],
    "TMV":  [("cash", "2026-09-22", ("SLEEVE",))],
}
RECREDIT_TOL = 3.0
CASH_TOL = 0.03
# removed from PAY_LAG 2026-10-05 (panel): n=0 family-inherited (QLD, UDOW,
# TECL never held live into an ex-date), or held live but the own credit not
# identified (SOXL 09-22: term below tolerance; TNA 2026-06-23: credit masked
# by ~$50k of account flows on ex+5..ex+8). They stay out unless an event is
# identified.
NOT_OBSERVED = ("SOXL", "QLD", "UDOW", "TECL", "TNA", "TLT", "SQQQ")


# ---------------------------------------------------------------- helpers

def load_panel():
    with open(PANEL) as f:
        return json.load(f)


def load_yahoo():
    with open(YAHOO) as f:
        return json.load(f)


def load_account():
    with open(ACCOUNT) as f:
        return json.load(f)


def dists_all(yahoo):
    return {t: dv.dists_from_chart(c) for t, c in yahoo.items()}


def run(engine, panel, dists, weights=None, live=None, live_dates=None, pay_lag=None,
        end=None, start=None):
    """analyze_series on one engine; `end` truncates live AND model at that
    date (the window-end clip), `pay_lag` overrides dv.PAY_LAG, `start` is
    passed through (the --start window)."""
    v = panel[engine]
    ld = live_dates or v["dates"]
    lv = live if live is not None else v["adj"]
    md, mv, raw = v["model_dates"], v["model"], v["raw"]
    if end is not None:
        k = ld.index(end) + 1
        ld, lv, raw = ld[:k], lv[:k], raw[:k]
        j = md.index(end) + 1
        md, mv = md[:j], mv[:j]
    return dv.analyze_series(ld, lv, md, mv,
                             weights if weights is not None else v["weights"],
                             dists, live_raw=raw, symphony=engine,
                             name=engine, detail=True, pay_lag=pay_lag, start=start)


def shown(result):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        dv.show(result)
    return buf.getvalue()


def gap_on(result, date, basis="gap_bps"):
    return next(d[basis] for d in result["daily"] if d["date"] == date)


def row_on(result, date):
    return next(d for d in result["daily"] if d["date"] == date)


def moments(rows, live_key="live_ret_total_return", model_key="model_ret_total_return"):
    a = [d[live_key] for d in rows]
    b = [d[model_key] for d in rows]
    return (cl.pearson(a, b), dv._beta(a, b), dv._vol_ratio(a, b))


# -------------------------------------------- broken-input transforms (input only)

def shift_exdates(dists, model_dates):
    """Every ex-date moved to the NEXT model trading day."""
    out = {}
    for t, dd in dists.items():
        out[t] = {}
        for ex, row in dd.items():
            later = [d for d in model_dates if d > ex]
            out[t][later[0] if later else ex] = row
    return out


def weights_same_day(weights, model_dates):
    """Re-key so a w(t-1) lookup returns Composer's w(t): the wrong timing."""
    out = {}
    for t, dd in weights.items():
        out[t] = {model_dates[i - 1]: dd[model_dates[i]]
                  for i in range(1, len(model_dates)) if model_dates[i] in dd}
    return out


def zero_amounts(dists):
    return {t: {ex: dict(row, amount=0.0) for ex, row in dd.items()}
            for t, dd in dists.items()}


def scale_amount(dists, ticker, factor):
    return {t: {ex: dict(row, amount=row["amount"] * (factor if t == ticker else 1.0))
                for ex, row in dd.items()} for t, dd in dists.items()}


def additive_convention(dists):
    """adj_ret := 0 makes the term w*D/P_prev: the additive convention."""
    return {t: {ex: dict(row, adj_ret=0.0) for ex, row in dd.items()}
            for t, dd in dists.items()}


def without(dists, ticker):
    return {t: dd for t, dd in dists.items() if t != ticker}


def weights_held_through(weights, ticker, ex, model_dates, n=dv.MAX_PAY_LAG):
    """The model is edited to KEEP the payer on ex..ex+n-1 (n model days;
    default the longest observed pay lag, so HELD_THROUGH for any fund)."""
    i = model_dates.index(ex)
    w_prev = weights[ticker][model_dates[i - 1]]
    out = {t: dict(dd) for t, dd in weights.items()}
    for d in model_dates[i:i + n]:
        out[ticker][d] = w_prev
    return out


def weights_exit_at_ex(weights, ticker, ex, model_dates, n=dv.MAX_PAY_LAG):
    """The model is edited to have SOLD the payer at the ex-date close."""
    i = model_dates.index(ex)
    out = {t: dict(dd) for t, dd in weights.items()}
    for d in model_dates[i:i + n]:
        out[ticker][d] = 0.0
    return out


def drop_live_date(panel, engine, date):
    v = panel[engine]
    i = v["dates"].index(date)
    return (v["dates"][:i] + v["dates"][i + 1:], v["adj"][:i] + v["adj"][i + 1:])


def extend_zvol_hold(weights):
    """HARV's model is edited to KEEP ZVOL across the 08-19 ex-date (it
    held it 08-18 and 08-20 but sold for 08-19): ZVOL 0.52 / PULS 0.48 on
    08-19, weights still sum to 1. ZVOL is then held 2 model days from ex."""
    out = {t: dict(dd) for t, dd in weights.items()}
    out["ZVOL"]["2026-08-19"] = 0.52
    out["PULS"]["2026-08-19"] = out["PULS"]["2026-08-19"] - 0.52
    return out


def rename_ticker(weights, dists, old, new):
    """The same payer under a ticker absent from PAY_LAG (unknown pay lag)."""
    return ({(new if t == old else t): dd for t, dd in weights.items()},
            {(new if t == old else t): dd for t, dd in dists.items()})


def lag_table(**override):
    """dv.PAY_LAG with some entries forced (the broken-input tables)."""
    return {**dv.PAY_LAG, **{t: (lag, 0) for t, lag in override.items()}}


def shifted_lag_table(delta):
    return {t: (max(1, lag + delta), n) for t, (lag, n) in dv.PAY_LAG.items()}


# Yahoo wire format (v8 chart API) built from the parsed fixture: bar and
# dividend timestamps at the 09:30 ET open (13:30 UTC), as Yahoo sends them.
def _ts(d):
    return int(dt.datetime(*map(int, d.split("-")), 13, 30,
                           tzinfo=dt.timezone.utc).timestamp())


def to_wire(chart):
    divs = {str(_ts(d)): {"amount": a, "date": _ts(d)} for d, a in chart["divs"]}
    splits = {}
    for d, ratio in chart.get("splits") or []:
        num, den = ratio.split(":")
        splits[str(_ts(d))] = {"date": _ts(d), "numerator": float(num),
                               "denominator": float(den), "splitRatio": ratio}
    return {"chart": {"error": None, "result": [{
        "meta": {"currency": "USD", "dataGranularity": "1d"},
        "timestamp": [_ts(d) for d in chart["dates"]],
        "events": {"dividends": divs, "splits": splits},
        "indicators": {"quote": [{"close": list(chart["close"])}],
                       "adjclose": [{"adjclose": list(chart["adjclose"])}]}}]}}


def _res(w):
    return w["chart"]["result"][0]


def wire_drop_divs(w):
    _res(w)["events"].pop("dividends")
    return w


def wire_div_date_plus1(w):
    ev = _res(w)["events"]
    ev["dividends"] = {str(v["date"] + 86400): dict(v, date=v["date"] + 86400)
                       for v in ev["dividends"].values()}
    return w


def wire_amount_half(w):
    for v in _res(w)["events"]["dividends"].values():
        v["amount"] *= 0.5
    return w


def wire_bar_date_plus1(w):
    _res(w)["timestamp"] = [t + 86400 for t in _res(w)["timestamp"]]
    return w


def wire_adjclose_is_close(w):
    ind = _res(w)["indicators"]
    ind["adjclose"][0]["adjclose"] = list(ind["quote"][0]["close"])
    return w


def wire_adjclose_missing(w):
    _res(w)["indicators"].pop("adjclose")
    return w


def wire_half_bar(w):
    """one bar with a close but no adjclose (must refuse, not patch)."""
    _res(w)["indicators"]["adjclose"][0]["adjclose"][-5] = None
    return w


WIRE_TICKERS = ("BIL", "PULS", "ZVOL")
WIRE_BROKEN = {"dividends dropped": wire_drop_divs,
               "dividend date +1 day": wire_div_date_plus1,
               "amount x0.5": wire_amount_half,
               "bar date +1 day": wire_bar_date_plus1,
               "adjclose := close": wire_adjclose_is_close,
               "adjclose missing": wire_adjclose_missing,
               "half bar (adjclose None)": wire_half_bar}


# --------------------------------------------------- gate predicates (shared)

T1_BAND = (-95.0, -45.0)


def gate_t1(harv):
    g = gap_on(harv, "2026-08-19")
    return T1_BAND[0] <= g <= T1_BAND[1]


CLEAN = [("HG", "2026-08-03"), ("HG", "2026-09-01"), ("HARV", "2026-08-31")]


def gate_t2(results):
    """Term accuracy on clean ex-dates, read on the all-stripped (price-only)
    column: the primary deliberately leaves held-through rows in the model."""
    return all(abs(gap_on(results[e], d, "gap_bps_price_only_basis")) <= 3.0
               for e, d in CLEAN)


def gate_t8(res, engines=None):
    bad = []
    for e, pins in PINNED.items():
        if engines is not None and e not in engines:
            continue
        for k, pin, tol in zip(PIN_KEYS, pins, PIN_TOL):
            if abs(res[e][k] - pin) > tol:
                bad.append((e, k, res[e][k], pin))
    return bad


ONE_POINT_TOL = 0.04


def gate_t9(harv):
    """corr must not be carried by the single fat ex-date."""
    c_all = moments(harv["daily"])[0]
    c_x = moments([d for d in harv["daily"] if d["date"] != "2026-08-19"])[0]
    return abs(c_all - c_x) < ONE_POINT_TOL, c_all, c_x


def invariance_violations(ret_tr, ret_px, exempt):
    """Days (outside `exempt` indices) where price-only != total-return,
    bit-for-bit."""
    return [i for i in range(1, len(ret_tr))
            if i not in exempt and ret_px[i].hex() != ret_tr[i].hex()]


def model_reproduction(panel, yahoo, engine, weights, dists, cost=True):
    """Rebuild divergence's all-stripped model return from tdvm_weights x
    Yahoo CLOSE returns with a one-way-turnover cost fitted on non-ex days
    (lens 2). Returns (c_bps, resid_sd_bps, resid_max_bps) over ALL days."""
    v = panel[engine]
    md = v["model_dates"]
    tr, px, ledger = dv.price_only_model_returns(md, v["model"], weights, dists)
    exidx = {md.index(x["applied_on"]) for x in ledger}

    def yret(t, d):
        c = yahoo[t]
        i = c["dates"].index(d)
        return c["close"][i] / c["close"][i - 1] - 1, c["adjclose"][i] / c["adjclose"][i - 1] - 1

    rows = []
    for i in range(1, len(md)):
        d, dp = md[i], md[i - 1]
        wp = {t: (weights[t].get(dp) or 0.0) for t in weights}
        wn = {t: (weights[t].get(d) or 0.0) for t in weights}
        turn = 0.5 * sum(abs(wn[t] - wp[t]) for t in weights)
        s_adj = sum(w * yret(t, d)[1] for t, w in wp.items() if w > 1e-9 and t != dv.CASH_TICKER)
        s_px = sum(w * yret(t, d)[0] for t, w in wp.items() if w > 1e-9 and t != dv.CASH_TICKER)
        rows.append((i, tr[i], px[i], s_adj, s_px, turn))
    fit = [(turn, tr_ - s_adj, 1 + s_adj) for i, tr_, px_, s_adj, s_px, turn in rows
           if i not in exidx]
    c = (sum(-r * to * g for to, r, g in fit) / sum((to * g) ** 2 for to, r, g in fit)
         if cost else 0.0)
    res = [(px_ - ((1 + s_px) * (1 - c * turn) - 1)) * 1e4
           for i, tr_, px_, s_adj, s_px, turn in rows]
    return c * 1e4, statistics.pstdev(res), max(abs(x) for x in res)


def labels(res, since="2026-07-22"):
    return {(e, x["date"], x["ticker"]): x["treatment"]
            for e, r in res.items() for x in r["distribution_ledger"] if x["date"] >= since}


def gate_t17_lag_evidence(panel, dists, table, evidence=None):
    """Every PAY_LAG entry is an OBSERVED own-event lag: n >= 1, at least one
    event listed in `evidence` (default LAG_EVIDENCE), and every listed event
    identified in the fixtures on ex+L for the table's L (cash: the residual's
    largest jump in ex+1..ex+8 is on ex+L and equals the entitlement within
    CASH_TOL; recredit: exactly one day in ex+1..ex+MAX_PAY_LAG+1 matches
    +term within RECREDIT_TOL, and it is ex+L). Returns the misses ([] = pass)."""
    evidence = LAG_EVIDENCE if evidence is None else evidence
    acct = load_account()["history"]
    a = dict(zip(acct["dates"], acct["series"]))
    dates = acct["dates"]

    def residual(d):                  # engines not yet live on d contribute 0
        return a[d] - sum(v["raw"][v["dates"].index(d)] for v in panel.values()
                          if d in v["dates"])
    full = {e: run(e, panel, dists, pay_lag=table) for e in panel}
    miss = []
    for t, (lag, n) in sorted(table.items()):
        if n < 1:
            miss.append(("n=0 (inherited, not observed)", t, lag))
        if not evidence.get(t):
            miss.append(("no identified own event in the fixtures", t, lag))
    for t, events in sorted(evidence.items()):
        if t not in table:
            continue
        lag = table[t][0]
        for ev in events:
            if ev[0] == "cash":
                _, ex, engines = ev
                i = dates.index(ex)
                jumps = [(residual(dates[k]) - residual(dates[k - 1]), k - i)
                         for k in range(i + 1, min(i + 9, len(dates)))]
                usd = sum(x["expected_income_usd"] for e in engines
                          for x in full[e]["distribution_ledger"]
                          if x["date"] == ex and x["ticker"] == t)
                top, k = max(jumps)
                if k != lag or not usd or abs(top - usd) / usd > CASH_TOL:
                    miss.append(("cash", t, ex, f"max jump {top:+.2f} on ex+{k}",
                                 f"entitlement {usd:.2f}", f"L={lag}"))
            else:
                _, e, ex = ev
                r = full[e]
                row = next(x for x in r["distribution_ledger"]
                           if x["date"] == ex and x["ticker"] == t)
                days = [d["date"] for d in r["daily"]]
                i = days.index(row["applied_on"])
                hits = [k for k in range(1, dv.MAX_PAY_LAG + 2) if i + k < len(days)
                        and abs(gap_on(r, days[i + k]) - row["term_bps"]) <= RECREDIT_TOL]
                if hits != [lag]:
                    miss.append(("recredit", t, e, ex, f"term {row['term_bps']:.1f} bps",
                                 f"matching days ex+{hits}", f"L={lag}"))
    return miss


def gate_t17b_zvol_short_hold(r):
    """ZVOL (L=1) held across its ex-date for 2 days: HELD_THROUGH, not
    subtracted, and (no other leaked row on HARV) the primary model is the
    total-return model."""
    z = [x for x in r["distribution_ledger"]
         if x["ticker"] == "ZVOL" and x["date"] == "2026-08-19"]
    return (len(z) == 1 and z[0]["treatment"] == "HELD_THROUGH"
            and z[0]["subtracted_bps"] == 0.0
            and r["model_cumulative_return"] == r["model_total_return_cumulative"])


def gate_t17c_ambiguous(r, out, strict_ref, lenient_ref, ticker="ZZZZ"):
    """Unknown-lag payer held 1..MAX_PAY_LAG-1 days: AMBIGUOUS, primary ==
    strict, lenient alternative reported, loud show() line. [] = pass."""
    bad = []
    row = [x for x in r["distribution_ledger"] if x["ticker"] == ticker]
    if len(row) != 1 or row[0]["treatment"] != "AMBIGUOUS":
        return [("treatment", [x["treatment"] for x in row])]
    x = row[0]
    if not (x["subtracted_bps"] == 0.0 and x.get("strict_subtracted_bps") == 0.0
            and x.get("lenient_subtracted_bps") == x["term_bps"] and x["pay_lag_bd"] is None):
        bad.append(("row alternatives", x))
    if [a["ticker"] for a in r["ambiguous_rows"]] != [ticker]:
        bad.append(("ambiguous_rows", r["ambiguous_rows"]))
    bad += [("primary != strict", k, r[k], strict_ref[k])
            for k in CONSUMER_KEYS if r[k] != strict_ref[k]]
    if (r["annualized_gap_ambiguous_lenient"] != lenient_ref["annualized_gap"]
            or r["cumulative_gap_ambiguous_lenient"] != lenient_ref["cumulative_gap"]):
        bad.append(("lenient", r["annualized_gap_ambiguous_lenient"],
                    lenient_ref["annualized_gap"]))
    loud = [ln for ln in out.splitlines() if f"AMBIGUOUS: {ticker}" in ln]
    if not (loud and f"pay lag for {ticker} is MISSING" in loud[0]
            and "account-cash residual" in loud[0]
            and f"{lenient_ref['annualized_gap']:+.1%}" in loud[0]):
        bad.append(("show() loud line", loud))
    return bad


def pending_profile(panel, dists, engine, ex, ticker, n_windows, table=None, weights=None):
    """[(k, treatment, credit_pending, held_days_checked, shown-as-pending)]
    for windows ending on model day ex+k, k = 0 .. n_windows-1."""
    md = panel[engine]["model_dates"]
    i = md.index(ex)
    out = []
    for k in range(n_windows):
        r = run(engine, panel, dists, pay_lag=table, end=md[i + k], weights=weights)
        x = next(y for y in r["distribution_ledger"] if y["date"] == ex and y["ticker"] == ticker)
        line = next(ln for ln in shown(r).splitlines()
                    if ln.strip().startswith(f"{ex} {ticker}"))
        out.append((k, x["treatment"], x["credit_pending"], x["held_days_checked"],
                    "credit pending" in line))
    return out


# Literal expected profiles, derived by hand (NOT from dv.PAY_LAG): the model
# holds the payer on every day shown; the credit lands at the open of model
# day ex+L, so the row is pending exactly while the window ends on ex+0 ..
# ex+L-1, and held_days_checked = min(k+1, L).
#   HARV PULS 2026-08-31, L=2 (credit 09-02): windows ending 08-31, 09-01
#     pending; 09-02, 09-03 not.
#   HG BIL 2026-09-01, L=3 (credit 09-04): 09-01, 09-02, 09-03 pending;
#     09-04, 09-08 not.
#   HARV ZVOL 2026-08-19 with the model edited to hold it (extend_zvol_hold),
#     L=1 (credit 08-20): the window ending ON the ex-date is pending.
H = "HELD_THROUGH"
EXPECTED_PENDING = {
    ("HARV", "2026-08-31", "PULS"): [(0, H, True, 1, True), (1, H, True, 2, True),
                                     (2, H, False, 2, False), (3, H, False, 2, False)],
    ("HG", "2026-09-01", "BIL"): [(0, H, True, 1, True), (1, H, True, 2, True),
                                  (2, H, True, 3, True), (3, H, False, 3, False),
                                  (4, H, False, 3, False)],
    ("HARV", "2026-08-19", "ZVOL"): [(0, H, True, 1, True), (1, H, False, 1, False),
                                     (2, H, False, 1, False)],
}


def classify_hold_part1(ticker, wt, fwd_dates, pay_lag=None):
    """The part-1 (db0a462) rule, verbatim, adapted to the 6-tuple: pending =
    span < L, i.e. one day too early. RULE mutant for the T17d broken test."""
    table = dv.PAY_LAG if pay_lag is None else pay_lag
    known = ticker in table
    need = table[ticker][0] if known else dv.MAX_PAY_LAG
    span = fwd_dates[:need]
    held = [(wt.get(d) or 0.0) > 1e-9 for d in span]
    run_ = next((k for k, h in enumerate(held) if not h), len(held))
    pending = len(span) < need and run_ == len(span)
    if run_ == len(span) and not pending:
        treatment = "HELD_THROUGH"
    elif run_ == 0:
        treatment = "LEAKED"
    elif known:
        treatment = "HELD_THROUGH" if pending else "LEAKED"
    else:
        treatment = "AMBIGUOUS"
    return treatment, len(span), need, pending, run_, min(len(fwd_dates), need + 1)


def gate_t17d_pending(panel, dists, table=None):
    """[] = every literal profile reproduced."""
    bad = []
    for (e, ex, t), want in EXPECTED_PENDING.items():
        w = extend_zvol_hold(panel["HARV"]["weights"]) if t == "ZVOL" else None
        got = pending_profile(panel, dists, e, ex, t, len(want), table=table, weights=w)
        if got != want:
            bad.append(((e, ex, t), [g for g, x in zip(got, want) if g != x]))
    return bad


# --start window (T18). Op2 reads the sleeve from 2026-08-01 (POLICY.md: "the
# 07-07..07-31 days compare two different strategies"). The base is the last
# close BEFORE start (07-31): the 07-31 close holdings are already the edited
# strategy (fills: BOXX bought 07-31 15:53 to 0.75 of the sleeve = the
# model's BOXX 0.75 / LABD 0.25; LABD -> BOXX 08-03 15:53 = the model's move),
# so the first counted return is 08-03 (its -9.33 bps is mostly LABD fill
# timing, ~-12 bps, the shortfall Op2 measures). Window 07-31 (base) .. 10-02: 44 trading days
# on/after start, 44 daily returns. Frozen on the 2026-10-05 fixture,
# re-derived 2026-10-06 and confirmed by the independent recomputation in
# gate_t18_start and by the verifier's own stdlib code (0.0671 / 0.992 /
# 1.017 / 1.025). The superseded boundary (base 08-03, 43 returns) read
# 0.0741 / 0.0136: PINNED_SLEEVE_FROM_0803_BASE, kept for the broken test.
OP2_START = "2026-08-01"
#                corr   beta   volr   maxDD   ann_gap  cum_gap  mean_bps  live_cum  model_cum
PINNED_SLEEVE_FROM_0801 = (0.992, 1.017, 1.025, 0.0481, 0.0671, 0.0125, 2.66, 0.0938, 0.0813)
PINNED_SLEEVE_FROM_0803_BASE = (0.992, 1.016, 1.024, 0.0481, 0.0741, 0.0136, 2.94, 0.0966, 0.0830)
SLEEVE_0801_WINDOW = (["2026-07-31", "2026-10-02"], "2026-08-03", 44, 44)


def _maxdd(vals):
    peak, dd = vals[0], 0.0
    for x in vals:
        peak = max(peak, x)
        dd = max(dd, 1.0 - x / peak)
    return dd


def policy_calendar(panel, engine, start):
    """POLICY's reading of --start, from the raw fixture calendar: trading
    days >= start are the window (day 1 = the first of them = the first
    counted return); the base is the last trading day BEFORE start (absent:
    the first window day is the base, as in a full-window read)."""
    v = panel[engine]
    mv = set(v["model_dates"])
    cal = [d for d in v["dates"] if d in mv]
    days = [d for d in cal if d >= start]
    before = [d for d in cal if d < start]
    base = before[-1] if before else days[0]
    return base, days, [base] + (days if before else days[1:])


def gate_t18_start(r, panel, engine, start, full):
    """--start result checked against values computed here from the raw
    fixture (not through analyze_series' slicing) and against the full-window
    run's own daily table restricted to the window. The calendar comes from
    POLICY (policy_calendar), not from the code's convention. [] = pass."""
    v = panel[engine]
    lv, mv = dict(zip(v["dates"], v["adj"])), dict(zip(v["model_dates"], v["model"]))
    base, days, win = policy_calendar(panel, engine, start)
    w0, w1 = base, win[-1]
    bad = []

    def chk(name, got, want, tol=0.0):
        if got is None or abs(got - want) > tol + 1e-12:
            bad.append((name, got, want))
    if r.get("window_start_requested") != start:
        bad.append(("window_start_requested", r.get("window_start_requested"), start))
    if r["window"] != [w0, w1]:
        bad.append(("window", r["window"], [w0, w1]))
    if r.get("window_first_return_date") != win[1]:
        bad.append(("window_first_return_date", r.get("window_first_return_date"), win[1]))
    if r.get("daily") and r["daily"][0]["date"] != win[1]:
        bad.append(("first daily row", r["daily"][0]["date"], win[1]))
    chk("n_trading_days", r.get("n_trading_days"), len(days))
    chk("n_days", r["n_days"], len(win) - 1)
    # live leg, from the fixture
    chk("live_cumulative_return", r["live_cumulative_return"], round(lv[w1] / lv[w0] - 1, 4))
    chk("live_max_drawdown", r["live_max_drawdown"], round(_maxdd([lv[d] for d in win]), 4))
    # model leg, from the fixture
    chk("model_total_return_cumulative", r["model_total_return_cumulative"],
        round(mv[w1] / mv[w0] - 1, 4))
    # ledger / ex_dates inside the window
    out = [x["date"] for x in r["distribution_ledger"] if not w0 < x["applied_on"] <= w1]
    out += [d for d, _, _ in r["ex_dates"] if not w0 <= d <= w1]
    if out:
        bad.append(("ledger/ex_dates outside window", out))
    # slice-equivalence: the full-window daily table restricted to the window
    rows = [d for d in full["daily"] if w0 < d["date"] <= w1]
    g = [d["gap_bps"] for d in rows]
    chk("mean_daily_gap_bps", r["mean_daily_gap_bps"], round(sum(g) / len(g), 2), 0.005)
    chk("annualized_gap", r["annualized_gap"], round(sum(g) / len(g) / 1e4 * 252, 4), 0.00005)
    f_l = f_m = 1.0
    for d in rows:
        f_l *= 1 + d["live_ret"]
        f_m *= 1 + d["model_ret"]
    chk("cumulative_gap", r["cumulative_gap"], round((f_l - 1) - (f_m - 1), 4), 0.00011)
    c, b, vr = moments(rows)
    chk("daily_return_correlation", r["daily_return_correlation"], round(c, 3), 0.0005)
    chk("live_beta_to_model", r["live_beta_to_model"], round(b, 3), 0.0005)
    chk("live_model_vol_ratio", r["live_model_vol_ratio"], round(vr, 3), 0.0005)
    if engine == "SLEEVE" and start == OP2_START:
        for k, pin, tol in zip(PIN_KEYS, PINNED_SLEEVE_FROM_0801, PIN_TOL):
            chk("pin " + k, r[k], pin, tol)
    return bad


LIVE_LEG_KEYS = ("live_cumulative_return", "live_max_drawdown")
MODEL_LEG_KEYS = ("model_cumulative_return", "model_total_return_cumulative")


def one_leg_unsliced(sliced, unsliced, leg):
    """The result an implementation would print if it applied start to only
    ONE leg: everything from the sliced run except `leg`'s keys ("live" or
    "model"), which come from the full-window run; the cumulative gap is
    recomputed from the mixture. (With the common calendar an intersection,
    truncating one leg's INPUT cannot produce this — T18 shows that — so the
    failure mode is a statistic read off an unsliced series.)"""
    r = dict(sliced)
    for k in (LIVE_LEG_KEYS if leg == "live" else MODEL_LEG_KEYS):
        r[k] = unsliced[k]
    r["cumulative_gap"] = round(r["live_cumulative_return"] - r["model_cumulative_return"], 4)
    return r


def gate_t18b_pre_window(r, full, panel, engine, start, out=None):
    """Pre-window credits, recomputed here from the FULL-window ledger and the
    raw model calendar (not via dv.pre_window_credit_rows): every non-LEAKED
    row applied at or before the base close whose credit day ex+L (known L)
    or any of ex+1..ex+MAX_PAY_LAG (unknown) is inside the window must be
    flagged, with the bias bound term/n_days*252 and the offset gap; show()
    must carry the !! line. [] = pass."""
    md = panel[engine]["model_dates"]
    base, _, win = policy_calendar(panel, engine, start)
    want = []
    for x in full["distribution_ledger"]:
        if x["treatment"] == "LEAKED" or x["applied_on"] > base:
            continue
        i = md.index(x["applied_on"])
        steps = ([x["pay_lag_bd"]] if x["pay_lag_bd"] is not None
                 else range(1, dv.MAX_PAY_LAG + 1))
        if any(i + k < len(md) and base < md[i + k] <= win[-1] for k in steps):
            want.append((x["date"], x["ticker"]))
    got = [(x["date"], x["ticker"]) for x in r.get("pre_window_credit_rows") or []]
    bad = [] if got == want else [("rows", got, want)]
    bps = sum(x["term_bps"] for x in r.get("pre_window_credit_rows") or [])
    bound = round(bps / 1e4 / r["n_days"] * 252, 4)
    if r.get("pre_window_credit_bias_annualized_max") != bound:
        bad.append(("bound", r.get("pre_window_credit_bias_annualized_max"), bound))
    if abs(r.get("annualized_gap_pre_window_credits_offset", 9)
           - (r["annualized_gap"] - bound)) > 0.00011:
        bad.append(("offset", r.get("annualized_gap_pre_window_credits_offset")))
    if out is not None and bool(want) != ("!! PRE-WINDOW CREDIT" in out):
        bad.append(("show() line", bool(want)))
    return bad


# T17e: literal classify_hold cases derived by hand (no PAY_LAG lookup for the
# expected values). Model days d0 = ex, d1 = ex+1, ...; table {"BIL": (3, 1),
# "PULS": (2, 1)}; "ZZZZ" is unlisted (unknown lag, L := MAX_PAY_LAG = 5).
# Each tuple: (ticker, held days from ex, model days in window, expected
# (treatment, checked, required, pending, run, days_in_window_from_ex)).
_D = [f"d{k}" for k in range(8)]
T17E_TABLE = {"BIL": (3, 1), "PULS": (2, 1)}
T17E_CASES = {
    # unknown lag held ex..ex+3 (MAX-1 days): the label still depends on L
    "unknown held MAX-1 -> AMBIGUOUS": ("ZZZZ", 4, 6, ("AMBIGUOUS", 5, 5, False, 4, 6)),
    # unknown lag held ex..ex+4: HELD_THROUGH for any lag <= 5, credit in window
    "unknown held MAX -> HELD_THROUGH": ("ZZZZ", 5, 6, ("HELD_THROUGH", 5, 5, False, 5, 6)),
    # same hold, window ends ex+4: credit (ex+5 at the latest) not in yet
    "unknown held MAX, window ex+4 -> pending": ("ZZZZ", 5, 5, ("HELD_THROUGH", 5, 5, True, 5, 5)),
    # unknown lag, window ends ex+2 with no exit: provisional AMBIGUOUS, pending
    "unknown clipped, no exit -> AMBIGUOUS pending": ("ZZZZ", 8, 3, ("AMBIGUOUS", 3, 5, True, 3, 3)),
    # known L=3, held ex only, window ends ex+1: exit seen -> LEAKED, never pending
    "known exited inside clipped span -> not pending": ("BIL", 1, 2, ("LEAKED", 2, 3, False, 1, 2)),
    # unknown lag, held ex..ex+1, window ends ex+2: exit seen -> AMBIGUOUS, not pending
    "unknown exited inside clipped span -> not pending": ("ZZZZ", 2, 3, ("AMBIGUOUS", 3, 5, False, 2, 3)),
    # known L=2 with 6 model days in window: days_in_window_from_ex capped at L+1
    "known days_in_window capped at L+1": ("PULS", 8, 6, ("HELD_THROUGH", 2, 2, False, 2, 3)),
}


def gate_t17e(classify=None):
    classify = classify or dv.classify_hold
    bad = []
    for name, (t, held, n, want) in T17E_CASES.items():
        wt = {d: (0.5 if k < held else 0.0) for k, d in enumerate(_D)}
        got = classify(t, wt, _D[:n], T17E_TABLE)
        if tuple(got) != want:
            bad.append((name, tuple(got), want))
    return bad


REPRO_SD, REPRO_MAX = 0.5, 1.0


def gate_t11(stats):
    c, sd, mx = stats
    return 9.0 < c < 12.0 and sd < REPRO_SD and mx < REPRO_MAX


# ------------------------------------------------------------------- tests

class DivergenceGates(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.panel = load_panel()
        cls.yahoo = load_yahoo()
        cls.dists = dists_all(cls.yahoo)
        cls.res = {e: run(e, cls.panel, cls.dists) for e in cls.panel}

    # T1 ---------------------------------------------------------------
    def test_t1_harv_0819_reproduction(self):
        harv = self.res["HARV"]
        self.assertLess(gap_on(harv, "2026-08-19", "gap_bps_total_return_basis"),
                        -350, "pre-adjustment HARV 08-19 should be ~-389 bps")
        g = gap_on(harv, "2026-08-19")
        self.assertTrue(gate_t1(harv),
                        f"HARV 2026-08-19 primary gap {g:+.1f} bps not in {T1_BAND}")
        self.assertEqual(harv["worst_daily_gap_date"], "2026-08-19")
        self.assertAlmostEqual(harv["worst_daily_gap_bps"], -61.2, delta=0.1)

    def test_t1_broken_exdates_shifted_one_day(self):
        md = self.panel["HARV"]["model_dates"]
        harv = run("HARV", self.panel, shift_exdates(self.dists, md))
        self.assertFalse(gate_t1(harv),
                         f"shifted ex-dates must NOT land in band; got "
                         f"{gap_on(harv, '2026-08-19'):+.1f}")

    def test_t1_broken_weights_same_day(self):
        md = self.panel["HARV"]["model_dates"]
        harv = run("HARV", self.panel, self.dists,
                   weights=weights_same_day(self.panel["HARV"]["weights"], md))
        self.assertFalse(gate_t1(harv),
                         f"w(t) timing must NOT land in band; got "
                         f"{gap_on(harv, '2026-08-19'):+.1f}")

    # T2 ---------------------------------------------------------------
    def test_t2_clean_exdates_within_3bps(self):
        for e, d in CLEAN:
            pre = gap_on(self.res[e], d, "gap_bps_total_return_basis")
            self.assertTrue(-40 <= pre <= -25, f"{e} {d} pre-adjustment {pre:+.1f}")
        self.assertTrue(gate_t2(self.res),
                        {f"{e} {d}": round(gap_on(self.res[e], d, "gap_bps_price_only_basis"), 2)
                         for e, d in CLEAN})

    def test_t2_broken_amounts_zeroed(self):
        z = zero_amounts(self.dists)
        res = {e: run(e, self.panel, z) for e in ("HG", "HARV")}
        for e, d in CLEAN:
            self.assertGreater(abs(gap_on(res[e], d, "gap_bps_price_only_basis")), 20.0,
                               f"{e} {d} with D=0 must stay a ~30 bps gap")
        self.assertFalse(gate_t2(res))

    # T3 ---------------------------------------------------------------
    def test_t3_non_exdate_invariance_bit_for_bit(self):
        for e, v in self.panel.items():
            tr, px, ledger = dv.price_only_model_returns(
                v["model_dates"], v["model"], v["weights"], self.dists)
            idx = {d: i for i, d in enumerate(v["model_dates"])}
            exempt = {idx[r["applied_on"]] for r in ledger}
            self.assertTrue(exempt, f"{e}: expected at least one applied ex-date")
            self.assertEqual(invariance_violations(tr, px, exempt), [], e)
            for i in exempt:                      # and the term really bit
                self.assertNotEqual(px[i].hex(), tr[i].hex(), (e, i))
            # the PRIMARY model touches only the LEAKED rows
            adj = dv.leak_adjusted_returns(tr, v["model_dates"], ledger)
            leaked = {idx[r["applied_on"]] for r in ledger if r["treatment"] == "LEAKED"}
            self.assertEqual(invariance_violations(tr, adj, leaked), [], e)
            for i in leaked:
                self.assertNotEqual(adj[i].hex(), tr[i].hex(), (e, i))

    def test_t3_broken_term_on_wrong_day_is_detected(self):
        v = self.panel["HARV"]
        tr, px, ledger = dv.price_only_model_returns(
            v["model_dates"], v["model"], v["weights"], self.dists)
        idx = {d: i for i, d in enumerate(v["model_dates"])}
        exempt = {idx[r["applied_on"]] for r in ledger}
        tr2, px2, _ = dv.price_only_model_returns(
            v["model_dates"], v["model"], v["weights"],
            shift_exdates(self.dists, v["model_dates"]))
        self.assertNotEqual(invariance_violations(tr2, px2, exempt), [],
                            "a term landing on a non-ex-date must be caught")

    def test_t3_live_curve_untouched(self):
        for e in self.panel:
            a, b = self.res[e], run(e, self.panel, zero_amounts(self.dists))
            self.assertEqual(a["live_cumulative_return"], b["live_cumulative_return"])
            self.assertEqual(a["live_max_drawdown"], b["live_max_drawdown"])
            self.assertEqual([d["live_ret"] for d in a["daily"]],
                             [d["live_ret"] for d in b["daily"]])

    # T4 ---------------------------------------------------------------
    def test_t4_interface_keys_finite(self):
        for e, r in self.res.items():
            self.assertNotIn("error", r)
            for k in CONSUMER_KEYS + SECONDARY_KEYS:
                self.assertIn(k, r, (e, k))
                self.assertIsInstance(r[k], float, (e, k))
                self.assertTrue(math.isfinite(r[k]), (e, k))
            self.assertIn(r["distribution_data"], ("COMPLETE", "INCOMPLETE"))
            self.assertEqual(r["distribution_data"], "COMPLETE", e)
            self.assertEqual(r["weight_dates_off_calendar"], [], e)
            self.assertIn("distribution_ledger", r)
            self.assertIn("ex_dates", r)
            self.assertEqual(len(r["window"]), 2)
            self.assertEqual(r["n_days"], len(r["daily"]))
            self.assertEqual(r["n_trading_days"], r["n_days"] + 1)
            self.assertIsNone(r["window_start_requested"])

    def test_t4_broken_too_new_returns_error_not_keys(self):
        v = self.panel["HARV"]
        r = dv.analyze_series(v["dates"][:3], v["adj"][:3], v["model_dates"][:3],
                              v["model"][:3], v["weights"], self.dists)
        self.assertIn("error", r)
        self.assertFalse(all(k in r for k in CONSUMER_KEYS))

    # T5 ---------------------------------------------------------------
    def test_t5_missing_held_payer_flags_incomplete(self):
        r = run("HARV", self.panel, without(self.dists, "ZVOL"))
        self.assertEqual(r["distribution_data"], "INCOMPLETE")
        self.assertEqual(r["distribution_missing_tickers"], ["ZVOL"])
        # the primary number is NOT adjusted for the missing payer — the flag
        # is the only thing standing between the reader and the old -389
        self.assertLess(gap_on(r, "2026-08-19"), -350)
        self.assertNotEqual(r["cumulative_gap"], self.res["HARV"]["cumulative_gap"])

    def test_t5_broken_payer_present_but_empty_is_complete(self):
        # fetched-and-paid-nothing is legitimately COMPLETE: the flag must
        # discriminate "not fetched" from "no distributions"
        d = dict(self.dists)
        d["ZVOL"] = {}
        r = run("HARV", self.panel, d)
        self.assertEqual(r["distribution_data"], "COMPLETE")
        self.assertEqual(r["distribution_missing_tickers"], [])
        self.assertLess(gap_on(r, "2026-08-19"), -350)   # still unadjusted...
        self.assertEqual(self.res["HARV"]["distribution_data"], "COMPLETE")
        self.assertTrue(gate_t1(self.res["HARV"]))         # ...unlike the real run

    # T6 ---------------------------------------------------------------
    def test_t6_print_all_engines(self):
        hdr = (f"\n{'engine':7}|{'live cum':>9}|{'mdl TR':>9}|{'mdl adj':>9}|"
               f"{'gap TR':>8}|{'gap new':>8}|{'corr TR':>8}|{'corr new':>9}|"
               f"{'beta':>6}|{'volr':>6}|{'ann TR':>8}|{'ann new':>8}|"
               f"{'ann allx':>9}|{'leak/held':>9}|{'$ model':>8}")
        print(hdr)
        for e, r in self.res.items():
            t = r["distribution_totals"]
            print(f"{e:7}|{r['live_cumulative_return']:>+9.2%}|"
                  f"{r['model_total_return_cumulative']:>+9.2%}|"
                  f"{r['model_cumulative_return']:>+9.2%}|"
                  f"{r['cumulative_gap_total_return_basis']:>+8.2%}|"
                  f"{r['cumulative_gap']:>+8.2%}|"
                  f"{r['daily_return_correlation_total_return_basis']:>8.3f}|"
                  f"{r['daily_return_correlation']:>9.3f}|"
                  f"{r['live_beta_to_model']:>6.2f}|{r['live_model_vol_ratio']:>6.2f}|"
                  f"{r['annualized_gap_total_return_basis']:>+8.1%}|"
                  f"{r['annualized_gap']:>+8.1%}|"
                  f"{r['annualized_gap_all_exdates_stripped']:>+9.1%}|"
                  f"{t['n_leaked']:>4}/{t['n_held_through']:<4}|"
                  f"{t['expected_income_usd']:>8,.0f}")
            for k in CONSUMER_KEYS:
                self.assertTrue(math.isfinite(r[k]), (e, k))

    # T7 (account cross-check) -----------------------------------------
    def test_t7_zvol_0819_entitlement_matches_account_cash_jump(self):
        """Lens 3: ZVOL 08-19 income landed in ACCOUNT unallocated cash on
        08-20 (position closed on the ex-date). The ledger's expected_income
        (HARV + KMLM) must match that independent observation."""
        acct = load_account()["history"]
        a = dict(zip(acct["dates"], acct["series"]))
        def residual(d):
            return a[d] - sum(v["raw"][v["dates"].index(d)] for v in self.panel.values())
        jump = residual("2026-08-20") - residual("2026-08-19")
        self.assertGreater(jump, 1900)
        ledger = sum(x["expected_income_usd"]
                     for e in ("HARV", "KMLM")
                     for x in self.res[e]["distribution_ledger"]
                     if x["ticker"] == "ZVOL" and x["date"] == "2026-08-19")
        print(f"\nZVOL 08-19: ledger entitlement ${ledger:,.2f} vs account cash "
              f"jump 08-20 ${jump:,.2f} (diff {ledger - jump:+.2f})")
        self.assertLess(abs(ledger - jump), 15.0)

    def test_t7_broken_weights_same_day_has_no_entitlement(self):
        tot = 0.0
        for e in ("HARV", "KMLM"):
            md = self.panel[e]["model_dates"]
            r = run(e, self.panel, self.dists,
                    weights=weights_same_day(self.panel[e]["weights"], md))
            tot += sum(x["expected_income_usd"] for x in r["distribution_ledger"]
                       if x["ticker"] == "ZVOL" and x["date"] == "2026-08-19")
        self.assertLess(tot, 1000.0, "w(t) timing must miss the $1,970 entitlement")

    # T8 (consumer keys pinned) ----------------------------------------
    def test_t8_consumer_keys_pinned_per_engine(self):
        bad = gate_t8(self.res)
        self.assertEqual(bad, [], f"consumer keys drifted from add. 38: {bad}")
        # orientation: HG live beat its model (sign of the gap), beta/vol > 0
        self.assertGreater(self.res["HG"]["live_cumulative_return"],
                           self.res["HG"]["model_cumulative_return"])
        self.assertGreater(self.res["HG"]["annualized_gap"], 0)
        # primary != total-return basis: the HARV false-fail must be visible
        # as a difference, with both sides at their known values
        for e, (corr_tr, ann_tr) in PINNED_TR.items():
            r = self.res[e]
            self.assertAlmostEqual(r["daily_return_correlation_total_return_basis"],
                                   corr_tr, delta=0.0015, msg=e)
            self.assertAlmostEqual(r["annualized_gap_total_return_basis"],
                                   ann_tr, delta=0.0006, msg=e)
        h = self.res["HARV"]
        self.assertGreater(h["daily_return_correlation"]
                           - h["daily_return_correlation_total_return_basis"], 0.7)
        self.assertGreater(h["annualized_gap"] - h["annualized_gap_total_return_basis"], 0.15)

    def test_t8_broken_raw_series_as_live_fails_pins(self):
        """The fixture carries raw and deposit-adjusted. Deposit days
        (08-17, 08-25: the account-cash redeploys) are ~0 on adj and >+70 bps
        on raw; feeding raw must blow every pin."""
        res = {e: run(e, self.panel, self.dists, live=self.panel[e]["raw"])
               for e in self.panel}
        bad = gate_t8(res)
        self.assertGreaterEqual(len(bad), 4 * 3, bad)
        for e in ("HG", "SLEEVE", "HARV"):
            # 08-25: the $1,970 ZVOL cash redeploy lands as a 'deposit' of
            # +859/+502/+611 -> raw minus adj return is the deposit in bps;
            # on the next (plain) day the two series move identically
            dep = (row_on(res[e], "2026-08-25")["live_ret"]
                   - row_on(self.res[e], "2026-08-25")["live_ret"]) * 1e4
            self.assertGreater(dep, 60.0, (e, dep))
            plain = (row_on(res[e], "2026-08-26")["live_ret"]
                     - row_on(self.res[e], "2026-08-26")["live_ret"]) * 1e4
            self.assertLess(abs(plain), 0.5, (e, plain))
        self.assertLess(res["HG"]["daily_return_correlation"], 0.2)

    # T9 (second moments not carried by one shared ex-date artefact) ---
    def test_t9_harv_corr_not_carried_by_single_exdate(self):
        ok, c_all, c_x = gate_t9(self.res["HARV"])
        self.assertTrue(ok, f"HARV corr all {c_all:.3f} vs excl 08-19 {c_x:.3f}")
        # and the consumer key is this pair, not the artefact pair
        self.assertAlmostEqual(self.res["HARV"]["daily_return_correlation"], c_all, places=3)
        # the artefact pair (live price vs model price-only) IS carried by it:
        # this is the 0.946 the panel refused as tracking evidence
        rows = self.res["HARV"]["daily"]
        a_all = moments(rows, "live_ret", "model_ret_price_only")[0]
        a_x = moments([d for d in rows if d["date"] != "2026-08-19"],
                      "live_ret", "model_ret_price_only")[0]
        self.assertGreater(a_all, 0.93)
        self.assertGreater(a_all - a_x, ONE_POINT_TOL)
        self.assertAlmostEqual(a_x, c_x, delta=0.01)    # without 08-19 both agree
        # Op2/Op3 engines are insensitive to the pair (payer weights small)
        for e in ("KMLM", "SLEEVE"):
            r = self.res[e]
            m = moments(r["daily"], "live_ret", "model_ret_price_only")
            self.assertAlmostEqual(r["daily_return_correlation"], m[0], delta=0.002, msg=e)
            self.assertAlmostEqual(r["live_beta_to_model"], m[1], delta=0.003, msg=e)

    def test_t9_broken_zvol_amount_doubled_is_one_point_driven(self):
        harv = run("HARV", self.panel, scale_amount(self.dists, "ZVOL", 2.0))
        ok, c_all, c_x = gate_t9(harv)
        self.assertFalse(ok, f"a wrong term must show up as a one-point swing "
                             f"({c_all:.3f} vs {c_x:.3f})")
        self.assertLess(harv["daily_return_correlation"], 0.82)

    # T10 (leak / held-through classifier vs the cash trail) -----------
    def test_t10_classifier_matches_lens3_cash_trail(self):
        seen = {}
        for e, r in self.res.items():
            for x in r["distribution_ledger"]:
                if x["date"] >= "2026-07-22":          # valid regime (all 4 live)
                    seen[(e, x["date"], x["ticker"])] = x["treatment"]
        for key in LENS3_HELD:
            self.assertEqual(seen.get(key), "HELD_THROUGH", key)
        for key in LENS3_LEAKED:
            self.assertEqual(seen.get(key), "LEAKED", key)
        for key in MODEL_ONLY:                         # documented miss
            self.assertEqual(seen.get(key), "LEAKED", key)
        self.assertEqual(set(seen), LENS3_HELD | LENS3_LEAKED | MODEL_ONLY)
        # independent confirmation of every LEAKED label that live actually
        # held: the account residual (value - sum of symphonies) jumps by the
        # entitlement within ex+1..ex+8 (ZVOL ex+1, BIL ex+3, TMV ex+5)
        acct = load_account()["history"]
        a = dict(zip(acct["dates"], acct["series"]))
        dates = [d for d in acct["dates"] if all(d in v["dates"] for v in self.panel.values())]
        def residual(d):
            return a[d] - sum(v["raw"][v["dates"].index(d)] for v in self.panel.values())
        pooled = {}                                    # (date, ticker) -> $ across engines
        for e, r in self.res.items():
            for x in r["distribution_ledger"]:
                if (e, x["date"], x["ticker"]) in LENS3_LEAKED:
                    pooled[(x["date"], x["ticker"])] = (
                        pooled.get((x["date"], x["ticker"]), 0.0) + x["expected_income_usd"])
        self.assertEqual(len(pooled), 3)
        for (ex, t), usd in pooled.items():
            i = dates.index(ex)
            jumps = [residual(d) - residual(dates[dates.index(d) - 1]) for d in dates[i + 1:i + 9]]
            self.assertLess(abs(max(jumps) - usd) / usd, 0.03, (ex, t, max(jumps), usd))
        # the model-only TLT row has NO cash jump (live never held it)
        i = dates.index("2026-09-01")
        jumps = [residual(d) - residual(dates[dates.index(d) - 1]) for d in dates[i + 1:i + 9]]
        self.assertLess(max(jumps), 50.0)
        # the bias the primary removes vs the all-stripped reference
        # HG re-derived for the per-fund table: BIL 04-01 (28.8 bps) now stays
        # in the primary model, so the all-stripped reference is lenient by it
        # too (0.0061 -> 0.0096)
        for e, lo, hi in (("KMLM", 0.009, 0.012), ("SLEEVE", 0.008, 0.011),
                          ("HARV", 0.040, 0.050), ("HG", 0.008, 0.011)):
            b = self.res[e]["held_through_credit_bias_annualized"]
            self.assertTrue(lo <= b <= hi, (e, b))

    def test_t10_broken_model_edited_to_hold_zvol_flips_label_and_gate(self):
        v = self.panel["HARV"]
        w = weights_held_through(v["weights"], "ZVOL", "2026-08-19", v["model_dates"])
        r = run("HARV", self.panel, self.dists, weights=w)
        self.assertEqual([x["treatment"] for x in r["distribution_ledger"]
                          if x["ticker"] == "ZVOL"], ["HELD_THROUGH"])
        self.assertFalse(gate_t1(r), gap_on(r, "2026-08-19"))     # -389 is back
        self.assertLess(r["annualized_gap"], -0.10)

    def test_t10_broken_model_edited_to_exit_puls_flips_label(self):
        v = self.panel["HARV"]
        w = weights_exit_at_ex(v["weights"], "PULS", "2026-08-31", v["model_dates"])
        r = run("HARV", self.panel, self.dists, weights=w)
        self.assertEqual(next(x["treatment"] for x in r["distribution_ledger"]
                              if x["ticker"] == "PULS" and x["date"] == "2026-08-31"),
                         "LEAKED")
        self.assertLess(abs(gap_on(r, "2026-08-31")), 3.0)
        self.assertLess(abs(gap_on(self.res["HARV"], "2026-08-31") + 35.6), 0.5)

    # T11 (model reproduction: convention + timing + cost, lens 2) -----
    def test_t11_model_reproduced_from_weights_x_yahoo_close(self):
        for e, v in self.panel.items():
            s = model_reproduction(self.panel, self.yahoo, e, v["weights"], self.dists)
            self.assertTrue(gate_t11(s), (e, s))

    def test_t11_broken_additive_convention_fails_on_high_yield(self):
        add = additive_convention(self.dists)
        s = model_reproduction(self.panel, self.yahoo, "HARV", self.panel["HARV"]["weights"], add)
        self.assertFalse(gate_t11(s), ("HARV additive", s))
        self.assertGreater(s[2], 5.0)                  # ZVOL 08-19: w*y*r_adj ~ 7 bps
        for e in ("KMLM", "SLEEVE"):
            s = model_reproduction(self.panel, self.yahoo, e, self.panel[e]["weights"], add)
            self.assertFalse(gate_t11(s), (e, s))

    def test_t11_broken_timing_and_cost(self):
        v = self.panel["HARV"]
        wsame = weights_same_day(v["weights"], v["model_dates"])
        s = model_reproduction(self.panel, self.yahoo, "HARV", wsame, self.dists)
        self.assertFalse(gate_t11(s), ("w(t)", s))
        self.assertGreater(s[1], 20.0)
        for e in self.panel:
            s = model_reproduction(self.panel, self.yahoo, e, self.panel[e]["weights"],
                                   self.dists, cost=False)
            self.assertFalse(gate_t11(s), (e, "no cost", s))
            self.assertGreater(s[1], 1.5)

    # T12 (calendar gap compounding) -----------------------------------
    def test_t12_live_calendar_gap_compounds_model_returns(self):
        v = self.panel["HARV"]
        ld, la = drop_live_date(self.panel, "HARV", "2026-09-10")
        r = run("HARV", self.panel, self.dists, live=la, live_dates=ld)
        self.assertEqual(r["n_days"], self.res["HARV"]["n_days"] - 1)
        m = dict(zip(v["model_dates"], v["model"]))
        got = row_on(r, "2026-09-11")["model_ret_total_return"]
        self.assertAlmostEqual(got, m["2026-09-11"] / m["2026-09-09"] - 1, places=12)
        single = m["2026-09-11"] / m["2026-09-10"] - 1
        self.assertGreater(abs(got - single), 1e-4)    # dropping would differ

    # T13 (cumulative / daily consistency) -----------------------------
    def test_t13_cumulative_consistent_with_daily(self):
        for e, r in self.res.items():
            f_l = f_m = 1.0
            for d in r["daily"]:
                f_l *= 1 + d["live_ret"]
                f_m *= 1 + d["model_ret"]
            self.assertAlmostEqual(f_l - 1, r["live_cumulative_return"], delta=0.0001, msg=e)
            self.assertAlmostEqual(f_m - 1, r["model_cumulative_return"], delta=0.0001, msg=e)
            self.assertAlmostEqual(r["cumulative_gap"],
                                   r["live_cumulative_return"] - r["model_cumulative_return"],
                                   delta=0.00011, msg=e)
            gaps = [d["gap_bps"] for d in r["daily"]]
            self.assertAlmostEqual(sum(gaps) / len(gaps), r["mean_daily_gap_bps"],
                                   delta=0.006, msg=e)
            self.assertAlmostEqual(r["annualized_gap"], r["mean_daily_gap_bps"] / 1e4 * 252,
                                   delta=0.0002, msg=e)
            self.assertAlmostEqual(min(gaps), r["worst_daily_gap_bps"], delta=0.06, msg=e)
            # side-invariance identity: lr - mr_px == lr_tr - mr_tr
            for d in r["daily"]:
                self.assertAlmostEqual(d["live_ret"] - d["model_ret_price_only"],
                                       d["live_ret_total_return"] - d["model_ret_total_return"],
                                       places=12)

    # T14 (weight keyed off the model calendar) ------------------------
    def test_t14_weight_date_off_calendar_flags_incomplete(self):
        v = self.panel["HARV"]
        i = v["model_dates"].index("2026-08-18")
        md = v["model_dates"][:i] + v["model_dates"][i + 1:]
        mv = v["model"][:i] + v["model"][i + 1:]
        r = dv.analyze_series(v["dates"], v["adj"], md, mv, v["weights"], self.dists,
                              live_raw=v["raw"], symphony="HARV", name="HARV", detail=True)
        self.assertEqual(r["distribution_data"], "INCOMPLETE")
        self.assertIn(["ZVOL", "2026-08-18"], r["weight_dates_off_calendar"])
        self.assertLess(gap_on(r, "2026-08-19"), -350)   # the term was NOT applied
        self.assertEqual(self.res["HARV"]["weight_dates_off_calendar"], [])

    # T15 (analyze(): the I/O path monitor.py calls) -------------------
    def _mock_composer(self, engine):
        v = self.panel[engine]
        epoch = dt.date(1970, 1, 1)
        def to_ms(d): return (dt.date.fromisoformat(d) - epoch).days * 86400000
        def to_day(d): return (dt.date.fromisoformat(d) - epoch).days
        def fake_get(path, **kw):
            return {"epoch_ms": [to_ms(d) for d in v["dates"]],
                    "series": v["raw"], "deposit_adjusted_series": v["adj"]}
        def fake_bt(sid, start=None, end=None, **kw):
            assert start == v["dates"][0] and end == v["dates"][-1]
            return {"legend": {sid: {"name": engine}},
                    "dvm_capital": {sid: {str(to_day(d)): x
                                          for d, x in zip(v["model_dates"], v["model"])}},
                    "tdvm_weights": {t: {str(to_day(d)): w for d, w in dd.items()}
                                     for t, dd in v["weights"].items()}}
        return fake_get, fake_bt

    def _with_mocks(self, engine, fail=(), detail=False):
        fake_get, fake_bt = self._mock_composer(engine)
        saved = (cl.get, cl.backtest_by_id, dv.fetch_yahoo_chart)
        cl.get, cl.backtest_by_id = fake_get, fake_bt
        dv.fetch_yahoo_chart = lambda t: None if t in fail else self.yahoo[t]
        try:
            r = dv.analyze("acct", engine, engine, detail=detail)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                dv.show(r)
            return r, buf.getvalue()
        finally:
            cl.get, cl.backtest_by_id, dv.fetch_yahoo_chart = saved

    def test_t15_analyze_equals_analyze_series_on_consumer_keys(self):
        for e in self.panel:
            r, out = self._with_mocks(e)
            self.assertNotIn("error", r)
            self.assertEqual(r["distribution_data"], "COMPLETE", e)
            for k in CONSUMER_KEYS + SECONDARY_KEYS:
                self.assertEqual(r[k], self.res[e][k], (e, k))
            self.assertNotIn("INCOMPLETE", out)
            self.assertEqual(gate_t8({e: r} | {x: self.res[x] for x in self.res if x != e}), [])

    def test_t15_broken_yahoo_failure_for_one_payer_is_loud(self):
        r, out = self._with_mocks("HARV", fail={"ZVOL"})
        self.assertEqual(r["distribution_data"], "INCOMPLETE")
        self.assertEqual(r["distribution_missing_tickers"], ["ZVOL"])
        self.assertIn("DISTRIBUTION DATA INCOMPLETE", out)
        self.assertIn("ZVOL", out.split("INCOMPLETE")[1][:120])
        self.assertIn("Do not read a gate verdict", out)
        self.assertEqual(r["worst_daily_gap_date"], "2026-08-19")
        self.assertLess(r["worst_daily_gap_bps"], -350)
        self.assertLess(r["daily_return_correlation"], 0.2)   # the add.-36 false fail

    def test_t15_failed_fetch_is_not_cached(self):
        saved = urllib.request.urlopen
        def boom(*a, **k):
            raise OSError("no network")
        urllib.request.urlopen = boom
        try:
            dv._YAHOO_CACHE.pop("ZZZNOTATICKER", None)
            self.assertIsNone(dv.fetch_yahoo_chart("ZZZNOTATICKER"))
            self.assertNotIn("ZZZNOTATICKER", dv._YAHOO_CACHE)
        finally:
            urllib.request.urlopen = saved

    def test_t15_cache_hit_serves_analyze_without_network(self):
        """The real fetch_yahoo_chart must serve a cached chart (what --all
        and the gauge-RED sweep rely on) — with the network dead, a
        pre-populated cache still yields a COMPLETE result equal to the
        pure-math run."""
        fake_get, fake_bt = self._mock_composer("HARV")
        saved = (cl.get, cl.backtest_by_id, urllib.request.urlopen, dict(dv._YAHOO_CACHE))
        def boom(*a, **k):
            raise OSError("no network")
        cl.get, cl.backtest_by_id, urllib.request.urlopen = fake_get, fake_bt, boom
        dv._YAHOO_CACHE.clear()
        try:
            for t in ("PULS", "VXZ", "ZVOL"):
                self.assertIsNone(dv.fetch_yahoo_chart(t))      # network dead
                dv._YAHOO_CACHE[t] = self.yahoo[t]
                self.assertIs(dv.fetch_yahoo_chart(t), self.yahoo[t])
            r = dv.analyze("acct", "HARV", "HARV")
            self.assertEqual(r["distribution_data"], "COMPLETE")
            for k in CONSUMER_KEYS:
                self.assertEqual(r[k], self.res["HARV"][k], k)
        finally:
            cl.get, cl.backtest_by_id, urllib.request.urlopen = saved[:3]
            dv._YAHOO_CACHE.clear()
            dv._YAHOO_CACHE.update(saved[3])

    def test_t15_broken_missing_deposit_adjusted_is_error_not_raw(self):
        """Composer response without deposit_adjusted_series: analyze() must
        return an error (monitor -> 'diagnostic unavailable'), never silently
        analyze the raw $ series (HARV would read corr 0.22 / +46%/yr and
        report COMPLETE — panel finding, lens 1)."""
        fake_get, fake_bt = self._mock_composer("HARV")
        def get_without(path, **kw):
            d = fake_get(path, **kw)
            d.pop("deposit_adjusted_series")
            return d
        saved = (cl.get, cl.backtest_by_id, dv.fetch_yahoo_chart)
        cl.get, cl.backtest_by_id = get_without, fake_bt
        dv.fetch_yahoo_chart = lambda t: self.yahoo[t]
        try:
            r = dv.analyze("acct", "HARV", "HARV")
        finally:
            cl.get, cl.backtest_by_id, dv.fetch_yahoo_chart = saved
        self.assertIn("error", r)
        self.assertIn("deposit_adjusted_series", r["error"])
        for k in CONSUMER_KEYS:
            self.assertNotIn(k, r)
        # the broken path it replaces: raw fed as live is a wrong COMPLETE number
        raw = run("HARV", self.panel, self.dists, live=self.panel["HARV"]["raw"])
        self.assertEqual(raw["distribution_data"], "COMPLETE")
        self.assertLess(raw["daily_return_correlation"], 0.5)
        self.assertGreater(raw["annualized_gap"], 0.3)

    def test_t15_analyze_uses_deposit_adjusted_not_raw(self):
        """Through the I/O path the live daily returns must be the
        deposit-adjusted ones (identical to the pure-math run on adj) and
        must NOT carry the 08-25 redeploy that the raw series shows."""
        for e in ("HG", "SLEEVE", "HARV"):
            r, _ = self._with_mocks(e, detail=True)
            self.assertEqual([d["live_ret"] for d in r["daily"]],
                             [d["live_ret"] for d in self.res[e]["daily"]], e)
            raw = run(e, self.panel, self.dists, live=self.panel[e]["raw"])
            dep = (row_on(raw, "2026-08-25")["live_ret"]
                   - row_on(r, "2026-08-25")["live_ret"]) * 1e4
            self.assertGreater(dep, 60.0, (e, dep))

    # T16 (Yahoo wire format: the REAL fetch_yahoo_chart success path) ----
    def wire_gate(self, mutate=None):
        """Serve Yahoo-shaped responses (built from the fixture, optionally
        mutated) through a patched urlopen, run the REAL fetch_yahoo_chart +
        dists_from_chart and the mocked-Composer analyze(). Returns
        (failures, harv_result); failures == [] is a pass."""
        def fake_urlopen(rq, timeout=None):
            url = rq.full_url if hasattr(rq, "full_url") else rq
            t = url.split("/chart/")[1].split("?")[0]
            w = to_wire(self.yahoo[t])
            return io.BytesIO(json.dumps(mutate(w) if mutate else w).encode())
        fake_get, fake_bt = self._mock_composer("HARV")
        saved = (cl.get, cl.backtest_by_id, urllib.request.urlopen, dict(dv._YAHOO_CACHE))
        cl.get, cl.backtest_by_id, urllib.request.urlopen = fake_get, fake_bt, fake_urlopen
        dv._YAHOO_CACHE.clear()
        bad = []
        try:
            for t in WIRE_TICKERS:
                chart = dv.fetch_yahoo_chart(t)
                if chart is None:
                    bad.append((t, "fetch -> None (INCOMPLETE)"))
                    continue
                got, want = dv.dists_from_chart(chart), self.dists[t]
                if sorted(got) != sorted(want):
                    bad.append((t, "ex-dates", sorted(set(got) ^ set(want))[:4]))
                    continue
                for ex in want:
                    for f in ("amount", "prev_close", "adj_ret", "px_ret"):
                        if abs(got[ex][f] - want[ex][f]) > 1e-12:
                            bad.append((t, ex, f, got[ex][f], want[ex][f]))
            dv._YAHOO_CACHE.clear()
            r = dv.analyze("acct", "HARV", "HARV")
        finally:
            cl.get, cl.backtest_by_id, urllib.request.urlopen = saved[:3]
            dv._YAHOO_CACHE.clear()
            dv._YAHOO_CACHE.update(saved[3])
        if r["distribution_data"] != "COMPLETE":
            bad.append(("HARV", r["distribution_data"], r["distribution_missing_tickers"]))
        bad += [("HARV pin",) + b for b in gate_t8({"HARV": r}, engines=("HARV",))]
        return bad, r

    def test_t16_yahoo_wire_round_trip_reproduces_fixture_and_pins(self):
        bad, r = self.wire_gate()
        self.assertEqual(bad, [])
        for k in CONSUMER_KEYS + SECONDARY_KEYS:
            self.assertEqual(r[k], self.res["HARV"][k], k)

    def test_t16_broken_wire_mutants_fail(self):
        for name, mutate in WIRE_BROKEN.items():
            bad, r = self.wire_gate(mutate)
            print(f"\n  wire mutant {name!r}: {len(bad)} failure(s), HARV "
                  f"{r['distribution_data']} corr {r.get('daily_return_correlation')} "
                  f"ann {r.get('annualized_gap')}; first: {bad[:1]}")
            self.assertNotEqual(bad, [], f"wire mutant {name!r} passed the gate")
            if name in ("adjclose missing", "half bar (adjclose None)"):
                # refused, never a price-only COMPLETE
                self.assertEqual(r["distribution_data"], "INCOMPLETE", name)
                self.assertEqual(r["distribution_missing_tickers"], ["PULS", "VXZ", "ZVOL"])
        # the two that silently reproduced the add.-36 false alarm are now caught
        for name in ("dividends dropped", "dividend date +1 day"):
            bad, r = self.wire_gate(WIRE_BROKEN[name])
            self.assertEqual(r["distribution_data"], "COMPLETE", name)
            self.assertLess(r["daily_return_correlation"], 0.2, name)

    # T17 (per-fund PAY_LAG classifier — panel condition C2) -------------
    def test_t17_pay_lag_table_matches_fixture_credits(self):
        """Each lag in the table is the ticker's OWN observed credit, found in
        the fixtures on ex+L: cash credits (ZVOL ex+1, BIL ex+3, SSO ex+4
        across Christmas 2025, TMV ex+5) in the account residual, in-symphony
        recredits (PULS ex+2, BIL ex+3, TQQQ ex+4, LABD ex+5) as the unique
        live-only +w*y day in the primary gap. No n=0 (family-inherited)
        entry; the removed tickers stay out."""
        self.assertEqual(dv.MAX_PAY_LAG, 5)
        self.assertEqual(sorted(dv.PAY_LAG),
                         ["BIL", "LABD", "PULS", "SSO", "TMV", "TQQQ", "ZVOL"])
        self.assertEqual([t for t, (_, n) in dv.PAY_LAG.items() if n < 1], [])
        for t in NOT_OBSERVED:
            self.assertNotIn(t, dv.PAY_LAG)
        self.assertEqual(gate_t17_lag_evidence(self.panel, self.dists, dv.PAY_LAG), [])
        # SSO's own event, read directly: HG held 17.393 sh at the 2025-12-24
        # open; account residual +2.00 on 12-31 = ex+4 trading days
        hg = next(x for x in self.res["HG"]["distribution_ledger"]
                  if x["ticker"] == "SSO" and x["date"] == "2025-12-24")
        self.assertAlmostEqual(hg["expected_income_usd"], 17.393243067 * 0.116, delta=0.01)
        self.assertEqual(dv.PAY_LAG["SSO"], (4, 1))

    def test_t17_broken_lag_table_shifted_fails_evidence(self):
        for delta in (+1, -1):
            miss = gate_t17_lag_evidence(self.panel, self.dists, shifted_lag_table(delta))
            self.assertGreaterEqual(len(miss), 5, (delta, miss))

    def test_t17_broken_soxl_or_inherited_lags_readded_fail(self):
        """Re-adding SOXL (its 2.6 bps term is below the 3-bps match
        tolerance, and the candidate days ex+1 and ex+5 = 09-29, a
        decision-divergence day, are noisy: not identified)
        or any n=0 family-inherited entry must fail — under part 1 all 48
        tests passed with them in."""
        for lag in (1, 3, 5):
            # as an inherited/unobserved entry: n=0, no event
            miss = gate_t17_lag_evidence(self.panel, self.dists, lag_table(SOXL=lag))
            self.assertIn(("n=0 (inherited, not observed)", "SOXL", lag), miss)
            self.assertIn(("no identified own event in the fixtures", "SOXL", lag), miss)
            # claimed as observed with an event: the event does not identify
            for claim in (("recredit", "KMLM", "2026-09-22"),
                          ("cash", "2026-09-22", ("KMLM",))):
                tbl = {**dv.PAY_LAG, "SOXL": (lag, 1)}
                miss = gate_t17_lag_evidence(self.panel, self.dists, tbl,
                                             {**LAG_EVIDENCE, "SOXL": [claim]})
                self.assertTrue(miss and all(m[1] == "SOXL" for m in miss), (lag, claim, miss))
            print(f"\n  SOXL lag {lag}: {miss[0]}")
        for t, lag in (("QLD", 4), ("UDOW", 4), ("TECL", 5), ("TNA", 5)):
            miss = gate_t17_lag_evidence(self.panel, self.dists, lag_table(**{t: lag}))
            self.assertIn(("n=0 (inherited, not observed)", t, lag), miss)

    def test_t17_removed_lags_flip_nothing_on_frozen_panel(self):
        """Dropping SOXL/QLD/UDOW/TECL/TNA from the table (unknown-lag path)
        changes no label, no AMBIGUOUS status and no primary key on any engine:
        KMLM SOXL 09-22 was held ex..ex+4 (HELD_THROUGH for any lag <= 5), HG
        TNA 2025-12-23 / 2026-06-23 were sold at the ex-date close (LEAKED for
        any lag); QLD/UDOW/TECL ex-dates were never held into."""
        part1 = {**dv.PAY_LAG, "SOXL": (5, 1), "QLD": (4, 0), "UDOW": (4, 0),
                 "TECL": (5, 0), "TNA": (5, 0)}
        old = {e: run(e, self.panel, self.dists, pay_lag=part1) for e in self.panel}
        self.assertEqual(labels(old, since=""), labels(self.res, since=""))
        for e in self.panel:
            self.assertEqual(self.res[e]["ambiguous_rows"], [], e)
            for k in CONSUMER_KEYS + SECONDARY_KEYS:
                self.assertEqual(old[e][k], self.res[e][k], (e, k))
        moved = sorted((e, x["date"], x["ticker"]) for e in self.panel
                       for x, y in zip(self.res[e]["distribution_ledger"],
                                       old[e]["distribution_ledger"])
                       if x["pay_lag_bd"] != y["pay_lag_bd"])
        self.assertEqual(moved, [("HG", "2025-12-23", "TNA"), ("HG", "2026-06-23", "TNA"),
                                 ("KMLM", "2026-09-22", "SOXL")])

    def test_t17a_no_cash_trail_label_flips_on_frozen_panel(self):
        new = labels(self.res)
        for key, old in OLD_RULE_LABELS.items():
            self.assertEqual(new.get(key), old, key)
        self.assertEqual(new[("KMLM", "2026-09-01", "TLT")], "LEAKED")
        self.assertEqual(set(new), set(OLD_RULE_LABELS) | MODEL_ONLY)
        # the old rule as an INPUT (uniform lag 5 = ex..ex+4) reproduces the
        # committed add.-38 results; across the WHOLE panel exactly one row
        # differs, and it is the pre-edit model-only HG BIL 04-01
        u5 = {t: (5, 0) for t in self.dists}
        old_res = {e: run(e, self.panel, self.dists, pay_lag=u5) for e in self.panel}
        a, b = labels(old_res, since=""), labels(self.res, since="")
        flips = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
        self.assertEqual(flips, EXPECTED_FLIPS)
        self.assertEqual(gate_t8(old_res, engines=("KMLM", "SLEEVE", "HARV")), [])
        for k, pin, tol in zip(PIN_KEYS, PINNED_FUND_AGNOSTIC_HG, PIN_TOL):
            self.assertLess(abs(old_res["HG"][k] - pin), tol, k)
        # and the HG re-pin is that one row: force it LEAKED (input: the model
        # sold BIL at the 04-01 close) and the old HG numbers come back
        v = self.panel["HG"]
        hg = run("HG", self.panel, self.dists,
                 weights=weights_exit_at_ex(v["weights"], "BIL", "2026-04-01", v["model_dates"]))
        for k in PIN_KEYS:
            self.assertEqual(hg[k], old_res["HG"][k], k)

    def test_t17a_broken_uniform_lag_1_flips_cash_trail_labels(self):
        new = labels({e: run(e, self.panel, self.dists,
                             pay_lag={t: (1, 0) for t in self.dists}) for e in self.panel})
        flipped = {k for k, old in OLD_RULE_LABELS.items() if new.get(k) != old}
        self.assertEqual(flipped, {("HG", "2026-08-03", "BIL"),
                                   ("SLEEVE", "2026-09-22", "TMV")})

    def test_t17b_zvol_short_hold_is_held_through(self):
        v = self.panel["HARV"]
        r = run("HARV", self.panel, self.dists, weights=extend_zvol_hold(v["weights"]))
        self.assertTrue(gate_t17b_zvol_short_hold(r),
                        [(x["ticker"], x["treatment"], x["subtracted_bps"])
                         for x in r["distribution_ledger"]])
        z = next(x for x in r["distribution_ledger"] if x["ticker"] == "ZVOL")
        self.assertEqual((z["pay_lag_bd"], z["held_days_from_ex"]), (1, 1))
        self.assertEqual(r["distribution_totals"]["subtracted_bps"], 0.0)
        self.assertLess(gap_on(r, "2026-08-19"), -350)   # live's dip, re-credited 08-20
        self.assertEqual(r["ambiguous_rows"], [])

    def test_t17b_broken_zvol_forced_lag_5_is_leaked(self):
        v = self.panel["HARV"]
        r = run("HARV", self.panel, self.dists, weights=extend_zvol_hold(v["weights"]),
                pay_lag=lag_table(ZVOL=5))
        self.assertFalse(gate_t17b_zvol_short_hold(r))
        self.assertEqual(next(x["treatment"] for x in r["distribution_ledger"]
                              if x["ticker"] == "ZVOL"), "LEAKED")

    def _unknown_case(self, pay_lag=None):
        v = self.panel["HARV"]
        w, d = rename_ticker(extend_zvol_hold(v["weights"]), self.dists, "ZVOL", "ZZZZ")
        r = run("HARV", self.panel, d, weights=w, pay_lag=pay_lag)
        strict = run("HARV", self.panel, self.dists, weights=extend_zvol_hold(v["weights"]))
        return r, shown(r), strict

    def test_t17c_unknown_lag_short_hold_is_ambiguous_strict(self):
        r, out, strict = self._unknown_case()
        self.assertEqual(gate_t17c_ambiguous(r, out, strict, self.res["HARV"]), [])
        self.assertEqual(r["distribution_data"], "COMPLETE")
        # strict reads LOWER than lenient (the safe direction for a pass/fail gate)
        self.assertLess(r["annualized_gap"], r["annualized_gap_ambiguous_lenient"])
        print("\n" + next(ln for ln in out.splitlines() if "AMBIGUOUS: ZZZZ" in ln).strip())
        # the 'any lag' sides of the unknown-lag rule are decided, not ambiguous
        v = self.panel["HARV"]
        w, d = rename_ticker(v["weights"], self.dists, "ZVOL", "ZZZZ")
        exited = run("HARV", self.panel, d, weights=w)        # sold for the ex-date
        self.assertEqual([x["treatment"] for x in exited["distribution_ledger"]
                          if x["ticker"] == "ZZZZ"], ["LEAKED"])
        w5 = weights_held_through(w, "ZZZZ", "2026-08-19", v["model_dates"])
        held = run("HARV", self.panel, d, weights=w5)         # held ex..ex+4
        self.assertEqual([x["treatment"] for x in held["distribution_ledger"]
                          if x["ticker"] == "ZZZZ"], ["HELD_THROUGH"])
        self.assertEqual(exited["ambiguous_rows"] + held["ambiguous_rows"], [])

    def test_t17c_broken_guessed_lag_fails(self):
        r, out, strict = self._unknown_case(pay_lag=lag_table(ZZZZ=5))
        bad = gate_t17c_ambiguous(r, out, strict, self.res["HARV"])
        self.assertNotEqual(bad, [])
        self.assertEqual(bad[0], ("treatment", ["LEAKED"]))
        self.assertNotIn("!! AMBIGUOUS", out)

    def test_t17d_window_end_clip_is_credit_pending(self):
        self.assertEqual(gate_t17d_pending(self.panel, self.dists), [])
        # HARV PULS 08-31 window-end case: ending 09-01 (ex+1) the credit
        # (09-02) is not in yet -> pending, and the primary gap carries the
        # -w*y dip; ending 09-02 the recredit is in and the dip cancels
        a = run("HARV", self.panel, self.dists, end="2026-09-01")
        b = run("HARV", self.panel, self.dists, end="2026-09-02")
        ra = next(x for x in a["distribution_ledger"] if x["date"] == "2026-08-31")
        rb = next(x for x in b["distribution_ledger"] if x["date"] == "2026-08-31")
        self.assertEqual((ra["credit_pending"], ra["days_in_window_from_ex"]), (True, 2))
        self.assertEqual((rb["credit_pending"], rb["days_in_window_from_ex"]), (False, 3))
        self.assertIn("!! 1 ledger row(s) credit pending", shown(a))
        self.assertNotIn("credit pending", shown(b))
        print(f"\n  HARV window to 09-01: ann {a['annualized_gap']:+.2%}/yr (pending); "
              f"to 09-02: {b['annualized_gap']:+.2%}/yr")
        self.assertLess(a["annualized_gap"] - b["annualized_gap"], -0.02)
        # the frozen panel's 09-30 PULS rows: L=2, credit 10-02 = window end
        for e in ("HARV", "KMLM"):
            x = next(y for y in self.res[e]["distribution_ledger"] if y["date"] == "2026-09-30")
            self.assertEqual((x["held_days_checked"], x["days_in_window_from_ex"],
                              x["credit_pending"]), (2, 3, False))
        # nothing on the frozen panel is pending
        self.assertFalse(any(x["credit_pending"] for r in self.res.values()
                             for x in r["distribution_ledger"]))

    def test_t17d_broken_part1_rule_fails_profiles(self):
        """RULE mutant: classify_hold swapped for the part-1 body (pending =
        span < L). It drops the flag on the window ending ex+L-1 (HARV PULS
        ending 09-01, HG BIL ending 09-03, ZVOL ending on the ex-date)."""
        saved = dv.classify_hold
        dv.classify_hold = classify_hold_part1
        try:
            bad = gate_t17d_pending(self.panel, self.dists)
            a = run("HARV", self.panel, self.dists, end="2026-09-01")
        finally:
            dv.classify_hold = saved
        self.assertEqual(sorted(k for k, _ in bad), sorted(EXPECTED_PENDING))
        for k, diffs in bad:
            self.assertEqual(len(diffs), 1, (k, diffs))   # exactly the ex+L-1 window
            print(f"\n  part-1 rule: {k} window ex+{diffs[0][0]} -> {diffs[0]}")
        self.assertNotIn("credit pending", shown(a))

    def test_t17d_broken_forced_lag_changes_pending_profile(self):
        got = pending_profile(self.panel, self.dists, "HARV", "2026-08-31", "PULS", 4,
                              table=lag_table(PULS=5))
        self.assertNotEqual(got, EXPECTED_PENDING[("HARV", "2026-08-31", "PULS")])

    # T18 (--start window: Op2 reads the sleeve from 2026-08-01) ----------
    def test_t18_sleeve_from_0801_pinned_and_independent(self):
        r = run("SLEEVE", self.panel, self.dists, start=OP2_START)
        self.assertEqual(gate_t18_start(r, self.panel, "SLEEVE", OP2_START,
                                        self.res["SLEEVE"]), [])
        self.assertEqual((r["window"], r["window_first_return_date"], r["n_trading_days"],
                          r["n_days"]), SLEEVE_0801_WINDOW)
        # POLICY's day count, written out by hand: 2026-08-03 = trading day 1;
        # 08-03..10-02 is 45 weekdays minus Labor Day 09-07 = 44
        self.assertEqual(r["daily"][0]["date"], "2026-08-03")
        self.assertAlmostEqual(r["daily"][0]["gap_bps"], -9.33, delta=0.01)
        self.assertEqual(r["distribution_data"], "COMPLETE")
        self.assertEqual([(x["date"], x["ticker"], x["treatment"])
                          for x in r["distribution_ledger"]],
                         [("2026-09-22", "LABD", "HELD_THROUGH"),
                          ("2026-09-22", "TMV", "LEAKED")])
        self.assertEqual(r["pre_window_credit_rows"], [])
        out = shown(r)
        self.assertIn(f"[--start {OP2_START}", out)
        self.assertIn("2026-07-31 (base close) .. 2026-10-02: 44 trading days on/after "
                      "2026-08-01, first counted return 2026-08-03, 44 daily returns", out)
        self.assertNotIn("PRE-WINDOW CREDIT", out)
        # every engine: the independent gate holds for the same start
        for e in self.panel:
            re_ = run(e, self.panel, self.dists, start=OP2_START)
            self.assertEqual(gate_t18_start(re_, self.panel, e, OP2_START, self.res[e]), [], e)

    def test_t18_broken_old_boundary_base_on_first_window_day_fails(self):
        """The superseded boundary (base = the first date >= start, so the
        first post-start return 07-31 -> 08-03 is dropped). Built as an input:
        the same code with start moved one trading day (08-04 makes 08-03 the
        base), labelled as the Op2 read. It reads lenient (+7.41 vs +6.71
        %/yr) and the POLICY calendar check must reject it."""
        r = run("SLEEVE", self.panel, self.dists, start="2026-08-04")
        for k, pin, tol in zip(PIN_KEYS, PINNED_SLEEVE_FROM_0803_BASE, PIN_TOL):
            self.assertLess(abs(r[k] - pin), tol, k)        # it IS the old read
        r = dict(r, window_start_requested=OP2_START)
        bad = gate_t18_start(r, self.panel, "SLEEVE", OP2_START, self.res["SLEEVE"])
        names = {b[0] for b in bad}
        for k in ("window", "window_first_return_date", "first daily row", "n_trading_days",
                  "pin annualized_gap", "pin cumulative_gap"):
            self.assertIn(k, names, bad)
        print(f"\n  old boundary (base 08-03): {len(bad)} failures, ann "
              f"{r['annualized_gap']:+.4f} vs pinned {PINNED_SLEEVE_FROM_0801[4]:+.4f}")

    def test_t18_broken_start_ignored_fails(self):
        r = run("SLEEVE", self.panel, self.dists)                 # start dropped
        r = dict(r, window_start_requested=OP2_START)             # even if it claims it
        bad = gate_t18_start(r, self.panel, "SLEEVE", OP2_START, self.res["SLEEVE"])
        self.assertGreaterEqual(len([b for b in bad if b[0].startswith("pin ")]), 6, bad)
        print(f"\n  start ignored: {len(bad)} failures, e.g. {bad[:2]}")

    def test_t18_broken_one_leg_sliced_fails(self):
        s = run("SLEEVE", self.panel, self.dists, start=OP2_START)
        for leg in ("live", "model"):
            r = one_leg_unsliced(s, self.res["SLEEVE"], leg)
            bad = gate_t18_start(r, self.panel, "SLEEVE", OP2_START, self.res["SLEEVE"])
            names = {b[0] for b in bad}
            self.assertIn(f"{leg}_cumulative_return" if leg == "live"
                          else "model_total_return_cumulative", names, (leg, bad))
            self.assertIn("cumulative_gap", names, (leg, bad))
            print(f"\n  start applied to the {'model' if leg == 'live' else 'live'} "
                  f"leg only: {sorted(names)}")

    def test_t18_input_truncation_is_equivalent_and_refetch_noted(self):
        """Truncating one leg's INPUT at start: live-only is bit-identical to
        start= (the common calendar is an intersection). Model+weights
        truncated (what refetching the backtest from start would look like if
        Composer's path were unchanged) gives the same consumer keys on this
        fixture. We still slice: a real refetch is a different model path
        (fresh buy-in from cash on day 1 and its turnover cost, no pre-start
        holding for w(t-1) / hold continuity) and would not be the path the
        full-window read sees."""
        v = self.panel["SLEEVE"]
        s = run("SLEEVE", self.panel, self.dists, start=OP2_START)
        k = next(i for i, d in enumerate(v["dates"]) if d >= OP2_START) - 1   # the base
        lv = run("SLEEVE", self.panel, self.dists, live=v["adj"][k:], live_dates=v["dates"][k:])
        for key in CONSUMER_KEYS + SECONDARY_KEYS:
            self.assertEqual(lv[key], s[key], key)
        j = next(i for i, d in enumerate(v["model_dates"]) if d >= OP2_START) - 1
        md, mv = v["model_dates"][j:], v["model"][j:]
        w = {t: {d: x for d, x in dd.items() if d >= md[0]} for t, dd in v["weights"].items()}
        m = dv.analyze_series(v["dates"], v["adj"], md, mv, w, self.dists, live_raw=v["raw"])
        diff = {key: (m[key], s[key]) for key in CONSUMER_KEYS + SECONDARY_KEYS
                if m[key] != s[key]}
        print(f"\n  model+weights truncated at start vs sliced: {diff or 'identical'}; "
              f"held tickers full {sorted(dv._held_tickers(v['weights']))} vs "
              f"truncated {sorted(dv._held_tickers(w))}")
        self.assertEqual(diff, {})

    def test_t18_start_none_is_full_window_bit_for_bit(self):
        for e in self.panel:
            r0 = self.res[e]
            r1 = run(e, self.panel, self.dists, start=r0["window"][0])
            self.assertIsNone(r0["window_start_requested"])
            self.assertEqual(r0["n_trading_days"], r0["n_days"] + 1)
            self.assertEqual(r0["pre_window_credit_rows"], [])
            self.assertEqual({k: x for k, x in r1.items() if k != "window_start_requested"},
                             {k: x for k, x in r0.items() if k != "window_start_requested"}, e)

    def test_t18_analyze_start_fetches_full_window(self):
        """The I/O path: analyze(start=) fetches the backtest over the FULL
        live window (the mock asserts start/end) and equals analyze_series."""
        for e in self.panel:
            fake_get, fake_bt = self._mock_composer(e)
            saved = (cl.get, cl.backtest_by_id, dv.fetch_yahoo_chart)
            cl.get, cl.backtest_by_id = fake_get, fake_bt
            dv.fetch_yahoo_chart = lambda t: self.yahoo[t]
            try:
                r = dv.analyze("acct", e, e, start=OP2_START)
            finally:
                cl.get, cl.backtest_by_id, dv.fetch_yahoo_chart = saved
            ref = run(e, self.panel, self.dists, start=OP2_START)
            for k in CONSUMER_KEYS + SECONDARY_KEYS + ["window", "n_trading_days",
                                                       "window_start_requested",
                                                       "window_first_return_date",
                                                       "pre_window_credit_rows"]:
                self.assertEqual(r[k], ref[k], (e, k))

    def test_t18b_pre_window_credit_flagged(self):
        """HARV and KMLM from 2026-08-01: PULS 07-31 (HELD_THROUGH, L=2) is
        applied on the base close, its credit lands 08-04 inside the window.
        Flagged, bounded, loud; SLEEVE (Op2) and HG have none."""
        for e in self.panel:
            r = run(e, self.panel, self.dists, start=OP2_START)
            self.assertEqual(gate_t18b_pre_window(r, self.res[e], self.panel, e, OP2_START,
                                                  shown(r)), [], e)
        h = run("HARV", self.panel, self.dists, start=OP2_START)
        x, = h["pre_window_credit_rows"]
        self.assertEqual((x["date"], x["ticker"], x["credit_day"]),
                         ("2026-07-31", "PULS", "2026-08-04"))
        # the live recredit is in the window's 08-04 gap (+42.5 vs a 34.4 term)
        self.assertGreater(gap_on(h, "2026-08-04"), x["term_bps"] - RECREDIT_TOL)
        self.assertAlmostEqual(h["pre_window_credit_bias_annualized_max"], 0.0197, delta=0.0001)
        k = run("KMLM", self.panel, self.dists, start=OP2_START)
        self.assertEqual([y["ticker"] for y in k["pre_window_credit_rows"]], ["PULS"])
        # a LEAKED row on the base close is NOT a pre-window credit: HARV from
        # 08-20 has ZVOL 08-19 (sold at the ex-date close) as its base-day row
        z = run("HARV", self.panel, self.dists, start="2026-08-20")
        self.assertEqual(z["window"][0], "2026-08-19")
        self.assertEqual(gate_t18b_pre_window(z, self.res["HARV"], self.panel, "HARV",
                                              "2026-08-20", shown(z)), [])
        self.assertEqual(z["pre_window_credit_rows"], [])
        # unknown-lag branch: KMLM from 09-29 (base 09-28). SOXL 09-22 has no
        # observed lag and was held ex..ex+4, so its credit could land on any
        # of ex+1..ex+MAX_PAY_LAG; only ex+5 = 09-29 is inside the window
        u = run("KMLM", self.panel, self.dists, start="2026-09-29")
        self.assertEqual(gate_t18b_pre_window(u, self.res["KMLM"], self.panel, "KMLM",
                                              "2026-09-29", shown(u)), [])
        self.assertIn("SOXL", [y["ticker"] for y in u["pre_window_credit_rows"]])
        print(f"\n  HARV from {OP2_START}: ann {h['annualized_gap']:+.2%}/yr, bound "
              f"{h['pre_window_credit_bias_annualized_max']:+.2%}, offset "
              f"{h['annualized_gap_pre_window_credits_offset']:+.2%}")

    def test_t18b_broken_flag_dropped_fails(self):
        h = run("HARV", self.panel, self.dists, start=OP2_START)
        r = dict(h, pre_window_credit_rows=[], pre_window_credit_bias_annualized_max=0.0,
                 annualized_gap_pre_window_credits_offset=h["annualized_gap"])
        bad = gate_t18b_pre_window(r, self.res["HARV"], self.panel, "HARV", OP2_START,
                                   shown(r))
        self.assertEqual({b[0] for b in bad}, {"rows", "show() line"}, bad)

    def test_t18c_start_must_be_iso(self):
        v = self.panel["SLEEVE"]
        for bad in ("08/01/2026", "2026-8-1", "20260801", "2026-08-01T00:00", "", 20260801):
            with self.assertRaises(ValueError, msg=repr(bad)):
                dv.analyze_series(v["dates"], v["adj"], v["model_dates"], v["model"],
                                  v["weights"], self.dists, start=bad)
        # the CLI exits before any network call
        saved = sys.argv
        try:
            for bad in ("08/01/2026", "2026-8-1"):
                sys.argv = ["divergence.py", "nNdBk7hc5NiBzeRvbI5T", "--start", bad]
                with self.assertRaises(SystemExit) as cm:
                    dv.main()
                self.assertIn("is not YYYY-MM-DD", str(cm.exception))
        finally:
            sys.argv = saved
        # the valid form is accepted
        self.assertEqual(run("SLEEVE", self.panel, self.dists, start=OP2_START)
                         ["window_start_requested"], OP2_START)

    def test_t17e_classify_hold_literal_cases(self):
        self.assertEqual(dv.MAX_PAY_LAG, 5)
        self.assertEqual(gate_t17e(), [])
        # and through the pipeline: HARV's ZVOL as an unlisted ZZZZ held
        # exactly MAX_PAY_LAG-1 days from the ex-date -> AMBIGUOUS, loud
        v = self.panel["HARV"]
        w, d = rename_ticker(v["weights"], self.dists, "ZVOL", "ZZZZ")
        w4 = weights_held_through(w, "ZZZZ", "2026-08-19", v["model_dates"],
                                  n=dv.MAX_PAY_LAG - 1)
        r = run("HARV", self.panel, d, weights=w4)
        z, = [x for x in r["distribution_ledger"] if x["ticker"] == "ZZZZ"]
        self.assertEqual((z["treatment"], z["held_days_from_ex"]), ("AMBIGUOUS", 4))
        self.assertIn("!! AMBIGUOUS: ZZZZ", shown(r))
        # unknown-lag pending, window ending ex+2: "credit lands ex+5 at the latest"
        p = run("HARV", self.panel, d, weights=w4, end="2026-08-21")
        z, = [x for x in p["distribution_ledger"] if x["ticker"] == "ZZZZ"]
        self.assertEqual((z["treatment"], z["credit_pending"]), ("AMBIGUOUS", True))
        self.assertIn("window ends ex+2, credit lands ex+5 at the latest", shown(p))

    def test_t17e_broken_part1_rule_fails_literal_cases(self):
        """RULE mutant (the part-1 body, as in T17d) misses the cases whose
        pending flag sits on the credit day."""
        bad = gate_t17e(classify_hold_part1)
        self.assertEqual({b[0] for b in bad}, {"unknown held MAX, window ex+4 -> pending"}, bad)

    # plumbing ----------------------------------------------------------
    def test_weights_to_iso_and_held(self):
        w = dv.weights_to_iso({"ZVOL": {"20684": 0.52}, "$USD": {"20684": 0.48},
                               "PULS": {"2026-08-18": 0.0}})
        self.assertEqual(w["ZVOL"], {"2026-08-19": 0.52})
        self.assertEqual(dv._held_tickers(w), {"ZVOL"})
        self.assertEqual(dv._held_tickers({"tdvm_weights": w}), {"ZVOL"})

    def test_dists_from_chart_matches_yahoo_convention(self):
        z = dv.dists_from_chart(self.yahoo["ZVOL"])["2026-08-19"]
        self.assertAlmostEqual(z["amount"], 0.485)
        self.assertAlmostEqual(z["prev_close"], 7.87, places=2)
        # term = y(1+r_adj) must equal r_adj - r_px exactly under Yahoo's rule
        term = z["amount"] / z["prev_close"] * (1 + z["adj_ret"])
        self.assertAlmostEqual(term, z["adj_ret"] - z["px_ret"], places=4)


if __name__ == "__main__":
    unittest.main()
