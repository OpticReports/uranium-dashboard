# Production spec — SOXL dispersion book on ibkr-executor

Target variant: **V0.W** (25% short SOXL / 75% long top-N constituents, weekly
rebalance). Backtest basis: 7.2% CAGR, 0.67 Sharpe, −23.3% maxDD, net beta −0.06.

> **Status: NOT approved for capital.** REPORT.md §1 concludes the durable edge
> is ~1.4%/yr and the rest is regime rent. This spec exists so that IF the book
> is run — as a small neutral diversifier or in paper — it is run correctly and
> instrumented to detect its own decay. Ship it OFFLINE first.

## 0. Separation of powers (repo law)

Per CLAUDE.md: the strategy engine is a **keyless decision brain**. It emits
order intents; it never holds IBKR credentials. All execution routes through
`ibkr-executor`, which owns the gateway connection.

```
soxl-dispersion manager (keyless)          ibkr-executor
  computes signals, targets, intents  -->  IB Gateway (ib_async) -> IBKR
  {REBALANCE, [{symbol, side, qty}], reason}
```

DRY_RUN default; OFFLINE → DRY → PAPER → LIVE gate ladder as
`ibkr-executor/README.md` defines. No live capital before a full paper cycle
covering at least one gate transition and one drift-band trigger.

## 1. Signal schedule and data dependencies

| input | source | cadence | fallback |
|---|---|---|---|
| SOXL, SOXS, SOXX EOD close | FMP `historical-price-eod` | daily 17:30 ET | IBKR `reqHistoricalData`; if both fail → **HOLD**, no trade |
| constituent closes | FMP dividend-adjusted | daily | IBKR historical |
| constituent market caps | FMP `historical-market-capitalization` | monthly (1st business day) | carry last month's ranking, flag stale |
| 3m T-bill | FMP `treasury-rates` | daily | carry forward ≤5d, then 0% |
| SOXL borrow rate | **IBKR SLB feed** (`reqMktData` genericTick 46 / short shortable-shares) | daily pre-open | if unavailable → assume 5.0% and alert; if >5.4% sustained 5d → **disable short leg** |
| ^VIX / ^VIX3M | FMP | daily | gate defaults to ON |

**Staleness rule.** Any input older than 3 trading days puts the book in HOLD
(maintain positions, no rebalance). Never trade on carried-forward prices.

## 2. Universe and target construction

```
MONTHLY (first business day, after close):
  caps        := market cap for each candidate, observed today
  eligible    := caps where price exists AND >=60 prior observations
  index30     := top 30 by cap
  basket      := top N (N=12) of index30, cap-weighted within the sleeve

WEEKLY (Wednesday close; see execution window):
  target[t]   := 0.75 * basket_weight[t]   for t in basket
  target[SOXL]:= -0.25
  if gate_state == OFF: scale all targets by 0.0   (cash)
```

Candidate list and the ICE-style capping helper live in `universe.py`;
`modified_cap_weights` is unit-tested against the 8%/4% caps.

**Point-in-time discipline in production is trivial but must be enforced:** rank
on caps as of the decision date and never re-rank history. The backtest's whole
survivorship apparatus exists to reproduce what production gets for free.

## 3. Gate

Only one gate survived both halves of the sample (REPORT.md §4), at Sharpe ~0.2.
**Default: gate DISABLED** — run the book ungated and let the drawdown ladder do
the risk control. If enabled, it is:

```
gate_ON := (SOXX_close < SMA200(SOXX)) AND (rvol20(SOXX) >= median(rvol20, 252d))
```

All signal inputs lag by one day (`signals._shift1`). Gate transitions are
logged and alerted; a transition forces a rebalance on the next window.

## 4. Order types and execution window

| decision | choice | why |
|---|---|---|
| window | **15:45–15:55 ET**, T+0 on signal day | Avoids the closing auction's leveraged-ETF rebalance flow. Every 3× ETF rebalances its swap book MOC; that print is the most adverse liquidity of the day for a SOXL order. |
| SOXL leg | **MIDPRICE** with 5bp cap, fallback LMT at bid/ask +2bp, 3 retries | SOXL spread is ~1–2bp on $4.9bn/day; midpoint fills reliably |
| stock legs | **adaptive LMT (IBKR Adaptive, Normal urgency)** | mega-cap names, 1bp spreads |
| never | MOC / LOC / MKT | see window rationale; MKT on a 3× ETF in a vol spike is how you pay 50bp |
| slippage budget | **3bp per side blended**, alert if 20-day realized > 6bp | backtest assumed 2bp ETF / 3bp stock |

Order sequencing: **trade the short leg first**. If the SOXL locate fails, the
long leg must not already be on — an unhedged 75% long basket is a different
strategy.

## 5. Position sizing, margin and the short leg

```
equity        := NetLiquidation
target_notional[s] := target_weight[s] * equity
qty[s]        := round(target_notional[s] / last_price[s])
```

**Margin (Portfolio Margin assumed).** Short 3× ETFs are penalised: FINRA
requires the maintenance requirement × the fund's leverage factor.

| regime | long stock | short 3× ETF | V0.W book requirement |
|---|---|---|---|
| Reg-T | 25% | **90%** | ~41% of equity |
| Portfolio Margin | ~15% | ~45% | ~23% of equity (max observed 33%) |

