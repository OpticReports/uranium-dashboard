# SPEC_AMENDMENTS.md — DRAFT (counter-agent pass, 2026-08-02)

Adversarial review of the EWM MODEL DESIGN per the §9 mandate, before
implementation. Empirical work in scratchpad `qa_ewm/` (FRED + FMP, user's
own keys); reasoned-only items are labeled as such. Sacred items untouched:
tier-specific deal data, lag-honest UI, delay-not-death stall modeling,
validation gates. Where a gate and an amendment could interact, the gate
wins and the interaction is called out.

Headline: no amendment changes the G1 anchors (modal 196–203 / weighted
~192.7 at Q1'27 — re-verified arithmetically below). The two structural
fixes are (1) moving the dissent bump to the scenario tail where futures
pricing is genuinely thin, and (6c) redefining cost-of-delay as a
decision-delay counterfactual rather than a month-difference, which as
specced can read near-zero exactly when delay is most expensive.

---

## 1. Dissent-cluster bump (+5–8pp to hike scenarios) — **AMEND to (c): tail-only, +3pp cap, one-cycle decay, always UI-flagged**

Reasoning (no tradeable-lag dataset exists for this; labeled REASONED):

- Dissents are public within seconds of the statement; fed funds / SOFR
  futures for the next one-two meetings reprice the same afternoon. Adding
  +5–8pp across all hike scenarios on top of futures-implied P_s
  double-counts the information in exactly the part of the curve that is
  most efficiently priced. No credible underreaction literature gives a
  multi-day tradeable lag at the FIRST-meeting horizon; academic work on
  dissent voting (Gerlach-Kristen; Thornton/Wheelock; Madeira & Madeira)
  finds dissents predict the FUTURE PATH of policy — i.e. the committee's
  reaction-function skew — not a mispricing of the next meeting.
- That is precisely where the spec's P_s vector is weakest anyway: the
  30/35/25/7/3 split over CUMULATIVE 0–4 hikes is well identified by
  futures for 0–2 hikes and essentially assumption-grade for hike-3/hike-4
  (options on SOFR futures at those strikes are thin, wide, and
  path-ambiguous). A 3-dissent hawkish cluster is a reaction-function
  signal, and the reaction function lives in the tail.

**Amended rule** (implement in params.json, all values operator-editable):

```
if hawkish dissents >= 3 at latest FOMC:
    bump = min(0.01 * n_dissents, 0.03)          # +3pp hard cap
    P[3], P[4] += bump * (0.7, 0.3)              # tail only
    P[0], P[1] -= bump * (0.5, 0.5)              # funded from dove side
    decay: bump *= 0 at the NEXT FOMC unless the cluster repeats
    (linear decay to zero across the inter-meeting period is acceptable)
UI: dissent-cluster flag ALWAYS shown when >=3, independent of the bump —
the flag is the primary product (it also drives the accelerate-pre-Dec-FOMC
action card); the probability bump is secondary.
```

Mirror-image rule for >=3 dovish dissents (bump cut-tail scenarios if the
scenario set is ever extended; today, shift tail weight back to P[0]/P[1]).

Gate check: tail-only +3pp moves weighted EV 192.7 -> 191.6 (−1.1M), still
inside G1's 189–194 band. The spec's own +6pp version (190.5) also passes,
so this amendment is argued on double-counting grounds, not gate survival.
G1 runs on July-2026 frozen inputs: the bump must be OFF in that fixture
unless a >=3 cluster actually existed at the July 2026 FOMC — encode the
fixture's dissent count explicitly, do not hardcode bump=0.

---

## 2. Static vs regime-dependent Window Score weights w1..w4 — **ACCEPT static weights; AMEND: add a SPIKE×POS green-cap override and de-duplicate the regime input (see 6e)**

Evidence from the canary's own rate-shock study
(`treasury-canary/RATE_SHOCK.md`, 2,480 weekly obs 1977–2026):

- The stock-bond correlation regime genuinely changes transmission: a
  +75bp/60d long-yield spike carries 47% 12-month recession odds in the
  POS regime (bonds not hedging) vs 21% baseline, and the only validated
  benign cell (PLUNGE×POS, 102/102 positive) is also regime-conditional.
- But the honest read cuts against continuous regime-dependent WEIGHTS:
  (i) the regime differential within SPIKE is small (47% POS vs 44% all —
  the spike itself is the signal, the regime is a modest modifier);
  (ii) the study's own honesty box counts episodes, not weeks — n is ~5
  rate cycles, exactly what the EWM's epistemic banner warns about. A
  w(regime) function is an extra degree of freedom that cannot be
  validated against G2/G3 (2022 was POS-regime red; 2019 was NEG-regime
  green — one episode per cell; any regime weighting "fits" trivially);
  (iii) the regime already enters the score twice — through w4 (Canary
  state includes the corr-regime tile) and through the shock-sim stress
  prob inside FCI-X, which conditions on the same regime. Making w1..w4
  regime-dependent would count the same state a third time.

**Amendment (discrete override, not weight morphing):**

```
if corr_regime == POS (60d stock-bond corr >= +0.2, canary convention)
   and long-yield shock d60 >= +75bp (canary SPIKE state):
    WindowScore(m) = min(WindowScore(m), 69)   # deny Green, allow Amber
    for all m whose signing-to-close gap contains >= 1 FOMC meeting
    log as trigger "SPIKE_POS_override" on any affected card
```

Rationale: this is the one regime cell with validated elevated transition
risk (47% recession-within-12m), it is auditable as a single rule-table
row, it cannot silently re-tune the calibration ("today reproduces Q1'27
green-amber" is untouched — today's cell is NEUTRAL×POS, baseline), and it
degrades gracefully: it can never turn a red month green, only cap greens.
Static w1..w4 stay frozen in params.json and get re-examined only if a
validation gate is ever re-run against a new episode.

---

## 3. GF recalibration damping 0.5x — **AMEND to sample-size shrinkage capped at 0.5, times bridge-R² once the bridge table exists**

0.5 is arbitrary but its SIGN and rough size are defensible: with a 1–2q
lag the print is a noisy measurement of the state ~1.5q ago, so full
pass-through is clearly wrong. The principled version is a shrinkage
weight, and it needs only one number per print (tier deal count):

```
lambda_q = min( 0.5 , n_q / (n_q + n0) ) * R2_bridge
new_anchor = old_anchor + lambda_q * (GF_tier_multiple_q - old_anchor)
```

- `n_q` = deal count in the GF tier ($100–250M) print for the quarter.
- `n0 = 40` (judgment tag): the prior-equivalent count at which the print
  earns half its cap. Rationale: quarterly tier-multiple sampling error on
  n~40 heterogeneous deals (cross-deal multiple sd ~2x turns) is ~0.3x —
  comparable to a plausible true quarterly drift, so a gain near 0.3–0.5
  is the Kalman-consistent range; the 0.5 CAP encodes the 1–2q lag (never
  chase a stale print at more than half weight).
- `R2_bridge = 1.0` until the size/sector/growth bridge table (§8
  UNRESOLVED: GF 7.1–7.3x vs Capstone 9.8x vs deal-specific 13–15x) is
  built; thereafter set it to the bridge regression's R², so a bridge that
  explains little of the tier-vs-deal gap automatically mutes GF deltas.
  This preserves the operator's §8 requirement that no GF LEVEL
  recalibration happens pre-bridge — only damped DELTA tracking.
- Average the two most recent prints when both are available (halves
  single-print noise at zero added complexity). Runs 4x/year; total
  implementation is ~5 lines.

Typical effect: n_q=40 -> lambda 0.25 (pre-bridge), i.e. roughly half the
spec's 0.5. Keep 0.5 as the params.json ceiling so the operator can revert.

---

## 4. FCI-X weights (0.30 BDC P/NAV, 0.25 BB OAS, 0.15 MOVE, 0.15 PIK/NA, 0.15 stress-prob) — **ACCEPT weights; AMEND the BB z construction; two hard warnings**

Honesty first: with no realized deal-financing-spread series, a true PCA
re-derivation of these weights is IMPOSSIBLE — the weights are and remain
judgment-tagged. What can be tested is the correlation structure of the
observable components, done over 2023-08..2026-07 (748 aligned days,
tightness-signed z; script `qa_ewm/`, FRED BAMLH0A1HYBB + FMP
BIZD/ARCC/OBDC/FSK/BXSL/JAAA/JBBB/^MOVE):

| level-z corr | BDC(−BIZD) | BB OAS | MOVE | CLO(−JBBB/JAAA) |
|---|---|---|---|---|
| BDC tight | 1.00 | −0.09 | −0.49 | **0.84** |
| BB OAS | | 1.00 | 0.70 | 0.26 |
| MOVE | | | 1.00 | −0.26 |

3m-change corr: all pairs 0.47–0.74 (max BDC-vs-CLO 0.73, BB-vs-CLO 0.74).
PCA: change-space PC1 explains 72% with near-equal loadings (0.44–0.53) —
consistent with spreading weight across components rather than
concentrating; level-space splits into two factors (54%/39%): a
private-credit factor (BDC, CLO ratio) vs a liquid-credit/vol factor
(BB OAS, MOVE).

Findings and rulings:

1. **No pair of ACTUAL spec components exceeds 0.8.** The 0.84 is BDC vs
   the JBBB/JAAA CLO ratio, which is NOT a spec component — it was probed
   as the tempting daily stand-in for the quarterly PIK/non-accrual
   series. Ruling: PIK/NA stays quarterly-and-held as specced (its 0.15
   weight is information the daily components don't carry precisely
   BECAUSE it is slow); builders must NOT daily-ize it with JBBB/JAAA,
   which would just re-buy the BDC factor at 0.84 correlation and
   effectively run BDC at 0.45 weight.
2. **The 0.30 BDC weight is currently earning its keep.** BDC-vs-BB level
   correlation by year: 0.91 (y1), 0.76 (y2), **−0.10 (y3)** — the 2026
   private-credit divergence documented in
   `treasury-canary/PRIVATE_CREDIT.md` (BIZD −30% off its 3y high while
   BB OAS sits at 174bp, z −0.64). For a $100–250M sale financed in
   private credit, the component that reprices private credit specifically
   must dominate the one that tracks liquid HY. Keep 0.30/0.25. Do not
   "fix" the low BDC-BB correlation — it is the signal.
3. **BB OAS availability**: FRED `BAMLH0A1HYBB` resolves but is capped at
   3y like all BAML series (first obs 2023-08-01; verified 2026-08-02,
   787 obs). **Recommended z window: the full available 3y** (shorter
   windows only amplify the next problem). The problem: the 3y basis
   contains no true stress episode (range 156–311bp vs ~450bp in 2022,
   ~750bp+ historical stress), so a move to ~300bp — historically
   unremarkable — would print z ≈ +3 and slam FCI-X to "tight".
   **Amendment**:

```
BB component = 0.5 * z_level_3y  +  0.5 * z_3mchg_3y      # spec's "level+3m chg", now explicit
z_level_3y clipped to [-1.5, +2.0]                         # stress-free-basis guardrail
optional recentering (params.json, default ON): map the level through the
full-history Baa−Aaa splice already used in the canary work
(HY_OAS ≈ 149 + 2.43·(BAA10Y−AAA10Y), R²=0.71; FRED AAA/BAA are uncapped —
fred_AAA.json / fred_BAA.json already cached in ewm/) so the level z is
computed against a basis that has seen 2008/2020/2022.
```

   The 3m-change leg needs no recentering (changes are basis-free) and is
   the leg that matters for a live financing window anyway.
4. MOVE at 0.15: level corr 0.70 with BB OAS — elevated but under
   threshold, and MOVE carries the rate-vol information that gates
   financing LOCKS rather than spreads. Keep.

---

## 5. Seeded cohort surface — month axis V(s,m), Sep'26–Dec'27 — **AMEND the seed from flat to a principled shape (three terms, all zero at the Q1'27 anchor)**

The spec pins scenario multiples at Q1'27 (M_s = [14.5, 14.0, 13.4, 11.8,
11.2] × EBITDA 14.0 -> V = [203, 196, 187.6, 165.2, 156.8]; weighted at
30/35/25/7/3 = 192.7 — re-verified) but says nothing about how V varies in
m. A flat month axis makes EV(m) differences come only from P_s drift and
feasibility, which understates real month structure. Seed shape (REASONED;
tagged source:"seeded-from-spec", replaced wholesale by the v6 report table
when available):

