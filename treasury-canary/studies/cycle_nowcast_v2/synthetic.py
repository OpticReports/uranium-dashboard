"""Cycle nowcast v2 — SYNTHETIC inputs for the dry run of run_study.py (task B3).

Nothing here reads real data. A bundle is a directory with the same layout and file formats
the real run reads (FRED CSVs, ALFRED-format vintage CSVs + vintage lists, the F6 tables
derived by vintages.py itself, an F7-format ADS panel derived by ads.derive_panel, a Piger
history workbook read by piger.load_history, an NBER turning-point CSV), so the run script,
the pipelines and the engine take exactly the code paths of the scored run.

Known structure (what the tests assert):
  * latent 6-month-growth factor f_t with recession spells (USREC) and a 2020 spike;
    g_PAYEMS = f + e_P; every other member g_c = alpha_c + beta_c * g_PAYEMS + e_c, so the
    lag-generalized bridge g_c(M) ~ 1 + g_c(M-L) + g_P(M) is EXACT for every L when the noise
    is zero (coefficients (alpha_c, 0, beta_c); projection == truth; BRIDGE_HH == realized);
  * -g6(ICSA) = g_PAYEMS + e_claims, so z_claims6(M) == COIN(M) exactly at zero noise and the
    CLAIMS_HH fit is exact too: ENS_HH error -> 0, completion errors -> 0, D-1 and D-2 PASS;
  * publication calendar: PAYEMS(M) first Friday of M+1, INDPRO(M) 15th of M+1, W875RX1(M)
    and CMRMTSPL(M-1) 28th of M+1 (one BEA day), ICSA Thursdays; so IS-A/B/C are canonical
    with K = M-2 / M-2 / M-1, except in the synthetic shutdown (delays -> lag 3 and lag 4);
  * vintage revisions: first print = truth * (1 + delta_c), second print truth * (1 + delta_c/2),
    then truth; target_first != target_latest by a known mechanism (equal when delta = 0);
  * ADS daily values = a + b * COIN_truth(month) + e_ads: the §5 calibration recovers
    slope 1/b and intercept -a/b (exactly as e_ads -> 0) and r is known in sign;
  * Piger releases with a 3x80% chain (declared at a known release), a 2020 one-month spike
    (never 3x80%, caught by the >= 50% rule at known releases), a 44% non-recession print, one
    header typo, and one ALFRED back-history glitch vintage.
Deterministic: noise is a hash of (tag, index) mapped through the normal inverse CDF; no
seeds, no random state. Standard library + numpy (+ openpyxl, a pinned dependency, to write
the Piger workbook in the format the real loader reads).
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import hashlib
import json
import math
import os
import sys
from statistics import NormalDist

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ads as A        # noqa: E402
import engine as E     # noqa: E402
import scoring as S    # noqa: E402
import vintages as V   # noqa: E402

_ND = NormalDist()
MEMBERS = ("PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL")
ALL13 = ("PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL", "PERMIT", "ICSA", "AWHMAN", "UMCSENT",
         "T10Y3M", "BAA10YM", "GS10", "TB3MS", "USREC")
# public NBER chronology used as the synthetic USREC spell set (dates only; no data values)
SPELLS = (("1960-05", "1961-02"), ("1970-01", "1970-11"), ("1973-12", "1975-03"), ("1980-02", "1980-07"),
          ("1981-08", "1982-11"), ("1990-08", "1991-03"), ("2001-04", "2001-11"), ("2008-01", "2009-06"),
          ("2020-03", "2020-04"))
ALPHA = {"PAYEMS": 0.0, "INDPRO": 0.004, "W875RX1": -0.002, "CMRMTSPL": 0.006}
BETA = {"PAYEMS": 1.0, "INDPRO": 1.3, "W875RX1": 0.8, "CMRMTSPL": 1.1}
BASE = {"PAYEMS": 52000.0, "INDPRO": 30.0, "W875RX1": 2100.0, "CMRMTSPL": 420000.0, "ICSA": 300000.0, "PERMIT": 1200.0}
FIRST_MONTH = {"PAYEMS": "1959-01", "INDPRO": "1959-01", "W875RX1": "1959-01", "CMRMTSPL": "1967-01",
               "ICSA": "1959-01", "PERMIT": "1960-01", "AWHMAN": "1959-01", "UMCSENT": "1959-01",
               "BAA10YM": "1959-01", "GS10": "1959-01", "TB3MS": "1959-01", "USREC": "1959-01", "T10Y3M": "1982-01"}

DEFAULTS = {
    "name": "noisy", "end_month": "2026-09",
    "member_noise_sd": 0.006, "payems_noise_sd": 0.004, "claims_noise_sd": 0.006, "curve_noise_sd": 0.15,
    "lead_noise_sd": 0.01,
    "first_print_delta": {"PAYEMS": 0.0006, "INDPRO": 0.004, "W875RX1": 0.005, "CMRMTSPL": 0.004},
    "vintage_obs_start": "1959-01",
    "regime_i_start": "2017-01-01", "vintage_end": "2019-12-31", "vintage_pull_start": "2016-06-01",
    "regime_ii_window": ("2000-01", "2013-05"), "list_years": ("1998-01", "2020-10"),
    # synthetic shutdown: BEA/Census releases delayed (month -> publication date)
    "delays": {"W875RX1": {"2018-12": "2019-03-01", "2019-01": "2019-03-29"},
               "CMRMTSPL": {"2018-10": "2019-03-01", "2018-11": "2019-03-29", "2018-12": "2019-03-29"}},
    "shutdown_windows": (("2018-12", "2019-03"),),
    "ads_a": 0.30, "ads_b": 2.0, "ads_noise_sd": 0.002, "ads_rev_sd": 0.10, "ads_start": "2012-06-01", "ads_daily_start": "2010-01-01",
    "piger_start": "2006-08-01", "piger_end": "2022-06-01", "piger_lag_months": 3,
    "piger_glitch_release": "2019-03-01", "piger_header_typo_release": "2019-01-01",
    "f1_as_of": "2026-08-07", "cmrmtspl_start": "1967-01",
}
ZERO_NOISE = {"name": "zero_noise", "member_noise_sd": 0.0, "payems_noise_sd": 0.0, "claims_noise_sd": 0.0,
              "curve_noise_sd": 0.0, "lead_noise_sd": 0.0,
              "first_print_delta": {"PAYEMS": 0.0, "INDPRO": 0.0, "W875RX1": 0.0, "CMRMTSPL": 0.0},
              "ads_noise_sd": 0.5, "ads_rev_sd": 0.0, "regime_i_start": "2017-06-01", "vintage_end": "2019-09-30",
              "vintage_pull_start": "2017-01-01", "delays": {}, "shutdown_windows": (),
              # CMRMTSPL from 1959 too: every member's expanding-z baseline is then identical, COIN == z(g_P)
              # exactly, the CLAIMS fit is exact and the partial 3-member mean is exact (D-2 FAIL by construction)
              "cmrmtspl_start": "1959-01"}


def params(**over) -> dict:
    p = json.loads(json.dumps(DEFAULTS))
    for k, v in over.items():
        p[k] = v
    return p


# ----------------------------------------------------------------------------- deterministic noise
def hnoise(tag: str, k) -> float:
    """Standard-normal deviate from sha256(tag:k): deterministic, platform-independent, seedless."""
    h = hashlib.sha256(f"{tag}:{k}".encode()).digest()
    u = (int.from_bytes(h[:8], "big") + 0.5) / 2.0 ** 64
    return _ND.inv_cdf(u)


# ----------------------------------------------------------------------------- calendar helpers
def months_between(a: str, b: str) -> list[str]:
    return [E.madd(a, k) for k in range(E.mdiff(b, a) + 1)]


def first_friday(m: str) -> str:
    y, mo = int(m[:4]), int(m[5:7])
    d = dt.date(y, mo, 1)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    return d.isoformat()


def day_of(m: str, day: int) -> str:
    y, mo = int(m[:4]), int(m[5:7])
    return dt.date(y, mo, min(day, calendar.monthrange(y, mo)[1])).isoformat()


def saturdays(m: str) -> list[str]:
    y, mo = int(m[:4]), int(m[5:7])
    return [dt.date(y, mo, d).isoformat() for d in range(1, calendar.monthrange(y, mo)[1] + 1) if dt.date(y, mo, d).weekday() == 5]


def weekdays(m: str) -> list[str]:
    y, mo = int(m[:4]), int(m[5:7])
    return [dt.date(y, mo, d).isoformat() for d in range(1, calendar.monthrange(y, mo)[1] + 1) if dt.date(y, mo, d).weekday() < 5]


def days_in(m: str) -> list[str]:
    y, mo = int(m[:4]), int(m[5:7])
    return [dt.date(y, mo, d).isoformat() for d in range(1, calendar.monthrange(y, mo)[1] + 1)]


def date_range(a: str, b: str, weekday: int | None = None):
    d, end = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    while d <= end:
        if weekday is None or d.weekday() == weekday:
            yield d.isoformat()
        d += dt.timedelta(days=1)


def add_days(d: str, k: int) -> str:
    return (dt.date.fromisoformat(d) + dt.timedelta(days=k)).isoformat()


# ----------------------------------------------------------------------------- the panel (truth)
def latent(months: list[str], P: dict) -> tuple[np.ndarray, np.ndarray]:
    """f_t (2*ln 6-month growth units) and USREC. Expansion mean +0.04, recession -0.08,
    the 2020 spell -0.5/-0.9 with a +0.25 rebound; AR(0.8) smoothing plus a small deterministic
    innovation (always on: the factor is the economy, not the measurement noise)."""
    n = len(months)
    usrec = np.zeros(n)
    for lo, hi in SPELLS:
        for k, m in enumerate(months):
            if lo <= m <= hi:
                usrec[k] = 1
    mu = np.where(usrec == 1, -0.08, 0.04)
    for m, v in (("2020-03", -0.5), ("2020-04", -0.9), ("2020-05", -0.45), ("2020-06", -0.1), ("2020-07", 0.25), ("2020-08", 0.2)):
        if m in months:
            mu[months.index(m)] = v
    f = np.zeros(n)
    for t in range(n):
        innov = 0.012 * hnoise("factor", t) + 0.004 * math.sin(t / 9.0)
        f[t] = (0.8 * f[t - 1] if t else 0.04) + 0.2 * mu[t] + innov
    return f, usrec


def levels_from_g6(g: np.ndarray, base: float) -> np.ndarray:
    """x_t = x_{t-6} * exp(g_t / 2): the engine's g6 recovers g exactly (first six at base)."""
    x = np.full(len(g), base)
    for t in range(6, len(g)):
        x[t] = x[t - 6] * math.exp(g[t] / 2.0)
    return x


