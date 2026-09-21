#!/usr/bin/env python3
"""Does the `fed_tightened` late-cycle flag care WHICH policy rate it reads?

Context: on 2026-09-21 the panel's "Fed tightened" chip was dark two business
days after a live 25bp hike. The flag is not a meeting detector — it fires
when the 12-month CHANGE in the 3-month rate exceeds +0.50pp, and two cuts
(2025-10-30, 2025-12-11) sit inside the same window. Before changing anything,
test whether the SERIES choice (3-month bill vs the fed funds rate) is
predictively material.

Test: for every crossing episode since 1955, compare the month the bill's
12-month change crosses +0.50pp against the month fed funds does.
  lead = bill_month - ff_month   (negative = the bill fires EARLIER)

Re-run:  python3 studies/fed_tightened_series_audit.py [datadir]
Data:    keyless FRED CSV (TB3MS, FEDFUNDS, DFEDTARU, DGS3MO), cached in datadir.
Written up in MARGIN_DEBT.md, "Flag definition audit (2026-09-21)".
"""
import csv
import datetime as dt
import os
import subprocess
import sys

BAR = 0.50          # percentage points, the flag's threshold
EPISODE_GAP = 12    # months: re-crossings inside a year are the same cycle
PAIR_WINDOW = 24    # months: how far apart two series may fire and still pair

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"


def fetch(series: str, datadir: str) -> str:
    path = os.path.join(datadir, f"{series}.csv")
    if not os.path.exists(path):
        subprocess.run(["curl", "-sS", "-m", "90", "-o", path,
                        FRED.format(series)], check=True)
    return path


def read_csv(path):
    for row in csv.reader(open(path)):
        if row[0][:1].isdigit() and row[1] not in (".", ""):
            yield dt.date.fromisoformat(row[0]), float(row[1])


def monthly(path) -> dict:
    return {(d.year, d.month): v for d, v in read_csv(path)}


def mi(t) -> int:
    """(year, month) -> month index."""
    return t[0] * 12 + t[1] - 1


def crossings(s: dict, bar: float = BAR, gap: int = EPISODE_GAP) -> list:
    """First month of each episode whose 12-month change exceeds `bar`."""
    fires, prev = [], False
    for y, m in sorted(s):
        back = (y - 1, m)
        if back not in s:
            continue
        now = s[(y, m)] - s[back] > bar
        if now and not prev and not (fires and mi((y, m)) - mi(fires[-1]) < gap):
            fires.append((y, m))
        prev = now
    return fires


def pair(fc: list, bc: list) -> list:
    """Nearest-neighbour pairing of fed-funds episodes to bill episodes."""
    rows, used = [], set()
    for f in fc:
        cand = [b for b in bc if abs(mi(b) - mi(f)) <= PAIR_WINDOW and b not in used]
        if not cand:
            rows.append((f, None, None))
            continue
        b = min(cand, key=lambda b: abs(mi(b) - mi(f)))
        used.add(b)
        rows.append((f, b, mi(b) - mi(f)))
    rows += [(None, b, None) for b in bc if b not in used]
    return sorted(rows, key=lambda r: mi(r[0] or r[1]))


def stamp(t) -> str:
    return f"{t[0]}-{t[1]:02d}" if t else "—"


def main(datadir: str) -> None:
    os.makedirs(datadir, exist_ok=True)
    bill = monthly(fetch("TB3MS", datadir))
    ff = monthly(fetch("FEDFUNDS", datadir))

    rows = pair([c for c in crossings(ff) if c[0] >= 1955],
                [c for c in crossings(bill) if c[0] >= 1955])
    leads = sorted(r[2] for r in rows if r[2] is not None)
    n = len(leads)
    med = leads[n // 2] if n % 2 else (leads[n // 2 - 1] + leads[n // 2]) / 2

    print(f"{'fed funds':>10} {'3m bill':>10} {'lead':>6}")
    for f, b, d in rows:
        print(f"{stamp(f):>10} {stamp(b):>10} {('' if d is None else f'{d:+d}'):>6}")
    print(f"\n{len(rows)} episodes since 1955, {n} paired "
          f"({sum(1 for r in rows if r[1] is None)} fed-funds-only, "
          f"{sum(1 for r in rows if r[0] is None)} bill-only)")
    print(f"median lead {med:+g} mo | mean {sum(leads) / n:+.2f} mo | "
          f"bill tied-or-earlier {sum(1 for d in leads if d <= 0)}/{n} | "
          f"within 1 month {sum(1 for d in leads if abs(d) <= 1)}/{n}")
    modern = [(r[0] or r[1], r[2]) for r in rows if r[2] is not None
              and (r[0] or r[1])[0] >= 1972]
    print("since 1972: " + ", ".join(f"{t[0]} {d:+d}" for t, d in modern))
    print(f"coverage: TB3MS from {stamp(min(bill))}, FEDFUNDS from {stamp(min(ff))}")

    # Would any alternative series flip the flag TODAY?
    print("\nlive readings (12-month change):")
    for label, s in (("TB3MS  3-month bill (monthly)", bill),
                     ("FEDFUNDS effective (monthly)", ff)):
        k = max(s)
        print(f"  {label}: {stamp(k)}  {s[k] - s[(k[0] - 1, k[1])]:+.2f}pp")
    for label, sid in (("DGS3MO 3-month bill (daily, what the flag reads)", "DGS3MO"),
                       ("DFEDTARU target upper bound (daily)", "DFEDTARU")):
        daily = list(read_csv(fetch(sid, datadir)))
        d, v = daily[-1]
        back = d - dt.timedelta(days=365)
        pd_, pv = min(daily, key=lambda t: abs((t[0] - back).days))
        print(f"  {label}: {d}  {v - pv:+.2f}pp  (vs {pd_})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else
         os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_fedflag"))
