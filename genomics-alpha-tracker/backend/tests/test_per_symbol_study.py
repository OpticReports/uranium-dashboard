"""Round-11 per-symbol study gates (docs/VARIANTS_PREREGISTRATION_R11_PER_SYMBOL.md):
select_capped_exec's per_symbol_max is default-preserving, refuses repeats on
the cap's own occupancy test without consuming a slot (same-gate-date
siblings included), the live-release sensitivity changes only the per-symbol
boundary, the sleeve's time-weighted curve removes band transfers, and the
two-tier decision rule + tie-break are checked clause by clause (each clause
isolated, each boundary at equality) on fixed numbers and on the frozen
results file."""
from __future__ import annotations

import json
import math
import random
from dataclasses import replace
from datetime import date

import pytest

from scripts import backtest_per_symbol_study as ps
from scripts.backtest_executor_mirror import (
    CAP, EXEC_T2, build_exec_rows, gate_rows, run_executor_book, select_capped_exec,
)
from tests.test_executor_mirror import _knob_market, dates, exec_row, flat_bars, make_market


def _pre_r11_select_capped_exec(rows: list[dict], cap: int | None) -> tuple[list[dict], int]:
    """select_capped_exec as committed before round 11 (verbatim body): the
    reference the default path must reproduce."""
    key = lambda t: (t.get("gate_date", t["entry_date"]), t["entry_date"], t["symbol"], t.get("flag", ""))  # noqa: E731
    ordered = sorted(rows, key=key)
    taken: list[dict] = []
    open_exits: list[str] = []
    for t in ordered:
        occupy_from = t.get("gate_date", t["entry_date"])
        open_exits = [x for x in open_exits if x >= occupy_from]
        if cap is not None and len(open_exits) >= cap:
            continue
        taken.append(t)
        open_exits.append(t["exit_date"])
    return taken, len(rows) - len(taken)


def row(sym: str, gate: str, exit_: str, entry: str | None = None, flag: str = "f") -> dict:
    return {"symbol": sym, "gate_date": f"2024-01-{gate}", "entry_date": f"2024-01-{entry or gate}",
            "exit_date": f"2024-01-{exit_}", "flag": flag}


def _random_rows(seed: int, n: int = 120) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        g = rng.randrange(1, 20)
        out.append(row(rng.choice("ABCDE") * 3, f"{g:02d}", f"{g + rng.randrange(0, 9):02d}",
                       entry=f"{g + rng.randrange(0, 2):02d}", flag=f"f{i}"))
    return out


# --- (a) default None is the pre-change behaviour ---------------------------------------

def test_default_none_is_byte_for_byte_the_pre_change_selection():
    hand = [row("AAA", "02", "10"), row("AAA", "03", "12"), row("BBB", "03", "05"), row("CCC", "04", "09"),
            row("AAA", "05", "06"), row("BBB", "06", "15"), row("DDD", "06", "07", entry="07")]
    for rows in [hand] + [_random_rows(s) for s in range(20)]:
        for cap in (None, 1, 2, 3, CAP):
            ref = _pre_r11_select_capped_exec(rows, cap)
            assert select_capped_exec(rows, cap) == ref
            assert select_capped_exec(rows, cap, None) == ref
            assert select_capped_exec(rows, cap, per_symbol_max=None) == ref
            taken, at_cap, refused = select_capped_exec(rows, cap, None, return_detail=True)
            assert taken == ref[0] and at_cap == ref[1] and refused == 0
            # the live-release switch and the refusal log are inert without a per-symbol limit
            log: list = []
            assert select_capped_exec(rows, cap, None, symbol_release="live", refusal_log=log) == ref
            assert log == []


