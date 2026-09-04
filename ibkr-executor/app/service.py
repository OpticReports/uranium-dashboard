"""IBKR executor service: decision loop + control surface.

Modes (auto-selected):
  OFFLINE : no TWS credentials -> DryAdapter, full logic, zero broker calls
  PAPER   : credentials + TRADING_MODE=paper -> real gateway, paper account
  LIVE    : TRADING_MODE=live AND DRY_RUN=false -> real orders (Nov gate)
DRY_RUN=true with credentials still routes everything (mutations AND reads)
through the DryAdapter; the paper-phase stock/ETF adapter has LANDED and is
exercised in PAPER mode (DRY_RUN=false, TRADING_MODE=paper).
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query

from .alerts import send
from .outages import OutageLog
from .config import settings
from .ib_adapter import DryAdapter
from .manager import LadderManager
from .nino import nino34_weekly

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

MGR: LadderManager | None = None
MGR_LOCK = threading.Lock()        # x12: serializes LADDER state writes the
                                   # same way BLEND_LOCK does for the blend —
                                   # /kill and /resume mutate legs/halted on
                                   # API threads while _loop steps and saves
                                   # on the loop thread. NEVER hold this and
                                   # BLEND_LOCK at the same time (the two
                                   # sections are always disjoint): a fixed
                                   # order is not needed if they never nest.
BLEND = None                       # Blend3070Manager, ONLY when BLEND_ENABLED
BLEND_LOCK = threading.Lock()      # serializes blend state writes: /kill's
                                   # request_flatten (API thread) vs
                                   # run_cycle (loop thread)
LOOP_WAKE = threading.Event()      # /kill pokes the loop so a queued blend
                                   # flatten runs within seconds, not a
                                   # full poll interval (R2)
ADAPTER = None
LAST: dict = {"loop_ok": 0.0, "nino34": None, "mode": "OFFLINE"}
# Boot retry (2026-08-28): _build() connects to the gateway, which cannot
# finish logging in until a 2FA push is approved. A failed build is
# therefore usually TEMPORARY and must be retried, not fatal.
BUILD_RETRY_S = 60.0        # tests monkeypatch this to 0
BUILD_ALERT_EVERY = 30      # ~1 page per 30 min while it keeps failing
# Last blend cycle outcome (feed's last_cycle + /health blend_loop): a
# silently failing blend loop must be visible from the outside.
BLEND_CYCLE: dict = {"date": None, "ok": None, "error": None,
                     "error_ts": None}
# Persisted gateway-outage ledger (built with the live adapter only).
OUTAGES = None


def _gateway_restarts(limit: int = 20) -> dict:
    """Restart records written by start.sh's supervisor. A gateway that keeps
    dying is a different problem from IBKR being unreachable, and the two used
    to be indistinguishable."""
    path = getattr(settings, "gateway_restart_log", "")
    out: list[dict] = []
    try:
        # seek to the tail: /health is probed every few seconds and used to
        # slurp the entire unrotated file (counter-agent measured 7.5 MB per
        # call on a one-year log)
        WINDOW = 256 * 1024
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - WINDOW))
            blob = fh.read().decode("utf-8", "replace")
        lines = blob.splitlines()
        if size > WINDOW:
            lines = lines[1:]      # only THEN is the first line partial
        for line in lines:
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(rec, dict):
                out.append(rec)
    except Exception:  # noqa: BLE001
        pass
    day = time.time() - 86400
    # count over EVERYTHING in the tail, then truncate for display: applying
    # the limit first made last_24h saturate at exactly the storm it exists
    # to reveal
    last_24h = sum(1 for r in out if _num_ts(r) >= day)
    return {"recent_shown": min(len(out), limit),
            "last_24h": last_24h,
            # every restart ts in the tail: the gateway watch counts how many
            # landed since the current outage began (0-1 = the process is
            # alive but not logged in; many = a crash loop)
            "recent_ts": [_num_ts(r) for r in out],
            # the breaker deliberately recreates a dead-gateway steady state
            # (stops hammering IBKR logins); it must be NAMED, not buried in
            # the last record's reason field (counter-agent 2026-08-24 F3)
            "circuit_open": bool(out) and out[-1].get("reason") == "circuit_open",
            "last": out[-1] if out else None}


def _num_ts(rec: dict) -> float:
    try:
        return float(rec.get("ts") or 0)
    except (TypeError, ValueError):
        return 0.0


# --- gateway watch: the two outage shapes supervision cannot see ----------
# (2026-09-02/03, two nights running, 13 h + 12.9 h). The gateway's daily
# restart landed as a process exit; the supervisor relaunched it; the fresh
# login waited on an IB Key push nobody tapped. The process was ALIVE, so
# the supervisor (which acts only on exits) never restarted it again, the
# 30-minute outage alert fired its generic text once, and the book sat blind
# until a human noticed in the morning. Two additions, both service-side so
# they see the outage ledger AND the restart log together:
#  1. STALL DIAGNOSIS: down > STALL_DIAG_S with at most one restart since
#     the drop = stuck at login, not crash-looping. Say so, once per outage,
#     and say what fixes it (the phone, or a Render restart for a fresh push).
#  2. PRE-OPEN PAGE: still down inside [08:30, 09:30) ET on a weekday - page
#     with the minutes left, once per outage per day. A restart AFTER the
#     open re-runs the blend mid-session (the 08-28 pattern); before it is
#     free.
STALL_DIAG_S = 30 * 60.0
PREOPEN_FROM = (8, 30)
PREOPEN_TO = (9, 30)
MARKET_TZ = "America/New_York"
GW_WATCH: dict = {"outage_since": None, "diagnosed": False, "preopen_paged": ""}


def _et(now_ts: float) -> datetime:
    return datetime.fromtimestamp(now_ts, tz=timezone.utc).astimezone(
        ZoneInfo(MARKET_TZ))


def _gateway_watch(now: float, summary: dict | None, restarts: dict | None,
                   send_fn, state: dict | None = None) -> list[str]:
    """Pure: returns which pages fired ('stall', 'preopen'); state carries
    once-per-outage / once-per-day bookkeeping."""
    st = GW_WATCH if state is None else state
    down_since = (summary or {}).get("currently_down_since")
    if not down_since:
        st.update(outage_since=None, diagnosed=False, preopen_paged="")
        return []
    if st.get("outage_since") != down_since:
        st.update(outage_since=down_since, diagnosed=False, preopen_paged="")
    fired: list[str] = []
    down_for = now - float(down_since)
    since_drop = sum(1 for t in ((restarts or {}).get("recent_ts") or [])
                     if t >= float(down_since) - 120)
    if not st["diagnosed"] and down_for > STALL_DIAG_S and since_drop <= 1:
        st["diagnosed"] = True
        send_fn(f"🚨 IB gateway down {int(down_for // 60)} min with NO "
                f"supervisor restart since the drop: the gateway process is "
                f"alive but NOT logged in — almost always a missed IB Key "
                f"push. It will not self-heal. Open IBKR Mobile (the request "
                f"may still be pending); otherwise Render → ibkr-executor → "
                f"Restart service and approve the fresh push.")
        fired.append("stall")
    et = _et(now)
    if et.weekday() < 5 and PREOPEN_FROM <= (et.hour, et.minute) < PREOPEN_TO:
        key = et.date().isoformat()
        if st.get("preopen_paged") != key:
            st["preopen_paged"] = key
            mins = PREOPEN_TO[0] * 60 + PREOPEN_TO[1] - (et.hour * 60 + et.minute)
            send_fn(f"🚨🚨 PRE-OPEN: IB gateway still down at "
                    f"{et.strftime('%H:%M')} ET, market opens in {mins} min. "
                    f"Restart it NOW (Render → ibkr-executor → Restart "
                    f"service, then approve the IBKR push). After 09:30 a "
                    f"restart re-runs the blend mid-session.")
            fired.append("preopen")
    return fired


# --- a real book on disk with the blend switched off -------------------------
# BLEND_ENABLED=false skips the manager entirely - no reconcile, no sweep,
# no /status section, no feed - and, until now, no word about it. 2026-08-28
# -> 09-02: a real:live book ($50k, 136 BIL + $2.5k stranded cash) sat that
# way for five days and the only boot line said "blend unaffected".
DISABLED_BOOK: dict | None = None
DISABLED_BOOK_REALERT_S = 24 * 3600.0


def _check_disabled_blend_book(path: str) -> dict | None:
    """Pure: the persisted book's holdings if it is a REAL-mode book with
    anything in it, else None. Never raises (a corrupt file is the blend
    manager's problem when it IS enabled; here it just means no claim)."""
    try:
        with open(path) as fh:
            raw = json.load(fh)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, dict) or not str(raw.get("mode", "")).startswith("real:"):
        return None
    pos = raw.get("positions") or {}
    held = {"positions": len(pos),
            "spy_qty": int(raw.get("spy_qty") or 0),
            "bil_qty": int(raw.get("bil_qty") or 0),
            "sleeve_cash": round(float(raw.get("sleeve_cash") or 0.0), 2)}
    if not (pos or held["spy_qty"] or held["bil_qty"] or held["sleeve_cash"] > 0):
        return None
    return {"path": path, "mode": raw.get("mode"), "halted": raw.get("halted"),
            **held}


