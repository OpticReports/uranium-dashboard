# Research ideas backlog — parked for future infrastructure

Owner directive 2026-07-23: keep the good ideas from reviewed papers on
hand; revisit when the owner builds an IBKR (or similar) execution stack
capable of higher-frequency / cross-sectional trading. Nothing here is
actionable in Composer today. Each idea lists what it needs before any
capital discussion.

## From Singha 2025 (drift regimes — paper REJECTED, ideas salvaged)

The paper's empirics are survivorship artifacts (see
singha2025-drift-regimes.md), but three concepts are independently sound
and worth a clean test on real infrastructure:

1. ~~**Stock-level (not market-level) regime gating.**~~ **CLOSED
   2026-08-27, addendum 32 — TESTED AND FAILED.** Built and measured on our
   own instruments: the regime label predicts forward returns with the
   WRONG sign (-1.27% mean spread, 0/13 tickers significant); the paper's
   regime-conditions-reversal interaction also inverts (corr IN -0.007 vs
   OUT +0.036); applied to HG's legs it cuts TREND Sharpe 0.89->0.22 and
   DIP-BUY 0.58->0.29. Decisive: against random gates at matched
   participation the real gate lands at the 10th percentile — worse than
   random. The inverted steelman also fails its null. Mechanism: our
   engines earn from mean reversion after stress, so a drift filter buys
   what has already run. Do not revisit without new evidence.
2. **Binary on/off signal activation rather than continuous weighting.**
   Turning a weak unconditional signal fully OFF outside its regime beats
   scaling it down, IF the conditional edge is real. Cheap to test.
3. **Mechanical kill-switch layer** (absolute-DD + rolling-window-loss +
   vol-spike + correlation-break, no manual re-entry). We have pieces of
   this in monitor.py alerts; a hard systematic version belongs in any
   future self-executing IBKR stack.

Validation bar before ANY of these trade real money (the standing rule):
- Survivorship-clean universe (point-in-time index membership, delistings
  included) — the exact failure that sank the source paper.
- Realistic costs: ≥5bp all-in per side for liquid large caps, spread +
  impact modeled; reversal-flavored signals tested against next-day-open
  fills, never close-to-close (bid-ask bounce).
- Full-cycle OOS including 2008, 2018, 2022 — not cherry bull windows.
- Sanity ceiling: any result with Sharpe > ~3 is presumed broken until the
  pipeline is proven clean.

## From Wang 2020 (HMM regimes — adopted for the canary, benched for equities)

- Gaussian-HMM equity regime labels had no forward-return edge for our
  symphonies (B1 FAIL), but the descriptive labeling worked on Treasury
  features (B1-T PASS → canary stat-regime strip). On an IBKR stack with
  intraday data, re-test whether HMM states on higher-frequency features
  (realized vol, microstructure) have forward edge where daily bars had
  none.

## From the execution study (addendum 14, 2026-07-29)

- Composer-vs-IBKR execution gap measured at -$1.3k..+$15k/yr on $250k —
  assumption-bound, not decision-grade. Revisit the migration case when:
  (a) divergence.py shows live Composer slippage persistently >5bps/side,
  (b) the book approaches ~$1M+ (gap scales with AUM), or (c) strategies
  are redesigned for materially lower turnover. The intraday-guard
  "responsiveness" benefit tested at ~zero on daily data — retest with real
  intraday data if the IBKR stack gets built.

## Capacity at $1M+ (owner plans ~12mo scale-up; measured 2026-07-29)

