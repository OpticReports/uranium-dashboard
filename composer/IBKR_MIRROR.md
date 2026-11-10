# IBKR mirror of the Composer book

Status (2026-11-10): BUILT on the branch, NOT deployed, switched OFF by default.
No order has been sent. Reaching production is a merge to main (the owner's
call), then env vars on Render; the first stage after that is PAPER only.

Two independent reviews found the first build SHIP-BLOCKED. Their findings were
fixed; a second round by three independent verifiers found the blocking fixes
hold and read PAPER clean, LIVE fix-then-ship; that round's findings are fixed
too. This document describes the code after both rounds. What is still owed
before any engine trades real money is listed under "Before live". Reports:
research/mirror/reviews/. Numbers: results/results.md addendum 55.

## Owner decisions (Casey, 2026-11-10)

1. Capital: the ~$118,000 in the IBKR account.
2. Composer is not changed at all. It keeps trading as it does now; the mirror
   copies it. The owner has accepted that the same leveraged engines are then
   held twice.
3. The mirror REPLACES the strategy the IBKR account runs today (blend3070:
   SPY core + genomics sleeve). The two never trade the same account at the
   same time (see Cutover).
4. One brain: every change from a thesis, test or report to a symphony, gate,
   POLICY operation or the methodology reaches both sides in the same change
   set, with a parity check (CLAUDE.md "ONE BRAIN, TWO BROKERS").

5. (11-10, after the review rounds) blend3070 IS retired at cutover. The brain
   gets its own small Render service (composer-brain in render.yaml): the
   decision brain stays out of the process that holds the broker session, and
   the executor's image does not contain composer/. The branch may be merged
   to main; the merge is made after 16:00 ET, because it redeploys the live
   executor and that restart needs an IB Key approval with the gateway idle.

6. (11-10) The IBKR account was a CASH account and was converted to MARGIN the
   same day (owner). Sale proceeds are therefore available for the same
   minute's buy; see "The cash account" below for why that mattered and what
   margin removes.

7. (11-10) The test is done with REAL money at a small size, not with weeks of
   paper: MIRROR_CAPITAL_USD=10000 across all four engines, checked daily
   against Composer, then scaled up by a cash credit to each sleeve. This
   replaces the ten-paper-session stage by the owner's decision. Kept from the
   staged rollout: the independent review of the round-2 fixes reads clean
   first; one paper session on the executor before the first real order (the
   live chain has never run at a real 15:54); blend3070 is flattened and
   switched off before the mirror's live book is armed; the tree attestation
   is armed (a live sleeve does not trade without it). Known distortions at
   this size: IBKR's per-order minimum commission and whole-share rounding on
   sleeves of $1,200-$3,400, so the test measures plumbing and execution, not
   return. On a margin account $10k is the book's limit, not IBKR's.

