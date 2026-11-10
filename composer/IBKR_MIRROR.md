# IBKR mirror of the Composer book

Status (2026-11-10): BUILT on the branch, NOT deployed, switched OFF by default.
No order has been sent. Reaching production is a merge to main (the owner's
call), then env vars on Render; the first stage after that is PAPER only.

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

Open, for the owner (see the end): sleeve weights at the start, the IBKR
account type, how fast engines go live, and the brain's hosting.

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

1. The executor reads the brain's clock (/mirror/session): decision bar 15:54
   ET (12:54 on a half-day), ending 15:55:00.
2. At 15:55:05 the pre-trade gates run. LIVE book: the account must hold
   exactly the book's shares and nothing else, the account's cash must cover
   the book's, the blend must be off. Any failure: no trade that session, with
   the reason.
3. The intents are read. They must be for today, computed after the decision
   bar closed, at most 90 seconds old, and not a replay. Otherwise the read is
   repeated every 3 seconds until 15:58:00, after which the session is a
   recorded NO TRADE.
4. The plan: daily sleeves go to target; the threshold sleeve (KMLM, 10pp)
   trades only when some asset sits further than the corridor from its target.
   Opposite legs across sleeves cross internally; only the net goes out.
5. LIVE: every symbol in the plan is checked against IBKR's own quote. Further
   than 1.5% from the brain's price (5% when the brain's price is an
   estimate), or only a previous-close quote: that symbol's sleeves sit the
   session out, the others trade.
6. Sells go first, as market DAY orders, each under an id written to disk
   before IBKR sees it. When they are booked, buys are sized from the cash
   actually received, never from expected proceeds.
7. 15:59:00: anything still working is cancelled and booked at what filled.
8. Afterwards the account is compared with the book. A mismatch seen twice,
   30 seconds apart, halts a live book.

## Controls

- POST /kill (existing): halts every mirror book; the LIVE book's positions
  are sold by the loop thread (at once in the regular session, else at the
  next open). POST /resume lifts it.
- POST /mirror/halt: stop trading, keep positions. POST /mirror/resume.
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

## Deploying the brain

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
        - key: MIRROR_API_TOKEN
          sync: false
        - key: FMP_API_KEY
          sync: false

It is NOT in render.yaml yet: adding it creates a billable service on the next
blueprint sync, which is the owner's decision. Because it redeploys when
fixtures/approved changes, an approved symphony change reaches the mirror the
same session it reaches main.

## One brain: what a change must do

- A symphony edited on Composer: the new tree passes the fidelity gate, the
  approved fixture is updated in the same change set, and the brain redeploys.
  Until then the two sides run different logic.
- A POLICY operation that moves capital between symphonies: the same amount
  through /mirror/transfer the same day.
- A gate or methodology change: it lives in the trees or in the shared
  evaluator, so it reaches both sides through the same fixture update.
- After any of these: the parity check (per engine, Composer's holdings versus
  the mirror's, and the day's returns) is run and reported before the change
  counts as done.

## What is NOT the same on the two sides (honesty box)

- Decision minute. The mirror decides on the 15:54 bar; Composer's own
  decision lands somewhere in 15:50-15:55. About one engine-day in twelve is
  close enough to flip.
- Composer skip days. On 10-26..10-28 Composer did not rebalance; the mirror
  would have.
- Fills. Market orders at about 15:55 on IBKR versus Composer's own execution.
- Whole shares, a 0.3% cash reserve per sleeve, and drift trims under
  max($25, 0.5% of the sleeve) are skipped.
- Dividends land in the IBKR account, not in a sleeve. They are attributed by
  hand through /mirror/credit until that is automated.
- Paper fills are at the brain's price: the paper record measures decisions
  and holdings, not execution cost.
