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
| daily-loss halt | equity < day-start x (1-6%) -> cancel all, flatten, halt |
| drawdown halt | equity < high-water x (1-25%) -> same |
| kill switch | POST /kill -> same; POST /resume to clear (manual only) |
| stale engine | feed stale/degraded -> new entries blocked, exits still run |
| drift check | venue vs ledger position mismatch > 2% equity -> RED event |
| orphan fills | our limit filled but paper cancelled -> unwound at market |
| restart | ledger + order map persisted; reboot re-places nothing |

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

## Ramp schedule — STAIRCASE (revised 2026-08-10; replaces the single-cliff plan)

Halt thresholds are percentages OF THE BASE, so they must be re-chosen when
the base or deposit changes (target: DD halt ~= 60-65% of deposit; the
executor warns if the DD halt exceeds 80% of the account — it could never
fire before wipeout).

**Why a staircase.** The original plan held KELLY_M at 0.05 for 15-20 trades
then jumped straight to 0.56 — an 11.2x step. Two problems: (1) slippage
measured on a ~$2.8k order does not generalize to a ~$31.5k order, so the
big jump was validated by extrapolation, not measurement; (2) at a measured
1.34 trades/week (318 historical trades, both legs) the account sits at
token size for ~11 weeks earning ~nothing. The staircase reaches 0.56 at the
SAME time (~week 12) while deploying ~4.7x more capital on the way and never
taking a step larger than 3x — safer per step AND a better experiment,
because slippage gets measured at each size before the next one.

| step | KELLY_M | advance at | ~week | pullback entry | step size |
|---|---|---|---|---|---|
| token (live now) | 0.05 | — | 0 | $2,813 | — |
| A | 0.15 | 4 trades (8 fills) | ~3 | $8,438 | 3.0x |
| B | 0.30 | 8 cumulative | ~6 | $16,875 | 2.0x |
| C | 0.45 | 12 cumulative | ~9 | $25,313 | 1.5x |
| D | 0.56 | 16 cumulative | ~12 | $31,500 | 1.2x |
| ceiling | up to 0.80 | +15-20 more at 0.56, quarterly Kelly re-run | ~Feb 2027 | $45,000 | 1.4x |

Sizes shown at SIZING_BASE_USD=50000 (fully funded against the $50k
deposit). Trend-leg entries are 1/3 of the pullback figures (25% vs 75%
weight). DD_HALT_PCT stays 0.35 and MAX_NOTIONAL_USD stays 80000 through
step D. Timing is a median from a 20k-path block bootstrap of the real
inter-trade gaps (p10/p90 on the 16-trade gate: ~wk 9 / ~wk 16) — the
schedule advances on TRADE COUNT, never on the calendar.

**Advance criteria (all must hold at each step):**
1. the step's trade count is complete (count FILLS — entry and exit are two
   independent slippage observations; 4 trades = 8 fills);
2. realized slippage within 2x the 6bp research assumption;
3. annualized funding cost under ~15%;
4. zero RED events and zero halts since the previous step;
5. leg states reconciled against the paper engine across the whole step.

**Step-BACK rules (the staircase must run both directions):**
- any criterion above fails -> HOLD at the current step, diagnose first;
- two consecutive steps with degrading fill quality -> step DOWN one;
- any halt -> hold at the current step for a full extra step's worth of
  trades after resuming.

**Discipline:** never move SIZING_BASE_USD and KELLY_M in the same step —
two levers at once and the attribution is lost. Never automate the ramp:
size increases stay a human decision, the same separation-of-powers rule
that keeps DRAWDOWN halts manual. Verify `/status` sizing_config after every
step (a blueprint default once contradicted the live env by 11x — caught
2026-08-10).

**Later: the base step.** Raising SIZING_BASE_USD 50000 -> 100000 doubles
notional again WITHOUT adding cash (sizing against 2x the deposit). It is
independent of the KELLY_M ramp and gated separately: only after step D has
run clean, with DD_HALT_PCT re-cut to 0.30 and MAX_NOTIONAL_USD to 160000 in
the same change. Worst-start stretch at that configuration: ~-$13.4k against
a $50k deposit (~-$19k at the 0.80 ceiling), from the 2021-26 replay.

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
  alert). It is a rate limiter, not a model-falsification event.
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
