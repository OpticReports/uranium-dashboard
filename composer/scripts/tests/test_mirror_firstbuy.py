"""Gates for the first-buy warning (2026-11-16 ZVOL: IBKR discarded the mirror's first ZVOL buy pending a
one-time token verification that the API never names). Review 2026-11-17 (D1-D8), its re-check, and the
two verifiers of the re-check fixes (queued transfers/credits/dividends, stale marks, fallback engines,
token redaction, saved date, save failure, malformed sleeves, the feed deadline) included."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import mirror_firstbuy as fb  # noqa: E402
import preclose  # noqa: E402

ZVOL_HOW = "cancelled ([202] Order Canceled - reason:Order was discarded.)"
KNOWN_1116 = {"BIL", "BOXX", "PULS", "SOXL", "SQQQ", "TECL", "VXZ"}


def feed(positions=None, history=None, mode="live", engines=("HG", "KMLM", "SLEEVE", "HARV"), sleeves=None,
         pending=None, dividends=None):
    return {"kind": "mirror-feed", "books": {"live": {
        "mode": mode, "engines": list(engines), "pending_requests": pending or [], "dividends_open": dividends or [],
        "book": {"positions": positions or {}, "sleeves": sleeves or {}}, "history": history or []}}}


def load_mirror_core():
    import importlib.util
    path = os.path.join(SCRIPTS, "..", "..", "ibkr-executor", "app", "mirror_core.py")
    spec = importlib.util.spec_from_file_location("mirror_core_for_test", path)
    mc = importlib.util.module_from_spec(spec)
    sys.modules["mirror_core_for_test"] = mc
    spec.loader.exec_module(mc)
    return mc


def published(mc, sl, marks):
    """the feed's sleeve exactly as ibkr-executor mirror.py _publish builds it (rounded) at `marks`"""
    return {"equity": round(mc.equity(sl, marks), 2), "cash": round(sl.cash, 2), "shares": dict(sorted(sl.shares.items())),
            "weights": {k: round(v, 5) for k, v in mc.weights(sl, marks).items()}, "rule": sl.rule, "corridor": sl.corridor}


def row(engine, after, status="ok", target=None, corridor=None):
    r = {"engine": engine, "status": status, "after": after, "target": target if target is not None else after}
    if corridor is not None:
        r["corridor"] = corridor
    return r


# ---- known set -------------------------------------------------------------------------------
def test_known_is_positions_plus_filled_buys_only():
    f = feed({"BIL": 183, "BOXX": 0}, [{"orders": [
        {"side": "BUY", "symbol": "TECL", "filled": 5, "qty": 5},
        {"side": "BUY", "symbol": "ZVOL", "filled": 0, "qty": 760, "how": ZVOL_HOW},   # rejected: not known
        {"side": "SELL", "symbol": "SOXL", "filled": 3, "qty": 3}]}])                     # a sell is not a buy
    assert fb.known_from_feed(f) == {"BIL", "TECL"}


def test_known_persists_across_the_feed_window(tmp_path):
    p = tmp_path / "ibkr-bought.json"
    fb.preview_check([], feed({"VXZ": 10}), p, today="2026-11-16")
    assert json.loads(p.read_text())["bought"] == ["VXZ"]
    lines, alerts = fb.preview_check([row("HG", {"VXZ": 1.0})], feed({"BIL": 1}), p)   # VXZ aged out of the feed
    assert alerts == [] and set(json.loads(p.read_text())["bought"]) == {"VXZ", "BIL"}


def test_missing_or_corrupt_store_is_empty(tmp_path):
    p = tmp_path / "x.json"
    assert fb.load_known(p) == (set(), None, None)
    for bad in ("not json", '{"bought": 5}', '{"bought": true}', "[1, 2]", '{"bought": ["BIL"], "saved": 7}'):
        p.write_text(bad)
        known, saved, eng = fb.load_known(p)      # never raises (re-check: a wrong-typed file escaped as TypeError)
        assert saved is None and known in (set(), {"BIL"})


def test_a_paper_book_never_teaches_the_set(tmp_path):
    p = tmp_path / "k.json"
    fb.save_known({"BIL"}, p, "2026-11-13")
    lines, alerts = fb.preview_check([row("HARV", {"ZVOL": 1.0})], feed({"ZVOL": 760}, mode="paper"), p)
    assert fb.load_known(p)[0] == {"BIL"}                     # the paper ZVOL was not learned
    assert len(alerts) == 1 and "not in live mode" in lines[0]


def test_save_false_writes_nothing(tmp_path):
    p = tmp_path / "k.json"
    fb.preview_check([], feed({"BIL": 1}), p, save=False)
    assert not p.exists()


# ---- the 15:15 alert ---------------------------------------------------------------------------
def test_the_2026_11_16_case_alerts_both_engines():
    lines, alerts = fb.first_buy_alerts([row("KMLM", {"SQQQ": 0.75, "ZVOL": 0.13, "PULS": 0.12}),
                                         row("HARV", {"ZVOL": 0.52, "PULS": 0.48}),
                                         row("HG", {"BIL": 1.0})], KNOWN_1116, feed())
    assert len(alerts) == 2
    assert alerts[0].startswith("FIRST BUY ON IBKR — KMLM") and "ZVOL" in alerts[0]
    assert alerts[1].startswith("FIRST BUY ON IBKR — HARV")
    assert all("the sleeve buys it when its rule next trades (a daily sleeve at the next session)" in a for a in alerts)


def test_no_alert_when_every_fund_is_known():
    assert fb.first_buy_alerts([row("HG", {"BIL": 1.0})], {"BIL"}, feed()) == ([], [])


def test_skips_gate_dust_and_non_numbers_and_says_when_a_preview_is_unavailable():
    rows = [row("GATE", {"NEW": 1.0}), row("SLEEVE", {"NEW": 1.0}, status="unavailable"),
            row("HG", {"BIL": 0.997, "DUST": 0.003, "ODD": "x"}, target={"BIL": 1.0})]
    lines, alerts = fb.first_buy_alerts(rows, {"BIL"}, feed())
    assert alerts == [] and lines == ["first-buy check: SLEEVE NOT checked (its preview is unavailable)"]
    # a paper-only engine's unavailable preview says nothing
    lines, alerts = fb.first_buy_alerts([row("SLEEVE", {"NEW": 1.0}, status="unavailable")], set(), feed(engines=("HG",)))
    assert (lines, alerts) == ([], [])


def test_engines_the_live_book_does_not_trade_are_skipped():
    f = feed(engines=("HG", "KMLM", "HARV"), sleeves={"HARV": {"frozen": True}})
    lines, alerts = fb.first_buy_alerts([row("SLEEVE", {"NEW": 1.0}), row("HARV", {"ZVOL": 1.0})], set(), f)
    assert alerts == []


