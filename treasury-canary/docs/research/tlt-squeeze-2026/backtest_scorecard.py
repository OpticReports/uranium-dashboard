"""Would the scorecard have flagged Oct 2023 (the flagship analog) in advance?
Evaluate every condition with ONLY data available as of 2023-10-20."""
import io, os
import httpx
import pandas as pd

ST = os.path.dirname(__file__)
ASOF = pd.Timestamp("2023-10-20")

def fred(series):
    r = httpx.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                  params={"id": series}, timeout=60, follow_redirects=True)
    df = pd.read_csv(io.StringIO(r.text)); df.columns = ["date", "v"]
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna().set_index("date")["v"]

# F1: lev-fund percentile PIT
tff = pd.read_csv(f"{ST}/data/tff.csv")
tff["date"] = pd.to_datetime(tff["report_date_as_yyyy_mm_dd"])
for c in ("lev_money_positions_long","lev_money_positions_short","open_interest_all"):
    tff[c] = pd.to_numeric(tff[c], errors="coerce")
d = tff[tff["contract_market_name"].isin(["UST BOND","ULTRA UST BOND","UST 10Y NOTE","ULTRA UST 10Y"])]
g = d.groupby("date").agg(l=("lev_money_positions_long","sum"),
                          s=("lev_money_positions_short","sum"),
                          oi=("open_interest_all","sum"))
g["net_pct_oi"] = 100*(g["l"]-g["s"])/g["oi"]
pit = g.loc[:ASOF, "net_pct_oi"]
print(f"F1 lev net%OI @ {pit.index[-1].date()}: {pit.iloc[-1]:+.1f}, PIT pctile "
      f"{100*(pit < pit.iloc[-1]).mean():.0f}% -> {'MET' if (pit < pit.iloc[-1]).mean() <= 0.10 else 'NOT MET'}")

# F2: TLT SI %SO — SI was 66M (Oct 13 2023 stlmt), SO ~604M (iShares later reported); ~11%
print("F2 TLT SI: 66M / ~600M SO ~ 11% -> NOT MET (was climbing; crossed 20% only mid-2024+)")

# F3: term premium PIT percentile since 2015
tp = fred("THREEFYTP10")
tp_pit = tp.loc["2015-01-01":ASOF]
print(f"F3 ACM TP @ {tp_pit.index[-1].date()}: {tp_pit.iloc[-1]:+.2f}, pctile since 2015 "
      f"{100*(tp_pit < tp_pit.iloc[-1]).mean():.0f}% -> {'MET' if (tp_pit < tp_pit.iloc[-1]).mean() >= 0.75 else 'NOT MET'}")

# T1: Fed path — Oct 2023: peak funds 5.25-5.50, held since Jul; market priced cuts mid-2024
# (fed futures history not in our pull; use known state: hold >=3 months = pre-pivot hold)
print("T1 Fed: on HOLD since Jul 2023 (3 mo), no cuts priced <6m as of mid-Oct -> NOT MET "
      "(pivot came Dec 13)")

# T2: payrolls 3m avg as of Oct 20 2023 (vintage caveat: using revised)
pay = fred("PAYEMS").diff()
p3 = pay.loc[:"2023-09-30"].tail(3)
print(f"T2 payrolls 3m avg (Jul-Sep 2023, revised): {p3.mean():+.0f}k -> NOT MET; Sahm:", end=" ")
sahm = fred("SAHMREALTIME")
print(f"{sahm.loc[:ASOF].iloc[-1]:+.2f} -> NOT MET")

# T3: core PCE 3m annualized as of Oct 2023 (Aug print available)
pce = fred("PCEPILFE").loc[:"2023-08-31"]
m3 = (pce.iloc[-1]/pce.iloc[-4])**4 - 1
print(f"T3 core PCE 3m ann (through Aug'23 print): {100*m3:.2f}% -> "
      f"{'MET' if m3 < 0.025 else 'NOT MET'}")

# T4: supply pivot — Nov 1 QRA was the trigger; on Oct 20 it was 12 days AHEAD (calendar!)
print("T4 supply: as of Oct 20 NOT MET — the QRA that met it was Nov 1, a SCHEDULED date "
      "12 days out (the calendar is the early-warning)")

# T5: MOVE
move = pd.read_csv(f"{ST}/data/MOVE.csv", parse_dates=["date"]).set_index("date")["close"]
mv = move.loc[:ASOF].iloc[-1]
print(f"T5 MOVE @ Oct 20 2023: {mv:.0f} -> {'MET (>120)' if mv > 120 else 'NOT MET'}")
