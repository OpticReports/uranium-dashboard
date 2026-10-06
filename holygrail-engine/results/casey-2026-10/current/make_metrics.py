"""Merge the section metrics into metrics.json (run last)."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
a = json.loads((OUT / "metrics_a1_a4.json").read_text())
b = json.loads((OUT / "metrics_a5_a6.json").read_text())
M = {"analysis": "A: Casey's CURRENT book through the Dalio Holy Grail lens (not the Composer HG symphony)",
     "params": json.loads((OUT / "predeclared_params.json").read_text()),
     "HELD": a["A1_at_stake_F4_F5"]["status"],
     "post_hoc": a.get("post_hoc", []) + b.get("post_hoc", []),
     "rf": a["rf"], "base_window": a["base_window"], "prior_vols_base_window": a["prior_vols_base_window"],
     "A1": a["A1"], "A1_robustness": a["A1_robustness"], "A2": a["A2"], "A3": a["A3"], "A3_weekly": a["A3_weekly"],
     "A3_private_assumption_driven": a["A3_private"], "A4_overlap_daily": a["A4_overlap_daily"],
     "A4_overlap_weekly": a["A4_overlap_weekly"], "A4_cash": a["A4_cash"],
     "A4_cash_net_of_commitments": a["A4_cash_net_of_commitments"], "A1_at_stake_F4_F5": a["A1_at_stake_F4_F5"],
     **{k: v for k, v in b.items() if k != "post_hoc"}}
(OUT / "metrics.json").write_text(json.dumps(M, indent=1, default=str))
(OUT / "metrics_a1_a4.json").unlink()
(OUT / "metrics_a5_a6.json").unlink()
print("metrics.json", (OUT / "metrics.json").stat().st_size)