p95 daily one-way trade at a $1M book vs 6-month avg daily $ volume:
ZVOL 32.6% of ADV (!), VBF 31.4% (!), VXZ 12.8%, VIXM 5.9%, ANGL 1.2%.
Composer batches MARKET orders into a 15-minute window and cannot work
orders — 30% of screen ADV in 15 minutes is 50-150bps impact territory on
those names, not the engine's 5bps (ETF create/redeem softens this — true
capacity is the underlying's depth — but batch market orders don't access
it well). ZVOL is already ~8% of ADV at the current $250k book: the
harvester's live divergence is the canary; watch its monthly numbers.
Scale path BEFORE any IBKR migration: swap thin tickers for deep
equivalents inside Composer (VBF->LQD/VCIT, VIXM/VXZ->VIXY-based mid-term
structures, ZVOL->deeper short-vol implementation) — same exposures,
penny-wide instruments; removes most of the capacity problem natively.
Migration gate at ~$500-750k: build the IBKR stack only if measured live
slippage trends >5bps/side or the ticker swaps prove unavailable.

## TSMOM shelf candidate (addendum 20, 2026-08-01 — CLOSED with reopen conditions)

Literature-faithful multi-asset trend engine (Man/AHL corpus), QA-validated
spec: sleeves SPY/TLT/GLD/DBC; signal = majority vote of 63/126/252d
cumulative returns; inverse-vol (63d) sleeve weights; long asset on
positive vote, else SH (for SPY) / TBF (for TLT) short legs, BIL for
GLD/DBC (no viable inverse). 19y frictionless: CAGR ~+6.5%, maxDD ~13%,
2008 +26.5%, 2022 +3.7%, corr to live blend 0.10. Composer-expressible
(nested ifs + wt-inverse-vol). DO NOT BUILD while: KMLM holds its ~29%
trend slot AND live-engine Sharpes stay >>1. REOPEN if KMLM is removed,
or engine Sharpes decay toward ~1 during a developing multi-quarter
inflation/trend regime. Prototype tree + QA data: session scratchpad
gates/tsmom_tree.json, agents' variant tables in session transcript.

## SETTLED QUESTIONS — do not re-study without new evidence (2026-08-05)

External de-risking overlays on the current engines are REJECTED as a
class, measured SIX independent ways: trend gates (add. 19b), strategy
vol-targeting (20b), DD-exit rules (21), VRP sizing (25), band-edge
variants (25), GARCH vol-regime gating + sizing on the harvester (31 --
including sizing UP, which fails the same way: every 'size up when calm'
rule concentrates short vol exactly where vol gaps). Mechanism, replicated: every engine is internally
convexity-aware and earns disproportionately in its own high-vol/stress
state; overlays de-risk exactly those states. Any new overlay proposal
must first show the ENGINES' character changed (e.g., live divergence
shows an engine losing its stress-state earnings) — otherwise cite this
entry and decline. Allocation-layer detection (two-tier alerts, book DD
alarm, cap, earn-back) remains the sanctioned risk machinery.

## Trigger to revisit

Owner starts building the IBKR execution project (or equivalent
higher-frequency capable stack). At that point: pick idea #1 (per-
instrument regime gating) first — it is the cheapest to falsify with a
survivorship-clean universe and honest costs.

## From the crash simulations (addendum 39, 2026-10-07)

Measured, not adopted — each is an owner decision; the house rule on
overlays stands (nine failures), so only mechanical changes with a
deterministic rationale are listed.

1. **C1 — KMLM short-vol termination** (SVIX leg -> PULS when VIX > VIX3M
   at the decision close). Real era: no measurable effect (+1%, 48 gate
   days, inside the placebo band). COVID replay: better under every
   regime-flag stand-in (crash-window maxDD -10 to -22pp). Deterministic
   mechanism, not a signal. KILLED for HARV (its backwardation entries are
   the edge: real era -5%, COVID 12m -9%, placebo p03).
2. **C3 — HARV cash leg PULS -> BIL.** Costs ~0.5%/yr; PULS fell ~5% in
   March 2020, BIL did not (COVID crash maxDD 11.5% -> 6.0%). BOXX would do
   the same job (did not exist in 2020). KMLM's 12% PULS leg: negligible.
