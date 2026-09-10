"""Service + adapter-logic gates: offline mode, auth, kill; pure helpers."""
from fastapi.testclient import TestClient

from app.config import settings
from app.ib_adapter import DryAdapter, pick_expiry, pick_strike, size_combos
from app.service import app
from app import blend as blend_mod


def test_gate_adapter_helpers():
    assert pick_expiry(["20270115", "20270219", "20270319"], "2027-02") == "20270219"
    assert pick_expiry(["20261218"], "2027-02") == "20261218"   # best available
    assert pick_expiry([], "2027-02") is None
    assert pick_strike([2.5, 2.75, 3.0, 3.25], 2.9) == 3.0
    # $10k at $0.55 net debit on NG's 10,000 multiplier -> 1 combo ($5.5k each)
    assert size_combos(10_000, 0.55, 10_000) == 1
    assert size_combos(10_000, 0.04, 1_120) == 223          # sugar-scale
    assert size_combos(10_000, 0.0, 100) == 0               # degenerate quote


def test_gate_dry_adapter_lifecycle():
    a = DryAdapter()
    r = a.open_spread({"underlying": "NG", "kind": "call_spread"}, 9_500)
    assert r["premium"] == 9_500
    assert a.mark(r["order_ref"]) == 9_500
    out = a.close_spread(r["order_ref"])
    assert out["value"] == 9_500
    assert a.mark(r["order_ref"]) is None
    assert [e["action"] for e in a.log] == ["open_spread", "close_spread"]


def test_gate_offline_service_and_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200            # public
        assert c.get("/status").status_code == 401
        assert c.post("/kill").status_code == 401
        r = c.get("/status", params={"token": "sekrit"})
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is True
        assert set(body["ladder"]) == {"NG", "SB", "SLV"}
        # kill halts the ladder even with nothing open
        r = c.post("/kill", params={"token": "sekrit"})
        assert r.json()["halted"] == "KILL"
        r = c.post("/resume", params={"token": "sekrit"})
        assert r.json()["ok"] is True


# --- corrective round: B3 (the open control surface) and the deploy config ---


def test_gate_b3_mutations_refuse_GET(tmp_path, monkeypatch):
    """B3 (live-blocker): `/kill` answered GET, so ANY GET of the URL
    flattened the book — a crawler, a Telegram/Slack link unfurl, a mail
    client prefetch, a browser address-bar prediction. The operator's own
    habit is what made it reachable: the token travels as a QUERY parameter,
    so the tokenised URL is exactly the string that gets pasted into a chat
    that unfurls links. `/resume` is a mutation too and goes the same way.

    Reads stay GET; nothing else about either handler changes."""
    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    with TestClient(app) as c:
        assert c.get("/kill", params={"token": "sekrit"}).status_code == 405
        assert c.get("/resume", params={"token": "sekrit"}).status_code == 405
        # ...and the POST form still works, unchanged
        assert c.post("/kill", params={"token": "sekrit"}
                      ).json()["halted"] == "KILL"
        assert c.post("/resume", params={"token": "sekrit"}).json()["ok"]
        # the reads are untouched
        assert c.get("/health").status_code == 200
        assert c.get("/status", params={"token": "sekrit"}).status_code == 200


def test_gate_b3_an_unset_exec_token_fails_closed_off_offline(monkeypatch):
    """B3: `if settings.exec_token and ...` SHORT-CIRCUITED on a falsy
    token, so an unset EXEC_TOKEN left /status, /kill and /resume
    UNAUTHENTICATED. render.yaml marks EXEC_TOKEN `sync: false` — it is
    dashboard-owned, so an unset or accidentally cleared one is a routine
    misconfiguration, not an exotic one.

    Fail closed in any mode that can reach a broker; OFFLINE (no
    credentials, no gateway, no orders) stays open by explicit scope."""
    import pytest
    from fastapi import HTTPException

    from app import service

    monkeypatch.setattr(settings, "exec_token", "")
    monkeypatch.setattr(settings, "tws_userid", "u")
    monkeypatch.setattr(settings, "tws_password", "p")
    with pytest.raises(HTTPException) as exc:
        service._auth(None, None)
    assert exc.value.status_code == 503
    assert "EXEC_TOKEN" in exc.value.detail
    # a supplied token cannot talk its way past an unset one either
    with pytest.raises(HTTPException):
        service._auth("anything", None)

    # OFFLINE: no credentials -> DryAdapter, nothing to protect
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "tws_password", "")
    service._auth(None, None)                      # no raise

    # and with a token set, the compare is exact (and constant-time)
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    service._auth("sekrit", None)
    service._auth(None, "sekrit")
    with pytest.raises(HTTPException) as exc:
        service._auth("sekri", None)
    assert exc.value.status_code == 401