def test_default_none_unchanged_on_the_full_executor_path():
    fires, mkt, tiers = _knob_market()
    rows, _ = build_exec_rows(fires, mkt, tiers, EXEC_T2)
    gated = gate_rows(rows, mkt["xbi_above_prior"][200])
    assert select_capped_exec(gated, CAP) == _pre_r11_select_capped_exec(gated, CAP)
    assert select_capped_exec(gated, CAP, per_symbol_max=None) == select_capped_exec(gated, CAP)


# --- (b) k=1 refuses an overlapping repeat; the slot goes to the next other name -----------

def test_k1_refuses_overlapping_repeat_and_hands_the_slot_on():
    rows = [row("AAA", "02", "10"), row("AAA", "03", "12"), row("BBB", "04", "12")]
    t0, s0 = select_capped_exec(rows, 2)
    assert [t["symbol"] for t in t0] == ["AAA", "AAA"] and s0 == 1        # live rule: BBB skipped at cap
    t1, at_cap, refused = select_capped_exec(rows, 2, per_symbol_max=1, return_detail=True)
    assert [(t["symbol"], t["gate_date"]) for t in t1] == [("AAA", "2024-01-02"), ("BBB", "2024-01-04")]
    assert refused == 1 and at_cap == 0
    # the 2-tuple form still reports every non-taken row
    assert select_capped_exec(rows, 2, per_symbol_max=1)[1] == 1


# --- (c) occupancy boundary is the cap's: exit_date == occupy_from is still held ----------

def test_same_symbol_boundary_matches_the_cap_occupancy_test():
    first = row("AAA", "02", "05")
    # cap's own test (cap 1, a different name): gated ON the exit date -> refused; the day after -> taken
    assert len(select_capped_exec([first, row("BBB", "05", "09")], 1)[0]) == 1
    assert len(select_capped_exec([first, row("BBB", "06", "09")], 1)[0]) == 2
    # per-symbol, same test: gated on the exit date -> still held -> refused
    t, at_cap, refused = select_capped_exec([first, row("AAA", "05", "09")], CAP, per_symbol_max=1,
                                            return_detail=True)
    assert len(t) == 1 and refused == 1 and at_cap == 0
    # gated after the prior exit -> taken
    t, at_cap, refused = select_capped_exec([first, row("AAA", "06", "09")], CAP, per_symbol_max=1,
                                            return_detail=True)
    assert len(t) == 2 and refused == 0
    # occupancy starts at the GATE date, not the fill: a repeat gated after the exit but whose
    # entry_date sorts later is still a fresh call
    t, _, refused = select_capped_exec([first, row("AAA", "06", "09", entry="07")], CAP, per_symbol_max=1,
                                       return_detail=True)
    assert len(t) == 2 and refused == 0


# --- (d) k=2 allows two, refuses the third ------------------------------------------------

def test_k2_allows_two_and_refuses_the_third():
    rows = [row("AAA", "02", "10"), row("AAA", "03", "10"), row("AAA", "04", "10"), row("AAA", "11", "15")]
    t, at_cap, refused = select_capped_exec(rows, CAP, per_symbol_max=2, return_detail=True)
    assert [x["gate_date"] for x in t] == ["2024-01-02", "2024-01-03", "2024-01-11"]
    assert refused == 1 and at_cap == 0
    # k=1 on the same rows: one, then the post-exit call
    t1, _, refused1 = select_capped_exec(rows, CAP, per_symbol_max=1, return_detail=True)
    assert [x["gate_date"] for x in t1] == ["2024-01-02", "2024-01-11"] and refused1 == 2


# --- (e) refused rows consume no cap slot -------------------------------------------------

