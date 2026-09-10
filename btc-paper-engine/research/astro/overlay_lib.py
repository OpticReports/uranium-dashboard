"""Shared harness for astrological overlays on S6 (the live blend).

VERIFIED: reproduces btc-paper-engine/backend/scripts/bench_blend.py's audited
blend_curve EXACTLY (CAGR 57.87%, MaxDD -28.27%, MAR 2.047, 412 trades).

S6 = 75% S3 (pullback) + 25% S4 (donchian) at 2.0x leverage.
Overlays act on ENTRY state only (ephemeris is deterministic and published
years ahead, so knowing the sky at entry_ts is not lookahead).

EVERY overlay must be scored against MATCHED RANDOM nulls: dropping or
down-weighting trades changes CAGR and MaxDD mechanically, so the question is
never "did it improve?" but "did it beat random filters of the same size?".
"""
import csv, sys, math, json, os
import numpy as np
BACKEND="/home/user/uranium-dashboard/btc-paper-engine/backend"
BARS="/tmp/claude-0/-home-user-uranium-dashboard/98a6cf63-599b-59a8-b758-40c71716fb29/scratchpad/bars_4h_btcusd_ext.csv"
CACHE="/tmp/ovl/trades.json"
W,LEV=0.25,2.0

def load():
    """-> (trades3, trades4, bars). Cached so agents don't each re-run the replay."""
    if os.path.exists(CACHE):
        d=json.load(open(CACHE)); return d["t3"],d["t4"],d["bars"]
    sys.path.insert(0,BACKEND)
    from app.engine.core import Bar
    from app.engine.replay import run_replay
    from app.config import RESEARCH_BOOKS,RESEARCH_SIGNAL,RESEARCH_TRADE
    bars=[Bar(ts=int(r["ts_open_unix"]),open=float(r["open"]),high=float(r["high"]),
              low=float(r["low"]),close=float(r["close"]),volume=float(r["volume"]))
          for r in csv.DictReader(open(BARS))]
    res=run_replay(bars,RESEARCH_BOOKS,RESEARCH_SIGNAL,RESEARCH_TRADE,cash_apy=0.0)
    def pack(b):
        return [dict(side=t.side,entry_ts=t.entry_ts,exit_ts=t.exit_ts,
                     entry_price=t.entry_price,exit_price=t.exit_price,
                     stop_price=t.stop_price,atr=t.atr_at_entry,
                     exit_reason=t.exit_reason,bars_held=t.bars_held,
                     pnl_pct=t.pnl_pct,
                     r=t.equity_after/t.equity_before-1) for t in b.trades]
    t3,t4=pack(res.books["S3"]),pack(res.books["S4"])
    bb=[dict(ts=b.ts,o=b.open,h=b.high,l=b.low,c=b.close) for b in bars]
    json.dump({"t3":t3,"t4":t4,"bars":bb},open(CACHE,"w"))
    return t3,t4,bb

def curve(t3,t4,size3=None,size4=None):
    """Blend NAV path. size* are per-trade multipliers in [0,1+]; None = all 1."""
    s3=[1.0]*len(t3) if size3 is None else size3
    s4=[1.0]*len(t4) if size4 is None else size4
    evs=sorted([(t["exit_ts"],"P",t["r"],s3[i]) for i,t in enumerate(t3) if s3[i]>0]
              +[(t["exit_ts"],"T",t["r"],s4[i]) for i,t in enumerate(t4) if s4[i]>0])
    eq=1.0; out=[]
    for ts,which,r,sz in evs:
        out.append((ts,eq)); eq*=1+LEV*(r*((1-W) if which=="P" else W))*sz
    out.append((evs[-1][0] if evs else 0,eq))
    return out

def stats(c):
    if len(c)<5: return None
    ts=np.array([x[0] for x in c]); nav=np.array([x[1] for x in c])
    yrs=(ts[-1]-ts[0])/(365.25*86400)
    cagr=nav[-1]**(1/yrs)-1
    mdd=float((nav/np.maximum.accumulate(nav)-1).min())
    r=np.diff(nav)/nav[:-1]
    return dict(cagr=100*cagr,mdd=100*mdd,
                mar=cagr/abs(mdd) if mdd<-0.005 else None,
                sharpe=float(r.mean()/(r.std()+1e-12)*math.sqrt(len(r)/yrs)),
                nav=float(nav[-1]),n=len(c)-1)

# ---- astrological state at a timestamp -----------------------------------
_AC={}
def astro(ts):
    if ts in _AC: return _AC[ts]
    import ephem
    d=ephem.Date("1970/1/1")+ts/86400.0
    def lon(cls):
        b=cls(); b.compute(d); return math.degrees(ephem.Ecliptic(b).lon)%360
    def retro(cls):
        b=cls(); b.compute(d); l1=math.degrees(ephem.Ecliptic(b).lon)%360
        b2=cls(); b2.compute(ephem.Date(d+1)); l2=math.degrees(ephem.Ecliptic(b2).lon)%360
        return (((l2-l1+180)%360)-180)<0
    L={n:lon(c) for n,c in (("sun",ephem.Sun),("moon",ephem.Moon),
        ("mercury",ephem.Mercury),("venus",ephem.Venus),("mars",ephem.Mars),
        ("jupiter",ephem.Jupiter),("saturn",ephem.Saturn))}
    m=ephem.Moon(); m.compute(d)
    o=dict(lon=L,phase=(L["moon"]-L["sun"])%360,
           illum=(1-math.cos(math.radians((L["moon"]-L["sun"])%360)))/2,
           merc_retro=retro(ephem.Mercury),venus_retro=retro(ephem.Venus),
           mars_retro=retro(ephem.Mars),jup_retro=retro(ephem.Jupiter),
           sat_retro=retro(ephem.Saturn),
           moon_dist=m.earth_distance,moon_lat=abs(math.degrees(ephem.Ecliptic(m).lat)))
    _AC[ts]=o; return o

def sep(a,b,A):
    return abs(((A["lon"][a]-A["lon"][b]+180)%360)-180)

BASE=None
def baseline(t3,t4):
    global BASE
    if BASE is None: BASE=stats(curve(t3,t4))
    return BASE

def score(t3,t4,size3,size4,nrep=2000,seed=0):
    """Overlay stats + percentile vs MATCHED random null (same total weight
    removed from each book, allocated at random)."""
    s=stats(curve(t3,t4,size3,size4))
    if s is None: return None
    rng=np.random.default_rng(seed)
    w3,w4=np.array(size3,float),np.array(size4,float)
    nc=[];nm=[]
    for _ in range(nrep):
        p3=list(rng.permutation(w3)); p4=list(rng.permutation(w4))
        q=stats(curve(t3,t4,p3,p4))
        if q: nc.append(q["cagr"]); nm.append(q["mar"] or 0)
    nc=np.array(nc); nm=np.array(nm)
    s["cagr_pctile"]=float(100*np.mean(nc<s["cagr"]))
    s["mar_pctile"]=float(100*np.mean(nm<(s["mar"] or 0)))
    s["null_cagr_med"]=float(np.median(nc)); s["null_mar_med"]=float(np.median(nm))
    s["kept_weight"]=float((w3.sum()+w4.sum())/(len(w3)+len(w4)))
    return s
