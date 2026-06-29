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
3. **Deploy.** Your dashboard will be at `https://<service-name>.onrender.com`.
   Add a custom domain (e.g. `genomics.optic.capital`) under
   **Settings → Custom Domains**, then CNAME it at your DNS provider.

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
| **Social / hype** | ✅ StockTwits (no key) + lexicon sentiment | **X/Twitter (PAID tier)**, Reddit (app creds) → fuller hype score |

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

## Coverage universe (editable 3 ways)

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

**Deactivate** (active=false) drops a name from active ingestion & default views
but **retains all historical data**. **Remove** (DELETE) hard-deletes the
universe row.

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
- **Sector Heatmap** — color = composite signal by subsector; click to drill in.
- **Watchlist** — sortable by any signal component; inline add/deactivate/remove.
- **Catalyst Calendar** — next 90 days, filterable by impact & subsector.
- **Movers in Narrative** — largest hype acceleration this week + active flags.
- **Per-name Deep Dive** — price chart with catalyst markers, estimate-revision
  timeline, hype timeline, runway gauge, auditable score breakdown, science feed.
- **Analyst Chat** — natural-language Q&A grounded in your data.

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

---

## Configuration (everything is YAML)
| File | Controls |
|---|---|
| `config/watchlist.yaml` | the universe (symbol, name, subsector tags, active) |
| `config/scoring.yaml` | component weights & parameters |
| `config/flags.yaml` | flag thresholds |
| `config/intervals.yaml` | scheduler refresh intervals per module |

Reload at runtime: `POST /universe/reload`, `POST /scores/reload`.

---

## Testing
```bash
cd backend && pytest          # 38 tests
```
Coverage includes the **scoring math with known inputs/outputs**
(`tests/test_scoring.py`), an offline end-to-end engine run
(`tests/test_engine.py`), universe sync/history-safety
(`tests/test_universe.py`), and catalyst normalization + override preservation
(`tests/test_catalysts.py`).

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
