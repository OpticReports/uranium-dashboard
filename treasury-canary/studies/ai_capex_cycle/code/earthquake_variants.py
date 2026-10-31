"""Robustness cuts for the earthquake scoping: GSY secondary rule (raw>=50% AND net>=50% over 24m,
24-month merge), exclude rebounds (market max drawdown >=40% in the prior 36 months), outcomes raw and
net-of-market, and the corrections effect WITHIN volatility terciles."""
import csv, json, math, sys, os
import numpy as np
RAW, OUT = sys.argv[1], sys.argv[2]
exec(open(os.path.join(os.path.dirname(__file__), "earthquake_scoping.py")).read().split("W, H, GAP, RUNUP")[0])   # reuse loaders/helpers

def episodes(raw_thr, net_thr, gap, H=24, W=24, excl_rebound=False, min_firms=None):
    eps=[]; last=[-10**6]*N
    for t in range(W, T-1):
        mk_prior_dd = max_dd(PM[max(0,t-36):t+1]) if excl_rebound else 0.0
        for j in range(N):
            if np.isnan(P[t,j]) or np.isnan(P[t-W,j]) or t-last[j] < gap: continue
            raw = P[t,j]/P[t-W,j]-1; net=(1+raw)/(PM[t]/PM[t-W])-1
            if raw < raw_thr or net < net_thr: continue
            if excl_rebound and mk_prior_dd >= 0.40: continue
            win=P[t-W:t+1,j]; fut=P[t:min(T,t+H+1),j]
            if np.isnan(fut).any() or len(fut)<13: continue
            futm=PM[t:t+len(fut)]
            eps.append({"industry":names[j],"month":months[t],"raw24":raw,"net24":net,"corr10":count_corrections(win,0.10),
                        "max_int_dd":max_dd(win),"vol":float(np.nanstd(R[t-W+1:t+1,j])*math.sqrt(12)),
                        "accel":(P[t,j]/P[t-12,j]-1)/raw if raw else None,
                        "fut_maxdd":max_dd(fut),"fut_maxdd_net":max_dd(fut/futm*futm[0])})
            last[j]=t
    return eps

def rate(sel, key="fut_maxdd"):
    n=len(sel); k=sum(e[key]>=0.40 for e in sel); return n, k, (k/n if n else None)

def table(eps, label, key="fut_maxdd"):
    out={"label":label,"n":len(eps)}
    n,k,p=rate(eps,key); out["all"]=(n,k,p)
    out["corr0"]=rate([e for e in eps if e["corr10"]==0],key); out["corr1"]=rate([e for e in eps if e["corr10"]==1],key); out["corr2p"]=rate([e for e in eps if e["corr10"]>=2],key)
    vals=sorted(e["vol"] for e in eps); q1,q2=vals[len(vals)//3],vals[2*len(vals)//3]
    within=[]
    for lo,hi,nm in ((0,q1,"lowvol"),(q1,q2,"midvol"),(q2,9,"highvol")):
        g=[e for e in eps if lo<=e["vol"]<hi]
        within.append((nm, rate([e for e in g if e["corr10"]==0],key), rate([e for e in g if e["corr10"]>=1],key)))
    out["within_vol"]=within
    fd=np.array([e[key] for e in eps]); 
    def sp(a,b): ra=np.argsort(np.argsort(a)); rb=np.argsort(np.argsort(b)); return float(np.corrcoef(ra,rb)[0,1])
    out["spearman"]={f: sp(np.array([e[f] for e in eps],float), fd) for f in ("corr10","max_int_dd","raw24","net24","vol")}
    return out

res=[]
res.append(table(episodes(1.0,-9,36),"A: raw>=100%, gap36 (as scoped)"))
res.append(table(episodes(1.0,-9,36,excl_rebound=True),"B: A minus post-crash rebounds (mkt DD>=40% in prior 36m)"))
res.append(table(episodes(0.5,0.5,24),"C: GSY secondary raw>=50% & net>=50%, gap24"))
res.append(table(episodes(0.5,0.5,24,excl_rebound=True),"D: C minus rebounds"))
res.append(table(episodes(0.5,0.5,24),"E: C, outcome = NET-of-market drawdown","fut_maxdd_net"))
res.append(table(episodes(1.0,1.0,24),"F: GSY primary raw>=100% & net>=100%, gap24"))
for r in res:
    f=lambda x: f"n={x[0]:3d} p={x[2]:.2f}" if x[2] is not None else "n=0"
    print(f"\n{r['label']}  ->  all {f(r['all'])}")
    print(f"   corrections 0: {f(r['corr0'])} | 1: {f(r['corr1'])} | >=2: {f(r['corr2p'])}")
    for nm,a,b in r["within_vol"]: print(f"   within {nm:8s}: 0 corr {f(a)} | >=1 corr {f(b)}")
    print("   spearman", {k:round(v,2) for k,v in r["spearman"].items()})
json.dump(res, open(os.path.join(OUT,"variants.json"),"w"), indent=1, default=float)