- **Reg-T is workable for V0.W** (41%) but **not** for V2/V4/V4.d — those need PM.
- Hard limit: **maintenance utilization ≤ 50%**. Above it, de-lever to target
  immediately rather than waiting for the weekly window.
- Backtest max PM utilization for V0.W: **33%**. An observed reading above 50%
  means the model is wrong, not that the market is unusual — halt and alert.

**Locate / buy-in handling.**

```
pre-trade:  request locate for full SOXL short quantity
  locate short of target  -> size the WHOLE book down proportionally
                             (keep the hedge ratio; never run the long leg naked)
  locate = 0              -> flatten to cash, alert, HOLD until locate returns
buy-in notice             -> treat as forced close: flatten both legs same day,
                             alert, do not re-enter for 5 trading days
```

Buy-in risk correlates with exactly the scenario that hurts most (SOXL squeezing
higher, short notional at its largest). This is the single operational risk that
the backtest cannot model.

## 6. Rebalance logic

```python
def on_close(state, data):
    if data.stale(max_age_days=3):
        return Hold("stale inputs")

    if state.drawdown() <= -0.25:
        return Flatten("drawdown circuit breaker")

    if data.borrow_rate("SOXL") > 0.054 and data.borrow_persisted(days=5):
        return Flatten("borrow above short-leg breakeven")

    util = state.margin_utilization()
    due  = state.is_weekly_window() or state.gate_changed()
    if util > 0.50:
        due = True                       # forced de-lever, off-cycle

    if not due:
        for sym, tgt in state.targets.items():        # drift band
            if abs(state.weight(sym) - tgt) > 0.05:
                due = True
                break
    if not due:
        return Hold("no trigger")

    targets = build_targets(data)                     # sec 2, scaled by gate
    targets = scale_for_locate(targets, data.locate("SOXL"))
    intents = diff_to_intents(state.positions, targets, equity=state.equity)
    intents = [i for i in intents if abs(i.notional) > 0.0025 * state.equity]
    return Rebalance(intents, reason=state.trigger_reason)
```

Note the **no-trade band** on the last line: skip any leg whose correction is
under 25bp of equity. Without it the weekly cadence churns 9.5× capital a year
for nothing (compare V0.D turnover 9.47 vs V0.W 4.53 for near-identical Sharpe).

## 7. Risk limits

| limit | value | action on breach |
|---|---|---|
| max gross exposure | 1.10× equity | de-lever to target |
| max net beta to SOXX | ±0.20 | rebalance; if 20 consecutive days outside → halt |
| per-name cap | 15% of equity | trim at rebalance |
| short leg notional | 25% ±5% of equity | forced rebalance |
| maintenance margin utilization | 50% | off-cycle de-lever |
| drawdown ladder | −10% → halve gross · −18% → quarter gross · **−25% → flat, manual restart** | automatic |
| borrow rate | >5.4%/yr for 5d → short leg off · >23.5% → book off | automatic |

The drawdown ladder is a **de-risking** ladder, not a stop: the backtest shows a
naive circuit breaker locks in losses (V7's gated variants underperform the
ungated book). Halving gross preserves the option to recover.

## 8. Monitoring and alerting

Telegram alerts (btc-executor pattern) on:

- **Borrow rate** crossing 3% / 5.4% / 10% (the 5.4% line is the short leg's
  carry breakeven — the single most important number to watch).
- **Margin cushion** below 2× the maintenance requirement.
- **Gate state changes** and every forced/off-cycle rebalance.
- **Locate failures** and any buy-in notice — page immediately.
- **Tracking vs backtest**: rolling 60-day realized Sharpe and net beta against
  the frozen expectation; alert if realized beta leaves ±0.20 or 60d slippage
  exceeds 6bp/side.
- **Decay monitor**: trailing 2-year α of SOXL vs SOXX. This is the edge itself.
  If it decays above −2%/yr, the strategy's structural component is gone —
  alert and review for shutdown.

`/status` surface exposes: positions, net beta, gross, margin utilization, gate
state, current borrow, drawdown, and the last rebalance reason.

## 9. Rollout gates

1. **OFFLINE** — decision loop only, DryAdapter, compare emitted targets against
   `variants.py` output for the same dates (must match to the share).
2. **PAPER** — one full month including a monthly reconstitution and at least
   one drift-band trigger. Verify locate behaviour and margin readings against
   the model's predictions.
3. **LIVE, 10% size** — one quarter. Compare realized slippage and borrow to the
   assumptions in REPORT.md §7.
4. **LIVE, full size** — only if realized Sharpe over the pilot is within the
   bootstrap 90% CI [3.6%, 10.9%] CAGR band and borrow has stayed under 5.4%.

## 10. Capacity

SOXL median daily dollar volume (trailing 12m): **$4.87bn**. At V0.W's 4.53×
annual turnover:

| capital | daily SOXL trade | % of ADV |
|---|---|---|
| $10mm | $0.18mm | 0.00% |
| $100mm | $1.80mm | 0.04% |
| $500mm | $8.99mm | 0.18% |
| $1bn | $17.98mm | 0.37% |

**Market impact is not the binding constraint — short locate is.** Capacity is
set by how much SOXL the lending desk will source, which is not a function of
ADV and is not observable from this data. Treat $250mm as the working ceiling
until a real locate conversation says otherwise.
