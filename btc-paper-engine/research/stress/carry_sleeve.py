"""Carry-sleeve emulator for the crash stress harness (RESEARCH ONLY).

Emulates the live ETH funding-carry sleeve (carry-executor/app/carry.py,
gated by backend/app/funding_monitor.py) on a 4h grid, so the integrator can
add its funding income, fees and on/off flips to the portfolio replay.

    long spot UETH qty  +  short ETH perp qty  (same qty, same mark)

Price P&L of the pair cancels by construction (both legs marked at one
price; basis NOT modelled), so the sleeve's value moves only by funding
received on the short (qty x px x rate at every 8h stamp while ON) and by
fees on the fills. The accounting is exact: value = cash + qty x entry_px at
all times, so a resize changes value only by its fees.

Timeline (everything acts at a bar CLOSE, IOC at mid, fees only):

  bar i = [T, C) with C = T + 4h.  At C, in this order:
    1. gate: every eval time E in {00,06,12,18 UTC} with T <= E < C reads
       the 30d trailing mean of annualised 8h rates over stamps <= E
       (coverage = stamps/90, < 0.5 -> reading untrusted, state frozen);
       ARM when mean >= arm (inclusive), DISARM when mean < disarm (strict),
       hysteresis in between.  The state change is applied at C, the first
       close strictly after E (carry.py acts on the next pass; here: the
       next bar's close).
    2. margin guard (carry.py _step L244): while short, if close >=
       liq x (1 - liq_buffer) -> unwind both legs at the close, no re-open
       for 24h (latched).  liq_px(short) = (usdc/qty + entry_px)/(1 + 2%),
       the HL ETH maintenance-margin formula (reproduces the venue's 8,843
       today).  usdc = usdc_backing + the sleeve's own net cash flows since
       the start (funding in, fees out, perp realised P&L, spot sale
       proceeds / purchase cost - unified-margin USDC; UETH never counts).
       The integrator post-checks the guard against the ACCOUNT's USDC path
       using the per-bar qty / entry_px / liq_px it gets back.
    3. desired = armed and not in the guard cooldown.  Open: buy spot and
       short perp at the close, qty = notional / close.  Close: sell spot,
       buy back the perp.  Fees on both legs each way.
    4. monthly resize (carry.py L271-278): at the first bar whose OPEN ts
       falls in a new UTC month, while ON, only if |qty x px / notional - 1|
       > resize_drift -> qty = notional / px; fees on the delta only.
    5. funding: every stamp s whose "bar close at or before" is C pays
       qty x close x rate_8h to the short (negative rate: the short pays).
       BitMEX stamps (04/12/20 UTC) coincide with 4h closes, so the state
       change at C precedes the stamp at C - the executor acts within
       minutes of the 18:00 eval, before the 20:00 stamp.

Nothing here touches production code or live config.
"""
from __future__ import annotations

import bisect
import csv
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

BAR_S = 4 * 3600
WINDOW_S = 30 * 86400            # the gate's trailing window
STAMPS_PER_WINDOW = 90           # 30d x 3 stamps/day (BitMEX 8h funding)
MIN_COVERAGE = 0.5               # funding_monitor.MIN_COVERAGE
EVAL_S = 6 * 3600                # funding_check_seconds (00/06/12/18 UTC)
ANNUALISE = 1095                 # 8h rate -> per year (3 x 365)
MM_ETH = 0.02                    # HL ETH maintenance margin
GUARD_COOLDOWN_S = 24 * 3600     # carry.GUARD_COOLDOWN_S
_EPS = 1e-9                      # the monitor's float-noise guard

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
BARS_DIR = os.path.join(HERE, "..", "cagr", "data")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def liq_px_short(usdc: float, qty: float, entry_px: float,
                 mm: float = MM_ETH) -> float:
    """Liquidation price of a short of `qty` entered at `entry_px` backed by
    `usdc` of margin: usdc + qty (entry - px) = mm x qty x px."""
    if qty <= 0:
        return math.nan
    return (usdc / qty + entry_px) / (1.0 + mm)


