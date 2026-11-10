"""Gate tests for mirror_dry.py (the IBKR mirror's DRY simulator and parity measurement; IBKR_MIRROR.md).

No network: fake prices, minutes, distributions, snapshots and ledger rows. Each behavioural test has
a BROKEN-INPUT twin that must land on the other side (a gate that cannot fail is not a gate).

  M1  costs: IBKR tiered commission ($0.0035 a share, the $0.35 minimum, the 1%-of-value cap) and
      slippage in the fill price, in the function and in the book's cash; twin: no slippage, no cost
  M2  distributions: credited once, on the shares held at the prior close, and left out of the price
      basis; twins: a payer that is not held, a day with no distribution, a re-run that does not pay twice
  M3  a three-day backfill verified by hand, to the cent; twin: one changed close moves the answer
  M4  close mode: the decision IS the ledger's target and the bookings are mirror_core's own (the same
      shares as driving mirror_core directly; mc.check clean after every session); twins: no ledger row
      -> the sleeve stands still, a target that does not sum to 1 -> skipped, a tampered venue -> reported
  M5  Composer's record and the parity classes: snapshot -> session, deposit-adjusted spans, flow days;
      knife-edge / no-rebalance / corridor path / late snapshot / whole-share; return tracking; twins
  M6  minute mode: the brain's payload decides, fills at the bar that starts at the decision time, the
      close when there is none (counted), half-days shift, a refusal stops cleanly; the as-of series
  M7  daily(): seeds once, idempotent, force re-runs the last session without double booking, atomic,
      never raises, MISMATCH only when the shadow ledger does not explain it
  M8  the FMP store: one request per ticker-day, disk cache, throttle, refusal remembered, key never shown
  M9  the brain through the real seams (mirror_brain.build on the frozen 2026-10-28 fixture)

Run: python3 -m unittest composer.scripts.tests.test_mirror_dry -v
"""
import datetime
import json
import math
import os
import sys
import tempfile
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
os.environ.pop("FMP_API_KEY", None)
import mirror_dry as md  # noqa: E402
import shadow_runner as sr  # noqa: E402

mc = md.mc
UTC = datetime.timezone.utc
D0, D1, D2, D3, D4 = "2026-02-27", "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"
CAL = [D0, D1, D2, D3, D4]
MAN = sr.load_manifest()
SID = {e: c["symphony"] for e, c in MAN.items()}


def market(aaa=(100.0, 100.0, 110.0, 121.0, 121.0), bbb=50.0, divs=None, extra=None):
    raw = {"AAA": dict(zip(CAL, aaa)), "BBB": {d: bbb for d in CAL}, "SPY": {d: 500.0 for d in CAL}}
    raw.update(extra or {})
    return md.Market(raw=raw, divs=divs or {}, calendar=CAL)


def led(d, e, target, live=None, status="agree", **kw):
    return dict({"date": d, "engine": e, "version": "v1", "target": target, "live": live if live is not None else dict(target),
                 "status": status}, **kw)


def shadow_of(*rows):
    return {(r["date"], r["engine"]): r for r in rows}


def two_sleeves(days=(D1, D2, D3), hg=None, harv=None):
    """HG and HARV rows for each day: {day: target} per engine (default AAA and BBB throughout)"""
    rows = []
    for d in days:
        rows.append(led(d, "HG", (hg or {}).get(d, {"AAA": 1.0})))
        rows.append(led(d, "HARV", (harv or {}).get(d, {"BBB": 1.0})))
    return shadow_of(*rows)


def run(shadow, mkt=None, slip=0.0, fractions=None, composer=None, **kw):
    return md.backfill(D1, kw.pop("end", D3), "close", shadow=shadow, market=mkt or market(), slip_bps=slip, capital=100_000.0,
                       fractions=fractions or {"HG": 0.5, "HARV": 0.5}, composer=composer if composer is not None else {}, **kw)


def read(path):
    with open(path) as f:
        return f.read()


def rows_of(res, engine):
    return {r["date"]: r for r in res["rows"] if r["engine"] == engine}


class NoNetwork(unittest.TestCase):
    def setUp(self):
        boom = unittest.mock.Mock(side_effect=AssertionError("network call in a unit test"))
        for target in ("mirror_dry._yahoo_chart", "shadow_runner.fetch_minutes", "shadow_runner._chart"):
            p = unittest.mock.patch(target, boom)
            p.start()
            self.addCleanup(p.stop)


# ------------------------------------------------------------------ M1 costs
class M1Costs(NoNetwork):
    def test_commission_per_share_minimum_and_cap(self):
        self.assertAlmostEqual(md.commission(1000, 50.0), 3.50)            # 1000 x 0.0035
        self.assertAlmostEqual(md.commission(498, 100.0), 1.743)
        self.assertAlmostEqual(md.commission(50, 50.0), 0.35)              # 0.175 -> the $0.35 minimum
        self.assertAlmostEqual(md.commission(100, 50.0), 0.35)             # exactly at the minimum
        self.assertAlmostEqual(md.commission(10, 1.00), 0.10)              # the minimum is capped at 1% of $10
        self.assertAlmostEqual(md.commission(20000, 0.20), 40.0)           # 70.00 per share -> capped at 1% of $4,000
        self.assertEqual(md.commission(0, 50.0), 0.0)
        self.assertEqual(md.commission(-7, 50.0), md.commission(7, 50.0))  # a sell costs what a buy costs
        # twins: just above the minimum it is per share again; just under the cap it is not capped
        self.assertAlmostEqual(md.commission(101, 50.0), 0.3535)
        self.assertAlmostEqual(md.commission(10, 40.0), 0.35)

    def test_slippage_is_against_the_mirror_on_both_sides(self):
        self.assertAlmostEqual(md.slipped(mc.SELL, 100.0, 2.0), 99.98)
        self.assertAlmostEqual(md.slipped(mc.BUY, 100.0, 2.0), 100.02)
        self.assertEqual(md.slipped(mc.BUY, 100.0, 0.0), 100.0)            # twin
        self.assertLess(md.slipped(mc.SELL, 100.0, 5.0), md.slipped(mc.SELL, 100.0, 2.0))

    def test_costs_reach_the_books_cash_exactly(self):
        res = run(two_sleeves((D1,)), slip=2.0, end=D1)
        hg = rows_of(res, "HG")[D1]
        order = next(o for o in res["book"][0]["order_list"] if o["symbol"] == "AAA")
        q = order["filled"]
        self.assertEqual(q, 498)                                           # floor(50,000 x 0.997 / 100)
        self.assertAlmostEqual(order["price"], 100.02)
        self.assertAlmostEqual(order["commission"], 1.743)
        self.assertAlmostEqual(hg["slippage"], 498 * 0.02, places=4)
        self.assertAlmostEqual(hg["commission"], 1.743, places=4)
        self.assertAlmostEqual(hg["equity"], 50_000 - 498 * 0.02 - 1.743, places=2)
        self.assertAlmostEqual(hg["ret_px_gross"], 0.0, places=9)           # before costs nothing happened
        self.assertAlmostEqual(hg["ret_px"], -(498 * 0.02 + 1.743) / 50_000, places=9)
        # twin: no slippage -> the fill is the close and only the commission is paid
        res0 = run(two_sleeves((D1,)), slip=0.0, end=D1)
        hg0 = rows_of(res0, "HG")[D1]
        self.assertEqual(hg0["slippage"], 0.0)
        self.assertAlmostEqual(hg0["equity"], 50_000 - 1.743, places=2)
        self.assertGreater(hg0["equity"], hg["equity"])

    def test_a_sell_is_slipped_down_and_charged(self):
        sh = two_sleeves((D1, D2), hg={D2: {"BBB": 1.0}})
        res = run(sh, slip=5.0, end=D2)
        sell = next(o for o in res["book"][1]["order_list"] if o["side"] == mc.SELL)
        self.assertEqual((sell["symbol"], sell["filled"]), ("AAA", 498))
        self.assertAlmostEqual(sell["price"], 110.0 * (1 - 5e-4))
        self.assertAlmostEqual(sell["commission"], 1.743)
        buy = next(o for o in res["book"][1]["order_list"] if o["side"] == mc.BUY)
        self.assertAlmostEqual(buy["price"], 50.0 * (1 + 5e-4))
        self.assertEqual(res["book"][1]["problems"], [])


