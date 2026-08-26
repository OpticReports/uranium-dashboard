# EXECUTOR.md — live S5 execution on Coinbase perps

A separate service that mirrors the paper engine's S5 blend (75% S3 pullback +
25% S4 trend @ 1.5x) onto a real Coinbase Advanced account, sized at the
Kelly-recommended multiplier. The paper engine stays the only decision-maker
and holds no exchange credentials; this service holds a **trade-only** key and
holds no strategy logic. Neither alone can lose money creatively.

## Architecture

```
btc-paper-engine (/exec/target, token-protected)
        |  desired state: pending limits, positions, stops, health flags
        v
btc-executor  --Coinbase Advanced API-->  BTC perp product
   mirror state machine + safety rails       (trade-only API key)
```

- **Pullback leg**: engine's one-bar limit entry -> post-only (maker, ~2bp)
  limit at the same price; cancelled when the engine cancels; ATR stop placed
  on fill as a venue stop-limit.
- **Trend leg**: engine channel-break pending -> market entry; chandelier
  trail mirrored as a venue stop, replaced when the trail ratchets >5bp.
- **Exits**: engine position vanishes -> cancel stop, close at market. If the
  venue stop fired first, the ledger reconciles without double-closing.
- **Sizing**: leg notional = KELLY_M x 1.5 x weight x sizing base. The base
  is live account equity by default, or the fixed SIZING_BASE_USD when set —
  the small-deposit construction (e.g. ~$40k USDC trading a $128k base; the
  deposit is the hard max loss, positions are sized to the base). Halt
  percentages anchor to the base so routine strategy swings against a small
  account don't false-trigger. Every order passes MAX_NOTIONAL_USD and
  MAX_ACCOUNT_LEV (of the base) caps.
- **Telemetry**: one equity/position mark per UTC day persists in state
  (/status "marks") — the raw series for live-vs-paper tracking error and
  funding-cost decomposition during the token phase. /pulse is a public,
  non-sensitive heartbeat (flags only) for automated monitoring.

## Safety rails