def test_corridor_target_is_checked_when_the_sleeve_idles_cash():
    """D3: KMLM's corridor did not trip for Composer, but the mirror sleeve sits >5% in cash after a
    rejected buy, so it trades to the full target: the target's new fund must alert"""
    sl = {"KMLM": {"equity": 14941.94, "cash": 1968.84, "weights": {"SQQQ": 0.749, "PULS": 0.119}}}
    r = row("KMLM", after={"SQQQ": 0.75, "PULS": 0.12}, target={"SQQQ": 0.75, "ZVOL": 0.13, "PULS": 0.12}, corridor=0.1)
    lines, alerts = fb.first_buy_alerts([r], KNOWN_1116, feed(sleeves=sl))
    assert len(alerts) == 1 and "ZVOL" in alerts[0]


def test_corridor_gap_is_on_invested_weights_not_equity_weights():
    """re-check SERIOUS: invested A 0.52 / C 0.48 with 4.5% cash; target A 0.40 / X 0.08 / C 0.52.
    On equity weights the gap reads 0.097 (< 0.10, 'no buy'); on invested weights it is 0.12 (> 0.10):
    the executor trades and buys X, so the warning must alert"""
    cash_frac = 0.045
    sl = {"KMLM": {"equity": 10000, "cash": 10000 * cash_frac,
                   "weights": {"A": 0.52 * (1 - cash_frac), "C": 0.48 * (1 - cash_frac)}}}
    r = row("KMLM", after={"A": 0.52, "C": 0.48}, target={"A": 0.40, "X": 0.08, "C": 0.52}, corridor=0.1)
    lines, alerts = fb.first_buy_alerts([r], {"A", "C"}, feed(sleeves=sl))
    assert len(alerts) == 1 and "X" in alerts[0]


def test_corridor_debt_or_empty_sleeve_trades():
    target = {"A": 0.9, "X": 0.1}
    r = row("KMLM", after={"A": 1.0}, target=target, corridor=0.1)
    for sleeve in ({"equity": 10000, "cash": -5.0, "weights": {"A": 1.0}},      # in debt
                   {"equity": 10000, "cash": 0.0, "weights": {}}):              # holds nothing
        lines, alerts = fb.first_buy_alerts([r], {"A"}, feed(sleeves={"KMLM": sleeve}))
        assert len(alerts) == 1, sleeve


def test_warning_rule_matches_the_executor_decide_sleeve():
    """the warning's threshold rule against the executor's own mirror_core.decide_sleeve on a grid of
    sleeves, with the feed built exactly as _publish builds it (rounded): whenever the executor trades,
    the warning must say it will. Both readings: the feed's marks (prices=None) and a re-mark at the
    decision's prices. The census proves the grid holds holds AND gap-only trades (not vacuous)."""
    mc = load_mirror_core()
    cfg = mc.Config()
    prices = {"A": 50.0, "C": 25.0, "X": 10.0}
    target = {"A": 0.40, "X": 0.08, "C": 0.52}
    misses, census = [], {"hold": 0, "gap_only_trade": 0, "other_trade": 0}
    for a_sh in range(40, 140, 7):
        for c_sh in range(80, 260, 11):
            for cash in (-10.0, -0.0051, -0.0049, 0.0, 150.0, 400.0, 700.0):
                sl = mc.Sleeve(name="KMLM", rule=mc.RULE_THRESHOLD, corridor=0.10, cash=cash,
                               shares={"A": a_sh, "C": c_sh})
                d = mc.decide_sleeve(sl, target, prices, cfg)
                eq = mc.equity(sl, prices)
                if d["action"] == "hold":
                    census["hold"] += 1
                elif cash >= -mc.DEBT_TOL_USD and cash / eq <= mc.MAX_IDLE_CASH_FRAC:
                    census["gap_only_trade"] += 1
                else:
                    census["other_trade"] += 1
                fs = published(mc, sl, prices)
                for px in (None, prices):
                    if d["action"] == "trade" and not fb.sleeve_will_reach_target(fs, target, 0.10, prices=px):
                        misses.append((a_sh, c_sh, cash, round(d["gap"], 4), "marks" if px is None else "live"))
    assert census["hold"] > 0 and census["gap_only_trade"] > 0 and census["other_trade"] > 0, census
    assert misses == []


def test_stale_marks_are_re_marked_at_the_preview_prices():
    """verifiers: the feed's marks are the last planned session's prices. A sleeve that looked inside
    its corridor at yesterday's marks can be outside it at today's prices; re-marking at the preview's
    live prices catches it, the stale marks alone do not"""
    mc = load_mirror_core()
    cfg = mc.Config()
    target = {"S": 0.75, "P": 0.20, "Z": 0.05}
    sl = mc.Sleeve(name="KMLM", rule=mc.RULE_THRESHOLD, corridor=0.10, cash=50.0, shares={"S": 143, "P": 285})
    yesterday = {"S": 50.0, "P": 10.0, "Z": 10.0}       # invested S 0.715 / P 0.285: largest gap 0.085, holds
    today = {"S": 50.0, "P": 11.0, "Z": 10.0}           # P +10%: invested P 0.305, gap 0.105 > 0.10: trades
    d_y, d_t = mc.decide_sleeve(sl, target, yesterday, cfg), mc.decide_sleeve(sl, target, today, cfg)
    assert d_y["action"] == "hold" and 0.08 < d_y["gap"] < 0.09
    assert d_t["action"] == "trade" and d_t["gap"] > 0.10
    fs = published(mc, sl, yesterday)
    assert fb.sleeve_will_reach_target(fs, target, 0.10, prices=None) is False          # stale: would miss
    assert fb.sleeve_will_reach_target(fs, target, 0.10, prices=today) is True          # re-marked: caught
    r = row("KMLM", after={"S": 0.715, "P": 0.285}, target=target, corridor=0.1)
    lines, alerts = fb.first_buy_alerts([r], {"S", "P"}, feed(sleeves={"KMLM": fs}), prices=today)
    assert len(alerts) == 1 and "Z" in alerts[0]