# --- deploy configuration (B2, B10, B8's pin) --------------------------------

def _ibkr_executor_env_block() -> str:
    """The `ibkr-executor` service block of the repo's render.yaml, as text.
    Parsed by hand on purpose: the suite must not grow a YAML dependency to
    assert a deploy fact."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(os.path.dirname(here), "render.yaml")
    with open(path) as fh:
        text = fh.read()
    start = text.index("name: ibkr-executor")
    nxt = text.find("\n  - type:", start)
    return text[start:] if nxt == -1 else text[start:nxt]


def test_gate_b2_blend_state_path_is_declared_onto_the_mounted_disk():
    """B2 (live-blocker): BLEND_STATE_PATH was UNDECLARED, so the live blend
    book fell back to app/config.py's `./data/blend_state.json` — the
    container's EPHEMERAL layer, NOT the ibkr-data disk mounted at /app/data
    that STATE_PATH has always used. With autoDeploy on, every deploy
    destroyed the book and re-seeded a FRESH one on top of shares the
    account still held. It is also what makes B1's restart-boundary
    double-sell routine rather than exotic: a deploy IS a restart."""
    block = _ibkr_executor_env_block()
    assert "mountPath: /app/data" in block
    assert "key: BLEND_STATE_PATH" in block
    assert "value: /app/data/blend_state.json" in block


def test_gate_b10_ib_client_id_is_declared_and_not_the_shared_default():
    """B10 (live-blocker): IB_CLIENT_ID was undeclared and defaults to 17.
    A TWS/API session already holding that id costs 20 connect attempts x
    15s and then KILLS the loop thread."""
    from app.config import Settings

    block = _ibkr_executor_env_block()
    assert "key: IB_CLIENT_ID" in block
    declared = [ln.split("value:")[1].strip().strip('"')
                for ln in block.splitlines()
                if "value:" in ln and "IB_CLIENT_ID" in block]
    assert any(v.isdigit() for v in declared)
    # and it is deliberately not the code default a human TWS may hold
    assert 'value: "1701"' in block
    assert Settings.model_fields["ib_client_id"].default == 17


def test_gate_b8_ib_async_is_pinned_to_a_major():
    """B8: `ib_async>=1.0` floated across a MAJOR. `Ticker.marketPrice()`
    lost its previous-close fallback between majors, so an unpinned rebuild
    could silently change what a MARK IS on a live-money book."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "requirements.txt")) as fh:
        req = [ln.strip() for ln in fh if ln.strip()
               and not ln.strip().startswith("#")]
    (pin,) = [ln for ln in req if ln.startswith("ib_async")]
    assert "<3" in pin and ">=2" in pin, pin


# --- tracker-blind watch (2026-09-10) -----------------------------------------
# The defect: fetch_intents returned None for EVERY failure, the loop only
# logged it, and _blend_cycle still stamped BLEND_CYCLE ok:True — so a blend
# book that planned nothing for days reported blend_loop.ok: true throughout.
# These gates pin the three ways that fix can rot: paging too early (cry
# wolf), paging too late (the original bug), and paging forever (burying the
# channel the kill switch needs).

def _fresh_watch() -> dict:
    return {"blind_since": None, "fails": 0, "last_ok": None,
            "reason": None, "paged_level": -1, "paged_reason": "",
            "last_page": None, "page_day": None, "page_count": 0,
            "config_count": 0}


