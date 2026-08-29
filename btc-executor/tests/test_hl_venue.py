"""Gates for the Hyperliquid venue adapter (app/hl.py).

Two classes of test here:
  1. CONTRACT gates - hl.HyperliquidVenue must satisfy the same Venue
     protocol, with the same hard-won semantics, as cb.CoinbaseVenue. Every
     one of these corresponds to a finding that cost real money on Coinbase.
  2. The SDK-EXISTENCE gate - an AST walk asserting every SDK method this
     adapter calls actually exists on the installed SDK. This is the test
     that would have caught `get_intx_position` (a method present in NO
     published version of coinbase-advanced-py) before it blinded the
     executor for three days. It ships WITH the adapter this time, not
     after the incident.
"""
from __future__ import annotations

import ast
import sys
import types

import pytest


# --------------------------------------------------------------------------
# A fake SDK, installed into sys.modules, so the suite never needs the real
# one and never touches the network.
class _FakeCloid:
    def __init__(self, raw):
        if not raw.startswith("0x") or len(raw[2:]) != 32:
            raise TypeError("cloid is not 16 bytes")
        self._raw = raw

    @staticmethod
    def from_str(s):
        return _FakeCloid(s)

    def to_raw(self):
        return self._raw

    def __eq__(self, other):
        return isinstance(other, _FakeCloid) and other._raw == self._raw

    def __hash__(self):
        return hash(self._raw)

    def __repr__(self):
        return self._raw


class _FakeInfo:
    def __init__(self, *a, **kw):
        self.state = {"marginSummary": {"accountValue": "50000.0"},
                      "assetPositions": []}
        self.mids = {"BTC": "80000.0"}
        self.orders: dict[str, dict] = {}      # raw cloid -> order record
        self.resting: list[dict] = []
        self.raise_on_state = None
        self.abstraction = "unifiedAccount"
        self.spot_usdc = 0.0
        # the signer (_Acct.address) approved as an agent, in the venue's
        # own shape: ms epoch, and MIXED CASE, because Hyperliquid does not
        # promise the checksum casing our config carries
        self.agents = [{"name": "BTC EXECUTOR",
                        "address": "0xDEADbeefDEADbeefDEADbeefDEADbeefDEADbeef",
                        "validUntil": 1_803_483_076_101}]
        # what userRole says about the SIGNER. Default: an ordinary
        # address that is nobody's agent.
        self.role = {"role": "user"}

    def meta(self, dex=""):
        return {"universe": [{"name": "BTC", "szDecimals": 5,
                              "maxLeverage": 40},
                             {"name": "ETH", "szDecimals": 4}]}

    def user_state(self, address, dex=""):
        if self.raise_on_state:
            raise RuntimeError(self.raise_on_state)
        return self.state

    def all_mids(self, dex=""):
        return self.mids

    def query_order_by_cloid(self, user, cloid):
        rec = self.orders.get(cloid.to_raw())
        if rec is None:
            return {"status": "unknownOid"}
        return {"status": "order", "order": rec}

    def open_orders(self, address, dex=""):
        return self.resting

    def query_user_abstraction_state(self, user):
        return self.abstraction

    def spot_user_state(self, address):
        return {"balances": [{"coin": "USDC", "total": str(self.spot_usdc)}]}

    def extra_agents(self, user):
        return self.agents

    def user_role(self, user):
        return self.role


class _FakeExchange:
    def __init__(self, *a, **kw):
        self.sent: list[dict] = []
        self.cancelled: list[str] = []
        self.bulk_cancelled: list[list] = []
        self.reject = None

    def order(self, name, is_buy, sz, limit_px, order_type,
              reduce_only=False, cloid=None, builder=None):
        self.sent.append({"coin": name, "is_buy": is_buy, "sz": sz,
                          "limit_px": limit_px, "order_type": order_type,
                          "reduce_only": reduce_only,
                          "cloid": cloid.to_raw() if cloid else None})
        if self.reject:
            return {"status": "ok", "response": {"data": {
                "statuses": [{"error": self.reject}]}}}
        return {"status": "ok", "response": {"data": {
            "statuses": [{"resting": {"oid": len(self.sent)}}]}}}

    def cancel_by_cloid(self, name, cloid):
        self.cancelled.append(cloid.to_raw())
        return {"status": "ok"}

    def bulk_cancel_by_cloid(self, reqs):
        self.bulk_cancelled.append(reqs)
        return {"status": "ok"}

    def cancel(self, name, oid):
        self.cancelled.append(f"oid:{oid}")
        return {"status": "ok"}


