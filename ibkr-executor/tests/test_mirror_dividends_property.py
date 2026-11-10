"""Dividends and splits through the manager, as a property test over random multi-session histories
(rotations, skipped sessions, restarts, the same dividend listed for ten days, a venue that pays on
the pay date, splits with cash in lieu), on the LIVE book against the scriptable account, for both
dividend rules. An independent model says what each sleeve is owed.

Ported from the second verification round (the second verifier's B2 harness, which found that a
dividend's entitlement was read from the last PLANNED session: a flatten or a split in between was
not seen). Two things in the model follow decisions taken after that harness was written, and are
marked where they are: the entitlement is carried through a split dated after the last traded close
and up to the ex-date (the rule the model's own VENUE always used), and a pay date the brain never
lists is assumed (ex + 7) only from ten days after the ex-date (R2), so such a receivable can be
open while the account already holds its cash."""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pytest

import test_mirror as tm
from app import mirror_core as mc

DAYS = ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18",
        "2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25"]
TEMPL = [
    tm.T1,
    dict(tm.T1, HG={"TQQQ": 1.0}, HARV={"BIL": 1.0}),
    dict(tm.T1, HG={"PULS": 0.5, "BIL": 0.5}, SLEEVE={"TQQQ": 0.5, "BOXX": 0.5}),
    dict(tm.T1, KMLM={"BIL": 0.5, "PULS": 0.5}, HARV={"SOXL": 0.3, "PULS": 0.7}),
    {"HG": {"SPY": 1.0}, "KMLM": {"TECL": 1.0}, "SLEEVE": {"BOXX": 1.0}, "HARV": {"BIL": 1.0}},
]
PAYERS = ("PULS", "BIL", "BOXX", "TQQQ", "SOXL")


