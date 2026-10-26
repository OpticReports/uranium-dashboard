"""Market-buy cushion + sleeve cash reserve gates (2026-10-26, the BIL x56
refusals; blend.py "MARKET-BUY CREDIT CUSHION" note).

Live: the BIL sweep, a MKT BUY sized to every whole share of idle sleeve
cash, was left `Inactive` with no reason by IBKR's cash-account credit check
on every cycle from 2026-10-07. The suite pins MKT_BUY_CUSHION and
SLEEVE_CASH_RESERVE_FRAC to 0 (conftest) so the legacy gates keep their exact
ledgers; THESE gates run the shipped values and check:
  * the shipped constants are the documented ones;
  * a venue that refuses a market buy without a 5% margin rejects the old
    sizing and accepts the new one (the regression this exists for);
  * seed / sweep / core-buy sizing, the sweep's convergence onto the reserve,
    entries funded past the reserve with BIL, the pre-fund hold beside it,
    the reserve top-up and the belt that must not call a blocked top-up an
    overdraw, the execution clamps, the budget cap;
  * the refusal note is a yes/no that never publishes the account's cash."""
from __future__ import annotations

import re
import time

import pytest

from app import blend as blend_mod
from app.blend import run_cycle
from app.ib_adapter import DryAdapter, ExecutorConnectionError
from tests.test_blend import (
    PRICES, SessionDryAdapter, _held_position, _seed_initialized, _session_cycle, entry, mk,
    payload, stop_row,
)

# Captured at import, before any per-test monkeypatch: the SHIPPED values.
LIVE_CUSHION = blend_mod.MKT_BUY_CUSHION
LIVE_RESERVE = blend_mod.SLEEVE_CASH_RESERVE_FRAC


@pytest.fixture
def shipped(monkeypatch):
    """Undo conftest's pin: run the shipped cushion and reserve."""
    monkeypatch.setattr(blend_mod, "MKT_BUY_CUSHION", LIVE_CUSHION)
    monkeypatch.setattr(blend_mod, "SLEEVE_CASH_RESERVE_FRAC", LIVE_RESERVE)


class _MarginVenue(DryAdapter):
    """A cash-account venue. A market-type BUY passes the credit check only
    when the account's available cash covers its value plus `margin`;
    otherwise it is left Inactive with NO reason - the live 2026-10-19 shape
    (PendingSubmit -> Inactive, errorCode 0). Fills move `cash`."""

    def __init__(self, cash: float, margin: float = 0.05):
        super().__init__()
        self.cash, self.margin, self.refused = cash, margin, []

    def place_stock_order(self, symbol, qty, order_type, stop_price=None,
                          tif="DAY", ref_price=None, client_order_id=None):
        if order_type in ("MKT", "MOO") and qty > 0:
            px = ref_price if ref_price is not None else self.spot(symbol)
            if qty * px * (1.0 + self.margin) > self.cash + 1e-9:
                self.refused.append((symbol, qty))
                raise RuntimeError("order rejected by venue (status Inactive): "
                                   "IBKR gave no reason")
        out = super().place_stock_order(symbol, qty, order_type,
                                        stop_price=stop_price, tif=tif,
                                        ref_price=ref_price,
                                        client_order_id=client_order_id)
        if order_type in ("MKT", "MOO") and out.get("status") == "filled":
            self.cash -= qty * out["fill_price"]       # a sell (qty < 0) credits
        return out

    def account_cash(self):
        return {"total_cash": self.cash, "net_liq": None,
                "available_funds": self.cash, "ts": time.time()}


def _sweeps(intents, sign=1):
    return [i for i in intents if i["action"] == "SWEEP" and i["qty"] * sign > 0]


# --- the shipped values -----------------------------------------------------------

def test_shipped_constants_are_the_documented_values():
    assert (LIVE_CUSHION, LIVE_RESERVE) == (0.05, 0.02)
    src = open(blend_mod.__file__).read()
    assert re.search(r"^MKT_BUY_CUSHION = 0\.05$", src, re.M)
    assert re.search(r"^SLEEVE_CASH_RESERVE_FRAC = 0\.02$", src, re.M)


# --- the regression: a 5%-margin venue ----------------------------------------------

