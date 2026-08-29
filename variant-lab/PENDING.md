# PENDING QUESTIONS — variant-lab

Ranked by weight of importance, per the standing convention: **P1** decision-gating,
**P2** score-moving, **P3** completeness. Each names what it would move. Status is
carried forward as a living ledger; 60-day expiry from first ask, and an unanswered
P1 at expiry is closed as refused and priced as a negative signal.

First asked 2026-08-29. Nothing is built pending the P1s — several of them change
what gets built, not merely how it is parameterised.

| # | P | question | what it moves | status |
|---|---|---|---|---|
| 1 | P1 | **Risk capital, account types, futures and options permissions, and acceptable peak-to-trough drawdown in dollars.** | Every number in the sizing stack. `c_max = 2/(1 + ln p / ln(1−d))` is undefined without your (p, d); the default (0.10, 0.30) → 0.268 is a placeholder I chose, not a preference of yours. Also determines which instruments are even expressible: one ES contract is ~$380k notional, CL ~$60k, and the Composer book probed at $276k. | asked |
| 2 | P1 | **Is the uranium sleeve actually held, and where?** No uranium position exists in either account this session can see (Composer = 6 tickers, IBKR = SPY + BIL) and no cost-basis file exists in the monorepo. Same question for genomics single names and any BTC spot held outside btc-executor. | Every netting number. Uranium sits in the 31-name mega-cluster at ρ = 0.58 alongside the leveraged-Nasdaq book — if held, it *adds* to your dominant factor rather than diversifying it, and the conditional-exposure figures in `README.md` are wrong. | asked |
| 3 | P1 | **Which reading of the no-trade gate?** "All three crowd definitions concordant" passes 2.5% of episodes = 1.8/yr → 144 years to n = 194, never validatable. "Reject only when a definition is on the opposite side" passes 87% = 41/yr → 6.3 years. | A 26× fork on how often the system is permitted to act, and whether it can *ever* be validated. Recommend LOOSE, with the 13.0% OPPOSED cases as a hard no-trade and the concordance class carried as a scorable field. | asked |
| 4 | P1 | **Which forecast primitive is the ledger's unit?** P(dd ≥ 40% within 24m) has a 16% base rate and a measured 1.84-year mean time-to-close → first meaningful R2 in 2029-02. P(dd ≥ 20% within 12m) closes in 0.86y and doubles R2 throughput. | Whether you get the headline hazard number or a calibration loop that matures this decade. Cannot be chosen for you — it is a preference about what the instrument is *for*. | asked |
| 5 | P1 | **Options: fund, defer, or scope out?** No free options-surface *history* exists at any price (Cboe 403s dated paths; OCC returns byte-identical output for every `reportDate`). The live surface is keyless and works; the history does not exist. (a) Fund a vendor (ORATS/IVolatility/Cboe DataShop) so thresholds calibrate before launch; (b) ship observation-only with a daily snapshot writer and no thresholds for 6–12 months; (c) scope options out of v1. | The carry-vs-catalyst detector — which both trader tracks identify as the real escalation trigger — and every defined-risk expression the crowding carve-out permits. Not modelling around this, per the house rule. | asked |
| 6 | P1 | **Energy z-score history: which treatment?** CFTC retroactively rewrote all energy COT for as-of dates 2007-07-03 → 2008-07-08; both channels now serve only restated values and the originals are unrecoverable. (a) Exclude that window from all calibration; (b) accept restated history and state it in the honesty box; (c) reconstruct from a 2008-vintage third-party archive. | Every threshold calibrated on that window, and it lands directly on the uranium/energy node. | asked |
| 7 | P1 | **The actual v1 instrument list.** The feed-resilience probe verified coverage against a 15-name uranium+macro set of its own construction. The coverage matrix, the min-bars thresholds and the fallback-gap list are all keyed to that guess. | Whether the coverage matrix is real. Several cells will change. Give the list and every cell gets re-verified. | asked |
| 8 | P1 | **Re-probe FRED from the Render production network.** It failed 8/8 from this session (HTTP/2 INTERNAL_ERROR, empty reply, ProxyError) on both `fredgraph.csv` and `/data/*.txt`, and it is *not* an egress-policy denial. The recon listed it live the same day. | Whether any rates, credit or liquidity series can depend on it. Deliberately not designed around. | asked |
| 9 | P2 | **Authorise building the C1 commitment register?** P(commitment abandoned within 12m) cannot be Brier-scored without a frozen historical register of official-actor commitments with `opened_on`/`closed_on`. None exists. Estimate: BIS corpus + primary feeds populate ~30–60 episodes back to 1996. | Whether the official-actor detector can publish a conditional probability at all, or stays a candidate generator with no base rate. Five worked examples are five episodes, not a base rate. | asked |
| 10 | P2 | **Atlanta Fed MPT redistribution terms, and whether to depend on `api.nasdaq.com`.** The Fed workbook ships a sheet named LICENSE containing no license text, and derives from CME data whose own site returns 403 with an explicit anti-scraping ToU. The Nasdaq endpoint is undocumented, unversioned, needs a browser User-Agent, and redistributes a third-party estimates vendor — and it is the *only* free dated single-name consensus found. | The entire equity sleeve's priced-in denominator rests on the Nasdaq endpoint; the rates baseline rests on the Fed workbook. Both need a named fallback before being wired. | asked |
| 11 | P2 | **Uranium has no consensus baseline at all** — no free 12–24m forward for the flagship theme. The refusal path is therefore the *default* for the thing you care most about, not a corner case. Accept the refusal, or source a baseline? | Whether `thesis_delta` is computable on uranium, i.e. whether the system can ever say a uranium view is *variant* rather than merely held. | asked |
| 12 | P3 | **Theme watchlist size.** 42 names → the ≥150% run-up band validates in 26.5y; 400 names → 4.8y. Is watchlist breadth a free variable? | Whether the one carve-out with a measured hazard lift (1.31×) can be validated in your lifetime. | asked |

## Notes on two of these

**On #1.** This is the one the house rule was written for. Every sizing number in
`BLUEPRINT.md` §6 is currently conditioned on a (p, d) I picked. It is recorded as a
declared default, not as an UNKNOWN quietly propagated into a verdict — but it is a
placeholder and the blueprint should not be read as if it were your number.

**On #5 and #9 together.** Both are cases where the honest answer is that the data to
validate a detector does not exist yet. The blueprint's response is the observation-only
path: ship the snapshot writer, accrue history, and publish nothing conditional until
there is a base rate. That is a real answer, but it is a 6–12 month answer, and you
should decide whether that is worth the build rather than discovering it later.
