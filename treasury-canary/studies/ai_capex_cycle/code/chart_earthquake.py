import json, sys, os, numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
OUT=sys.argv[1]; j=json.load(open(os.path.join(OUT,"summary.json"))); eps=json.load(open(os.path.join(OUT,"episodes.json")))
C={"a":"#1d4ed8","b":"#c2410c","c":"#0d9488","d":"#7e22ce","ink":"#1f2937","muted":"#6b7280","grid":"#e5e7eb","surface":"#fcfcfb"}
plt.rcParams.update({"font.size":9,"axes.grid":True,"grid.color":C["grid"],"grid.linewidth":0.6,"axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":C["surface"],"axes.facecolor":C["surface"],"legend.frameon":False,"axes.edgecolor":C["muted"]})
fig,axes=plt.subplots(1,2,figsize=(12.5,5.2),gridspec_kw={"width_ratios":[1.25,1]})
ax=axes[0]
groups=[("run-up size\n(24m return)",j["by_raw24"],C["a"]),("volatility\nduring run-up",j["by_vol"],C["c"]),("corrections ≥10%\nduring run-up",j["by_corr10"],C["b"])]
x=0; ticks=[]; labels=[]
sub={"raw24 low":"<107%","raw24 mid":"107–117%","raw24 high":"≥117%","vol low":"<19%","vol mid":"19–27%","vol high":"≥27%"}
for title,gs,col in groups:
    for k,g in enumerate(gs):
        p=g["p_crash"]; lo,hi=g["wilson90"]
        ax.bar(x,p,color=col,width=0.72,alpha=0.55+0.2*k)
        ax.errorbar(x,p,yerr=[[p-lo],[hi-p]],color=C["ink"],capsize=3,lw=1)
        ax.text(x,hi+0.015,f"n={g['n']}",ha="center",fontsize=7.5,color=C["muted"])
        lab=g["group"].replace(" corrections >=10%","").replace(" corrections","").replace(" correction","").replace(">=","≥")
        for kk,vv in sub.items():
            if lab.startswith(kk): lab=["low","mid","high"][k]+"\n"+vv
        ticks.append(x); labels.append(lab); x+=1
    ax.text(x-2,-0.2,title,ha="center",fontsize=8.5,color=C["ink"],transform=ax.get_xaxis_transform()); x+=0.8
ax.axhline(j["unconditional_base_rate_crash40_24m"]["p"],color=C["muted"],ls="--",lw=0.9); ax.text(7.0,j["unconditional_base_rate_crash40_24m"]["p"]+0.012,"base rate, any\nindustry-month %.0f%%"%(100*j["unconditional_base_rate_crash40_24m"]["p"]),ha="center",va="bottom",fontsize=7,color=C["muted"])
ax.axhline(j["all"]["p_crash"],color=C["a"],ls=":",lw=0.9); ax.text(0,j["all"]["p_crash"]+0.01,"all run-ups: %.0f%%"%(100*j["all"]["p_crash"]),fontsize=7.5,color=C["a"])
ax.set_xticks(ticks); ax.set_xticklabels(labels,fontsize=7.5); ax.set_ylim(0,0.6); ax.set_ylabel("P(≥40% drawdown in the next 24 months)")
ax.set_title("After a +100%% two-year run-up, 49 US industries 1926–2026\n(n = %d run-ups in 27 calendar clusters; bars treat run-ups as independent, they are not)"%j["all"]["n"],loc="left",fontsize=9.5,color=C["ink"])
ax=axes[1]
cols={0:C["a"],1:C["c"],2:C["b"]}
for kcorr,lab in ((0,"0 corrections ≥10%"),(1,"1 correction"),(2,"≥2 corrections")):
    sel=[e for e in eps if (min(e["corr10"],2)==kcorr)]
    ax.scatter([min(e["raw24"],4) for e in sel],[e["fut_maxdd"] for e in sel],s=14,alpha=0.65,color=cols[kcorr],label=lab,edgecolors="none")
ax.axhline(0.40,color=C["ink"],lw=0.8,ls="--"); ax.text(3.95,0.41,"crash line 40%",ha="right",fontsize=7.5,color=C["ink"])
cur=j["current"]
for nm,col in (("Chips",C["d"]),("Hardw",C["d"])):
    v=cur[nm]["raw24"]; ax.axvline(v,color=col,lw=1,ls=":"); ax.text(v+0.03,0.97 if nm=="Hardw" else 0.80,f"{nm} now\n{v:+.0%} (24m)",fontsize=7.5,color=col,va="top")
ax.set_xlim(0.85,4.05); ax.set_ylim(0,1); ax.set_xlabel("run-up: 24-month return (capped at +300%)"); ax.set_ylabel("max drawdown, next 24 months")
ax.set_title("One dot per run-up\ncolour = corrections during it (rank-correlated +0.75 with volatility)",loc="left",fontsize=9.5,color=C["ink"])
ax.legend(loc="upper right",fontsize=8)
fig.text(0.01,0.005,"SCOPING, not pre-registered. Ken French 49 industry portfolios, value-weighted monthly; run-up = +100% raw in 24 months, first trigger, 36-month cooling; crash = ≥40% peak-to-trough within 24 months. READ WITH CARE: the 408 run-ups fall into 27 calendar clusters and the 'crash' is mostly the market's (sector vs market drawdown Spearman +0.76); with clusters as the unit, only run-up SIZE keeps a determinate sign (cluster-bootstrap 90% CI 1.7 to 4.3 log-odds); volatility, acceleration and the count of corrections all straddle zero (zero-correction effect -0.6 to +0.8). The analogy is untested here, not refuted and not confirmed. Under GSY's own rule and arithmetic net-of-market definition the free file gives n ≈ 47-50 with a 40% crash rate (GSY: 53% on their CRSP industries); a stricter ratio-net screen gives n = 60 / 53%. In those small panels the corrections sign flips with the definition.",fontsize=7,color=C["muted"],wrap=True)
fig.tight_layout(rect=(0,0.1,1,1)); fig.savefig(os.path.join(OUT,"fig_earthquake_scoping.png"),dpi=150)
print("ok")
