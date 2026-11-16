"""Gate tests for mirror_dry.py (the IBKR mirror's DRY simulator and parity measurement; IBKR_MIRROR.md).

No network: fake prices, minutes, distributions, snapshots and ledger rows. Each behavioural test has
a BROKEN-INPUT twin that must land on the other side (a gate that cannot fail is not a gate).

  M1  costs: IBKR tiered commission ($0.0035 a share, the $0.35 minimum, the 1%-of-value cap) and
      slippage in the fill price, in the function and in the book's cash; twin: no slippage, no cost
  M2  distributions through the core: a receivable for the shares held at the close before the
      ex-date, credited from the pay date to a sleeve that still holds the payer (rule "composer"),
      else leaked to unallocated account cash; rule "holder" always credits; conservation (accrued =
      credited + leaked + open); twins: not held, no pay date yet, a late row, the same row twice
  M3  a three-day backfill verified by hand, to the cent; twin: one changed close moves the answer
  M4  close mode: the decision IS the ledger's target and the bookings are mirror_core's own (the same
      shares as driving mirror_core directly; mc.check clean after every session); twins: no ledger row
      -> the sleeve stands still, a target that does not sum to 1 -> skipped, a tampered venue -> reported
  M5  Composer's record and the parity classes: snapshot -> session, deposit-adjusted spans, flow days;
      knife-edge / no-rebalance / corridor path / late snapshot / whole-share; return tracking; twins
  M6  minute mode: the brain's PINNED payload decides as of 15:54:00, fills at the bar that starts at
      that instant, the close when there is none (counted), sized on the brain's published prices,
      half-days shift, a refusal stops cleanly; the as-of series
  M7  daily(): seeds once, idempotent, force re-runs the last session without double booking, atomic,
      never raises, MISMATCH only when the shadow ledger does not explain it, the brain's own dividend
      rows are the ones booked
  M8  the FMP store: one request per ticker-day, disk cache, throttle, refusal remembered, key never shown
  M9  the brain through the real seams (mirror_brain.build pinned, on the frozen 2026-10-28 fixture)
  M10 limit buys: sized at the core's limit floored to the venue's tick (equal to the executor's own
      rounding); a buy fills only at or below its limit, never above it, else it is unfilled and the
      cash stays; sells are market orders; twins: without the rule the same fill overspends
  M11 splits: closes on the as-traded basis, the sleeves' shares rescaled by the core before the plan,
      cash in lieu left unallocated; twins: the split not listed, listed twice, listed late

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


def market(aaa=(100.0, 100.0, 110.0, 121.0, 121.0), bbb=50.0, divs=None, extra=None, splits=None):
    raw = {"AAA": dict(zip(CAL, aaa)), "BBB": {d: bbb for d in CAL}, "SPY": {d: 500.0 for d in CAL}}
    raw.update(extra or {})
    return md.Market(raw=raw, divs=divs or {}, calendar=CAL, splits=splits)


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
        for target in ("mirror_dry._yahoo_chart", "shadow_runner.fetch_minutes", "shadow_runner._chart",
                       "shadow_runner.fetch_actions"):
            p = unittest.mock.patch(target, boom)
            p.start()
            self.addCleanup(p.stop)


# ------------------------------------------------------------------ M1 costs
class M1Costs(NoNetwork):
    def test_commission_per_share_minimum_and_cap(self):
        self.assertAlmostEqual(md.commission(1000, 50.0), 3.50)            # 1000 x 0.0035
        self.assertAlmostEqual(md.commission(497, 100.0), 1.7395)
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
        # wanted floor(50,000 x 0.999 / 100) = 499; sized AT ITS LIMIT (100.50) from the cash less the 0.1%
        # reserve: floor(499 x 49,950 / (499 x 100.50)) = 497
        self.assertEqual(math.floor(499 * 49_950 / (499 * 100.5)), 497)
        self.assertEqual((q, order["limit"]), (497, 100.5))
        self.assertAlmostEqual(order["price"], 100.02)
        self.assertAlmostEqual(order["commission"], 1.7395)
        self.assertAlmostEqual(hg["slippage"], 497 * 0.02, places=4)
        self.assertAlmostEqual(hg["commission"], 1.7395, places=4)
        self.assertAlmostEqual(hg["equity"], 50_000 - 497 * 0.02 - 1.7395, places=2)
        self.assertAlmostEqual(hg["ret_gross"], 0.0, places=9)              # before costs nothing happened
        self.assertAlmostEqual(hg["ret_px_gross"], 0.0, places=9)
        self.assertAlmostEqual(hg["ret"], -(497 * 0.02 + 1.7395) / 50_000, places=7)
        self.assertEqual(hg["ret"], hg["ret_px"])                           # no distribution: one basis
        # twin: no slippage -> the fill is the close and only the commission is paid
        res0 = run(two_sleeves((D1,)), slip=0.0, end=D1)
        hg0 = rows_of(res0, "HG")[D1]
        self.assertEqual(hg0["slippage"], 0.0)
        self.assertAlmostEqual(hg0["equity"], 50_000 - 1.7395, places=2)
        self.assertGreater(hg0["equity"], hg["equity"])

    def test_a_sell_is_slipped_down_and_charged(self):
        sh = two_sleeves((D1, D2), hg={D2: {"BBB": 1.0}})
        res = run(sh, slip=5.0, end=D2)
        sell = next(o for o in res["book"][1]["order_list"] if o["side"] == mc.SELL)
        self.assertEqual((sell["symbol"], sell["filled"], sell["limit"]), ("AAA", 497, None))   # a market order
        self.assertAlmostEqual(sell["price"], 110.0 * (1 - 5e-4))
        self.assertAlmostEqual(sell["commission"], 1.7395)
        buy = next(o for o in res["book"][1]["order_list"] if o["side"] == mc.BUY)
        self.assertAlmostEqual(buy["price"], 50.0 * (1 + 5e-4))
        self.assertEqual(res["book"][1]["problems"], [])


# ------------------------------------------------------------------ M2 distributions
PAID = {"AAA": {D2: (1.0, D3)}}                    # AAA: ex D2, $1 a share, paid D3


class M2Distributions(NoNetwork):
    def test_a_receivable_at_the_ex_date_is_credited_from_the_pay_date(self):
        res = run(two_sleeves(), market(divs=PAID))
        hg = rows_of(res, "HG")
        # ex-date: a receivable for the 497 shares held at the D1 close; no cash yet, so no return yet
        self.assertEqual((hg[D1]["div_accrued"], hg[D2]["div_accrued"], hg[D2]["div"]), (0.0, 497.0, 0.0))
        self.assertEqual(hg[D2]["accrued_by"], {"AAA": 497.0})
        self.assertEqual(hg[D2]["receivable_open"], 497.0)
        self.assertEqual(hg[D2]["ret"], hg[D2]["ret_px"])
        # pay date: HG still holds AAA -> its cash is credited, once
        self.assertEqual((hg[D3]["div"], hg[D3]["div_by"], hg[D3]["div_leaked"]), (497.0, {"AAA": 497.0}, 0.0))
        self.assertEqual(hg[D3]["receivable_open"], 0.0)
        self.assertAlmostEqual(sum(r["div"] for r in res["rows"]), 497.0)
        self.assertEqual([b["div"] for b in res["book"]], [0.0, 0.0, 497.0])
        self.assertEqual(res["unallocated"], 0.0)
        # the price basis takes exactly the credit out of the day's return
        self.assertAlmostEqual(hg[D3]["ret"] - hg[D3]["ret_px"], 497.0 / hg[D3]["equity_prev"], places=7)
        self.assertAlmostEqual(hg[D3]["ret_px"], (hg[D3]["equity"] - 497.0) / hg[D3]["equity_prev"] - 1, places=7)
        # ... and the credit is the sleeve's own cash from then on
        base = rows_of(run(two_sleeves()), "HG")
        self.assertAlmostEqual(hg[D3]["equity"] - base[D3]["equity"], 497.0, delta=5.0)   # $497, less what buying with it cost
        self.assertEqual((hg[D2]["index"], hg[D2]["index_px"]), (base[D2]["index"], base[D2]["index_px"]))
        rec = res["receivables"]
        self.assertEqual([(r["id"], r["status"], r["settled"], r["shares"], r["total"]) for r in rec],
                         [(f"div-AAA-{D2}-HG", "credited", D3, 497, 497.0)])

    def test_the_composer_rule_leaks_what_the_sleeve_no_longer_holds_and_the_holder_rule_credits_it(self):
        sh = two_sleeves(hg={D2: {"BBB": 1.0}, D3: {"BBB": 1.0}})          # HG sells AAA on its ex-date: entitled, then gone
        res = run(sh, market(divs=PAID))
        hg = rows_of(res, "HG")
        self.assertEqual((hg[D2]["div_accrued"], hg[D3]["div"], hg[D3]["div_leaked"]), (497.0, 0.0, 497.0))
        self.assertEqual(hg[D3]["leaked_by"], {"AAA": 497.0})
        self.assertEqual((res["unallocated"], res["book"][2]["unallocated"], res["book"][2]["unallocated_change"]), (497.0, 497.0, 497.0))
        self.assertEqual(res["receivables"][0]["status"], "leaked")
        self.assertEqual(hg[D3]["ret"], hg[D3]["ret_px"])                   # nothing reached the sleeve
        self.assertEqual(res["book"][2]["problems"], [])                   # and the book's cash still reconciles
        # twin: rule "holder" credits whoever held the shares at the ex-date, whatever it holds now
        held = run(sh, market(divs=PAID), rule="holder")
        h2 = rows_of(held, "HG")
        self.assertEqual((h2[D3]["div"], h2[D3]["div_leaked"], held["unallocated"]), (497.0, 0.0, 0.0))
        self.assertAlmostEqual(h2[D3]["equity"] - hg[D3]["equity"], 497.0, delta=5.0)
        self.assertEqual(held["receivables"][0]["status"], "credited")
        with self.assertRaises(ValueError):
            run(sh, market(divs=PAID), rule="everyone")

    def test_twins_not_held_no_distribution_and_not_yet_paid(self):
        # BBB pays, but HG holds AAA: nothing for HG; HARV (994 BBB) is owed and paid
        res = run(two_sleeves(), market(divs={"BBB": {D2: (0.25, D3)}}))
        self.assertEqual(rows_of(res, "HG")[D2]["div_accrued"], 0.0)
        self.assertAlmostEqual(rows_of(res, "HARV")[D2]["div_accrued"], 994 * 0.25)
        self.assertAlmostEqual(rows_of(res, "HARV")[D3]["div"], 994 * 0.25)
        # no distribution anywhere: both bases are the same number every day
        for r in run(two_sleeves())["rows"]:
            self.assertEqual((r["div"], r["div_accrued"], r["div_leaked"]), (0.0, 0.0, 0.0))
            self.assertEqual(r["ret"], r["ret_px"])
        # an ex-date before the sleeve held the payer (D1: bought at that day's close) owes nothing
        res = run(two_sleeves(), market(divs={"AAA": {D1: (1.0, D2)}}))
        self.assertEqual((sum(r["div_accrued"] for r in res["rows"]), res["receivables"]), (0.0, []))
        # no pay date listed: the core never guesses one this early -> still a receivable when the window ends
        res = run(two_sleeves(), market(divs={"AAA": {D2: 1.0}}))
        hg = rows_of(res, "HG")
        self.assertEqual((hg[D3]["div"], hg[D3]["receivable_open"]), (0.0, 497.0))
        self.assertEqual((res["receivables"][0]["status"], res["receivables"][0]["pay_date"]), ("open", None))
        self.assertEqual(res["parity"]["book"]["distributions"]["open_usd"], 497.0)

    def test_an_unknown_pay_date_waits_for_a_later_listing_or_for_the_cores_give_up_day(self):
        t = {"HG": {"status": "ok", "target": {"AAA": 1.0}}}
        px = {"AAA": 100.0}
        row = {"ticker": "AAA", "ex_date": D2, "pay_date": None, "amount": 1.0}
        ex = datetime.date.fromisoformat(D2)
        day = lambda n: (ex + datetime.timedelta(days=n)).isoformat()   # noqa: E731

        def book_at_the_ex_date():
            sim = md.Sim(md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5}), 0.0)
            sim.session(D1, t, px, px, px)
            _, b = sim.session(D2, t, px, px, px, [row])
            self.assertEqual((b["div_accrued"], b["div"], sim.receivables[0]["pay_date"]), (497.0, 0.0, None))
            return sim
        # (1) the same dividend listed again WITH its pay date: due from that date, not before
        sim = book_at_the_ex_date()
        _, b = sim.session(D3, t, px, px, px, [dict(row, pay_date=D4)])
        self.assertEqual((b["div"], sim.receivables[0]["pay_date"], sim.receivables[0]["status"]), (0.0, D4, "open"))
        _, b = sim.session(D4, t, px, px, px, [dict(row, pay_date=day(30))])   # a known date is not moved by a later listing
        self.assertEqual((b["div"], sim.receivables[0]["status"], len(sim.receivables)), (497.0, "credited", 1))
        self.assertEqual(sim.receivables[0]["pay_date"], D4)
        # (2) never listed with one: nothing until the core's give-up day, then its assumed date applies
        sim = book_at_the_ex_date()
        n = mc.PAY_DATE_GIVE_UP_DAYS
        _, b = sim.session(day(n - 1), t, px, px, px, [row])
        self.assertEqual((b["div"], b["receivable_open"]), (0.0, 497.0))
        self.assertIsNone(mc.receivable_pay_date(sim.receivables[0], day(n - 1)))
        _, b = sim.session(day(n), t, px, px, px)
        self.assertEqual((b["div"], b["receivable_open"], sim.receivables[0]["status"]), (497.0, 0.0, "credited"))
        self.assertEqual((sim.receivables[0]["pay_date"], sim.receivables[0]["pay_date_assumed"]), (day(mc.DEFAULT_PAY_LAG_DAYS), True))
        # twin: a listed pay date is honoured as it is, however far out (no give-up applies to it)
        sim = md.Sim(md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5}), 0.0)
        sim.session(D1, t, px, px, px)
        sim.session(D2, t, px, px, px, [dict(row, pay_date=day(30))])
        _, b = sim.session(day(n), t, px, px, px)
        self.assertEqual((b["div"], b["receivable_open"]), (0.0, 497.0))

    def test_the_rows_are_the_brains_shape_and_window(self):
        sat = "2026-03-01"                                                 # no session that day: it is in D1's rows
        m = market(divs={"AAA": {sat: (1.0, D2), D2: 0.5, "2026-02-10": 0.7}})
        rows, splits = m.actions(D1)
        self.assertEqual(rows, [{"ticker": "AAA", "ex_date": sat, "pay_date": D2, "amount": 1.0}])   # D2's is not due yet
        self.assertEqual(splits, [])
        self.assertEqual([x["ex_date"] for x in m.actions(D2)[0]], [sat, D2])     # ... and nothing older than 10 days
        self.assertEqual(m.actions(D2)[0][1]["pay_date"], None)
        self.assertEqual(m.actions("2026-03-20")[0], [])                   # twin: outside the window

    def test_a_row_seen_twice_is_booked_once_and_a_late_row_reads_the_holdings_of_its_day(self):
        both = {"HG": {"status": "ok", "target": {"AAA": 1.0}}, "HARV": {"status": "ok", "target": {"BBB": 1.0}}}
        swap = {"HG": {"status": "ok", "target": {"AAA": 1.0}}, "HARV": {"status": "ok", "target": {"AAA": 1.0}}}
        row = {"ticker": "AAA", "ex_date": D2, "pay_date": D3, "amount": 1.0}
        m = market()
        sim = md.Sim(md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5}), 0.0)
        sim.session(D1, both, m.closes(D1), m.closes(D1), m.closes(D1))
        sim.session(D2, swap, m.closes(D2), m.closes(D2), m.closes(D2))    # the ex-date passes with no row; HARV buys AAA at its close
        self.assertGreater(sim.book.sleeves["HARV"].shares["AAA"], 400)
        er, b = sim.session(D3, swap, m.closes(D3), m.closes(D3), m.closes(D3), [row, dict(row)])   # it surfaces late, twice
        self.assertEqual([(r["sleeve"], r["shares"]) for r in sim.receivables], [("HG", 497)])   # the D1 close's holder alone
        self.assertEqual((er[0]["div"], er[1]["div"], b["div"]), (497.0, 0.0, 497.0))
        self.assertEqual(b["problems"], [])
        _, b = sim.session(D4, swap, m.closes(D4), m.closes(D4), m.closes(D4), [row])       # and again the next session
        self.assertEqual((b["div"], b["div_accrued"], len(sim.receivables)), (0.0, 0.0, 1))
        # twin: published on its ex-date it reads the sleeves as they stand before that session's plan - the same answer
        sim2 = md.Sim(md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5}), 0.0)
        sim2.session(D1, both, m.closes(D1), m.closes(D1), m.closes(D1))
        sim2.session(D2, swap, m.closes(D2), m.closes(D2), m.closes(D2), [row])
        self.assertEqual([(r["sleeve"], r["shares"]) for r in sim2.receivables], [("HG", 497)])
        # twin: an unusable row is ignored, never guessed at
        sim2.session(D3, swap, m.closes(D3), m.closes(D3), m.closes(D3), [{"ticker": "AAA", "ex_date": D3, "amount": -1.0}, "junk", None])
        self.assertEqual(len(sim2.receivables), 1)

    def test_the_bookings_are_the_cores_own_calls(self):
        sh = two_sleeves(hg={D3: {"BBB": 1.0}})
        mkt = market(divs=PAID)
        res = run(sh, mkt)
        book, open_recs, leaked = mc.Book.seed(100_000.0, {"HG": 0.5, "HARV": 0.5}, md.rules_from_manifest()), [], 0.0
        for d in (D1, D2, D3):
            px = mkt.closes(d)
            for row in mkt.actions(d)[0]:
                if row["ex_date"] == d:
                    open_recs += mc.dividend_receivables({n: dict(s.shares) for n, s in book.sleeves.items()}, row)
            for r in list(open_recs):
                out = mc.settle_receivable(book, r, d, "composer")
                if out["action"] != "not_due":
                    open_recs.remove(r)
                    leaked += r["total"] if out["action"] == "leaked" else 0.0
            t = {e: {"status": "ok", "target": sh[(d, e)]["target"], "version": "v1"} for e in ("HG", "HARV")}
            plan = mc.build_plan(book, t, px, d)
            mc.apply_crosses(book, plan)
            for o in plan["sells"]:
                mc.book_fill(book, o, o["qty"], o["ref"], md.commission(o["qty"], o["ref"]))
            mc.apply_transfers(book, plan)
            limits = {sym: md.tick_floor(mc.buy_limit(px[sym])) for asks in plan["buy_asks"].values() for sym in asks}
            for o in mc.size_buys(book, plan, limits=limits):
                mc.book_fill(book, o, o["qty"], o["ref"], md.commission(o["qty"], o["ref"]))
            mc.finish(book, plan)
        self.assertEqual(res["book_final"], book.to_dict())
        self.assertEqual((open_recs, leaked, res["unallocated"]), ([], 0.0, 0.0))


# ------------------------------------------------------------------ M3 three days by hand
class M3ThreeDaysByHand(NoNetwork):
    """HG $50,000: AAA 100 -> 110 (ex $1 a share, paid the next session) -> 121, then into BBB at 50. No
    slippage, so every number below is integer shares x round prices and the tiered commission. The
    core's defaults: 0.1% cash reserve, buys sized at a limit 0.5% above the reference."""

    def test_to_the_cent(self):
        sh = two_sleeves(hg={D3: {"BBB": 1.0}})
        res = run(sh, market(divs=PAID))
        hg, harv = rows_of(res, "HG"), rows_of(res, "HARV")
        # D1: wanted floor(50,000 x 0.999 / 100) = 499; at the 100.50 limit the cash less its reserve buys
        # floor(499 x 49,950 / 50,149.50) = 497 AAA at 100; commission 497 x 0.0035 = 1.7395
        cash1 = 50_000 - 497 * 100 - 1.7395
        e1 = cash1 + 497 * 100
        self.assertEqual((hg[D1]["action"], hg[D1]["target"]), ("trade", {"AAA": 1.0}))
        self.assertAlmostEqual(hg[D1]["equity"], round(e1, 2), places=2)
        self.assertAlmostEqual(hg[D1]["ret"], -1.7395 / 50_000, places=7)
        # D2: AAA 110, ex $1: a $497 receivable, no cash. Wanted floor(54,968.2605 x 0.999 / 110) = 499: the 2
        # missing shares ($220) are under the dust floor (0.5% of the sleeve, $274.84): no trade
        e2 = cash1 + 497 * 110
        self.assertEqual(math.floor(e2 * 0.999 / 110), 499)
        self.assertLess(2 * 110, 0.005 * e2)
        self.assertEqual((hg[D2]["action"], hg[D2]["reason"]), ("hold", "at target"))
        self.assertAlmostEqual(hg[D2]["equity"], round(e2, 2), places=2)
        self.assertEqual((hg[D2]["div"], hg[D2]["div_accrued"], hg[D2]["commission"]), (0.0, 497.0, 0.0))
        self.assertAlmostEqual(hg[D2]["ret"], e2 / e1 - 1, places=7)
        # D3: the $497 is credited BEFORE the plan (HG still holds AAA). Then sell 497 AAA at 121 (1.7395);
        # wanted floor(60,932.2605 x 0.999 / 50) = 1217 BBB; at the 50.25 limit the cash less the reserve
        # buys floor(1217 x (60,930.521 x 0.999) / (1217 x 50.25)) = 1211 (commission 4.2385)
        cash3 = cash1 + 497.0 + 497 * 121 - 1.7395
        self.assertEqual(math.floor((cash1 + 497.0 + 497 * 121) * 0.999 / 50), 1217)
        self.assertEqual(math.floor(1217 * (cash3 * 0.999) / (1217 * 50.25)), 1211)
        cash3 -= 1211 * 50 + 1211 * 0.0035
        e3 = cash3 + 1211 * 50
        self.assertAlmostEqual(hg[D3]["equity"], round(e3, 2), places=2)
        self.assertAlmostEqual(hg[D3]["div"], 497.0)
        self.assertAlmostEqual(hg[D3]["ret"], e3 / e2 - 1, places=7)
        self.assertAlmostEqual(hg[D3]["ret_px"], (e3 - 497.0) / e2 - 1, places=7)
        self.assertAlmostEqual(hg[D3]["commission"], 1.7395 + 4.2385, places=4)
        self.assertEqual(hg[D3]["weights"], {"BBB": round(1211 * 50 / e3, 6)})
        self.assertEqual(res["book_final"]["sleeves"][0]["shares"], {"BBB": 1211})
        # the booked index is e3 / 50,000; the price-basis one leaves the credit out of D3's return
        self.assertAlmostEqual(hg[D3]["index"], e3 / 50_000, places=7)
        self.assertAlmostEqual(hg[D3]["index_px"], (e2 / 50_000) * ((e3 - 497.0) / e2), places=7)
        self.assertAlmostEqual(hg[D3]["index_gross"], (e3 + 1.7395 + 4.2385) / e1, places=7)   # each day before its own costs
        # HARV: wanted 999 BBB, 994 at the 50.25 limit (commission 3.479), then flat
        self.assertAlmostEqual(harv[D3]["equity"], round(50_000 - 994 * 0.0035, 2), places=2)
        self.assertEqual((harv[D2]["action"], harv[D3]["action"]), ("hold", "hold"))
        # the book: equity is the two sleeves; venue orders D1 2, D2 0, D3 2; nothing crossed, nothing unfilled
        self.assertAlmostEqual(res["book"][2]["equity"], round(e3 + 50_000 - 994 * 0.0035, 2), places=2)
        self.assertEqual([b["orders"] for b in res["book"]], [2, 0, 2])
        self.assertEqual([b["crosses"] for b in res["book"]], [0, 0, 0])
        self.assertEqual([b["buys_unfilled"] for b in res["book"]], [0, 0, 0])
        self.assertEqual([b["problems"] for b in res["book"]], [[], [], []])
        self.assertEqual([b["overspent"] for b in res["book"]], [{}, {}, {}])

    def test_twin_one_changed_close_moves_the_answer(self):
        sh = two_sleeves(hg={D3: {"BBB": 1.0}})
        a = rows_of(run(sh, market(divs=PAID)), "HG")[D3]["equity"]
        b = rows_of(run(sh, market(aaa=(100.0, 100.0, 110.0, 120.0, 120.0), divs=PAID)), "HG")[D3]["equity"]
        self.assertAlmostEqual(a - b, 497 * 1.0, delta=1.0)                # 497 shares x the $1 lower exit

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
            limits = {sym: md.tick_floor(mc.buy_limit(px[sym])) for asks in plan["buy_asks"].values() for sym in asks}
            for o in mc.size_buys(book, plan, limits=limits):
                self.assertEqual(o["limit"], limits[o["symbol"]])
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
        divs = {"AAA": {days[5]: (0.4, days[7]), days[12]: (0.4, days[13])}, "CCC": {days[9]: 1.1},   # CCC: no pay date listed
                "BBB": {days[3]: (0.2, days[4]), days[15]: (0.2, days[18])}, "DDD": {days[8]: (0.9, days[9])}}
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
        self.assertTrue(all(b["overspent"] == {} for b in res["book"]))    # nor does any sleeve: buys are sized at their limit
        self.assertGreater(sum(b["crosses"] for b in res["book"]), 0)      # four sleeves, four funds: legs do cross
        self.assertAlmostEqual(sum(r["div"] for r in res["rows"]), sum(b["div"] for b in res["book"]), places=1)
        # distributions are conserved: everything accrued was credited, leaked, or is still owed
        acc, cred, leak = (sum(r[k] for r in res["rows"]) for k in ("div_accrued", "div", "div_leaked"))
        owed = sum(r["total"] for r in res["receivables"] if r["status"] == "open")
        self.assertGreater(acc, 0)
        self.assertGreater(cred, 0)
        self.assertAlmostEqual(acc, cred + leak + owed, places=1)
        self.assertAlmostEqual(res["unallocated"], leak, places=1)
        self.assertEqual({r["status"] for r in res["receivables"]} - {"open", "credited", "leaked"}, set())
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
        self.assertEqual((book.positions(), b["problems"], b["orders"]), ({"AAA": 497}, [], 1))


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
        # twin: Composer on the target everywhere -> every engine-day agrees (the idle cash is inside 3%)
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

    def test_a_flip_at_the_mirrors_own_decision_minute_has_its_own_class(self):
        tgt_close, tgt_1555 = {"AAA": 1.0}, {"BBB": 1.0}
        lg = led(D2, "HG", tgt_close)                                      # Composer holds what the close says
        row = {"weights": {"BBB": 0.997}, "action": "trade", "target": tgt_1555, "mode": "minute", "decide": "15:55", "label": "close call"}
        ok, _, cls, note = md.classify_day(row, lg, None, None, False, None)
        self.assertEqual((ok, cls), (False, "decision-minute"))
        self.assertIn("at 15:55 the logic said BBB 100% (close call)", note)
        # twins: in close mode the row's target IS the ledger's, so the class cannot arise; and the
        # ledger's own knife-edge still wins when it names one
        self.assertEqual(md.classify_day(dict(row, mode="close"), lg, None, None, False, None)[2], "other")
        self.assertEqual(md.classify_day(row, dict(lg, status="knife-edge"), None, None, False, None)[2], "knife-edge")

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
        # Composer earned exactly the mirror's booked return -> zero difference; then 40 bps more on D3
        comp = {"HG": {d: {"dav": 1000.0 * hg[d]["index"], "value": hg[d]["equity"], "holdings": {"AAA": 1.0}, "kind": "close",
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
    return {"schema": 2, "pinned": True, "asof_et": "15:54:00", "replay": True, "problems": [], "quotes": {"source": "fmp-1m"},
            "engines": {e: ({"status": "ok", "target": t, "version": "v9", "label": "firm", "rule": "daily"} if t else
                            {"status": "unavailable", "note": "no prices for XYZ"}) for e, t in targets.items()}}


class M6MinuteMode(NoNetwork):
    def setUp(self):
        super().setUp()
        # a bar is keyed by the minute it STARTS: "15:53" ends at 15:54:00, the decision instant
        self.bars = {("AAA", D2): {"15:52": 108.0, "15:53": 109.0, "15:54": 109.5, "15:59": 110.0},
                     ("BBB", D2): {"15:30": 50.0},                         # thin: nothing at 15:53 or 15:54
                     ("AAA", D3): {"15:53": 120.0, "15:54": 120.5}, ("BBB", D3): {"15:53": 50.0, "15:54": 50.1}}
        self.asked, self.pinned = [], []

    def build(self, plan):
        def fake(now, quotes=None, fetch=None, pinned=False):
            e = sr.et_now(now)
            self.asked.append((e.date().isoformat(), e.strftime("%H:%M:%S")))
            self.pinned.append(pinned)
            return payload(**plan[e.date().isoformat()])
        return fake

    def test_decides_from_the_brain_and_fills_at_the_decision_minutes_bar(self):
        sh = two_sleeves((D1,))                                            # close mode warms the book on D1
        plan = {D2: {"HG": {"BBB": 1.0}, "HARV": {"AAA": 1.0}}, D3: {"HG": {"BBB": 1.0}, "HARV": {"AAA": 1.0}}}
        res = md.backfill(D1, D3, "minute", minute_start=D2, shadow=sh, market=market(), minutes=FakeMinutes(self.bars),
                          build=self.build(plan), composer={}, slip_bps=0.0, capital=100_000.0, fractions={"HG": 0.5, "HARV": 0.5})
        self.assertEqual(self.asked, [(D2, "15:54:00"), (D3, "15:54:00")])  # the warm-up day never asks the brain
        self.assertEqual(self.pinned, [True, True])                        # the decision AS OF that instant, never an ad hoc read
        self.assertEqual(md.DECIDE, sr._hm(sr._min("16:00") - sr.DECISION_MINUTE))   # the instant the brain's clock publishes
        self.assertEqual([b["mode"] for b in res["book"]], ["close", "minute", "minute"])
        o = {x["symbol"] + x["side"]: x for x in res["book"][1]["order_list"]}
        # the sleeves swap: AAA and BBB cross at the REFERENCE (the bar ENDING 15:54:00, 109.0; BBB's last trade 50.0)
        self.assertEqual(res["book"][1]["crosses"], 2)
        self.assertAlmostEqual(o["AAASELL"]["ref"], 109.0)
        self.assertAlmostEqual(o["AAASELL"]["ref"], sr.minute_price(self.bars[("AAA", D2)], "15:54"))   # shadow_runner's own read
        self.assertAlmostEqual(o["AAASELL"]["px"], 109.5)                   # filled at the close of the bar that STARTS 15:54
        self.assertAlmostEqual(o["BBBBUY"]["px"], 50.0)                     # no such bar: the day's close
        self.assertEqual(res["book"][1]["fill_fallbacks"], ["BBB"])
        self.assertEqual(res["minute"]["fallbacks"], 1)
        self.assertEqual(res["minute"]["fallback_tickers"], {"BBB": 1})
        self.assertEqual((res["minute"]["covered"], res["minute"]["stopped"]), (2, None))
        hg = rows_of(res, "HG")
        self.assertEqual((hg[D2]["mode"], hg[D2]["decide"], hg[D2]["label"], hg[D2]["version"]), ("minute", "15:54", "firm", "v9"))
        self.assertEqual(hg[D2]["target"], {"BBB": 1.0})                   # the brain's, not a ledger's (there is none)
        self.assertEqual(res["book"][1]["problems"], [])
        # valued at the official close: HARV now holds AAA, marked at 110.0, not at its 109.5 fill
        harv = rows_of(res, "HARV")[D2]
        shares = mc.Book.from_dict(res["book_final"]).sleeves["HARV"].shares["AAA"]
        self.assertAlmostEqual(harv["weights"]["AAA"], shares * 110.0 / harv["equity"], places=3)

    def test_minute_mode_without_a_price_history_is_refused_up_front(self):
        with self.assertRaises(ValueError) as cm:                          # no fake brain, no Yahoo: nothing could decide
            md.backfill(D1, D3, "minute", minute_start=D2, shadow=two_sleeves((D1,)), market=market(),
                        minutes=FakeMinutes(self.bars), composer={})
        self.assertIn("Yahoo", str(cm.exception))

    def test_twin_fill_at_the_close_and_other_decision_times(self):
        ref, fills, fb = md.minute_prices(D2, "15:54", ["AAA", "BBB"], FakeMinutes(self.bars), market(), "close")
        self.assertEqual((fills, fb), ({"AAA": 110.0, "BBB": 50.0}, []))    # a market-on-close order: no fallback to count
        self.assertEqual(ref["AAA"], 109.0)
        ref, fills, fb = md.minute_prices(D2, "15:53", ["AAA"], FakeMinutes(self.bars), market())
        self.assertEqual((ref["AAA"], fills["AAA"], fb), (108.0, 109.0, []))   # a minute earlier: the bars starting 15:52 and 15:53
        ref, fills, fb = md.minute_prices(D2, "15:55", ["AAA"], FakeMinutes(self.bars), market())
        self.assertEqual((ref["AAA"], fb), (109.5, ["AAA"]))               # a minute later (the first run's instant): one bar on
        # "+N": the bar ENDING N minutes after the instant; "+1" is "next"; past the last bar it is the close, counted
        f = lambda fill: md.minute_prices(D2, "15:52", ["AAA"], FakeMinutes(self.bars), market(), fill)[1:]   # noqa: E731
        self.assertEqual((f("+1"), f("next"), f("+2"), f("+3")), (({"AAA": 108.0}, []),) * 2 + (({"AAA": 109.0}, []), ({"AAA": 109.5}, [])))
        self.assertEqual(f("+5"), ({"AAA": 110.0}, ["AAA"]))
        for bad in ("+0", "2", "later", None):
            with self.assertRaises(ValueError):
                f(bad)
        # a print 30% off the day's close is not a fill (a split, a bad tick): the close, and counted
        bad = dict(self.bars)
        bad[("AAA", D2)] = {"15:53": 109.0, "15:54": 33.0}
        ref, fills, fb = md.minute_prices(D2, "15:54", ["AAA"], FakeMinutes(bad), market())
        self.assertEqual((fills["AAA"], fb), (110.0, ["AAA"]))
        # no minute at all before the decision: the reference is the previous close
        ref, _, _ = md.minute_prices(D2, "15:54", ["BBB"], FakeMinutes({}), market(bbb=50.0))
        self.assertEqual(ref["BBB"], 50.0)

    def test_the_brains_published_prices_are_the_sizing_reference(self):
        sh = two_sleeves((D1,))
        plan = {D2: {"HG": {"BBB": 1.0}, "HARV": {"BBB": 1.0}}}

        def build(prices):
            def fake(now, quotes=None, fetch=None, pinned=False):
                return dict(payload(**plan[sr.et_now(now).date().isoformat()]), prices=prices)
            return fake
        kw = dict(minute_start=D2, shadow=sh, market=market(), composer={}, slip_bps=0.0, capital=100_000.0,
                  fractions={"HG": 0.5, "HARV": 0.5})
        res = md.backfill(D1, D2, "minute", minutes=FakeMinutes(self.bars), build=build({"AAA": 109.2, "BBB": 50.0}), **kw)
        sell = next(o for o in res["book"][1]["order_list"] if o["side"] == mc.SELL)
        self.assertEqual((sell["symbol"], sell["ref"], sell["px"]), ("AAA", 109.2, 109.5))   # sized on the brain's, filled on the bar
        self.assertEqual(res["minute"]["unpriced_skips"], [])
        # twin: the brain prices only what its trees mention. A sleeve still holding something else is
        # left out of the plan, exactly as the executor would leave it (and it is listed)
        res = md.backfill(D1, D2, "minute", minutes=FakeMinutes(self.bars), build=build({"BBB": 50.0}), **kw)
        hg = rows_of(res, "HG")[D2]
        self.assertEqual((hg["action"], hg["brain"]), ("skip", "ok"))
        self.assertIn("no price for AAA", hg["reason"])
        self.assertEqual(hg["weights"].keys(), {"AAA"})
        self.assertEqual([(x["date"], x["engine"]) for x in res["minute"]["unpriced_skips"]], [(D2, "HG")])
        self.assertEqual(rows_of(res, "HARV")[D2]["action"], "hold")       # the other sleeve is untouched by it

    def test_half_days_keep_their_distance_to_the_close(self):
        self.assertEqual(md.decide_at("2026-11-27"), "12:54")
        self.assertEqual(md.decide_at("2026-11-27", "15:45"), "12:45")
        self.assertEqual(md.decide_at("2026-11-25"), "15:54")               # twin: a full day
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
        self.bars = {("AAA", x): {"15:53": p - 0.5, "15:54": p - 0.4} for x, p in zip(CAL, (100.0, 100.0, 110.0, 121.0, 121.0))}
        self.bars.update({("BBB", x): {"15:53": 50.0, "15:54": 50.0} for x in CAL})
        self.plan = {x: {"HG": {"AAA": 1.0}, "HARV": {"BBB": 1.0}} for x in CAL}
        self.divs, self.boom, self.published = {}, None, None

    def build(self, now, quotes=None, fetch=None, pinned=False):
        if self.boom:
            raise self.boom
        self.assertTrue(pinned)
        out = payload(**self.plan[sr.et_now(now).date().isoformat()])
        return out if self.published is None else dict(out, dividends=self.published, splits=[])

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
        self.assertIn("MIRROR DRY 2026-03-02 (decided 15:54 ET)", lines[0])
        self.assertIn("no snapshot", lines[-1])
        rows = self.rows()
        self.assertEqual([r["engine"] for r in rows], ["HG", "HARV", "BOOK"])
        hg, book = rows[0], rows[2]
        self.assertEqual((hg["action"], hg["decide"], hg["mode"], hg["label"]), ("trade", "15:54", "minute", "firm"))
        self.assertEqual(hg["parity"], "no Composer snapshot")
        saved = json.loads(read(self.book))
        self.assertEqual((saved["session"], saved["seeded_on"], saved["capital"]), (D1, D1, 100_000.0))
        self.assertEqual((saved["schema"], saved["rule"], saved["state"]["last"]), (2, "composer", D1))
        # sized on the 15:54:00 price (99.5) at its limit (99.5 x 1.005 floored to the cent: 99.99), filled at
        # the close of the bar ending 15:55 (99.6), valued at the close (100.0)
        want = math.floor(50_000 * 0.999 / 99.5)
        q = math.floor(want * 49_950 / (want * 99.99))
        self.assertEqual((want, q, book["order_list"][0]["limit"]), (502, 499, 99.99))
        self.assertEqual(saved["book"]["sleeves"][0]["shares"], {"AAA": q})
        self.assertAlmostEqual(hg["equity"], round(50_000 - q * 99.6 - md.commission(q, 99.6) + q * 100.0, 2), places=2)
        self.assertEqual(book["overspent"], {})
        self.assertEqual(book["orders"], 2)
        self.composer(D1)                                                  # a snapshot for the seeding day itself
        lines, _ = self.day(D1, force=True)
        self.assertIn("seeded today", lines[-1])                           # holdings are compared, the day's return is not
        self.assertNotIn("diff_bps", self.rows()[0])
        self.assertEqual(self.rows()[0]["parity"], "same")
        saved = json.loads(read(self.book))
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
        self.divs = {"AAA": {D2: (1.0, D2)}}                               # ex and paid on D2
        self.day(D1)
        lines, _ = self.day(D2)
        self.assertIn("distributions credited $499.00", lines[1])
        first = self.rows()
        book = json.loads(read(self.book))
        lines, alerts = self.day(D2, force=True)
        self.assertEqual(alerts, [])
        again = self.rows()
        self.assertEqual(len(again), 6)                                    # replaced, not appended
        self.assertEqual(again[3]["equity"], first[3]["equity"])
        self.assertEqual(again[3]["div"], first[3]["div"])                 # the distribution was paid once
        self.assertEqual(again[3]["div"], 499.0)
        saved = json.loads(read(self.book))
        self.assertEqual(saved["book"], book["book"])
        self.assertEqual([(r["id"], r["status"]) for r in saved["state"]["receivables"]], [(f"div-AAA-{D2}-HG", "credited")])
        self.assertEqual(saved["state"]["div_seen"], [f"div-AAA-{D2}"])
        self.assertEqual(saved["before"]["state"]["receivables"], [])
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
        self.assertNotIn("flipped after", alerts[0])                       # the close logic agrees with the mirror here
        self.assertIn("1 of 2 engines hold the same", lines[-1])
        hg, harv = self.rows()[3], self.rows()[4]
        self.assertEqual((hg["parity"], harv["parity"]), ("MISMATCH", "same"))
        self.assertAlmostEqual(hg["composer_ret"], 0.10)                   # deposit-adjusted value 1000 -> 1100
        self.assertEqual(hg["composer_ret_basis"], "dav")
        self.assertAlmostEqual(hg["diff_bps"], (hg["ret"] - 0.10) * 1e4, places=1)
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
        # ... and when the close logic sides with Composer, the alert says the call flipped after 15:54
        with open(self.shadow, "w") as f:
            f.write("")
        self.shadow_rows(led(D2, "HG", {"BBB": 1.0}, status="agree"))
        lines, alerts = self.day(D2, force=True)
        self.assertEqual(len(alerts), 1)
        self.assertIn("the call flipped after the mirror's decision minute", alerts[0])
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

    def test_a_half_day_frozen_feed_refusal_is_named_in_the_no_decision_alert(self):
        """the brain refused SPY's half-day bar as a frozen feed (mirror_brain.build: every engine's note leads with the
        halt line, the why is the problems line led by 'half-day, a frozen feed: '): the alert quotes that line, the
        reason whole, then the note (33850e01 quoted the halt line alone). Twin: the same refusal without that line
        quotes the note as before"""
        self.day(D1)
        halt = "SPY's price is not from the bar ending 15:54:00 ET (its last traded bar ends 15:46:00)"
        why = "every one of SPY's bars without volume since that trade closed at one price, not the trade's"
        line = (f"half-day, a frozen feed: {why} (its last trade: the bar ending 15:46:00 ET; FMP's SPY bar ending "
                f"15:54:00 ET has no volume): not taken as the decision bar")
        real = self.build

        def refused(with_line):
            def build(now, quotes=None, fetch=None, pinned=False):
                p = real(now, pinned=pinned)
                p["engines"] = {e: {"status": "unavailable", "note": halt} for e in p["engines"]}
                p["problems"] = [halt] + ([line] if with_line else [])
                return p
            return build
        self.build = refused(True)
        lines, alerts = self.day(D2)
        self.assertEqual(len(alerts), 1, alerts)
        self.assertTrue(alerts[0].startswith(f"MIRROR DRY NO DECISION — {D2} 15:54 ET: HG, HARV had no target from the "
                                             f"brain (half-day, a frozen feed: {why} (its last trade: "), alerts[0])
        self.assertIn(f"not taken as the decision bar; {halt}); those sleeves stood still.", alerts[0])
        self.build = refused(False)
        lines, alerts = self.day(D2, force=True)
        self.assertEqual(alerts, [f"MIRROR DRY NO DECISION — {D2} 15:54 ET: HG, HARV had no target from the brain ({halt}); "
                                  f"those sleeves stood still."])
        import mirror_brain as mb
        self.assertTrue(line.startswith(mb.FROZEN_FEED))                     # the words the brain leads that line with

    def test_a_sleeve_the_brain_does_not_price_is_alerted(self):
        self.day(D1)                                                       # HG now holds AAA
        real = self.build

        def unpriced(now, quotes=None, fetch=None, pinned=False):
            return dict(real(now, pinned=pinned), prices={"BBB": 50.0})    # the trees no longer mention AAA
        self.build = unpriced
        self.plan[D2] = {"HG": {"BBB": 1.0}, "HARV": {"BBB": 1.0}}
        lines, alerts = self.day(D2)
        self.assertEqual(len(alerts), 1)
        self.assertIn("MIRROR DRY SLEEVE LEFT OUT — HG", alerts[0])
        self.assertIn("no price for AAA", alerts[0])
        self.assertEqual(self.rows()[3]["action"], "skip")
        self.build = lambda now, quotes=None, fetch=None, pinned=False: dict(real(now, pinned=pinned), prices={"AAA": 109.5, "BBB": 50.0})
        self.assertEqual(self.day(D2, force=True)[1], [])                  # twin: priced -> it trades, no alert
        self.assertEqual(self.rows()[3]["action"], "trade")

    def test_no_day_return_is_compared_across_a_session_the_step_did_not_run(self):
        self.day(D1)
        self.composer(D2, dav=(1100.0, 2000.0))
        self.composer(D3, dav=(1210.0, 2000.0))
        lines, alerts = self.day(D3)                                       # D2 was never run: the book's return spans two sessions
        self.assertEqual(alerts, [])
        self.assertNotIn("diff_bps", self.rows()[3])
        self.assertAlmostEqual(self.rows()[3]["composer_ret"], 0.10)       # Composer's is D3's alone
        self.assertGreater(self.rows()[3]["ret"], 0.20)
        self.day(D4)                                                       # twin: consecutive sessions are compared
        self.composer(D4, dav=(1210.0, 2000.0))
        self.day(D4, force=True)
        self.assertIn("diff_bps", self.rows()[6])

    def test_the_brains_published_dividends_are_the_ones_booked(self):
        self.day(D1)                                                       # HG holds 499 AAA
        self.divs = {"AAA": {D2: (9.0, D2)}}                               # the simulator's own list says $9 ...
        self.published = [{"ticker": "AAA", "ex_date": D2, "pay_date": D2, "amount": 1.0}]   # ... the brain publishes $1
        self.day(D2)
        self.assertEqual(self.rows()[3]["div"], 499.0)                     # what the executor is given is what is booked
        self.published = []                                                # twin: the brain publishes none -> none booked
        self.day(D2, force=True)
        self.assertEqual((self.rows()[3]["div"], self.rows()[3]["div_accrued"]), (0.0, 0.0))
        self.published = None                                              # twin: a payload without the field (a seam's fake)
        self.day(D2, force=True)                                           # falls back to the simulator's own list
        self.assertEqual(self.rows()[3]["div"], 499 * 9.0)

    def test_an_unfilled_limit_buy_is_reported_and_keeps_its_cash(self):
        self.bars[("AAA", D1)] = {"15:53": 99.5, "15:54": 100.2}           # +70 bps in the minute: past the 99.99 limit
        lines, alerts = self.day(D1)
        self.assertEqual(alerts, [])
        self.assertIn("1 limit buy(s) UNFILLED, cash kept: AAA x499 (limit 99.99, bar 100.20)", lines[0])
        hg, book = self.rows()[0], self.rows()[2]
        self.assertEqual((hg["weights"], hg["cash_share"], hg["unfilled"]), ({}, 1.0, {"AAA": 499}))
        self.assertEqual((book["buys"], book["buys_unfilled"], book["overspent"]), (2, 1, {}))
        lines, alerts = self.day(D2)                                       # the next session's plan buys it
        self.assertEqual(self.rows()[3]["action"], "trade")
        self.assertEqual(self.rows()[3]["weights"].keys(), {"AAA"})

    def test_a_book_of_the_older_schema_is_refused_not_reseeded(self):
        os.makedirs(os.path.dirname(self.book))
        old = json.dumps({"schema": 1, "session": D1, "book": md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5}).to_dict()})
        with open(self.book, "w") as f:
            f.write(old)
        lines, alerts = self.day(D2)
        self.assertIn("MIRROR DRY FAILED", alerts[0])
        self.assertIn("schema 1 is not 2", alerts[0])
        self.assertEqual(read(self.book), old)

    def test_half_day_decides_six_minutes_before_its_own_close(self):
        cal = ["2026-11-25", "2026-11-27"]
        mkt = md.Market(raw={"AAA": {d: 100.0 for d in cal}, "BBB": {d: 50.0 for d in cal}, "SPY": {d: 500.0 for d in cal}}, calendar=cal)
        bars = {("AAA", "2026-11-27"): {"12:53": 99.5, "12:54": 99.6, "15:53": 90.0, "15:54": 90.0},
                ("BBB", "2026-11-27"): {"12:53": 50.0, "12:54": 50.0}}
        self.plan["2026-11-27"] = self.plan[D1]
        lines, alerts = self.day("2026-11-27", market=mkt, minutes=FakeMinutes(bars))
        self.assertEqual(alerts, [])
        self.assertIn("decided 12:54 ET", lines[0])
        order = self.rows()[2]["order_list"][0]
        self.assertEqual((order["symbol"], order["ref"], order["px"]), ("AAA", 99.5, 99.6))   # the bars around 12:54, not 15:54


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

    def brain(self, scale=None, events=None, actions=None, bar="15:53"):
        import preclose as pc
        fam = set(self.fx["prices"])
        bars = {(t, "2026-10-28"): {bar: s["2026-10-28"]} for t, s in self.fx["prices"].items() if "2026-10-28" in s}

        def fetch(t):
            res = self.chart(t)
            res["events"] = (events or {}).get(t) or {}
            if scale and t in scale:                                       # history lowered by a later distribution
                a = res["indicators"]["adjclose"][0]["adjclose"]
                res["indicators"]["adjclose"][0]["adjclose"] = [x * scale[t] for x in a]
            return res
        y = md.Yahoo(fetch=fetch, actions=actions)
        mn = FakeMinutes(bars)
        self.assertTrue(fam)
        return md.brain_payload("2026-10-28", "15:54", y, mn), pc

    def test_targets_through_the_seams_match_the_approved_logic(self):
        p, pc = self.brain()
        self.assertTrue(p["replay"])
        self.assertEqual(p["session"], "2026-10-28")
        self.assertEqual((p["quotes"] or {}).get("source"), "fmp-1m")
        # a PINNED build as of 15:54:00 ET, on the bar that ends at that instant
        self.assertEqual((p["schema"], p["pinned"], p["asof_et"]), (2, True, "15:54:00"))
        self.assertEqual(p["decision_bar"], {"end_utc": "2026-10-28T19:54:00Z", "spy_utc": "2026-10-28T19:54:00Z", "complete": True})
        self.assertEqual(p["dividends"], [])                               # read through the seam (none in this fixture) ...
        unread = " ".join(x for x in p["problems"] if "dividends and splits not read" in x)
        self.assertFalse([t for t in self.fx["prices"] if f" {t}" in unread.replace(",", " ")])   # ... for every ticker it has
        for eng in ("HG", "SLEEVE", "HARV"):
            self.assertEqual(p["engines"][eng]["status"], "ok", p["engines"][eng])
            self.assertTrue(pc.same(p["engines"][eng]["target"], self.fx["expected"][eng]["2026-10-28"]), eng)
        self.assertEqual(p["engines"]["KMLM"]["rule"], "threshold")

    def test_twin_a_decision_bar_that_has_not_printed_is_no_decision(self):
        p, _ = self.brain(bar="15:52")                                     # SPY's last bar ends 15:53:00, a minute short
        self.assertFalse(p["decision_bar"]["complete"])
        self.assertEqual({r["status"] for r in p["engines"].values()}, {"unavailable"})

    def test_dividends_reach_the_payload_through_the_seam_with_fmps_pay_dates(self):
        import mirror_brain as mb
        held = sorted(mb.era_tickers(sr.load_manifest()) & set(self.fx["prices"]))
        t = "BIL" if "BIL" in held else held[0]
        at = lambda d: int(datetime.datetime.fromisoformat(d + "T13:30:00+00:00").timestamp())   # noqa: E731
        events = {t: {"dividends": {"a": {"date": at("2026-10-26"), "amount": 0.31}, "b": {"date": at("2026-09-01"), "amount": 0.30}}}}
        fmp = {"dividends": [{"ex_date": "2026-10-26", "pay_date": "2026-10-29", "amount": 0.3085},
                             {"ex_date": "2026-10-27", "pay_date": "2026-10-30", "amount": 0.11}], "splits": []}
        p, _ = self.brain(events=events, actions=lambda x: fmp if x == t else None)
        mine = [x for x in p["dividends"] if x["ticker"] == t]
        # Yahoo's event with FMP's amount and pay date; the older one is outside the brain's window; FMP's second
        # entry is a day from Yahoo's (the same event, never counted twice)
        self.assertEqual(mine, [{"ticker": t, "ex_date": "2026-10-26", "pay_date": "2026-10-29", "amount": 0.3085}])
        # twin: Yahoo's events alone -> the same ex-date, Yahoo's amount, no pay date (the core then assumes one)
        p, _ = self.brain(events=events)
        self.assertEqual([x for x in p["dividends"] if x["ticker"] == t],
                         [{"ticker": t, "ex_date": "2026-10-26", "pay_date": None, "amount": 0.31}])
        # twin: an event dated after the replayed session is not known yet
        p, _ = self.brain(events={t: {"dividends": {"a": {"date": at("2026-10-29"), "amount": 0.31}}}})
        self.assertEqual([x for x in p["dividends"] if x["ticker"] == t], [])

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


# ------------------------------------------------------------------ M10 limit buys
class M10LimitBuys(NoNetwork):
    T = {"HG": {"status": "ok", "target": {"AAA": 1.0}}}

    def one(self, fill, slip=0.0, **kw):
        """HG, $50,000 cash, buys AAA: reference 100.00 (limit 100.50, 497 shares), the fill bar prints `fill`"""
        sim = md.Sim(md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5}), slip, **kw)
        er, b = sim.session(D1, self.T, {"AAA": 100.0}, {"AAA": fill}, {"AAA": fill})
        return sim, er[0], b

    def test_a_buy_above_its_limit_is_unfilled_and_the_cash_stays(self):
        sim, hg, b = self.one(100.51)                                      # a cent above the limit
        self.assertEqual(sim.book.positions(), {})
        self.assertEqual(sim.book.sleeves["HG"].cash, 50_000.0)
        self.assertEqual(b["problems"], [])                                # not an error: the order is simply not filled
        self.assertEqual((b["buys"], b["buys_unfilled"], b["orders"]), (1, 1, 0))
        self.assertEqual(b["unfilled"], [{"symbol": "AAA", "qty": 497, "ref": 100.0, "limit": 100.5, "px": 100.51,
                                          "asks": {"HG": 497}}])
        self.assertEqual((hg["unfilled"], hg["weights"], hg["cash_share"]), ({"AAA": 497}, {}, 1.0))
        self.assertEqual((hg["commission"], hg["slippage"], hg["traded"], hg["ret"]), (0.0, 0.0, 0.0, 0.0))
        self.assertEqual(b["overspent"], {})
        # the cash is still there, so the next session's plan buys again, at that day's limit
        px = {"AAA": 101.0}
        er, b2 = sim.session(D2, self.T, px, px, px)
        want = math.floor(50_000 * 0.999 / 101.0)
        self.assertEqual((er[0]["action"], sim.book.positions()), ("trade", {"AAA": math.floor(want * 49_950 / (want * 101.5))}))
        self.assertEqual(b2["buys_unfilled"], 0)

    def test_twin_at_or_below_the_limit_it_fills_and_never_above_it(self):
        sim, hg, b = self.one(100.50)                                      # exactly at the limit: filled
        self.assertEqual((sim.book.positions(), b["buys_unfilled"]), ({"AAA": 497}, 0))
        self.assertAlmostEqual(sim.book.sleeves["HG"].cash, 50_000 - 497 * 100.5 - 1.7395, places=6)
        self.assertGreaterEqual(sim.book.sleeves["HG"].cash, 0.0)          # sized at the limit: it cannot cost more than it has
        sim, hg, b = self.one(100.20)
        self.assertEqual(b["order_list"][0]["price"], 100.2)
        # slippage is added to the fill, but a limit order never pays more than its limit
        sim, hg, b = self.one(100.45, slip=20.0)                           # 100.45 x 1.002 = 100.6509
        self.assertEqual((b["order_list"][0]["filled"], b["order_list"][0]["price"]), (497, 100.5))
        self.assertAlmostEqual(hg["slippage"], 497 * 0.05, places=4)
        self.assertEqual(b["overspent"], {})

    def test_twin_without_the_rule_the_same_fill_overspends(self):
        sim, hg, b = self.one(101.0, limit_buys=False)                     # the first run's behaviour: filled 1% above the reference
        self.assertEqual(sim.book.positions(), {"AAA": 497})
        self.assertEqual(b["problems"], [])
        self.assertAlmostEqual(b["overspent"]["HG"], 50_000 - 497 * 101.0 - 1.7395, places=2)   # the sleeve borrowed $198.74
        self.assertLess(b["cash_low"], -198)
        sim, hg, b = self.one(101.0)                                       # with it: unfilled, nothing borrowed
        self.assertEqual((sim.book.positions(), b["overspent"], b["buys_unfilled"]), ({}, {}, 1))
        self.assertEqual(b["cash_low"], 50_000.0)

    def test_a_limit_requoted_at_the_fill_is_sized_there_and_fills(self):
        sim, hg, b = self.one(101.0, limit_at="fill")                      # what the live executor does after its sells
        o = b["order_list"][0]
        self.assertEqual((o["limit"], o["filled"], o["price"]), (101.5, math.floor(499 * 49_950 / (499 * 101.5)), 101.0))
        self.assertEqual(o["filled"], 492)
        self.assertEqual(b["buys_unfilled"], 0)
        with self.assertRaises(ValueError):
            md.Sim(md.seed_book(), limit_at="close")

    def test_a_sell_is_a_market_order_however_far_the_price_moved(self):
        sim, _, _ = self.one(100.0)
        t = {"HG": {"status": "ok", "target": {"BBB": 1.0}}}
        ref, fills = {"AAA": 100.0, "BBB": 50.0}, {"AAA": 80.0, "BBB": 50.0}   # AAA prints 20% under the reference
        er, b = sim.session(D2, t, ref, fills, fills)
        sell = next(o for o in b["order_list"] if o["side"] == mc.SELL)
        self.assertEqual((sell["filled"], sell["price"], sell["limit"]), (497, 80.0, None))
        # the buy is then sized from the cash the sell really raised, never from what was expected
        buy = next(o for o in b["order_list"] if o["side"] == mc.BUY)
        self.assertLessEqual(buy["filled"] * buy["limit"], 497 * 80.0 + 300)
        self.assertEqual((b["overspent"], b["problems"]), ({}, []))

    def test_the_limit_is_the_cores_floored_to_the_venues_tick_like_the_executors(self):
        import ib_adapter                                                  # the executor's own rounding (pure; no connection)
        for px in (0.5321, 0.91, 0.99995, 1.0, 7.02, 8.24, 33.333, 99.5, 158.65, 600.0, 4999.99):
            core = mc.buy_limit(px)
            mine = md.tick_floor(core)
            self.assertEqual(mine, ib_adapter.round_limit_to_tick(core, "BUY"), px)
            self.assertLessEqual(mine, core)                               # never loosened ...
            self.assertGreater(mine, core - (0.01 if core >= 1 else 0.0001) - 1e-12)   # ... and within one tick
        self.assertEqual(md.tick_floor(99.5 * 1.005), 99.99)                # 99.9975 -> 99.99, not 100.00
        self.assertEqual(md.tick_floor(0.123456), 0.1234)
        for bad in (0, -1.0, float("nan"), float("inf"), None, "x", 0.00004):
            self.assertIsNone(md.tick_floor(bad), bad)
        _, _, b = self.one(100.0)
        self.assertEqual(b["order_list"][0]["limit"], md.tick_floor(mc.buy_limit(100.0)))
        self.assertEqual((mc.Config().buy_cushion, mc.Config().cash_reserve_frac), (0.005, 0.001))   # what the numbers here assume

    def test_no_filled_buy_ever_leaves_a_sleeve_in_debt(self):
        import random
        rnd = random.Random(5)
        for i in range(300):
            ref = round(rnd.uniform(0.6, 400.0), 4)
            fill = ref * (1 + rnd.uniform(-0.02, 0.02))
            sim = md.Sim(md.seed_book(rnd.uniform(500, 200_000), {"HG": 0.5, "HARV": 0.5}), rnd.choice((0.0, 2.0, 10.0)))
            _, b = sim.session(D1, self.T, {"AAA": ref}, {"AAA": fill}, {"AAA": fill})
            self.assertEqual(b["overspent"], {}, (ref, fill))
            self.assertGreaterEqual(min(x.cash for x in sim.book.sleeves.values()), 0.0, (ref, fill))
            o = b["order_list"][0] if b["order_list"] else None
            if o and o["filled"]:
                self.assertLessEqual(o["price"], o["limit"] + 1e-12)
                self.assertLessEqual(o["px"], o["limit"] + 1e-9)
            elif o:
                self.assertGreater(o["px"], o["limit"])

    def test_the_backfill_counts_every_unfilled_leg_and_says_whether_it_would_have_filled_later(self):
        sh = two_sleeves((D1,))
        plan = {D2: {"HG": {"BBB": 1.0}, "HARV": {"BBB": 1.0}}, D3: {"HG": {"BBB": 1.0}, "HARV": {"BBB": 1.0}}}
        bars = {("AAA", D2): {"15:53": 109.0, "15:54": 109.5},
                ("BBB", D2): {"15:53": 50.0, "15:54": 50.3, "15:55": 50.4, "15:56": 50.2, "15:58": 50.6},   # +60 bps in the minute
                ("AAA", D3): {"15:53": 120.0, "15:54": 120.5}, ("BBB", D3): {"15:53": 50.0, "15:54": 50.1}}

        def build(now, quotes=None, fetch=None, pinned=False):
            return payload(**plan[sr.et_now(now).date().isoformat()])
        kw = dict(minute_start=D2, shadow=sh, market=market(), build=build, composer={}, slip_bps=0.0, capital=100_000.0,
                  fractions={"HG": 0.5, "HARV": 0.5})
        res = md.backfill(D1, D3, "minute", minutes=FakeMinutes(bars), **kw)
        hg = rows_of(res, "HG")
        self.assertEqual(len(res["unfilled"]), 1)
        u = res["unfilled"][0]
        self.assertEqual((u["date"], u["symbol"], u["limit"], u["px"], u["asks"]), (D2, "BBB", 50.25, 50.3, {"HG": u["qty"]}))
        self.assertEqual((u["over_limit_bps"], u["ref_to_fill_bps"]), (10.0, 60.0))
        self.assertEqual(u["later"], {"at": "15:57", "px": 50.2})           # the order keeps working until 15:59:00
        self.assertEqual((hg[D2]["weights"], hg[D2]["unfilled"]), ({}, {"BBB": u["qty"]}))   # AAA sold (a market order), all cash
        self.assertEqual((hg[D3]["action"], hg[D3]["weights"].keys()), ("trade", {"BBB"}))   # bought the next session
        lb = res["parity"]["book"]["limit_buys"]
        self.assertEqual((lb["buy_orders"], lb["unfilled_orders"], lb["unfilled_legs"], lb["sessions"]), (2, 1, 1, 1))
        self.assertAlmostEqual(lb["unfilled_usd"], u["qty"] * 50.3, places=2)
        self.assertIn("a limit buy left unfilled into the day (BBB)", md.cause_labeller([], res["rows"], "HG")({"d0": D2, "d1": D3}))
        # twin: the same minute inside the cushion fills, and nothing is listed
        ok = dict(bars)
        ok[("BBB", D2)] = {"15:53": 50.0, "15:54": 50.2}
        res = md.backfill(D1, D3, "minute", minutes=FakeMinutes(ok), **kw)
        self.assertEqual((res["unfilled"], res["parity"]["book"]["limit_buys"]["unfilled_orders"]), ([], 0))
        self.assertEqual(rows_of(res, "HG")[D2]["weights"].keys(), {"BBB"})
        # twin: no later bar at or below the limit -> it would not have filled by 15:59 either
        never = dict(bars)
        never[("BBB", D2)] = {"15:53": 50.0, "15:54": 50.3, "15:55": 50.4, "15:59": 50.0}
        res = md.backfill(D1, D3, "minute", minutes=FakeMinutes(never), **kw)
        self.assertIsNone(res["unfilled"][0]["later"])                     # the 15:59 bar ends at the close: after the cancel


