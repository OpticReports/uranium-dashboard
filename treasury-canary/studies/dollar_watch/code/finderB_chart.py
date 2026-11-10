import pandas as pd, numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, matplotlib.dates as mdates, sys
S=pd.read_pickle(sys.argv[1]); out=sys.argv[2]
EP=[('2008 GFC','2007-06-01','2009-06-30','2009-03-03'),('2015-16 EM/China','2014-07-01','2016-06-30','2016-01-20'),('2018 EM/Q4','2018-01-01','2019-03-31','2018-11-27'),('2020 COVID','2020-01-01','2020-09-30','2020-03-23'),('2022 Fed hikes','2022-01-01','2023-03-31','2022-09-26')]
ROWS=[('usd_broad','Broad dollar (index)','#2a78d6'),('cp_fin_spread','Fin. CP 3m − T-bill (pp)','#eb6834'),('ofr_funding','OFR FSI funding subindex','#1baf7a'),('swpt','Fed CB liquidity swaps ($bn)','#6250d6'),('emfx_basket','EM FX basket (↑ = EM weaker)','#e34948'),('gold','Gold $/oz','#eda100')]
fig,axes=plt.subplots(len(ROWS),len(EP),figsize=(18,13),facecolor='#fcfcfb')
for j,(name,a,b,pk) in enumerate(EP):
    for i,(k,lab,col) in enumerate(ROWS):
        ax=axes[i,j]; s=S[k]; w=s[(s.index>=a)&(s.index<=b)]
        if k=='swpt': w=w/1000
        ax.plot(w.index,w.values,color=col,lw=1.6); ax.axvline(pd.Timestamp(pk),color='#52514e',lw=0.8,ls='--')
        ax.set_facecolor('#fcfcfb'); ax.grid(alpha=0.25); ax.tick_params(labelsize=8)
        for sp in ('top','right'): ax.spines[sp].set_visible(False)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4 if (pd.Timestamp(b)-pd.Timestamp(a)).days>400 else 2)); ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
        if i==0: ax.set_title(f'{name}\n$ peak {pk}',fontsize=10,color='#0b0b0b')
        if j==0: ax.set_ylabel(lab,fontsize=9,color='#52514e')
        if len(w): 
            ext=w.idxmax() if k not in ('gold',) else w.idxmin(); ax.plot([ext],[w.loc[ext]],'o',ms=5,color=col,mec='#fcfcfb',mew=1.5)
fig.suptitle('Dollar-funding stress by episode: leading series peak BEFORE the broad dollar (dashed = broad-dollar peak; dot = series extreme)\nSources: FRED DTWEXBGS/DTWEXB, DCPF3M−DTB3, SWPT, DEX* pairs; OFR FSI; FMP XAUUSD', fontsize=11, color='#0b0b0b')
fig.tight_layout(rect=(0,0,1,0.95)); fig.savefig(out,dpi=110); print('saved',out)