def _live_shape_book(tmp_path):
    """The live failure's shape: idle sleeve cash $5,600, the core fully
    invested, and NOTHING in the account outside the book's cash (the stage-2
    adoption had made all of it book cash). Sleeve weight 33.7%, inside the
    30% +-5 band, so no rebalance muddies the cycle."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=5_600.0, bil_qty=300, spy_qty=700,
                      core_cash=0.0)
    return m


def test_old_sizing_is_refused_by_a_margin_venue(tmp_path):
    """Pinned (cushion 0, reserve 0) = the pre-fix sizing: 56 BIL for $5,600
    of cash, refused with no reason, exactly the live page. (The note's own
    wording is gated below with the shipped margin; under this pin its
    margin is 0 by construction.)"""
    m = _live_shape_book(tmp_path)
    venue = _MarginVenue(cash=5_600.0)
    alerts = []
    run_cycle(m, venue, payload(), "2026-08-20", alert=alerts.append)
    assert venue.refused == [("BIL", 56)]
    page = next(a for a in alerts if "intent failed (SWEEP BIL)" in a)
    assert "status Inactive" in page and "IBKR gave no reason" in page
    assert not re.search(r"5,?600", page), "the account's cash level leaked"


def test_shipped_note_ledger_ahead_of_the_account_says_funds_without_a_figure(tmp_path,
                                                                            shipped):
    """The ledger believes $5,600 is idle; the account holds $4,000. The
    shipped sizing (46 sh, $4,830 with the margin) is refused, and the page
    names a funds refusal with no cash figure."""
    m = _live_shape_book(tmp_path)
    venue = _MarginVenue(cash=4_000.0)
    alerts = []
    run_cycle(m, venue, payload(), "2026-08-20", alert=alerts.append)
    assert venue.refused == [("BIL", 46)]
    page = next(a for a in alerts if "intent failed (SWEEP BIL)" in a)
    assert "do NOT cover it at a 5% market-order margin" in page
    assert not re.search(r"4,?000|5,?600", page), "the account's cash level leaked"


def test_shipped_note_when_the_venue_margin_is_wider_than_assumed(tmp_path, shipped):
    """IBKR's margin wider than the shipped 5%: the funds DO cover the order
    at 5%, and the page says the margin may be wider or the cause another -
    it does not claim to know which."""
    m = _live_shape_book(tmp_path)
    venue = _MarginVenue(cash=5_600.0, margin=0.40)
    alerts = []
    run_cycle(m, venue, payload(), "2026-08-20", alert=alerts.append)
    assert venue.refused == [("BIL", 46)]
    page = next(a for a in alerts if "intent failed (SWEEP BIL)" in a)
    assert "DO cover it at a 5% margin: either IBKR's margin is wider" in page
    assert not re.search(r"5,?600", page), "the account's cash level leaked"


def test_new_sizing_passes_the_margin_venue_and_settles_on_the_reserve(tmp_path, shipped):
    m = _live_shape_book(tmp_path)
    venue = _MarginVenue(cash=5_600.0)
    alerts = []
    for _ in range(4):
        run_cycle(m, venue, payload(), "2026-08-20", alert=alerts.append)
    assert venue.refused == [], f"refused: {venue.refused}"
    assert not [a for a in alerts if "intent failed" in a]
    buys = [o for o in venue.orders_log() if o["symbol"] == "BIL" and o["qty"] > 0] \
        if hasattr(venue, "orders_log") else None
    # 46 sh (4,888 // 105 with the $712 reserve), then 2 sh, then nothing
    assert m.state.bil_qty == 300 + 46 + 2
    reserve = LIVE_RESERVE * m.sleeve_value(PRICES)
    assert reserve <= m.state.sleeve_cash < reserve + 100.0 * (1 + LIVE_CUSHION)
    assert buys is None or len(buys) == 2


# --- sizing ------------------------------------------------------------------------

def test_seed_sizes_core_and_sweep_with_cushion_and_reserve(tmp_path, shipped):
    m = mk(tmp_path)                                  # $10,000 book, 30/70
    out = m.step("2026-08-20", payload(), PRICES)
    (core,) = [o for o in out if o["action"] == "CORE_BUY"]
    (sweep,) = _sweeps(out)
    assert core["qty"] == 66                          # 7,000 // 105
    assert sweep["qty"] == 28                         # (3,000 - 60) // 105
    assert sweep["reserve_usd"] == pytest.approx(60.0)


def test_overnight_headroom_and_cushion_compound_on_the_core_buy(tmp_path, shipped,
                                                                 monkeypatch):
    monkeypatch.setattr(blend_mod, "CORE_BUY_OVERNIGHT_HEADROOM", 0.01)
    m = mk(tmp_path)
    (core,) = [o for o in m.step("2026-08-20", payload(), PRICES)
               if o["action"] == "CORE_BUY"]
    assert core["qty"] == int(7_000.0 // (100.0 * 1.01 * 1.05)) == 66


def test_core_buys_converge_without_ever_spending_the_last_dollar(tmp_path, shipped):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=0.0, bil_qty=30, spy_qty=40, core_cash=3_000.0)
    venue = _MarginVenue(cash=3_000.0)
    bought = []
    for _ in range(4):
        before = m.state.spy_qty
        run_cycle(m, venue, payload(), "2026-08-20", alert=lambda _a: None)
        bought.append(m.state.spy_qty - before)
    assert venue.refused == []
    assert bought[:2] == [28, 1] and sum(bought[2:]) == 0     # 3,000//105, 200//105
    assert 0.0 <= m.state.core_cash <= 100.0


def test_sweep_never_dips_into_the_reserve_and_dust_is_left_alone(tmp_path, shipped):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=500.0, bil_qty=25, spy_qty=70)
    (sw,) = _sweeps(m.step("2026-08-20", payload(), PRICES))
    # sleeve 3,000 -> reserve 60; (500 - 60) // 105 = 4
    assert sw["qty"] == 4 and sw["reserve_usd"] == pytest.approx(60.0)
    m.state.sleeve_cash = 150.0                  # 150 - 60 = 90 < one share
    assert not _sweeps(m.step("2026-08-20", payload(), PRICES))


def test_budget_cap_still_binds_after_the_cushion(tmp_path, shipped):
    # gross = 70 SPY + 20 BIL = $9,000; sleeve $3,000 -> reserve $60
    free = mk(tmp_path / "free")
    _seed_initialized(free, sleeve_cash=1_000.0, bil_qty=20, spy_qty=70)
    (sw_free,) = _sweeps(free.step("2026-08-20", payload(), PRICES))
    assert sw_free["qty"] == 8                   # (1,000 - 60) // 105
    capped = mk(tmp_path / "capped", blend_budget=9_300.0)
    _seed_initialized(capped, sleeve_cash=1_000.0, bil_qty=20, spy_qty=70)
    (sw_cap,) = _sweeps(capped.step("2026-08-20", payload(), PRICES))
    assert sw_cap["qty"] == 3                    # $300 of gross headroom // $100


# --- entries, the pre-fund hold, the top-up --------------------------------------

def test_entries_are_funded_past_the_reserve_with_bil(tmp_path, shipped):
    """$280 of cash, a $250 entry: without the reserve the cash pays for it
    and nothing is sold; with it the plan sells BIL so the reserve survives
    the entry - the venue headroom for the MOO's own credit check."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=280.0, bil_qty=30, spy_qty=70)
    out = m.step("2026-08-20", payload(entries=[entry()], stops=[stop_row()]), PRICES)
    (enter,) = [o for o in out if o["action"] == "ENTER"]
    sells = _sweeps(out, sign=-1)
    assert enter["qty"] == 5 and len(sells) == 1
    cash_after = 280.0 - sells[0]["qty"] * 100.0 - enter["qty"] * 50.0
    assert cash_after >= LIVE_RESERVE * m.sleeve_value(PRICES) - 1e-9


