import json, numpy as np, pandas as pd
ROOT="/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil"
P=pd.read_csv(f"{ROOT}/data/panel.csv",index_col="date",parse_dates=True); P.index=P.index.to_period("M")
EV=json.load(open(f"{ROOT}/data/events.json")); NUM=json.load(open(f"{ROOT}/blocks/event/numbers.json"))
M=lambda s:pd.Period(s,"M"); ONSETS=[M(x) for x in EV["recession_onsets"]]; USREC=P.usrec.astype(int)
B1=[M(m) for m,_ in EV["drawdown_starts_B1_running_peak"]]
RES=M("2025-08"); fmt=lambda p:p.strftime("%Y-%m")
DEFS={"D1-RED":("oil_12m_pct",50),"D1-YELLOW":("oil_12m_pct",25),"D2":("nopi36_sum12",10),"D3-RED":("real_oil_12m_pct",50),"D3-YELLOW":("real_oil_12m_pct",25),"PPI-RED":("ppi_crude_12m_pct",50),"PPI-D2":("ppi_nopi36_sum12",10)}
curve=P.curve_flat_gs6m.astype(str).str.lower().eq("true")
def on(col,th): return (P[col]>=th).fillna(False)

def episodes(onmask, strict):
    """strict=True: build runs from USREC=0 ON months only (in-recession ON = OFF for gap counting).
       strict=False: block's reading (runs on all ON months, membership filtered)."""
    src = onmask & (USREC==0) if strict else onmask
    idx=list(src[src].index); runs=[]; cur=[]
    for t in idx:
        if cur and (t-cur[-1]).n-1>6: runs.append(cur); cur=[]
        cur.append(t)
    if cur: runs.append(cur)
    out=[]
    for r in runs:
        on0=[t for t in r if USREC[t]==0]
        out.append(dict(raw_first=r[0],raw_last=r[-1],on0=on0))
    return out

def score(onmask, events, h, wstart, strict=False, dd=None):
    eps=[e for e in episodes(onmask,strict) if e["raw_first"]>=wstart]
    claimed=set(); res=[]
    for ep in eps:
        hits=[]
        if ep["on0"]:
            for e in events:
                if e in claimed: continue
                o=ep["on0"]
                if dd and e==dd[0]:
                    o=[t for t in o if dd[1]<=t<=dd[2]]
                    if not o: continue
                if o[0]<e<=o[-1]+h: hits.append(e)
        coin=[e for e in events if e<=ep["raw_first"]<=e+3]
        if hits: st="hit"; claimed|=set(hits)
        elif coin: st="coincident"
        elif not ep["on0"]: st="inrec"
        elif ep["on0"][-1]+h>RES: st="pending"
        else: st="fp"
        res.append(dict(ep,status=st,hits=hits,coin=coin))
    return res
def recall(onmask, events, h, dstart, dd=None):
    on0=onmask&(USREC==0); c=[];ev=[]
    for e in events:
        if e-h<dstart: continue
        lo,hi=e-h,e-1
        if dd and e==dd[0]: lo,hi=max(lo,dd[1]),min(hi,dd[2])
        ev.append(e)
        if any(on0.get(t,False) for t in pd.period_range(lo,hi,freq="M")): c.append(e)
    return c,ev
def mprec(onmask, events, h, wstart):
    months=[t for t in P.index if t>=wstart and USREC[t]==0 and t+h<=RES]
    pos=lambda t:any(t<e<=t+h for e in events)
    onm=[t for t in months if onmask[t]]
    return sum(map(pos,onm)),len(onm),sum(map(pos,months)),len(months)
DD=(M("1981-08"),M("1980-08"),M("1981-07")); CW=M("1953-04"); CO=[e for e in ONSETS if e>=M("1953-08")]
def cmp(k,mine):
    b=NUM.get(k,{}).get("value","<missing>")
    flag="" if (b==mine or (isinstance(b,float) and isinstance(mine,float) and abs(b-mine)<1e-3)) else "   <<<< MISMATCH"
    print(f"  {k}: block={b} mine={mine}{flag}")
print("=== B. NBER common-window scoring, block reading (strict=False) vs numbers.json ===")
for h in (12,18):
    for name,(col,th) in DEFS.items():
        o=on(col,th); se=score(o,ONSETS,h,CW,False,DD)
        hits=[e for e in se if e["status"]=="hit"]; fps=[e for e in se if e["status"]=="fp"]; coin=[e for e in se if e["status"]=="coincident"]; pend=[e for e in se if e["status"]=="pending"]
        c,ev=recall(o,CO,h,P[col].first_valid_index(),DD); np_,non,bp,bn=mprec(o,ONSETS,h,CW)
        pre=f"{name}_h{h}"; print(name,h)
        cmp(f"{pre}_hits",len(hits)); cmp(f"{pre}_false_positives",len(fps)); cmp(f"{pre}_coincident",len(coin)); cmp(f"{pre}_pending",len(pend))
        cmp(f"{pre}_recall_caught",len(c)); cmp(f"{pre}_recall_evaluable",len(ev))
        cmp(f"{pre}_month_precision",round(np_/non,4)); cmp(f"{pre}_month_precision_n_on",non); cmp(f"{pre}_base_rate",round(bp/bn,4))
        cmp(f"{pre}_false_positive_names",[fmt(e["on0"][0]) for e in fps])
        cmp(f"{pre}_hit_names",[f"{fmt(e['on0'][0])}→{','.join(fmt(x) for x in e['hits'])}" for e in hits])
        cmp(f"{pre}_coincident_names",[f"{fmt(e['raw_first'])}~{','.join(fmt(x) for x in e['coin'])}" for e in coin])