3. **C2 — HG bear gate (trend baskets -> BIL when SPY < 200d MA).** The
   measured price of HG's long-bear risk: ~-10%/yr in 2015-23, worse in
   2022 and in V-recoveries; +1.1x/+1.2x and DD 71% -> 60%/29% in the
   2000/2008 reconstructions. Not recommended as-is. Reopen only if the
   owner wants to pay bull-market return for grinding-bear protection.
4. **HG long-bear calibration.** Reconstructed HG draws down ~70% in both
   2000-02 and 2007-09 (36% in its real record; 40% anomaly alarm). The
   alarm will fire early and often in a multi-year bear; that is
   informational, not a trade. KMLM's crash behaviour is unresolvable
   (regime flag not reconstructible; results span -58% to +51% in the
   COVID window across six stand-ins) — the engine's edge is concentrated
   on exact flag timing, a fragility to keep in mind at any weight above
   the current 29%.

## From the gate study (addendum 40, 2026-10-08)

5. **HG 200d-family gate — the simplest member only.** In the 1990-2026
   proxy every 200d-family gate on HG's trend baskets raises Sharpe
   (1.00 -> 1.11-1.19), Sortino and Calmar and cuts max DD 72% -> 60-65%,
   beating 200 re-dated placebos and its own inverse; the return edge is
   five bear episodes and the cost is every V-recovery (2015-26: every
   gate costs 5-28pp/yr, nothing beats as-built). The members (binary,
   vote, hysteresis, G6) cannot be told apart (block-bootstrap P 0.45-0.80;
   best-of-7 edge = +0.03 Sharpe = selection effect). If the owner wants
   the insurance, build the binary 200d gate (or G6) as a draft and run
   the standard gate tests; do not tune the shape.
6. **CLOSED again: macro conditioning of the gate** (CAPE level, CAPE
   high-for-long, yield-curve inversion, credit-spread percentile, oil
   +50% yoy, and their count). None beats a level-matched placebo in both
   panels; CAPE and credit lose to their mirror inverses; the curve loses
   on all three metrics in the long panel; oil's four episodes are not
   evidence. Literature agrees (curve: 24/24 loser as an equity exit,
   Fama-French 2019; CAPE: Sharpe = buy-and-hold, AIM 2017). Reopen only
   with a refereed result showing a macro conditioner improving a trend
   rule out of sample — the one such hint (Neely et al. 2014) puts macro
   on the RE-ENTRY side.
7. **Reopen condition for a graded gate:** the state-conditional slow/fast
   blend of Goulding-Harvey-Mazzoleni (FAJ 2024; Sharpe 0.64 -> 0.80 after
   costs, weights shrunk to 0.5). HG already carries both legs (SPY vs
   200d = slow; TQQQ 10>20d = fast). Not built: it is a fitted blend with
   <=5 bear episodes to fit on; it would need the full placebo/inverse
   treatment and a pre-registered spec before any live test.


8. HG leverage gate on the trend baskets (add. 42, 2026-10-17). Plain SPY>200d on
   {TQQQ,UPRO,UDOW,SSO,TNA} only; fallback 1x (+53.6%/1.12/DD 65% over 1990-2026), half
   cash (+54.6/1.14/62) or cash (+55.5/1.16/60 = add. 40 B1); costs 11pp/yr and 0.06
   Sharpe in 2015-26. Owner decision open (extends entry 5). Never gate the dip-buys.
9. KMLM long-leg vol gate (add. 42). V20<25 / VT16 on SOXL/TECL/SPXL/LABU: DD 55 -> 45-48,
   Sharpe 2.15 -> 2.21, CAGR -11pp, 2015-26 in sample only. Needs a long-history KMLM
   stand-in before it can be a candidate.
10. Negative result worth keeping (add. 42): de-levering HG's RSI dip-buys hurts on every
    metric in both panels; they are the engine's bear-market return source (+77%/+84%/yr
    in 2000-02 / 2007-09 on the proxy panel, 3x by construction).

