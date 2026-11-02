# SPEC v0 review: statistics and design (counter-agent 1 of 2), 2026-11-02

**Verdict: NOT_PASS. 2 BLOCKING, 3 SERIOUS, 5 MINOR, 3 NOTE.** As written, D-1 cannot change the
decision. On a series with no information, its benchmark centres T at −0.03 to −0.09 rather than 0.
At the edges the SPEC calls detectable, D-1 almost never reaches PASS. And the run uses up the only
unseen data.

Basis (scripts and outputs in `review_stats_work/`):
- Synthetic simulations of the exact D-1 pipeline.
- Mechanical counts on in-sample DTWEXBGS (dates, episodes, |E_f|).
- The sd of DXY daily log changes by era.
- **No DEX\* file was opened. No S1, p_f or further-move statistic was computed on any D-1
  currency or on DXY 1973–2005.**

## BLOCKING

**B1. The benchmark is not a valid null: a series with no information scores T < 0**
(§3.5 L211–217, L226–230; §4 L282–283)

- **Why.** E_f is the eligible days of the *whole* episode. Both its extent and the firing day's
  position depend on the path *after* earlier E_f days and after f itself. So p_f is a look-ahead
  quantity, not the hit rate of any real-time random rule.
- **Test.** I ran the SPEC's D-1 pipeline exactly: trailing-σ s, gate, decel, near-high, 120-day
  cooling, S1 at 250 days, E_f including the firing day. The series were martingales (no momentum, no
  mean reversion): 150 paths × 48 years, with path-clustered SE.

  | null model | rule hit − unconditional | **D_f (SPEC's E_f)** | E_f ≤ f only | E_f ≥ f only |
  |---|---|---|---|---|
  | constant-vol random walk | +0.015 ± 0.009 | **−0.032 ± 0.006** | −0.019 ± 0.004 | −0.034 ± 0.007 |
  | GARCH-t, α .08, β .90 | −0.053 ± 0.009 | **−0.077 ± 0.006** | −0.022 ± 0.005 | −0.086 ± 0.006 |
  | GARCH-t, α .10, β .89 | −0.079 ± 0.010 | **−0.094 ± 0.006** | −0.020 ± 0.004 | −0.107 ± 0.006 |

- **Two mechanisms.** The look-ahead set biases the random walk. Under GARCH there is also vol
  timing: the decel day sits just after the steepest climb, at high conditional vol, so S1 is less
  likely there by construction.
- **Consequence.** I ran the D-1 classifier on the GARCH-null pool at K = 25 and 35. Result: FAIL
  72–76%, **INVERSE 24–28%**, PASS 0. A series with no information would print "deceleration has
  marked a FIRST wave more often than the extreme" about one time in four. L216's claim ("isolates
  Casey's hypothesis") is false.
- **The sign-flip is not exact either.** D_f = S1 − p_f is a centred Bernoulli, which is skewed
  whenever p_f ≠ 0.5. Measured size at nominal 0.05 is 0.03 at p_f = 0.30 and 0.06–0.08 at
  p_f = 0.65 (K 15–35).
- **Fix.**
  - State H0 explicitly.
  - Build the null from surrogates in the Brock–Lakonishok–LeBaron style: per currency, B ≥ 500
    GARCH(1,1)-t surrogates fitted to its daily log changes. Use a date-synchronised
    standardised-residual bootstrap so the cross-section is kept. Run the identical pipeline on
    them.
  - Test T against the surrogate distribution in both tails. Centre PASS, FAIL and INVERSE on
    T − median_surr(T).
  - Add merge-blocking gate **G6**: on martingale surrogates, the centred T has mean 0 ± 0.01 and size
    0.05 ± 0.015.
  - The fitting uses returns, not S1, so it can run at the blind count.

**B2. PASS is close to unreachable; the "+0.15–0.25 MDE" is wrong**
(§2.2 L101–103; §4 L280–282, L288–290, L303–305; §6 L349–350; Q4 L366)

- **The formula is right but is not the PASS rule.** 2.486·sd/√K does give 0.147–0.250. The PASS
  rule adds three things:
  - **The T ≥ 0.15 bar.** It lifts the effective MDE to 0.20 (K 35, sd .35) through 0.25 (K 20,
    sd .45). At a true T of 0.15, PASS by T and p alone is 0.44–0.50, not 0.80. At K_min = 15 the
    MDE is 0.26–0.29.
  - **"≥ 60% of clusters D_c > 0".** This measures the raw hit rate, not the edge. A singleton has
    D_c > 0 only if it is a hit, so the expected share is about p_f + edge (≈ 0.55 at an edge of
    0.20). Clusters with D_c = 0 count against it.
  - **D_f ≡ 0 whenever E_f is all hits or all misses.** E_f spans about 60–120 days, so the
    250-day windows of its days largely overlap. This happens for 52–56% of firings in the martingale simulations. In
    sample, the no-yield variant already has a firing with |E_f| = 1 (2022-11-21). So T ≈ half the
    edge in informative episodes.
- **Simulated P(PASS), K 25–35:**

  | model | edge in informative episodes | P(PASS) | P(FAIL) |
  |---|---|---|---|
  | idealised (SPEC's sd, no zero-D firings, no B1 bias) | +0.15 | 0.35–0.36 | 0.07–0.12 |
  | idealised | +0.25 | 0.83–0.86 | 0.00 |
  | martingale pool (zero-D share and B1 bias included) | +0.16 (RW) / +0.19 (GARCH) | 0.00–0.01 | **0.60–0.81** |
  | martingale pool | +0.27 / +0.32 | 0.03–0.06 | 0.15–0.32 |
  | martingale pool | +0.38 / +0.45 | 0.28–0.35 | 0.01–0.04 |

  Singleton-heavy panels do worse even when idealised: PASS 0.35–0.42 at +0.25.
- **D-2 and D-3 are diluted the same way.**
  - D-2 FAIL, which vetoes the dollar colour, happens 86–95% of the time with no information and
    40–43% at a +0.32 edge.
  - D-3 PASS at n = 12 is 0.12 at +0.32, and it *falls* as n grows (0.05 at n = 48) because
    E[T] ≈ +0.07 < 0.15.
  - §2.1's "~41 years" assumes a binomial test against a fixed p0, which is not the pre-registered
    statistic.
- **FAIL is a bare cut.** "T < 0.05, permanently" has no precision requirement, and a real
  +0.16–0.19 edge lands there 60–81% of the time.
- **Fix.**
  1. Delete the share bar and the absolute T ≥ 0.15 bar. PASS = surrogate-calibrated one-sided
     p ≤ 0.05 on the centred T.
  2. FAIL only if the one-sided 95% upper bound of the centred T is below +0.10. Anything else is
     INCONCLUSIVE.
  3. Replace K_min with a power floor computed blind: run the pipeline on surrogates with an injected
     edge at the blind-count K, and declare UNDERPOWERED if power at +0.20 is below 0.5.
  4. Consider an outcome horizon that overlaps less across E_f (60–120 days) to cut the zero-D
     share, and choose it on surrogates before the freeze.
  5. Reprint §2.2, §6 and Q4 with the simulated MDEs.
  6. If the redesigned power is still below 0.5 at a plausible edge, the honest default for Q1 is
     `forward_only`, keeping D-1 unseen. CLAUDE.md: never build a phase whose result cannot change
     the decision.

## SERIOUS

**S1. The unit of inference is undetermined, and its units are not independent**
(§3.5 L219–222, L233; L96–98)

- **Linkage gap shorter than the outcome window.** Clusters are linked at 126 days but outcomes run
  250 days, so adjacent clusters share up to 123 days of outcome window through the common dollar.
  The same applies to "each firing its own cluster (≥ 120 days apart)" in D-2 and D-3.
- **The firing share runs high.** Measured shares of episodes that fire, against the assumed 60–75%:
  - 86% in sample with the frozen rule;
  - 100% without the yield condition;
  - 88% for the D-1 transposition applied to the dollar;
  - 97–98% in the GARCH simulations.

  GARCH also gives 0.40 episodes per currency-year, so expect about 250 firings.
- **The span switch is likely.** Synthetic panel: the SPEC's currencies, start dates and stress
  windows, plus idiosyncratic firings.

  | firings | K at 126-day linkage | P(span > 24m → calendar years) | K by calendar year | K at 250-day linkage |
  |---|---|---|---|---|
  | 71 | 25 | 0.01 | 29 | 17 |
  | 148 | 31 | 0.26 | 40 | 16 |
  | 202 | 32 | 0.84 | 45 | 11 |
  | 265 | 28 | 1.00 | 48 | 5 |

- **Neither branch has independent units.** Calendar-year clusters (K ≈ 45–48) are then very
  likely primary (P 0.84–1.00 at 200–265 firings). They split single episodes (Jul-97..Jan-99, Sep-08..Mar-09) into "independent"
  years whose outcome windows overlap. Units whose outcome windows cannot overlap give K ≈ 5–17,
  which is at or below K_min.
- **Fix.**
  - Define units so that outcome windows cannot overlap across units: single linkage at ≥ 250
    trading days, or fixed 2-year blocks with each episode assigned to the block of its first
    firing.
  - Power that K via B2 fix 3.
  - In D-2 and D-3, merge firings less than 250 days apart.

**S2. The vol-scaled transposition is not "the frozen rule in volatility units"** (§3.2 L161–171)

- **Self-test on the dollar itself.** In-sample, dates only: the D-1 transposition with the yield
  condition kept, applied to DTWEXBGS, against the 5 frozen firings after the 2009-04-09 warm-up.
  - Kept: 2011-11-01 and 2022-07-28.
  - Shifted: 2020-04-09 moves to 04-16.
  - Lost: 2010-06-03 (s 1.35, gate 5.39% vs a 4.78% climb) and 2012-06-07 (s 1.22, gate 4.88% vs
    4.49%). The trailing σ still holds 2008.
  - Added: 2015-02-19, 2015-08-12 and 2016-06-03. Here s ≈ 0.81–0.86 lowers the gate to 3.2–3.4%,
    and each cleared it by 0.01–0.03pp. These are policy rallies, the regime in which the 1973–2005
    monthly analogue failed.
- **The obvious fix does not work.** Replacing σ_B with the median trailing σ (0.00333 vs 0.00342)
  still loses 2010-06 and 2012-06 and adds 2015-02-24. The problem is the time variation of a 3-year trailing σ (s 0.72–1.45),
  not its level.
- **D-2 uses yet another transposition.** It takes a constant s = 1.38 from 2006–26 and applies it
  backwards, so forward data sets the threshold (against the spirit of G2). Its gate is then 2.1σ of
  a 20-day move in the 1980s and 3.2σ in the 1970s, against 2.6σ in sample.
- **So a D-1 PASS speaks about a different rule.** That rule adapts to regime, fires on calm-period
  rallies and suppresses a second scramble within 3 years of a large one. The D-1 × D-2 table then
  transfers it to a gauge showing the s = 1 rule.
- **Fix.**
  - Add gate **G3b**: the D-1 transposition (yield on) applied to DTWEXBGS must reproduce the
    frozen post-warm-up dates within ±10 days.
  - Choose between at most two scale estimators on G3b alone, which uses only seen dollar dates (for
    example a 10-year trailing σ, or a fixed per-currency σ from a pre-sample window).
  - If neither passes, make Q8's `raw_frozen` primary or drop D-1.
  - Use the same estimator in D-2.

**S3. "15 floating currencies" is false for about 20% of the sample** (L18, L92–93, L176–177)

- **The peg filter removes almost nothing.** The SPEC's own arithmetic goes from 734 to 650
  currency-years after about 60 years of warm-up and outcome windows, which leaves only about 20–25
  currency-years removed as pegged: the MYR 1998–2005 hard peg and little else.
- **Basket and crawling pegs pass it.** They quote a USD rate that moves every day, so they never
  reach ≥ 50% exact zeros:
  - AUD to 1983-12, NZD to 1985-03;
  - NOK to 1992-12, SEK to 1992-11;
  - INR to 1993-03, LKR to 2001-01, MYR to 1997-07;
  - THB and KRW to 1997;
  - BRL to 1999-01.

  That is about 140 eligible currency-years, counted from public regime dates; no file was read.
- **Those spans add K without information.** Policy devaluation steps (AUD 1976, NZD 1984, SEK 1982,
  INR 1991, THB 1984) give a homogeneous E_f, so D = 0. Low-vol pegs hit the 0.25 clip on s, which
  sets a 1% gate that fires on crawl steps. Both add K and firings without information, which
  inflates the K floor and changes what a PASS means.
- **Fix.** Pre-register an external de facto regime filter on a frozen vintage, for example
  Ilzetzki–Reinhart–Rogoff coarse code ≥ 3 (managed float or freer). Apply it blind, then recompute
  the currency-years and K.

## MINOR

1. **The leave-one-out bar is vacuous** (L280). T₋c > 0 holds exactly when D_c < K·T. With T ≥ 0.15
   and K ≥ 15, K·T ≥ 2.25, while D_c ≤ 1, so it is always met. **Fix:** require the minimum
   leave-one-out centred T ≥ 0 (or p ≤ 0.10), or make it descriptive.
2. **The INVERSE wording overclaims** (L283). T ≤ −0.10 means the rule did worse than a random
   eligible day, not "a first wave more often than the extreme": the raw hit rate can still be above
   50%. **Fix:** "flagged the extreme less often than a random day at the same stage (T, K)".
3. **Gaps a builder would fill after the fact.**
   - (a) In D-0, D-2 and D-3, E_f leaves out the yield condition that the rule has, so T there tests
     deceleration plus yield-typing. **Fix:** add it to E_f.
   - (b) The §3.2 calendar needs VIXCLS, which starts in 1990, so D-2 has no defined calendar. Both
     in-sample calendars give identical firings (checked). **Fix:** use B ∩ Y everywhere.
   - (c) E_f is undefined when an episode holds 2 or more firings (**fix:** truncate at the next
     firing), and for days whose 250-day window passes the sample end or enters a peg.
   - (d) T_clean is undefined: filter firings within clusters, or re-cluster?
   - (e) D-3 has no FAIL or INCONCLUSIVE condition and no number of looks: one look at n = 12, or a
     test at each firing with α-spending?
   - (f) "DTWEXM fallback if ICE DXY fails a gate" does not name the gate or its tolerance.
4. **The dollar licence can be met by disjoint subsets** (L241–243). T_global > 0 can come from the
   contaminated global clusters (the post-2000 global events are finder B's five windows) and
   T_clean > 0 from clean singletons. **Fix:** require T over global ∩ clean clusters > 0, and
   report its K.
5. **Printed horizons are understated** (L54–60, L311–312).
   - The normal approximations check out (n = 11.2 / 22.9 / 64.6). Exact binomial needs 13 / 26 / 68
     firings, i.e. 45 / 90 / 234 years.
   - MOM's "~18 episodes, ~180 years" is finder C's bar (two-sided 95% at 50% power). At the SPEC's
     own convention (one-sided, 80% power), 0.48 vs 0.29 needs 38–40 episodes, about 400 years.
   - **Fix:** correct the printed numbers. No decision moves.

## NOTE

1. S1 uses the window (k, k+250], but G1's "further rise" from decel_realtime uses [k, k+250). They
   are identical on all 7 in-sample firings; state one definition.
2. The memo quotes 2022-07-28 as "+6.6% more", but the committed json and a recompute both give
   +5.2%. It is an S1 miss either way. Passed to the numbers reviewer.
3. The benchmark only samples episodes in which the rule fired, so episode selection is never
   tested. That is harmless at the 86–100% firing share measured above, but the SPEC should say so.

**Confirmed sound:** G1 reproduces the 6 / 7 dates on both calendars. One-sidedness is pre-stated.
The decision classes are exhaustive and mutually exclusive. The D-3 arithmetic matches its stated
(binomial) basis. Every RE-ARM, yield and raw-threshold variant is descriptive, so there is no
multiplicity leak.

**Not checked (needs outcomes):** the real p_f, the zero-D share and the null bias on D-1 currencies.
Measure them on surrogates (B1, B2), not on the data.
