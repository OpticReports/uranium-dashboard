"""Stage A data (PREREG.md): CBOE's daily settlement file for every monthly VX contract, and the
S&P 500 VIX Short-Term Futures index rebuilt from them. Files are downloaded once to the session scratchpad
and parsed as data only (CSV; nothing executed)."""
import calendar
import csv
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "macro_2026-11"))
import mdata as md  # noqa: E402

RAW = md.w.kdata.SCRATCH + "/vixfut/cboe"
os.makedirs(RAW, exist_ok=True)
CODE = "FGHJKMNQUVXZ"
ARCH = "https://cdn.cboe.com/resources/futures/archive/volume-and-price/CFE_{c}{yy}_VX.csv"
NEW = "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{d}.csv"
FIRST, LAST = (2004, 5), (2027, 3)


def std_expiry(y, m):
    """the Wednesday 30 days before the third Friday of the following month"""
    ny, nm = (y + (m == 12)), (m % 12 + 1)
    fr = [w[calendar.FRIDAY] for w in calendar.monthcalendar(ny, nm) if w[calendar.FRIDAY]][2]
    return dt.date(ny, nm, fr) - dt.timedelta(days=30)


def _get(url, path):
    if os.path.exists(path):
        return os.path.getsize(path) > 200
    r = subprocess.run(["curl", "-sS", "-m", "60", "-o", path, "-w", "%{http_code}", url], capture_output=True, text=True)
    ok = r.stdout.strip() == "200" and os.path.getsize(path) > 200 and open(path).read(10).startswith("Trade")
    if not ok:
        open(path, "w").write("")                                             # remember the miss
    return ok


def fetch():
    """one file per monthly contract; returns {(y, m): path}"""
    out = {}
    y, m = FIRST
    while (y, m) <= LAST:
        a = f"{RAW}/arch_{y}{m:02d}.csv"
        if _get(ARCH.format(c=CODE[m - 1], yy=f"{y % 100:02d}"), a):
            out[(y, m)] = a
        else:
            e = std_expiry(y, m)
            for k in (0, -1, 1, -2, 2):                                        # a holiday moves the settlement by a day
                d = (e + dt.timedelta(days=k)).isoformat()
                p = f"{RAW}/new_{y}{m:02d}_{d}.csv"
                if _get(NEW.format(d=d), p):
                    out[(y, m)] = p
                    break
        y, m = (y + (m == 12)), (m % 12 + 1)
    return out


def _date(s):
    s = s.strip()
    if "/" in s:
        mm, dd, yy = s.split("/")
        return f"{int(yy):04d}-{int(mm):02d}-{int(dd):02d}"
    return s[:10]


def contracts():
    """{(y, m): {day: settlement}} from the files; a settlement of 0 (no price yet) is dropped.
    Prices before 2007-03-26 were quoted at 10 x the index (CBOE rescaled the contract); they are divided by 10."""
    f = RAW + "/contracts.json"
    if os.path.exists(f):
        o = json.load(open(f))
        return {tuple(int(x) for x in k.split("-")): v for k, v in o.items()}
    out = {}
    for (y, m), p in sorted(fetch().items()):
        px = {}
        for r in csv.DictReader(open(p)):
            try:
                d, s = _date(r["Trade Date"]), float(r["Settle"])
            except (KeyError, ValueError, TypeError):
                continue
            if s > 0:
                px[d] = s / 10.0 if d < "2007-03-26" and s > 90 else s
        if px:
            out[(y, m)] = px
    json.dump({f"{y}-{m}": v for (y, m), v in out.items()}, open(f, "w"))
    return out


def index(start="2005-12-20"):
    """({day: daily return of the short-term index (excess)}, detail) by the published roll rule.
    The settlement day of a contract is its last listed day; business days are the days any contract settled."""
    C = contracts()
    last = {k: max(v) for k, v in C.items()}                                   # each contract's final settlement day
    days = sorted({d for v in C.values() for d in v if d >= "2004-06-01"})
    pos = {d: i for i, d in enumerate(days)}
    keys = sorted(C)
    ret, w1_of, legs, miss = {}, {}, {}, []
    prev_w = None
    for i, d in enumerate(days):
        live = [k for k in keys if last[k] > d and min(C[k]) <= d]            # not yet at final settlement
        # first month = the nearest contract still trading tomorrow; on its final day a contract has rolled out
        if len(live) < 2:
            continue
        m1, m2 = live[0], live[1]
        # roll period: from the final-settlement day of the previous contract through the day before m1's
        prev_k = keys[keys.index(m1) - 1] if keys.index(m1) > 0 else None
        if prev_k is None or last[prev_k] not in pos or last[m1] not in pos:
            continue
        a, b = pos[last[prev_k]], pos[last[m1]] - 1                            # first and last day of the period
        dtot = b - a + 1
        k = i - a + 1                                                          # this is the k-th day of the period
        w1 = (dtot - k) / dtot
        if prev_w is not None and d >= start:
            (p1, p2, pw) = prev_w
            y = days[i - 1]
            if all(x in C[c] for c in (p1, p2) for x in (d, y)):
                num = pw * C[p1][d] + (1 - pw) * C[p2][d]
                den = pw * C[p1][y] + (1 - pw) * C[p2][y]
                ret[d] = num / den - 1
            else:
                miss.append(d)
        prev_w = (m1, m2, w1)
        w1_of[d], legs[d] = w1, (m1, m2)
    return ret, {"w1": w1_of, "legs": legs, "missing": miss, "last": {f"{y}-{m:02d}": v for (y, m), v in last.items()}}


if __name__ == "__main__":
    F = fetch()
    C = contracts()
    print("contract files", len(F), "parsed", len(C), "first", min(C), "last", max(C))
    gaps = [(y, m) for y in range(2005, 2027) for m in range(1, 13) if (y, m) not in C and (2005, 11) <= (y, m) <= (2026, 12)]
    print("monthly contracts missing between 2005-11 and 2026-12:", gaps)
    r, det = index()
    ds = sorted(r)
    print("index days", len(ds), ds[0], ds[-1], "missing", len(det["missing"]), det["missing"][:8])
    import numpy as np
    for y in ("2006", "2008", "2011", "2017", "2018", "2020", "2022", "2025"):
        x = np.array([r[d] for d in ds if d[:4] == y])
        print(y, len(x), "log growth", round(float(np.log1p(x).sum()), 3), "worst/best day", round(float(x.min()), 3), round(float(x.max()), 3))
    for d in ("2008-10-21", "2008-10-22", "2008-10-23", "2018-02-05", "2018-02-06", "2020-03-16", "2020-03-17", "2020-03-18"):
        print(d, det["legs"].get(d), round(det["w1"].get(d, float("nan")), 3), round(r.get(d, float("nan")), 4))