@pytest.fixture
def venue(monkeypatch):
    """Build HyperliquidVenue through its REAL __init__ against a fake SDK."""
    ex_mod = types.ModuleType("hyperliquid.exchange")
    ex_mod.Exchange = _FakeExchange
    info_mod = types.ModuleType("hyperliquid.info")
    info_mod.Info = _FakeInfo
    types_mod = types.ModuleType("hyperliquid.utils.types")
    types_mod.Cloid = _FakeCloid
    const_mod = types.ModuleType("hyperliquid.utils.constants")
    const_mod.MAINNET_API_URL = "https://api.hyperliquid.xyz"
    const_mod.TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"
    utils_mod = types.ModuleType("hyperliquid.utils")
    utils_mod.constants = const_mod
    utils_mod.types = types_mod
    pkg = types.ModuleType("hyperliquid")
    pkg.exchange, pkg.info, pkg.utils = ex_mod, info_mod, utils_mod
    eth_mod = types.ModuleType("eth_account")

    class _Acct:
        address = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

        @staticmethod
        def from_key(k):
            return _Acct()
    eth_mod.Account = _Acct
    for name, mod in (("hyperliquid", pkg), ("hyperliquid.exchange", ex_mod),
                      ("hyperliquid.info", info_mod),
                      ("hyperliquid.utils", utils_mod),
                      ("hyperliquid.utils.types", types_mod),
                      ("hyperliquid.utils.constants", const_mod),
                      ("eth_account", eth_mod)):
        monkeypatch.setitem(sys.modules, name, mod)

    from app.hl import HyperliquidVenue

    class Cfg:
        hl_secret_key = "0x" + "11" * 32
        # the MAIN account, deliberately DIFFERENT from the signer: an agent
        # wallet signs for an account it is not
        hl_account_address = "0xMAIN0000000000000000000000000000000000ac"
        hl_coin = "BTC"
        hl_testnet = True
    return HyperliquidVenue(Cfg())


# --------------------------------------------------------------------------
# THE gate: never call an SDK method that does not exist.
def test_gate_hl_calls_only_real_sdk_methods():
    """The test that would have caught the incident at merge. `cb.py` called
    `get_intx_position`, which exists in NO published version of the
    Coinbase SDK; it had never once executed successfully, and its failure
    is what made "flat" and "broken" indistinguishable for three days. This
    adapter ships with the equivalent gate from day one."""
    ex = pytest.importorskip("hyperliquid.exchange",
                             reason="hyperliquid SDK not installed")
    info = pytest.importorskip("hyperliquid.info")
    import app.hl as hlmod
    tree = ast.parse(open(hlmod.__file__).read())
    called: dict[str, set] = {"exchange": set(), "info": set()}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
            if node.value.attr in called:
                called[node.value.attr].add(node.attr)
    assert called["exchange"] and called["info"], "expected SDK calls in hl.py"
    missing = ([m for m in sorted(called["exchange"])
                if not hasattr(ex.Exchange, m)]
               + [m for m in sorted(called["info"])
                  if not hasattr(info.Info, m)])
    assert not missing, f"hl.py calls SDK methods that do not exist: {missing}"


# --------------------------------------------------------------------------
# Contract gates, each mapped to a Coinbase finding.
def test_gate_stops_are_always_reduce_only(venue):
    """THE reason for the venue change. On Coinbase place_stop was not
    reduce-only, so a stop the venue could not back OPENED a position -
    every naked-stop finding in the 2026-08 chain descends from that one
    fact. If this assertion ever fails, the entire rationale is gone."""
    venue.place_stop("SELL", 0.01, 74_000.0, "T-1-S74000-1")
    sent = venue.exchange.sent[-1]
    assert sent["reduce_only"] is True, "protective stop is not reduce-only"
    assert sent["order_type"]["trigger"]["tpsl"] == "sl"
    assert sent["order_type"]["trigger"]["isMarket"] is True
    assert sent["order_type"]["trigger"]["triggerPx"] == 74_000.0