8. (11-10 evening) blend3070 is sold and switched off on Wed 11-11 REGARDLESS
   of whether the mirror goes live that day (owner: "yes sell all tmr
   regardless"). The mirror's real-money start is the same day at 15:54 ET
   only if the replacement round-3 executor review is clean and the 15:15
   attestation ran; otherwise the account sits in cash and it starts 11-12.
   /kill also halts the mirror's books: lift that with POST /mirror/resume,
   never /resume (which would lift the blend's halt).

Starting weights: Composer's live split on the day (default, see below).

Recommendation on the weights: seed at Composer's live split on the cutover
day (11-09: HG 34.3 / KMLM 26.8 / SLEEVE 26.5 / HARV 12.4), not at the policy
targets (29/29/27/15). The purpose of the mirror is that the two books move
together; with the same mix the book-level returns are comparable day by day,
and every POLICY transfer on Composer is then mirrored by the same share of
the book. Engine-level parity does not depend on the choice.

## Evidence that the logic copies

The shadow runner (scripts/shadow_runner.py) re-evaluates the four approved
trees daily against Composer's actual holdings. 2026-07-15..2026-11-09, 308
engine-days: 272 same decision, 24 knife-edge (the call flips inside
15:50-15:55), 12 Composer no-rebalance days (all 10-26..10-28), 0 logic
disagreements. Exactness limit: about one engine-day in twelve sits on a
threshold and can land either way; on a Composer skip day the mirror follows
the logic and Composer does not.

## What is built

| Piece | File | Role |
|---|---|---|
| Brain (keyless) | composer/scripts/mirror_brain.py | Evaluates the approved trees (fixtures/approved) on live prices through the pre-close preview's own pipeline and publishes, per engine: target weights, tree version, Composer's rebalance rule (daily, or threshold with its corridor), how close the call is, and the prices it was evaluated on. Also the session clock: when the decision bar ends and when the session closes. Reads no broker and no Composer key. |
| Core (pure) | ibkr-executor/app/mirror_core.py | Virtual sleeves (cash + whole shares), the daily / threshold rule, one netted order per symbol across sleeves, internal crosses, sells booked before buys are sized from the cash actually there, each venue order booked exactly once. |
| Strategy | ibkr-executor/app/mirror.py | One book per instance: the session state machine, pre-trade gates, venue quote cross-check, write-ahead order ids, halt and flatten, the account-versus-book check, transfers and cash credits. |
| Service wiring | ibkr-executor/app/service.py | Built only when MIRROR_ENABLED. One pass per loop iteration; /kill and /resume gain a mirror stage; /mirror/feed, /mirror/halt, /mirror/resume, /mirror/transfer, /mirror/credit. |
| Paper simulator | composer/scripts/mirror_dry.py | Replays history through the SAME core to measure parity against Composer's record before any money moves. |

Separation of powers holds: the brain is keyless; the only credentials are the
executor's existing IBKR session. The executor's adapter gained two read-only
methods (the account's positions; what an order executed) and nothing else.

## One session

1. The executor reads the brain's clock (/mirror/session). The decision
   instant is 15:54:00 ET (12:54:00 on a half-day): the end of the decision
   bar, the minute the shadow runner's calibration found closest to Composer's
   own decision (Composer submits its orders at a median 15:53:04).
2. In the morning the pre-trade gates run once, read-only, so a problem is
   known before the afternoon. At 15:54:25 they run for real. LIVE book: the
   account must hold exactly the book's shares and nothing else, the account's
   cash must cover the book's, the blend must be off. A permanent reason (the
   blend is on, no sleeve) skips the session at once; a transient one is
   retried until 15:58:00.
3. The intents are read with ?after=15:54:00. The brain answers with the
   decision AS OF that instant: prices only from 1-minute bars ending at or
   before it, the same answer whatever second it is computed, cached and never
   rebuilt once settled. It answers "not yet" until the decision minute is
   published (FMP takes 10-25 s) and while the feed is incomplete; from two
   minutes after the instant, if the market as a whole is priced, it settles
   with only the affected engines unavailable. The executor accepts only a
   pinned payload for today's instant with a complete decision bar. An engine
   is unavailable when the feed is dead, a ticker it decides on has no trade
   of its own, its data is short, or its tree is not the one Composer runs. A
   LIVE book additionally refuses any sleeve whose tree was not attested that
   day; a paper book trades it and says so.
4. Corporate actions first: a split rescales the sleeves' shares; a dividend
   becomes a receivable for the sleeves that held the payer at the close
   before the ex-date, credited from the pay date.
5. The plan: daily sleeves go to target; the threshold sleeve (KMLM, 10pp)
   trades only when some asset's invested weight sits further than the
   corridor from its target. Opposite legs across sleeves cross internally;
   only the net goes out.
6. LIVE: every symbol in the plan is checked against IBKR's own quote. Further
   than 1.5% from the brain's price (5% when the brain's price is an
   estimate), or only a previous-close quote: that symbol's sleeves sit the
   session out, the others trade.
7. Sells go first, as market DAY orders, each under an id written to disk
   before IBKR sees it. When they are booked, the buy symbols are quoted again
   and the buys go out as DAY LIMIT orders at quote x 1.005, sized at that
   limit from the cash actually received: a buy can never cost more than the
   cash set aside for it.
8. 15:59:00: anything still working is cancelled and booked at what filled. No
   new order is sent after that instant.
9. Afterwards the account is compared with the book. A mismatch seen twice,
   30 seconds apart, halts a live book.

A halt or /kill is re-read before every single order: one that lands mid-plan
stops everything not yet sent. An order whose fate the venue cannot prove is
never guessed at: it stays unresolved, says so daily, and the operator books
it with /mirror/resolve.

## Controls

- POST /kill (existing): halts every mirror book; the LIVE book's positions
  are sold by the loop thread (at once in the regular session, else at the
  next open), in up to five rounds until nothing the account holds is left.
  POST /resume lifts it and says which halt it lifted.
- POST /mirror/halt: stop trading, keep positions. POST /mirror/resume.
- POST /mirror/resolve {id, filled, price}: book an order the book has flagged
  unresolved. The venue is asked once more and its own answer wins; a price
  above the order's limit or far from its reference is refused.
- POST /mirror/adjust {sleeve, symbol, shares, cash, note}: a signed
  correction of one sleeve, for a divergence nothing else explains. One that
  would put the sleeve in debt needs "force": true.
- A flatten runs for up to 30 minutes of open session and never reports
  complete while the account still holds stock.
- POST /mirror/transfer {from, to, amount}: capital between two sleeves, with
  the next session's plan. The POLICY operations that move money between
  symphonies on Composer land here the same day.
- POST /mirror/credit {sleeve, amount}: a dividend the account received for a
  sleeve's shares (or a fee, negative). A live book takes it only from cash
  the account really holds beyond the book.
- GET /mirror/feed (READ_TOKEN): the books, for the parity monitor.
- /status and /health carry a mirror block only when the mirror is enabled.

## Rollout (executor law: staged, one step at a time)

| Stage | Settings | What happens |
|---|---|---|
| 0 Off | MIRROR_ENABLED unset | The service is exactly what it was. |
| 1 Paper | MIRROR_ENABLED=true, MIRROR_BRAIN_URL, MIRROR_API_TOKEN, MIRROR_CAPITAL_USD=118000 | All four engines in a paper book inside the live service: real decisions and timing, fills at the brain's price, no order and no account read. blend3070 keeps trading. At least ten sessions, compared with Composer daily. |
| 2 Cutover | see below | blend3070 retired; the account is all cash. |
| 3 Live, staged | MIRROR_LIVE_ENGINES=HARV, then more | Named engines trade for real; the rest stay on paper. |

An engine is live only when it is named in MIRROR_LIVE_ENGINES AND the service
itself trades for real (TWS credentials, DRY_RUN=false).

## Cutover from blend3070 (owner actions, in this order)

The two strategies cannot share the account: the blend reconciles the
account's positions and cash against its own book every cycle, and the mirror
requires the account to hold exactly its book. So:

1. POST /kill: the blend flattens its SPY core and sleeve (and halts).
2. Set BLEND_ENABLED=false on Render. Archive the blend's state file, or the
   service will alert about a real book on disk.
3. Confirm the account is all cash (/status, IBKR).
4. Set MIRROR_LIVE_ENGINES. The live book seeds each named sleeve from the
   account's cash and trades at that day's decision.

Until step 4 the mirror's live book refuses to trade, by design.

## The cash account

A rotation sells one fund and buys another in the same minute, so the buy is
paid for with sale proceeds that settle the next business day (T+1).

- A MARGIN account makes sale proceeds available for trading at once (IBKR's
  own statement). The mirror would still never borrow: buys are limit orders
  sized to the cash the book holds.
- A CASH account: IBKR's own pages disagree. One says a cash account has no
  access to sale proceeds until settlement; another says they may fund a
  purchase as long as the new position is held until the first sale settles
  (selling it sooner is "free riding"); a third says the settled-cash check is
  made when the order is entered. On THIS account the existing strategy
  recorded market buys sized near available cash coming back refused within a
  second, lists "unsettled same-day proceeds" among the causes it does not
  cover, and was built to spend settled cash only.
- If IBKR refuses a buy funded by the same minute's sale, the sleeve sits in
  cash until the next session: every rotation loses a day, on exactly the days
  the strategy is changing its mind. The mirror books the refusal and does not
  borrow or retry; nothing breaks, but the two books stop matching.

Recommendation: ask IBKR to change the account to a margin (Reg T) account
before any engine is live. Two things change with it and should be accepted
knowingly: a cash account cannot be overdrawn or sold short by mistake, a
margin account can, so the mirror's own guards (limit buys sized to cash, the
flatten ceiling, the account-versus-book check) carry that alone; and the
existing strategy's settled-cash assumptions stop binding. If the account
stays a cash account, the first live engine is the test: one rotation shows
whether IBKR accepts the buy.

