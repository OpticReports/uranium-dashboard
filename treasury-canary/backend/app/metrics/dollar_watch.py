"""Dollar watch tab (studies/dollar-watch.md §5, §9): assembles GET /dollar-watch.

DESCRIPTIVE ONLY. No odds, no colour-coded states, no crisis calls: every
historical number is in-sample and comes from the frozen reference
(sources/dollar_reference.json, rebuilt by studies/dollar_watch/code/
build_reference.py); every conditional count carries its N and base rate. The
pre-registration (studies/dollar_watch/spec/SPEC_v1.md, forward only) is frozen
in sources/dollar_freeze.json; this module records, point in time, what its
offline harness (studies/dollar_watch/prereg/d3.py) will need (memo §9.4).

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
  forward   the pre-registration's point-in-time duties: D-3 eligibility and units,
            the placebo rule, archived inputs, maturity blocks, one onset row per
            month at its close, revision checks.

sources/dollar_data.fetch_all() fetches; build_dollar_watch(inputs, today=...,
ledger_file=...) assembles (pure apart from the ledger file, injectable).
"""
from __future__ import annotations

import bisect
import gzip
import hashlib
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

HONESTY_LIVE = [
    "Descriptive panel: readings and counts only, each conditional count with its N and base rate; nothing here is a forecast or a crisis call.",
    "Live readings use today's data vintage; the broad dollar (H.10) is published weekly, so it can lag the DXY by up to two weeks. "
    "A reading dated today is intraday until the session ends.",
    "2026 (as of 2026-11-02) sits outside every pattern in this study: gold fell 27-31% from its January high with the dollar up under 6% and no "
    "dollar-funding stress, Brent nearly doubled, and foreign official custody is at a 14-year low. The dollar-funding mechanism "
    "does not explain it; do not read the crisis records on this page onto it.",
    "PREREG",                                                     # replaced at build time by prereg_line()
    "Live ledger rows are measured from the first S&P close after the release that made a firing visible (the H.10 release; a momentum "
    "month's end), never from the firing day. The historical rows are in-sample and measured from the data date (momentum: monthly "
    "averages, EM FX as of the 28th).",
]

