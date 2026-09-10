import csv,json,numpy as np,datetime
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE,ORANGE,AQUA="#2a78d6","#eb6834","#1baf7a"
RED,INK,SEC,MUTED="#e34948","#0b0b0b","#52514e","#898781"
GRID,AX,SURF,VIOLET="#e1e0d9","#c3c2b7","#fcfcfb","#4a3aa7"
out=json.load(open("corrected_results.json"))
A=[x for x in out if x["family"][0] in "ABCDEF"]
G=[x for x in out if x["family"]=="G_control"]; H=[x for x in out if x["family"]=="H_null"]
feat=json.load(open("features.json"))
rows=list(csv.DictReader(open("../btc_daily_full.csv")))
close=np.array([float(r["close"]) for r in rows]); N=len(rows)
y=np.full(N,np.nan); y[1:]=np.diff(np.log(close)); ok=~np.isnan(y); r=y[ok]; n=len(r)
ts=np.array([int(x["ts"]) for x in rows])[ok]
F={k:np.array([f[k] for f in feat])[ok] for k in feat[0]}

fig,axs=plt.subplots(2,2,figsize=(15,10.6),facecolor=SURF)
for a in axs.ravel():
    a.set_facecolor(SURF)
    for s in ("top","right"): a.spines[s].set_visible(False)
    for s in ("left","bottom"): a.spines[s].set_color(AX)
    a.tick_params(colors=SEC,labelsize=9)

ax=axs[0,0]
grp=[("astrology\n153 tests",A),("known-REAL\ncontrols 19",G),("known-FALSE\nnulls 30",H)]
x=np.arange(3); w=0.36
for j,(key,lab,col) in enumerate((("dir_p","direction",BLUE),("vol_p","volatility",ORANGE))):
    v=[100*sum(q[key]<0.05 for q in rs)/len(rs) for _,rs in grp]
    ax.bar(x+(j-0.5)*w,v,w,color=col,label=lab,zorder=3)
    for xi,vi in zip(x+(j-0.5)*w,v):
        ax.text(xi,vi+0.9,f"{vi:.0f}%",ha="center",fontsize=8.8,color=INK,fontweight="bold")
ax.axhline(5,color=RED,lw=1.6,ls="--",zorder=4)
ax.text(2.45,5.9,"5% = chance",fontsize=8.6,color=RED,ha="right")
ax.set_xticks(x); ax.set_xticklabels([g[0] for g in grp],fontsize=9,color=INK)
ax.set_ylabel("% of tests with p<0.05",fontsize=10,color=SEC); ax.set_ylim(0,45)
ax.grid(axis="y",color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=9,labelcolor=SEC,loc="upper left")
ax.set_title("The test has power. Astrology sits at chance.",fontsize=12.5,color=INK,
             fontweight="bold",loc="left",pad=38)
