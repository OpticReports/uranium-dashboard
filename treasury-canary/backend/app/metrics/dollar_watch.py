"""Dollar watch tab (studies/dollar-watch.md §5, §9): assembles GET /dollar-watch.

DESCRIPTIVE ONLY. No odds, no colour-coded states, no crisis calls: every
historical number is in-sample and comes from the frozen reference
(sources/dollar_reference.json, rebuilt by studies/dollar_watch/code/
build_reference.py); every conditional count carries its N and base rate. The
pre-registration is drafted, reviewed NOT_PASS and not frozen (memo §9.4).

Four layers plus the forward ledger:
  state     ICE DXY vs Johnson's ad hoc 85-105 band, the Fed broad index and its
            AFE/EME split, the dollar-yield quadrant, 12-month momentum, safe
            havens, the EM FX basket, Brent.
  funding   CP-bill, OFR funding/EM/safe assets, NFCI risk, SOFR tails, swap
            lines, EMB, each against its own history.
  scramble  the fixed deceleration rule run live: gate first, three indicators
            shown separately and never summed, two confirmations, the permanent
            in-sample record and its null.
  slow      BIS dollar credit outside the US, the FX-swap stock, policy rates vs
            the Fed, the 2-year vs the funds ceiling, the Treasury channel.
  ledger    firings after the reference cut-off, append-only on the persistent
            disk; each horizon's outcome is frozen into its row when it matures.

sources/dollar_data.fetch_all() fetches; build_dollar_watch(inputs, today=...,
ledger_file=...) assembles (pure apart from the ledger file, injectable).
"""
from __future__ import annotations

import bisect
import json
import logging
import math
import os
import threading
from datetime import date, datetime, timedelta, timezone

from ..config import settings

logger = logging.getLogger(__name__)

REF_PATH = os.path.join(os.path.dirname(__file__), "..", "sources", "dollar_reference.json")
try:                                   # a broken reference must take down this route, not the whole app
    with open(REF_PATH, encoding="utf-8") as _fh:
        REF = json.load(_fh)
    REF_ERROR = None
except Exception as _exc:  # noqa: BLE001
    REF, REF_ERROR = {}, f"{type(_exc).__name__}: {_exc}"
    logger.error("dollar_reference.json unreadable: %s", REF_ERROR)

# The frozen rule (identical to build_reference.py RULE; a gate test asserts the reference agrees).
RULE_FROZEN = {"index": "Fed broad dollar DTWEXBGS, daily, on days with DTWEXBGS, DGS10 and VIXCLS all published (the frozen code/decel_realtime.py index)",
               "roc_days": 20, "window_days": 60, "min_max_roc": 0.04, "decel_ratio": 0.5, "near_high": 0.97,
               "yield_lookback_days": 20, "cooling_days": 120, "rearm_multiple": 1.5, "first_eval_index": 80}
RULE = (REF.get("scramble_rule") or {}).get("params") or RULE_FROZEN
FROZEN_ON = REF.get("frozen_on", "2026-11-02")
LAST_INDEX_DAY = (REF.get("scramble_rule") or {}).get("last_index_day", FROZEN_ON)    # the frozen record ends here
LAST_FROZEN_MONTH = ((REF.get("dxy_monthly") or {}).get("months") or [FROZEN_ON[:7]])[-1]
LEDGER_NAME = "dollar_ledger.json"
EMFX_IDS = ["DEXBZUS", "DEXMXUS", "DEXSFUS", "DEXINUS", "DEXKOUS", "DEXTHUS", "DEXCHUS", "DEXMAUS"]
QUAD_LABEL = {"usd_up_yld_down": "dollar up, 10-year yield down", "usd_up_yld_up": "dollar up, 10-year yield up",
              "usd_down_yld_up": "dollar down, 10-year yield up", "usd_down_yld_down": "dollar down, 10-year yield down"}
SCRAMBLE_WORDS = "dollar scramble peaking"      # a met (a) reads only this; nothing about the crisis
EXPIRES = "2027-01-01"                          # 60 days from the first ask (CLAUDE.md pending-question rule)

HONESTY_LIVE = [
    "Descriptive panel: readings and counts only, each conditional count with its N and base rate; nothing here is a forecast or a crisis call.",
    "Live readings use today's data vintage; the broad dollar (H.10) is published weekly, so it can lag the DXY by up to two weeks. "
    "A reading dated today is intraday until the session ends.",
    "2026 (as of 2026-11-02) sits outside every pattern in this study: gold fell 27-31% from its January high with the dollar up under 6% and no "
    "dollar-funding stress, Brent nearly doubled, and foreign official custody is at a 14-year low. The dollar-funding mechanism "
    "does not explain it; do not read the crisis records on this page onto it.",
    "The pre-registration was drafted and both reviews returned NOT_PASS: the currency cross-section is not run as designed; the "
    "route is the forward ledger, which needs decades to score at realistic edges. The freeze waits on Casey's answers on the "
    "crisis list, the rule variant, the rule that dates future crises and what may ever drive a live notification.",
    "Ledger outcomes are measured from the first S&P close after the H.10 release that made a firing visible, not from the firing day.",
]

