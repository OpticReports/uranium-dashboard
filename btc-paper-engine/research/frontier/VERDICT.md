# Counter-agent verdict on the frontier study — 2026-09-10

**NOT PRESENTED AS A RESULT.** The panel broke enough of it that the numbers
in `frontier.json` must not be quoted. Recorded here so the record survives
the correction.

Three claims went in. One survived with a correction, one is dead, one
survived in direction only.

| claim | verdict |
|---|---|
| C1 · leverage moves return and DD together, so it cannot answer "more profit, same DD" | **SURVIVES**, but "MAR is flat" is wrong — MAR *rises* 1.273 → 1.319 (exit-step) from 0.5x to 2.0x. Leverage mildly improves risk-adjusted return in-sample over that range. Say "moves you along the frontier", never "is neutral". |
| C2 · MAR degrades above 2.0x = over-betting, empirically | **DEAD.** A basis artifact. |
| C3 · cost and cash yield add return at equal-or-lower DD | **DIRECTION SURVIVES, BOTH MAGNITUDES BREAK**, and the ranking claim reverses. |

## B1 — the cash lever was LEVERED. ~44% of it was mine, not the market's.

`frontier.py`'s `eq *= 1 + lev * r` builds `r` from `equity_after/start_equity`,
which already contains the accrued yield — so the 4% got multiplied by 1.5.

The tell is exact: uplift ÷ lev is flat across the whole ray (2.74, 2.99,
3.24, 3.47, 3.88, 4.17), and the honest model agrees with the coded one
*precisely* at lev 1.0 and diverges only above it. That is a bug signature,
not an effect.

It is also backwards in the mechanism: at higher leverage the book deploys
more and holds LESS idle cash (51.9% at 1.5x vs 61.8% at 1x). The code has
idle-cash yield rising with leverage when it should fall.

**Honest cash lever: ~+2.7 to +3.0pp at 1.5x, not +4.86pp.** And the claim
"cash yield beats a leverage step from 1.5x to 1.75x (+4.38pp)" **reverses**.

## B2 — I contradicted my own ruling from the same day

`RESEARCH_FEES.md` A2.2/A2.5, committed hours earlier, names this identical
channel and rules against it: *"`cash_apy=0.00` is the more defensible
setting, not the flattering one… an inconsistency, not a feature."* That
ruling was binding enough to retire the 0.35 Kelly rung. This study then used
`cash_apy=0.04` as a **lever**.

`RESEARCH_PROTOCOL.md` §9 item 1 prices the same thing at **~+0.7pp CAGR**.
This reported +4.86pp — **7x** — and reconciled against neither.

## B3 — C2 reverses under the engine's own marking convention

`frontier.py` levers trade-close returns; `live.py:464-479` (`_blend_step`,
the shipped consumer) levers per-snapshot MARKED returns. Levering chunky
returns is not the same as levering their sub-steps, and the two diverge with
leverage:

| lev | exit-step MAR (published) | bar-marked MAR (live) |
|---|---|---|
| 2.0 | **1.319 (peak)** | 1.283 |
| 3.0 | 1.179 | 1.313 |
| 4.0 | 1.050 | **1.314 (still rising)** |

Worse, C2 is not stable across this study's own four arms: MAR peaks at 2.0,
2.0, 2.5 and 3.0 depending on the arm — so the very levers C3 promotes push
the alleged over-betting threshold outward. **C2 and C3 cannot both be
asserted from this table.**

## The rest, briefly

- **S1** — "fee 8.64 = what we actually pay" is FALSE for the donchian leg.
  `core.py:246` passes `fee_bps` explicitly, so `setdefault` cannot override
  it: S4 pays **12.00 bps in every arm**, and `frontier.json`'s S4 block is
  byte-identical across the fee arms. Worth +0.47pp of baseline — 26% of the
  claimed fee lever, sitting in the baseline as a modelling error. Disclosed
  in PREREG A2.6 and then contradicted by this study's own docstring.
- **S2** — the dropped-first-exit bug (PROTOCOL §9 item 6) is inherited
  verbatim and costs **+1.12pp at 1.5x — 62% of the headline fee lever**. It
  scales with leverage, so it is not common-mode across the ray.
- **S3** — the 5.76 arm holds trade count at 190, i.e. it models around the
  selection effect PREREG A1.1/A1.6 explicitly declined to model. Per
  CLAUDE.md that is an input to REQUEST. +1.80pp is an upper bound on a
  counterfactual we cannot measure.
- **S4** — the ray ignores every live rail. At lev ≥ 2.5 the shipped executor
  would have flattened and halted (15 bars below −35% DD at 2.5x, 330 at
  3.0x). And the halts never fire in the model because they are evaluated on
  the **1x** books — which is precisely what makes the naive re-scale
  self-consistent, and precisely what would not protect a levered account.
- **S5** — n = 1. Every max-DD trough on the ray is the same 2024-04-22
  episode. The MAR spreads carrying C1 and C2 are 0.02–0.14 wide and rest on
  one drawdown in one price path, with no bootstrap — while KELLY.md's
  Politis–Romano pipeline sits in the repo and was used for the fee study.
- **S6** — the MTM drawdown this study promised to report alongside
  trade-close is **silently absent**: `frontier.py` filters for
  `mtm_max_dd_pct`, a key `book_stats` never emits. So "MTM runs ~1pp deeper"
  was asserted from the fee study, not measured here.
- **S7** — unregistered. 4 arms × 9 levs = **36 configs**, absent from the
  §1 trial registry.

## What survived attack, and is safe

- **Funding cost on levered notional.** Expected to bite; does not. Mean net
  signed exposure is −0.0010 (the legs cancel), so at 15%/yr the drag at 3.0x
  is +0.07pp.
- **The fee arithmetic itself**, reproduced independently to 0.01pp: 2.88 bps
  × 190 entries × 0.75 weight × 1.5 lev compounds to 30.70% vs 30.71%
  measured. 5.76 is the right *rate* per A1.1.
- **The naive re-scale matches the shipped architecture** — `main.py` serves
  `{w_trend: 0.25, lev: 1.5}` against 1x legs. The defect is S4's fee, not
  the re-scaling.

## MAR is the wrong yardstick for the question Casey asked

PROTOCOL §4 fixes MAR as the primary objective, so using it is compliant —
but "maximize profit with **no increase in drawdown**" is a constrained
maximization, and MAR is a ratio that improves by shrinking its denominator.
`RESEARCH_CARRY.md` already logs this exact failure mode from its own
counter-agent: *"MAR mechanically rewards dilution"* — from the same 4% cash
assumption, in the same direction.

The right instrument is **iso-drawdown CAGR**: pin DD at the incumbent and
solve for leverage per arm.

| arm | lev needed | CAGR | vs S5 today |
|---|---|---|---|
| incumbent | 1.500 | 28.91% | — |
| post-only rests | 1.510 | 30.90% | **+1.99pp** |
| + cash (as coded) | 1.537 | 34.58% | +5.67pp |
| + both (as coded) | 1.547 | 36.74% | +7.83pp |

On the live marked convention with the cash bug fixed: **+3.52pp honest vs
+6.52pp as-coded.** Direction confirmed, magnitude roughly halved.

## The open input, which gates the largest remaining lever

Whether idle USDC margin on Hyperliquid earns anything like 4% is a FACT WE
DO NOT HAVE. Every cash-arm number is conditioned on it. Per CLAUDE.md that
is an input to request, not to model around — so it is asked, not assumed,
and no cash figure ships until it is answered.
