"""GATE: book totals reconcile and unknown streams fail.  Plus schema, views
and look-through."""
from pathlib import Path

import pytest
import yaml

from holygrail.book import book_from_dict, load_book
from holygrail.errors import AssumptionError, ReconciliationError, UnknownStreamError, ValidationError

EXAMPLE = Path(__file__).resolve().parents[1] / "books" / "example.yaml"
A = {"value": 0.05, "source": "t", "confidence": "low"}


def _raw(**over):
    raw = {
        "name": "t",
        "streams": {"SPY": {"type": "market", "symbol": "SPY"}, "cash": {"type": "cash"},
                    "L": {"type": "composite", "components": {"SPY": 1.0}, "leverage": 2.0, "financing_spread": A}},
        "positions": [{"name": "a", "value_usd": 600, "stream": "SPY", "sleeve": "core"},
                      {"name": "b", "value_usd": 300, "stream": "L", "sleeve": "core", "tags": ["lev"]},
                      {"name": "c", "value_usd": 100, "stream": "cash", "sleeve": "cash", "investable": False}],
        "totals": {"total_usd": 1000, "sleeves": {"core": 900, "cash": 100}},
    }
    raw.update(over)
    return raw


def test_example_book_loads_and_reconciles():
    b = load_book(EXAMPLE)
    assert b.total_usd == pytest.approx(230_000)
    assert b.view("investable").total_usd == pytest.approx(200_000)
    assert b.view("liquid").total_usd == pytest.approx(200_000)
    assert b.universe["private_credit"].expected_return.source.startswith("derived")


def test_totals_reconcile_or_fail():
    book_from_dict(_raw())
    with pytest.raises(ReconciliationError, match="declared 1,001.50"):
        book_from_dict(_raw(totals={"total_usd": 1001.5}))
    with pytest.raises(ReconciliationError, match="sleeve 'core'"):
        book_from_dict(_raw(totals={"total_usd": 1000, "sleeves": {"core": 800, "cash": 200}}))
    with pytest.raises(ReconciliationError, match="not declared"):
        book_from_dict(_raw(totals={"sleeves": {"core": 900}}))
    assert book_from_dict(_raw(totals={"total_usd": 1000.4})).total_usd == 1000  # within $1 tolerance
    assert book_from_dict(_raw(totals=None)).warnings  # no totals is allowed but noted


def test_unknown_stream_fails():
    raw = _raw()
    raw["positions"][0]["stream"] = "QQQ"
    with pytest.raises(UnknownStreamError, match="QQQ"):
        book_from_dict(raw)
    raw = _raw()
    raw["streams"]["L"]["components"] = {"IWM": 1.0}
    with pytest.raises(UnknownStreamError, match="IWM"):
        book_from_dict(raw)


def test_schema_failures_are_loud():
    raw = _raw(); raw["streams"]["SPY"]["expected_return"] = 0.07
    with pytest.raises(AssumptionError, match="bare"):
        book_from_dict(raw)
    raw = _raw(); raw["streams"]["SPY"]["expected_return"] = "@missing"
    with pytest.raises(AssumptionError, match="undefined"):
        book_from_dict(raw)
    raw = _raw(); raw["positions"][0]["value_usd"] = -5
    with pytest.raises(ValidationError, match="liability"):
        book_from_dict(raw)
    raw = _raw(); raw["positions"][0]["colour"] = "red"
    with pytest.raises(ValidationError, match="unknown keys"):
        book_from_dict(raw)
    raw = _raw(); raw["streams"]["SPY"]["tickr"] = "x"
    with pytest.raises(ValidationError, match="unknown keys"):
        book_from_dict(raw)
    raw = _raw(); raw["positions"][1]["name"] = "a"
    with pytest.raises(ValidationError, match="duplicate"):
        book_from_dict(raw)
    raw = _raw(); raw["positions"][0]["liquidity"] = "very"
    with pytest.raises(ValidationError, match="liquidity"):
        book_from_dict(raw)
    raw = _raw(); raw["settings"] = {"risk_free": 0.04}
    with pytest.raises(AssumptionError):
        book_from_dict(raw)


def test_named_assumptions_and_liabilities():
    raw = _raw(assumptions={"mu": A})
    raw["streams"]["SPY"]["expected_return"] = "@mu"
    raw["positions"].append({"name": "loan", "value_usd": -100, "stream": "cash", "sleeve": "cash", "liability": True})
    raw["totals"] = {"total_usd": 900, "sleeves": {"core": 900, "cash": 0}}
    b = book_from_dict(raw)
    assert b.universe["SPY"].expected_return.value == 0.05 and b.total_usd == 900


def test_views_and_look_through():
    b = book_from_dict(_raw())
    w = b.view("whole")
    assert w.total_usd == 1000 and w.weights()["SPY"] == pytest.approx(0.6)
    inv = b.view("investable")
    assert inv.total_usd == 900 and "cash" not in inv.streams
    assert b.view("whole", include_tags=["lev"]).total_usd == 300
    assert b.view("whole", exclude_tags=["lev"]).total_usd == 700
    assert b.view("whole", sleeves=["cash"]).total_usd == 100
    lt = inv.look_through_usd(b.universe)
    assert lt["SPY"] == pytest.approx(600 + 2 * 300) and lt["__rf__"] == pytest.approx(-300)
    with pytest.raises(ValidationError, match="no positions"):
        b.view("whole", include_tags=["nothing"])
    with pytest.raises(ValidationError):
        b.view("bogus")
