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


def test_no_alert_when_every_fund_is_known():
    assert fb.first_buy_alerts([row("HG", {"BIL": 1.0})], {"BIL"}, feed()) == ([], [])


def test_skips_gate_unavailable_dust_and_non_numbers():
    rows = [row("GATE", {"NEW": 1.0}), row("SLEEVE", {"NEW": 1.0}, status="unavailable"),
            row("HG", {"BIL": 0.997, "DUST": 0.003, "ODD": "x"})]
    assert fb.first_buy_alerts(rows, {"BIL"}, feed()) == ([], [])


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
    assert fb.queued(feed(pending=[{"kind": "credit", "sleeve": "KMLM", "amount": -200.0}]), "KMLM") == (False, -200.0)
    fs = {"equity": 10000.0, "cash": 100.0, "shares": {"A": 100}, "weights": {"A": 0.99}}
    assert fb.sleeve_will_reach_target(fs, {"A": 0.95, "X": 0.05}, 0.10, add_cash=-200.0, prices={"A": 99.0}) is True


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
