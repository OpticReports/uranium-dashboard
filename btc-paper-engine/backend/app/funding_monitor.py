"""Funding-regime monitor — the RESEARCH_CARRY.md deployment trigger.

Policy (Casey, 2026-08-26): the V6 carry sleeve (70% S6 + 30% funding carry)
is PARKED until the funding subsidy returns. This module measures the 30d
trailing mean annualized BTC perp funding on INTX (the venue the sleeve
would actually trade) and Hyperliquid (the hotter leading indicator), and
pages Telegram ONCE per state crossing:

  ARM    when 30d mean >= arm_pct    (default 8%/yr, >= inclusive)
  DISARM when 30d mean <  disarm_pct (default 5%/yr, strict)

The 5-8% band is deliberate hysteresis: hourly funding prints are far too
noisy for a single threshold, and even the 30d mean wanders around the
line. Threshold rationale (RESEARCH_CARRY.md "Deployment policy"):
break-even vs T-bill cash is ~4.5-5%; the extra ~3pp pays for what the
backtest did not price (margin drag, basis MTM, liquidation topology).
The threshold is a written policy, not a backtested rule - in-sample it
reduces to "run V6 in 2023-25, don't in 2026".

INTX crossings page as ACTION (the tradable venue); HL crossings as info
(leading indicator only). This module is a RESEARCH SIGNAL: it places no
trades, changes no config, and acting on an alert is a human decision.

State persists in BookStateRow("_funding_monitor") so restarts never
re-page an old crossing. Every failure degrades to a logged no-op - the
monitor must never take down or delay the engine.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone

import httpx

from . import alerts
from .config import settings

logger = logging.getLogger(__name__)

_STATE_KEY = "_funding_monitor"
WINDOW_DAYS = 30
EXPECTED_STAMPS = WINDOW_DAYS * 24
MIN_COVERAGE = 0.5          # below this the reading is untrusted: no transition
_HISTORY_MAX = 1000

_HL_URL = "https://api.hyperliquid.xyz/info"
# The venue whose state the live carry sleeve FOLLOWS (Casey, 2026-10-01:
# ETH carry in the main HL account, gated 8% on / 5% off, $30k). The
# monitor decides; carry-executor (credentialed) only executes, via
# GET /carry/target.
CARRY_VENUE = "HL_ETH"
_INTX_URL = ("https://api.international.coinbase.com/api/v1/"
             "instruments/BTC-PERP/funding")


# ---------------------------------------------------------------- fetchers

def fetch_hl_hourly(now_s: float | None = None, days: int = 31,
                    timeout: float = 30.0, coin: str = "BTC") -> dict[int, float]:
    """Hyperliquid hourly funding, {hour_epoch_s: rate}. Ascending pages,
    500 stamps (~21d) per call; stamps carry second-level jitter so keys
    are bucketed to the hour (last write wins - dedupes re-prints)."""
    now_ms = int((now_s if now_s is not None else time.time()) * 1000)
    start_ms = now_ms - days * 86400 * 1000
    out: dict[int, float] = {}
    cur = start_ms
    with httpx.Client(timeout=timeout) as client:
        for _ in range(5):
            r = client.post(_HL_URL, json={
                "type": "fundingHistory", "coin": coin,
                "startTime": cur, "endTime": now_ms})
            r.raise_for_status()
            batch = r.json() or []
            for d in batch:
                out[int(d["time"]) // 3600_000 * 3600] = float(d["fundingRate"])
            if len(batch) < 500:
                break
            cur = max(int(d["time"]) for d in batch) + 1
    return out


def fetch_intx_hourly(now_s: float | None = None, days: int = 31,
                      timeout: float = 30.0) -> dict[int, float]:
    """INTX BTC-PERP hourly funding, {hour_epoch_s: rate}. The endpoint
    pages NEWEST-FIRST (offset 0 = latest), so walk pages until one dips
    past the cutoff."""
    now = now_s if now_s is not None else time.time()
    cutoff = now - days * 86400
    out: dict[int, float] = {}
    offset = 0
    with httpx.Client(timeout=timeout) as client:
        for _ in range(12):
            r = client.get(_INTX_URL, params={"result_limit": 100,
                                              "result_offset": offset})
            r.raise_for_status()
            res = r.json().get("results") or []
            if not res:
                break
            oldest = now
            for row in res:
                ts = datetime.strptime(
                    row["event_time"], "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc).timestamp()
                oldest = min(oldest, ts)
                if ts >= cutoff:
                    out[int(ts) // 3600 * 3600] = float(row["funding_rate"])
            if oldest < cutoff or len(res) < 100:
                break
            offset += len(res)
    return out


# ---------------------------------------------------------------- metric

def trailing_mean_annualized(rates: dict[int, float], now_s: float,
                             days: int = WINDOW_DAYS) -> tuple[float | None, float]:
    """(mean annualized %, coverage 0..1) over stamps in [now-days, now].
    None when the window holds no stamps at all."""
    lo = now_s - days * 86400
    vals = [v for t, v in rates.items() if lo <= t <= now_s]
    if not vals:
        return None, 0.0
    coverage = min(1.0, len(vals) / (days * 24))
    return sum(vals) / len(vals) * 24 * 365 * 100, coverage


# ---------------------------------------------------------------- monitor

def _default_load() -> dict | None:
    from .store.db import BookStateRow, session_scope
    with session_scope() as s:
        row = s.get(BookStateRow, _STATE_KEY)
        return json.loads(row.state_json) if row is not None else None


def _default_save(state: dict) -> None:
    from .store.db import BookStateRow, session_scope
    with session_scope() as s:
        s.merge(BookStateRow(book=_STATE_KEY, state_json=json.dumps(state),
                             last_processed_bar=0))


class FundingMonitor:
    """Hysteretic ARM/DISARM state machine per venue. Injectable fetchers,
    alert fn, clock and persistence hooks keep the logic fully testable."""

    def __init__(self, fetchers=None, alert_fn=None, load_fn=None,
                 save_fn=None, clock=None):
        self.fetchers = fetchers or {
            "INTX": fetch_intx_hourly, "HL": fetch_hl_hourly,
            # the TRADED gate since 2026-10-01: the ETH carry sleeve
            # (carry-executor) is long spot UETH / short the HL ETH perp
            CARRY_VENUE: lambda now_s: fetch_hl_hourly(now_s=now_s,
                                                       coin="ETH")}
        self.alert_fn = alert_fn or alerts.send
        self.load_fn = load_fn or _default_load
        self.save_fn = save_fn or _default_save
        self.clock = clock or time.time
        self.state: dict = {"venues": {}, "history": [], "last_checked": None}
        self._loaded = False
        self._lock = threading.Lock()

    # -------- persistence --------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            saved = self.load_fn()
            if saved:
                self.state.update(saved)
        except Exception as exc:  # noqa: BLE001
            # NOT loaded (review 2026-10-01 SERIOUS-4): marking it loaded let
            # the next check() run from an empty state and overwrite the saved
            # row - in the 5-8% band that flipped an ARMED carry gate to
            # DISARMED and closed a sleeve nothing decided to close.
            logger.warning("funding monitor state load failed: %s", exc)
            self._load_err = str(exc)
            return
        self._load_fails = 0
        self._loaded = True

    def _persist(self) -> None:
        try:
            self.save_fn(self.state)
        except Exception as exc:  # noqa: BLE001
            logger.warning("funding monitor state save failed: %s", exc)

    # -------- core --------

    def _transition(self, venue: str, mean_pct: float | None,
                    coverage: float, readings: dict) -> None:
        # SCHEMA NOTE (counter-agent 2026-08-26): persisted venue dicts are
        # read with direct keys - any future key added here must be read
        # with .get defaults (or bump the state key) so old saved state
        # cannot KeyError a restarted monitor.
        v = self.state["venues"].setdefault(
            venue, {"armed": False, "mean_ann_pct": None, "coverage": None,
                    "insufficient": False, "last_change_ts": None})
        v["mean_ann_pct"] = round(mean_pct, 2) if mean_pct is not None else None
        v["coverage"] = round(coverage, 3)
        if mean_pct is None or coverage < MIN_COVERAGE:
            if not v["insufficient"]:
                logger.warning("funding monitor %s: insufficient data "
                               "(coverage %.0f%%) - state frozen",
                               venue, 100 * coverage)
            v["insufficient"] = True
            return
        v["insufficient"] = False
        arm, disarm = settings.funding_arm_pct, settings.funding_disarm_pct
        other = next((f"{k} {r[0]:.1f}%" for k, r in readings.items()
                      if k != venue and r[0] is not None), "")
        if not v["armed"] and mean_pct >= arm - 1e-9:   # inclusive under float noise
            v["armed"] = True
            v["last_change_ts"] = int(self.clock())
            if venue == CARRY_VENUE:
                self.alert_fn(
                    f"⚡ CARRY ON — HL ETH perp 30d funding "
                    f"{mean_pct:.1f}%/yr ≥ {arm:g}% ({other}). carry-executor "
                    f"opens the ETH carry sleeve (long spot UETH / short ETH "
                    f"perp) on its next pass. Turns off < {disarm:g}%.")
            elif venue == "INTX":
                self.alert_fn(
                    f"⚡ FUNDING REGIME ARMED — INTX BTC perp 30d "
                    f"funding {mean_pct:.1f}%/yr ≥ {arm:g}% "
                    f"({other}). The V6 carry-sleeve trigger fired: run the "
                    f"pre-deploy runway in RESEARCH_CARRY.md before any money "
                    f"moves. Disarms < {disarm:g}%.")
            else:
                self.alert_fn(
                    f"\U0001f4c8 HL BTC funding 30d {mean_pct:.1f}%/yr ≥ "
                    f"{arm:g}% (leading indicator; {other}). Watch for INTX "
                    f"to follow — the sleeve trades INTX.")
        elif v["armed"] and mean_pct < disarm - 1e-9:   # strict under float noise
            v["armed"] = False
            v["last_change_ts"] = int(self.clock())
            if venue == CARRY_VENUE:
                self.alert_fn(
                    f"⚡ CARRY OFF — HL ETH perp 30d funding "
                    f"{mean_pct:.1f}%/yr < {disarm:g}% ({other}). "
                    f"carry-executor closes the ETH carry sleeve on its next "
                    f"pass.")
                return
            label = ("FUNDING REGIME DISARMED — INTX" if venue == "INTX"
                     else "\U0001f4c9 HL funding disarmed —")
            self.alert_fn(
                f"{label} 30d {mean_pct:.1f}%/yr < {disarm:g}% ({other}). "
                f"Carry sleeve stays parked.")

    def check(self) -> dict:
        """One measurement + state pass. Fetch/persist failures degrade to
        logged no-ops (the daemon loop catches anything else). Network
        happens OUTSIDE the lock so /funding snapshots never block on a
        slow venue; only the state transition + persist are serialized."""
        now = self.clock()
        readings: dict[str, tuple[float | None, float]] = {}
        for venue, fetch in self.fetchers.items():
            try:
                rates = fetch(now_s=now)
                readings[venue] = trailing_mean_annualized(rates, now)
            except Exception as exc:  # noqa: BLE001
                logger.warning("funding fetch %s failed: %s", venue, exc)
                readings[venue] = (None, 0.0)
        with self._lock:
            self._ensure_loaded()
            if not self._loaded:
                # saved state unreadable: no transition, no persist, so the
                # stored hysteresis survives until the DB answers again.
                # Paged once at the 3rd failed pass in a row (re-review
                # NOTE): otherwise an unreadable row silences the monitor.
                self._load_fails = getattr(self, "_load_fails", 0) + 1
                if self._load_fails == 3:
                    try:
                        self.alert_fn(
                            f"🚨 funding monitor cannot load its saved state "
                            f"({getattr(self, '_load_err', '?')}) - no gate "
                            f"transitions until it does; the carry signal "
                            f"ages to stale and carry-executor holds.")
                    except Exception:  # noqa: BLE001
                        logger.exception("load-failure alert failed")
                return self.snapshot_locked()
            for venue, (mean_pct, coverage) in readings.items():
                self._transition(venue, mean_pct, coverage, readings)
            self.state["last_checked"] = int(now)
            self.state["history"] = (self.state["history"] + [{
                "ts": int(now),
                **{k: (round(r[0], 2) if r[0] is not None else None)
                   for k, r in readings.items()},
            }])[-_HISTORY_MAX:]
            self._persist()
            return self.snapshot_locked()

    def snapshot(self) -> dict:
        with self._lock:
            return self.snapshot_locked()

    def carry_target(self) -> dict:
        """What carry-executor follows. The ENGINE decides (keyless brain);
        the executor only executes and refuses to act on a stale or
        insufficient signal."""
        with self._lock:
            self._ensure_loaded()
            v = dict(self.state.get("venues", {}).get(CARRY_VENUE) or {})
            return {"venue": CARRY_VENUE, "coin": "ETH",
                    "armed": bool(v.get("armed", False)),
                    # unknown until the saved state has actually loaded
                    "known": self._loaded and bool(v)
                    and not v.get("insufficient", True),
                    "mean_ann_pct": v.get("mean_ann_pct"),
                    "coverage": v.get("coverage"),
                    "last_change_ts": v.get("last_change_ts"),
                    "last_checked": self.state.get("last_checked"),
                    "check_seconds": settings.funding_check_seconds,
                    "arm_pct": settings.funding_arm_pct,
                    "disarm_pct": settings.funding_disarm_pct}

    def snapshot_locked(self) -> dict:
        self._ensure_loaded()
        return {
            "policy": {"window_days": WINDOW_DAYS,
                       "arm_pct": settings.funding_arm_pct,
                       "disarm_pct": settings.funding_disarm_pct,
                       # the TRADED gate since 2026-10-01 (ETH carry);
                       # INTX stays as the BTC-sleeve reference reading
                       "gate_venue": CARRY_VENUE,
                       "btc_reference_venue": "INTX",
                       "doc": "btc-paper-engine/RESEARCH_CARRY.md"},
            "last_checked": self.state.get("last_checked"),
            "venues": self.state.get("venues", {}),
            "history_points": len(self.state.get("history", [])),
            "history": self.state.get("history", [])[-90:],
        }


MONITOR = FundingMonitor()


def start_funding_monitor() -> None:
    def _loop():
        time.sleep(60)                     # let the app/DB settle first
        while True:
            try:
                MONITOR.check()
            except Exception as exc:  # noqa: BLE001
                logger.exception("funding monitor check failed: %s", exc)
            time.sleep(settings.funding_check_seconds)

    threading.Thread(target=_loop, daemon=True).start()