```
V(s,m) = EBITDA(m) * [ M_s + shape(s,m) ] * (1 - rush(m))

EBITDA(m) = 14.0 * (1 + g)^(years since anchor),  g default 0.0
shape(s,m), Δq = quarters after Q1'27 (0 for m in or before Q1'27):
    s ∈ {0,1} (dove):  +0.10x * Δq, capped at +0.30x
    s = 2 (base):       0
    s ∈ {3,4} (hawk):  −0.15x * Δq, floored at −0.60x
rush(m) = 2% for feasible months within 1 month of the feasibility
          frontier, else 0   (default 0 in the G1 fixture; see below)
```

Rationale and magnitudes:

- **Multiples flat, not trending, for fixed s within the window**: a
  scenario already fixes the rate path; conditional on it, tier multiples
  move slowly. The asymmetric drift term encodes the one real month-axis
  effect: under sustained-hike scenarios, LATER closes price against
  cumulatively repriced financing and a thinning sponsor pool — GF-type
  tier multiples move ~1–1.5x peak-to-trough over ~6–8 quarters, i.e.
  ~0.15–0.2x/quarter during tightening, hence −0.15x/q. Under dove
  scenarios the mirror effect (cuts feeding through to leverage
  availability) is real but slower: +0.10x/q, capped. This is a PRICE
  effect for deals that do close — it does not double-count DMHI stall
  risk, which is a timing/probability effect and stays in the stall model
  (delay-not-death, untouched).
