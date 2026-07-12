"""Event study — conditional forward returns behind the Playbook tab.

Run: python -m scripts.event_study   (from backend/)
Writes ../PLAYBOOK_DATA.json (consumed to build the Playbook tab + PLAYBOOK.md).

For each dashboard state-transition event, compute forward total returns at
3/6/12/24 months for: US equities (price-only, OECD index 1957+ — dividends
omitted, disclosed), 10y Treasury (total-return approximation from GS10 yields:
carry + duration*Δy + 0.5*duration²*Δy², standard literature shortcut), and
cash (TB3MS compounded). Baseline = unconditional forward returns, all months.

Events (definitions identical to scripts/backtest.py):
  INVERSION_START  first month of a sustained (>=3mo) 3m10y inversion
  DIS_INVERSION    the month the sustained inversion ends (re-steepening)
  SAHM_TRIGGER     SAHMREALTIME crosses >= 0.50 from below (deduped 24m)
  BREADTH_ALARM    leading-stack majority alarm (>=50% flashing, 2 consecutive
                   months, outside recession & post-recession echo)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backtest import (  # noqa: E402  (reuses its cached FRED CSVs + logic)
    fred_csv, month_key, add_months, months_between,
)
from app.metrics.curve import analyze_spread  # noqa: E402

HORIZONS = (3, 6, 12, 24)


def monthly_map(sid: str) -> dict[tuple[int, int], float]:
    d, v = fred_csv(sid)
    return {month_key(dd): vv for dd, vv in zip(d, v) if vv is not None}


# --- asset return series (monthly) -------------------------------------------
eq = monthly_map("SPASTT01USM661N")          # equity price index, 1957+
y10 = monthly_map("GS10")                     # 10y CMT yield, %
bill = monthly_map("TB3MS")                   # 3m bill, %

months = sorted(set(eq) & set(y10) & set(bill))

# 10y Treasury monthly total return (approximation)
tr10: dict[tuple[int, int], float] = {}
cash: dict[tuple[int, int], float] = {}
eqr: dict[tuple[int, int], float] = {}
for i in range(1, len(months)):
    m0, m1 = months[i - 1], months[i]
    y0, y1 = y10[m0] / 100.0, y10[m1] / 100.0
    dur = (1 - (1 + y0 / 2) ** -20) / (y0 / 2) if y0 > 0 else 9.0   # par-bond mod duration
    dy = y1 - y0
    tr10[m1] = y0 / 12 - dur * dy + 0.5 * dur * dur * dy * dy
    cash[m1] = bill[m0] / 1200.0
    eqr[m1] = eq[m1] / eq[m0] - 1.0


def fwd(series: dict, start: tuple[int, int], h: int) -> float | None:
    """Compound forward return over h months starting the month AFTER `start`."""
    acc = 1.0
    for k in range(1, h + 1):
        r = series.get(add_months(start, k))
        if r is None:
            return None
        acc *= (1 + r)
    return round((acc - 1) * 100.0, 1)


# --- event dates (identical definitions to backtest.py) -----------------------
tb3_d, tb3_v = fred_csv("TB3MS")
gs10_d, gs10_v = fred_csv("GS10")
m3 = dict(zip(tb3_d, tb3_v))
m10 = dict(zip(gs10_d, gs10_v))
common = sorted(set(m3) & set(m10))
sp_dates = [d for d in common if m3[d] is not None and m10[d] is not None]
sp_vals = [m10[d] - m3[d] for d in sp_dates]
a = analyze_spread(sp_dates, sp_vals, min_inversion_days=3, steepen_persist_days=6)
episodes = [e for e in a.episodes if e.sustained]
inv_starts = [month_key(e.start) for e in episodes]
dis_invs = [month_key(e.dis_inversion) for e in episodes if e.dis_inversion]

sahm = monthly_map("SAHMREALTIME")
sahm_triggers: list[tuple[int, int]] = []
prev_val = None
for ym in sorted(sahm):
    v = sahm[ym]
    if prev_val is not None and prev_val < 0.5 <= v:
        if not sahm_triggers or (ym[0] * 12 + ym[1]) - (sahm_triggers[-1][0] * 12 + sahm_triggers[-1][1]) > 24:
            sahm_triggers.append(ym)
    prev_val = v

BREADTH_ALARMS = [(1979, 11), (2001, 1), (2007, 10), (2023, 11), (2025, 11)]  # from backtest Part C

EVENTS = {
    "INVERSION_START": inv_starts,
    "DIS_INVERSION": dis_invs,
    "SAHM_TRIGGER": sahm_triggers,
    "BREADTH_ALARM": BREADTH_ALARMS,
}

ASSETS = {"equities": eqr, "treasury_10y": tr10, "cash": cash}


def median(xs: list[float]) -> float | None:
    xs = sorted(xs)
    if not xs:
        return None
    n = len(xs)
    return round(xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2, 1)


out: dict = {"generated": date.today().isoformat(), "horizons": list(HORIZONS),
             "events": {}, "baseline": {}}

# baseline: unconditional forward returns from every month with full data
for asset, series in ASSETS.items():
    out["baseline"][asset] = {}
    for h in HORIZONS:
        vals = [fwd(series, m, h) for m in months[:-h]]
        vals = [v for v in vals if v is not None]
        out["baseline"][asset][str(h)] = {"median": median(vals), "n": len(vals)}

for ev_name, dates in EVENTS.items():
    rows = []
    for ym in dates:
        row = {"date": f"{ym[0]}-{ym[1]:02d}"}
        for asset, series in ASSETS.items():
            row[asset] = {str(h): fwd(series, ym, h) for h in HORIZONS}
        rows.append(row)
    agg = {}
    for asset in ASSETS:
        agg[asset] = {}
        for h in HORIZONS:
            vals = [r[asset][str(h)] for r in rows if r[asset][str(h)] is not None]
            agg[asset][str(h)] = {"median": median(vals), "n": len(vals),
                                  "min": min(vals) if vals else None,
                                  "max": max(vals) if vals else None}
    out["events"][ev_name] = {"episodes": rows, "aggregate": agg}

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
path = os.path.join(root, "PLAYBOOK_DATA.json")
json.dump(out, open(path, "w"), indent=1)
print(f"Wrote {path}")

# generated TS module for the Playbook tab (committed; regenerate via this script)
ts_path = os.path.join(root, "frontend", "src", "lib", "playbookData.ts")
with open(ts_path, "w") as f:
    f.write("// GENERATED by backend/scripts/event_study.py — do not edit by hand.\n")
    f.write("// Conditional forward returns behind the Playbook tab.\n")
    f.write("export const PLAYBOOK_DATA = ")
    f.write(json.dumps(out, indent=1))
    f.write(" as const;\n")
print(f"Wrote {ts_path}")

# compact console summary
for ev_name, data in out["events"].items():
    print(f"\n== {ev_name} ({len(data['episodes'])} events) — median fwd returns % ==")
    print(f"{'asset':14} " + " ".join(f"{h:>7}m" for h in HORIZONS) + "   (baseline 12m)")
    for asset in ASSETS:
        base = out["baseline"][asset]["12"]["median"]
        meds = " ".join(f"{(data['aggregate'][asset][str(h)]['median'] if data['aggregate'][asset][str(h)]['median'] is not None else float('nan')):>8}" for h in HORIZONS)
        print(f"{asset:14} {meds}   ({base})")
