"""Independent re-implementation of the earthquake scoping + stress tests. Reads Ken French files directly."""
import csv, sys, math, json
import numpy as np
RAW=sys.argv[1]
def block(path, marker):
    rows=list(csv.reader(open(path))); i=next(k for k,r in enumerate(rows) if r and marker in r[0])
    names=[h.strip() for h in rows[i+1][1:]]; data={}
    for r in rows[i+2:]:
        if not r or not (r[0].strip().isdigit() and len(r[0].strip())==6): break
        data[r[0].strip()]=[float(x) for x in r[1:]]
    return names,data
names,ret=block(RAW+"/49_Industry_Portfolios.csv","Average Value Weighted Returns -- Monthly")
_,nf=block(RAW+"/49_Industry_Portfolios.csv","Number of Firms in Portfolios")
fr=list(csv.reader(open(RAW+"/F-F_Research_Data_Factors.csv"))); mkt={}
for r in fr:
    if r and r[0].strip().isdigit() and len(r[0].strip())==6 and len(r)>=5: mkt[r[0].strip()]=(float(r[1])+float(r[4]))/100
months=sorted(set(ret)&set(mkt)); T=len(months); N=len(names)
R=np.array([ret[m] for m in months])/100; R[R<=-0.99]=np.nan
NF=np.array([nf[m] for m in months])
M=np.array([mkt[m] for m in months]); PM=np.cumprod(1+M)
P=np.full_like(R,np.nan)
for j in range(N):
    acc=1.0
    for t in range(T):
        if np.isnan(R[t,j]): acc=1.0; continue
        acc*=1+R[t,j]; P[t,j]=acc
def maxdd(x):
    pk=np.maximum.accumulate(x); return float(np.max(1-x/pk))
def ncorr(x,thr):
    """distinct declines >= thr from a running peak; a new count requires a new high in between."""
    pk=x[0]; n=0; armed=True
    for v in x[1:]:
        if v>=pk: pk=v; armed=True
        elif armed and 1-v/pk>=thr: n+=1; armed=False
    return n
# unit tests of both correction counters
sys.path.insert(0,"/dev/null")
exec(open(sys.argv[2]).read().split("W, H, GAP, RUNUP")[0].split("def count_corrections")[1].join(["def count_corrections",""]) if False else "")
src=open(sys.argv[2]).read(); start=src.index("def count_corrections"); end=src.index("W, H, GAP, RUNUP"); ns={}; exec(src[start:end],ns); cc=ns["count_corrections"]
tests={"flat":([100,100,100],0),"one_10":([100,90,100],1),"two_sep":([100,90,101,90,102],2),"same_peak_double_dip":([100,90,99,85,100],1),
       "exact_10":([100,90],1),"9pct":([100,91,100],0),"deep_single":([100,50,60,55,120],1),"end_in_dd":([100,120,100],1),"rise_only":([100,150,200,250],0),
       "dip_then_lower_dip_no_newhigh":([100,85,95,80],1),"three":([100,89,110,98,120,105,130],3),"recover_not_newhigh_then_dip":([100,89,99,89,99],1)}
print("== count_corrections unit tests (scoping fn vs independent fn)")
for k,(seq,exp) in tests.items():
    a=cc(np.array(seq,float),0.10); b=ncorr(np.array(seq,float),0.10); print(f"  {k:32s} expect {exp} scoping {a} indep {b} {'OK' if a==b==exp else 'MISMATCH'}")
def run(W=24,H=24,gap=36,raw_thr=1.0,net_thr=None,net_mode="ratio",min_firms=None,outcome="raw",five_yr=None,merge=False):
    eps=[]; last=[-10**6]*N; sigs={j:[] for j in range(N)}
    for t in range(W,T-1):
        for j in range(N):
            if np.isnan(P[t,j]) or np.isnan(P[t-W,j]): continue
            raw=P[t,j]/P[t-W,j]-1
            if raw<raw_thr: continue
            mg=PM[t]/PM[t-W]
            net=(1+raw)/mg-1 if net_mode=="ratio" else raw-(mg-1)
            if net_thr is not None and net<net_thr: continue
            if min_firms and NF[t,j]<min_firms: continue
            if five_yr is not None:
                if t-60<0 or np.isnan(P[t-60,j]) or P[t,j]/P[t-60,j]-1<five_yr: continue
            if merge:
                sigs[j].append(t); continue
            if t-last[j]<gap: continue
            fut=P[t:min(T,t+H+1),j]
            if np.isnan(fut).any() or len(fut)<13: continue
            futm=PM[t:t+len(fut)]
            win=P[t-W:t+1,j]
            eps.append(dict(ind=names[j],m=months[t],raw=raw,net=net,c10=ncorr(win,.10),vol=float(np.nanstd(R[t-W+1:t+1,j])*math.sqrt(12)),
                            dd=maxdd(fut),ddn=maxdd(fut/futm*futm[0]),nfut=len(fut)-1))
            last[j]=t
    if merge:  # finder-C style: merge signal months with gap<=24 into one episode, date = first signal
        for j,idx in sigs.items():
            if not idx: continue
            starts=[idx[0]]
            for a,b in zip(idx,idx[1:]):
                if b-a>24: starts.append(b)
            for t in starts:
                fut=P[t:min(T,t+H+1),j]
                if np.isnan(fut).any() or len(fut)<13: continue
                futm=PM[t:t+len(fut)]; win=P[t-W:t+1,j]
                eps.append(dict(ind=names[j],m=months[t],raw=P[t,j]/P[t-W,j]-1,c10=ncorr(win,.10),vol=float(np.nanstd(R[t-W+1:t+1,j])*math.sqrt(12)),dd=maxdd(fut),ddn=maxdd(fut/futm*futm[0]),nfut=len(fut)-1))
    return eps