def test_refused_rows_do_not_consume_cap_slots():
    # cap 2: AAA holds one slot; three AAA repeats are refused; BBB and later CCC must still fit
    # in the second slot (CCC after BBB's exit) — had a refusal taken a slot, BBB would be at cap
    rows = [row("AAA", "02", "20"), row("AAA", "03", "20"), row("AAA", "04", "20"), row("AAA", "05", "20"),
            row("BBB", "06", "08"), row("CCC", "09", "12"), row("DDD", "10", "12")]
    t, at_cap, refused = select_capped_exec(rows, 2, per_symbol_max=1, return_detail=True)
    assert [x["symbol"] for x in t] == ["AAA", "BBB", "CCC"]
    assert refused == 3 and at_cap == 1                    # DDD meets a full cap (AAA + CCC)
    assert len(t) + at_cap + refused == len(rows)
    # the cap is checked first: a repeat arriving at a full cap counts as skipped_at_cap
    rows2 = [row("AAA", "02", "20"), row("BBB", "02", "20"), row("AAA", "03", "20")]
    _, at_cap2, refused2 = select_capped_exec(rows2, 2, per_symbol_max=1, return_detail=True)
    assert at_cap2 == 1 and refused2 == 0


# --- (f) the two-tier decision rule, clause by clause, and the tie-break -------------------

T1 = dict(bonf_lo=0.01, p5=0.05, max_dd_arm=0.21, max_dd_a0=0.20, sharpe_delta_5y=0.02,
          p90_share_arm=0.39, p90_share_a0=0.40)                 # tier 1 passes, tier 2 fails (share)
T2 = dict(bonf_lo=-0.10, p5=-0.05, max_dd_arm=0.203, max_dd_a0=0.20, sharpe_delta_5y=-0.04,
          p90_share_arm=0.28, p90_share_a0=0.40)                 # tier 1 fails, tier 2 passes

T1_CLAUSE = {"bonf_lo": "bonf2_lo_gt_0", "max_dd_arm": "max_dd_within_2pp_of_a0",
             "sharpe_delta_5y": "sharpe_delta_5y_gt_0"}
T2_CLAUSE = {"p5": "p5_ge_minus_0.10", "max_dd_arm": "max_dd_within_0.5pp_of_a0",
             "sharpe_delta_5y": "sharpe_delta_5y_ge_minus_0.05", "p90_share_arm": "p90_share_10pp_below_a0"}


def _only_clause_fails(reasons: dict, clause: str) -> bool:
    return reasons[clause] is False and all(v for c, v in reasons.items() if c != clause)


def test_tier1_improvement_each_clause():
    d = ps.decide_arm(**T1)
    assert d["decision"] == "PROPOSE" and d["tier"] == "improvement"
    assert all(d["reasons"]["tier1_improvement"].values())
    for k, v in (("bonf_lo", 0.0), ("bonf_lo", None), ("bonf_lo", float("nan")), ("max_dd_arm", 0.221),
                 ("sharpe_delta_5y", 0.0), ("sharpe_delta_5y", None), ("sharpe_delta_5y", float("nan"))):
        d = ps.decide_arm(**{**T1, k: v})
        assert d["decision"] == "NULL" and d["tier"] is None, (k, v)
        # exactly the perturbed clause fails, every other tier-1 clause still holds
        assert _only_clause_fails(d["reasons"]["tier1_improvement"], T1_CLAUSE[k]), (k, v)


def test_tier1_boundaries_at_equality():
    # strict: bonf_lo > 0 and 5y delta > 0 (tested at 0 above); max DD inclusive at exactly A0 + 2 pp
    d = ps.decide_arm(**{**T1, "max_dd_arm": 0.25, "max_dd_a0": 0.23})
    assert d["reasons"]["tier1_improvement"]["max_dd_within_2pp_of_a0"] is True and d["tier"] == "improvement"
    assert ps.decide_arm(**{**T1, "bonf_lo": 1e-9})["tier"] == "improvement"
    assert ps.decide_arm(**{**T1, "sharpe_delta_5y": 1e-9})["tier"] == "improvement"