def simulate(tmp, seed, rule, allow_split=True, skip_p=0.2):
    rnd = random.Random(seed)
    r = tm.Rig(tmp, live=True, dividend_rule=rule)
    v = r.venue
    px = dict(tm.PX)
    # ---- the schedule
    divs = []
    for _ in range(rnd.randint(2, 6)):
        ex = rnd.choice(DAYS[1:8])
        lag = rnd.choice((None, 0, 1, 2, 5))
        pay = None if lag is None else (date.fromisoformat(ex) + timedelta(days=lag)).isoformat()
        d = {"ticker": rnd.choice(PAYERS), "ex_date": ex, "pay_date": pay, "amount": round(rnd.uniform(0.05, 0.6), 4)}
        if not any(x["ticker"] == d["ticker"] and x["ex_date"] == ex for x in divs):
            divs.append(d)
    splits = []
    if allow_split and rnd.random() < 0.6:
        t = rnd.choice(("TQQQ", "SOXL", "TECL", "PULS"))
        day = rnd.choice(DAYS[1:9])
        if not any(x["ticker"] == t and x["ex_date"] == day for x in divs):
            splits.append({"ticker": t, "date": day, "ratio": rnd.choice((2.0, 3.0, 0.5, 0.2, 1.5))})
    due_of = lambda d: d["pay_date"] or (date.fromisoformat(d["ex_date"]) + timedelta(days=mc.DEFAULT_PAY_LAG_DAYS)).isoformat()  # noqa: E731
    # ---- state of the model
    close_sleeves = {}       # session -> {sleeve: {ticker: shares}} after that session
    close_acct = {}
    traded = []              # sessions that reached a plan
    paid, in_lieu, seen_at = set(), 0.0, {}
    owed = {}                # (ticker, ex, sleeve) -> dict(total, shares)
    model_status = {}
    last_close = {"sleeves": {}, "acct": {}}
    log = []
    for i, day in enumerate(DAYS):
        r.clock.now = tm.at("09:35:00", day)
        # splits effective today, at the venue
        for s in splits:
            if s["date"] == day:
                t, ratio = s["ticker"], s["ratio"]
                pos = v._positions.get(t, 0)
                new = int(math.floor(pos * ratio + 1e-9))
                px[t] = round(px[t] / ratio, 4)
                v.quotes[t] = px[t]
                frac = pos * ratio - new
                if pos:
                    v._positions[t] = new
                    cash = round(frac * px[t], 2)
                    v.cash += cash
                    in_lieu += cash
                    # the model's sleeves follow the book's own rule (largest remainder) - checked below against the venue
                log.append(f"{day} split {t} x{ratio}: account {pos} -> {new}")
        # the venue pays what is due, on the ACCOUNT's shares at the close before the ex-date
        for k, d in enumerate(divs):
            if k not in paid and due_of(d) <= day:
                prev = [x for x in DAYS if x < d["ex_date"]]
                shares = (close_acct.get(prev[-1]) or {}).get(d["ticker"], 0) if prev else 0
                # a split between that close and the ex-date changes the entitled shares
                for s in splits:
                    if s["ticker"] == d["ticker"] and prev and prev[-1] < s["date"] <= d["ex_date"]:
                        shares = int(math.floor(shares * s["ratio"] + 1e-9))
                v.cash += shares * d["amount"]
                paid.add(k)
                log.append(f"{day} venue pays {d['ticker']} ex {d['ex_date']}: {shares} x {d['amount']}")
        if rnd.random() < 0.3:
            r.boot()
        skip = i not in (0, len(DAYS) - 1, len(DAYS) - 2) and rnd.random() < skip_p
        tg = rnd.choice(TEMPL)
        lo = (date.fromisoformat(day) - timedelta(days=10)).isoformat()
        listed = [dict(d) for d in divs if lo <= d["ex_date"] <= day]
        sp = [dict(s) for s in splits if lo <= s["date"] <= day]
        r.brain.make = lambda now, tg=tg, day=day, listed=listed, sp=sp: tm.payload(
            now, tg, prices=dict(px), session=day, rules={}, dividends=listed, splits=sp)
        r.brain.fail = "transport" if skip else None
        before = {n: dict(s.shares) for n, s in r.m.book.sleeves.items()}
        r.tick("15:54:30", day)
        if rnd.random() < 0.2:
            r.boot()
        r.tick("15:58:30", day)
        r.tick("15:59:30", day)
        row = r.m.state["last_run"]
        assert row and row["session"] == day, (day, row and row.get("session"), r.m._why)
        if skip:
            assert row["outcome"] == "skipped", row
        else:
            assert row["outcome"] != "skipped", (seed, day, row.get("reason"), log[-3:])
            traded.append(day)
            # ---- the model: dividends first seen at this plan
            for d in listed:
                key = (d["ticker"], d["ex_date"])
                if key in seen_at:
                    continue
                seen_at[key] = day
                if d["ex_date"] == day:
                    hold = before_split_fix(before, splits, day, r)        # holdings as the plan saw them
                else:
                    prev = [x for x in traded if x < d["ex_date"]]
                    hold = close_sleeves.get(prev[-1], {}) if prev else {}
                    for s in splits:
                        if prev and prev[-1] < s["date"] <= d["ex_date"] and sum(sh.get(s["ticker"], 0) for sh in hold.values()):
                            b = mc.Book()
                            for n, sh in hold.items():
                                b.sleeves[n] = mc.Sleeve(name=n, shares=dict(sh))
                            mc.apply_split(b, s["ticker"], s["ratio"])
                            hold = {n: dict(x.shares) for n, x in b.sleeves.items()}
                for name, sh in hold.items():
                    q = sh.get(d["ticker"], 0)
                    if q > 0:
                        owed[(d["ticker"], d["ex_date"], name)] = {
                            "shares": q, "total": round(q * d["amount"], 6), "due": due_of(d),
                            "not_before": None if d["pay_date"] else (date.fromisoformat(d["ex_date"]) + timedelta(
                                days=mc.PAY_DATE_GIVE_UP_DAYS)).isoformat()}
            # ---- settlement in the model (first traded session on or after the due date; held is read before the trades)
            now_hold = before_split_fix(before, splits, day, r)
            for key, o in owed.items():
                if key in model_status or o["due"] > day or (o["not_before"] and day < o["not_before"]):
                    continue
                held = now_hold.get(key[2], {}).get(key[0], 0) > 0
                model_status[key] = "credited" if (rule == "holder" or held) else "leaked"
        close_sleeves[day] = {n: dict(s.shares) for n, s in r.m.book.sleeves.items()}
        close_acct[day] = dict(v.positions_snapshot()["stocks"])
        probs = mc.check(r.m.book, v.positions_snapshot()["stocks"], exact=True)
        assert probs == [] or skip, (seed, day, probs, log[-4:])
    return r, divs, splits, owed, model_status, in_lieu, log