def rate(sel,key="dd"):
    n=len(sel); k=sum(e[key]>=.40 for e in sel); return f"n={n:3d} p={k/n:.2f}" if n else "n=0"
def report(label,eps,key="dd"):
    c0=[e for e in eps if e["c10"]==0]; c1=[e for e in eps if e["c10"]==1]; c2=[e for e in eps if e["c10"]>=2]
    vals=sorted(e["vol"] for e in eps); q1,q2=vals[len(vals)//3],vals[2*len(vals)//3]
    lo=[e for e in eps if e["vol"]<q1]; mid=[e for e in eps if q1<=e["vol"]<q2]; hi=[e for e in eps if e["vol"]>=q2]
    rv=sorted(e["raw"] for e in eps); r1,r2=rv[len(rv)//3],rv[2*len(rv)//3]
    print(f"{label}: all {rate(eps,key)} | corr0 {rate(c0,key)} corr1 {rate(c1,key)} corr>=2 {rate(c2,key)} | vol terciles {rate(lo,key)} {rate(mid,key)} {rate(hi,key)} | raw terciles {rate([e for e in eps if e['raw']<r1],key)} {rate([e for e in eps if r1<=e['raw']<r2],key)} {rate([e for e in eps if e['raw']>=r2],key)}")
    print(f"      within lowvol: corr0 {rate([e for e in lo if e['c10']==0],key)} corr>=1 {rate([e for e in lo if e['c10']>=1],key)} | midvol: {rate([e for e in mid if e['c10']==0],key)} {rate([e for e in mid if e['c10']>=1],key)}")
base=run(); print("\n== BASE replication (raw>=100%, gap36)"); report("A base",base)
strict=[e for e in base if e["net"]>=1.0]; print("  strict subset (ratio net>=100%):",rate(strict), "n_fut<24:",sum(e['nfut']<24 for e in base))
print("\n== STRESS")
report("gap24",run(gap=24)); report("gap12",run(gap=12)); report(">=10 firms",run(min_firms=10)); report("net-of-mkt OUTCOME",base,"ddn")
report("gap24 + >=10 firms + net outcome",run(gap=24,min_firms=10),"ddn")
print("\n== GSY-rule variants (raw>=100 & net>=100)")
report("F ratio-net gap24 (scoping F)",run(gap=24,net_thr=1.0))
report("diff-net gap24",run(gap=24,net_thr=1.0,net_mode="diff"))
report("diff-net gap24 +5y>=50% +10 firms",run(gap=24,net_thr=1.0,net_mode="diff",min_firms=10,five_yr=0.5))
fc=run(net_thr=1.0,net_mode="diff",min_firms=10,five_yr=0.5,merge=True); report("finderC rule (diff-net, 5y, 10 firms, 24m merge)",fc)
print("  finderC-rule episodes:",len(fc),[ (e['ind'],e['m']) for e in fc][:50])
fc2=run(net_thr=1.0,net_mode="diff",min_firms=10,five_yr=None,merge=True); print("  finderC rule without 5y filter: n=",len(fc2), rate(fc2))
fc3=run(net_thr=1.0,net_mode="ratio",min_firms=10,five_yr=0.5,merge=True); print("  finderC rule but ratio-net: n=",len(fc3), rate(fc3))
# base rate
k=n=0
for t in range(0,T-13,12):
    for j in range(N):
        fut=P[t:min(T,t+25),j]
        if np.isnan(fut).any() or len(fut)<13: continue
        n+=1; k+=maxdd(fut)>=.4
print(f"\nunconditional base rate (every 12m): {k}/{n} = {k/n:.3f}")
k=n=0
for t in range(0,T-13):
    for j in range(N):
        fut=P[t:min(T,t+25),j]
        if np.isnan(fut).any() or len(fut)<25: continue
        n+=1; k+=maxdd(fut)>=.4
print(f"unconditional base rate (all months, full 24m horizon): {k}/{n} = {k/n:.3f}")
# finder A KF-calc spot checks on 49-ind file
def ru(ind,m):
    j=names.index(ind); t=months.index(m); return P[t,j]/P[t-24,j]-1
print("\n2-yr run-ups to peak: Telcm 200003 %.0f%%, Chips 200003 %.0f%%, Util 192909 %.0f%%, Oil 198011 %.0f%%"%(100*ru("Telcm","200003"),100*ru("Chips","200003"),100*ru("Util","192909"),100*ru("Oil","198011")))