print("\n=== C. STRICT reading (in-recession ON months treated as OFF for episode building), h=12, NBER common window ===")
for name,(col,th) in DEFS.items():
    o=on(col,th); se=score(o,ONSETS,12,CW,True,DD)
    hits=[e for e in se if e["status"]=="hit"]; fps=[e for e in se if e["status"]=="fp"]; coin=[e for e in se if e["status"]=="coincident"]; pend=[e for e in se if e["status"]=="pending"]
    print(f"  {name}: hits {len(hits)} [{', '.join(fmt(e['on0'][0])+'→'+','.join(map(fmt,e['hits'])) for e in hits)}]; FP {len(fps)} [{', '.join(fmt(e['on0'][0]) for e in fps)}]; coincident {len(coin)} [{', '.join(fmt(e['raw_first']) for e in coin)}]; pending {len(pend)}")
print("\n=== D. D2 2004-05..2009-04 episode anatomy (nopi36_sum12 >= 10 pattern) ===")
s=P.loc[M("2004-01"):M("2009-06"),"nopi36_sum12"]; o=(s>=10)
off=[fmt(t) for t in s.index if not o[t]]; print("  OFF months 2004-01..2009-06:",off)
print("  ON months 2004-05..2007-12 count:",int(o.loc[M('2004-05'):M('2007-12')].sum()))
print("\n=== E. Recall with 1953-08 EXCLUDED (common-window reading: e-h must be >= 1953-04) ===")
for name,(col,th) in DEFS.items():
    o=on(col,th); c,ev=recall(o,CO,12,CW,DD); print(f"  {name}: {len(c)}/{len(ev)}")
print("\n=== F. §5 curve-conditioned, NBER 10 onsets, 1953-09+ ===")
CS=M("1953-09"); CON=[e for e in ONSETS if e>=M("1957-09")]
RULES={"curve_flat_alone":curve,"D1-RED_alone":on("oil_12m_pct",50),"D1-RED_AND_curve_flat":on("oil_12m_pct",50)&curve,"D2_alone":on("nopi36_sum12",10),"D2_AND_curve_flat":on("nopi36_sum12",10)&curve,"D3-RED_alone":on("real_oil_12m_pct",50),"D3-RED_AND_curve_flat":on("real_oil_12m_pct",50)&curve}
for evn,(events,dd,dstart_events) in {"NBER":(CON,DD,None),"B1":(B1,None,None)}.items():
    for h in (12,):
        for k,o in RULES.items():
            se=score(o,events,h,CS,False,dd); hits=[e for e in se if e["status"]=="hit"]; fps=[e for e in se if e["status"]=="fp"]
            ds=CS if "curve" in k else P[DEFS[k.split("_")[0]][0]].first_valid_index(); ds=max(ds,CS)
            c,ev=recall(o,events,h,ds,dd); np_,non,bp,bn=mprec(o,events,h,CS)
            key=f"curve5_{evn}_{k}_h{h}"; print(f"{evn} {k} h{h}")
            cmp(f"{key}_month_precision",round(np_/non,4) if non else None); cmp(f"{key}_base",round(bp/bn,4)); cmp(f"{key}_hits",len(hits)); cmp(f"{key}_false_positives",len(fps)); cmp(f"{key}_recall",f"{len(c)}/{len(ev)}")
print("\n=== G. Curve-alone catch set vs oil+curve catch set (does oil add any onset?) ===")
cc,_=recall(curve,CON,12,CS,DD); print("  curve alone caught:",[fmt(x) for x in cc])
for k in ("D1-RED_AND_curve_flat","D2_AND_curve_flat","D1-RED_alone","D2_alone"):
    c,_=recall(RULES[k],CON,12,CS,DD); print(f"  {k} caught:",[fmt(x) for x in c],"outside curve set:",[fmt(x) for x in c if x not in cc])
print("\n=== H. 1990-08 D2: any USREC=0 ON month in [1989-08,1990-07]? ===")
o=on("nopi36_sum12",10); print("  ", [fmt(t) for t in pd.period_range(M("1989-08"),M("1990-07"),freq="M") if o[t]], "nopi sum12 1990-07/08:",round(P.loc[M("1990-07"),"nopi36_sum12"],2),round(P.loc[M("1990-08"),"nopi36_sum12"],2))
print("\n=== I. 2020-03 D2: ON months in [2019-03,2020-02] ===")
print("  ", [(fmt(t),round(P.loc[t,'nopi36_sum12'],2)) for t in pd.period_range(M("2019-01"),M("2020-02"),freq="M") if o[t]])
print("\n=== J. Regime R3 rows: base rate & month counts ===")
for R,(lo,hi) in {"R3":(M("2020-01"),M("2024-08"))}.items():
    months=[t for t in P.index if lo<=t<=hi and USREC[t]==0]; pos=[t for t in months if any(t<e<=t+12 for e in ONSETS)]
    print("  R3 resolved USREC=0 months",len(months),"positives",[fmt(t) for t in pos],"base",round(len(pos)/len(months),4),"block",NUM["regime_R3_h12_base"]["value"])
print("\n=== K. 2022 FP at h=18 resolvedness: D2 2021-10 episode last0 ===")
se=score(on("nopi36_sum12",10),ONSETS,18,CW,False,DD); e22=[e for e in se if e["raw_first"]==M("2021-10")][0]; print("  last0",fmt(e22["on0"][-1]),"+18 =",fmt(e22["on0"][-1]+18),"status",e22["status"])