def test_queued_transfer_credit_and_dividend_each_make_the_sleeve_trade():
    """verifier 1 SERIOUS: _plan applies due dividends and operator credits to the sleeve's cash BEFORE the
    decision, and build_plan forces a sleeve named in a planned transfer. KMLM inside its corridor with
    1% cash and a never-bought X in the target: with nothing queued the executor holds (a line); with
    a transfer either way, a credit, or a dividend receivable it trades and buys X (an alert)."""
    mc = load_mirror_core()
    cfg = mc.Config()
    target = {"A": 0.47, "C": 0.47, "X": 0.06}
    prices = {"A": 50.0, "C": 50.0, "X": 10.0}
    sl = mc.Sleeve(name="KMLM", rule=mc.RULE_THRESHOLD, corridor=0.10, cash=100.0, shares={"A": 99, "C": 99})
    assert mc.decide_sleeve(sl, target, prices, cfg)["action"] == "hold"
    fs = published(mc, sl, prices)
    r = row("KMLM", after={"A": 0.5, "C": 0.5}, target=target, corridor=0.1)
    lines, alerts = fb.first_buy_alerts([r], {"A", "C"}, feed(sleeves={"KMLM": fs}), prices=prices)
    assert alerts == [] and "does not trade it today" in lines[0]
    cases = {
        "transfer in": [{"kind": "transfer", "from": "HG", "to": "KMLM", "amount": 500.0}],
        "transfer out": [{"kind": "transfer", "from": "KMLM", "to": "HG", "amount": 500.0}],
        "credit": [{"kind": "credit", "sleeve": "KMLM", "amount": 800.0}],
    }
    for name, pending in cases.items():
        lines, alerts = fb.first_buy_alerts([r], {"A", "C"}, feed(sleeves={"KMLM": fs}, pending=pending), prices=prices)
        assert len(alerts) == 1 and "X" in alerts[0], name
    # the executor agrees: the credit raises idle cash over 5% and it trades
    sl2 = mc.Sleeve(name="KMLM", rule=mc.RULE_THRESHOLD, corridor=0.10, cash=900.0, shares={"A": 99, "C": 99})
    assert mc.decide_sleeve(sl2, target, prices, cfg)["action"] == "trade"
    div = [{"sleeve": "KMLM", "total": 800.0, "status": "open", "ticker": "A"}]
    lines, alerts = fb.first_buy_alerts([r], {"A", "C"}, feed(sleeves={"KMLM": fs}, dividends=div), prices=prices)
    assert len(alerts) == 1, "dividend"
    other = [{"kind": "credit", "sleeve": "HG", "amount": 800.0}, {"kind": "transfer", "from": "HG", "to": "HARV", "amount": 1.0}]
    lines, alerts = fb.first_buy_alerts([r], {"A", "C"}, feed(sleeves={"KMLM": fs}, pending=other), prices=prices)
    assert alerts == [], "another engine's queue is not KMLM's"


def test_queued_debit_into_debt_makes_it_trade():
    assert fb.queued(feed(pending=[{"kind": "credit", "sleeve": "KMLM", "amount": -200.0}]), "KMLM") == (False, -200.0, 0.0)
    fs = {"equity": 10000.0, "cash": 100.0, "shares": {"A": 100}, "weights": {"A": 0.99}}
    assert fb.sleeve_will_reach_target(fs, {"A": 0.95, "X": 0.05}, 0.10, lo=-200.0, prices={"A": 99.0}) is True


def test_a_debt_is_not_hidden_by_credits_or_receivables_the_executor_may_skip():
    """round-4 verifier SERIOUS (a regression of e3f6e91f): KMLM at -3.00 with a $36.20 receivable not yet
    due, or a $50 credit the executor refuses - the executor repairs the debt by trading; summing every
    queued amount into one figure read +33.20 and said 'no buy'. The interval tests debt at its low end."""
    fs = {"equity": 9997.0, "cash": -3.0, "shares": {"A": 100, "C": 100}, "weights": {"A": 0.5, "C": 0.5}}
    target = {"A": 0.47, "C": 0.47, "X": 0.06}
    r = row("KMLM", after={"A": 0.5, "C": 0.5}, target=target, corridor=0.1)
    for f in (feed(sleeves={"KMLM": fs}, dividends=[{"sleeve": "KMLM", "total": 36.2, "status": "open"}]),
              feed(sleeves={"KMLM": fs}, pending=[{"kind": "credit", "sleeve": "KMLM", "amount": 50.0}])):
        lines, alerts = fb.first_buy_alerts([r], {"A", "C"}, f, prices={"A": 50.0, "C": 50.0})
        assert len(alerts) == 1 and "X" in alerts[0]
    # a refused unforced debit beside a forced credit: lo is deep in debt -> trades (conservative)
    fs2 = dict(fs, cash=-1.35, equity=9998.65)
    f = feed(sleeves={"KMLM": fs2}, pending=[{"kind": "credit", "sleeve": "KMLM", "amount": 3027.90, "force": True},
                                              {"kind": "credit", "sleeve": "KMLM", "amount": -2154.11}])
    assert fb.first_buy_alerts([r], {"A", "C"}, f, prices={"A": 50.0, "C": 50.0})[1]


def test_any_subset_of_the_queue_the_executor_applies_is_covered():
    """the interval property against the executor's own decide_sleeve: for random sleeves and queues of
    credits, debits and receivables, whichever SUBSET the executor ends up applying, if it trades the
    warning (given the whole queue) must say so"""
    import itertools
    import random
    mc = load_mirror_core()
    cfg = mc.Config()
    rnd = random.Random(20261117)
    target = {"A": 0.47, "C": 0.47, "X": 0.06}
    prices = {"A": 50.0, "C": 40.0, "X": 10.0}
    misses = trades = 0
    for _ in range(1500):
        a_sh, c_sh = rnd.randint(60, 140), rnd.randint(80, 170)
        base = rnd.choice([-60.0, -3.0, -0.004, 0.0, 20.0, 120.0, 300.0, 520.0])
        items = [round(rnd.choice([-1, 1]) * rnd.uniform(1, 700), 2) for _ in range(rnd.randint(1, 3))]
        lo, hi = sum(x for x in items if x < 0), sum(x for x in items if x > 0)
        sl0 = mc.Sleeve(name="KMLM", rule=mc.RULE_THRESHOLD, corridor=0.10, cash=base, shares={"A": a_sh, "C": c_sh})
        fs = published(mc, sl0, prices)
        warn = fb.sleeve_will_reach_target(fs, target, 0.10, lo=lo, hi=hi, prices=prices)
        for k in range(len(items) + 1):
            for sub in itertools.combinations(items, k):
                sl = mc.Sleeve(name="KMLM", rule=mc.RULE_THRESHOLD, corridor=0.10, cash=base + sum(sub),
                               shares={"A": a_sh, "C": c_sh})
                if mc.decide_sleeve(sl, target, prices, cfg)["action"] == "trade":
                    trades += 1
                    misses += not warn
    assert trades > 500 and misses == 0


def test_adjust_and_resolve_requests_force_a_trade():
    assert fb.queued(feed(pending=[{"kind": "adjust", "sleeve": "KMLM", "cash": 10.0}]), "KMLM")[0] is True
    assert fb.queued(feed(pending=[{"kind": "adjust", "sleeve": "HG", "cash": 10.0}]), "KMLM")[0] is False
    assert fb.queued(feed(pending=[{"kind": "resolve", "order": "x"}]), "KMLM")[0] is True


