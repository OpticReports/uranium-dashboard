"""Merge the three section metrics into metrics.json (run last)."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
parts = {k: json.loads((OUT / f"metrics_{k}.json").read_text()) for k in ("liquid", "postexit", "private", "repair")}
M = {"analysis": "No-leverage follow-up (Casey 2026-10-06): N1 corrected liquid book, N2 unlevered liquid proposal, "
                 "N3 $18M post-exit without leverage, N4 private credit / venture as Dalio streams. 'Dalio Holy Grail' = Dalio's "
                 "framework, never the Composer HG symphony.",
     "params": json.loads((OUT / "predeclared_params.json").read_text()),
     "post_hoc": sum((p.get("post_hoc", []) for p in parts.values()), []) + [{
         "item": "N3 replays: first run used listed basket names in tech_2000_02/gfc_2008; corrected to QQQ as declared ('as post-exit')",
         "why": "implementation slip vs the predeclared rule; after the fix ALT-2 UNLEVERED replays reproduce post-exit metrics exactly"}, {
         "item": "repair 2 (counter-agent): look-through notional added (repair_lookthrough.py, lookthrough_notional.*)",
         "why": "'no leverage' was applied as no borrowing / no levered balanced funds; the 3x ETFs inside Casey's Composer strategy were "
                "kept and not disclosed. Disclosure only; no N1-N4 number changed."}],
     "relayed_answers_resolution": {
         "verbatim": "'1. Passes thru 2. There is and we are too small on the SPV 3. I'm not sure, but fees would continue as is so yes to fees'",
         "mapping": "DexMat pro-rata follow-up questions, recorded in venture-deal-analyzer/deals/dexmat/ic.md (Answered 2026-10-06): "
                    "(1) the pro-rata right passes through the SPV; (2) a major-investor threshold exists and the SPV is too small to meet it; "
                    "(3) fees continue as is on any follow-on (Casey: 'I'm not sure, but...' - medium confidence)",
         "effect": "no number in N1-N4 changes; DexMat $75k commitment stands; item CLOSED, not to be asked again",
         "supersedes": "params.inputs_casey_2026_10_06.relayed_answers_unmapped (predeclared file left frozen)"},
     "counter_agent_review": "RUN 2026-10-06: 2 blocking (N1 repaid-capital premise; undisclosed embedded 3x leverage) + 4 non-blocking items; "
                             "repair pass applied (N1 conditional range + P1 ask, look-through notional, F17 scope label, DexMat answers "
                             "closed). The repair itself has NOT been independently re-verified.",
     **{k: {kk: vv for kk, vv in v.items() if kk != "post_hoc"} for k, v in parts.items()}}
(OUT / "metrics.json").write_text(json.dumps(M, indent=1, default=str))
print("metrics.json", (OUT / "metrics.json").stat().st_size)