# ------------------------------------------------------------------ M2 distributions
class M2Distributions(NoNetwork):
    def test_credited_once_on_prior_shares_and_left_out_of_the_price_basis(self):
        res = run(two_sleeves(), market(divs={"AAA": {D2: 1.0}}))
        hg = rows_of(res, "HG")
        self.assertEqual(hg[D1]["div"], 0.0)
        self.assertAlmostEqual(hg[D2]["div"], 498.0)                       # 498 shares held at the D1 close x $1
        self.assertEqual(hg[D2]["div_by"], {"AAA": 498.0})
        self.assertEqual(hg[D3]["div"], 0.0)                               # once: not again the next session
        self.assertAlmostEqual(sum(r["div"] for r in res["rows"]), 498.0)
        self.assertAlmostEqual(res["book"][1]["div"], 498.0)
        # the price basis takes exactly the credit out of the day's return
        self.assertAlmostEqual(hg[D2]["ret"] - hg[D2]["ret_px"], 498.0 / hg[D2]["equity_prev"], places=7)
        self.assertAlmostEqual(hg[D2]["ret_px"], (hg[D2]["equity"] - 498.0) / hg[D2]["equity_prev"] - 1, places=7)
        # ... and the credit stays in the book afterwards (it is cash the sleeve reinvests)
        base = rows_of(run(two_sleeves()), "HG")
        self.assertGreater(hg[D3]["equity"], base[D3]["equity"] + 498.0)   # $498 and what it earned on D3
        self.assertAlmostEqual(hg[D1]["index_px"], base[D1]["index_px"])

    def test_twins_not_held_and_no_distribution(self):
        # BBB pays, but HG holds AAA: nothing for HG; HARV (997 BBB) collects
        res = run(two_sleeves(), market(divs={"BBB": {D2: 0.25}}))
        self.assertEqual(rows_of(res, "HG")[D2]["div"], 0.0)
        self.assertAlmostEqual(rows_of(res, "HARV")[D2]["div"], 997 * 0.25)
        # no distribution anywhere: both bases are the same number every day
        for r in run(two_sleeves())["rows"]:
            self.assertEqual(r["div"], 0.0)
            self.assertAlmostEqual(r["ret"], r["ret_px"], places=12)
        # an ex-date before the sleeve held the payer (D1: bought at that day's close) pays nothing
        res = run(two_sleeves(), market(divs={"AAA": {D1: 1.0}}))
        self.assertEqual(sum(r["div"] for r in res["rows"]), 0.0)

    def test_an_ex_date_between_sessions_is_paid_at_the_next_one(self):
        sat = "2026-03-01"                                                 # no session: paid on D1... to holders at D0
        m = market(divs={"AAA": {sat: 1.0, "2026-03-03": 0.5}})
        self.assertEqual(m.dividends(D1, D2), {"AAA": 0.5})
        self.assertEqual(m.dividends(D0, D1), {"AAA": 1.0})
        self.assertEqual(m.dividends(D2, D3), {})                          # twin: nothing in (D2, D3]
        self.assertEqual(m.dividends(None, D2), {"AAA": 0.5})


# ------------------------------------------------------------------ M3 three days by hand
class M3ThreeDaysByHand(NoNetwork):
    """HG $50,000: AAA 100 -> 110 (ex $1 a share) -> 121, then into BBB at 50. No slippage, so every
    number below is integer shares x round prices and the tiered commission."""

    def test_to_the_cent(self):
        sh = two_sleeves(hg={D3: {"BBB": 1.0}})
        res = run(sh, market(divs={"AAA": {D2: 1.0}}))
        hg, harv = rows_of(res, "HG"), rows_of(res, "HARV")
        # D1: floor(50,000 x 0.997 / 100) = 498 AAA at 100; commission 498 x 0.0035 = 1.743
        e1 = 50_000 - 1.743
        self.assertEqual((hg[D1]["action"], hg[D1]["target"]), ("trade", {"AAA": 1.0}))
        self.assertAlmostEqual(hg[D1]["equity"], round(e1, 2), places=2)
        self.assertAlmostEqual(hg[D1]["ret"], -1.743 / 50_000, places=9)
        # D2: +498 x $1 credited; AAA 110. Equity before trading 198.257 + 498 + 54,780 = 55,476.257;
        # wanted floor(55,476.257 x 0.997 / 110) = 502 -> buy 4 at 110 (commission: the $0.35 minimum)
        cash2 = (50_000 - 498 * 100 - 1.743) + 498.0
        self.assertEqual(math.floor((cash2 + 498 * 110) * 0.997 / 110), 502)
        cash2 -= 4 * 110 + 0.35
        e2 = cash2 + 502 * 110
        self.assertAlmostEqual(hg[D2]["equity"], round(e2, 2), places=2)
        self.assertAlmostEqual(hg[D2]["div"], 498.0)
        self.assertAlmostEqual(hg[D2]["ret"], e2 / e1 - 1, places=7)
        self.assertAlmostEqual(hg[D2]["ret_px"], (e2 - 498.0) / e1 - 1, places=7)
        self.assertAlmostEqual(hg[D2]["commission"], 0.35, places=4)
        # D3: sell 502 AAA at 121 (commission 1.757), buy floor(60,997.907 x 0.997 / 50) = 1216 BBB (4.256)
        cash3 = cash2 + 502 * 121 - 502 * 0.0035
        self.assertEqual(math.floor((cash2 + 502 * 121) * 0.997 / 50), 1216)
        cash3 -= 1216 * 50 + 1216 * 0.0035
        e3 = cash3 + 1216 * 50
        self.assertAlmostEqual(hg[D3]["equity"], round(e3, 2), places=2)
        self.assertAlmostEqual(hg[D3]["ret"], e3 / e2 - 1, places=7)
        self.assertEqual(hg[D3]["weights"], {"BBB": round(1216 * 50 / e3, 6)})
        self.assertEqual(res["book_final"]["sleeves"][0]["shares"], {"BBB": 1216})
        # the price-basis index chains the three price returns; the total return is e3 / 50,000
        want = (1 - 1.743 / 50_000) * ((e2 - 498.0) / e1) * (e3 / e2)
        self.assertAlmostEqual(hg[D3]["index_px"], want, places=7)
        # HARV: 997 BBB at 50 on D1 (commission 3.4895), then flat
        self.assertAlmostEqual(harv[D3]["equity"], round(50_000 - 997 * 0.0035, 2), places=2)
        self.assertEqual((harv[D2]["action"], harv[D3]["action"]), ("hold", "hold"))
        # the book: equity is the two sleeves; venue orders D1 2, D2 1, D3 2; nothing crossed
        self.assertAlmostEqual(res["book"][2]["equity"], round(e3 + 50_000 - 997 * 0.0035, 2), places=2)
        self.assertEqual([b["orders"] for b in res["book"]], [2, 1, 2])
        self.assertEqual([b["crosses"] for b in res["book"]], [0, 0, 0])
        self.assertEqual([b["problems"] for b in res["book"]], [[], [], []])

    def test_twin_one_changed_close_moves_the_answer(self):
        sh = two_sleeves(hg={D3: {"BBB": 1.0}})
        a = rows_of(run(sh, market(divs={"AAA": {D2: 1.0}})), "HG")[D3]["equity"]
        b = rows_of(run(sh, market(aaa=(100.0, 100.0, 110.0, 120.0, 120.0), divs={"AAA": {D2: 1.0}})), "HG")[D3]["equity"]
        self.assertAlmostEqual(a - b, 502 * 1.0, delta=1.0)                # 502 shares x the $1 lower exit

    def test_opposite_legs_cross_inside_the_book_at_no_cost(self):
        sh = two_sleeves(hg={D3: {"BBB": 1.0}}, harv={D3: {"AAA": 1.0}})   # the sleeves swap on D3
        res = run(sh, slip=2.0)
        b3 = res["book"][2]
        self.assertEqual(b3["crosses"], 2)                                 # AAA and BBB both cross
        self.assertGreater(b3["crossed"], 90_000)
        self.assertLess(b3["traded"], 25_000)                              # only the net reaches the venue
        self.assertLessEqual(b3["orders"], 2)
        self.assertEqual(b3["problems"], [])
        swap_cost = b3["commission"] + b3["slippage"]
        # twin: HG alone rotates -> everything goes through the venue and costs several times more
        solo = run(two_sleeves(hg={D3: {"BBB": 1.0}}), slip=2.0)["book"][2]
        self.assertEqual(solo["crosses"], 0)
        self.assertGreater(solo["commission"] + solo["slippage"], 3 * swap_cost)