def test_either_reading_trading_counts():
    """the feed's marks say the gap is out, the live prices pull it back in: still counted as a trade
    (never miss a case the stale reading caught)"""
    fs = {"equity": 10000.0, "cash": 0.0, "shares": {"S": 100, "P": 100}, "weights": {"S": 0.60, "P": 0.40}}
    target = {"S": 0.70, "P": 0.27, "Z": 0.03}       # at marks: P .40 vs .27 = .13 > .09 -> trades
    live = {"S": 69.0, "P": 31.0}                     # live: S .69 / P .31 -> largest gap .04 -> holds
    assert fb.sleeve_will_reach_target({k: v for k, v in fs.items() if k != "weights"} | {"weights": {"S": 0.69, "P": 0.31}},
                                       target, 0.10, prices=live) is False                # the live reading alone holds
    assert fb.sleeve_will_reach_target(fs, target, 0.10, prices=live) is True             # either reading: trades


def test_a_fund_with_no_live_price_keeps_its_implied_mark():
    """round-4 verifier note: one missing preview price must not throw away the live reading for the
    whole sleeve; the missing fund keeps its implied mark (weight x equity / shares)"""
    mc = load_mirror_core()
    cfg = mc.Config()
    target = {"S": 0.75, "P": 0.20, "Z": 0.05}
    sl = mc.Sleeve(name="KMLM", rule=mc.RULE_THRESHOLD, corridor=0.10, cash=50.0, shares={"S": 143, "P": 285})
    marks, now = {"S": 50.0, "P": 10.0, "Z": 10.0}, {"S": 50.0, "P": 11.0, "Z": 10.0}
    assert mc.decide_sleeve(sl, target, now, cfg)["action"] == "trade"
    fs = published(mc, sl, marks)
    assert fb.sleeve_will_reach_target(fs, target, 0.10, prices={"P": 11.0}) is True     # S has no live price
    assert fb.sleeve_will_reach_target(fs, target, 0.10, prices={}) is False             # marks only: holds


def test_the_executor_rule_daily_wins_and_the_smaller_corridor_is_used():
    target = {"A": 0.9, "X": 0.1}
    fs = {"equity": 10000.0, "cash": 0.0, "shares": {"A": 100}, "weights": {"A": 1.0}}
    r = row("KMLM", after={"A": 1.0}, target=target, corridor=0.10)          # gap 0.10: inside the slack? no: 0.10 > 0.09
    lines, alerts = fb.first_buy_alerts([r], {"A"}, feed(sleeves={"KMLM": dict(fs, rule="daily", corridor=None)}))
    assert len(alerts) == 1                                                  # the executor trades it daily
    near = {"A": 0.95, "X": 0.05}                                            # gap 0.05: holds at 0.10, trades at 0.04
    r2 = row("KMLM", after={"A": 1.0}, target=near, corridor=0.10)
    assert fb.first_buy_alerts([r2], {"A"}, feed(sleeves={"KMLM": dict(fs, rule="threshold", corridor=0.10)}))[1] == []
    assert fb.first_buy_alerts([r2], {"A"}, feed(sleeves={"KMLM": dict(fs, rule="threshold", corridor=0.04)}))[1]


def test_a_small_target_weight_on_a_daily_engine_is_a_buy():
    """round-4 note: MIN_WEIGHT filters end-state remnants, never a TARGET weight"""
    r = row("HARV", after={"PULS": 0.996, "NEW": 0.004}, target={"PULS": 0.996, "NEW": 0.004})
    assert len(fb.first_buy_alerts([r], {"PULS"}, feed())[1]) == 1


# ---- alternatives: the preview's other outcomes (round-4 verifiers SERIOUS) --------------------------
def _ledger_row(date, engine, label=None):
    path = os.path.join(SCRIPTS, "..", "results", "monitor", "preclose-ledger.jsonl")
    rows = [json.loads(x) for x in open(path) if x.strip()]
    return [r for r in rows if r.get("date") == date and r.get("engine") == engine
            and (label is None or r.get("label") == label)][-1]


def test_the_2026_11_06_harv_zvol_flip_alerts():
    """the real case: HARV's 15:16 preview on 2026-11-06 ended in PULS 1.0, 'could flip' (SPY -0.36%, 1.6 sigma) to
    {PULS .64, ZVOL .36}, and Composer took it. IBKR has never bought ZVOL: the alternative alerts and
    names what flips it"""
    r = _ledger_row("2026-11-06", "HARV", "could flip")
    lines, alerts = fb.first_buy_alerts([r], KNOWN_1116, feed())
    assert len(alerts) == 1 and alerts[0].startswith("FIRST BUY ON IBKR (if a call flips) —")
    assert "HARV ZVOL (could flip; SPY -0.36%, 1.63 sigma)" in alerts[0]
    assert "it is bought when that sleeve's rule next trades." in alerts[0]


def test_a_firm_calls_alternative_is_a_line_not_a_push():
    """2026-11-10: SLEEVE was 'firm'; its 2-sigma SHY alternative {BOXX .5, UVXY .5} was crossed only by
    the close, after the decision, and Composer stayed in BOXX (shadow ledger: knife-edge). A firm
    call's alternative is shown, not pushed (round 5: alert fatigue)"""
    r = _ledger_row("2026-11-10", "SLEEVE")
    assert r["label"] == "firm" and r["flip"]["instead"] == {"BOXX": 0.5, "UVXY": 0.5}
    lines, alerts = fb.first_buy_alerts([r], KNOWN_1116, feed())
    assert alerts == [] and lines and "SLEEVE could buy UVXY if SHY" in lines[0] and "not pushed" in lines[0]


def test_alternatives_combine_into_one_alert_and_known_funds_stay_quiet():
    harv = _ledger_row("2026-11-06", "HARV", "could flip")
    sleeve = _ledger_row("2026-11-10", "SLEEVE")
    k1103 = _ledger_row("2026-11-03", "KMLM")                  # a close call whose ZVOL is only in 'market'
    lines, alerts = fb.first_buy_alerts([harv, sleeve, k1103], KNOWN_1116, feed())
    assert len(alerts) == 1 and "HARV ZVOL (could flip" in alerts[0] and "KMLM ZVOL (close call; market" in alerts[0]
    assert "SLEEVE" not in alerts[0] and any("SLEEVE could buy UVXY" in x for x in lines)
    assert fb.first_buy_alerts([harv, sleeve, k1103], KNOWN_1116 | {"ZVOL", "UVXY"}, feed()) == ([], [])


