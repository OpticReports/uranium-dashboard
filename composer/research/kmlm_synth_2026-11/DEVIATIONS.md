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
8. **How F4 and F5 are scored (written before either was computed).** Window: 2021-06-01 (the first day
   every variant's indicator exists on the real fund, as in addendum 57) to 2024-03-28; the second part
   (2022-08-01 on) beside it. The real-fund run uses the corrected total-return series (6). F4 "holds the
   same" = the same set of funds in the live rule's target that session; growth = the live rule's total log
   growth. F5 = Spearman rank correlation, across the 74 variants, of total log growth minus the live
   rule's. The synthetic is cut to the fund's own first day so both runs warm up on the same sessions.

## The long-history run: design fixed before it was run (2026-11-20)

Fidelity as scored: F2-F5 pass on both windows; F1 (daily correlation >= 0.90) is 0.874 on the whole
overlap and 0.907 on the second part. On the pre-registration's own reading (the later window) all five
pass; on deviation 2's whole-window reading F1 misses. So the long history is run and judged as
pre-registered, and anything that passes on it is a CANDIDATE to be ruled on by the independent
verifiers, not a settled finding. Seen before this run: addendum 57's stand-in years (2007-09..2020-12 on
RYMFX), where longer windows averaged +0.087 log/yr (t 1.6).

9.  **Panel.** `research/longrun/long_panel.build_long_prices()` (main mode `ts_synth`), with its KMLM
    series replaced by the synthetic (today's rules; exposure as calibrated; deviation 7 for markets with
    no data yet). The synthetic's calendar is the long panel's SPY sessions; it must reproduce the
    fidelity run's series on every later day (checked in code).
10. **Three stretches, never pooled across the model line.**
    REAL 2021-06-01..2026-11-19: the real fund (corrected total return), as addendum 57.
    REPLICATION 2008-02-01..2020-12-01: every one of the 22 markets has data and VIX-fund returns come
    from the real VIX term structure. (Leveraged and sector funds before their launch are their index
    times the leverage, as the long panel builds them.)
    MODEL 1991-04-01..2008-01-31: VIX funds are a model of futures that did not trade (before 2004) or of
    a curve fitted from the VIX alone (to 2006-07); the euro, JGB and Bund legs are missing for part of it;
    sector funds before 1998 are industry portfolios. Shown, with the two other VIX-model modes as a
    range; it cannot carry a verdict.
    1991 is as far as the VIX itself goes back (1990) plus the warm-up: 50 years is not reachable for THIS
    symphony because a third of its tree trades volatility funds.
11. **Cells.** The 62 switch-type variants. The 12 threshold variants (F3) are not run before 2021: their
    thresholds were calibrated on 1990-2020 data.
12. **Verdict rule** (the five conditions of addendum 57 on REPLICATION + REAL joined, 62 cells):
    (1) ahead, family-wise p < 0.10, max-statistic stationary bootstrap (mean block 10, 5,000 draws,
    studentised, centred); (2) ahead in REPLICATION and in REAL separately; (3) neighbours on its grid
    also ahead; (4) max drawdown no more than 5 points worse than the live rule's in each stretch;
    (5) still ahead at double cost. Also reported: each cell's MODEL-years result, the long (14-60) and
    short (3-8) window group averages per stretch, and the smallest gain the test could see.
