import json, csv, sys, os, numpy as np
from datetime import date
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, matplotlib.dates as mdates
OUT=sys.argv[1]; J=json.load(open(os.path.join(OUT,"dollar_summary.json"))); rows=list(csv.DictReader(open(os.path.join(OUT,"dollar_monthly.csv"))))
C={"a":"#1d4ed8","b":"#c2410c","c":"#0d9488","d":"#7e22ce","ink":"#1f2937","muted":"#6b7280","grid":"#e5e7eb","surface":"#fcfcfb","rec":"#d1d5db"}
plt.rcParams.update({"font.size":9,"axes.grid":True,"grid.color":C["grid"],"grid.linewidth":0.6,"axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":C["surface"],"axes.facecolor":C["surface"],"legend.frameon":False,"axes.edgecolor":C["muted"]})
md=lambda m: date(int(m[:4]),int(m[5:7]),1)
d=[md(r["month"]) for r in rows]; x=[float(r["dxy_spliced"]) for r in rows]; rec=[int(r["usrec"]) for r in rows]
fig=plt.figure(figsize=(13,9.5)); gs=fig.add_gridspec(3,2,height_ratios=[1.5,1.2,1.1])
ax=fig.add_subplot(gs[0,:])
on=None
for i,(dd,r) in enumerate(zip(d,rec)):
    if r and on is None: on=dd
    if not r and on is not None: ax.axvspan(on,dd,color=C["rec"],alpha=0.55,lw=0); on=None
ax.axhspan(85,105,color=C["c"],alpha=0.08,lw=0); ax.axhline(105,color=C["c"],lw=0.8,ls="--"); ax.axhline(85,color=C["c"],lw=0.8,ls="--")
ax.plot(d,x,color=C["a"],lw=1.2,label="ICE DXY, monthly average of daily closes (Yahoo daily history 1971+, assembled by finder A)")
for lab,dt_,yv in (("Volcker / LatAm 1982",date(1982,8,1),118),("Plaza 1985",date(1985,3,1),160),("Asia/Russia/LTCM 1997-98",date(1998,8,1),102),("dotcom / Argentina 2001-02",date(2001,7,1),120),("GFC 2008-09",date(2009,3,1),89),("EM/China 2015-16",date(2015,12,1),100),("COVID 2020",date(2020,3,1),100),("gilt/JGB/EM 2022",date(2022,9,1),112)):
    ax.annotate(lab,xy=(dt_,yv),xytext=(dt_,yv+9),fontsize=7.5,color=C["ink"],ha="center",arrowprops=dict(arrowstyle="-",color=C["muted"],lw=0.6))
ax.text(date(1973,6,1),106,"Johnson's band 85–105",fontsize=8,color=C["c"])
ax.set_ylim(70,175); ax.set_xlim(date(1973,1,1),date(2027,1,1)); ax.set_ylabel("DXY")
ax.set_title("ICE DXY 1973–2026 against Johnson's 85–105 band (shaded = NBER recessions); latest month %.1f, 2 Nov 2026 close 101.7"%x[-1],loc="left",fontsize=9.5,color=C["ink"])
ax.legend(loc="upper right",fontsize=7.5); ax.xaxis.set_major_locator(mdates.YearLocator(5)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
# panel 2: outcomes by group
ax=fig.add_subplot(gs[1,:])
groups=[("all months",J["all"]),("6m rise ≥ 10%",J["speed"][2]),("6m rise ≥ 15%",J["speed"][3]),("6m fall ≤ −8%",J["speed"][5]),("rise ≥5% &\n10y yield DOWN",J["quadrant"][0]),("rise ≥5% &\n10y yield UP",J["quadrant"][1]),("DXY > 105",J["band"][0]),("DXY < 85",J["band"][1]),("inside band",J["band"][2])]
xs=np.arange(len(groups)); w=0.26
ax.bar(xs-w,[g["p_spx_dd20"] for _,g in groups],w,color=C["a"],label="P(S&P 500 drawdown ≥ 20% within 12 months)")
ax.bar(xs,[g["p_spread_up100bp"] for _,g in groups],w,color=C["b"],label="P(Baa − 10y spread widens ≥ 100bp within 12 months)")
ax.bar(xs+w,[g["p_rec_start"] for _,g in groups],w,color=C["d"],label="P(NBER recession starts within 12 months)")
for i,(_,g) in enumerate(groups): ax.text(i,max(g["p_spx_dd20"],g["p_spread_up100bp"],g["p_rec_start"])+0.015,f"n={g['n']}",ha="center",fontsize=7,color=C["muted"])
ax.set_xticks(xs); ax.set_xticklabels([n for n,_ in groups],fontsize=7.5); ax.set_ylim(0,0.42); ax.set_ylabel("share of months")
ax.set_title("What followed, by dollar state (monthly 1973-01..2025-09, 627 months ≈ 52 independent 12-month windows): counts, not probabilities",loc="left",fontsize=9.5,color=C["ink"])
ax.legend(loc="upper left",fontsize=7.5,ncol=3)
# panel 3: end-of-crisis
ax=fig.add_subplot(gs[2,:])
eps=J["speed_episodes"]; xs=np.arange(len(eps))
ax.bar(xs-0.27,[100*e["spx_fwd12_from_trigger"] for e in eps],0.27,color=C["muted"],label="S&P 12m return from the month the 6m rise hit +10%")
ax.bar(xs,[100*(e["spx_fwd12_from_turn"] or 0) for e in eps],0.27,color=C["c"],label="from the real-time turn (first month 3% below the dollar's 6m high)")
ax.bar(xs+0.27,[100*(e["spx_fwd12_from_peak"] or 0) for e in eps],0.27,color=C["a"],label="from the dollar's peak (known only in hindsight)")
ax.axhline(0,color=C["ink"],lw=0.7)
ax.set_xticks(xs); ax.set_xticklabels([f"{e['trigger']}\npeak {e['dxy_peak']}\nturn {e['realtime_turn']}" for e in eps],fontsize=7.5); ax.set_ylabel("%"); ax.set_ylim(-25,62)
ax.set_title("The dollar's peak as an all-clear for EQUITIES: the twelve fastest rises (6-month +10%) — S&P up 12 months after the peak in 7 of 12 (base: 76% of all months)",loc="left",fontsize=9.5,color=C["ink"])
ax.legend(loc="upper left",fontsize=7.5,ncol=3)
fig.text(0.01,0.005,"SCOPING, not pre-registered. Outcomes over the following 12 months; base rates on the first bars. Dollar = FRED TWEXMMTH (1973-2019) spliced to DTWEXAFEGS (2006+, monthly mean) at the 2019-12 ratio and rescaled to DXY units by the median ratio to ICE DXY on 168 overlapping months (the two indices differ in weights: the 1970s levels and the band crossings are approximate). S&P = Shiller monthly average to 2023-09, FRED SP500 monthly mean after. Only 6 fast-rise episodes with 12-month cooling: descriptive.",fontsize=7,color=C["muted"],wrap=True)
fig.tight_layout(rect=(0,0.04,1,1)); fig.savefig(os.path.join(OUT,"fig_dollar_scoping.png"),dpi=150); print("ok")
