"""Gates for the first-buy warning (2026-11-16 ZVOL: IBKR discarded the mirror's first ZVOL buy pending a
one-time token verification that the API never names)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import mirror_firstbuy as fb  # noqa: E402
import preclose  # noqa: E402

ZVOL_HOW = "cancelled ([202] Order Canceled - reason:Order was discarded.)"


def feed(positions=None, history=None):
    return {"kind": "mirror-feed", "books": {"live": {"book": {"positions": positions or {}}, "history": history or []}}}


def row(engine, after, status="ok"):
    return {"engine": engine, "status": status, "after": after}


# ---- known set -------------------------------------------------------------------------------
def test_known_is_positions_plus_filled_buys_only():
    f = feed({"BIL": 183, "BOXX": 0}, [{"orders": [
        {"side": "BUY", "symbol": "TECL", "filled": 5, "qty": 5},
        {"side": "BUY", "symbol": "ZVOL", "filled": 0, "qty": 760, "how": ZVOL_HOW},   # rejected: not known
        {"side": "SELL", "symbol": "SOXL", "filled": 3, "qty": 3}]}])                     # a sell is not a buy
    assert fb.known_from_feed(f) == {"BIL", "TECL"}


def test_known_persists_across_the_feed_window(tmp_path):
    p = tmp_path / "ibkr-bought.json"
    fb.preview_check([], feed({"VXZ": 10}), p)
    assert json.loads(p.read_text())["bought"] == ["VXZ"]
    # VXZ sold and aged out of the feed's history: still known
    lines, alerts = fb.preview_check([row("HG", {"VXZ": 1.0})], feed({"BIL": 1}), p)
    assert alerts == [] and set(json.loads(p.read_text())["bought"]) == {"VXZ", "BIL"}


def test_missing_or_corrupt_store_is_empty(tmp_path):
    p = tmp_path / "x.json"
    assert fb.load_known(p) == set()
    p.write_text("not json")
    assert fb.load_known(p) == set()


# ---- the 15:15 alert ---------------------------------------------------------------------------
def test_the_2026_11_16_case_alerts_both_engines():
    known = {"BIL", "BOXX", "PULS", "SOXL", "SQQQ", "TECL", "VXZ"}
    alerts = fb.first_buy_alerts([row("KMLM", {"SQQQ": 0.75, "ZVOL": 0.13, "PULS": 0.12}),
                                  row("HARV", {"ZVOL": 0.52, "PULS": 0.48}),
                                  row("HG", {"BIL": 1.0})], known)
    assert len(alerts) == 2
    assert alerts[0].startswith("FIRST BUY ON IBKR — KMLM") and "ZVOL" in alerts[0]
    assert alerts[1].startswith("FIRST BUY ON IBKR — HARV")


def test_no_alert_when_every_fund_is_known():
    assert fb.first_buy_alerts([row("HG", {"BIL": 1.0})], {"BIL"}) == []


def test_skips_gate_unavailable_and_dust():
    rows = [row("GATE", {"NEW": 1.0}), row("SLEEVE", {"NEW": 1.0}, status="unavailable"),
            row("HG", {"BIL": 0.997, "DUST": 0.003})]
    assert fb.first_buy_alerts(rows, {"BIL"}) == []


def test_unread_feed_is_a_line_not_an_alert(tmp_path):
    lines, alerts = fb.preview_check([row("HARV", {"ZVOL": 1.0})], None, tmp_path / "k.json")
    assert alerts == [] and "not checked" in lines[0]


# ---- preclose wiring --------------------------------------------------------------------------
def test_preclose_without_env_does_nothing():
    assert preclose.first_buy([row("HARV", {"ZVOL": 1.0})], env={}) == ([], [])


def test_preclose_uses_the_feed_and_skips_the_gate_row(tmp_path):
    led = [{"engine": "GATE", "status": "open"}, row("HARV", {"ZVOL": 0.52, "PULS": 0.48})]
    lines, alerts = preclose.first_buy(led, env={}, fetch=lambda: feed({"PULS": 59}), path=tmp_path / "k.json")
    assert lines == [] and len(alerts) == 1 and "ZVOL" in alerts[0] and "PULS" not in alerts[0].split("buy ")[1].split(" at")[0]


def test_preclose_feed_failure_never_raises(tmp_path):
    def boom():
        raise RuntimeError("HTTP 401: the read token was refused")
    lines, alerts = preclose.first_buy([row("HARV", {"ZVOL": 1.0})], env={}, fetch=boom, path=tmp_path / "k.json")
    assert alerts == [] and "not checked" in lines[0]


# ---- the parity UNFILLED hint -----------------------------------------------------------------
def test_discard_hint_names_the_fund_and_the_fix():
    h = fb.discard_hint([{"symbol": "ZVOL", "qty": 760, "filled": 0, "how": ZVOL_HOW},
                         {"symbol": "BIL", "qty": 1, "filled": 1, "how": "filled"}])
    assert "ZVOL" in h and "BIL" not in h and "verify" in h


def test_no_hint_for_other_cancellations():
    assert fb.discard_hint([{"symbol": "X", "qty": 5, "filled": 2, "how": "cancelled at the window's end"}]) == ""
    assert fb.discard_hint([{"symbol": "Z", "qty": 5, "filled": 5, "how": ZVOL_HOW}]) == ""   # filled: no hint