def test_gate_entries_are_not_reduce_only(venue):
    """Symmetry check: an ENTRY marked reduce-only would silently never
    fill on a flat book - the mirror would believe in a position that can
    never exist. Wrong in the opposite direction, equally fatal."""
    venue.place_limit("BUY", 0.01, 79_000.0, "P-1-E1")
    venue.place_market("BUY", 0.01, "P-1-C1")
    assert all(s["reduce_only"] is False for s in venue.exchange.sent)


def test_gate_flat_is_unambiguous_and_errors_raise(venue):
    """Coinbase omitted flat products, so 'flat' and 'the read failed' were
    the SAME response - the ambiguity that blinded the executor for three
    days. Here a clean response with no row for our coin is a CONFIRMED
    flat; only a genuine failure raises."""
    venue.info.state = {"marginSummary": {"accountValue": "50000"},
                        "assetPositions": []}
    assert venue.position() == 0.0
    venue.info.state["assetPositions"] = [
        {"position": {"coin": "ETH", "szi": "3.0"}}]
    assert venue.position() == 0.0, "another coin's position leaked in"
    venue.info.raise_on_state = "api down"
    with pytest.raises(RuntimeError):
        venue.position()


def test_gate_position_is_signed_no_side_guessing(venue):
    """cb.py had to infer sign from a `side` string and refused to guess on
    UNKNOWN. szi is already signed - there is nothing to guess."""
    for szi, want in (("0.34", 0.34), ("-0.14", -0.14)):
        venue.info.state = {"marginSummary": {"accountValue": "50000"},
                            "assetPositions": [
                                {"position": {"coin": "BTC", "szi": szi}}]}
        assert venue.position() == pytest.approx(want)


def test_gate_order_status_never_returns_bare_none_on_error(venue,
                                                            monkeypatch):
    """An API failure is NOT 'no such order'. Resolving that ambiguity in
    whichever direction let the caller proceed is what armed a duplicate
    stop on Coinbase."""
    def _boom(*a, **kw):
        raise RuntimeError("api down")
    monkeypatch.setattr(venue.info, "query_order_by_cloid", _boom)
    st = venue.order_status("T-1-S74000-1")
    assert st is not None and st["status"] == "UNKNOWN"


def test_gate_transitional_status_is_open_not_cancelled(venue):
    """A transitional order read as CANCELLED provokes a duplicate stop -
    the Coinbase QUEUED lesson, which applies unchanged here."""
    raw = venue._sdk_cloid("T-1")
    for state, want in (("open", "OPEN"), ("queued", "OPEN"),
                        ("triggered", "OPEN"), ("filled", "FILLED"),
                        ("canceled", "CANCELLED"), ("rejected", "CANCELLED")):
        venue.info.orders[raw] = {"status": state,
                                  "order": {"origSz": "0.01", "sz": "0.01"}}
        assert venue.order_status("T-1")["status"] == want, state


def test_gate_unmapped_status_is_unknown_not_assumed(venue):
    """A status the venue adds later must read UNKNOWN, never silently
    bucket as terminal."""
    venue.info.orders[venue._sdk_cloid("T-9")] = {
        "status": "someNewStateWeHaveNeverSeen",
        "order": {"origSz": "0.01", "sz": "0.01"}}
    assert venue.order_status("T-9")["status"] == "UNKNOWN"


def test_gate_cloid_is_deterministic_and_valid(venue):
    """Deterministic derivation replaces cb_order_map.json entirely. The
    handle to a live order is recomputable on any process after any crash,
    so a non-atomic map write can no longer lose it (fast-follow F4, gone
    rather than fixed)."""
    from app.hl import derive_cloid
    a, b = derive_cloid("T-1787155200-S74152-1"), derive_cloid("T-1787155200-S74152-1")
    assert a == b, "cloid derivation is not deterministic"
    assert a.startswith("0x") and len(a) == 34
    assert derive_cloid("T-1787155200-S74152-2") != a, "salt collision"
    _FakeCloid.from_str(a)          # must satisfy the SDK's own validator


def test_gate_quantize_rounds_down_never_up(venue):
    """The executor may under-fill its target but must NEVER size above it -
    a round-up turned a 0.466-contract chase into a full contract on
    Coinbase, more than double the intent."""
    assert venue.quantize(0.0199999) <= 0.0199999
    assert venue.quantize(0.123456789) == pytest.approx(0.12345, abs=1e-9)
    assert venue.quantize(0.000001) == 0.0
    with pytest.raises(ValueError):
        venue._sz(0.000001)         # sub-lot must fail LOUD, not inflate


