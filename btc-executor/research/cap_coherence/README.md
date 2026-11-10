# MAX_NOTIONAL_USD never moved with SIZING_BASE_USD

`SIZING_BASE_USD` went 1,000 → 25,000 on 2026-09-09. `MAX_NOTIONAL_USD` is
still 2,000, the value chosen for the old base. Both are `sync:false` and set
by hand in the Render dashboard, and until this commit nothing compared them.

**How the cap was identified — from the venue, not from config.** The
2026-09-09 16:00:37 pullback entry filled 0.02481 BTC at 78,557. The sizing
formula predicts 0.135 × 1.5 × 0.75 × 25,000 / 78,557 = 0.04833. Solving
`_leg_qty`'s clamp for the binding cap:

```
room = cap/px - other          other = 0.00064 (the open trend leg, old size)
2000/78557 - 0.00064 = 0.024819    actual fill 0.02481
```

Exact to five decimals. Nothing else in the range fits.

## Consequences

| | before (base 1,000) | now (base 25,000) |
|---|---|---|
| pullback leg wanted | $152 | $3,797 |
| cap allowed | $152 | **$1,950** |
| daily-loss line (6% of base) | $60 | $1,500 |
| drawdown line (35% of base) | $350 | $8,750 |
| most the caps can lose | $2,000 | $2,000 |

Two things follow, and they differ in how strongly they can be stated:

1. **Sizing is running at about half of intent.** The Kelly scale-up is only
   partly in effect, and a rate-limited `cap_clamp` RED has been firing.
2. **The drawdown line is out of reach of any single position.** $8,750 is
   4.4x the largest position the caps permit, so a total loss of that position
   would not fire it. This does **not** mean the breaker can never fire —
   drawdown accrues across trades, so enough consecutive losers still reach it.
   The daily line, at 0.75x, is still reachable in one position.

## Honesty box

- The cap value is **inferred** from one live fill plus `_leg_qty`'s arithmetic,
  not read from the Render dashboard. It fits to five decimals and no other
  round value fits, but it has not been confirmed against the env directly.
- The "total losses of a max position" framing deliberately avoids any
  assumption about stop distance, trade frequency or win rate. A tighter guard
  (`> 0.5 × cap`, phrased as "% adverse move to fire") was written first and
  **rejected**: it fired on a config the existing coherence test calls sound,
  and the single-move framing was wrong because drawdown is cumulative.
- The pre-existing coherence guard compares the drawdown line to the **account**
  and cannot see this; it did not fire, correctly, because $8,750 is not more
  than 80% of a ~$100k account.
- Not modelled: leverage-driven liquidation, gap risk beyond the stop, and the
  effect of the cap being **account-wide** — as the trend leg grows it squeezes
  the pullback leg further, which is why `other` appears in the arithmetic.

## The decision is Casey's

Both vars are `sync:false`; neither is settable from here. Either raise
`MAX_NOTIONAL_USD` so sizing matches intent and the halt lines come back into
range, or lower `SIZING_BASE_USD` so the halts match the exposure that is
actually permitted. They have to move together — `render.yaml`'s own comment
already says so ("RAISING THE BASE INSTEAD WOULD HAVE DISARMED A HALT").