## Before live (gates, in order)

1. Owner: confirm blend3070 is retired at cutover; the brain's hosting; the
   merge to main (it redeploys the live executor, mirror off).
2. Paper for at least ten sessions. The monitor already steps a paper book
   daily on the composer side (results/mirror/dry-ledger.jsonl, from 11-10);
   the executor's own paper book starts when MIRROR_ENABLED is set.
3. An independent review of the round-2 fixes and of the code as it then
   stands. Round 2 is verified by its authors only.
4. The account: MARGIN since 11-10 (owner). DONE as a gate. Still worth
   watching on the first live rotation: one limit buy sized near available
   cash accepted by IBKR. On a margin account the venue no longer refuses an
   overdraft or a short sale, so the mirror's own guards carry that alone.
5. The attestation armed: MIRROR_ATTEST_TOKEN on the brain, and
   scripts/mirror_attest.py run by the 15:15 preview routine (an attestation
   older than an hour before the decision does not count). A live sleeve does
   not trade without it.
6. Engines live one at a time. HARV is the smallest and the most
   minute-sensitive; SLEEVE never missed a session on paper.

## Deploying the brain

MIRROR_BRAIN_URL must be https: the executor never sends its token over plain
http except to localhost.

The brain needs a small always-on service: stdlib Python, no disk.

    - type: web
      name: composer-brain
      runtime: python
      plan: starter
      buildCommand: "true"
      startCommand: python composer/scripts/mirror_brain.py --serve
      healthCheckPath: /health
      autoDeploy: true
      buildFilter:
        paths:
          - composer/scripts/**
          - composer/fixtures/approved/**
      envVars:
        - key: MIRROR_API_TOKEN       # the executor's read token
          sync: false
        - key: MIRROR_ATTEST_TOKEN    # the Composer-keyed routine's write token
          sync: false
        - key: FMP_API_KEY            # required: the pinned decision needs minute bars
          sync: false

It is in render.yaml (owner, 11-10); the block above is its shape. Because it
redeploys when fixtures/approved changes, an approved symphony change reaches
the mirror the same session it reaches main.

After the merge, in the Render dashboard (values are typed there, never in
the repo or a chat):
- composer-brain: MIRROR_API_TOKEN (any long random string), MIRROR_ATTEST_TOKEN
  (a different one), FMP_API_KEY.
- ibkr-executor, to start the PAPER book: MIRROR_ENABLED=true,
  MIRROR_BRAIN_URL=https://<the brain's onrender.com host>,
  MIRROR_API_TOKEN (the same value as the brain's), MIRROR_CAPITAL_USD=118000,
  and MIRROR_WEIGHTS if not the policy split. MIRROR_LIVE_ENGINES stays unset.

## One brain: what a change must do

- A symphony edited on Composer: the new tree passes the fidelity gate, the
  approved fixture is updated in the same change set, and the brain redeploys.
  Until then that engine's sleeve HOLDS on the mirror: a routine with the
  Composer key (scripts/mirror_attest.py, about 15:50 ET) posts each
  symphony's live version and tree hash to the brain, and an engine whose
  approved tree does not hash equal is published unavailable, naming both
  versions. With no attestation at all the brain says so and trades the
  approved tree (set MIRROR_REQUIRE_ATTESTATION to make that a hold too). The
  brain itself never holds the Composer key.
- A POLICY operation that moves capital between symphonies: the same amount
  through /mirror/transfer the same day.
- A gate or methodology change: it lives in the trees or in the shared
  evaluator, so it reaches both sides through the same fixture update.
- After any of these: the parity check (per engine, Composer's holdings versus
  the mirror's, and the day's returns) is run and reported before the change
  counts as done.

## What is NOT the same on the two sides (honesty box)

- Decision instant. The mirror decides as of 15:54:00; Composer's own instant
  moves between 15:50:54 and 15:55:49 from day to day, so no fixed minute
  reproduces it. Replayed on 83 sessions the 15:54:00 decision equals
  Composer's holdings on 292 of 296 engine-sessions; expect 2-4% of
  engine-days to differ whatever minute is chosen.
- Composer skip days. On 10-26..10-28 Composer did not rebalance; the mirror
  would have. That stretch alone is about 3 points of return difference in the
  backfill, in Composer's favour that time.
- Commissions. IBKR charges per share; Composer charges nothing. Estimated
  $1,750-3,350 a year on $118k (1.5-2.8%), because the strategies turn the
  book over about 130-170 times a year. It cannot be removed, only chosen
  (tiered pricing) and accepted.
- Fills. Sells are market orders at about 15:54:40; buys are limit orders 0.5%
  above the quote, so on a fast up-move a buy can be left partly unfilled and
  the cash waits a day.
- Whole shares, a 0.1% cash reserve per sleeve, the 0.5% buy cushion, and
  drift trims under max($25, 0.5% of the sleeve) are skipped.
- Dividends follow Composer's own rule by default (MIRROR_DIVIDEND_RULE):
  credited to the sleeve from the pay date only if it still holds the payer,
  otherwise the cash stays unallocated in the account, as it does on Composer.
- A threshold sleeve seeded from cash buys the target while Composer may be
  sitting inside its corridor: on about one start day in five the holdings
  differ by 6-10% of the sleeve for 2-4 sessions, then never again.
- Paper fills are at the brain's price: the paper record measures decisions
  and holdings, not execution cost.
- The account is a CASH account. Whether IBKR lets it fund a buy from the same
  minute's sale proceeds is unverified (its own pages disagree) and decides
  whether a rotation completes the same day. Paper trading cannot show this.