def test_gate_sides_only_when_the_gate_is_within_reach(tmp_path):
    """round 5: a far gate's other side (e.g. TQQQ in a relief rally) must not push every session"""
    def led(sigma, open_now=True, open_prev=True):
        return [{"engine": "GATE", "date": "2026-11-17", "time": "15:15", "left": 35, "sigma": sigma, "open": open_now,
                 "open_prev": open_prev, "sides": [{"BIL": 1.0}, {"TQQQ": 1.0}]}, dict(row("HG", {"BIL": 1.0}), label="firm")]
    far = preclose.first_buy(led(13.1), env={}, fetch=lambda: feed({"BIL": 1}), path=tmp_path / "a.json")
    near = preclose.first_buy(led(1.5), env={}, fetch=lambda: feed({"BIL": 1}), path=tmp_path / "b.json")
    flipping = preclose.first_buy(led(13.1, True, False), env={}, fetch=lambda: feed({"BIL": 1}), path=tmp_path / "c.json")
    assert far[1] == []
    assert len(near[1]) == 1 and "HG TQQQ (firm; SPY across its 200-day)" in near[1][0]   # a gate side pushes even when firm
    assert len(flipping[1]) == 1


def test_hg_gets_the_gate_sides_through_preclose(tmp_path):
    led = [{"engine": "GATE", "date": "2026-11-17", "time": "15:15", "left": 35, "sides": [{"BIL": 1.0}, {"QLD": 1.0}]},
           row("HG", {"BIL": 1.0}), row("HARV", {"PULS": 1.0})]
    lines, alerts = preclose.first_buy(led, env={}, fetch=lambda: feed({"BIL": 1, "PULS": 1}), path=tmp_path / "k.json")
    assert len(alerts) == 1 and "HG QLD" in alerts[0] and "HARV" not in alerts[0]


# ---- wiring and failure paths (round-4 verifier 2) ---------------------------------------------------
def _stale_case():
    mc = load_mirror_core()
    target = {"S": 0.75, "P": 0.20, "Z": 0.05}
    sl = mc.Sleeve(name="KMLM", rule=mc.RULE_THRESHOLD, corridor=0.10, cash=50.0, shares={"S": 143, "P": 285})
    fs = published(mc, sl, {"S": 50.0, "P": 10.0, "Z": 10.0})
    fs.update(rule="threshold", corridor=0.10)
    led = [{"engine": "GATE", "date": "2026-11-17", "time": "15:15", "left": 35},
           row("KMLM", after={"S": 0.715, "P": 0.285}, target=target)]
    return led, feed({"S": 143, "P": 285}, sleeves={"KMLM": fs})


def test_preclose_threads_the_preview_prices_to_the_re_mark(tmp_path):
    """kills the surviving mutations: first_buy or preview_check dropping `prices` silently turns the
    re-mark off and the sleeve is read at stale marks again"""
    led, f = _stale_case()
    lines, alerts = preclose.first_buy(led, env={}, fetch=lambda: f, path=tmp_path / "a.json",
                                       prices={"S": 50.0, "P": 11.0, "Z": 10.0})
    assert len(alerts) == 1 and "Z" in alerts[0]
    lines, alerts = preclose.first_buy(led, env={}, fetch=lambda: f, path=tmp_path / "b.json", prices=None)
    assert alerts == [] and "does not trade it today" in lines[0]


def test_the_feed_error_reason_reaches_the_line(tmp_path):
    def boom():
        raise RuntimeError("HTTP 401: the read token was refused")
    lines, alerts = preclose.first_buy([row("HARV", {"ZVOL": 1.0})], env={}, fetch=boom, path=tmp_path / "k.json")
    assert "HTTP 401" in lines[0]


def test_a_system_exit_inside_the_fetch_never_escapes(tmp_path):
    def exits():
        raise SystemExit("x")
    lines, alerts = preclose.first_buy([row("HARV", {"ZVOL": 1.0})], env={}, fetch=exits, path=tmp_path / "k.json")
    assert alerts == [] and "not read" in lines[0]


def test_fetch_feed_redacts_a_latin1_escaped_token():
    import mirror_parity as mp
    tok = "s3cr\u00e9t-y"

    def boom(req, timeout=None):
        raise ValueError(f"bad header {tok.encode('latin-1')!r}")
    try:
        mp.fetch_feed("https://e.example", tok, opener=boom)
        raise AssertionError("no error")
    except RuntimeError as e:
        assert "s3cr" not in str(e) and "***" in str(e)


def test_the_deadline_thread_is_a_daemon(tmp_path):
    import threading
    import time

    def slow():
        time.sleep(3)
        return feed()
    preclose.first_buy([row("HARV", {"ZVOL": 1.0})], env={}, fetch=slow, path=tmp_path / "k.json", deadline=0.2)
    others = [t for t in threading.enumerate() if t is not threading.main_thread() and t.is_alive()]
    assert others and all(t.daemon for t in others)



def test_malformed_sleeve_assumes_a_trade_and_keeps_other_engines():
    for bad in ({"weights": [1, 2]}, {"cash": "x", "weights": {"A": 1.0}}, {"shares": {"A": "lots"}, "weights": None}):
        assert fb.sleeve_will_reach_target(bad, {"A": 0.9, "X": 0.1}, 0.10) is True
    rows = [row("KMLM", after={"A": 1.0}, target={"A": 0.9, "X": 0.1}, corridor=0.1), row("HARV", {"ZVOL": 1.0})]
    lines, alerts = fb.first_buy_alerts(rows, {"A"}, feed(sleeves={"KMLM": {"weights": [1, 2]}}))
    assert len(alerts) == 2


def test_corridor_target_not_tripping_is_a_line_not_an_alert():
    sl = {"KMLM": {"equity": 10000, "cash": 10, "weights": {"SQQQ": 0.75, "PULS": 0.25}}}
    r = row("KMLM", after={"SQQQ": 0.75, "PULS": 0.25}, target={"SQQQ": 0.75, "ZVOL": 0.05, "PULS": 0.20}, corridor=0.1)
    lines, alerts = fb.first_buy_alerts([r], KNOWN_1116, feed(sleeves=sl))
    assert alerts == [] and "does not trade it today" in lines[0]


def test_unread_feed_falls_back_to_the_saved_set(tmp_path):
    p = tmp_path / "k.json"
    fb.save_known(KNOWN_1116, p, "2026-11-16")
    lines, alerts = fb.preview_check([row("HARV", {"ZVOL": 1.0})], None, p, why="the mirror feed was not read (HTTP 401)")
    assert len(alerts) == 1 and "saved set of 2026-11-16" in lines[0] and "HTTP 401" in lines[0]


def test_a_feed_with_no_live_book_never_alerts(tmp_path):
    p = tmp_path / "k.json"
    fb.save_known({"BIL"}, p, "2026-11-16", {"HARV"})
    f = {"kind": "mirror-feed", "books": {"dry": {"mode": "paper"}}}
    lines, alerts = fb.preview_check([row("HARV", {"ZVOL": 1.0})], f, p)
    assert alerts == [] and "no live IBKR book" in lines[0]


