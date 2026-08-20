# 🧬 Genomics Sector Alpha Tracker

A local-first analytics dashboard that tracks the genomics sector to surface
**forward-looking alpha** for a family office. It is built for signal extraction
and early detection of inflection points — not just data display.

- **Backend:** FastAPI + SQLite (clean Postgres upgrade path) + APScheduler
- **Frontend:** React + Tailwind + Recharts (served separately, talks REST)
- **Runs fully on free data** (yfinance baseline). Every premium feed is optional
  and drops in via `.env` with **no code changes**.

---

## TL;DR — run it

### Docker (recommended)
```bash
cp backend/.env.example backend/.env          # all keys optional; defaults work
docker compose up --build                      # API :8000, dashboard :5173
docker compose run --rm --profile tools backfill   # build history from day one
```
Open **http://localhost:5173** (API docs at **http://localhost:8000/docs**).

### Bare metal
```bash
# --- backend ---
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m scripts.backfill          # seeds universe + history + first scores
uvicorn app.main:app --reload       # http://localhost:8000

# --- frontend (new shell) ---
cd frontend
npm install
npm run dev                         # http://localhost:5173 (proxies /api -> :8000)
```

### Deploy a live, shareable URL (Render)
The repo ships a single-service image ([`Dockerfile`](Dockerfile) — FastAPI serves
the built React SPA, so one URL, no CORS) and a `render.yaml` blueprint **at the
repository root** (Render requires it there for Blueprint auto-detection).

