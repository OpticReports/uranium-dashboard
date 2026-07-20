"""55-year regime-bootstrap of the 4-engine blend (1971-2026).
Spine: real monthly regime labels from S&P dailies (TREND-UP / CHOP / CRASH).
Engines: regime-conditional monthly returns from each engine's LONGEST real
record (HG 2015+, SLEEVE 2021+, KMLM 2023+, HARV = guarded sim 2018-23 +
real 2023+). Joint sampling: each simulated month picks ONE real month of the
same regime; engines alive that month use their actual return (preserves
cross-correlation), others draw from their marginal bucket.
Variant CONSERVATIVE: KMLM's CRASH/CHOP buckets replaced by HG's (its 814td
record contains no hostile regime; this bounds the optimism).
"""
import json, math, random, datetime
SC = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"

r = json.load(open(f"{SC}/gspc-daily.json"))["chart"]["result"][0]
q = r["indicators"]["quote"][0]
spx = {}
for ts, c in zip(r["timestamp"], q["close"]):
    if c is not None:
        d = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date()
        spx[d.isoformat()] = c
sd = sorted(spx)
by_m = {}
for i, dt in enumerate(sd):
    by_m.setdefault(dt[:7], []).append((spx[dt], spx[sd[i-1]] if i else spx[dt]))
regime, spx_mret = {}, {}
for ym, rows in sorted(by_m.items()):
    mret = rows[-1][0] / rows[0][1] - 1
    worst = min(a/b - 1 for a, b in rows)
    spx_mret[ym] = mret
    regime[ym] = "CRASH" if (mret < -0.05 or worst < -0.03) else ("TREND-UP" if mret > 0.025 else "CHOP")
months = [ym for ym in sorted(regime) if "1971-01" <= ym <= "2026-06"]
freq = {reg: sum(1 for m in months if regime[m] == reg)/len(months) for reg in ("TREND-UP","CHOP","CRASH")}
print(f"spine: {months[0]}..{months[-1]} ({len(months)} months) freq={ {k: round(v,3) for k,v in freq.items()} }")
print(f"spine SPX cagr: {(math.prod(1+spx_mret[m] for m in months))**(12/len(months))-1:+.1%}")

def monthly(curve):
    me = {}
    for dt in sorted(curve): me[dt[:7]] = curve[dt]
    yms = sorted(me)
    return {yms[i]: me[yms[i]]/me[yms[i-1]]-1 for i in range(1, len(yms))}

eng = {}
eng["HG"] = monthly(json.load(open(f"{SC}/curvemax-HG.json")))
eng["SLEEVE"] = monthly(json.load(open(f"{SC}/curvemax-SLEEVE.json")))
eng["KMLM"] = monthly(json.load(open(f"{SC}/curvemax-KMLM.json")))
# HARV: guarded sim 2018-2023 stitched with real (identical-guarded) 2023+
sim = json.load(open(f"{SC}/harv_guard_sim.json"))          # written by sim step
real = monthly(json.load(open(f"{SC}/curve-harv-guarded.json")))
harv = dict(sim)
harv.update(real)
eng["HARV"] = harv

buckets = {k: {reg: [] for reg in freq} for k in eng}
for k, m in eng.items():
    for ym, ret in m.items():
        if ym in regime: buckets[k][regime[ym]].append((ym, ret))
for k in eng:
    print(k, {reg: len(v) for reg, v in buckets[k].items()})

donor_months = {reg: sorted({ym for ym, _ in buckets["HG"][reg]}) for reg in freq}

def draw_month(reg, rng, conservative):
    m_star = rng.choice(donor_months[reg])
    out = {}
    for k in eng:
        b = buckets[k][reg]
        if conservative and k == "KMLM" and reg in ("CRASH", "CHOP"):
            b = buckets["HG"][reg]
        hit = dict(b).get(m_star) if not (conservative and k == "KMLM" and reg in ("CRASH","CHOP")) else None
        out[k] = hit if hit is not None else rng.choice(b)[1]
    return out

def run(weights, K=800, conservative=False, seq=None, seed=11):
    rng = random.Random(seed)
    seq = seq or [regime[m] for m in months]
    cagrs, mdds = [], []
    for _ in range(K):
        cur, peak, mdd = 1.0, 1.0, 0.0
        for reg in seq:
            d = draw_month(reg, rng, conservative)
            r_ = sum(weights[k]*d[k] for k in weights)
            cur *= (1 + r_)
            peak = max(peak, cur); mdd = max(mdd, 1 - cur/peak)
        cagrs.append(cur**(12/len(seq)) - 1)
        mdds.append(mdd)
    cagrs.sort(); mdds.sort()
    p = lambda a, q: a[int(q*(len(a)-1))]
    return dict(cagr_p05=p(cagrs,.05), cagr_med=p(cagrs,.5), dd_med=p(mdds,.5), dd_p95=p(mdds,.95))

ALLOCS = {
    "current 45/27/27/0":  {"HG":.453,"KMLM":.273,"SLEEVE":.274,"HARV":0},
    "chosen 19/39/27/15":  {"HG":.19,"KMLM":.39,"SLEEVE":.27,"HARV":.15},
    "HG-fund 30/27/27/15": {"HG":.30,"KMLM":.27,"SLEEVE":.27,"HARV":.15},
    "balanced 25/25/27/23":{"HG":.25,"KMLM":.25,"SLEEVE":.27,"HARV":.23},
    "defensive 15/25/27/33":{"HG":.15,"KMLM":.25,"SLEEVE":.27,"HARV":.33},
}
for label, variant in (("AS-MEASURED", False), ("CONSERVATIVE-KMLM", True)):
    print(f"\n=== 55y regime-bootstrap (1971-2026 spine) — {label} ===")
    print(f"{'allocation':24} {'CAGR p05':>9} {'CAGR med':>9} {'DD med':>8} {'DD p95':>8}")
    for name, w in ALLOCS.items():
        s = run(w, conservative=variant)
        print(f"{name:24} {s['cagr_p05']:>+9.1%} {s['cagr_med']:>+9.1%} {s['dd_med']:>8.1%} {s['dd_p95']:>8.1%}")
json.dump({"regime": regime, "months": months, "freq": freq}, open(f"{SC}/spine.json","w"))
