import sys, math, json
sys.path.insert(0,'/tmp/ovl'); import lib
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE,ORANGE,AQUA="#2a78d6","#eb6834","#1baf7a"
RED,INK,SEC,MUTED="#e34948","#0b0b0b","#52514e","#898781"
GRID,AX,SURF,VIOLET="#e1e0d9","#c3c2b7","#fcfcfb","#4a3aa7"
t3,t4,bars=lib.load()
A3=[lib.astro(t["entry_ts"]) for t in t3]; A4=[lib.astro(t["entry_ts"]) for t in t4]
def sizes(f): return [1.0 if f(a) else 0.0 for a in A3],[1.0 if f(a) else 0.0 for a in A4]
def nav(f=None):
    if f is None: c=lib.curve(t3,t4)
    else:
        s3,s4=sizes(f); c=lib.curve(t3,t4,s3,s4)
    return np.array([x[0] for x in c]),np.array([x[1] for x in c])

fig,axs=plt.subplots(2,2,figsize=(15,10.4),facecolor=SURF)
for a in axs.ravel():
    a.set_facecolor(SURF)
    for s in ("top","right"): a.spines[s].set_visible(False)
    for s in ("left","bottom"): a.spines[s].set_color(AX)
    a.tick_params(colors=SEC,labelsize=9)

# A: the multiplicity story
ax=axs[0,0]
fam=[("lunar",64,2,3.2),("retrograde",40,6,2.0),("aspect",318,13,15.9),
     ("size mod",30,0,1.5),("exit/stop",35,5,1.8),("zodiac/misc",110,4,4.3)]
x=np.arange(len(fam)); w=0.38
ax.bar(x-w/2,[f[2] for f in fam],w,color=ORANGE,label="cleared 95th pctile",zorder=3)
ax.bar(x+w/2,[f[3] for f in fam],w,color=MUTED,label="expected by CHANCE",zorder=3)
for i,f in enumerate(fam):
    ax.text(i-w/2,f[2]+0.35,f"{f[2]}",ha="center",fontsize=8.8,color=INK,fontweight="bold")
    ax.text(i+w/2,f[3]+0.35,f"{f[3]:.1f}",ha="center",fontsize=8.8,color=SEC)
ax.set_xticks(x); ax.set_xticklabels([f"{f[0]}\n({f[1]})" for f in fam],fontsize=8.8,color=INK)
ax.set_ylabel("variants clearing the 95th percentile",fontsize=10,color=SEC)
ax.grid(axis="y",color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=9,labelcolor=SEC,loc="upper left")
ax.set_title("30 'winners' out of 699 — chance predicts 29",fontsize=12.5,color=INK,
             fontweight="bold",loc="left",pad=36)
