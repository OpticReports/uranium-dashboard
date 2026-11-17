"""Gates for the first-buy warning (2026-11-16 ZVOL: IBKR discarded the mirror's first ZVOL buy pending a
one-time token verification that the API never names). Review 2026-11-17 (D1-D8) cases included."""
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


def feed(positions=None, history=None, mode="live", engines=("HG", "KMLM", "SLEEVE", "HARV"), sleeves=None):
    return {"kind": "mirror-feed", "books": {"live": {
        "mode": mode, "engines": list(engines),
        "book": {"positions": positions or {}, "sleeves": sleeves or {}}, "history": history or []}}}


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
    sleeves: whenever the executor trades, the warning must say it will (a false positive is allowed
    only inside the 1-point slack)"""
    import importlib.util
    path = os.path.join(SCRIPTS, "..", "..", "ibkr-executor", "app", "mirror_core.py")
    spec = importlib.util.spec_from_file_location("mirror_core_for_test", path)
    mc = importlib.util.module_from_spec(spec)
    sys.modules["mirror_core_for_test"] = mc
    spec.loader.exec_module(mc)
    cfg = mc.Config()
    prices = {"A": 50.0, "C": 25.0, "X": 10.0}
    target = {"A": 0.40, "X": 0.08, "C": 0.52}
    misses, checked = [], 0
    for a_sh in range(40, 140, 7):
        for c_sh in range(80, 260, 11):
            for cash in (-10.0, 0.0, 150.0, 400.0, 700.0):
                sl = mc.Sleeve(name="KMLM", rule=mc.RULE_THRESHOLD, corridor=0.10, cash=cash,
                               shares={"A": a_sh, "C": c_sh})
                d = mc.decide_sleeve(sl, target, prices, cfg)
                eq = mc.equity(sl, prices)
                w = {k: v for k, v in mc.weights(sl, prices).items() if k != "cash"}
                feed_sleeve = {"equity": eq, "cash": cash, "weights": w}
                warn = fb._sleeve_will_reach_target(feed_sleeve, target, 0.10)
                checked += 1
                if d["action"] == "trade" and not warn:
                    misses.append((a_sh, c_sh, cash, round(d["gap"], 4)))
    assert checked > 100 and misses == []


def test_corridor_target_not_tripping_is_a_line_not_an_alert():
    sl = {"KMLM": {"equity": 10000, "cash": 10, "weights": {"SQQQ": 0.75, "PULS": 0.25}}}
    r = row("KMLM", after={"SQQQ": 0.75, "PULS": 0.25}, target={"SQQQ": 0.75, "ZVOL": 0.05, "PULS": 0.20}, corridor=0.1)
    lines, alerts = fb.first_buy_alerts([r], KNOWN_1116, feed(sleeves=sl))
    assert alerts == [] and "corridor does not trip" in lines[0]


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


def test_the_fallback_uses_the_engines_saved_with_the_set(tmp_path):
    p = tmp_path / "k.json"
    fb.save_known({"BIL"}, p, "2026-11-16", {"HG", "HARV"})
    lines, alerts = fb.preview_check([row("SLEEVE", {"NEW": 1.0}), row("HARV", {"ZVOL": 1.0})], None, p)
    assert len(alerts) == 1 and "HARV" in alerts[0]


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