def _disabled_book_alert(book: dict, send_fn) -> None:
    send_fn(f"🚨🚨 blend is DISABLED (BLEND_ENABLED unset/false) but a REAL "
            f"book is on disk ({book['mode']}): {book['positions']} "
            f"position(s), {book['spy_qty']} SPY, {book['bil_qty']} BIL, "
            f"${book['sleeve_cash']:,.2f} sleeve cash. NOTHING is reconciling, "
            f"sweeping or protecting it. Set BLEND_ENABLED=true (outside "
            f"09:30-16:00 ET) or archive the book deliberately. This repeats "
            f"daily until resolved.")


def _auth(hdr: str | None, q: str | None) -> None:
    if settings.exec_token and hdr != settings.exec_token and q != settings.exec_token:
        raise HTTPException(status_code=401, detail="bad exec token")


def _build_managers():
    """Construct the state-owning managers EXACTLY ONCE per process.

    Split out of _build (counter-agent 2026-08-28): the boot retry loop calls
    the adapter build repeatedly, and re-running this part reassigns the MGR
    and BLEND globals with no lock while /kill and /resume mutate those same
    objects under MGR_LOCK/BLEND_LOCK from API threads. A /kill landing in
    that window wrote `halted` + the flatten journal onto an object the
    rebuild then replaced, and the swapped-in manager's next save() erased
    it. That window used to be one ~5-minute boot; with retries it would be
    open for as long as the gateway stays unreachable - exactly while the
    operator is reacting to 'build failed' pages and most likely to hit
    /kill."""
    global MGR, BLEND
    MGR = LadderManager(settings, settings.state_path)
    if MGR.archived_state:
        # x12: an unreadable ladder file used to become a fresh, un-halted
        # ladder in silence — open legs and `halted` forgotten.
        logger.error("ladder: %s", MGR.archived_state)
        send(f"🚨🚨 ibkr ladder: {MGR.archived_state} — verify open legs at "
             f"the venue before the ladder trades again")
    # blend3070 is opt-in: BLEND_ENABLED=false (the default) leaves the
    # service byte-for-byte as before — no manager, no polling, no /status
    # section, no state file. EXCEPT that a real book already on disk must
    # never be abandoned in silence (see _check_disabled_blend_book).
    global DISABLED_BOOK
    if not settings.blend_enabled:
        DISABLED_BOOK = _check_disabled_blend_book(settings.blend_state_path)
        if DISABLED_BOOK:
            logger.error("blend DISABLED with a real book on disk: %s",
                         DISABLED_BOOK)
            _disabled_book_alert(DISABLED_BOOK, send)
            DISABLED_BOOK["last_alert_ts"] = time.time()
    if settings.blend_enabled:
        from .blend import Blend3070Manager
        BLEND = Blend3070Manager(settings, settings.blend_state_path)
        if BLEND.archived_state:
            if BLEND.archived_state_critical:
                # y4: an UNREADABLE book is not a routine mode change —
                # open positions and `halted` were just forgotten. Same
                # severity as the ladder's sibling path.
                logger.error("blend: %s", BLEND.archived_state)
                send(f"🚨🚨 blend: {BLEND.archived_state} — verify open "
                     f"positions and resting stops at the venue")
            else:
                # Mode-transition guard: the previous book's fills belong to
                # another mode (e.g. DRY placeholder prices) — starting clean.
                logger.warning("blend: %s", BLEND.archived_state)
                send(f"⚠️ blend: starting a FRESH book — {BLEND.archived_state}")


