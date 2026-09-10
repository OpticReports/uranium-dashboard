import csv, json, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
BLUE,ORANGE,AQUA="#2a78d6","#eb6834","#1baf7a"
RED,INK,SEC,MUTED="#e34948","#0b0b0b","#52514e","#898781"
GRID,AX,SURF,VIOLET="#e1e0d9","#c3c2b7","#fcfcfb","#4a3aa7"
fin=json.load(open("final_results.json"))
feat=json.load(open("features.json"))
rows=list(csv.DictReader(open("../btc_daily_full.csv")))
close=np.array([float(r["close"]) for r in rows]); ret=np.diff(np.log(close)); n=len(ret)
eq=np.load("equity.npy",allow_pickle=True); nms=np.load("names.npy",allow_pickle=True)
A=[r for r in fin if r["family"][0] in "ABCDEF"]
G=[r for r in fin if r["family"]=="G_control"]; H=[r for r in fin if r["family"]=="H_null"]

fig,axs=plt.subplots(2,2,figsize=(15,10.5),facecolor=SURF)
for a in axs.ravel():
    a.set_facecolor(SURF)
    for s in ("top","right"): a.spines[s].set_visible(False)
    for s in ("left","bottom"): a.spines[s].set_color(AX)
    a.tick_params(colors=SEC,labelsize=9)

# A: hit rates vs the noise floor
ax=axs[0,0]
grp=[("astrology\n(153 tests)",A),("known-REAL\ncontrols (19)",G),("known-FALSE\nnulls (30)",H)]
x=np.arange(3); w=0.36
for j,(key,lab,col) in enumerate((("ret_p","direction",BLUE),("vol_p","volatility",ORANGE))):
    v=[100*sum(r[key]<0.05 for r in rs)/len(rs) for _,rs in grp]
    ax.bar(x+(j-0.5)*w,v,w,color=col,label=lab,zorder=3)
    for xi,vi in zip(x+(j-0.5)*w,v):
        ax.text(xi,vi+1.1,f"{vi:.0f}%",ha="center",fontsize=8.6,color=INK,fontweight="bold")
ax.axhline(5,color=RED,lw=1.6,ls="--",zorder=4)
ax.text(2.42,6.4,"5% = chance",fontsize=8.6,color=RED,ha="right")
ax.set_xticks(x); ax.set_xticklabels([g[0] for g in grp],fontsize=9,color=INK)
ax.set_ylabel("% of tests with p<0.05",fontsize=10,color=SEC); ax.set_ylim(0,66)
ax.grid(axis="y",color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=9,labelcolor=SEC,loc="upper left")
ax.set_title("The nulls fire MORE than astrology on volatility",
             fontsize=12.5,color=INK,fontweight="bold",loc="left",pad=36)