def test_gate_rejected_order_raises_not_silently_ok(venue):
    """HL returns status 'ok' with a per-order error inside. Treating that
    envelope as success would book a fill that never happened - which is
    exactly how the phantom position got into the ledger."""
    venue.exchange.reject = "Insufficient margin"
    with pytest.raises(RuntimeError, match="Insufficient margin"):
        venue.place_market("BUY", 0.01, "T-1-C1")


def test_gate_post_only_cross_retries_and_is_recorded(venue):
    """Short entries at a positive basis get Alo-rejected; crossing fills at
    our limit or better. The cross is recorded for the ramp's coverage row."""
    calls = {"n": 0}
    real = venue.exchange.order

    def _flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"status": "ok", "response": {"data": {"statuses": [
                {"error": "Post only order would have immediately matched"}]}}}
        return real(*a, **kw)
    venue.exchange.order = _flaky
    venue.place_limit("SELL", 0.01, 80_000.0, "P-1-E1")
    assert venue.post_only_crosses == ["P-1-E1"]
    assert venue.exchange.sent[-1]["order_type"]["limit"]["tif"] == "Gtc"


def test_gate_open_orders_sweep_sees_forgotten_orders(venue):
    """The F1 sweep, native. This is the ONLY check that can catch an armed
    order the ledger has forgotten on a hedged book, where a position read
    reports 0 whether the legs are real or phantom."""
    venue.info.resting = [
        {"coin": "BTC", "oid": 1, "cloid": venue._sdk_cloid("T-1-S74000-1"),
         "side": "A", "sz": "0.01", "limitPx": "73000", "triggerPx": "74000",
         "reduceOnly": True},
        {"coin": "ETH", "oid": 2, "cloid": None, "side": "B", "sz": "1",
         "limitPx": "3000"}]
    got = venue.open_orders()
    assert len(got) == 1 and got[0]["side"] == "SELL"
    assert got[0]["reduce_only"] is True and got[0]["trigger_px"] == 74_000.0


def test_gate_configured_coin_always_in_the_banner(venue):
    """A diagnostic banner that can omit the thing we trade misdirected a
    live incident diagnosis once already (2026-08-27, BIP-20DEC30-CDE)."""
    rows = venue.list_perp_candidates()
    assert any("BTC" in r and "(configured)" in r for r in rows), rows
    venue.coin = "NOTACOIN"
    rows = venue.list_perp_candidates()
    assert any("NOTACOIN" in r and "NOT FOUND" in r for r in rows), rows


def test_gate_unknown_coin_fails_at_construction(monkeypatch, venue):
    """Config pointing at a coin the venue does not list must fail LOUD at
    boot, not one rejected order at a time."""
    venue.coin = "NOTACOIN"
    with pytest.raises(RuntimeError, match="not in the Hyperliquid perp"):
        venue._coin_meta()


def test_gate_account_address_is_mandatory(monkeypatch, venue):
    """THE agent-wallet trap, and the reason this is a hard failure rather
    than a default. An agent wallet SIGNS for a main account but HOLDS
    NOTHING itself - Hyperliquid's own UI says "the account's public address
    must be used for info requests". Falling back to the signer would query
    the AGENT, find no positions, and return 0.0 as a CONFIRMED FLAT forever
    while the real account carried the book: the 2026-08-26 phantom-position
    failure mode, re-entered through config."""
    from app.hl import HyperliquidVenue

    class Blank:
        hl_secret_key = "0x" + "11" * 32
        hl_account_address = ""
        hl_coin = "BTC"
        hl_testnet = True
    with pytest.raises(RuntimeError, match="HL_ACCOUNT_ADDRESS is required"):
        HyperliquidVenue(Blank())


def test_gate_reads_target_the_main_account_not_the_signer(venue):
    """Positions must be read for the MAIN account. If this ever regresses to
    the signer's address the book reads permanently flat."""
    assert venue.address == "0xMAIN0000000000000000000000000000000000ac"
    seen = {}
    real = venue.info.user_state

    def _spy(addr, dex=""):
        seen["addr"] = addr
        return real(addr, dex)
    venue.info.user_state = _spy
    venue.position()
    assert seen["addr"] == "0xMAIN0000000000000000000000000000000000ac"