APPLIED = {}


def before_split_fix(before, splits, day, r):
    """the plan sees the sleeves AFTER every split dated up to today that the book had not applied yet
    (a split whose own session was skipped is applied at the next plan)"""
    out = {n: dict(sh) for n, sh in before.items()}
    done = APPLIED.setdefault(id(r.venue), {})
    for k, s in enumerate(splits):
        if s["date"] <= day and done.get(k, day) == day:
            done[k] = day
            tot = sum(sh.get(s["ticker"], 0) for sh in out.values())
            if tot:
                b = mc.Book()
                for n, sh in out.items():
                    b.sleeves[n] = mc.Sleeve(name=n, shares=dict(sh))
                mc.apply_split(b, s["ticker"], s["ratio"])
                out = {n: dict(x.shares) for n, x in b.sleeves.items()}
    return out


@pytest.mark.parametrize("rule", ["holder", "composer"])
def test_dividends_and_splits_property(tmp_path_factory, rule):
    bad = []
    N = 60
    stats = {"divs": 0, "credited": 0, "leaked": 0, "splits": 0}
    for seed in range(N):
        try:
            r, divs, splits, owed, model, in_lieu, log = simulate(tmp_path_factory.mktemp(f"{rule}{seed}"), seed, rule)
        except AssertionError as exc:
            bad.append(f"seed {seed}: {str(exc)[:300]}")
            continue
        recs = r.m.state["dividends"]
        ids = [x["id"] for x in recs]
        try:
            assert len(ids) == len(set(ids)), f"a receivable booked twice: {sorted(i for i in ids if ids.count(i) > 1)}"
            got = {(x["ticker"], x["ex_date"], x["sleeve"]): x for x in recs}
            assert set(got) == set(owed), (f"receivables differ: only book {sorted(set(got) - set(owed))}, "
                                           f"only model {sorted(set(owed) - set(got))}")
            for key, o in owed.items():
                assert got[key]["shares"] == o["shares"] and abs(got[key]["total"] - o["total"]) < 1e-6, (key, got[key], o)
                want = model.get(key, "open")
                assert got[key]["status"] == want, (key, got[key]["status"], want, got[key])
            credited = sum(x["total"] for x in recs if x["status"] == "credited")
            leaked = sum(x["total"] for x in recs if x["status"] == "leaked")
            still = sum(x["total"] for x in recs if x["status"] == "open")
            # cash conservation against the ACCOUNT: everything the venue paid is either in a sleeve, leaked, or
            # still owed; cash in lieu of a split's fraction is never booked by the book itself
            gap = r.venue.cash - r.m.book.cash()
            assert gap >= -0.01, f"the book claims more cash than the account: {gap:.2f}"
            unseen = 0.0
            # R2: a receivable whose pay date the brain never listed stays OPEN until ex + 10 days, while the venue
            # paid it at ex + 7: that cash is in the account and not yet in a sleeve
            venue_paid = {(d["ticker"], d["ex_date"]) for d in divs
                          if (d["pay_date"] or (date.fromisoformat(d["ex_date"]) + timedelta(days=mc.DEFAULT_PAY_LAG_DAYS)).isoformat()) <= DAYS[-1]}
            open_paid = sum(x["total"] for x in recs if x["status"] == "open" and (x["ticker"], x["ex_date"]) in venue_paid)
            assert all(not x.get("pay_date") for x in recs if x["status"] == "open" and (x["ticker"], x["ex_date"]) in venue_paid), "an open receivable with a KNOWN pay date that the venue has paid"
            assert abs(gap - (leaked + in_lieu + open_paid)) < 0.02, f"cash: account - book = {gap:.2f}, explained: leaked {leaked:.2f} + cash in lieu {in_lieu:.2f} + open but paid {open_paid:.2f} (open {still:.2f})"
            stats["divs"] += len(owed)
            stats["credited"] += sum(1 for x in recs if x["status"] == "credited")
            stats["leaked"] += sum(1 for x in recs if x["status"] == "leaked")
            stats["splits"] += len(splits)
            # every credited receivable appears in exactly one session's credits
            hist = [c["id"] for row in r.m.state["history"] for c in (row.get("credits") or []) if c.get("kind") == "dividend"]
            assert len(hist) == len(set(hist)), f"a dividend credited in two sessions: {hist}"
            assert sorted(hist) == sorted(x["id"] for x in recs if x["status"] == "credited")
            assert mc.check(r.m.book, r.venue.positions_snapshot()["stocks"], exact=True) == []
        except AssertionError as exc:
            bad.append(f"seed {seed}: {str(exc)[:400]} | {log[-5:]}")
    assert stats["credited"] > 40 and stats["splits"] > 15 and stats["divs"] > 100, stats      # not vacuous
    assert not bad, f"{len(bad)} of {N} histories fail; first 6:\n" + "\n".join(bad[:6])


