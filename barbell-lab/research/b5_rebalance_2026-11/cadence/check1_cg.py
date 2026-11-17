import json,sys
import pandas as pd, numpy as np
D=sys.argv[1]
def ld(t):
    j=json.load(open(f"{D}/dl/{t}.json"))["chart"]["result"][0]
    idx=pd.to_datetime(j["timestamp"],unit="s",utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    df=pd.DataFrame({"adj":j["indicators"]["adjclose"][0]["adjclose"],"raw":j["indicators"]["quote"][0]["close"]},index=idx).dropna()
    dv={pd.to_datetime(int(k),unit="s",utc=True).tz_convert("America/New_York").tz_localize(None).normalize():v["amount"] for k,v in j["events"].get("dividends",{}).items()}
    return df,dv
for t in "DFSVX DISVX DFEMX ASFYX".split():
    df,dv=ld(t)
    ratio=df.adj/df.raw; jump=ratio.shift(1)/ratio
    rawr=df.raw.pct_change(); adjr=df.adj.pct_change()
    print(t)
    # days where raw dropped >3% in December, and whether adj also dropped
    sel=df.index[(df.index.month==12)&(rawr< -0.03)&(df.index.year>=2012)&(df.index.year<=2021)]
    for d in sel:
        i=df.index.get_loc(d)
        print("  ",d.date(),"raw %.3f adj %.3f div %.3f p %.2f impl_dist %.3f"%(rawr.iloc[i],adjr.iloc[i],dv.get(d,0),df.raw.iloc[i-1],(1-1/jump.iloc[i])*df.raw.iloc[i-1]))
    # all ratio jumps pre-2021 vs dividends
    big=jump[(jump-1).abs()>1e-4]
    mism=[(d.date(),round((1-1/v)*df.raw.shift(1)[d],3),dv.get(d,0)) for d,v in big.items() if abs((1-1/v)*df.raw.shift(1)[d]-dv.get(d,0))>0.01]
    print("  adj-factor events:",len(big),"mismatch vs div events:",mism[:6])
