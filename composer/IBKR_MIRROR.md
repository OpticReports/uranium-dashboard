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
   On a half-day (12:54:00, a 13:00 close: 12:54:25 to act, 12:59:00 to
   cancel) FMP can stop carrying VOLUME after 12:45 while it keeps publishing
   the bars (its archive of all three 2025 half-days; SPY itself on
   2025-11-28), which the dead-feed rules refused on two of the three
   (12-24 passed by one ticker). There, and only there, a ticker with a bar
   without volume in the two minutes to the instant counts as trading when
   its own last trade is at most 15 minutes old, the price being that
   trade's, and one of its bars without volume since moved off that price.
   For the book that is all "frozen" means: every bar without volume since
   the ticker's last trade closed at that trade's own price. A feed stuck at
   another price (a tick off, a half-cent) is counted; what bounds it is the
   floor below and the 15-minute age. SPY's decision bar counts the same way
   with a stricter rule, because it is the decision bar: when SPY's last
   trade is more than two minutes old, its bars without volume since must
   also close at two or more prices, and not three or more in a row at one
   price up to the instant (2025-11-28, the one real day SPY leaned, its
   trade 8 minutes old: 8 prices in 8 bars). A SPY trade within those two
   minutes (FMP's volume gone from SPY's last one or two bars; a trade
   ending exactly two minutes before the instant included) needs no such
   evidence: it is what the full-day rule and the floor count as really
   trading, SPY is priced at it, and one or two closes cannot show a live
   feed (on real SPY minutes the stricter tests refused 99.9% of the
   one-bar instants and 4% of the two-bar ones; "moved" alone 4% of the
   one-bar ones). Let through by design, bounded by the 15-minute age (SPY
   priced at its own last trade) and the floor: SPY frozen at one price but
   for one bar among the last three, and two stale prices alternating
   (mirror_brain.spy_frozen). The executor accepts
   SPY priced before the instant only on an early close by its own calendar
   that the payload's close_et and the brain's clock also give. All of it
   only while at least half the trees' tickers really traded in those two
   minutes (77%, 75% and 81% on 2025's three); that floor is the book's, not
   each engine's (recorded, not built: at the floor an engine can be decided
   with none of its own decision tickers really trading). Each ticker counted
   so is named in the payload's `problems`, and its breadth gives the real
   trades and these apart; no bars, older trades, bars frozen at the last
   trade's price (SPY: or failing its stricter rule), or too few real trades
   are refused as on a full day (mirror_brain.py's docstring;
   tests/test_mirror_halfday.py on both sides). Below the floor the brain has
   read the whole book: its "not yet" is held 10 s like any other (not
   re-read on every 3-second request), and says "FMP has not answered for
   ..." when unanswered tickers are why.
   Known, not built: a session's close counts as final only from 16:15 ET
   (shadow_runner.FINAL_AFTER), on a half-day too, so a parity check or a
   paper-book run made by hand between 13:15 and 16:15 on one still reads
   the session before; the scheduled 16:35 ET runs are unaffected.
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
  unresolved. The venue is asked once more and its own answer wins (while it
  cannot be asked nothing is booked: the request stays queued); a price
  above the order's limit or far from its reference is refused, and so is a
  commission above max($5, 1% of the trade) without "force": true.
- POST /mirror/adjust {sleeve, symbol, shares, cash, note}: a signed
  correction of one sleeve, for a divergence nothing else explains. One that
  would put the sleeve in debt needs "force": true.
- A flatten runs for up to 30 minutes of open session (counted between its
  rounds, not while an order is working) and never reports complete while
  the account still holds stock. Every flatten sell is checked against the
  account's positions as it is sent: it is cut to what the account holds and
  not sent at all when that is nothing or cannot be read.
