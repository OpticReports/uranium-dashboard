"""Independent recomputation for the regime_petro block audit."""
import json, math
import numpy as np, pandas as pd
from scipy import stats
ROOT="/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil"
P=pd.read_csv(f"{ROOT}/data/panel.csv",index_col="date",parse_dates=True); P.index=P.index.to_period("M")
T=pd.read_csv(f"{ROOT}/data/tic_oil_exporters.csv",index_col="date",parse_dates=True); T.index=T.index.to_period("M")
N=json.load(open(f"{ROOT}/blocks/regime_petro/numbers.json"))
M=lambda s: pd.Period(s,"M")
onsets=[M(x) for x in json.load(open(f"{ROOT}/data/events.json"))["recession_onsets"]]
print("=== 0. panel sanity")
print("last panel month", P.index[-1], "custody zeros", int((P.custody_bn==0).sum()), "custody nan", int(P.custody_bn.isna().sum()))
c12=P.custody_12m_pct.replace([np.inf,-np.inf],np.nan)
print("custody_12m raw inf count", int(np.isinf(P.custody_12m_pct.fillna(0)).sum()), "first finite", c12.dropna().index[0], "-100 count", int((c12==-100).sum()))
print("usd_12m first/last", P.usd_12m_pct.dropna().index[0], P.usd_12m_pct.dropna().index[-1], "nan in 1986+:", int(P.loc["1986-01":,"usd_12m_pct"].isna().sum()))
print("oil_12m nan 1986+:", int(P.loc["1986-01":,"oil_12m_pct"].isna().sum()))
# does oil_12m_pct equal wti pct_change(12)?
chk=(P.wti.pct_change(12)*100 - P.oil_12m_pct).abs().max(); print("oil_12m_pct == wti pct_change(12): maxdiff", chk)
# is igrea_12m_chg diff(12)?
print("igrea_12m == diff12 maxdiff", (P.igrea.diff(12)-P.igrea_12m_chg).abs().max(), "igrea first", P.igrea.dropna().index[0])

print("\n=== 1. D1-RED episodes per SPEC-LITERAL rule (USREC=0 ON months only, merge <=6 OFF)")
on=(P.oil_12m_pct>=50).fillna(False)
on0=on & (P.usrec==0)
idx=list(on0[on0].index); runs=[[idx[0]]]
for t in idx[1:]:
    if (t-runs[-1][-1]).n-1<=6: runs[-1].append(t)
    else: runs.append([t])
lit=[(str(r[0]),str(r[-1]),len(r)) for r in runs]
print("spec-literal episodes:", lit)
# ALL-ON runs (block's construction)
idx=list(on[on].index); runsA=[[idx[0]]]
for t in idx[1:]:
    if (t-runsA[-1][-1]).n-1<=6: runsA[-1].append(t)
    else: runsA.append([t])
print("all-ON runs:", [(str(r[0]),str(r[-1]),len(r)) for r in runsA])
blk=[(e["start"],e["raw_span"],e["n_on0"],e["outcome_h12"]) for e in N["episodes_D1RED"]["value"]]
print("block episodes:", blk)
# in-recession ON months 1980-08..1981-07 and 1980-09..1980-12 check
print("ON months 1980-08..1981-12:", [str(t) for t in on.loc["1980-08":"1981-12"][on.loc["1980-08":"1981-12"]].index])
print("oil_12m 1990-07..1990-12:", P.loc["1990-07":"1990-12","oil_12m_pct"].round(1).to_dict())
print("oil_12m 1973-10..1974-02:", P.loc["1973-10":"1974-02","oil_12m_pct"].round(1).to_dict())
print("oil_12m 2022-01..2022-08:", P.loc["2022-01":"2022-08","oil_12m_pct"].round(1).to_dict())
print("usrec 2020-01..2020-07:", P.loc["2020-01":"2020-07","usrec"].to_dict())

print("\n=== 2. supply/demand rule + IGREA recompute")
DIS={"1973-10":"embargo","1978-11":"Iran","1980-09":"Iran-Iraq","1990-08":"Kuwait","2002-12":"Venezuela","2003-03":"Iraq","2011-02":"Libya","2019-09":"Abqaiq","2022-02":"Ukraine"}
ig12=P.igrea_12m_chg
for e in N["episodes_D1RED"]["value"]:
    s=M(e["start"]); near=[d for d in DIS if M(d)<=s<=M(d)+3]
    # alt reading: strictly after, (d, d+3]
    near_strict=[d for d in DIS if M(d)<s<=M(d)+3]
    w=ig12.loc[:s].iloc[-120:].dropna()
    # exclusive-of-start alternative: 120 months ending s-1
    w2=ig12.loc[:s-1].iloc[-120:].dropna()
    igc = None if s not in ig12.index or pd.isna(ig12.get(s)) or len(w)<60 else ("demand" if ig12[s]>w.median() else "supply")
    igc2 = None if len(w2)<60 or pd.isna(ig12.get(s)) else ("demand" if ig12[s]>w2.median() else "supply")
    print(e["start"], "supply" if near else "demand", "| strict-after:", "supply" if near_strict else "demand", "| igrea:", igc, f"(n={len(w)}, med={w.median() if len(w) else float('nan'):.1f}, val={ig12.get(s,float('nan')):.1f})", "| igrea excl-start:", igc2)

