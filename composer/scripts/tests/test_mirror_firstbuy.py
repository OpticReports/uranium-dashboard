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
    assert fb.load_known(p) == (set(), None)
    p.write_text("not json")
    assert fb.load_known(p) == (set(), None)


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

    def spy(rows, known, f=None):
        seen.update({r["engine"]: r.get("corridor") for r in rows})
        return real(rows, known, f)
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


# ---- the parity UNFILLED hint -----------------------------------------------------------------
def test_discard_hint_names_the_fund_and_the_fix():
    h = fb.discard_hint([{"symbol": "ZVOL", "qty": 760, "filled": 0, "how": ZVOL_HOW},
                         {"symbol": "BIL", "qty": 1, "filled": 1, "how": "filled"}])
    assert "ZVOL" in h and "BIL" not in h and "verify" in h and "until its rule next trades" in h


def test_no_hint_for_other_cancellations():
    assert fb.discard_hint([{"symbol": "X", "qty": 5, "filled": 2, "how": "cancelled at the window's end"}]) == ""
    assert fb.discard_hint([{"symbol": "Z", "qty": 5, "filled": 5, "how": ZVOL_HOW}]) == ""   # filled: no hint