ax.text(0,1.05,"Every family's hit count sits at its own chance expectation. The one apparent excess\n"
        "(retrograde) is explained by that family's 39-config internal search.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

# B: what the folk rules cost
ax=axs[0,1]
ts,n0=nav()
t_yr=(ts-ts[0])/(365.25*86400)
ax.semilogy(t_yr,n0,color=INK,lw=2.4,label="S6 unchanged  →15.7x",zorder=5)
for lab,f,c in (("skip Mercury retrograde  →11.3x",lambda a: not a["merc_retro"],ORANGE),
                ("skip full-moon ±3d  →10.0x",lambda a: not (117<=a["phase"]<=243),AQUA),
                ("only new-moon ±3d  →3.0x",lambda a: (a["phase"]<=37 or a["phase"]>=323),VIOLET)):
    tt,nn=nav(f); ax.semilogy((tt-ts[0])/(365.25*86400),nn,color=c,lw=1.6,label=lab,zorder=3)
ax.set_ylabel("equity, log scale (1.0 = start)",fontsize=10,color=SEC)
ax.set_xlabel("years",fontsize=10,color=SEC)
ax.grid(color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=8.6,labelcolor=SEC,loc="upper left")
ax.set_title("The folk rules are expensive, not neutral",fontsize=12.5,color=INK,
             fontweight="bold",loc="left",pad=36)
ax.text(0,1.05,"Sitting out Mercury retrograde costs 4.4x of terminal wealth over 6.2 years.\n"
        "Skipping full moons costs 5.7x. Neither avoids drawdown.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

# C: the best candidate's collapse
ax=axs[1,0]
stages=["full\nsample","re-add 3\nof 47 trades","2nd half\nalone","S4 book\nalone","retrograde\nstation only"]
pct=[99.2,83.4,73.7,81.8,77.9]
cols=[AQUA if p>=95 else ORANGE for p in pct]
ax.bar(range(len(stages)),pct,color=cols,width=0.6,zorder=3)
for i,p in enumerate(pct):
    ax.text(i,p+1.4,f"{p:.1f}",ha="center",fontsize=9,color=INK,fontweight="bold")
ax.axhline(95,color=RED,lw=1.7,ls="--",zorder=4)
ax.text(4.42,96.3,"95th pctile bar",fontsize=8.6,color=RED,ha="right")
ax.set_xticks(range(len(stages))); ax.set_xticklabels(stages,fontsize=8.6,color=INK)
ax.set_ylabel("MAR percentile vs matched nulls",fontsize=10,color=SEC)
ax.set_ylim(0,108)
ax.grid(axis="y",color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.set_title("The best candidate, poked once",fontsize=12.5,color=INK,
             fontweight="bold",loc="left",pad=36)
ax.text(0,1.05,"'Skip Mercury station ±3d' looked superb (CAGR 66% vs 57%, MAR 2.73 vs 2.01) and\n"
        "cleared four separate nulls. Three trades carry 79% of it; two are the same day.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

# D: percentile != better than S6
ax=axs[1,1]
pts=[("ONLY octile 0 (new)",19.54,1.252,95.2),("ONLY new-moon ±1d",11.10,1.271,95.0),
     ("ONLY last-qtr octile",12.07,1.117,93.8),("SKIP perigee p10",63.73,2.254,91.3),
     ("skip Mercury retro",49.53,1.95,85.0),("skip full-moon ±3d",46.71,1.252,41.9)]
for nm,cg,mar,p in pts:
    c=AQUA if p>=95 else MUTED
    ax.scatter([cg],[mar],s=90,color=c,zorder=4,edgecolor=SURF,linewidth=1.5)
    ax.annotate(nm,(cg,mar),textcoords="offset points",xytext=(7,6),fontsize=8.2,color=SEC)
ax.scatter([56.95],[2.014],s=190,marker="*",color=INK,zorder=6,edgecolor=SURF,linewidth=1.5)
ax.annotate("S6 unchanged",(56.95,2.014),textcoords="offset points",xytext=(-9,10),
            fontsize=9,color=INK,fontweight="bold",ha="right")
ax.axvline(56.95,color=INK,lw=1,ls=":",zorder=2); ax.axhline(2.014,color=INK,lw=1,ls=":",zorder=2)
ax.set_xlabel("CAGR %",fontsize=10,color=SEC); ax.set_ylabel("MAR (CAGR / MaxDD)",fontsize=10,color=SEC)
ax.grid(color=GRID,lw=0.8,zorder=0); ax.set_axisbelow(True)
ax.set_title("Clearing the null ≠ beating S6",fontsize=12.5,color=INK,
             fontweight="bold",loc="left",pad=36)
ax.text(0,1.05,"Green = cleared the 95th percentile. They beat RANDOMLY discarding the same number\n"
        "of trades — while landing far below S6 on both axes. They are smaller strategies.",
        transform=ax.transAxes,fontsize=8.6,color=MUTED,va="bottom")

fig.suptitle("Astrological overlays on S6 — 699 variants, none improves the strategy we trade",
             fontsize=15.5,color=INK,fontweight="bold",x=0.006,ha="left",y=0.992)
fig.tight_layout(rect=[0,0.005,1,0.945],h_pad=3.6)
fig.savefig("/tmp/ovl/overlay_summary.png",dpi=150,facecolor=SURF)
print("wrote /tmp/ovl/overlay_summary.png")
