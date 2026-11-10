"""Independent audit recompute for block probit_is (written from the spec, not from run.py)."""
import json, warnings
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy.stats import norm, rankdata
warnings.filterwarnings("ignore")
ROOT="/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil"
P=pd.read_csv(f"{ROOT}/data/panel.csv",index_col="date",parse_dates=True)
N=json.load(open(f"{ROOT}/blocks/probit_is/numbers.json"))
K=N["KEY_NUMBERS"]["value"]
OUT={}
u=P["usrec"].astype(int)
# transforms from raw
oil=P["wti"].pct_change(12)*100; oilw=oil.clip(-100,100)
spread=P["gs10"]-P["tb3ms"]
lp=np.log(P["wti"]); nopi=(100*(lp-lp.shift(1).rolling(36,min_periods=36).max())).clip(lower=0); nopi12=nopi.rolling(12,min_periods=12).sum()
ff=P["fedfunds"].diff(12)
es=P["energy_share_pct"]
def lab(h):
    fut=pd.concat([u.shift(-k) for k in range(1,h+1)],axis=1)
    y=(fut.max(axis=1)>=1).astype(float); y[fut.isna().any(axis=1)]=np.nan; return y
def auc(p,y):
    r=rankdata(p); n1=y.sum(); n0=len(y)-n1; return float((r[y==1].sum()-n1*(n1+1)/2)/(n1*n0))
def fit(df,cols,h,hac=True):
    X=sm.add_constant(df[cols],has_constant="add")
    if hac: r=sm.Probit(df["y"],X).fit(method="newton",maxiter=100,disp=0,cov_type="HAC",cov_kwds={"maxlags":h-1})
    else: r=sm.Probit(df["y"],X).fit(method="newton",maxiter=100,disp=0)
    return r
def build(h,target,cols,start="1953-04-01",end=None):
    df=pd.DataFrame({"y":lab(h),"spread":spread,"oilw":oilw,"nopi12":nopi12,"ff":ff,"es":es,"u":u,"oil":oil})
    tmax=pd.Timestamp("2025-08-01")-pd.DateOffset(months=h)
    df=df.loc[start:tmax]
    if end is not None: df=df.loc[:end]
    if target=="B": df=df[df["u"]==0]
    return df.dropna(subset=["y"]+cols)
def dP(params,spread_v,shock=50,oilkey="oilw"):
    e0=params["const"]+params["spread"]*spread_v; return float(norm.cdf(e0+params[oilkey]*shock)-norm.cdf(e0))

# --- headline h=12 fits
res={}
for tg in ("A","B"):
    dA=build(12,tg,["spread"]); ra=fit(dA,["spread"],12)
    db=build(12,tg,["spread","oilw"]); rb=fit(db,["spread","oilw"],12)
    dn=build(12,tg,["spread","nopi12"]); rn=fit(dn,["spread","nopi12"],12)
    de=build(12,tg,["spread","oilw","ff"]); re_=fit(de,["spread","oilw","ff"],12)
    Xa=sm.add_constant(dA[["spread"]]); Xb=sm.add_constant(db[["spread","oilw"]])
    res[tg]={"n_a":len(dA),"npos_a":int(dA.y.sum()),"a_auc":auc(ra.predict(Xa),dA.y.values),"b_auc":auc(rb.predict(Xb),db.y.values),
             "b_oil":float(rb.params["oilw"]),"b_oil_z":float(rb.tvalues["oilw"]),"b_mcf":float(1-rb.llf/rb.llnull),"a_mcf":float(1-ra.llf/ra.llnull),
             "nopi":float(rn.params["nopi12"]),"nopi_z":float(rn.tvalues["nopi12"]),
             "e_oil":float(re_.params["oilw"]),"e_oil_z":float(re_.tvalues["oilw"]),"e_ff":float(re_.params["ff"]),"e_ff_z":float(re_.tvalues["ff"]),"n_e":len(de),
             "a_b0":float(ra.params["const"]),"a_b1":float(ra.params["spread"]),
             "sample":f"{dA.index[0]:%Y-%m}..{dA.index[-1]:%Y-%m}"}
    if tg=="B":
        res[tg]["dP50_s0"]=dP(rb.params,0); res[tg]["dP50_s1"]=dP(rb.params,1)
        pe=re_.params; res[tg]["dPff300_s0"]=float(norm.cdf(pe["const"]+pe["ff"]*3)-norm.cdf(pe["const"]))
        # naive z for comparison (spec says never report; just to see how HAC changes things)
        rb_n=fit(db,["spread","oilw"],12,hac=False); res[tg]["b_oil_z_naive"]=float(rb_n.tvalues["oilw"])
        # HAC with small-sample correction
        X=sm.add_constant(db[["spread","oilw"]]); rc=sm.Probit(db["y"],X).fit(method="newton",maxiter=100,disp=0,cov_type="HAC",cov_kwds={"maxlags":11,"use_correction":True})
        res[tg]["b_oil_z_hac_corr"]=float(rc.tvalues["oilw"])
