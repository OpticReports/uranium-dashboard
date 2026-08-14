# RATE-SHOCK SIMULATOR — BUILD SPEC v1.0
(Verbatim operator spec, received 2026-08-01. Amendments in SPEC_AMENDMENTS.md.)

## 1. Concept & Objective
Forward-looking scenario panel: "Given N Fed hikes over the next 2-4 quarters,
what does the price distribution look like for (a) equities / AI-capex complex
and (b) high-yield credit (HYG)?" Output: percentile fan charts (5/25/50/75/95)
per asset per hike scenario, horizon to end-Q2 2027. NOT naive Monte Carlo:
two-stage conditional — (1) rate-path scenarios as surprise vs market-implied
path, (2) asset responses via estimated sensitivities + regime switching, MC
simulating only residual noise around conditional drift. Epistemic framing in
UI tooltip: betas from ~5 hiking cycles; regime probabilities are judgment
encoded as parameters. Scenario visualization, not prediction.

## 2. Architecture
Stage 1 rate-path engine (implied + scenario -> surprise S(t), CS(t));
Stage 2 conditional asset response (HYG duration+OAS regime-switch; equity
real-yield duration beta + capex-crack regime jump; Markov stress state
P(stress | CS, canaries)); Stage 3 MC residual engine (10k paths, Student-t
nu=4, vol from MOVE/VIX, percentile cones).

## 3. Data
Fed funds implied path (manual-config JSON acceptable); DGS2/DGS10; DFII10;
BAMLH0A0HYM2; HYG price+dist yield; SPX/QQQ/SOXX; MOVE (existing feed); VIX;
FOMC dates static (Sep 16, Oct 27-28, Dec 8-9 2026; Jan, Mar, Apr 2027).
Cache via existing layer; refresh daily; do not block on live CME feed.

## 4. Math
4.1 Stage 1: r_mkt step function through FOMC dates (initial hardcode ok:
+25bp Oct ~70%, +25bp Dec ~45%); r_scn = user hikes at consecutive meetings
from Oct 2026; S = r_scn - r_mkt; Dy10 = kappa*S, kappa default 0.45; real
share rho=0.7.
4.2 HYG: dP/P = -D*Dy_treas - SD*dOAS + carry*dt; D=3.2, SD=3.5, carry=dist
yield ~6.5% live. OAS 2-state Markov monthly: normal theta=310bp sigma=25,
dtheta=-8bp/priced hike +15bp/surprise hike; stress theta=500bp sigma=60,
entry jump +120bp; P(n->s)=logistic(a+b*CS+c*canary), a=-4.0, b=3.5/100bp,
c=0.8*normalized canary composite. Calibrate: 0-1 hikes -> P(stress by
Q2'27) 8-12%; 3-4 hikes -> 35-50%.
4.3 Equity: dlogP = -beta_dur*dreal_surprise; beta SPX 5.5, QQQ 7.5, SOXX 9.0
per 100bp real surprise (2022 sample — QA must re-estimate). Earnings drift
+7%/yr SPX, +10% QQQ/SOXX. Capex-crack jump in stress: SPX -12%, QQQ -18%,
SOXX -25% phased 2mo, vol x1.6 for 4mo; 1-month transition lag on CS input.
4.4 MC: monthly Aug 2026-Jun 2027, N=10k, antithetic, fixed seed + reseed
button; Student-t nu=4 scaled to annualized vol (equity VIX*0.9; HYG blend
0.4 MOVE-mapped + 0.6 realized 60d); corr equity/HYG 0.6 normal / 0.85 stress
(Gaussian copula on t-marginals unless QA shows t-copula needed); outputs:
monthly percentile bands, P(drawdown>10%/20%), terminal histogram.

## 5. Backend
app/simulators/{rate_paths,hyg_engine,equity_engine,mc_core,calibration}.py,
router shock_sim.py. Endpoints: GET /shock-sim/scenarios; POST /shock-sim/run
{hikes, assets, seed?, overrides?} -> {bands, probs, meta}; GET
/shock-sim/calibration. Runtime < 1.5s full run; cache by params hash.
`overrides` mandatory (sensitivity surface).

## 6. Frontend
Panel RateShockSimulator beside the canary charts. Controls: hikes 0-4
segmented, asset multiselect, seed refresh, stress-prob toggle. Fan chart:
stacked percentile bands + median, FOMC vertical lines, stress-prob sparkline.
Param drawer (collapsed): live-editable params via overrides, source tags
(estimated|judgment|literature; judgment = amber dot). Epistemic tooltip.

## 7. params.json: every param has default, plausible range, source tag.

## 8. Validation gates (merge-blocking)
G1 2022 replay: actual 2022 surprise (~+450bp vs Jan-22 implied) -> median
sim SPX -18..-30%, HYG -8..-15%. G2 2004 replay: low surprise -> P(drawdown)
< 15% (must NOT crash on telegraphed hikes). G3 0-surprise sanity: plain
drift+vol cone. G4 bands monotonic, no NaN, deterministic under fixed seed.

## 9. Agent mandate: counter-agent (challenge economics; SPEC_AMENDMENTS.md
with accept/reject rationale; authority to amend where argued better) + QA
quant (re-derive defaults, tornado sensitivity ±50% -> high-sensitivity flags,
vectorization/seed/antithetic/t-scaling checks incl. var=nu/(nu-2), copula
tail check: if joint 5th-pct co-crash differs >20% vs t-copula, switch).
Author's known prior errors: stale leverage math, inconsistent divisors —
treat spec skeptically. Sacred: two-stage architecture + validation gates.

## 10. Phases: P0 stage1+params+/scenarios; P1 HYG+MC+gates 3-4; P2 equity+
regime+gates 1-2; P3 frontend+drawer+canary hook; P4 QA pass+tornado+
SPEC_AMENDMENTS+merge.
