"""CORRECTED battery (counter-agent 2026-09-04, findings B1/B3/M1).

B1 fix: y[j] = log(close[j]/close[j-1]) = the return OF day j, predicted by
        the ephemeris at 00:00 of day j. Ephemeris is deterministic and
        published years ahead, so this is implementable and lookahead-free.
        The original code tested the syzygy day + 2.
B3 fix: volatility is |z| where z = ret / GARCH(1,1) 1-step-ahead sigma using
        ONLY data through j-1. Raw |ret| made the nulls fire at 43%.
M1 fix: eclipses use ECLIPTIC LATITUDE at syzygy (the node condition), not
        declination. The old mask caught 2 of 13 real lunar eclipses.
"""
import csv, json, math, itertools, datetime
import numpy as np, ephem
from scipy import stats, optimize

feat=json.load(open("features.json"))
rows=list(csv.DictReader(open("../btc_daily_full.csv")))
close=np.array([float(r["close"]) for r in rows]); ts=np.array([int(r["ts"]) for r in rows])
N=len(rows)
y=np.full(N,np.nan); y[1:]=np.diff(np.log(close))      # y[j] = return OF day j
ok=~np.isnan(y)

# ---- GARCH(1,1) causal sigma ---------------------------------------------
r=y[ok]; r=r-r.mean()
def nll(p):
    w,a,b=np.exp(p)
    if a+b>=0.999: return 1e9
    s2=np.empty(len(r)); s2[0]=r.var()
    for i in range(1,len(r)): s2[i]=w+a*r[i-1]**2+b*s2[i-1]
    return 0.5*np.sum(np.log(s2)+r**2/s2)
res=optimize.minimize(nll,np.log([r.var()*0.01,0.1,0.85]),method="Nelder-Mead",
                      options={"maxiter":4000,"xatol":1e-8,"fatol":1e-8})
w,a,b=np.exp(res.x)
s2=np.empty(len(r)); s2[0]=r.var()
for i in range(1,len(r)): s2[i]=w+a*r[i-1]**2+b*s2[i-1]   # s2[i] uses info thru i-1
sig=np.sqrt(s2)
print(f"GARCH(1,1): omega={w:.2e} alpha={a:.3f} beta={b:.3f} persistence={a+b:.4f}")
absz=np.abs(r)/sig                                        # standardised |return|

# ---- rebuild masks at the CORRECT alignment ------------------------------
F={k:np.array([f[k] for f in feat]) for k in feat[0]}
# the flag sits on the bar containing the syzygy; the syzygy CALENDAR DAY is
# that bar - 1, and its own return is y[that day].
def shift(mask, k=-1):
    o=np.zeros(N,bool); idx=np.where(mask)[0]+k
    o[idx[(idx>=0)&(idx<N)]]=True; return o
full_d=shift(F["full_moon_day"]==1); new_d=shift(F["new_moon_day"]==1)
def win(ev,k):
    o=np.zeros(N,bool)
    for j in np.where(ev)[0]: o[max(0,j-k):min(N,j+k+1)]=True
    return o
# ecliptic LATITUDE of the moon -> the real node condition for eclipses
elat=np.empty(N)
for i,t in enumerate(ts):
    m=ephem.Moon(); m.compute(ephem.Date("1970/1/1")+t/86400.0)
    elat[i]=math.degrees(ephem.Ecliptic(m).lat)
elat=np.abs(elat)
lun_ecl=win(full_d,1)&(elat<1.0); sol_ecl=win(new_d,1)&(elat<1.0)
print(f"eclipse masks: lunar n={lun_ecl.sum()}, solar n={sol_ecl.sum()} "
      f"(old declination-based masks: 23 / 30)")

tests={}
def add(fam,name,m):
    m=np.asarray(m,bool)&ok
    if 20<=m.sum()<=ok.sum()-20: tests[name]=(fam,m)
for k,mk in (("full_moon_day",full_d),("new_moon_day",new_d)):
    add("A_lunar",f"A:{k}",mk)
    for w_ in (1,3): add("A_lunar",f"A:{k[:-4]}w{w_}",win(mk,w_))
pa=F["moon_phase_deg"]
add("A_lunar","A:waxing",pa<180); add("A_lunar","A:waning",pa>=180)
for o in range(8): add("A_lunar",f"A:phase_octile_{o}",(pa>=o*45)&(pa<(o+1)*45))
add("A_lunar","A:illum_high",F["moon_illum"]>0.75)
add("A_lunar","A:illum_low",F["moon_illum"]<0.25)
for k in ("perigee_w1","apogee_w1","decl_max_w1","decl_min_w1"):
    add("A_lunar",f"A:{k}",F[k]==1)
for p in ("mercury","venus","mars","jupiter","saturn"):
    rr=F[f"retro_{p}"]==1; fam="B_retro" if p=="mercury" else "C_retro"
    add(fam,f"{fam[0]}:{p}_retro",rr)
    if p=="mercury":
        st=np.zeros(N,bool); s3=np.zeros(N,bool); e3=np.zeros(N,bool)
        pre=np.zeros(N,bool); post=np.zeros(N,bool)
        for i in range(1,N):
            if rr[i] and not rr[i-1]: s3[i:i+3]=True; st[max(0,i-1):i+2]=True; pre[max(0,i-21):i]=True
            if not rr[i] and rr[i-1]: e3[max(0,i-3):i]=True; st[max(0,i-1):i+2]=True; post[i:i+21]=True
        for nm,mk in (("first3",s3),("last3",e3),("station_w1",st),
                      ("preshadow",pre),("postshadow",post)): add("B_retro",f"B:mercury_{nm}",mk)
        sep=np.abs(((F["lon_mercury"]-F["lon_sun"]+180)%360)-180)
        add("B_retro","B:mercury_cazimi",(sep<3)&rr)