def _build_adapter():
    """Adapter/gateway only - the part the boot loop RETRIES."""
    global ADAPTER, OUTAGES
    if not (settings.tws_userid and settings.tws_password):
        ADAPTER = DryAdapter()
        LAST["mode"] = "OFFLINE"
        logger.warning("OFFLINE mode: no TWS credentials; DryAdapter active")
        return
    if settings.dry_run:
        ADAPTER = DryAdapter()
        LAST["mode"] = f"DRY ({settings.trading_mode})"
        logger.warning("DRY_RUN with credentials: mutations stay simulated")
        # the gateway + supervisor run in DRY too (creds exist) - without a
        # ledger the /health gateway block was dark in exactly the rehearsal
        # mode that precedes live (counter-agent 2026-08-24 F6-ii). The
        # DryAdapter never calls the hooks, so this records restarts only.
        global OUTAGES
        OUTAGES = OutageLog(settings.outage_log_path)
        return
    from .ib_adapter import IBAdapter
    OUTAGES = OutageLog(settings.outage_log_path)
    if OUTAGES.history and OUTAGES.history[-1].get("ended_by") == "process_restart":
        # the previous process died mid-outage: it did NOT self-heal, and
        # that is precisely the case supervision is meant to eliminate
        logger.warning("previous gateway outage ended by process restart, "
                       "not by reconnect: %s", OUTAGES.history[-1])
    ADAPTER = IBAdapter(settings, outage_log=OUTAGES)
    LAST["mode"] = settings.trading_mode.upper()


