"""Historical analog layer for the business-cycle tracker.

"Which past months looked most like today, and what happened next?" —
the useful idea inside the Zeberg 'Historical Analog' screenshot, built
transparently. Nearest-neighbor over a 13-dimension monthly state vector,
every dimension an EXPANDING-window z-score (no full-sample lookahead):

  coincident members (4): 6m annualized growth of PAYEMS, INDPRO,
    W875RX1, CMRMTSPL
  leading members (6): yield curve, permits 6m growth, -claims 6m growth,
    factory hours, sentiment change, -Baa spread
  regime extras (3): SPX 12m momentum, CPI yoy, fed funds 12m change
    (the 1970s and the 2000s look alike on growth alone; inflation and
    policy stance separate them)

Distance: RMS over dimensions both months have (>= MIN_DIMS required).
Match strength is reported as a PERCENTILE of all candidate distances -
never an invented "93/100" score.

Skill test (pre-registered, recomputed live, shown in the honesty box):
walk-forward from 1975 - at each month t, find top-K analogs among months
whose 12m outcome was already known at t (i <= t-36 and i+12 <= t), take
the analog frequency of recession-within-12m as the forecast, and Brier-
score it against the base rate known at t. Same design for forward-12m
SPX return (analog median vs climatology median, MAE). If analogs carry
no skill the panel says so - the layer is DESCRIPTIVE either way.

Honesty:
- NBER labels are used as if known with hindsight when SCORING both
  methods (real-time NBER dating lags ~a year); the comparison is fair
  but live probabilities are approximations.
- SPX is Shiller/datahub monthly PRICE level (no dividends), topped up
  with the FMP live month; forward returns are price returns.
- Validation on revised macro data - live vintages are noisier.
"""
from __future__ import annotations

import logging
import math

import httpx

from ..config import settings
from . import business_cycle as bc
from .fred import fetch_series

logger = logging.getLogger(__name__)

EXTRA_SERIES = ["CPIAUCSL", "FEDFUNDS"]
SPX_URL = ("https://raw.githubusercontent.com/datasets/s-and-p-500/"
           "main/data/data.csv")
FMP_URL = ("https://financialmodelingprep.com/stable/historical-price-eod/"
           "light?symbol=%5EGSPC&apikey={key}")

MIN_DIMS = 10          # of 13; months missing more are not comparable
EXCLUDE_M = 36         # no analog within 3y of the target (autocorrelation)
TOP_K = 10             # neighbors used for probabilities
SHOW_K = 5             # neighbors surfaced on the panel
SKILL_START = "1975-01"
DIM_NAMES = ["payrolls", "indprod", "real_income", "mfg_sales",
             "curve", "permits", "claims", "hours", "sentiment", "baa",
             "spx_mom12", "cpi_yoy", "ffr_chg12"]


def _fetch_spx(raw_override: dict | None = None) -> dict[str, float]:
    """{YYYY-MM: close}. Shiller/datahub monthly back to 1871, FMP tops up
    the current month. Tests inject via raw_override['SPX']."""
    if raw_override is not None and "SPX" in raw_override:
        return {str(d)[:7]: float(v) for d, v in raw_override["SPX"]}
    out: dict[str, float] = {}
    r = httpx.get(SPX_URL, timeout=30, follow_redirects=True)
    r.raise_for_status()
    for line in r.text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 2 and parts[1]:
            try:
                v = float(parts[1])
            except ValueError:
                continue
            if v > 0:
                out[parts[0][:7]] = v
    if not out:
        raise RuntimeError("analog: SPX history empty")
    if settings.fmp_api_key:
        try:
            rows = httpx.get(FMP_URL.format(key=settings.fmp_api_key),
                             timeout=30).json()
            latest: dict[str, float] = {}
            for row in rows if isinstance(rows, list) else []:
                m = str(row.get("date", ""))[:7]
                if m and row.get("price"):
                    latest.setdefault(m, float(row["price"]))  # first = newest
            for m, v in latest.items():
                if m > max(out):
                    out[m] = v
        except Exception as exc:  # noqa: BLE001
            logger.warning("analog: FMP top-up failed (%s) - Shiller only", exc)
    return out