def test_phantom_receivable_after_a_flatten(tmp_path):
    """shares sold by a /kill flatten BEFORE the ex-date, with the ex-date's own session not planned (still
    halted): the next plan reads the entitlement from the last history row, which predates the flatten"""
    r = tm.Rig(tmp_path, live=True, venue_cash=150_000.0, dividend_rule="holder")     # $50k of the account is not the book's
    r.tick("15:54:30")                                                               # Tue 11-10: KMLM and HARV hold PULS
    held = {n: s.shares.get("PULS", 0) for n, s in r.m.book.sleeves.items() if s.shares.get("PULS")}
    assert held
    r.clock.now = tm.at("10:00:00", "2026-11-11")                                    # Wed: /kill, everything is sold
    r.m.halt("kill", flatten=True)
    for _ in range(4):
        r.clock.now += timedelta(seconds=6)
        r.m.tick(r.venue)
    assert r.m.book.positions() == {} and r.venue.positions_snapshot()["stocks"] == {}
    # Thu 11-12 is PULS's ex-date; the book is still halted (no plan, no row). Nobody holds PULS at Wed's close
    r.tick("15:54:30", "2026-11-12")
    r.m.resume()
    div = {"ticker": "PULS", "ex_date": "2026-11-12", "pay_date": "2026-11-13", "amount": 0.20}
    r.brain.make = lambda now: tm.payload(now, tm.T1, session="2026-11-13", rules={}, dividends=[dict(div)])
    cash0 = r.venue.cash                                                             # the account receives NO dividend
    r.tick("15:54:30", "2026-11-13")
    r.tick("15:55:00", "2026-11-13")
    recs = r.m.state["dividends"]
    credited = [(x["sleeve"], x["shares"], x["total"], x["status"], x["basis"]) for x in recs]
    assert not recs, (f"receivables for shares the book sold BEFORE the ex-date (the account was paid nothing): {credited}")


