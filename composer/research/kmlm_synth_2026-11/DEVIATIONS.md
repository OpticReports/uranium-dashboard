# Deviations from PREREG.md (each recorded before the affected number was computed, unless it says otherwise)

Seen before the build (the scouting pass's rough first fit, 2021-03-01..2024-03-28, nothing tuned): daily
correlation with the corrected fund 0.871 (2023-01..2024-03: 0.920), switch-flag agreement 96.4% (98.1%),
monthly correlation with the published index 2008-03..2020-11 0.967, synthetic vol 13.9% vs fund 16.7%.
RYMFX on the same days: 0.612 and 86.9%.

1. **The one scalar is calibrated on the PUBLISHED INDEX, not on the fund.** Exposure = the least-squares
   slope (through the origin) of the index's monthly return on the synthetic's gross monthly return over the
   months before the fund existed where all 22 markets have data. So NO fund data is used to build the
   synthetic, and the whole fund overlap is validation. Stricter than the pre-registration.
2. **The fidelity bars are read on 2021-03-01..2024-03-28**, the days where the fund has 60 closes for its
   RSI and the futures files have data (they end 2024-03-28), and separately on the second part
   (2022-08-01..2024-03-28). The pre-registered halves (split at 2023-12-01, to the last close) cannot be
   scored: no roll-adjusted futures data after 2024-03 is reachable from here.
3. **The signal rule is inferred from the fund's published holdings, not from a rulebook** (none is public):
   a market's strength at the close of D is the average over the 21 sessions ending D-1 of the daily sign
   of (price above its 252-session simple average); the position is the strength times a fixed notional.
   The scout found this on 21 holdings files; the published text says only "a daily trend signal ... versus
   its long-term moving average ... executed in small increments over a period of several days".
4. **Notionals:** the published basket split (commodities 25%, currencies 32.5%, global bonds 42.5%), equal
   within a basket, reset on the first session of each month, times the one exposure scalar. Cash earns
   T-bills on all assets. Costs 0.90% (expense ratio) + 0.15% (the fund's own estimate of trading costs).
5. **The signal is read on each market's excess-return index** (the held contract's daily returns chained),
   the documented "synthetic price ... rolling forward futures contracts", not on a raw front-month price.
6. **The fund is measured on its corrected total return** (raw closes plus the distributions on the fund's
   page): Yahoo's adjusted close understates the 2022-12-28 distribution ($2.481 for $4.037692).
7. **Before a market's data starts, its basket is split among the markets that have data** (equal within
   the basket; basket shares unchanged). The index committee's actual historical market list is not public.
