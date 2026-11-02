"""Dollar watch tab (studies/dollar-watch.md §5): assembles GET /dollar-watch.

DESCRIPTIVE ONLY. Nothing here is a probability, a warning colour or a lamp:
every historical number is in-sample, carries its N and base rate, and comes
from the frozen reference (sources/dollar_reference.json, rebuilt by
studies/dollar_watch/code/build_reference.py). The pre-registration that could
license more is drafted and NOT frozen.

Four layers:
  state     dollar STATE: ICE DXY vs Johnson's 85-105 band, the Fed broad index
            and its AFE/EME split, 6m/12m change, the dollar-yield quadrant
            label, the 12-month momentum reading, safe havens, EM FX, Brent.
  funding   DOLLAR-FUNDING NOWCAST: CP-bill, OFR funding/EM/safe assets, NFCI
            risk, SOFR tails, swap lines, EMB, each against its own history.
  scramble  DOLLAR-SCRAMBLE PEAK gauge: the frozen deceleration rule run live,
            the gate, three indicators shown separately and never summed, two
            confirmations, the permanent historical record and its null.
  slow      SLOW STATE: BIS dollar credit outside the US, the FX-swap stock,
            policy rates vs the Fed, the 2y vs the funds rate, the Treasury
            channel, and the dated forward ledger.

Two layers so the assembly is testable offline: sources/dollar_data.fetch_all()
fetches, build_dollar_watch(inputs, today=...) is pure apart from the ledger
file it appends to (path injectable for tests).
"""
from __future__ import annotations

import bisect
import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone

from ..config import settings

logger = logging.getLogger(__name__)

REF_PATH = os.path.join(os.path.dirname(__file__), "..", "sources", "dollar_reference.json")
with open(REF_PATH, encoding="utf-8") as _fh:
    REF = json.load(_fh)
FROZEN_ON = REF["frozen_on"]
RULE = REF["scramble_rule"]["params"]
LEDGER_NAME = "dollar_ledger.json"
EMFX_IDS = ["DEXBZUS", "DEXMXUS", "DEXSFUS", "DEXINUS", "DEXKOUS", "DEXTHUS", "DEXCHUS", "DEXMAUS"]
QUAD_LABEL = {"usd_up_yld_down": "dollar up, 10-year yield down", "usd_up_yld_up": "dollar up, 10-year yield up",
              "usd_down_yld_up": "dollar down, 10-year yield up", "usd_down_yld_down": "dollar down, 10-year yield down"}
SCRAMBLE_WORDS = "dollar scramble peaking"      # the gauge's only wording for a met (a); never anything about the crisis

HONESTY = REF["honesty"] + [
    "Descriptive panel: readings and counts only, each count with its N and base rate; nothing here is a forecast or a crisis call.",
    "Live readings use today's data vintage; the broad dollar (H.10) is published weekly, so it can lag the DXY by a week.",
    "The pre-registration (a cross-section of currencies, the 1973-2005 DXY, a forward ledger) is drafted, not frozen: "
    "it waits on Casey's choice of the primary crisis list.",
]


# ---------------------------------------------------------------------------- small helpers
def worst(statuses) -> str:
    seen = set(statuses)
    if not seen or "error" in seen or None in seen:
        return "error"
    return "stale" if "stale" in seen else "ok"


def r(x, k=2):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, k)


def pairs(s: dict | None) -> list[tuple[str, float]]:
    """{dates, values} -> [(iso, value)] without gaps, sorted."""
    if not s:
        return []
    return sorted((d, v) for d, v in zip(s.get("dates") or [], s.get("values") or []) if v is not None)


def asof(ps: list[tuple[str, float]], d: str):
    """last value on or before d (None if none)."""
    i = bisect.bisect_right(ps, (d, float("inf"))) - 1
    return ps[i][1] if i >= 0 else None


def add_months(d: str, k: int) -> str:
    y, m = int(d[:4]), int(d[5:7]) + k
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}{d[7:]}"


def chg_pct(ps, months: int):
    if not ps:
        return None
    d, v = ps[-1]
    v0 = asof(ps, add_months(d, -months))
    return r(100 * (v / v0 - 1), 1) if v0 else None


def chg_abs(ps, months: int, k=2):
    if not ps:
        return None
    d, v = ps[-1]
    v0 = asof(ps, add_months(d, -months))
    return r(v - v0, k) if v0 is not None else None


def pct_rank(ps, since: str | None = None):
    """(share of the history at or below the latest value, n, first date) — the own-history percentile."""
    xs = [v for d, v in ps if since is None or d >= since]
    if len(xs) < 20:
        return None, len(xs), None
    last = ps[-1][1]
    srt = sorted(xs)
    return r(100 * bisect.bisect_right(srt, last) / len(srt), 0), len(xs), (ps[0][0] if since is None else since)


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def spread(a: list, b: list, scale: float = 1.0) -> list[tuple[str, float]]:
    """a - b on a's dates with b as-of (same-day or the latest prior print)."""
    out = []
    for d, v in a:
        w = asof(b, d)
        if w is not None:
            out.append((d, (v - w) * scale))
    return out


def weekly(ps, since: str | None = None, k=3) -> dict:
    """last observation of each ISO week -> {dates, values} (keeps chart payloads small)."""
    out: dict[tuple, tuple] = {}
    for d, v in ps:
        if since and d < since:
            continue
        y, w, _ = date.fromisoformat(d).isocalendar()
        out[(y, w)] = (d, v)
    rows = [out[key] for key in sorted(out)]
    return {"dates": [d for d, _ in rows], "values": [r(v, k) for _, v in rows]}


def monthly_avg(ps) -> dict[str, float]:
    acc: dict[str, list] = {}
    for d, v in ps:
        acc.setdefault(d[:7], []).append(v)
    return {m: sum(v) / len(v) for m, v in acc.items()}


