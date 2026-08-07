# RESEARCH_SWITCH.md — dynamic S5↔S6 leverage interleaving study
## ⚠️ RETRACTED HEADLINE (2026-08-07, same day): look-ahead bug found by counter-agent QA

**Original claim (WRONG):** a 30-day price-efficiency gate (2.0x when directional,
1.5x in chop) beat both static books on return AND drawdown — MAR 2.40 vs ~1.57,
permutation p=0.002, bootstrap-dominant.

**What the QA panel found:** the gate's leverage for step k was decided from a
signal window ending at step k's own exit — and since blend steps span multiple
days, that window CONTAINED the step's own price path. The gate was labeling
trades by their own outcomes. Smoking gun: mean unlevered step return split by
the contemporaneous signal is +0.98% / −0.40%; split by the honestly LAGGED
signal it is **+0.33% / +0.28% — no forward predictive power**. A second, minor
leak: `exit_ts` is a bar-OPEN timestamp, so the signal's last bar closed 4h in
the future. Both bugs are now fixed in `backend/scripts/research_switch.py`
(signals use closed bars only; decisions made at the PREVIOUS exit).

**Why the original robustness checks didn't catch it:** the permutation test,
threshold sweep, and (r, eff)-pair bootstrap all PRESERVED the leaked
contemporaneous pairing — they proved the alignment was real, not that it was
predictive. The independent statistical counter-agent (concentration,
leave-one-year-out, selection-bias simulation, three permutation nulls) also
returned CONFIRMED for the same reason. Only the timestamp-semantics audit
found it. Lesson recorded below.

## Corrected results (honest implementation, same protocol)

| rule | full ret | full maxDD | full MAR | OOS MAR | % at 2x |
|---|---|---|---|---|---|
| S5 static | +214.5% | −21.4% | 1.55 | 1.33 | 0% |
| S6 static | +332.5% | −27.7% | 1.60 | 1.35 | 100% |
| EFF gate q40 (ex-headline) | +269.3% | −24.6% | **1.57** | 1.36 | 53% |
| best corrected rule (tr200inv) | +259.8% | −21.4% | 1.76 | 1.63 | 37% |
| vol-q60 | +307.6% | −22.3% | 1.89 | 1.43 | 56% |

**Selection-noise benchmark (from the statistical counter-agent):** the best of
16 RANDOM block-structured leverage rules on this data achieves median MAR
1.83–1.88 (q95 ~2.05). Every corrected rule sits at or below what pure
selection luck delivers. `tr200inv` (2x in bears) and `vol-q60` are the only
rules with any residual interest — both survive signal lagging (slow signals) —
but neither clears the selection-noise bar with 284 steps of evidence.

## Full QA panel outcome (4 adversarial counter-agents)

| lens | verdict | key finding |
|---|---|---|
| Statistical (concentration, LOYO, selection-sim, 3 permutation nulls) | CONFIRMED — **fooled** | every test preserved the leaked (signal,return) pairing; but its selection-noise bar (best-of-41 rules ≈ MAR 1.9–2.1 by luck) is the standard any future rule must clear |
| Timestamp/look-ahead audit | **FATAL** | signal window at step k's exit contains step k's own path; honest lag → edge gone |
| Live mechanics | **NOT DEPLOYABLE** | independently found the same leak; the only implementable variant today (lever fixed at each leg's ENTRY — `mirror.py` never resizes open legs) scores MAR 1.51 full / 1.28 OOS, BELOW static S5; resize costs (~2–5bp/switch), whipsaw (18.5 switches/yr) and funding drag (0.4–1.4%/yr at 2x) are all secondary |
| Out-of-window regime attack (2020-06→2026-07 refetch, ETH cross-check) | moot for the gate (ran the leaked method) | valid by-products: the BLEND itself made money straight through the Nov-21→Jun-22 crash at both levers (its crash-safety belongs to the strategy, not any gate); the blend has NO edge on ETH (books halt in 2021) — this is a BTC-specific system; honest gate on the extended 5.6y window: MAR 2.50 vs statics 2.32/2.42 — inside selection noise |

## Conclusion

**No deployable switching edge was found.** The corrected study is a negative
result: with this sample, nothing beats simply choosing a static leverage —
and the S5-vs-S6 choice remains governed by the Kelly engine (rec ≈ 1.4x
effective; see KELLY.md). The live plan is unchanged: S5, KELLY_M ramp
0.05 → 0.56 → 0.80.

If the switching idea is revisited, the honest path is the one that cannot
leak: shadow-log a slow signal (200d-trend or realized-vol regime) alongside
live trading for months and evaluate the LIVE record, requiring it to clear
the selection-noise bar (~1.9 full-window MAR equivalent) before any sizing
change.

## Process lessons (why this doc stays in the repo)

1. **Timestamp semantics are the #1 backtest killer.** `exit_ts` = bar OPEN
   here; any signal window ending "at" a trade's exit almost certainly
   includes the trade. The fix pattern: signals from CLOSED bars only, and
   decisions indexed to the PREVIOUS decision point.
2. **Statistical robustness cannot detect a leak it resamples.** Permutation
   tests, bootstraps and sweeps that preserve the (signal, return) pairing
   validate leaked results perfectly. Only a mechanics audit of when each
   number becomes knowable catches it.
3. **The counter-agent panel worked exactly as designed:** four independent
   adversarial lenses; three attacks failed; the one that mattered
   (timestamp audit with mandatory lag-1 re-run) killed the finding in a
   day, before any capital or code-path was touched.
4. The retraction is same-day and the original claim was never wired into
   any live system.

*Original methodology, corrected script and per-rule table:
`backend/scripts/research_switch.py` (QA-fixed). Statistical counter-agent
findings preserved in the study history; basis: trade-step, research fees,
4y fixture window 2022-08→2026-07, 284 steps.*
