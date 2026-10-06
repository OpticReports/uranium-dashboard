"""Merge the three section metrics into metrics.json (run last)."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
parts = {k: json.loads((OUT / f"metrics_{k}.json").read_text()) for k in ("liquid", "postexit", "private")}
M = {"analysis": "No-leverage follow-up (Casey 2026-10-06): N1 corrected liquid book, N2 unlevered liquid proposal, "
                 "N3 $18M post-exit without leverage, N4 private credit / venture as Dalio streams. 'Dalio Holy Grail' = Dalio's "
                 "framework, never the Composer HG symphony.",
     "params": json.loads((OUT / "predeclared_params.json").read_text()),
     "post_hoc": sum((p.get("post_hoc", []) for p in parts.values()), []) + [{
         "item": "N3 replays: first run used listed basket names in tech_2000_02/gfc_2008; corrected to QQQ as declared ('as post-exit')",
         "why": "implementation slip vs the predeclared rule; after the fix ALT-2 UNLEVERED replays reproduce post-exit metrics exactly"}],
     "counter_agent_review": "NOT RUN by the author; required before these numbers are acted on (CLAUDE.md)",
     **{k: {kk: vv for kk, vv in v.items() if kk != "post_hoc"} for k, v in parts.items()}}
(OUT / "metrics.json").write_text(json.dumps(M, indent=1, default=str))
print("metrics.json", (OUT / "metrics.json").stat().st_size)
