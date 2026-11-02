import csv, json, sys, os, numpy as np
from datetime import date
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, matplotlib.dates as mdates
RAW, OUT = sys.argv[1], sys.argv[2]
def fredd(fid):
    o={}
    for r in csv.DictReader(open(os.path.join(RAW,fid+".csv"))):
        if r[fid] not in ("","."): o[r["observation_date"]]=float(r[fid])
    return o
bd=fredd("DTWEXBGS"); vix=fredd("VIXCLS"); days=sorted(d for d in bd if d in vix)
B=np.array([bd[d] for d in days]); V=np.array([vix[d] for d in days]); roc=np.full(len(B),np.nan)
for k in range(20,len(B)): roc[k]=100*(B[k]/B[k-20]-1)
fires={f["fire"]:f for f in json.load(open(os.path.join(OUT,"decel_realtime.json")))}
dd=lambda s: date(int(s[:4]),int(s[5:7]),int(s[8:10]))
C={"a":"#1d4ed8","b":"#c2410c","c":"#0d9488","d":"#7e22ce","ink":"#1f2937","muted":"#6b7280","grid":"#e5e7eb","surface":"#fcfcfb"}
plt.rcParams.update({"font.size":8.5,"axes.grid":True,"grid.color":C["grid"],"grid.linewidth":0.6,"axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":C["surface"],"axes.facecolor":C["surface"],"legend.frameon":False,"axes.edgecolor":C["muted"]})
eps=[("GFC 2008-09","2008-07-01","2009-06-30","2008-09-22"),("euro crisis 2011","2011-07-01","2012-03-31","2011-11-01"),("COVID 2020","2020-01-15","2020-07-31","2020-04-09"),("2022 hikes / gilt / JGB","2022-03-01","2023-01-31","2022-07-28")]
fig,axes=plt.subplots(3,4,figsize=(15,9),sharex="col")
for j,(lab,lo,hi,fire) in enumerate(eps):
    idx=[i for i,d in enumerate(days) if lo<=d<=hi]; x=[dd(days[i]) for i in idx]
    pk=idx[0]+int(np.argmax(B[idx[0]:idx[-1]+1])); rk=idx[0]+int(np.nanargmax(roc[idx[0]:idx[-1]+1])); vk=idx[0]+int(np.argmax(V[idx[0]:idx[-1]+1]))
    ax=axes[0,j]; ax.plot(x,B[idx],color=C["a"],lw=1.3); ax.set_title(lab,loc="left",fontsize=9.5,color=C["ink"])
    for a in axes[:,j]:
        a.axvline(dd(fire),color=C["b"],lw=1,ls="--"); a.axvline(dd(days[pk]),color=C["a"],lw=1,ls=":"); a.axvline(dd(days[vk]),color=C["d"],lw=0.9,ls="-.")
    ax.text(dd(fire),B[idx].max(),"rule fires",color=C["b"],fontsize=7.5,ha="right",va="top",rotation=90)
    ax.text(dd(days[pk]),B[idx].min(),"dollar peak",color=C["a"],fontsize=7.5,ha="left",va="bottom",rotation=90)
    f=fires[fire]; ax.text(0.02,0.04,f"after the fire: dollar +{f['dollar_more_rise_pct']}% more to its peak;\nVIX {f['vix_fwd60_chg']:+.0f} pts in 60 days",transform=ax.transAxes,fontsize=7.5,color=C["ink"],va="bottom")
    if j==0: ax.set_ylabel("broad dollar (DTWEXBGS)")
    ax=axes[1,j]; ax.plot(x,roc[idx],color=C["c"],lw=1.3); ax.axhline(0,color=C["ink"],lw=0.6)
    ax.plot([dd(days[rk])],[roc[rk]],"o",color=C["c"],ms=5); ax.text(dd(days[rk]),roc[rk],"  peak rate of climb",fontsize=7.5,color=C["c"],va="center")
    if j==0: ax.set_ylabel("20-day rate of climb, %")
    ax=axes[2,j]; ax.plot(x,V[idx],color=C["d"],lw=1.3); ax.text(dd(days[vk]),V[vk],"  VIX peak",fontsize=7.5,color=C["d"],va="center")
    if j==0: ax.set_ylabel("VIX")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%y"))
fig.suptitle("Casey's deceleration rule: does the dollar's rate of climb peak before its level does, and does that mark the top of the SCRAMBLE?  (daily, broad dollar; scoping, not scored)",x=0.01,ha="left",fontsize=10.5,color=C["ink"])
fig.text(0.01,0.005,"SCOPING. Real-time rule: 20-day rate of climb <= half its trailing-60-day maximum, that maximum >= 4%, dollar within 3% of its 60-day high, 10y yield down over the scramble; 120-day cooling, re-armed on a 1.5x bigger scramble (the re-arm was added AFTER the 2008-09-22 miss). Parameters were chosen on 2008/2020/2022 and sit at the optimum of a sweep. Record on the motivating V-spikes: 2020-04-09 clean (dollar +1.4% more, S&P +13% in 60 days); 2008-09-22 first wave (dollar +17.7% more, S&P -44% to the low); 2022-07-28 first wave (dollar +6.6% more, S&P -12%); the re-armed 2008-11-06 firing had the dollar +6.5% more and the S&P -25% (VIX -20). 2011 and the other euro mini-episodes resolved within weeks. On unseen monthly 1973-2005 data the rule has no edge (3 of 10 vs 42% base). It marks the peak of a dollar SCRAMBLE at best, never that a crisis has subsided; 2022 was a policy grind, not a scramble (swap lines peaked at $11bn).",fontsize=7,color=C["muted"],wrap=True)
fig.tight_layout(rect=(0,0.06,1,0.96)); fig.savefig(os.path.join(OUT,"fig_decel_rule.png"),dpi=150); print("ok")
