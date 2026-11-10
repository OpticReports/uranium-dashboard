#!/usr/bin/env bash
# Keyless data pull for studies/oil-shock-recession-weight.md (spec v1).
# Re-run from this folder: ./fetch_data.sh && python3 parse_tic.py && python3 build_panel.py
set -euo pipefail
cd "$(dirname "$0")/data"
for s in WTISPLC WPU0561 DCOILWTICO DCOILBRENTEU CPIAUCSL USREC TB3MS GS10 T10Y3M DGS10 DGS3MO \
         FEDFUNDS UNRATE INDPRO PAYEMS WMTSECL1 DTWEXM DTWEXBGS DNRGRC1M027SBEA PCE; do
  curl -sS -m 90 -o "$s.csv" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$s"
done
# S&P 500 daily from 1927-12-30 (period1 = 0 would silently start at 1970 and left-censor the 1968 peak)
curl -sS -m 180 -A "Mozilla/5.0 (canary-study)" \
  "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?period1=-1325583000&period2=4102444800&interval=1d" \
  -o gspc_daily_1927.json
# TIC Major Foreign Holders history (2000-03 .. present)
curl -sS -m 90 -A "Mozilla/5.0" -o mfhhis01.txt \
  "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/mfhhis01.txt"
# Dallas Fed / Kilian index of global real economic activity
curl -sS -m 90 -A "Mozilla/5.0" -o igrea.xlsx \
  "https://www.dallasfed.org/-/media/Documents/research/igrea/igrea.xlsx"
ls -la
