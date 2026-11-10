import json, numpy as np, pandas as pd
ROOT="/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil"
P=pd.read_csv(f"{ROOT}/data/panel.csv",index_col="date",parse_dates=True); P.index=P.index.to_period("M")
EV=json.load(open(f"{ROOT}/data/events.json")); NUM=json.load(open(f"{ROOT}/blocks/event/numbers.json"))
M=lambda s:pd.Period(s,"M"); ON_=[M(x) for x in EV["recession_onsets"]]; USREC=P.usrec.astype(int)
print("=== A. derived-column integrity (recompute from raw) ===")
w=P.wti; o12=100*(w/w.shift(12)-1); print("oil_12m_pct maxabsdiff",(o12-P.oil_12m_pct).abs().max())
ro=w/P.cpi; r12=100*(ro/ro.shift(12)-1); print("real_oil_12m_pct maxabsdiff",(r12-P.real_oil_12m_pct).abs().max())
pp=P.ppi_crude; p12=100*(pp/pp.shift(12)-1); print("ppi_12m maxabsdiff",(p12-P.ppi_crude_12m_pct).abs().max())
lw=np.log(w); m36=lw.shift(1).rolling(36,min_periods=36).max(); nopi=100*np.clip(lw-m36,0,None)
print("nopi36_monthly maxabsdiff",(nopi-P.nopi36_monthly).abs().max(), " first valid mine",nopi.first_valid_index(),"panel",P.nopi36_monthly.first_valid_index())
s12=nopi.rolling(12,min_periods=12).sum(); print("nopi36_sum12 maxabsdiff",(s12-P.nopi36_sum12).abs().max())
lp=np.log(pp); pm36=lp.shift(1).rolling(36,min_periods=36).max(); pn=100*np.clip(lp-pm36,0,None); ps12=pn.rolling(12,min_periods=12).sum()
print("ppi_nopi36_sum12 maxabsdiff",(ps12-P.ppi_nopi36_sum12).abs().max())
sg=P.gs10-P.tb3ms; print("spread_gs maxabsdiff",(sg-P.spread_gs).abs().max())
cf=P.spread_gs.rolling(6,min_periods=6).min()<0.25; cfp=P.curve_flat_gs6m.astype(str).str.lower().eq("true")
print("curve_flat_gs6m mismatches",int((cf!=cfp)[P.spread_gs.rolling(6,min_periods=6).min().notna()].sum()), "panel flat where mine NaN:",int(cfp[P.spread_gs.rolling(6,min_periods=6).min().isna()].sum()))
# any NaN in columns inside 1953-04+?
for c in ["oil_12m_pct","real_oil_12m_pct","nopi36_sum12","spread_gs","curve_flat_gs6m","ppi_crude_12m_pct","ppi_nopi36_sum12"]:
    print(c,"NaN in 1953-04+:",int(P.loc[M("1953-04"):,c].isna().sum()))
# daily 252 check
d=pd.read_csv(f"{ROOT}/data/DCOILWTICO.csv"); d.columns=["date","v"]; d.date=pd.to_datetime(d.date); d=d.dropna().reset_index(drop=True)
d["pct"]=100*(d.v/d.v.shift(252)-1); d["m"]=d.date.dt.to_period("M"); last=d.groupby("m").tail(1).set_index("m")["pct"]
cmpd=pd.concat([last,P.wti_daily_252_pct],axis=1).dropna(); print("wti_daily_252_pct maxabsdiff vs my last-print/252-back:",(cmpd.iloc[:,0]-cmpd.iloc[:,1]).abs().max())
print("live: 2026-09-09 print",d.v.iloc[-1],"252 obs back",d.v.iloc[-253],d.date.iloc[-253].date(),"pct",d.pct.iloc[-1])
print("last USREC print month",P.usrec.last_valid_index())
