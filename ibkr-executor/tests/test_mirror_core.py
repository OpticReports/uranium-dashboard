"""Gate tests for the Composer mirror core (app/mirror_core.py): pure logic, no adapter, no clock."""
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
    run(book, {"HARV": ok({"PULS": 0.4, "ZVOL": 0.6})})
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