print("\n=== 3. correlations by regime, recompute + seed/block sensitivity")
REG={"R1":("1986-01","2008-12"),"R2":("2009-01","2019-12"),"R3":("2020-01","2026-08")}
def bb(x,y,blk=12,draws=1000,seed=20260915):
    rng=np.random.default_rng(seed); n=len(x); nb=math.ceil(n/blk); out=[]
    for _ in range(draws):
        st=rng.integers(0,n-blk+1,size=nb); ii=np.concatenate([np.arange(s,s+blk) for s in st])[:n]
        out.append(np.corrcoef(x[ii],y[ii])[0,1])
    return np.percentile(out,[5,95])
# circular / stationary alternative
def sb(x,y,blk=12,draws=2000,seed=1):
    rng=np.random.default_rng(seed); n=len(x); out=[]
    for _ in range(draws):
        ii=[]; 
        while len(ii)<n:
            s=rng.integers(0,n); L=rng.geometric(1/blk); ii+= [ (s+k)%n for k in range(L)]
        ii=np.array(ii[:n]); out.append(np.corrcoef(x[ii],y[ii])[0,1])
    return np.percentile(out,[5,95])
P2=P.copy(); P2.loc[P2.custody_bn==0,"custody_bn"]=np.nan; P2["custody_12m_pct"]=c12
for pair,col in [("oil_usd","usd_12m_pct"),("oil_custody","custody_12m_pct")]:
    for rg,(a,b) in REG.items():
        if pair=="oil_custody" and rg=="R1": continue
        d=P2.loc[a:b,["oil_12m_pct",col]].dropna(); x,y=d.iloc[:,0].values,d.iloc[:,1].values
        pr=np.corrcoef(x,y)[0,1]; sr=stats.spearmanr(x,y).statistic
        ci=bb(x,y); ci2=bb(x,y,seed=7); ci24=bb(x,y,blk=24); cis=sb(x,y)
        k=f"{pair}_{rg}"
        print(f"{k}: n={len(d)} ({d.index[0]}..{d.index[-1]}) pearson={pr:+.4f} spearman={sr:+.4f} | block: {N[k+'_pearson']['value']:+.4f} ci {N[k+'_pearson_ci']['value']} | mine seed20260915 {ci.round(3)} seed7 {ci2.round(3)} blk24 {ci24.round(3)} stationary {cis.round(3)}")
        # fisher-z naive CI with effective n = n/12
        ne=len(d)/12; z=np.arctanh(pr); se=1/np.sqrt(max(ne-3,1)); print(f"   fisher-z with n_eff={ne:.1f}: [{np.tanh(z-1.645*se):+.2f},{np.tanh(z+1.645*se):+.2f}]")
# R3 sensitivity: drop 2020-2021 COVID rebound months
d=P2.loc["2020-01":"2026-08",["oil_12m_pct","usd_12m_pct"]].dropna()
for lo in ["2020-01","2021-01","2022-01","2022-07"]:
    dd=d.loc[lo:]; print(f"R3 oil-usd from {lo}: n={len(dd)} pearson={np.corrcoef(dd.iloc[:,0],dd.iloc[:,1])[0,1]:+.3f} spearman={stats.spearmanr(dd.iloc[:,0],dd.iloc[:,1]).statistic:+.3f}")
# level correlation / lag check: contemporaneous vs oil leading usd by 0..
print("R3 winsorised oil [-100,100] pearson:", np.corrcoef(d.iloc[:,0].clip(-100,100),d.iloc[:,1])[0,1].round(3))

print("\n=== 4. H4a recompute")
def annual(col,lo,hi):
    s=T[col].dropna(); s=s[(s.index>=M(lo))&(s.index<=M(hi))]
    dec=s[s.index.month==12]; rows=[]
    for p in dec.index:
        q=p-12
        if q in dec.index: rows.append((str(p),float(dec[p]-dec[q]),float(P.wti[p]/P.wti[q]-1)*100))
    return pd.DataFrame(rows,columns=["m","dsh","oil"])