def test_tier2_risk_control_each_clause():
    d = ps.decide_arm(**T2)
    assert d["decision"] == "PROPOSE" and d["tier"] == "risk_control"
    assert not all(d["reasons"]["tier1_improvement"].values())
    assert all(d["reasons"]["tier2_risk_control"].values())
    for k, v in (("p5", -0.101), ("p5", None), ("p5", float("nan")), ("max_dd_arm", 0.206),
                 ("sharpe_delta_5y", -0.051), ("sharpe_delta_5y", None), ("p90_share_arm", 0.31),
                 ("p90_share_arm", None)):
        d = ps.decide_arm(**{**T2, k: v})
        assert d["decision"] == "NULL" and d["tier"] is None, (k, v)
        assert _only_clause_fails(d["reasons"]["tier2_risk_control"], T2_CLAUSE[k]), (k, v)
    d = ps.decide_arm(**{**T2, "p90_share_a0": None})
    assert d["decision"] == "NULL" and _only_clause_fails(d["reasons"]["tier2_risk_control"],
                                                          "p90_share_10pp_below_a0")


def test_tier2_boundaries_at_equality_are_inclusive():
    # every tier-2 floor is >= / <= : exactly on the line passes (values chosen exact in binary
    # where possible; the others sit on the line to within one ulp, the side the contract allows)
    on_line = {"p5": -0.10, "max_dd_arm": 0.25 + 0.005, "max_dd_a0": 0.25, "sharpe_delta_5y": -0.05,
               "p90_share_arm": 0.375 - 0.10, "p90_share_a0": 0.375}
    d = ps.decide_arm(**{**T2, **on_line})
    assert all(d["reasons"]["tier2_risk_control"].values()) and d["tier"] == "risk_control"
    # one step past each line fails that clause alone
    for k, v in (("p5", -0.1001), ("max_dd_arm", 0.2551), ("sharpe_delta_5y", -0.0501), ("p90_share_arm", 0.2751)):
        d = ps.decide_arm(**{**T2, **on_line, k: v})
        assert _only_clause_fails(d["reasons"]["tier2_risk_control"], T2_CLAUSE[k]), (k, v)


def test_first_tier_met_wins():
    both = {**T1, "p90_share_arm": 0.20, "max_dd_arm": 0.20}                   # meets tier 1 AND tier 2
    assert all(ps.decide_arm(**both)["reasons"]["tier2_risk_control"].values())
    assert ps.decide_arm(**both)["tier"] == "improvement"


def test_tie_break_higher_point_delta_then_u1():
    assert ps.choose([("U1", "NULL", 0.1), ("U2", "NULL", 0.2)])["proposal"] is None
    assert ps.choose([("U1", "NULL", 0.1), ("U2", "PROPOSE", -0.2)])["proposal"] == "U2"
    assert ps.choose([("U1", "PROPOSE", 0.1), ("U2", "NULL", 0.2)])["proposal"] == "U1"
    assert ps.choose([("U1", "PROPOSE", 0.01), ("U2", "PROPOSE", 0.02)])["proposal"] == "U2"
    assert ps.choose([("U1", "PROPOSE", 0.03), ("U2", "PROPOSE", 0.02)])["proposal"] == "U1"
    tie = ps.choose([("U1", "PROPOSE", 0.02), ("U2", "PROPOSE", 0.02)])
    assert tie["proposal"] == "U1" and "tie" in tie["rule"]


# --- (g) refusal breakdown: exit-date boundary (A1) and same-gate-date siblings (A2) --------

def test_live_release_frees_the_symbol_on_its_exit_date_only():
    first = row("AAA", "02", "05")
    log: list = []
    t, _, refused = select_capped_exec([first, row("AAA", "05", "09")], CAP, per_symbol_max=1,
                                       return_detail=True, refusal_log=log)
    assert refused == 1 and len(log) == 1 and log[0][1] == [first]
    assert ps.refusal_breakdown(log, 1) == {"refused_exit_date_boundary_only": 1,
                                            "refused_by_same_gate_date_sibling": 0}
    # live release: the call exiting ON the gate date no longer blocks the repeat
    t, _, refused = select_capped_exec([first, row("AAA", "05", "09")], CAP, per_symbol_max=1,
                                       return_detail=True, symbol_release="live")
    assert len(t) == 2 and refused == 0
    # ... but one exiting AFTER the gate date still does, and the cap's occupancy is unchanged
    _, _, refused = select_capped_exec([first, row("AAA", "04", "09")], CAP, per_symbol_max=1,
                                       return_detail=True, symbol_release="live")
    assert refused == 1
    assert len(select_capped_exec([first, row("BBB", "05", "09")], 1, symbol_release="live")[0]) == 1
    with pytest.raises(ValueError):
        select_capped_exec([first], CAP, 1, symbol_release="strict")