ax.text(0,1.055,"Known-false synthetic cycles hit 43% — so the volatility test is broken by "
        "vol-clustering,\nnot detecting astrology. Direction: astrology 6.5% ≈ chance.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

# B: IS vs OOS collapse
ax=axs[0,1]
pairs=[(r["ret_is_edge"],r["ret_oos_edge"]) for r in A
       if np.isfinite(r.get("ret_is_edge",np.nan)) and np.isfinite(r.get("ret_oos_edge",np.nan))]
xs=[p[0] for p in pairs]; ys=[p[1] for p in pairs]
ax.scatter(xs,ys,s=26,color=BLUE,alpha=0.55,edgecolor="none",zorder=3)
lim=max(max(map(abs,xs)),max(map(abs,ys)))*1.08
ax.plot([-lim,lim],[-lim,lim],color=MUTED,lw=1.2,ls=":",zorder=2)
ax.axhline(0,color=AX,lw=1); ax.axvline(0,color=AX,lw=1)
for nm,c in (("D:mercury_jupiter_square",ORANGE),("D:mars_jupiter_sextile",RED)):
    r=[q for q in A if q["test"]==nm][0]
    if not (np.isfinite(r["ret_is_edge"]) and np.isfinite(r["ret_oos_edge"])): continue
    ax.scatter([r["ret_is_edge"]],[r["ret_oos_edge"]],s=90,color=c,zorder=5,
               edgecolor=SURF,linewidth=1.6)
    ax.annotate(nm.split(":")[1],(r["ret_is_edge"],r["ret_oos_edge"]),
                textcoords="offset points",xytext=(-6,10),fontsize=8.4,
                color=c,fontweight="bold",ha="right")
rho=np.corrcoef(xs,ys)[0,1]
print(f"IS/OOS pairs={len(xs)} corr={rho:.3f}")
ax.set_xlabel("in-sample edge, bps/day (2011–2019)",fontsize=10,color=SEC)
ax.set_ylabel("out-of-sample edge, bps/day (2019–2026)",fontsize=10,color=SEC)
ax.grid(color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.set_title(f"In-sample edge does not survive (r = {rho:+.2f})",
             fontsize=12.5,color=INK,fontweight="bold",loc="left",pad=36)
ax.text(0,1.055,"Each dot is one astrological test. If the effects were real the cloud would "
        "hug the dotted\ndiagonal. The two strongest in-sample hits collapsed to ~zero.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

# C: lunar phase curve
ax=axs[1,0]
pa=np.array([f["moon_phase_deg"] for f in feat])[:n]
nb=12; edges=np.linspace(0,360,nb+1); ctr=(edges[:-1]+edges[1:])/2
mu=[];se=[]
for i in range(nb):
    m=(pa>=edges[i])&(pa<edges[i+1]); r=ret[m]
    mu.append(r.mean()*1e4); se.append(r.std(ddof=1)/np.sqrt(len(r))*1e4)
mu=np.array(mu); se=np.array(se)
ax.errorbar(ctr,mu,yerr=1.96*se,fmt="o-",color=BLUE,ecolor=AX,elinewidth=1.4,
            capsize=3,markersize=6,lw=1.8,zorder=3)
ax.axhline(0,color=RED,lw=1.5,ls="--",zorder=2)
for xp,lab in ((0,"new"),(180,"full"),(360,"new")):
    ax.axvline(xp,color=MUTED,lw=1,ls=":",zorder=1)
    ax.text(xp,ax.get_ylim()[1]*0.94,lab,fontsize=8.6,color=MUTED,ha="center")
ax.set_xlim(-8,368); ax.set_xticks([0,90,180,270,360])
ax.set_xlabel("lunar phase angle (deg)  —  0/360 = new moon, 180 = full moon",
              fontsize=10,color=SEC)
ax.set_ylabel("mean next-day return, bps",fontsize=10,color=SEC)
ax.grid(axis="y",color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.set_title("No lunar cycle in BTC returns",fontsize=12.5,color=INK,
             fontweight="bold",loc="left",pad=36)
ax.text(0,1.055,"12 phase bins, 15 years, 95% CIs. Every bin's interval contains zero; "
        "full-moon day p=0.60,\nnew-moon day p=0.46.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

# D: equity curves
ax=axs[1,1]
cols={"buy & hold":INK,"hold waxing (new->full)":BLUE,"hold waning (full->new)":ORANGE,
      "B&H minus full-moon +/-3d":AQUA,"B&H minus mercury retro":VIOLET}
for e,nm in zip(eq,nms):
    if nm in cols:
        ax.semilogy(e,color=cols[nm],lw=2.2 if nm=="buy & hold" else 1.5,
                    label=nm,zorder=4 if nm=="buy & hold" else 3)
ax.set_ylabel("equity, log scale (1.0 = start)",fontsize=10,color=SEC)
ax.set_xlabel("days since 2011-08-18",fontsize=10,color=SEC)
ax.grid(color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=8.4,labelcolor=SEC,loc="upper left")
ax.set_title("Every astrological rule loses to buy-and-hold",
             fontsize=12.5,color=INK,fontweight="bold",loc="left",pad=36)
ax.text(0,1.055,"15y, 6bps round-trip. B&H 80.8% CAGR / 84.9% MaxDD; best astro rule "
        "64.5% / 83.4%.\nNone improves drawdown either.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

fig.suptitle("Astrology vs Bitcoin — 153 pre-registered tests, 15 years, nothing survives",
             fontsize=15.5,color=INK,fontweight="bold",x=0.006,ha="left",y=0.992)
fig.tight_layout(rect=[0,0.005,1,0.95],h_pad=3.2)
fig.savefig("astro_findings.png",dpi=150,facecolor=SURF)
print("wrote astro_findings.png")