def build_vectors(raw_override: dict | None = None) -> dict:
    """Monthly 13-dim state matrix + outcome arrays, shared by the live
    board and the walk-forward skill test."""
    M = bc._fetch_all(raw_override)
    for s in EXTRA_SERIES:
        if raw_override is not None:
            pairs = raw_override.get(s, [])
            M[s] = bc._monthly([p[0] for p in pairs],
                               [float(p[1]) for p in pairs], "last")
        else:
            dates, vals = fetch_series(s, start=bc.START)
            M[s] = bc._monthly(dates, vals, "last")
        if not M[s]:
            raise RuntimeError(f"analog: no data for {s}")
    spx = _fetch_spx(raw_override)

    months = sorted(set(M["PAYEMS"]) & set(M["INDPRO"]))
    months = [m for m in months if m >= "1960-01"]

    def arr(name, src=None):
        src = src if src is not None else M[name]
        return [src.get(m) for m in months]

    curve = [(a if a is not None else
              ((g - t) if g is not None and t is not None else None))
             for a, g, t in zip(arr("T10Y3M"), arr("GS10"), arr("TB3MS"))]
    sent = arr("UMCSENT")
    dsent = [None] + [(b - a) if a is not None and b is not None else None
                      for a, b in zip(sent, sent[1:])]
    spx_a = arr("SPX", spx)

    def mom12(xs):
        return [None] * 12 + [
            (math.log(xs[i] / xs[i - 12]) * 100)
            if xs[i] and xs[i - 12] else None
            for i in range(12, len(xs))]

    def d12(xs):
        return [None] * 12 + [
            (xs[i] - xs[i - 12])
            if xs[i] is not None and xs[i - 12] is not None else None
            for i in range(12, len(xs))]

    dims = [
        bc._zs(bc._g6(arr("PAYEMS"))),
        bc._zs(bc._g6(arr("INDPRO"))),
        bc._zs(bc._g6(arr("W875RX1"))),
        bc._zs(bc._g6(arr("CMRMTSPL"))),
        bc._zs(curve),
        bc._zs(bc._g6(arr("PERMIT"))),
        bc._zs([-x if x is not None else None
                for x in bc._g6(arr("ICSA"))]),
        bc._zs(arr("AWHMAN")),
        bc._zs(dsent),
        bc._zs([-x if x is not None else None for x in arr("BAA10YM")]),
        bc._zs(mom12(spx_a)),
        bc._zs(mom12(arr("CPIAUCSL"))),
        bc._zs(d12(arr("FEDFUNDS"))),
    ]
    matrix = [[dims[d][i] for d in range(len(dims))]
              for i in range(len(months))]
    coin = bc._mean_rows(dims[:4])
    lead3 = bc._mean_rows(dims[4:10])
    phases = [bc.phase_of(c, l) for c, l in zip(coin, lead3)]
    return {"months": months, "matrix": matrix, "rec": arr("USREC"),
            "spx": spx_a, "coin": coin, "phase": phases}


def _dist(a: list, b: list) -> float | None:
    acc, n = 0.0, 0
    for x, y in zip(a, b):
        if x is not None and y is not None:
            acc += (x - y) ** 2
            n += 1
    return math.sqrt(acc / n) if n >= MIN_DIMS else None


def _fwd_ret(spx: list, i: int, h: int) -> float | None:
    if i + h < len(spx) and spx[i] and spx[i + h]:
        return round((spx[i + h] / spx[i] - 1) * 100, 2)
    return None


def _rec_within(rec: list, i: int, h: int = 12) -> bool | None:
    w = rec[i + 1:i + 1 + h]
    if len(w) < h or any(r is None for r in w):
        return None
    return any(r == 1 for r in w)


def _neighbors(V: dict, t: int, known_by: int | None = None) -> list[tuple]:
    """(distance, i) sorted ascending, i at least EXCLUDE_M from t. When
    known_by is set (skill test), an analog's 12m outcome must have been
    OBSERVABLE at that month: i + 12 <= known_by."""
    out = []
    for i in range(len(V["months"])):
        if abs(i - t) < EXCLUDE_M:
            continue
        if known_by is not None and i + 12 > known_by:
            continue
        d = _dist(V["matrix"][t], V["matrix"][i])
        if d is not None:
            out.append((d, i))
    out.sort()
    return out