- POST /mirror/transfer {from, to, amount}: capital between two sleeves, with
  the next session's plan. The POLICY operations that move money between
  symphonies on Composer land here the same day: the daily routine sends
  them with composer/scripts/mirror_transfer.py under the transfer-only
  MIRROR_TRANSFER_TOKEN (header X-Transfer-Token), which opens this route
  alone, is capped at MIRROR_TRANSFER_MAX_FRAC of the book's equity and 6
  requests per cap period (until the ET date has changed AND the book has
  run a session since AND no transfer sent with the token is still waiting
  to be applied: a weekend is one allowance), takes nothing below $1
  and is alerted on every use; EXEC_TOKEN still works here, uncapped.
- POST /mirror/credit {sleeve, amount}: a dividend the account received for a
  sleeve's shares (or a fee, negative). A live book takes it only from cash
  the account really holds beyond the book, and - without "force": true -
  only while seeds plus credits stay within MIRROR_MAX_BOOK_USD (unset:
  MIRROR_CAPITAL_USD, so on a fully seeded book every credit needs the cap
  raised or force). Every credit a live book takes is alerted.
- Live only: seeding never totals more than MIRROR_CAPITAL_USD; the buys of a
  session are not sent while the book's cash exceeds what the account is
  shown to hold by more than $1, or while the account's cash cannot be read.
  "Shown to hold": IB's TotalCashValue, except while it still reads what it
  read before the session's sells - IB's update lag (sent on a position
  change, otherwise every 3 minutes), not a fact about the account - AND the
  account's positions, read again before the buys, are exactly what it held
  at the pre-trade check less the shares the sells were booked at. Then it is
  that reading plus what the sells executed (a commission IB has not reported
  yet counted at 1.1% of the fill + $10; a sell with no reported price, or one
  booked by /mirror/resolve, at nothing until TotalCashValue shows it). That
  commission bound assumes IBKR's per-order maximum (1% of the trade plus the
  fees passed through): it may not hold for a large order of a name under
  about $3.40 a share, and does not on another pricing plan. When the
  positions differ - a sale booked that never executed, an execution counted
  twice, a trade by hand IB has reported - or cannot be read: TotalCashValue
  alone, the rule before. A TotalCashValue that has moved but shows only some
  of the sells (an IB update landing between them) gets the rule before too:
  on a day the sells it does not show yet exceed the cash outside the book,
  the buys wait for IB's next update. (IB reports a corrected execution as
  one more execution whose execId differs only after the last period; the
  adapter keeps the latest correction alone and logs each correction it sees
  once, raw, at WARNING.) Positions come on IB's position subscription, not
  on the 3-minute cycle. While TotalCashValue lags, on a day the sells exceed
  the cash outside the book, the buys wait as long as the positions trail the
  fills, rounded up to the next 1.5 s poll; beyond the window, the rule
  before (measured in simulation: 5 / 30 / 120 s behind cost 6 / 30 / 120 s).
  On any other day TotalCashValue alone covers the book and the buys go at
  the first look. How far the positions trail is unverified on the live
  gateway. The run's buy_cash.positions_confirmed_after_s records it - the
  seconds from the last sell's booking, to the second, to the first look at
  which the positions agree: an upper bound on how far they trailed that
  booking, to a 1.5 s step - only when TotalCashValue had not yet moved at
  that look (None otherwise, nothing logged); it is also logged at INFO,
  since the run record is dropped when the run ends. Such a hold is alerted
  as a warning ("not yet confirmed by the account's positions; re-read every
  step": IB's lag, or a real difference) and in red only once it has lasted
  10 s; a disagreement reading the positions again is not expected to change
  (no record of them from before the run, a record of them that cannot be
  read, a holding that is not a whole stock lot) in red at once, and no
  warning follows a red this process already sent (after a restart the new
  process warns once more, then its red comes). Keep at least 1.1% of a
  day's sells + $10 an order outside the book (about $1.3k on a $117k
  rotation): below that, a commission IB had not reported when its sell was
  booked holds a lagging day's buys. A live state file that holds shares
  while no live book is built is alerted in red at every boot.
