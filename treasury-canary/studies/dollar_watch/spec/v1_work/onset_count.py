"""SPEC v1 §5 forward onset rule, run AS WRITTEN on 2000-01..2026-10 (pre-committed check §5.4).
Dates, markers and subtype flags only. Usage: python3 -I onset_count.py RAWDIR FEDJSON OUTJSON"""
import csv, json, sys, bisect, math, datetime as dt
import numpy as np
RAW, FED, OUT = sys.argv[1:4]
def fred(s):
    o=[]
    for r in csv.DictReader(open(f"{RAW}/{s}.csv")):
        v=r[s]
        if v not in ("", "."): o.append((r["observation_date"], float(v)))
    return o
def ym(d): return d[:7]
def add_m(m,k):
    y,mm=int(m[:4]),int(m[5:7]); t=y*12+mm-1+k; return f"{t//12:04d}-{t%12+1:02d}"
months=[]; m="2000-01"
while m<="2026-10": months.append(m); m=add_m(m,1)
trip={m:{} for m in months}
# 1 VIX
for d,v in fred("VIXCLS"):
    if ym(d) in trip and v>=40: trip[ym(d)].setdefault("1_vix",(d,v))
# 2 OFR FSI
fsi=[(r["Date"],float(r["OFR FSI"])) for r in csv.DictReader(open(f"{RAW}/fsi.csv")) if r["OFR FSI"] not in ("",".")]
fsi.sort(); fd=[d for d,_ in fsi]; fv=np.array([v for _,v in fsi])
above=[]
for i,(d,v) in enumerate(fsi):
    dd=dt.date.fromisoformat(d); start=dd.replace(year=dd.year-5) if not (dd.month==2 and dd.day==29) else dd.replace(year=dd.year-5,day=28)
    j0=bisect.bisect_left(fd,start.isoformat()); prior=fv[j0:i]
    if i<250 or len(prior)<250 and j0==0 and i<250: above.append(None); continue
    if len(prior)<250: above.append(None); continue
    p95=float(np.percentile(prior,95)); above.append((v>p95,p95))
for i in range(4,len(fsi)):
    w=above[i-4:i+1]
    if all(x is not None and x[0] for x in w) and ym(fd[i]) in trip:
        trip[ym(fd[i])].setdefault("2_ofr",(fd[i],float(fv[i]),round(above[i][1],3)))
first_ofr_eval=next(fd[i] for i,x in enumerate(above) if x is not None)
# 3 EM FX basket
ids=["DEXBZUS","DEXMXUS","DEXSFUS","DEXINUS","DEXKOUS","DEXTHUS","DEXCHUS","DEXMAUS"]
legs={s:fred(s) for s in ids}
days=sorted({d for s in ids for d,_ in legs[s] if d>="1995-01-03"})
def asof(ps,d):
    i=bisect.bisect_right(ps,(d,float("inf")))-1; return ps[i][1] if i>=0 else None
bk=[]
for d in days:
    vals=[asof(legs[s],d) for s in ids]
    if all(v is not None and v>0 for v in vals): bk.append((d,math.exp(sum(math.log(v) for v in vals)/8)))
for i in range(63,len(bk)):
    d,v=bk[i]
    if ym(d) in trip and v/bk[i-63][1]-1>=0.10: trip[ym(d)].setdefault("3_emfx",(d,round(100*(v/bk[i-63][1]-1),1)))
# 4 S&P
spx=[(r["date"],float(r["close"])) for r in csv.DictReader(open(f"{RAW}/spx_daily.csv"))]
sv=[v for _,v in spx]
for i in range(251,len(spx)):
    d,v=spx[i]
    if ym(d) in trip:
        hi=max(sv[i-251:i+1])
        if v<=0.80*hi: trip[ym(d)].setdefault("4_spx",(d,round(100*(v/hi-1),1)))
# 5 Fed
fedj=json.load(open(FED))
for a in fedj["actions"]:
    if ym(a["date"]) in trip: trip[ym(a["date"])].setdefault("5_fed",(a["date"],a["url"]))
# onsets
onsets=[]; last=None
for m in months:
    if len(trip[m])>=2 and (last is None or months.index(m)-months.index(last)>12):
        onsets.append(m); last=m
# subtype
swpt=fred("SWPT"); cp=dict(fred("DCPF3M")); tb=dict(fred("DTB3"))
spr=[(d,cp[d]-tb[d]) for d in sorted(cp) if d in tb]
spr5=[(spr[i][0],sum(x for _,x in spr[i-4:i+1])/5) for i in range(4,len(spr))]
res=[]
for m in onsets:
    win={m,add_m(m,1),add_m(m,2)}
    sw=[(d,v) for d,v in swpt if ym(d) in win and v>50000]
    c5=[(d,round(v,2)) for d,v in spr5 if ym(d) in win and v>1.00]
    sw_avail=any(ym(d) in win for d,_ in swpt)
    res.append({"onset":m,"markers":{k:v for k,v in sorted(trip[m].items())},
                "dollar_funding_subtype":bool(sw or c5),
                "subtype_evidence":{"swpt_gt_50bn_first":sw[0] if sw else None,"swpt_available":sw_avail,"cp_bill_5d_gt_1pp_first":c5[0] if c5 else None}})
two=[m for m in months if len(trip[m])>=2]
out={"rule":"SPEC v1 §5.1-5.3 as pre-committed","window":"2000-01..2026-10","n_onsets":len(onsets),
     "bounds":[3,13],"degenerate":not(3<=len(onsets)<=13),"onsets":res,
     "months_with_ge2_markers":two,"months_any_marker":{m:sorted(trip[m]) for m in months if trip[m]},
     "notes":{"ofr_first_evaluable_day":first_ofr_eval,"em_basket_first_day":bk[0][0],"swpt_first":swpt[0][0],
              "spx_source":"Yahoo ^GSPC committed data/spx_daily.csv","ofr_vintage":"fsi.csv fetched 2026-11-02 (current vintage, not as-published)"}}
json.dump(out,open(OUT,"w"),indent=1)
print("n onsets",len(onsets),"degenerate",out["degenerate"])
for r in res: print(r["onset"],sorted(r["markers"]),"DF" if r["dollar_funding_subtype"] else "-",r["subtype_evidence"])
print("months with >=2 markers:",two)