# ------------------------------------------------------------------ M4 close mode drives mirror_core
class M4CloseModeDrivesMirrorCore(NoNetwork):
    def test_the_decision_is_the_ledgers_target_and_the_book_is_mirror_cores(self):
        sh = two_sleeves(hg={D2: {"AAA": 0.6, "BBB": 0.4}, D3: {"BBB": 1.0}})
        mkt = market()
        res = run(sh, mkt)
        for r in res["rows"]:
            self.assertEqual(r["target"], sh[(r["date"], r["engine"])]["target"])
        # the same sessions driven through mirror_core by hand, as its own tests do
        book = mc.Book.seed(100_000.0, {"HG": 0.5, "HARV": 0.5}, md.rules_from_manifest())
        for d in (D1, D2, D3):
            px = mkt.closes(d)
            t = {e: {"status": "ok", "target": sh[(d, e)]["target"], "version": "v1"} for e in ("HG", "HARV")}
            plan = mc.build_plan(book, t, px, d)
            mc.apply_crosses(book, plan)
            for o in plan["sells"]:
                mc.book_fill(book, o, o["qty"], o["ref"], md.commission(o["qty"], o["ref"]))
            mc.apply_transfers(book, plan)
            for o in mc.size_buys(book, plan):
                mc.book_fill(book, o, o["qty"], o["ref"], md.commission(o["qty"], o["ref"]))
            mc.finish(book, plan)
            self.assertEqual(mc.check(book, book.positions()), [])
        self.assertEqual(res["book_final"], book.to_dict())
        self.assertEqual(mc.check(mc.Book.from_dict(res["book_final"]), res["state"]["venue"]), [])
        self.assertTrue(all(b["problems"] == [] for b in res["book"]))

    def test_invariants_hold_after_every_session_of_a_busy_month(self):
        import random
        rnd = random.Random(11)
        days = [f"2026-03-{x:02d}" for x in range(2, 28) if datetime.date(2026, 3, x).weekday() < 5]
        syms = ["AAA", "BBB", "CCC", "DDD"]
        px = {s: 20.0 + 30 * i for i, s in enumerate(syms)}
        raw, rows = {s: {} for s in syms}, []
        for d in days:
            for s in syms:
                px[s] *= math.exp(rnd.gauss(0, 0.04))
                raw[s][d] = px[s]
            for e in md.FRACTIONS:
                if rnd.random() < 0.1:
                    continue                                               # no ledger row that engine-day
                picks = rnd.sample(syms, rnd.randint(1, 3))
                ws = [rnd.random() + 0.1 for _ in picks]
                rows.append(led(d, e, {s: w / sum(ws) for s, w in zip(picks, ws)}))
        divs = {"AAA": {days[5]: 0.4, days[12]: 0.4}, "CCC": {days[9]: 1.1}}
        mkt = md.Market(raw=raw, divs=divs, calendar=days)
        sim_seen = []
        real = md.Sim.session

        def spy(self, d, *a, **k):
            out = real(self, d, *a, **k)
            sim_seen.append((d, mc.check(self.book, self.venue), self.book.cash()))
            return out
        with unittest.mock.patch.object(md.Sim, "session", spy):
            res = md.backfill(days[0], days[-1], "close", shadow=shadow_of(*rows), market=mkt, composer={}, slip_bps=2.0)
        self.assertEqual(len(sim_seen), len(days))
        for d, problems, cash in sim_seen:
            self.assertEqual(problems, [], d)
            self.assertGreaterEqual(cash, -1e-6, d)                        # the book never borrows
        self.assertTrue(all(b["problems"] == [] for b in res["book"]))
        self.assertGreater(sum(b["crosses"] for b in res["book"]), 0)      # four sleeves, four funds: legs do cross
        self.assertAlmostEqual(sum(r["div"] for r in res["rows"]), sum(b["div"] for b in res["book"]), places=1)
        # the KMLM sleeve is the threshold one and does hold inside its corridor some days
        kmlm = [r for r in res["rows"] if r["engine"] == "KMLM"]
        self.assertTrue(any("corridor" in (r["reason"] or "") for r in kmlm))
        self.assertEqual(mc.Book.from_dict(res["book_final"]).sleeves["KMLM"].corridor, 0.10)

    def test_twin_no_ledger_row_or_a_bad_target_leaves_the_sleeve_alone(self):
        sh = two_sleeves(hg={D3: {"BBB": 1.0}})
        del sh[(D2, "HG")]                                                 # the ledger has no HG row on D2
        sh[(D3, "HARV")] = led(D3, "HARV", {"AAA": 0.5})                    # a target that does not sum to 1
        res = run(sh)
        hg, harv = rows_of(res, "HG"), rows_of(res, "HARV")
        self.assertEqual(hg[D2]["action"], "skip")
        self.assertIn("no target", hg[D2]["reason"])
        self.assertEqual(hg[D2]["weights"].keys(), {"AAA"})                # still holds what it held
        self.assertEqual(hg[D3]["action"], "trade")                        # and trades again when a row is back
        self.assertEqual(harv[D3]["action"], "skip")
        self.assertIn("sum", harv[D3]["reason"])
        self.assertEqual(harv[D3]["weights"].keys(), {"BBB"})
        self.assertEqual(res["skipped_sessions"], [])                      # some engine had a target every day
        # no row for anyone -> the session is listed as skipped
        only = shadow_of(led(D1, "HG", {"AAA": 1.0}), led(D3, "HG", {"AAA": 1.0}))
        self.assertEqual(run(only)["skipped_sessions"], [D2])

    def test_twin_a_book_that_disagrees_with_the_venue_is_reported(self):
        book = md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5})
        sim = md.Sim(book, 0.0)
        px = market().closes(D1)
        t = {"HG": {"status": "ok", "target": {"AAA": 1.0}}}
        _, b = sim.session(D1, t, px, px, px)
        self.assertEqual(b["problems"], [])
        sim.venue["AAA"] -= 1                                              # the account lost a share the book still owns
        _, b = sim.session(D2, t, market().closes(D2), market().closes(D2), market().closes(D2))
        self.assertTrue(any("AAA" in p and "venue" in p for p in b["problems"]), b["problems"])

    def test_a_missing_fill_price_leaves_the_order_unfilled_and_says_so(self):
        book = md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5})
        sim = md.Sim(book, 0.0)
        px = market().closes(D1)
        t = {"HG": {"status": "ok", "target": {"AAA": 1.0}}}
        _, b = sim.session(D1, t, px, {}, px)                              # a plan, and no price to fill it at
        self.assertEqual(book.positions(), {})
        self.assertTrue(any("no fill price for AAA" in p for p in b["problems"]))
        self.assertEqual(b["orders"], 0)
        _, b = sim.session(D2, t, px, px, px)                              # twin: with a price it fills
        self.assertEqual((book.positions(), b["problems"], b["orders"]), ({"AAA": 498}, [], 1))


# ------------------------------------------------------------------ M5 Composer's record and parity
def snap(taken_at, **eng):
    """a monitor snapshot: eng = {ENGINE: (deposit_adjusted_value, value, holdings)}"""
    return {"taken_at": taken_at, "symphonies": {SID[e]: {"name": e, "value": v, "deposit_adjusted_value": dav, "cash": 1.0,
                                                           "holdings": h, "last_percent_change": 0.0123}
                                                 for e, (dav, v, h) in eng.items()}}