# ------------------------------------------------------------------ M11 splits
class M11Splits(NoNetwork):
    """SSS splits 2:1 on D3. It TRADED at 200, 200, 100, 100; the source restates the past: 100 throughout."""

    def mkt(self, listed=True, restated=True):
        sss = dict(zip(CAL, (100.0,) * 5 if restated else (200.0, 200.0, 200.0, 100.0, 100.0)))
        return market(extra={"SSS": sss}, splits={"SSS": [(D3, 2, 1)]} if listed else None)

    def test_closes_are_the_prices_the_fund_traded_at(self):
        m = self.mkt()
        self.assertEqual([m.closes(d)["SSS"] for d in CAL], [200.0, 200.0, 200.0, 100.0, 100.0])
        self.assertEqual((m.traded_factor("SSS", D2), m.traded_factor("SSS", D3), m.traded_factor("AAA", D1)), (2.0, 1.0, 1.0))
        self.assertEqual(m.actions(D3)[1], [{"ticker": "SSS", "date": D3, "ratio": 2.0}])
        self.assertEqual(m.actions(D2)[1], [])                             # not before its day
        # a split announced for a date the series does not reach yet is in no price: no factor
        ahead = market(extra={"SSS": {d: 100.0 for d in CAL}}, splits={"SSS": [("2026-04-01", 2, 1)]})
        self.assertEqual(ahead.closes(D1)["SSS"], 100.0)
        # minute bars and the brain's prices are restated the same way in a replay, and come back the same way
        bars = {("SSS", D2): {"15:53": 100.0, "15:54": 100.5}}
        ref, fills, fb = md.minute_prices(D2, "15:54", ["SSS"], FakeMinutes(bars), m)
        self.assertEqual((ref["SSS"], fills["SSS"], fb), (200.0, 201.0, []))
        ref, _, _ = md.minute_prices(D2, "15:54", ["SSS"], FakeMinutes(bars), m, brain_prices={"SSS": 100.2})
        self.assertEqual(ref["SSS"], 200.4)

    def test_the_sleeves_shares_are_rescaled_by_the_core_before_the_plan(self):
        sh = two_sleeves((D1, D2, D3, D4), hg={d: {"SSS": 1.0} for d in CAL})
        res = run(sh, self.mkt(), end=D4)
        hg = rows_of(res, "HG")
        first = next(o for o in res["book"][0]["order_list"] if o["symbol"] == "SSS")
        self.assertEqual((first["filled"], first["price"]), (248, 200.0))  # floor(249 x 49,950 / (249 x 201.00)), at what it traded at
        self.assertEqual([x["after"] for x in res["splits_applied"]], [{"HG": 496}])
        self.assertEqual(res["splits_applied"][0]["date"], D3)
        # D3's plan then sees 496 shares at 100 and tops up the 3 the 200-dollar price could not buy
        self.assertEqual([(o["side"], o["symbol"], o["filled"]) for o in res["book"][2]["order_list"]], [(mc.BUY, "SSS", 3)])
        self.assertEqual(res["book_final"]["sleeves"][0]["shares"], {"SSS": 499})
        self.assertEqual(res["state"]["venue"]["SSS"], 499)                # the 'account' was split too: mc.check stays clean
        self.assertTrue(all(b["problems"] == [] for b in res["book"]))
        self.assertAlmostEqual(hg[D3]["ret"], 0.0, places=4)               # nothing happened to the holder (a $0.35 commission)
        self.assertAlmostEqual(hg[D4]["equity"], hg[D2]["equity"], delta=0.5)
        self.assertEqual(res["unallocated"], 0.0)                          # 2:1 leaves no fraction
        # twin: the same traded prices with the split NOT listed -> the book keeps the old count and halves
        bad = rows_of(run(sh, self.mkt(listed=False, restated=False), end=D4), "HG")
        self.assertAlmostEqual(bad[D3]["ret"], -0.5, places=2)

    def test_a_reverse_split_floors_the_book_and_leaves_the_cash_in_lieu_unallocated(self):
        book = md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5})
        book.sleeves["HG"].shares["SSS"], book.sleeves["HARV"].shares["SSS"] = 15, 7
        sim = md.Sim(book, 0.0)
        hold = {}                                                          # no targets: both sleeves stand still
        row = {"ticker": "SSS", "date": D2, "ratio": 0.1}
        px = {"SSS": 30.0}
        _, b = sim.session(D2, hold, px, px, px, None, [row])
        self.assertEqual(b["splits"][0]["before"], {"HARV": 7, "HG": 15})
        self.assertEqual(sum(b["splits"][0]["after"].values()), 2)         # floor(22 x 0.1); the core says who gets them
        self.assertEqual(book.positions(), {"SSS": 2})
        self.assertEqual(sim.venue, {"SSS": 2})
        self.assertAlmostEqual(b["splits"][0]["fraction"], 0.2)
        self.assertAlmostEqual(sim.unallocated, 0.2 * 30.0)                # the broker's cash in lieu: no sleeve's until credited
        self.assertEqual((b["unallocated"], b["problems"]), (6.0, []))
        self.assertEqual(book.cash(), 100_000.0)                           # the core books nothing in cash
        _, b = sim.session(D3, hold, px, px, px, None, [row, row])         # twin: listed again -> not applied again
        self.assertEqual((b["splits"], book.positions(), sim.unallocated), ([], {"SSS": 2}, 6.0))

    def test_twin_a_split_that_surfaces_after_its_session_is_reported_not_applied(self):
        book = md.seed_book(100_000.0, {"HG": 0.5, "HARV": 0.5})
        book.sleeves["HG"].shares["SSS"] = 10
        sim = md.Sim(book, 0.0)
        px = {"SSS": 30.0}
        sim.session(D2, {}, px, px, px)                                    # D2 ran, and the split dated D2 was not listed
        _, b = sim.session(D3, {}, px, px, px, None, [{"ticker": "SSS", "date": D2, "ratio": 2.0}])
        self.assertEqual(book.positions(), {"SSS": 10})
        self.assertTrue(any("split SSS" in p and "not applied" in p for p in b["problems"]), b["problems"])
        # twin: an unusable row, or a split of something nobody holds, changes nothing and says nothing
        _, b = sim.session(D4, {}, px, px, px, None, [{"ticker": "SSS", "date": D4, "ratio": -2}, {"ticker": "ZZZ", "date": D4, "ratio": 2.0}, "junk"])
        self.assertEqual((book.positions(), b["problems"], b["splits"]), ({"SSS": 10}, [], []))


if __name__ == "__main__":
    unittest.main()
