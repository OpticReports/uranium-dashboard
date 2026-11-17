import json,sys
import pandas as pd, numpy as np
D=sys.argv[1]
def ld(t):
    j=json.load(open(f"{D}/dl/{t}.json"))["chart"]["result"][0]
    idx=pd.to_datetime(j["timestamp"],unit="s",utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    df=pd.DataFrame({"adj":j["indicators"]["adjclose"][0]["adjclose"],"raw":j["indicators"]["quote"][0]["close"]},index=idx)
    ev=j.get("events",{})
    return df,ev
for t in "AVUV AVDV PHYS KMLM AVEM QUAL TAIL DFSVX DISVX DFEMX ASFYX GLD".split():
    df,ev=ld(t)
    print(t, "events:",list(ev.keys()), "nan adj:",int(df.adj.isna().sum()), "dup idx:",int(df.index.duplicated().sum()))
    ratio=(df.adj/df.raw)
    # implied distribution at each ratio jump: ratio_{t-1}/ratio_t = 1 - d/P_{t-1}
    jump=ratio.shift(1)/ratio  # >1 means adj factor applied before t
    cg={pd.to_datetime(int(k),unit="s",utc=True).tz_convert("America/New_York").tz_localize(None).normalize():v["amount"] for k,v in ev.get("capitalGains",{}).items()}
    dv={pd.to_datetime(int(k),unit="s",utc=True).tz_convert("America/New_York").tz_localize(None).normalize():v["amount"] for k,v in ev.get("dividends",{}).items()}
    # check cap gains: is the adj factor at cg date consistent with div only or div+cg?
    bad=0; rows=[]
    for d,a in cg.items():
        if d not in df.index: continue
        i=df.index.get_loc(d); p=df.raw.iloc[i-1]
        f_obs=jump.iloc[i]
        dd=dv.get(d,0)
        f_div=1/(1-dd/p); f_all=1/(1-(dd+a)/p)
        rows.append((d.date(),round(a,3),round(dd,3),round(f_obs,5),round(f_div,5),round(f_all,5), round(a/p*100,2)))
    if rows:
        print("  capgain events n=",len(rows)); 
        for r in rows[-8:]: print("  ",r)
    rr=df.adj.pct_change()
    print("  big moves:", [(d.date(),round(v,3)) for d,v in rr[rr.abs()>0.12].items()][:10])
