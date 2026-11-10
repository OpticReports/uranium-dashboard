"""Gate tests for the Composer mirror core (app/mirror_core.py): pure logic, no adapter, no clock.

Besides the original gates: the review's core items - the corridor read on INVESTED weights (reviewer
B's M1), a sleeve in debt or idling in cash (A-05), the dust rule's two exemptions (A-05, A-09), buys
sized AT THEIR LIMIT (A-05 / D5), an all-or-nothing booking, and the dividend and split accounting
(reviewer B's B2 and S2), which lives here so the research-side simulator applies the same rules."""
import json
import math
import random

import pytest

from app import mirror_core as mc

PX = {"TECL": 130.0, "SOXL": 45.0, "PULS": 49.5, "ZVOL": 6.8, "BIL": 91.4, "BOXX": 118.9, "VXZ": 48.2, "SQQQ": 49.5}
FRACS = {"HG": 0.29, "KMLM": 0.29, "SLEEVE": 0.27, "HARV": 0.15}
RULES = {"KMLM": {"rule": mc.RULE_THRESHOLD, "corridor": 0.10}}


def ok(target, version="v1"):
    return {"status": "ok", "target": target, "version": version}


def fresh(capital=118_000.0):
    return mc.Book.seed(capital, FRACS, RULES)


def run(book, targets, prices=PX, session="2026-11-10", fill=None, cfg=None, transfers=None):
    """plan -> crosses -> sells -> transfers -> buys, every venue order filled whole at `fill(order)`
    (default: its reference price). Returns the plan."""
    fill = fill or (lambda o: (o["qty"], o["ref"], 0.0))
    plan = mc.build_plan(book, targets, prices, session, cfg, transfers)
    mc.apply_crosses(book, plan)
    for o in plan["sells"]:
        mc.book_fill(book, o, *fill(o))
    mc.apply_transfers(book, plan)
    for o in mc.size_buys(book, plan, cfg=cfg):
        mc.book_fill(book, o, *fill(o))
    mc.finish(book, plan)
    return plan


def total_equity(book, prices=PX):
    return sum(mc.equity(s, prices) for s in book.sleeves.values())


# ------------------------------------------------------------------ helpers
def test_allocate_is_exact_proportional_and_never_over_an_ask():
    assert mc.allocate(10, {"a": 5, "b": 5}) == {"a": 5, "b": 5}
    assert mc.allocate(0, {"a": 5}) == {"a": 0}
    assert mc.allocate(3, {"a": 1, "b": 1, "c": 1}) == {"a": 1, "b": 1, "c": 1}
    assert mc.allocate(1, {"b": 1, "a": 1}) == {"a": 1, "b": 0}            # tie -> by name
    rnd = random.Random(7)
    for _ in range(2000):
        asks = {f"s{i}": rnd.randint(0, 400) for i in range(rnd.randint(1, 5))}
        whole = sum(asks.values())
        total = rnd.randint(0, whole)
        out = mc.allocate(total, asks)
        assert sum(out.values()) == total
        for k, v in out.items():
            assert 0 <= v <= asks[k]
            assert abs(v - total * asks[k] / whole) < 1.0 if whole else v == 0
    with pytest.raises(mc.MirrorError):
        mc.allocate(6, {"a": 5})


def test_clean_target_accepts_only_a_full_weight_vector():
    assert mc.clean_target({"TECL": 1.0})[0] == {"TECL": 1.0}
    assert mc.clean_target({"A": 0.375, "B": 0.375, "C": 0.25, "D": 0.0})[0] == {"A": 0.375, "B": 0.375, "C": 0.25}
    for bad in (None, {}, {"A": 0.5}, {"A": 1.2}, {"A": float("nan")}, {"A": -0.1, "B": 1.1}, {"A": True}, {"": 1.0}, [1]):
        assert mc.clean_target(bad)[0] is None, bad


def test_seed_and_round_trip():
    book = fresh()
    assert math.isclose(book.cash(), 118_000.0)
    assert book.sleeves["KMLM"].rule == mc.RULE_THRESHOLD and book.sleeves["KMLM"].corridor == 0.10
    again = mc.Book.from_dict(json.loads(json.dumps(book.to_dict())))
    assert again.to_dict() == book.to_dict()
    with pytest.raises(mc.MirrorError):
        mc.Book.seed(1000, {"A": 0.5, "B": 0.4})
    with pytest.raises(mc.MirrorError):
        mc.Book.from_dict({"schema": 99, "sleeves": []})
    with pytest.raises(mc.MirrorError):
        mc.Book.from_dict({"schema": 1, "sleeves": [{"name": "A", "shares": {"X": 1.5}}]})
    with pytest.raises(mc.MirrorError):
        mc.Book.from_dict({"schema": 1, "sleeves": [{"name": "A"}, {"name": "A"}]})


