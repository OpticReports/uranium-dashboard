"""Parse TIC 'Major Foreign Holders' history (mfhhis01.txt, 2000-03..2025-12) into
a monthly CSV of oil-exporter Treasury holdings ($bn) and their share of the total.

Two UNSPLICED segments (spec v1, §3):
  seg1 2000-03..2011-12: TIC 'Oil Exporters' aggregate (footnote 3/ basket:
        Ecuador, Venezuela, Indonesia, Bahrain, Iran, Iraq, Kuwait, Oman, Qatar,
        Saudi Arabia, UAE, Algeria, Gabon, Libya, Nigeria). Norway is NOT in it.
  seg2 2012-01+: named basket3 = Saudi Arabia + UAE + Kuwait (reported every month 2012+);
        basket4 adds Iraq where TIC lists it (2012-2019, 2022) — secondary.
        Norway (GPFG) kept as its own column, never summed in.
Benchmark breaks: 2002-2011 blocks carry TWO 'Jun' columns (revised Series N first,
prior Series N-1 second). We keep the FIRST (revised) June so Jun..Dec of each
block sits on one series; 12m changes are only meaningful within a segment.
"""
import re, pandas as pd

import os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
WANT = {"Oil Exporters": "oil_exporters", "Saudi Arabia": "saudi", "United Arab Emirates": "uae",
        "Kuwait": "kuwait", "Norway": "norway", "Iraq": "iraq", "Grand Total": "grand_total"}

rows: dict = {}
months = years = None
for line in open(f"{D}/mfhhis01.txt", encoding="latin-1"):
    cells = [c.strip() for c in line.rstrip("\n").split("\t")]
    if len(cells) > 1 and cells[1] in MON and cells[0] == "":
        months = [c for c in cells[1:] if c in MON]
        continue
    if cells[0] == "Country":
        years = [c for c in cells[1:] if re.fullmatch(r"\d{4}", c)]
        continue
    key = re.sub(r"\s+\d+/$", "", cells[0].strip('"')).strip()
    if key in WANT and months and years:
        vals = cells[1:1 + len(months)]
        seen = set()
        for mth, yr, v in zip(months, years, vals):
            k = pd.Timestamp(int(yr), MON[mth], 1)
            if (k, WANT[key]) in seen:      # duplicate June: FIRST (revised) wins
                continue
            seen.add((k, WANT[key]))
            try:
                x = float(v.replace(",", ""))
            except ValueError:
                continue
            rows.setdefault(k, {})[WANT[key]] = x
df = pd.DataFrame.from_dict(rows, orient="index").sort_index()
df.index.name = "date"
df["basket3"] = df[["saudi", "uae", "kuwait"]].sum(axis=1, min_count=3)   # seg2 primary (always reported 2012+)
df["basket4"] = df[["saudi", "uae", "kuwait", "iraq"]].sum(axis=1, min_count=4)  # +Iraq where reported
df["seg1_share_pct"] = df["oil_exporters"] / df["grand_total"] * 100.0
df["seg2_share_pct"] = df["basket3"] / df["grand_total"] * 100.0
df["seg2b_share_pct"] = df["basket4"] / df["grand_total"] * 100.0
df["norway_share_pct"] = df["norway"] / df["grand_total"] * 100.0
df.to_csv(f"{D}/tic_oil_exporters.csv")
print(df.shape)
print(df.loc["2011-06-01":"2011-07-01"].to_string())
print(df.loc["2010-06-01":"2010-07-01", ["oil_exporters", "grand_total"]].to_string())
print(df[["oil_exporters", "basket3", "basket4", "norway", "grand_total"]].notna().groupby(df.index.year).sum().T.to_string())
