"""Regenerate frontend/src/lib/dollarFixture.ts from a real GET /dollar-watch build.

    python3 scripts/dollar_frontend_fixture.py INPUTS.json[.gz] ../frontend/src/lib/dollarFixture.ts

INPUTS is a sources/dollar_data.fetch_all() dump (tests/fixtures/dollar_watch holds the
2026-11-02 capture, trimmed). Builds the live payload and the all-null payload, thins the
long series for size, stamps a fixed `generated`, and writes both as TS literals.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.metrics import dollar_watch as dw  # noqa: E402


def _thin(s, k):
    if not s or not isinstance(s.get("dates"), list):
        return s
    n = len(s["dates"])
    keep = [i for i in range(n) if i % k == 0 or i == n - 1]
    return {key: ([v[i] for i in keep] if isinstance(v, list) and len(v) == n else v) for key, v in s.items()}


def slim(p: dict) -> dict:
    p = json.loads(json.dumps(p))
    m = (p.get("state") or {}).get("dxy", {}).get("monthly") or {}
    if m.get("months"):
        n = len(m["months"])
        keep = [i for i in range(n) if i % 3 == 0 or i >= n - 24]
        for key in ("months", "avg", "close"):
            m[key] = [m[key][i] for i in keep]
    if (p.get("state") or {}).get("emfx"):
        p["state"]["emfx"]["series"] = _thin(p["state"]["emfx"].get("series"), 4)
    for k in ("cp_fin", "ofr_funding", "swap_lines"):
        if ((p.get("funding") or {}).get("series") or {}).get(k):
            p["funding"]["series"][k] = _thin(p["funding"]["series"][k], 4)
    sc = p.get("scramble") or {}
    if sc.get("series_long"):
        sc["series_long"] = _thin(sc["series_long"], 4)
    if (sc.get("series") or {}).get("dates"):
        sc["series"] = _thin(sc["series"], 3)
    p["generated"] = "2026-11-02T20:00:00+00:00"
    return p


def main(src: str, out: str) -> None:
    opener = gzip.open if src.endswith(".gz") else open
    with opener(src, "rt", encoding="utf-8") as fh:
        inp = json.load(fh)
    with tempfile.TemporaryDirectory() as tmp:
        live = dw.build_dollar_watch(inp, today="2026-11-02", ledger_file=os.path.join(tmp, "l.json"))
        null = dw.build_dollar_watch({}, today="2026-11-02", ledger_file=os.path.join(tmp, "n.json"))
    hdr = ("// Dev fixtures for the Dollar watch tab: GET /dollar-watch as the backend builds it from a captured\n"
           "// fetch_all() (live) and with every source down (all-null; the frozen record still ships). Long series\n"
           "// thinned for size. Regenerate with backend/scripts/dollar_frontend_fixture.py, never by hand.\n"
           'import type { DollarWatch } from "./api";\n\n'
           "// The backend payload carries more keys than the view reads, so the literals are cast, not excess-checked.\n")
    body = (f"export const DOLLAR_FIXTURE = {json.dumps(slim(live), separators=(',', ':'))} as unknown as DollarWatch;\n\n"
            f"export const DOLLAR_ALL_NULL = {json.dumps(slim(null), separators=(',', ':'))} as unknown as DollarWatch;\n")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(hdr + body)
    print("wrote", out, len(hdr + body), "bytes")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
