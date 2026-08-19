"""Human-readable labels for machine codes that leak into generated text.

Anything the desk reads should say "Phase 3 trial results", never
"phase3_readout". The UI has its own copy of this map (lib/format.js) for
values rendered raw; this one covers backend-composed sentences (flag
messages, call theses, binary framing).
"""
from __future__ import annotations

EVENT_LABELS = {
    "pdufa": "FDA decision (PDUFA)",
    "adcom": "FDA advisory committee",
    "interim_analysis": "interim analysis readout",
    "phase3_readout": "Phase 3 trial results",
    "phase2_readout": "Phase 2 trial results",
    "phase1_readout": "Phase 1 trial results",
    "data_presentation": "data presentation (medical conference)",
    "earnings": "earnings report",
    "conference": "investor conference",
    "other": "corporate event",
}


def event_label(event_type: str | None) -> str:
    if not event_type:
        return "event"
    return EVENT_LABELS.get(event_type, event_type.replace("_", " "))
