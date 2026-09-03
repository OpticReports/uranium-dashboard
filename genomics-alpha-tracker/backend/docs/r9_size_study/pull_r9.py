import json, os, time
import httpx

SC = os.path.dirname(os.path.abspath(__file__))
K = os.environ["FMP_API_KEY"]
BARS = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend/data/backtest_bars.json"
syms = sorted(json.load(open(BARS)).keys())
print(len(syms), "symbols")

def get(path, params):
    for a in range(4):
        try:
            r = httpx.get(f"https://financialmodelingprep.com/stable/{path}",
                          params={**params, "apikey": K}, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception:
            time.sleep(2 ** a)
    return None

def finra(sym):
    for a in range(4):
        try:
            r = httpx.post("https://api.finra.org/data/group/otcMarket/name/"
                           "consolidatedShortInterest",
                           json={"limit": 500,
                                 "compareFilters": [{"compareType": "EQUAL",
                                                     "fieldName": "symbolCode",
                                                     "fieldValue": sym}],
                                 "dateRangeFilters": [{"fieldName": "settlementDate",
                                                       "startDate": "2017-12-01",
                                                       "endDate": "2099-01-01"}]},
                           timeout=60)
            r.raise_for_status()
            return r.text
        except Exception:
            time.sleep(2 ** a)
    return None

for i, s in enumerate(syms):
    for sub, path, params in (
            ("grades", "grades", {"symbol": s}),
            ("ev", "enterprise-values", {"symbol": s, "period": "quarter", "limit": "60"}),
            ("bs", "balance-sheet-statement", {"symbol": s, "period": "quarter", "limit": "60"}),
            ("inc", "income-statement", {"symbol": s, "period": "quarter", "limit": "60"})):
        f = f"{SC}/{sub}/{s}.json"
        if os.path.exists(f) and os.path.getsize(f) > 200:
            continue
        d = get(path, params)
        if d is not None:
            json.dump(d, open(f, "w"))
        time.sleep(0.1)
    f = f"{SC}/si/{s}.csv"
    if not (os.path.exists(f) and os.path.getsize(f) > 200):
        t = finra(s)
        if t:
            open(f, "w").write(t)
    if i % 8 == 0:
        print(i, s, flush=True)
print("done")
import glob
for sub in ("grades", "ev", "bs", "inc", "si"):
    print(sub, len(glob.glob(f"{SC}/{sub}/*")))