def truth_panel(P: dict) -> dict:
    """Monthly truth for all 13 series plus the growth arrays. Returns
    {'months', 'f', 'usrec', 'g': {c: g}, 'monthly': {sid: {month: value}}, 'curve'}."""
    months = months_between("1959-01", P["end_month"])
    n = len(months)
    f, usrec = latent(months, P)
    g = {"PAYEMS": f + P["payems_noise_sd"] * np.array([hnoise("gP", t) for t in range(n)])}
    for c in ("INDPRO", "W875RX1", "CMRMTSPL"):
        g[c] = ALPHA[c] + BETA[c] * g["PAYEMS"] + P["member_noise_sd"] * np.array([hnoise("g" + c, t) for t in range(n)])
    g["CLAIMS"] = g["PAYEMS"] + P["claims_noise_sd"] * np.array([hnoise("gC", t) for t in range(n)])
    lead = lambda k: np.concatenate([f[k:], np.full(k, f[-1])])  # noqa: E731  (the factor k months ahead)
    curve = 1.0 + 20.0 * lead(6) + P["curve_noise_sd"] * np.array([hnoise("curve", t) for t in range(n)])
    g["PERMIT"] = 0.5 * lead(4) + P["lead_noise_sd"] * np.array([hnoise("permit", t) for t in range(n)])
    lv = {c: levels_from_g6(g[c], BASE[c]) for c in MEMBERS}
    lv["ICSA"] = levels_from_g6(-g["CLAIMS"], BASE["ICSA"])
    lv["PERMIT"] = levels_from_g6(g["PERMIT"], BASE["PERMIT"])
    awh = 40.0 + 10.0 * lead(2) + 0.02 * np.array([hnoise("awh", t) for t in range(n)]) * (P["lead_noise_sd"] > 0)
    sent = 85.0 + 200.0 * lead(3) + 0.5 * np.array([hnoise("sent", t) for t in range(n)]) * (P["lead_noise_sd"] > 0)
    baa = 2.0 - 10.0 * lead(1) + 0.02 * np.array([hnoise("baa", t) for t in range(n)]) * (P["lead_noise_sd"] > 0)
    gs10 = np.full(n, 6.0)
    monthly = {}
    for sid in ALL13:
        lo = P.get("cmrmtspl_start", FIRST_MONTH[sid]) if sid == "CMRMTSPL" else FIRST_MONTH[sid]
        sel = [(k, m) for k, m in enumerate(months) if m >= lo]
        if sid in lv:
            monthly[sid] = {m: float(lv[sid][k]) for k, m in sel}
        elif sid == "AWHMAN":
            monthly[sid] = {m: float(awh[k]) for k, m in sel}
        elif sid == "UMCSENT":
            monthly[sid] = {m: float(sent[k]) for k, m in sel}
        elif sid == "BAA10YM":
            monthly[sid] = {m: float(baa[k]) for k, m in sel}
        elif sid == "GS10":
            monthly[sid] = {m: float(gs10[k]) for k, m in sel}
        elif sid == "TB3MS":
            monthly[sid] = {m: float(gs10[k] - curve[k]) for k, m in sel}
        elif sid == "T10Y3M":
            monthly[sid] = {m: float(curve[k]) for k, m in sel}
        elif sid == "USREC":
            monthly[sid] = {m: float(usrec[k]) for k, m in sel}
    return {"months": months, "f": f, "usrec": usrec, "g": g, "monthly": monthly, "curve": curve}


