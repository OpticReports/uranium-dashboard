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