OUT["h12"]=res
cmp={"IS_b_oil_coef_TargetB_h12":res["B"]["b_oil"],"IS_b_oil_hac_z_TargetB_h12":res["B"]["b_oil_z"],"IS_b_auc_TargetB_h12":res["B"]["b_auc"],"IS_a_auc_TargetB_h12":res["B"]["a_auc"],
     "IS_b_oil_coef_TargetA_h12":res["A"]["b_oil"],"IS_b_oil_hac_z_TargetA_h12":res["A"]["b_oil_z"],"IS_b_nopi_coef_TargetB_h12":res["B"]["nopi"],"IS_b_nopi_hac_z_TargetB_h12":res["B"]["nopi_z"],
     "IS_e_oil_coef_TargetB_h12":res["B"]["e_oil"],"IS_e_oil_hac_z_TargetB_h12":res["B"]["e_oil_z"],"IS_e_ff_coef_TargetB_h12":res["B"]["e_ff"],"IS_e_ff_hac_z_TargetB_h12":res["B"]["e_ff_z"],
     "dP_oil_plus50_spread0_IS":res["B"]["dP50_s0"],"dP_oil_plus50_spread1_IS":res["B"]["dP50_s1"],"dP_ff_plus300bp_spread0_IS":res["B"]["dPff300_s0"],
     "study_a_TargetA_b0_h12":res["A"]["a_b0"],"study_a_TargetA_b1_h12":res["A"]["a_b1"]}
# --- Q3 blocks
q3={}
for k,(s,e) in {"R0R1":("1953-04-01","2008-12-01"),"R2R3":("2009-01-01",None)}.items():
    d=build(12,"B",["spread","oilw"],start=s,end=e); r=fit(d,["spread","oilw"],12)
    X=sm.add_constant(d[["spread","oilw"]])
    # positive regions in CALENDAR months (not filtered index)
    pos=d.index[d.y==1]; regions=[]; 
    for m in pos:
        if regions and (m.year-regions[-1][1].year)*12+m.month-regions[-1][1].month==1: regions[-1][1]=m
        else: regions.append([m,m])
    q3[k]={"sample":f"{d.index[0]:%Y-%m}..{d.index[-1]:%Y-%m}","n":len(d),"npos":int(d.y.sum()),"oil":float(r.params["oilw"]),"oil_z":float(r.tvalues["oilw"]),
           "dP50_s0":dP(r.params,0),"auc":auc(r.predict(X),d.y.values),"calendar_regions":[f"{a:%Y-%m}..{b:%Y-%m}" for a,b in regions],
           "n_oil_nonzero":int((d.oilw!=0).sum()),"converged":bool(r.mle_retvals["converged"])}
q3["ratio"]=q3["R2R3"]["dP50_s0"]/q3["R0R1"]["dP50_s0"]
cmp.update({"Q3_R0R1_oil_coef":q3["R0R1"]["oil"],"Q3_R0R1_oil_hac_z":q3["R0R1"]["oil_z"],"Q3_R0R1_dP_plus50_spread0":q3["R0R1"]["dP50_s0"],"Q3_R0R1_n":q3["R0R1"]["n"],"Q3_R0R1_n_pos":q3["R0R1"]["npos"],
            "Q3_R2R3_oil_coef":q3["R2R3"]["oil"],"Q3_R2R3_oil_hac_z":q3["R2R3"]["oil_z"],"Q3_R2R3_dP_plus50_spread0":q3["R2R3"]["dP50_s0"],"Q3_R2R3_n":q3["R2R3"]["n"],"Q3_R2R3_n_pos":q3["R2R3"]["npos"],"Q3_ratio_R2R3_over_R0R1":q3["ratio"]})
