# CANARY_COUPLING_RESEARCH.md — wiring canary market-risk data into the EWM

Research memo (2026-08-02), commissioned by the operator: "how do we take
canary data around risk and market rate adjustments and apply it here? we
have market risk indicators that are rate sensitive or yield sensitive that
could be illuminating here." Two-agent round: a full inventory of every live
in-process canary signal, and a deep evidence review of which market
indicators have documented links to private-M&A deal outcomes.

---

## 0. What was found broken (fixed in this commit, before any new wiring)

1. **The EWM has never read the live canary composite.** `ewm/api.py`
   called `compute_all(session)` — a type error against the real signature
   `compute_all(bundle, auctions)` — swallowed by a bare except, silently
   falling back to the hardcoded 0.25. Every "Canary composite 25/100" the
   board has ever shown was the fallback, not data. Fixed to the
   `compute_all(fetch_bundle(), auctions=[])` idiom, with a new guard:
   coverage < 30% (degraded feed) returns None → explicit fallback rather
   than reading an empty bundle as "all calm".
2. **The rate-shock simulator's canary hook was broken three ways**
   (`routes_shock_sim._canary01`): a 3-positional call into a 2-positional
   signature (→ always the 0.3 fallback), a negated 3m10y spread, and a
   percent fed where a fraction was expected. All fixed; the simulator's
   stress-entry logistic now sees the real curve state.
3. `window_scores(spike_pos_override=...)` — written for the rate-shock
   panel's SPIKE×POS state, tested for effect, never passed by any caller.
   Wiring it is item 1 of the shortlist below.

Regression tests added (`tests/test_canary_wiring.py`, offline).

---

## 1. Inventory: live, rate/yield-sensitive canary signals available in-process

All of these are already computed inside the same service the EWM runs in —
no new data sources needed, no HTTP hops. (Full catalog with access paths
retained in the research transcript; the decision-relevant subset:)

