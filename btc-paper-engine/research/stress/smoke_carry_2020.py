"""Smoke run of carry_sleeve on the COVID analogue window: real BitMEX ETHUSD
8h funding 2020-02-13..2021-02-13 and real Bitstamp ETH 4h closes, scaled so
the first close = 2,574, from the live sleeve state (ON, 11.096 @ 2,703.9).

Three runs: (A) ETHUSD funding exactly the window (the gate has no history
for its first 15 days: coverage < 0.5 -> frozen ARMED); (B) plus the real 30
days of funding before the window, so the gate reads a full window from day 1
as the live gate does; (C) XBTUSD funding (+30d) as the LINEAR-perp proxy:
BitMEX ETHUSD is a quanto settled in XBT whose funding ran structurally rich
in 2020 (mean 74%/yr, 30d mean never < 19.5%), while the live HL ETH perp is
linear USDC. Prints gate flips with dates, total funding, fees, final value.

    python3 smoke_carry_2020.py  (writes smoke_carry_2020.txt next to it)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from carry_sleeve import (BARS_DIR, DATA, load_closes, load_funding, utc,  # noqa: E402
                          simulate_carry)

LIVE = {"on": True, "qty": 11.096, "entry_px": 2703.9}
FIRST_CLOSE = 2574.0


def ts_of(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def run(label: str, lo: int, hi: int, fund_lo: int, lines: list[str],
        funding_file: str = "funding_bitmex_ETHUSD.csv") -> None:
    closes_raw = load_closes(os.path.join(BARS_DIR, "bars_4h_ethusd.csv"), lo=lo, hi=hi)
    ts0 = min(closes_raw)
    scale = FIRST_CLOSE / closes_raw[ts0]
    closes = {t: c * scale for t, c in closes_raw.items()}
    fund = load_funding(os.path.join(DATA, funding_file),
                        lo_ms=fund_lo * 1000, hi_ms=(hi + 4 * 3600) * 1000)
    r = simulate_carry(closes, fund, LIVE)
    on_bars = sum(r.on)
    lines.append(f"\n=== {label} ===")
    lines.append(f"bars {len(r.ts)}  {utc(r.ts[0])} .. {utc(r.ts[-1] + 14400)} (close)  "
                 f"scale {scale:.4f} (raw first close {closes_raw[ts0]:.2f})")
    lines.append(f"funding stamps {len(fund)}  {utc(min(fund) // 1000)} .. {utc(max(fund) // 1000)}")
    lines.append(f"start: on={LIVE['on']} qty={LIVE['qty']} entry={LIVE['entry_px']} "
                 f"-> held notional at first close {LIVE['qty'] * FIRST_CLOSE:,.0f}")
    lines.append(f"first gate reading (bar 0): {r.gate_mean[0]:.2f}%/yr; "
                 f"gate readings: min {min(g for g in r.gate_mean if g == g):.2f}  "
                 f"max {max(g for g in r.gate_mean if g == g):.2f}")
    lines.append("events (bar-close UTC, kind, px, qty, gate %, sleeve value):")
    lines.append(r.describe() or "  (none)")
    n_flips = len(r.flips())
    lines.append(f"flips {n_flips}  bars ON {on_bars}/{len(r.ts)} ({on_bars / len(r.ts):.0%})")
    lines.append(f"total funding {r.funding_cum[-1]:+,.2f}  fees {r.fees_cum[-1]:,.2f}  "
                 f"final value {r.value[-1]:,.2f}  (start 30,000.00; net {r.value[-1] - 30000:+,.2f})")
    lines.append(f"liq_px while on: min {min(x for x in r.liq_px if x == x):,.0f}  "
                 f"max ETH close {max(closes.values()):,.0f}  min {min(closes.values()):,.0f}  "
                 f"margin_guard events {sum(1 for e in r.events if e[1] == 'margin_guard')}")
    # quarterly marks
    for m in (3, 6, 9, 12):
        tq = r.ts[0] + m * 30 * 86400 if m < 12 else r.ts[-1]
        i = max(j for j, t in enumerate(r.ts) if t <= tq)
        lines.append(f"  month {m:2d} ({utc(r.ts[i] + 14400)}): value {r.value[i]:,.2f}  "
                     f"funding {r.funding_cum[i]:+,.2f}  fees {r.fees_cum[i]:,.2f}  on={r.on[i]}")


def main() -> None:
    lo, hi = ts_of("2020-02-13"), ts_of("2021-02-13")
    lines = ["carry_sleeve smoke: COVID analogue 2020-02-13 .. 2021-02-13, real ETHUSD "
             "BitMEX funding, real Bitstamp ETH 4h closes scaled to 2,574, live start"]
    run("A: funding exactly the window (gate frozen ARMED for its first 15 days)",
        lo, hi, lo, lines)
    run("B: + real 30d of funding before the window (gate reads a full window from day 1)",
        lo, hi, lo - 30 * 86400, lines)
    run("C: XBTUSD funding (+30d) as the LINEAR-perp proxy - BitMEX ETHUSD is a quanto "
        "(XBT-settled) whose funding ran structurally rich in 2020; HL ETH is a linear USDC perp",
        lo, hi, lo - 30 * 86400, lines, funding_file="funding_bitmex_XBTUSD.csv")
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(HERE, "smoke_carry_2020.txt"), "w") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    main()