def test_k2_boundary_counts_only_when_fewer_than_k_blockers_outlive_the_gate():
    rows = [row("AAA", "02", "05"), row("AAA", "03", "09"), row("AAA", "05", "12")]
    log: list = []
    select_capped_exec(rows, CAP, per_symbol_max=2, refusal_log=log)
    assert len(log) == 1 and ps.refusal_breakdown(log, 2)["refused_exit_date_boundary_only"] == 1
    rows = [row("AAA", "02", "06"), row("AAA", "03", "09"), row("AAA", "05", "12")]
    log = []
    select_capped_exec(rows, CAP, per_symbol_max=2, refusal_log=log)
    assert len(log) == 1 and ps.refusal_breakdown(log, 2)["refused_exit_date_boundary_only"] == 0


def test_two_same_symbol_fires_in_one_payload_k1_takes_the_first_only():
    # the live-port gate (counter-agent A2): siblings on one gate date, ordered by (gate, entry, symbol, flag)
    rows = [row("AAA", "03", "09", flag="b"), row("AAA", "03", "09", flag="a"), row("BBB", "03", "09")]
    log: list = []
    t, at_cap, refused = select_capped_exec(rows, CAP, per_symbol_max=1, return_detail=True, refusal_log=log)
    assert [(x["symbol"], x["flag"]) for x in t] == [("AAA", "a"), ("BBB", "f")] and refused == 1
    assert ps.refusal_breakdown(log, 1)["refused_by_same_gate_date_sibling"] == 1
    assert ps.same_gate_dup_groups(rows) == 1
    # the live rule (no per-symbol limit) takes both siblings
    assert len(select_capped_exec(rows, CAP)[0]) == 3
    assert "entry_intents" in ps.LIVE_PORT_SPEC and "exiting" in ps.LIVE_PORT_SPEC


# --- (h) sleeve time-weighted curve removes band transfers (B1) -----------------------------

def _band_market(n: int = 10):
    ds = dates(n, start=date(2024, 1, 1))
    mkt = make_market({"AAA": flat_bars(ds, 1.0)})
    mkt["px"]["AAA"] = {d: 1.0 for d in ds}
    # SPY drops (sleeve overweight -> sleeve_to_core) then rallies (underweight -> core_to_sleeve)
    spy = {d: (100.0 if i < 2 else 55.0 if i < 5 else 160.0) for i, d in enumerate(ds)}
    return ds, mkt, spy


def test_idle_sleeve_twr_is_flat_through_band_transfers_both_ways():
    ds, mkt, spy = _band_market()
    cfg = replace(EXEC_T2, sleeve_target=0.30, start_equity=120_000.0)
    bk = run_executor_book([], mkt, cfg, spy_px=spy)               # all-cash sleeve, no carry: zero return
    flows = [bk["daily"][d.isoformat()]["sleeve_band_flow"] for d in ds]
    assert any(f < 0 for f in flows) and any(f > 0 for f in flows)
    assert sum(1 for f in flows if f) == bk["meta"]["rebalances"]
    sc = [v for _, v in bk["sleeve_curve"]]
    assert sc[-1] - sc[0] == pytest.approx(sum(flows), abs=1e-6)  # the bucket moved ONLY by transfers
    assert max(sc) / min(sc) > 1.1                                 # ... and visibly so
    twr = ps.sleeve_twr_curve(bk)
    assert [d for d, _ in twr] == ds
    assert all(v == pytest.approx(sc[0], rel=1e-12) for _, v in twr)
    m = ps.sleeve_twr_metrics(twr, {"full": (ds[0], ds[-1])})["full"]
    assert m["cagr"] == pytest.approx(0.0, abs=1e-12) and m["max_dd"] == pytest.approx(0.0, abs=1e-12)
    fs = ps.sleeve_flow_summary(bk)
    assert fs["n_flow_days"] == bk["meta"]["rebalances"]
    assert fs["net_flow_into_sleeve_usd"] == pytest.approx(sum(flows))


