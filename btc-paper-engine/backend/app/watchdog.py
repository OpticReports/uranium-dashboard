"""Executor watchdog — keyless, read-only, model-free monitoring.

WHY THIS EXISTS (2026-08-22): every alert path the live stack had ran from
inside btc-executor, so the one failure it could never report was its own
death. A crashed, OOM-killed or failed-deploy executor pages nobody: the
Telegram silence looks exactly like a quiet market. The only agent-side
cover was a scheduled Claude check, which stops the moment model credits,
usage windows or the schedule itself lapse.

So the watch lives here instead, in the always-on engine, and needs no
model, no credentials and no human: a dead-man's switch that pages when the
executor stops answering, plus the engine-vs-executor coherence check that
neither service could make alone (the executor knows its ledger, the engine
knows the book; only a third party comparing them sees a mirror that has
quietly stopped mirroring).

LAW (EXECUTOR.md separation of powers): the engine stays KEYLESS. This
module reads the executor's PUBLIC /pulse and nothing else — no token, no
venue credentials, no order placement, no state mutation anywhere. It can
observe and it can page. It can never trade.

It also must never be able to break or delay the strategy: it runs on its
own daemon thread, every exception is swallowed and logged, and a failure
to reach the executor is itself just an observation (see _silence).

WHAT IT CANNOT COVER, stated plainly: it is hosted in the engine, so it
dies with the engine. Engine down alone is already covered from the other
side (the executor's stale-feed rail blocks entries and pages RED), which
makes the two services mutual watchers. Neither covers BOTH being down —
a Render account suspension or platform outage. Nothing hosted on Render
can. In that case the protection is the venue-resting stop (real order at
Coinbase, survives every host failure); an external uptime ping is the only
thing that would page. That residual is documented, not silently implied
away.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import httpx

logger = logging.getLogger(__name__)

# executor leg -> engine book. The mirror's whole job is that these agree.
LEG_BOOK = {"pullback": "S3", "trend": "S4"}


def _send(text: str) -> None:
    """Telegram, fire-and-forget. Same contract as the executor's alerts
    module: unset env is a silent no-op, and alerting can never delay or
    take down the caller."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return

    def _post():
        try:
            httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat, "text": text[:4000]}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("watchdog telegram send failed: %s", exc)

    threading.Thread(target=_post, daemon=True).start()


