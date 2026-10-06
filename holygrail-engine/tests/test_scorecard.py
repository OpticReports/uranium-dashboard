"""Full offline pipeline: book -> data (synthetic cache) -> moments -> scorecard."""
import numpy as np
import pytest

from holygrail.book import load_book
from holygrail.scorecard import ScoreSettings, prepare_moments, score_book, scorecard, scorecard_markdown


def test_scorecard_offline_pipeline(test_book_yaml, offline_loader):
    book = load_book(test_book_yaml)
    sc = score_book(book, offline_loader, view="investable")
    assert sc["nav_usd"] == pytest.approx(100_000)
    rows = {r["stream"]: r for r in sc["streams"]}
    assert set(rows) == {"EQA", "BND", "GLDX", "CRYX", "LEV", "NAV", "LOAN", "cash"}
    assert sum(r["dollar_share"] for r in rows.values()) == pytest.approx(1.0)
    assert sum(r["risk_share"] for r in rows.values()) == pytest.approx(1.0)
    assert rows["cash"]["risk_share"] == 0 and rows["cash"]["good"] is None
    assert rows["EQA"]["mu_basis"] == "assumption" and rows["BND"]["mu_basis"] == "historical_in_sample"
    assert rows["LEV"]["mu_basis"].startswith("look-through")
    eb = sc["effective_bets"]
    assert {r["measure"] for r in eb["rows"]} == {"dr2", "equal_rho", "pca_entropy", "prc_inverse_hhi", "min_torsion"}
    assert eb["dr2"] == pytest.approx(eb["dr"] ** 2)
    types = {f["type"] for f in sc["flags"]}
    assert "position_concentration" in types and "few_bets" in types
    env = sc["environment"]
    assert sum(env["risk_share"].values()) + env["unmapped_risk_share"] == pytest.approx(1.0)
    assert env["mapping"]["CRYX"]["source"] == "manual"
    g = sc["gearing"]
    assert g["leverage_to_target"] == pytest.approx(0.10 / sc["portfolio"]["vol"])
    h = sc["honesty"]
    assert "NOT forecasts" in h["measurement_basis"]["warning"]
    assert h["measurement_basis"]["risk_free"]["basis"] == "measured"
    assert any(a["item"] == "LOAN.default.prob" for a in h["assumptions"])
    assert any(a["item"] == "LEV.financing_spread" for a in h["assumptions"])
    assert any("stale" in x for x in h["not_modelled"]) and any("jumps" in x for x in h["not_modelled"])
    assert h["non_market_marks"][0]["position"] == "G"
    assert h["provenance"]["EQA"]["warnings"] == ["SYNTHETIC test series"]
    md = scorecard_markdown(sc)
    for section in ("Effective number of bets", "Risk share vs dollar share", "Flags", "Environment balance",
                    "Gearing", "Honesty", "NOT modelled"):
        assert section in md


def test_scorecard_whole_view_and_filters(test_book_yaml, offline_loader):
    book = load_book(test_book_yaml)
    whole = score_book(book, offline_loader, view="whole")
    assert whole["nav_usd"] == pytest.approx(110_000)
    crypto = score_book(book, offline_loader, view="whole", exclude_tags=["crypto", "spending"])
    assert "CRYX" not in {r["stream"] for r in crypto["streams"]}
    st = ScoreSettings.from_book(book, target_vol=0.2)
    assert st.target_vol == 0.2 and st.window_years == 4
    v = book.view("investable")
    m, prov, rf, sp, rets = prepare_moments(book, v, offline_loader, st)
    sc = scorecard(book, v, m, st, rf_info=rf, spread_info=sp, provenance=prov)
    assert sc["gearing"]["target_vol"] == 0.2
    assert rets.index[-1] <= np.datetime64("2026-09-30")
