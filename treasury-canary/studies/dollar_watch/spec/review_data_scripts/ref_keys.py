"""Print ONLY which dates carry EM-basket outcome fields in dollar_reference.json (no values)."""
import json, sys
ref = json.load(open(sys.argv[1]))
print("frozen_on", ref.get("frozen_on"))
sr = ref["scramble_rule"]
print("rule index:", sr["params"]["index"])
print("firings (re-arm) dates:", [f["date"] for f in sr["firings"]])
print("firings_unpatched:", sr["firings_unpatched"])
for f in sr["firings"]:
    o = f.get("outcomes", {})
    flags = {h: (None if o.get(h) is None else ("emfx" if o[h].get("emfx_pct") is not None else "no-emfx")) for h in ("3m", "6m", "12m")}
    print("  firing", f["date"], flags)
print("momentum episodes:", ref["momentum"]["episodes"])
for row in ref["momentum_ledger"]:
    o = row["outcomes"]
    flags = {h: (None if o.get(h) is None else ("emfx" if o[h].get("emfx_pct") is not None else "no-emfx")) for h in ("3m", "6m", "12m")}
    print("  mom", row["month"], flags)
print("monthly_null months:", sr["monthly_null"]["months"])
print("top-level keys:", sorted(ref.keys()))