# ------------------------------------------------------------------ the rebalance rule
def test_first_plan_invests_every_sleeve_and_keeps_a_cash_reserve():
    book = fresh()
    t = {"HG": ok({"TECL": 1.0}), "KMLM": ok({"SOXL": 0.375, "TECL": 0.375, "PULS": 0.25}),
         "SLEEVE": ok({"BOXX": 1.0}), "HARV": ok({"PULS": 1.0})}
    plan = run(book, t)
    assert all(d["action"] == "trade" for d in plan["sleeves"].values())
    assert plan["sells"] == [] and plan["crosses"] == []
    assert {o["symbol"] for o in plan["buys"]} == {"TECL", "SOXL", "PULS", "BOXX"}
    assert math.isclose(total_equity(book), 118_000.0, abs_tol=1e-6)        # filled at ref, no fees
    for name, s in book.sleeves.items():
        eq = mc.equity(s, PX)
        assert 0 <= s.cash <= eq * 0.02, (name, s.cash)                    # invested, small reserve
        w = mc.weights(s, PX)
        for sym, tw in t[name]["target"].items():
            assert abs(w[sym] - tw) < 0.01
    assert mc.check(book, book.positions()) == []
    assert book.sleeves["HG"].last_trade == "2026-11-10" and book.sleeves["HG"].version == "v1"


def test_threshold_sleeve_holds_inside_its_corridor_and_trades_outside_it():
    book = fresh()
    run(book, {"KMLM": ok({"SOXL": 0.75, "PULS": 0.25})})
    held = dict(book.sleeves["KMLM"].shares)
    # the sleeve part of the target changes by 9pp: inside the 10pp corridor -> no trade
    p2 = run(book, {"KMLM": ok({"SOXL": 0.75, "PULS": 0.16, "VXZ": 0.09})}, session="2026-11-11")
    assert p2["sleeves"]["KMLM"]["action"] == "hold" and book.sleeves["KMLM"].shares == held
    assert "corridor" in p2["sleeves"]["KMLM"]["reason"]
    # the leveraged leg changes: far outside -> trades to the new target
    p3 = run(book, {"KMLM": ok({"TECL": 0.75, "PULS": 0.25})}, session="2026-11-12")
    assert p3["sleeves"]["KMLM"]["action"] == "trade"
    assert "SOXL" not in book.sleeves["KMLM"].shares and book.sleeves["KMLM"].shares["TECL"] > 0
    # a daily sleeve with the same 9pp change DOES trade
    run(book, {"HARV": ok({"PULS": 1.0})}, session="2026-11-12b")
    p4 = run(book, {"HARV": ok({"PULS": 0.91, "VXZ": 0.09})}, session="2026-11-13")
    assert p4["sleeves"]["HARV"]["action"] == "trade"


def test_corridor_boundary_is_inclusive_like_composers_preview():
    s = mc.Sleeve("K", cash=0.0, shares={"A": 600, "B": 400}, rule=mc.RULE_THRESHOLD, corridor=0.10)
    px = {"A": 50.0, "B": 50.0}
    assert mc.decide_sleeve(s, {"A": 0.5, "B": 0.5}, px, mc.Config())["action"] == "hold"       # gap == 10pp
    s.shares = {"A": 610, "B": 390}
    d = mc.decide_sleeve(s, {"A": 0.5, "B": 0.5}, px, mc.Config())                              # gap 11pp
    assert d["action"] == "trade" and d["deltas"]["A"] < 0 < d["deltas"]["B"]


def test_drift_trims_are_skipped_but_entries_and_exits_never_are():
    book = fresh()
    # (set up fully invested: sized at its limits, a first plan leaves the 0.5% cushion in cash, and
    # topping THAT up is not the drift this gate is about)
    run(book, {"HARV": ok({"PULS": 0.4, "ZVOL": 0.6})}, cfg=mc.Config(buy_cushion=0.0))
    before = dict(book.sleeves["HARV"].shares)
    moved = dict(PX, ZVOL=PX["ZVOL"] * 1.004)                               # 0.24pp of drift
    p = run(book, {"HARV": ok({"PULS": 0.4, "ZVOL": 0.6})}, prices=moved, session="d2")
    assert p["sleeves"]["HARV"]["action"] == "hold" and book.sleeves["HARV"].shares == before
    # a tiny new position is still entered; a tiny old one is still fully exited
    p = run(book, {"HARV": ok({"PULS": 0.399, "ZVOL": 0.599, "VXZ": 0.002})}, session="d3")
    assert book.sleeves["HARV"].shares.get("VXZ", 0) >= 0 and p["sleeves"]["HARV"]["deltas"].get("VXZ", 0) >= 0
    run(book, {"HARV": ok({"PULS": 0.4, "ZVOL": 0.6})}, session="d4")
    assert "VXZ" not in book.sleeves["HARV"].shares


def test_a_sleeve_without_a_usable_target_or_price_is_skipped_whole():
    book = fresh()
    run(book, {"HG": ok({"TECL": 1.0}), "HARV": ok({"PULS": 1.0})})
    hg = dict(book.sleeves["HG"].shares)
    cases = {
        "missing": {},
        "unavailable": {"HG": {"status": "unavailable", "note": "no prices for XLK"}},
        "bad sum": {"HG": ok({"TECL": 0.5})},
        "no price for target": {"HG": ok({"NOPE": 1.0})},
    }
    for label, t in cases.items():
        p = run(book, t, session=label)
        assert p["sleeves"]["HG"]["action"] == "skip", label
        assert book.sleeves["HG"].shares == hg, label
    px = dict(PX)
    px.pop("TECL")                                                          # held symbol has no price
    p = mc.build_plan(book, {"HG": ok({"BIL": 1.0})}, px, "s")
    assert p["sleeves"]["HG"]["action"] == "skip" and "TECL" in p["sleeves"]["HG"]["reason"]