- What the guard cannot see, and the operating rule. While TotalCashValue
  lags, three things move the account's cash with nothing the guard reads
  showing them, and the buys can then borrow beyond the account's cash
  outside the book: (1) cash leaving with no position moving - a withdrawal,
  a fee - as much as it exceeds that cash; (2) a trade by hand that IB has
  not yet reported as a position when the guard reads - a purchase, as much
  as its cost exceeds that cash; (3) a price correction of a sell after it
  was booked - up to its size beyond that cash. The 2026-11-13 safety review
  measured (1), (2) and, of (3), corrections of the price. For (1) and (2),
  the rule before this held such a day's buys until IB caught up only when
  the day's sells exceeded the cash outside the book. (3) is new with this
  guard: the rule before never borrowed on it (a correction is at most the
  day's sells), and it can happen only on a day the sells exceed the cash
  outside the book. A bust of a sell moves a position (its shares come back):
  it is closed once IB reports that position (the guard takes TotalCashValue
  alone; the post-trade check halts on the shares); before that it is (2)'s
  exposure - at most the day's sells, so, like (3), new with this guard and
  only on such a day. Nothing closes a bust before IB reports it, by the
  guard's first look (in the step the sells are booked): the operating rule
  covers withdrawals and trades by hand, not IB's busts. Operating rule, for
  (1) and (2): no withdrawal pending
  or posting, and no trade by hand, in the mirror's account on a session day
  until that session's run is done (the run: roughly 15:45-16:05 ET;
  12:45-13:05 on a half-day). When IBKR posts a withdrawal is not verified
  here: one asked for earlier in the day may post during the run. (A trade
  by hand moves a position once IB has reported its position: the guard then
  takes TotalCashValue alone and waits for it only on a day the sells exceed
  the cash outside the book; on any other day a purchase TotalCashValue does
  not yet show is (2)'s exposure, as under the rule before, and the
  post-trade check then halts the book.) Nothing closes (3): it needs a
  correction larger than the cash outside the book inside TotalCashValue's
  lag. The book never sees a correction after booking (the post-trade check
  compares shares, not cash): its cash stays over by it until it is debited
  with POST /mirror/credit, and the pre-trade gate refuses a session only
  once that over-count exceeds the cash outside the book.
- GET /mirror/feed (READ_TOKEN): the books, for the parity monitor.
- /status and /health carry a mirror block only when the mirror is enabled.

## A gateway session whose open orders cannot be read (K5)