| rail | behavior |
|---|---|
| DRY_RUN (default ON) | full state machine runs; orders only logged |
| daily-loss halt | day loss > DAILY_LOSS_HALT_PCT (6%) **of the sizing base** -> cancel all, flatten, halt. Auto-rearms at UTC rollover at KELLY_M <= 0.30; MANUAL above. Boundary caveat: a rearm grants a fresh full day budget, so worst-case loss across a UTC boundary is ~2x the daily rail |
| drawdown halt | equity below high-water minus DD_HALT_PCT (live: 0.35) **of the sizing base** -> same, manual resume |
| kill switch | POST /kill -> same; POST /resume to clear (manual only). Resume also verifies every stop ref against the venue and clears dead ones — but on a leg the ledger believes HOLDS, a dead ref is cleared only once the venue BACKS the ledger (clearing it hands the mirror a placement path that is not reduce-only: on a flat venue that arms a full-size NAKED stop). Divergence -> `LEDGER_DIVERGENCE` halt. Unreadable venue -> the ref is left STRICTLY ALONE: not cleared **and not cancelled**, because in a correlated outage (status UNKNOWN *and* position unreadable — one API failure, and what 2026-08-26 actually looked like) cancelling first killed a live stop and then went on believing in it, and the churn guard suppressed replacement forever. Pages `stop_ref_unverified` (ACTION) |
| /resume?adopt_venue=1 | operator escape from a divergent ledger. A halt whose flatten FAILED keeps its ledger on purpose (it is the only record of what we believe we hold), so `LEDGER_DIVERGENCE` re-fires on every plain /resume — a deadlock only a redeploy could break. `adopt_venue=1` cancels the stops we still believe in, then resets the ledger to venue truth (flat venue -> all legs zeroed; venue holds something unattributable -> refs cleared and entries BLOCKED, same as boot). Refuses outright if the venue cannot be read. Deliberately NOT automatic: only a human who has just looked at Coinbase can tell "our belief is stale" from "the read is lying again" |
| stop protection is BOUNDED | a position whose stop keeps failing is closed, not retried forever. One counter per position (`stop_vanish[leg:entry_ts]`, persisted so a crash-loop cannot reset it), one cap (`STOP_REPLACE_MAX` = 3), fed by BOTH failure doors: a stop the venue confirms then kills (`stop_vanished`), and a stop the venue never confirms — accept-then-cancel inside the ~1s confirm window, or a persistent UNKNOWN read (`stop_unconfirmed`). One poll counts ONE failure even when both doors open, and a placement the venue CONFIRMS resets the counter (unless that same poll recorded a failure — otherwise an accept-then-kill storm, where every placement confirms and every one dies a poll later, would reset forever and never trip the cap). Past the cap -> `STOP_UNPLACEABLE` halt, taken BEFORE the refs are cleared so `_halt_locked`'s terminal-verification loop can still see the order it may have failed to cancel |
| stop placement CHOKE POINT | every path that sends a stop — first placement, trail-ratchet replacement, post-vanish re-arm — passes one corroboration in `_maintain_stop`. It cannot live in the vanished-stop handler: that door only opens on a literal `CANCELLED` status, while a blind read returns UNKNOWN, falls through the churn guard, and once the chandelier ratchets past `stop_replace_bps` (5bp of $74k is $37 — routine for a trend leg) went straight to `place_stop` with no position read at all. Diverged -> `LEDGER_DIVERGENCE` halt; unreadable -> place NOTHING, page `stop_backing_blind`, retry next poll |
| corroboration is AGGREGATE | `venue.position()` is the NET across both legs on one product, so it is compared against the ledger SUM (`sum(l.qty)`), never one leg. Per-leg comparison was wrong in both directions: it false-halted an ordinary S3-long/S4-short book (net 0 read as "the venue holds nothing", including on the silent 00:00 UTC rearm), and it let a phantom leg hide behind a real one (ledger 0.01 real + 0.01 phantom vs venue 0.01 — same sign, non-zero, so it passed, and 0.02 of stops went out against 0.01 of position). Divergence = the venue holds LESS than the ledger claims, or holds it the other way round; holding MORE is fine (a reduce-sized stop still reduces) and is `position_drift`'s problem. **DISCLOSED LIMIT:** on a netted venue a ledger whose legs cancel is indistinguishable from a wholly phantom one — both read 0 — so per-leg stops on an opposite-side book rest on ledger belief alone. No position read can fix this; it needs the open-orders sweep (F1) |
| halt on a BLIND venue | position unreadable at halt time -> cancel NOTHING (the resting stop stays alive), page ACTION-NEEDED, still halt trading. A halt may only cancel/flatten/zero after the venue confirms: probe -> cancel_all -> verify our orders terminal -> re-read (retried) -> flatten (2026-08-26 incident: the old order stripped the stop then aborted) |
| stale engine | feed stale/degraded -> new entries blocked (RED alert, rate-limited), exits still run |
| drift check | venue vs ledger position mismatch > 1% of equity (below one CDE contract) -> RED event. A FAILED venue read is itself a RED (venue_read_failed, 30-min cooldown) - blindness is never silent (2026-08-26: 3 silent days) |
| orphan fills | our limit filled but paper cancelled -> unwound at market |
| restart | ledger + order map persisted; reboot re-places nothing. Boot RECONCILES venue vs ledger: venue-confirmed-flat vs ledger-long -> adopt flat, cancel the trap stop, page (the phantom class); venue-holds vs ledger-flat -> page + BLOCK entries, adopt nothing; unreadable -> page, adopt nothing |
| stop/chase/entry identity | every stop, chase AND entry order carries a persisted attempt counter in its client order id - a cancel-then-replace can never re-send an id the venue has seen. BELIEF ASYMMETRY, deliberate: a STOP is believed only after the venue confirms it OPEN (stop_unconfirmed pages otherwise; failing toward "no stop believed" is safe because the next step re-places under a fresh salt). An ENTRY is believed AT SEND and kept on an unverifiable read (failing toward "order believed live" is safe because the identity dedupe then suppresses re-sends - the round-3 review proved the opposite polarity re-sent full size every poll); an entry ref clears only on a venue-CONFIRMED terminal-and-unfilled read |
| rollback | NEVER roll back to a pre-2026-08-26 image while executor_state.json exists (old loader wipes state on unknown fields); boot writes a one-time .pre-phantom-fix.bak snapshot |

## Setup

1. **Coinbase**: enable derivatives; fund with USDC. Create a CDP API key with
   **view + trade only** (no transfer/withdraw). Note the key name and private
   key PEM.
2. **Render**: deploy the `btc-executor` service from render.yaml. Enter
   secrets in the dashboard: `CB_API_KEY_NAME`, `CB_API_PRIVATE_KEY`,
   `EXEC_TOKEN` (same value as on btc-paper-engine).
3. **Product**: boot logs list every BTC futures product the key can trade
   (`BTC futures products visible to this key: [...]`). Set `CB_PRODUCT_ID`
   accordingly (INTX perp: `BTC-PERP-INTX`; US CFM contracts appear with a
   `-CDE` suffix and trade in 0.01-BTC contracts — the adapter handles both).

