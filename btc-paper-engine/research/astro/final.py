"""DEFINITIVE pass. The circular-rotation p-values are DISCARDED: verified
invalid for periodic masks (rotation statistic autocorr 0.63 at lag 29 = the
lunar period, so 5000 rotations were ~30 independent draws). Welch t is used
instead - validated against 30 INDEPENDENT lunar rotations, which agreed to
0.001. BH-FDR over the 153 astrological tests; IS/OOS split as the decisive
filter per the pre-registration."""
import csv, json, numpy as np
from scipy import stats

feat=json.load(open("features.json"))
rows=list(csv.DictReader(open("../btc_daily_full.csv")))
close=np.array([float(r["close"]) for r in rows]); ret=np.diff(np.log(close)); n=len(ret)
absret=np.abs(ret)
src=open("battery.py").read().split("# --- statistics")[0]
src=src.replace('json.dump(res','#').replace('print(','#print(')
ns={"__name__":"m"}; exec(compile(src,"masks","exec"),ns)
tests=ns["tests"]; valid=ns["valid"]
half=n//2

out=[]
for name,(fam,mask) in tests.items():
    m=np.asarray(mask,bool)[:n]
    if m.sum()<20 or m.sum()>n-20: continue
    row={"test":name,"family":fam,"n_on":int(m.sum())}
    for key,y in (("ret",ret),("vol",absret)):
        t=stats.ttest_ind(y[m],y[~m],equal_var=False)
        row[f"{key}_edge_bps"]=float((y[m].mean()-y[~m].mean())*1e4)
        row[f"{key}_t"]=float(t.statistic); row[f"{key}_p"]=float(t.pvalue)
        # IS / OOS halves
        for tag,sl in (("is",slice(0,half)),("oos",slice(half,n))):
            mm=m[sl]; yy=y[sl]
            if 10<mm.sum()<len(mm)-10:
                tt=stats.ttest_ind(yy[mm],yy[~mm],equal_var=False)
                row[f"{key}_{tag}_edge"]=float((yy[mm].mean()-yy[~mm].mean())*1e4)
                row[f"{key}_{tag}_p"]=float(tt.pvalue)
            else:
                row[f"{key}_{tag}_edge"]=float("nan"); row[f"{key}_{tag}_p"]=float("nan")
    out.append(row)
json.dump(out,open("final_results.json","w"),indent=1)

A=[r for r in out if r["family"][0] in "ABCDEF"]
G=[r for r in out if r["family"]=="G_control"]; H=[r for r in out if r["family"]=="H_null"]
def bh(rs,key,q=0.10):
    p=np.array([r[key] for r in rs]); o=np.argsort(p); m=len(p)
    ok=p[o]<=q*np.arange(1,m+1)/m
    crit=p[o][np.max(np.where(ok)[0])] if ok.any() else 0.0
    return crit,int(ok.sum() and np.max(np.where(ok)[0])+1)

print("="*80); print("DEFINITIVE RESULTS (Welch t, BH-FDR q=0.10, 15y daily BTC)"); print("="*80)
for key,lbl in (("ret_p","DIRECTION (next-day return)"),("vol_p","VOLATILITY (|next-day return|)")):
    print(f"\n--- {lbl} ---")
    for nm,rs in (("astrology A-F",A),("controls G",G),("nulls H",H)):
        a=sum(r[key]<0.05 for r in rs)
        print(f"   {nm:<16} p<0.05: {a:>3}/{len(rs)} ({100*a/len(rs):5.1f}%)   [chance 5.0%]")
    crit,k=bh(A,key)
    print(f"   BH-FDR q=0.10 -> {k} survivor(s)  (critical p={crit:.5f})")
    kk="ret" if key=="ret_p" else "vol"
    print(f"   {'test':<30}{'n':>5}{'edge':>9}{'t':>7}{'p':>8}{'IS edge':>9}{'IS p':>7}{'OOS edge':>10}{'OOS p':>7}")
    for r in sorted(A,key=lambda x:x[key])[:8]:
        print(f"   {r['test']:<30}{r['n_on']:>5}{r[kk+'_edge_bps']:>9.1f}{r[kk+'_t']:>7.2f}"
              f"{r[key]:>8.4f}{r[kk+'_is_edge']:>9.1f}{r[kk+'_is_p']:>7.3f}"
              f"{r[kk+'_oos_edge']:>10.1f}{r[kk+'_oos_p']:>7.3f}")
print("\n--- headline claims (what Casey asked about) ---")
byn={r["test"]:r for r in out}
print(f"   {'test':<30}{'n':>5}{'ret edge':>10}{'ret p':>8}{'vol edge':>10}{'vol p':>8}")
for w in ["A:full_moon_day","A:full_moon_w1","A:full_moon_w3","A:new_moon_day",
          "A:new_moon_w1","A:waxing","B:mercury_retro","B:mercury_retro_first3",
          "B:mercury_station_w1","B:mercury_cazimi","E:solar_eclipse_w1","E:lunar_eclipse_w1"]:
    r=byn.get(w)
    if r: print(f"   {r['test']:<30}{r['n_on']:>5}{r['ret_edge_bps']:>10.1f}{r['ret_p']:>8.3f}"
                f"{r['vol_edge_bps']:>10.1f}{r['vol_p']:>8.3f}")
print("\n--- known-real controls: does the battery have POWER? ---")
for r in sorted(G,key=lambda x:x["ret_p"])[:4]:
    print(f"   {r['test']:<30}{r['n_on']:>5}{r['ret_edge_bps']:>10.1f}{r['ret_p']:>8.4f}")
