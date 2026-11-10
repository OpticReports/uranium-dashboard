"""Would any of this have MADE MONEY? Trade the folk rules and the best
in-sample hit, long-only vs buy-and-hold, 6bps round-trip taker cost."""
import csv, json, numpy as np
feat=json.load(open("features.json"))
rows=list(csv.DictReader(open("../btc_daily_full.csv")))
close=np.array([float(r["close"]) for r in rows]); ret=np.diff(np.log(close)); n=len(ret)
F={k:np.array([f[k] for f in feat])[:n] for k in feat[0]}
COST=0.0006

def stats_of(pos, name):
    """pos[i] in {0,1} = hold BTC over day i (decided at close of i-1)."""
    turn=np.abs(np.diff(np.concatenate([[0],pos])))
    r=pos*ret - turn*COST
    eq=np.exp(np.cumsum(r)); yrs=n/365.25
    cagr=eq[-1]**(1/yrs)-1
    dd=1-eq/np.maximum.accumulate(eq); mdd=dd.max()
    sharpe=r.mean()/r.std()*np.sqrt(365.25) if r.std()>0 else 0
    return {"name":name,"cagr":100*cagr,"mdd":100*mdd,"sharpe":sharpe,
            "days_in":100*pos.mean(),"trades":int(turn.sum()),"final":eq[-1],"eq":eq}

pa=F["moon_phase_deg"]
res=[]
res.append(stats_of(np.ones(n),"buy & hold"))
# folk rule: buy new moon -> sell full moon (hold the WAXING half)
res.append(stats_of((pa<180).astype(float),"hold waxing (new->full)"))
res.append(stats_of((pa>=180).astype(float),"hold waning (full->new)"))
# avoid the 3 days around full moon
av=np.ones(n); av[F["full_moon_w3"]==1]=0
res.append(stats_of(av,"B&H minus full-moon +/-3d"))
# avoid mercury retrograde
res.append(stats_of((F["retro_mercury"]==0).astype(float),"B&H minus mercury retro"))
res.append(stats_of((F["retro_mercury"]==1).astype(float),"ONLY mercury retro"))
# the best IN-SAMPLE hit: mercury-jupiter square
sep=np.abs(((F["lon_mercury"]-F["lon_jupiter"]+180)%360)-180)
mjs=(np.abs(sep-90)<=6).astype(float)
res.append(stats_of(mjs,"ONLY mercury-jupiter square"))
half=n//2
print(f"{'strategy':<32}{'CAGR%':>9}{'MaxDD%':>9}{'Sharpe':>8}{'%days':>7}{'trades':>8}")
for r in res:
    print(f"{r['name']:<32}{r['cagr']:>9.1f}{r['mdd']:>9.1f}{r['sharpe']:>8.2f}"
          f"{r['days_in']:>7.0f}{r['trades']:>8d}")
# IS vs OOS for the best in-sample hit
print(f"\nIS/OOS split of the strongest in-sample signal (mercury-jupiter square):")
for tag,sl in (("IS  2011-2019",slice(0,half)),("OOS 2019-2026",slice(half,n))):
    m=mjs[sl].astype(bool); y=ret[sl]
    print(f"   {tag}: edge {1e4*(y[m].mean()-y[~m].mean()):+7.1f} bps/day  "
          f"n={m.sum()}")
json.dump({r["name"]:{k:v for k,v in r.items() if k!="eq"} for r in res},
          open("strategy_results.json","w"),indent=1)
np.save("equity.npy",np.array([r["eq"] for r in res]))
np.save("names.npy",np.array([r["name"] for r in res]))