- **EBITDA growth defaults to 0**: the spec's +$1M ≈ +$13–15M rule is a
  multiple, not a forecast; the EV strip must not manufacture drift from
  an assumed g. Surface g in the tornado — at the deal's ~14x it dominates
  everything if the operator supplies a real forecast.
- **Rush discount** (~2% of value ≈ 0.25–0.3x): closes forced at the very
  edge of process feasibility compress competitive tension (fewer parties,
  weaker BAFO dynamics). Parameterized, DEFAULT 0 in the July-2026 frozen
  fixture so G1 anchors are exactly preserved; operator activates it once
  the live process stage is known.
- Gate check: shape(s, Q1'27) = 0 for all s by construction — modal
  196–203 and weighted 192.7 reproduce exactly. By Q4'27 the seed now
  says: dove closes ≈ +0.3x (+4M), hawk closes ≈ −0.45x (−6M) — the
  late-window EV fan widens under hawkish P_s drift, which is the
  economically correct behavior the flat seed was missing, and it feeds
  the cost-of-delay curve a real gradient instead of zero.

---

## 6. Other §4 design flaws — four amendments, one accept

**(a) Cost-of-delay definition — AMEND (the material one).** As specced,
`EV(m) − EV(best feasible)` is a MONTH-CHOICE curve: it prices choosing a
worse month with today's information. It reads ~0 when adjacent months
have similar EV — exactly the situation in which operators feel safe
stalling — while the true cost of stalling is losing the CURRENT feasible
set. Ship two curves, headline the second:

```
month-choice:   CoD_choice(m) = EV(m*) − EV(m),  m* = argmax over feasible m
decision-delay: CoD_delay(k)  = EV_now(m*_now) − EV_shift(m*_shift(k))
    where EV_shift freezes P_s, FCI-X, DMHI at TODAY's values (no
    look-ahead, consistent with the replay QA rule) and shifts the
    feasibility frontier right by k weeks before re-optimizing.
$/week headline = CoD_delay(4) / 4 weeks.
```

CoD_delay is nonzero whenever delay pushes the frontier past a good month
or deeper into event-dense signing-to-close gaps, even when the EV curve is
locally flat. Freezing inputs makes it a conservative lower bound; say so
in the card rationale.

**(b) Event-density weighting — AMEND: stage- and tilt-dependent gap,
FOMC > CPI.** The signing-to-close gap is not a constant: strategic
all-cash runs ~2–3mo, sponsor-financed ~3.5–5mo. The spec already computes
a sponsor-vs-strategic tilt off FCI-X — reuse it:

```
gap(m) = tilt * 4.5mo + (1 − tilt) * 2.5mo     # tilt = sponsor share, from FCI-X rule
event density(m) = ( 1.0 * n_FOMC + 0.4 * n_CPI ) / gap(m)_months, inside [sign, close]
```

FOMC meetings reprice P_s discontinuously (and are where financing outs get
tested); CPI prints matter mainly via FOMC expectations — weight 0.4
(judgment tag). Density normalized per month so longer gaps aren't
mechanically penalized twice (the tilt already lengthens the gap).

**(c) Feasibility lead time "5–7mo from launch" — AMEND to remaining-lead-
time by stage.** "From launch" is ambiguous once the process is underway
and would keep striking months long after they become reachable. Lookup
(operator-editable, mid defaults):

```
pre-launch 6.5mo · teaser/IOI 5mo · management-meetings 4mo ·
LOI/exclusivity 3mo · signed 1.5mo (financing + regulatory close)
strike-through m where m < today + leadtime_remaining(stage)
```

Struck months stay uncolored (spec is right that un-choosable ≠ red —
ACCEPT that part; G4 tests should cover at least two stages, not just
pre-launch).

**(d) Rule-table trigger flapping — AMEND: hysteresis + persistence.** Hard
thresholds (P(2 hikes) > 40%, stress prob > 25%, FCI-X > +0.75) on daily
inputs will flap cards on and off around the boundary, destroying trust in
the prescriptive layer. Add to every daily-signal trigger: activate at
threshold, deactivate at threshold − 5pp (probabilities) / − 0.15
(z-scores), and require 3 consecutive daily closes beyond the activation
threshold before a card fires. Log both threshold crossings and the
hysteresis state with the card (extends, not replaces, the sacred
every-card-logs-its-trigger rule). Quarterly-input triggers (DMHI, PIK/NA)
need no persistence rule.

**(e) Stress-prob double-count — AMEND definition of w4.** Shock-sim
stress prob appears inside FCI-X (0.15 weight) AND plausibly inside the w4
Canary component. Define w4's Canary input to EXCLUDE the shock-sim stress
prob — it should carry the curve/recession model and the corr-regime state
only — so the stress prob enters the Window Score exactly once, via FCI-X.
(This also keeps amendment 2's SPIKE×POS override from triple-counting.)

---

## Data caveats

- FRED BAML confirmed 3y-capped on this key (BAMLH0A1HYBB, BAMLH0A0HYM2,
  BAMLC0A4CBBB all start 2023-08-01 as of 2026-08-02). AAA/BAA (Moody's)
  are uncapped — hence the splice route in §4.3.
- FMP `^MOVE` resolves (the bare ticker `MOVE` is an unrelated equity —
  do not use it); BIZD/ARCC/OBDC/FSK/BXSL/JAAA/JBBB all resolve with
  history to 2023-07.
- Correlation window 2023-08..2026-07 contains one private-credit
  divergence episode and no systemic credit event; the >0.8 redundancy
  screen is therefore necessary-not-sufficient. Revisit if the FCI-X is
  ever re-weighted after a realized deal-spread series becomes available.
- Challenges 1, 2 (override design), 5, and 6 are reasoned where noted;
  no dissent-reaction tick data or v6 report table was available to this
  session.

---

## v2 amendments (2026-08-02) — report-v6 surface + ramp round

Operator-approved build ("build it and ill take a look for feed back").
Governing inputs: cohort_v6.json (authoritative report extraction) and
METHODOLOGY_RESEARCH.md (shortlist items 1-4, 6).

1. **Pricing basis switched to REVENUE multiples.** The seeded EBITDA
   surface (14.0-14.5x on $14M) is retired; cells are now the report's
   per-scenario value RANGES at the two report close windows, expressed as
   revenue multiples on the $105M basis (1.38-2.00x). The re-anchor action
   card converts +$1M revenue at 1.38-2.00x (was +$13-15M per EBITDA turn).
2. **Dynamic revenue ramp (operator premise).** Two editable waypoints —
   run-rate $105M at end-Dec-2026 and the $200-225M valuation target at
   2027-07-31 — define a linear "evenly scaling" revenue line; the target
   revenue is back-solved at the modal-path multiple (judgment-tagged) and
   today's implied run-rate is the same line extrapolated back (~$102M).
   The report held performance constant; the ramp is the operator's stated
   scaling premise layered on top, and `pin_report` disables it (gate G1
   reproduces the report cells exactly in pinned mode).
3. **Flat 6% exec-noise band retired** in favor of the report's hawk-skewed
   cell ranges, propagated as perfect-correlation EV_lo/EV_hi bounds.
4. **Closed-form breakeven row** (memo e2): pinned mode reproduces the memo
   exactly — Q2 ahead $1.05M pure EV; flips at ~16pp (s1→s2), ~9.5pp
   (s0→s3), ~7pp extra hawk-row stall hazard. Live (ramp-on) mode shows the
   real decision: Q2 ahead ~$6M, stall flip ~38pp. Powers a within-5pp
   action card.
5. **Split-concentration Dirichlet weight band** (memo e1), mean-preserving
   via Beta on the tail mass (kappa 15) x Dirichlet head (kappa 60).
6. **Stall model wired to the report's row-level 25-35% odds**; Q1 closes
   carry half the hawk-row stall exposure (transmission-window argument),
   Q2+ carries it all. Stall-adjusted EV and hold-to-Jul-27 premium rows
   added; cost-of-delay is now stall-adjusted, horizon-capped at the target
   date, with a hawk-conditional cost column (base-case delay cost is ~0
   under the ramp by construction — the risk lives there and in stall odds).
7. **Monte Carlo valuation fan** with operator toggles: force 0-4 hikes,
   stock crash (moderate x0.85 / severe x0.70 multiple — half the 2022-23
   revenue-deal gradient, phased over the report's 1-2q transmission lag,
   judgment-tagged), the report's off-cohort 50bp-regime branch ($145-170M
   band, 40% stall), and an extra-stall-hazard probe matching the breakeven
   h* definition. Deterministic seed; dead paths excluded from the fan and
   surfaced as p_no_deal.
8. **Gates recut**: G1 is now report-fidelity (pinned cells exact, weighted
   EV $186-193M, modal $192-200M) + memo-closed-form breakeven + ramp
   waypoints + hawk-skew + Dirichlet determinism + MC toggle bounds +
   scenario-count stress (memo e3: preferred window stable under tail-merge
   and row-2 split). G2/G3/G4 replays unchanged and green. 159 canary tests.
