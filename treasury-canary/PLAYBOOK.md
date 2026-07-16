# The Canary Playbook — Conditional Asset Returns by Dashboard State

_An event study of what U.S. equities, 10-year Treasuries, and cash actually did
after each of this dashboard's state transitions, 1957–2026, with prescriptive
implications. Generated data: `PLAYBOOK_DATA.json` (reproduce:
`python -m scripts.event_study`). Research, not investment advice._

---

## 1. Methodology (read before the tables)

**Events.** Four state transitions, defined *identically* to the live dashboard
and the backtest (no bespoke definitions): sustained-inversion start,
dis-inversion (re-steepening), Sahm-Rule trigger, and leading-stack majority
alarm. Event dates come from the same code paths that light the dashboard.

**Assets & returns.** Monthly, 1957→present:
- *Equities:* OECD U.S. share-price index — **price-only; dividends omitted**.
  This understates absolute equity returns by roughly 2–4%/yr, but the
  conditional-vs-baseline comparison is on equal footing (both omit dividends).
- *10y Treasury:* total-return approximation from GS10 yields — carry +
  duration×Δy + ½·duration²·Δy² (standard literature shortcut; par-bond
  modified duration).
- *Cash:* 3-month bill, compounded monthly.
- *Gold:* **omitted** — no clean free long-history series (FRED's LBMA feed is
  dead). Episode record, qualitatively: gold performed strongly in the
  1973–75 and 2007–09 windows and *fell* in the forced-liquidation phase of
  March 2020 before rallying. We do not put numbers on what we cannot source.

**Honest statistics.** 5–10 events per state is a small sample. We report
medians with min/max ranges and every episode individually (in the data file /
Playbook tab). No significance tests are quoted because none would be honest at
this N. Regime mix matters: pre-1985 events occurred amid high inflation where
duration hedged poorly; post-1990 events in the disinflation regime where it
hedged well. Weight the modern episodes accordingly.

**Baseline.** Unconditional forward returns computed from *every* month in the
sample: equities **+9.4%**, 10y Treasury **+3.8%**, cash **+4.5%** per 12
months (medians). Every conditional number below should be read against these.

---

## 2. Findings by state

### State: SUSTAINED INVERSION BEGINS (9 events)

| Horizon | Equities | 10y Treasury | Cash |
|---|---|---|---|
| 3m | +2.9% | +3.1% | +1.5% |
| 6m | +0.3% | +5.8% | +3.0% |
| **12m** | **−5.8%** (vs +9.4% base) | **+4.9%** (vs +3.8%) | **+5.0%** |
| 24m | +2.0% | **+12.9%** | +10.5% |

**Reading.** The inversion is the *regime change* moment: over the following
12 months equities underperform their baseline by ~15 percentage points
(median −5.8% vs +9.4%), while duration and cash both beat their baselines.
Note the 3–6 month numbers: equities are still flat-to-positive — **inversion
is not a sell-everything-today signal**; it is the start of a repositioning
window. Cash yields are mechanically high when the curve inverts (that's what
an inversion is), which is why cash competes so well here.

### State: DIS-INVERSION / RE-STEEPENING (9 events) — the canary itself

| Horizon | Equities | 10y Treasury | Cash |
|---|---|---|---|
| 3m | −0.8% | +0.7% | +1.2% |
| **6m** | **−5.6%** | +2.3% | +2.2% |
| 12m | +6.0% | **+8.6%** (vs +3.8%) | +4.4% |
| **24m** | **+19.9%** | **+23.5%** | +10.6% |

**Reading.** This is the sharpest table in the study, and it validates the
canary's design three ways:
1. **The 0–6 month window after dis-inversion is the worst equity window in
   the entire study** (median −5.6% at 6m). The backtest found recession onset
   follows dis-inversion by a median of 5 months (modern era: 3/8/5) — these
   forward returns are that fact expressed in prices.
2. **Duration is the asset of this state**: +8.6% at 12m and +23.5% at 24m —
   roughly 2–3× baseline — because dis-inversion typically happens when the
   front end collapses as the Fed cuts into weakness.
3. **The 24-month equity number (+19.9%) is the recovery**: selling equities
   at dis-inversion and never re-entering forfeits the rebound. The state is a
   *timing* signal for a 6–12 month defensive window, not a permanent exit.

### State: SAHM TRIGGER (10 events)

| Horizon | Equities | 10y Treasury | Cash |
|---|---|---|---|
| 3m | −1.2% | +0.6% | +1.2% |
| 6m | +1.8% | +0.4% | +2.3% |
| 12m | +4.1% | +2.5% | +4.8% |
| 24m | +0.9% | +4.9% | +9.9% |

**Reading.** The single most important prescriptive nuance in this study:
**the Sahm trigger is too late to de-risk.** By the time it fires, the
recession has begun and equities have typically already drawn down — forward
12-month equity returns from the trigger are *positive* (+4.1%), because you
are often closer to the bottom than the top. Treasury returns are mediocre
(many triggers landed in the 1970s–80s inflation regime). The Sahm trigger's
correct uses are: (a) confirmation that the curve's earlier warning was real,
(b) the *starting gun for planning re-entry*, and (c) a stop on adding new
defensive trades — not initiating them.

### State: LEADING-STACK MAJORITY ALARM (5 events)

| Horizon | Equities | 10y Treasury | Cash |
|---|---|---|---|
| 3m | +8.6% | +1.5% | +1.2% |
| 6m | +4.0% | +2.3% | +2.1% |
| 12m | +8.1% | +6.6% | +4.3% |
| 24m | **−2.7%** | **+21.9%** | +7.4% |