def test_twr_equals_the_bucket_without_transfers_and_chains_pre_flow_returns_with_them():
    ds, mkt, spy = _band_market(12)
    mkt["px"]["AAA"] = {d: 1.0 + 0.02 * i for i, d in enumerate(ds)}
    rows = [exec_row("AAA", ds[1], ds[8], fill=1.02, entry_ref=1.02, risk=0.1, exit_px=1.16)]
    solo = run_executor_book(rows, mkt, replace(EXEC_T2, start_equity=120_000.0), spy_px=spy)
    assert all(e["sleeve_band_flow"] == 0.0 for e in solo["daily"].values())
    tw = ps.sleeve_twr_curve(solo)
    assert [d for d, _ in tw] == [d for d, _ in solo["sleeve_curve"]]
    assert all(a == pytest.approx(b, rel=1e-12) for (_, a), (_, b) in zip(tw, solo["sleeve_curve"]))
    bk = run_executor_book(rows, mkt, replace(EXEC_T2, sleeve_target=0.30, start_equity=120_000.0), spy_px=spy)
    sc, twr = bk["sleeve_curve"], ps.sleeve_twr_curve(bk)
    for i in range(1, len(sc)):
        pre = sc[i][1] - bk["daily"][sc[i][0].isoformat()]["sleeve_band_flow"]
        assert twr[i][1] / twr[i - 1][1] == pytest.approx(pre / sc[i - 1][1], rel=1e-12)


# --- (i) the frozen results file agrees with the rule applied to its own numbers -----------

def test_frozen_results_recompute():
    if not ps.RESULTS.exists():
        pytest.skip("results file not generated")
    res = json.loads(ps.RESULTS.read_text())
    assert res["reduction_check"]["pass"] is True and res["sanity_reproduction_a0"]["pass"] is True
    a0 = res["arms"]["A0"]
    cands = []
    for n in ("U1", "U2"):
        m = res["arms"][n]
        b = m["vs_a0"]["sharpe_delta_bootstrap"]
        d = ps.decide_arm(b["bonf_lo"], b["p5"], m["book"]["full"]["max_dd"], a0["book"]["full"]["max_dd"],
                          m["vs_a0"]["deltas"]["5y"]["sharpe"], m["concentration"]["largest_name_share_p90"],
                          a0["concentration"]["largest_name_share_p90"])
        assert d["decision"] == m["decision"]["decision"] == res["decisions"][n]["decision"], n
        assert d["tier"] == res["decisions"][n]["tier"], n
        assert d["reasons"] == m["decision"]["reasons"], n
        cands.append((n, d["decision"], m["vs_a0"]["point_sharpe_delta_full"]))
        # the pre-registered sleeve metrics are the time-weighted ones; the bucket is kept, relabelled
        assert "time-weighted" in m["sleeve_basis"] and "sleeve_bucket_incl_transfers" in m
        assert m["sleeve_flows"]["n_flow_days"] == m["sleeve_flows"]["n_rebalances"]
        assert math.isfinite(m["sleeve"]["full"]["sharpe"])
        assert "sensitivity_live_release" in m
    assert ps.choose(cands)["proposal"] == res["proposal"]["proposal"]