# ----------------------------------------------------------------------------- raw observation rows (FRED / ALFRED shapes)
def obs_rows(sid: str, monthly: dict, last_month: str | None = None, last_day: str | None = None) -> list[tuple[str, str]]:
    """(date, value) rows in the native frequency: monthly first-of-month; ICSA weekly (every
    week-ending Saturday of the month carries the month's level, so the monthly mean equals
    it exactly); T10Y3M daily weekdays (constant within the month)."""
    rows = []
    for m in sorted(monthly):
        if last_month is not None and m > last_month:
            break
        v = monthly[m]
        if sid == "ICSA":
            for d in saturdays(m):
                if last_day is None or d <= last_day:
                    rows.append((d, f"{v:.6f}"))
        elif sid == "T10Y3M":
            for d in weekdays(m):
                if last_day is None or d <= last_day:
                    rows.append((d, f"{v:.6f}"))
        else:
            rows.append((m + "-01", f"{v:.12g}" if sid not in ("USREC",) else f"{int(v)}"))
    return rows


def write_fred_csv(path: str, sid: str, rows) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        f.write(f"observation_date,{sid}\n")
        for d, v in rows:
            f.write(f"{d},{v}\n")


def alfred_body(sid: str, vdate: str, rows) -> bytes:
    lines = [f"observation_date,{sid}_{vdate.replace('-', '')}"] + [f"{d},{v}" for d, v in rows]
    return ("\n".join(lines) + "\n").encode()