OUT["q3"]=q3
# --- interaction 1959+ (uncentred AND centred, to show the interaction coef is invariant)
d=build(12,"B",["spread","oilw","es"],start="1959-01-01"); m=d.es.mean()
d["ix_c"]=d.oilw*(d.es-m); d["ix_u"]=d.oilw*d.es
rc=fit(d,["spread","oilw","ix_c"],12); ru=fit(d,["spread","oilw","ix_u"],12)
def dPs(p,share,mean): b=p["oilw"]+p["ix_c"]*(share-mean); return float(norm.cdf(p["const"]+b*50)-norm.cdf(p["const"]))
es_now=float(es.dropna().iloc[-1]); es80=float(es.loc["1980-06-01"])
OUT["interaction"]={"n":len(d),"npos":int(d.y.sum()),"mean_share":m,"ix_centred":float(rc.params["ix_c"]),"ix_centred_z":float(rc.tvalues["ix_c"]),
    "ix_uncentred":float(ru.params["ix_u"]),"ix_uncentred_z":float(ru.tvalues["ix_u"]),"oil_main_uncentred":float(ru.params["oilw"]),"oil_main_uncentred_z":float(ru.tvalues["oilw"]),
    "dP_1980":dPs(rc.params,es80,m),"dP_mean":dPs(rc.params,m,m),"dP_now":dPs(rc.params,es_now,m),"es_now":es_now,"es80":es80,
    "share_gt7_months":[f"{i:%Y-%m}" for i in es.index[es>7]][:1]+[f"{i:%Y-%m}" for i in es.index[es>7]][-1:], "n_share_gt7":int((es>7).sum()),
    "share_at_onsets":{f"{o}":(float(es.loc[o]) if pd.notna(es.get(o,np.nan)) else None) for o in ["1960-05-01","1970-01-01","1973-12-01","1980-02-01","1981-08-01","1990-08-01","2001-04-01","2008-01-01","2020-03-01"]}}
cmp.update({"Q3_interaction_coef":float(rc.params["ix_c"]),"Q3_interaction_hac_z":float(rc.tvalues["ix_c"])})
# --- conditional cut
d=build(12,"B",["spread","oil"]); red=d[d.oil>=50]
OUT["cut"]={"gt":{"n":int((red.spread>0.25).sum()),"npos":int(red.y[red.spread>0.25].sum())},"le":{"n":int((red.spread<=0.25).sum()),"npos":int(red.y[red.spread<=0.25].sum()),"months":[f"{i:%Y-%m}" for i in red.index[red.spread<=0.25]]},
    "all":{"n":len(red),"npos":int(red.y.sum())},"base":float(d.y.mean()),"base_gt":float(d.y[d.spread>0.25].mean()),"base_le":float(d.y[d.spread<=0.25].mean())}
cmp.update({"cut_P_onset12_D1RED_spread_gt_0.25":OUT["cut"]["gt"]["npos"]/OUT["cut"]["gt"]["n"],"cut_n_D1RED_spread_gt_0.25":OUT["cut"]["gt"]["n"],"cut_P_onset12_D1RED_spread_le_0.25":OUT["cut"]["le"]["npos"]/OUT["cut"]["le"]["n"],"cut_n_D1RED_spread_le_0.25":OUT["cut"]["le"]["n"]})
# --- correlations
cc={}
for k,(s,e) in {"R0":("1953-04-01","1985-12-01"),"R1":("1986-01-01","2008-12-01"),"R2":("2009-01-01","2019-12-01"),"R3":("2020-01-01","2026-08-01"),"full":("1953-04-01","2026-08-01")}.items():
    dd=pd.DataFrame({"o":oilw,"ou":oil,"s":spread}).loc[s:e].dropna(); cc[k]={"n":len(dd),"w":float(dd.o.corr(dd.s)),"u":float(dd.ou.corr(dd.s))}
# spec's -0.13: what window/transform gives it?
for s,e in [("1953-04-01","2024-08-01"),("1953-04-01","2026-08-01"),("1947-01-01","2026-08-01")]:
    dd=pd.DataFrame({"o":oilw,"ou":oil,"s":spread}).loc[s:e].dropna(); cc[f"alt_{s[:7]}_{e[:7]}"]={"w":float(dd.o.corr(dd.s)),"u":float(dd.ou.corr(dd.s))}
OUT["corr"]=cc
cmp.update({"corr_oil12w_spread_full":cc["full"]["w"],"corr_oil12w_spread_R0":cc["R0"]["w"],"corr_oil12w_spread_R1":cc["R1"]["w"],"corr_oil12w_spread_R2":cc["R2"]["w"],"corr_oil12w_spread_R3":cc["R3"]["w"]})
# R3 narrative check: oil and spread paths 2021-2023
OUT["r3_path"]={f"{i:%Y-%m}":(round(float(oil[i]),1),round(float(spread[i]),2)) for i in pd.date_range("2021-01-01","2023-12-01",freq="3MS")}
# --- D1-RED episodes (spec rule)
on=((oil>=50)&(u==0)).fillna(False); onm=list(P.index[on]); eps=[]
for m_ in onm:
    if eps and (m_.year-eps[-1][1].year)*12+m_.month-eps[-1][1].month-1<=6: eps[-1][1]=m_; eps[-1][2]+=1
    else: eps.append([m_,m_,1])