def test_pinned_suite_keeps_the_pre_change_entry_funding(tmp_path):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=280.0, bil_qty=30, spy_qty=70)
    out = m.step("2026-08-20", payload(entries=[entry()], stops=[stop_row()]), PRICES)
    assert [o for o in out if o["action"] == "ENTER"] and not _sweeps(out, sign=-1)


def test_prefund_hold_and_reserve_coexist_without_reswept_cash(tmp_path, shipped,
                                                              monkeypatch):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=10.0, bil_qty=30)
    a = SessionDryAdapter()
    alerts = []
    pl = payload(entries=[entry()], stops=[stop_row()])
    monkeypatch.setattr(blend_mod, "reference_prices", lambda *_a, **_k: PRICES)
    cyc = lambda *t: _session_cycle(m, a, pl, alerts, monkeypatch, *t)   # noqa: E731
    cyc(2026, 8, 20, 10, 35)                 # in session: pre-fund the post-close MOO
    sells = [o for o in a.orders("BIL") if o["qty"] < 0]
    assert len(sells) == 1 and m.state.bil_qty == 26     # $250 + the $60 reserve
    cyc(2026, 8, 20, 11, 0)
    cyc(2026, 8, 20, 14, 0)
    assert len(a.orders("BIL")) == 1, "raised again or swept the hold/reserve back"
    cyc(2026, 8, 20, 20, 5)                  # after extended hours: the MOO
    (moo,) = a.orders(order_type="MOO")
    assert moo["status"] == "working"
    reserve = LIVE_RESERVE * m.sleeve_value(PRICES)
    assert m.state.sleeve_cash - m.reserved_sleeve_cash() >= reserve - 1e-6