Each new IB API session asks for its open orders at connect. Until that answer
has ended no open-orders read can be trusted (its late end would cut a later
request's list short), so nothing is sold or bought (a /kill flatten included)
while the positions and the cash are still read. Such a session is kept for
its late answer and replaced by a fresh one on a doubling schedule: 40 s after
the connect gave up on it, then 80, 160, 320, 640 s, capped at 15 min; it
starts over when a connect fails and when the outage ends. Two lost answers
met at the decision still trade before 15:58:00 (12:58:00 on a half-day). Past
30 min the outage pages once (DOWN: the cause, and how many fresh sessions
this outage tried), and its end is announced from its last cause: after an
unsynced spell, open orders were unreadable, positions and cash were read
(ibkr-executor/app/ib_adapter.py _unsynced_replace_interval;
ibkr-executor/tests/test_mirror_d1r5.py and test_mirror_d1r6.py).

Known, not built (measured on the simulated clock and on scripted gateways,
never on a real IB gateway):
- Late versus lost. The adapter cannot tell a lost answer from a late one
  before it drops a session, and the schedule takes it as lost, the failure
  actually observed. A gateway that answers EVERY new session's request a
  fixed time late, after a drop at the decision: up to ~95 s late it trades
  as before (the same sessions and instants as round 4); ~95-125 s late it
  trades ~95 s later, close to the 15:59:00 cancel (buys as late as
  15:58:59); ~125-220 s late it does not trade (round 4 kept the second
  session for good and traded); later than that neither does. More than ~15
  min late overnight the outage never closes (66 replacements, one DOWN
  page, the next decision not traded). Keeping both (a probe session on a
  second clientId before the kept one is dropped) is not built. Pinned by
  ibkr-executor/tests/test_mirror_d1r6.py.
- A failed connect restarts the schedule. If a real gateway refuses an
  immediate same-clientId reconnect (IB error 326), the interval never
  doubles past 40 s: measured ~12 connect attempts and 6 sessions an hour
  idle, ~72 attempts and 36 sessions an hour during a /kill flatten, bounded
  by the reconnect backoff (a 45 s minimum gap).
- The cap's cost: after a spell long enough to reach 900 s, a gateway that
  heals with no FIN is found up to ~15 min later. Three lost answers met at
  the decision do not trade (the 4th session is due ~325 s after decide_at);
  a /kill flatten sells after ~322 s with three lost, ~658 s with four.
- A gateway-only restart that accepts the next connect at once keeps the
  interval: the schedule does not restart on a gateway FIN.
- Considered, not built: the first step inside the decision window and
  during a flatten (it costs the late band from ~55 s), a reset on a gateway
  FIN, a ~1 s pause before the reconnect.
- The end notice follows the outage's last cause only: an unsynced page
  followed by a spell with no session at all (a refused reconnect included)
  ends with the plain words, and the converse ends with the unsynced ones.
- Pre-existing: a session lost to an outage inside the window ends with an
  info-level "traded" summary (sold 0/N ...); the loud lines are the
  per-order red "NOT sent" alerts.
- The /kill alert, measured with the live and dry books and the blend's
  notes over every branch it words (3,456, each write failing as on a full
  disk): 3,615 characters at most against alerts.send's 4,000 cut (2,032 with
  nothing failing; 1,382 with the live book alone and the blend off). It can
  pass the cut only when the exception texts it quotes average more than 206
  characters (a full disk's is 70); its last line, the resume instruction,
  is then what is cut first.

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

1. POST /kill: the blend halts and sells its SLEEVE positions only. Its SPY core and
   its BIL sweep are NOT sold by /kill (seen live 2026-11-11: five sleeve names
   sold, SPY 108 and BIL 178 left): sell those two by hand at IBKR.
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

## Scaling the live book

The live book starts at $10,000 (owner decision 7) and is scaled up by one
cash credit per sleeve, at Composer's split. The owner's gates before it is
scaled (11-12), all three met first:

1. The IB connection fix is live on the executor.
2. At least two clean sessions on it: no halt, no unresolved order, no
   account-versus-book problem, every sleeve traded or held by its rule.
3. A real sell-then-buy rotation filled on the live book and matched
   Composer's holdings that day.

The plan comes from `python3 composer/scripts/mirror_scale.py --to 50000`
(`--json` for the same plan as JSON). It is read-only: it reads Composer's
split from the monitor's last snapshot (the four engines' values; unallocated
cash left out; a snapshot more than 3 days old is warned about) and the live
book from the executor's feed, sends nothing and holds no exec token. Per
engine: target = round(to x Composer weight, 2), credit = round(target - the
sleeve's equity, 2). It refuses, on one line starting "MIRROR SCALE REFUSED",
while the book is halted or has an open run, an unresolved order, an error, a
queued request (a POLICY transfer included: scale on another day) or a sleeve
missing or frozen; unless the account's post-trade check of the book's last
session was made, is done and found no problem (the executor clears that
check at the end of every run and on /mirror/adjust: re-run the planner after
the next session's check); on a session day from its paste cutoff (15:00 ET,
12:00 on a half-day) while that day's session has not run yet ("today's
session has not run yet: re-run after it and its post-trade check (if the
executor missed today's session, re-run after midnight ET)": a line printed
then would be for the next session, and today's, run in between, would void
it); when --to is not above the book or is more than 10x it; when
an engine is already above its Composer share at that size (it names the
smallest --to at which none is, or says it is beyond 10x); and when a dollar
figure on the feed is not finite or is beyond $1,000,000,000 (a malformed
feed). The plan is for ONE session: the first after the book's last that it
can still be pasted for, and the line expires with it. The credits are fixed
dollars: the book lands at the size asked plus whatever its current holdings
move before that session, less that session's commissions. Then, in order:

(a) The cap. The executor refuses a credit that takes the live book's
    funded_usd (its seeds plus every positive credit and what /mirror/adjust
    added) above MIRROR_MAX_BOOK_USD + $1, credit by credit, smallest first
    (mirror.py _over_cap, _apply_credits). The plan prints the value to set:
    (funded + the credits) x 1.05, rounded up to the next $500 - $53,000 for
    $10,000 -> $50,000. The feed does not publish funded_usd; the plan
    estimates it from the seeds and the credits in the feed's session rows,
    and the line in (b) checks the executor's own figure. Render ->
    ibkr-executor -> Environment: MIRROR_MAX_BOOK_USD = the cap, "Save,
    rebuild and deploy", never between 15:15 and 16:05 ET (12:15-13:05 on a
    half-day). Change only MIRROR_MAX_BOOK_USD in that deploy, not
    MIRROR_LIVE_ENGINES: a sleeve it drops stays in the book's state, not
    frozen, until the executor's first tick with the IB gateway logged in
    (mirror.py _reconcile_sleeves), so a line pasted before then queues only
    the credits before that sleeve in the line's order (HG, KMLM, SLEEVE,
    HARV) and stops there; the ones after it are not sent. The restart logs
    the IB gateway in again: approve the IB Key push.