def reading(ps, unit: str, src=None, basis=None, status="error", dp=2, pct_since: str | None = None) -> dict:
    if not ps:
        return {"latest": None, "asof": None, "unit": unit, "src": src, "basis": basis, "status": "error"}
    p_all, n_all, first = pct_rank(ps)
    p10, n10, _ = pct_rank(ps, since=pct_since) if pct_since else (None, None, None)
    return {"latest": r(ps[-1][1], dp), "asof": ps[-1][0], "unit": unit, "src": src, "basis": basis, "status": status,
            "pct_own_history": p_all, "n": n_all, "history_from": first, "pct_10y": p10, "n_10y": n10}


# ---------------------------------------------------------------------------- the frozen rule (identical to the builder)
def scramble_firings(dates, B, Y, rearm=True, p=RULE):
    """The frozen deceleration rule, line for line as build_reference.py / decel_realtime.py
    (the live version also evaluates the latest index day). Returns firing dicts with index k."""
    n = len(B)
    roc = [None] * n
    for k in range(p["roc_days"], n):
        roc[k] = B[k] / B[k - p["roc_days"]] - 1
    fires, last, last_mx = [], -10 ** 9, 0.0
    for k in range(p["first_eval_index"], n):
        w = [(roc[j], j) for j in range(k - p["window_days"], k + 1) if roc[j] is not None]
        mx = max(v for v, _ in w)
        kmx = min(j for v, j in w if v == mx)
        if (mx >= p["min_max_roc"] and roc[k] <= p["decel_ratio"] * mx
                and B[k] >= p["near_high"] * max(B[k - p["window_days"]:k + 1])
                and Y[k] < Y[max(0, kmx - p["yield_lookback_days"])]
                and (k - last > p["cooling_days"] or (rearm and mx >= p["rearm_multiple"] * last_mx))):
            fires.append({"date": dates[k], "k": k, "roc20_max_pct": r(100 * mx, 1), "roc20_max_date": dates[kmx],
                          "roc20_now_pct": r(100 * roc[k], 1), "dollar": r(B[k], 2)})
            last, last_mx = k, mx
    return fires


def rule_index(fred: dict):
    """(dates, B, Y) on days with DTWEXBGS, DGS10 and VIXCLS all published (the frozen index)."""
    b, y, v = (dict(pairs(fred.get(s))) for s in ("DTWEXBGS", "DGS10", "VIXCLS"))
    ds = sorted(d for d in b if d in y and d in v)
    return ds, [b[d] for d in ds], [y[d] for d in ds]


def rule_state(ds, B, Y, p=RULE) -> dict | None:
    """Every clause of the rule at the latest index day, as numbers (nothing summed)."""
    n = len(B)
    if n < p["first_eval_index"] + 1:
        return None
    k = n - 1
    rd = p["roc_days"]
    roc = [B[j] / B[j - rd] - 1 if j >= rd else None for j in range(n)]
    w = [(roc[j], j) for j in range(k - p["window_days"], k + 1) if roc[j] is not None]
    mx = max(v for v, _ in w)
    kmx = min(j for v, j in w if v == mx)
    hi = max(B[k - p["window_days"]:k + 1])
    y_ref = Y[max(0, kmx - p["yield_lookback_days"])]
    start = max(0, kmx - rd)                       # where the largest climb began
    return {"asof": ds[k], "k": k, "dollar": r(B[k], 2), "roc20_now_pct": r(100 * roc[k], 2),
            "roc20_max_60d_pct": r(100 * mx, 2), "roc20_max_date": ds[kmx], "ratio_now_to_max": r(roc[k] / mx, 2) if mx > 0 else None,
            "dollar_vs_60d_high_pct": r(100 * (B[k] / hi - 1), 2), "y10_now": Y[k], "y10_ref": y_ref,
            "y10_ref_date": ds[max(0, kmx - p["yield_lookback_days"])],
            "gate_open": bool(mx >= p["min_max_roc"] and Y[k] < y_ref),
            "climb_ge_4pct": bool(mx >= p["min_max_roc"]), "y10_falling": bool(Y[k] < y_ref),
            "decel_met": bool(roc[k] <= p["decel_ratio"] * mx), "near_high_met": bool(B[k] >= p["near_high"] * hi),
            "episode_start": ds[start], "episode_dollar_peak": r(max(B[start:k + 1]), 2),
            "episode_dollar_peak_date": ds[start + B[start:k + 1].index(max(B[start:k + 1]))]}


# ---------------------------------------------------------------------------- ledger (append-only, forward only)
def ledger_path() -> str:
    return os.path.join(settings.cache_dir, LEDGER_NAME)