def test_the_fallback_checks_every_engine_and_notes_the_unconfirmed(tmp_path):
    """verifier 2: an engine added to the live book after the last save must not be skipped silently when
    the feed is unread; it alerts, with a note that it was not live at the save"""
    p = tmp_path / "k.json"
    fb.save_known({"BIL"}, p, "2026-11-16", {"HG", "HARV"})
    lines, alerts = fb.preview_check([row("SLEEVE", {"NEW": 1.0}), row("HARV", {"ZVOL": 1.0})], None, p)
    assert len(alerts) == 2 and "every engine checked" in lines[0]
    sleeve = next(a for a in alerts if "— SLEEVE" in a)
    harv = next(a for a in alerts if "— HARV" in a)
    assert sleeve.startswith("FIRST BUY ON IBKR —") and "was not trading live on 2026-11-16" in sleeve
    assert "was not trading live" not in harv


def test_the_half_day_decision_time_reaches_the_message(tmp_path):
    led = [{"engine": "GATE", "date": "2026-11-27", "time": "12:15", "left": 35}, row("HARV", {"ZVOL": 1.0})]
    assert preclose.decision_at(led) == "12:50"
    lines, alerts = preclose.first_buy(led, env={}, fetch=lambda: feed({"PULS": 1}), path=tmp_path / "k.json")
    assert "at ~12:50" in alerts[0]
    assert preclose.decision_at([{"engine": "GATE"}]) == "15:50"


def test_unread_feed_and_no_saved_set_is_a_line(tmp_path):
    lines, alerts = fb.preview_check([row("HARV", {"ZVOL": 1.0})], None, tmp_path / "k.json")
    assert alerts == [] and "not checked" in lines[0]


# ---- preclose wiring --------------------------------------------------------------------------
def test_preclose_without_env_says_so():
    lines, alerts = preclose.first_buy([row("HARV", {"ZVOL": 1.0})], env={}, path=None, save=False)
    assert "not set" in lines[0]


def test_preclose_uses_the_feed_and_skips_the_gate_row(tmp_path):
    led = [{"engine": "GATE", "status": "open"}, row("HARV", {"ZVOL": 0.52, "PULS": 0.48})]
    lines, alerts = preclose.first_buy(led, env={}, fetch=lambda: feed({"PULS": 59}), path=tmp_path / "k.json")
    assert len(alerts) == 1 and alerts[0].split("buy ")[1].startswith("ZVOL at")


def test_preclose_feed_failure_never_raises_and_never_shows_a_token(tmp_path):
    def boom():
        raise RuntimeError("HTTP 401: the read token was refused")
    lines, alerts = preclose.first_buy([row("HARV", {"ZVOL": 1.0})], env={"MIRROR_READ_TOKEN": "s3cret"},
                                       fetch=boom, path=tmp_path / "k.json")
    assert alerts == [] and "not checked" in lines[0] and "s3cret" not in " ".join(lines)


def test_preclose_attaches_the_manifest_corridor(tmp_path):
    """led rows drop 'corridor': first_buy re-attaches it from the manifest so D3 applies to KMLM"""
    seen = {}
    real = fb.first_buy_alerts

    def spy(rows, *a, **k):
        seen.update({r["engine"]: r.get("corridor") for r in rows})
        return real(rows, *a, **k)
    fb.first_buy_alerts = spy
    try:
        preclose.first_buy([row("KMLM", {"SQQQ": 1.0}), row("HG", {"BIL": 1.0})], env={},
                           fetch=lambda: feed({"SQQQ": 1, "BIL": 1}), path=tmp_path / "k.json")
    finally:
        fb.first_buy_alerts = real
    assert seen["KMLM"] is not None and seen["HG"] is None


def test_main_flag_skips_the_check():
    src = open(os.path.join(SCRIPTS, "preclose.py")).read()
    assert '"--no-first-buy" not in sys.argv' in src and 'save="--no-ledger" not in sys.argv' in src
    assert src.index("sys.stdout.flush()") < src.index("fl, fa = first_buy(")


# ---- the parity UNFILLED hint -----------------------------------------------------------------
def test_discard_hint_names_the_fund_and_the_fix():
    h = fb.discard_hint([{"symbol": "ZVOL", "qty": 760, "filled": 0, "how": ZVOL_HOW},
                         {"symbol": "BIL", "qty": 1, "filled": 1, "how": "filled"}])
    assert "ZVOL" in h and "BIL" not in h and "verify" in h and "until its rule next trades" in h


def test_no_hint_for_other_cancellations():
    assert fb.discard_hint([{"symbol": "X", "qty": 5, "filled": 2, "how": "cancelled at the window's end"}]) == ""
    assert fb.discard_hint([{"symbol": "Z", "qty": 5, "filled": 5, "how": ZVOL_HOW}]) == ""   # filled: no hint


# ---- verifiers of the re-check fixes: persistence, token, deadline, main ---------------------------
def test_the_saved_date_never_moves_back(tmp_path):
    p = tmp_path / "k.json"
    fb.preview_check([], feed({"BIL": 1}), p, today="2026-11-17")
    fb.preview_check([], feed({"BIL": 1}), p, today="2026-11-10")
    assert fb.load_known(p)[1] == "2026-11-17"


def test_a_save_failure_is_said_and_leaves_no_temp_file(tmp_path):
    p = tmp_path / "k.json"
    p.mkdir()                                     # a directory where the file should be: os.replace fails
    lines, alerts = fb.preview_check([row("HARV", {"ZVOL": 1.0})], feed({"BIL": 1}), p)
    assert "was not saved" in lines[0] and len(alerts) == 1
    assert not (tmp_path / "k.tmp").exists()


def test_fetch_feed_never_sends_or_prints_a_token_with_a_line_break():
    import mirror_parity as mp
    for tok in ("abc\ndef", "abc\rdef", "abc\tdef", ""):
        try:
            mp.fetch_feed("https://e.example", tok, opener=lambda *a, **k: (_ for _ in ()).throw(AssertionError("sent")))
            raise AssertionError("no refusal")
        except RuntimeError as e:
            assert "not sent" in str(e) and (not tok or tok not in str(e))


def test_fetch_feed_redacts_an_escaped_token_in_an_error():
    import mirror_parity as mp
    tok = "s3cr\u00e9t-x"

    def boom(req, timeout=None):
        raise ValueError(f"Invalid header value {tok.encode()!r} and {tok!r}")
    try:
        mp.fetch_feed("https://e.example", tok, opener=boom)
        raise AssertionError("no error")
    except RuntimeError as e:
        msg = str(e)
        assert "s3cr" not in msg and "***" in msg