## Ramp schedule — v3 (2026-08-10, post counter-agent panel)

Two adversarial reviews (statistical adequacy; risk sequencing) demolished
most of the v2 staircase's reasoning. What they established, with numbers:

- **The slippage justification is dead.** Live book measurement on
  BIP-20DEC30-CDE: spread 1.54bp, level-1 depth 50 contracts ($32.5k). Every
  step through 0.56 (48.5 contracts) fills INSIDE level 1 at one price; the
  0.80 ceiling takes 19 contracts from level 2 for ~$1 of extra cost. Modelled
  size-dependence across the whole range is ~0.5bp — roughly **10x below the
  per-fill noise floor**. There is no size-dependent execution risk here to
  discover gradually. (Casey called this before the agents did.)
- **v2 was RISKIER, not safer.** Simulated over 382 possible start dates:
  v2 carried 4.55x the notional of the cliff plan but **8.06x the worst-case
  drawdown** and a deeper drawdown at 100% of start dates — because the big
  rungs stacked in the back half, landing losses on an already-drawn book.
  "Small steps" measured jump size; risk is set by POSITION size.
- **The latent-bug case is decisive.** Cumulative notional carried before a
  bug is discovered at trade 10: cliff $20.5k vs v2 $50.8k. A 100%-loss
  defect at that point costs the cliff a survivable $20.5k and v2 **the whole
  deposit**. Bounding that number IS the token phase's purpose.
- **Gates were underpowered or unfalsifiable.** 4 trades = ~5.6 informative
  fills; the "within 2x of 6bp" test fails a truly-12bp venue exactly 50% of
  the time at any n. Worse, `cb.py` discarded `average_filled_price`
  entirely — the slippage criterion had sample size ZERO. (Fixed; fills are
  now recorded.)

### The schedule

| step | KELLY_M | advance at | pullback entry | max step |
|---|---|---|---|---|
| token (live) | 0.05 | — | $2,813 | — |
| A | 0.10 | 4 trades | $5,625 | 2.0x |
| B | 0.20 | 8 cumulative | $11,250 | 2.0x |
| C | 0.35 | 12 cumulative | $19,688 | 1.75x |
| D | 0.56 | 16 cumulative | $31,500 | 1.6x |
| ceiling | up to 0.80 | +15-20 at 0.56, quarterly Kelly re-run | $45,000 | 1.4x |

Tested against the alternatives: this rung shape cuts deployed notional 25%
and worst-trade loss 22% vs v2 at identical timing, and **strictly dominates
it** on every risk metric. Sizes at SIZING_BASE_USD=50000; trend-leg entries
are 1/3 of these.

### Advance criteria (ALL must hold)

1. the step's trade count is complete;
2. **cumulative ramp P&L >= 0** — the v2 hole: every other criterion could
   pass while the account sat at its ramp trough, and losing trades bought
   step credit. With this gate: p05 drawdown improves 47%, P(halt) 5.0% ->
   2.4%. Cost: median time to 0.56 goes ~12.6 -> ~18.7 weeks. Worth it;
3. **fill quality** (the primary execution metric, replacing slippage):
   zero post-only rejections unhandled, `entry_chase` rate <= 25%;
4. zero RED events and zero halts since the previous step;
5. leg states reconciled against the paper engine across the whole step.

Slippage is RECORDED via a fill-watch queue (every order placed - entries,
chases, stops, closes - is polled until its status resolves, then its
average fill price lands in state.fills as adverse-positive slip_bps vs the
engine reference). NOTE (2026-08-11 counter-agent audit): the 2026-08-10
commit CLAIMED this and shipped a function with zero call sites and a sign
bug - the dataset was empty until today. Sample count starts now. Pooled
across all steps, one-sided 90% upper bound - never a per-step pass/fail,
which the sample size cannot support.

### Step-BACK / circuit rules

- any criterion fails -> HOLD at the current step, diagnose first;
- **ramp drawdown <= -$5,000 -> step DOWN one.** The $17,500 DRAWDOWN halt
  fired in 0 of 382 simulated ramps — at step D it needs a 41.7% adverse
  move, i.e. it is unreachable during the ramp and cannot do this job;