class M5ComposerRecordAndParity(NoNetwork):
    def test_a_snapshot_speaks_for_the_right_session(self):
        f = md.snapshot_session
        self.assertEqual(f("2026-03-03T21:35:00+00:00", CAL), (D2, "close"))        # 16:35 ET
        self.assertEqual(f("2026-03-04T01:10:00+00:00", CAL), (D2, "close"))        # 20:10 ET the same evening
        self.assertEqual(f("2026-03-04T12:30:00+00:00", CAL), (D2, "late"))         # 07:30 ET, before the open
        self.assertEqual(f("2026-03-07T15:00:00+00:00", CAL), (D4, "late"))         # a Saturday
        self.assertEqual(f("2026-03-04T19:00:00+00:00", CAL), (D2, "next-day"))     # 14:00 ET during D3: holdings only
        self.assertEqual(f("2026-03-04T21:00:00+00:00", CAL), (D3, "close"))        # twin: at the close it is D3's own
        self.assertEqual(f("garbage", CAL), (None, None))

    def test_record_spans_and_flow_days(self):
        snaps = [snap("2026-03-02T21:35:00+00:00", HG=(1000.0, 50_000.0, {"AAA": 0.999})),
                 snap("2026-03-03T21:35:00+00:00", HG=(1100.0, 55_000.0, {"AAA": 0.999})),
                 snap("2026-03-04T19:00:00+00:00", HG=(1150.0, 57_500.0, {"AAA": 0.5, "BBB": 0.499})),   # intraday D3... for D2
                 snap("2026-03-05T21:35:00+00:00", HG=(1210.0, 70_500.0, {"BBB": 0.999}))]
        rec = md.composer_record(snaps, CAL)["HG"]
        self.assertEqual(sorted(rec), [D1, D2, D4])                        # the intraday one never replaces D2's close
        self.assertEqual(rec[D2]["kind"], "close")
        self.assertEqual(rec[D1]["holdings"], {"AAA": 1.0})                # normalised over the invested part
        spans = md.composer_spans(rec, CAL)
        self.assertEqual([(s["d0"], s["d1"], s["n"]) for s in spans], [(D1, D2, 1), (D2, D4, 2)])
        self.assertAlmostEqual(spans[0]["ret"], 0.10)
        self.assertEqual(spans[0]["flow"], 0.0)                            # value moved with the return
        self.assertAlmostEqual(spans[1]["ret"], 0.10)
        self.assertAlmostEqual(spans[1]["flow"], 70_500.0 - 55_000.0 * 1.1, places=2)   # a $10,000 deposit
        # twin: only an intraday snapshot for a session -> holdings, no value, no return through it
        only = md.composer_record([snaps[0], snaps[2]], CAL)["HG"]
        self.assertEqual((only[D2]["kind"], only[D2]["dav"]), ("next-day", None))
        self.assertEqual(md.composer_spans(only, CAL), [])

    def test_tracking_statistics_and_the_exclusion(self):
        idx = {D0: 1.0, D1: 1.01, D2: 1.0302, D3: 1.0302 * 0.99, D4: 1.0302 * 0.99 * 1.03}
        spans = [{"d0": D0, "d1": D1, "n": 1, "ret": 0.01}, {"d0": D1, "d1": D2, "n": 1, "ret": 0.015},
                 {"d0": D2, "d1": D4, "n": 2, "ret": 0.0197}]
        t = md.tracking(idx, spans)
        self.assertEqual((t["n_daily"], t["n_spans"], t["sessions"]), (2, 3, 4))
        self.assertAlmostEqual(t["mean_bps"], (0.0 + 50.0) / 2, places=3)   # D2: mirror +2.00% vs +1.50%
        self.assertAlmostEqual(t["cum_mirror"], idx[D4] - 1, places=6)
        self.assertAlmostEqual(t["cum_composer"], 1.01 * 1.015 * 1.0197 - 1, places=6)
        self.assertEqual(t["worst"][0]["date"], D2)
        x = md.tracking(idx, spans, exclude=[D3])                          # the two-session span touches D3: dropped
        self.assertEqual((x["n_spans"], x["n_daily"]), (2, 2))
        self.assertAlmostEqual(x["cum_composer"], 1.01 * 1.015 - 1, places=6)
        self.assertEqual(md.tracking(idx, [])["n_daily"], 0)                # twin: nothing to compare

    def test_same_holdings_agree_and_each_disagreement_gets_its_class(self):
        aaa, bbb = {"AAA": 1.0}, {"BBB": 1.0}
        sh = shadow_of(led(D1, "HG", aaa), led(D2, "HG", aaa, live=bbb, status="knife-edge", edge={"basis": "intraday", "time": "15:54"}),
                       led(D3, "HG", bbb, live=aaa, status="no-rebalance", live_asof=D1),
                       led(D1, "HARV", bbb), led(D2, "HARV", bbb, live=aaa), led(D3, "HARV", bbb))
        res = run(sh)
        par = res["parity"]["decisions"]
        self.assertEqual(par["HG"]["classes"], {"agree": 1, "composer-no-rebalance": 1, "knife-edge": 1})
        self.assertEqual(par["HARV"]["classes"], {"agree": 2, "other": 1})   # 'agree' in the ledger, yet different: unexplained
        self.assertEqual(par["ALL"]["n"], 6)
        self.assertAlmostEqual(par["ALL"]["share"], 0.5)
        other = next(x for x in res["parity"]["disagreements"] if x["class"] == "other")
        self.assertEqual((other["date"], other["engine"]), (D2, "HARV"))
        self.assertIn("Composer AAA 100%", other["note"])
        # twin: Composer on the target everywhere -> every engine-day agrees (the 0.3% cash reserve is inside 3%)
        ok = run(two_sleeves())["parity"]["decisions"]
        self.assertEqual(ok["ALL"]["classes"], {"agree": 6})

    def test_the_cash_reserve_alone_never_breaks_agreement_but_a_3pp_gap_does(self):
        row = {"weights": {"AAA": 0.9940}, "action": "hold", "target": {"AAA": 1.0}}
        ok, dist, cls, _ = md.classify_day(row, led(D1, "HG", {"AAA": 1.0}), None, None, False, None)
        self.assertTrue(ok)
        self.assertLess(dist, 0.01)
        row = {"weights": {"AAA": 0.93, "BBB": 0.064}, "action": "hold", "target": {"AAA": 1.0}}
        ok, dist, cls, _ = md.classify_day(row, led(D1, "HG", {"AAA": 1.0}), None, None, False, None)
        self.assertEqual((ok, cls), (False, "whole-share"))                # Composer is on the target; the mirror is off it

    def test_corridor_path_and_late_snapshot_classes(self):
        tgt = {"AAA": 0.75, "BBB": 0.25}
        row = {"weights": {"AAA": 0.68, "BBB": 0.317}, "action": "hold", "gap": 0.07, "target": tgt}
        lg = led(D2, "KMLM", tgt, live=tgt)
        f = md.classify_day
        self.assertEqual(f(row, lg, 0.10, True, False, None)[2], "corridor-path")       # Composer rebalanced, the mirror held
        self.assertIn("Composer rebalanced", f(row, lg, 0.10, True, False, None)[3])
        self.assertEqual(f(dict(row, action="trade"), lg, 0.10, False, False, None)[2], "corridor-path")
        self.assertEqual(f(row, lg, 0.10, False, False, D1)[2], "corridor-path")        # both held, apart since D1
        self.assertEqual(f(row, lg, 0.10, None, False, None, (D1,))[2], "corridor-path")   # stood still on a ledger gap
        self.assertEqual(f(row, lg, 0.10, False, True, None)[2], "late-snapshot")
        # twins: a daily engine has no corridor to blame (Composer on the target, the mirror off it: sizing;
        # Composer off the target too: unexplained); the same holdings agree whatever the flags
        self.assertEqual(f(row, lg, None, True, False, None)[2], "whole-share")
        self.assertEqual(f(row, led(D2, "HG", tgt, live={"AAA": 0.5, "BBB": 0.5}), None, True, False, None)[2], "other")
        self.assertTrue(f(dict(row, weights=tgt), lg, 0.10, True, True, D1)[0])

    def test_composer_traded_reads_the_drifted_holdings(self):
        raw = {"AAA": {D1: 100.0, D2: 110.0}, "BBB": {D1: 50.0, D2: 50.0}}
        held = {"AAA": 0.5, "BBB": 0.5}
        drifted = sr.drift(held, raw, D1, D2)
        sh = shadow_of(led(D1, "KMLM", held), led(D2, "KMLM", held, live=drifted))
        self.assertIs(md.composer_traded(sh, raw, D2, D1, "KMLM"), False)   # only drift: no trade
        sh[(D2, "KMLM")]["live"] = held
        self.assertIs(md.composer_traded(sh, raw, D2, D1, "KMLM"), True)    # back at 50/50: it rebalanced
        self.assertIsNone(md.composer_traded(sh, raw, D2, None, "KMLM"))    # no previous session on record

    def test_return_tracking_against_composer_end_to_end(self):
        sh = two_sleeves()
        base = run(sh)
        hg = rows_of(base, "HG")
        # Composer earned exactly the mirror's price return -> zero difference; then 40 bps more on D3
        comp = {"HG": {d: {"dav": 1000.0 * hg[d]["index_px"], "value": hg[d]["equity"], "holdings": {"AAA": 1.0}, "kind": "close",
                           "taken_at": d} for d in (D1, D2, D3)}}
        t = run(sh, composer=comp)["parity"]["engines"]["HG"]["tracking"]
        self.assertEqual(t["n_daily"], 2)
        self.assertAlmostEqual(t["mean_bps"], 0.0, places=3)
        self.assertAlmostEqual(t["cum_gap"], 0.0, places=6)
        comp["HG"][D3]["dav"] *= 1.004
        t = run(sh, composer=comp)["parity"]["engines"]["HG"]["tracking"]
        self.assertAlmostEqual(t["worst"][0]["diff_bps"], -44.0, delta=1.0)  # 40 bps on a 1.10x day
        self.assertEqual(t["worst"][0]["date"], D3)
        self.assertLess(t["cum_gap"], -0.0035)