def test_gate_the_blend_path_declares_every_env_var_it_needs():
    """The root cause of 2026-09-10: the blend book was deployable while
    TRACKER_URL was never declared, so config.py's "" default made
    fetch_intents return None before issuing any request — no exception, no
    negative-cache entry, no trace at all.

    A substring check for one key does not pin that shape (counter-agent
    T4/CA-10): the incident is DECLARING THE BOOK WITHOUT ITS BRAIN. So this
    asserts the whole set, and it fails the moment the blend path is
    deployable with any leg of its tracker wiring missing."""
    from app.config import Settings

    block = _ibkr_executor_env_block()
    declared = {ln.split("- key:")[1].strip()
                for ln in block.splitlines() if "- key:" in ln}

    # If the book can be turned on here, the way to REACH the tracker must be
    # declared here too. Either all of it, or none of it.
    blend_keys = {"BLEND_ENABLED", "BLEND_STATE_PATH"}
    tracker_keys = {"TRACKER_URL", "TRACKER_API_TOKEN"}
    if declared & blend_keys:
        missing = tracker_keys - declared
        assert not missing, (
            f"the blend path is declared ({sorted(declared & blend_keys)}) "
            f"but its tracker wiring is not: missing {sorted(missing)} — "
            f"this is the 2026-09-10 configuration exactly")

    # and each one defaults to a value that makes the service silently inert,
    # which is WHY declaring them is load-bearing rather than tidiness
    assert Settings.model_fields["tracker_url"].default == ""
    assert Settings.model_fields["tracker_api_token"].default == ""
    assert Settings.model_fields["blend_enabled"].default is False


def test_gate_tracker_blind_needs_both_the_count_and_the_clock():
    """Three failed polls OR ten minutes is not enough — it takes both.
    Count alone over-fires because /kill wakes the loop and stacks attempts
    in seconds; clock alone over-fires when the loop is parked on a wedged
    gateway and has barely polled."""
    from app.service import _tracker_watch

    t0 = 1_000_000.0
    st, pages = _fresh_watch(), []
    assert _tracker_watch(t0, "transport", pages.append, st) == []
    assert _tracker_watch(t0 + 300, "transport", pages.append, st) == []
    assert pages == []                       # 2 polls in: still quiet
    assert _tracker_watch(t0 + 601, "transport", pages.append, st) == ["blind"]
    assert len(pages) == 1

    # 3 failures inside 2 seconds (the /kill-wake shape): the clock holds.
    st2, p2 = _fresh_watch(), []
    for dt in (0, 1, 2):
        _tracker_watch(t0 + dt, "transport", p2.append, st2)
    assert p2 == []

    # 20 minutes blind but only 2 attempts: the count holds.
    st3, p3 = _fresh_watch(), []
    _tracker_watch(t0, "transport", p3.append, st3)
    _tracker_watch(t0 + 1200, "transport", p3.append, st3)
    assert p3 == []


def test_gate_tracker_config_errors_page_on_the_first_poll():
    """no_url / auth / redirect never self-heal — only a human editing a
    Render env var clears them — so the transient threshold buys nothing and
    spends a window that may only be hours long."""
    from app.service import _tracker_watch

    for reason in ("no_url", "auth", "redirect"):
        st, pages = _fresh_watch(), []
        assert _tracker_watch(1_000_000.0, reason, pages.append, st) == ["config"]
        assert len(pages) == 1
        assert "NOT self-heal" in pages[0]
        # and it does not then re-page every cycle
        assert _tracker_watch(1_000_300.0, reason, pages.append, st) == []
        assert len(pages) == 1


def test_gate_tracker_cache_skip_is_not_an_attempt():
    """FEED_FAIL_TTL suppresses the fetch on a cycle woken moments after a
    failure. No request was made, so it is evidence of neither blindness nor
    recovery: it must not advance the counter (over-paging) and must not
    clear it (under-paging)."""
    from app.service import _tracker_watch

    t0 = 1_000_000.0
    st, pages = _fresh_watch(), []
    _tracker_watch(t0, "transport", pages.append, st)
    snapshot = dict(st)
    assert _tracker_watch(t0 + 30, "cache_skip", pages.append, st) == []
    assert st == snapshot                    # untouched, in both directions
    assert pages == []