ax.text(0,1.055,"After repairing the volatility test (GARCH-standardised), the known-FALSE nulls fire 0%\n"
        "and the known-REAL controls fire 37% — so a real effect WOULD be seen. Astrology: 3.9%.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

ax=axs[0,1]
pr=[(q["dir_is_edge"]*1e4,q["dir_oos_edge"]*1e4) for q in A
    if np.isfinite(q["dir_is_edge"]) and np.isfinite(q["dir_oos_edge"])]
xs=[p[0] for p in pr]; ys=[p[1] for p in pr]
ax.scatter(xs,ys,s=26,color=BLUE,alpha=0.5,edgecolor="none",zorder=3)
lim=max(max(map(abs,xs)),max(map(abs,ys)))*1.08
ax.plot([-lim,lim],[-lim,lim],color=MUTED,lw=1.2,ls=":",zorder=2)
ax.axhline(0,color=AX,lw=1); ax.axvline(0,color=AX,lw=1)
for nm,c,lab in (("A:full_moon_day",ORANGE,"full moon day"),
                 ("D:mars_jupiter_sextile",RED,"mars-jupiter sextile")):
    q=[z for z in A if z["test"]==nm][0]
    ax.scatter([q["dir_is_edge"]*1e4],[q["dir_oos_edge"]*1e4],s=95,color=c,zorder=5,
               edgecolor=SURF,linewidth=1.6)
    ax.annotate(lab,(q["dir_is_edge"]*1e4,q["dir_oos_edge"]*1e4),textcoords="offset points",
                xytext=(-8,11),fontsize=8.6,color=c,fontweight="bold",ha="right")
rho=np.corrcoef(xs,ys)[0,1]
ax.set_xlabel("in-sample edge, bps/day (2011–2019)",fontsize=10,color=SEC)
ax.set_ylabel("out-of-sample edge, bps/day (2019–2026)",fontsize=10,color=SEC)
ax.grid(color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.set_title(f"Nothing persists out of sample (r = {rho:+.2f})",fontsize=12.5,color=INK,
             fontweight="bold",loc="left",pad=38)
ax.text(0,1.055,"Full moon day is +64 bps in-sample (p=0.016) and +18 bps out-of-sample (p=0.39).\n"
        "A real effect would sit on the dotted diagonal.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

ax=axs[1,0]
def shift(m,k=-1):
    o=np.zeros(n,bool); i=np.where(m)[0]+k; o[i[(i>=0)&(i<n)]]=True; return o
pa=F["moon_phase_deg"]; nb=12; e=np.linspace(0,360,nb+1); ctr=(e[:-1]+e[1:])/2
mu=[];se=[]
for i in range(nb):
    m=(pa>=e[i])&(pa<e[i+1]); v=r[m]; mu.append(v.mean()*1e4); se.append(v.std(ddof=1)/np.sqrt(len(v))*1e4)
mu=np.array(mu); se=np.array(se)
ax.errorbar(ctr,mu,yerr=1.96*se,fmt="o-",color=BLUE,ecolor=AX,elinewidth=1.4,capsize=3,
            markersize=6,lw=1.8,zorder=3)
fm=shift(F["full_moon_day"]==1)
ax.scatter([180],[r[fm].mean()*1e4],s=130,marker="D",color=ORANGE,zorder=6,
           edgecolor=SURF,linewidth=1.6)
ax.annotate("full-moon DAY\n+64 bps (p=0.016)\ndies OOS",(180,r[fm].mean()*1e4),
            textcoords="offset points",xytext=(12,-6),fontsize=8.6,color=ORANGE,fontweight="bold")
ax.axhline(0,color=RED,lw=1.5,ls="--",zorder=2)
ax.set_xlim(-8,392); ax.set_xticks([0,90,180,270,360])
ax.set_xlabel("lunar phase angle (deg)  —  0/360 new moon, 180 full moon",fontsize=10,color=SEC)
ax.set_ylabel("mean return that day, bps",fontsize=10,color=SEC)
ax.grid(axis="y",color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.set_title("No lunar cycle — one lone bin, and it does not replicate",fontsize=12.5,
             color=INK,fontweight="bold",loc="left",pad=38)
ax.text(0,1.055,"12 phase bins, 15y, 95% CIs, CORRECTED alignment (the first pass tested the\n"
        "wrong calendar day). Every bin's interval contains zero.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

ax=axs[1,1]
yrs=np.array([datetime.datetime.utcfromtimestamp(int(t)).year for t in ts])
cost=np.select([yrs<=2013,yrs<=2015,yrs<=2017,yrs<=2019,yrs<=2021],
               [0.0110,0.0070,0.0050,0.0030,0.0020],0.0012)
simple=np.exp(r)-1
def eqof(pos):
    p=np.asarray(pos,float); turn=np.abs(np.diff(np.concatenate([[0.0],p])))
    return np.cumprod(1+p*simple-turn*cost)
w3=np.zeros(n,bool)
for j in np.where(fm)[0]: w3[max(0,j-3):j+4]=True
for lab,pos,c,lw in (("buy & hold",np.ones(n),INK,2.3),
                     ("hold waxing (new→full)",(pa<180).astype(float),BLUE,1.5),
                     ("B&H minus full-moon ±3d",np.where(w3,0.0,1.0),AQUA,1.5),
                     ("B&H minus mercury retro",(F["retro_mercury"]==0).astype(float),VIOLET,1.5),
                     ("long ONLY on full moon",fm.astype(float),ORANGE,1.5)):
    ax.semilogy(eqof(pos),color=c,lw=lw,label=lab,zorder=4 if lab=="buy & hold" else 3)
ax.set_ylabel("equity, log scale (1.0 = start)",fontsize=10,color=SEC)
ax.set_xlabel("days since 2011-08-18",fontsize=10,color=SEC)
ax.grid(color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=8.3,labelcolor=SEC,loc="upper left")
ax.set_title("Every rule loses to buy-and-hold",fontsize=12.5,color=INK,
             fontweight="bold",loc="left",pad=38)
ax.text(0,1.055,"Realistic time-varying costs (110→12 bps round-trip). B&H 80.7% CAGR / 84.9% DD.\n"
        "Trading the full-moon effect itself returns −1.1%: 12 round-trips a year eat it.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

fig.suptitle("Astrology vs Bitcoin — 153 pre-registered tests, 15 years, corrected and re-run",
             fontsize=15.5,color=INK,fontweight="bold",x=0.006,ha="left",y=0.993)
fig.tight_layout(rect=[0,0.005,1,0.945],h_pad=3.6)
fig.savefig("astro_final.png",dpi=150,facecolor=SURF)
print("wrote astro_final.png")
