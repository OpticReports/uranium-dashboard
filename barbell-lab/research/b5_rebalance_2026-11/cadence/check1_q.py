import json,sys
import pandas as pd
D=sys.argv[1]
def ld(t):
    j=json.load(open(f"{D}/dl/{t}.json"))["chart"]["result"][0]
    idx=pd.to_datetime(j["timestamp"],unit="s",utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    return pd.Series(j["indicators"]["adjclose"][0]["adjclose"],index=idx)
R=pd.DataFrame({t:ld(t) for t in "DISVX DFSVX DFEMX ASFYX SPY GLD".split()}).pct_change()
for d in ["2016-12-12","2016-12-13","2016-12-14","2016-12-15","2016-12-16","2016-12-19","2015-12-02","2015-12-03","2015-12-04","2019-12-02"]:
    print(d, R.loc[d].round(4).to_dict())