@pytest.mark.parametrize("ratio", [3.0, 0.2])
def test_split_then_ex_date_with_neither_session_planned(tmp_path, ratio):
    """Tue 11-10: KMLM and HARV hold PULS. Wed 11-11: PULS splits; Thu 11-12: PULS goes ex. Neither session is
    planned (the brain is down; or, live, the split was listed late and the pre-trade gate refused). Fri's
    plan applies the split, then reads the dividend's entitlement from TUESDAY's history row: PRE-split
    shares at a POST-split amount per share."""
    r = tm.Rig(tmp_path, live=True, venue_cash=150_000.0, dividend_rule="holder")     # $50k of the account is not the book's
    v = r.venue
    r.tick("15:54:30")
    held = sum(s.shares.get("PULS", 0) for s in r.m.book.sleeves.values())
    assert held == v._positions["PULS"] > 0
    post = int(math.floor(held * ratio + 1e-9))
    v._positions["PULS"] = post                                                      # Wed: the split, in the account
    px = dict(tm.PX, PULS=round(tm.PX["PULS"] / ratio, 4))
    v.quotes["PULS"] = px["PULS"]
    r.brain.fail = "transport"
    for day in ("2026-11-11", "2026-11-12"):
        r.tick("15:54:30", day)
        r.tick("15:58:30", day)
        assert r.m.state["last_run"]["outcome"] == "skipped"
    r.brain.fail = None
    amount = 0.20
    paid = post * amount                                                             # paid on the shares held at Wed's close
    v.cash += paid
    div = {"ticker": "PULS", "ex_date": "2026-11-12", "pay_date": "2026-11-13", "amount": amount}
    sp = {"ticker": "PULS", "date": "2026-11-11", "ratio": ratio}
    r.brain.make = lambda now: tm.payload(now, tm.T1, prices=px, session="2026-11-13", rules={}, dividends=[div], splits=[sp])
    r.tick("15:54:30", "2026-11-13")
    assert r.m.state["last_run"]["outcome"] != "skipped", r.m.state["last_run"]
    assert mc.check(r.m.book, v.positions_snapshot()["stocks"], exact=True) == []        # the split itself is right
    booked = sum(x["total"] for x in r.m.state["dividends"] if x["status"] in ("credited", "open"))
    assert booked == pytest.approx(paid, abs=0.5), \
        (f"split x{ratio:g}: the account was paid ${paid:,.2f} ({post} sh x {amount}); the book booked ${booked:,.2f} "
         f"({[(x['sleeve'], x['shares'], x['status']) for x in r.m.state['dividends']]})")


def test_live_credit_waits_for_the_accounts_cash_and_is_credited_once(tmp_path):
    r = tm.Rig(tmp_path, live=True, dividend_rule="holder")                           # account cash == book cash
    r.tick("15:54:30")
    held = sum(s.shares.get("PULS", 0) for s in r.m.book.sleeves.values())
    div = {"ticker": "PULS", "ex_date": "2026-11-11", "pay_date": "2026-11-12", "amount": 0.20}
    mk = lambda day: (lambda now: tm.payload(now, tm.T1, session=day, rules={}, dividends=[dict(div)]))  # noqa: E731
    credited = lambda: sum(c["amount"] for row in r.m.state["history"] for c in row.get("credits") or [])  # noqa: E731
    r.brain.make = mk("2026-11-11")
    r.tick("15:54:30", "2026-11-11")
    r.brain.make = mk("2026-11-12")
    r.tick("15:54:30", "2026-11-12")                                                  # due, not paid: waits
    assert {x["status"] for x in r.m.state["dividends"]} == {"open"} and credited() == 0
    r.boot()
    r.venue.cash += held * 0.20 - 5.0                                                 # paid $5 short
    r.brain.make = mk("2026-11-13")
    r.tick("15:54:30", "2026-11-13")
    st = sorted((x["sleeve"], x["status"]) for x in r.m.state["dividends"])
    r.venue.cash += 5.0
    r.boot()
    r.brain.make = mk("2026-11-16")
    r.tick("15:54:30", "2026-11-16")
    assert {x["status"] for x in r.m.state["dividends"]} == {"credited"}
    assert credited() == pytest.approx(held * 0.20, abs=0.01)
    r.boot()
    r.brain.make = mk("2026-11-17")
    r.tick("15:54:30", "2026-11-17")
    assert credited() == pytest.approx(held * 0.20, abs=0.01)                         # never twice
    assert r.m.book.cash() <= r.venue.cash + 0.01
    assert mc.check(r.m.book, r.venue.positions_snapshot()["stocks"], exact=True) == []
    print("\n[B2] paid $5 short on 11-13: statuses", st)