def _build():
    """Full single-shot build (tests and any non-retrying caller)."""
    _build_managers()
    _build_adapter()


def _loop():
    global LOOP_WAKE
    # Fresh wake event per loop thread: a superseded loop from an earlier
    # lifespan (tests spawn several; daemon threads never die) keeps
    # waiting on its OLD event, so /kill only ever wakes the CURRENT loop.
    LOOP_WAKE = threading.Event()
    # A constructor raise (gateway auth, ib_async loop binding) must never
    # kill the loop thread SILENTLY (adapter review M2 sub-note): alert
    # loudly. It must ALSO NOT kill it PERMANENTLY (2026-08-28): the old
    # code `return`ed here, so a boot that merely lost a race with the
    # gateway's login left the service alive, serving /health, and inert
    # FOREVER - no loop, no reconcile, no alerts - until a human noticed
    # and redeployed. With 2FA in the login path that race is routine: the
    # gateway cannot finish logging in until the operator taps approve on
    # their phone, which is often longer than _connect()'s ~5 minute
    # budget. Retry with backoff so a late approval self-heals.
    attempt = 0
    managers_built = False
    while True:
        try:
            # Managers build ONCE (never reassigned under a live /kill) but
            # INSIDE the guarded loop: a raise from LadderManager or
            # Blend3070Manager - both of which touch the persistent disk on
            # construction - used to kill this thread with no alert at all
            # once the build was split (counter-agent re-review 2026-08-28,
            # FATAL). That is the exact "alive, serving /health, inert
            # forever" mode this batch exists to remove.
            if not managers_built:
                _build_managers()
                managers_built = True
            _build_adapter()
            break
        except Exception as exc:  # noqa: BLE001
            attempt += 1
            logger.exception("executor build failed (attempt %d): %s",
                             attempt, exc)
            # Alert on the first failure and then only rarely: a retry
            # loop must not become a pager loop (the alert-once doctrine
            # the blend's intent breaker already follows).
            if attempt == 1 or attempt % BUILD_ALERT_EVERY == 0:
                send(f"🚨🚨 ibkr-executor build failed ({exc}) — NO trading "
                     f"loop yet; retrying every {BUILD_RETRY_S:.0f}s "
                     f"(attempt {attempt}). If the gateway is waiting on a "
                     f"2FA approval, approving it recovers this with no "
                     f"redeploy.")
            time.sleep(BUILD_RETRY_S)
    if attempt:
        send(f"✅ ibkr-executor recovered after {attempt} failed build "
             f"attempt(s) — trading loop starting")
    send(f"🌊 ibkr-executor up — mode {LAST['mode']}, "
         + (f"ladder legs {[k for k in MGR.state.legs]}"
            if settings.ladder_enabled else "ladder DISABLED (LADDER_ENABLED "
            "unset)")
         + (", blend ENABLED" if settings.blend_enabled else
            ", blend DISABLED" + (" — REAL BOOK ON DISK, see the alert above"
                                  if DISABLED_BOOK else "")))
    while True:
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            nino = nino34_weekly()
            LAST["nino34"] = nino
            marks = {}
            # x12: the ladder block mutates and persists MGR — /kill and
            # /resume do the same from API threads. Serialize them exactly
            # as BLEND_LOCK serializes the blend (alerts are sent outside
            # the lock so a slow Telegram call never holds it).
            ladder_alerts: list[str] = []
            # ladder gate below: when disabled, no marks, no step(), no
            # intents - nothing can open or close. State untouched; /kill
            # still works on any previously-open leg (MGR stays built).
            with MGR_LOCK:
              if settings.ladder_enabled:
                for key, leg in MGR.state.legs.items():
                    if leg.status == "OPEN" and leg.order_ref:
                        try:
                            marks[key] = ADAPTER.mark(leg.order_ref)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("mark %s failed: %s", key, exc)
                intents = MGR.step(today, nino, marks)
                for it in intents:
                    try:
                        if it["action"] == "OPEN":
                            r = ADAPTER.open_spread(it["structure"], it["budget"])
                            MGR.on_opened(it["leg"], r["premium"], r["order_ref"], today)
                            ladder_alerts.append(
                                f"⚡ ibkr ladder OPEN {it['leg']}: {it['reason']} "
                                f"(premium ${r['premium']:,.0f}, mode {LAST['mode']})")
                        elif it["action"] == "CLOSE":
                            leg = MGR.state.legs[it["leg"]]
                            r = ADAPTER.close_spread(leg.order_ref)
                            MGR.on_closed(it["leg"], r["value"], it["reason"], today)
                            ladder_alerts.append(
                                f"⚡ ibkr ladder CLOSE {it['leg']}: {it['reason']} "
                                f"-> ${r['value']:,.0f}")
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("intent %s failed: %s", it, exc)
                        ladder_alerts.append(
                            f"🚨 ibkr intent failed ({it['action']} {it['leg']}): {exc}\n"
                            f"→ no action needed from you — forward this to Claude "
                            f"(if it repeats, gateway/credentials may need you)")
                MGR.save()
            for msg in ladder_alerts:
                send(msg)
            if BLEND is not None:
                try:
                    from .blend import fetch_intents, run_cycle
                    payload = fetch_intents(settings)
                    if payload is None:
                        # Tracker outage: the cycle STILL runs — reconcile
                        # (stop-fill ingestion, orphan cancel retries,
                        # STOP_MISSING re-placement) and the local 90-day
                        # belt are unconditional; only tracker-dependent
                        # decisions are skipped (counter-agent N13).
                        logger.warning("blend: tracker unreachable; "
                                       "reconcile-only cycle (no new "
                                       "decisions)")
                    with BLEND_LOCK:
                        run_cycle(BLEND, ADAPTER, payload, today, alert=send)
                    BLEND_CYCLE.update({"date": today, "ok": True,
                                        "error": None})
                except Exception as exc:  # noqa: BLE001
                    logger.exception("blend cycle error: %s", exc)
                    BLEND_CYCLE.update({"date": today, "ok": False,
                                        "error": str(exc),
                                        "error_ts": time.time()})
                    if BLEND.state.flatten_request is not None:
                        # R2: a queued kill-flatten must never fail
                        # silently — loud every failing cycle until done.
                        send(f"🚨🚨 blend: cycle FAILED with a /kill "
                             f"flatten QUEUED ({exc}) — nothing flattened "
                             f"yet; the loop retries next cycle, book "
                             f"stays halted")
            # Gateway watch (stall diagnosis + pre-open page) and the daily
            # disabled-book re-alert. Reporting only: a raise here must not
            # take the trading loop down, so it is guarded on its own.
            try:
                if OUTAGES is not None:
                    _gateway_watch(time.time(), OUTAGES.summary(),
                                   _gateway_restarts(), send)
                if DISABLED_BOOK and (time.time() - DISABLED_BOOK.get(
                        "last_alert_ts", 0.0)) > DISABLED_BOOK_REALERT_S:
                    _disabled_book_alert(DISABLED_BOOK, send)
                    DISABLED_BOOK["last_alert_ts"] = time.time()
            except Exception as exc:  # noqa: BLE001
                logger.warning("gateway watch failed (ignored): %s", exc)
            LAST["loop_ok"] = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.exception("loop error: %s", exc)
        LOOP_WAKE.wait(settings.poll_seconds)   # /kill sets it to skip the
        LOOP_WAKE.clear()                       # wait (queued flatten)


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_loop, daemon=True).start()
    yield