OUT["episodes"]=[(f"{a:%Y-%m}",f"{b:%Y-%m}",c) for a,b,c in eps]
OUT["oil12_1980_08_to_1981_07"]={f"{i:%Y-%m}":round(float(oil[i]),1) for i in pd.date_range("1980-08-01","1981-07-01",freq="MS")}
OUT["oil12_1990_1991"]={f"{i:%Y-%m}":(round(float(oil[i]),1),int(u[i])) for i in pd.date_range("1990-06-01","1991-06-01",freq="MS")}
OUT["oil12_1973_1974"]={f"{i:%Y-%m}":(round(float(oil[i]),1),int(u[i])) for i in pd.date_range("1973-09-01","1974-03-01",freq="MS")}
# --- "six recessions preceded by shallow inversions" check: min spread in 12m before each pre-1982 onset
OUT["min_spread_pre_onset"]={o:float(spread.loc[pd.Timestamp(o)-pd.DateOffset(months=12):pd.Timestamp(o)-pd.DateOffset(months=1)].min()) for o in ["1953-08-01","1957-09-01","1960-05-01","1970-01-01","1973-12-01","1980-02-01","1981-08-01","1990-08-01","2001-04-01","2008-01-01","2020-03-01"]}
# --- deployed reproduction from raw daily DGS10-DGS3MO, 1981-09+, deployed labels (t+12 <= 2026-08)
def fred(sid):
    s=pd.read_csv(f"{ROOT}/data/{sid}.csv"); s.columns=["date","v"]; s["date"]=pd.to_datetime(s["date"]); s["v"]=pd.to_numeric(s["v"],errors="coerce"); return s.set_index("date")["v"]
d10,d3=fred("DGS10"),fred("DGS3MO"); t10y3m=fred("T10Y3M")
OUT["dgs3mo_first"]=str(d3.dropna().index.min().date()); OUT["t10y3m_first"]=str(t10y3m.dropna().index.min().date())
spd=(d10-d3).dropna().resample("MS").mean()
y12=lab(12)
for start in ("1981-09-01","1982-01-01"):
    df=pd.DataFrame({"y":y12,"s":spd}).loc[start:"2025-08-01"].dropna()
    r=sm.Probit(df.y,sm.add_constant(df[["s"]])).fit(method="newton",maxiter=100,disp=0)
    OUT[f"deployed_repro_dailyspread_{start[:7]}"]={"n":len(df),"npos":int(df.y.sum()),"b0":float(r.params["const"]),"b1":float(r.params["s"]),"auc":auc(r.predict(sm.add_constant(df[["s"]])),df.y.values)}
# also on t10y3m monthly mean from 1982-01 (should equal block's row)
df=pd.DataFrame({"y":y12,"s":t10y3m.dropna().resample("MS").mean()}).loc["1982-01-01":"2025-08-01"].dropna()
r=sm.Probit(df.y,sm.add_constant(df[["s"]])).fit(method="newton",maxiter=100,disp=0)
OUT["deployed_repro_t10y3m_1982"]={"n":len(df),"npos":int(df.y.sum()),"b0":float(r.params["const"]),"b1":float(r.params["s"])}
# --- oil z range across h for the 12m spec (all specs b,c,e both targets)
zs={}
for h in (6,12,18,24):
    for tg in ("A","B"):
        for nm,cols in (("b",["spread","oilw"]),("c",["oilw"]),("e",["spread","oilw","ff"])):
            d=build(h,tg,cols); r=fit(d,cols,h); zs[f"h{h}_{tg}_{nm}"]=round(float(r.tvalues["oilw"]),2)
OUT["oil_z_by_h"]=zs; OUT["oil_z_min_max"]=(min(zs.values()),max(zs.values()))
# --- compare to block
diffs={k:(K[k],v,abs(K[k]-v)) for k,v in cmp.items() if K.get(k) is not None and abs(K[k]-v)>1e-6}
OUT["key_number_diffs_gt_1e-6"]=diffs; OUT["n_keys_compared"]=len(cmp)
json.dump(OUT,open("audit_out.json","w"),indent=1,default=str)
print(json.dumps(OUT,indent=1,default=str))