(b) The credits. When the executor is back, paste the plan's ONE line into
    Render -> ibkr-executor -> Shell, once, before 15:00 ET on a weekday
    (12:00 on a half-day) or any time on a weekend, and by the cutoff of the
    plan's session (the plan prints it): the credits must be queued before
    the session that applies them, so the evening POLICY routine never sizes
    a transfer on pre-credit equity. The line is plain python3 and the
    standard library only (`python3 -c 'exec("""...""")'`, one line). It
    reads EXEC_TOKEN inside the container and sends it ONLY to the executor
    in that same container, http://127.0.0.1:$PORT/mirror/credit (PORT as
    start.sh's uvicorn reads it, 8000 when unset; http.client: no proxy, no
    redirect followed): the token never leaves the container, and never
    appears on screen or in the repo. It sends NOTHING - one line starting
    "NOTHING SENT", exit 1 - when EXEC_TOKEN is not there or is not printable
    ASCII (it is never printed), or the book's state file is not there;
    outside the hours above, the reason said; after the plan's session
    cutoff, or once the book has run a session since the plan (re-run the
    planner); when any request is queued, whatever its kind (its inbox, read
    first, and the state's requests, each listed: a second paste sends
    nothing); while the book is halted or a flatten is pending (its halt
    file), a run is open, or a sleeve it credits is frozen or no longer in the
    book; unless the account's post-trade check of the plan's last session is
    still on record, done and clean (an applied /mirror/adjust clears it:
    re-run the planner after the next session's check); when
    MIRROR_MAX_BOOK_USD there is not a number above 0 (the executor would then
    cap the book at MIRROR_CAPITAL_USD and refuse the credits); or unless that
    cap covers the book's own funded_usd (its state file) plus the credits to
    the cent - no $1 slack. Then it POSTs {"sleeve", "amount", "note", "book"}
    per engine with the header X-Exec-Token and prints each answer. At the
    first error or answer that is not 200 it STOPS at once - "STOPPED:
    <sleeve> <reason>", exit 2 - naming the credits answered 200 above it
    (queued), which were not sent, and whether the one that failed was NOT
    queued (an HTTP 4xx: the executor's /mirror/credit refuses before it
    queues; or nothing listening on PORT) or may have been queued all the
    same (any other failure). Nothing queued at all: fix the cause and paste
    the line again. Otherwise whatever was queued applies at the next session
    and cannot be withdrawn: after that session, re-run the planner and paste
    its new line. An error is printed as its type and message with the token
    masked. The note reads "scale-up to $<to> at Composer's split of
    <snapshot date>". Re-run the planner after ANY /mirror/adjust and paste
    only its new line: an adjust on the evening of the plan's last session is
    followed by that evening's tick making that session's post-trade check
    again - clean when the shares are as booked (it compares shares, not
    cash) - so an older line would still send, its credits sized on the book
    before the adjust.
(c) The executor applies them at that session's decision (15:54 ET, 12:54
    on a half-day): first the dividends due, then the credits, smallest
    first, each only if the account's cash (IBKR's TotalCashValue) covers
    the book's cash plus it, within $1, and the cap holds. The plan prints
    the account's minimum - the book's cash + the dividends due by that
    session + the credits + a margin of max($100, 0.5% of the credits);
    check it at IBKR before (b). Short by even $1 of the first three, the
    executor refuses the LARGEST credit whole and the book trades mis-split
    until a new plan lands. The same plan invests them: the daily sleeves go
    to target, and KMLM trades too (idle cash above 5% of a threshold sleeve
    overrides its corridor). Every credit taken is alerted. A refused credit
    is alerted in red and dropped, NOT retried: fix the cause, re-run the
    planner and paste its new line.
