# Oil shocks and recession odds — how much weight does oil deserve? (spec v0, pre-registered)

**Status: SPEC — written 2026-09-15 BEFORE any number was computed.** Results are appended
below the spec once the pre-specified tests run; nothing in §2–§5 may be edited after
results exist except to log an amendment with its date and reason.

## 0. Why this study

Casey (2026-09-15): we are in an oil shock / elevated-oil regime; the canary scores oil on
the pin board; how is oil's contribution to RECESSION ODDS weighted, have we backtested
prior oil-shock regimes, and what weight should it get given that "all indicators are not
equal — some are larger markets with larger effects" and "we're on a petrodollar system"?

## 1. What the canary does with oil today (audit of the deployed instrument)

| Where | What oil does | Weight in recession odds |
|---|---|---|
| Recession dial (`/recession-model`) | nothing — horizon probits on the 3m10y spread only (plus a term-premium-adjusted twin) | **0** |
| Pin board `oil_shock` channel (`pins.py`) | WTI 12-month % change; anchors 0 / +25 / +50 / +100 (benign / yellow / red / extreme); mass $20T (household consumption), speed 3–12m, kill rate "preceded ~10 of 11 postwar recessions (Hamilton)" | none — static badges, "never fitted" by design |
| Pin history / damage windows (`pin_history.py`) | red episodes cast a 3–12 month window forward (Hamilton lag) | none |
| Accident composite hindcast (`studies/pin-rule-hindcast.md` v3) | measured an **oil-OR-policy window** rule bundled with `policy_shock`: +curve 45% / 5-of-6 on drawdowns, 37% / 4-of-4 on onsets | oil never isolated |
| Flow compass (`flows.py`) | oil's 20d return as a regime discriminator (supply shock vs demand fear) | none |
| Prior probit-augmentation test (glossary `transmission_note`, `pins.py` NFCI horse race) | financial-conditions index added nothing walk-forward → "the calibrated probability is never adjusted" | oil was not tested |

So: **no standalone oil backtest has ever been run**, the deployed oil history starts in
1986 (FRED `DCOILWTICO`), so the 1973, 1979–80 and 1990 shocks — the whole basis of the
Hamilton kill-rate claim — have never been in-sample for this instrument, and oil's weight
in the recession odds is zero by construction.

## 2. Questions (fixed before measurement)

- Q1. Is an oil shock, on its own, a usable recession signal on the full postwar record —
  precision vs base rate, lead times, and named false positives?
- Q2. Does oil add information BEYOND the yield curve, out of sample (the weighting question)?
- Q3. Has the relationship changed by regime: regulated/OPEC era (≤1985), 1986–2008,
  shale era 2009–2019, US net-petroleum-exporter era (2020+)? Supply-driven vs demand-driven
  price rises (Kilian)?
- Q4. Petrodollar thesis: do high oil prices show up as foreign-official Treasury demand
  (recycling), and did that link hold in the last two shocks?
- Q5. What does the instrument read RIGHT NOW under each definition, and what would the
  answer to Q2 imply for today's odds?

## 3. Data (all public, keyless; frozen copies in the study's data folder)

