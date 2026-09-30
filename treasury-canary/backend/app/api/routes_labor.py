"""GET /labor/sahm — Sahm-Rule time series + NBER bands for the labor chart."""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.labor import _sahm_from_unrate
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["labor"])

SAHM_TRIGGER = 0.50


@router.get("/labor/sahm")
def sahm_series():
    bundle = fetch_bundle()
    sd, sv = bundle.get("sahm", ([], []))
    if not any(v is not None for v in sv):        # fall back to computing from UNRATE
        ud, uv = bundle.get("unrate", ([], []))
        sd, sv = _sahm_from_unrate(ud, uv)
        source = "computed from FRED:UNRATE"
    else:
        source = "FRED:SAHMREALTIME"

    series = [{"date": d.isoformat(), "value": v} for d, v in zip(sd, sv) if v is not None]
    latest = series[-1]["value"] if series else None

    # NBER recession bands
    rd, rv = bundle.get("recession", ([], []))
    bands, run_start, prev = [], None, 0.0
    for d, v in zip(rd, rv):
        cur = v or 0.0
        if cur == 1.0 and prev != 1.0:
            run_start = d
        if cur != 1.0 and prev == 1.0 and run_start:
            bands.append({"start": run_start.isoformat(), "end": d.isoformat()})
            run_start = None
        prev = cur
    if run_start and rd:
        bands.append({"start": run_start.isoformat(), "end": rd[-1].isoformat()})

    step = max(1, len(series) // 3000)
    return {
        "series": series[::step], "recessions": bands, "trigger": SAHM_TRIGGER,
        "current": latest, "triggered": (latest is not None and latest >= SAHM_TRIGGER),
        "source": source,
        "note": "Sahm gap = 3mo-avg unemployment minus its 12mo low. >=0.50 has marked the "
                "onset of every recession since the 1970s.",
    }


# ── Labor Stress Board (studies/labor-stress-board.md) ───────────────────────
# Series fetched on their own long histories (the shared bundle starts 1976):
# SOS needs 78 weeks of warm-up and the strip's percentiles use full history.
BOARD_SERIES = {
    # rule inputs
    "iursa": "IURSA", "ccnsa": "CCNSA", "covemp": "COVEMP",
    "job_losers": "LNS13023621", "clf": "CLF16OV", "epop_prime": "LNS12300060",
    "lfpr_prime": "LNS11300060", "pop_prime": "LNU00000060", "unemploy": "UNEMPLOY",
    "unrate": "UNRATE", "sahm": "SAHMREALTIME",
    # strip-only
    "u6": "U6RATE", "nilfwjn": "NILFWJN", "nei": "NEIM156SFRBRIC",
    "ue_flow": "LNS17100000", "jolts_hires": "JTSHIR", "jolts_quits": "JTSQUR",
    "jolts_layoffs": "JTSLDR", "lt_share": "LNS13025703", "lt_level": "UEMP27OV",
    "med_dur": "UEMPMED", "hours": "AWHNONAG", "fb_lfpr": "LNU01373395",
    "nb_lfpr": "LNU01373413",
}
BOARD_START = "1967-01-01"
BOARD_CHART_MONTHS = 180


def _board_series() -> dict:
    from concurrent.futures import ThreadPoolExecutor

    from ..sources.fred import fetch_series
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {k: ex.submit(fetch_series, sid, BOARD_START)
                for k, sid in BOARD_SERIES.items()}
        return {k: f.result() for k, f in futs.items()}


def board_payload(series: dict) -> dict:
    """Pure: raw FRED observations -> the panel payload (testable offline)."""
    from ..metrics import labor_stress as L
    vals = L.rule_values(series)
    lit = L.lit(vals)
    states = L.board(lit)
    months = sorted(states)[-BOARD_CHART_MONTHS:]
    rules = []
    for rid, spec in L.RULES.items():
        v = vals.get(rid, {})
        last = max(v) if v else None
        rules.append({
            "id": rid, "leg": spec["leg"], "label": spec["label"],
            "threshold": spec["threshold"], "unit": spec["unit"],
            "watch": spec.get("watch"),
            "value": v[last] if last else None,
            "month": f"{last[0]}-{last[1]:02d}" if last else None,
            "lit": lit[rid].get(last) if last else None,
            # distance to trigger: value / threshold (1.0 = the line)
            "ratio": round(v[last] / spec["threshold"], 3) if last else None,
        })
    history = []
    for k in months:
        row = {"month": f"{k[0]}-{k[1]:02d}", "state": states[k]}
        for rid, spec in L.RULES.items():
            x = vals.get(rid, {}).get(k)
            row[rid] = round(x / spec["threshold"], 3) if x is not None else None
        history.append(row)
    last = months[-1] if months else None
    return {
        "state": states[last] if last else None,
        "month": f"{last[0]}-{last[1]:02d}" if last else None,
        "rules": rules, "history": history, "strip": L.strip(series),
        "note": ("ALERT = a layoff rule (A) AND a slack rule (B/C) lit in the same "
                 "month; WATCH = any one rule lit. The Board answers 'is a "
                 "layoff-driven downturn confirmed?'; the strip answers 'is the "
                 "headline rate too good?' — they can disagree."),
    }


@router.get("/labor/board")
def labor_board():
    return board_payload(_board_series())