def test_the_feed_read_has_an_overall_deadline(tmp_path):
    import time

    def slow():
        time.sleep(5)
        return feed()
    t0 = time.monotonic()
    lines, alerts = preclose.first_buy([row("HARV", {"ZVOL": 1.0})], env={}, fetch=slow, path=tmp_path / "k.json",
                                       deadline=0.3)
    assert time.monotonic() - t0 < 2.0
    assert "no answer within" in lines[0] and alerts == []


def _run_main(monkeypatch, capsys, led, alerts=(), capture_prices=None, argv=("preclose.py",)):
    """preclose.main() with the preview stubbed: (exit code, stdout, the prices first_buy received)"""
    import types
    seen = {}

    def fake_preview(now, get_meta, get_drift=None, fetch=None, quotes=None, capture=None, pin=False):
        if capture is not None and capture_prices is not None:
            capture.update(prices=capture_prices)
        return ["PRE-CLOSE line"], list(alerts), list(led)

    def fake_first_buy(led_, env=None, fetch=None, path=None, save=True, prices=None, deadline=None):
        seen.update(prices=prices, save=save)
        return ["first-buy line"], ["FIRST BUY ON IBKR — HARV is set to buy ZVOL at ~15:50, x."]
    monkeypatch.setattr(preclose, "preview", fake_preview)
    monkeypatch.setattr(preclose, "first_buy", fake_first_buy)
    monkeypatch.setattr(preclose, "append_ledger", lambda rows, path=None: None)
    monkeypatch.setitem(sys.modules, "composerlib", types.SimpleNamespace(get=lambda *a, **k: {}, default_account=lambda: "x"))
    monkeypatch.setattr(sys, "argv", list(argv))
    try:
        preclose.main()
    except SystemExit as e:
        return e.code, capsys.readouterr().out, seen
    raise AssertionError("main did not exit")


def test_main_passes_the_preview_prices_and_prints_the_alert(monkeypatch, capsys):
    led = [{"engine": "GATE", "date": "2026-11-17", "time": "15:15", "left": 35}, row("HARV", {"ZVOL": 1.0})]
    code, out, seen = _run_main(monkeypatch, capsys, led, capture_prices={"ZVOL": 6.7})
    assert code == 2 and seen["prices"] == {"ZVOL": 6.7} and seen["save"] is True
    assert out.index("PRE-CLOSE line") < out.index("first-buy line") < out.index("ALERT(S):")
    assert "!! FIRST BUY ON IBKR — HARV" in out


def test_main_no_ledger_does_not_save_and_no_first_buy_skips(monkeypatch, capsys):
    led = [{"engine": "GATE"}, row("HARV", {"ZVOL": 1.0})]
    code, out, seen = _run_main(monkeypatch, capsys, led, argv=("preclose.py", "--no-ledger"))
    assert seen["save"] is False
    code, out, seen = _run_main(monkeypatch, capsys, led, argv=("preclose.py", "--no-first-buy"))
    assert seen == {} and code == 0 and "first-buy" not in out


def test_main_says_when_no_preview_ran_but_not_on_a_no_session_day(monkeypatch, capsys):
    code, out, seen = _run_main(monkeypatch, capsys, [], alerts=["PRE-CLOSE UNAVAILABLE — no live SPY price."])
    assert "first-buy check: not run (no preview rows)" in out and seen == {}
    code, out, seen = _run_main(monkeypatch, capsys, [])                  # no session: the single line only
    assert out.strip() == "PRE-CLOSE line" and code == 0


# ---- round-5 verifiers: untested behaviours, now gated --------------------------------------------
def test_market_alternatives_are_read():
    r = {"engine": "HARV", "status": "ok", "after": {"PULS": 1.0}, "target": {"PULS": 1.0}, "label": "close call",
         "market": {"-2": {"PULS": 0.3, "ZVOL": 0.7}}}
    lines, alerts = fb.first_buy_alerts([r], {"PULS"}, feed())
    assert len(alerts) == 1 and "HARV ZVOL (close call; market -2 sigma)" in alerts[0]
    r2 = dict(r, market={"2": {"PULS": 0.3, "SVIX": 0.7}})                      # a positive key reads with its sign
    assert "HARV SVIX (close call; market +2 sigma)" in fb.first_buy_alerts([r2], {"PULS"}, feed())[1][0]


def test_a_fund_in_the_main_alert_is_not_repeated_in_the_combined_one():
    r = {"engine": "HARV", "status": "ok", "after": {"ZVOL": 1.0}, "target": {"ZVOL": 1.0}, "label": "could flip",
         "flip": {"ticker": "SPY", "move": -0.003, "sigma": 1.2, "instead": {"ZVOL": 0.5, "SVIX": 0.5}}}
    lines, alerts = fb.first_buy_alerts([r], set(), feed())
    assert len(alerts) == 2 and "ZVOL" in alerts[0] and "SVIX" in alerts[1] and "ZVOL" not in alerts[1]


def test_a_daily_engines_alternative_is_read_with_floor_zero():
    r = {"engine": "HARV", "status": "ok", "after": {"PULS": 1.0}, "target": {"PULS": 1.0}, "label": "could flip",
         "flip": {"ticker": "SPY", "move": -0.003, "sigma": 1.2, "instead": {"PULS": 0.996, "NEW": 0.004}}}
    assert "HARV NEW" in fb.first_buy_alerts([r], {"PULS"}, feed())[1][0]


def test_threshold_path_reads_the_target_with_floor_zero():
    fs = {"equity": 10000.0, "cash": 800.0, "shares": {"A": 92}, "weights": {"A": 0.92}, "rule": "threshold", "corridor": 0.1}
    r = row("KMLM", after={"A": 1.0}, target={"A": 0.996, "X": 0.004}, corridor=0.10)
    lines, alerts = fb.first_buy_alerts([r], {"A"}, feed(sleeves={"KMLM": fs}), prices={"A": 100.0})
    assert len(alerts) == 1 and "X" in alerts[0]


def test_rule_merge_both_directions_and_no_corridor():
    base = {"equity": 10000.0, "cash": 0.0, "shares": {"A": 100}, "weights": {"A": 1.0}, "rule": "threshold", "corridor": 0.1}
    target = {"A": 0.95, "X": 0.05}                                   # gap 0.05: a 0.10 corridor holds
    # manifest daily (row corridor None), feed threshold: daily wins
    assert fb.first_buy_alerts([row("KMLM", after={"A": 1.0}, target=target)], {"A"}, feed(sleeves={"KMLM": base}))[1]
    # manifest's corridor the smaller one (0.04): it is used
    assert fb.first_buy_alerts([row("KMLM", after={"A": 1.0}, target=target, corridor=0.04)], {"A"},
                               feed(sleeves={"KMLM": base}))[1]
    # a threshold with no corridor (None or 0) trades daily, and never raises
    for c in (None, 0):
        lines, alerts = fb.first_buy_alerts([row("KMLM", after={"A": 1.0}, target=target, corridor=0.10)], {"A"},
                                            feed(sleeves={"KMLM": dict(base, corridor=c)}))
        assert len(alerts) == 1, c