app = FastAPI(title="IBKR Executor", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    # Gateway reliability, deliberately NOT part of the health verdict:
    # tying it to `status` would make Render restart the whole container -
    # executor included, possibly mid-order - on every routine gateway blip,
    # including its mandatory daily restart. Supervision restarts the gateway
    # process alone; this block only reports.
    body = {"status": "ok", "service": "ibkr-executor", "mode": LAST["mode"],
            "loop_age_s": round(time.time() - LAST["loop_ok"], 1)
            if LAST["loop_ok"] else None}
    # The blend_loop section exists ONLY when BLEND_ENABLED (same doctrine as
    # /status's blend section): a cycle that keeps raising is caught by the
    # main loop and would otherwise fail silently — surface it here.
    if BLEND is not None:
        err_ts = BLEND_CYCLE.get("error_ts")
        qm = getattr(BLEND.state, "quotes_missing_since", None)
        body["blend_loop"] = {
            "ok": BLEND_CYCLE["ok"] is not False,
            "last_error_age_s": round(time.time() - err_ts, 1)
            if err_ts else None,
            # a cycle that skips every decision on absent quotes is a
            # SUCCESSFUL cycle, so ok:true said nothing about whether the
            # book could trade - one Telegram alert then permanent silence
            # (2026-08-24). Age, not a boolean: watchers can threshold it.
            "quotes_missing_for_s": max(0.0, round(time.time() - qm, 1))
            if qm else None}
    if DISABLED_BOOK:
        # A real book the service is NOT managing - visible from outside,
        # not only in a Telegram page that scrolled away.
        body["blend_disabled_book"] = {k: DISABLED_BOOK[k] for k in
                                       ("mode", "positions", "spy_qty",
                                        "bil_qty", "sleeve_cash", "halted")}
    if OUTAGES is not None:
        # Guarded: healthCheckPath is /health, so a raise here 500s the probe
        # and Render restarts the WHOLE container - executor included,
        # possibly mid-order. That is the exact outcome the comment above
        # says this block avoids, reached by another route (counter-agent
        # 2026-08-24, CRITICAL). Reporting must never fail the verdict.
        try:
            summ = OUTAGES.summary() or {}
            body["gateway"] = {
                "down_since": summ.get("currently_down_since"),
                "outages_30d": summ.get("outages"),
                "self_healed_30d": summ.get("self_healed"),
                "needed_a_restart_30d": summ.get("needed_a_restart"),
                "restarts_24h": (_gr := _gateway_restarts()).get("last_24h"),
                "circuit_open": _gr.get("circuit_open")}
        except Exception as exc:  # noqa: BLE001
            logger.warning("gateway health block failed (ignored): %s", exc)
            body["gateway"] = {"error": "unavailable"}
    return body


@app.get("/status")
def status(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if MGR is None:
        return {"ready": False}
    body = {"ready": True, "mode": LAST["mode"], "dry_run": settings.dry_run,
            "nino34_weekly": LAST["nino34"],
            "ladder_enabled": settings.ladder_enabled,
            "ladder": {k: vars(v) for k, v in MGR.state.legs.items()},
            "banked": MGR.state.banked, "halted": MGR.state.halted,
            "leg_budget": MGR.leg_budget(),
            "events": MGR.state.events[-40:],
            "dry_intents": getattr(ADAPTER, "log", [])[-40:]}
    # The "blend" section exists ONLY when BLEND_ENABLED: with the flag off,
    # /status is byte-identical to the pre-blend service.
    if BLEND is not None:
        # M2 (thread-safety): this handler runs on a FastAPI worker thread;
        # the ib_async event loop belongs to the service loop thread. Serve
        # the loop-thread-refreshed mark cache — NEVER call the adapter
        # from here. Staleness is shown (marks_age_s), not hidden.
        marks = BLEND.mark_cache
        body["blend"] = BLEND.status_summary(marks.get("prices") or None)
        ts = marks.get("ts")
        body["blend"]["marks_age_s"] = (round(time.time() - ts, 1)
                                        if ts else None)
    # /status is the operator's incident endpoint - it was the one place
    # blind to gateway state (counter-agent 2026-08-24)
    body.update(_gateway_report())
    return body


@app.get("/blend/feed")
def blend_feed(x_read_token: str | None = Header(default=None)):
    """READ-ONLY public-safe blend feed (the research site's Execution tab,
    reverse-proxied by the tracker). Gated by READ_TOKEN via X-Read-Token —
    a separate, weaker credential than EXEC_TOKEN: it can only read book
    state, never kill/resume or see exec surfaces. Empty READ_TOKEN (the
    default) or BLEND_ENABLED=false keeps the endpoint a 404 — nothing is
    exposed until Casey explicitly sets the token."""
    if BLEND is None or not settings.read_token:
        raise HTTPException(status_code=404, detail="not found")
    supplied = x_read_token or ""
    if not secrets.compare_digest(supplied.encode("utf-8"),
                                  settings.read_token.encode("utf-8")):
        raise HTTPException(status_code=401, detail="bad read token")
    # M2 (thread-safety): serve the loop-thread-refreshed mark cache only —
    # this handler runs on a FastAPI worker thread and must NEVER touch the
    # adapter/ib_async loop. Staleness is shown (marks_age_s), not hidden.
    marks = BLEND.mark_cache
    prices: dict = marks.get("prices") or {}
    today = datetime.now(timezone.utc).date().isoformat()
    body = BLEND.feed(prices, today)
    ts = marks.get("ts")
    body["marks_age_s"] = round(time.time() - ts, 1) if ts else None
    body["mode"] = LAST["mode"]
    body["last_cycle"] = {"date": BLEND_CYCLE["date"], "ok": BLEND_CYCLE["ok"],
                          "error": BLEND_CYCLE["error"]}
    body.update(_gateway_report())
    return body


def _gateway_report() -> dict:
    """Gateway reliability for operator endpoints. Never raises."""
    if OUTAGES is None:
        return {}
    try:
        return {"gateway_outages": OUTAGES.summary(),
                "gateway_restarts": _gateway_restarts()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("gateway report failed (ignored): %s", exc)
        return {"gateway_outages": {"error": "unavailable"}}


@app.api_route("/kill", methods=["GET", "POST"])
def kill(x_exec_token: str | None = Header(default=None),
         token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if MGR is None:
        return {"ok": False}
    blend_note = ""
    # The BLEND halt runs FIRST: it is the cheapest and most urgent action
    # here (a journal write under BLEND_LOCK), and putting the ladder's
    # adapter round-trips ahead of it would let a slow spread close delay
    # halting the book (x12 added MGR_LOCK below — never let it gate this).
    if BLEND is not None:
        # R2 (two-stage kill): this handler runs on a FastAPI worker
        # thread, but ib_async binds its event loop to the thread that owns
        # the connection — the blend loop thread. An API-thread flatten
        # pumps a FRESH loop against the shared transport: every wait times
        # out, healthy stops get mis-parked as "likely filled", and
        # cross-thread writes risk session corruption. So /kill only
        # JOURNALS the flatten request (persisted — survives a restart) and
        # halts the book immediately; the loop thread executes the flatten
        # on its next iteration (woken right away below) with
        # reconcile-first semantics (N14) and alerts what actually closed
        # vs parked — the summary here claims only what is true NOW.
        today = datetime.now(timezone.utc).date().isoformat()
        with BLEND_LOCK:
            BLEND.request_flatten(today)
        LOOP_WAKE.set()                 # flatten runs within seconds
        loop_age = (time.time() - LAST["loop_ok"]) if LAST["loop_ok"] else None
        loop_warn = ""
        if loop_age is None or loop_age > 2 * settings.poll_seconds:
            loop_warn = (" ⚠️ the execution loop looks DOWN (see /health) "
                         "— the flatten will NOT run until it recovers; "
                         "flatten manually if urgent")
        blend_note = (" + blend HALTED, flatten QUEUED for the execution "
                      "loop (it owns the venue connection); a completion "
                      "alert will state what closed vs parked" + loop_warn)
    # x12: mutating legs/halted from this API thread must not interleave
    # with the loop thread's own ladder step + save (they raced with no
    # lock at all). MGR_LOCK is taken only AFTER the blend section above
    # released BLEND_LOCK — the two locks are never held together.
    with MGR_LOCK:
        for key, leg in MGR.state.legs.items():
            if leg.status == "OPEN" and leg.order_ref:
                try:
                    r = ADAPTER.close_spread(leg.order_ref)
                    MGR.on_closed(key, r["value"], "manual kill",
                                  datetime.now(timezone.utc).date().isoformat())
                except Exception as exc:  # noqa: BLE001
                    logger.exception("kill close %s failed: %s", key, exc)
        MGR.state.halted = "KILL"
        MGR.save()
    send(f"🔴 ACTION NEEDED (you) — ibkr ladder KILLED: all legs closed, "
         f"ladder halted{blend_note}\n→ it stays halted until you hit "
         f"/resume?token=YOUR_TOKEN")
    return {"ok": True, "halted": "KILL",
            "blend": "flatten_queued" if BLEND is not None else None}


@app.api_route("/resume", methods=["GET", "POST"])
def resume(x_exec_token: str | None = Header(default=None),
           token: str | None = Query(default=None)):
    _auth(x_exec_token, token)
    if MGR is None:
        return {"ok": False}
    with MGR_LOCK:                  # x12: same serialization as /kill
        # Z-K: /resume clears EVERY halt, a data-integrity SCHEMA_DRIFT
        # exactly like a KILL. That is deliberate — y2 keeps every leg field
        # this build understands across a drifted load, so a resumed ladder
        # re-opens only genuinely WAITING legs and an OPEN leg keeps its
        # order_ref — but the operator must be told WHICH halt they just
        # cleared, or "resumed" reads like an ordinary un-kill.
        prior = MGR.state.halted
        MGR.state.halted = None
        MGR.save()
    blend_prior = None
    breakers_cleared: list = []
    seed_acked = False
    if BLEND is not None:
        # N3: /resume must not race the loop thread's cycle (a resume
        # interleaved with execute_flatten un-halts a book that is being
        # sold and lets the same cycle place fresh entries). BLEND_LOCK
        # serializes it behind any in-flight cycle, flatten included.
        with BLEND_LOCK:
            blend_prior = BLEND.state.halted
            from .blend import intent_breaker_state
            breakers_cleared = sorted(intent_breaker_state())
            BLEND.resume(datetime.now(timezone.utc).date().isoformat())
            seed_acked = BLEND.state.bootstrap_ack
    drift = "SCHEMA_DRIFT" in (prior, blend_prior)
    send("ibkr ladder resumed"
         + (f" (cleared halt: {prior})" if prior else " (was not halted)")
         + (f"; blend book resumed (cleared halt: {blend_prior})"
            if blend_prior else "")
         + (f"; blend intent breaker(s) RE-ARMED: {', '.join(breakers_cleared)}"
            if breakers_cleared else "")
         + ("\n→ this ALSO authorized the blend to seed a fresh book on top "
            "of existing venue holdings, TODAY ONLY. If that is not what you "
            "meant, /kill revokes it." if seed_acked else "")
         + ("\n→ SCHEMA_DRIFT was a data-integrity halt, not a kill: those "
            "rows came from a build this one does not fully understand. "
            "Every field this build knows was kept and nothing live was "
            "re-opened — confirm the venue matches the book before trusting "
            "the next cycle." if drift else ""))
    return {"ok": True, "cleared": prior, "blend_cleared": blend_prior}