class Watchdog:
    """Polls the executor's public pulse and pages on trouble.

    Conditions are keyed and latched: a condition pages once when it opens,
    re-pages only after `cooldown_s` while it stays open, and sends one
    RECOVERED line when it closes. That keeps a stuck condition from
    becoming the 35-page storm the drift false-positive produced on
    2026-08-17, without ever going silent about something still broken.
    """

    def __init__(self, cfg, book_state) -> None:
        self.cfg = cfg
        # injected callable -> {"S3": {...}, "S4": {...}}; keeps this module
        # import-free of live.py (and trivially testable)
        self.book_state = book_state
        self.open: dict[str, float] = {}      # key -> last paged monotonic ts
        self.since: dict[str, float] = {}     # key -> first-seen monotonic ts
        self.last_ok: float | None = None     # last successful pulse
        self.started = time.monotonic()

    # -- condition bookkeeping ------------------------------------------
    def _fire(self, key: str, level: str, msg: str) -> None:
        now = time.monotonic()
        last = self.open.get(key)
        if last is not None and (now - last) < self.cfg.watchdog_cooldown_s:
            return                            # still open, still cooling
        self.open[key] = now
        _send(f"{level} watchdog/{key}: {msg}")
        logger.warning("watchdog %s %s: %s", level, key, msg)

    def _clear(self, key: str, msg: str) -> None:
        if self.open.pop(key, None) is not None:
            self.since.pop(key, None)
            _send(f"✅ watchdog/{key} RECOVERED: {msg}")
            logger.info("watchdog cleared %s: %s", key, msg)
        else:
            self.since.pop(key, None)

    def _persisted(self, key: str, seconds: float) -> bool:
        """True once a condition has been continuously true for `seconds`.

        Used for divergence: the executor confirms a position only after the
        engine closes the bar, so a legitimate handoff window shows as
        disagreement for minutes. A real mirror bug does not heal.
        """
        now = time.monotonic()
        first = self.since.setdefault(key, now)
        return (now - first) >= seconds

    # -- checks ----------------------------------------------------------
    def _silence(self, exc: Exception | None) -> None:
        """Dead-man's switch: the executor is not answering.

        Grace on boot: a fresh engine has no `last_ok` yet, so it measures
        silence from its own start rather than paging instantly on a
        deploy where the executor is a few seconds behind.
        """
        ref = self.last_ok if self.last_ok is not None else self.started
        quiet = time.monotonic() - ref
        if quiet >= self.cfg.watchdog_silence_s:
            self._fire("executor_silent", "🚨 ACTION NEEDED",
                       f"no pulse for {int(quiet)}s "
                       f"({exc.__class__.__name__ if exc else 'unreachable'}). "
                       "Executor may be down: check Render, then check "
                       "Coinbase for open positions. Venue stops remain "
                       "resting and still protect open trades.")

    def _coherence(self, pulse: dict) -> None:
        books = {}
        try:
            books = self.book_state() or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("watchdog book_state failed: %s", exc)
            return                            # our own fault; never page
        legs = pulse.get("legs") or {}
        for leg, book in LEG_BOOK.items():
            b, l = books.get(book), legs.get(leg)
            if not isinstance(b, dict) or not isinstance(l, dict):
                continue
            key = f"divergence_{leg}"
            engine_pos = b.get("position") is not None
            exec_pos = bool(l.get("in_position"))
            if engine_pos == exec_pos:
                self._clear(key, f"{leg}/{book} agree "
                                 f"({'in position' if exec_pos else 'flat'})")
                continue
            if not self._persisted(key, self.cfg.watchdog_divergence_s):
                continue                      # inside the handoff window
            self._fire(key, "🚨 ACTION NEEDED",
                       f"{book} engine={'POSITION' if engine_pos else 'FLAT'} "
                       f"vs executor {leg}={'POSITION' if exec_pos else 'FLAT'}"
                       f" for >{self.cfg.watchdog_divergence_s}s — the mirror "
                       "has stopped mirroring. Check /pulse and Coinbase.")

    def check(self) -> dict:
        """One pass. Returns the pulse (or {}) — for tests and /health."""
        try:
            r = httpx.get(self.cfg.watchdog_pulse_url, timeout=10)
            r.raise_for_status()
            pulse = r.json()
        except Exception as exc:  # noqa: BLE001
            self._silence(exc)
            return {}
        if not isinstance(pulse, dict):
            self._silence(None)
            return {}

        self.last_ok = time.monotonic()
        self._clear("executor_silent", "pulse answering again")

        halted = pulse.get("halted")
        if halted:
            self._fire("halted", "🚨 ACTION NEEDED",
                       f"executor HALTED ({halted}) — trading is stopped "
                       "until you resume it.")
        else:
            self._clear("halted", "not halted")

        age = pulse.get("last_target_age_s")
        if isinstance(age, (int, float)) and age > self.cfg.watchdog_target_age_s:
            self._fire("stale_feed", "⚠️",
                       f"executor's engine feed is {int(age)}s old — new "
                       "entries are blocked on its side.")
        else:
            self._clear("stale_feed", "feed fresh")

        reds = pulse.get("red_events_24h")
        if isinstance(reds, int) and reds > 0:
            self._fire("red_events", "⚠️",
                       f"{reds} RED event(s) in the last 24h — check /status.")
        else:
            self._clear("red_events", "no RED events in 24h")

        if pulse.get("ready") is False:
            self._fire("not_ready", "⚠️", "executor reports ready=false.")
        else:
            self._clear("not_ready", "ready")

        self._coherence(pulse)
        return pulse


def start_watchdog(cfg, book_state) -> Watchdog | None:
    """Start the poll thread. Returns None when disabled (default)."""
    if not cfg.watchdog_enabled or not cfg.watchdog_pulse_url:
        return None
    wd = Watchdog(cfg, book_state)

    def _loop():
        while True:
            try:
                wd.check()
            except Exception as exc:  # noqa: BLE001
                # the watchdog failing must never be able to stop the engine
                logger.exception("watchdog pass failed: %s", exc)
            time.sleep(cfg.watchdog_period_s)

    threading.Thread(target=_loop, daemon=True).start()
    logger.info("watchdog started: %s every %ss",
                cfg.watchdog_pulse_url, cfg.watchdog_period_s)
    return wd