def test_gate_tracker_recovery_pages_once_then_rearms():
    from app.service import _tracker_watch

    t0 = 1_000_000.0
    st, pages = _fresh_watch(), []
    for dt in (0, 300, 601):
        _tracker_watch(t0 + dt, "transport", pages.append, st)
    assert len(pages) == 1
    assert _tracker_watch(t0 + 3600, "ok", pages.append, st) == ["recovered"]
    assert "will not be entered" in pages[-1]     # honest about what was lost
    assert st["blind_since"] is None and st["fails"] == 0
    assert st["paged_level"] == -1 and st["last_ok"] == t0 + 3600
    # a healthy poll afterwards is silent...
    assert _tracker_watch(t0 + 3900, "ok", pages.append, st) == []
    assert len(pages) == 2
    # ...and a NEW outage, once clear of the page floor, still pages (the r3
    # lesson: a quiet recovery must not swallow the next outage)
    for dt in (7200, 7500, 7900):
        _tracker_watch(t0 + dt, "transport", pages.append, st)
    assert len(pages) == 3


def test_gate_tracker_blip_that_never_paged_never_announces_recovery():
    from app.service import _tracker_watch

    t0 = 1_000_000.0
    st, pages = _fresh_watch(), []
    _tracker_watch(t0, "transport", pages.append, st)
    assert _tracker_watch(t0 + 300, "ok", pages.append, st) == []
    assert pages == []


def test_gate_tracker_healthy_poll_never_pages():
    """A reachable tracker with an empty entries list, a gate that is off, or
    a halted book all plan zero orders. None of that is blindness, and the
    watch keys on the FETCH, never on 'nothing was planned' — XBI can sit
    under its 200dma for weeks."""
    from app.service import _tracker_watch

    st, pages = _fresh_watch(), []
    for i in range(10):
        assert _tracker_watch(1_000_000.0 + i * 300, "ok", pages.append, st) == []
    assert pages == []


def test_gate_tracker_escalation_decays_and_is_bounded():
    """288 cycles/day x one alarm buries the emergency channel (the
    FLATTEN_MAX_ATTEMPTS arithmetic). A long outage must page a handful of
    times, not hundreds."""
    from app.service import _tracker_watch

    t0 = 1_000_000.0
    st, pages = _fresh_watch(), []
    for dt in (0, 300, 601):
        _tracker_watch(t0 + dt, "transport", pages.append, st)
    assert len(pages) == 1
    assert _tracker_watch(t0 + 1800, "transport", pages.append, st) == []
    assert _tracker_watch(t0 + 3601, "transport", pages.append, st) == ["escalate"]
    assert _tracker_watch(t0 + 7200, "transport", pages.append, st) == []
    assert _tracker_watch(t0 + 14_401, "transport", pages.append, st) == ["escalate"]
    assert _tracker_watch(t0 + 100_801, "transport", pages.append, st) == ["escalate"]
    # a three-day outage polled every 300s = 864 cycles -> single digits
    st2, p2 = _fresh_watch(), []
    for i in range(864):
        _tracker_watch(t0 + i * 300, "transport", p2.append, st2)
    assert len(p2) <= 6, len(p2)


def test_gate_tracker_a_new_permanent_reason_repages():
    """The tracker came back but now rejects the token: the diagnosis changed
    to one that will never self-heal, and that deserves its own page rather
    than silence until the next rung."""
    from app.service import _tracker_watch

    t0 = 1_000_000.0
    st, pages = _fresh_watch(), []
    for dt in (0, 300, 601):
        _tracker_watch(t0 + dt, "transport", pages.append, st)
    pages.clear()
    # A permanent diagnosis bypasses the floor — "pages on the first failed
    # poll" has to be true as written — and is bounded by its OWN reserved
    # budget instead, so a flapping transient can never spend it.
    assert _tracker_watch(t0 + 900, "auth", pages.append, st) == ["config"]
    assert "NEW reason" in pages[0]
    assert "NOT self-heal" in pages[0]
    # ...and it does not then re-page every cycle for the SAME reason
    assert _tracker_watch(t0 + 1200, "auth", pages.append, st) == []