11. Forward watch, not a gate (add. 43, 2026-10-17): "CAPE >= 35 with the 200d" on HG's
    trend baskets. Sharpe 1.19 vs 1.12 over 1990-2026, timing beats 209/210 re-datings,
    but four episodes and a hindsight threshold; de-levered since 2025-07 and 25% behind
    the 200d over that stretch. Log the live stretch; revisit after it completes.

12. Lead, untested (add. 51, 2026-11-01): a 12-1 month cross-asset momentum sleeve (top 3 of SPY EFA
    EEM IEF TLT GLD DBC VNQ UUP, monthly) earned Sharpe 0.73 / DD -14% in 2012-26 (0.56 / -27% from
    2008) with ~0.07 correlation to the book. Not cash-like (0.52 correlation with SPY, a -27% drawdown
    in 2008-09) and not a return improver; a possible diversifier beside KMLM if one is ever wanted,
    which would need its own study. The paper's asset-class value leg (worst 5-year return) earns
    0.1-0.3 across lookbacks (0.29 in AQR's own series since 2012). Do not build a value engine on its
    own; see add. 51 answer 4.
13. IBKR value/momentum stock sleeve (add. 52, 2026-11-03): a big-cap long-only 50/50 of top-30%
    12-2 momentum and top-30% book-to-market (French 2x3 rows, 140-300 names each) earned the market
    +2.6%/yr gross over 1963-2026 (+2.2% net of assumed costs), beta 1, TE 5%, but +0.3%/yr since 2010
    (-0.1% net; -0.6%/yr through 2024, the rest is the 2025-26 value rally); the live ETF versions
    earned SPY +0.5% (MTUM+VLUE, 2013-; +0.0 with October 2026) to -3.3% (QVAL+QMOM, 2016-). A SPY
    replacement, not a diversifier for the Composer book, and not a return engine. If the exposure is
    wanted: ETF pair first (SPMO or MTUM + VLUE, quarterly), measured against SPY; a stock engine only
    for capacity/ownership reasons, behind the point-in-time fundamentals prerequisite (add. 51),
    keyless through ibkr-executor, shadowed. Open input: the owner's genomics sleeve record.
14. SETTLED (add. 53, 2026-11-05): overnight / pre-open overlays on the engines' leveraged legs — exit
    or flip at the open on the fund's gap, the sector's gap, Asia's closes, the DAX open, VIX level /
    change / backwardation, the entry day's crash, their AND-combinations, and a flip-frequency
    breaker — every one lowered CAGR, Sharpe and (mostly) deepened max DD on the KMLM and HG paths
    2015-26, at or below the 5th placebo percentile: after an oversold close, a bad overnight predicts a
    better session (893 dip-buy mornings since 2008: bottom gap decile +4.7% open-to-close, 70% up).
    The tenth failure of the de-risking-overlay class. The IBKR migration gains nothing from overnight
    action; fills (add. 14b) and decision time (add. 50) were closed earlier. Reopen only with a
    mechanism that is not "de-risk the stress state". The live question 11-05 raised is sizing (KMLM's
    75% single-3x-fund leg; Op 3), not venue. The other side (buy the open after an oversold close on
    a 5%+ gap-down, SOXL/TECL/TQQQ/LABU): +3.6% on 40 days in 18 years, nominal t 2.0, family-wise p
    0.32, +1.9% without the best three trades, no transfer to seven other leveraged funds — an
    in-sample anomaly to log (one pre-registered rule, auction prints), not an edge to trade; 38
    trades needed for t 2.

15. SETTLED (add. 54.1, 2026-11-05): KMLM leg sizing. Caps on the 75% leveraged leg are a pure sizing
    trade on the engine's own path (Sharpe flat): each point of max drawdown costs 1.1-1.6 points of CAGR
    over 1995-2026 and 4-5 points in the rules' own years, where max DD is the COVID episode by
    definition (leave-one-year-out 2.9-5.6). Vol-targeting and VIX gates look cheaper since 2015 only
    because of Feb-Mar 2020 and cost more over 31 years; 2x/1x substitutions are the worst ratios. The
    SOXL dip-buy branch (the one that fired into 11-05) has no measured return (n 212, t 0.2) but its
    real fall-through is SQQQ/TLT and that edited tree is worse since 2015: it stays as built. Nothing
    here says to resize; the leg size is the owner's call (Op 3, 11-09). Reopen only with a different
    objective than CAGR per point of drawdown (a loss limit, a financing constraint).
16. Execution-log line, not a build (add. 54.2): KMLM, exit a SWITCHER leg (weight 0.375) at the open on
    an own gap ≤ −8% vs the adjusted prior close — 22 fires on 19 days in 11 years, +4.4 pp/yr on a
    194%/yr engine, p_fw 0.13 by rows / 0.14 by days, three episodes, ex-2026 inside the placebo band.
    Joined to the add. 53 morning-bounce log (item 14); ~34 fires for t 2 ≈ 18 years. The RSI-gated
    versions of the same rule depend on a 0.2-point read on 11-05 and must not be used live. Every HG
    rule and every ≤ −5% gated rule: not an edge (settled).
17. Sleeve reading rule (add. 54.3): the Crash Convexity Sleeve responds to bond/credit shocks and
    KIE/PEJ sector extremes, not to VIX or broad-index crashes (0 of 21 triggers on 11-05, correctly);
    its crash return arrives in the 5-20 sessions after a crash day (one per run n 19, next-5 +2.8%,
    84% positive). Judge it then; the Op 1 band sells it then. Whether to add a static vol leg (VIXM:
    +7.3% on crash days, −34% in calm years, +0.7% of the book on 11-05) is the owner's Op 2 question
    (2027-01). Data risk logged: Yahoo's bond-ETF series can miss a monthly ex-dividend, which moves
    the one-day reads by the size of the SHY thresholds (the five early-October path/ledger misses).
18. Watch item (add. 54.4): HARV's one-session short-vol entries on inverted closes have paid in
    sample (real era 15 trades, +0.61%, 80% win, t 1.0; counterfactual ×2.09 → ×1.94); the two
    real-era deep (< −8%) entries lost while the 29-entry record points the other way; 11-05 is deep
    entry number three, outcome in the live evidence record (first inverted close in 77 sessions).
    Revisit at ≥ 30 live inverted-close entries. Monitor label "harvester" → "HARV day return"
    (todo). UPSTREAM DATA DEFECT (add. 47 panel): Yahoo's VXZ is stale for 2018-01-26..2019-01-31
    (169 flat sessions, the Feb-2018 episode included); HARV's and the KMLM sleeve's 2018 path days
    rest on it. Fix: splice VIXM for VXZ in long_panel.py and rebuild engines_ts_synth.json (a
    separate pass; add. 47's frozen harvester numbers for 2018 change, signs do not).
19. SETTLED (add. 54.5): futures volume and the overnight Globex session. The overnight tape predicts
    the SIZE of the next session, not its direction, and the size read is the RANGE (|SPY o→c| 0.41% →
    0.72% by range tercile, t 6.5; volume alone t 5.6 but jointly t 1.0): the overnight move reverses
    on average, down nights continue 51% of the time, and no volume / range / recovery / note / gold /
    yen split survives family-wise over splits with 8+ nights a side. The 11-05 crash was intraday (ES
    +0.04% at 09:00 on 1.0x volume; the funds' own 09:30 prints had it). Two climax-volume cells to
    log, pre-registered, ten occurrences each before anything is a rule: SPY climax volume (≥ 2x its
    median) the session before a 3%+ gap-down → bounce (26 days in 18 months, +3.2% vs −0.4%,
    family-wise 0.04; the engines' legs bounce on exactly those mornings, so no exit rule uses it);
    the fund's own climax volume before a 5%+ gap-down on a fund NOT oversold → continuation (12 days,
    −5.0%, family-wise 0.06, no mirror; the one rule that would have exited 11-05). Data: Yahoo repeats
    the prior session's futures volume on some days (patched from the hourly bars). Not free, not
    tested: VIX futures intraday, open interest, basis, order flow.
20. QUEUED, process, after the IBKR mirror (owner, 2026-11-10): studies come back narrower
    than the thesis they were asked to test. Example: the overnight study (add. 53) answered
    "TA on futures was off a cliff" with price-only proxies (fund opens, sector opens,
    Asia/DAX cash closes, VIX cash) and no futures data at all; futures volume and the
    Globex session were tested only when the owner asked (add. 54.5). Diagnosis to confirm:
    (a) scope follows the data already on disk, not the thesis; (b) no step decomposes the
    thesis into its testable parts before the build; (c) the counter-agent audits the
    correctness of what was built, never the coverage of what was left out; (d) the honesty
    box lists omissions as caveats at the end, not as a gap list that triggers work.
    Candidate fix: a thesis map before every study (each mechanism against each data family:
    price, volume, positioning / open interest, term structure, breadth, cross-asset
    confirmation, horizon and timing, regime splits, second-order effects), every cell
    marked tested or not tested with the reason and the cost to obtain the data; a coverage
    critic in the counter-agent pass; reports lead with what was and was not tested. If it
    works, it becomes a CLAUDE.md convention (mirrors regenerated in the same commit).

21. IN PROGRESS (add. 55, 2026-11-10): the IBKR mirror of the Composer book. Built, off by default,
    not deployed. Gates left, in order: (a) owner: retire blend3070 at cutover, the brain's hosting,
    the merge; (b) paper for at least ten sessions (the monitor's daily paper book from 11-10; the
    executor's own paper book once deployed); (c) an independent review of the round-2 fixes and of
    the final code before any engine is live; (d) on the real account: one limit buy sized near
    cash, and whether same-minute sale proceeds fund a buy; (e) the attestation routine scheduled
    (mirror_attest.py at the 15:15 preview) and MIRROR_ATTEST_TOKEN set; (f) engines live one at a
    time. composer/IBKR_MIRROR.md is the runbook.

22. CANDIDATE EDGE, forward test first (add. 55.4): the mirror's order time. Same 15:54 decisions
    filled at the bar ending 15:56 instead of 15:55: about +160 bps of the book over 83 sessions;
    on Composer's 110 rotation engine-days a 15:56 fill is +3.2 bps of the sleeve against its
    15:53 (t 1.2), placebo -3.3. Mechanism to test: what Composer (and the crowd running the same
    symphonies) buys is dearest at 15:53-15:55. Test: decision stays 15:54:00; alternate the order
    delay by session (0 / 60 / 120 s) on real fills once an engine is live; pre-register 40
    rotation days a side; measure fill against the 15:54 reference. Needs an executor setting for
    the order delay (not built).

23. Idle distributions on BOTH brokers (add. 55.3): a distribution whose payer is not held on the
    pay date lands in account cash outside every symphony / sleeve. Hindcast on $118k: $4,167 a
    year (3.5% of the book) idle until swept; the Composer book is about 2.6x that size. Not lost,
    but uninvested. Candidate standing operation: sweep unallocated cash back into the engines pro
    rata each month (Composer: an invest per symphony under POLICY; mirror: /mirror/credit). Check
    the monitor's IDLE CASH alert covers it and size the drag before proposing the operation.

24. Executor test hygiene on main (found while building the mirror, not touched):
    tests/test_blend.py::test_gate_mf3_5_a_halt_landing_mid_plan_never_opens_a_ladder_spread fails
    in this environment today, apparently on any real date inside the ladder's November window
    (the loop seems to open a leg on the real calendar before the test freezes it; not
    investigated further); and one of the blend /kill service-loop tests fails about one run
    in 3-6 (a different one each time). Both predate the mirror.