# ------------------------------------------------------------------ M6 minute mode
class FakeMinutes(md.Minutes):
    """the real store on canned bars: {(ticker, date): {'HH:MM': close}}"""

    def __init__(self, bars, refuse_on=None, **kw):
        self.bars, self.refuse_on, self.calls = bars, refuse_on, []

        def fetch(t, d, key):
            self.calls.append((t, d))
            if refuse_on and d >= refuse_on:
                raise RuntimeError(f"FMP {t} {d}: HTTP Error 429: Too Many Requests")
            return dict(bars.get((t, d), {}))
        super().__init__(key="k-secret", fetch=fetch, rate=1e9, sleep=lambda s: None, **kw)


def payload(**targets):
    return {"schema": 1, "asof_et": "15:55:00", "replay": True, "problems": [], "quotes": {"source": "fmp-1m"},
            "engines": {e: ({"status": "ok", "target": t, "version": "v9", "label": "firm", "rule": "daily"} if t else
                            {"status": "unavailable", "note": "no prices for XYZ"}) for e, t in targets.items()}}


class M6MinuteMode(NoNetwork):
    def setUp(self):
        super().setUp()
        self.bars = {("AAA", D2): {"15:53": 108.0, "15:54": 109.0, "15:55": 109.5, "15:59": 110.0},
                     ("BBB", D2): {"15:30": 50.0},                         # thin: nothing at 15:54 or 15:55
                     ("AAA", D3): {"15:54": 120.0, "15:55": 120.5}, ("BBB", D3): {"15:54": 50.0, "15:55": 50.1}}
        self.asked = []

    def build(self, plan):
        def fake(now, quotes=None, fetch=None):
            e = sr.et_now(now)
            self.asked.append((e.date().isoformat(), e.strftime("%H:%M")))
            return payload(**plan[e.date().isoformat()])
        return fake

    def test_decides_from_the_brain_and_fills_at_the_decision_minutes_bar(self):
        sh = two_sleeves((D1,))                                            # close mode warms the book on D1
        plan = {D2: {"HG": {"BBB": 1.0}, "HARV": {"AAA": 1.0}}, D3: {"HG": {"BBB": 1.0}, "HARV": {"AAA": 1.0}}}
        res = md.backfill(D1, D3, "minute", minute_start=D2, shadow=sh, market=market(), minutes=FakeMinutes(self.bars),
                          build=self.build(plan), composer={}, slip_bps=0.0, capital=100_000.0, fractions={"HG": 0.5, "HARV": 0.5})
        self.assertEqual(self.asked, [(D2, "15:55"), (D3, "15:55")])       # the warm-up day never asks the brain
        self.assertEqual([b["mode"] for b in res["book"]], ["close", "minute", "minute"])
        o = {x["symbol"] + x["side"]: x for x in res["book"][1]["order_list"]}
        # the sleeves swap: AAA and BBB cross at the REFERENCE (the 15:54 bar's close 109.0; BBB's last trade 50.0)
        self.assertEqual(res["book"][1]["crosses"], 2)
        self.assertAlmostEqual(o["AAASELL"]["ref"], 109.0)
        self.assertAlmostEqual(o["AAASELL"]["px"], 109.5)                   # filled at the close of the bar that STARTS 15:55
        self.assertAlmostEqual(o["BBBBUY"]["px"], 50.0)                     # no 15:55 bar: the day's close
        self.assertEqual(res["book"][1]["fill_fallbacks"], ["BBB"])
        self.assertEqual(res["minute"]["fallbacks"], 1)
        self.assertEqual(res["minute"]["fallback_tickers"], {"BBB": 1})
        self.assertEqual((res["minute"]["covered"], res["minute"]["stopped"]), (2, None))
        hg = rows_of(res, "HG")
        self.assertEqual((hg[D2]["mode"], hg[D2]["decide"], hg[D2]["label"], hg[D2]["version"]), ("minute", "15:55", "firm", "v9"))
        self.assertEqual(hg[D2]["target"], {"BBB": 1.0})                   # the brain's, not a ledger's (there is none)
        self.assertEqual(res["book"][1]["problems"], [])
        # valued at the official close: HARV now holds AAA, marked at 110.0, not at its 109.5 fill
        harv = rows_of(res, "HARV")[D2]
        shares = mc.Book.from_dict(res["book_final"]).sleeves["HARV"].shares["AAA"]
        self.assertAlmostEqual(harv["weights"]["AAA"], shares * 110.0 / harv["equity"], places=3)

    def test_twin_fill_at_the_close_and_other_decision_times(self):
        ref, fills, fb = md.minute_prices(D2, "15:55", ["AAA", "BBB"], FakeMinutes(self.bars), market(), "close")
        self.assertEqual((fills, fb), ({"AAA": 110.0, "BBB": 50.0}, []))    # a market-on-close order: no fallback to count
        self.assertEqual(ref["AAA"], 109.0)
        ref, fills, fb = md.minute_prices(D2, "15:54", ["AAA"], FakeMinutes(self.bars), market())
        self.assertEqual((ref["AAA"], fills["AAA"], fb), (108.0, 109.0, []))   # a minute earlier: the 15:53 and 15:54 bars
        # a print 30% off the day's close is not a fill (a split, a bad tick): the close, and counted
        bad = dict(self.bars)
        bad[("AAA", D2)] = {"15:54": 109.0, "15:55": 33.0}
        ref, fills, fb = md.minute_prices(D2, "15:55", ["AAA"], FakeMinutes(bad), market())
        self.assertEqual((fills["AAA"], fb), (110.0, ["AAA"]))
        # no minute at all before the decision: the reference is the previous close
        ref, _, _ = md.minute_prices(D2, "15:55", ["BBB"], FakeMinutes({}), market(bbb=50.0))
        self.assertEqual(ref["BBB"], 50.0)

    def test_half_days_keep_their_distance_to_the_close(self):
        self.assertEqual(md.decide_at("2026-11-27"), "12:55")
        self.assertEqual(md.decide_at("2026-11-27", "15:45"), "12:45")
        self.assertEqual(md.decide_at("2026-11-25"), "15:55")               # twin: a full day
        self.assertIn("2026-11-27", sr.HALF_DAYS)

    def test_an_unavailable_engine_stands_still_and_is_listed(self):
        sh = two_sleeves((D1,))
        plan = {D2: {"HG": None, "HARV": {"BBB": 1.0}}, D3: {"HG": {"AAA": 1.0}, "HARV": {"BBB": 1.0}}}
        res = md.backfill(D1, D3, "minute", minute_start=D2, shadow=sh, market=market(), minutes=FakeMinutes(self.bars),
                          build=self.build(plan), composer={}, capital=100_000.0, fractions={"HG": 0.5, "HARV": 0.5})
        hg = rows_of(res, "HG")
        self.assertEqual((hg[D2]["action"], hg[D2]["brain"]), ("skip", "unavailable"))
        self.assertIn("no prices for XYZ", hg[D2]["reason"])
        self.assertEqual(res["minute"]["unavailable"][0]["engines"], ["HG"])
        self.assertEqual(hg[D3]["action"], "hold")                         # twin: decided again the next day

    def test_a_refusal_stops_cleanly_and_keeps_what_it_has(self):
        sh = two_sleeves((D1,))
        plan = {D2: {"HG": {"BBB": 1.0}, "HARV": {"AAA": 1.0}}, D3: {"HG": {"AAA": 1.0}, "HARV": {"BBB": 1.0}}}
        mn = FakeMinutes(self.bars, refuse_on=D3)
        res = md.backfill(D1, D3, "minute", minute_start=D2, shadow=sh, market=market(), minutes=mn, build=self.build(plan),
                          composer={}, capital=100_000.0, fractions={"HG": 0.5, "HARV": 0.5})
        self.assertEqual(res["sessions"], [D1, D2])                        # D3 was not half-simulated
        self.assertEqual(res["minute"]["covered"], 1)
        self.assertIn("refused", res["minute"]["stopped"])
        self.assertIn("429", res["minute"]["stopped"])
        self.assertNotIn("k-secret", json.dumps(res["minute"]))
        self.assertEqual(res["end"], D2)
        # twin: nothing refused -> both minute sessions are there
        ok = md.backfill(D1, D3, "minute", minute_start=D2, shadow=sh, market=market(), minutes=FakeMinutes(self.bars),
                         build=self.build(plan), composer={}, capital=100_000.0, fractions={"HG": 0.5, "HARV": 0.5})
        self.assertEqual((ok["sessions"], ok["minute"]["covered"]), ([D1, D2, D3], 2))

    def test_the_as_of_series_is_what_yahoo_showed_that_day(self):
        raw = {D0: 100.0, D1: 101.0, D2: 102.0, D3: 100.5, D4: 101.0}       # $2 ex on D3: Yahoo's adjusted history today
        k = 1 - 2.0 / raw[D2]
        adj = {D0: 100.0 * k, D1: 101.0 * k, D2: 102.0 * k, D3: 100.5, D4: 101.0}
        a, r = md.asof_series(adj, raw, D2)
        self.assertEqual(sorted(a), [D0, D1, D2])                           # nothing after the day
        for d in (D0, D1, D2):
            self.assertAlmostEqual(a[d], raw[d], places=9)                  # no distribution had been paid yet
        self.assertEqual(r, {D0: 100.0, D1: 101.0, D2: 102.0})
        # twin: as fetched today the same bars sit 2% lower, so a raw 15:54 price on D2 reads as a +2% day
        self.assertAlmostEqual(102.0 / adj[D1] - 1, 102.0 / 101.0 / k - 1)
        self.assertGreater(102.0 / adj[D1] - 1, 0.03)
        self.assertAlmostEqual(102.0 / a[D1] - 1, 102.0 / 101.0 - 1)
        # on and after the ex-date the adjustment is already in: the series keeps it
        a3, _ = md.asof_series(adj, raw, D3)
        self.assertAlmostEqual(a3[D2], 102.0 * k)
        self.assertEqual(md.asof_series({}, {}, D2), ({}, {}))


