"""(1) Real-time replay: truncate the data at each firing day and at the next index day; does each implementation
fire on the truncated sample, and on which date? (2) Look-ahead (G2): scramble all values after day k; do the
firings at or before k change? US series only (DTWEXBGS / DGS10 / VIXCLS), firing dates already public."""
import ast, csv, os, random, sys
FRED, BR = sys.argv[1:3]
def fredd(fid):
    o = {}
    for r in csv.DictReader(open(os.path.join(FRED, fid + ".csv"))):
        if r[fid] not in ("", "."): o[r["observation_date"]] = float(r[fid])
    return o
src = open(BR).read(); tree = ast.parse(src); ns = {"r": lambda x, k=2: None if x is None else round(x, k)}
for node in tree.body:
    if (isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "RULE" for t in node.targets)) or \
       (isinstance(node, ast.FunctionDef) and node.name == "scramble_firings"):
        exec(compile(ast.Module(body=[node], type_ignores=[]), BR, "exec"), ns)
sf = ns["scramble_firings"]
B, Y, V = fredd("DTWEXBGS"), fredd("DGS10"), fredd("VIXCLS")
cal = sorted(d for d in B if d in Y and d in V)
Bv = [B[d] for d in cal]; Yv = [Y[d] for d in cal]

def frozen_loop(B, Y, rearm):            # decel_realtime.py's firing logic verbatim (pure python), incl. range(80, len(B)-1)
    n = len(B); roc = [None] * n
    for k in range(20, n): roc[k] = B[k] / B[k - 20] - 1
    fires = []; last = -999; last_mx = 0.0
    for k in range(80, n - 1):
        w = roc[k - 60:k + 1]; mx = max(w); kmx = k - 60 + w.index(mx)
        if mx >= 0.04 and roc[k] <= 0.5 * mx and B[k] >= 0.97 * max(B[k - 60:k + 1]) and Y[k] < Y[max(0, kmx - 20)] and (k - last > 120 or (rearm and mx >= 1.5 * last_mx)):
            last = k; last_mx = mx; fires.append(k)
    return fires

for rearm in (False, True):
    full = [f["k"] for f in sf(cal, Bv, Yv, rearm)]
    assert [cal[k] for k in full] == [cal[k] for k in frozen_loop(Bv, Yv, rearm)]
    print("variant", "rearm" if rearm else "unpatched")
    for k in full:
        a = sf(cal[:k + 1], Bv[:k + 1], Yv[:k + 1], rearm)          # data end = firing day
        b = frozen_loop(Bv[:k + 1], Yv[:k + 1], rearm)
        c = frozen_loop(Bv[:k + 2], Yv[:k + 2], rearm)              # one more index day
        print(f"  {cal[k]}: builder on data-to-{cal[k]} fires that day: {bool(a) and a[-1]['date'] == cal[k]} | "
              f"frozen script on data-to-{cal[k]}: {bool(b) and b[-1] == k} | frozen with next day {cal[k+1]}: {bool(c) and c[-1] == k}")
    # (2) perturbation after each firing day k (and after k-1): scramble the future 25 times
    rng = random.Random(20261102); bad = 0
    for k in full:
        for cut in (k, k - 1, k + 1):
            ref = [f["date"] for f in sf(cal, Bv, Yv, rearm) if f["k"] <= cut]
            for _ in range(25):
                B2 = Bv[:cut + 1] + [x * rng.uniform(0.8, 1.25) for x in Bv[cut + 1:]]
                Y2 = Yv[:cut + 1] + [x + rng.uniform(-2, 2) for x in Yv[cut + 1:]]
                got = [f["date"] for f in sf(cal, B2, Y2, rearm) if f["k"] <= cut]
                bad += got != ref
    print("  perturbation runs with a changed firing at or before the cut:", bad, "of", len(full) * 3 * 25)
# last index day status
k = len(cal) - 1
print("last index day", cal[k], "is evaluated by the builder but not by decel_realtime.py")