def skill_test(V: dict) -> dict:
    """Walk-forward Brier (recession-within-12m) and MAE (fwd-12m SPX
    return): analog forecast vs the baseline known at each month."""
    months, rec, spx = V["months"], V["rec"], V["spx"]
    b_an = b_bs = 0.0
    m_an = m_bs = 0.0
    n_b = n_m = 0
    for t in range(len(months) - 12):
        if months[t] < SKILL_START:
            continue
        y = _rec_within(rec, t)
        actual = _fwd_ret(spx, t, 12)
        nbrs = _neighbors(V, t, known_by=t)[:TOP_K]
        if len(nbrs) < TOP_K:
            continue
        an_rec = [_rec_within(rec, i) for _, i in nbrs]
        an_ret = [_fwd_ret(spx, i, 12) for _, i in nbrs]
        an_rec = [x for x in an_rec if x is not None]
        an_ret = sorted(x for x in an_ret if x is not None)
        hist = [_rec_within(rec, j) for j in range(t - 12)]
        hist = [x for x in hist if x is not None]
        rets = sorted(x for x in (_fwd_ret(spx, j, 12)
                                  for j in range(t - 12)) if x is not None)
        if y is not None and an_rec and hist:
            p_an = sum(an_rec) / len(an_rec)
            p_bs = sum(hist) / len(hist)
            b_an += (p_an - y) ** 2
            b_bs += (p_bs - y) ** 2
            n_b += 1
        if actual is not None and an_ret and rets:
            med = lambda xs: xs[len(xs) // 2]
            m_an += abs(med(an_ret) - actual)
            m_bs += abs(med(rets) - actual)
            n_m += 1
    return {
        "n_months": n_b,
        "brier_analog": round(b_an / n_b, 4) if n_b else None,
        "brier_base_rate": round(b_bs / n_b, 4) if n_b else None,
        "ret_mae_analog_pp": round(m_an / n_m, 2) if n_m else None,
        "ret_mae_climatology_pp": round(m_bs / n_m, 2) if n_m else None,
        "design": (f"walk-forward from {SKILL_START}; top-{TOP_K} analogs, "
                   f"outcomes observable at forecast time (i+12<=t), "
                   f">= {EXCLUDE_M}m exclusion window"),
    }


def board(raw_override: dict | None = None) -> dict:
    V = build_vectors(raw_override)
    months, spx, rec = V["months"], V["spx"], V["rec"]
    t = len(months) - 1
    while t > 0 and _dist(V["matrix"][t], V["matrix"][t]) is None:
        t -= 1                      # walk back to the last complete month
    nbrs = _neighbors(V, t)
    all_d = [d for d, _ in nbrs]
    top = nbrs[:TOP_K]

    def pctile(d):
        if not all_d:
            return None
        return round(100 * sum(1 for x in all_d if x > d) / len(all_d), 1)

    analogs = []
    for d, i in top[:SHOW_K]:
        analogs.append({
            "month": months[i], "distance": round(d, 3),
            "closer_than_pct": pctile(d),
            "phase_then": V["phase"][i],
            "fwd_spx_6m_pct": _fwd_ret(spx, i, 6),
            "fwd_spx_12m_pct": _fwd_ret(spx, i, 12),
            "fwd_spx_18m_pct": _fwd_ret(spx, i, 18),
            "recession_within_12m": _rec_within(rec, i),
            "spx_path_fwd18": [
                round((spx[i + h] / spx[i] - 1) * 100, 2)
                if i + h < len(spx) and spx[i] and spx[i + h] else None
                for h in range(0, 19)],
        })
    rec_probs = [x for x in (_rec_within(rec, i) for _, i in top)
                 if x is not None]
    clim = [x for x in (_rec_within(rec, j) for j in range(len(months) - 12))
            if x is not None]
    fwd12 = sorted(x for x in (_fwd_ret(spx, j, 12)
                               for j in range(len(months) - 12))
                   if x is not None)
    return {
        "asof": months[t],
        "current_phase": V["phase"][t],
        "dims": DIM_NAMES,
        "current_vector": [round(x, 2) if x is not None else None
                           for x in V["matrix"][t]],
        "analogs": analogs,
        "analog_recession_within_12m_pct":
            round(100 * sum(rec_probs) / len(rec_probs), 1)
            if rec_probs else None,
        "climatology_recession_within_12m_pct":
            round(100 * sum(clim) / len(clim), 1) if clim else None,
        "climatology_fwd12_median_pct":
            fwd12[len(fwd12) // 2] if fwd12 else None,
        "skill": skill_test(V),
        "basis": ("13-dim expanding-z vector; RMS distance over shared dims; "
                  "match strength = distance percentile vs ALL candidate "
                  "months (no invented 0-100 score). SPX = Shiller monthly "
                  "price level (no dividends) + FMP live month. NBER labels "
                  "hindsight-final in the skill scoring (real-time dating "
                  "lags ~1y). DESCRIPTIVE unless the skill box shows the "
                  "analog beating the baseline."),
    }
