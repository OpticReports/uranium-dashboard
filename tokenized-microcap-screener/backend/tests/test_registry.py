"""Gate tests for the classifier. The squatter tests are the merge-blocking
ones: if a memecoin that merely adopts a listed ticker as its symbol can pass
as a tokenized equity, every downstream number is garbage."""
from __future__ import annotations

import pytest

from app.engine.registry import classify_token, names_match, normalize_company


def test_normalize_strips_legal_suffixes():
    assert normalize_company("Farmmi, Inc.") == "farmmi"
    assert normalize_company("MICRON TECHNOLOGY INC") == "micron"
    assert normalize_company("GameStop Corp.") == "gamestop"
    assert normalize_company("Reddit, Inc.") == "reddit"


def test_normalize_never_shortens_on_substring():
    # "co" is a legal token but must only be dropped as a WHOLE word.
    assert normalize_company("Coca Cola Co") == "cocacola"


def test_names_match_rejects_short_coincidences():
    assert not names_match("AI", "APPLIED INDUSTRIAL TECHNOLOGIES INC")
    assert names_match("NVIDIA", "NVIDIA CORP")
    assert names_match("Farmmi, Inc.", "Farmmi, Inc.")


def test_official_robinhood_wrapper_classifies(universe, markers, base_assets):
    tok = {"address": "0xff08", "symbol": "MU",
           "name": "Micron Technology • Robinhood Token"}
    view = classify_token(tok, "robinhood", universe, markers, base_assets)
    assert view is not None
    assert view.ticker == "MU"
    assert view.issuer_class == "OFFICIAL_ROBINHOOD"


def test_unofficial_wrapper_classifies_and_is_labelled(universe, markers, base_assets):
    """The Farmmi case: the SEC title byte-for-byte, but no issuer marker."""
    tok = {"address": "0x5D2e", "symbol": "FAMI", "name": "Farmmi, Inc."}
    view = classify_token(tok, "robinhood", universe, markers, base_assets)
    assert view is not None
    assert view.ticker == "FAMI"
    assert view.issuer_class == "UNOFFICIAL"


@pytest.mark.parametrize("name,symbol", [
    ("MU MU THE BULL", "MU"),      # real squatter seen on Robinhood Chain
    ("NVDA", "NVDA"),              # symbol echo, no company name
    ("Money Mushroom", "JINQIAN"),
    ("Super Farmmi", "FARMMI"),
])
def test_ticker_squatters_are_rejected(name, symbol, universe, markers, base_assets):
    tok = {"address": "0xdead", "symbol": symbol, "name": name}
    assert classify_token(tok, "robinhood", universe, markers, base_assets) is None


def test_base_assets_are_never_equities(universe, markers, base_assets):
    for sym in ("ETH", "USDG", "WETH", "SOL"):
        tok = {"address": "0x0", "symbol": sym, "name": "Global Dollar"}
        assert classify_token(tok, "robinhood", universe, markers, base_assets) is None


def test_marker_cannot_be_copied_into_a_squatters_name(universe, markers, base_assets):
    """A squatter pasting the marker into its name must still fail the name
    test, or the marker becomes a free pass."""
    tok = {"address": "0xbad", "symbol": "MU",
           "name": "MU MU THE BULL • Robinhood Token"}
    assert classify_token(tok, "robinhood", universe, markers, base_assets) is None
