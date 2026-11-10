"""RESEARCH_CAGR.md figure. python3 chart.py -> cagr_answer.png"""
import json, datetime as dt, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
BLUE,ORANGE,AQUA,RED,INK,SEC,MUTED,GRID,AX,SURF="#2a78d6","#eb6834","#1baf7a","#e34948","#0b0b0b","#52514e","#898781","#e1e0d9","#c3c2b7","#fcfcfb"
c=json.load(open("candidates.json")); f=json.load(open("final_numbers.json")); cv=json.load(open("final_curves.json"))
fig,ax=plt.subplots(1,3,figsize=(17,5.6)); fig.patch.set_facecolor(SURF)
def style(a):
    a.set_facecolor(SURF); [a.spines[s].set_visible(False) for s in ("top","right")]
    [a.spines[s].set_color(AX) for s in ("left","bottom")]; a.tick_params(colors=SEC,labelsize=9)
# A per-era Sharpe
eras=["E1 2013-16","E2 2017-19","E3 2020-21","E4 2022-24H1","E5 2024H2-26 (SPENT)"]; lab=["2013-16","2017-19","2020-21","2022-24H1","2024H2-26\n(spent)"]
ser=[("baseline","today 75/25",MUTED),("H5a H1+H2a","70/30 + resting stop",BLUE),("H5b H1+H2b","50/50 (REJECTED)",ORANGE)]
x=np.arange(len(eras)); w=0.26
for i,(k,l,col) in enumerate(ser):
    a=ax[0]; a.bar(x+(i-1)*w,[c[k][e]["k=1"]["sharpe"] for e in eras],w,color=col,label=l,zorder=3)
ax[0].axhline(0,color=AX,lw=1); ax[0].set_xticks(x); ax[0].set_xticklabels(lab,fontsize=8.5)
ax[0].axvspan(1.5,4.5,color=GRID,alpha=.45,zorder=0); ax[0].text(3,-0.2,"2020+: no reweight is reliably better",ha="center",fontsize=8.5,color=SEC)
ax[0].set_title("A. Sharpe by era — the gain is all pre-2020",loc="left",fontsize=11,color=INK); ax[0].legend(frameon=False,fontsize=8.5,loc="upper left")
ax[0].set_ylim(-0.3,1.6); ax[0].yaxis.grid(True,color=GRID,zorder=0); style(ax[0])
# B $/yr vs max DD, fixed base
names=["live today (75/25, k=0.20)","75/25, k=0.30","REC: H1 + 70/30, k=0.30","H1 + 70/30, k=0.45 (rejected size)"]
short=["today\nk 0.20","75/25\nk 0.30","REC 70/30\nk 0.30","70/30\nk 0.45 ✗"]; cols=[MUTED,AX,BLUE,RED]
for j,st in enumerate(("2014","2019")):
    for i,n in enumerate(names):
        o=f[f"{st}+ | {n}"]; xx=i+(j-.5)*0.38
        ax[1].bar(xx,o["avg_pnl_per_yr"]/1000,0.36,color=cols[i],alpha=1 if st=="2019" else .45,zorder=3)
        ax[1].text(xx,o["avg_pnl_per_yr"]/1000+0.3,f"DD\n{o['max_dd_usd']/1000:.0f}k",ha="center",fontsize=7.5,color=SEC)
ax[1].set_xticks(range(4)); ax[1].set_xticklabels(short,fontsize=8.5); ax[1].set_ylabel(r"\$k profit per year on \$100k (fixed base)",fontsize=9,color=SEC)
ax[1].set_title("B. Money per year — faded bars from 2014, solid from 2019",loc="left",fontsize=11,color=INK)
ax[1].text(2.62,18.2,"k 0.45: 5 daily-loss halt trips\nsince 2014 (manual resume)",ha="center",fontsize=7.5,color=RED)
ax[1].set_ylim(0,20); ax[1].yaxis.grid(True,color=GRID,zorder=0); style(ax[1])
# C equity 2019+
for n,col,lw in [(names[0],MUTED,1.6),(names[2],BLUE,2.2),(names[3],RED,1.2)]:
    ts,eq=cv[f"2019|{n}"]; d=[dt.datetime.utcfromtimestamp(t) for t in ts]
    ax[2].plot(d,np.array(eq)/1000,color=col,lw=lw,label=n.replace("REC: ",""))
ax[2].axhline(70,color=RED,lw=1,ls="--"); ax[2].text(d[len(d)//40],71,r"-30% budget (\$70k)",fontsize=8,color=RED)
ax[2].set_ylabel(r"account \$k (fixed \$100k base)",fontsize=9,color=SEC); ax[2].legend(frameon=False,fontsize=8,loc="upper left")
ax[2].set_title("C. What the account would have done, 2019→2026-07",loc="left",fontsize=11,color=INK); ax[2].yaxis.grid(True,color=GRID); style(ax[2])
fig.suptitle("Best robust setting for the $100k: resting-stop fix + 70/30 weights at KELLY_M 0.30  (~$9-11k/yr, max DD $12-19k)",x=0.01,ha="left",fontsize=13,color=INK,fontweight="bold")
fig.text(0.01,0.005,"Backtest, in-sample for most parameters; fixed-base (how live sizes); 4.32bp/side; Bitstamp 4h; MTM. Not a forecast. Trial registry ~2,533; DSR 0.25.",fontsize=8,color=MUTED)
fig.tight_layout(rect=(0,0.03,1,0.94)); fig.savefig("cagr_answer.png",dpi=140,facecolor=SURF)