def test_gate_health_surfaces_tracker_blindness_without_flipping_status():
    """/health is Render's healthCheckPath. A blind tracker must show up in
    the BODY and never in the status code: restarting the container does not
    fix a dead tracker, it just restart-loops a live-money service."""
    import time as _time

    from app import service as svc

    now = _time.time()
    monkey = {"blind_since": now - 1200, "fails": 4, "last_ok": now - 1500,
              "reason": "auth", "paged_level": 0, "paged_reason": "auth"}
    old_blend, old_watch = svc.BLEND, svc.TRACKER_WATCH
    try:
        svc.BLEND, svc.TRACKER_WATCH = object(), monkey
        body = svc.health()
        assert body["status"] == "ok"
        assert body["tracker"]["ok"] is False
        assert body["tracker"]["reason"] == "auth"
        assert body["tracker"]["blind_polls"] == 4
        assert body["tracker"]["blind_for_s"] >= 1200
        assert body["tracker"]["last_ok_age_s"] >= 1500
        # BLEND_ENABLED=false stays byte-identical to the pre-blend service
        svc.BLEND = None
        assert "tracker" not in svc.health()
    finally:
        svc.BLEND, svc.TRACKER_WATCH = old_blend, old_watch


def test_gate_health_reports_whether_it_can_page_at_all(monkeypatch):
    """alerts.send is a silent no-op with the Telegram env unset. An alerting
    fix that cannot reach anyone is the same bug wearing a hat, so /health
    says whether the channel exists."""
    from app import service as svc

    old_blend = svc.BLEND
    try:
        svc.BLEND = object()
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert svc.health()["tracker"]["alerts_configured"] is False
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
        assert svc.health()["tracker"]["alerts_configured"] is True
    finally:
        svc.BLEND = old_blend


def test_gate_tracker_ok_is_null_until_a_poll_has_actually_succeeded():
    """`blind_since is None` is ALSO true for a service that has never
    completed a single poll — a dead loop thread, a ladder-section raise
    before the blend block, a boot that never got that far. Reporting those
    as ok:true rebuilds the green lie this block exists to end. The field is
    tri-state and the null is the point (counter-agent SB-3/T6/CA-7)."""
    from app import service as svc

    old_blend, old_watch = svc.BLEND, svc.TRACKER_WATCH
    try:
        svc.BLEND = object()
        svc.TRACKER_WATCH = _fresh_watch()           # never polled
        assert svc.health()["tracker"]["ok"] is None
        import time as _t
        svc.TRACKER_WATCH = dict(_fresh_watch(), last_ok=_t.time())
        assert svc.health()["tracker"]["ok"] is True
        svc.TRACKER_WATCH = dict(_fresh_watch(), blind_since=_t.time())
        assert svc.health()["tracker"]["ok"] is False
        # a loop WEDGED after one good poll (a ladder-section raise skips the
        # blend block every iteration) must not hold ok:true on an ancient
        # stamp — null means "unknown", which covers both never and no-longer
        svc.TRACKER_WATCH = dict(_fresh_watch(), last_ok=_t.time() - 86_400)
        assert svc.health()["tracker"]["ok"] is None
    finally:
        svc.BLEND, svc.TRACKER_WATCH = old_blend, old_watch