- **above KELLY_M 0.30 the daily-loss halt reverts to MANUAL resume.** At
  steps C/D a single ordinary-bad trade (-15.6% on notional, the worst in six
  years) trips the $3,000 daily rail — and auto-rearm would silently clear
  the only breaker that is actually reachable during the ramp. IMPLEMENTED
  in `_roll_day` as of 2026-08-11 - it was doc-only for a day (counter-agent
  find); the -$5,000 step-down remains deliberately manual ("never automate
  the ramp");
- two consecutive steps with degrading fill quality -> step DOWN one;
- any halt -> hold for a full extra step's worth of trades after resuming.

### Discipline

Never move SIZING_BASE_USD and KELLY_M in the same step. Never automate the
ramp. Verify `/status` sizing_config after every step — the blueprint has now
contradicted the live env on THREE variables (KELLY_M 11x, SIZING_BASE_USD,
MAX_NOTIONAL_USD clamping steps C and D); all three are fixed in render.yaml
and gate-tested.

### Funding: off the ramp

Funding cannot be gated on a ramp step. At realistic autocorrelation it needs
**~197 days** to estimate an annualized rate to +/-5pp; 3 weeks gives +/-15pp.
Worse, the book is 46% long / 48% short so the funding LEVEL nearly cancels —
the real cost is the correlation between signed exposure and momentum
(corr +0.51), which needs a bull AND a bear to estimate. Price it offline
against the replay's exposure path; carry a live dollar budget per step
instead.

### Later: the base step

Raising SIZING_BASE_USD 50000 -> 100000 doubles notional again WITHOUT adding
cash. Independent of the KELLY_M ramp, gated separately: only after step D has
run clean, with DD_HALT_PCT re-cut to 0.30 and MAX_NOTIONAL_USD to 160000 in
the same change.

## Expectations (measured, 2y window, dashboard basis)

S5 at KELLY_M=0.56 on Coinbase perps modeled at ~33.7% CAGR gross of funding
(paper dashboard 32.8%); at full size P(maxDD>30%) ~14%, at Kelly size ~10%
budget. These are in-sample numbers on the window the strategy was selected
on — treat as ceilings, not forecasts. Funding is unmodeled and measured
across the staircase (it accrues on calendar time while positions are open,
so it is measured identically regardless of how fast the size ramps).

## Operations

- `GET /status` — mode, halts, per-leg ledger, last 50 events, dry-run intents
- `POST /kill` / `POST /resume` — emergency stop / manual restart
- Executor state: `/app/data/executor_state.json` (persistent disk)
- The engine's `/exec/target` is token-protected; set EXEC_TOKEN on BOTH
  services or the feed 401s.

## Halt automation (2026-08-07)

- **DAILY_LOSS auto-rearms** at the UTC day rollover (informational ✅
  alert) while KELLY_M <= 0.30; above that it holds for manual resume (ramp
  v3 rule, enforced in code). Rearm caveat, disclosed: the new day gets a
  fresh full budget anchored at post-loss equity, and if the engine still
  holds its position the mirror re-enters it - worst case across a boundary
  is roughly 2x the daily rail. Below 0.30 the dollar amounts are small and
  this is accepted; above 0.30 the manual gate closes it.
- **LEDGER_DIVERGENCE and STOP_UNPLACEABLE are protection failures, not
  risk breaches** (2026-08-26), and are ALWAYS manual-resume at every
  KELLY_M — the auto-rearm is keyed on `DAILY_LOSS` alone. `LEDGER_DIVERGENCE`
  = the venue does not back a position the ledger claims, so replacing its
  stop would OPEN one; `STOP_UNPLACEABLE` = protection for a live position
  failed `STOP_REPLACE_MAX` times through either door (vanished-after-confirm
  or never-confirmed). Both halt into the normal cancel/flatten sequence, so
  the intended end state is a flat book — verify that on Coinbase before
  resuming, because a halt on a blind venue deliberately flattens nothing.
  If a plain `/resume` keeps re-halting `LEDGER_DIVERGENCE`, the flatten
  failed and the ledger is stale: flatten on Coinbase yourself, then use
  `/resume?adopt_venue=1` (see the safety-rails table). The auto-rearm
  announces `auto_rearm_blocked`, never a ✅ "cleared", when this fires at
  the UTC rollover.
- **DRAWDOWN and KILL remain manual-resume**, deliberately: a circuit
  breaker with automatic reset is a retry loop, and the −35%-of-base floor
  is only a floor because a human stands behind it. Resume is a
  capital-allocation decision (same size / smaller / stop).
- **Transfer reconciliation:** when the whole book is flat (ledger empty,
  venue confirms no exposure), a material equity jump can only be a
  deposit/withdrawal — the halt anchors (day start, HWM) shift by the jump
  instead of tripping the breaker. Any equity move while positions are
  open takes the normal halt path. Limitation: a transfer landing during a
  service restart is absorbed as baseline, not detected as a jump.