PENDING = [   # status per CLAUDE.md: asked / answered / refused / expired; "open" = ours to source, not a question to Casey
    {"rank": "P1", "q": "Which crisis list is the primary?", "moves": "every base rate on the panel",
     "status": "answered", "answered_on": "2026-11-02", "answer": "C16 (16 dollar-stress onsets); A25 and N5 shown beside it"},
    {"rank": "P1", "q": "Route after both reviews of SPEC v0 returned NOT_PASS?", "moves": "whether anything is scored before the 2060s",
     "status": "answered", "answered_on": "2026-11-02", "answer": "forward only: the dated ledger; the cross-section is withdrawn"},
    {"rank": "P1", "q": "Primary deceleration variant?", "moves": "the ledger's primary record",
     "status": "answered", "answered_on": "2026-11-02", "answer": "unpatched; re-arm logged alongside (descriptive)"},
    {"rank": "P1", "q": "How are future crises dated for the ledger?", "moves": "how forward firings are scored",
     "status": "answered", "answered_on": "2026-11-02",
     "answer": "2 of 5 mechanical markers (VIX at or above 40; OFR FSI above its 5-year 95th percentile for 5 days; EM FX basket +10% in 63 "
               "days; S&P -20% from its 252-day high; a Fed emergency action); 8 onsets on 2000-2026, inside the pre-committed 3-13"},
    {"rank": "P2", "q": "May a live notification on the gauge ever come from anything but the forward ledger?", "moves": "the notification licence",
     "status": "answered", "answered_on": "2026-11-02", "answer": "no: only a forward-test PASS"},
    {"rank": "P1", "q": "Keep the drift bracket in the forward test as frozen (a PASS judged as if the dollar drifted -1% a year, a FAIL "
                        "as if +1%)? Without it a -1%/yr trend roughly doubles the false-PASS rate; with it, power at a +0.20 edge falls "
                        "from 0.43 to 0.24 in calm markets (0.44 either way in volatile ones) and a record with no edge most likely ends "
                        "undecided. It does not cover a volatility-regime shift (2016-26 volatility plus -1%/yr: false PASS about 0.07); "
                        "the stronger option (also bracketing volatility) brings that to about 0.04 but cuts power at +0.20 from about "
                        "0.39 to 0.26. In force as the default; any change is post-hoc and needs a new SPEC version.",
     "moves": "how hard a PASS is, and how often the record ends undecided", "first_asked": "2026-11-03",
     "status": "answered", "answered_on": "2026-11-03", "answer": "keep the default: the drift bracket as frozen"},
    {"rank": "P2", "q": "Accept the redesigned forward test (a no-information GARCH-t null; looks at 8 / 16 / 24 matured units with alpha "
                        "spent 0.005 / 0.020 / 0.050; a placebo rule without the deceleration clause scored beside it, never changing "
                        "the wording; a PASS reads 'beat a no-information model', deceleration-specific: not tested)? In force as the "
                        "default.",
     "moves": "what a PASS or FAIL means decades from now"},
    {"rank": "P2", "q": "Keep the onset rule's 12-month exclusion from the last onset (a long crisis re-dates itself at month 13, as 2009-01 "
                        "did after 2007-12)? In force as the default; any change is post-hoc and needs a new SPEC version.",
     "moves": "how long crises are dated in the ledger (descriptive outcomes only)"},
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
def scramble_firings(dates, B, Y, rearm=True, p=RULE, decel=True):
    """The frozen deceleration rule, line for line as build_reference.py / decel_realtime.py
    (the live version also evaluates the latest index day). Returns firing dicts with index k.
    decel=False is SPEC v1's placebo (stats review v1 S2): the same rule without the deceleration clause, so it
    fires on the first day of a >= 4% climb near the high with the 10-year falling (unpatched only)."""
    n = len(B)
    roc = [None] * n
    for k in range(p["roc_days"], n):
        roc[k] = B[k] / B[k - p["roc_days"]] - 1
    fires, last, last_mx = [], -10 ** 9, 0.0
    for k in range(p["first_eval_index"], n):
        w = [(roc[j], j) for j in range(k - p["window_days"], k + 1) if roc[j] is not None]
        mx = max(v for v, _ in w)
        kmx = min(j for v, j in w if v == mx)
        if (mx >= p["min_max_roc"] and (not decel or roc[k] <= p["decel_ratio"] * mx)
                and B[k] >= p["near_high"] * max(B[k - p["window_days"]:k + 1])
                and Y[k] < Y[max(0, kmx - p["yield_lookback_days"])]
                and (k - last > p["cooling_days"] or (rearm and mx >= p["rearm_multiple"] * last_mx))):
            fires.append({"date": dates[k], "k": k, "roc20_max_pct": r(100 * mx, 1), "roc20_max_date": dates[kmx],
                          "roc20_now_pct": r(100 * roc[k], 1), "dollar": r(B[k], 2)})
            last, last_mx = k, mx
    return fires


FORWARD_CALENDAR = ("days with DTWEXBGS and DGS10 both published (SPEC v1 §2, stats review v1 S3); the in-sample record used the "
                    "frozen script's calendar, which also required VIXCLS: the two differ on 7 Good Fridays in 2006-2026 and give "
                    "identical firings")


def rule_index(fred: dict):
    """(dates, B, Y) on days with DTWEXBGS and DGS10 both published: the live rule's and D-3's calendar (FORWARD_CALENDAR)."""
    b, y = (dict(pairs(fred.get(s))) for s in ("DTWEXBGS", "DGS10"))
    ds = sorted(d for d in b if d in y)
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


LEDGER_VIEW_KINDS = ("scramble_rule", "momentum")      # the rows the ledger table shows and scores; the others are SPEC v1 bookkeeping


def freeze_matured(path: str, compute, last_day: str, today: str) -> dict:
    """Write each matured horizon's outcome into its row, field by field, once (data review v1 M4: a missing
    component waits on its own and never holds the others back; a value is never changed after it is written)."""
    with _LEDGER_LOCK:
        led = load_ledger(path)
        if led.get("_unreadable") or not led["entries"]:
            return led
        changed = False
        for e in led["entries"]:
            if e.get("kind") not in LEDGER_VIEW_KINDS:
                continue
            for h, o in compute(e, last_day).items():
                if o is None:
                    continue
                cur = (e.get("outcomes_frozen") or {}).get(h)
                add = {k: v for k, v in o.items() if v is not None and (cur is None or k not in cur)}
                if not add:
                    continue
                done = e.setdefault("outcomes_frozen", {})
                if cur is None:
                    done[h] = dict(add, frozen_on=today)
                else:
                    cur.update(add)
                    cur.setdefault("late_fields", {}).update({k: today for k in add})
                changed = True
        return _write_ledger(path, led) if changed else led


# ---------------------------------------------------------------------------- outcome helpers
def _bdays_between(a: str, b: str) -> int:
    """business days after a up to and including b (weekdays that are not US federal holidays)."""
    d, e, n = date.fromisoformat(a), date.fromisoformat(b), 0
    while d < e:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in us_federal_holidays(d.year):
            n += 1
    return n


def emfx_stale(fred: dict) -> str | None:
    """Why the EM basket is withheld, or None: a missing leg, or a leg whose last observation is more than 10 business
    days behind the newest leg (a stopped leg would otherwise be carried flat into every outcome; data review v1 M4)."""
    last = {s: pairs(fred.get(s))[-1][0] for s in EMFX_IDS if pairs(fred.get(s))}
    if len(last) < len(EMFX_IDS):
        return "missing leg(s): " + ", ".join(s for s in EMFX_IDS if s not in last)
    newest = max(last.values())
    behind = [s for s in EMFX_IDS if _bdays_between(last[s], newest) > 10]
    return (", ".join(f"{s} ends {last[s]}" for s in behind) + f", more than 10 business days behind {newest}") if behind else None


def emfx_basket(fred: dict) -> tuple[list[tuple[str, float]], str | None]:
    """Equal-weight log-average of the 8 FRED EM pairs (EM currency per dollar; up = EM weaker), rebased so the average
    of its first month from 2006 on (Jan-2006 on the full FRED history) = 100. Returns (series, base month); empty
    when a leg is missing or stale (emfx_stale)."""
    legs = {s: pairs(fred.get(s)) for s in EMFX_IDS}
    why = emfx_stale(fred)
    if why:
        if all(legs.values()):
            logger.warning("EM FX basket withheld: %s", why)
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


def forward_outcomes(anchor: str | None, spx, emfx, baa, broad, last_day: str) -> dict:
    """S&P, EM FX basket, Baa-10y and broad-dollar changes 3/6/12 calendar months after `anchor` (an S&P close date)."""
    o = {}
    if not anchor:
        return {f"{k}m": None for k in (3, 6, 12)}
    s0, e0, b0, d0 = asof(spx, anchor), asof(emfx, anchor), asof(baa, anchor), asof(broad, anchor)
    for k in (3, 6, 12):
        dk = add_months(anchor, k)
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
    showing no sign of a squeeze by the same test as the summaries (_funding_word 'quiet' or 'usual': the CP spread's 5-day
    average under 1pp and no funding price gauge at its 80th own-history percentile or higher; wording re-check 2026-11-03)."""
    g = state["safe_haven"]["gold"]
    off = g.get("off_52w_high_pct")
    if off is None or off > -15 or _funding_word({x["id"]: x for x in fund["rows"]}) not in ("quiet", "usual"):
        return None
    return ("with no sign of a dollar-funding squeeze (the CP spread's 5-day average under 1pp, it and the OFR funding index under "
            "their 80th percentiles): outside the crisis pattern below")


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
    em_why = emfx_stale(fred)
    if em_why and all(pairs(fred.get(s)) for s in EMFX_IDS):
        issues.append(f"the EM FX basket is withheld: {em_why}")
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
    c5 = r(sum(v for _, v in cpf[-5:]) / 5, 2) if len(cpf) >= 5 else None              # SPEC v1 §5.3's dollar-funding line is on this
    rows[0].update(mean_5d=c5, pct_5d_own_history=r(100 * sum(1 for _, v in cpf if v <= c5) / len(cpf), 0) if c5 is not None else None)
    wk4 = (date.fromisoformat(swpt[-1][0]) - timedelta(days=28)).isoformat() if swpt else None
    next(x for x in rows if x["id"] == "swap_lines")["prev_4w"] = r(asof(swpt, wk4), 2) if wk4 else None   # is the stock falling?
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
           "variant_live": "both variants run and logged; unpatched is the frozen primary (re-arm was added after the 2008-09-22 "
                           "miss and stays descriptive)",
           "vspike_timing": ref.get("vspike_timing"), "monthly_null": ref.get("monthly_null"), "end_of_scramble": REF.get("end_of_scramble"),
           "basis": ref.get("basis"), "wording": SCRAMBLE_WORDS, "last_index_day": LAST_INDEX_DAY, "calendar": FORWARD_CALENDAR,
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
    placebo = {f["date"]: {"kind": "placebo_rule", "date": f["date"], "variants": ["unpatched"], "h10_release": h10_release(f["date"]),
                           **{x: f[x] for x in ("roc20_max_pct", "roc20_max_date", "roc20_now_pct", "dollar")}}
               for f in scramble_firings(ds, B, Y, False, decel=False) if f["date"] > LAST_INDEX_DAY}
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
    prev = _rule_state(path).get("last_index_day") or _seed_index_day()
    b_last = (pairs(fred.get("DTWEXBGS")) or [(ds[-1], None)])[-1][0]
    rows = (enrich_firings(new, ds, B, Y, path, prev, b_last=b_last) if new else []) + \
        (enrich_firings(placebo, ds, B, Y, path, prev, kind="placebo_rule", b_last=b_last) if placebo else [])
    led = append_ledger(path, rows, today) if rows else load_ledger(path)
    if not led.get("_unreadable") and not led.get("_write_failed"):
        # only once this vintage's rows are saved (an unsaved firing must still read as first-vintage next build),
        # and never backwards (an older cached vintage must not re-open days already seen)
        _save_rule_state(path, {"last_index_day": max(prev or "", ds[-1]), "saved_on": today})
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
    em, _ = emfx_basket(fred)
    last_day = min([p[-1][0] for p in (spx, em, baa, broad) if p] or [today])
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
        return forward_outcomes(anchor(e), spx, em, baa, broad, last)

    led = freeze_matured(path, compute, last_day, today) if spx else load_ledger(path)
    if led.get("_write_failed"):
        write_problems.append(f"matured outcomes not saved: {led['_write_failed']}")
    live = []
    for e in led.get("entries", []):
        if not isinstance(e.get("date"), str) or e.get("kind") not in LEDGER_VIEW_KINDS:
            continue
        frozen = e.get("outcomes_frozen") or {}
        live.append({**e, "anchor_close": anchor(e), "outcomes": {h: frozen.get(h) for h in ("3m", "6m", "12m")}})
    status = "error" if led.get("_unreadable") or write_problems else "ok"
    return {"frozen_momentum": REF.get("momentum_ledger"), "frozen_momentum_basis": REF.get("momentum_ledger_basis"),
            "frozen_rule": [{k: f.get(k) for k in ("date", "reading", "outcomes", "dollar_further_rise_pct", "spx_to_next_low_pct",
                                                    "observable_on", "spx_to_next_low_from_observable_pct", "spx_firing_to_observable_pct")}
                            for f in (REF.get("scramble_rule") or {}).get("firings") or []],
            "live": live, "frozen_on": FROZEN_ON, "cutoff_rule": LAST_INDEX_DAY, "cutoff_momentum": LAST_FROZEN_MONTH,
            "outcomes_through": last_day,
            "basis": "frozen rows are in-sample reconstructions; live rows are appended the day the panel first sees a firing after the "
                     "reference cut-off and are never edited; each horizon (3, 6, 12 months: S&P 500, EM FX basket, Baa minus 10-year, broad dollar) "
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


# ---------------------------------------------------------------------------- plain-language summaries (Casey, 2026-11-03)
def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _sp(x, d=1, u="%") -> str:
    return f"{x:+.{d}f}{u}"


def _level(pct) -> str:
    """where a reading sits against its own history, in words."""
    return ("high" if pct >= 80 else "firm" if pct >= 60 else "middling" if pct >= 40 else "soft" if pct >= 20 else "low") + " against its history"


ELEVATED_PCT = 80      # own-history percentile at or above which a funding gauge reads "elevated" (wording re-check 2026-11-03)


def _funding_elevated(rows: dict) -> list[tuple[str, float]]:
    """(name, percentile) of the price gauges at or above ELEVATED_PCT of their own history: CP on its 5-day average, the OFR
    funding index on its latest value."""
    cp, of = rows.get("cp_fin") or {}, rows.get("ofr_funding") or {}
    out = []
    if _num(cp.get("pct_5d_own_history")) and cp["pct_5d_own_history"] >= ELEVATED_PCT:
        out.append(("the CP spread's 5-day average", cp["pct_5d_own_history"]))
    if _num(of.get("pct_own_history")) and of["pct_own_history"] >= ELEVATED_PCT:
        out.append(("the OFR funding index", of["pct_own_history"]))
    return out


def _funding_word(rows: dict) -> str | None:
    """Dollar funding in one word, shared by the summaries and the gold tile's note (wording review and re-check, 2026-11-03).
    'strained' = the CP spread's 5-day average above 1pp (SPEC v1 §5.3's line; the 5-day average moves a fifth per print);
    'elevated' = below that line, but CP's 5-day average or the OFR funding index at or above the 80th percentile of its own
    history (the 1-year medians alone read 'quiet' in early 2009, when they were crisis medians); 'quiet' = both at or below their
    1-year medians; 'usual' = the rest, the common state (about three days in five since 2020); None = not enough data. Swap-line
    usage is a lagging stock and never sets the word."""
    cp, of = rows.get("cp_fin") or {}, rows.get("ofr_funding") or {}
    c5 = cp.get("mean_5d")
    if _num(c5) and c5 > 1.0:
        return "strained"
    if _funding_elevated(rows):
        return "elevated"
    if not all(_num(v) for v in (c5, cp.get("median_1y"), of.get("latest"), of.get("median_1y"))):
        return None
    return "quiet" if c5 <= cp["median_1y"] and of["latest"] <= of["median_1y"] else "usual"


def _span(d: dict) -> str:
    a, b = str(d.get("peak") or "")[:7], str(d.get("trough") or "")[:7]
    return a if a == b or not b else f"{a} to {b}"


def summaries(state: dict, fund: dict, scr: dict, slow: dict, led: dict, fwd: dict) -> dict:
    """'What this means', layer by layer, from today's readings: each set against its own history or an in-sample base rate,
    and each saying what it does not tell you. Descriptive only: no forecast, no crisis call. Every number is one the panel
    already shows; a missing input drops its sentence rather than printing a hole."""
    out: dict[str, list[str]] = {}
    rows = {r.get("id"): r for r in (fund.get("rows") or []) if _num(r.get("latest"))}      # gauges with a reading today
    cp, sw = rows.get("cp_fin") or {}, rows.get("swap_lines") or {}
    ranked = [r for r in rows.values() if _num(r.get("pct_own_history"))]                     # EMB carries no percentile
    hot = [r for r in ranked if r["pct_own_history"] >= 90]
    word = _funding_word(rows)
    c5 = cp.get("mean_5d")
    swap_big = _num(sw.get("latest")) and sw["latest"] > 50
    swap_falling = swap_big and _num(sw.get("prev_4w")) and sw["latest"] < sw["prev_4w"]
    swap_tail = swap_falling and word in ("quiet", "usual")              # a lagging stock running off, with calm prices
    swap_new = swap_big and not swap_falling and word not in ("strained", None)   # still being drawn: demand CP prices need not show
    swap_dir = "rising" if swap_new and _num(sw.get("prev_4w")) and sw["latest"] > sw["prev_4w"] else "not falling"
    ons = fwd.get("onsets") or {}
    st = scr.get("state") or {}
    fz = (fwd.get("freeze") or {}).get("freeze_date")
    fz = fz if isinstance(fz, str) and fz[:4].isdigit() else None

    # layer 1: the dollar against its own history
    L = []
    dx = state.get("dxy") or {}
    if _num(dx.get("latest")) and _num(dx.get("pct_own_history")):
        tail = (f"; {_sp(dx['chg_6m_pct'])} over 6 months and {_sp(dx['chg_12m_pct'])} over 12 (daily closes)"
                if _num(dx.get("chg_6m_pct")) and _num(dx.get("chg_12m_pct")) else "")
        L.append(f"The dollar is {_level(dx['pct_own_history'])}: the ICE DXY at {dx['latest']:.1f} is at the {_ord(dx['pct_own_history'])} "
                 f"percentile of month-end closes since 1971, {dx.get('band_position') or 'band position n/a'}{tail}.")
    q = state.get("quadrant") or {}
    on, base = q.get("onsets_C16") or {}, (q.get("base_all_months") or {}).get("shares") or {}
    k = q.get("quadrant")
    if k and _num((on.get("counts") or {}).get(k)) and _num(base.get(k)):
        sig_n, sig_b = (on.get("counts") or {}).get("usd_up_yld_down"), base.get("usd_up_yld_down")
        tail = (": the quadrant most onsets began in, a description of onset months as they happen rather than a forecast" if k == "usd_up_yld_down" else
                f"; the study's onset pattern is the dollar up with the 10-year falling ({sig_n} of {on.get('n')} onsets vs "
                f"{round(100 * sig_b)}% of months), which is not today's" if _num(sig_n) and _num(sig_b) else "")
        L.append(f"Over the 3 months to {q.get('month')}: {q.get('label')}. In-sample, {on['counts'][k]} of {on.get('n')} dollar-stress "
                 f"onsets (C16) began in this quadrant, against {round(100 * base[k])}% of all months{tail}.")
    mom = state.get("momentum") or {}
    if _num(mom.get("dxy_12m_pct")):
        m12 = mom["dxy_12m_pct"]
        head = f"12-month momentum (monthly averages, to {mom.get('month') or 'n/a'}) is {_sp(m12)}"
        c = (mom.get("by_list") or {}).get("C16") or {}
        began = mom.get("episodes_began_in_a25_crisis", (REF.get("momentum") or {}).get("episodes_began_in_a25_crisis"))
        if mom.get("signal") and all(_num(c.get(f)) for f in ("episodes_followed_12m", "episodes", "base_12m")):
            L.append(f"{head}, above the +10% line: in-sample, {c['episodes_followed_12m']} of {c['episodes']} such episodes were followed "
                     f"by a C16 onset within 12 months, against {round(100 * c['base_12m'])}% of all months"
                     + (f"; {began} of the {c['episodes']} began during a crisis already under way" if _num(began) else "")
                     + "; the edge depends on the crisis list and is not validated.")
        elif mom.get("signal"):
            L.append(f"{head}, above the +10% line the study watches; its in-sample record is unavailable.")
        elif m12 >= 10:                                   # rounded to 1 dp upstream: +10.0% with the signal off is just short
            L.append(f"{head}, just short of the line the study watches (it needs more than +10%).")
        else:
            L.append(f"{head}, below the +10% line the study watches"
                     + (f" (last above it in {mom['last_signal_month']})" if mom.get("last_signal_month") else "") + ".")
    sh = state.get("safe_haven") or {}
    g = sh.get("gold") or {}
    if _num(g.get("off_52w_high_pct")):
        off = g["off_52w_high_pct"]
        where = f"{abs(off):.1f}% below its 52-week high" if off < 0 else "at its 52-week high"
        dfo = [str(o) for o in (ons.get("historical_dollar_funding") or [])]
        dd = [d for d in ((sh.get("gold_record") or {}).get("drawdowns") or []) if _num(d.get("close_pct"))
              and any(o <= str(d.get("peak"))[:7] <= add_months(o + "-01", 12)[:7] for o in dfo)]   # falls begun within a year of a dollar-funding onset
        if g.get("note") and word in ("quiet", "usual") and dd:     # the tile's own test, the same word as the funding headline
            yrs = " and ".join(sorted({str(d.get("peak"))[:4] for d in dd}))
            ex = "; ".join(f"{d.get('episode')} {d['close_pct']:.0f}%, {_span(d)}" for d in dd)
            L.append(f"Gold is {where} with no sign of a dollar-funding squeeze. In the {yrs} dollar-funding squeezes gold fell before "
                     f"recovering ({ex}; close to close), so a fall without one does not fit that pattern.")
        else:
            L.append(f"Gold is {where}.")
    L.append("What it tells you: where the dollar sits against its own history. None of these readings has been validated as an early sign "
             "of crisis: the band showed no edge, momentum's in-sample edge depends on the crisis list, and the quadrant describes onset "
             "months as they happen. Read them as context.")
    out["state"] = L

    # layer 2: the plumbing
    F = []
    if _num(cp.get("latest")) and _num(sw.get("latest")):
        els = _funding_elevated(rows)
        el = (f"{els[0][0]} is at the {_ord(els[0][1])} percentile of its own history"
              + (f" and {els[1][0]} at the {_ord(els[1][1])}" if len(els) > 1 else "")) if els else ""
        adj = {"strained": "under strain on the crisis dating's own line (the CP spread's 5-day average above 1pp)",
               "elevated": f"elevated: under the crisis dating's 1pp line, but {el}",
               "quiet": "quiet (the CP spread's 5-day average and the OFR funding index at or below their 1-year medians)",
               "usual": "in its usual range (the CP spread's 5-day average or the OFR funding index above its 1-year median, "
                        "as on about three days in five since 2020)"}.get(word or "")
        pc = f" ({_ord(cp['pct_own_history'])} percentile since {(cp.get('history_from') or '')[:4]})" if _num(cp.get("pct_own_history")) else ""
        F.append((f"Dollar funding is {adj}. " if adj else "") + f"Financial commercial paper costs {cp['latest']:.2f}pp over Treasury "
                 f"bills{pc} and foreign central banks owe ${sw['latest']:.2f}bn on the Fed's swap lines.")
        hist, dfl = ons.get("historical") or [], ons.get("historical_dollar_funding") or []
        rec = f" ({len(dfl)} of the {len(hist)} onsets dated 2000-2026 were: {', '.join(dfl)})" if hist and dfl else ""
        past = (["the 1pp line"] if _num(c5) and c5 > 1.0 else []) + (["the $50bn line"] if sw["latest"] > 50 else [])
        F.append(f"The crisis dating calls an onset dollar-funding when the CP spread's 5-day average passes 1pp or swap lines pass $50bn{rec}. "
                 f"Today: {f'{c5:.2f}pp' if _num(c5) else 'n/a'} and ${sw['latest']:.2f}bn"
                 + (", past both lines." if len(past) == 2 else f", past {past[0]}." if past else ", below both." if _num(c5) else "."))
        if swap_tail:
            F.append(f"Swap-line borrowing is above the $50bn line but falling (${sw['prev_4w']:.0f}bn four weeks earlier). Usage lags "
                     "funding prices: in 2008 and 2020 it peaked about two months after CP minus bills and stayed above $50bn until "
                     "Sep-2009 and Sep-2020, so a falling stock with calm prices reads as the tail of a squeeze rather than new strain.")
        elif swap_new:
            F.append(f"Swap-line borrowing is above the $50bn line and {swap_dir}"
                     + (f" (${sw['prev_4w']:.0f}bn four weeks earlier)" if _num(sw.get("prev_4w")) else "")
                     + ": dollar demand abroad that US funding prices need not show. From Dec-2011 to Feb-2012 euro-area draws rose "
                     "from $2bn to $109bn while the CP spread stayed near its median.")
    if ranked:
        nh = len(hot)
        F.append(f"{nh} of {len(ranked)} gauges with a percentile {'sits' if nh == 1 else 'sit'} at or above the 90th percentile of "
                 f"{'its' if nh == 1 else 'their'} own history (about one in ten would on an ordinary day)"
                 + (": " + ", ".join(f"{r.get('label')} ({_ord(r['pct_own_history'])}, history from {(r.get('history_from') or '')[:4]})"
                                     for r in hot) + "." if hot else "."))
    F.append("What it tells you: whether borrowing dollars is getting harder, the mechanism behind a dollar scramble. In 2008, 2020 and "
             "2022 these gauges moved with or ahead of the dollar's peak, but their first alarms came roughly with the crisis itself "
             "(n = 2), and they were silent in the 2015-16 and 2018 EM scares: they show strain as it happens, not ahead of time.")
    out["funding"] = F

    # layer 3: the gauge
    S = []
    climb = _sp(st["roc20_max_60d_pct"]) if _num(st.get("roc20_max_60d_pct")) else "n/a"
    if st:
        win = f"the broad dollar's largest 20-day climb in the last 60 index days (about three months) is {climb}"
        if scr.get("gate_open"):
            ind = scr.get("indicators") or {}
            a = ind.get("a_deceleration") or {}
            if a.get("met") is True:
                a_txt = "met: the climb has slowed to half its peak or less with the dollar near its high, the reading a firing needs"
            elif a.get("met") is False and _num(a.get("dollar_vs_60d_high_pct")) and a["dollar_vs_60d_high_pct"] < -3:
                a_txt = (f"not met: the dollar is already {abs(a['dollar_vs_60d_high_pct']):.1f}% below its 60-day high, "
                         "so the climb has reversed")
            elif a.get("met") is False and _num(a.get("ratio_now_to_max")) and a["ratio_now_to_max"] > 0.5:
                a_txt = "not met: the 20-day climb is still above half its peak"
            else:
                a_txt = "not met" if a.get("met") is False else "unknown"
            met = lambda x: "met" if (x or {}).get("met") is True else "not met" if (x or {}).get("met") is False else "unknown"   # noqa: E731
            S.append(f"The scramble gauge is open: {win}, with the 10-year below where it stood before the climb. Deceleration (a) is "
                     f"{a_txt}. Funding easing (b, on the latest print) is {met(ind.get('b_funding_easing'))}, and gold and EM bonds turning (c) "
                     f"{met(ind.get('c_risk_turn'))}; the three are shown separately and never added up.")
        else:
            S.append(f"The scramble gauge is closed: {win} (it opens at +4% with the 10-year falling). No dollar scramble is under way "
                     "on this definition.")
    lf = [e for e in (scr.get("live_firings") or []) if e.get("kind") == "scramble_rule"]
    if lf:
        S.append(f"Live firings since the cut-off: {', '.join(str(e.get('date')) for e in lf)} (logged; the forward test scores only "
                 f"firings dated after the {fz or 'freeze'} freeze under the default rule, as first published).")
    ref = REF.get("scramble_rule") or {}
    unp = set(ref.get("firings_unpatched") or [])
    fr = [f for f in (ref.get("firings") or []) if f.get("date") in unp]
    clean = [f for f in fr if str(f.get("reading", "")).startswith("clean")]
    first = [f for f in fr if str(f.get("reading", "")).startswith("first wave")]
    rest = [f for f in fr if f not in clean and f not in first]
    if clean and first:
        rise = " and ".join(f"{f['dollar_further_rise_pct']:.0f}%" for f in first if _num(f.get("dollar_further_rise_pct")))
        c0 = clean[0].get("dollar_further_rise_pct")
        yrs = sorted({f["date"][:4] for f in rest})
        S.append(f"In-sample, on parameters chosen on the same episodes: {len(fr)} firings since 2006. On the three episodes it was tuned on, "
                 f"it fired near the top once ({', '.join(f['date'][:4] for f in clean)}"
                 + (f", the dollar only {c0:.1f}% higher afterwards" if _num(c0) else "") + ") and on the first wave twice "
                 f"({', '.join(f['date'][:4] for f in first)})"
                 + (f", after which the dollar rose another {rise}" if rise else "")
                 + (f"; the other {len(rest)} came on {'euro-crisis' if all('euro-crisis' in str(f.get('reading')) for f in rest) else 'other'} "
                    f"dollar spikes ({yrs[0]}-{yrs[-1][2:]})" if rest else "")
                 + ". On 1973-2005 monthly data it showed no edge.")
    S.append("A firing would read 'dollar scramble peaking': it is about the top of a dollar scramble and says nothing about the crisis itself.")
    out["scramble"] = S

    # layer 4: the backdrop
    W = []
    uc = slow.get("usd_credit") or {}
    if _num(uc.get("total_tn")) and _num(uc.get("yoy_pct")):
        W.append(f"Dollar credit to non-bank borrowers outside the US is ${uc['total_tn']:.2f}tn, {_sp(uc['yoy_pct'])} a year ({uc.get('quarter')}). "
                 + ("It has set records in calm years and before crises alike, so it sizes the backdrop rather than timing anything."
                    if uc["yoy_pct"] >= 0 else "That is a contraction; from 2001 to 2026 the only ones were 2009Q1-Q3 and 2022Q3-2023Q4."))
    t = slow.get("treasury") or {}
    cu, y = t.get("custody") or {}, t.get("y10") or {}
    if _num(cu.get("latest")) and _num(cu.get("chg_12m_pct")):
        pc = f", the {_ord(cu['pct_10y'])} percentile of the last 10 years" if _num(cu.get("pct_10y")) else ""
        W.append(f"Treasuries the Fed holds in custody for foreign official accounts are ${cu['latest']:,.0f}bn, {_sp(cu['chg_12m_pct'])} over "
                 f"12 months{pc}."
                 + (" A fall can mean official holders selling Treasuries to raise dollars, as in March 2020, or simply custody moving elsewhere."
                    if cu["chg_12m_pct"] < 0 else ""))
    if _num(y.get("latest")):
        pc = (f" ({_ord(y['pct_own_history'])} percentile since {(y.get('history_from') or '')[:4] or 'the series began'})"
              if _num(y.get("pct_own_history")) else "")
        ch = f", {_sp(t['y10_chg_6m_pp'], 2, 'pp')} in 6 months" if _num(t.get("y10_chg_6m_pp")) else ""
        W.append(f"The 10-year yield is {y['latest']:.2f}%{pc}{ch}.")
    W.append("What it tells you: how much dollar debt sits abroad and who holds Treasuries; these move over quarters and describe "
             "the backdrop, not the timing.")
    out["slow"] = W

    # the ledger and the pre-registration
    live = led.get("live") or []
    out["ledger"] = [("No live firing or momentum episode since the cut-off." if not live else
                      f"{len(live)} live row{'s' if len(live) != 1 else ''} since the cut-off, each recorded the day the panel first saw "
                      "it; recorded values are never changed."),
                     "Outcomes are frozen into each row as they mature. At about one scored unit every four to five years, the "
                     "forward test needs decades before it can say anything."]
    d3 = fwd.get("d3") or {}
    P = []
    if fz:
        u = d3.get("units") or 0
        P.append(f"Frozen {fz}: the rule is graded only on firings after that date. {u} unit{'s' if u != 1 else ''} so far (a unit is a "
                 "firing plus its 250-index-day outcome window); the first look comes at 8 matured units, around 2060-2067, and with no "
                 "real edge the most likely end is 'undecided'.")
    if ons:
        nl, nm = ons.get("live") or [], ons.get("next_month")
        nxt = (f" {nm} is dated at its close on {ons.get('next_close') or 'n/a'}, or as late as {onset_deadline(nm)} if an input or "
               "the Fed-list review is still outstanding." if isinstance(nm, str) and len(nm) == 7 else "")
        P.append(f"Crisis months dated since {FIRST_LIVE_MONTH}: {ons.get('months_evaluated', 0)}; onsets among them: "
                 f"{', '.join(str(e.get('date')) for e in nl) if nl else 'none'}.{nxt}")
    P.append("Nothing on this page is coloured as a signal or sends a notification. Only a forward-test PASS could add one neutral "
             "colour on the deceleration reading (3a) and a notification; every other reading stays descriptive under any outcome. "
             "The coloured chips show data health only.")
    out["forward"] = P

    # the page as a whole
    parts = []
    if _num(dx.get("pct_own_history")):
        parts.append(f"the dollar is {_level(dx['pct_own_history'])}")
    if word:
        notes = ([f"{len(hot)} gauge{'s' if len(hot) > 1 else ''} near the top of {'their' if len(hot) > 1 else 'its'} range"] if hot else []) \
            + (["swap-line borrowing above $50bn but falling"] if swap_tail else [f"swap-line borrowing above $50bn and {swap_dir}"] if swap_new else [])
        par = f" ({'; '.join(notes)})" if notes else ""
        parts.append({"strained": "dollar funding is under strain", "elevated": f"funding is elevated{par}", "quiet": f"funding is {'mostly quiet' if hot else 'quiet'}{par}",
                      "usual": f"funding is in its usual range{par}"}[word])
    if st:
        parts.append("the scramble gauge is open" if scr.get("gate_open") else "the scramble gauge is closed")
    if _num(uc.get("yoy_pct")):
        parts.append(f"dollar debt abroad is {'growing' if uc['yoy_pct'] > 0 else 'shrinking' if uc['yoy_pct'] < 0 else 'flat'}")
    parts[:1] = [x[:1].upper() + x[1:] for x in parts[:1]]       # the box's own title says "Reading the page together"
    watch = (["the CP spread's 5-day average falling back under 1pp"] if word == "strained" else
             ["funding gauges climbing toward their 2008 and 2020 levels (the CP spread's 5-day average past 1pp)"])
    a_met = ((scr.get("indicators") or {}).get("a_deceleration") or {}).get("met") is True
    if st:
        watch.append(("the dollar 3% off its episode peak (the first confirmation), or the scramble gauge closing" if a_met else
                      "the deceleration reading (a) being met, or the scramble gauge closing") if scr.get("gate_open") else
                     "the scramble gauge opening (a 4% climb with yields falling)")
    watch.append("a month dated as a crisis onset by the mechanical markers")
    caveat = ("None of these readings has been validated as an early sign of crisis; the base rate or own-history percentile beside "
              "each one is the honest guide.")
    out["page"] = ([", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] + ".",
                    "Taken together this describes where the dollar and its plumbing stand, not a forecast. " + caveat,
                    "What would change this picture: " + "; ".join(watch) + ". Each shows above as it happens."]
                   if parts else ["Live data unavailable: only the frozen record below applies.", caveat])
    return out


def build_dollar_watch(inp: dict, today: str | None = None, ledger_file: str | None = None) -> dict:
    if REF_ERROR:
        raise RuntimeError(f"dollar reference unavailable: {REF_ERROR}")
    today = today or datetime.now(timezone.utc).date().isoformat()
    path = ledger_file or ledger_path()
    state = state_block(inp)
    fund = funding_block(inp)
    state["safe_haven"]["gold"]["note"] = gold_funding_note(state, fund)
    scr = scramble_block(inp, fund, today, path)
    fwd = forward_block(inp, scr, today, path)
    slow = slow_block(inp)
    led = ledger_block(inp, state, today, path)
    if scr.get("ledger_status") not in (None, "ok"):          # the rule's append failed or found the file unreadable
        led["status"] = "error"
        why = f"scramble-rule rows not saved: {scr['ledger_problem']}" if scr.get("ledger_problem") else f"scramble-rule rows: {scr['ledger_status']}"
        led["problem"] = "; ".join(x for x in (led.get("problem"), why) if x)
    blocks = {"state": state["status"], "funding": fund["status"], "scramble": scr["status"], "slow": slow["status"], "ledger": led["status"],
              "forward": fwd["status"]}
    return {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "frozen_on": FROZEN_ON, "mode": "descriptive",
            "status": {"overall": worst(blocks.values()), "blocks": blocks},
            "headline": headline(state, fund, scr, slow),
            "state": state, "funding": fund, "scramble": scr, "slow": slow, "ledger": led, "forward": fwd,
            "crisis_lists": REF.get("crisis_lists"), "window_convention": REF.get("window_convention"),
            "provenance": {k: (REF.get("provenance") or {}).get(k) for k in ("study", "builder", "reviews")},
            "pending_questions": [dict(q, status="asked", first_asked=q.get("first_asked", "2026-11-02"),
                                       expires=(date.fromisoformat(q.get("first_asked", "2026-11-02")) + timedelta(days=60)).isoformat())
                                  if "status" not in q else dict(q, first_asked=q.get("answered_on"), expires=None) for q in PENDING],
            "summaries": summaries(state, fund, scr, slow, led, fwd),
            "honesty": list(REF.get("honesty") or []) + [prereg_line() if h == "PREREG" else h for h in HONESTY_LIVE]}




def prereg_line() -> str:
    fd = _freeze_date()
    if fd:
        return (f"Pre-registration frozen {fd} (SPEC v1, forward only): the deceleration rule is graded only on firings after the "
                "freeze (unpatched variant) against a no-information volatility model bracketed for drift (a PASS is judged at a "
                "-1%/yr dollar drift, a FAIL at +1%/yr), with a placebo rule scored beside it. The first look comes at 8 matured "
                "units (about 2060-2070) and only a PASS there could license a colour or a notification. C16 is the primary crisis "
                "list; future crises are dated by 2 of 5 mechanical markers, one month at a time.")
    return ("Pre-registration answered 2026-11-02 (forward only; C16; unpatched; 2-of-5 crisis dating); the freeze record is "
            "pending its reviews.")


# ============================================================================ the frozen pre-registration (SPEC v1)
# studies/dollar_watch/spec/SPEC_v1.md: forward-only. The panel records, point in time, everything the
# D-3 test and the onset rule will need later; it never computes p_u or a look (that is the offline
# harness studies/dollar_watch/prereg/d3.py, checked by two verifiers at each look).
FREEZE_PATH = os.path.join(os.path.dirname(__file__), "..", "sources", "dollar_freeze.json")
FED_PATH = os.path.join(os.path.dirname(__file__), "..", "sources", "dollar_fed_actions.json")
PU_PATH = os.path.join(os.path.dirname(__file__), "..", "sources", "dollar_pu_records.json")
D3_KINDS = ("scramble_rule", "placebo_rule")       # the rule and its placebo (stats review v1 S2), scored the same way


def _load_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"


def _sha256_file(path: str | None) -> str | None:
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except Exception:  # noqa: BLE001
        return None


FREEZE, FREEZE_ERROR = _load_json(FREEZE_PATH)
FED, FED_ERROR = _load_json(FED_PATH)
FED_SHA = _sha256_file(FED_PATH)
PU, PU_ERROR = _load_json(PU_PATH)
HIST_ONSETS = list(((FREEZE.get("onset_check") or {}).get("onsets")) or [])
HIST_DOLLAR_FUNDING = set(((FREEZE.get("onset_check") or {}).get("dollar_funding_subtype")) or [])
UNIT_GAP = int(((FREEZE.get("d3") or {}).get("unit_merge_index_days")) or 250)
FIRST_LIVE_MONTH = str(FREEZE.get("onset_first_month") or add_months(LAST_FROZEN_MONTH + "-01", 1)[:7])   # frozen, not rebuilt


def _freeze_date() -> str | None:
    fd = FREEZE.get("freeze_date")
    return fd if isinstance(fd, str) and len(fd) == 10 and fd[:4].isdigit() else None


# ---------------------------------------------------------------------------- the H.10 release calendar (C5) and month closes
def _nth_weekday(y: int, m: int, wd: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(days=7 * (n - 1))


def _last_weekday(y: int, m: int, wd: int) -> date:
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - wd) % 7)


def us_federal_holidays(y: int) -> set[str]:
    """US federal holidays (observed: Saturday -> Friday, Sunday -> Monday)."""
    fixed = [(1, 1), (7, 4), (11, 11), (12, 25)] + ([(6, 19)] if y >= 2021 else [])
    out = set()
    for m, d in fixed:
        x = date(y, m, d)
        x = x - timedelta(days=1) if x.weekday() == 5 else x + timedelta(days=1) if x.weekday() == 6 else x
        out.add(x.isoformat())
    for x in (_nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3), _last_weekday(y, 5, 0), _nth_weekday(y, 9, 0, 1),
              _nth_weekday(y, 10, 0, 2), _nth_weekday(y, 11, 3, 4)):
        out.add(x.isoformat())
    return out


def _is_bday(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in us_federal_holidays(d.year)


def h10_release(d: str) -> str:
    """The H.10 release that first carries day d: the Monday after d's week (4:15pm ET, after the equity
    close), moved to the next business day when that Monday is a federal holiday."""
    dt = date.fromisoformat(d) + timedelta(days=7 - date.fromisoformat(d).weekday())
    while not _is_bday(dt):
        dt += timedelta(days=1)
    return dt.isoformat()


H10_SOURCE = "computed: the Monday after the data week, next business day on a federal holiday (H.10 weekly release)"


def _month_end(m: str) -> date:
    y, mm = int(m[:4]), int(m[5:7])
    return date(y + (mm == 12), mm % 12 + 1, 1) - timedelta(days=1)


def _last_bday(m: str) -> date:
    d = _month_end(m)
    while not _is_bday(d):
        d -= timedelta(days=1)
    return d


def _bdays_after(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        n -= _is_bday(d)
    return d


def onset_close(m: str) -> str:
    """SPEC v1 §5.6: month m is evaluated once, at the first build on or after the later of the day AFTER the H.10 release
    carrying m's last business day (the release comes at 4:15pm ET; data re-check S-1) and m's end + 5 business days."""
    rel = date.fromisoformat(h10_release(_last_bday(m).isoformat())) + timedelta(days=1)
    return max(rel.isoformat(), _bdays_after(_month_end(m), 5).isoformat())


def onset_deadline(m: str) -> str:
    """the last day m may wait for a late input or the Fed-list review: the end of the following month."""
    return _month_end(add_months(m + "-01", 1)[:7]).isoformat()


def _covers(ps: list, m: str, weekly: bool = False) -> bool:
    """the series reaches m's last business day (weekly: m's last Wednesday), i.e. every observation dated in m is out."""
    if weekly:
        d = _month_end(m)
        last = d - timedelta(days=(d.weekday() - 2) % 7)
    else:
        last = _last_bday(m)
    return bool(ps) and ps[-1][0] >= last.isoformat()


def _fresh(s: dict | None) -> bool:
    """fetched this build (status "ok"), not served from a stale cache."""
    return bool(s) and s.get("status") == "ok"


# ---------------------------------------------------------------------------- archives and the rule state (C2, C7)
def _ledger_dir(path: str) -> str:
    return os.path.dirname(os.path.abspath(path))


def archive_bytes(path: str, src: str | None, compress: bool = False) -> dict:
    """Copy a fetched file's exact bytes into <ledger dir>/archive/<sha256> (gzip-compressed as <sha256>.gz when asked;
    the hash is always of the raw bytes; deduplicated)."""
    if not src:
        return {"sha256": None, "archived": False}
    try:
        with open(src, "rb") as fh:
            body = fh.read()
    except Exception:  # noqa: BLE001
        return {"sha256": None, "archived": False}
    return archive_body(path, body, compress)


def archive_body(path: str, body: bytes, compress: bool = False) -> dict:
    h = hashlib.sha256(body).hexdigest()
    dst = os.path.join(_ledger_dir(path), "archive", h + (".gz" if compress else ""))
    if not os.path.exists(dst):
        try:
            from ..sources.fred_csv import _write_atomic
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            _write_atomic(dst, gzip.compress(body, mtime=0) if compress else body)
        except Exception as exc:  # noqa: BLE001
            return {"sha256": h, "archived": False, "error": str(exc)[:120]}
    return {"sha256": h, "archived": True, "bytes": len(body), **({"gzip": True} if compress else {})}


def _source_file(name: str) -> str | None:
    try:
        from ..sources.dollar_data import cache_file
        f = cache_file(name)
        return f if os.path.exists(f) else None
    except Exception:  # noqa: BLE001
        return None


def _rule_state(path: str) -> dict:
    d, _ = _load_json(os.path.join(_ledger_dir(path), "dollar_rule_state.json"))
    return d if isinstance(d, dict) else {}


def _save_rule_state(path: str, state: dict) -> None:
    try:
        from ..sources.fred_csv import _write_atomic
        os.makedirs(_ledger_dir(path), exist_ok=True)
        _write_atomic(os.path.join(_ledger_dir(path), "dollar_rule_state.json"), json.dumps(state, sort_keys=True))
    except Exception as exc:  # noqa: BLE001
        logger.warning("dollar rule state not saved: %s", exc)


# ---------------------------------------------------------------------------- D-3 rows: eligibility, units, inputs (C1, C2; data review v1 S1)
def d3_eligibility(d: str, first_vintage: bool | None, freeze_date: str | None) -> tuple[bool | None, str | None]:
    """SPEC v1 §1 / §3.1: a row is evidence only if its data date is after the freeze date AND it fired on the first
    vintage that carried that date. None = the first vintage is unknown (reconstructed from ALFRED at the look)."""
    if freeze_date is None:
        return False, "no freeze record yet: in-sample"
    if d <= freeze_date:
        return False, "data date on or before the freeze date: in-sample, never scored"
    if first_vintage is None:
        return None, "first vintage unknown (no earlier rule state): reconstruct from ALFRED at the look (SPEC v1 §3.1)"
    if first_vintage is False:
        return False, "appeared only after a revision: logged, never scored (SPEC v1 §3.1)"
    return True, None


def first_vintage(d: str, prev_last_index_day: str | None, b_last: str) -> bool | None:
    """Did the panel read the first vintage that carried day d? False if an earlier build had already seen d; True if d is
    in the week the latest H.10 release added (b_last = DTWEXBGS's last day this build); None otherwise: an outage spanned a
    release, so a later vintage is being read (data re-check M-A) - reconstructed from ALFRED by the harness."""
    if prev_last_index_day is None:
        return None
    if d <= prev_last_index_day:
        return False
    return True if h10_release(d) == h10_release(b_last) else None


def _seed_index_day() -> str | None:
    """with no rule state yet, the freeze vintage's last day: the panel was frozen having seen it (data re-check M-A)."""
    return ((FREEZE.get("d3") or {}).get("garch_fit") or {}).get("last") if _freeze_date() else None


def enrich_firings(new: dict, ds, B, Y, path: str, prev_last_index_day: str | None, kind: str = "scramble_rule",
                   b_last: str | None = None) -> list[dict]:
    """SPEC v1 §6.1 fields for rows the ledger does not hold yet: k, clause values, the release, whether the firing showed
    on the first vintage that carried its date, D-3 eligibility, unit assignment and archived inputs. Units start only at
    eligible unpatched rows and are measured from the unit's FIRST firing (k - k1 < 250 merges; never chained): a
    pre-freeze or revision-born row never starts or absorbs a unit. Index gaps are counted on the vintage being read."""
    led = load_ledger(path)
    have = {(e.get("kind"), e.get("date")) for e in led.get("entries", [])}
    units = sorted((e for e in led.get("entries", []) if e.get("kind") == kind and e.get("d3_eligible") is True
                    and e.get("unit_first") == e.get("date")), key=lambda e: e["date"])
    pos = {d: i for i, d in enumerate(ds)}
    fz = _freeze_date()
    out = []
    inputs = None
    for d in sorted(new):
        e = new[d]
        if (kind, d) in have or d not in pos:
            continue
        k = pos[d]
        kmx = pos.get(e["roc20_max_date"], k)
        ref_i = max(0, kmx - RULE["yield_lookback_days"])
        fv = first_vintage(d, prev_last_index_day, b_last or ds[-1])
        elig, why = d3_eligibility(d, fv, fz)
        e.update(k=k, calendar="DTWEXBGS & DGS10", y10_now=Y[k], y10_ref=Y[ref_i], y10_ref_date=ds[ref_i],
                 near_high_ratio=r(B[k] / max(B[max(0, k - RULE["window_days"]):k + 1]), 4),
                 h10_release=h10_release(d), h10_release_source=H10_SOURCE,
                 first_vintage_contains_date=fv, d3_eligible=elig, d3_note=why)
        if "unpatched" in e["variants"] and elig is True:
            last_unit = units[-1] if units else None
            ku = None if last_unit is None else pos.get(last_unit["date"], last_unit.get("k"))
            if last_unit is not None and last_unit["date"] not in pos:
                e["unit_gap_note"] = "the unit's first date is off this vintage's calendar: the gap uses its stored k (mixed vintages)"
            if isinstance(ku, int) and k - ku < UNIT_GAP:
                e.update(unit_first=last_unit["date"], index_gap_to_unit_first=k - ku)
            else:
                e.update(unit_first=d, index_gap_to_unit_first=0)
                units.append(e)
        else:
            e.update(unit_first=None, index_gap_to_unit_first=None)       # re-arm-only, pre-freeze and revision-born rows
        if inputs is None:
            inputs = {sid: archive_bytes(path, _source_file(sid)) for sid in ("DTWEXBGS", "DGS10")}
        e["inputs"] = inputs
        out.append(e)
    return out


def revision_checks(path: str, rearm_dates: set, unp_dates: set, today: str, placebo_dates: set | None = None) -> dict:
    """C3: when a live row's fire status changes on a new vintage, append {checked_on, still_fires}; never delete."""
    with _LEDGER_LOCK:
        led = load_ledger(path)
        if led.get("_unreadable") or not led["entries"]:
            return led
        changed = False
        for e in led["entries"]:
            if e.get("kind") == "scramble_rule":
                now = {v: (e["date"] in (unp_dates if v == "unpatched" else rearm_dates)) for v in (e.get("variants") or [])}
            elif e.get("kind") == "placebo_rule" and placebo_dates is not None:
                now = {"unpatched": e["date"] in placebo_dates}
            else:
                continue
            checks = e.setdefault("revision_checks", [])
            if not checks or checks[-1].get("still_fires") != now:
                checks.append({"checked_on": today, "still_fires": now})
                changed = True
        return _write_ledger(path, led) if changed else led


def _write_once(path: str, kind: str, field: str, compute, today: str) -> dict:
    """Write `field` into each row of `kind` once, when compute(row) returns a value (never changed after)."""
    with _LEDGER_LOCK:
        led = load_ledger(path)
        if led.get("_unreadable") or not led["entries"]:
            return led
        changed = False
        for e in led["entries"]:
            if e.get("kind") != kind or field in e:
                continue
            v = compute(e)
            if v is not None:
                e[field] = dict(v, frozen_on=today)
                changed = True
        return _write_ledger(path, led) if changed else led


def maturity_250d(e: dict, ds, B, inp: dict, path: str, full: bool = True) -> dict | None:
    """C4 / SPEC v1 §6.2: the D-3 hit on the maturity vintage plus (full=True) the descriptive tracks, once k+250 exists."""
    pos = {d: i for i, d in enumerate(ds)}
    kk = pos.get(e.get("date"))
    if kk is None or kk + 250 > len(ds) - 1:
        return None
    seg = B[kk + 1:kk + 251]
    mx = max(seg)
    imx = kk + 1 + seg.index(mx)
    fred = inp.get("fred") or {}
    out = {"hit": bool(mx <= 1.03 * B[kk]), "dollar_at_firing": r(B[kk], 4), "max_b": r(mx, 4), "max_date": ds[imx],
           "further_rise_pct": r(100 * (mx / B[kk] - 1), 2), "maturity_date": ds[kk + 250],
           "maturity_vintage": archive_bytes(path, _source_file("DTWEXBGS")).get("sha256")}
    if not full:
        return out
    rel = h10_release(e["date"])
    kr = next((i for i in range(kk, len(ds)) if ds[i] > rel), None)
    if kr is not None and kr + 250 <= len(ds) - 1:
        out["hit_release_anchored"] = bool(max(B[kr + 1:kr + 251]) <= 1.03 * B[kr])
    out["s2_days_to_max"] = imx - kk
    cp = spread(pairs(fred.get("DCPF3M")), pairs(fred.get("DTB3")))
    cp5 = [(cp[i][0], sum(v for _, v in cp[i - 4:i + 1]) / 5) for i in range(4, len(cp))]
    v0, d60 = asof(cp5, e["date"]), ds[kk + 60]
    win = [v for d, v in cp5 if e["date"] < d <= d60]
    out["s3_funding_peak_passed"] = bool(max(win) <= v0) if v0 is not None and win else None
    g = pairs(inp.get("gold"))
    g0 = asof(g, e["date"])
    gw = [v for d, v in g if e["date"] < d <= d60]
    out["s4_gold_held"] = bool(min(gw) >= 0.97 * g0) if g0 and gw else None
    spx = pairs(fred.get("SP500"))
    s0 = asof(spx, e["date"])
    sf = [(d, v) for d, v in spx if d > e["date"]][:250]
    if s0 and len(sf) == 250:
        lo = min(sf, key=lambda x: x[1])
        out["c1_spx_min_above_minus10"] = bool(lo[1] >= 0.90 * s0)
        out["c4_days_to_spx_low"] = sf.index(lo) + 1
        out["spx_low_pct"] = r(100 * (lo[1] / s0 - 1), 1)
    vix = pairs(fred.get("VIXCLS"))
    v_0 = asof(vix, e["date"])
    vf = [(d, v) for d, v in vix if d > e["date"]]
    below = next((i + 1 for i, (_, v) in enumerate(vf) if v < 25), None)
    out["c2_days_to_vix_below_25"] = below
    out["c2_vix_reexceeds_within_60"] = bool(any(v > v_0 for _, v in vf[:60])) if v_0 is not None and len(vf) >= 60 else None
    em, _ = emfx_basket(fred)
    ef = [(d, v) for d, v in em if d > e["date"]][:250]
    out["c3_emfx_extreme_date"] = max(ef, key=lambda x: x[1])[0] if len(ef) == 250 else None
    return out


# ---------------------------------------------------------------------------- the forward onset rule (C6, C7; SPEC v1 §5; data review v1 S2)
ONSET_FRED = ["VIXCLS", "SP500"] + EMFX_IDS          # markers 1, 3 and 4 (marker 2: the OFR fsi.csv; marker 5: the Fed list)


def _p95_flags(fsi: list[tuple[str, float]], start: str) -> dict[str, tuple[bool, float]]:
    """for each FSI day >= start: (above its own P95 over the prior 5 calendar years, that P95); needs 250 prior obs."""
    import numpy as np
    days = [d for d, _ in fsi]
    vals = [v for _, v in fsi]
    out = {}
    for i, d in enumerate(days):
        if d < start:
            continue
        dd = date.fromisoformat(d)
        lo = (dd.replace(year=dd.year - 5) if not (dd.month == 2 and dd.day == 29) else dd.replace(year=dd.year - 5, day=28)).isoformat()
        j0 = bisect.bisect_left(days, lo)
        prior = vals[j0:i]
        if len(prior) < 250:
            continue
        p95 = float(np.percentile(prior, 95))
        out[d] = (vals[i] > p95, p95)
    return out


def _fsi(inp: dict) -> list[tuple[str, float]]:
    ofr = inp.get("ofr") or {}
    return pairs({"dates": ofr.get("dates"), "values": ofr.get("OFR FSI")})


def onset_markers(inp: dict, months: list[str]) -> dict[str, dict]:
    """SPEC v1 §5.1: which of the five markers tripped in each month (first date and value). A withheld EM basket
    (emfx_stale) trips nothing."""
    fred = inp.get("fred") or {}
    trip: dict[str, dict] = {m: {} for m in months}
    if not months:
        return trip
    lo = months[0] + "-01"
    for d, v in pairs(fred.get("VIXCLS")):
        if d[:7] in trip and v >= 40:
            trip[d[:7]].setdefault("1_vix", {"date": d, "value": v})
    fsi = _fsi(inp)
    flags = _p95_flags(fsi, add_months(lo, -1))
    fd = sorted(flags)
    for i in range(4, len(fd)):
        w = [flags[x] for x in fd[i - 4:i + 1]]
        if all(a for a, _ in w) and fd[i][:7] in trip:
            trip[fd[i][:7]].setdefault("2_ofr", {"date": fd[i], "value": dict(fsi).get(fd[i]), "p95": r(w[-1][1], 4)})
    legs = {s: pairs(fred.get(s)) for s in EMFX_IDS}
    if all(legs.values()) and not emfx_stale(fred):
        days = sorted({d for s in EMFX_IDS for d, _ in legs[s] if d >= add_months(lo, -6)})
        bk = []
        for d in days:
            vals = [asof(legs[s], d) for s in EMFX_IDS]
            if all(v is not None and v > 0 for v in vals):
                bk.append((d, math.exp(sum(math.log(v) for v in vals) / 8)))
        for i in range(63, len(bk)):
            d, v = bk[i]
            if d[:7] in trip and v / bk[i - 63][1] - 1 >= 0.10:
                trip[d[:7]].setdefault("3_emfx", {"date": d, "value": r(100 * (v / bk[i - 63][1] - 1), 1)})
    spx = pairs(fred.get("SP500"))
    sv = [v for _, v in spx]
    for i in range(251, len(spx)):
        d, v = spx[i]
        if d[:7] in trip and v <= 0.80 * max(sv[i - 251:i + 1]):
            trip[d[:7]].setdefault("4_spx", {"date": d, "value": r(100 * (v / max(sv[i - 251:i + 1]) - 1), 1)})
    for a in (FED.get("actions") or []):
        if a.get("date", "")[:7] in trip:
            trip[a["date"][:7]].setdefault("5_fed", {"date": a["date"], "url": a.get("url")})
    return trip


def _onset_missing(inp: dict, m: str) -> list[str]:
    """the onset inputs that are not fresh this build or do not yet reach m's last business day (data re-check S-1).
    The EM basket covers m when its newest leg reaches that day and no leg is stale (emfx_stale)."""
    fred = inp.get("fred") or {}
    miss = [s for s in ("VIXCLS", "SP500") if not (_fresh(fred.get(s)) and _covers(pairs(fred.get(s)), m))]
    if not (_fresh(inp.get("ofr")) and _covers(_fsi(inp), m)):
        miss.append("OFR FSI")
    legs = [pairs(fred.get(s)) for s in EMFX_IDS]
    stale = [s for s in EMFX_IDS if not _fresh(fred.get(s))]
    if stale:
        miss.append("EM FX legs not fresh: " + ", ".join(stale))
    elif not all(legs) or not _covers(max(legs, key=lambda x: x[-1][0] if x else ""), m):
        miss.append("EM FX basket")
    else:
        why = emfx_stale(fred)
        if why:
            miss.append(f"EM FX basket withheld ({why})")
    return miss


def _fsi_extract(inp: dict, m: str) -> bytes:
    """the OFR FSI values marker 2 reads for month m (data re-check M-E): from 5 years before the month preceding m
    (a 5-day run can start there) to m's end, as "date,OFR FSI" rows with exact float text."""
    lo = date.fromisoformat(add_months(m + "-01", -1))
    lo = (lo.replace(year=lo.year - 5) - timedelta(days=7)).isoformat()
    hi = _month_end(m).isoformat()
    rows = "".join(f"{d},{v!r}\n" for d, v in _fsi(inp) if lo <= d <= hi)
    return ("date,OFR FSI\n" + rows).encode()


def _window12(m: str) -> set[str]:
    return {add_months(m + "-01", -j)[:7] for j in range(1, 13)}


def evaluate_onsets(inp: dict, path: str, today: str) -> list[dict]:
    """SPEC v1 §5.3: every month from the first live month is evaluated ONCE, in order, at the first build on or after its
    close, once the Fed list is reviewed through it and every input reaches the month's end (or at the deadline, the end
    of the following month, recording what was missing). A row is written for every month, onset or not; the 12-month
    exclusion reads only earlier months. Later revisions and list appends go to the row's revision_checks, never to `onset`."""
    led = load_ledger(path)
    if led.get("_unreadable"):
        return []
    done = {e["date"] for e in led["entries"] if e.get("kind") == "onset_month"}
    known = set(HIST_ONSETS) | {e["date"] for e in led["entries"] if e.get("kind") == "onset_month" and e.get("onset")}
    reviewed = str(FED.get("reviewed_through") or "")
    fred = inp.get("fred") or {}
    new, m = [], FIRST_LIVE_MONTH
    while m < today[:7]:
        if m in done:
            m = add_months(m + "-01", 1)[:7]
            continue
        close = onset_close(m)
        if today < close:
            break
        missing = _onset_missing(inp, m)
        fed_ok = reviewed >= m
        if (missing or not fed_ok) and today <= onset_deadline(m):
            break                                             # wait for the input or the R1 list review, until the deadline
        trip = onset_markers(inp, [m])[m]
        prior = sorted(x for x in known if x in _window12(m))
        n = len(trip)
        row = {"kind": "onset_month", "date": m, "evaluated_on": today, "close": close, "markers": trip, "n_markers": n,
               "onset": bool(n >= 2 and not prior), "excluded_by": prior[-1] if n >= 2 and prior else None,
               "inputs_missing": missing or None,
               "late_evaluation": today > onset_deadline(m),           # after a ledger reset or a long outage: not point in time
               "fed_list": {"sha256": FED_SHA, "reviewed_through": reviewed or None, "current": fed_ok},
               "inputs": {s: {"sha256": _sha256_file(_source_file(s)), "last_obs": (pairs(fred.get(s)) or [(None, None)])[-1][0],
                              "status": (fred.get(s) or {}).get("status")} for s in ONSET_FRED},
               "ofr_fsi": {**archive_body(path, _fsi_extract(inp, m), compress=True), "extract": "date,OFR FSI; 5 years before m-1 to m's end",
                           "full_file_sha256": _sha256_file(_source_file("ofr_fsi")), "last_obs": (_fsi(inp) or [(None, None)])[-1][0],
                           "status": (inp.get("ofr") or {}).get("status")},
               "rule": "SPEC v1 §5 (2 of 5; 12-month exclusion from the last onset), evaluated once at the month's close"}
        new.append(row)
        if row["onset"]:
            known.add(m)
        m = add_months(m + "-01", 1)[:7]
    if new:
        w = append_ledger(path, new, today)
        if w.get("_write_failed") or w.get("_unreadable"):
            raise OSError(f"onset rows not saved: {w.get('_write_failed') or 'ledger unreadable'}")
    onset_revision_checks(inp, path, today)
    swpt = pairs(fred.get("SWPT"))
    cp = spread(pairs(fred.get("DCPF3M")), pairs(fred.get("DTB3")))
    cp5 = [(cp[i][0], sum(v for _, v in cp[i - 4:i + 1]) / 5) for i in range(4, len(cp))]

    def subtype(e):
        if not e.get("onset"):
            return None
        m0 = e["date"]
        m2 = add_months(m0 + "-01", 2)[:7]
        if today < onset_close(m2):
            return None                                       # pending until m+2's close (M2)
        miss = [s for s in ("SWPT", "DCPF3M", "DTB3")
                if not (_fresh(fred.get(s)) and _covers(pairs(fred.get(s)), m2, weekly=(s == "SWPT")))]
        if miss and today <= onset_deadline(m2):
            return None
        win = {m0, add_months(m0 + "-01", 1)[:7], m2}
        sw = [(d, v) for d, v in swpt if d[:7] in win and v > 50_000]
        c5 = [(d, r(v, 2)) for d, v in cp5 if d[:7] in win and v > 1.00]
        return {"dollar_funding": bool(sw or c5), "swpt_gt_50bn_first": sw[0] if sw else None,
                "cp_bill_5d_gt_1pp_first": c5[0] if c5 else None, "close": onset_close(m2), "inputs_missing": miss or None}

    led = _write_once(path, "onset_month", "subtype", subtype, today)
    if led.get("_write_failed"):
        raise OSError(f"onset subtype not saved: {led['_write_failed']}")
    return [e for e in led.get("entries", []) if e.get("kind") == "onset_month"]


def onset_revision_checks(inp: dict, path: str, today: str) -> None:
    """re-read every evaluated month on today's data and list; append {checked_on, markers_now} when the set of tripped
    markers changes. Skipped when an input failed to fetch (a fetch failure is not a revision)."""
    fred = inp.get("fred") or {}
    if any(not pairs(fred.get(s)) for s in ONSET_FRED) or not _fsi(inp):
        return
    with _LEDGER_LOCK:
        led = load_ledger(path)
        rows = [e for e in led.get("entries", []) if e.get("kind") == "onset_month"]
        if led.get("_unreadable") or not rows:
            return
        now = onset_markers(inp, sorted(e["date"] for e in rows))
        changed = False
        for e in rows:
            keys = sorted(now.get(e["date"], {}))
            checks = e.get("revision_checks") or []
            last = checks[-1]["markers_now"] if checks else sorted(e.get("markers") or {})
            if keys != last:
                e["revision_checks"] = checks + [{"checked_on": today, "markers_now": keys, "fed_list_sha256": FED_SHA}]
                changed = True
        if changed:
            _write_ledger(path, led)


def mature_momentum(inp: dict, path: str, today: str) -> None:
    """C8 (data review v1 M2): a momentum row's onset record is written once every month m+1..m+12 has been evaluated
    and every onset among them has its subtype; its EM FX 12-month maximum rise once the basket reaches past m+12's close."""
    fred = inp.get("fred") or {}
    em, _ = emfx_basket(fred)
    led = load_ledger(path)
    rows = {e["date"]: e for e in led.get("entries", []) if e.get("kind") == "onset_month"}

    def onsets_12m(e):
        win = [add_months(e["date"] + "-01", j)[:7] for j in range(1, 13)]
        if any(x >= FIRST_LIVE_MONTH and x not in rows for x in win):
            return None                                       # a month not evaluated yet
        hit = [x for x in win if x in HIST_ONSETS or (rows.get(x) or {}).get("onset")]
        if any(x in rows and "subtype" not in rows[x] for x in hit):
            return None                                       # a subtype still pending
        return {"onsets": hit, "dollar_funding": [x for x in hit if x in HIST_DOLLAR_FUNDING or
                                                  ((rows.get(x) or {}).get("subtype") or {}).get("dollar_funding")]}

    def emfx_12m(e):
        m = e["date"]
        end = add_months(m + "-01", 12)[:7]
        if today < onset_close(end) or not _covers(em, end):
            return None
        e0 = asof(em, _month_end(m).isoformat())
        ew = [v for d, v in em if add_months(m + "-01", 1)[:7] <= d[:7] <= end]
        return {"max_rise_pct": r(100 * (max(ew) / e0 - 1), 1)} if e0 and ew else None

    for field, fn in (("onset_within_12m", onsets_12m), ("emfx_12m", emfx_12m)):
        w = _write_once(path, "momentum", field, fn, today)
        if w.get("_write_failed"):
            raise OSError(f"momentum {field} not saved: {w['_write_failed']}")


# ---------------------------------------------------------------------------- the forward block
def retry_archives(path: str) -> None:
    """data re-check M-C: a rule or placebo row whose input bytes failed to archive is retried while the cached file still
    has the recorded sha256 (the same bytes); only the archive flag changes, never the evidence."""
    with _LEDGER_LOCK:
        led = load_ledger(path)
        if led.get("_unreadable"):
            return
        changed = False
        for e in led.get("entries", []):
            if e.get("kind") not in D3_KINDS:
                continue
            for sid, rec in (e.get("inputs") or {}).items():
                if rec and not rec.get("archived") and rec.get("sha256") and _sha256_file(_source_file(sid)) == rec["sha256"]:
                    got = archive_bytes(path, _source_file(sid))
                    if got.get("archived") and got.get("sha256") == rec["sha256"]:
                        e["inputs"] = dict(e["inputs"], **{sid: dict(got, archived_late=True)})
                        changed = True
        if changed:
            _write_ledger(path, led)


def archive_usage(path: str) -> dict:
    """the archive's size on the persistent disk (data re-check M-E)."""
    d = os.path.join(_ledger_dir(path), "archive")
    try:
        files = [os.path.join(d, f) for f in os.listdir(d)]
        return {"files": len(files), "bytes": sum(os.path.getsize(f) for f in files)}
    except FileNotFoundError:
        return {"files": 0, "bytes": 0}
    except Exception as exc:  # noqa: BLE001
        return {"files": None, "bytes": None, "error": str(exc)[:120]}


def forward_block(inp: dict, scr: dict, today: str, path: str) -> dict:
    """Runs the point-in-time duties (C3, C4, C6-C8) and summarises the frozen pre-registration for the panel."""
    fred = inp.get("fred") or {}
    ds, B, Y = rule_index(fred)
    problems = []
    try:
        if len(ds) > RULE["first_eval_index"]:
            rearm = {f["date"] for f in scramble_firings(ds, B, Y, True)}
            unp = {f["date"] for f in scramble_firings(ds, B, Y, False)}
            plc = {f["date"] for f in scramble_firings(ds, B, Y, False, decel=False)}
            for what, w in (("revision checks", revision_checks(path, rearm, unp, today, placebo_dates=plc)),
                            ("rule maturity", _write_once(path, "scramble_rule", "outcomes_250d",
                                                          lambda e: maturity_250d(e, ds, B, inp, path), today)),
                            ("placebo maturity", _write_once(path, "placebo_rule", "outcomes_250d",
                                                             lambda e: maturity_250d(e, ds, B, inp, path, full=False), today))):
                if w.get("_write_failed"):
                    problems.append(f"{what} not saved: {w['_write_failed']}")
        months = evaluate_onsets(inp, path, today)
        mature_momentum(inp, path, today)
    except Exception as exc:  # noqa: BLE001 - the forward duties must never take the panel down
        logger.exception("dollar forward duties failed: %s", exc)
        problems.append(f"{type(exc).__name__}: {str(exc)[:160]}")
    retry_archives(path)
    led = load_ledger(path)
    if led.get("_unreadable"):
        problems.append("the ledger file is unreadable or wrongly shaped: nothing is being recorded")
    months = [e for e in led.get("entries", []) if e.get("kind") == "onset_month"]      # the summary reads the ledger itself
    unarchived = [f"{e['kind']} {e['date']}" for e in led.get("entries", []) if e.get("kind") in D3_KINDS
                  and any(not (x or {}).get("archived") for x in (e.get("inputs") or {}).values())]
    unarchived += [f"onset_month {e['date']}" for e in months if not (e.get("ofr_fsi") or {}).get("archived")]
    if unarchived:
        problems.append(f"inputs not archived for {len(unarchived)} rows ({', '.join(unarchived[:3])})")
    late = [e["date"] for e in months if e.get("late_evaluation")]
    if late:
        problems.append(f"{len(late)} months dated after their deadline, not point in time ({', '.join(late[:3])})")
    pu = {(x.get("kind"), x.get("date")): x for x in (PU.get("records") or [])}

    def d3_summary(kind):
        rows = [e for e in led.get("entries", []) if e.get("kind") == kind]
        units = [e for e in rows if e.get("d3_eligible") is True and e.get("unit_first") == e.get("date")]
        return {"rows": len(rows), "units": len(units), "matured": sum("outcomes_250d" in e for e in units),
                "in_sample_rows": sum(e.get("d3_eligible") is False for e in rows),
                "eligibility_unknown": sum(e.get("d3_eligible") is None for e in rows),
                "with_p_u": sum((kind, e["date"]) in pu for e in units),
                "unit_list": [{"date": e["date"], "k": e.get("k"), "matured": "outcomes_250d" in e,
                               "hit": (e.get("outcomes_250d") or {}).get("hit"),
                               "p_u_zero": ((pu.get((kind, e["date"])) or {}).get("by_drift") or {}).get("zero", {}).get("p_u")} for e in units]}

    dec, plc_s = d3_summary("scramble_rule"), d3_summary("placebo_rule")
    nxt = FIRST_LIVE_MONTH
    done = {e["date"] for e in months}
    while nxt in done:
        nxt = add_months(nxt + "-01", 1)[:7]
    hist = (FREEZE.get("onset_check") or {})
    d3f = FREEZE.get("d3") or {}
    return {"freeze": {**{k: FREEZE.get(k) for k in ("freeze_date", "spec_version", "route", "primary_crisis_list", "decel_primary_variant",
                                                       "forward_onset_rule", "answered_by", "answered_on")},
                       "notification_licence": FREEZE.get("lamp_license")},
            "garch": d3f.get("garch_fit"),
            "d3": {"units": dec["units"], "matured": dec["matured"], "looks": [8, 16, 24], "next_look_at": 8, "decel": dec, "placebo": plc_s,
                   "status": "before look 1: descriptive" if dec["matured"] < 8 else "look due: run the offline harness",
                   "rule": "unpatched firings after the freeze date that showed on the first vintage carrying their date; a unit runs "
                           "250 index days from its first firing; hit = the broad dollar rises at most 3% further over the next 250 index "
                           "days; null = the frozen GARCH(1,1)-t, a PASS judged at a -1%/yr drift and a FAIL at +1%/yr; exact "
                           "Poisson-binomial with alpha spent 0.005 / 0.020 / 0.050 at 8 / 16 / 24 matured units; the placebo rule (no "
                           "deceleration clause) scored beside it; a PASS would read 'dollar scramble peaking: beat a no-information model' "
                           "(deceleration-specific: not tested)",
                   "calendar": FORWARD_CALENDAR},
            "onsets": {"historical": hist.get("onsets"), "historical_dollar_funding": hist.get("dollar_funding_subtype"),
                       "historical_note": "the frozen rule run on 2000-2026 as a pre-committed degeneracy check (8, inside 3-13): "
                                          "a calibration check, not validation; long crises re-date at month 13 (Q18)",
                       "live": [e for e in months if e.get("onset")], "months_evaluated": len(months),
                       "last_evaluated": months[-1]["date"] if months else None, "next_month": nxt, "next_close": onset_close(nxt),
                       "late_months": late},
            "archive": archive_usage(path),
            "fed_actions": {"n": len(FED.get("actions") or []), "last": ((FED.get("actions") or [{}])[-1]).get("date"),
                            "reviewed_through": FED.get("reviewed_through"), "sha256": FED_SHA, "error": FED_ERROR},
            "status": "error" if (FREEZE_ERROR or FED_ERROR or PU_ERROR or problems) else "ok", "problems": problems or None}
