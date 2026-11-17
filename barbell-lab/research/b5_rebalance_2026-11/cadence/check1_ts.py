import json,sys,collections
import pandas as pd
D=sys.argv[1]
for t in "AVUV AVDV PHYS KMLM AVEM QUAL TAIL DFSVX DISVX DFEMX ASFYX GLD SPY".split():
    j=json.load(open(f"{D}/dl/{t}.json"))["chart"]["result"][0]
    ts=pd.to_datetime(j["timestamp"],unit="s",utc=True)
    hrs=collections.Counter(ts.tz_convert("America/New_York").strftime("%H:%M"))
    print(t,len(ts),ts.min().date(),ts.max(),j["meta"].get("exchangeTimezoneName"),j["meta"].get("dataGranularity"),hrs.most_common(3))
