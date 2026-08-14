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


def _episodes(idxs: list[int]) -> list[list[int]]:
    """Group neighbor indices into distinct historical episodes (members
    within 12 months chain together). Top-10 neighbors are often 3 months
    of the same event - counting them separately inflated the headline
    recession probability (counter-agent QA, 2026-08-11)."""
    eps: list[list[int]] = []
    for i in sorted(idxs):
        if eps and i - eps[-1][-1] <= 12:
            eps[-1].append(i)
        else:
            eps.append([i])
    return eps


def _recent_calibration(V: dict, years: int = 4) -> dict:
    """Mean analog p(recession-within-12m) per calendar year for the recent
    past, with the observed outcome where the window has closed. The analog
    has over-predicted continuously since 2024 (QA find) - the panel must
    show that streak, not just the long-sample Brier win."""
    months, rec = V["months"], V["rec"]
    y0 = int(months[-1][:4]) - years + 1
    out: dict[str, dict] = {}
    for t in range(len(months)):
        yr = months[t][:4]
        if int(yr) < y0:
            continue
        nbrs = _neighbors(V, t, known_by=t)[:TOP_K]
        if len(nbrs) < TOP_K:
            continue
        ps = [x for x in (_rec_within(rec, i) for _, i in nbrs)
              if x is not None]
        if not ps:
            continue
        o = out.setdefault(yr, {"p_sum": 0.0, "n": 0, "rec_observed": False,
                                "windows_closed": 0})
        o["p_sum"] += sum(ps) / len(ps)
        o["n"] += 1
        y = _rec_within(rec, t)
        if y is not None:
            o["windows_closed"] += 1
            o["rec_observed"] = o["rec_observed"] or y
    return {yr: {"mean_p_pct": round(100 * o["p_sum"] / o["n"], 1),
                 "recession_observed": o["rec_observed"]
                 if o["windows_closed"] else None}
            for yr, o in sorted(out.items())}


EBP_URL = ("https://www.federalreserve.gov/econres/notes/feds-notes/"
           "ebp_csv.csv")


def _ebp_context(raw_override: dict | None = None) -> dict | None:
    """DESCRIPTIVE side panel only. The 2026-08-11 referee REJECTED EBP as
    an analog dimension (no skill, full-history re-estimation risk, and the
    2007 narrative failed at the matched month: EBP at 2007-06 was -0.35,
    MORE benign than today). What survives is the plain fact: where the
    excess bond premium sits now vs its run-up through 2008. Never enters
    the distance metric."""
    try:
        if raw_override is not None:
            if "EBP" not in raw_override:
                return None
            pairs = [(str(d)[:7], float(v)) for d, v in raw_override["EBP"]]
        else:
            r = httpx.get(EBP_URL, timeout=30)
            r.raise_for_status()
            pairs = []
            for ln in r.text.strip().splitlines()[1:]:
                cols = ln.split(",")
                try:
                    mth, _d, yr = cols[0].split("/")
                    pairs.append((f"{yr}-{int(mth):02d}", float(cols[2])))
                except (ValueError, IndexError):
                    continue
        if not pairs:
            return None
        pairs.sort()
        vals = dict(pairs)
        cur_m, cur_v = pairs[-1]
        hist = [v for _, v in pairs]
        pct = round(100 * sum(1 for v in hist if v < cur_v) / len(hist), 1)
        peak0708 = max((v for m, v in pairs if "2007-01" <= m <= "2009-06"),
                       default=None)
        return {"month": cur_m, "value": round(cur_v, 2),
                "percentile": pct,
                "at_2007_06": round(vals["2007-06"], 2)
                if "2007-06" in vals else None,
                "peak_2007_09": round(peak0708, 2)
                if peak0708 is not None else None,
                "note": ("descriptive only - rejected as a model input "
                         "(2026-08-11 referee: no skill, history "
                         "re-estimated); shown because it tempers the 2007 "
                         "analog: credit is not confirming the rhyme")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("analog: EBP context unavailable (%s)", exc)
        return None


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
    # episode-level view of the SAME top-10 (QA caveat a)
    eps = _episodes([i for _, i in top])
    ep_rec, covid = [], False
    for members in eps:
        best = min(members, key=lambda i: _dist(V["matrix"][t],
                                                V["matrix"][i]) or 9e9)
        r = _rec_within(rec, best)
        if r is not None:
            ep_rec.append(r)
            if r and "2019-01" <= months[best] <= "2020-02":
                covid = True
    # top-10 DISTINCT episodes walking down the full ranking
    seen_eps: list[list[int]] = []
    de_rec = []
    for d, i in nbrs:
        if any(abs(i - m) <= 12 for ep in seen_eps for m in ep):
            for ep in seen_eps:
                if any(abs(i - m) <= 12 for m in ep):
                    ep.append(i)
            continue
        seen_eps.append([i])
        r = _rec_within(rec, i)
        if r is not None:
            de_rec.append(r)
        if len(seen_eps) == TOP_K:
            break
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
        "episodes": {"n": len(eps), "recession": sum(ep_rec),
                     "includes_covid": covid,
                     "by_episode_pct": round(100 * sum(ep_rec) / len(ep_rec), 1)
                     if ep_rec else None,
                     "top10_distinct_episode_pct":
                     round(100 * sum(de_rec) / len(de_rec), 1)
                     if de_rec else None},
        "recent_calibration": _recent_calibration(V),
        "ebp_context": _ebp_context(raw_override),
        "current_missing_dims": [DIM_NAMES[d] for d in range(len(DIM_NAMES))
                                 if V["matrix"][t][d] is None],
        "climatology_recession_within_12m_pct":
            round(100 * sum(clim) / len(clim), 1) if clim else None,
        "climatology_fwd12_median_pct":
            fwd12[len(fwd12) // 2] if fwd12 else None,
        "skill": skill_test(V),
        "basis": ("13-dim expanding-z vector; RMS distance over shared dims; "
                  "match strength = distance percentile vs ALL candidate "
                  "months (no invented 0-100 score). SPX = Shiller monthly "
                  "price average (no dividends) + FMP live month. NBER labels "
                  "hindsight-final in the skill scoring (real-time dating "
                  "lags ~1y). Each month is z-scored on its own expanding "
                  "stats (as seen at the time); QA 2026-08-11: under a "
                  "single common-yardstick normalization the 1990 analogs "
                  "drop out of the top-10 while 2007-07 remains #1 - treat "
                  "the #1 as robust and the supporting cast as "
                  "convention-sensitive. Skill edge is concentrated in "
                  "2008/1979/2001 and borderline under year-block resampling "
                  "(90% CI touches zero). DESCRIPTIVE - a regime read, not "
                  "a calibrated probability."),
    }
