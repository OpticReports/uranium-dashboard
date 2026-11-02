"""DTWEXBGS vintages (ALFRED): how much history is revised between vintages (levels and daily log changes),
and do the frozen rule's firing DATES (US series, already public) change across vintages?"""
import ast, csv, glob, math, os, sys
VD, FRED, BR = sys.argv[1:4]
def load(path):
    rows = list(csv.reader(open(path))); out = {}
    for r in rows[1:]:
        if len(r) >= 2 and r[1] not in ("", "."): out[r[0]] = float(r[1])
    return out
def fredd(fid):
    o = {}
    for r in csv.DictReader(open(os.path.join(FRED, fid + ".csv"))):
        if r[fid] not in ("", "."): o[r["observation_date"]] = float(r[fid])
    return o
src = open(BR).read(); ns = {"r": lambda x, k=2: None if x is None else round(x, k)}
for node in ast.parse(src).body:
    if (isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "RULE" for t in node.targets)) or \
       (isinstance(node, ast.FunctionDef) and node.name == "scramble_firings"):
        exec(compile(ast.Module(body=[node], type_ignores=[]), BR, "exec"), ns)
sf = ns["scramble_firings"]
Y, V = fredd("DGS10"), fredd("VIXCLS")
repo = fredd("DTWEXBGS")
vs = sorted(glob.glob(os.path.join(VD, "v_*.bin")))
latest = load(vs[-1])
print("repo file == latest vintage (2026-10-26) on common dates:", all(abs(repo[d] - latest[d]) < 1e-9 for d in repo if d in latest), "| repo last", max(repo), "| latest-vintage last", max(latest))
prev = None
for p in vs:
    v = os.path.basename(p)[2:12]; s = load(p)
    common = sorted(d for d in s if d in latest)
    lv = [math.log(s[d] / latest[d]) for d in common]
    ch = [math.log(s[b] / s[a]) - math.log(latest[b] / latest[a]) for a, b in zip(common, common[1:])]
    ratio_spread = 100 * (max(lv) - min(lv))
    maxdch = max(abs(x) for x in ch) * 1e4
    rms = math.sqrt(sum(x * x for x in ch) / len(ch)) * 1e4
    cal = sorted(d for d in s if d in Y and d in V)
    un = [f["date"] for f in sf(cal, [s[d] for d in cal], [Y[d] for d in cal], False)]
    re_ = [f["date"] for f in sf(cal, [s[d] for d in cal], [Y[d] for d in cal], True)]
    stats = [(f["date"], f["roc20_max_pct"]) for f in sf(cal, [s[d] for d in cal], [Y[d] for d in cal], True)]
    print(f"vintage {v}: last obs {max(s)} | vs latest: level-ratio spread {ratio_spread:.3f}% | daily-change diff max {maxdch:.2f}bp rms {rms:.3f}bp"
          f" | unpatched {un} | rearm-only {[d for d in re_ if d not in un]} | roc20max {[x[1] for x in stats]}")
    if prev is not None:
        pc = sorted(d for d in s if d in prev)
        d1 = max(abs(math.log(s[b] / s[a]) - math.log(prev[b] / prev[a])) for a, b in zip(pc, pc[1:])) * 1e4
        print(f"      revised vs previous pulled vintage: max daily-change diff {d1:.2f}bp over {pc[0]}..{pc[-1]}")
    prev = s