# ---------------------------------------------------------------------------
# 2026-08-28, caught before the first live order: Hyperliquid keeps TWO USDC
# pools and marginSummary.accountValue reports only the perp one. It read
# $0.00 against a real $998.99 in spot.
def test_gate_equity_includes_spot_under_a_unified_account(venue):
    """Every circuit breaker is equity-derived. A constant zero makes every
    loss compute as zero, so NO HALT CAN EVER FIRE - and sizing would have
    looked fine, because SIZING_BASE_USD is a fixed number. The book would
    have traded correctly with its rails silently absent."""
    venue.info.abstraction = "unifiedAccount"
    venue.info.state = {"marginSummary": {"accountValue": "0.0"},
                        "assetPositions": []}
    venue.info.spot_usdc = 998.99528
    assert venue.equity() == pytest.approx(998.99528), \
        "equity blind to spot under a unified account -> halts dead"


def test_gate_equity_excludes_spot_when_not_unified(venue):
    """The opposite error loosens the rails. With separate pools spot does
    NOT back perps, so counting it would overstate what is at risk."""
    venue.info.abstraction = "disabled"
    venue.info.state = {"marginSummary": {"accountValue": "250.0"},
                        "assetPositions": []}
    venue.info.spot_usdc = 48_000.0
    assert venue.equity() == pytest.approx(250.0), \
        "counted spot as perp collateral on a non-unified account"


def test_gate_unreadable_abstraction_raises_rather_than_guessing(venue):
    """A silent default here either kills the halts or loosens them. An
    unreadable venue is a first-class condition everywhere else in this
    codebase; it is one here too."""
    def _boom(user):
        raise RuntimeError("info endpoint down")
    venue.info.query_user_abstraction_state = _boom
    venue.info.state = {"marginSummary": {"accountValue": "100.0"},
                        "assetPositions": []}
    with pytest.raises(RuntimeError, match="info endpoint down"):
        venue.equity()


def test_gate_abstraction_is_cached_not_polled_per_call(venue):
    """One extra /info call per equity read is fine; one per anything else
    is not. Cached for 60s, and the cache must not mask a real change
    forever."""
    calls = {"n": 0}
    real = venue.info.query_user_abstraction_state

    def _count(user):
        calls["n"] += 1
        return real(user)
    venue.info.query_user_abstraction_state = _count
    venue.info.spot_usdc = 100.0
    for _ in range(5):
        venue.equity()
    assert calls["n"] == 1, f"queried abstraction {calls['n']}x for 5 reads"
    venue._abs_cache = (0.0, True)          # expire
    venue.equity()
    assert calls["n"] == 2, "cache never expires"


# --------------------------------------------------------------------------
# Agent-wallet expiry (HL-3). Hyperliquid API wallets expire on a date the
# venue will tell us; past it EVERY order is rejected, protective ones
# included. That is the naked-position failure with a calendar on it.
def test_gate_agent_expiry_is_read_and_converted_from_ms(venue):
    """The venue reports ms; the rails think in seconds. An unconverted
    value is ~57000x too large, i.e. 'expires in 55 million days' - a
    warning that can never fire, which is the same as no rail at all."""
    assert venue.agent_valid_until() == pytest.approx(1_803_483_076.101), \
        "agent expiry not converted from the venue's milliseconds"


def test_gate_agent_matched_by_address_not_display_name(venue):
    """The name is operator-chosen, editable, and duplicable in the HL UI.
    A name match can point at a DIFFERENT key than the one we sign with -
    reporting a healthy expiry for a wallet we do not use, while ours dies."""
    venue.info.agents = [{"name": "BTC EXECUTOR",       # our name...
                          "address": "0x" + "ab" * 20,  # ...someone else's key
                          "validUntil": 9_999_999_999_000}]
    assert venue.agent_valid_until() == 0.0, \
        "matched an agent row by NAME - reported a key we cannot sign with"


