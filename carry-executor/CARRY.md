# carry-executor — ETH funding carry sleeve

Casey, 2026-10-01: "start working on the carry trade logic". Choices made with
him: **ETH carry in the main Hyperliquid account, using idle USDC (no transfer),
$30k, gated 8% on / 5% off, a separate service.**

## What it does

- **Position:** long spot **UETH** (pair `@151`) and short the **ETH perp** in
  the same quantity. Price moves cancel, apart from the small spot-vs-perp
  basis. The short collects funding.
- **Decision (keyless engine):** `btc-paper-engine` `GET /carry/target`. The
  funding monitor's HL ETH reading turns the sleeve ON when the 30-day mean is
  at least 8%/yr and OFF below 5%. Pages: "⚡ CARRY ON / OFF".
- **Execution (this service):** every 5 min, one IOC per leg (±15 bp from mid):
  - spot is moved first toward the target;
  - then the perp is set to the negative of what spot *actually holds*;
  - an open buys spot, then shorts the filled quantity;
  - a close sells spot, then buys back the short reduce-only.

  A partial fill can never leave a naked short.
- **Target:** notional / spot mid on open. Re-sized at a UTC month start, only
  if the position has drifted more than 25% from the notional.
- **Margin:** the ETH perp is set to CROSS margin (5×) before the first short,
  so the account's USDC backs it.

**It owns ETH and UETH in this account.** Any extra UETH, or a manual ETH perp
position, is traded back to the sleeve's target. Don't hold ETH or UETH by
hand in the main account. It never touches BTC.

There is no testnet rehearsal: HL testnet has no UETH pair, so the service
refuses to start there. DRY_RUN on mainnet is the rehearsal.

## Funding (where the money comes from)

- About $30k of the ~$100k spot USDC, which is idle collateral, becomes UETH.
- The short needs only a few thousand dollars of margin from the same USDC
  pool.
- Nothing is transferred in or out of the account.
- btc-executor's equity counts UETH at its spot mid (2026-10-01), so the swap
  does not look like a loss to the BTC book's halts. The short's P&L is
  already inside the USDC total, verified live: the unified spot USDC figure
  moves cent-for-cent with perp unrealized PnL.

## Rails

| rail | behaviour |
|---|---|
| `DRY_RUN` (default **true**) | sends nothing; logs each distinct intended order once |
| `CARRY_NOTIONAL_USD` (default **0**) | 0 never opens. An open sleeve keeps its size at 0; close it with `CARRY_ENABLED=false`. Approved size: 30000 |
| `CARRY_MAX_NOTIONAL_USD` (repo, 50k) | env above it sizes at the cap and pages |
| stale / unknown / malformed decision | **holds the venue**: no open, close or re-size, and never re-buys a sleeve the account no longer holds. Only the hedge is kept matched |
| `CARRY_ENABLED=false` | unwinds and stays flat; works without the engine |
| margin guard | ETH mid within 15% of the short's liquidation price → unwind + RED, then **no re-open for 24h**. A liquidation price at or below the mark (nonsense for a short) is ignored and paged. The first open logs the venue's liquidation price |
| unreadable venue | no orders; RED after 3 passes |
| hedge gap > $50 for 2 passes | RED `unhedged`, also counted on passes that failed mid-way, from a fresh read |
| cross-margin setup | done BEFORE any risk-adding order; if it fails, nothing is bought that pass |
| UETH locked in a resting spot order | RED `spot_locked` (cancel it on the HL UI) |
| `POST /halt` / `/resume` (EXEC_TOKEN) | stop / restart sending; legs left as they are |
| btc-executor stops counting UETH (rollback) while the sleeve is held | RED `sleeve_unseen` after 3 passes (~15 min); nothing is unwound. Not checked while carry is HALTED |
| unreadable state file | boots HALTED |

## Go-live (Casey's actions)

**Precondition:** btc-executor and btc-paper-engine must be on the build that
includes this change. Merging to main deploys both. The carry service also
checks this itself: it will not open while btc-executor's public `/pulse`
lacks `equity_counts_spot_tokens: true`. That build is what makes btc-executor
count spot UETH in equity instead of reading the swap as a $30k loss.

1. **Approve a new API wallet** in Hyperliquid (API → generate). Name it
   "CARRY EXECUTOR". This is the third named slot of 3. The service refuses to
   start on btc-executor's key.
2. **btc-paper-engine (Render):** add `EXEC_READ_TOKEN` (a new random value).
   It can read `/carry/target` and `/exec/target` and nothing else.
3. **Create the `carry-executor` service** from the blueprint and set:

   | variable | value |
   |---|---|
   | `HL_SECRET_KEY` | the new agent's key |
   | `HL_ACCOUNT_ADDRESS` | the main account |
   | `ENGINE_READ_TOKEN` | the engine's `EXEC_READ_TOKEN` from step 2. **Never** the engine's `EXEC_TOKEN`, which can halt and reset the BTC books |
   | `EXEC_TOKEN` / `EXEC_READ_TOKEN` | new values, for this service's own `/halt` `/resume` `/status` |
   | Telegram vars | same bot as the other services |

   Leave `DRY_RUN` and `CARRY_NOTIONAL_USD` unset.
4. **Dry run:** set `CARRY_NOTIONAL_USD=30000` and keep `DRY_RUN` unset.
   Check `/pulse`: the btc-executor preflight passes (no `open_blocked`),
   the signal reads ARMED (HL ETH is ~10%/yr today), and the dry-run intent
   shows a spot BUY of ~30000/px UETH. Run it for at least a day.
5. **Live:** set `DRY_RUN=false`. On the first armed pass it opens, and you
   get a "✅ carry opened" page carrying the venue's liquidation price.

To exit: `CARRY_ENABLED=false` (unwind), or `POST /halt` (freeze).

## Honesty box

- **Economics:**
  - ETH funding on HL ran 22% in 2024, 8.5% in 2025 and 5.8% in 2026 so far;
    the last 30 days are ~10%.
  - At current funding, $30k earns about $2.5–3k/yr; on the trailing year,
    about $1.8k.
  - A round trip on both legs costs ~23 bp.
  - Since mid-2024 the edge over T-bills has been ~0 (RESEARCH_SHARPE.md).
    Against idle USDC, which earns nothing on HL, it is real.
- **Not modelled / risks:**
  - UETH is a bridged token (Unit, 2-of-3 MPC); a depeg is uncovered.
  - Spot-vs-perp basis has been ±15 bp typical, with rare wicks.
  - The short shares the USDC margin pool with the BTC book.
  - Funding can turn negative inside the 5–8% hold band.
  - IOC slippage cap: with no liquidity inside ±15 bp, a leg simply doesn't
    fill that pass.
- **Not yet verified on the venue:**
  - whether the 4% referral discount applies to spot fees;
  - the exact cross-margin liquidation price for the ETH short alongside the
    BTC book (the guard reads the venue's own `liquidationPx`).
