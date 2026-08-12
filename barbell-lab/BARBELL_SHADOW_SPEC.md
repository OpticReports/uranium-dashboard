# BARBELL-SHADOW — live shadow tracker for the BARBELL-TIMER champion

**Frozen 2026-08-12, BEFORE any live evidence existed.** Every rule below was
fixed on this date. Amendments (if ever) get logged here with dates, and
nothing already accrued is re-scored under new rules.

## What this is (and is not)

A **keyless decision brain** that computes, records, and displays — every
month — what the BARBELL-TIMER study's surviving engine would hold, using
**live tradeable instruments**. It places **no orders, holds no credentials,
and never will** (repo separation-of-powers law: strategy engines are keyless;
credentials live only in executor services).

Why it exists: the BARBELL-TIMER study (research/barbell_timer/VERDICT.md)
exhausted its multiple-testing budget at family = 28. Any further mining of
the same 1990–2026 window is more likely to fit noise than signal. The only
uncontaminated evidence left is **forward evidence** — so the champion goes
on paper, frozen, and earns its record live.

Path to live trading (each stage needs Casey's explicit go, none is implied):

1. **SHADOW (this)** — decisions logged monthly on the barbell-lab service.
2. **PAPER via IBKR** — ibkr-executor consumes `/api/shadow` against the IBKR
   paper account. Separate build, DRY_RUN semantics, staged rollout gates.
3. **LIVE via IBKR** — same executor, real account, position caps + kill
   switches, per the ibkr-executor rollout law.

## Variants tracked (both frozen)

**V1 `relmom_cash`** — the study champion, verbatim:
- 12-1 relative momentum: GDE if `mom121(GDE) > mom121(SPY)` else SPY.
- Absolute filter: winner held only if its own `mom121 > mom121(bills)`;
  otherwise BOXX.

**V2 `relmom_s16gated`** — pre-registered refinement from amendment A17
(NOT a study survivor at rule level; it ships to shadow to earn evidence,
never to skip ahead of V1):
- V1's state, except: state == GDE **and** s16 risk-off → BOXX.
- s16 (live proxy): `mom121(XLU) − mom121(SPY) > 0` → risk-off.
  DEVIATION FLAG: the study's s16 used Ken French *Utils* minus the
  *equal-weight 12-industry market* (61.8% OOS hit rate, p_adj≈0.08). Live
  we substitute XLU (cap-weighted utilities ETF) and SPY (cap-weighted
  market). This proxy choice is frozen here, before evidence; the study's
  Telcm≠XLC lesson says sector-fund proxies can invert — that risk is
  accepted and disclosed, not hidden. QUANTIFIED (counter-agent referee,
  2026-08-12): swapping only the market leg from equal-weight to the
  cap-weighted market flips the s16 sign in 43/437 OOS months (9.8%) and
  degrades the in-sample gated backtest from Calmar 0.55 / −18.8% maxDD
  (study construction) to 0.38 / −25.0% — roughly a third of the gate's
  drawdown benefit. The XLU-for-French-Utils substitution is an ADDITIONAL
  unmeasured basis on top. V2 is therefore strictly evidence-earning; it
  never jumps the queue ahead of V1.

Benchmarks recorded alongside: B&H GDE, B&H SPY, static 50/50
(monthly-drift-rebalanced, same cost model).

## Data + signal construction (frozen)

- Prices: Yahoo adjusted daily closes (FMP cross-check) for GDE, SPY, BOXX,
  XLU via the standard ingest (`config/data.yaml`, no proxies — live ETF
  history only; 12-1 needs 13 months and GDE has traded since 2023-03).
- Monthly return of month *t* = month-end adjusted close *t* / month-end
  adjusted close *t−1* − 1. A month is **complete** only when the ingested
  data contains a later-month trading day.
- `mom121(x)` = compounded monthly returns over months *t−11 … t−1*
  (11 months, **skipping month t**) — the repo-standard 12-1 convention.
- Bills (absolute-filter benchmark only): monthly bill return for month *t*
  = `(1 + DTB3[month-end t−1]/100)^(1/12) − 1` (FRED DTB3, de-annualized;
  known at the start of month t). BOXX the *held instrument* uses the real
  fund's returns — the bills series is only the filter's hurdle.

## Timing + accounting (frozen — the Oct-2008 lesson is the whole point)

- Decision month *t* uses only complete months ≤ *t*; the decided state is
  **held for month t+1** and earns close(*t*) → close(*t+1*) monthly return
  (intramonth-blind, same convention as the study).
- The nightly job logs the held-month decision **append-only** to
  `shadow_log` on the first run of each month. A decision first logged after
  the **5th calendar day** of its held month is stamped **LATE** — the study
  showed one month of execution slippage (Oct-2008) erased the entire
  drawdown edge, so discipline is tracked as data, not assumed.
- Shadow returns charge **5bp × one-way turnover** on switches, drift-aware,
  initial buy-in uncharged — identical to the study's cost model.

## Integrity tripwires

- **Recompute-vs-log**: the board recomputes every decision since freeze from
  current data and diffs against the append-only log. Any mismatch (vendor
  revised history, adjusted-close drift) is a RED flag on the page and an
  alert row. Logged decisions are never edited.
- Signals live in `src/barbell/shadow.py`; its gate tests pin exact parity
  with the research implementation on the frozen study fixture
  (`research/barbell_timer/panel_monthly.json` → `rules_results.json`
  rule-2 states). If the live brain ever diverges from the studied brain,
  tests fail before deploy.

## Pre-registered evaluation (honesty box, written before any outcome)

- 24/36 live months **cannot** statistically confirm a CAGR/Calmar edge —
  the study needed 36 *years*. No performance kill-bar is pretended here.
- Graduation to stage 2 (IBKR paper) is **operational**, judged at ≥ 12 live
  months: zero unresolved recompute-vs-log mismatches, zero LATE months
  (or a fix for whatever caused them), and live GDE/BOXX behavior consistent
  with the study's synthetic assumptions (no unexplained tracking anomaly).
- What WOULD kill the engine early: a decision the research implementation
  would not have made (implementation divergence), or a repeat of the
  lag-stress failure mode in live ops (LATE month coinciding with a switch).
- Reference frozen study numbers (OOS 1990-02→2026-07, synthetic GDE):
  relmom_cash 15.23% CAGR / −22.7% maxDD / Calmar 0.67 vs SPY
  11.03% / −50.8% / 0.22; lag-stressed relmom_cash 12.90% / −49.3% (KILL).
  Live results will differ: real GDE ≠ synthetic (TE ±1%/yr band), and
  36 months is weather, not climate.

## Amendment log

- **2026-08-12 (pre-live, same day as freeze; counter-agent referee
  findings on commit a252aa2).** Surveillance hardening only — no
  pre-registered rule, timing, or cost changed; nothing accrued is
  re-scored:
  1. **Missing-log tripwire**: a live-scored held month with no logged row
     past its day-5 deadline is a RED board failure (wall-clock based, so a
     stale feed or dead scheduler cannot hide a month). The referee showed
     the original build let a stale-DTB3 month vanish silently — the exact
     Oct-2008 failure class the tracker exists to catch.
  2. **Tri-state recompute check**: a logged decision month absent from the
     recomputed frame (vendor truncated history) is now an explicit
     UNRECOMPUTABLE warning, never a silent pass.
  3. **Per-variant benchmark windows**: benchmark equity is computed over
     exactly each variant's scored months, never a longer window.
  4. **Contiguity assertion** on every monthly input series (positional
     12-1 windows would silently misalign across a gap month; DTB3 had no
     other continuity validation).
  5. s16 proxy risk quantified in the deviation flag above.