# ----------------------------------------------------------------------------- publication calendar
def pub_date(sid: str, M: str, P: dict) -> str:
    """Publication date of month M of series sid (synthetic calendar; delays per P['delays'])."""
    dl = P.get("delays", {}).get(sid, {})
    if M in dl:
        return dl[M]
    nxt = E.madd(M, 1)
    if sid == "PAYEMS":
        return first_friday(nxt)
    if sid == "INDPRO":
        return day_of(nxt, 15)
    if sid == "W875RX1":
        return day_of(nxt, 28)
    if sid == "CMRMTSPL":                      # CMRMTSPL(M) prints with W875RX1(M+1): the 28th of M+2
        return P.get("delays", {}).get("CMRMTSPL", {}).get(M) or day_of(E.madd(M, 2), 28)
    if sid == V.PI_SERIES:
        return day_of(nxt, 28)
    raise ValueError(sid)


def pub_calendar(sid: str, P: dict) -> dict[str, str]:
    """{month: publication date} from 2014-01, MONOTONE: a delayed month is never overtaken by
    the next month's on-time print (the later month is published the same day instead, so the
    overtaken month is never a vintage's latest month — a 'never_latest' row, as in ALFRED)."""
    out, prev = {}, None
    for M in months_between("2014-01", P["end_month"]):
        d = pub_date(sid, M, P)
        if prev is not None and d < prev:
            d = prev
        out[M] = d
        prev = d
    return out


def member_vintage_dates(sid: str, P: dict) -> dict[str, str]:
    """{vintage date: latest month} over the pull window, one vintage per publication date
    (the latest month published that day) plus, for PAYEMS, one revision-only vintage each
    20 March that restates history."""
    out = {}
    for M, d in pub_calendar(sid, P).items():
        if P["vintage_pull_start"] <= d <= P["vintage_end"]:
            out[d] = M                                   # a later month on the same day wins
    if sid == "PAYEMS":
        for y in range(int(P["vintage_pull_start"][:4]), int(P["vintage_end"][:4]) + 1):
            d = f"{y}-03-20"
            if P["vintage_pull_start"] <= d <= P["vintage_end"] and d not in out:
                latest = max(m for dd, m in out.items() if dd < d)
                out[d] = latest
    return dict(sorted(out.items()))


def vintage_values(sid: str, truth: dict, latest: str, P: dict) -> list[tuple[str, str]]:
    """Observations of the vintage whose latest month is `latest`: first print of `latest`
    = truth * (1 + delta), second print truth * (1 + delta / 2), earlier months at truth."""
    delta = P["first_print_delta"].get(sid, 0.0)
    rows = []
    for m in sorted(truth):
        if m < P["vintage_obs_start"] or m > latest:
            continue
        v = truth[m]
        if m == latest:
            v *= 1.0 + delta
        elif m == E.madd(latest, -1):
            v *= 1.0 + delta / 2.0
        rows.append((m + "-01", f"{v:.12g}"))
    return rows