def test_reserve_top_up_sells_bil_once(tmp_path, shipped):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=10.0, bil_qty=30, spy_qty=70)
    a = DryAdapter()
    run_cycle(m, a, payload(), "2026-08-20", alert=lambda _a: None)
    assert m.state.bil_qty == 29                 # reserve 60.2 - 10 -> one share
    out = m.step("2026-08-20", payload(), PRICES)
    assert not _sweeps(out, sign=-1) and not _sweeps(out), "top-up churns"


def test_a_blocked_top_up_is_not_an_overdraw(tmp_path, shipped):
    """No BIL to sell (the sleeve is a held position + $10): the reserve
    cannot be restored this cycle. That is not a negative ledger - no RED
    belt event, no order. Sleeve 30.1%, inside the band: no rebalance."""
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=3_010.0, bil_qty=0, spy_qty=70)
    _held_position(m, qty=60, fill=50.0)         # $3,000 of CRSP, $10 cash left
    assert m.state.sleeve_cash == pytest.approx(10.0)
    out = m.step("2026-08-20", payload(), PRICES)
    assert not [o for o in out if o["action"] in ("SWEEP", "REBALANCE", "CORE_BUY")]
    assert not [e for e in m.state.events if "still negative" in e["msg"]]


# --- execution clamps ----------------------------------------------------------------

def _forced_plan(m, monkeypatch, intents):
    monkeypatch.setattr(m, "step", lambda *_a, **_k: [dict(i) for i in intents])


def test_execution_clamps_use_the_cushion_and_the_reserve(tmp_path, shipped, monkeypatch):
    m = mk(tmp_path)
    _seed_initialized(m, sleeve_cash=3_000.0, bil_qty=0, spy_qty=40, core_cash=3_000.0)
    _forced_plan(m, monkeypatch, [
        {"action": "CORE_BUY", "symbol": "SPY", "qty": 30, "reason": "t"},
        {"action": "SWEEP", "symbol": "BIL", "qty": 30, "reserve_usd": 60.0, "reason": "t"},
    ])
    a = DryAdapter()
    run_cycle(m, a, payload(), "2026-08-20", alert=lambda _a: None)
    assert m.state.spy_qty == 40 + 28            # 3,000 // 105
    assert m.state.bil_qty == 28                 # (3,000 - 60) // 105


# --- the refusal note ----------------------------------------------------------------

class _CashAnswer:
    def __init__(self, avail=None, raises=False):
        self.avail, self.raises = avail, raises

    def account_cash(self):
        if self.raises:
            raise RuntimeError("gateway down")
        return {"total_cash": 1.0, "net_liq": None, "available_funds": self.avail}


@pytest.mark.parametrize("avail, want", [
    (5_600.0, "do NOT cover it at a 5% market-order margin"),
    (9_999.0, "DO cover it at a 5% margin: either IBKR's margin is wider"),
    (None, "neither confirmed nor ruled out"),
])
def test_refusal_note_is_a_yes_no_that_never_publishes_the_cash(avail, want, shipped):
    note = blend_mod._buy_refusal_note(_CashAnswer(avail), 56, 100.0)
    assert want in note
    if avail is not None:
        for s in (f"{avail:,.0f}", f"{avail:.0f}", f"{avail:,.2f}"):
            assert s not in note
    assert "neither confirmed" in blend_mod._buy_refusal_note(_CashAnswer(raises=True), 56, 100.0)


class _Raising:
    def __init__(self, exc):
        self.exc = exc

    def place_stock_order(self, *a, **k):
        raise self.exc

    def account_cash(self):
        return {"total_cash": 1.0, "available_funds": 0.0}


def test_place_market_buy_annotates_only_a_reasonless_inactive(shipped):
    with pytest.raises(RuntimeError, match="do NOT cover"):
        blend_mod._place_market_buy(_Raising(RuntimeError(
            "order rejected by venue (status Inactive): IBKR gave no reason")),
            "BIL", 56, 100.0, "c1")
    reasoned = RuntimeError("order rejected by venue (status Cancelled): [201] x")
    with pytest.raises(RuntimeError) as ei:
        blend_mod._place_market_buy(_Raising(reasoned), "BIL", 56, 100.0, "c2")
    assert ei.value is reasoned
    down = ExecutorConnectionError("could not connect to IB gateway")
    with pytest.raises(ExecutorConnectionError) as ei2:
        blend_mod._place_market_buy(_Raising(down), "BIL", 56, 100.0, "c3")
    assert ei2.value is down
