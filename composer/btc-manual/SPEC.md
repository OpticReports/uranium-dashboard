# BTC MA Strategy — Specification Questionnaire

Purpose: turn the manually-traded setup into an exact, testable specification.
Fill every field. Where a rule doesn't exist ("we eyeball it"), write
**DISCRETIONARY** — do not invent a rule that wasn't used. Honest
"discretionary" answers are more valuable than tidy fake rules: they tell us
what can be automated and what can't.

Companion file: `trade_log_template.csv` — the historical trade log schema.
Both go back to the analyst (Claude) for audit → formalization → replay
backtest → verdict.

---

## 1. Instrument & venue

- 1.1 Exact instrument traded (BTC spot? perpetual futures? which pair):
- 1.2 Venue(s) and account type:
- 1.3 Leverage used (range, typical):
- 1.4 Typical position size ($ or % of trading capital):
- 1.5 Fee tier actually paid (maker/taker, bps) + typical funding paid if perps:
- 1.6 Hours traded (24/7? specific sessions? alerts-driven?):

## 2. Charts & indicators (exact definitions)

- 2.1 MA type per use: SMA / EMA / other (specify per length if mixed):
- 2.2 The full MA set — for EACH timeframe (1h / 4h / 12h / 1d / 1w), list
      the exact lengths used (e.g., 1h: EMA21, EMA50; 4h: EMA200; 1d: SMA50,
      SMA200; 1w: SMA20):
- 2.3 Which chart timeframe is the EXECUTION chart (where entries are pulled
      the trigger on)?
- 2.4 Are higher-timeframe MAs drawn on the execution chart, or checked on
      their own charts?
- 2.5 Any non-MA indicators involved (RSI, volume, VWAP, funding, OI…)? Exact
      settings and role (filter? trigger? confirmation?):
- 2.6 Candle basis: close-of-candle decisions or intra-candle (wick touches)?

## 3. Setup taxonomy

List every DISTINCT setup you trade. Copy the block per setup. Name them —
these names must match the `setup_type` column in the trade log.

For each setup:
- 3.1 Name (e.g., "4h-200EMA bounce", "1d-50MA breakout-retest"):
- 3.2 Direction (long / short / both):
- 3.3 Trigger — the exact condition that makes it a valid entry (touch within
      X% of the MA? candle close back above? N-candle confirmation? wick
      rejection shape?):
- 3.4 Confluence requirements — what ELSE must be true (e.g., "only long if
      price > 1d 200MA", "weekly MA rising", "RSI not overbought"):
- 3.5 Invalidations — what kills the setup before entry:
- 3.6 How often does this setup appear (per week/month, roughly):
- 3.7 Team's belief about when it works vs fails (trend vs chop, etc.):

## 4. Entry mechanics

- 4.1 Order type (limit resting at the MA? market after confirmation? stop
      order above breakout level?):
- 4.2 Entry price rule (at MA? at candle close? at retest of level?):
- 4.3 Scaling in (all at once / tranches — exact rule):
- 4.4 Max concurrent positions / max total exposure:

## 5. Exit mechanics

- 5.1 Initial stop placement — exact rule (X% below MA? below swing low?
      ATR-based? fixed $):
- 5.2 Profit target — exact rule (next MA up? fixed R multiple? fixed %?
      prior high?):
- 5.3 Trailing rule if any (trail behind which MA/structure, updated when?):
- 5.4 Partial exits (levels, fractions):
- 5.5 Time stop (exit after N hours/candles if nothing happens?):
- 5.6 Manual overrides — under what circumstances does the team exit outside
      the rules? (news, feel, drawdown). Estimate what fraction of exits were
      overrides: ___%

## 6. Risk & sizing

- 6.1 Risk per trade (% of capital at stop):
- 6.2 Sizing formula (fixed $, fixed risk, conviction-scaled — exact):
- 6.3 Daily/weekly loss limits and what happens at the limit:
- 6.4 Correlation rule (do you reduce size when several setups fire at once?):

## 7. Discretion audit — the most important section

- 7.1 Of 10 typical entries, how many followed the written rules exactly
      vs involved judgment (chart context, "looks weak", news)?  ___/10
- 7.2 What information does the trader use that is NOT in sections 2–5
      (order-book, funding, Twitter/news, session time, "feel")? List all:
- 7.3 Are there setups that LOOK valid by the rules that the team routinely
      skips? What distinguishes the skipped ones?
- 7.4 Who traded it (one person or several)? Did results differ by person?
- 7.5 Was the approach ever changed mid-history (new rules, new MA set,
      post-loss adjustments)? Date the changes.

## 8. Track record context

- 8.1 Period traded (start date → end date, any gaps and why):
- 8.2 Starting and current trading capital (for the log's PnL to be checked
      against — account statements or exchange export strongly preferred
      over hand-kept logs):
- 8.3 Are ALL trades in the log — including losers, fat-fingers, and
      abandoned experiments? (Survivorship in the log is the #1 reason
      manual records don't replicate.)
- 8.4 Rough self-assessment: net P&L over the period, worst drawdown, and
      the single worst losing streak.

---

## What happens with this

1. **Audit** — trade-log statistics: expectancy, R-distribution, win rate by
   setup/timeframe/regime, fee+funding drag, comparison vs buy-and-hold over
   the same period, and consistency checks against account statements.
2. **Formalization** — sections 2–6 become code; section 7 tells us which
   trades the code should and shouldn't reproduce.
3. **Replay** — the coded rules run on historical hourly/4h data over the
   same period; its trades are matched against the log. High match + positive
   expectancy = automatable edge. Low match = the edge (if any) is the
   trader's discretion, not the rules — different conclusion, still useful.
4. **Verdict** — automate (with venue/sizing plan), keep manual (with better
   logging), or retire, based on what the data supports.
