"""Equivalence: decel_realtime.py (as run) vs build_reference.py scramble_firings (extracted by ast, run unmodified)
on the repo's data/fred files; calendars B&Y (old builder) and B&Y&V (frozen script / new builder); both variants."""
import ast, csv, json, os, sys
FRED, BR, RT, COMMITTED = sys.argv[1:5]

def fredd(fid):
    o = {}
    for r in csv.DictReader(open(os.path.join(FRED, fid + ".csv"))):
        v = r[fid]
        if v not in ("", "."):
            o[r["observation_date"]] = float(v)
    return o

# --- extract RULE dict and scramble_firings from build_reference.py without executing the module
src = open(BR).read()
tree = ast.parse(src)
ns = {"r": lambda x, k=2: None if x is None else round(x, k)}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "RULE" for t in node.targets):
        exec(compile(ast.Module(body=[node], type_ignores=[]), BR, "exec"), ns)
    if isinstance(node, ast.FunctionDef) and node.name == "scramble_firings":
        exec(compile(ast.Module(body=[node], type_ignores=[]), BR, "exec"), ns)
sf = ns["scramble_firings"]
print("RULE:", {k: v for k, v in ns["RULE"].items() if k != "index"})

B, Y, V = fredd("DTWEXBGS"), fredd("DGS10"), fredd("VIXCLS")
cal_BY = sorted(d for d in B if d in Y)
cal_BYV = sorted(d for d in B if d in Y and d in V)
print("calendar B&Y:", len(cal_BY), cal_BY[0], cal_BY[-1], "| B&Y&V:", len(cal_BYV), cal_BYV[0], cal_BYV[-1])
diff = sorted(set(cal_BY) - set(cal_BYV))
print("days in B&Y but not B&Y&V (VIX missing):", len(diff), diff)
print("days with B but no DGS10:", len([d for d in B if d not in Y]), "| with B but no VIX:", len([d for d in B if d not in V]))

def run_sf(cal, rearm):
    return sf(cal, [B[d] for d in cal], [Y[d] for d in cal], rearm)

res = {}
for cname, cal in (("B&Y", cal_BY), ("B&Y&V", cal_BYV)):
    for rearm in (False, True):
        fs = run_sf(cal, rearm)
        res[(cname, rearm)] = fs
        print(f"scramble_firings {cname:6s} {'rearm' if rearm else 'unpatched':9s} n={len(fs)}:",
              [(f["date"], f["roc20_max_pct"], f["roc20_max_date"], f["roc20_now_pct"]) for f in fs])

for var, fn in (("unpatched", "decel_realtime.json"), ("rearm", "decel_realtime_rearm.json")):
    rt = json.load(open(os.path.join(RT, fn)))
    cm = json.load(open(os.path.join(COMMITTED, fn)))
    key = lambda L: [(x["fire"], x["roc20_max_pct"], x["roc_max_day"], x["roc20_now_pct"], x["dollar"], x["dollar_peak_next250"], x["dollar_more_rise_pct"]) for x in L]
    print(f"decel_realtime.py fresh run == committed {fn}:", key(rt) == key(cm))
    if key(rt) != key(cm):
        for a, b in zip(key(rt), key(cm)):
            if a != b: print("   fresh", a, "\n   commit", b)
    sfd = [(f["date"], f["roc20_max_pct"], f["roc20_max_date"], f["roc20_now_pct"]) for f in res[("B&Y&V", var == "rearm")]]
    rtd = [(x["fire"], x["roc20_max_pct"], x["roc_max_day"], x["roc20_now_pct"]) for x in rt]
    print(f"  {var}: scramble_firings(B&Y&V) == decel_realtime (date, roc20max, argmax day, roc20 now):", sfd == rtd)
    sfo = [(f["date"], f["roc20_max_pct"], f["roc20_max_date"], f["roc20_now_pct"]) for f in res[("B&Y", var == "rearm")]]
    print(f"  {var}: scramble_firings(B&Y)   == decel_realtime:", sfo == rtd)
    if sfo != rtd:
        for a, b in zip(sfo, rtd):
            if a != b: print("     B&Y", a, " vs frozen", b)
