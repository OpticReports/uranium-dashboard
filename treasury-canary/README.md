# 🐤 Treasury Market Health Monitor — "The Canary"

An institution-grade, daily-refreshing Treasury market health monitor that acts as
a recession / market-distress canary. It ingests the rates-desk metric set from
**free public APIs**, scores each metric green/yellow/red against historically
grounded thresholds, rolls them into a composite **Treasury Stress Score (0–100)**
and an **Estrella-Mishkin recession probability**, and alerts on regime changes.

> **The headline signal:** detect and alert on **yield-curve re-steepening after a
> sustained inversion** — because recessions have historically begun *after* the
> curve dis-inverts, not while it is inverted. This is a first-class, visualized,
> alertable signal, not a footnote. (Framed as association, not causation; post-2000
> lead times have been longer and noisier.)

Standalone app that lives alongside the genomics dashboard in this repo.

- **Backend:** Python 3.11 + FastAPI + SQLite (SQLAlchemy) + APScheduler
- **Frontend:** React + Vite + TypeScript + Tailwind + Recharts
- **Free-first:** everything core runs on free public APIs; only **FRED** needs a
  free key. Missing sources degrade to `STALE` and the composite reweights.

---

## Build status (in progress)

| Phase | Status |
|---|---|
| Backend foundation (config, store, db, contracts) | ✅ |
| Curve metrics + re-steepening state machine (core) + tests | ✅ |
| Scoring (thresholds, composite, events) + tests | ✅ |
| Recession model (Estrella-Mishkin probit) + tests | ✅ |
| FRED source (cache + backoff + graceful degradation) + tests | ✅ |
| Volatility / funding / premium / cross-asset metrics (FRED) | ✅ |
| Jobs (backfill, refresh) + API routes + main.py | ✅ |
| Frontend (all panels) + "?" tooltips everywhere | ✅ |
| Deploy wiring (Docker, render.yaml, same-domain section) | ✅ |
| Recession horizon model (probit + CI + AUC) & labor signals (Sahm/claims) | ✅ |
| Flow compass ("where is the money going") & Dalio pin board | ✅ |
| Leading stack (additive, toggleable, never fitted) | ✅ |
| Auctions (E, FiscalData) · OFR FSI (G) · foreign custody (F) — full coverage | ✅ |
| Open slot: on-the-run/off-the-run spread (no clean free source; not faked) | ⏳ |

Backend tests: `cd backend && python -m pytest -q` (currently 58 passing).

## Run it

### Docker (single service — API serves the built SPA)
```bash
cp .env.example backend/.env          # optionally set FRED_API_KEY
FRED_API_KEY=xxxx docker compose up --build   # -> http://localhost:8000
```

### Bare metal
```bash
# backend
cd backend && python -m pip install -e . && python -m pytest -q   # 24 tests
uvicorn app.main:app --reload         # http://localhost:8000 (docs at /docs)
# frontend (new shell)
cd frontend && npm install && npm run dev     # http://localhost:5173 (proxies to :8000)
```
Trigger an immediate pull/compute: `curl -X POST localhost:8000/refresh`.

## Deploy (same domain, new section)
The app ships a single-service `Dockerfile` and a standalone `render.yaml` (kept
separate from the genomics app's root blueprint so the live deploy is untouched).
To surface it under the existing domain as a new section, either:
- **Path route** `research.optic.capital/canary/*` via a reverse-proxy rule to the
  canary service, or
- **Subdomain** `canary.optic.capital` (own Render service) plus a nav link from the
  genomics dashboard.

Set `FRED_API_KEY` (free) in the Render dashboard; optionally `ALERT_WEBHOOK_URL`.

## API
`GET /health · /metrics · /metrics/{id}/history · /composite · /recession-prob ·
/curve/canary?pair=3m10y · /events · /alerts · /news` and `POST /refresh`.

## Which modules work with NO keys
Treasury FiscalData (par curve, auctions), NY Fed (SOFR, ACM term premium), OFR
(Financial Stress Index), and the RSS news feed are keyless. FRED (curve tenors,
real yields, breakevens, funding rates, VIX, credit OAS, USREC, recession model)
needs a free `FRED_API_KEY`.

## Design guarantees
- **Config-driven:** thresholds (`scoring/thresholds.py`, override via `THRESHOLDS_FILE`)
  and category weights (`scoring/composite.py`) retune without code edits.
- **Explainable composite:** score decomposes into per-category contributions.
- **Graceful degradation:** a dead source → `STALE` rows + reweighted composite, never a crash.
- **History from day one:** every run persists a snapshot.
- **UTC storage, rendered in America/Puerto_Rico.**
- **Idempotent alerts:** events dedupe on `(event_type, dedup_key)` so each transition fires once.