# ------------------------------------------------------------------ netting, phases, cash
def test_opposite_legs_cross_internally_and_only_the_net_reaches_the_venue():
    book = fresh()
    run(book, {"HG": ok({"TECL": 1.0}), "KMLM": ok({"SOXL": 0.75, "PULS": 0.25})})
    hg_tecl = book.sleeves["HG"].shares["TECL"]
    # HG leaves TECL for BIL; KMLM moves its leveraged leg from SOXL to TECL
    plan = run(book, {"HG": ok({"BIL": 1.0}), "KMLM": ok({"TECL": 0.75, "PULS": 0.25})}, session="d2")
    cross = [c for c in plan["crosses"] if c["symbol"] == "TECL"]
    assert len(cross) == 1 and cross[0]["sellers"] == {"HG": cross[0]["qty"]} and cross[0]["buyers"] == {"KMLM": cross[0]["qty"]}
    tecl_sells = [o for o in plan["sells"] if o["symbol"] == "TECL"]
    tecl_buys = [o for o in plan["buys"] if o["symbol"] == "TECL"]
    assert tecl_buys == []                                                  # HG sold more than KMLM wanted
    assert tecl_sells[0]["qty"] == hg_tecl - cross[0]["qty"]
    assert "TECL" not in book.sleeves["HG"].shares and book.sleeves["KMLM"].shares["TECL"] == cross[0]["qty"]
    assert math.isclose(total_equity(book), 118_000.0, abs_tol=1e-6)
    ids = [o["id"] for o in plan["sells"] + plan["buys"]]
    assert len(ids) == len(set(ids)) and all(i.startswith("mirror-d2-") for i in ids)


def test_buys_are_limit_orders_sized_at_their_limit():
    """D5 / A-05: a buy is costed at the price it can never fill above. quantity x limit fits the
    sleeve's cash less its reserve - so a fill ANYWHERE at or under the limit never overdraws it."""
    cfg = mc.Config()
    assert (cfg.buy_cushion, cfg.cash_reserve_frac) == (0.005, 0.001)
    book = fresh()
    t = {"HG": ok({"TECL": 1.0}), "KMLM": ok({"SOXL": 0.375, "TECL": 0.375, "PULS": 0.25})}
    plan = mc.build_plan(book, t, PX, "s")
    mc.apply_crosses(book, plan)
    mc.apply_transfers(book, plan)
    cash = {n: s.cash for n, s in book.sleeves.items()}
    buys = mc.size_buys(book, plan)
    for o in buys:
        assert o["limit"] == pytest.approx(o["ref"] * 1.005) and o["limit"] == mc.buy_limit(o["ref"])
    for name in ("HG", "KMLM"):
        at_limit = sum(o["asks"].get(name, 0) * o["limit"] for o in buys)
        assert at_limit <= cash[name] * (1 - cfg.cash_reserve_frac) + 1e-9, name
        assert at_limit > cash[name] * 0.985, name                           # ... and it is not timid about it
    for o in buys:                                                           # the WORST fill the venue can give
        mc.book_fill(book, o, o["qty"], o["limit"], 0.0)
    assert all(s.cash >= 0 for s in book.sleeves.values())
    # the caller's own limits (the venue's quote, on its grid) are what is sized at
    book2 = fresh()
    plan2 = mc.build_plan(book2, {"HG": ok({"TECL": 1.0})}, PX, "s")
    mc.apply_crosses(book2, plan2)
    hi = mc.size_buys(book2, plan2, limits={"TECL": 143.0})[0]               # the tape is 10% above the reference
    assert hi["limit"] == 143.0 and hi["ref"] == PX["TECL"] and hi["qty"] * 143.0 <= book2.sleeves["HG"].cash
    assert hi["qty"] < plan2["buy_asks"]["HG"]["TECL"]                       # fewer shares, never borrowed money
    assert mc.buy_limit(600.0) == 603.0 and mc.buy_limit(40.0) == 40.2       # no float dust under a grid point


def test_buys_are_sized_from_actual_cash_and_never_borrow():
    book = fresh()
    run(book, {"HG": ok({"TECL": 1.0})})
    # the TECL sell fills 6% below the reference: BIL buys must shrink to the cash that arrived
    def fill(o):
        return (o["qty"], o["ref"] * (0.94 if o["side"] == mc.SELL else 1.0), 0.0)
    plan = run(book, {"HG": ok({"BIL": 1.0})}, session="d2", fill=fill)
    hg = book.sleeves["HG"]
    assert hg.cash >= -1e-6 and "TECL" not in hg.shares and hg.shares["BIL"] > 0
    asked = plan["buy_asks"]["HG"]["BIL"]
    assert plan["buys"][0]["qty"] < asked                                   # scaled down
    assert book.cash() >= -1e-6