def test_gate_revoked_agent_reads_as_expired_not_healthy(venue):
    """A clean response that does not list us is DEFINITIVE: revoked, never
    approved, or HL_SECRET_KEY belongs to another wallet. No order will
    ever succeed, so it must reach the expiry rail, not a silent pass."""
    venue.info.agents = []
    assert venue.agent_valid_until() == 0.0, \
        "an unlisted (revoked) agent read as having no expiry"


def test_gate_unreadable_agent_list_raises_rather_than_reporting_healthy(venue):
    """Unreadable is not absent. Returning None here would mean 'this key
    never expires', permanently disarming the rail on a transient outage."""
    def _boom(user):
        raise RuntimeError("info endpoint down")
    venue.info.extra_agents = _boom
    with pytest.raises(RuntimeError, match="info endpoint down"):
        venue.agent_valid_until()


def test_gate_main_account_key_has_no_expiry(venue):
    """Trading with the main account's own key is a valid (less safe) setup
    and cannot expire. It must not be reported as expired-now, which would
    halt a perfectly healthy book forever."""
    venue.address = venue.agent_address        # signer IS the account
    assert venue.agent_valid_until() is None


# --------------------------------------------------------------------------
# The $10 floor. Hyperliquid refuses any order under $10 notional and does
# NOT document a reduce-only exemption, so a sub-$10 position cannot be
# closed by its stop OR by the halt's flatten.
def test_gate_min_notional_rejection_is_its_own_error(venue):
    """A generic 'order rejected' on the protective path reads as a venue
    hiccup and gets retried. This one is not retryable at any size - the
    page has to say so, or the operator debugs the wrong thing while an
    unprotected residue sits open."""
    from app.hl import MinNotionalRejected
    venue.exchange.reject = "Order must have minimum value of $10."
    with pytest.raises(MinNotionalRejected, match="cannot be closed by ANY"):
        venue.place_stop("SELL", 0.00001, 74_000.0, "T-1-S74000-1")


def test_gate_other_rejections_stay_generic(venue):
    """Only the floor gets the special type. Widening it would relabel
    ordinary rejections as unrecoverable."""
    from app.hl import MinNotionalRejected
    venue.exchange.reject = "Insufficient margin to place order."
    with pytest.raises(RuntimeError) as e:
        venue.place_market("SELL", 0.01, "T-1-X1")
    assert not isinstance(e.value, MinNotionalRejected)


def test_gate_agent_unapproved_key_names_both_addresses(venue):
    """The rail's first live boot returned the not-in-the-list sentinel and
    the operator saw 'agent_days_left: -20693' - a description of the
    arithmetic, not of the fault. The two addresses ARE the diagnosis: what
    we sign with, and what the account actually approved."""
    venue.info.agents = [{"name": "BTC EXECUTOR",
                          "address": "0x" + "ab" * 20,
                          "validUntil": 9_999_999_999_000}]
    assert venue.agent_valid_until() == 0.0
    note = venue.agent_note
    assert venue.agent_address.lower() in note.lower(), "signer not named"
    assert ("0x" + "ab" * 20) in note.lower(), "approved agent not named"
    assert venue.address.lower() in note.lower(), "main account not named"


def test_gate_agent_note_clears_once_the_key_matches(venue):
    """A stale note would keep explaining a fault that is fixed, and the
    halt page prefers the note over the date."""
    venue.info.agents = []
    venue.agent_valid_until()
    assert venue.agent_note
    venue.info.agents = [{"name": "BTC EXECUTOR",
                          "address": venue.agent_address,
                          "validUntil": 1_803_483_076_101}]
    venue.agent_valid_until()
    assert venue.agent_note is None, "note survived the fix"


# --------------------------------------------------------------------------
# extraAgents lists only the NAMED agents. approveAgent with the agentName
# field ABSENT creates the unnamed/default API wallet, which is just as able
# to trade and simply is not in that list. The first cut of this rail read
# absence as "not approved" and would have halted a healthy book.
def test_gate_agent_unnamed_default_wallet_is_not_treated_as_unapproved(venue):
    """A valid unnamed API wallet must NOT reach the halt. Halting a book
    whose key signs fine is the self-inflicted damage the unreadable branch
    exists to avoid."""
    venue.info.agents = []                      # named list is empty...
    venue.info.role = {"role": "agent",         # ...but we ARE its agent
                       "data": {"user": venue.address}}
    with pytest.raises(RuntimeError, match="UNNAMED"):
        venue.agent_valid_until()
    assert venue.agent_note is None, "flagged a valid key as a mismatch"