def utc(ts: int | float) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def month_of(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m")


def load_funding(path: str, lo_ms: int | None = None,
                 hi_ms: int | None = None) -> dict[int, float]:
    """{ts_ms: rate_8h} from a funding_bitmex_*.csv, optionally windowed
    (inclusive bounds, ms)."""
    out: dict[int, float] = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            t = int(r["ts_ms"])
            if lo_ms is not None and t < lo_ms:
                continue
            if hi_ms is not None and t > hi_ms:
                continue
            out[t] = float(r["rate_8h"])
    return out


def load_closes(path: str, lo: int | None = None, hi: int | None = None,
                now: float | None = None) -> dict[int, float]:
    """{ts_open: close} from a bars_4h_*.csv, keeping only CLOSED bars
    (ts + 4h <= now) and optionally windowed on the open ts (lo <= ts < hi)."""
    now = time.time() if now is None else now
    out: dict[int, float] = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            t = int(r["ts_open_unix"])
            if t + BAR_S > now:
                continue
            if lo is not None and t < lo:
                continue
            if hi is not None and t >= hi:
                continue
            out[t] = float(r["close"])
    return out


# --------------------------------------------------------------------------
# result
# --------------------------------------------------------------------------
@dataclass
class CarryResult:
    ts: list[int]                      # bar OPEN ts, the eth_closes grid
    value: list[float]                 # sleeve value at the bar close
    on: list[bool]                     # position held after the close
    funding_cum: list[float]           # net funding received, cumulative
    fees_cum: list[float]              # fees paid, cumulative (positive)
    events: list[tuple]                # (ts_open, kind, detail dict)
    liq_px: list[float]                # short's liq px after the close (nan when flat)
    # extras for the integrator's post-checks
    armed: list[bool] = field(default_factory=list)      # gate state after the close
    qty: list[float] = field(default_factory=list)        # ETH held (both legs)
    entry_px: list[float] = field(default_factory=list)   # perp short avg entry
    usdc_eff: list[float] = field(default_factory=list)   # sleeve-local USDC backing
    gate_mean: list[float] = field(default_factory=list)  # last gate reading, %/yr (nan before any)

    def flips(self) -> list[tuple]:
        """Position changes only (gate_on / gate_off / margin_guard)."""
        return [e for e in self.events if e[1] in ("gate_on", "gate_off", "margin_guard")]

    def describe(self) -> str:
        lines = []
        for t, kind, d in self.events:
            lines.append(f"{utc(d['close_ts'])}  {kind:13s} px {d['px']:>10,.2f}  "
                         f"qty {d.get('qty', 0.0):8.4f}  gate {d.get('mean_ann_pct', math.nan):6.2f}%  "
                         f"value {d['value']:>10,.2f}  {d.get('note', '')}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# the simulation
# --------------------------------------------------------------------------
def simulate_carry(eth_closes: dict[int, float], funding_8h: dict[int, float],
                   start: dict, notional: float = 30000.0,
                   usdc_backing: float = 70000.0, fee_spot_bps: float = 7.0,
                   fee_perp_bps: float = 4.5, arm: float = 8.0,
                   disarm: float = 5.0, resize_drift: float = 0.25,
                   liq_buffer: float = 0.15) -> CarryResult:
    """See the module docstring for the per-bar order of operations.

    eth_closes: {bar_open_ts_s: close}; funding_8h: {ts_ms: raw 8h rate};
    start: {'on': bool, 'qty': float, 'entry_px': float} - the live sleeve.
    The gate starts ARMED (it is armed today, 10.2%)."""
    if not eth_closes:
        raise ValueError("eth_closes is empty")
    ts = sorted(int(t) for t in eth_closes)
    closes = [float(eth_closes[t]) for t in ts]
    n = len(ts)

    # funding stamps, sorted, with prefix sums of the annualised % rate
    keys = sorted(int(k) for k in funding_8h)
    stamp_s = [k // 1000 for k in keys]
    raw = [float(funding_8h[k]) for k in keys]
    ann = [r * ANNUALISE * 100.0 for r in raw]
    pref = [0.0]
    for a in ann:
        pref.append(pref[-1] + a)

    def gate_reading(E: int) -> tuple[float | None, float]:
        """(mean annualised %, coverage) over stamps in [E - 30d, E];
        funding_monitor.trailing_mean_annualized on 8h stamps."""
        lo = bisect.bisect_left(stamp_s, E - WINDOW_S)
        hi = bisect.bisect_right(stamp_s, E)
        cnt = hi - lo
        if cnt == 0:
            return None, 0.0
        return (pref[hi] - pref[lo]) / cnt, min(1.0, cnt / STAMPS_PER_WINDOW)

    fee_s = fee_spot_bps / 1e4
    fee_p = fee_perp_bps / 1e4

    # ---- state ----
    on = bool(start.get("on", False))
    qty = float(start.get("qty", 0.0)) if on else 0.0
    entry = float(start.get("entry_px", 0.0)) if on else 0.0
    if on and (qty <= 0 or entry <= 0):
        raise ValueError("start on=True needs qty > 0 and entry_px > 0")
    cash = notional - qty * entry          # value == notional at the start
    cash0 = cash
    armed = True                           # the live gate is armed today
    guard_until = -math.inf
    last_resize_month = month_of(ts[0])
    funding_cum = 0.0
    fees_cum = 0.0
    last_mean = math.nan
    events: list[tuple] = []

    out = CarryResult(ts=ts, value=[], on=[], funding_cum=[], fees_cum=[],
                      events=events, liq_px=[])

    def value_now(px: float) -> float:
        return cash + qty * px + qty * (entry - px)   # == cash + qty*entry

    def usdc_now() -> float:
        return usdc_backing + (cash - cash0)

    def fill(dq: float, px: float) -> float:
        """Trade dq ETH on BOTH legs at px (dq > 0: buy spot / add to the
        short; dq < 0: sell spot / cover). Returns the fee. Keeps
        value == cash + qty*entry exact."""
        nonlocal cash, qty, entry, fees_cum
        notional_traded = abs(dq) * px
        fee = notional_traded * (fee_s + fee_p)
        if dq > 0:
            cash -= dq * px                              # spot buy
            entry = (qty * entry + dq * px) / (qty + dq) if qty + dq > 0 else px
            qty += dq
        else:
            d = -dq
            cash += d * px                               # spot sale
            cash += d * (entry - px)                     # perp short realised
            qty -= d
            if qty <= 1e-12:
                qty, entry = 0.0, 0.0
        cash -= fee
        fees_cum += fee
        return fee

    def event(kind: str, T: int, C: int, px: float, **extra) -> None:
        d = {"close_ts": C, "utc": utc(C), "px": px, "qty": qty,
             "entry_px": entry, "mean_ann_pct": last_mean,
             "value": value_now(px), "armed": armed}
        d.update(extra)
        events.append((T, kind, d))

    si = 0                                   # funding stamp cursor
    # skip stamps before the first close (no "close at or before" exists)
    first_close = ts[0] + BAR_S
    while si < len(stamp_s) and stamp_s[si] < first_close:
        si += 1

    for i in range(n):
        T, px = ts[i], closes[i]
        C = T + BAR_S
        C_next = ts[i + 1] + BAR_S if i + 1 < n else C + 1   # last bar: stamps == C only

        # 1. gate evals in [T, C): first close strictly after E is C
        E = -(-T // EVAL_S) * EVAL_S
        while E < C:
            mean, cov = gate_reading(E)
            if mean is not None and cov >= MIN_COVERAGE:
                last_mean = mean
                if not armed and mean >= arm - _EPS:
                    armed = True
                elif armed and mean < disarm - _EPS:
                    armed = False
            E += EVAL_S

        # 2. margin guard on the close, from the state held INTO the close
        if on and qty > 0:
            liq = liq_px_short(usdc_now(), qty, entry)
            if px >= liq * (1.0 - liq_buffer):
                fee = fill(-qty, px)
                on = False
                guard_until = C + GUARD_COOLDOWN_S
                event("margin_guard", T, C, px, fee=fee, liq_px=liq,
                      note=f"close within {liq_buffer:.0%} of liq {liq:,.2f}; "
                           f"flat until {utc(guard_until)}")

        # 3. desired state
        desired = armed and C >= guard_until
        if desired and not on:
            dq = notional / px
            fee = fill(dq, px)
            on = True
            note = "re-open after guard cooldown" if math.isfinite(guard_until) and C - guard_until < BAR_S else "open"
            event("gate_on", T, C, px, fee=fee, note=note)
        elif not desired and on:
            fee = fill(-qty, px)
            on = False
            event("gate_off", T, C, px, fee=fee, note="close: gate disarmed")

        # 4. monthly resize at the first bar of a new UTC month
        m = month_of(T)
        if m != last_resize_month:
            last_resize_month = m
            if on and qty > 0:
                drift = qty * px / notional - 1.0
                if abs(drift) > resize_drift:
                    target = notional / px
                    fee = fill(target - qty, px)
                    event("resize", T, C, px, fee=fee, drift=drift,
                          note=f"drift {drift:+.1%} -> qty {target:.4f}")

        # 5. funding stamps whose close-at-or-before is C
        while si < len(stamp_s) and stamp_s[si] < C_next:
            if on and qty > 0:
                pay = qty * px * raw[si]
                cash += pay
                funding_cum += pay
            si += 1

        # record
        out.value.append(value_now(px))
        out.on.append(on)
        out.funding_cum.append(funding_cum)
        out.fees_cum.append(fees_cum)
        out.liq_px.append(liq_px_short(usdc_now(), qty, entry) if on else math.nan)
        out.armed.append(armed)
        out.qty.append(qty)
        out.entry_px.append(entry)
        out.usdc_eff.append(usdc_now())
        out.gate_mean.append(last_mean)
    return out
