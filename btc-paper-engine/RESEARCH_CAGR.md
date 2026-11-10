# RESEARCH_CAGR.md — raise CAGR and size the $100k to a −30% drawdown

Casey, 2026-09-28. Pre-registration: `research/cagr/PREREG.md` (committed
`3d4a97d`, before any candidate ran; AMENDMENT 1 `9b929ec`, before H5).
Harness, scripts, results: `research/cagr/`. Figure: `research/cagr/cagr_answer.png`.

## Answer

**No large CAGR improvement survived verification.** What survived is small:
a correctness fix (H1) and a modest reweight off the pullback leg (70/30).
The real lever is **size**, and the ceiling there is the daily-loss halt, not
drawdown.

**Recommended (awaiting Casey's approval, nothing shipped):**

| setting | today | proposed |
|---|---|---|
| trend trail (engine) | ratchet-then-test, same bar | **H1**: test resting trail, then ratchet |
| blend w_trend (engine /exec/target) | 0.25 | **0.30** |
| KELLY_M | 0.20 | **0.30** |
| SIZING_BASE_USD | 100,000 | 100,000 (fixed; re-base by hand, upward, when flat) |
| MAX_NOTIONAL_USD | 40,000 | **60,000** (peak gross ≈ $57k) |
| DD_HALT_PCT | 0.35 | **0.30** (Casey's −30% = $30k) |
| DAILY_LOSS_HALT_PCT | 0.06 | 0.06 |

Live-like backtest (fixed $100k base, 4.32 bp/side, MTM):

| | 2019+ $/yr | 2019+ max DD | 2014+ $/yr | 2014+ max DD | $6k daily-loss trips 2014+ |
|---|---|---|---|---|---|
| today (75/25, k 0.20) | $6,958 | −$8.7k | $4,688 | −$13.0k | 0 |
| **proposed** | **$11,262** | **−$12.4k** | **$8,929** | **−$19.1k** | **0** |
| proposed at k 0.45 | $16,892 | −$18.6k | $13,394 | −$28.7k | 5 |

Code changes needed (repo, Casey signs): `mirror.KELLY_M_CAP` 0.20 → 0.30;
`MAX_EXPOSURE_FRAC` given headroom so an ordinary drawdown doesn't page
`exposure_over_cap` every poll (at k 0.30 × 1.5 × base it sits ON the 0.45
line and any equity dip crosses it); `main.py` /exec/target, `live.BLENDS`,
dashboard S5 w_trend 0.25 → 0.30; `core._process_donchian` → resting-stop
order, with gate tests on a ratchet-then-wick bar and a gap bar.

## Why not bigger

- **k 0.45 fits −30% on drawdown but trips the daily-loss halt.** Above
  KELLY_M 0.30 `_roll_day` makes DAILY_LOSS manual-resume (ramp v3). At 0.45
  it trips 5× since 2014 (2 since 2019); a halt that waits for a human took
  2019+ CAGR from ~11% to ~1% in the ruin review. Going past 0.30 is a
  decision about that rule, not about drawdown.
- **The full-history size is set by thin 2013 markets.** k at a realised −30%:
  0.39 from 2013, a stable ~0.50–0.57 plateau for starts 2014–2017 (spans the
  2014, 2018 and 2022 bears and the 2020 crash), inflating from 2018 on.
- **Compounding overstates live.** Harness CAGRs compound; live sizes off a
  fixed base. At k 0.45: 13.3% compounding vs 8.2% fixed base (full sample).
  Every dollar figure above is fixed base.

## Candidates (pre-registered rule; full 2013-01..2026-07; CAGR at k_safe)

| | result | verdict | adversarial review |
|---|---|---|---|
| baseline (live engine) | 9.7% | — | — |
| H1 resting-stop trail | 10.2% | PASS | sound; 3 of 344 trend trades change, none since 2020 — a correctness fix, not an edge |
| H2a walk-forward inv-vol | 12.8% | PASS | no lookahead; settles at a near-static ~30% trend share; **cannot run live** (needs 2,190 bars of leg returns, engine keeps 800) → use static 0.30 |
| H2b 50/50 | 23.0% | PASS by rule | **REFUTED (fatal)**: whole edge is 2013–19, in-sample for the trend leg; worse since 2022 (ΔSharpe −0.15); 0.50 is a point on a monotone line, not a peak |
| H3 cross-asset trend | 10.0% | FAIL | E4 Sharpe −0.47 |
| H4 lookback ensemble | 1.1% | FAIL | worse every era |
| H5a H1+H2a | 13.4% (13.2% on the registered window) | PASS | survives, smaller: **11.5% vs 8.8%** at a realised −30% |
| H5b H1+H2b | 23.9% | PASS by rule | rejected with H2b |

Per-era Sharpe (k=1) E1/E2/E3/E4/E5: baseline 0.45/−0.04/1.10/1.45/1.01;
H5a 0.55/0.43/1.18/1.49/0.93. **From 2020 on the reweight is statistically
indistinguishable from today** (paired bootstrap ΔSharpe +0.03 [−0.07, +0.12]).
What supports it is the pullback leg losing money in 2013–2019, eras
genuinely out of sample for that leg (the pullback lost 2013 −34%, 2014 −27%,
2015 −25%, 2017 −45%, 2018 −48%; it has made 14.5%/yr since 2019).

## The finding that matters most

On 13 years of history this is a **2020+ engine**. The trend leg made money
in every era; the pullback lost badly before 2020 and has carried the book
since. The live 75/25 weighting is a bet that the post-2020 market structure
(leveraged perps, liquidation cascades — the pullback's stated rationale)
persists. 70/30 hedges that bet slightly; it does not remove it.

## Honesty box

- Basis: mark-to-market; fees 4.32 bp/side (live HL); engine code path for
  every trade (trade list reproduces production `run_replay` exactly —
  gate-tested, mutation-checked). Bitstamp 4h, BTC from 2011-08.
- Harness audited by an independent counter-agent (reproduced a leg to the
  cent); its fixes are in with tests that fail on the pre-fix code.
- In-sample for most parameters: pullback fit on 2024–26, trend on 2013–21;
  E5 (2024H2–26) spent. **DSR 0.25** for H5a against ~2,533 trials (baseline
  0.10). Treat every number as an upper bound.
- Not modelled: engine book halts (S3 would have halted 2020-03-20), the
  1–2 min post-bar window before the venue stop moves, HL mark-price triggers,
  funding (net exposure ≈ 0, <0.2%/yr), pullback-stop gap fills (+2.97pp,
  harness optimistic there), manual-resume behaviour after a halt.
- Liquidation is not a constraint: unified account, venue `liquidationPx`
  null; 1.25% maintenance means ~49% adverse move at 2× gross.

## Pending questions (ranked)

- **P1** Approve the proposed settings and the four code changes (moves
  expected P&L ~+60% vs today, max DD −$12k → −$19k on 2014+).
- **P1** Keep DAILY_LOSS manual-resume above KELLY_M 0.30? It is the only
  thing capping size at 0.30; loosening it is the path to ~0.45–0.50.
- **P2** Re-base cadence for SIZING_BASE_USD (proposal: by hand, upward only,
  when flat, after a new high-water mark).
- **P2** Keep the tripwires (T1 −$500, T4 98% HW) or scale them with size?
  At $45k gross they will fire on ordinary noise.
- **P3** Build a shadow-replay σ service so walk-forward inv-vol could run
  live (buys little over static 0.30 today).