(d) That night's parity check against Composer (mirror_parity.py) removes
    the operator credits from that day's return, so the scale-up day is not
    read as a gain: chained through the session's fills when the sleeve's
    credit went in whole (its buys filled, its cash after the session at most
    5% of it, no buy of the session short), at face value when none of its
    buys filled. A credit only partly invested gets no day-return comparison
    that day ("the credited cash was only partly invested": neither reading
    is right then); the holdings still are compared. A POLICY transfer leg
    (mirror_transfer.py) is refused while operator credits are queued for
    either of its sleeves: it is sized after the session applies them. A leg
    below $1 even once they are applied is below $1 at the mirror's size:
    nothing is sent, exit 0.

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

The half-day rule (2026-11-13: round 4 and its round-5 and round-6 fixes):
redeploy composer-brain and ibkr-executor TOGETHER, and before Fri
2026-11-27, the next half-day.
The executor's own half-day check is about the calendar and SPY's time only
(mirror.py _validate); the frozen-feed and real-trade floors live in the
brain. A patched executor with the earlier brain accepts what that brain
still publishes on a half-day with no trade after 12:40 (prices moving) or
with a frozen tail, and trades it: a review measured both traded.

After the merge, in the Render dashboard (values are typed there, never in
the repo or a chat):
- composer-brain: MIRROR_API_TOKEN (any long random string), MIRROR_ATTEST_TOKEN
  (a different one), FMP_API_KEY.
- ibkr-executor, to start the PAPER book: MIRROR_ENABLED=true,
  MIRROR_BRAIN_URL=https://<the brain's onrender.com host>,
  MIRROR_API_TOKEN (the same value as the brain's), MIRROR_CAPITAL_USD=118000,
  and MIRROR_WEIGHTS if not the policy split. MIRROR_LIVE_ENGINES stays unset.
- ibkr-executor, for the POLICY routine's mirror leg: MIRROR_TRANSFER_TOKEN (a long random string of its own, at least 24 characters, never EXEC_TOKEN or READ_TOKEN). The routine side holds the same value as a NETWORK SECRET on the cloud environment (set 2026-11-12: host ibkr-executor.onrender.com, header X-Transfer-Token, no prefix), never as an environment variable: the platform adds it to requests to that host and replaces a stand-in, so the routine runs `MIRROR_TRANSFER_TOKEN=via-network-secret python3 composer/scripts/mirror_transfer.py ...` and the real value is never readable in a session. Verified 2026-11-12 with a request naming no book: "refused: not a valid transfer" (the password passed; nothing queued) with no header and with a stand-in. And optionally MIRROR_TRANSFER_MAX_FRAC (default 0.25 of the book's equity per cap period: until the next session on a later ET date).
- ibkr-executor, optional: MIRROR_MAX_BOOK_USD - the cap on a live book's seeded-plus-credited capital (unset or 0 = MIRROR_CAPITAL_USD); a /mirror/credit above it is refused without "force": true.

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