def test_an_unfilled_sell_leaves_the_shares_and_buys_nothing_it_cannot_pay_for():
    book = fresh()
    run(book, {"HG": ok({"TECL": 1.0})})
    tecl, cash0 = book.sleeves["HG"].shares["TECL"], book.sleeves["HG"].cash
    def fill(o):
        return (0, None, 0.0) if o["side"] == mc.SELL else (o["qty"], o["ref"], 0.0)
    plan = run(book, {"HG": ok({"BIL": 1.0})}, session="d2", fill=fill)
    assert book.sleeves["HG"].shares["TECL"] == tecl
    spent = sum(o["filled"] * o["price"] for o in plan["buys"] if o["filled"])
    assert spent <= cash0 + 1e-6 and book.sleeves["HG"].cash >= -1e-6


def test_a_partial_sell_is_split_by_largest_remainder_and_books_once():
    book = mc.Book({"A": mc.Sleeve("A", 0.0, {"X": 30}), "B": mc.Sleeve("B", 0.0, {"X": 70})})
    px = {"X": 10.0, "Y": 5.0}
    plan = mc.build_plan(book, {"A": ok({"Y": 1.0}), "B": ok({"Y": 1.0})}, px, "s")
    order = plan["sells"][0]
    assert order["qty"] == 100 and order["asks"] == {"A": 30, "B": 70}
    split = mc.book_fill(book, order, 55, 9.9, commission=1.10)
    assert split == {"A": 17, "B": 38} or split == {"A": 16, "B": 39}
    assert sum(split.values()) == 55
    assert book.positions()["X"] == 45
    assert math.isclose(book.cash(), 55 * 9.9 - 1.10, abs_tol=1e-9)
    with pytest.raises(mc.MirrorError):
        mc.book_fill(book, order, 10, 9.9)                                  # already booked
    for bad in (-1, 101, 1.5):
        o2 = dict(order, applied=False)
        with pytest.raises(mc.MirrorError):
            mc.book_fill(book, o2, bad, 9.9)
    with pytest.raises(mc.MirrorError):
        mc.book_fill(book, dict(order, applied=False), 5, None)             # filled with no price


def test_a_sleeve_can_never_sell_shares_it_does_not_own():
    book = mc.Book({"A": mc.Sleeve("A", 0.0, {"X": 5})})
    order = {"id": "mirror-s-S-X", "side": mc.SELL, "symbol": "X", "qty": 10, "asks": {"A": 10}, "applied": False}
    with pytest.raises(mc.MirrorError):
        mc.book_fill(book, order, 10, 1.0)


def test_phase_order_is_enforced():
    book = fresh()
    run(book, {"HG": ok({"TECL": 1.0}), "KMLM": ok({"SOXL": 0.75, "PULS": 0.25})})
    plan = mc.build_plan(book, {"HG": ok({"BIL": 1.0}), "KMLM": ok({"TECL": 0.75, "PULS": 0.25})}, PX, "d2")
    with pytest.raises(mc.MirrorError):
        mc.size_buys(book, plan)                                            # sells not booked
    mc.apply_crosses(book, plan)
    with pytest.raises(mc.MirrorError):
        mc.apply_crosses(book, plan)
    for o in plan["sells"]:
        mc.book_fill(book, o, o["qty"], o["ref"])
    mc.apply_transfers(book, plan)
    mc.size_buys(book, plan)
    with pytest.raises(mc.MirrorError):
        mc.size_buys(book, plan)


def test_transfers_move_capital_between_sleeves_through_the_plan():
    book = fresh()
    t = {"HG": ok({"TECL": 1.0}), "KMLM": ok({"SOXL": 0.75, "PULS": 0.25}), "SLEEVE": ok({"BOXX": 1.0}),
         "HARV": ok({"PULS": 1.0})}
    run(book, t)
    hg0, sl0 = mc.equity(book.sleeves["HG"], PX), mc.equity(book.sleeves["SLEEVE"], PX)
    plan = run(book, t, session="d2", transfers=[{"from": "HG", "to": "SLEEVE", "amount": 5000.0}])
    assert plan["transfers"][0]["status"] == "moved"
    assert abs(mc.equity(book.sleeves["HG"], PX) - (hg0 - 5000.0)) < 1.0
    assert abs(mc.equity(book.sleeves["SLEEVE"], PX) - (sl0 + 5000.0)) < 1.0
    assert math.isclose(total_equity(book), 118_000.0, abs_tol=1e-6)
    # refused: unknown sleeve, non-positive, more than the giver has
    for bad in ({"from": "HG", "to": "NOPE", "amount": 10.0}, {"from": "HG", "to": "HARV", "amount": -1},
                {"from": "HG", "to": "HARV", "amount": 1e9}, {"from": "HG", "to": "HG", "amount": 10.0}):
        p = mc.build_plan(book, t, PX, "d3", transfers=[bad])
        assert p["transfers"][0]["status"] == "refused"
    # a transfer forces a threshold sleeve to trade even inside its corridor
    p = mc.build_plan(book, t, PX, "d4", transfers=[{"from": "KMLM", "to": "HARV", "amount": 2000.0}])
    assert p["sleeves"]["KMLM"]["action"] == "trade"


