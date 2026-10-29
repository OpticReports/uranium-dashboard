"""Cycle nowcast v2 — engine (pure functions, numpy only; no network, no pandas).

Implements SPEC v1 of studies/cycle-nowcast-v2.md (sections cited per function):

  v0 §1 / v1 §1      month axis, g6, expanding z, COIN, phases, conventions
  v1 §2.1            lag-generalized bridge (component x lag), D1 row admission
  v1 §2.2            completed coincident COIN_HH(P), skip rule, band keying
  v1 §2.3            CLAIMS / CLAIMS_HH, row admission K(d) (D2/D6), IS label,
                     stored completions (D4), identity gates
  v1 §2.4            shutdown / over-lag rule (drop-and-re-mean, reason field)
  v1 §1 ENS_GRID     ENS_GRID_REPRO (selector errors through M-1) and
                     ENS_GRID_D3 (through M-2)
  v1 §7.1            reproduction_mode vs scoring_mode

Two modes (v1 §7.1):
  reproduction_mode  bridge rows t < M for every lag; CLAIMS rows t <= M-1 with
                     partial-member targets ADMITTED (the August form, n = 587
                     on F1 for the full-history fit); selector errors through M-1.
  scoring_mode       bridge rows t <= M-L (D1); CLAIMS rows t <= K(d) = M - max_c L_c
                     and complete targets only (D2/D6); selector errors through M-2 (D3).

Data contract: every public function takes {series: {YYYY-MM: value}} (monthly
dicts; ICSA and T10Y3M already collapsed to monthly means by the loaders below)
or a Dataset built from it. Nothing here reads the network. Deterministic: no
seeds, no randomness; numpy lstsq on explicit row sets.

Numerical conventions pinned (v1 §1, DT-11): population sd with the deployed
module's +1e-9 in the denominator; 120-observation warm-up INCLUSIVE of the
current month; g6 in 2*ln units (not percent).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os

import numpy as np

# ----------------------------------------------------------------------------
# constants (v0 §1, v1 §1, §2)
# ----------------------------------------------------------------------------
START = "1959-01"            # coincident members' data start (v1 §2.1, DT-10)
LEAD_START = "1960-01"       # leading composite keeps the deployed 1960 start
Z_MIN = 120                  # expanding-z warm-up, inclusive of the current month
EPS = 1e-9                   # deployed `_zs` / `_zs_at` denominator guard
MIN_ROWS = 24                # OLS minimum rows, else fallback (A10 / A22)
MAX_BRIDGE_LAG = 3           # lags 1..3 bridged; >= 4 dropped (v1 §2.4)
COIN_RECESSION = -0.75
COIN_MEMBERS = ("PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL")
BRIDGED_MEMBERS = ("INDPRO", "W875RX1", "CMRMTSPL")
MEAN_COLLAPSE = {"ICSA", "T10Y3M"}           # weekly / daily -> month mean (DT-23)
LEAD_MEMBERS = ("yield curve", "building permits", "jobless claims (inv.)",
                "factory hours", "sentiment change", "Baa spread (inv.)")
MODES = ("reproduction", "scoring")

# canonical lag patterns for the target month M (v0 §3)
PATTERNS = {
    "A": {"INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 2},
    "B": {"INDPRO": 0, "W875RX1": 1, "CMRMTSPL": 2},
    "C": {"INDPRO": 0, "W875RX1": 0, "CMRMTSPL": 1},
}
# the M-1 completion pattern each IS implies (lags L_c - 1 floored at 0, v1 §2.2)
PREV_PATTERNS = {k: {c: max(L - 1, 0) for c, L in p.items()} for k, p in PATTERNS.items()}

# the seven NBER onsets inside the 1972-01+ window and the August realized
# crossing months (v0 §7.1 table; verified from USREC on F1 by gates.py)
ONSETS = ("1973-12", "1980-02", "1981-08", "1990-08", "2001-04", "2008-01", "2020-03")
REALIZED_CROSS = ("1974-01", "1979-09", "1981-11", "1990-09", "2001-03", "2008-02", "2020-03")


# ----------------------------------------------------------------------------
# month arithmetic
# ----------------------------------------------------------------------------
def m2i(m: str) -> int:
    """'YYYY-MM' -> integer month number."""
    return int(m[:4]) * 12 + int(m[5:7]) - 1


def i2m(i: int) -> str:
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def madd(m: str, k: int) -> str:
    return i2m(m2i(m) + k)


def mdiff(a: str, b: str) -> int:
    """calendar months a - b."""
    return m2i(a) - m2i(b)


# ----------------------------------------------------------------------------
# loaders (file I/O only; parsing with the csv/json modules; untrusted files
# are data, never executed)
# ----------------------------------------------------------------------------
def monthly_from_pairs(pairs, how: str, start: str = START) -> dict:
    """[(date, value), ...] -> {YYYY-MM: value}. `how` = 'mean' (ICSA, T10Y3M:
    a week belongs to the month of its week-ending Saturday, DT-23) or 'last'.
    Observations dated before `start`-01 are dropped (the deployed fetch uses
    start=1959-01-01). Mirrors business_cycle._monthly arithmetic."""
    buckets: dict[str, list[float]] = {}
    lo = start + "-01"
    for d, v in pairs:
        d = str(d)
        if v is None:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v in ("", "."):
                continue
        v = float(v)
        if not math.isfinite(v):
            continue
        if d[:10] < lo:
            continue
        buckets.setdefault(d[:7], []).append(v)
    return {m: (sum(vs) / len(vs) if how == "mean" else vs[-1]) for m, vs in buckets.items()}


def series_from_raw(raw: dict, start: str = START) -> dict:
    """{series: [(date, value), ...]} -> {series: {YYYY-MM: value}}."""
    return {s: monthly_from_pairs(pairs, "mean" if s in MEAN_COLLAPSE else "last", start)
            for s, pairs in raw.items()}


def load_fixture_json(path: str, start: str = START) -> dict:
    """F1: backend/tests/fixtures_cycle_fred.json -> monthly series dict."""
    with open(path) as f:
        raw = json.load(f)
    return series_from_raw(raw, start)


def read_fred_csv(path: str, expect_id: str | None = None):
    """FRED fredgraph CSV -> (series_id, [(date, value_str), ...]). Header must
    be observation_date,<ID>."""
    with open(path, newline="") as f:
        r = csv.reader(f)
        hdr = next(r, None)
        if hdr is None:
            raise ValueError(f"{path}: empty body")
        if len(hdr) < 2 or hdr[0] != "observation_date":
            raise ValueError(f"{path}: unexpected header {hdr}")
        sid = hdr[1]
        if expect_id is not None and sid != expect_id:
            raise ValueError(f"{path}: header id {sid} != {expect_id}")
        rows = [(row[0], row[1]) for row in r if len(row) >= 2]
    return sid, rows


def _n_finite_rows(rows) -> int:
    """number of (date, value_str) rows whose value parses to a finite float."""
    n = 0
    for _, v in rows:
        try:
            if math.isfinite(float(str(v).strip())):
                n += 1
        except ValueError:
            continue
    return n


def load_fred_csv_dir(dirpath: str, series=None, start: str = START) -> dict:
    """F3: a directory of <ID>.csv FRED pulls -> monthly series dict."""
    if series is None:
        series = [fn[:-4] for fn in sorted(os.listdir(dirpath))
                  if fn.endswith(".csv") and fn != "multi_series.csv"]
    out = {}
    for s in series:
        p = os.path.join(dirpath, s + ".csv")
        if not os.path.exists(p):
            continue
        _, rows = read_fred_csv(p, expect_id=s)
        out[s] = monthly_from_pairs(rows, "mean" if s in MEAN_COLLAPSE else "last", start)
    return out


def read_alfred_csv(path: str, expect_id: str | None = None, expect_date: str | None = None):
    """ALFRED alfredgraph CSV -> (id, vintage YYYY-MM-DD, [(date, value_str)]).
    Validates the header `observation_date,<ID>_<YYYYMMDD>` and the v1 §4.4
    '>= 1 data row' rule (at least one row with a finite value; an empty body,
    a header-only file or an all-'.' file is refused, never an empty series)."""
    with open(path, newline="") as f:
        r = csv.reader(f)
        hdr = next(r, None)
        if hdr is None:
            raise ValueError(f"{path}: empty body")
        if len(hdr) < 2 or hdr[0] != "observation_date" or "_" not in hdr[1]:
            raise ValueError(f"{path}: unexpected ALFRED header {hdr}")
        sid, ymd = hdr[1].rsplit("_", 1)
        if len(ymd) != 8 or not ymd.isdigit():
            raise ValueError(f"{path}: bad vintage suffix {hdr[1]}")
        vd = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
        if expect_id is not None and sid != expect_id:
            raise ValueError(f"{path}: header id {sid} != {expect_id}")
        if expect_date is not None and vd != expect_date:
            raise ValueError(f"{path}: header vintage {vd} != {expect_date}")
        rows = [(row[0], row[1]) for row in r if len(row) >= 2]
    if _n_finite_rows(rows) == 0:
        raise ValueError(f"{path}: no data row with a finite value (v1 §4.4 '>= 1 data row')")
    return sid, vd, rows


def load_alfred_state(dirpath: str, date: str, series, start: str = START,
                      prefix: str = "alf_", vintage_dates: dict | None = None) -> dict:
    """F4: {dirpath}/alf_<ID>_<vd>.csv for each ID that exists -> monthly
    series dict (the vintage in hand at `date`). vd = vintage_dates[ID] when
    given (v1 §4.4: the latest LISTED vintage <= the issue date, which for a
    weekly series is usually not the issue date itself), else `date`; the file
    header must carry that vintage date. Missing files are skipped and the
    caller decides (bridge-half gating when ICSA is absent)."""
    out = {}
    for s in series:
        vd = (vintage_dates or {}).get(s, date)
        p = os.path.join(dirpath, f"{prefix}{s}_{vd}.csv")
        if not os.path.exists(p):
            continue
        _, _, rows = read_alfred_csv(p, expect_id=s, expect_date=vd)
        out[s] = monthly_from_pairs(rows, "mean" if s in MEAN_COLLAPSE else "last", start)
    return out


def latest_listed_vintage(list_path: str, d: str) -> str | None:
    """Latest date in a vd_<ID>.txt vintage list that is <= d (v1 §4.4 'for issue
    date d use the latest listed vintage <= d'); None when no listed date is <= d."""
    best = None
    with open(list_path) as f:
        for ln in f:
            v = ln.strip()
            if v and v <= d and (best is None or v > best):
                best = v
    return best


def truncate_series(series: dict, last_month: str, names=None) -> dict:
    """Return a copy with the named series (default all) cut to months <= last_month.
    Used to build synthetic information states from final-vintage data."""
    names = set(series) if names is None else set(names)
    return {s: ({m: v for m, v in d.items() if m <= last_month} if s in names else dict(d))
            for s, d in series.items()}


# ----------------------------------------------------------------------------
# transforms (v0 §1)
# ----------------------------------------------------------------------------
def g6(x: np.ndarray) -> np.ndarray:
    """6-month annualized log growth 2*(ln x_M - ln x_{M-6}) on a gap-free
    monthly axis; nan where either end is missing or non-positive."""
    x = np.asarray(x, float)
    out = np.full(x.shape, np.nan)
    if len(x) > 6:
        a, b = x[6:], x[:-6]
        ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
        tmp = np.full(a.shape, np.nan)
        tmp[ok] = 2.0 * (np.log(a[ok]) - np.log(b[ok]))
        out[6:] = tmp
    return out


def expanding_z(x: np.ndarray, zmin: int = Z_MIN, eps: float = EPS) -> np.ndarray:
    """Expanding z-score: history = all finite values up to and INCLUDING the
    current one (nan skipped, not appended); output once the history has
    >= zmin values; population sd + eps. Mirrors business_cycle._zs."""
    x = np.asarray(x, float)
    out = np.full(x.shape, np.nan)
    idx = np.flatnonzero(np.isfinite(x))
    vals = x[idx]
    for k in range(zmin - 1, len(vals)):
        h = vals[:k + 1]
        out[idx[k]] = (vals[k] - h.mean()) / (h.std() + eps)
    return out


def z_against(hist: np.ndarray, x: float, zmin: int = Z_MIN, eps: float = EPS):
    """z of x against a history that EXCLUDES x (bridged projections, v1 §1
    DT-11); None when the history is shorter than zmin."""
    h = np.asarray(hist, float)
    h = h[np.isfinite(h)]
    if len(h) < zmin:
        return None
    return float((x - h.mean()) / (h.std() + eps))


def ols(X, y) -> np.ndarray:
    """OLS with intercept via numpy lstsq (same call as the deployed _ols)."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    A = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return beta


def label3(x) -> str | None:
    """3-phase scoring label (v0 §1): CONTRACTION < -0.75 <= STALL < 0 <= EXPANSION."""
    if x is None or not np.isfinite(x):
        return None
    return "CONTRACTION" if x < COIN_RECESSION else "STALL" if x < 0 else "EXPANSION"


def phase5(coin, lead) -> str | None:
    """Deployed 5-phase board label (business_cycle.phase_of)."""
    if coin is None or lead is None or not (np.isfinite(coin) and np.isfinite(lead)):
        return None
    if coin < COIN_RECESSION:
        return "CONTRACTION"
    if coin < 0 and lead < -0.3:
        return "SLOWDOWN"
    if coin < 0:
        return "STALL"
    if lead < -0.5:
        return "LATE_CYCLE"
    return "EXPANSION"


# ----------------------------------------------------------------------------
# Dataset: month axis + coincident members + CLAIMS regressors
# ----------------------------------------------------------------------------
class Dataset:
    """Monthly arrays on a gap-free PAYEMS month axis from `start` to the last
    PAYEMS month (v0 §1: 'Month axis = PAYEMS months'). Index arithmetic equals
    calendar-month arithmetic.

    G[c]  6m growth of member c;  Z[c] its actual expanding z (through its own month)
    coin  available-member mean of Z (COIN; 3-member 1969-06..1977-05 on F1)
    nmem  members available per month; complete[t] = every member that EXISTS
          for t (t >= its first z month) has a z at t  (D6; the 1969-06..1977-05
          three-member months count as complete)
    zc    z_claims6 series form: expanding z of -g6(monthly-mean ICSA)
    zk    z_curve series form: expanding z of T10Y3M (GS10-TB3MS before 1982-01)
    """

    def __init__(self, series: dict, start: str = START, end: str | None = None):
        if "PAYEMS" not in series or not series["PAYEMS"]:
            raise ValueError("PAYEMS is required: it defines the month axis")
        self.series = series
        last = max(series["PAYEMS"]) if end is None else end
        i0, i1 = m2i(start), m2i(last)
        self.start = start
        self.months = [i2m(i) for i in range(i0, i1 + 1)]
        self.n = len(self.months)
        self.idx = {m: i for i, m in enumerate(self.months)}
        self.raw = {s: self._align(d) for s, d in series.items()}
        self.G = {c: g6(self.raw[c]) if c in self.raw else np.full(self.n, np.nan)
                  for c in COIN_MEMBERS}
        self.Z = {c: expanding_z(self.G[c]) for c in COIN_MEMBERS}
        self.first_z = {}
        for c in COIN_MEMBERS:
            f = np.flatnonzero(np.isfinite(self.Z[c]))
            self.first_z[c] = int(f[0]) if len(f) else None
        Zm = np.column_stack([self.Z[c] for c in COIN_MEMBERS])
        fin = np.isfinite(Zm)
        self.nmem = fin.sum(1)
        with np.errstate(invalid="ignore"):
            self.coin = np.where(self.nmem > 0, np.nansum(Zm, 1) / np.maximum(self.nmem, 1), np.nan)
        exists = np.zeros_like(fin)
        for j, c in enumerate(COIN_MEMBERS):
            if self.first_z[c] is not None:
                exists[self.first_z[c]:, j] = True
        self.exists = exists
        self.complete = (self.nmem > 0) & np.all(~exists | fin, axis=1)
        # CLAIMS regressors (series form, DT-11)
        if "ICSA" in self.raw:
            self.zc = expanding_z(-g6(self.raw["ICSA"]))
        else:
            self.zc = np.full(self.n, np.nan)
        self.curve = self._curve()
        self.zk = expanding_z(self.curve)
        self.usrec = self.raw.get("USREC")
        self._cache: dict = {}

    # -- helpers -------------------------------------------------------------
    def _align(self, d: dict) -> np.ndarray:
        out = np.full(self.n, np.nan)
        for m, v in d.items():
            i = self.idx.get(m)
            if i is not None:
                out[i] = v
        return out

    def _curve(self) -> np.ndarray:
        t = self.raw.get("T10Y3M")
        g = self.raw.get("GS10")
        tb = self.raw.get("TB3MS")
        out = np.full(self.n, np.nan)
        if t is not None:
            out = t.copy()
        if g is not None and tb is not None:
            alt = g - tb
            fill = ~np.isfinite(out) & np.isfinite(alt)
            out[fill] = alt[fill]
        return out

    def i(self, m: str) -> int:
        return self.idx[m]

    def last_index(self, s: str) -> int | None:
        """index of the last finite observation of series s on the axis."""
        if s not in self.raw:
            return None
        f = np.flatnonzero(np.isfinite(self.raw[s]))
        return int(f[-1]) if len(f) else None

    def exists_at(self, c: str, i: int) -> bool:
        return self.first_z[c] is not None and i >= self.first_z[c]

    def available_mean(self, i: int, members) -> float:
        """mean of the actual z of the given members at i (nan if any missing);
        members that do not exist at i are skipped like the realized composite."""
        zs = []
        for c in members:
            if not self.exists_at(c, i):
                continue
            z = self.Z[c][i]
            if not np.isfinite(z):
                return float("nan")
            zs.append(z)
        return float(np.mean(zs)) if zs else float("nan")


def build(series: dict, start: str = START, end: str | None = None) -> Dataset:
    return Dataset(series, start, end)


# ----------------------------------------------------------------------------
# leading composite (as deployed: 1960 start, PAYEMS & INDPRO axis, 3m MA)
# ----------------------------------------------------------------------------
def leading_composite(series: dict, start: str = LEAD_START) -> tuple[list, np.ndarray, dict]:
    """Deployed leading composite (v0 §1, v1 §2.1): axis = months with both
    PAYEMS and INDPRO, >= start; members curve, g6 PERMIT, -g6 ICSA, AWHMAN,
    dUMCSENT, -BAA10YM, each expanding-z on that axis; mean of available; then
    a 3-month moving average of the up-to-3 available values. Docstring note
    (DT-10): the deployed module's frozen leading claims (3 of 15 spells false,
    strictly early 4 of 7, 82.5% real-time agreement) were measured on these
    1960-start labels; the 1959 start applies to the coincident members only.
    Returns (months, lead, member_z)."""
    months = sorted(set(series["PAYEMS"]) & set(series["INDPRO"]))
    months = [m for m in months if m >= start]
    n = len(months)

    def arr(name):
        d = series.get(name, {})
        return np.array([d.get(m, np.nan) if d.get(m) is not None else np.nan for m in months], float)

    t, g, tb = arr("T10Y3M"), arr("GS10"), arr("TB3MS")
    curve = t.copy()
    alt = g - tb
    fill = ~np.isfinite(curve) & np.isfinite(alt)
    curve[fill] = alt[fill]
    sent = arr("UMCSENT")
    dsent = np.full(n, np.nan)
    dsent[1:] = sent[1:] - sent[:-1]
    mz = {
        LEAD_MEMBERS[0]: expanding_z(curve),
        LEAD_MEMBERS[1]: expanding_z(g6(arr("PERMIT"))),
        LEAD_MEMBERS[2]: expanding_z(-g6(arr("ICSA"))),
        LEAD_MEMBERS[3]: expanding_z(arr("AWHMAN")),
        LEAD_MEMBERS[4]: expanding_z(dsent),
        LEAD_MEMBERS[5]: expanding_z(-arr("BAA10YM")),
    }
    Zm = np.column_stack(list(mz.values()))
    k = np.isfinite(Zm).sum(1)
    with np.errstate(invalid="ignore"):
        raw = np.where(k > 0, np.nansum(Zm, 1) / np.maximum(k, 1), np.nan)
    lead = np.full(n, np.nan)
    for i in range(n):
        w = raw[max(0, i - 2):i + 1]
        w = w[np.isfinite(w)]
        if len(w):
            lead[i] = w.mean()
    return months, lead, mz


# ----------------------------------------------------------------------------
# lag-generalized bridge (v1 §2.1; D1)
# ----------------------------------------------------------------------------
def _check_mode(mode: str):
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")


def bridge_rows_end(i: int, L: int, mode: str) -> int:
    """Last admissible training row for the bridge of lag L at target index i:
    scoring_mode t <= M-L (D1: g_c(t) must be in hand); reproduction_mode t < M."""
    return i - L if mode == "scoring" else i - 1


def bridge_fit(ds: Dataset, c: str, L: int, T: int):
    """OLS g_c(t) ~ 1 + g_c(t-L) + g_PAYEMS(t) on rows L <= t <= T with all
    three terms defined. Returns (beta|None, n_rows); None when n < MIN_ROWS
    (caller falls back to g_c(M-L), A10). Cached per (c, L, T)."""
    key = ("bf", c, L, T)
    hit = ds._cache.get(key)
    if hit is not None:
        return hit
    g, gp = ds.G[c], ds.G["PAYEMS"]
    if T < L:
        res = (None, 0)
    else:
        t = np.arange(L, T + 1)
        ok = np.isfinite(g[t]) & np.isfinite(g[t - L]) & np.isfinite(gp[t])
        n = int(ok.sum())
        if n < MIN_ROWS:
            res = (None, n)
        else:
            res = (ols(np.column_stack([g[t - L][ok], gp[t][ok]]), g[t][ok]), n)
    ds._cache[key] = res
    return res


def bridge_member(ds: Dataset, i: int, c: str, L: int, mode: str):
    """z of member c for month index i at observed lag L.
    L = 0 -> actual z (status 'actual'); 1..3 -> bridged projection z-scored
    against g_c history through i-L, projection excluded (status 'bridged', or
    'fallback' when the fit has < MIN_ROWS rows); L >= 4 -> 'dropped' (v1 §2.4);
    a member that does not exist at i -> 'not_existing' (skipped as the realized
    composite skips it); history < 120 -> 'skipped_short_history' (v1 §2.2).
    Returns (z or nan, status, info)."""
    _check_mode(mode)
    if not ds.exists_at(c, i):
        # the realized composite skips a member before its first z month
        # (CMRMTSPL before 1977-06): the completion skips it too (A3/A7)
        return (float("nan"), "not_existing", {})
    if L == 0:
        z = ds.Z[c][i]
        return (float(z), "actual", {}) if np.isfinite(z) else (float("nan"), "actual_missing", {})
    if L > MAX_BRIDGE_LAG:
        return (float("nan"), "dropped", {"lag": L})
    if i - L < 0:
        return (float("nan"), "inputs_missing", {})
    gl, gp = ds.G[c][i - L], ds.G["PAYEMS"][i]
    if not (np.isfinite(gl) and np.isfinite(gp)):
        return (float("nan"), "inputs_missing", {})
    T = bridge_rows_end(i, L, mode)
    beta, n = bridge_fit(ds, c, L, T)
    if beta is None:
        proj, status = float(gl), "fallback"
    else:
        proj, status = float(beta[0] + beta[1] * gl + beta[2] * gp), "bridged"
    hist = ds.G[c][:i - L + 1]
    z = z_against(hist, proj)
    if z is None:
        return (float("nan"), "skipped_short_history",
                {"hist_n": int(np.isfinite(hist).sum()), "lag": L})
    return (z, status, {"n_fit": n, "beta": None if beta is None else [float(b) for b in beta],
                        "proj_g": proj, "rows_through": ds.months[T] if 0 <= T < ds.n else None,
                        "lag": L})


def pattern_key(bridged: dict, dropped=(), skipped=()) -> str:
    """Stable string key for a bridged pattern P plus the dropped set and the
    skipped set (v1 §2.2 band keying). The skipped members (short-history rule,
    1977-06/07 on F1) are part of the key so a completion whose bridged member
    was skipped is never filed under the all-actual pattern."""
    b = ",".join(f"{c}:{int(L)}" for c, L in sorted(bridged.items()))
    d = ",".join(sorted(dropped))
    s = ",".join(sorted(skipped))
    return f"bridged[{b}]|dropped[{d}]|skipped[{s}]"


def complete_month(ds: Dataset, i: int, pattern: dict, mode: str) -> dict:
    """COIN_HH(month i | pattern) (v1 §2.2): mean over the four members of the
    actual z where lag 0, the bridged z at lags 1..3, dropped at lag >= 4 with
    the mean re-taken, short-history members skipped and flagged. `pattern`
    maps member -> lag (members absent from it are lag 0; PAYEMS is always 0).
    value is nan when an existing, non-dropped member has no z (partial state)."""
    out = {"month": ds.months[i], "actual": [], "bridged": {}, "fallback": [],
           "skipped": [], "dropped": [], "missing": [], "not_existing": [], "fits": {}}
    zs = []
    for c in COIN_MEMBERS:
        L = int(pattern.get(c, 0))
        z, st, info = bridge_member(ds, i, c, L, mode)
        if st == "actual":
            zs.append(z)
            out["actual"].append(c)
        elif st in ("bridged", "fallback"):
            zs.append(z)
            out["bridged"][c] = L
            out["fits"][c] = info
            if st == "fallback":
                out["fallback"].append(c)
        elif st == "dropped":
            out["dropped"].append(c)
        elif st == "skipped_short_history":
            out["skipped"].append(c)
        elif st == "not_existing":
            out["not_existing"].append(c)
        else:
            out["missing"].append(c)
    out["value"] = float(np.mean(zs)) if zs and not out["missing"] else float("nan")
    out["n_members"] = len(zs)
    out["pattern_key"] = pattern_key(out["bridged"], out["dropped"], out["skipped"])
    out["requested_pattern"] = {c: int(L) for c, L in pattern.items()}
    return out


def coin_hh_history(ds: Dataset, pattern: dict, mode: str) -> np.ndarray:
    """Stored walk-forward completions COIN_HH(m | pattern) for EVERY month m on
    the axis (D4: computed once per (m, pattern) with fits through m-L only,
    never recomputed with a later fit). Cached. Used as the CLAIMS_HH training
    regressor history (the 'spliced history' when no per-issue-date store
    exists, v1 §4.1) and as the HH persistence form."""
    key = ("hh", tuple(sorted((c, int(L)) for c, L in pattern.items())), mode)
    hit = ds._cache.get(key)
    if hit is not None:
        return hit
    out = np.full(ds.n, np.nan)
    for i in range(ds.n):
        if ds.nmem[i] == 0:
            continue
        out[i] = complete_month(ds, i, pattern, mode)["value"]
    ds._cache[key] = out
    return out


# ----------------------------------------------------------------------------
# CLAIMS / CLAIMS_HH (v0 §1 method 5, v1 §2.3)
# ----------------------------------------------------------------------------
def claims_features(ds: Dataset, i: int, prev: float):
    """[COIN_prev, z_claims6(i), z_claims6(i) - z_claims6(i-3), z_curve(i)] or None."""
    if i < 3 or prev is None or not np.isfinite(prev):
        return None
    f = [float(prev), float(ds.zc[i]), float(ds.zc[i] - ds.zc[i - 3]), float(ds.zk[i])]
    return f if all(np.isfinite(f)) else None


def claims_design(ds: Dataset, prev_series: np.ndarray, require_complete: bool, tag: str):
    """Row-wise design for COIN(t) ~ 1 + prev_series[t-1] + z_claims6(t) +
    d3 z_claims6(t) + z_curve(t): returns (F (n x 4), valid mask). valid[t]
    needs every feature finite, COIN(t) finite and (D6) complete[t] when
    require_complete. The design's content tag hashes BOTH the regressor
    history and the valid mask (so two designs on the same history with
    different row admission — require_complete True vs False — never alias);
    the cache key is (caller tag, require_complete, content tag)."""
    n = ds.n
    F = np.full((n, 4), np.nan)
    F[1:, 0] = prev_series[:-1]
    F[:, 1] = ds.zc
    F[3:, 2] = ds.zc[3:] - ds.zc[:-3]
    F[:, 3] = ds.zk
    valid = np.isfinite(F).all(1) & np.isfinite(ds.coin)
    if require_complete:
        valid &= ds.complete
    tag = f"{tag}|rc={int(bool(require_complete))}:{_design_tag(np.where(np.isfinite(prev_series), prev_series, -9.0), valid)}"
    key = ("cd", tag)
    hit = ds._cache.get(key)
    if hit is not None:
        return hit[0]
    res = (F, valid, tag)
    ds._cache[key] = (res,)
    return res


def claims_fit(ds: Dataset, design, T: int):
    """OLS on the design rows t <= T. Returns (beta|None, n, first_row, last_row).
    The cache key is the design's own content tag (regressor history AND valid
    mask, see claims_design) plus T: two different designs can never share a fit."""
    key = ("cfit", design[2], T)
    hit = ds._cache.get(key)
    if hit is not None:
        return hit
    F, valid = design[0], design[1]
    rows = np.flatnonzero(valid[:T + 1]) if T >= 0 else np.array([], int)
    n = len(rows)
    if n < MIN_ROWS:
        res = (None, n, None, None)
    else:
        res = (ols(F[rows], ds.coin[rows]), n, ds.months[rows[0]], ds.months[rows[-1]])
    ds._cache[key] = res
    return res


def claims_value(ds: Dataset, i: int, T: int, design, prev_forecast: float):
    """CLAIMS estimate for target index i from the fit on rows t <= T and the
    forecast row [prev_forecast, z_claims6(i), d3, z_curve(i)]. Falls back to
    prev_forecast (persistence, A18) when the fit has < MIN_ROWS rows or the
    forecast features are undefined (1972-01..1977-08 on F1)."""
    beta, n, r0, r1 = claims_fit(ds, design, T)
    f = claims_features(ds, i, prev_forecast)
    if beta is None or f is None:
        return float(prev_forecast), "fallback", n, None
    return float(beta[0] + beta[1:] @ np.asarray(f)), "fit", n, beta


# ----------------------------------------------------------------------------
# IS label, lags, row admission (v1 §2.3)
# ----------------------------------------------------------------------------
def is_label(P_indpro: int, P_w875: int, M: int) -> str:
    """IS LABEL at any date: A if P_INDPRO < M; B if P_INDPRO = M and P_W875RX1 < M;
    C if P_W875RX1 = M. CMRMTSPL is carried as a lag, never in the label."""
    if P_indpro < M:
        return "A"
    if P_w875 < M:
        return "B"
    return "C"


def information_state(ds: Dataset) -> dict:
    """From the vintage in hand: M = last PAYEMS month, P_c, lags L_c = M - P_c,
    K(d) = min_c P_c = M - max_c L_c, IS label."""
    M_i = ds.last_index("PAYEMS")
    P = {}
    for c in COIN_MEMBERS:
        li = ds.last_index(c)
        P[c] = li if li is not None else -1
    lags = {c: int(M_i - P[c]) for c in COIN_MEMBERS}
    K_i = min(P.values())
    return {"M_i": int(M_i), "M": ds.months[M_i], "P": P, "lags": lags,
            "K_i": int(K_i), "K": ds.months[K_i] if K_i >= 0 else None,
            "IS": is_label(P["INDPRO"], P["W875RX1"], M_i)}


def admissible_rows(ds: Dataset, K_i: int) -> np.ndarray:
    """ROW ADMISSION (D2/D6): row t admissible iff t <= K(d) and COIN(t) is a
    complete-member mean (3-member 1969-06..1977-05 count as complete)."""
    mask = np.zeros(ds.n, bool)
    if K_i >= 0:
        mask[:K_i + 1] = True
    return mask & ds.complete


def claims_rows_end(i: int, Lmax: int, mode: str) -> int:
    """Last CLAIMS training row for target index i: reproduction t <= M-1;
    scoring t <= K(d) = M - max_c L_c (D2)."""
    return i - 1 if mode == "reproduction" else i - Lmax


# ----------------------------------------------------------------------------
# lag simulation (v0 §3 / v1 §3): one pattern, one mode, one claims form
# ----------------------------------------------------------------------------
def scored_window_end(ds: Dataset) -> str:
    """v1 §1 Windows: the scored window ends at the last month in which all four
    members are published (the last complete COIN on the fixture; 2026-05 on F1).
    The scored-run script passes window=('1972-01', scored_window_end(ds)) and
    logs it with n; the reproduction gate keeps the F1 default (1972-01..2026-06)."""
    comp = np.flatnonzero(ds.complete)
    if not len(comp):
        raise ValueError("no complete COIN month on this dataset")
    return ds.months[int(comp[-1])]


def eval_targets(ds: Dataset, window=("1972-01", "2026-06")) -> list:
    """target indices i with window[0] <= month <= window[1], COIN(i) and COIN(i-1) finite.
    The default window is the F1 reproduction-gate window (v1 §7.1); the scored
    run uses ('1972-01', scored_window_end(ds))."""
    lo, hi = window
    return [i for i, m in enumerate(ds.months)
            if lo <= m <= hi and i >= 1 and np.isfinite(ds.coin[i]) and np.isfinite(ds.coin[i - 1])]


def simulate(ds: Dataset, pattern: dict, mode: str, targets=None, claims_form: str = "hh",
             window=("1972-01", "2026-06")) -> dict:
    """Walk-forward lag-pattern simulation on final-vintage data.

    pattern      member -> lag for the target month M (e.g. PATTERNS['A'])
    mode         'reproduction' | 'scoring' (row admission, v1 §7.1)
    claims_form  'original' : regressor realized COIN(t-1) in training and
                              realized COIN(M-1) in the forecast row (August)
                 'hh'       : regressor = stored completions COIN_HH(t-1 | prev
                              pattern) in training AND forecast (v1 §2.3, D4)
                 'S'        : August training; forecast regressor = available-
                              members mean of M-1 (the deployed ENS_BC_S form)
    Returns arrays over the eval targets: months, y (realized COIN(M)),
    pers_real / pers_avail / pers_hh (three persistence forms, D5), bridge
    (= COIN_HH(M | pattern)), claims, ens (0.5/0.5), comp_prev (COIN_HH(M-1)),
    claims_status, plus per-row completion flags."""
    _check_mode(mode)
    if claims_form not in ("original", "hh", "S"):
        raise ValueError(claims_form)
    if targets is None:
        targets = eval_targets(ds, window)
    pattern = {c: int(L) for c, L in pattern.items()}
    Lmax = max([0] + [L for L in pattern.values()])
    prev_pattern = {c: max(L - 1, 0) for c, L in pattern.items()}
    hist_prev = coin_hh_history(ds, prev_pattern, mode)
    if claims_form == "hh":
        prev_series, tag = hist_prev, "hh:" + pattern_key(prev_pattern)
        require_complete = (mode == "scoring")
    else:
        prev_series, tag = ds.coin, "real"
        require_complete = (mode == "scoring")
    design = claims_design(ds, prev_series, require_complete, tag)
    in_hand_prev = [c for c in COIN_MEMBERS if prev_pattern.get(c, 0) == 0]
    n = len(targets)
    out = {k: np.full(n, np.nan) for k in
           ("y", "pers_real", "pers_avail", "pers_hh", "bridge", "claims", "ens", "comp_prev")}
    out["months"] = [ds.months[i] for i in targets]
    out["targets"] = list(targets)
    out["claims_status"] = []
    out["claims_n"] = np.zeros(n, int)
    out["bridge_flags"] = []
    out["prev_flags"] = []
    for k, i in enumerate(targets):
        out["y"][k] = ds.coin[i]
        out["pers_real"][k] = ds.coin[i - 1]
        out["pers_avail"][k] = ds.available_mean(i - 1, in_hand_prev)
        out["pers_hh"][k] = hist_prev[i - 1]
        cm = complete_month(ds, i, pattern, mode)
        out["bridge"][k] = cm["value"]
        out["bridge_flags"].append({"bridged": cm["bridged"], "skipped": cm["skipped"],
                                    "dropped": cm["dropped"], "fallback": cm["fallback"],
                                    "missing": cm["missing"], "key": cm["pattern_key"]})
        cp = complete_month(ds, i - 1, prev_pattern, mode)
        out["comp_prev"][k] = cp["value"]
        out["prev_flags"].append({"bridged": cp["bridged"], "skipped": cp["skipped"],
                                  "dropped": cp["dropped"], "key": cp["pattern_key"]})
        if claims_form == "original":
            prev_fc = ds.coin[i - 1]
        elif claims_form == "hh":
            prev_fc = hist_prev[i - 1]
        else:
            prev_fc = ds.available_mean(i - 1, ("PAYEMS", "INDPRO", "W875RX1"))
        T = claims_rows_end(i, Lmax, mode)
        v, st, nf, _ = claims_value(ds, i, T, design, prev_fc)
        out["claims"][k] = v
        out["claims_status"].append(st)
        out["claims_n"][k] = nf
        out["ens"][k] = 0.5 * out["bridge"][k] + 0.5 * v
    out["pattern"] = pattern
    out["prev_pattern"] = prev_pattern
    out["mode"] = mode
    out["claims_form"] = claims_form
    return out


# ----------------------------------------------------------------------------
# August-form members for ENS_GRID_REPRO (v0 §1 methods 1-3) and the selector
# ----------------------------------------------------------------------------
def _design_tag(*arrays) -> str:
    """content hash of design arrays: cache keys never collide across different inputs."""
    h = hashlib.sha1()
    for a in arrays:
        h.update(np.ascontiguousarray(np.asarray(a, float)).tobytes())
    return h.hexdigest()[:16]


def _walk_forward(ds: Dataset, F: np.ndarray, valid: np.ndarray, targets, mode: str,
                  Lmax: int, forecast_rows: np.ndarray, fallback: np.ndarray, tag: str):
    """Generic expanding OLS COIN(t) ~ 1 + F[t] on rows t <= end(i), refit per
    target, persistence fallback (< MIN_ROWS rows or undefined forecast row).
    Cache key = (tag, content hash of F and valid, T)."""
    tag = f"{tag}:{_design_tag(np.where(np.isfinite(F), F, -9.0), valid)}"
    out = np.full(len(targets), np.nan)
    for k, i in enumerate(targets):
        T = claims_rows_end(i, Lmax, mode)
        key = ("wf", tag, T)
        hit = ds._cache.get(key)
        if hit is None:
            rows = np.flatnonzero(valid[:T + 1]) if T >= 0 else np.array([], int)
            hit = ols(F[rows], ds.coin[rows]) if len(rows) >= MIN_ROWS else None
            ds._cache[key] = hit
        f = forecast_rows[i]
        if hit is None or not np.all(np.isfinite(f)):
            out[k] = fallback[i]
        else:
            out[k] = hit[0] + hit[1:] @ f
    return out


def ar2_series(ds: Dataset, targets, mode: str = "reproduction") -> np.ndarray:
    """AR2 (August): COIN(M) ~ 1 + COIN(M-1) + COIN(M-2), rows t <= M-1 (reproduction)."""
    n = ds.n
    F = np.full((n, 2), np.nan)
    F[1:, 0] = ds.coin[:-1]
    F[2:, 1] = ds.coin[:-2]
    valid = np.isfinite(F).all(1) & np.isfinite(ds.coin)
    if mode == "scoring":
        valid &= ds.complete
    fb = np.full(n, np.nan)
    fb[1:] = ds.coin[:-1]
    return _walk_forward(ds, F, valid, targets, mode, 1, F, fb, "ar2")


def leadreg_series(ds: Dataset, lead_months, lead, targets, mode: str = "reproduction") -> np.ndarray:
    """LEADREG (August): COIN(M) ~ 1 + COIN(M-1) + LEAD(M-1) + dLEAD(M-1),
    dLEAD = 1-month change (R1 reading A20), rows t <= M-1."""
    n = ds.n
    L = np.full(n, np.nan)
    for m, v in zip(lead_months, lead):
        j = ds.idx.get(m)
        if j is not None:
            L[j] = v
    F = np.full((n, 3), np.nan)
    F[1:, 0] = ds.coin[:-1]
    F[1:, 1] = L[:-1]
    F[2:, 2] = L[1:-1] - L[:-2]
    valid = np.isfinite(F).all(1) & np.isfinite(ds.coin)
    if mode == "scoring":
        valid &= ds.complete
    fb = np.full(n, np.nan)
    fb[1:] = ds.coin[:-1]
    return _walk_forward(ds, F, valid, targets, mode, 1, F, fb, "leadreg")


def grid_dictionary(names) -> list:
    """ENS_GRID dictionary (v0 §1 method 6): singletons, all pairs at 25/50/75,
    equal-weight. For 5 members: 5 + 30 + 1 = 36 combos. Each entry
    (label, weight vector)."""
    k = len(names)
    combos = []
    for a in range(k):
        w = np.zeros(k)
        w[a] = 1.0
        combos.append((names[a], w))
    for a in range(k):
        for b in range(a + 1, k):
            for wa in (0.25, 0.5, 0.75):
                w = np.zeros(k)
                w[a], w[b] = wa, 1.0 - wa
                combos.append((f"{wa:g}*{names[a]}+{1 - wa:g}*{names[b]}", w))
    combos.append(("equal", np.full(k, 1.0 / k)))
    return combos


def ens_grid(members: dict, y: np.ndarray, selector_lag: int = 1, warmup: int = 24,
             default: str = "equal") -> dict:
    """ENS_GRID selector: at target k choose the dictionary combo with the lowest
    cumulative past-OOS MSE over targets j <= k - selector_lag (REPRO: 1 =
    errors through M-1; D3: 2 = through M-2), starting after `warmup` targets.
    Before that the `default` combo ('equal' | 'pers' | 'none') is used.
    Ties -> the first combo in dictionary order (deterministic).
    Returns {forecast, chosen (label per target or None), n_selected,
    count_by_label, dictionary}."""
    names = list(members)
    P = np.column_stack([np.asarray(members[k], float) for k in names])
    y = np.asarray(y, float)
    combos = grid_dictionary(names)
    C = np.array([w for _, w in combos])
    F = P @ C.T                                        # n_targets x n_combos
    E2 = (F - y[:, None]) ** 2
    fin = np.isfinite(E2)
    cum = np.nancumsum(np.where(fin, E2, 0.0), axis=0)
    cnt = np.cumsum(fin, axis=0)
    n = len(y)
    out = np.full(n, np.nan)
    chosen = [None] * n
    labels = [c[0] for c in combos]
    if default == "equal":
        dflt = len(combos) - 1
    elif default == "pers":
        dflt = names.index("PERS")
    else:
        dflt = None
    for k in range(n):
        j = k - selector_lag
        if k < warmup or j < 0:
            if dflt is not None:
                out[k] = F[k, dflt]
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            mse = np.where(cnt[j] > 0, cum[j] / np.maximum(cnt[j], 1), np.inf)
        b = int(np.argmin(mse))
        out[k] = F[k, b]
        chosen[k] = labels[b]
    counts: dict[str, int] = {}
    for c in chosen:
        if c is not None:
            counts[c] = counts.get(c, 0) + 1
    return {"forecast": out, "chosen": chosen, "n_selected": sum(c is not None for c in chosen),
            "count_by_label": counts, "dictionary": labels, "selector_lag": selector_lag,
            "warmup": warmup, "default": default}


def ens_grid_repro_members(ds: Dataset, targets, series: dict) -> dict:
    """The five August members in their August forms for ENS_GRID_REPRO
    (v1 §1): PERS, AR2, LEADREG, BRIDGE (pattern A), CLAIMS (original), all in
    reproduction_mode. Gate only (354/630, 0.3319)."""
    simA = simulate(ds, PATTERNS["A"], "reproduction", targets, "original")
    lm, lead, _ = leading_composite(series)
    return {"PERS": simA["pers_real"], "AR2": ar2_series(ds, targets, "reproduction"),
            "LEADREG": leadreg_series(ds, lm, lead, targets, "reproduction"),
            "BRIDGE": simA["bridge"], "CLAIMS": simA["claims"]}


def ens_grid_d3_members(ds: Dataset, targets, series: dict, pattern_name: str) -> dict:
    """Members in their HH/available forms at IS-A or IS-B for ENS_GRID_D3
    (v1 §1 F21/DT-22; reported in the scored run only, selector errors through
    M-2): PERS_HH = COIN_HH(M-1 | prev pattern); AR2_HH on [COIN_HH(M-1),
    COIN(M-2)] (COIN(M-2) is realized at K = M-2); LEADREG_HH on [COIN_HH(M-1),
    LEAD(M-1), dLEAD(M-1)]; BRIDGE_HH; CLAIMS_HH — all scoring_mode rows t <= K.
    NOT computed on F1 in this stage."""
    pat = PATTERNS[pattern_name]
    sim = simulate(ds, pat, "scoring", targets, "hh")
    Lmax = max(pat.values())
    prev = coin_hh_history(ds, PREV_PATTERNS[pattern_name], "scoring")
    n = ds.n
    # AR2_HH
    F2 = np.full((n, 2), np.nan)
    F2[1:, 0] = prev[:-1]
    F2[2:, 1] = ds.coin[:-2]
    v2 = np.isfinite(F2).all(1) & np.isfinite(ds.coin) & ds.complete
    fb = np.full(n, np.nan)
    fb[1:] = prev[:-1]
    ar2 = _walk_forward(ds, F2, v2, targets, "scoring", Lmax, F2, fb, "ar2hh:" + pattern_name)
    # LEADREG_HH
    lm, lead, _ = leading_composite(series)
    L = np.full(n, np.nan)
    for m, v in zip(lm, lead):
        j = ds.idx.get(m)
        if j is not None:
            L[j] = v
    F3 = np.full((n, 3), np.nan)
    F3[1:, 0] = prev[:-1]
    F3[1:, 1] = L[:-1]
    F3[2:, 2] = L[1:-1] - L[:-2]
    v3 = np.isfinite(F3).all(1) & np.isfinite(ds.coin) & ds.complete
    lr = _walk_forward(ds, F3, v3, targets, "scoring", Lmax, F3, fb, "leadreghh:" + pattern_name)
    return {"PERS": sim["pers_hh"], "AR2": ar2, "LEADREG": lr,
            "BRIDGE": sim["bridge"], "CLAIMS": sim["claims"]}


# ----------------------------------------------------------------------------
# bands (v1 §2.2, §2.4): keyed to the bridged pattern of the displayed month
# ----------------------------------------------------------------------------
def band_lookup(bands: dict | None, key: str):
    """bands = {pattern_key: {'p10': .., 'p90': .., 'basis': .., 'n': ..}} from the
    lag simulation (scored run). Returns the entry or None (band pending)."""
    if not bands:
        return None
    return bands.get(key)


def apply_band(value: float, band: dict | None):
    """[completed + p10(e), completed + p90(e)] with e = realized - completed."""
    if band is None or value is None or not np.isfinite(value):
        return None
    return [float(value + band["p10"]), float(value + band["p90"])]


# ----------------------------------------------------------------------------
# the entry point: issue(state, d)
# ----------------------------------------------------------------------------
def legacy_form_would_issue(state: dict, start: str = START) -> tuple[bool, str]:
    """Engine-side emulation of the DEPLOYED fixed-lag gates (business_cycle.
    nowcast lines 519-553): axis PAYEMS & INDPRO >= 1960-01; None when the
    composite has caught up with the last PAYEMS month, when the gap != 1, or
    when any bridge input is not at its trained lag {INDPRO 1, W875RX1 1,
    CMRMTSPL 2}. gates.py calls the real deployed module; this predicate lets
    the offline tests state the expectation without importing the backend."""
    for s_ in ("PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL"):
        if not state.get(s_):
            return False, f"{s_} absent from the state (the deployed compute() refuses a partial board)"
    axis = sorted(set(state["PAYEMS"]) & set(state["INDPRO"]))
    axis = [m for m in axis if m >= "1960-01"]
    tgt = max(state["PAYEMS"])
    last_realized = axis[-1]          # coin[-1] exists as soon as any member has z
    if last_realized >= tgt:
        return False, "catch-up gate: composite axis already contains the target month"
    if mdiff(tgt, last_realized) != 1:
        return False, "one-step gate: gap != 1"
    for s, lag in (("INDPRO", 1), ("W875RX1", 1), ("CMRMTSPL", 2)):
        if mdiff(tgt, max(state[s])) != lag:
            return False, f"fixed-lag gate: {s} at lag {mdiff(tgt, max(state[s]))} != trained {lag}"
    return True, "all deployed gates pass"


def issue(state: dict, d: str | None = None, mode: str = "scoring", bands: dict | None = None,
          stored_completions: dict | None = None, start: str = START) -> dict:
    """Issue the v2 reading from the series as known at date d (any lags).

    state   {series: {YYYY-MM: value}} — the vintage in hand (monthly dicts)
    d       issue date (informational; the vintage, never the calendar, decides)
    bands   optional {pattern_key: {p10, p90, basis}} from the scored lag
            simulation; None -> band pending (nothing is scored in this stage)
    stored_completions  optional {IS: {YYYY-MM: COIN_HH(m)}} per-issue-date store
            (regime (i)); None -> canonical-lag completions recomputed
            walk-forward on the vintage in hand ('spliced history', v1 §4.1)

    Returns {target_month, info_set, lags, K, dropped, members_bridged,
    members_skipped, bridge_hh, claims_hh, ens_hh, phase, completed_prev,
    completed_target, persistence, claims_fit, reason}. reason is None when a
    nowcast exists; otherwise it says why (v1 §2.4: None only when no PAYEMS
    month lies beyond the last complete COIN)."""
    _check_mode(mode)
    ds = build(state, start)
    # every COIN member must be IN the vintage in hand with a z history: a member
    # absent from the state, present but empty, or too short for a single z is
    # not a 'not_existing' month (that status is strictly for months before a
    # member's first z on a state that contains the member) — it is a missing
    # input, and v1 §2.4 says every None carries a reason.
    absent = [c for c in COIN_MEMBERS if ds.last_index(c) is None or ds.first_z[c] is None]
    st = information_state(ds)
    M_i, M, lags, K_i, IS = st["M_i"], st["M"], st["lags"], st["K_i"], st["IS"]
    comp_idx = np.flatnonzero(ds.complete)
    last_complete = int(comp_idx[-1]) if len(comp_idx) else None
    # members whose latest observation lies beyond the last PAYEMS month (e.g. the
    # G.17 out while BLS is delayed): dropped by the PAYEMS axis, lag floored at 0
    # (correct per v1 §2.4: the target is the last PAYEMS month) — flagged, not silent
    members_ahead = [c for c in COIN_MEMBERS if state.get(c) and max(state[c]) > M]
    base = {"issue_date": d, "target_month": M, "info_set": IS, "lags": lags,
            "K": st["K"], "mode": mode,
            "last_complete_coin": ds.months[last_complete] if last_complete is not None else None,
            "legacy_form_issues": legacy_form_would_issue(state, start)[0]}
    if absent:
        return {**base, "lags": {c: (None if c in absent else L) for c, L in lags.items()},
                "K": None, "nowcast": None, "bridge_hh": None, "claims_hh": None, "ens_hh": None,
                "phase": None, "dropped": [], "members_bridged": {}, "members_skipped": [],
                "completed_prev": None, "completed_target": None, "persistence": None,
                "claims_fit": None, "claims_reason": None,
                "flags": {"members_absent": absent, "members_ahead": members_ahead},
                "reason": f"member(s) {absent} absent, empty or without a z history (< {Z_MIN} growth "
                          f"observations) in the vintage in hand — no nowcast (the lag >= 4 drop rule "
                          f"applies to a published member, never to a missing one)"}
    if last_complete is not None and last_complete >= M_i:
        return {**base, "nowcast": None, "bridge_hh": None, "claims_hh": None, "ens_hh": None,
                "phase": None, "dropped": [], "members_bridged": {}, "members_skipped": [],
                "completed_prev": None, "completed_target": None, "persistence": None,
                "claims_fit": None,
                "reason": f"COIN({M}) is complete (all members published); no PAYEMS month "
                          f"lies beyond the last complete COIN — nothing to nowcast"}
    pattern = {c: lags[c] for c in BRIDGED_MEMBERS}
    prev_pattern = {c: max(lags[c] - 1, 0) for c in BRIDGED_MEMBERS}
    cm = complete_month(ds, M_i, pattern, mode)
    cp = complete_month(ds, M_i - 1, prev_pattern, mode) if M_i >= 1 else None
    bridge = cm["value"] if np.isfinite(cm["value"]) else None
    # CLAIMS_HH: the labelled IS's fit; regressor history = stored completions
    canon_prev = PREV_PATTERNS[IS]
    if stored_completions and IS in stored_completions:
        hist_prev = np.full(ds.n, np.nan)
        for m, v in stored_completions[IS].items():
            j = ds.idx.get(m)
            if j is not None:
                hist_prev[j] = v
        hist_tag, hist_basis = f"stored:{IS}", "stored per-issue-date completions"
    else:
        hist_prev = coin_hh_history(ds, canon_prev, mode)
        hist_tag = "hh:" + pattern_key(canon_prev)
        hist_basis = "spliced history: canonical-lag completions recomputed walk-forward on the vintage in hand"
    claims = None
    claims_fit_info = None
    claims_reason = None
    prev_fc = cp["value"] if cp is not None else float("nan")
    if "ICSA" not in state or not np.isfinite(ds.zc[M_i]):
        claims_reason = "ICSA not in the state (or z_claims6 undefined for the target month)"
    elif not np.isfinite(ds.zk[M_i]):
        claims_reason = "curve (T10Y3M / GS10-TB3MS) undefined for the target month"
    elif not np.isfinite(prev_fc):
        claims_reason = "completed COIN(M-1) undefined (partial state)"
    else:
        design = claims_design(ds, hist_prev, True, hist_tag)
        v, status, nfit, beta = claims_value(ds, M_i, K_i, design, prev_fc)
        if status == "fit":
            claims = v
            _, n_, r0, r1 = claims_fit(ds, design, K_i)
            claims_fit_info = {"n": int(n_), "rows": [r0, r1], "coef": [float(b) for b in beta],
                               "rows_through": st["K"], "regressor_history": hist_basis,
                               "info_set_fit": IS}
        else:
            claims_reason = f"CLAIMS_HH fit has {nfit} < {MIN_ROWS} admissible rows"
    ens = 0.5 * bridge + 0.5 * claims if (bridge is not None and claims is not None) else None
    prev_band = band_lookup(bands, cp["pattern_key"]) if cp is not None else None
    tgt_band = band_lookup(bands, cm["pattern_key"])
    pending = "pending: lag-simulation error distribution not available in this stage (nothing scored)"
    completed_prev = None
    if cp is not None:
        completed_prev = {"month": cp["month"], "value": cp["value"] if np.isfinite(cp["value"]) else None,
                          "pattern": cp["bridged"], "dropped": cp["dropped"], "skipped": cp["skipped"],
                          "pattern_key": cp["pattern_key"],
                          "band": apply_band(cp["value"], prev_band),
                          "band_basis": prev_band["basis"] if prev_band else pending,
                          "nonstandard_pattern": (cp["bridged"] != {c: L for c, L in canon_prev.items() if L > 0}
                                                  or bool(cp["dropped"]))}
    completed_target = {"month": cm["month"], "value": bridge, "pattern": cm["bridged"],
                        "dropped": cm["dropped"], "skipped": cm["skipped"],
                        "pattern_key": cm["pattern_key"], "band": apply_band(cm["value"], tgt_band),
                        "band_basis": tgt_band["basis"] if tgt_band else pending}
    in_hand_prev = [c for c in COIN_MEMBERS if prev_pattern.get(c, 0) == 0]
    pers = None
    if M_i >= 1:
        real_prev = ds.coin[M_i - 1] if ds.complete[M_i - 1] else float("nan")
        pers = {"realized": float(real_prev) if np.isfinite(real_prev) else None,
                "available": (lambda v: float(v) if np.isfinite(v) else None)(ds.available_mean(M_i - 1, in_hand_prev)),
                "hh": completed_prev["value"] if completed_prev else None}
    reason = None
    if bridge is None:
        reason = ("BRIDGE_HH undefined: " + ("members missing " + str(cm["missing"]) if cm["missing"]
                                               else "no member available"))
    elif claims is None:
        # the nowcast (ENS_HH) is None whenever either half is: v1 §2.4 'every None
        # carries a reason' — the frontend renders nowcast.reason (DT-10)
        reason = "claims half unavailable: " + str(claims_reason)
    return {**base, "nowcast": ens, "bridge_hh": bridge, "claims_hh": claims, "ens_hh": ens,
            "phase": label3(ens) if ens is not None else None,
            "dropped": cm["dropped"], "members_bridged": cm["bridged"], "members_skipped": cm["skipped"],
            "members_actual": cm["actual"], "bridge_fits": cm["fits"],
            "completed_prev": completed_prev, "completed_target": completed_target,
            "persistence": pers, "claims_fit": claims_fit_info, "claims_reason": claims_reason,
            "flags": {"lag_ge3": [c for c, L in lags.items() if L >= 3],
                      "is_c_cmrmtspl_lag2": IS == "C" and lags["CMRMTSPL"] == 2,
                      # BEA before the Fed: W875RX1(M) in hand while INDPRO lags (label A by
                      # the clause order; W875RX1 enters the IS-A completion at lag 0)
                      "w875_ahead_of_indpro": lags["W875RX1"] < lags["INDPRO"],
                      "members_ahead": members_ahead,
                      "members_absent": []},
            "reason": reason}


# ----------------------------------------------------------------------------
# NBER onsets from USREC
# ----------------------------------------------------------------------------
def onsets_from_usrec(ds: Dataset, since: str = "1972-01") -> list:
    """months where USREC goes 0 -> 1, month >= since."""
    if ds.usrec is None:
        return list(ONSETS)
    r = ds.usrec
    out = []
    for i in range(1, ds.n):
        if r[i] == 1 and r[i - 1] == 0 and ds.months[i] >= since:
            out.append(ds.months[i])
    return out
