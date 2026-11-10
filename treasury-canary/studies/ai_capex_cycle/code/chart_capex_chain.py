import csv, sys, os, numpy as np
from datetime import date
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, matplotlib.dates as mdates
CAP, CEN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
rows=list(csv.DictReader(open(CAP)))
q=[r["cal_quarter"] for r in rows]
def qd(s): y,qq=s.split("Q"); return date(int(y),3*int(qq)-2,1)
dates=[qd(x) for x in q]
cos=["MSFT","AMZN","GOOGL","META","ORCL"]
cap={c: np.array([float(r[c+"_capex"])/1e9 for r in rows]) for c in cos}
ocf=np.array([float(r["combined_ocf"])/1e9 for r in rows]); tot=np.array([float(r["combined_capex"])/1e9 for r in rows])
ttm_c=np.array([tot[i-3:i+1].sum() if i>=3 else np.nan for i in range(len(tot))]); ttm_o=np.array([ocf[i-3:i+1].sum() if i>=3 else np.nan for i in range(len(tot))])
cen=[]; 
for r in csv.DictReader(open(CEN)):
    m=r["month"].strip(); v=r["private_data_center_NSA_musd"]
    import re, calendar
    mm=re.match(r"^([A-Z][a-z]{2})-(\d{2})", m)
    if v and mm:
        mi=list(calendar.month_abbr).index(mm.group(1)); cen.append((date(2000+int(mm.group(2)),mi,1), float(v)/1000))
cen.sort()
C={"a":"#1d4ed8","b":"#c2410c","c":"#0d9488","d":"#7e22ce","e":"#b45309","ink":"#1f2937","muted":"#6b7280","grid":"#e5e7eb","surface":"#fcfcfb"}
plt.rcParams.update({"font.size":9,"axes.grid":True,"grid.color":C["grid"],"grid.linewidth":0.6,"axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":C["surface"],"axes.facecolor":C["surface"],"legend.frameon":False,"axes.edgecolor":C["muted"]})
fig,axes=plt.subplots(1,3,figsize=(14,4.6))
ax=axes[0]; bottom=np.zeros(len(tot)); cols=[C["a"],C["e"],C["c"],C["d"],C["b"]]
for c,col in zip(cos,cols):
    ax.bar(dates,cap[c],bottom=bottom,width=80,color=col,label=c,edgecolor=C["surface"],linewidth=0.5); bottom+=cap[c]
ax.set_ylabel("$bn per quarter"); ax.set_title("Hyperscaler capex per quarter (EDGAR XBRL)\n\\$%.0fbn in 2026Q3, +%.0f%% yoy"%(tot[-1],100*(tot[-1]/tot[-5]-1)),loc="left",fontsize=9.5,color=C["ink"])
ax.legend(loc="upper left",fontsize=8,ncol=2,bbox_to_anchor=(0,0.95)); ax.xaxis.set_major_locator(mdates.YearLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax=axes[1]; ok=~np.isnan(ttm_c)
ax.plot(np.array(dates)[ok],ttm_c[ok],color=C["b"],lw=1.6,label="capex, trailing 4 quarters")
ax.plot(np.array(dates)[ok],ttm_o[ok],color=C["a"],lw=1.6,label="operating cash flow, trailing 4 quarters")
ax.fill_between(np.array(dates)[ok],ttm_c[ok],ttm_o[ok],where=ttm_c[ok]>ttm_o[ok],color=C["b"],alpha=0.15,interpolate=True)
r=ttm_c[-1]/ttm_o[-1]
ax.text(dates[-1],ttm_c[-1]-80,"capex/OCF %.2f (TTM)\n1.17 in Q3 alone; 1.24 ex Oracle's\n$11.4bn customer prepayments in OCF"%r,ha="right",fontsize=8,color=C["b"])
ax.set_ylabel("$bn, trailing 4 quarters"); ax.set_title("Capex has caught up with the cash that funds it\n(the gap is debt, leases and SPVs)",loc="left",fontsize=9.5,color=C["ink"])
ax.legend(loc="upper left",fontsize=8); ax.xaxis.set_major_locator(mdates.YearLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax=axes[2]; cd=[x[0] for x in cen]; cv=[x[1] for x in cen]
sel=[i for i,x in enumerate(cd) if x>=date(2014,1,1)]
ax.plot([cd[i] for i in sel],[cv[i] for i in sel],color=C["c"],lw=1.4,label="Census private data-center construction put in place, NSA $bn/month")
ax.set_title("Data-center construction per month (Census)\n\\$%.1fbn in Aug-2026, +%.0f%% yoy, 2-month lag"%(cv[-1],100*(cv[-1]/cv[-13]-1)),loc="left",fontsize=9.5,color=C["ink"])
ax.set_ylabel("$bn per month"); ax.legend(loc="upper left",fontsize=8); ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.text(0.01,0.01,"SCOPING. Capex = PaymentsToAcquirePropertyPlantAndEquipment (AMZN: PaymentsToAcquireProductiveAssets; META adds FinanceLeasePrincipalPayments), fiscal quarters mapped to calendar quarters, ORCL fiscal quarter ending in the calendar quarter; finance-lease additions NOT in the bars (MSFT 5.2bn, AMZN 1.5bn USD in Q3). Oracle's Q3 OCF (23.1bn) includes 11.4bn of customer capex prepayments that Oracle itself nets out of its own capex measure: ex-prepayments the group ratio is 1.24 and Oracle alone 2.4x. BEA: information-processing equipment +41% yoy, 0.86pp of Q3-2026 GDP growth.",fontsize=7,color=C["muted"],wrap=True)
fig.tight_layout(rect=(0,0.07,1,1)); fig.savefig(os.path.join(OUT,"fig_capex_chain_scoping.png"),dpi=150); print("ok ttm capex",round(ttm_c[-1]),"ttm ocf",round(ttm_o[-1]),"ratio",round(r,2))