# ------------------------------------------------------------------ the review's rule changes
def test_m1_the_corridor_is_read_on_invested_weights_as_composer_reads_it():
    """reviewer B's M1 (test_B2): the mirror divided each holding by equity INCLUDING cash, so every
    held weight read (1 - cash share) of Composer's. Both directions."""
    px = {"A": 100.0, "B": 100.0, "C": 100.0}
    s = mc.Sleeve(name="KMLM", cash=500.0, shares={"A": 601, "B": 200, "C": 199}, rule="threshold", corridor=0.10)
    target = {"A": 0.5, "B": 0.25, "C": 0.25}                               # Composer reads A at 60.1%: 10.1pp -> trade
    d1 = mc.decide_sleeve(s, target, px, mc.Config())
    s2 = mc.Sleeve(name="KMLM", cash=500.0, shares={"A": 599, "B": 401}, rule="threshold", corridor=0.10)
    d2 = mc.decide_sleeve(s2, {"A": 0.5, "B": 0.5}, px, mc.Config())        # Composer reads A at 59.9%: 9.9pp -> hold
    assert (d1["action"], d2["action"]) == ("trade", "hold")
    assert d1["gap"] == pytest.approx(0.101) and d2["gap"] == pytest.approx(0.099)
    assert sum(d1["invested"].values()) == pytest.approx(1.0) and sum(d1["weights"].values()) < 1.0
    assert mc.invested_weights(mc.Sleeve("x", cash=10.0), px) == {}


def test_a_threshold_sleeve_idling_in_cash_or_in_debt_is_never_inside_its_corridor():
    px = {"A": 100.0, "B": 100.0}
    t = {"A": 0.5, "B": 0.5}
    at_target = dict(shares={"A": 500, "B": 500}, rule="threshold", corridor=0.10)
    assert mc.decide_sleeve(mc.Sleeve("K", cash=1_000.0, **at_target), t, px, mc.Config())["action"] == "hold"
    # more than 5% of the sleeve in cash (a refused buy, a short fill): a state Composer never reaches
    idle = mc.decide_sleeve(mc.Sleeve("K", cash=6_000.0, **at_target), t, px, mc.Config())
    assert idle["action"] == "trade" and idle["deltas"] == {"A": 29, "B": 29}
    assert mc.decide_sleeve(mc.Sleeve("K", cash=5_000.0, **at_target), t, px, mc.Config())["action"] == "hold"   # 4.76%
    # in debt: it trades, and its trims are exempt from the dust rule until the debt is repaid
    debt = mc.decide_sleeve(mc.Sleeve("K", cash=-150.0, **at_target), t, px, mc.Config())
    assert debt["action"] == "trade" and "debt" in debt["reason"] and debt["deltas"] == {"A": -2, "B": -2}
    daily = mc.decide_sleeve(mc.Sleeve("D", cash=-150.0, shares={"A": 500, "B": 500}), t, px, mc.Config())
    assert daily["deltas"] == {"A": -2, "B": -2}                             # $200 a leg: under the $499 floor, traded anyway
    twin = mc.decide_sleeve(mc.Sleeve("D", cash=150.0, shares={"A": 500, "B": 500}), t, px, mc.Config())
    assert twin["action"] == "hold" and twin["deltas"] == {}                 # ... which it is not for a sleeve in credit
    assert mc.in_debt(mc.Sleeve("x", cash=-0.001)) is False                  # float dust is not a debt


def test_a_transfer_is_exempt_from_the_dust_rule_so_a_small_one_moves_in_full():
    """A-09: a transfer under the dust floor sold nothing and handed over only the giver's reserve"""
    book = fresh()
    t = {"HG": ok({"TECL": 1.0}), "KMLM": ok({"SOXL": 0.375, "TECL": 0.375, "PULS": 0.25}), "SLEEVE": ok({"BOXX": 1.0}),
         "HARV": ok({"PULS": 1.0})}
    run(book, t)
    run(book, t, session="d1b")
    k0, h0 = mc.equity(book.sleeves["KMLM"], PX), mc.equity(book.sleeves["HARV"], PX)
    plan = run(book, t, session="d2", transfers=[{"from": "KMLM", "to": "HARV", "amount": 300.0}])   # ~0.9% of KMLM
    assert plan["transfers"][0]["status"] == "moved" and plan["transfers"][0]["moved"] == 300.0
    assert plan["sleeves"]["KMLM"]["action"] == "trade" and all(d < 0 for d in plan["sleeves"]["KMLM"]["deltas"].values())
    assert mc.equity(book.sleeves["KMLM"], PX) == pytest.approx(k0 - 300.0) and book.sleeves["KMLM"].cash >= 0
    assert mc.equity(book.sleeves["HARV"], PX) == pytest.approx(h0 + 300.0)


def test_a_booking_is_all_or_nothing():
    book = mc.Book({"A": mc.Sleeve("A", 0.0, {"X": 30}), "B": mc.Sleeve("B", 0.0, {"X": 5})})
    order = {"id": "mirror-s-S-X", "side": mc.SELL, "symbol": "X", "qty": 40, "asks": {"A": 30, "B": 10}, "applied": False}
    before = book.to_dict()
    with pytest.raises(mc.MirrorError):                                      # B owns 5, would sell 10
        mc.book_fill(book, order, 40, 10.0)
    assert book.to_dict() == before and not order["applied"]                 # A was NOT sold on the way to the refusal
    with pytest.raises(mc.MirrorError):
        mc.book_fill(book, dict(order, asks={"A": 30, "NOPE": 10}), 40, 10.0)
    assert book.to_dict() == before