1. On [Render](https://render.com): **New + → Blueprint → connect this repo**. It
   reads `render.yaml` automatically.
2. When prompted, enter these secrets (all `sync: false` → stored by Render, never
   in git): **`FMP_API_KEY`**, and a **`DASHBOARD_USER`** / **`DASHBOARD_PASSWORD`**
   login of your choice (the app is password-gated when both are set).
   Optional: **`BLEND_API_TOKEN`** — a dedicated read-only token the
   ibkr-executor uses to poll `GET /blend3070/intents` (that one route only;
   set the same value as `TRACKER_API_TOKEN` on the executor) so the
   executor never holds the dashboard password.
3. **Deploy.** Your dashboard will be at `https://<service-name>.onrender.com`.
   Add a custom domain (e.g. `research.optic.capital`) under
   **Settings → Custom Domains**, then CNAME it at your DNS provider. The
   dashboard itself lives at `/genomics/` (the root `/` redirects there), with
   the Treasury Canary at `/canary/`.

The blueprint uses the **Starter plan with a 1 GB persistent disk** so the service
stays always-on (the ingestion scheduler actually runs) and your history survives
restarts. It defaults to **`MARKET_PROVIDER=fmp`** on purpose: cloud hosts share
datacenter IPs that yfinance rate-limits (429) and StockTwits/ClinicalTrials block
(403), but your **authenticated FMP key works from anywhere** — so prices,
fundamentals, and analyst data populate reliably. `BACKFILL_ON_STARTUP=true` seeds
data on first boot.

> The same image deploys to Fly.io / Railway / any VM. For a heavier datastore,
> point `DATABASE_URL` at Postgres (no code changes).

---

## What works without any paid keys

| Layer | Free baseline | What a paid key adds |
|---|---|---|
| **Market / financials** | ✅ yfinance: OHLCV, market cap, fundamentals, cash runway, R&D, short interest & options IV/skew *where exposed* | Polygon/FMP/Tiingo: cleaner options & short data, especially thin-float names |
| **Analyst** | ✅ yfinance upgrades/downgrades (rating direction) | FMP: price-target & EPS/revenue **estimate revisions** → revision *velocity* |
| **Catalyst calendar** | ✅ ClinicalTrials.gov + yfinance earnings (no key) | — (PDUFA/AdComm/conferences are operator-curated via the API) |
| **Science signal** | ✅ PubMed + bioRxiv/medRxiv (no key) | NCBI key raises PubMed rate limits |
| **Social / hype** | ✅ **ApeWisdom** (no key, ~15 subreddits, real daily mention counts) + StockTwits + lexicon sentiment | FMP social (StockTwits+Twitter history, uses FMP key), **X/Twitter (PAID tier)**, Reddit (app creds) → fuller hype score |

> **Graceful degradation is guaranteed:** any module missing its key logs a
> warning and is skipped. The pipeline never crashes. Check `/health` to see
> which optional keys are active.

### Required vs optional keys

**None are required.** Optional keys (all in `backend/.env`):

| Key | Enables |
|---|---|
| `POLYGON_API_KEY` / `FMP_API_KEY` / `TIINGO_API_KEY` | premium market data (set `MARKET_PROVIDER` to match) |
| `FMP_API_KEY` | analyst estimate/price-target revisions (revision velocity) |
| `X_BEARER_TOKEN` | X/Twitter hype ingestion (**paid tier**) |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit hype ingestion |
| `ANTHROPIC_API_KEY` (+ `SENTIMENT_ENGINE=anthropic`) | LLM sentiment instead of lexicon |
| `NCBI_API_KEY` / `NCBI_EMAIL` | higher PubMed rate limits |

---

## Coverage universe (editable 4 ways)

The watchlist is seeded from [`backend/config/watchlist.yaml`](backend/config/watchlist.yaml)
(32 names across synbio, AI-drug, gene-editing, sequencing, liquid-biopsy, RNA,
mRNA, neuro/psychedelics, devices, and a pharma anchor). Subsector tags are
**first-class and free-form** so you can roll signal up by theme and invent new
themes on the fly.

Edit the universe without code changes via **any** of:
1. **Dashboard UI** — *Watchlist* tab → "Add + Backfill" (symbol validated &
   company name auto-fetched; immediate backfill kicks off) and inline
   **Deactivate / Remove** per row.
2. **REST API** — `POST /universe`, `PATCH /universe/{symbol}`,
   `DELETE /universe/{symbol}`, `GET /universe`, `POST /universe/reload`.
3. **File** — edit `watchlist.yaml` and `POST /universe/reload` (or restart).
   Sync is an **upsert — it never wipes history**.
4. **Discovery** — the dynamic-universe pipeline (below) proposes candidates
   automatically; a hard-gated, weekly-capped **auto-promote**
   (`config/discovery.yaml`) can add names on its own.

**Deactivate** (active=false) drops a name from active ingestion & default views
but **retains all historical data**. **Remove** (DELETE) hard-deletes the
universe row.

---

## Universe discovery

The universe should never again depend on a human remembering a company exists
(MRNA's +130% readout day was missed partly because nobody added the name).
A daily sweep (`app/ingestion/discovery.py`, Discovery tab in the UI) proposes
candidates into an auditable queue — two keyless lanes:

- **Movers** (the miss-detector): Nasdaq healthcare screener census
  (~1,100 US-listed names, cached 24h) — any |move| ≥ 10% on a ≥$300M name
  **not** in the universe.
- **Catalyst**: deterministic 10-day rotation over the census; ClinicalTrials.gov
  (cached 7d) — near phase-3 primary completion dates, or active phase 2/3 +
  genomics keyword match.

Each candidate carries a 0–100 score (mcap band + catalyst proximity +
genomics relevance + mover recency) and its raw evidence. **Auto-promote** is
config-togglable and conservative, with two ways in, both capped at 3
promotions per rolling week (manual promotions count against the cap too):

- **Standard**: score ≥ 70 AND mcap ≥ $2B AND (phase-3 PCD ≤ 90d OR a ≤7-day
  |move| ≥ 15%).
- **Mega-cap mover fast-path**: mcap ≥ $10B AND a ≤7-day |move| ≥ 10% AND an
  active drug/biologic trial on CT.gov (fails closed when CT.gov is dark).
  Exists because the score under-detects registered-name mismatches — the
  2026-06-17 MRNA replay scores 41 and only this path would have added it.

Auto-promote only acts on status `new` — a desk `watch` judgment is never
overridden. Promotion is reversible — deactivate retains history. **Dismiss**
records a reason and suppresses re-entry for 90 days; set
`auto_promote: false` in `config/discovery.yaml` to make discovery
propose-only. Endpoints: `GET /discovery/candidates`, `GET /discovery/summary`,
`POST /discovery/run`, `POST /discovery/candidates/{sym}/promote|dismiss`.

**Known blind spots** (counter-agent, 2026-08-19): the Nasdaq
`sector=health_care` census misses genomics *tools/diagnostics* classified
elsewhere (verified absent: EXAS, TXG, PACB, TEM, TMO, DHR) — tools coverage
still relies on watchlist curation; slow re-rates that never print a ≥10% day
only surface via the catalyst lane; CT.gov registered-name mismatches
under-detect catalysts (mitigated in the tracker by `ctgov_names`, not
available for names we don't know yet).

---

## Alpha synthesis — the actual point

A scoring engine combines the layers into a per-name composite **Alpha Signal**.
Every component is visible and individually weighted; weights live in
[`config/scoring.yaml`](backend/config/scoring.yaml) (no code edits to retune —
`POST /scores/reload` after editing).

| Component | Meaning |
|---|---|
| `revision_velocity` | recency-weighted net direction of estimate revisions (leading indicator) |
| `catalyst_score` | Σ over upcoming catalysts of `impact_weight × time_decay` (rewards proximity) |
| `hype_divergence` | z(mention **acceleration**) − z(price change) → positive = chatter leading price |
| `positioning` | short-interest percentile + options skew (squeeze/crowding) |
| `runway_penalty` | drag that ramps in as cash runway drops below threshold |

**Composite** = weighted mean of components, each normalized to a common 0–100
scale (from a cross-sectional z-score or percentile) before weighting.

> **Auditable by design:** every score response (`GET /scores/{symbol}`, and the
> deep-dive view) exposes the full `formula` — raw value, normalized
> contribution, weight, and weighted term per component — so you see **why** a
> name lit up, not just the number.

> **No-data ≠ zero:** missing components are listed in `missing[]` and *excluded
> from the weighting denominator* — they never drag a name toward zero. Thin-float
> names (ALMR, GENB, QSI, MASS) with patchy options/short data surface as `n/a`,
> not `0`.

### Named, evidence-linked flags
Thresholds live in [`config/flags.yaml`](backend/config/flags.yaml). Each flag
links back to the underlying rows (which catalysts, revisions, posts):
- **pre_catalyst_sentiment_ramp** — hype acceleration rising into a catalyst within N days
- **analyst_revision_cluster** — ≥X same-direction revisions in a short window
- **unusual_options_social_spike** — IV/skew move co-occurring with a mention spike
- **runway_cliff_approaching** — quarters-of-runway crossing below threshold
- **binary_event_within_n_days** — high-impact catalyst imminent

---

## Dashboard views
- **Today** (default) — what's actionable right now, readable by a first-time
  viewer: sector regime strip (XBI/ARKG/IBB), fresh flags as tradeable cards
  (why it fired, that signal's real hit rate, reference levels, liquidity tier,
  binary-event framing), open calls with signal-decay hints, this week's
  catalysts, and a pre-market digest (EST/NYSE framing, data-freshness stamped).
- **Sector Heatmap** — color = composite signal by subsector; click to drill in.
- **Watchlist** — sortable by any signal component; inline add/deactivate/remove.
- **Catalyst Calendar** — next 90 days, filterable by impact & subsector.
- **Movers in Narrative** — largest hype acceleration this week + active flags.
- **Calls Log** — the tracker's own exact trade calls, logged and graded (below).
- **Per-name Deep Dive** — price chart with catalyst markers, estimate-revision
  timeline, hype timeline, runway gauge, auditable score breakdown, science feed.
- **Analyst Chat** — natural-language Q&A grounded in your data.

---

## Calls Log — the tracker grades itself

The tracker doesn't just flag names — it makes **exact trade calls** and keeps
score. When a trigger signal fires (pre-catalyst sentiment ramp, upward analyst
revision cluster, unusual options + social spike) on a name whose composite
clears the conviction bar, a call is logged with:

- **entry** (latest close), **stop** (2×ATR, %-fallback), **target** (2R), and a
  **time-stop** — which lands the day *before* the nearest binary catalyst, so
  auto-calls sell into events rather than holding through binaries.

Levels are **frozen at fire-time and never edited**. A scheduled evaluator then
grades every open call against subsequent daily bars — target hit, stopped out
(a bar spanning both levels grades as stopped, the conservative reading), or
time-stop expiry — and records return % and **R-multiple**. The *Calls Log* tab
shows open calls with live unrealized P&L, the closed-call history, and a
**scorecard by signal type** (win rate, avg return, avg R) — so "which signals
actually pay" is answered with evidence, and weights/thresholds get retuned
from the record, not intuition.

Manual calls (the desk's own takes, or a chat memo worth tracking) are logged
via the same tab or `POST /calls` — missing levels are auto-filled the same way
so every call is gradeable. Tuning lives in
[`config/calls.yaml`](backend/config/calls.yaml) (triggers, conviction gate,
cooldown, risk unit, horizon); the engine is deliberately conservative because
false positives are the main failure mode.

**Evidence-based defaults.** The stop/target/time-stop defaults come from a
real-data backtest of the exit mechanics
([`docs/BACKTEST_CALLS.md`](../docs/BACKTEST_CALLS.md), ~2y adjusted bars,
30 names): a **genuinely paired** exit-config grid (identical entries in every
cell), open-first gap-aware fills, cluster-bootstrap CIs, regime split, and
**slippage-adjusted plateau selection**. Headline findings: tight (1.5–2×ATR)
stops look best frictionless but lose their edge to trading costs, and
3×ATR / 3:1 / 45d is robust net of slippage in both XBI regimes (net avg R
0.190; the 2:1 neighbor is statistically indistinguishable). Rerun with
`python -m scripts.backtest_calls --refresh`.

**Every closed call gets a post-mortem — the WHY, not just the outcome.**
Computed from the data, never hand-written: path excursions (did it ever work,
or did we round-trip a +2R winner?), sector attribution (name alpha vs XBI
beta over the trade window), signal decay (did the composite fade before the
exit?), catalyst discipline, and — ~10 bars after exit — a **hindsight
verdict**: a stop that kept falling *protected capital*; one that snapped back
above entry was a *shakeout* (a pattern of shakeouts means widen the stop, not
blame the signal). Shown under each closed call in the Calls Log.

**The improvement loop is itself a system** ([`TUNING.md`](TUNING.md)). On a
monthly cadence an agent reads the aggregate evidence (`GET /tuning/evidence`),
checks per-lane sufficiency (`scripts/tune_proposal.py`), and may propose ONE
config change — which must first pass a statistical gate
(`evals/replay.py`): weights changes need a bootstrap-confirmed rank-IC
improvement on forward XBI-excess returns; trigger promotions need n ≥ 20 with
a Wilson 90% lower-bound hit rate above 50%; exit-parameter changes rerun the
slippage-adjusted backtest. Passing proposals arrive as pull requests with the
evidence and gate output attached — **a human merges, always**. "No proposal
this cycle" is the expected output until the record fattens.

**The flags grade themselves too.** Every flag — including ones that never
became calls — is graded from its fire-time close against forward 1w/1m/3m
returns, raw and XBI-excess (`GET /flags/track-record`). Flag cards on the
Today tab show that signal's live hit rate (with n, and an "insufficient
history" warning below n=10). New signal ideas (pullback-into-catalyst,
insider clusters) ship **observe-only** and are promoted to call triggers only
when their record earns it. This is the loop that turns the equal starting
weights into evidence-based ones.

**Exit engines get shadow-graded the same way (H11/H8).** The round-2 variant
campaign's best construction — R2-A: a 200dma prior-close XBI regime gate plus
3×ATR trailing exits with a 90-day time stop
([`docs/BACKTEST_VARIANTS_R2.md`](docs/BACKTEST_VARIANTS_R2.md)) — is replay
evidence only, so before it can touch `calls.yaml` it must earn a **live**
record. Every live auto-call is therefore additionally graded under the
trailing exit engine (independently of the live grade — either book may close
a call first), and the XBI 50/200dma gate state is logged daily on the
prior-close convention. `GET /shadow/track-record` compares the two engines on
the **same closed calls** (n, hit rate, avg/total R) plus the regime summary;
`GET /shadow/regime` is the daily gate log. This is a pure shadow book: it
changes **nothing** about live call generation, levels, exits, or the paper
account.

---

## Analyst Chat (grounded LLM)
Interrogate the data in plain English — e.g. *"thoughts on MU given its forward
P/E? bull and bear case, then a probability analysis on the trade."* A Claude agent
answers by **calling tools that pull your real data** (Alpha Signal components,
flags, catalysts, fundamentals/runway) plus **live FMP valuation for any ticker**,
then writes a structured trade memo (snapshot · thesis & smart entry · bull · bear
· probability/EV · what-would-change-my-mind). The model is instructed never to
invent numbers — every figure traces to a tool result.

- Requires `ANTHROPIC_API_KEY` (the tab shows a "disabled" notice without it; the rest of the app runs regardless).
- **Sonnet 4.6** by default; a **"Deep analysis"** toggle switches to **Opus 4.8**.
- Research, not investment advice.

**Token-cost optimization.** An agentic tool loop re-sends the entire conversation
(system prompt + tool schemas + every prior tool result) on *each* iteration —
quadratic token growth, the dominant cost. Two measures cut it sharply with no
quality loss:
1. **Prompt caching** — the static prefix (system + tool schemas) and the *growing*
   conversation tail both carry an ephemeral `cache_control` breakpoint, so every
   loop iteration and follow-up turn reads the prior prefix at **~0.1×** instead of
   full price. This is what neutralizes the quadratic growth.
2. **Lean tool payloads** — tools return only what the model needs to reason (e.g.
   the 0–100 component scores, not the verbose audit `formula`), shrinking the
   results that get re-sent every iteration.

Each answer shows a live usage line (`tokens in/out · % cached → tokens saved`) so
the savings are visible.

---

## Configuration (everything is YAML)
| File | Controls |
|---|---|
| `config/watchlist.yaml` | the universe (symbol, name, subsector tags, active) |
| `config/scoring.yaml` | component weights & parameters |
| `config/flags.yaml` | flag thresholds |
| `config/calls.yaml` | trade-call triggers, conviction gate, risk unit, horizon |
| `config/intervals.yaml` | scheduler refresh intervals per module |
| `config/discovery.yaml` | universe-discovery lanes, auto-promote gates & weekly cap |

Reload at runtime: `POST /universe/reload`, `POST /scores/reload`.

---

## Testing
```bash
cd backend && pytest          # 80 tests
```
Coverage includes the **scoring math with known inputs/outputs**
(`tests/test_scoring.py`), an offline end-to-end engine run
(`tests/test_engine.py`), universe sync/history-safety
(`tests/test_universe.py`), catalyst normalization + override preservation
(`tests/test_catalysts.py`), the **trade-call level math, grading rules,
generation gates, and scorecard** (`tests/test_calls.py`), and the
**review-hardening pass** — gap-aware fills, binary-expiry refusal, liquidity
tiers, hardened flags, re-fire suppression, flag forward-return grading
(`tests/test_review_hardening.py`).

---

## Architecture & extensibility

Each data source is an independent module implementing a common
`fetch() → normalize() → upsert()` contract
([`ingestion/base.py`](backend/app/ingestion/base.py)), so sources can be added
or disabled in isolation. Market providers share a `MarketProvider` interface
([`ingestion/providers/`](backend/app/ingestion/providers/)) — swap yfinance ↔
Polygon/FMP/Tiingo by changing `MARKET_PROVIDER`.

### Directory tree
```
genomics-alpha-tracker/
├── docker-compose.yml
├── README.md
├── backend/
│   ├── Dockerfile  requirements.txt  pyproject.toml  .env.example
│   ├── config/            # watchlist, scoring, flags, intervals (all YAML)
│   ├── app/
│   │   ├── main.py        # FastAPI app + lifespan (init, sync, scheduler)
│   │   ├── config.py  db.py  models.py  schemas.py  scheduler.py
│   │   ├── routers/       # universe, market, catalysts, scores, views
│   │   ├── ingestion/     # base + market/analyst/catalysts/science/social + runner
│   │   │   └── providers/ # yfinance | polygon | fmp | tiingo
│   │   ├── scoring/       # components.py (pure math), engine.py, flags.py
│   │   ├── universe/      # manager.py (YAML <-> DB sync)
│   │   └── utils/         # normalize, cache, ratelimit, sentiment
│   ├── scripts/backfill.py
│   └── tests/             # scoring, engine, universe, catalysts
└── frontend/
    ├── Dockerfile  nginx.conf  package.json  vite/tailwind config
    └── src/
        ├── App.jsx  lib/{api,format}.js
        ├── components/    # AddTicker, RunwayGauge, Flags
        └── views/         # Heatmap, Watchlist, CatalystCalendar, Movers, DeepDive
```

---

## Notes for the analyst
- **Backfill first** (`scripts.backfill`) so signals have history; newly added
  tickers auto-backfill on insert.
- Premium feeds (a market feed + X API) are the two that most change output
  quality — set them in `.env` when available; nothing else needs to change.
- This is research tooling, not investment advice.