def test_gate_a_flapping_tracker_cannot_page_every_cycle():
    """ok/fail/ok/fail re-arms the ladder on every recovery, so without a hard
    floor between pages a flapping tracker pages on every failure and every
    recovery — 288/day at the deployed cadence, the exact spam the decaying
    ladder exists to prevent (counter-agent T2/CA-4)."""
    from app.service import _tracker_watch

    from app.service import TRACKER_MAX_PAGES_PER_DAY

    t0 = 86_400_000.0        # exactly a UTC day boundary: 288 x 300s = 1 day,
                             # so the whole window lands in ONE budget bucket
    st, pages = _fresh_watch(), []
    t = t0
    for cycle in range(288):     # 3 failures, one success, repeat
        reason = "ok" if cycle % 4 == 3 else "transport"
        _tracker_watch(t, reason, pages.append, st)
        t += 300
    # The budget bounds ALARM pages. Recovery lines are exempt on purpose —
    # an operator told "BLIND" and then never told it came back is worse off
    # than one told nothing (R18-2) — so the real invariant is: recoveries
    # never outnumber the alarms that earned them, and the total is bounded
    # at twice the budget rather than at the budget.
    alarms = [m for m in pages if m.startswith("🚨")]
    recoveries = [m for m in pages if m.startswith("✅")]
    assert TRACKER_MAX_PAGES_PER_DAY == 6      # the budget itself is pinned
    assert len(alarms) <= 6, len(alarms)       # ...and the bound is absolute:
                                               # asserting against the imported
                                               # constant passes for any value
                                               # of it, budget removed included
                                               # (re-review R18R-2)
    assert len(recoveries) <= len(alarms), (len(recoveries), len(alarms))
    assert len(pages) <= 12, len(pages)

    # and two CONFIG reasons alternating, each of which pages on first sight
    # and bypasses the floor: bounded by the RESERVED budget instead
    from app.service import TRACKER_MAX_CONFIG_PAGES_PER_DAY
    st2, p2 = _fresh_watch(), []
    t = t0
    for cycle in range(288):
        _tracker_watch(t, "auth" if cycle % 2 else "no_url", p2.append, st2)
        t += 300
    # Two budgets are in play: the reserved one for the DIAGNOSIS pages, and
    # the shared one for the escalation rungs that follow them. Both bound
    # it; the contract is that the sum is a handful, against 288 cycles.
    assert TRACKER_MAX_CONFIG_PAGES_PER_DAY == 3
    assert len(p2) <= 9, len(p2)               # 3 config + 6 shared, absolute

    # a STEADY three-day outage stays in single digits, and still pages on
    # each new day rather than going permanently quiet
    st3, p3 = _fresh_watch(), []
    t = t0
    for cycle in range(864):
        _tracker_watch(t, "transport", p3.append, st3)
        t += 300
    assert 3 <= len(p3) <= 9, len(p3)


def test_gate_a_config_page_cannot_be_starved_by_a_flapping_transient():
    """One shared budget let the LEAST important pages starve the MOST
    important one: a flapping transient spent all six, and the no_url/auth
    that followed — the diagnosis that never self-heals and that the round
    promises pages on the FIRST failed poll — was silently suppressed
    (re-review R18-1)."""
    from app.service import _tracker_watch

    t0 = 86_400_000.0
    st, pages = _fresh_watch(), []
    t = t0
    for cycle in range(120):            # burn the shared budget on transients
        _tracker_watch(t, "ok" if cycle % 4 == 3 else "transport",
                       pages.append, st)
        t += 300
    assert st["page_count"] >= 6, st["page_count"]
    pages.clear()
    # now a permanent cause appears, same UTC day, seconds after the last page
    assert _tracker_watch(t, "auth", pages.append, st) == ["config"]
    assert "NOT self-heal" in pages[0]


def test_gate_a_recovery_is_never_swallowed_by_the_page_floor():
    """The floor ate the RECOVERED line for the most common outage lengths
    while the state reset regardless, so the operator got '🚨 BLIND' and then
    silence, with nothing ever closing the loop (re-review R18-2)."""
    from app.service import _tracker_watch

    t0 = 86_400_000.0
    st, pages = _fresh_watch(), []
    for dt in (0, 300, 601):
        _tracker_watch(t0 + dt, "transport", pages.append, st)
    assert len(pages) == 1
    # recovery lands well inside the 30-minute floor
    assert _tracker_watch(t0 + 900, "ok", pages.append, st) == ["recovered"]
    assert pages[-1].startswith("✅")


def test_gate_a_raising_pager_costs_nothing_and_stops_nothing():
    """_page spent the floor and the budget BEFORE send_fn returned, so one
    broken transport muted the next real page — and the raise escaped
    _tracker_watch, skipping the recovery path's own state reset
    (re-review R18-4/R17R-5)."""
    from app.service import _tracker_watch

    t0 = 86_400_000.0
    st = _fresh_watch()

    def boom(_msg):
        raise RuntimeError("telegram down")

    for dt in (0, 300, 601):
        assert _tracker_watch(t0 + dt, "transport", boom, st) == []
    assert st["page_count"] == 0 and st["last_page"] is None
    assert st["paged_level"] == -1          # nothing advanced on a lost page
    # the transport heals: the page that was never delivered is not owed to
    # a spent budget, and the watch itself never stopped counting
    pages = []
    assert _tracker_watch(t0 + 900, "transport", pages.append, st) == ["blind"]


