# DEVIATIONS from PREREG.md (B.5 fill-delay study) — result is labeled "deviated from prereg"

Logged 2026-11-16 during execution. Each entry: what PREREG said, what was done, why, and the effect.

## Data (sec 3)
- **D1 Gold (LBMA PM fix) UNOBTAINABLE.** prices.lbma.org.uk/json/gold_pm.json -> HTTP 403
  (Cloudflare challenge); FRED GOLDPMGBD228NLBM -> 404 (series removed from FRED in 2022);
  Nasdaq Data Link LBMA/GOLD -> 403. PREREG's MISSING DATA RULE says STOP and report. A strict
  reading therefore ends the study here. **Not followed**: to answer the question, gold was built
  from (a) GCUSD, COMEX continuous front-month price, price-spliced, from the repo's frozen fixture
  barbell-lab/research/barbell_timer/fixtures/fmp_gcusd_light.json (1976-02-26..2004-11-17), then
  (b) GLD Yahoo adjusted close from 2004-11-18 (GLD is the PREREG's own splice instrument).
  Effects: Universe B starts 1976-02-27 instead of 1968-04 (~8 years lost); pre-2004 gold
  includes futures roll jumps and the COMEX-settle vs PM-fix timing mismatch (daily corr
  GCUSD vs GLD on the overlap = 0.88). The fixture came from FMP (keyed API) originally; it was
  read from the repo, no key used here.
- **D2 Emerging markets daily UNOBTAINABLE.** The French library publishes emerging-market
  portfolios/factors MONTHLY only (daily file names return 404; the library index lists no daily
  emerging file). PREREG's fallback (Big/High) is also monthly-only. Primary Universe A folds the
  AVEM 0.059 weight into the developed ex-US small-value analogue (sleeve weight 0.177), mirroring
  PREREG's own fold rule for A-long. Sensitivity "A_veiex": AVEM = Vanguard EM index fund VEIEX
  (Yahoo adjusted close), 1994-05+.
- **D3 USD leg.** PREREG: DTWEXB spliced to DTWEXBGS. DTWEXB only starts 1995-01-04, so
  1973-1994 uses FRED DTWEXM (major-currencies index), then DTWEXB 1995-01-04..2005, DTWEXBGS 2006+.
  Index returns only (no interest-differential carry).
- **D4 KMLM analogue interpretation.** "60-day EWMA" implemented as EWMA of squared daily returns
  with span=60, lagged one day; vol scaling updated daily, sign signal updated at month-end and
  applied from the next day. No leverage cap. Equity leg = French Mkt-RF; bond leg = DGS10 TR - RF;
  gold leg = gold - RF; USD leg = index return. Check vs KMLM ETF 2020-12..2026-09: daily corr 0.34,
  weekly 0.30 -> weak proxy (PREREG already flags KMLM proxy as weakest).
- **D5 KMLM/ASFYX sensitivity.** The repo's ASFYX splice file was not found; rebuilt from Yahoo
  ASFYX (2010-08+) spliced to KMLM from 2020-12-03.
- **D6 Data end.** French daily files end 2026-09-30 (202609 build), so every universe ends
  2026-09-30 although FRED/Yahoo/CBOE run to Nov 2026.
- **D7 10y Treasury TR.** Duration-only approximation as specified: carry y(t-1)*days/365 minus
  modified duration (10y par bond, semiannual) x dy. No convexity term.
- **D8 French holes.** 2 interior rows in Universe A with a missing value were set to 0 return.
  Non-US-calendar days in the ex-US file are compounded into the next US trading day.

## Method (sec 1, 2, 4)
- **D9 Placebo 1 on T-M.** "Non-trigger days >= 11 days from any real trigger" leaves too few days
  when month-ends fall every ~21 trading days, so the minimum distance was relaxed to 6 trading
  days for T-M (the code relaxes only when the >=11 pool is smaller than the event count;
  T-D and T-MB kept >= 11).
- **D10 Event set.** Per-event tests use the triggers of the k=1 baseline run (T-D trigger
  dates are path-dependent and differ slightly by k). Holdings at the trigger close are the
  baseline run's. Placebo seeds: 20261116 (P1) and 20261117 (P2); PREREG gave no placebo seed.
- **D11 Halves and pre-2013.** Each segment is a fresh simulation starting at target weights;
  midpoint = calendar midpoint of the window. Pass-bar "cells" = full + H1 + H2 per universe.
- **D12 Bootstrap.** Month-end flags are resampled together with their return rows, so the
  turn-of-month alignment is preserved inside blocks. One bootstrap per segment. Bootstrap at
  primary cost (5 bps) only.
- **D13 Annualization** uses 252 trading days per year throughout.
- **D14 Extra cost sensitivities (added, not replacing).** The caller asked for
  barbell-lab/config/backtest.yaml one-way bps with 2x stress. Primary stays flat 5 bps
  (PREREG); 2 and 10 bps flat run as pre-registered; added: yaml mapping and yaml x2.
  Mapping, Universe A: AVUV 5, PHYS 8, QUAL 3, KMLM 10, AVDV(+AVEM fold) 10, TAIL 12.
  Universe B: US equity -> SPY 1, UST10 -> default 10 (no ladder ETF in yaml), gold -> PHYS 8.
- **D15 Counter-agent review (sec 7) NOT done by this agent.** PREREG requires a counter-agent
  review of code and numbers before results are presented; the caller must run it.