# ------------------------------------------------------------------ dividends (reviewer B's B2)
DIV = {"ticker": "PULS", "ex_date": "2026-11-10", "pay_date": "2026-11-12", "amount": 0.25}


def test_dividend_receivables_follow_the_shares_held_before_the_ex_date():
    held = {"HARV": {"PULS": 357, "ZVOL": 10}, "KMLM": {"PULS": 172}, "HG": {"TECL": 5}, "SLEEVE": {}}
    rows = mc.dividend_receivables(held, DIV)
    assert rows == [
        {"id": "div-PULS-2026-11-10-HARV", "sleeve": "HARV", "ticker": "PULS", "ex_date": "2026-11-10",
         "pay_date": "2026-11-12", "shares": 357, "amount": 0.25, "total": 89.25},
        {"id": "div-PULS-2026-11-10-KMLM", "sleeve": "KMLM", "ticker": "PULS", "ex_date": "2026-11-10",
         "pay_date": "2026-11-12", "shares": 172, "amount": 0.25, "total": 43.0}]
    assert json.loads(json.dumps(rows)) == rows                              # JSON in, JSON out
    assert mc.dividend_receivables({"HG": {"TECL": 5}}, DIV) == []           # nobody held it: no entitlement
    assert mc.dividend_receivables(held, dict(DIV, pay_date=None))[0]["pay_date"] is None             # R2: never guessed here
    assert mc.dividend_receivables(held, dict(DIV, pay_date="2026-11-01"))[0]["pay_date"] is None     # before the ex-date: not a pay date
    for bad in (dict(DIV, amount=0), dict(DIV, amount=float("nan")), dict(DIV, amount=True), dict(DIV, ex_date="soon"),
                dict(DIV, ticker=""), None, [], dict(DIV, amount=-1.0)):
        assert mc.dividend_receivables(held, bad) == [], bad
    assert mc.dividend_key("PULS", "2026-11-10") == "div-PULS-2026-11-10" and mc.split_key("SQQQ", "2026-11-10") == "split-SQQQ-2026-11-10"


def test_settle_receivable_applies_the_rule_and_books_only_a_credit():
    def book_with(harv_puls):
        return mc.Book({"HARV": mc.Sleeve("HARV", 100.0, {"PULS": harv_puls} if harv_puls else {"BIL": 3}),
                        "KMLM": mc.Sleeve("KMLM", 50.0, {"PULS": 172})})
    rec = mc.dividend_receivables({"HARV": {"PULS": 357}}, DIV)[0]
    b = book_with(357)
    assert mc.settle_receivable(b, rec, "2026-11-11")["action"] == "not_due" and b.sleeves["HARV"].cash == 100.0
    out = mc.settle_receivable(b, rec, "2026-11-12")                         # the pay date, still held: credited
    assert out == {"action": "credited", "amount": 89.25, "held": True} and b.sleeves["HARV"].cash == 189.25
    assert b.sleeves["KMLM"].cash == 50.0                                    # nobody else's cash moves
    sold = book_with(0)                                                      # the sleeve sold the payer before the pay date
    assert mc.settle_receivable(sold, rec, "2026-11-12", "composer") == {"action": "leaked", "amount": 0.0, "held": False}
    assert sold.sleeves["HARV"].cash == 100.0                                # Composer's rule: the cash is nobody's
    assert mc.settle_receivable(sold, rec, "2026-11-12", "holder")["action"] == "credited" and sold.sleeves["HARV"].cash == 189.25
    late = book_with(357)                                                    # a live account that has not been paid yet
    assert mc.settle_receivable(late, rec, "2026-11-12", cash_arrived=False) == {"action": "wait", "amount": 0.0, "held": True}
    assert late.sleeves["HARV"].cash == 100.0
    # the holding test is made ONCE: a credit that waited for its cash is not lost to a later sale ...
    assert mc.settle_receivable(book_with(0), dict(rec, held=True), "2026-11-20", "composer")["action"] == "credited"
    # ... and a leak decided on the pay date is not undone by buying the payer back
    assert mc.settle_receivable(book_with(357), dict(rec, held=False), "2026-11-20", "composer")["action"] == "leaked"
    assert mc.settle_receivable(late, rec, "2026-12-11", cash_arrived=False)["action"] == "wait"       # 29 days
    assert mc.settle_receivable(late, rec, "2026-12-12", cash_arrived=False)["action"] == "expired"    # 30
    assert mc.settle_receivable(late, rec, "2026-12-12", cash_arrived=True)["action"] == "credited"    # paid late is still paid
    assert mc.settle_receivable(mc.Book(), rec, "2026-11-12")["action"] == "void"
    with pytest.raises(mc.MirrorError):
        mc.settle_receivable(b, rec, "2026-11-12", rule="nope")
    with pytest.raises(mc.MirrorError):
        mc.settle_receivable(b, dict(rec, total=float("nan")), "2026-11-12")