def test_gate_a_suppressed_page_never_advances_the_rung():
    """The `if sent:` guard is what stops a suppressed page from burning a
    rung it never announced. It was a surviving mutation — deleting it left
    all 312 tests green (re-review R18-5)."""
    from app.service import _tracker_watch

    t0 = 86_400_000.0
    st, pages = _fresh_watch(), []
    for dt in (0, 300, 601):
        _tracker_watch(t0 + dt, "transport", pages.append, st)
    assert st["paged_level"] == 0 and len(pages) == 1
    # 1h rung falls inside the floor -> suppressed, and the rung must NOT
    # advance, or the escalation is silently skipped for good
    assert _tracker_watch(t0 + 1900, "transport", pages.append, st) == []
    assert st["paged_level"] == 0, st["paged_level"]
    # once the floor clears, the rung it was owed still fires
    assert _tracker_watch(t0 + 3700, "transport", pages.append, st) == ["escalate"]
    assert st["paged_level"] == 1


def test_gate_the_page_text_carries_its_remedy_and_its_blast_radius():
    """Both were code-only and ungated: emptying _TRACKER_BLAST, or dropping
    the config `tail` from the escalation rungs, left the whole suite green
    while every page silently lost the half that makes it actionable
    (re-review R18R-3, round-17 T9/T5 and T2-doctrine)."""
    from app.service import _tracker_watch

    t0 = 86_400_000.0
    st, pages = _fresh_watch(), []
    for dt in (0, 300, 601):
        _tracker_watch(t0 + dt, "transport", pages.append, st)
    first = pages[0]
    assert "no cash is raised" in first
    assert "GTC stops" in first and "90-day time stop" in first
    assert "delayed, not lost" in first          # exits, stated correctly
    assert "ARE lost" in first                   # entries, stated correctly

    # a CONFIG outage's escalation rung must still name the fix
    st2, p2 = _fresh_watch(), []
    _tracker_watch(t0, "auth", p2.append, st2)
    assert "NOT self-heal" in p2[0]
    assert _tracker_watch(t0 + 3700, "auth", p2.append, st2) == ["escalate"]
    assert "NOT self-heal" in p2[-1], p2[-1]


def test_gate_a_raising_watch_cannot_stop_the_protective_cycle(tmp_path,
                                                               monkeypatch):
    """The watch is a REPORTING call sitting in front of the protective one.
    Deleting its try/except left the suite green while anything raising inside
    it — alerts.send, a malformed state dict — aborted the iteration before
    _blend_cycle: the watchdog killing the thing it guards (re-review
    R18R-3, round-17 CA-5/SB-5).

    _tracker_watch itself is made to raise, which is exactly what the guard
    at the call site exists for; patching `send` instead would kill the loop
    at its boot alert, long before the blend block."""
    import time as _time

    from app.config import settings
    from app import service
    from app.service import app as service_app
    from fastapi.testclient import TestClient

    cycles = []

    def boom(*a, **kw):
        raise RuntimeError("watch exploded")

    monkeypatch.setattr(service, "_tracker_watch", boom)
    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "blend_state_path", str(tmp_path / "b.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "blend_enabled", True)
    monkeypatch.setattr(settings, "poll_seconds", 3600)
    monkeypatch.setattr(blend_mod, "run_cycle",
                        lambda *a, **kw: (cycles.append(a[2]), [])[1])
    try:
        with TestClient(service_app):
            for _ in range(200):
                if cycles:
                    break
                _time.sleep(0.05)
        assert cycles, "the protective cycle never ran behind a raising watch"
    finally:
        service.BLEND = None
        service.MGR = None
        service._reset_tracker_watch()


def test_gate_the_watch_runs_after_the_supersede_checkpoint():
    """MF-2's law: a bumped generation must not act. The watch was originally
    called BEFORE `if _superseded(gen): return`, so a superseded lifespan
    still paged and still mutated the module-global watch. Ordering is the
    behaviour here, and nothing else pins it (re-review R18R-3 / CA-6)."""
    import inspect

    from app import service

    src = inspect.getsource(service._loop)
    guard = src.index("if _superseded(gen):\n                    return")
    call = src.index("_tracker_watch(time.time(), reason, send)")
    assert guard < call, "the watch must sit after the supersede checkpoint"
    # ...and inside the guard that stops it killing the cycle
    assert "try:\n                    _tracker_watch(" in src
