import io
import httpx
import pandas as pd

def fred(series):
    r = httpx.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                  params={"id": series}, timeout=60, follow_redirects=True)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "v"]
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna().set_index("date")["v"]

pay = fred("PAYEMS")
chg = pay.diff()
print("payrolls last 6:", [(d.strftime('%Y-%m'), f"{v:+.0f}k") for d, v in chg.tail(6).items()])
print("3m avg:", f"{chg.tail(3).mean():+.0f}k")

sahm = fred("SAHMREALTIME")
print("Sahm:", sahm.index[-1].date(), sahm.iloc[-1], "(trigger 0.50)")

pce = fred("PCEPILFE")
m3 = (pce.iloc[-1] / pce.iloc[-4]) ** 4 - 1
yoy = pce.iloc[-1] / pce.iloc[-13] - 1
print(f"core PCE ({pce.index[-1].date()}): 3m ann {100*m3:.2f}%  yoy {100*yoy:.2f}%")

cpi = fred("CPILFESL")
m3c = (cpi.iloc[-1] / cpi.iloc[-4]) ** 4 - 1
print(f"core CPI ({cpi.index[-1].date()}): 3m ann {100*m3c:.2f}%  yoy {100*(cpi.iloc[-1]/cpi.iloc[-13]-1):.2f}%")

hy = fred("BAMLH0A0HYM2")
print(f"HY OAS: {hy.iloc[-1]:.2f} ({hy.index[-1].date()}), 3m ago {hy.iloc[-64]:.2f}")

unrate = fred("UNRATE")
print(f"UNRATE: {unrate.iloc[-1]} ({unrate.index[-1].date()}), 12m low {unrate.tail(13).min()}")