def test_r2_a_pay_date_not_known_yet_is_left_open_and_only_assumed_ten_days_after_the_ex_date():
    """round 2 (R2): FMP lists a dividend before it knows the pay date. Guessing ex + 7 at once
    finalised a date that the next listing would have corrected."""
    rec = mc.dividend_receivables({"HARV": {"PULS": 357}}, dict(DIV, pay_date=None))[0]
    assert rec["pay_date"] is None
    book = lambda: mc.Book({"HARV": mc.Sleeve("HARV", 100.0, {"PULS": 357})})        # noqa: E731
    for day in ("2026-11-10", "2026-11-17", "2026-11-18", "2026-11-19"):             # ex + 0 .. ex + 9: not known, not due
        assert mc.receivable_pay_date(rec, day) is None
        b = book()
        assert mc.settle_receivable(b, rec, day)["action"] == "not_due" and b.sleeves["HARV"].cash == 100.0
    assert mc.receivable_pay_date(rec, "2026-11-20") == "2026-11-17"                 # ex + 10: ex + 7 is assumed
    b = book()
    assert mc.settle_receivable(b, rec, "2026-11-20")["action"] == "credited" and b.sleeves["HARV"].cash == 189.25
    late = dict(rec, pay_date="2026-11-25")                                          # the twin: a later listing supplied it
    assert mc.receivable_pay_date(late, "2026-11-20") == "2026-11-25"
    assert mc.settle_receivable(book(), late, "2026-11-24")["action"] == "not_due"
    assert mc.settle_receivable(book(), late, "2026-11-25")["action"] == "credited"
    assert mc.PAY_DATE_GIVE_UP_DAYS == 10 and mc.DEFAULT_PAY_LAG_DAYS == 7


def test_r3_a_sleeve_the_caller_holds_back_is_skipped_in_the_callers_words():
    """round 2 (R3): the executor's own gate (a live sleeve whose tree is not attested) reaches the
    plan as status 'unavailable' + skip_reason; the plan's reason is that text, not 'brain: ...'"""
    book = fresh()
    targets = {"HG": ok({"BIL": 1.0}), "KMLM": ok({"SOXL": 0.5, "PULS": 0.5}), "SLEEVE": ok({"BOXX": 1.0}),
               "HARV": {"status": "unavailable", "version": "v9", "target": {"PULS": 1.0},
                        "skip_reason": "LIVE tree gate: HARV's tree is not attested"}}
    plan = mc.build_plan(book, targets, PX, "2026-11-10", mc.Config())
    assert plan["sleeves"]["HARV"] == {"action": "skip", "reason": "LIVE tree gate: HARV's tree is not attested", "deltas": {}}
    assert "PULS" not in {s for s, q in plan["buy_asks"].get("HARV", {}).items()} and "HARV" not in plan["buy_asks"]
    assert plan["sleeves"]["HG"]["action"] == "trade"
    twin = mc.build_plan(fresh(), dict(targets, HARV={"status": "unavailable", "note": "no prices"}), PX, "2026-11-10", mc.Config())
    assert twin["sleeves"]["HARV"]["reason"] == "brain: no prices"


# ------------------------------------------------------------------ splits (reviewer B's S2)
def test_a_split_does_not_change_what_a_sleeve_is_worth():
    """reviewer B's test_B3b: SQQQ 1:5 on 2025-11-20. The book kept the old share count against the
    new price: sleeve equity 33,515 -> 133,515, and a plan to sell 2,004 of the account's 500 shares."""
    s = mc.Sleeve(name="KMLM", cash=100.0, shares={"SQQQ": 2500, "PULS": 170}, rule="threshold", corridor=0.10)
    book = mc.Book({"KMLM": s})
    before = mc.equity(s, {"SQQQ": 10.0, "PULS": 49.5})
    out = mc.apply_split(book, "SQQQ", 0.2)
    after = mc.equity(s, {"SQQQ": 50.0, "PULS": 49.5})
    assert after == pytest.approx(before) and s.shares == {"SQQQ": 500, "PULS": 170} and s.cash == 100.0
    assert out == {"ticker": "SQQQ", "ratio": 0.2, "before": {"KMLM": 2500}, "after": {"KMLM": 500},
                   "total_before": 2500, "total_after": 500, "fraction": 0.0}
    d = mc.decide_sleeve(s, {"SQQQ": 0.75, "PULS": 0.25}, {"SQQQ": 50.0, "PULS": 49.5}, mc.Config())
    assert d["action"] == "hold"                                             # the twin of the bug: no phantom trade


