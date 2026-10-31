import csv, sys, os
from datetime import date
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, matplotlib.dates as mdates
D, OUT = sys.argv[1], sys.argv[2]
def rd(f):
    out={}
    for r in csv.DictReader(open(os.path.join(D,f+".csv"))):
        if r[f] not in (".",""): out[r["observation_date"]]=float(r[f])
    return out
gdp=rd("GDP"); tb=rd("TBSDODNS"); rec=None
r={d: tb[d]/1000/gdp[d]*100 for d in tb if d in gdp}
ds=sorted(r); d3=[]; dd=[]
for d in ds:
    y=str(int(d[:4])-3)+d[4:]
    if y in r: dd.append(date(int(d[:4]),int(d[5:7]),1)); d3.append(r[d]-r[y])
C={"a":"#1d4ed8","b":"#c2410c","ink":"#1f2937","muted":"#6b7280","grid":"#e5e7eb","surface":"#fcfcfb","rec":"#d1d5db"}
plt.rcParams.update({"font.size":9,"axes.grid":True,"grid.color":C["grid"],"grid.linewidth":0.6,"axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":C["surface"],"axes.facecolor":C["surface"],"legend.frameon":False,"axes.edgecolor":C["muted"]})
# recessions from USREC
import urllib.request
usrec=rd("USREC") if os.path.exists(os.path.join(D,"USREC.csv")) else {}
fig,ax=plt.subplots(figsize=(11,4.3))
on=None
for d in sorted(usrec):
    dt=date(int(d[:4]),int(d[5:7]),1)
    if usrec[d]>=1 and on is None: on=dt
    if usrec[d]<1 and on is not None: ax.axvspan(on,dt,color=C["rec"],alpha=0.55,lw=0); on=None
ax.plot(dd,d3,color=C["a"],lw=1.3,label="US nonfinancial business debt / GDP, 3-year change (pp; Fed Z.1 TBSDODNS / BEA GDP)")
ax.axhline(8.99,color=C["b"],lw=1,ls="--"); ax.text(date(1956,6,1),9.4,"R-zone credit threshold +8.99 pp (Greenwood-Hanson-Shleifer-Sørensen 2022; with a +26.6% 3-yr equity rise → 3-yr crisis probability 45% vs 4%)",fontsize=7.5,color=C["b"])
ax.axhline(0,color=C["ink"],lw=0.7)
ax.plot([dd[-1]],[d3[-1]],"o",color=C["b"],ms=5); ax.annotate(f"2026Q2: {d3[-1]:+.1f} pp",xy=(dd[-1],d3[-1]),xytext=(date(2017,1,1),-11),fontsize=8.5,color=C["ink"],arrowprops=dict(arrowstyle="-",color=C["ink"],lw=0.6))
for yr,lab in ((2000,"2000Q1"),(2008,"2008Q4")):
    i=next(k for k,x in enumerate(dd) if x>=date(yr,1 if yr==2000 else 10,1)); ax.annotate(f"{lab}: {d3[i]:+.1f}",xy=(dd[i],d3[i]),xytext=(dd[i],d3[i]+(4 if yr==2000 else 3)),fontsize=8,color=C["ink"],ha="center",arrowprops=dict(arrowstyle="-",color=C["ink"],lw=0.6))
ax.set_ylabel("percentage points"); ax.set_xlim(date(1955,1,1),date(2027,6,1)); ax.set_ylim(-18,16)
ax.xaxis.set_major_locator(mdates.YearLocator(5)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.set_title("The 2008-type credit gauge is off today, but it was also off in 2000: it did not catch the last tech-capex bust (shaded = NBER recessions)",loc="left",fontsize=10,color=C["ink"])
ax.legend(loc="lower left",fontsize=8)
fig.text(0.01,0.01,"SCOPING. Z.1 nonfinancial business debt securities + loans (incl. corporate bonds and bank/nonbank loans; SPV debt only where consolidated) over nominal GDP. The $680bn+ AI-trade issuance of 2024-26 is visible in corporate debt but nominal GDP grew faster. 2000Q1 read +8.3 pp (under the line) and a -45% market, -78% Nasdaq and a recession followed; 2008Q4 +12.1 pp. Today -4.5 pp: the LEVEL is higher (73.6% vs 63.9% in 2000) and debt growth is re-accelerating (+2.2% yoy in 2024Q1 to +5.1% in 2026Q2) but still below nominal GDP. The AI cluster's own issuance (~2.1% of GDP) is telecom-2000 scale and partly outside this series (leases, SPVs, private credit, vendor equity). Reads: a 2008 is not set up; it says nothing about a 2000.",fontsize=7,color=C["muted"],wrap=True)
fig.tight_layout(rect=(0,0.07,1,1)); fig.savefig(os.path.join(OUT,"fig_rzone_scoping.png"),dpi=150); print("ok", round(d3[-1],2))