# ----------------------------------------------------------------------------- Piger releases
def piger_history(P: dict, months: list[str], usrec: np.ndarray) -> list[dict]:
    """Synthetic first-release history: one release on the 1st of each month from piger_start
    to piger_end, latest month = release month - piger_lag_months. Probabilities (decimal):
    a 2008 chain 0.30 (2008-01), 0.55, 0.62, 0.85, 0.90, 0.92 ... falling through 2009; a 2020
    spike 0.60 / 0.95 / 0.30 (never three > 0.80); 2021-09 = 0.44; 0.02 elsewhere (+ a tiny
    deterministic ripple). Each release carries the same back-history (no re-basing)."""
    prob = {}
    for k, m in enumerate(months):
        prob[m] = 0.02 + 0.01 * (0.5 + 0.5 * math.sin(k / 7.0))
    path2008 = {"2007-12": 0.20, "2008-01": 0.30, "2008-02": 0.55, "2008-03": 0.62, "2008-04": 0.85, "2008-05": 0.90, "2008-06": 0.92,
                "2008-07": 0.95, "2008-08": 0.97, "2008-09": 0.98, "2008-10": 0.98, "2008-11": 0.97, "2008-12": 0.96, "2009-01": 0.95,
                "2009-02": 0.93, "2009-03": 0.90, "2009-04": 0.85, "2009-05": 0.75, "2009-06": 0.60, "2009-07": 0.30, "2009-08": 0.15,
                "2009-09": 0.12, "2009-10": 0.10, "2009-11": 0.08, "2009-12": 0.05}
    prob.update(path2008)
    prob.update({"2020-03": 0.60, "2020-04": 0.95, "2020-05": 0.30, "2020-06": 0.08, "2021-09": 0.44})
    releases = []
    for d in months_between(P["piger_start"][:7], P["piger_end"][:7]):
        rd = d + "-01"
        latest = E.madd(d, -P["piger_lag_months"])
        ms = [m for m in months if "1967-01" <= m <= latest]
        releases.append({"release_date": rd, "months": ms, "probs": [prob[m] for m in ms]})
    return releases