| Signal | Scale | Rate-sensitive? | Natural EWM use |
|---|---|---|---|
| `composite.score` (canary) | 0–100 higher=worse, ~65% rate-driven (curve 30%, vol, term premium, funding) | mixed | window score `w_canary` (now actually live) |
| `recession.nfci` (Chicago Fed NFCI) | sd units, 0=avg, +=tighter — *exactly* the EWM's `fcix_z` convention | financing conditions | `fcix_z` primary source (as trailing z — raw NFCI would pin the transfer function) |
| `crossasset.hy_oas` | bp (FRED ~3y history cap) | credit spread | financing-state trigger + fcix co-signal |
| `leading.sloos` (C&I tightening net %) | %, Y 10 / R 20, quarterly | bank lending | `dmhi01` leg |
| pins `private_credit` channel | 0–100 worse (CCC pctile, CCC−BBB dispersion, NDFI lending) | credit | `dmhi01` leg (daily) |
| rate-shock panel `state`×`regime` | SPIKE/PLUNGE/NEUTRAL × POS/MIXED/NEG | pure rate × equity | `spike_pos_override` (exact match) |
| `bundle["2y"]` 3-month change | pp | pure front-end | hawk-repricing nowcast (the gates' own validated proxy: fired Dec-2021, silent 2019) |
| shock-sim `simulate(hikes,...)` | `stress_prob` = per-month stress-state occupancy (list, NOT cumulative), dd probabilities, bands | maximal (FOMC surprise path, κ(term premium), VIX, MOVE, HY) | `stress_prob` for action card 5, per-scenario weighted |
| `vol.move` (10y realized-vol proxy) | ≈MOVE units | pure rate-vol | context/confirmation only |
| fast-leverage `WASHED_OUT` etc. | states; only WASHED_OUT is VALIDATED (p=0.011) | equity | context only for EWM |
| `recession.prob` (probit), `curve.*` states | %, enums | pure curve | inside composite already — do not re-wire separately (double count) |

No live source exists for `dissent_cluster` (nothing parses FOMC votes) —
it stays a manual input; the Δ2y>0.4pp/3m proxy is the market-visible
stand-in and is already gate-validated in the replay tests.

---

## 2. Evidence review: which indicators actually predict deal outcomes

Graded STRONG / SUGGESTIVE / THIN. Full citations in the research
transcript; the load-bearing numbers:

### STRONG — HY credit spreads → LBO financing, multiples, volume
- Axelson–Jenkinson–Strömberg–Weisbach (J. Finance 2013, 1,157 buyouts):
  **each 100bp of HY spread widening ≈ −5.9% LBO leverage and −4.8%
  purchase multiple** (t≈−7.9/−6.9); the HY spread is "the only consistent
  predictor of buyout leverage", and private-transaction pricing is MORE
  credit-sensitive than public comps.
- 2022 episode: HY OAS ~310→~583bp ⇒ leveraged-loan issuance −63%, HY
  issuance −76%, LBO count 147→51→32, LBO equity checks >50% for the first
  time. The market shut at only ~500–600bp because the MOVE was fast —
  **level AND speed both matter** (trigger design: >~450–500bp level, or
  >+150bp/60–90d change).
- Gilchrist–Zakrajšek excess bond premium: credit-supply component of
  spreads robustly forecasts activity/recessions.
- Lags: issuance stops in weeks; deal volume −1–2 quarters; completed
  multiples reprice over 2–4 quarters (matches the report's own
  transmission-lag premise).
- **Mid-market caveat:** a ~$200M deal likely prices in the direct-lending
  market (54–59% of LBO financing 2023), so HY OAS is a proxy; BDC
  price/NAV discounts are the right daily observable for that market
  (currently the deepest since COVID) but exist only as a spec
  (PRIVATE_CREDIT.md) — the pins `private_credit` channel is the
  implemented stand-in.

### STRONG — what stress actually does to processes (stall vs death)
- Withdrawn deal VALUE spiked to ~20% in 2022 (~$271B) but withdrawal by
  COUNT stayed ~3%; 2022–23 terminations did NOT spike (unlike 2008) —
  stress showed up as **fewer launches and longer processes, not busted
  signings**. This directly supports the EWM's delay-not-death stall model
  and says market stress should feed the **stall/launch hazard**, not a
  signed-deal death rate.
- Denis–Macias (JFQA 2013): MAEs underlie 69% of terminations, 80% of
  renegotiations; average renegotiated cut on a target MAE ≈ **−15%**.
  LMM practitioner base rates: ~30–40% of deals retraded between LOI and
  close in normal times, typical accepted haircut ~7%. (These calibrate the
  stall recut constants — currently −6.5% — as conservative-but-in-range.)

### SUGGESTIVE — rate-path *uncertainty* freezes deals
- Bonaime–Gulen–Ion (JFE 2018): policy uncertainty cuts M&A, strongest for
  monetary uncertainty, through a real-options "wait" channel, amplified
  for irreversible deals (a company sale is maximally irreversible).
  Adra et al. (JCF 2020): fed-funds increases raise deal-withdrawal odds.
- **No published MOVE-threshold estimate exists**; MOVE is collinear with
  the credit trigger. Use repricing *speed* (Δ2y) in the nowcast; MOVE
  stays confirmation/display.

### STRONG NULL — VIX for private targets (important!)
- Bhagwat–Dam–Harford (JFQA 2016): VIX → public-target deal count
  elasticity −0.11…−0.29 with a strong high-VIX nonlinearity, but for
  **private targets the coefficient is ~1/10th and statistically zero at
  all deal sizes** (the mechanism is interim risk between signing and
  shareholder vote — private sellers can commit ex ante). VIX must NOT be
  wired as an independent driver of this deal's outcomes; context only.

### THIN — stock-bond correlation, long-yield shock states, term premium, COT
- No study links these to M&A volume/completion (searched directly).
  Legitimate roles: the corr regime *conditions* how a rate shock
  transmits (SPIKE×POS = "nothing hedges"), term premium drives the
  simulator's κ. Keep as conditioners/context, never as standalone
  deal-outcome inputs. The frozen rate-shock study's own honesty box
  applies: SPIKE×POS is a **recession-odds** signal (47% vs 21%), NOT a
  stock-sell signal (p=0.21) — the deny-Green cap should be labeled as
  recession-risk caution.

### STRONG — Fed-path nowcasting practice
- Fed funds futures/OIS dominate ≤6m horizons (Gürkaynak–Sack–Swanson);
  the 2y is ~the integral of the path plus premia, so 2y momentum is a
  defensible FRED-only repricing flag (contamination ±20–50bp).
  Free upgrade if desired later: Atlanta Fed Market Probability Tracker
  (SOFR-options-implied distributions, daily).
- Scenario-weight updating best practice: **entropy pooling** (minimum
  relative-entropy tilt of the prior toward market-implied constraints)
  with **shrinkage toward the prior and dual-threshold hysteresis** —
  never raw overwrites. Growth-at-Risk (Adrian et al.) template: tighter
  financial conditions shift the DOWNSIDE quantile, not the mean.

---

## 3. Coupling design (the double-counting map)

The one dominant factor across HY OAS / MOVE / VIX / BDC / P(stress) is
credit-vol stress. Rule: **one primary trigger per channel; everything
else confirms, conditions, or displays.** The canary composite already
carries curve/vol/funding into the window score at w=0.20 — nothing below
re-feeds those components separately.

| EWM channel | Primary live input | Confirm/condition | Never |
|---|---|---|---|
| Window score `w_canary` | composite.score/100 (now live) | — | — |
| Window score `w_fcix` | NFCI trailing-z | HY OAS z co-signal | raw NFCI (pins the transfer fn) |
| Window score `w_dmhi` | SLOOS (quarterly) + pins private_credit channel (daily), inverted, averaged | — | VIX (documented null) |
| Deny-GREEN cap | rate-shock SPIKE×POS (exact `spike_pos_override` match), labeled recession-risk | — | — |
| Stall hazard | HY financing state: BENIGN <400bp / TIGHT 400–500 or +150bp/90d / SHUT >500 → stall_p multiplier ×1 / ×1.33 / ×1.67 on hawk rows, dual-threshold hysteresis (release at 425) | private_credit channel RED co-trigger | signed-deal death rate (evidence: stress stalls, doesn't kill) |
| Scenario weights | REPORT weights remain the model. Market nowcast shown BESIDE them: Δ2y-3m repricing flag + HY state → a bounded tilt chip ("market repricing toward row 2") with max ±5pp entropy-style tilt, λ-shrunk, hysteresis — **display + optional apply button, never silent auto-update** | dissent_cluster stays manual | wholesale reweight from prices |
| Value cells | NEVER touched by live data (bridge rule: tier data steers deltas, damped — levels are the report's) | — | — |
| Delta chip (display) | AJSW financing headwind: −4.8%/100bp × (HY OAS now − 284bp at report date), shown on the plain summary as "financing conditions vs report date" | — | — |
| Action card 5 `stress_prob` | simulator run per scenario, weighted by cohort weights, **max monthly occupancy** (labeled: understates cumulative P(ever-stress); sim horizon ends 2027-06, before the sale goal) | — | broken `_canary01` hook (fixed; pass composite explicitly) |

Provenance rule: every auto-wired input renders with source + asof + an
AUTO/MANUAL toggle in the settings drawer; manual override always wins and
is event-logged (Cooke-style: record the basis, score it after each FOMC).

---

## 4. Ranked implementation shortlist

1. **Live-inputs autopilot** (highest value, smallest lift): wire
   `fcix_z` ← NFCI trailing-z, `dmhi01` ← inverted SLOOS + private_credit
   pin channel, `spike_pos_override` ← rate-shock panel state, with
   AUTO/MANUAL toggles, provenance chips, and event-logged overrides.
   (canary01 fix already shipped with this memo.)
2. **HY financing-state → stall hazard + action card**: three-state
   trigger with hysteresis; drives the stall multiplier on hawk rows and a
   new card ("financing window tightening: expect retrades, +1–2q process
   risk"); breakeven h* re-read against the live stall multiplier.
3. **Financing-headwind delta chip** on the plain summary: AJSW elasticity
   × HY move since the report date — display-only, keeps report cells
   pristine while showing how conditions have drifted.
4. **Market-path nowcast strip**: Δ2y-3m + HY state → "which cohort row is
   the market voting for", with a bounded ±5pp APPLY-button tilt
   (entropy-lite, shrunk, hysteretic) — never silent.
5. **Weighted simulator stress bridge** for card 5 (per-scenario runs,
   honest cumulative-vs-occupancy labeling).
6. (Later, separate build) BDC NAV-discount gauge per PRIVATE_CREDIT.md —
   the *right* market for this deal size; until then the pins
   private_credit channel is the implemented proxy.

Items 1–5 are all in-process reads of existing computations — no new data
sources, no new cost. The evidence-graded rule set above is the contract:
STRONG couplings get wired, SUGGESTIVE get confirmation roles, THIN and
the VIX null stay display-only.