def test_an_exit_inside_preview_check_never_escapes_first_buy(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise SystemExit("x")
    monkeypatch.setattr(fb, "preview_check", boom)
    lines, alerts = preclose.first_buy([row("HARV", {"ZVOL": 1.0})], env={}, fetch=lambda: feed(), path=tmp_path / "k.json")
    assert alerts == [] and lines[0].startswith("first-buy check failed")


# ---- final round (verifier of the round-5 follow-ups) ----------------------------------------------
def test_a_gate_side_pushes_even_when_hgs_own_firm_flip_is_the_gate(tmp_path):
    """with the gate 2-3 sigma away, HG's closest flip IS the gate crossing and HG is 'firm': the gate
    side must still push (the firm flip's line must not swallow it)"""
    led = [{"engine": "GATE", "date": "2026-11-18", "time": "15:15", "left": 35, "sigma": 2.5, "open": False,
            "open_prev": False, "sides": [{"TQQQ": 1.0}, {"BIL": 1.0}]},
           dict(row("HG", {"BIL": 1.0}), label="firm",
                flip={"ticker": "SPY", "move": 0.0061, "sigma": 2.5, "instead": {"TQQQ": 1.0}})]
    lines, alerts = preclose.first_buy(led, env={}, fetch=lambda: feed({"BIL": 1}), path=tmp_path / "k.json")
    assert len(alerts) == 1 and "HG TQQQ (firm; SPY across its 200-day)" in alerts[0]


def test_the_gate_side_radius_is_flip_max(tmp_path):
    def led(sigma):
        return [{"engine": "GATE", "date": "2026-11-18", "time": "15:15", "left": 35, "sigma": sigma, "open": True,
                 "open_prev": True, "sides": [{"BIL": 1.0}, {"TQQQ": 1.0}]}, dict(row("HG", {"BIL": 1.0}), label="firm")]
    inside = preclose.first_buy(led(preclose.FLIP_MAX - 0.1), env={}, fetch=lambda: feed({"BIL": 1}), path=tmp_path / "a.json")
    outside = preclose.first_buy(led(preclose.FLIP_MAX + 0.1), env={}, fetch=lambda: feed({"BIL": 1}), path=tmp_path / "b.json")
    edge = preclose.first_buy(led(preclose.FLIP_MAX), env={}, fetch=lambda: feed({"BIL": 1}), path=tmp_path / "c.json")
    assert len(inside[1]) == 1 and outside[1] == [] and len(edge[1]) == 1     # the gate sigma is rounded: 3.00 occurs


def test_one_rows_alternatives_list_a_fund_once():
    r = {"engine": "HARV", "status": "ok", "after": {"PULS": 1.0}, "target": {"PULS": 1.0}, "label": "close call",
         "flip": {"ticker": "SPY", "move": -0.003, "sigma": 1.2, "instead": {"PULS": 0.5, "ZVOL": 0.5}},
         "market": {"-2": {"PULS": 0.3, "ZVOL": 0.7}, "-1": {"PULS": 0.4, "ZVOL": 0.6}}}
    alerts = fb.first_buy_alerts([r], {"PULS"}, feed())[1]
    assert len(alerts) == 1 and alerts[0].count("ZVOL") == 1


# ---- verifier of the final round (2026-11-17) --------------------------------------------------------
def test_several_new_funds_read_them():
    _, alerts = fb.first_buy_alerts([row("HARV", {"ZVOL": 0.5, "UVXY": 0.5})], KNOWN_1116, feed())
    assert len(alerts) == 1 and "UVXY, ZVOL" in alerts[0] and "the sleeve buys them when its rule next trades" in alerts[0]


def test_a_non_firm_row_names_the_nearer_flip_not_the_gate():
    """gate sides go first only on a firm call; on a close call the preview's closest flip (here 0.28 sigma)
    is named, not the farther gate crossing (verifier's NOTE, 2026-11-17)"""
    r = dict(row("HG", {"BIL": 1.0}), label="close call", alts=[{"QLD": 1.0}, {"BIL": 1.0}],
             flip={"ticker": "TQQQ", "move": -0.002, "sigma": 0.28, "instead": {"QLD": 1.0}})
    _, alerts = fb.first_buy_alerts([r], {"BIL"}, feed())
    assert len(alerts) == 1 and "HG QLD (close call; TQQQ -0.20%, 0.28 sigma)" in alerts[0]
    assert "SPY across its 200-day" not in alerts[0]
    firm = dict(r, label="firm")                                   # firm: the gate side is read first and pushes
    lines, alerts = fb.first_buy_alerts([firm], {"BIL"}, feed())
    assert len(alerts) == 1 and "HG QLD (firm; SPY across its 200-day)" in alerts[0] and lines == []


import unittest  # noqa: E402


class TestRunsUnderPytest(unittest.TestCase):
    """The tests above are pytest functions (tmp_path, monkeypatch, capsys) that `python3 -m unittest`
    does not collect: it reported 'Ran 0 tests ... OK' for this file (verifier, 2026-11-17). Under
    unittest this one test runs the file with pytest (without an inherited PYTEST_ADDOPTS or
    PYTEST_CURRENT_TEST), and fails if pytest is missing or any test fails or is deselected."""

    def test_the_first_buy_gate_tests_run_under_pytest(self):
        if os.environ.get("PYTEST_CURRENT_TEST") and "_pytest" in sys.modules:   # inside pytest: they ran
            self.skipTest("running under pytest")
        import importlib.util
        import shutil
        import subprocess
        if importlib.util.find_spec("pytest") is not None:
            cmd = [sys.executable, "-m", "pytest"]
        else:
            exe = shutil.which("pytest") or os.path.expanduser("~/.local/bin/pytest")
            if not os.path.exists(exe):
                self.fail("pytest not found: the first-buy gate tests in this file did not run")
            cmd = [exe]
        env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_ADDOPTS", "PYTEST_CURRENT_TEST")}
        r = subprocess.run(cmd + ["-q", "-p", "no:cacheprovider", os.path.abspath(__file__)], capture_output=True,
                           text=True, timeout=900, cwd=os.path.dirname(os.path.dirname(SCRIPTS)), env=env)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out[-3000:])
        self.assertRegex(out, r"\b\d+ passed")
        self.assertNotRegex(out, r"\b\d+ (failed|errors?|deselected)\b")