# ------------------------------------------------------------------ M7 daily()
class M7Daily(NoNetwork):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        self.book, self.ledger = os.path.join(d, "out", "dry-book.json"), os.path.join(d, "out", "dry-ledger.jsonl")
        self.snaps, self.shadow = os.path.join(d, "monitor"), os.path.join(d, "shadow.jsonl")
        os.makedirs(self.snaps)
        self.bars = {("AAA", x): {"15:54": p - 0.5, "15:55": p - 0.4} for x, p in zip(CAL, (100.0, 100.0, 110.0, 121.0, 121.0))}
        self.bars.update({("BBB", x): {"15:54": 50.0, "15:55": 50.0} for x in CAL})
        self.plan = {x: {"HG": {"AAA": 1.0}, "HARV": {"BBB": 1.0}} for x in CAL}
        self.divs, self.boom = {}, None

    def build(self, now, quotes=None, fetch=None):
        if self.boom:
            raise self.boom
        return payload(**self.plan[sr.et_now(now).date().isoformat()])

    def day(self, d, **kw):
        kw.setdefault("minutes", FakeMinutes(self.bars))
        kw.setdefault("market", market(divs=self.divs))
        return md.daily(d, self.book, self.ledger, kw.pop("force", False), build=self.build, snapshot_dir=self.snaps,
                        shadow_path=self.shadow, capital=100_000.0, fractions={"HG": 0.5, "HARV": 0.5}, slip_bps=0.0, **kw)

    def composer(self, d, hhmm_utc="21:35", hg=None, harv=None, dav=(1000.0, 2000.0)):
        s = snap(f"{d}T{hhmm_utc}:00+00:00", HG=(dav[0], 50_000.0, hg or {"AAA": 0.999}), HARV=(dav[1], 50_000.0, harv or {"BBB": 0.999}))
        with open(os.path.join(self.snaps, f"snapshot-{d.replace('-', '')}T{hhmm_utc.replace(':', '')}00Z.json"), "w") as f:
            json.dump(s, f)

    def shadow_rows(self, *rows):
        with open(self.shadow, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def rows(self):
        return md.read_dry_ledger(self.ledger)

    def test_first_use_seeds_and_writes_one_row_per_engine_plus_the_book(self):
        self.assertFalse(os.path.exists(self.book))
        lines, alerts = self.day(D1)
        self.assertEqual(alerts, [])
        self.assertTrue(1 <= len(lines) <= 3)
        self.assertIn("MIRROR DRY 2026-03-02 (decided 15:55 ET)", lines[0])
        self.assertIn("no snapshot", lines[-1])
        rows = self.rows()
        self.assertEqual([r["engine"] for r in rows], ["HG", "HARV", "BOOK"])
        hg, book = rows[0], rows[2]
        self.assertEqual((hg["action"], hg["decide"], hg["mode"], hg["label"]), ("trade", "15:55", "minute", "firm"))
        self.assertEqual(hg["parity"], "no Composer snapshot")
        saved = json.loads(read(self.book))
        self.assertEqual((saved["session"], saved["seeded_on"], saved["capital"]), (D1, D1, 100_000.0))
        # sized on the 15:54 price (99.5), filled at the 15:55 bar's close (99.6), valued at the close (100.0)
        q = math.floor(50_000 * 0.997 / 99.5)
        self.assertEqual(q, 501)
        self.assertEqual(saved["book"]["sleeves"][0]["shares"], {"AAA": q})
        self.assertAlmostEqual(hg["equity"], round(50_000 - q * 99.6 - md.commission(q, 99.6) + q * 100.0, 2), places=2)
        self.assertEqual(book["overspent"], {})
        self.assertEqual(book["orders"], 2)
        self.assertEqual(saved["before"]["session"], None)                 # the state before this session: the fresh seed
        self.assertEqual(saved["before"]["book"]["sleeves"][0]["shares"], {})

    def test_idempotent_and_the_next_day_continues_the_same_book(self):
        self.day(D1)
        book1, led1 = read(self.book), read(self.ledger)
        lines, alerts = self.day(D1)
        self.assertEqual(alerts, [])
        self.assertIn("already in the ledger", lines[0])
        self.assertEqual((read(self.book), read(self.ledger)), (book1, led1))
        lines, alerts = self.day(D2)                                       # twin: a new date does run
        self.assertEqual(alerts, [])
        rows = self.rows()
        self.assertEqual([r["date"] for r in rows], [D1] * 3 + [D2] * 3)
        hg1, hg2 = rows[0], rows[3]
        self.assertEqual(hg2["action"], "hold")
        self.assertAlmostEqual(hg2["equity_prev"], hg1["equity"], places=2)
        self.assertAlmostEqual(hg2["ret"], hg2["equity"] / hg1["equity"] - 1, places=6)   # AAA 100 -> 110
        self.assertGreater(hg2["ret"], 0.099)
        self.assertEqual(json.loads(read(self.book))["seeded_on"], D1)
        # an older date than the book's is refused with an alert, and changes nothing
        book2 = read(self.book)
        os.remove(self.ledger)
        lines, alerts = self.day(D1)
        self.assertEqual(len(alerts), 1)
        self.assertIn("before the book's last session", alerts[0])
        self.assertEqual(read(self.book), book2)

    def test_force_reruns_the_last_session_without_booking_twice(self):
        self.divs = {"AAA": {D2: 1.0}}
        self.day(D1)
        self.day(D2)
        first = self.rows()
        book = json.loads(read(self.book))
        lines, alerts = self.day(D2, force=True)
        self.assertEqual(alerts, [])
        again = self.rows()
        self.assertEqual(len(again), 6)                                    # replaced, not appended
        self.assertEqual(again[3]["equity"], first[3]["equity"])
        self.assertEqual(again[3]["div"], first[3]["div"])                 # the distribution was paid once
        self.assertGreater(again[3]["div"], 0)
        self.assertEqual(json.loads(read(self.book))["book"], book["book"])
        # twin: without the saved before-state a re-run WOULD double book: the trade is already done
        self.assertNotEqual(book["before"]["book"], book["book"])
        # a run that died after the book was written and before the ledger heals itself the same way
        with open(self.ledger, "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in first[:3]))
        lines, alerts = self.day(D2)
        self.assertEqual(alerts, [])
        self.assertEqual(self.rows()[3]["equity"], first[3]["equity"])
        self.assertEqual(json.loads(read(self.book))["book"], book["book"])

    def test_atomic_a_crash_while_writing_leaves_the_old_files(self):
        self.day(D1)
        book1, led1 = read(self.book), read(self.ledger)
        with unittest.mock.patch("mirror_dry.os.replace", side_effect=OSError("disk full")):
            lines, alerts = self.day(D2)
        self.assertEqual(len(alerts), 1)
        self.assertIn("MIRROR DRY FAILED", alerts[0])
        self.assertIn("disk full", alerts[0])
        self.assertEqual((read(self.book), read(self.ledger)), (book1, led1))
        self.assertEqual(sorted(os.listdir(os.path.dirname(self.book))), ["dry-book.json", "dry-ledger.jsonl"])   # no temp left
        lines, alerts = self.day(D2)                                       # twin: the disk is back, the day runs
        self.assertEqual(alerts, [])
        self.assertEqual(len(self.rows()), 6)

    def test_never_raises(self):
        self.day(D1)
        book1 = read(self.book)
        for boom in (RuntimeError("brain down"), SystemExit("error: HTTP 503"), ValueError("bad payload")):
            self.boom = boom
            lines, alerts = self.day(D2)
            self.assertEqual(len(alerts), 1, boom)
            self.assertIn("MIRROR DRY FAILED", alerts[0])
            self.assertTrue(lines)
        self.boom = None
        lines, alerts = self.day(D2, minutes=FakeMinutes(self.bars, refuse_on=D2))   # FMP refuses
        self.assertIn("MIRROR DRY FAILED", alerts[0])
        self.assertNotIn("k-secret", " ".join(lines + alerts))
        lines, alerts = self.day("2026-03-06", market=market())            # no close for that date
        self.assertIn("no close for 2026-03-06", alerts[0])
        lines, alerts = self.day("not-a-date")
        self.assertIn("MIRROR DRY FAILED", alerts[0])
        self.assertEqual(read(self.book), book1)                    # none of them touched the book
        with open(self.book, "w") as f:
            f.write("{not json")
        lines, alerts = self.day(D2)
        self.assertIn("MIRROR DRY FAILED", alerts[0])
        self.assertEqual(read(self.book), "{not json")              # a corrupt book is never overwritten by a reseed
        # the twin: with nothing broken the same call succeeds
        with open(self.book, "w") as f:
            f.write(book1)
        self.assertEqual(self.day(D2)[1], [])

    def test_mismatch_only_when_the_shadow_ledger_does_not_explain_it(self):
        self.day(D1)
        # D2: Composer's HG went to BBB; the mirror (and the brain) stayed in AAA
        self.composer(D1)
        self.composer(D2, hg={"BBB": 0.999}, dav=(1100.0, 2001.0))
        self.shadow_rows(led(D2, "HG", {"AAA": 1.0}, live={"BBB": 1.0}, status="agree"), led(D2, "HARV", {"BBB": 1.0}))
        lines, alerts = self.day(D2)
        self.assertEqual(len(alerts), 1)
        self.assertIn("MIRROR MISMATCH — HG on 2026-03-03", alerts[0])
        self.assertIn("Composer holds BBB 100%", alerts[0])
        self.assertIn("1 of 2 engines hold the same", lines[-1])
        hg, harv = self.rows()[3], self.rows()[4]
        self.assertEqual((hg["parity"], harv["parity"]), ("MISMATCH", "same"))
        self.assertAlmostEqual(hg["composer_ret"], 0.10)                   # deposit-adjusted value 1000 -> 1100
        self.assertEqual(hg["composer_ret_basis"], "dav")
        self.assertAlmostEqual(hg["diff_bps"], (hg["ret_px"] - 0.10) * 1e4, places=1)
        # twin 1: the ledger calls it a knife-edge -> explained, no alert
        with open(self.shadow, "w") as f:
            f.write("")
        self.shadow_rows(led(D2, "HG", {"AAA": 1.0}, live={"BBB": 1.0}, status="knife-edge"), led(D2, "HARV", {"BBB": 1.0}))
        lines, alerts = self.day(D2, force=True)
        self.assertEqual(alerts, [])
        self.assertEqual(self.rows()[3]["parity"], "explained (knife-edge)")
        # twin 2: a Composer no-rebalance day -> explained
        with open(self.shadow, "w") as f:
            f.write("")
        self.shadow_rows(led(D2, "HG", {"AAA": 1.0}, live={"BBB": 1.0}, status="no-rebalance"))
        self.assertEqual(self.day(D2, force=True)[1], [])
        # twin 3: no shadow row at all -> nothing explains it -> alert
        with open(self.shadow, "w") as f:
            f.write("")
        lines, alerts = self.day(D2, force=True)
        self.assertEqual(len(alerts), 1)
        self.assertIn("nothing for this session", alerts[0])
        # twin 4: Composer holds what the mirror holds -> same, no alert, whatever the ledger says
        for f in os.listdir(self.snaps):
            os.remove(os.path.join(self.snaps, f))
        self.composer(D2)
        lines, alerts = self.day(D2, force=True)
        self.assertEqual(alerts, [])
        self.assertIn("2 of 2 engines hold the same", lines[-1])
        self.assertEqual(self.rows()[3]["composer_ret_basis"], "lpc")      # no D1 snapshot left: Composer's own day change

    def test_an_engine_without_a_decision_alerts_and_stands_still(self):
        self.day(D1)
        self.plan[D2] = {"HG": None, "HARV": {"BBB": 1.0}}
        lines, alerts = self.day(D2)
        self.assertEqual(len(alerts), 1)
        self.assertIn("MIRROR DRY NO DECISION", alerts[0])
        self.assertIn("HG", alerts[0])
        self.assertEqual(self.rows()[3]["action"], "skip")
        self.assertEqual(self.rows()[3]["weights"].keys(), {"AAA"})

    def test_half_day_decides_five_minutes_before_its_own_close(self):
        cal = ["2026-11-25", "2026-11-27"]
        mkt = md.Market(raw={"AAA": {d: 100.0 for d in cal}, "BBB": {d: 50.0 for d in cal}, "SPY": {d: 500.0 for d in cal}}, calendar=cal)
        bars = {("AAA", "2026-11-27"): {"12:54": 99.5, "12:55": 99.6, "15:54": 90.0, "15:55": 90.0}, ("BBB", "2026-11-27"): {"12:54": 50.0, "12:55": 50.0}}
        self.plan["2026-11-27"] = self.plan[D1]
        lines, alerts = self.day("2026-11-27", market=mkt, minutes=FakeMinutes(bars))
        self.assertEqual(alerts, [])
        self.assertIn("decided 12:55 ET", lines[0])
        order = self.rows()[2]["order_list"][0]
        self.assertEqual((order["symbol"], order["px"]), ("AAA", 99.6))     # the 12:55 bar, not the 15:55 one


# ------------------------------------------------------------------ M8 the FMP store
class M8MinuteStore(NoNetwork):
    def test_one_request_per_ticker_day_memory_then_disk(self):
        with tempfile.TemporaryDirectory() as d:
            a = FakeMinutes({("AAA", D1): {"15:54": 99.0, "_close": "16:00"}}, cache_dir=d)
            self.assertEqual(a.get("AAA", D1), {"15:54": 99.0})
            self.assertEqual(a.get("AAA", D1), {"15:54": 99.0})
            self.assertEqual((a.calls, a.requests), ([("AAA", D1)], 1))
            b = FakeMinutes({}, cache_dir=d)                               # a rerun: from disk, no request
            self.assertEqual(b.get("AAA", D1), {"15:54": 99.0})
            self.assertEqual(b.calls, [])
            self.assertEqual(b.get("ZZZ", D1), {})                         # twin: not cached -> asked
            self.assertEqual(b.calls, [("ZZZ", D1)])

    def test_todays_unfinished_session_is_not_written_to_disk(self):
        with tempfile.TemporaryDirectory() as d:
            now = datetime.datetime(2026, 3, 3, 20, 0, tzinfo=UTC)          # 15:00 ET on D2
            m = FakeMinutes({("AAA", D2): {"14:59": 1.0}, ("AAA", D1): {"15:59": 1.0}}, cache_dir=d, now=lambda: now)
            m.get("AAA", D2)
            m.get("AAA", D1)
            self.assertFalse(os.path.exists(os.path.join(d, "fmp", D2, "AAA.json")))
            self.assertTrue(os.path.exists(os.path.join(d, "fmp", D1, "AAA.json")))     # twin: a finished day is

    def test_throttle_spaces_the_requests(self):
        clock, slept = [0.0], []

        def sleep(s):
            slept.append(s)
            clock[0] += s
        m = md.Minutes(key="k", fetch=lambda t, d, k: {}, rate=4.0, clock=lambda: clock[0], sleep=sleep)
        for i in range(5):
            m.get(f"T{i}", D1)
        self.assertEqual(len(slept), 4)                                    # every request after the first waits
        self.assertAlmostEqual(sum(slept), 1.0, places=6)                  # five requests take a second: 4 a second
        m.get("T0", D1)
        self.assertEqual(len(slept), 4)                                    # twin: a cached answer does not wait

    def test_refusal_is_remembered_and_the_key_never_appears(self):
        def fetch(t, d, k):
            raise RuntimeError(f"FMP {t} {d}: HTTP Error 429: Too Many Requests for apikey={k}")
        m = md.Minutes(key="SECRET123", fetch=fetch, rate=1e9, sleep=lambda s: None)
        with self.assertRaises(md.Refused) as cm:
            m.get("AAA", D1)
        self.assertNotIn("SECRET123", str(cm.exception))
        self.assertNotIn("SECRET123", m.refused)
        with self.assertRaises(md.Refused):
            m.get("BBB", D1)                                               # no further request after a refusal
        self.assertEqual(m.requests, 1)
        # twin: a timeout is an error for that ticker, not a refusal of the feed
        n = md.Minutes(key="SECRET123", fetch=unittest.mock.Mock(side_effect=TimeoutError("timed out")), rate=1e9, sleep=lambda s: None)
        with self.assertRaises(RuntimeError) as cm:
            n.get("AAA", D1)
        self.assertNotIsInstance(cm.exception, md.Refused)
        self.assertIsNone(n.refused)
        self.assertIn(("AAA", D1), n.errors)
        with self.assertRaises(md.Refused):
            md.Minutes(key="").get("AAA", D1)                              # no key: nothing is asked


# ------------------------------------------------------------------ M9 the real brain through the seams
class M9RealBrain(unittest.TestCase):
    """mirror_brain.build on the frozen 2026-10-28 closes, reached through Yahoo.live and Minutes.quotes"""

    @classmethod
    def setUpClass(cls):
        import gzip
        with gzip.open(os.path.join(HERE, "fixtures", "shadow-2026-10-28.json.gz")) as f:
            cls.fx = json.load(f)

    def chart(self, t, paid_after=None):
        """Yahoo's wire format for the fixture's series (fetched 'today': the last trade is after the replay).
        paid_after: (ex-date index from the end, amount) - a distribution Yahoo has since applied to its history"""
        s = self.fx["prices"].get(t)
        if s is None:
            raise RuntimeError("no such ticker")
        days = sorted(s)
        ts = [int(datetime.datetime.fromisoformat(d + "T14:30:00+00:00").timestamp()) for d in days]
        close = [s[d] for d in days]
        adj = list(close)
        return {"meta": {"regularMarketTime": int(datetime.datetime(2026, 11, 9, 21, 0, tzinfo=UTC).timestamp())},
                "timestamp": ts, "indicators": {"quote": [{"close": close}], "adjclose": [{"adjclose": adj}]}, "events": {}}

    def brain(self, scale=None):
        import preclose as pc
        fam = set(self.fx["prices"])
        bars = {(t, "2026-10-28"): {"15:53": s["2026-10-28"]} for t, s in self.fx["prices"].items() if "2026-10-28" in s}

        def fetch(t):
            res = self.chart(t)
            if scale and t in scale:                                       # history lowered by a later distribution
                a = res["indicators"]["adjclose"][0]["adjclose"]
                res["indicators"]["adjclose"][0]["adjclose"] = [x * scale[t] for x in a]
            return res
        y = md.Yahoo(fetch=fetch)
        mn = FakeMinutes(bars)
        self.assertTrue(fam)
        return md.brain_payload("2026-10-28", "15:54", y, mn), pc

    def test_targets_through_the_seams_match_the_approved_logic(self):
        p, pc = self.brain()
        self.assertTrue(p["replay"])
        self.assertEqual(p["session"], "2026-10-28")
        self.assertEqual((p["quotes"] or {}).get("source"), "fmp-1m")
        for eng in ("HG", "SLEEVE", "HARV"):
            self.assertEqual(p["engines"][eng]["status"], "ok", p["engines"][eng])
            self.assertTrue(pc.same(p["engines"][eng]["target"], self.fx["expected"][eng]["2026-10-28"]), eng)
        self.assertEqual(p["engines"]["KMLM"]["rule"], "threshold")

    def test_a_distribution_paid_since_does_not_change_the_replay(self):
        base, pc = self.brain()
        # every history as Yahoo adjusts it after a later 1.5% distribution: the as-of series undoes it
        later, _ = self.brain(scale={t: 0.985 for t in self.fx["prices"]})
        for eng in base["engines"]:
            self.assertEqual(later["engines"][eng].get("target"), base["engines"][eng].get("target"), eng)
        # twin: WITHOUT the as-of rebasing the same inputs put a +1.5% day into every fund on the replayed day
        adj = {d: v * 0.985 for d, v in self.fx["prices"]["SPY"].items()}
        raw = dict(self.fx["prices"]["SPY"])
        a, _ = md.asof_series(adj, raw, "2026-10-28")
        self.assertAlmostEqual(a["2026-10-27"], raw["2026-10-27"], places=6)
        self.assertAlmostEqual(raw["2026-10-28"] / adj["2026-10-27"] / (raw["2026-10-28"] / raw["2026-10-27"]), 1 / 0.985, places=9)


if __name__ == "__main__":
    unittest.main()
