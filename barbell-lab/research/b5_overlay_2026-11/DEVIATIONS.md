# Deviations from PREREG.md

## Amendment 1 - 2026-11-18, BEFORE any overlay result existed
Source: independent design review of PREREG.md (counter-agent, read-only, verdict PASS WITH CORRECTIONS:
1 BLOCKING, 7 SERIOUS, 5 MINOR). Only data loading and the engine file existed when these were adopted.

D1 (BLOCKING - hedge stand-ins flatter every overlay in 2008). Every EXT/DISC result is run on TWO tapes and a
   verdict must hold on both: T1 = the registered stand-ins (TAIL<-BIL, KMLM<-RYMFX); T2 = "strong hedge":
   TAIL modelled as b*IEF + c*(CBOE PPUT - S&P 500 TR), b and c fitted on real TAIL 2017-04-07..END and applied
   before it; KMLM<-BIL + 2.0x(RYMFX - BIL) before ASFYX (a stated stress, not an estimate of KMLM).
   TAIL and KMLM leave-one-out verdicts are adjudicated on CONF only.
D2 (power). max-T is one-sided and run on a PRIMARY family of 8 arms fixed here: B3, B8, B15, B17, A1, A6, M1, M14.
   The other 45 are EXPLORATORY (full-53 max-T printed beside it). The minimum detectable Sharpe difference
   (one-sided 10%, 80% power, from the bootstrap SE) is printed beside every verdict.
D3 (warm-up). All signals warm on pre-window history from 2005-01-03 (KMLM and TAIL earn bills before RYMFX/BIL
   exist; cash = DTB3 before BIL). Trading results are measured from 2007-06-01 only. Each arm's first date off
   base weights is printed; arms inert through 2008 are flagged.
D4 (matched control). Solved PER WINDOW (EXT, DISC, CONF) on the arm's REALIZED average weights (fixed-point
   iteration on the control's targets; residual printed). SURVIVES additionally requires Sharpe >= LIVE.
D5 (placebo). All admissible circular offsets (>= 63d from either end), identical across arms, run per window.
   DRAWDOWN TOOL now requires a FAMILY-WISE placebo p < 0.10 on EXT for the drawdown improvement (per-offset
   maximum across the primary family; full-53 printed) and a lower ulcer index than the control in DISC and CONF.
D6 (legs that do not pull their weight). Leave-one-out is run both pro-rata and to-BIL with paired-bootstrap
   intervals on Sharpe, max drawdown and ulcer. A leg is FLAGGED only if dropping it improves Sharpe with an
   interval excluding zero on CONF and the same sign on EXT (both tapes).
D7 (walk-forward). LIVE is a candidate; the stitched TARGET path is run through the engine (switching costs
   paid) and scored against its own matched control and the shift placebo; it is labelled an upper bound
   (the arm menu was written with hindsight; it starts after the GFC).
D8 (harvest families added, exploratory, same exposure so the control is LIVE): H1-H3 band width 10/15/30%;
   H4 daily band check at 20%; H5 daily per-leg trim to target when any leg exceeds 1.25x target (proceeds
   pro-rata to the rest); H6 the same trim on KMLM and TAIL only.
D9 (signal trades). A signal trade moves only the legs whose target changed, against BIL (whole-book rebalance
   only if BIL cannot fund it). The placebo mean is reported as a second control.
D10 (publication lags). DTWEXBGS lagged 6 trading days (weekly release). UNRATE for month M is effective from
   the first trading day on or after the 12th of M+1 (replaces "one full month"; revisions still not modelled).
   CAPE keeps the full-month lag.
D11 (ill-defined arms). Stops with SMA100 re-entry re-enter only on a fresh upward cross (price at or below
   SMA100 at some point since the exit, then above it) or on a new high above the exit peak. A14 multipliers
   are renormalised so RISK weight is unchanged. Arms that are near-static (same state > 95% of EXT) are flagged.
D12 (stale mutual-fund NAVs). Same-close stress is reported on CONF only; any near-passer is rerun with ETF
   proxies (SCZ/EFA, EEM) in place of DISVX/DFEMX.
D13 (block length). The larger of the 21d and 63d bootstrap p-values decides.
D14 (clarifications). DISC/CONF is a sub-period consistency check, not a holdout. DSR counts every evaluated
   configuration. Volume indicators use the volume-source ETF's own return for day direction and are computed
   per source then spliced 60 trading days after the leg's ETF goes live. LEG tier is measured from 1996-01-02
   (252d warm-up after the 1995 data start).
