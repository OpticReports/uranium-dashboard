"""Sector-tier measurements, stage 3 input: the blind labelling batches.

Amendment 5/7: every eligible name (cap >= $300M on some day, the same set
stage 2 searched) is labelled by two independent labellers who see ONLY the
company name, the screener and FMP industries, and the full FMP description.
No symbol order, source, tier, watchlist or queue information reaches them:
batches are shuffled with the pre-registered seed, and the files carry
nothing else.

    cd genomics-alpha-tracker/backend && python -m research.sector_tier.prep_labels <out_dir>
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from research.sector_tier import build_ctgov as C  # noqa: E402
from research.sector_tier import build_population as P  # noqa: E402

BATCH = 40
SEED = 20261005


def main(out_dir: Path) -> None:
    pop = json.loads(P.OUT_POP.read_text())
    census = {r["symbol"]: r for r in P.census_today()}
    names = C.eligible(pop, census)
    rows = []
    for p in names:
        path = P.CACHE / "fmp" / "profile" / f"{p['symbol']}.json"
        prof = (json.loads(path.read_text()) or [None])[0] if path.exists() else None
        rows.append({"symbol": p["symbol"], "name": p["name"],
                     "industry_screener": p.get("screener_industry"),
                     "industry_fmp": (prof or {}).get("industry") or p.get("fmp_industry"),
                     "description": ((prof or {}).get("description") or p.get("description") or "")[:2500]})
    random.Random(SEED).shuffle(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    batches = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]
    for i, b in enumerate(batches):
        (out_dir / f"batch_{i:02d}.json").write_text(json.dumps(b, indent=1))
    (out_dir / "index.json").write_text(json.dumps({"n": len(rows), "batches": len(batches),
                                                    "symbols": [[r["symbol"] for r in b] for b in batches]}))
    print(f"{len(rows)} names in {len(batches)} batches -> {out_dir}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
