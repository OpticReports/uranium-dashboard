import csv, json, numpy as np
D='<scratch>/dxy/'
rows=list(csv.DictReader(open(D+'scoping/out/dollar_monthly.csv')))
m=[r['month'] for r in rows]; X=np.array([float(r['dxy_spliced']) for r in rows]); P=np.array([float(r['spx_shiller']) for r in rows]); SPR=np.array([float(r['baa_minus_gs10']) for r in rows]); REC=np.array([int(r['usrec']) for r in rows])
T=len(m)
print("months",m[0],m[-1],T)
# (a) which months are 6m rise >=15%, and spread+100bp hits; cluster them
hits=[]
for t in range(6,T-12):
    d6=X[t]/X[t-6]-1
    if d6>=0.15:
        sr=max(SPR[t:t+13])-SPR[t]; rec=any(REC[k]==1 and REC[k-1]==0 for k in range(t+1,t+13))
        hits.append((m[t],round(d6,3),round(sr,2),rec))
print("6m>=15% months:",hits)
# DXY>105 months with S&P dd>=20% in next 12m
dd20=[]
for t in range(6,T-12):
    if X[t]>105:
        fut=P[t:t+13]; pk=-1; dd=0
        for v in fut: pk=max(pk,v); dd=max(dd,1-v/pk)
        if dd>=0.20: dd20.append(m[t])
print("DXY>105 & dd>=20pct months n=",len(dd20), dd20)
# (b) base rate: S&P higher 12m later, all months 1973-2025
fw=[P[t+12]>P[t] for t in range(T-12)]
print("base P(S&P up 12m) 1973+:",round(np.mean(fw),3), "n",len(fw))
# speed-episode ex-post-peak claim check
s=json.load(open(D+'scoping/out/dollar_summary.json'))['speed_episodes']
print("fwd12 from ex-post peak:",[(e['dxy_peak'],round(e['spx_fwd12_from_peak'],3)) for e in s])
print(" positive:",sum(1 for e in s if e['spx_fwd12_from_peak']>0),"of",len(s))
print("fwd12 from realtime turn positive:",sum(1 for e in s if e['spx_fwd12_from_turn'] and e['spx_fwd12_from_turn']>0),"of",len(s))
# (c) effective independent obs: 627 months with 12m windows
print("effective n ~",627/12)
# (e) narrow crisis list base rates and band/speed tests on real DXY monthly close (finder A)
fa=list(csv.DictReader(open(D+'finderA/data/dollar_monthly.csv')))
fm=[r['month'] for r in fa if r['dxy_close']]; fc=np.array([float(r['dxy_close']) for r in fa if r['dxy_close']])
def mi(s): return fm.index(s)
for label,onsets in (("L-narrow5",["1982-08","1998-08","2008-09","2020-03","2022-09"]),("L-7 (+1974-06,+1997-07)",["1974-06","1982-08","1997-07","1998-08","2008-09","2020-03","2022-09"])):
    on=[mi(o) for o in onsets]; N=len(fm)
    for H in (12,24):
        base=np.mean([any(t<o<=t+H for o in on) for t in range(N-H)])
        # band excursions (merged gap<=3m) on monthly close, first month outside
        exc=[];state=None;last_end=None
        for t in range(N):
            s="a" if fc[t]>105 else "b" if fc[t]<85 else None
            if s and state is None:
                if exc and last_end is not None and t-last_end<=3 and exc[-1][1]==s: pass
                else: exc.append([t,s])
                state=s
            elif not s and state is not None: state=None; last_end=t
        bh=[any(e[0]<o<=e[0]+H for o in on) for e in exc]
        # speed: first month of 6m rise>=10%, 12m cooling
        sp=[];last=-99
        for t in range(6,N):
            if fc[t]/fc[t-6]-1>=0.10 and t-last>=12: sp.append(t); last=t
        sh=[any(t<o<=t+H for o in on) for t in sp]
        # 12m rise >10%
        sp2=[];last=-99
        for t in range(12,N):
            if fc[t]/fc[t-12]-1>=0.10 and t-last>=12: sp2.append(t); last=t
        sh2=[any(t<o<=t+H for o in on) for t in sp2]
        print(f"{label} H={H}m base={base:.2f} | band exc n={len(exc)} hit={sum(bh)} ({np.mean(bh):.2f}) | 6m>=10% n={len(sp)} hit={sum(sh)} ({np.mean(sh):.2f}) | 12m>=10% n={len(sp2)} hit={sum(sh2)} ({np.mean(sh2):.2f})")
        if H==12: print("   12m>=10% trigger months:",[fm[t] for t in sp2], "hits:",[fm[t] for t,h in zip(sp2,sh2) if h])