def test_gate_agent_role_for_a_different_master_is_still_unapproved(venue):
    """role=agent is not enough: an agent of SOMEONE ELSE'S account cannot
    trade ours. The master must match, or absence stays definitive."""
    venue.info.agents = []
    venue.info.role = {"role": "agent", "data": {"user": "0x" + "cd" * 20}}
    assert venue.agent_valid_until() == 0.0
    assert venue.agent_note, "no diagnosis for a foreign-account agent"


def test_gate_agent_plain_user_role_is_unapproved(venue):
    """The genuine mismatch case still reports as expired-now."""
    venue.info.agents = []
    venue.info.role = {"role": "user"}
    assert venue.agent_valid_until() == 0.0
    assert venue.agent_note


def test_gate_agent_named_match_never_consults_user_role(venue):
    """The precise path must win: a named match carries validUntil, and an
    extra /info call per check for nothing is waste."""
    called = {"n": 0}

    def _role(user):
        called["n"] += 1
        return {"role": "user"}
    venue.info.user_role = _role
    assert venue.agent_valid_until() == pytest.approx(1_803_483_076.101)
    assert called["n"] == 0, "queried userRole despite a named match"


# --------------------------------------------------------------------------
# WHICH NETWORK (2026-08-28). HL_TESTNET was truthy in production, so every
# info call answered about a different chain: extraAgents empty, userRole
# 'missing', and the agent rail concluded "your key is not approved" about a
# key that is properly approved on mainnet.
def test_gate_network_is_recorded_not_just_used(venue):
    """The fixture config sets hl_testnet=True. If the choice is only ever a
    local variable, nothing downstream can publish or check it - which is
    exactly why it stayed invisible through three rounds of diagnosis."""
    assert venue.network == "testnet"
    assert venue.testnet is True


def test_gate_mainnet_is_the_default_and_is_labelled(monkeypatch):
    import app.hl as hlmod

    class Cfg:
        hl_secret_key = "0x" + "11" * 32
        hl_account_address = "0xMAIN0000000000000000000000000000000000ac"
        hl_coin = "BTC"
        # hl_testnet deliberately ABSENT: the default must be mainnet, and
        # must still be labelled rather than left None.
    v = hlmod.HyperliquidVenue(Cfg())
    assert v.network == "mainnet" and v.testnet is False


# --------------------------------------------------------------------------
# PRICE GRID (2026-08-29). Hyperliquid enforces 5 significant figures AND
# (6 - szDecimals) decimals; the SDK applies that rule ONLY inside its own
# _slippage_price helper, and Exchange.order() wires whatever float it gets.
# Every price this adapter sent was off-grid, so every order was destined to
# be rejected - including the halt's flatten.
def _sdk_legal(px, sz_decimals=5):
    """The venue's own rule, from hyperliquid/exchange.py:131-132."""
    return round(float(f"{px:.5g}"), 6 - sz_decimals) == px


def test_gate_every_order_price_is_on_the_venue_grid(venue):
    """The blocker. If any of these prices reaches the wire unrounded the
    venue rejects it, and the order that matters most is the flatten."""
    venue.place_limit("BUY", 0.002, 77123.45, "P-1-E1", post_only=True)
    venue.place_stop("SELL", 0.002, 74880.70, "P-1-S74880-1")
    venue.info.mids = {"BTC": "78010.37"}
    venue.place_market("BUY", 0.00065, "T-1-E1")
    assert venue.exchange.sent, "no orders captured"
    for o in venue.exchange.sent:
        assert _sdk_legal(o["limit_px"]), f"off-grid limit_px {o['limit_px']}"
        trig = (o["order_type"].get("trigger") or {}).get("triggerPx")
        if trig is not None:
            assert _sdk_legal(trig), f"off-grid triggerPx {trig}"


def test_gate_post_only_entry_rounds_away_from_the_market(venue):
    """Snapping a maker bid UP can push it across the spread: the Alo is
    rejected and the retry pays taker. Round away, always."""
    venue.place_limit("BUY", 0.002, 77123.45, "P-1-E1", post_only=True)
    assert venue.exchange.sent[-1]["limit_px"] <= 77123.45
    venue.place_limit("SELL", 0.002, 77123.45, "P-2-E1", post_only=True)
    assert venue.exchange.sent[-1]["limit_px"] >= 77123.45