| Series | Use | Coverage | Caveat |
|---|---|---|---|
| FRED `WTISPLC` monthly spot WTI | the long oil price | 1946-01+ | pre-1983 prices are posted/regulated (1971–81 price controls) — steps, not a market; cross-checked against `WPU0561` |
| FRED `WPU0561` PPI crude petroleum | cross-check for pre-1986 path (Hamilton's series) | 1947-01+ | producer price, not spot |
| FRED `DCOILWTICO` daily WTI → monthly mean | what the deployed channel reads | 1986+ | |
| FRED `CPIAUCSL` | real oil | 1947+ | |
| FRED `USREC` | NBER recession months → onsets | full | NBER dates 4–12m after the fact; outcome truth uses final dating |
| FRED `GS10`−`TB3MS` | 3m10y curve 1953+ | 1953-04+ | bills on discount basis: understates BEY 20–40bp (BACKTEST.md caveat); `T10Y3M` (CMT) used where available (1982+) — the live dashboard's instrument |
| FRED `FEDFUNDS`, `INDPRO`, `UNRATE`, `PAYEMS` | policy pace; supply/demand split; context | 1954+/1919+ | INDPRO is revised (vintage bias, disclosed) |
| Yahoo `^GSPC` daily → monthly close/low | ≥15% drawdown starts | 1970+ (this pull) | same construction as `pin_history._drawdown_spans` |
| FRED `WMTSECL1` Fed custody (weekly → monthly) | foreign-official UST demand | 2002-12+ | |
| TIC Major Foreign Holders history | "Oil Exporters" aggregate 2000–2011; Saudi Arabia / UAE / Kuwait / Norway / Iraq individually 2012+ | 2000+ | baskets differ across the 2012 break — never spliced |

Shared panel: one monthly CSV built once (`build_panel.py`) and read by every test, so all
blocks use identical inputs.

## 4. Pre-specified definitions (no threshold search)

Oil-shock definitions:
- **D1 — deployed rule.** Nominal WTI 12-month % change ≥ +25 (YELLOW), ≥ +50 (RED). This
  is exactly the live `oil_shock` channel, applied to the 1946+ series.
- **D2 — Hamilton net oil price increase (NOPI).** log(WTI) − max(log WTI over the prior 36
  months), floored at 0. "On" when ≥ +10 log-pct (a material new 3-year high). Hamilton
  1996/2003's transform; chosen because a price RECOVERY after a crash (2009–10, 2021) is
  not a shock under NOPI but IS under D1.
- **D3 — real oil.** WTI/CPI 12-month % change ≥ +25 / ≥ +50 (same anchors as D1).
- **Curve flat** (the deployed accident-gauge condition): min 3m10y over the trailing 6
  months < +0.25pp.
- **Supply vs demand split (Kilian proxy):** an oil-shock month is "demand-driven" when
  INDPRO 12-month growth is above its trailing-10-year median, "supply-driven" otherwise.
  Crude proxy, stated as such — a full Kilian decomposition needs global production and
  shipping data we do not have.
- **Regimes:** R0 1947–1985 (regulated/OPEC), R1 1986–2008 (market pricing, US net
  importer), R2 2009–2019 (shale), R3 2020+ (US net petroleum exporter; EIA: first
  net-export year 2020). R3 contains one onset (2020-03, pandemic) — no power; report as such.

Event sets: NBER onsets (1948-12 … 2020-03; 11 inside the 1953+ curve window); ≥15% SPX
drawdown starts (1970+, 12 events), each judged "hit" if it BEGINS within the horizon.

Horizons: 12 months (headline, matches the dial) and 18 months (Hamilton's 3–12m lag can
straddle the 12m cutoff; reported second, never used to rescue a miss).

Statistics (all pre-specified):
- Month-level precision = P(event within h | rule on), vs base rate over the same window.
- Cluster-level: contiguous "on" runs = episodes; hit rate = episodes followed by an event;
  recall = events preceded by an "on" month within h. Every episode is NAMED with its
  outcome (hit / false positive / pending) — no anonymous counts.
- Probits at horizons 6/12/18/24, monthly, on the 1953+ panel: (a) curve only (the deployed
  model, refit here), (b) curve + oil, (c) oil only; oil enters once as NOPI36 and once as
  the 12m % change (two pre-declared specifications, both reported, no picking). Report
  coefficient, z, in-sample AUC, McFadden pseudo-R².
- Walk-forward: expanding window, refit every month, first prediction 1970-01 (same design
  as BACKTEST.md §B), score OOS AUC, Brier and log-score for (a) vs (b). Uncertainty: moving
  block bootstrap on months (block = 12) for the AUC difference, 1,000 draws, seed 20260915.
- **Decision rule for "oil adds weight" (fixed now):** OOS AUC(b) − AUC(a) ≥ +0.02 AND OOS
  Brier improves AND the oil coefficient is positive in ≥ 90% of walk-forward refits. Any
  one failing → oil does NOT earn a numeric weight in the odds.
- Marginal effect, reported regardless: Δ P(recession, 12m) for a +50% oil shock at spread
  = 0 and at spread = +1pp, from the in-sample (b) fit. Descriptive.
- Petrodollar: correlation (and sign) between 12m oil change and 12m change in oil-exporter
  UST holdings (TIC) and in Fed custody; the 2014–16 crash and 2022 spike reported as
  named episodes. No causal claim.

## 5. Pre-registered outcomes → actions

| Result | Canary change |
|---|---|
| Q2 decision rule MET | add an **oil-augmented probit variant** to `/recession-model`, displayed beside the raw and TP-adjusted dials exactly as the TP-adjusted variant is — never blended into the headline (standing rule: the calibrated probability is never adjusted) |
| Q2 decision rule NOT met | recession odds stay curve-only; the measured non-result is recorded in the oil channel's `certainty`/`kill_rate` text and in `pin_history.measured_roles` |
| D2 (NOPI) beats D1 on cluster precision with equal-or-better recall | switch the channel's trigger leg to NOPI (or add it as a second part) with anchors set from the measured episode distribution, documented like every other anchor |
| Kill-rate claim differs from the measured record | rewrite `kill_rate` to the measured count (e.g. "n of m postwar onsets, k false positives named") |
| R3 (net-exporter era) evidence or literature shows the transmission changed | add a regime note to the channel's `certainty` string and glossary entry |
| Always | split `studies/pin_rule_hindcast.py`'s oil-OR-policy rule into oil-alone and policy-alone and re-report; add the study script under `studies/` so it re-runs keyless |

## 6. Honesty box (to be completed with results)

Sample: ~11 onsets, ~9 oil-shock episodes — cluster-level 95% CIs are ±30pp wide. Prices
are unrevised; INDPRO is revised (favours the supply/demand split). The 1973 and 1979
shocks arrived with Fed tightening and price controls — oil and policy are confounded in
exactly the episodes that anchor the kill-rate claim. Thresholds (+25/+50, NOPI ≥10) are
the deployed anchors and Hamilton's transform, not searched — but Hamilton chose his
transform after seeing 1973–1990. All numbers are descriptive history, never calibration.

---
_Results appended below by the study run; counter-agent verdicts logged alongside._