def write_piger_xlsx(path: str, releases: list[dict], typo_release: str | None) -> None:
    """The workbook shape piger.load_history reads: header [None, release dates...], rows
    [month, p...]; one header written with the year off by one (the real file's quirk)."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    hdr = [None]
    for r in releases:
        d = dt.date.fromisoformat(r["release_date"])
        if typo_release and r["release_date"] == typo_release:
            d = d.replace(year=d.year - 1)
        hdr.append(dt.datetime(d.year, d.month, d.day))
    ws.append(hdr)
    months = releases[-1]["months"]
    cols = [dict(zip(r["months"], r["probs"])) for r in releases]
    for m in months:
        y, mo = int(m[:4]), int(m[5:7])
        ws.append([dt.datetime(y, mo, 1)] + [c.get(m) for c in cols])
    fixed = dt.datetime(2026, 10, 20, 0, 0, 0)
    wb.properties.created = wb.properties.modified = fixed          # no wall-clock in docProps
    wb.save(path)
    _rezip_deterministic(path)


def _rezip_deterministic(path: str) -> None:
    """openpyxl stamps every zip entry with the current time; rewrite the archive with fixed
    entry timestamps so the workbook's bytes (and the bundle hashes / run_id) are reproducible."""
    import re
    import zipfile
    with zipfile.ZipFile(path) as zin:
        members = [(i.filename, zin.read(i.filename)) for i in zin.infolist()]
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in members:
            if name == "docProps/core.xml":                 # openpyxl re-stamps dcterms:modified at save time
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)", rb"\g<1>2026-10-20T00:00:00Z\g<2>", data)
                data = re.sub(rb"(<dcterms:created[^>]*>)[^<]*(</dcterms:created>)", rb"\g<1>2026-10-20T00:00:00Z\g<2>", data)
            zi = zipfile.ZipInfo(name, date_time=(2026, 10, 20, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zout.writestr(zi, data)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------- ADS archive
def ads_vintage_dates(P: dict) -> list[str]:
    """Thursdays (claims days) plus the payrolls Fridays, the 15th and the 28th in the window."""
    lo, hi = P["ads_start"], P["vintage_end"]
    ds = set(date_range(lo, hi, weekday=3))
    for M in months_between(lo[:7], hi[:7]):
        for d in (first_friday(E.madd(M, 1)), day_of(M, 15), day_of(M, 28)):
            if lo <= d <= hi:
                ds.add(d)
    return sorted(ds)


def ads_daily(P: dict, coin: dict, first_day: str, last_day: str) -> list[tuple[str, float]]:
    """ADS(day) = a + b * COIN_truth(month of day) + e; months without a COIN value (warm-up)
    are skipped by the archive (ADS starts 1960-03 in reality; here where COIN exists)."""
    out = []
    for M in months_between(first_day[:7], last_day[:7]):
        if M not in coin:
            continue
        for d in days_in(M):
            if first_day <= d <= last_day:
                out.append((d, P["ads_a"] + P["ads_b"] * coin[M] + P["ads_noise_sd"] * hnoise("ads", d)))
    return out


def ads_rows_with_revisions(daily, vdates, P) -> list[tuple]:
    """Workbook rows: value(day, vintage) = truth(day) + rev, rev = ads_rev_sd * eta_vintage *
    max(0, 1 - age/60) for days within 60 days of the vintage date (the real end-point revision:
    the filter's last two months move as later data arrive; older days are at truth), None for
    days after the vintage date."""
    do = np.array([dt.date.fromisoformat(d).toordinal() for d, _ in daily])
    vo = np.array([dt.date.fromisoformat(v).toordinal() for v in vdates])
    truth = np.array([v for _, v in daily])
    eta = np.array([hnoise("adsrev", v) for v in vdates]) * P.get("ads_rev_sd", 0.0)
    age = vo[None, :] - do[:, None]
    rev = eta[None, :] * np.clip(1.0 - age / 60.0, 0.0, 1.0)
    vals = truth[:, None] + rev
    ok = age >= 0
    rows = []
    for i, (d, _) in enumerate(daily):
        rows.append((d.replace("-", ":"), *[float(vals[i, j]) if ok[i, j] else None for j in range(len(vdates))]))
    return rows


# ----------------------------------------------------------------------------- the bundle
def sha256_file(path: str) -> str:
    return S.sha256_file(path)


def build_bundle(out_dir: str, P: dict | None = None, log=lambda *_: None) -> dict:
    """Write a complete synthetic bundle into out_dir and return its manifest."""
    P = P or params()
    os.makedirs(out_dir, exist_ok=True)
    T = truth_panel(P)
    months, monthly = T["months"], T["monthly"]
    # ---- F5: the 'frozen pull' at the end (lags like the real 2026-10-20 pull: W875RX1 M-1, CMRMTSPL M-2)
    end = P["end_month"]
    f5_last = {"PAYEMS": end, "INDPRO": end, "W875RX1": E.madd(end, -1), "CMRMTSPL": E.madd(end, -2)}
    f5_dir = os.path.join(out_dir, "f5")
    f5_raw = {}
    for sid in ALL13:
        rows = obs_rows(sid, monthly[sid], f5_last.get(sid), None)
        f5_raw[sid] = rows
        write_fred_csv(os.path.join(f5_dir, sid + ".csv"), sid, rows)
    f5_series = E.load_fred_csv_dir(f5_dir, list(ALL13))
    bundle_sha = S.series_hash(f5_series)
    # ---- F1 analog: the state as of f1_as_of (PAYEMS M, INDPRO/W875RX1 M-1, CMRMTSPL M-2 with first prints)
    f1_d = P["f1_as_of"]
    M1 = E.madd(f1_d[:7], -1)                       # payrolls day of f1_as_of month covers M-1
    f1_last = {"PAYEMS": M1, "INDPRO": E.madd(M1, -1), "W875RX1": E.madd(M1, -1), "CMRMTSPL": E.madd(M1, -2)}
    f1_raw = {}
    for sid in ALL13:
        if sid in MEMBERS:
            rows = vintage_values(sid, monthly[sid], f1_last[sid], {**P, "vintage_obs_start": "1959-01"})
        else:
            rows = obs_rows(sid, monthly[sid], None, f1_d)
            rows = [(d, v) for d, v in rows if d <= f1_d]
        f1_raw[sid] = [[d, float(v)] for d, v in rows]
    os.makedirs(os.path.join(out_dir, "f1"), exist_ok=True)
    with open(os.path.join(out_dir, "f1", "fixtures_cycle_fred.json"), "w") as f:
        json.dump(f1_raw, f, separators=(",", ":"))
    # ---- vintage cache + lists (ALFRED format), derived F6 tables via vintages.py
    cache = os.path.join(out_dir, "vintages", "cache")
    lists = os.path.join(out_dir, "vintages", "lists")
    panel_dir = os.path.join(out_dir, "vintages", "panel")
    os.makedirs(lists, exist_ok=True)
    list_records = []
    expected_lags = {}
    for sid in MEMBERS:
        vd = member_vintage_dates(sid, P)
        for d, latest in vd.items():
            body = alfred_body(sid, d, vintage_values(sid, monthly[sid], latest, P))
            V._atomic_write(V.cache_path(cache, sid, d), body)
            V._atomic_write(V.cache_path(cache, sid, d)[:-4] + ".meta.json", b"{}\n")
        # the list: regime (ii) proxy years (dates only) + the cached dates
        dates = set(vd)
        for M in months_between(P["list_years"][0], P["list_years"][1]):
            d = pub_date(sid, M, P)
            if d < P["vintage_pull_start"] and (sid != "W875RX1" or d >= S.W875_OWN_DATES_FROM):
                dates.add(d)                    # list-only dates (regime (ii) proxy); cached dates cover the rest
        list_records.append(_save_list(lists, sid, sorted(dates)))
    # PI list (dates only, regime (ii) IS-C proxy)
    list_records.append(_save_list(lists, V.PI_SERIES, sorted({pub_date(V.PI_SERIES, M, P) for M in months_between(P["list_years"][0], P["list_years"][1])
                                                               if pub_date(V.PI_SERIES, M, P) < P["vintage_pull_start"]})))
    # ICSA: Thursday vintages carrying weeks through the previous Saturday
    icsa_dates = []
    for d in date_range(P["vintage_pull_start"], P["vintage_end"], weekday=3):
        last_sat = add_days(d, -5)
        rows = [(dd, v) for dd, v in obs_rows("ICSA", monthly["ICSA"], None, last_sat) if dd >= P["vintage_obs_start"] + "-01"]
        V._atomic_write(V.cache_path(cache, "ICSA", d), alfred_body("ICSA", d, rows))
        V._atomic_write(V.cache_path(cache, "ICSA", d)[:-4] + ".meta.json", b"{}\n")
        icsa_dates.append(d)
    list_records.append(_save_list(lists, "ICSA", icsa_dates))
    # Piger releases + ALFRED RECPROUSM156N vintages (3 days after each release in the window; one glitch)
    releases = piger_history(P, months, T["usrec"])
    piger_dir = os.path.join(out_dir, "piger")
    os.makedirs(piger_dir, exist_ok=True)
    write_piger_xlsx(os.path.join(piger_dir, "History_of_Real_Time_Recession_Probabilities.xlsx"), releases, P.get("piger_header_typo_release"))
    rec_dates = []
    for r in releases:
        d = add_days(r["release_date"], 3)
        if not (P["vintage_pull_start"] <= d <= P["vintage_end"]):
            continue
        vec = {m: 100.0 * p for m, p in zip(r["months"], r["probs"])}
        if r["release_date"] == P.get("piger_glitch_release"):
            vec["2008-05"], vec["2008-06"] = 0.1, 0.1          # the back-history load glitch
        rows = [(m + "-01", f"{v:.4f}") for m, v in vec.items()]
        V._atomic_write(V.cache_path(cache, "RECPROUSM156N", d), alfred_body("RECPROUSM156N", d, rows))
        V._atomic_write(V.cache_path(cache, "RECPROUSM156N", d)[:-4] + ".meta.json", b"{}\n")
        rec_dates.append(d)
    list_records.append(_save_list(lists, "RECPROUSM156N", rec_dates))
    V.write_lists_manifest(lists, list_records)
    # derived F6 tables with the real pipeline functions
    series6 = list(MEMBERS) + ["ICSA", "RECPROUSM156N"]
    vt = V.vintage_table(cache, series6, lists, P["vintage_pull_start"])
    if vt.missing:
        raise RuntimeError(f"synthetic cache misses listed vintages: {vt.missing[:5]}")
    os.makedirs(panel_dir, exist_ok=True)
    h1 = V.write_csv(os.path.join(panel_dir, "vintage_table.csv"), vt, V.VT_FIELDS)
    idt = V.issue_dates(vt)
    h2 = V.write_csv(os.path.join(panel_dir, "issue_dates.csv"), idt, V.ID_FIELDS)
    wide, long_ = V.issue_panel(vt, idt, cache, start=P["regime_i_start"])
    h3 = V.write_csv(os.path.join(panel_dir, "issue_panel_wide.csv"), wide, V.WIDE_FIELDS)
    h4 = V.write_csv(os.path.join(panel_dir, "issue_panel_long.csv"), long_, V.LONG_FIELDS)
    with open(os.path.join(panel_dir, "build_summary.json"), "w") as f:
        json.dump({"vintage_table_sha256": h1, "issue_dates_sha256": h2, "issue_panel_wide_sha256": h3, "issue_panel_long_sha256": h4,
                   "n_vintages": len(vt), "n_issue_dates": len(wide), "start": P["vintage_pull_start"], "synthetic": True}, f, indent=1, sort_keys=True)
    # ---- ADS archive in the workbook shape -> F7 panel via ads.derive_panel (+ the monthly matrix)
    ds5 = E.build(f5_series)
    coin = {m: float(ds5.coin[i]) for i, m in enumerate(ds5.months) if np.isfinite(ds5.coin[i])}
    vdates = ads_vintage_dates(P)
    daily = ads_daily(P, coin, P["ads_daily_start"], P["vintage_end"])
    hdr = ["Date"] + [f"ADS_INDEX_{d[5:7]}{d[8:10]}{d[2:4]}" for d in vdates]
    rows = ads_rows_with_revisions(daily, vdates, P)
    panel, ref_daily, pmonths, Ssum, Ccnt, pvd, n_rows = A.derive_panel(hdr, rows, ref_vintage=vdates[0])
    ads_dir = os.path.join(out_dir, "ads")
    os.makedirs(ads_dir, exist_ok=True)
    ppath = os.path.join(ads_dir, "ads_vintage_panel.csv")
    with open(ppath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=A.PANEL_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(panel)
    np.savez(os.path.join(ads_dir, "ads_monthly_matrix.npz"), months=np.array(pmonths), vintage_dates=np.array(pvd), sums=Ssum, counts=Ccnt)
    with open(os.path.join(ads_dir, "ads_hashes.json"), "w") as f:
        json.dump({"panel_sha256": sha256_file(ppath), "matrix_sha256": sha256_file(os.path.join(ads_dir, "ads_monthly_matrix.npz")),
                   "n_vintages": len(vdates), "first_vintage": vdates[0], "last_vintage": vdates[-1], "synthetic": True,
                   "affine": {"a": P["ads_a"], "b": P["ads_b"], "noise_sd": P["ads_noise_sd"], "rev_sd": P.get("ads_rev_sd", 0.0)}}, f, indent=1, sort_keys=True)
    # ---- NBER turning points (synthetic announcement clock: peak + 9 months, trough + 15 months)
    nber_dir = os.path.join(out_dir, "nber")
    os.makedirs(nber_dir, exist_ok=True)
    with open(os.path.join(nber_dir, "nber_turning_points_announcements.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["turning_point", "type", "month", "announcement_date", "announcement_lag_months", "announcement_url"])
        for lo, hi in SPELLS:
            if lo < "1980-01":
                continue
            peak = E.madd(lo, -1)
            w.writerow([peak, "peak", peak, E.madd(peak, 9) + "-01", 9, "synthetic"])
            w.writerow([hi, "trough", hi, E.madd(hi, 15) + "-01", 15, "synthetic"])
    # ---- expected structure for the tests
    for M in months_between(P["regime_i_start"][:7], P["vintage_end"][:7]):
        for IS, sid in (("A", "PAYEMS"), ("B", "INDPRO"), ("C", "W875RX1")):
            d = pub_calendar(sid, P)[M]
            if P["regime_i_start"] <= d <= P["vintage_end"]:
                st = {c: max(m for m, dd in pub_calendar(c, P).items() if dd <= d) for c in MEMBERS}
                expected_lags[d + "|" + IS] = {"M": st["PAYEMS"], "lags": {c: E.mdiff(st["PAYEMS"], st[c]) for c in MEMBERS},
                                               "K": min(st.values())}
    manifest = {"synthetic_marker": S.SYNTHETIC_MARKER, "bundle_sha256": bundle_sha, "params": P,
                "regime_i_start": P["regime_i_start"], "shutdown_windows": P["shutdown_windows"],
                "regime_ii_window": P["regime_ii_window"], "f5_last_months": f5_last, "f1_last_months": f1_last,
                "structure": {"alpha": ALPHA, "beta": BETA, "members": MEMBERS,
                              "piger_expected": {"start_release": "2008-09-01", "start_trigger": ["2008-04", "2008-05", "2008-06"],
                                                 "first_recession_month": "2008-02", "peak_month": "2008-01",
                                                 "end_release": "2010-01-01", "trough_month": "2009-06",
                                                 "sens_1m50_2020": ["2020-06-01", "2020-07-01"], "glitch_vintage": add_days(P["piger_glitch_release"], 3) if P.get("piger_glitch_release") else None},
                              "expected_issue_states": expected_lags,
                              "ads": {"a": P["ads_a"], "b": P["ads_b"], "noise_sd": P["ads_noise_sd"], "cal_slope": 1.0 / P["ads_b"], "cal_intercept": -P["ads_a"] / P["ads_b"]}},
                "n_vintages": len(vt), "n_issue_rows": len(wide), "n_releases": len(releases), "n_ads_vintages": len(vdates)}
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    # ---- hashes of every bundle file (the F5/F6/F7/F8 freeze analog); the cache is covered by vintage_table.csv rows
    hashes = {}
    for root, _, fns in os.walk(out_dir):
        for fn in sorted(fns):
            rel = os.path.relpath(os.path.join(root, fn), out_dir)
            if rel == "hashes.json" or rel.startswith("vintages/cache/"):
                continue
            hashes[rel] = sha256_file(os.path.join(root, fn))
    with open(os.path.join(out_dir, "hashes.json"), "w") as f:
        json.dump(hashes, f, indent=1, sort_keys=True)
    log(f"[synthetic] bundle {P['name']} -> {out_dir}: {len(vt)} vintages, {len(wide)} issue rows, {len(vdates)} ADS vintages, {len(releases)} releases")
    return manifest


def _save_list(lists_dir: str, sid: str, dates: list[str]) -> dict:
    return V.save_vintage_list(lists_dir, sid, list(dates), b"synthetic", "synthetic")


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", required=True)
    p.add_argument("--zero-noise", action="store_true")
    a = p.parse_args(argv)
    m = build_bundle(a.out, params(**ZERO_NOISE) if a.zero_noise else params(), log=print)
    print(json.dumps({k: v for k, v in m.items() if k not in ("structure", "params")}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
