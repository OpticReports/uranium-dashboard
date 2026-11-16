"""Regenerate frontend/src/lib/gdpFixture.ts from a real GET /gdp-watch build on the shipped snapshot.

    python3 scripts/gdp_frontend_fixture.py ../frontend/src/lib/gdpFixture.ts

Builds the payload from sources/gdp_snapshot.json.gz (status "snapshot"), stamps a fixed `generated`, and writes it
as a TS literal. Never edit the output by hand.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.metrics import gdp_watch as gw  # noqa: E402
from app.sources import gdp_data  # noqa: E402

if __name__ == "__main__":
    snap = gdp_data.load_snapshot()
    keys = ("yoy", "qoq", "pop", "ngdpd", "weo_growth")
    inp = {**{k: snap[k] for k in keys}, "status": {k: "snapshot" for k in keys}, "snapshot_as_of": snap["as_of"]}
    p = gw.build_gdp_watch(inp, today=snap["as_of"])
    p["generated"] = f"{snap['as_of']}T20:00:00+00:00"
    body = ("// Dev fixture for the GDP tab: GET /gdp-watch built from the snapshot frozen with the study\n"
            "// (backend/app/sources/gdp_snapshot.json.gz). Regenerate with backend/scripts/gdp_frontend_fixture.py.\n"
            'import type { GdpWatch } from "./api";\n\n'
            "// The backend payload carries more keys than the view reads, so the literal is cast, not excess-checked.\n"
            f"export const GDP_FIXTURE = {json.dumps(p, separators=(',', ':'))} as unknown as GdpWatch;\n")
    open(sys.argv[1], "w", encoding="utf-8").write(body)
    print("wrote", sys.argv[1], len(body), "bytes")
