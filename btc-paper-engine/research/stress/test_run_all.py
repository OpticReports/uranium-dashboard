"""Gate tests for run_all.py added after the independent review (2026-10-07).
Each fails on the pre-review run_all.py: funding_for defaulted to ETHUSD
wherever its data covered the window, there was no HONESTY box, no quanto
column, no seam/funding sensitivities and no 12m* label."""
from __future__ import annotations

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import run_all                                                      # noqa: E402
import stress                                                       # noqa: E402
from stress import BAR, DAY, build_spliced                          # noqa: E402

NOW = stress.SEED_NOW


# (xiii) headline carry funding is the XBTUSD proxy, never the quanto (BLOCKING)
def test_headline_funding_is_xbtusd_even_where_ethusd_covers():
    assert run_all.HEADLINE_FUNDING == "XBTUSD" and run_all.QUANTO_FUNDING == "ETHUSD"
    assert "not the live venue" in run_all.QUANTO_LABEL
    bars = build_spliced("btcusd", "2020-02-13", now=NOW)
    n = len(bars.path)
    assert run_all.funding_covers("ETHUSD", bars.anchor_ts)      # the quanto series exists here
    fund, meta = run_all.funding_for(bars.anchor_ts, n, bars.t0)  # the default
    assert meta["source"] == "XBTUSD" and meta["quanto"] is False
    fq, mq = run_all.funding_for(bars.anchor_ts, n, bars.t0, "ETHUSD")
    assert mq["source"] == "ETHUSD" and mq["quanto"] is True
    # the quanto is structurally richer than the proxy over the same window
    assert mq["mean_ann_pct"] > meta["mean_ann_pct"] + 20
    assert meta["neg_stamps_pct"] > mq["neg_stamps_pct"]
    # the force= spelling still works and still cannot make ETHUSD the default
    assert run_all.funding_for(bars.anchor_ts, n, bars.t0, force="XBTUSD")[1]["source"] == "XBTUSD"
    # no quanto series for the 1999 window: it is refused, not silently proxied
    b99 = build_spliced("btcusd", "2017-12-17", now=NOW)
    assert not run_all.funding_covers("ETHUSD", b99.anchor_ts)
    with pytest.raises(ValueError):
        run_all.funding_for(b99.anchor_ts, len(b99.path), b99.t0, "ETHUSD")
    assert run_all.funding_for(b99.anchor_ts, len(b99.path), b99.t0)[1]["source"] == "XBTUSD"
    # the BTC-book funding dict: seconds, on today's grid, covering the path
    bf = run_all.btc_funding_from(fund)
    assert all(k % 3600 == 0 for k in bf) and min(bf) >= bars.t0 - 31 * DAY
    assert max(bf) >= bars.t0 + n * BAR - 8 * 3600
    assert len(bf) == len(fund)


# (xiv) the honesty box names every review item ---------------------------------
def test_honesty_box_names_the_review_items():
    text = " ".join(run_all.HONESTY_STATIC).lower()
    for needle in ("quanto", "not the live venue", "btc perp funding", "high-water ratchets",
                   "reanchor", "halt_confirm_polls", "post_only", "_reconcile_transfers",
                   "slippage", "validation window", "volume regime", "not a splice artefact",
                   "with or without", "no linear-eth perp funding history", "upper bound"):
        assert needle in text, needle


# (xv) the table carries the quanto column, the 12m* label, the seam block and
# the funding block (from the saved results.json; skipped only when there is none)
def test_table_from_results_json():
    if not os.path.exists(run_all.RESULTS):
        pytest.skip("results.json not generated")
    with open(run_all.RESULTS) as fh:
        res = json.load(fh)
    assert res["meta"]["headline_funding"] == "XBTUSD"
    assert res["meta"]["btc_funding_modelled"] is True
    assert res["meta"]["seam"]["s4"]["stopped_on_real_path"] is True
    table = "\n".join(res["table"])
    assert "quanto" in table and "12m*" in table and "seam-dropped" in table
    assert "BTC perp funding" in table and "daily rail" in table
    for scen, _ in run_all.SCENARIOS:
        S = res["scenarios"][scen]
        for K in run_all.KS:
            s = S["runs"][run_all.kkey(K)]["off+0"]
            assert s["carry"]["funding_source"] == "XBTUSD" and s["btc_funding"]["modelled"]
            assert s["btc_funding"]["total"] < 0            # a cost on every crash path
            assert "worst_day_intrabar" in s and "rail_use" in s
            assert S["seam_range"][run_all.kkey(K)]["min"] <= s["balances"]["365"] <= \
                S["seam_range"][run_all.kkey(K)]["max"]
        assert ("K0.75" in S["runs_quanto"]) == run_all.funding_covers("ETHUSD", stress.ts_of(S["anchor"]))
    assert any("knife-edge" in line.lower() for line in res["honesty"])
    assert any("Daily-loss rail at K0.3" in line for line in res["honesty"])
    assert res["scenarios"]["1999"]["range_12m"]["K0.75"]["excluded"] == {
        "off-28": res["scenarios"]["1999"]["range_12m"]["K0.75"]["excluded"]["off-28"]}
    assert "not a crash path" in res["scenarios"]["1999"]["range_12m"]["K0.75"]["excluded"]["off-28"]
    assert res["scenarios"]["COVID"]["range_12m"]["K0.75"]["excluded"] == {}
    # the quanto column is the richer one on every covered cell
    for scen in ("COVID", "2008"):
        S = res["scenarios"][scen]
        for K in run_all.KS:
            for off in S["runs_quanto"][run_all.kkey(K)]:
                assert S["runs_quanto"][run_all.kkey(K)][off]["balances"]["365"] > \
                    S["runs"][run_all.kkey(K)][off]["balances"]["365"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