PL=["sun","moon","mercury","venus","mars","jupiter","saturn"]
for x,z in itertools.combinations(PL,2):
    sep=np.abs(((F[f"lon_{x}"]-F[f"lon_{z}"]+180)%360)-180)
    for an,ad in (("conj",0),("sextile",60),("square",90),("trine",120),("opp",180)):
        add("D_aspect",f"D:{x}_{z}_{an}",np.abs(sep-ad)<=6)
add("E_eclipse","E:lunar_eclipse_w1",lun_ecl); add("E_eclipse","E:solar_eclipse_w1",sol_ecl)
Z=["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius",
   "Capricorn","Aquarius","Pisces"]
for i,zn in enumerate(Z):
    add("F_zodiac",f"F:sun_in_{zn}",(F["lon_sun"]//30).astype(int)==i)
    add("F_zodiac",f"F:moon_in_{zn}",(F["lon_moon"]//30).astype(int)==i)
dts=[datetime.datetime.utcfromtimestamp(int(t)) for t in ts]
dow=np.array([d.weekday() for d in dts]); mon=np.array([d.month for d in dts])
for i,nm in enumerate(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]): add("G_control",f"G:dow_{nm}",dow==i)
for i in range(1,13): add("G_control",f"G:month_{i:02d}",mon==i)
rng=np.random.default_rng(20260904)
for j in range(30):
    per=rng.uniform(7,400); ph=rng.uniform(0,2*np.pi)
    add("H_null",f"H:synth_{j:02d}",np.sin(2*np.pi*np.arange(N)/per+ph)>0.5)

# ---- run both outcomes ----------------------------------------------------
half=len(r)//2
out=[]
for name,(fam,m) in tests.items():
    mm=m[ok]
    row={"test":name,"family":fam,"n_on":int(mm.sum())}
    for key,v in (("dir",r),("vol",absz)):
        t=stats.ttest_ind(v[mm],v[~mm],equal_var=False)
        row[f"{key}_edge"]=float(v[mm].mean()-v[~mm].mean())
        row[f"{key}_p"]=float(t.pvalue)
        for tag,sl in (("is",slice(0,half)),("oos",slice(half,len(r)))):
            q=mm[sl]; vv=v[sl]
            if 10<q.sum()<len(q)-10:
                row[f"{key}_{tag}_p"]=float(stats.ttest_ind(vv[q],vv[~q],equal_var=False).pvalue)
                row[f"{key}_{tag}_edge"]=float(vv[q].mean()-vv[~q].mean())
            else: row[f"{key}_{tag}_p"]=float("nan"); row[f"{key}_{tag}_edge"]=float("nan")
    out.append(row)
json.dump(out,open("corrected_results.json","w"),indent=1)

A=[x for x in out if x["family"][0] in "ABCDEF"]; G=[x for x in out if x["family"]=="G_control"]
H=[x for x in out if x["family"]=="H_null"]
def bh(rs,key,q=0.10):
    p=np.array([x[key] for x in rs]); o=np.argsort(p); m=len(p)
    okk=p[o]<=q*np.arange(1,m+1)/m
    return int(np.max(np.where(okk)[0])+1) if okk.any() else 0
print("\n"+"="*80); print("CORRECTED RESULTS"); print("="*80)
for key,lbl,unit in (("dir_p","DIRECTION (return OF the event day)",1e4),
                     ("vol_p","VOLATILITY (GARCH-standardised |z|)",100)):
    print(f"\n--- {lbl} ---")
    for nm,rs in (("astrology",A),("controls",G),("nulls",H)):
        h=sum(x[key]<0.05 for x in rs)
        print(f"   {nm:<11} p<0.05: {h:>3}/{len(rs)} ({100*h/len(rs):5.1f}%)   BH q=.10 -> {bh(rs,key)}")
    kk=key[:3]
    print(f"   {'test':<30}{'n':>5}{'edge':>10}{'p':>8}{'IS p':>8}{'OOS p':>8}")
    for x in sorted(A,key=lambda z:z[key])[:6]:
        print(f"   {x['test']:<30}{x['n_on']:>5}{x[kk+'_edge']*unit:>10.1f}{x[key]:>8.4f}"
              f"{x[kk+'_is_p']:>8.3f}{x[kk+'_oos_p']:>8.3f}")
print("\n--- headline claims, CORRECTED alignment ---")
byn={x["test"]:x for x in out}
print(f"   {'test':<28}{'n':>5}{'dir bps':>9}{'dir p':>8}{'vol %':>8}{'vol p':>8}")
for wnt in ("A:full_moon_day","A:full_moon_w1","A:new_moon_day","A:new_moon_w1","A:waxing",
            "B:mercury_retro","B:mercury_station_w1","E:lunar_eclipse_w1","E:solar_eclipse_w1"):
    x=byn.get(wnt)
    if x: print(f"   {x['test']:<28}{x['n_on']:>5}{x['dir_edge']*1e4:>9.1f}{x['dir_p']:>8.3f}"
                f"{x['vol_edge']*100:>8.1f}{x['vol_p']:>8.3f}")
print("\n--- controls on the REPAIRED volatility test (power demonstration) ---")
for x in sorted(G,key=lambda z:z["vol_p"])[:6]:
    print(f"   {x['test']:<28}{x['n_on']:>5}{x['vol_edge']*100:>8.1f}%{x['vol_p']:>9.5f}"
          f"  IS p={x['vol_is_p']:.3f}  OOS p={x['vol_oos_p']:.3f}")
