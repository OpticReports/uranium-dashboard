import json, numpy as np, pandas as pd
ROOT="/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil"
P=pd.read_csv(f"{ROOT}/data/panel.csv",index_col="date",parse_dates=True); P.index=P.index.to_period("M"); M=lambda s:pd.Period(s,"M")
NUM=json.load(open(f"{ROOT}/blocks/event/numbers.json")); USREC=P.usrec.astype(int)
g=lambda v:2 if v>=50 else 1 if v>=25 else 0
b=P.loc[M("1987-01"):,["oil_12m_pct","wti_daily_252_pct"]].dropna(); gm=b.oil_12m_pct.map(g); gd=b.wti_daily_252_pct.map(g)
print("IA D1: n",len(b),"3-grade",round((gm==gd).mean(),4),"onoff",round(((gm==2)==(gd==2)).mean(),4),"live-red/panel-not",int(((gd==2)&(gm!=2)).sum()),"reverse",int(((gm==2)&(gd!=2)).sum()))
c=P.loc[M("1982-01"):,["curve_flat_gs6m","curve_flat_daily183"]].dropna(); cm=c.curve_flat_gs6m.astype(str).str.lower().eq("true"); cd=c.curve_flat_daily183.astype(float)==1
print("IA curve: n",len(c),"agree",round((cm==cd).mean(),4),"daily-only",int((cd&~cm).sum()),"monthly-only",int((cm&~cd).sum()))
fc=P.spread_cmt.rolling(6,min_periods=6).min()<0.25; fg=P.spread_gs.rolling(6,min_periods=6).min()<0.25; ok=P.spread_cmt.rolling(6,min_periods=6).min().notna()
print("IA cmt: n",int(ok.sum()),"disagree",int((fc[ok]!=fg[ok]).sum()),"cmt-only",int((fc[ok]&~fg[ok]).sum()))
# also: CMT vs GS using the panel's spread_cmt from 1982-01 with min_periods=1 (spec's 17?)
fc1=P.spread_cmt.rolling(6,min_periods=1).min()<0.25; ok1=P.spread_cmt.notna(); print("  with min_periods=1 from 1982-01: disagree",int((fc1[ok1]!=fg[ok1]).sum()))
L=M("2026-08"); print("Q5 panel 2026-08: oil_12m",round(P.loc[L,'oil_12m_pct'],4),"real",round(P.loc[L,'real_oil_12m_pct'],4),"nopi12",round(P.loc[L,'nopi36_sum12'],4),"spread_gs",P.loc[L,'spread_gs'],"flat",P.loc[L,'curve_flat_gs6m'],"6m min",round(P.spread_gs.rolling(6).min().loc[L],3))
print("Q5 2026 nopi monthly:",{str(t):round(v,2) for t,v in P.loc[M('2026-01'):,'nopi36_monthly'].items() if v>0}, "sum12 by month:",{str(t):round(v,2) for t,v in P.loc[M('2026-03'):,'nopi36_sum12'].items()})
print("2026-04 spread_gs",P.loc[M('2026-04'),'spread_gs'],"curve_flat_gs6m",P.loc[M('2026-04'),'curve_flat_gs6m'],"daily183",P.loc[M('2026-04'),'curve_flat_daily183'],"spread_cmt",P.loc[M('2026-04'),'spread_cmt'])
# D2 sensitivity: gap rule '<6' and dropping only 2020-03 edge credit
s=P.nopi36_sum12>=10
for gap in (6,5):
    idx=list(s[s].index); runs=[];cur=[]
    for t in idx:
        if cur and (t-cur[-1]).n-1>gap: runs.append(cur);cur=[]
        cur.append(t)
    runs.append(cur)
    print(f"gap<= {gap}: D2 episodes starting 2004-2008:",[(str(r[0]),str(r[-1])) for r in runs if M('2004-01')<=r[0]<=M('2008-12')])
print("2019 D2 ON months & values:",[(str(t),round(P.loc[t,'nopi36_sum12'],2)) for t in P.loc[M('2018-04'):M('2019-06')].index if s[t]])
# 1948-12 comparable-to-Hamilton set (1948-12..2008-01 = Hamilton's 11 postwar recessions)
print("full-window D1-RED h12 recall (block):",NUM["full_D1-RED_h12_recall"]["value"],"1948-12 cat:", NUM["D1-RED_h12_event_categories"]["value"].get("1948-12","(not in common set)"))