for seg,col,lo,hi in [("seg1","seg1_share_pct","2000-03","2011-12"),("seg2","seg2_share_pct","2012-01","2025-12"),("norway","norway_share_pct","2003-01","2025-12")]:
    a=annual(col,lo,hi); pr=stats.pearsonr(a.oil,a.dsh); sr=stats.spearmanr(a.oil,a.dsh)
    print(seg, "n",len(a), a.m.iloc[0], a.m.iloc[-1], f"pearson {pr.statistic:+.4f} spearman {sr.statistic:+.4f} | block {N['h4a_'+seg+'_pearson']['value']:+.4f} / {N['h4a_'+seg+'_spearman']['value']:+.4f}")
    # alt: use panel oil_12m_pct at Dec (should be same), and $-level change instead of share
# alternative H4a specs (sensitivity, not the test): June obs; $bn change; lagged share (oil t-1 -> share t)
for seg,col,lo,hi in [("seg1","seg1_share_pct","2000-03","2011-12"),("seg2","seg2_share_pct","2012-01","2025-12")]:
    s=T[col].dropna(); s=s[(s.index>=M(lo))&(s.index<=M(hi))]
    for mth in [6,12]:
        pts=s[s.index.month==mth]; rows=[]
        for p in pts.index:
            q=p-12
            if q in pts.index: rows.append((float(pts[p]-pts[q]),float(P.wti[p]/P.wti[q]-1)*100, float(P.wti[q]/P.wti[q-12]-1)*100 if (q-12) in P.index else np.nan))
        a=pd.DataFrame(rows,columns=["dsh","oil","oil_lag"])
        print(f"  {seg} month={mth}: n={len(a)} contemporaneous r={np.corrcoef(a.oil,a.dsh)[0,1]:+.3f}; oil lagged 1y r={np.corrcoef(a.oil_lag[a.oil_lag.notna()],a.dsh[a.oil_lag.notna()])[0,1]:+.3f} (n={a.oil_lag.notna().sum()})")
# monthly overlapping corr, for context
for seg,col,lo,hi in [("seg1","seg1_share_pct","2000-03","2011-12"),("seg2","seg2_share_pct","2012-01","2025-12")]:
    s=T[col].dropna(); s=s[(s.index>=M(lo))&(s.index<=M(hi))]; ds=s.diff(12).dropna(); o=P.oil_12m_pct.reindex(ds.index)
    print(f"  {seg} monthly overlapping 12m-change corr r={np.corrcoef(o,ds)[0,1]:+.3f} n={len(ds)}")
print("leg3 seg2 share 2021-12,2022-12:", T.seg2_share_pct[M("2021-12")], T.seg2_share_pct[M("2022-12")])
print("leg3 alt windows: 2022-02->2023-02", T.seg2_share_pct[M("2022-02")], T.seg2_share_pct[M("2023-02")], "; 2022-06->2023-06", T.seg2_share_pct[M("2022-06")], T.seg2_share_pct[M("2023-06")])
print("seg2 $bn 2021-12,2022-12:", T.basket3[M("2021-12")], T.basket3[M("2022-12")], "grand", T.grand_total[M("2021-12")], T.grand_total[M("2022-12")])
print("Norway zeros/near-zero pre-2012:", int((T.norway.loc[:"2011-12"]==0).sum()), "n norway obs", int(T.norway.notna().sum()))
print("Norway 2005 rows exist?", T.loc["2005-01":"2005-12","norway"].notna().sum(), "grand_total 2005-12", T.grand_total[M("2005-12")])

print("\n=== 5. 3(iii) response windows")
def resp(a,b):
    return {c: round((P[c][M(b)]/P[c][M(a)]-1)*100,2) for c in ["indpro","payems"]}
for a,b in [("2021-03","2022-03"),("2022-02","2023-02"),("2022-03","2023-03"),("2022-06","2023-06"),("1974-01","1975-01"),("1973-12","1974-12"),("1990-09","1991-09"),("1990-08","1991-08"),("2002-12","2003-12"),("1979-08","1980-08"),("1980-09","1981-09")]:
    print(a,"->",b,resp(a,b))
print("2021-03..2022-06 raw span; 2022-02 is month", (M("2022-02")-M("2021-03")).n, "of the episode")

print("\n=== 6. custody named episodes")
for a,b in [("2014-06","2016-02"),("2022-02","2022-12")]:
    print(a,b,"custody",round(P2.custody_bn[M(a)],1),round(P2.custody_bn[M(b)],1),round((P2.custody_bn[M(b)]/P2.custody_bn[M(a)]-1)*100,3),"wti",round((P.wti[M(b)]/P.wti[M(a)]-1)*100,1),"seg2",round(T.seg2_share_pct[M(a)],3),round(T.seg2_share_pct[M(b)],3))