def test_gate_crossing_bounds_round_toward_aggression(venue):
    """A stop's bound rounded back INSIDE the spread turns a protective
    order into a resting one. That is not protection."""
    venue.place_stop("SELL", 0.002, 74880.70, "P-1-S74880-1")
    sell = venue.exchange.sent[-1]
    assert sell["limit_px"] <= 74880.70 * (1 - 0.02), "sell bound not aggressive"
    venue.place_stop("BUY", 0.002, 80100.30, "T-1-S80100-1")
    buy = venue.exchange.sent[-1]
    assert buy["limit_px"] >= 80100.30 * (1 + 0.02), "buy bound not aggressive"


def test_gate_taker_retry_after_post_only_cross_rounds_into_the_market(venue):
    """The Gtc retry exists to cross. Rounding it away would re-reject it."""
    venue.exchange.reject = "Post only order would have immediately matched"
    real, n = venue.exchange.order, {"i": 0}

    def once(*a, **kw):
        n["i"] += 1
        if n["i"] > 1:                 # only the FIRST (Alo) send is rejected
            venue.exchange.reject = None
        return real(*a, **kw)
    venue.exchange.order = once
    venue.place_limit("BUY", 0.002, 77123.45, "P-1-E1", post_only=True)
    assert n["i"] == 2, "post-only rejection did not trigger the taker retry"
    alo, gtc = venue.exchange.sent[-2], venue.exchange.sent[-1]
    assert alo["limit_px"] <= 77123.45, "maker attempt rounded into the market"
    assert gtc["limit_px"] >= 77123.45, "taker retry rounded away from the market"


def test_gate_price_grid_matches_the_venue_rule_across_magnitudes(venue):
    """Both rules bind, and which one binds depends on price magnitude:
    5 sig figs is $1 at BTC's ~$78k but $0.1 at $7.8k."""
    for raw in (77670.5, 77123.45, 7712.345, 771.2345, 1.234567):
        for mode in ("nearest", "up", "down"):
            v = venue._px(raw, mode)
            assert _sdk_legal(v), f"{raw!r}/{mode} -> {v!r} is off-grid"
            if mode == "up":
                assert v >= venue._px(raw, "nearest") or v >= raw
            if mode == "down":
                assert v <= venue._px(raw, "nearest") or v <= raw


def test_gate_price_snapping_refuses_nonsense(venue):
    for bad in (0, -1.0):
        with pytest.raises(ValueError):
            venue._px(bad)


def test_gate_price_below_the_grid_raises_instead_of_sending_zero(venue):
    """BTC has szDecimals=5, so the perp decimal cap is ONE place: a price
    under $0.05 has no representation and snaps to 0.0. Sending 0.0 as a
    limit or a trigger would be an order at any price - refuse instead."""
    with pytest.raises(ValueError, match="not tradable"):
        venue._px(0.00012345)


def test_gate_equity_does_not_double_count_once_a_position_pledges_margin(venue):
    """The blocker the flat-state fix could not see. HL's docs say the spot
    figure spans spot AND perps under a unified account, so adding
    marginSummary on top double-counts the moment collateral is pledged -
    and equity feeds day_start_equity and high_water, so it would move both
    halt thresholds with it."""
    venue.info.abstraction = "unifiedAccount"
    venue.info.spot_usdc = 999.00
    venue.info.state = {"marginSummary": {"accountValue": "999.00"},
                        "assetPositions": [{"position": {"coin": "BTC",
                                                         "szi": "0.00194"}}]}
    assert venue.equity() == pytest.approx(999.00), \
        "summed both pools: equity reads 2x once a position opens"


def test_gate_equity_records_both_pools_for_the_operator(venue):
    """Whether the unified spot figure carries unrealised perp PnL is
    UNVERIFIED until a live position exists. Keep both numbers so the first
    one settles it instead of being guessed at."""
    venue.info.abstraction = "unifiedAccount"
    venue.info.spot_usdc = 999.00
    venue.info.state = {"marginSummary": {"accountValue": "12.34"},
                        "assetPositions": []}
    venue.equity()
    assert venue.equity_parts == {"perp": 12.34, "spot": 999.00}
