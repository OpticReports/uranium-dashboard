# IBKR mirror of the Composer book — design and decisions

Status (2026-11-10): DESIGN. Nothing built, nothing deployed, no order path.

## Owner decisions (Casey, 2026-11-10)

1. Capital: the mirror trades the ~$118,000 currently available in the IBKR
   account. The blend3070 book (SPY core + R2-A sleeve) is untouched.
2. Composer stays exactly as it is, trading in parallel: "I just want to run
   the same strategy since it's performing so much better." The owner has
   accepted that the same leveraged engines are then held twice.
3. One brain: every change from a thesis, test or report to a symphony, gate,
   POLICY operation or methodology must reach both sides, with a parity check
   that the two perform the same way (CLAUDE.md "ONE BRAIN, TWO BROKERS").

Working assumption until the owner says otherwise: the mirror uses the same
engine targets as the Composer book, HG 29 / KMLM 29 / SLEEVE 27 / HARV 15.

## Evidence that the logic copies

The shadow runner (scripts/shadow_runner.py) re-evaluates the four approved
trees daily against Composer's actual holdings. 2026-07-15..2026-11-09, 308
engine-days: 272 same decision, 24 knife-edge (the call flips inside
15:50-15:55), 12 Composer no-rebalance days (all 10-26..10-28), 0 logic
disagreements. Exactness limit: about one engine-day in twelve sits on a
threshold and can land either way; on Composer skip days the mirror would
follow the logic and Composer would not.

## Architecture (separation of powers: keyless brain, credentials only in executors)

1. SYNC. Composer remains the editor. Before each decision a sync reads each
   symphony's live version (the logic-drift check). A new version must pass a
   fidelity gate: every node supported by the evaluator, and the evaluator's
   replay of its backtest matching Composer's own day by day. Pass: the new
   tree becomes the approved fixture and the mirror uses it that session.
   Fail: that engine stays on its last approved version and the owner is
   alerted. The Composer key stays where it is today (the composer tooling);
   the brain never holds it.
2. BRAIN (keyless). Evaluates the approved trees at ~15:45 ET on live prices
   (FMP minute bars, Yahoo fallback; the preclose.py price path) and publishes
   per-engine target weights, tree version, knife-edge flags and each
   engine's rebalance rule over a read-only token-gated endpoint, the same
   contract shape the genomics tracker uses for blend3070's intents.
3. EXECUTOR (ibkr-executor, new strategy, MIRROR_ENABLED=false and
   DRY_RUN=true by default). Four virtual sleeves with their own capital and
   holdings; KMLM's 10pp threshold corridor and the daily rebalance of the
   other three; one netted set of market-on-close orders sent before the
   listing exchanges' auction cutoffs; fills booked per sleeve; kill switch
   scoped to the mirror's own positions; Telegram on every action.
4. PARITY MONITOR. Daily, per engine: Composer's holdings and day return vs
   the mirror's; alerts on any decision difference that is not a known
   knife-edge or Composer skip day, and on return drift beyond fills.
5. ROLLOUT (executor law). DRY for at least ten sessions with every intended
   order compared against what Composer did that day; PAPER; LIVE one engine
   at a time starting with HARV (smallest).

## Integration finding: the shared account (OPEN QUESTION for the owner)

blend3070 reconciles the IBKR account against its own book every cycle:
per-symbol held vs booked quantity, cash deltas against a TotalCashValue
baseline, a BIL sweep of its idle cash, and a /kill flatten. A second
strategy in the same account that also holds BIL (HG's safe leg) and moves
$118k of cash would show up in all four checks as unexplained venue truth.

- Option A (recommended): a separate IBKR account for the mirror, funded by
  an internal transfer of the $118k. The blend's checks never see the mirror.
  Open sub-question: whether one login can trade both accounts (one gateway)
  or the mirror needs its own gateway container.
- Option B: the same account, with the blend's reconcile made mirror-aware
  (venue truth minus the mirror's book, per symbol and in cash). This edits
  the blend's most hardened code paths and needs a full independent
  verification pass before deploy.

## Deployment note

ibkr-executor deploys from main (Render autoDeploy). This branch's copy of
ibkr-executor is stale (pre-blend3070); executor work starts from main's
tree, and reaching production is a merge to main, which is the owner's call.

## Model note

The executor stage touches live money in a ~10,000-line hardened service.
Per the repo rule (never downgrade the model on live-money work), the
executor build and its independent verification run on the strongest model.
