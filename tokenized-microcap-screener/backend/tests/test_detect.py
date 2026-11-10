"""Gate tests for launch detection, run against the REAL /token-pairs/v1
response for the tokenized Farmmi token captured on 2026-09-02."""
from __future__ import annotations

from app.engine.detect import detect_launch, detect_launches, equity_tokens_in


def _by(pairs, base, quote):
    for p in pairs:
        if p["baseToken"]["symbol"] == base and p["quoteToken"]["symbol"] == quote:
            return p
    raise AssertionError(f"fixture missing {base}/{quote}")


def test_jinqian_fami_is_a_launch(fami_pairs, universe, markers, base_assets):
    launch = detect_launch(_by(fami_pairs, "JINQIAN", "FAMI"),
                           universe, markers, base_assets)
    assert launch is not None
    assert launch.equity.ticker == "FAMI"
    assert launch.equity.issuer_class == "UNOFFICIAL"
    assert launch.meme_symbol == "JINQIAN"
    assert launch.liquidity_usd > 1_000_000
    assert launch.volume_h24 > 1_000_000


def test_stable_and_native_quotes_are_not_launches(fami_pairs, universe, markers,
                                                   base_assets):
    """USDG/FAMI is the wrapper's own liquidity pool, FAMI/ETH its native pool.
    Neither is a meme launch, and counting them would inflate every cluster."""
    for base, quote in (("USDG", "FAMI"), ("FAMI", "ETH")):
        assert detect_launch(_by(fami_pairs, base, quote), universe, markers,
                             base_assets) is None


def test_symbol_collision_impersonator_is_not_a_launch(fami_pairs, universe,
                                                       markers, base_assets):
    """The real FAMI/FAMI row: a second token also calling itself FAMI, pooled
    against the genuine wrapper. It is impersonation or wrapper arb, not a new
    meme, and counting it would let empty copycat pools fake a cluster."""
    pair = _by(fami_pairs, "FAMI", "FAMI")
    assert pair["baseToken"]["address"] != pair["quoteToken"]["address"]
    assert detect_launch(pair, universe, markers, base_assets) is None


def test_nvda_fixture_is_all_wrappers_and_lookalikes(nvda_pairs, universe,
                                                     markers, base_assets):
    """Every NVDA row captured on 2026-09-02 is either the official wrapper's
    own pool, an unofficial wrapper, or a bare-echo lookalike named "NVDA".
    None is a meme launch, and the detector must say so rather than manufacture
    one — a screen that finds a launch in this data would find one anywhere."""
    assert detect_launches(nvda_pairs, universe, markers, base_assets) == []


def test_official_wrapper_is_recognised_in_the_nvda_fixture(nvda_pairs, universe,
                                                            markers, base_assets):
    tokens = equity_tokens_in(nvda_pairs, universe, markers, base_assets)
    classes = {t.issuer_class for t in tokens if t.ticker == "NVDA"}
    assert "OFFICIAL_ROBINHOOD" in classes


def test_mu_squatter_is_the_meme_side_not_the_equity(mu_pairs, universe, markers,
                                                     base_assets):
    """'MU MU THE BULL' pooled against the official Micron wrapper must resolve
    with Micron as the EQUITY and the squatter as the meme — never the reverse."""
    launches = detect_launches(mu_pairs, universe, markers, base_assets)
    hits = [l for l in launches if l.meme_name == "MU MU THE BULL"]
    assert hits
    for l in hits:
        assert l.equity.ticker == "MU"
        assert l.equity.issuer_class == "OFFICIAL_ROBINHOOD"


def test_cluster_is_visible_in_the_real_fami_data(fami_pairs, universe, markers,
                                                  base_assets):
    """The cascade signature: many distinct memes against ONE ticker."""
    launches = detect_launches(fami_pairs, universe, markers, base_assets)
    assert all(l.equity.ticker == "FAMI" for l in launches)
    memes = {l.meme_symbol for l in launches}
    assert {"JINQIAN", "MUSHROOMCOIN", "YUANBAO"} <= memes
    assert len(memes) >= 5


def test_registry_grows_from_pairs(fami_pairs, universe, markers, base_assets):
    tokens = equity_tokens_in(fami_pairs, universe, markers, base_assets)
    assert {t.ticker for t in tokens} == {"FAMI"}
    assert tokens[0].company == "Farmmi, Inc."


def test_malformed_pairs_do_not_raise(universe, markers, base_assets):
    for junk in ({}, {"chainId": "robinhood"}, {"baseToken": {}, "quoteToken": {}},
                 {"chainId": "x", "baseToken": None, "quoteToken": None}):
        assert detect_launch(junk, universe, markers, base_assets) is None
