"""Executor service: background mirror loop + status/control API.

Control surface:
  GET  /health   - liveness
  GET  /status   - full executor state (mode, ledger, events, last target)
  POST /kill     - cancel everything, flatten, halt until /resume
  POST /resume   - clear a halt (manual operator action)
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Header

from .config import settings
from .feed import EngineFeed
from .mirror import (Executor, DRILL_CYCLE_NEED,  # noqa: F401
                     SLIPPAGE_SAMPLE_NEED)


def _auth(x_exec_token: str | None, token_q: str | None) -> None:
    """Control/status endpoints share the EXEC_TOKEN secret. Header for
    tools, ?token= for a browser. No token configured -> open (dev only)."""
    if settings.exec_token and x_exec_token != settings.exec_token \
            and token_q != settings.exec_token:
        raise HTTPException(status_code=401, detail="bad exec token")

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

FEED = EngineFeed(settings.engine_url, settings.exec_token)
LAST: dict = {"target": None, "target_ts": 0, "loop_ok": 0}
EXEC: Executor | None = None


VENUES = ("coinbase", "hyperliquid")


def _venue_name() -> str:
    """Validated at boot. An unknown VENUE RAISES rather than defaulting -
    a typo must never route real orders to whichever venue happens to be
    the fallback, and the caller's retry loop turns this into a loud,
    repeating ACTION page instead of a silent wrong-exchange deploy."""
    v = str(getattr(settings, "venue", "coinbase") or "coinbase").strip().lower()
    if v not in VENUES:
        raise RuntimeError(f"VENUE={v!r} is not one of {VENUES}")
    return v


def _build_executor() -> Executor:
    import os
    inner = None
    which = _venue_name()
    LAST["venue_init_error"] = None
    LAST["venue_products"] = None
    LAST["venue_name"] = which
    if which == "hyperliquid":
        missing = "no HL_SECRET_KEY set" if not settings.hl_secret_key else None
        if missing:
            LAST["venue_init_error"] = missing
        else:
            try:
                from .hl import HyperliquidVenue
                inner = HyperliquidVenue(settings)
                LAST["venue_products"] = inner.list_perp_candidates()
                logger.info("hyperliquid perps visible: %s",
                            LAST["venue_products"])
            except Exception as exc:  # noqa: BLE001
                LAST["venue_init_error"] = f"{type(exc).__name__}: {exc}"
                logger.error("hyperliquid venue init failed: %s", exc)
                inner = None
    elif not (settings.cb_api_key_name and settings.cb_api_private_key):
        LAST["venue_init_error"] = "no CB_API_KEY_NAME / CB_API_PRIVATE_KEY set"
    else:
        try:
            from .cb import CoinbaseVenue
            inner = CoinbaseVenue(settings)
            LAST["venue_products"] = inner.list_perp_candidates()
            logger.info("BTC futures products visible to this key: %s",
                        LAST["venue_products"])
        except Exception as exc:  # noqa: BLE001
            LAST["venue_init_error"] = f"{type(exc).__name__}: {exc}"
            logger.error("coinbase venue init failed: %s", exc)
            inner = None
    if not settings.dry_run and inner is None:
        # LIVE mode must never silently demote to a shadow book: the old
        # fall-through ran DryRunVenue over a real account - synthetic $10k
        # equity, continuous fills, and NOBODY maintaining real positions or
        # stops, while /health stayed green (counter-agent find 2026-08-11,
        # same phenotype as the DRY_RUN blueprint incident). Alert and raise;
        # _loop retries with backoff so a transient Coinbase outage self-heals.
        from .alerts import send
        # RATE-LIMITED (re-gate 2026-08-27): alerts.send has no cooldown of
        # its own and never touches Executor._event's RATE_LIMITED table, so
        # the new retry loop below would fire this ACTION page on every
        # attempt - 144 identical pages a day, forever, on a missing-key
        # condition that never self-heals. This repo set its own house rule
        # at one page per 30 min after halt_config (~180/hr) and
        # stop_vanished (4,320/day); the retry is right, its paging was not.
        now = time.time()
        if now - LAST.get("init_paged_at", 0.0) > 1800:
            LAST["init_paged_at"] = now
            send("🔴 ACTION NEEDED (you) — executor venue_init_failed: LIVE "
                 f"mode cannot connect to {which.upper()} "
                 f"({LAST['venue_init_error']}). "
                 "No orders are being managed; any open positions/stops are "
                 "untouched on the venue. Retrying automatically every "
                 "30s-10min - if this repeats, check the venue's status and "
                 f"the {which} credentials in Render. "
                 "(This page is rate-limited to 1/30min.)")
        raise RuntimeError(f"live venue init failed: "
                           f"{LAST['venue_init_error']}")
    if settings.dry_run:
        from .cb import DryRunVenue
        venue = DryRunVenue(inner, persist_path=os.path.join(
            os.path.dirname(settings.state_path) or ".", "dryrun_book.json"))
        logger.warning("DRY RUN mode: no orders will be sent (inner=%s)",
                       type(inner).__name__ if inner else None)
    else:
        venue = inner
    LAST["venue_inner"] = type(inner).__name__ if inner else None
    LAST["_inner"] = inner
    LAST["venue_products_ts"] = time.time()
    return Executor(venue, settings)


def _loop() -> None:
    global EXEC
    # The venue_init_failed ACTION page has promised "Retrying
    # automatically" since 2026-08-11 — but this call sat OUTSIDE any
    # try, so a raise killed the daemon thread and no retry ever existed
    # (counter-agent 2026-08-27, out-of-delta find). Mid-incident that is
    # the worst possible shape: a transient Coinbase outage at deploy time
    # left the service permanently dead while its own alert claimed it was
    # self-healing. Backoff 30s -> 60s -> ... -> capped 10 min, forever:
    # a LIVE book must not stay unmanaged because boot raced an outage.
    delay, attempts = 30.0, 0
    while EXEC is None:
        try:
            EXEC = _build_executor()
        except Exception as exc:  # noqa: BLE001
            attempts += 1
            logger.exception("executor build failed, retrying in %ss: %s",
                             delay, exc)
            time.sleep(delay)
            delay = min(delay * 2, 600.0)
    if attempts:
        # close the loop the ACTION page opened: an operator who was told
        # "no orders are being managed" must be told when that stops being
        # true, or they act on a stale page.
        from .alerts import send
        send(f"✅ executor venue_init recovered after {attempts} failed "
             f"attempt(s) — the book is being managed again; no action needed")
    while True:
        try:
            target = FEED.get_target()
            if target is not None:
                LAST["target"] = target
                LAST["target_ts"] = time.time()
                EXEC.step(target)
            LAST["loop_ok"] = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.exception("executor loop error: %s", exc)
        time.sleep(settings.poll_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_loop, daemon=True).start()
    yield


app = FastAPI(title="S5 Executor", version="0.1.0", lifespan=lifespan)


def _build_sha() -> str | None:
    """Which commit is actually running.

    Added 2026-08-28 after a live diagnosis stalled on a question nothing
    could answer. A rail was reporting a fault, a fix was pushed, and there
    was no way to tell from outside whether the next reading came from the
    OLD build or the new one — so a value that had not changed was
    indistinguishable from a deploy that had not landed, and the diagnosis
    could only be guessed at. Every other field on these endpoints
    describes STATE; without this one none of them can be attributed to a
    version of the code.

    Render injects RENDER_GIT_COMMIT. Absent (local, or a runtime that does
    not set it) the honest answer is null, never a guess."""
    import os
    sha = (os.environ.get("RENDER_GIT_COMMIT")
           or os.environ.get("GIT_COMMIT") or "").strip()
    return sha[:7] or None


@app.get("/health")
def health():
    return {"status": "ok", "service": "btc-executor",
            "dry_run": settings.dry_run,
            "build": _build_sha(),
            "loop_age_s": round(time.time() - LAST["loop_ok"], 1)
            if LAST["loop_ok"] else None}


@app.get("/pulse")
def pulse():
    """Public minimal heartbeat for automated monitoring: state flags only —
    no equity, no position sizes, no order details."""
    if EXEC is None:
        return {"ready": False, "build": _build_sha()}
    st = EXEC.state
    now = time.time()
    red_24h = sum(1 for e in st.events
                  if e.get("level") == "RED" and now - e.get("ts", 0) < 86_400)
    _rv = _ramp_v4(st)
    rv = _rv["rows"]
    return {"ready": True, "dry_run": settings.dry_run,
            # which commit produced every other field below — without it a
            # reading cannot be attributed to a build (2026-08-28)
            "build": _build_sha(),
            # WHICH VENUE is publicly visible: a book silently running on
            # the wrong exchange is the one config error no ledger check can
            # catch, and this is the only unauthenticated surface.
            "venue": LAST.get("venue_name", "coinbase"),
            "halted": st.halted, "red_events_24h": red_24h,
            "ramp_v4_met": f"{sum(r['met'] for r in rv.values())}/{len(rv)}",
            # without this a 13/13 -> 0/13 drop at the provenance split reads
            # as data loss to whoever is watching the heartbeat
            "ramp_v4_unattributed": _rv["unattributed_total"],
            # attestation drives unattributed to 0; without this the public
            # heartbeat reports attested rows identically to observed ones
            "ramp_v4_attested": sum(1 for r in rv.values()
                                    if r.get("attested")),
            # why auto-drill is not drilling. Without this, "armed and
            # waiting behind an open position" and "broken" look identical
            # on the only endpoint that is public.
            # Bare reason TOKEN only: _drill_refusal returns
            # venue_not_flat:{pos} and position_unreadable:{exc}, which would
            # publish position sizes and raw API error text (key ids included)
            # on an unauthenticated endpoint (counter-agent 2026-08-24).
            "auto_drill": ("off" if getattr(st, "auto_drill_off", None)
                           else (getattr(EXEC, "_auto_drill_wait", None)
                                 or "ok").split(":")[0]),
            "last_target_age_s": round(now - LAST["target_ts"], 1)
            if LAST["target_ts"] else None,
            # age of the last SUCCESSFUL venue position read. Every other
            # field here reads the LEDGER (belief); this is the only signal
            # of venue truth an external monitor gets. null = never read
            # this process; a growing number = the executor is going blind
            # (2026-08-26: three days blind with a healthy-looking pulse).
            "venue_read_age_s": (round(now - st.last_venue_read_ts, 1)
                                 if getattr(st, "last_venue_read_ts", 0)
                                 else None),
            # WHICH KEY IS DEPLOYED, as the address it signs as. Added
            # 2026-08-28 after a key swap could not be verified from
            # outside: agent_days_left said "this key is not an approved
            # agent", but it could not say WHICH key, so "you pasted the
            # wrong one" and "the new one has not loaded yet" were the same
            # observation - and every other signal that might have
            # distinguished them (the build sha, which does not change on an
            # env edit; the rolling RED count, which can absorb a new event
            # as an old one ages out) turned out not to. This one is
            # unambiguous: compare it against the approved agent.
            # Not a secret - an agent address is public on-chain, already
            # discoverable from the account, and useless without the key.
            "agent_address": (getattr(EXEC.venue, "agent_address", None)
                              or getattr(getattr(EXEC.venue, "inner", None),
                                         "agent_address", None)),
            # ...and WHICH ACCOUNT it signs FOR. Both halves are needed:
            # publishing only the signer sent a live diagnosis down the wrong
            # path for two rounds, because "this key is not an approved agent
            # of X" is equally consistent with a wrong key and a wrong X, and
            # X was the one nobody could see. It is also the address
            # position() and equity() read, so a wrong value here is the
            # phantom-position failure mode itself: a real book elsewhere,
            # reported as a CONFIRMED FLAT, with a healthy-looking
            # venue_read_age_s because the read genuinely succeeded - against
            # the wrong account.
            # Leaks nothing: userRole(agent_address) already returns this
            # address to anyone, and agent_address is published above.
            "account_address": (getattr(EXEC.venue, "address", None)
                                or getattr(getattr(EXEC.venue, "inner", None),
                                           "address", None)),
            # WHICH CHAIN every other field describes. venue="hyperliquid"
            # was not enough: mainnet and testnet are the same adapter and
            # the same healthy-looking pulse, against different accounts.
            "network": (getattr(EXEC.venue, "network", None)
                        or getattr(getattr(EXEC.venue, "inner", None),
                                   "network", None)),
            # days until the signing key stops working (Hyperliquid agent
            # wallets expire). null = no expiry, or not read yet. The
            # executor halts itself at T-1 day, but this makes the clock
            # visible to an external monitor long before that.
            "agent_days_left": (
                round((getattr(st, "agent_valid_until", None) - now) / 86400.0, 2)
                if getattr(st, "agent_valid_until", None) is not None else None),
            "legs": {n: {"in_position": l.qty != 0.0,
                         "entry_open": l.entry_cloid is not None,
                         "stop_placed": l.stop_cloid is not None}
                     for n, l in st.legs.items()}}


@app.get("/status")
def status(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if EXEC is None:
        return {"ready": False}
    inner = LAST.get("_inner")
    if inner and time.time() - (LAST.get("venue_products_ts") or 0) > 600:
        # refresh discovery so newly-enabled products (e.g. after the
        # account's derivatives onboarding) show up without a restart
        try:
            LAST["venue_products"] = inner.list_perp_candidates()
        except Exception as exc:  # noqa: BLE001
            logger.warning("product re-discovery failed: %s", exc)
        LAST["venue_products_ts"] = time.time()
    st = EXEC.state
    venue = EXEC.venue
    dry_log = getattr(venue, "log", None)
    out = {"ready": True, "dry_run": settings.dry_run,
           "build": _build_sha(),
           "venue_inner": LAST.get("venue_inner"),
           "venue_init_error": LAST.get("venue_init_error"),
           "venue_products": LAST.get("venue_products"),
           "product": settings.cb_product_id,
           "kelly_m": settings.kelly_m,
           "sizing_config": {
               "sizing_base_usd": settings.sizing_base_usd or "account equity",
               "kelly_m": settings.kelly_m,
               "max_notional_usd": settings.max_notional_usd,
               "max_account_lev": settings.max_account_lev,
               "daily_loss_halt_pct": settings.daily_loss_halt_pct,
               "dd_halt_pct": settings.dd_halt_pct},
           "halted": st.halted,
           "day_start_equity": st.day_start_equity,
           "high_water": st.high_water,
           "legs": {n: vars(l) for n, l in st.legs.items()},
           "marks": st.marks[-400:],
           "fills": getattr(st, "fills", [])[-400:],
           "events": st.events[-50:],
           "last_target": LAST["target"],
           "last_target_age_s": round(time.time() - LAST["target_ts"], 1)
           if LAST["target_ts"] else None,
           "coverage": getattr(st, "coverage", {}),
           "coverage_live": getattr(st, "coverage_live", {}),
           "coverage_attested": getattr(st, "coverage_attested", {}),
           "mode_flips": getattr(st, "mode_flips", 0),
           "drills": getattr(st, "drills", [])[-10:],
           "auto_drill": {"enabled": settings.auto_drill,
                          "spacing_s": settings.auto_drill_spacing_s,
                          "off": getattr(st, "auto_drill_off", None),
                          # full reason string stays on the TOKEN-GATED
                          # endpoint; /pulse publishes only the bare token
                          "waiting_on": getattr(EXEC, "_auto_drill_wait",
                                                None),
                          "next_needed": EXEC._needed_auto_drill()},
           "ramp_v4": _ramp_v4(st)}
    try:
        out["equity"] = venue.equity()
        out["venue_position_btc"] = venue.position()
    except Exception as exc:  # noqa: BLE001
        out["venue_error"] = str(exc)
    if dry_log is not None:
        out["dry_run_intents"] = dry_log[-50:]
    return out


RAMP_V4_REQUIRED = {"entry_long": 2, "entry_short": 2, "stop_placed": 2,
                    "stop_filled": 1, "signal_exit": 2, "chase": 1,
                    "post_only_cross": 1, "restart_with_position": 1,
                    "config_change": 1, "drill_cycle": DRILL_CYCLE_NEED,
                    "halt": 1, "resume": 1}


def _ramp_v4(st) -> dict:
    """Ramp gate on LIVE-MODE evidence only.

    `have` reads state.coverage_live (events produced with DRY_RUN=false).
    The all-modes total and the difference are reported alongside as
    `all_modes` / `unattributed` so nothing disappears silently — but only
    live counts can mark a row met. Rationale: the matrix exists to prove
    venue mechanics, and a dry-run event proves the state machine against
    DryRunVenue instead. Counts written before the mode split (2026-08-21)
    carry no provenance and are therefore unattributed: they must be
    re-earned live, which is the conservative direction.
    """
    # Shape-hardened: /status AND the public /pulse both render this, and
    # _load_state accepts any JSON that parses. A corrupt row must not blind
    # monitoring with a 500 (counter-agent find 2026-08-21).
    cov = getattr(st, "coverage", {}) or {}
    live = getattr(st, "coverage_live", {}) or {}
    cov = cov if isinstance(cov, dict) else {}
    live = live if isinstance(live, dict) else {}
    fills = getattr(st, "fills", []) or []
    fills = fills if isinstance(fills, list) else []
    # a fill recorded before the split has no "live" key -> unattributed
    # void fills are excluded: the 2026-08-26 incident recorded two chase
    # fills with 1320bps of fictitious "slippage" (measured against a
    # days-stale engine price) — one of which never happened at all. They
    # stay in the record for audit, marked void, and count toward nothing.
    n_live = sum(1 for f in fills
                 if isinstance(f, dict) and f.get("live") is True
                 and not f.get("void"))

    def _n(d, k):
        v = d.get(k, 0)
        return v if isinstance(v, int) and v >= 0 else 0

    att = getattr(st, "coverage_attested", {}) or {}
    att = att if isinstance(att, dict) else {}

    def _row(k, need, have, all_modes):
        # live > all_modes is impossible from _cov (which writes both) and
        # can only come from a tampered/rolled-back state file. Never let it
        # render as satisfied.
        corrupt = have > all_modes
        return {"have": have, "need": need,
                "met": (have >= need) and not corrupt,
                "all_modes": all_modes,
                "unattributed": max(0, all_modes - have),
                # attested != observed: the matrix must keep saying which,
                # and "have: 7, attested: 2" is ambiguous without observed
                **({"attested": _n(att, k),
                    "observed": max(0, have - _n(att, k))}
                   if _n(att, k) else {}),
                **({"corrupt": True} if corrupt else {})}

    rows = {k: _row(k, v, _n(live, k), _n(cov, k))
            for k, v in RAMP_V4_REQUIRED.items()}
    rows["slippage_sample"] = _row("slippage_sample", SLIPPAGE_SAMPLE_NEED,
                                   n_live, len(fills))
    return {"spec": "RAMP_V4.md (frozen 2026-08-15; mode guard 2026-08-21)",
            "basis": "live-mode events only (DRY_RUN=false)",
            "attestation": getattr(st, "attestation", None),
            "rows": rows,
            "coverage_complete": all(r["met"] for r in rows.values()),
            "unattributed_total": sum(r["unattributed"] for r in rows.values()),
            "note": "advance KELLY_M per spec only when coverage_complete "
                    "AND slippage sane (edge-monitor slip CUSUM quiet). "
                    "unattributed counts are pre-split or dry-run events - "
                    "they never satisfy a row"}


@app.post("/coverage/attest")
def coverage_attest(confirm: bool = Query(False),
                    note: str = Query(""),
                    acknowledge_unwitnessed: bool = Query(False),
                    x_exec_token: str | None = Header(default=None),
                    token: str | None = Query(default=None)):
    """ONE-SHOT: promote pre-split coverage counts to live-attributed.

    Deliberate, bounded hole in the mode guard for the single migration
    where counts were genuinely earned live but predate provenance
    recording. Refuses if anything is already attributed, if the executor
    is not live, or if the retained event log shows any DRY_RUN flip.
    See RAMP_V4.md; requires ?confirm=true.
    """
    _auth(x_exec_token, token)
    if EXEC is None:
        raise HTTPException(status_code=503, detail="executor not ready")
    if not confirm:
        raise HTTPException(status_code=400,
                            detail="pass confirm=true: this promotes rows to "
                                   "ATTESTED evidence and cannot be undone")
    return EXEC.attest_coverage(note, acknowledge_unwitnessed)


@app.post("/drill")
def drill(kind: str = Query("cycle"),
          x_exec_token: str | None = Header(default=None),
          token: str | None = Query(default=None)):
    """RAMP v4 drill (RAMP_V4.md): ONE min-size round trip through the real
    order paths. Token-gated, budgeted, refuses unless the whole book is
    flat. Never scheduled - a human calls this."""
    _auth(x_exec_token, token)
    if EXEC is None:
        raise HTTPException(status_code=503, detail="executor not ready")
    return EXEC.drill(kind)


@app.get("/test-alert")
def test_alert(x_exec_token: str | None = Header(default=None),
               token: str | None = Query(default=None)):
    """Browser-friendly Telegram wiring check (token-gated)."""
    _auth(x_exec_token, token)
    import os
    from .alerts import send
    configured = bool(os.environ.get("TELEGRAM_BOT_TOKEN")
                      and os.environ.get("TELEGRAM_CHAT_ID"))
    if configured:
        send("✅ test: btc-executor → Telegram wiring works")
    return {"telegram_configured": configured,
            "sent": configured,
            "hint": None if configured else
            "set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars"}


@app.api_route("/kill", methods=["GET", "POST"])
def kill(x_exec_token: str | None = Header(default=None),
         token: str | None = Query(default=None)):
    """GET allowed so the kill switch works from any browser (token-gated)."""
    _auth(x_exec_token, token)
    if EXEC is None:
        return {"ok": False}
    EXEC.halt("KILL", "manual kill switch")
    return {"ok": True, "halted": EXEC.state.halted}


@app.api_route("/resume", methods=["GET", "POST"])
def resume(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None),
           adopt_venue: int = Query(default=0)):
    """adopt_venue=1 resets the LEDGER to what the venue actually holds
    before clearing the halt.

    Needed because a halt whose flatten failed keeps its (divergent) ledger
    on purpose, and LEDGER_DIVERGENCE then re-fires on every plain /resume —
    a deadlock only a redeploy could break (re-gate 2026-08-26 N2). Use it
    ONLY after looking at Coinbase yourself: it makes the venue the source
    of truth, which is the right call when you have just verified the venue,
    and the wrong one if the position read is what is broken."""
    _auth(x_exec_token, token)
    if EXEC is None:
        return {"ok": False}
    # `adopted` reports the OUTCOME, not the request (re-gate 2026-08-27):
    # echoing the query parameter made a REFUSED adopt on a blind venue
    # indistinguishable from a successful one, hiding that the stops the
    # operator believes were cancelled are still armed.
    ok = EXEC.resume(adopt_venue=bool(adopt_venue))
    return {"ok": True, "halted": EXEC.state.halted,
            "adopt_requested": bool(adopt_venue),
            "adopted": bool(adopt_venue) and bool(ok)}
