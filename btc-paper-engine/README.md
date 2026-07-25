# BTC Pullback Paper-Trading Engine

Paper/test engine for the three validated BTC pullback strategy configurations
(spec: `paper_engine_spec` v1.0; research: `BTC_Winning_Strategies_Report`).
**Paper execution only — no exchange keys, no real orders.** The engine's
purpose is to measure the live-vs-backtest gap before any capital decision.

- Backend: FastAPI + SQLite (persistent disk), single background poll loop.
- Signals: 4h Bitstamp BTC/USD bars, SMA50/200 regime + RSI(14) pullback +
  volume + 0.5-ATR depth filters; limit entry at signal close (1-bar patience);
  2.5×ATR frozen stop; SMA50-reclaim exit; 60-bar time stop.
- Books: S1 vol-target 5.5% (longs 0.75×, cap 3×) · S2 fixed 1.95×
  (longs 0.75×, cap 2.5×) · S3 unlevered 1× control. $100k paper each.
- Frontend: one-page dashboard at `/btc` behind the research.optic.capital
  login gate (conditions strip, books, equity curves, trade log, events).

## Acceptance (§6) — deviation report, 2026-07-25

Replay 2024-07-24 → 2026-07-24 on Bitstamp 4h bars vs the reference sim
(`backend/reference/btc_trades_limit_entry_reference.csv`):

| Check | Expected | Engine | Verdict |
|---|---|---|---|
| Trade count | 89 ±2 | **89** | exact |
| Exit mix (signal/stop) | 58/31 ±3 | **58/31** | exact |
| Win rate | 62.9% ±1.5 | **62.9%** | exact |
| S3 total / max DD | +48.1% / −14.2% | **+48.1% / −14.2%** | exact |
| S1 total / max DD | +64.5% / −22.3% | **+64.5% / −22.3%** | exact |
| S1 OOS (Dec 2025→) | +29.9% / −10.3% | **+29.9% / −10.3%** | exact |
| S2 total / max DD | +101.4% / −22.9% | **+101.4% / −22.9%** | exact |
| Per-trade identity | ≥95% timestamps | **89/89 on prices** | see note |

Two artifacts discovered during acceptance (documented, matched deliberately):

1. **Reference timestamp labels are shifted +1 bar before ~2024-09-10** (the
   research dataset's own stitching). Entry/exit PRICES match ours to the
   penny for all 89 trades, so trade identity is checked on prices with
   timestamps required within one bar.
2. **The research compounds shorts on a price-ratio basis** (short ret =
   entry/exit − 1, futures-style) while spec §3 dollar accounting gives
   ret − ret² per short. Both are computed: the live books use §3 dollar
   accounting (the honest USD paper book); `research_basis_stats()` reproduces
   the reference accounting for the table above. Gap on S3 over the window:
   +48.1% (research basis) vs +41.7% (dollar basis) — entirely the shorts'
   squared terms, guarded by a regression test.

Fee model decoded from the reference: taker exits charge 6 bps of ENTRY
notional (ret = favorable price ratio − 6 bps, matches reference to ~0.1 bp).

## Engine semantics pinned by tests

Fill-bar close ineligible for signal exit · stop inactive on the fill bar
(no bars_held=0) and beats close exits within a bar · close exits execute at
next bar open · unfilled limit cancels and may re-arm the same close ·
vol-target sizing clamps at the notional cap on tiny-ATR entries ·
drawdown halts block entries but keep managing the open position · restart
at any bar resumes bit-identically (6-cut-point kill test).

## Operations

- `GET /status` health + per-book state; `/conditions` = live n/6 setup strip.
- `POST /books/{S1|S2|S3}/halt|resume` manual kill-switch (resume re-anchors
  the drawdown baseline); `POST /resume-data` clears a price-sanity halt.
- `POST /replay` re-runs the acceptance replay with the active config
  (warns if config ≠ research defaults).
- DEGRADED (no data >10 min) blocks new entries, keeps protective stops.
- Kraken cross-check: >5% Bitstamp deviation halts entries until reset.
- Restarts rebuild from SQLite and process any bars missed while down.

## Non-goals (v1)

No real orders; no walk-forward re-optimization; no confidence sizing, partial
exits, trailing stops, or loss-streak throttles (all explicitly rejected in
the research). Schema carries a `symbol`-ready design for later assets.