def test_a_split_floors_the_book_total_and_shares_it_by_largest_remainder():
    book = mc.Book({"A": mc.Sleeve("A", 1.0, {"X": 3}), "B": mc.Sleeve("B", 2.0, {"X": 2500}),
                    "C": mc.Sleeve("C", 3.0, {"X": 4, "Y": 9}), "D": mc.Sleeve("D", 4.0, {"Y": 1})})
    out = mc.apply_split(book, "X", 0.2)                                     # exact: 0.6, 500, 0.8 -> 501.4
    assert out["total_before"] == 2507 and out["total_after"] == 501 and out["fraction"] == pytest.approx(0.4)
    assert out["after"] == {"A": 0, "B": 500, "C": 1}                        # the one spare share to the largest remainder
    assert book.positions() == {"X": 501, "Y": 10} and "X" not in book.sleeves["A"].shares
    assert [s.cash for s in book.sleeves.values()] == [1.0, 2.0, 3.0, 4.0]   # cash in lieu is NOT booked here
    assert mc.check(book) == []
    fwd = mc.Book({"A": mc.Sleeve("A", 0.0, {"X": 7}), "B": mc.Sleeve("B", 0.0, {"X": 5})})
    assert mc.apply_split(fwd, "X", 1.5)["after"] == {"A": 11, "B": 7} and fwd.positions() == {"X": 18}   # 10.5 + 7.5 = 18
    assert mc.apply_split(fwd, "X", 2.0)["after"] == {"A": 22, "B": 14}
    assert mc.apply_split(fwd, "NOPE", 2.0)["total_after"] == 0              # nobody holds it: nothing happens
    third = mc.Book({"A": mc.Sleeve("A", 0.0, {"X": 9})})
    assert mc.apply_split(third, "X", 0.3333333)["after"] == {"A": 3}        # a ratio published as a rounded float
    for bad in (0, -2.0, float("nan"), True, "2", None):
        with pytest.raises(mc.MirrorError):
            mc.apply_split(fwd, "X", bad)
    rnd = random.Random(5)
    for _ in range(500):                                                     # never a share created, never one lost twice
        n = rnd.randint(1, 4)
        b = mc.Book({f"s{i}": mc.Sleeve(f"s{i}", 0.0, {"X": rnd.randint(1, 3000)}) for i in range(n)})
        total = b.positions()["X"]
        ratio = rnd.choice([2.0, 3.0, 1.5, 0.5, 0.2, 0.1, 0.05, 0.25])
        res = mc.apply_split(b, "X", ratio)
        assert res["total_after"] == math.floor(total * ratio + 1e-9) == sum(res["after"].values())
        assert 0 <= res["fraction"] < 1 and b.positions().get("X", 0) == res["total_after"]
        for name, q in res["before"].items():
            assert abs(res["after"][name] - q * ratio) < 1.0


def test_check_compares_the_book_with_the_venue():
    book = fresh()
    run(book, {"HG": ok({"TECL": 1.0})})
    pos = book.positions()
    assert mc.check(book, pos) == []
    assert mc.check(book, dict(pos, TECL=pos["TECL"] - 1)) != []
    assert mc.check(book, dict(pos, SPY=10)) != []                           # exact: a stranger's shares
    assert mc.check(book, dict(pos, SPY=10), exact=False) == []              # shared account: venue >= book
    assert mc.check(book, dict(pos, TECL=pos["TECL"] - 1), exact=False) != []


# ------------------------------------------------------------------ randomized conservation
def test_random_sessions_conserve_shares_and_cash():
    rnd = random.Random(20261110)
    syms = list(PX)
    for trial in range(60):
        book = fresh(rnd.choice([20_000.0, 118_000.0, 1_000_000.0]))
        prices = dict(PX)
        venue: dict = {}
        venue_cash = book.cash()
        for day in range(12):
            prices = {s: p * math.exp(rnd.gauss(0, 0.04)) for s, p in prices.items()}
            targets = {}
            for name in book.sleeves:
                if rnd.random() < 0.1:
                    continue                                                # brain silent for this sleeve
                picks = rnd.sample(syms, rnd.randint(1, 3))
                ws = [rnd.random() + 0.05 for _ in picks]
                targets[name] = ok({s: w / sum(ws) for s, w in zip(picks, ws)})
            def fill(o):
                frac = rnd.choice([1.0, 1.0, 1.0, 0.5, 0.0])
                q = int(o["qty"] * frac)
                slip = 1 + rnd.gauss(0, 0.002)
                return (q, o["ref"] * slip if q else None, 0.35 if q else 0.0)
            before = total_equity(book, prices)
            plan = mc.build_plan(book, targets, prices, f"t{trial}d{day}")
            mc.apply_crosses(book, plan)
            flow = 0.0
            for o in plan["sells"]:
                q, px, fee = fill(o)
                mc.book_fill(book, o, q, px, fee)
                venue[o["symbol"]] = venue.get(o["symbol"], 0) - q
                venue_cash += q * (px or 0) - fee
                flow += q * ((px or 0) - prices[o["symbol"]]) - fee
            mc.apply_transfers(book, plan)
            for o in mc.size_buys(book, plan):
                q, px, fee = fill(o)
                mc.book_fill(book, o, q, px, fee)
                venue[o["symbol"]] = venue.get(o["symbol"], 0) + q
                venue_cash -= q * (px or 0) + fee
                flow -= q * ((px or 0) - prices[o["symbol"]]) + fee
            mc.finish(book, plan)
            assert mc.check(book, {k: v for k, v in venue.items() if v}) == [], (trial, day)
            assert math.isclose(book.cash(), venue_cash, rel_tol=0, abs_tol=1e-6), (trial, day)
            assert math.isclose(total_equity(book, prices), before + flow, rel_tol=0, abs_tol=1e-6), (trial, day)
            assert book.cash() >= -1.0, (trial, day, book.cash())           # never borrows (slip cushion aside)
            for s in book.sleeves.values():
                assert all(isinstance(q, int) and q > 0 for q in s.shares.values())