**Reading.** Only 5 events — treat gently. The pattern: near-term equity
returns after breadth alarms are *good* (the 2023-11 false positive's monster
rally sits in these medians), but the 24-month picture inverts hard (equities
−2.7%, duration +21.9%). Breadth alarms mark *late-cycle* conditions: momentum
can carry risk assets for months, but the two-year risk/reward decisively
favors duration. This is a "stop adding risk / start building the defensive
book" state, not a market-timing trigger.

---

## 3. The prescriptions (exacting, state-by-state)

Framed for a family-office mandate: sizes are expressed as *tilts from your
strategic allocation*, not absolute bets. All figures reference the tables
above; every claim is traceable to the data file. The failure modes cited are
real episodes, not hypotheticals.

**STATE: NORMAL (today's state on 3m10y).**
Hold strategic allocation. Do not pre-position for a recession the curve does
not predict: the unconditional equity baseline (+9.4%/12m) is the cost of
false defensiveness. Maintain the monitoring discipline; the canary's value is
that you will not need to guess.

**STATE: SUSTAINED INVERSION (≥ ~2–3 months below zero).**
- Over the following 1–2 quarters (not in one day): reduce equity beta by
  20–30% of its strategic weight; the 3–6m tables show you have time to do
  this without panic pricing.
- Redirect into the front end first (cash yields are at their cycle peak by
  construction) and *begin* extending duration — the 10y's +12.9%/24m says
  duration wins the full arc, but the 1978/1980 episodes warn that extending
  all at once into an inflationary inversion is painful. Stage it.
- Do NOT short equities on this signal alone: median 3m is +2.9%, and the
  2022 episode ran 25 months without a recession.
- Failure mode to respect: **1966** — inversion, no recession, equities fine.
  Size the tilt so being wrong costs basis points, not the mandate.

**STATE: RE-STEEPENING (the canary fires).**
- This is the maximum-defensiveness state, and it has a clock: the historical
  danger window is **the next 6 months** (median equity −5.6%; modern onsets
  at 3/8/5 months).
- Complete the equity reduction begun at inversion (to the mandate's defensive
  floor), hold maximum permitted duration (the +8.6%/12m, +23.5%/24m asset),
  keep a cash sleeve for the re-entry.
- **Check the steepening's cause before acting** (one glance at the Flow
  Compass + funding panel): a *bull* steepener (front-end collapsing = Fed
  cutting into weakness) is the recession pattern above; a *bear* steepener
  (long-end rising on supply/fiscal premium — term premium jumping, DEBASEMENT
  regime) is a different disease whose remedy is *less* duration, not more.
  The 2024-12 dis-inversion had meaningful bear-steepening character — one
  reason (with 19 months elapsed) it may become the second false positive.
- Pre-commit the re-entry plan at the moment the canary fires, when you are
  calm: the +19.9%/24m equity number is earned by buying *during* the
  subsequent recession, and no one feels like doing it then. A staged re-entry
  triggered by the Sahm confirmation (below) converts that number from
  hindsight into procedure.

**STATE: SAHM TRIGGER.**
- Do not initiate new de-risking — you are late (12m forward equities +4.1%).
- Treat it as: confirmation the cycle turned (the curve's warning was real),
  the signal to *begin staged re-entry* of the equity book (e.g., thirds over
  two quarters), and the point to start harvesting duration gains as the Fed's
  cuts get priced.
- The 1970s caveat: if inflation is unanchored (check the 5y5y breakeven
  panel), duration is not the safe harbor these medians imply — the 24m
  Treasury median (+4.9%) is dragged down by exactly those episodes.

**STATE: BREADTH ALARM (majority of leading families flashing).**
- Freeze net risk additions; begin building the defensive book you would want
  at inversion. Do not sell aggressively — near-term momentum after these
  alarms has historically been positive (+8.6%/3m), and N=5 counsels humility.
- The two-year asymmetry (equities −2.7% vs duration +21.9%) is the reason to
  act at all: this state buys you *time* to reposition cheaply.

**Standing rules across all states.**
1. Signals compose: curve → breadth → re-steepening → Sahm is the historical
   sequence (each confirmed the last in 2000–01 and 2006–08). Escalate the
   tilt as they stack, and distrust any one signal alone.
2. The credit veto: none of the defensive states are high-conviction unless
   HY OAS is widening too (cross-confirmation, category H). Treasury signal +
   tight credit = watch, don't lunge (the 2023-11 breadth alarm is the
   cautionary example).
3. The inflation veto: duration prescriptions assume anchored breakevens.
   5y5y above ~3% flips the 1970s regime switch — favor cash and real assets
   over the 10y.
4. Every tilt gets an exit rule written the day it goes on, keyed to the
   dashboard state that would falsify it (e.g., "re-steepening resolves NORMAL
   for 60 trading days → unwind").

---

## 4. Limitations register

- N = 5–10 events per state; medians hide dispersion (min/max in data file).
- Price-only equities; dividends omitted on both sides of every comparison.
- 10y total return is an approximation (carry + duration + convexity terms).
- Gold unsourced at this history length; excluded rather than approximated.
- Regime heterogeneity: pre-1985 inflation-era episodes weaken the duration
  prescriptions; they are flagged inline where they bind.
- Event dates use final (revised) macro data for Sahm/breadth (market-price
  events are revision-free); a vintage replay is the outstanding rigor step.
- Nothing here escapes the deepest limitation: 10 recessions is 10 data points.
  These are priors to discipline judgment, not laws.