PENDING = [   # status per CLAUDE.md: asked / answered / refused / expired; "open" = ours to source, not a question to Casey
    {"rank": "P1", "q": "Which crisis list is the primary: A25 (25 broad crises), C16 (16 dollar-stress onsets; default) or N5 (the 5 funding squeezes, reported only)?",
     "moves": "every base rate on the panel; the freeze"},
    {"rank": "P1", "q": "Route after both reviews returned NOT_PASS: forward_only (the dated ledger; recommended) or a redesigned cross-section on the clean subset (low power)?",
     "moves": "whether anything is scored before the 2030s"},
    {"rank": "P1", "q": "Primary deceleration variant: unpatched (default) or re-arm? Both are logged forward either way.",
     "moves": "the ledger's primary record"},
    {"rank": "P1", "q": "The mechanical rule that dates future crises for the ledger (default: 2 of 5 markers: VIX at or above 40; OFR FSI above its "
                        "5-year 95th percentile for 5 days; EM FX basket +10% in 63 days; S&P -20% from its 252-day high; a Fed emergency action)",
     "moves": "how forward firings are scored"},
    {"rank": "P2", "q": "May a live notification on the gauge ever come from anything but the forward ledger? (default: ledger only)",
     "moves": "the notification licence"},
    {"rank": "P2", "q": "Is a paid basis-swap feed (the direct price of offshore dollars) worth it for the funding layer?", "moves": "layer 2 completeness"},
    {"rank": "P2", "q": "Reconstruct and freeze EM OAS history (FRED truncated it to 2023-11) as the repo does for HY/IG", "moves": "the EM stress row",
     "status": "open"},
    {"rank": "P3", "q": "Daily gold before 2000 (LBMA/FRED gone): find a free source", "moves": "the pre-2000 gold table", "status": "open"},
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
    return sorted((d, v) for d, v in zip(s.get("dates") or [], s.get("values") or []) if isinstance(d, str) and v is not None)


def asof(ps: list[tuple[str, float]], d: str):
    """last value on or before d (None if none)."""
    i = bisect.bisect_right(ps, (d, float("inf"))) - 1
    return ps[i][1] if i >= 0 else None


def first_after(ps: list[tuple[str, float]], d: str):
    """(date, value) of the first observation strictly after d, or (None, None)."""
    i = bisect.bisect_right(ps, (d, float("inf")))
    return ps[i] if i < len(ps) else (None, None)


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
    """(share of the history at or below the latest value, n, first date): the own-history percentile."""
    xs = [v for d, v in ps if since is None or d >= since]
    if len(xs) < 20:
        return None, len(xs), None
    srt = sorted(xs)
    return r(100 * bisect.bisect_right(srt, ps[-1][1]) / len(srt), 0), len(xs), (ps[0][0] if since is None else since)


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def spread(a: list, b: list, scale: float = 1.0) -> list[tuple[str, float]]:
    """a - b on a's dates with b as-of; rounded so equal printed spreads tie exactly (percentiles are at-or-below)."""
    out = []
    for d, v in a:
        w = asof(b, d)
        if w is not None:
            out.append((d, round((v - w) * scale, 6)))
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


def _ord(x) -> str:
    n = int(round(x))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _month_range(a: str, b: str) -> list[str]:
    out, m = [], a
    while m <= b:
        out.append(m)
        m = add_months(m + "-01", 1)[:7]
    return out


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
    """Every clause of the rule at the latest index day, as numbers (nothing summed). The window is the
    61 index days k-60..k, as in the rule."""
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
    seg = B[start:k + 1]
    return {"asof": ds[k], "k": k, "dollar": r(B[k], 2), "roc20_now_pct": r(100 * roc[k], 2),
            "roc20_max_60d_pct": r(100 * mx, 2), "roc20_max_date": ds[kmx], "ratio_now_to_max": r(roc[k] / mx, 2) if mx > 0 else None,
            "dollar_vs_60d_high_pct": r(100 * (B[k] / hi - 1), 2), "y10_now": Y[k], "y10_ref": y_ref,
            "y10_ref_date": ds[max(0, kmx - p["yield_lookback_days"])],
            "gate_open": bool(mx >= p["min_max_roc"] and Y[k] < y_ref),
            "climb_ge_4pct": bool(mx >= p["min_max_roc"]), "y10_falling": bool(Y[k] < y_ref),
            "decel_met": bool(roc[k] <= p["decel_ratio"] * mx), "near_high_met": bool(B[k] >= p["near_high"] * hi),
            "episode_start": ds[start], "episode_dollar_peak": r(max(seg), 2), "episode_dollar_peak_date": ds[start + seg.index(max(seg))]}


def h10_release(d: str) -> str:
    """The Monday after day d's week: the H.10 release that first carries d (4:15pm ET, after the equity close)."""
    dt = date.fromisoformat(d)
    return (dt + timedelta(days=7 - dt.weekday())).isoformat()


# ---------------------------------------------------------------------------- ledger (append-only, forward only)
_LEDGER_LOCK = threading.Lock()


def ledger_path() -> str:
    """$DOLLAR_LEDGER_PATH, else <parent of CACHE_DIR>/ledger/dollar_ledger.json (/app/data/ledger on Render:
    the persistent disk, outside the disposable caches)."""
    override = os.environ.get("DOLLAR_LEDGER_PATH")
    if override:
        return override
    base = os.path.dirname(os.path.abspath(settings.cache_dir.rstrip("/\\")))
    return os.path.join(base, "ledger", LEDGER_NAME)


def load_ledger(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return {"entries": []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("dollar ledger unreadable (%s); it is NOT written over", exc)
        return {"entries": [], "_unreadable": True}
    if not (isinstance(d, dict) and isinstance(d.get("entries"), list)
            and all(isinstance(e, dict) and isinstance(e.get("kind"), str) and isinstance(e.get("date"), str) for e in d["entries"])):
        logger.warning("dollar ledger has an unexpected shape; it is NOT written over")
        return {"entries": [], "_unreadable": True}
    return d


def _write_ledger(path: str, led: dict) -> dict:
    try:
        from ..sources.fred_csv import _write_atomic
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        body = {k: v for k, v in led.items() if not k.startswith("_") or k == "_about"}
        _write_atomic(path, json.dumps(body, indent=1, sort_keys=True))
    except Exception as exc:  # noqa: BLE001
        logger.warning("dollar ledger write failed: %s", exc)
        led["_write_failed"] = str(exc)[:200]
    return led


def append_ledger(path: str, new: list[dict], today: str) -> dict:
    """Add entries not already present (key: kind + date); never edit or drop one.
    An unreadable or wrongly shaped file is left untouched (the payload says so)."""
    with _LEDGER_LOCK:
        led = load_ledger(path)
        if led.get("_unreadable"):
            return led
        have = {(e.get("kind"), e.get("date")) for e in led["entries"]}
        added = [dict(e, recorded_on=today) for e in new if (e["kind"], e["date"]) not in have]
        if not added:
            return led
        led = {"_about": "Dollar watch forward ledger: append-only, one row per live firing after the reference cut-off "
                         f"({LAST_INDEX_DAY} for the rule, {LAST_FROZEN_MONTH} for momentum); recorded_on is the day the panel first "
                         "saw it; each horizon's outcome is frozen into the row when it matures.",
               "frozen_on": FROZEN_ON, "entries": led["entries"] + added}
        return _write_ledger(path, led)


def freeze_matured(path: str, compute, last_day: str, today: str) -> dict:
    """Write each matured horizon's outcome into its row once (fields are only ever added, never changed)."""
    with _LEDGER_LOCK:
        led = load_ledger(path)
        if led.get("_unreadable") or not led["entries"]:
            return led
        changed = False
        for e in led["entries"]:
            done = e.setdefault("outcomes_frozen", {})
            for h, o in compute(e, last_day).items():
                if o is not None and h not in done and all(v is not None for v in o.values()):
                    done[h] = dict(o, frozen_on=today)
                    changed = True
        return _write_ledger(path, led) if changed else led


# ---------------------------------------------------------------------------- outcome helpers
def emfx_basket(fred: dict) -> tuple[list[tuple[str, float]], str | None]:
    """Equal-weight log-average of the 8 FRED EM pairs (EM currency per dollar; up = EM weaker), rebased so the average
    of its first month from 2006 on (Jan-2006 on the full FRED history) = 100. Returns (series, base month)."""
    legs = {s: pairs(fred.get(s)) for s in EMFX_IDS}
    if any(not legs[s] for s in EMFX_IDS):
        return [], None
    days = sorted({d for s in EMFX_IDS for d, _ in legs[s] if d >= "2006-01-01"})
    raw = []
    for d in days:
        vals = [asof(legs[s], d) for s in EMFX_IDS]
        if all(v is not None and v > 0 for v in vals):
            raw.append((d, math.exp(sum(math.log(v) for v in vals) / len(vals))))
    if not raw:
        return [], None
    base_m = raw[0][0][:7]
    first = [v for d, v in raw if d[:7] == base_m]
    b0 = sum(first) / len(first)
    return [(d, 100 * v / b0) for d, v in raw], base_m


def forward_outcomes(anchor: str | None, spx, baa, broad, last_day: str) -> dict:
    """S&P, Baa-10y and broad-dollar changes 3/6/12 calendar months after `anchor` (an S&P close date).
    EM FX outcomes are withheld until the pre-registration freeze."""
    o = {}
    if not anchor:
        return {f"{k}m": None for k in (3, 6, 12)}
    s0, b0, d0 = asof(spx, anchor), asof(baa, anchor), asof(broad, anchor)
    for k in (3, 6, 12):
        dk = add_months(anchor, k)
        if dk > last_day:
            o[f"{k}m"] = None               # not yet matured
            continue
        s1, b1, d1 = asof(spx, dk), asof(baa, dk), asof(broad, dk)
        o[f"{k}m"] = {"spx_pct": r(100 * (s1 / s0 - 1), 1) if s0 and s1 else None,
                      "baa10y_pp": r(b1 - b0, 2) if b0 is not None and b1 is not None else None,
                      "broad_dollar_pct": r(100 * (d1 / d0 - 1), 1) if d0 and d1 else None}
    return o


# ---------------------------------------------------------------------------- layer 1: state
def dxy_monthly(dxy_ps) -> dict:
    """Frozen monthly DXY (1971-01..cut-off) + live COMPLETE months after it, keyed by calendar month,
    with a contiguity check (a missing month is an error, never a silent index shift) and a splice check."""
    ref = REF.get("dxy_monthly") or {"months": [], "avg": [], "close": []}
    avg = dict(zip(ref["months"], ref["avg"]))
    close = dict(zip(ref["months"], ref["close"]))
    live_avg = monthly_avg(dxy_ps)
    live_close = {}
    for d, v in dxy_ps:
        live_close[d[:7]] = v
    cur = dxy_ps[-1][0][:7] if dxy_ps else None
    first = dxy_ps[0][0][:7] if dxy_ps else None          # the window's first month is partial
    complete = sorted(m for m in live_avg if cur and first < m < cur)
    overlap = [m for m in complete if m in avg and avg[m]]
    diffs = [abs(live_avg[m] / avg[m] - 1) for m in overlap]
    for m in complete:
        if m not in avg:
            avg[m], close[m] = r(live_avg[m], 2), r(live_close[m], 2)
    months = sorted(avg)
    gaps = [m for m in _month_range(months[0], months[-1]) if m not in avg] if months else []
    max_diff = r(100 * max(diffs), 2) if diffs else None
    return {"months": months, "avg": [avg[m] for m in months], "close": [close[m] for m in months],
            "frozen_through": LAST_FROZEN_MONTH, "gaps": gaps,
            "month_to_date": {"month": cur, "avg": r(live_avg.get(cur), 2), "days": sum(1 for d, _ in dxy_ps if d[:7] == cur)} if cur else None,
            "splice_check": {"overlap_months": len(overlap), "max_abs_diff_pct": max_diff,
                             "ok": bool(max_diff is not None and max_diff <= 0.5)},
            "basis": ref.get("basis")}


def momentum_now(mon: dict) -> dict:
    """12-month change of the monthly-average DXY, by calendar key (a gap gives None, never a 13-month span)."""
    avg = dict(zip(mon["months"], mon["avg"]))
    ms = mon["months"]

    def chg12(m):
        p = add_months(m + "-01", -12)[:7]
        return avg[m] / avg[p] - 1 if avg.get(m) and avg.get(p) else None

    m_last = ms[-1] if ms else None
    v = chg12(m_last) if m_last else None
    sig = [m for m in ms if (chg12(m) or 0) > 0.10]
    mom = REF.get("momentum") or {}
    return {"month": m_last, "dxy_12m_pct": r(100 * v, 1) if v is not None else None,
            "signal": bool(v is not None and v > 0.10), "threshold_pct": 10.0,
            "last_signal_month": sig[-1] if sig else None, "signal_months": sig, "basis": "monthly averages",
            "definition": mom.get("definition"), "by_list": mom.get("by_list"),
            "episodes_history": mom.get("episodes"), "episodes_began_in_a25_crisis": mom.get("episodes_began_in_a25_crisis"),
            "caveat": mom.get("caveat")}


def quadrant_now(mon: dict, dgs10_ps) -> dict:
    gm = {m: round(v, 2) for m, v in monthly_avg(dgs10_ps).items()}   # = GS10 (monthly average of business days)
    n_obs: dict[str, int] = {}
    for d, _ in dgs10_ps:
        n_obs[d[:7]] = n_obs.get(d[:7], 0) + 1
    avg = dict(zip(mon["months"], mon["avg"]))
    q = REF.get("quadrant") or {}
    out = {"definition": (q.get("definition") or "") + "; live 10-year = monthly average of DGS10 (the GS10 definition)",
           "onsets_C16": (q.get("by_list") or {}).get("C16"),
           "onsets_A25": {k: ((q.get("by_list") or {}).get("A25") or {}).get(k) for k in ("counts", "n")},
           "base_all_months": q.get("base_all_months"), "labels": QUAD_LABEL}
    for m in reversed(mon["months"]):
        p = add_months(m + "-01", -3)[:7]
        if m in gm and p in gm and avg.get(m) and avg.get(p) and n_obs.get(m, 0) >= 15:
            dd = avg[m] / avg[p] - 1
            dy = gm[m] - gm[p]
            qq = ("usd_up" if dd > 0 else "usd_down") + "_" + ("yld_up" if dy > 0 else "yld_down")
            return {**out, "month": m, "dxy_3m_pct": r(100 * dd, 1), "y10_3m_pp": r(dy, 2), "quadrant": qq, "label": QUAD_LABEL[qq]}
    return {**out, "month": None, "quadrant": None, "label": None}


def band_note() -> str:
    band = REF.get("band") or {}
    parts = []
    for key in ("A25", "C16", "N5"):
        x = (band.get("by_list") or {}).get(key) or {}
        n = x.get("n_excursions") or 0
        if not n:
            continue
        e12, e24 = x["base_12m"] * n, x["base_24m"] * n
        if abs(x["hits_12m"] - e12) <= 1 and abs(x["hits_24m"] - e24) <= 1:
            where = "within one excursion of its base"
        elif x["hits_12m"] < e12 and x["hits_24m"] < e24:
            where = "below its base"
        else:
            where = "above its base"
        parts.append(f"{key} {where} ({x['hits_12m']} vs {e12:.1f} expected at 12m; {x['hits_24m']} vs {e24:.1f} at 24m)")
    return ("Base = share of all months 1971-2026 with an onset in the window. " + "; ".join(parts)
            + ". No edge on any list. In-sample.")


def gold_note() -> str:
    g = REF.get("gold") or {}
    f = REF.get("dollar_fell_at_peak_stress") or {}
    op = (g.get("open_episodes") or [{}])[0]
    open_txt = f"; the open 2026 episode is {op['pct_so_far']:+.1f}% so far" if op.get("pct_so_far") is not None else ""
    fo = (f.get("open_episodes") or [{}])[0]
    f_open = (f" (the open 2026 episode, {fo['dxy_eve_to_peak_stress_pct_so_far']:+.1f}% so far, is provisional)"
              if fo.get("dxy_eve_to_peak_stress_pct_so_far") is not None else "")
    return (f"Gold was higher at the end than on the eve in {g.get('ended_higher')} of {g.get('n_with_end')} completed crises "
            f"({g.get('ended_higher_gt_1pct')} by more than 1%{open_txt}), against about {round(100 * (g.get('base_share') or 0))}% of all windows "
            "of the same lengths since 1971: no better than gold's own drift. It fell in all four episodes above: in the liquidation "
            "weeks of 2008 and 2020, over months in 2022 and the dotcom bust; it rose outright in 1973-74 and 1987. "
            f"The DXY was lower at peak stress than on the eve in {f.get('fell')} of {f.get('n_crises')} completed crises{f_open}, against about "
            f"{round(100 * (f.get('base_share') or 0))}% of same-length windows: it rose into peak stress in "
            f"{(f.get('n_crises') or 0) - (f.get('fell') or 0)} of {f.get('n_crises')}, more often than usual.")


def gold_funding_note(state: dict, fund: dict) -> str | None:
    """The gold tile's 'outside the crisis pattern' note, shown only when gold is 15%+ off its high AND dollar funding is
    quiet by the gauge's own test (financial CP minus bill and OFR funding both at or below their 1-year medians)."""
    g = state["safe_haven"]["gold"]
    rows = {x["id"]: x for x in fund["rows"]}
    cp, of = rows["cp_fin"], rows["ofr_funding"]
    vals = (g.get("off_52w_high_pct"), cp["latest"], cp["median_1y"], of["latest"], of["median_1y"])
    if any(v is None for v in vals) or g["off_52w_high_pct"] > -15:
        return None
    if not (cp["latest"] <= cp["median_1y"] and of["latest"] <= of["median_1y"]):
        return None
    pr = f"financial CP minus bill at its {_ord(cp['pct_own_history'])} percentile" if cp.get("pct_own_history") is not None else "financial CP minus bill below its 1-year median"
    return f"with dollar funding quiet ({pr}): outside the crisis pattern below"


def state_block(inp: dict) -> dict:
    fred = inp.get("fred") or {}
    dx = inp.get("dxy") or {}
    dxy_ps = pairs(dx)
    st: dict = {}
    mon = dxy_monthly(dxy_ps)
    band = REF.get("band") or {}
    last = dxy_ps[-1][1] if dxy_ps else None
    pos = None
    if last is not None:
        side = "above" if last > band.get("hi", 105) else "below" if last < band.get("lo", 85) else "inside"
        pos = f"{side} Johnson's ad hoc 85-105 band (no edge found)"
    closes = [c for c in mon["close"] if c is not None]
    st["dxy"] = {**reading(dxy_ps, "index", dx.get("src"), dx.get("basis"), dx.get("status") or "error", 2),
                 "provider": dx.get("provider"), "intraday": bool(dx.get("intraday")),
                 "chg_6m_pct": chg_pct(dxy_ps, 6), "chg_12m_pct": chg_pct(dxy_ps, 12),
                 "monthly": mon, "band_position": pos}
    # the daily feed holds ten years only: rank today's level against every month-end close since 1971 instead
    st["dxy"].update(pct_own_history=r(100 * sum(1 for c in closes if c <= last) / len(closes), 0) if last is not None and closes else None,
                     pct_10y=None, n_10y=None, n=len(closes), history_from=mon["months"][0] if mon["months"] else None,
                     pct_basis="share of month-end closes since 1971 at or below today's level")
    st["band"] = {**band, "note": band_note()}
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
    off = r(100 * (gps[-1][1] / hi52 - 1), 1) if gps and hi52 else None
    st["safe_haven"] = {
        "gold": {**reading(gps, "$/oz", g.get("src"), g.get("basis"), g.get("status") or "error", 1), "provider": g.get("provider"),
                 "intraday": bool(g.get("intraday")), "chg_6m_pct": chg_pct(gps, 6), "chg_12m_pct": chg_pct(gps, 12),
                 "off_52w_high_pct": off, "note": None},          # set in build_dollar_watch, only if funding is quiet (gold_funding_note)
        "chf": {**reading(pairs(fred.get("DEXSZUS")), "CHF per $", (fred.get("DEXSZUS") or {}).get("src"), "Swiss francs per dollar (up = franc weaker)",
                          (fred.get("DEXSZUS") or {}).get("status") or "error", 4), "chg_6m_pct": chg_pct(pairs(fred.get("DEXSZUS")), 6),
                "chg_12m_pct": chg_pct(pairs(fred.get("DEXSZUS")), 12)},
        "jpy": {**reading(pairs(fred.get("DEXJPUS")), "JPY per $", (fred.get("DEXJPUS") or {}).get("src"), "yen per dollar (up = yen weaker)",
                          (fred.get("DEXJPUS") or {}).get("status") or "error", 2), "chg_6m_pct": chg_pct(pairs(fred.get("DEXJPUS")), 6),
                "chg_12m_pct": chg_pct(pairs(fred.get("DEXJPUS")), 12)},
        "gold_record": REF.get("gold"), "dollar_fell_at_peak_stress": REF.get("dollar_fell_at_peak_stress"), "note": gold_note()}
    em, em_base = emfx_basket(fred)
    st["emfx"] = {**reading(em, f"index ({em_base or 'n/a'} average = 100; up = EM currencies weaker)", None,
                            "equal-weight log-average of BRL, MXN, ZAR, INR, KRW, THB, CNY, MYR per dollar (FRED H.10; TRY and IDR are not on FRED daily)",
                            worst([(fred.get(s) or {}).get("status") for s in EMFX_IDS]), 1,
                            pct_since=add_months(em[-1][0], -120) if em else None),
                  "chg_6m_pct": chg_pct(em, 6), "chg_12m_pct": chg_pct(em, 12), "series": weekly(em, k=1)}
    brent = pairs(fred.get("DCOILBRENTEU"))
    st["brent"] = {**reading(brent, "$/bbl", (fred.get("DCOILBRENTEU") or {}).get("src"), "Brent crude spot (EIA via FRED)",
                             (fred.get("DCOILBRENTEU") or {}).get("status") or "error", 1), "chg_12m_pct": chg_pct(brent, 12)}
    st["counter_examples"] = REF.get("counter_examples")
    issues = []
    if mon["gaps"]:
        issues.append(f"the monthly DXY has gaps ({', '.join(mon['gaps'][:3])}...): momentum and the quadrant are not computed across them")
        st["momentum"].update(dxy_12m_pct=None, signal=None)
    if dxy_ps and not mon["splice_check"]["ok"]:
        issues.append("the live DXY does not match the frozen monthly basis (splice check)")
    st["issues"] = issues
    st["status"] = worst([st["dxy"]["status"], broad["broad"]["status"], st["emfx"]["status"], (fred.get("DGS10") or {}).get("status"),
                          "error" if mon["gaps"] else "ok", "stale" if issues else "ok"])
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
    swpt = [(d, v / 1000) for d, v in f["SWPT"] if d >= "2007-12-12"]     # from the first swap lines: earlier zeros are not a history
    e = inp.get("emb") or {}
    emb = pairs(e)

    def row(rid, label, ps, unit, srcs, status, dp, direction, note=None):
        rd = reading(ps, unit, srcs, None, status, dp, pct_since=add_months(ps[-1][0], -120) if ps else None)
        yr = [v for d, v in ps if d > add_months(ps[-1][0], -12)] if ps else []
        return {"id": rid, "label": label, **rd, "median_1y": r(median(yr), dp), "direction": direction, "note": note}

    emb_row = row("emb", "EM dollar bonds (EMB ETF price)", emb, "$", e.get("src"), e.get("status") or "error", 2,
                  "lower = EM dollar bonds cheaper (US yields or EM spreads)",
                  "a price, not a spread; the feed holds two years, so it is read as its 1-month change and its distance from the 52-week high")
    hi = max((v for d, v in emb if d >= add_months(emb[-1][0], -12)), default=None) if emb else None
    emb_row.update(pct_own_history=None, pct_10y=None, n_10y=None, chg_1m_pct=chg_pct(emb, 1), intraday=bool(e.get("intraday")),
                   off_52w_high_pct=r(100 * (emb[-1][1] / hi - 1), 1) if emb and hi else None)
    rows = [
        row("cp_fin", "Financial CP minus 3-month bill", cpf, "pp", [src["DCPF3M"], src["DTB3"]], worst([stt["DCPF3M"], stt["DTB3"]]), 2, "higher = more stress"),
        row("cp_nonfin", "Nonfinancial CP minus 3-month bill", cpn, "pp", [src["DCPN3M"], src["DTB3"]], worst([stt["DCPN3M"], stt["DTB3"]]), 2,
            "higher = more stress", "the nonfinancial CP rate is published irregularly"),
        row("ofr_funding", "OFR stress index: funding", ofr_ps["Funding"], "index (0 = average)", ofr.get("src"), ofr_st, 3, "higher = more stress"),
        row("ofr_em", "OFR stress index: emerging markets", ofr_ps["Emerging markets"], "index (0 = average)", ofr.get("src"), ofr_st, 3, "higher = more stress"),
        row("ofr_safe", "OFR stress index: safe assets", ofr_ps["Safe assets"], "index (0 = average)", ofr.get("src"), ofr_st, 3, "higher = more demand for safe assets"),
        row("nfci_risk", "Chicago Fed NFCI risk subindex", f["NFCIRISK"], "index (0 = average)", src["NFCIRISK"], stt["NFCIRISK"], 3, "higher = tighter (weekly)"),
        row("sofr_tail", "SOFR 99th percentile minus SOFR", tail, "bp", [src["SOFR99"], src["SOFR"]], worst([stt["SOFR99"], stt["SOFR"]]), 0,
            "higher = repo tail stress", "history begins in 2018: no crisis record"),
        row("sofr_iorb", "SOFR minus interest on reserves", iorb, "bp", [src["SOFR"], src["IORB"]], worst([stt["SOFR"], stt["IORB"]]), 0,
            "above zero = reserves less ample", "history begins in 2021: no crisis record"),
        row("swap_lines", "Fed central-bank liquidity swaps outstanding", swpt, "$bn", src["SWPT"], stt["SWPT"], 2,
            "higher = foreign central banks borrowing dollars (weekly, Wednesday)", "history from the first swap lines, Dec-2007"),
        emb_row,
    ]
    return {"rows": rows,
            "label": "Funding prices led the dollar's peak by 3-5 months in 2008 and 2022 (n = 2), moved with it in 2020 and were silent "
                     "in the EM growth scares. Their first alarms came within about two months of the crisis's start as the 25-crisis list "
                     "dates it (2007, 2022; n = 2): roughly coincident with the crisis. The lead is over the dollar squeeze, which the "
                     "16-onset list dates later. The SOFR rows begin in 2018 and have no such record.",
            "series": {"cp_fin": weekly(cpf, since="2007-01-01"), "ofr_funding": weekly(ofr_ps["Funding"], since="2007-01-01"),
                       "swap_lines": weekly(swpt, since="2007-12-01")},
            "leadlag": REF.get("funding_leadlag"), "swap_events": (REF.get("events") or {}).get("swap_lines"),
            "basis": "own-history percentile = share of the series' history (from the date shown) at or below today's value",
            "status": worst([x["status"] for x in rows if x["id"] != "cp_nonfin"])}


# ---------------------------------------------------------------------------- layer 3: the scramble gauge
def above_prior_high(ps, n=20, drop_last=False):
    """(latest completed close, max of the n closes before it, latest above it)."""
    ps = ps[:-1] if drop_last else ps
    if len(ps) < n + 1:
        return None, None, None
    prior = max(v for _, v in ps[-n - 1:-1])
    return ps[-1][1], prior, bool(ps[-1][1] > prior)


def scramble_block(inp: dict, fund: dict, today: str, path: str) -> dict:
    fred = inp.get("fred") or {}
    ds, B, Y = rule_index(fred)
    ref = REF.get("scramble_rule") or {}
    unp_dates = set(ref.get("firings_unpatched") or [])
    history = [dict(f, variant="both" if f["date"] in unp_dates else "re-arm only") for f in (ref.get("firings") or [])]
    out = {"params": RULE, "history": history, "history_unpatched": ref.get("firings_unpatched"),
           "variant_live": "both variants run and logged; unpatched is the default primary until Casey decides "
                           "(re-arm was added after the 2008-09-22 miss)",
           "vspike_timing": ref.get("vspike_timing"), "monthly_null": ref.get("monthly_null"), "end_of_scramble": REF.get("end_of_scramble"),
           "basis": ref.get("basis"), "wording": SCRAMBLE_WORDS, "last_index_day": LAST_INDEX_DAY,
           "status": worst([(fred.get(s) or {}).get("status") for s in ("DTWEXBGS", "DGS10", "VIXCLS")])}
    if len(ds) <= RULE["first_eval_index"]:
        out.update(state=None, gate_open=None, indicators=None, confirmations=None, live_check=None, live_firings=[],
                   fires_today=None, series=None, series_long=None, status="error")
        return out
    rearm = scramble_firings(ds, B, Y, True)
    unp = scramble_firings(ds, B, Y, False)
    hist_re = [f["date"] for f in rearm if f["date"] <= LAST_INDEX_DAY]
    hist_un = [f["date"] for f in unp if f["date"] <= LAST_INDEX_DAY]
    out["live_check"] = {"reproduces_frozen_rearm": hist_re == [f["date"] for f in history],
                         "reproduces_frozen_unpatched": hist_un == list(ref.get("firings_unpatched") or []),
                         "live_history_rearm": hist_re, "live_history_unpatched": hist_un,
                         "note": "the rule re-run on today's data vintage up to the frozen record's last index day; a mismatch means "
                                 "H.10 or FRED revised the history"}
    new: dict = {}
    for variant, fs in (("re-arm", rearm), ("unpatched", unp)):
        for f in fs:
            if f["date"] > LAST_INDEX_DAY:
                e = new.setdefault(f["date"], {"kind": "scramble_rule", "date": f["date"], "variants": [], "h10_release": h10_release(f["date"]),
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
        vals = (cp["latest"], cp["median_1y"], of["latest"], of["median_1y"])
        b_met = None if any(v is None for v in vals) else bool(cp["latest"] < cp["median_1y"] and of["latest"] < of["median_1y"])
        g, e = inp.get("gold") or {}, inp.get("emb") or {}
        g_now, g_hi, g_ok = above_prior_high(pairs(g), drop_last=bool(g.get("intraday")))
        e_now, e_hi, e_ok = above_prior_high(pairs(e), drop_last=bool(e.get("intraday")))
        out["indicators"] = {
            "a_deceleration": {"met": bool(st["decel_met"] and st["near_high_met"]), "roc20_now_pct": st["roc20_now_pct"],
                               "roc20_max_60d_pct": st["roc20_max_60d_pct"], "ratio_now_to_max": st["ratio_now_to_max"],
                               "dollar_vs_60d_high_pct": st["dollar_vs_60d_high_pct"],
                               "rule": "20-day climb at or below half its 60-day maximum, dollar within 3% of its 60-day high"},
            "b_funding_easing": {"met": b_met, "cp_now": cp["latest"], "cp_median_1y": cp["median_1y"],
                                 "ofr_funding_now": of["latest"], "ofr_funding_median_1y": of["median_1y"],
                                 "rule": "financial CP minus bill AND the OFR funding subindex both below their 1-year medians"},
            "c_risk_turn": {"met": bool(g_ok and e_ok) if g_ok is not None and e_ok is not None else None,
                            "gold_now": r(g_now, 1), "gold_prior_20d_high": r(g_hi, 1), "emb_now": r(e_now, 2), "emb_prior_20d_high": r(e_hi, 2),
                            "rule": "gold AND EMB closing above their prior 20-day highs (completed sessions only)"},
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
    out["ledger_status"] = "unreadable" if led.get("_unreadable") else "write_failed" if led.get("_write_failed") else "ok"
    out["ledger_problem"] = led.get("_write_failed")
    return out


# ---------------------------------------------------------------------------- layer 4: slow state
def _q_end(tp: str) -> str | None:
    if "-Q" not in tp:
        return None
    y, q = tp.split("-Q")
    try:
        return f"{y}-{int(q) * 3:02d}"
    except ValueError:
        return None


def _prev_year(tp: str) -> str:
    return f"{int(tp[:4]) - 1}{tp[4:]}"


def slow_block(inp: dict) -> dict:
    fred = inp.get("fred") or {}
    bis = inp.get("bis") or {}
    out: dict = {}
    tot = [(tp, v) for tp, v in ((bis.get("gli_total") or {}).get("series") or {}).get("_", []) if v is not None and _q_end(tp)]
    eme = {tp: v for tp, v in ((bis.get("gli_eme") or {}).get("series") or {}).get("_", []) if v is not None}
    bps = pairs(fred.get("DTWEXBGS"))
    hist = REF.get("redollarisation") or {}
    if tot:
        tp, v = tot[-1]
        tmap = dict(tot)
        prev = tmap.get(_prev_year(tp))
        yoy = r(100 * (v / prev - 1), 1) if prev else None
        e_v, e_prev = eme.get(tp), eme.get(_prev_year(tp))
        qs = [t for t, _ in tot if t >= "2007-Q1"]
        yoys = [r(100 * (tmap[t] / tmap[_prev_year(t)] - 1), 1) if tmap.get(_prev_year(t)) else None for t in qs]
        bm = monthly_avg(bps)
        dyoy = []
        for t in qs:
            me = _q_end(t)
            d1, d0 = bm.get(me), bm.get(f"{int(me[:4]) - 1}{me[4:]}")
            dyoy.append(r(100 * (d1 / d0 - 1), 1) if d1 and d0 else None)
        label = None
        if yoy is not None:
            label = (f"re-dollarising (Johnson's term: dollar credit outside the US expanding, as in "
                     f"{hist.get('quarters_credit_growing')} of {hist.get('quarters')} quarters since 2001)") if yoy > 0 else \
                    "de-dollarising (Johnson's term: dollar credit outside the US contracting; seen only in 2009Q1-Q3 and 2022Q3-2023Q4)"
        out["usd_credit"] = {
            "quarter": tp, "total_tn": r(v / 1e6, 3), "yoy_pct": yoy, "eme_tn": r(e_v / 1e6, 3) if e_v else None,
            "eme_yoy_pct": r(100 * (e_v / e_prev - 1), 1) if e_v and e_prev else None,
            "eme_share_pct": r(100 * e_v / v, 1) if e_v else None, "label": label,
            "reading": "descriptive, not a fuel gauge: the stock has set records in calm years and before crises alike since 2010",
            "series": {"quarters": qs, "credit_yoy_pct": yoys, "dollar_yoy_pct": dyoy},
            "history": hist, "src": [(bis.get("gli_total") or {}).get("src"), (bis.get("gli_eme") or {}).get("src")],
            "basis": "BIS global liquidity indicators: USD credit (bank loans and debt securities) to non-bank borrowers outside the US; "
                     "the chart uses simple yoy % changes and the Fed broad index averaged over each quarter's last month (2007+); the "
                     "study's correlations use log changes on quarter-end values (close, not identical)",
            "status": worst([(bis.get("gli_total") or {}).get("status"), (bis.get("gli_eme") or {}).get("status")])}
    else:
        out["usd_credit"] = {"status": "error", "history": hist}
    fa = [(tp, v) for tp, v in ((bis.get("fx_all") or {}).get("series") or {}).get("_", []) if v is not None]
    fu = {tp: v for tp, v in ((bis.get("fx_usd") or {}).get("series") or {}).get("_", []) if v is not None}
    out["fx_swaps"] = ({"period": fa[-1][0], "all_tn": r(fa[-1][1] / 1e6, 2), "usd_leg_tn": r(fu[fa[-1][0]] / 1e6, 2) if fa[-1][0] in fu else None,
                        "prev_period": fa[-2][0] if len(fa) > 1 else None, "prev_all_tn": r(fa[-2][1] / 1e6, 2) if len(fa) > 1 else None,
                        "basis": "BIS OTC derivatives: outright forwards, FX swaps and currency swaps, notional outstanding, all counterparties "
                                 "(semiannual, about five months' lag); gross notional, not a net dollar shortfall",
                        "src": [(bis.get("fx_all") or {}).get("src"), (bis.get("fx_usd") or {}).get("src")],
                        "status": worst([(bis.get("fx_all") or {}).get("status"), (bis.get("fx_usd") or {}).get("status")])}
                       if fa else {"status": "error"})
    cb = (bis.get("cbpol") or {}).get("series") or {}
    names = {"US": "United States", "XM": "Euro area", "JP": "Japan", "GB": "United Kingdom", "CH": "Switzerland", "BR": "Brazil",
             "MX": "Mexico", "IN": "India", "KR": "Korea", "ZA": "South Africa", "TR": "Turkey", "ID": "Indonesia", "CN": "China"}
    us = {tp: v for tp, v in cb.get("US", []) if v is not None}
    prow = []
    for a in names:
        ps = [(tp, v) for tp, v in cb.get(a, []) if v is not None]
        if not ps:
            continue
        m, rate = ps[-1]
        v12 = dict(ps).get(add_months(m + "-01", -12)[:7])
        prow.append({"area": a, "name": names[a], "rate": rate, "month": m,
                     "vs_fed_pp": r(rate - us[m], 2) if a != "US" and m in us else None,     # the Fed rate in the SAME month
                     "chg_12m_pp": r(rate - v12, 2) if v12 is not None else None})
    out["policy_rates"] = {"rows": prow, "src": (bis.get("cbpol") or {}).get("src"),
                           "basis": "BIS central bank policy rates, monthly, end of period; US = mid-point of the target range; "
                                    "'vs Fed' compares the same month",
                           "status": (bis.get("cbpol") or {}).get("status") or "error"}
    d2, ft = pairs(fred.get("DGS2")), pairs(fred.get("DFEDTARU"))
    gap = r(d2[-1][1] - asof(ft, d2[-1][0]), 2) if d2 and ft and asof(ft, d2[-1][0]) is not None else None
    out["us2y_vs_funds"] = {"dgs2": r(d2[-1][1], 2) if d2 else None, "dgs2_asof": d2[-1][0] if d2 else None,
                            "fed_upper": r(ft[-1][1], 2) if ft else None, "fed_upper_asof": ft[-1][0] if ft else None, "gap_pp": gap,
                            "reading": None if gap is None else ("2-year above the funds-rate ceiling: the curve prices a higher policy path "
                                                                 "(or a term premium)" if gap > 0 else "2-year at or below the funds-rate ceiling"),
                            "status": worst([(fred.get("DGS2") or {}).get("status"), (fred.get("DFEDTARU") or {}).get("status")])}
    y10, tp10 = pairs(fred.get("DGS10")), pairs(fred.get("THREEFYTP10"))
    cus = [(d, v / 1000) for d, v in pairs(fred.get("WMTSECL1"))]
    ev = REF.get("events") or {}
    out["treasury"] = {
        "y10": reading(y10, "%", (fred.get("DGS10") or {}).get("src"), "10-year Treasury yield", (fred.get("DGS10") or {}).get("status") or "error", 2),
        "y10_chg_6m_pp": chg_abs(y10, 6),
        "term_premium": reading(tp10, "pp", (fred.get("THREEFYTP10") or {}).get("src"), "Kim-Wright 10-year term premium",
                                (fred.get("THREEFYTP10") or {}).get("status") or "error", 2),
        "custody": {**reading(cus, "$bn", (fred.get("WMTSECL1") or {}).get("src"),
                              "Treasuries held at the New York Fed for foreign official accounts (weekly)",
                              (fred.get("WMTSECL1") or {}).get("status") or "error", 1, pct_since=add_months(cus[-1][0], -120) if cus else None),
                    "chg_12m_pct": chg_pct(cus, 12)},
        "april_2025": ev.get("treasury_2025"), "chain_2022": ev.get("chain_2022")}
    out["status"] = worst([out["usd_credit"].get("status"), out["fx_swaps"].get("status"), out["policy_rates"]["status"],
                           out["us2y_vs_funds"]["status"], out["treasury"]["y10"]["status"]])
    return out


# ---------------------------------------------------------------------------- the ledger view
def ledger_block(inp: dict, state: dict, today: str, path: str) -> dict:
    """Frozen in-sample rows + live forward rows. Live outcomes are measured from the first S&P close after a firing
    became observable (the H.10 release for the rule; the month's end for momentum) and frozen into the row at maturity."""
    fred = inp.get("fred") or {}
    spx, baa, broad = pairs(fred.get("SP500")), pairs(fred.get("BAA10Y")), pairs(fred.get("DTWEXBGS"))
    last_day = min([p[-1][0] for p in (spx, baa, broad) if p] or [today])
    mom = state["momentum"]
    mon = state["dxy"]["monthly"]
    avg = dict(zip(mon["months"], mon["avg"]))
    new = []
    sig = mom.get("signal_months") or []
    for m in sig:
        if m <= LAST_FROZEN_MONTH:
            continue
        prev = [x for x in sig if x < m]
        gap = (int(m[:4]) - int(prev[-1][:4])) * 12 + int(m[5:7]) - int(prev[-1][5:7]) if prev else 99
        if gap > 12:
            p = add_months(m + "-01", -12)[:7]
            new.append({"kind": "momentum", "date": m, "dxy_12m_pct": r(100 * (avg[m] / avg[p] - 1), 1) if avg.get(m) and avg.get(p) else None,
                        "dxy": avg.get(m)})
    write_problems = []
    if new:
        w = append_ledger(path, new, today)
        if w.get("_write_failed"):
            write_problems.append(f"momentum row not saved: {w['_write_failed']}")

    def anchor(e) -> str | None:
        """first S&P close after the later of (a) the day the firing became public (the H.10 release; a momentum
        month's end) and (b) the day the panel recorded it: outcomes the panel could not have captured are never scored."""
        if e.get("kind") == "scramble_rule":
            public = e.get("h10_release") or h10_release(e["date"])
        else:
            public = add_months(e["date"] + "-01", 1)[:7] + "-00"
        d, _ = first_after(spx, max(public, e.get("recorded_on") or ""))
        return d

    def compute(e, last):
        return forward_outcomes(anchor(e), spx, baa, broad, last)

    led = freeze_matured(path, compute, last_day, today) if spx else load_ledger(path)
    if led.get("_write_failed"):
        write_problems.append(f"matured outcomes not saved: {led['_write_failed']}")
    live = []
    for e in led.get("entries", []):
        if not isinstance(e.get("date"), str):
            continue
        frozen = e.get("outcomes_frozen") or {}
        live.append({**e, "anchor_close": anchor(e), "outcomes": {h: frozen.get(h) for h in ("3m", "6m", "12m")}})
    status = "error" if led.get("_unreadable") or write_problems else "ok"
    return {"frozen_momentum": REF.get("momentum_ledger"), "frozen_momentum_basis": REF.get("momentum_ledger_basis"),
            "frozen_rule": [{k: f.get(k) for k in ("date", "reading", "outcomes", "dollar_further_rise_pct", "spx_to_next_low_pct",
                                                    "observable_on", "spx_to_next_low_from_observable_pct", "spx_firing_to_observable_pct")}
                            for f in (REF.get("scramble_rule") or {}).get("firings") or []],
            "live": live, "frozen_on": FROZEN_ON, "cutoff_rule": LAST_INDEX_DAY, "cutoff_momentum": LAST_FROZEN_MONTH,
            "outcomes_through": last_day, "emfx_withheld": REF.get("emfx_withheld"),
            "basis": "frozen rows are in-sample reconstructions; live rows are appended the day the panel first sees a firing after the "
                     "reference cut-off and are never edited; each horizon (3, 6, 12 months: S&P 500, Baa minus 10-year, broad dollar) "
                     "is frozen into the row when it matures; at realistic edges the record needs decades to score",
            "status": status, "problem": "; ".join(write_problems) or ("ledger file unreadable or wrongly shaped" if led.get("_unreadable") else None)}


# ---------------------------------------------------------------------------- assembly
def headline(state: dict, fund: dict, scr: dict, slow: dict) -> str:
    dx = state["dxy"]
    parts = []
    if dx.get("latest") is not None:
        when = f"{dx['asof']}{', intraday' if dx.get('intraday') else ''}"
        pr = f"; {_ord(dx['pct_own_history'])} percentile of month-end closes since 1971" if dx.get("pct_own_history") is not None else ""
        parts.append(f"DXY {dx['latest']:.1f} ({when}), {dx['band_position']}{pr}")
    b = state["broad"]["broad"]
    if b.get("latest") is not None:
        c6 = b.get("chg_6m_pct")
        parts.append(f"broad dollar {b['latest']:.1f} ({b['asof']}){'' if c6 is None else f', {c6:+.1f}% in 6 months'}")
    rows = {x["id"]: x for x in fund["rows"]}
    cp, sw = rows["cp_fin"], rows["swap_lines"]
    if cp.get("latest") is not None:
        pr = "" if cp.get("pct_own_history") is None else f" ({_ord(cp['pct_own_history'])} percentile of its history since {(cp.get('history_from') or '')[:4]})"
        parts.append(f"financial CP minus bill {cp['latest']:.2f}pp{pr}")
    if sw.get("latest") is not None:
        parts.append(f"swap lines ${sw['latest']:.2f}bn")
    st = scr.get("state")
    if st:
        if st["gate_open"]:
            parts.append(f"scramble gauge open: largest 20-day climb {st['roc20_max_60d_pct']:+.1f}% ({st['roc20_max_date']}) with the 10-year falling")
        else:
            parts.append(f"scramble gauge closed: largest 20-day climb in 60 index days {st['roc20_max_60d_pct']:+.1f}% "
                         "(it opens at +4% with the 10-year falling)")
    uc = slow.get("usd_credit") or {}
    if uc.get("total_tn") is not None:
        yy = "" if uc.get("yoy_pct") is None else f", {uc['yoy_pct']:+.1f}% yoy"
        parts.append(f"dollar credit outside the US ${uc['total_tn']:.2f}tn{yy} ({uc.get('quarter')})")
    if not parts:
        return "Live data unavailable (no source answered); the frozen historical record below still applies."
    return "; ".join(parts) + "."


def build_dollar_watch(inp: dict, today: str | None = None, ledger_file: str | None = None) -> dict:
    if REF_ERROR:
        raise RuntimeError(f"dollar reference unavailable: {REF_ERROR}")
    today = today or datetime.now(timezone.utc).date().isoformat()
    path = ledger_file or ledger_path()
    state = state_block(inp)
    fund = funding_block(inp)
    state["safe_haven"]["gold"]["note"] = gold_funding_note(state, fund)
    scr = scramble_block(inp, fund, today, path)
    slow = slow_block(inp)
    led = ledger_block(inp, state, today, path)
    if scr.get("ledger_status") not in (None, "ok"):          # the rule's append failed or found the file unreadable
        led["status"] = "error"
        why = f"scramble-rule rows not saved: {scr['ledger_problem']}" if scr.get("ledger_problem") else f"scramble-rule rows: {scr['ledger_status']}"
        led["problem"] = "; ".join(x for x in (led.get("problem"), why) if x)
    blocks = {"state": state["status"], "funding": fund["status"], "scramble": scr["status"], "slow": slow["status"], "ledger": led["status"]}
    return {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "frozen_on": FROZEN_ON, "mode": "descriptive",
            "status": {"overall": worst(blocks.values()), "blocks": blocks},
            "headline": headline(state, fund, scr, slow),
            "state": state, "funding": fund, "scramble": scr, "slow": slow, "ledger": led,
            "crisis_lists": REF.get("crisis_lists"), "window_convention": REF.get("window_convention"),
            "provenance": {k: (REF.get("provenance") or {}).get(k) for k in ("study", "builder", "reviews")},
            "pending_questions": [dict(q, status="asked", first_asked="2026-11-02", expires=EXPIRES) if "status" not in q else
                                  dict(q, first_asked=None, expires=None) for q in PENDING],
            "honesty": list(REF.get("honesty") or []) + HONESTY_LIVE + ([REF["emfx_withheld"] + "."] if REF.get("emfx_withheld") else [])}