def load_ledger(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        if isinstance(d, dict) and isinstance(d.get("entries"), list):
            return d
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("dollar ledger unreadable (%s); a new file is NOT written over it", exc)
        return {"entries": [], "_unreadable": True}
    return {"entries": []}


def append_ledger(path: str, new: list[dict], today: str) -> dict:
    """Add entries not already present (key: kind + date); never edit or drop one.
    An unreadable file is left untouched (the payload says so)."""
    led = load_ledger(path)
    if led.get("_unreadable"):
        return led
    have = {(e.get("kind"), e.get("date")) for e in led["entries"]}
    added = [dict(e, recorded_on=today) for e in new if (e["kind"], e["date"]) not in have]
    if added:
        led = {"_about": "Dollar watch forward ledger: append-only, one row per live firing after the freeze "
                         f"({FROZEN_ON}); recorded_on is the day the panel first saw it.",
               "frozen_on": FROZEN_ON, "entries": led["entries"] + added}
        try:
            from ..sources.fred_csv import _write_atomic
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            _write_atomic(path, json.dumps(led, indent=1, sort_keys=True))
        except Exception as exc:  # noqa: BLE001
            logger.warning("dollar ledger write failed: %s", exc)
            led["_write_failed"] = str(exc)[:200]
    return led


# ---------------------------------------------------------------------------- outcome helpers (as the builder)
def emfx_basket(fred: dict) -> list[tuple[str, float]]:
    """Equal-weight log-average of the 8 FRED EM pairs (EM currency per dollar; up = EM weaker), Jan-2006 = 100."""
    legs = {s: pairs(fred.get(s)) for s in EMFX_IDS}
    if any(not legs[s] for s in EMFX_IDS):
        return []
    days = sorted({d for s in EMFX_IDS for d, _ in legs[s] if d >= "2006-01-01"})
    raw = []
    for d in days:
        vals = [asof(legs[s], d) for s in EMFX_IDS]
        if all(v is not None and v > 0 for v in vals):
            raw.append((d, math.exp(sum(math.log(v) for v in vals) / len(vals))))
    if not raw:
        return []
    b0 = raw[0][1]
    return [(d, 100 * v / b0) for d, v in raw]


def forward_outcomes(d: str, spx, emfx, baa, broad, last_day: str) -> dict:
    o = {}
    s0, e0, b0, d0 = asof(spx, d), asof(emfx, d), asof(baa, d), asof(broad, d)
    for k in (3, 6, 12):
        dk = add_months(d, k)
        if dk > last_day:
            o[f"{k}m"] = None               # not yet matured
            continue
        s1, e1, b1, d1 = asof(spx, dk), asof(emfx, dk), asof(baa, dk), asof(broad, dk)
        o[f"{k}m"] = {"spx_pct": r(100 * (s1 / s0 - 1), 1) if s0 and s1 else None,
                      "emfx_pct": r(100 * (e1 / e0 - 1), 1) if e0 and e1 else None,
                      "baa10y_pp": r(b1 - b0, 2) if b0 is not None and b1 is not None else None,
                      "broad_dollar_pct": r(100 * (d1 / d0 - 1), 1) if d0 and d1 else None}
    return o


# ---------------------------------------------------------------------------- layer 1: state
def dxy_monthly(dxy_ps) -> dict:
    """frozen monthly DXY (1971-01..2026-10) + live complete months after it, and a splice check."""
    ref = REF["dxy_monthly"]
    months, avg, close = list(ref["months"]), list(ref["avg"]), list(ref["close"])
    live_avg = monthly_avg(dxy_ps)
    live_close = {}
    for d, v in dxy_ps:
        live_close[d[:7]] = v
    cur = dxy_ps[-1][0][:7] if dxy_ps else None
    first = dxy_ps[0][0][:7] if dxy_ps else None          # the first live month is partial (the 2-year window starts mid-month)
    complete = sorted(m for m in live_avg if cur and first < m < cur)
    have = set(months)
    overlap = [m for m in complete if m in have]
    ref_avg = dict(zip(months, avg))
    diffs = [abs(live_avg[m] / ref_avg[m] - 1) for m in overlap if ref_avg.get(m)]
    for m in complete:
        if m > months[-1]:
            months.append(m)
            avg.append(r(live_avg[m], 2))
            close.append(r(live_close[m], 2))
    return {"months": months, "avg": avg, "close": close, "frozen_through": ref["months"][-1],
            "month_to_date": {"month": cur, "avg": r(live_avg.get(cur), 2), "days": sum(1 for d, _ in dxy_ps if d[:7] == cur)} if cur else None,
            "splice_check": {"overlap_months": len(overlap), "max_abs_diff_pct": r(100 * max(diffs), 2) if diffs else None},
            "basis": ref["basis"]}


def momentum_now(mon: dict) -> dict:
    ms, avg = mon["months"], mon["avg"]
    i = len(ms) - 1
    v = avg[i] / avg[i - 12] - 1 if i >= 12 and avg[i] and avg[i - 12] else None
    sig_months = [ms[j] for j in range(12, len(ms)) if avg[j] and avg[j - 12] and avg[j] / avg[j - 12] - 1 > 0.10]
    return {"month": ms[i], "dxy_12m_pct": r(100 * v, 1) if v is not None else None,
            "signal": bool(v is not None and v > 0.10), "threshold_pct": 10.0,
            "last_signal_month": sig_months[-1] if sig_months else None, "signal_months": sig_months,
            "definition": REF["momentum"]["definition"], "by_list": REF["momentum"]["by_list"],
            "episodes_history": REF["momentum"]["episodes"], "caveat": REF["momentum"]["caveat"]}


def quadrant_now(mon: dict, dgs10_ps) -> dict:
    gm = {m: round(v, 2) for m, v in monthly_avg(dgs10_ps).items()}   # = GS10 (monthly average of business days)
    n_obs: dict[str, int] = {}
    for d, _ in dgs10_ps:
        n_obs[d[:7]] = n_obs.get(d[:7], 0) + 1
    ms, avg = mon["months"], mon["avg"]                                  # complete months on the DXY calendar
    cand = [i for i in range(3, len(ms)) if ms[i] in gm and ms[i - 3] in gm and n_obs.get(ms[i], 0) >= 15]
    out = {"definition": REF["quadrant"]["definition"] + "; live 10-year = monthly average of DGS10 (the GS10 definition)",
           "onsets_C16": REF["quadrant"]["by_list"]["C16"], "onsets_A25": {k: REF["quadrant"]["by_list"]["A25"][k] for k in ("counts", "n")},
           "base_all_months": REF["quadrant"]["base_all_months"], "labels": QUAD_LABEL}
    if not cand:
        return {**out, "month": None, "quadrant": None, "label": None}
    i = cand[-1]
    dd = avg[i] / avg[i - 3] - 1
    dy = gm[ms[i]] - gm[ms[i - 3]]
    q = ("usd_up" if dd > 0 else "usd_down") + "_" + ("yld_up" if dy > 0 else "yld_down")
    return {**out, "month": ms[i], "dxy_3m_pct": r(100 * dd, 1), "y10_3m_pp": r(dy, 2), "quadrant": q, "label": QUAD_LABEL[q]}


def state_block(inp: dict) -> dict:
    fred = inp.get("fred") or {}
    dx = inp.get("dxy") or {}
    dxy_ps = pairs(dx)
    st = {}
    mon = dxy_monthly(dxy_ps)
    band = REF["band"]
    last = dxy_ps[-1][1] if dxy_ps else None
    pos = None
    if last is not None:
        pos = ("above the band" if last > band["hi"] else "below the band" if last < band["lo"] else
               f"inside the band, {r(band['hi'] - last, 1)} points below the top")
    closes = [c for c in mon["close"] if c is not None]
    st["dxy"] = {**reading(dxy_ps, "index", dx.get("src"), dx.get("basis"), dx.get("status") or "error", 2),
                 "provider": dx.get("provider"), "chg_6m_pct": chg_pct(dxy_ps, 6), "chg_12m_pct": chg_pct(dxy_ps, 12),
                 "monthly": mon, "band_position": pos}
    # the daily feed holds two years only: rank today's close against every month-end close since 1971 instead
    st["dxy"].update(pct_own_history=r(100 * sum(1 for c in closes if c <= last) / len(closes), 0) if last is not None and closes else None,
                     n=len(closes), history_from=mon["months"][0], pct_basis="share of month-end closes since 1971 at or below today's close")
    st["band"] = band
    broad = {}
    for sid, key in (("DTWEXBGS", "broad"), ("DTWEXAFEGS", "afe"), ("DTWEXEMEGS", "eme")):
        ps = pairs(fred.get(sid))
        broad[key] = {**reading(ps, "index (Jan-2006 = 100)", (fred.get(sid) or {}).get("src"), (fred.get(sid) or {}).get("basis"),
                                (fred.get(sid) or {}).get("status") or "error", 2, pct_since=add_months(ps[-1][0], -120) if ps else None),
                      "chg_6m_pct": chg_pct(ps, 6), "chg_12m_pct": chg_pct(ps, 12)}
    bps = pairs(fred.get("DTWEXBGS"))
    broad["high_since_2006"] = {"value": r(max(v for _, v in bps), 2), "date": max(bps, key=lambda x: x[1])[0]} if bps else None
    st["broad"] = broad
    st["momentum"] = momentum_now(mon)
    st["quadrant"] = quadrant_now(mon, pairs(fred.get("DGS10")))
    g = inp.get("gold") or {}
    gps = pairs(g)
    hi52 = max((v for d, v in gps if d >= add_months(gps[-1][0], -12)), default=None) if gps else None
    st["safe_haven"] = {
        "gold": {**reading(gps, "$/oz", g.get("src"), g.get("basis"), g.get("status") or "error", 1), "provider": g.get("provider"),
                 "chg_6m_pct": chg_pct(gps, 6), "chg_12m_pct": chg_pct(gps, 12),
                 "off_52w_high_pct": r(100 * (gps[-1][1] / hi52 - 1), 1) if gps and hi52 else None},
        "chf": {**reading(pairs(fred.get("DEXSZUS")), "CHF per $", (fred.get("DEXSZUS") or {}).get("src"), "Swiss francs per dollar (down = franc stronger)",
                          (fred.get("DEXSZUS") or {}).get("status") or "error", 4), "chg_6m_pct": chg_pct(pairs(fred.get("DEXSZUS")), 6)},
        "jpy": {**reading(pairs(fred.get("DEXJPUS")), "JPY per $", (fred.get("DEXJPUS") or {}).get("src"), "yen per dollar (down = yen stronger)",
                          (fred.get("DEXJPUS") or {}).get("status") or "error", 2), "chg_6m_pct": chg_pct(pairs(fred.get("DEXJPUS")), 6)},
        "gold_record": REF["gold"], "dollar_fell_at_peak_stress": REF["dollar_fell_at_peak_stress"]}
    em = emfx_basket(fred)
    st["emfx"] = {**reading(em, "index (Jan-2006 = 100; up = EM currencies weaker)", None,
                            "equal-weight log-average of BRL, MXN, ZAR, INR, KRW, THB, CNY, MYR per dollar (FRED H.10; TRY and IDR are not on FRED daily)",
                            worst([(fred.get(s) or {}).get("status") for s in EMFX_IDS]), 1,
                            pct_since=add_months(em[-1][0], -120) if em else None),
                  "chg_6m_pct": chg_pct(em, 6), "chg_12m_pct": chg_pct(em, 12), "series": weekly(em, k=1),
                  "legs": {s: {"latest": r(pairs(fred.get(s))[-1][1], 4) if pairs(fred.get(s)) else None,
                               "chg_12m_pct": chg_pct(pairs(fred.get(s)), 12)} for s in EMFX_IDS}}
    brent = pairs(fred.get("DCOILBRENTEU"))
    st["brent"] = {**reading(brent, "$/bbl", (fred.get("DCOILBRENTEU") or {}).get("src"), "Brent crude spot (EIA via FRED)",
                             (fred.get("DCOILBRENTEU") or {}).get("status") or "error", 1), "chg_12m_pct": chg_pct(brent, 12)}
    st["counter_examples"] = REF["counter_examples"]
    st["status"] = worst([st["dxy"]["status"], broad["broad"]["status"], st["emfx"]["status"],
                          (fred.get("DGS10") or {}).get("status")])
    return st


# ---------------------------------------------------------------------------- layer 2: funding
def funding_block(inp: dict) -> dict:
    fred = inp.get("fred") or {}
    ofr = inp.get("ofr") or {}
    f = {s: pairs(fred.get(s)) for s in ("DCPF3M", "DCPN3M", "DTB3", "NFCIRISK", "SOFR", "SOFR99", "IORB", "SWPT")}
    src = {s: (fred.get(s) or {}).get("src") for s in f}
    stt = {s: (fred.get(s) or {}).get("status") or "error" for s in f}
    ofr_ps = {c: pairs({"dates": ofr.get("dates"), "values": ofr.get(c)}) for c in ("Funding", "Emerging markets", "Safe assets")}
    ofr_st = ofr.get("status") or "error"
    cpf = spread(f["DCPF3M"], f["DTB3"])
    cpn = spread(f["DCPN3M"], f["DTB3"])
    tail = spread(f["SOFR99"], f["SOFR"], 100)
    iorb = spread(f["SOFR"], f["IORB"], 100)
    swpt = [(d, v / 1000) for d, v in f["SWPT"]]
    e = inp.get("emb") or {}
    emb = pairs(e)

    def row(rid, label, ps, unit, srcs, status, dp, direction, note=None):
        rd = reading(ps, unit, srcs, None, status, dp, pct_since=add_months(ps[-1][0], -120) if ps else None)
        yr = [v for d, v in ps if ps and d > add_months(ps[-1][0], -12)]
        return {"id": rid, "label": label, **rd, "median_1y": r(median(yr), dp), "direction": direction, "note": note}

    emb_row = row("emb", "EM dollar bonds (EMB ETF)", emb, "$", e.get("src"), e.get("status") or "error", 2, "lower = EM dollar debt under pressure")
    hi = max((v for d, v in emb if emb and d >= add_months(emb[-1][0], -12)), default=None)
    emb_row.update(pct_own_history=None, pct_10y=None, chg_1m_pct=chg_pct(emb, 1),
                   off_52w_high_pct=r(100 * (emb[-1][1] / hi - 1), 1) if emb and hi else None,
                   note="price, not a spread; the feed holds two years, so it is read as its 1-month change and its distance from the 52-week high")
    rows = [
        row("cp_fin", "Financial CP minus 3-month bill", cpf, "pp", [src["DCPF3M"], src["DTB3"]], worst([stt["DCPF3M"], stt["DTB3"]]), 2, "higher = more stress"),
        row("cp_nonfin", "Nonfinancial CP minus 3-month bill", cpn, "pp", [src["DCPN3M"], src["DTB3"]], worst([stt["DCPN3M"], stt["DTB3"]]), 2,
            "higher = more stress", "the nonfinancial CP rate is published irregularly"),
        row("ofr_funding", "OFR stress index: funding", ofr_ps["Funding"], "index (0 = average)", ofr.get("src"), ofr_st, 3, "higher = more stress"),
        row("ofr_em", "OFR stress index: emerging markets", ofr_ps["Emerging markets"], "index (0 = average)", ofr.get("src"), ofr_st, 3, "higher = more stress"),
        row("ofr_safe", "OFR stress index: safe assets", ofr_ps["Safe assets"], "index (0 = average)", ofr.get("src"), ofr_st, 3, "higher = more demand for safe assets"),
        row("nfci_risk", "Chicago Fed NFCI risk subindex", f["NFCIRISK"], "index (0 = average)", src["NFCIRISK"], stt["NFCIRISK"], 3, "higher = tighter (weekly)"),
        row("sofr_tail", "SOFR 99th percentile minus SOFR", tail, "bp", [src["SOFR99"], src["SOFR"]], worst([stt["SOFR99"], stt["SOFR"]]), 0, "higher = repo tail stress"),
        row("sofr_iorb", "SOFR minus interest on reserves", iorb, "bp", [src["SOFR"], src["IORB"]], worst([stt["SOFR"], stt["IORB"]]), 0, "above zero = reserves less ample"),
        row("swap_lines", "Fed central-bank liquidity swaps outstanding", swpt, "$bn", src["SWPT"], stt["SWPT"], 2,
            "higher = foreign central banks borrowing dollars (weekly, Wednesday)"),
        emb_row,
    ]
    peaks = REF["funding_leadlag"]
    out = {"rows": rows, "label": "leads the dollar's peak, coincident with crisis onset, silent in the EM growth scares (2015-16, 2018)",
           "series": {"cp_fin": weekly(cpf, since="2007-01-01"), "ofr_funding": weekly(ofr_ps["Funding"], since="2007-01-01"),
                      "swap_lines": weekly(swpt, since="2007-01-01")},
           "leadlag": peaks, "swap_events": REF["events"]["swap_lines"],
           "swap_peaks": [{"date": "2008-12-17", "bn": 583.1}, {"date": "2012-02-15", "bn": 109.1}, {"date": "2020-05-27", "bn": 448.9},
                          {"date": "2023-12-27", "bn": 1.36}],
           "basis": "own-history percentile = share of the series' history (from the date shown) at or below today's value; "
                    "alarm and peak dates from the study's lead/lag table (trading days vs the broad dollar's peak)",
           "status": worst([x["status"] for x in rows if x["id"] not in ("cp_nonfin",)])}
    return out


# ---------------------------------------------------------------------------- layer 3: the scramble gauge
def above_prior_high(ps, n=20):
    """(today's close, max of the prior n closes, today above it)."""
    if len(ps) < n + 1:
        return None, None, None
    prior = max(v for _, v in ps[-n - 1:-1])
    return ps[-1][1], prior, bool(ps[-1][1] > prior)


def scramble_block(inp: dict, fund: dict, today: str, path: str) -> dict:
    fred = inp.get("fred") or {}
    ds, B, Y = rule_index(fred)
    ref = REF["scramble_rule"]
    out = {"params": RULE, "variant_live": ref["variant_live"], "history": ref["firings"], "history_unpatched": ref["firings_unpatched"],
           "vspike_timing": ref["vspike_timing"], "monthly_null": ref["monthly_null"], "end_of_scramble": REF["end_of_scramble"],
           "basis": ref["basis"], "wording": SCRAMBLE_WORDS,
           "status": worst([(fred.get(s) or {}).get("status") for s in ("DTWEXBGS", "DGS10", "VIXCLS")])}
    if len(ds) <= RULE["first_eval_index"]:
        out.update(state=None, gate_open=None, indicators=None, confirmations=None, live_check=None, live_firings=[])
        out["status"] = "error"
        return out
    rearm = scramble_firings(ds, B, Y, True)
    unp = scramble_firings(ds, B, Y, False)
    hist_re = [f["date"] for f in rearm if f["date"] <= FROZEN_ON]
    hist_un = [f["date"] for f in unp if f["date"] <= FROZEN_ON]
    frozen_re = [f["date"] for f in ref["firings"]]
    out["live_check"] = {"reproduces_frozen_rearm": hist_re == frozen_re, "reproduces_frozen_unpatched": hist_un == ref["firings_unpatched"],
                         "live_history_rearm": hist_re, "live_history_unpatched": hist_un,
                         "note": "the rule re-run on today's data vintage; a mismatch means H.10 or FRED revised the history"}
    new = {}
    for variant, fs in (("re-arm", rearm), ("unpatched", unp)):
        for f in fs:
            if f["date"] > FROZEN_ON:
                e = new.setdefault(f["date"], {"kind": "scramble_rule", "date": f["date"], "variants": [],
                                               **{x: f[x] for x in ("roc20_max_pct", "roc20_max_date", "roc20_now_pct", "dollar")}})
                e["variants"].append(variant)
    st = rule_state(ds, B, Y)
    out["state"] = st
    out["gate_open"] = st["gate_open"]
    out["fires_today"] = {"re-arm": bool(rearm and rearm[-1]["k"] == len(ds) - 1), "unpatched": bool(unp and unp[-1]["k"] == len(ds) - 1)}
    out["series"] = {"dates": ds[-750:], "dollar": [r(x, 2) for x in B[-750:]],
                     "roc20_pct": [r(100 * (B[j] / B[j - 20] - 1), 2) if j >= 20 else None for j in range(max(0, len(B) - 750), len(B))]}
    out["series_long"] = weekly(list(zip(ds, B)), k=2)
    if not st["gate_open"]:
        out["indicators"] = None
        out["confirmations"] = None
    else:
        rows = {x["id"]: x for x in fund["rows"]}
        cp, of = rows["cp_fin"], rows["ofr_funding"]
        b_met = (cp["latest"] is not None and cp["median_1y"] is not None and of["latest"] is not None and of["median_1y"] is not None
                 and cp["latest"] < cp["median_1y"] and of["latest"] < of["median_1y"])
        g_now, g_hi, g_ok = above_prior_high(pairs(inp.get("gold")))
        e_now, e_hi, e_ok = above_prior_high(pairs(inp.get("emb")))
        out["indicators"] = {
            "a_deceleration": {"met": bool(st["decel_met"] and st["near_high_met"]), "roc20_now_pct": st["roc20_now_pct"],
                               "roc20_max_60d_pct": st["roc20_max_60d_pct"], "ratio_now_to_max": st["ratio_now_to_max"],
                               "dollar_vs_60d_high_pct": st["dollar_vs_60d_high_pct"],
                               "rule": "20-day climb at or below half its 60-day maximum, dollar within 3% of its 60-day high"},
            "b_funding_easing": {"met": bool(b_met), "cp_now": cp["latest"], "cp_median_1y": cp["median_1y"],
                                 "ofr_funding_now": of["latest"], "ofr_funding_median_1y": of["median_1y"],
                                 "rule": "financial CP minus bill AND the OFR funding subindex both below their 1-year medians"},
            "c_risk_turn": {"met": bool(g_ok and e_ok) if g_ok is not None and e_ok is not None else None,
                            "gold_now": r(g_now, 1), "gold_prior_20d_high": r(g_hi, 1), "emb_now": r(e_now, 2), "emb_prior_20d_high": r(e_hi, 2),
                            "rule": "gold AND EMB closing above their prior 20-day highs"},
            "note": "three indicators shown separately and never summed; a met (a) reads 'dollar scramble peaking' and says nothing about the crisis"}
        sw = [(d, v) for d, v in pairs(fred.get("SWPT")) if d >= st["episode_start"]]
        sw_pk = max((v for _, v in sw), default=None)
        out["confirmations"] = {
            "dollar_off_peak_pct": r(100 * (B[-1] / st["episode_dollar_peak"] - 1), 2) if st["episode_dollar_peak"] else None,
            "dollar_3pct_off_peak": bool(st["episode_dollar_peak"] and B[-1] <= 0.97 * st["episode_dollar_peak"]),
            "swap_now_bn": r(sw[-1][1] / 1000, 2) if sw else None, "swap_episode_peak_bn": r(sw_pk / 1000, 2) if sw_pk else None,
            "swap_below_10pct_of_peak": (bool(sw[-1][1] < 0.10 * sw_pk) if sw and sw_pk and sw_pk >= 10_000 else None),
            "episode_start": st["episode_start"],
            "rule": "the dollar 3% off its episode peak; swap-line usage under 10% of the episode's peak (shown only if that peak was at least $10bn)"}
    led = append_ledger(path, list(new.values()), today) if new else load_ledger(path)
    out["live_firings"] = [e for e in led.get("entries", []) if e.get("kind") == "scramble_rule"]
    out["ledger_status"] = ("unreadable" if led.get("_unreadable") else "write_failed" if led.get("_write_failed") else "ok")
    return out


# ---------------------------------------------------------------------------- layer 4: slow state
def _q_end(tp: str) -> str:
    y, q = tp.split("-Q") if "-Q" in tp else (tp[:4], "4")
    return f"{y}-{int(q) * 3:02d}"


def slow_block(inp: dict) -> dict:
    fred = inp.get("fred") or {}
    bis = inp.get("bis") or {}
    out: dict = {}
    tot = [(tp, v) for tp, v in ((bis.get("gli_total") or {}).get("series") or {}).get("_", []) if v is not None]
    eme = dict((tp, v) for tp, v in ((bis.get("gli_eme") or {}).get("series") or {}).get("_", []) if v is not None)
    bps = pairs(fred.get("DTWEXBGS"))
    if tot:
        tp, v = tot[-1]
        prev = dict(tot).get(f"{int(tp[:4]) - 1}{tp[4:]}")
        yoy = r(100 * (v / prev - 1), 1) if prev else None
        e_v = eme.get(tp)
        e_prev = eme.get(f"{int(tp[:4]) - 1}{tp[4:]}")
        qs = [t for t, _ in tot if t >= "2007-Q1"]
        tmap = dict(tot)
        yoys = [r(100 * (tmap[t] / tmap[f"{int(t[:4]) - 1}{t[4:]}"] - 1), 1) if tmap.get(f"{int(t[:4]) - 1}{t[4:]}") else None for t in qs]
        bm = monthly_avg(bps)
        dyoy = []
        for t in qs:
            me = _q_end(t)
            d1, d0 = bm.get(me), bm.get(f"{int(me[:4]) - 1}{me[4:]}")
            dyoy.append(r(100 * (d1 / d0 - 1), 1) if d1 and d0 else None)
        out["usd_credit"] = {
            "quarter": tp, "total_tn": r(v / 1e6, 3), "yoy_pct": yoy, "eme_tn": r(e_v / 1e6, 3) if e_v else None,
            "eme_yoy_pct": r(100 * (e_v / e_prev - 1), 1) if e_v and e_prev else None,
            "eme_share_pct": r(100 * e_v / v, 1) if e_v else None,
            "label": None if yoy is None else ("re-dollarising (Johnson's term: dollar credit outside the US expanding)" if yoy > 0
                                               else "de-dollarising (Johnson's term: dollar credit outside the US contracting)"),
            "reading": "coincident; the dollar moves about a quarter first; descriptive, not a fuel gauge",
            "series": {"quarters": qs, "credit_yoy_pct": yoys, "dollar_yoy_pct": dyoy},
            "history": REF["redollarisation"], "src": [(bis.get("gli_total") or {}).get("src"), (bis.get("gli_eme") or {}).get("src")],
            "basis": "BIS global liquidity indicators: USD credit (bank loans and debt securities) to non-bank borrowers outside the US; "
                     "simple yoy % changes; dollar = Fed broad index, average of the quarter's last month (2007+). The study's "
                     "correlations use log changes on the same basis (same sign, nearly the same size)",
            "status": worst([(bis.get("gli_total") or {}).get("status"), (bis.get("gli_eme") or {}).get("status")])}
    else:
        out["usd_credit"] = {"status": "error", "history": REF["redollarisation"]}
    fa = [(tp, v) for tp, v in ((bis.get("fx_all") or {}).get("series") or {}).get("_", []) if v is not None]
    fu = dict((tp, v) for tp, v in ((bis.get("fx_usd") or {}).get("series") or {}).get("_", []) if v is not None)
    out["fx_swaps"] = ({"period": fa[-1][0], "all_tn": r(fa[-1][1] / 1e6, 2), "usd_leg_tn": r(fu[fa[-1][0]] / 1e6, 2) if fa[-1][0] in fu else None,
                        "prev_period": fa[-2][0] if len(fa) > 1 else None, "prev_all_tn": r(fa[-2][1] / 1e6, 2) if len(fa) > 1 else None,
                        "basis": "BIS OTC derivatives: outright forwards, FX swaps and currency swaps, notional outstanding, all counterparties "
                                 "(semiannual, about five months' lag); the stock is gross notional, not a net dollar shortfall",
                        "src": [(bis.get("fx_all") or {}).get("src"), (bis.get("fx_usd") or {}).get("src")],
                        "status": worst([(bis.get("fx_all") or {}).get("status"), (bis.get("fx_usd") or {}).get("status")])}
                       if fa else {"status": "error"})
    cb = (bis.get("cbpol") or {}).get("series") or {}
    names = {"US": "United States", "XM": "Euro area", "JP": "Japan", "GB": "United Kingdom", "CH": "Switzerland", "BR": "Brazil",
             "MX": "Mexico", "IN": "India", "KR": "Korea", "ZA": "South Africa", "TR": "Turkey", "ID": "Indonesia", "CN": "China"}
    us = [(tp, v) for tp, v in cb.get("US", []) if v is not None]
    us_now = us[-1][1] if us else None
    prow = []
    for a in names:
        ps = [(tp, v) for tp, v in cb.get(a, []) if v is not None]
        if not ps:
            continue
        v12 = dict(ps).get(add_months(ps[-1][0] + "-01", -12)[:7])
        prow.append({"area": a, "name": names[a], "rate": ps[-1][1], "month": ps[-1][0],
                     "vs_fed_pp": r(ps[-1][1] - us_now, 2) if us_now is not None and a != "US" else None,
                     "chg_12m_pp": r(ps[-1][1] - v12, 2) if v12 is not None else None})
    out["policy_rates"] = {"rows": prow, "src": (bis.get("cbpol") or {}).get("src"),
                           "basis": "BIS central bank policy rates, monthly, end of period (US = mid-point of the target range)",
                           "status": (bis.get("cbpol") or {}).get("status") or "error"}
    d2, ft = pairs(fred.get("DGS2")), pairs(fred.get("DFEDTARU"))
    out["us2y_vs_funds"] = {"dgs2": r(d2[-1][1], 2) if d2 else None, "dgs2_asof": d2[-1][0] if d2 else None,
                            "fed_upper": r(ft[-1][1], 2) if ft else None, "fed_upper_asof": ft[-1][0] if ft else None,
                            "gap_pp": r(d2[-1][1] - asof(ft, d2[-1][0]), 2) if d2 and ft and asof(ft, d2[-1][0]) is not None else None,
                            "reading": "2-year above the funds-rate ceiling = the market prices hikes",
                            "status": worst([(fred.get("DGS2") or {}).get("status"), (fred.get("DFEDTARU") or {}).get("status")])}
    y10, tp10 = pairs(fred.get("DGS10")), pairs(fred.get("THREEFYTP10"))
    cus = [(d, v / 1000) for d, v in pairs(fred.get("WMTSECL1"))]
    out["treasury"] = {
        "y10": reading(y10, "%", (fred.get("DGS10") or {}).get("src"), "10-year Treasury yield", (fred.get("DGS10") or {}).get("status") or "error", 2),
        "y10_chg_6m_pp": chg_abs(y10, 6),
        "term_premium": reading(tp10, "pp", (fred.get("THREEFYTP10") or {}).get("src"), "Kim-Wright 10-year term premium",
                                (fred.get("THREEFYTP10") or {}).get("status") or "error", 2),
        "custody": {**reading(cus, "$bn", (fred.get("WMTSECL1") or {}).get("src"),
                              "Treasuries held at the New York Fed for foreign official accounts (weekly)",
                              (fred.get("WMTSECL1") or {}).get("status") or "error", 1, pct_since=add_months(cus[-1][0], -120) if cus else None),
                    "chg_12m_pct": chg_pct(cus, 12)},
        "april_2025": REF["events"]["treasury_2025"], "chain_2022": REF["events"]["chain_2022"]}
    out["status"] = worst([out["usd_credit"].get("status"), out["fx_swaps"].get("status"), out["policy_rates"]["status"],
                           out["us2y_vs_funds"]["status"], out["treasury"]["y10"]["status"]])
    return out


# ---------------------------------------------------------------------------- the ledger view
def ledger_block(inp: dict, state: dict, today: str, path: str) -> dict:
    """Frozen in-sample rows (momentum episodes, rule firings) + live forward rows with outcomes as they mature."""
    fred = inp.get("fred") or {}
    spx, baa, broad = pairs(fred.get("SP500")), pairs(fred.get("BAA10Y")), pairs(fred.get("DTWEXBGS"))
    em = emfx_basket(fred)
    last_day = min([p[-1][0] for p in (spx, baa, broad, em) if p] or [today])
    mom = state["momentum"]
    mon = state["dxy"]["monthly"]
    new = []
    if mom.get("signal_months"):
        sig = mom["signal_months"]
        ms = mon["months"]
        idx = {m: i for i, m in enumerate(ms)}
        for m in sig:
            if m <= FROZEN_ON[:7]:
                continue
            prev = [x for x in sig if x < m]
            if not prev or idx[m] - idx[prev[-1]] > 12:
                i = idx[m]
                new.append({"kind": "momentum", "date": m, "dxy_12m_pct": r(100 * (mon["avg"][i] / mon["avg"][i - 12] - 1), 1),
                            "dxy": mon["avg"][i]})
    led = append_ledger(path, new, today) if new else load_ledger(path)
    live = []
    for e in led.get("entries", []):
        d = e["date"] if len(e["date"]) == 10 else e["date"] + "-28"
        live.append({**e, "outcomes": forward_outcomes(d, spx, em, baa, broad, last_day)})
    return {"frozen_momentum": REF["momentum_ledger"], "frozen_momentum_basis": REF["momentum_ledger_basis"],
            "frozen_rule": [{k: f[k] for k in ("date", "reading", "outcomes", "dollar_further_rise_pct", "spx_to_next_low_pct")} for f in REF["scramble_rule"]["firings"]],
            "live": live, "frozen_on": FROZEN_ON, "outcomes_through": last_day,
            "basis": "frozen rows are in-sample reconstructions; live rows are appended the day the panel first sees a firing after the freeze "
                     "and are never edited; outcomes fill in at 3, 6 and 12 months (S&P 500, EM FX basket, BAA minus 10y, broad dollar)",
            "status": "ok" if not led.get("_unreadable") else "error"}


# ---------------------------------------------------------------------------- assembly
def _ord(x) -> str:
    n = int(round(x))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def headline(state: dict, fund: dict, scr: dict, slow: dict) -> str:
    dx = state["dxy"]
    parts = []
    if dx.get("latest") is not None:
        parts.append(f"DXY {dx['latest']:.1f} ({dx['asof']}), {dx['band_position']}")
    b = state["broad"]["broad"]
    if b.get("latest") is not None:
        c6 = state["broad"]["broad"].get("chg_6m_pct")
        parts.append(f"broad dollar {b['latest']:.1f} ({b['asof']}){'' if c6 is None else f', {c6:+.1f}% in 6 months'}")
    rows = {x["id"]: x for x in fund["rows"]}
    cp, sw = rows["cp_fin"], rows["swap_lines"]
    if cp.get("latest") is not None:
        pr = "" if cp.get("pct_own_history") is None else f" ({_ord(cp['pct_own_history'])} percentile of its history since {(cp.get('history_from') or '')[:4]})"
        parts.append(f"financial CP minus bill {cp['latest']:.2f}pp{pr}")
    if sw.get("latest") is not None:
        parts.append(f"swap lines ${sw['latest']:.1f}bn")
    st = scr.get("state")
    if st:
        if st["gate_open"]:
            parts.append(f"scramble gauge OPEN: largest 20-day climb {st['roc20_max_60d_pct']:+.1f}% ({st['roc20_max_date']}) with the 10-year falling")
        else:
            parts.append(f"scramble gauge closed: largest 20-day climb in 60 days {st['roc20_max_60d_pct']:+.1f}% "
                         f"(it opens at +4% with the 10-year falling)")
    uc = slow.get("usd_credit") or {}
    if uc.get("total_tn") is not None:
        parts.append(f"dollar credit outside the US ${uc['total_tn']:.2f}tn, {uc['yoy_pct']:+.1f}% yoy ({uc['quarter']})")
    if not parts:
        return "Live data unavailable (no source answered); the frozen historical record below still applies."
    return "; ".join(parts) + "."


def build_dollar_watch(inp: dict, today: str | None = None, ledger_file: str | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date().isoformat()
    path = ledger_file or ledger_path()
    state = state_block(inp)
    fund = funding_block(inp)
    scr = scramble_block(inp, fund, today, path)
    slow = slow_block(inp)
    led = ledger_block(inp, state, today, path)
    blocks = {"state": state["status"], "funding": fund["status"], "scramble": scr["status"], "slow": slow["status"], "ledger": led["status"]}
    return {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "frozen_on": FROZEN_ON, "mode": "descriptive",
            "status": {"overall": worst(blocks.values()), "blocks": blocks},
            "headline": headline(state, fund, scr, slow),
            "state": state, "funding": fund, "scramble": scr, "slow": slow, "ledger": led,
            "crisis_lists": REF["crisis_lists"], "window_convention": REF["window_convention"],
            "provenance": {k: REF["provenance"][k] for k in ("study", "builder", "reviews")},
            "pending_questions": [
                {"rank": "P1", "q": "Which crisis list is the frozen primary: A25 (25 broad crises), C16 (16 dollar-stress onsets, the default) "
                                    "or N5 (the 5 funding squeezes, reported only)?", "moves": "every base rate on the panel and the pre-registration freeze",
                 "status": "asked", "first_asked": "2026-11-02"}],
            "honesty": HONESTY}
