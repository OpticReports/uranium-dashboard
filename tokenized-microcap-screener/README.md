# Tokenized Microcap Screener

Finds memecoins being pooled against a **tokenized share of a listed company**,
maps the pool back to the US listing, and ranks the listings by how much of the
equity move still looks to come.

Built after Farmmi (`FAMI`) on 2026-09-02: a $5.7M nanocap mushroom exporter on
a Nasdaq delisting clock that traded 815M shares — ~330x its median day — and
printed +309% intraday before giving most of it back.

## The structural signal

The memecoins that moved listed stocks were not merely *named* after a company.
They were **pooled against a tokenized share of it**. `JINQIAN`'s deep pool
quotes in `FAMI`; `MU MU THE BULL` quotes in tokenized `MU`; `Artificial Inu`
quotes in tokenized `NVDA`.

That makes meme → ticker a property of the pool, not an inference from a name,
so it can be detected mechanically:

```
pair where exactly one side is a tokenized equity
  and the other is neither an equity token nor a chain base asset
```

The mapping is exact because tokenized wrappers carry the company's registered
name. DEX Screener returns the JINQIAN pool's quote token as `Farmmi, Inc.` —
byte-for-byte the SEC title for `FAMI`.

## What it will NOT do

A symbol match is never enough. `MU MU THE BULL` trades as symbol `MU`; a token
named `NVDA` trades against real tokenized `NVDA`. Ticker squatters are the
dominant failure mode, so a token counts as an equity only if it carries an
issuer marker (`… • Robinhood Token`, `… xStock`) **or** its name matches the
SEC company title for that symbol. Bare-echo lookalikes are excluded outright.

## Official vs unofficial wrappers — a real distinction

| | official (`… • Robinhood Token`) | unofficial |
|---|---|---|
| mint / redeem | yes | **none** |
| path to the tape | on-chain buying can transmit | people *seeing* it and buying the listing |

The FAMI wrapper the memes traded against was **unofficial**. Nothing
mechanically connected on-chain demand to Nasdaq — the entire link was
attention. Scored accordingly, not filtered out.

## The ladder, and the measured lead of each rung

Lead measured from DEX Screener `pairCreatedAt` to the first 5-minute bar that
cleared +12.8% (2026-09-02 09:45 ET):

| rung | when (ET) | lead |
|---|---|---|
| `TOKENIZED` — wrapper pool seeded | 09-01 17:54 | **+15.8 h** |
| `PAIRED` — first meme (`JINQIAN`) | 09-02 09:32 | +0.2 h (13 min) |
| `RAMPING` — second meme (`FORASEN`) | 09-02 10:42 | −1.0 h |
| `CLUSTER` — cascade complete | 09-02 11:36 | −1.9 h |
| `EQUITY_MOVING` | 09-02 09:45 | — |

**The cascade rungs are coincident or lagging.** The only comfortably tradable
rung was the dullest one: somebody had wrapped a $5.7M nanocap the previous
evening and no meme existed yet. That is what `cold_tokenization_score` grades,
and it is why nanocap wrappers are swept every 2 minutes rather than every 30 —
on the meme rung, cadence *is* the signal.

Alerts fire on a fresh climb onto `TOKENIZED` (nanocap only), `RAMPING` or
`CLUSTER`, and are **suppressed once the equity is already moving** — by then
an alert is an obituary.

## Alerts

Rides the **same Telegram bot as treasury-canary and the executors** — set
`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` on this service too. Unset = no-op.

Severity ranks rungs by **how much runway they leave**, which inverts the
obvious ordering:

| severity | rung | why |
|---|---|---|
| `CRITICAL` | `RAMPING` | ~13 minutes of lead. Act now or not at all. |
| `RED` | `TOKENIZED` | ~15.8h of lead. The rung worth waking up for. |
| `WARN` | `CLUSTER` | Arrived 1.9h *after* the move. Context, not a call. |

`TELEGRAM_MIN_SEVERITY=RED` (the deploy default) mutes the cluster notices and
keeps the two rungs that leave time to act. Every message carries **the pools**
— symbol, liquidity, 24h volume, liquidity trend, and a direct DEX Screener
link each — plus float and float turnover. A ticker with no way to look at what
is trading against it is not an actionable alert.

## Scores

Four orthogonal axes, kept separate so it is visible which one failed.
`earliness` **multiplies** rather than adds: a setup perfect on every other axis
that has already run scores zero, not "still pretty good".

- **credibility** — pool depth, liquidity/FDV, two-sidedness, breadth, turnover,
  and **liquidity trajectory**. One reading cannot tell a pool being built from
  one being drained; the change between two readings can, so a pool whose LP is
  walking out gets its score multiplied down however deep it looks right now.
- **heat** — acceleration, not level
- **pumpability** — cheap, small cap, beaten down, and above all **free float
  and float turnover**
- **earliness** — how much of the equity move is still ahead

### What actually separates a pumpable stock

Six factors, each scored 0-100 and **reported individually** — a score nobody
can interrogate is not analysis. Weights renormalise over whatever inputs are
present, so a dark lane lowers confidence rather than scoring a name as if the
missing input were bad.

| factor | weight | what it answers |
|---|---:|---|
| cost to move | 0.28 | median **dollar** volume — MU trades $26.6B/day, FAMI $950K, on share volumes only ~4x apart |
| float | 0.22 | free float. WHLR's is 21,783 shares |
| squeeze history | 0.18 | has it *already* done a violent up-day? WHLR: +97.8%, two days over +30% |
| capable of moving | 0.12 | realized daily vol — the NTIC control |
| price | 0.10 | sub-$1 names travel in bigger percentages |
| market cap | 0.10 | size, when FMP is on |

**Cheap and illiquid is not pumpable.** NTIC has the smallest dollar volume of
any name tested ($17.8K/day) and has never moved: 1.6% daily vol, best day
+9.9%. Squeeze history and realized vol are what separate it from WHLR, and
float alone cannot.

Two data-quality guards, both from real readings:

- A market cap of **0** (WHLR, per FMP) is a gap, not a $0 company — scored as
  "tiny" it handed WHLR a free 100/100.
- A market cap of **$13,605** for a NASDAQ-listed REIT is stale share data
  after reverse splits. Nasdaq's continued-listing standards make it
  impossible, so readings under $250K are dropped rather than rewarded.

### Dilution — what you are buying

Deliberately **not** folded into pumpability: printing stock does not make a
squeeze less likely, it makes holding one dangerous. Surfaced as its own flag.

Farmmi at the time of the meme: **37.4M shares outstanding against 1.84M
weighted shares in the last annual report** — roughly 20x dilution since the
filing — on **$804K of cash** against a **$53.1M** annual loss. That company
issues into strength; that is what the strength is for.

**Short interest and institutional ownership are not wired.** Both would be
natural additions. FMP returns an empty array for both on this plan — including
for `GME`, so it is a plan limitation, not a microcap data gap. They are absent
rather than proxied by something else; `/health` reports
`short_interest: false`.

## Data lanes (all public; one optional key)

### Sweep order matters more than sweep breadth

The keyless fallback walks the 10.4k SEC tickers alphabetically and needs about
two days to reach every name — so on a fresh deploy the wrappers that matter
would surface last. With an FMP key the sweep is ordered by **market cap
ascending** and covers the ~2,100 US listings under $250M in about an hour.

One live 200-ticker pass of that ordering found unofficial wrappers the
discovery feeds never carry, including `WHLR` (Wheeler REIT, on Robinhood
Chain, a 21,783-share float) and `PPBT` (Purple Biotech, wrapper minted the
same day). Neither is a call — a wrapper existing says a setup is possible, not
that anything will happen.

| lane | source | auth |
|---|---|---|
| pairs, launches | DEX Screener | none |
| microcap sweep order | FMP `/stable/company-screener` | **optional** `FMP_API_KEY` |
| ticker → company | SEC `company_tickers.json` | none (needs contact in UA) |
| quote, history | stockanalysis.com | none |
| market cap, float | FMP `/stable/profile` | **optional** `FMP_API_KEY` |

Every lane degrades to a logged warning; a dark lane never takes a scan down or
fabricates a call. `/health` reports which optional lanes are live.

`sec.gov` returns **403** to a User-Agent without a contact address — set
`SEC_CONTACT` to a monitored mailbox.

## Schema changes on a persistent disk

`SQLModel.metadata.create_all()` creates missing **tables** and never alters an
existing one, and the Render disk deliberately persists `screener.db` across
deploys — so a column added in code is simply absent in production. `init_db()`
therefore runs `create_all()` **and** an additive `migrate()` that `ALTER`s in
any missing columns. It only ever adds; it never drops, renames or retypes.

This shipped as a real outage on 2026-09-03, and the shape of the failure is
the lesson: `/health` selected only `id`, so it returned **200 with a healthy
registry count of 253** while every endpoint selecting a full model returned
500 on `no such column: candidate.equity_price`. `/health` now reports
`schema_drift` and degrades when the models and the database disagree.

## Why it was returning 500s

Two causes, both fixed, both worth knowing about because they are generic to
"scheduler + SQLite + web worker in one process":

1. **Schema drift** (above) — added columns were absent in the live database.
2. **Lock contention.** Default SQLite gives one writer that BLOCKS readers,
   and a contended lock raises immediately rather than waiting. `rollup()` held
   a single write transaction open across ~5 blocking HTTP calls per ticker for
   131 tickers, so every dashboard request during a scan hit
   `database is locked`. Now: `journal_mode=WAL` (readers proceed during a
   write), `busy_timeout=15000` (contention waits instead of erroring), and
   `rollup()` commits per ticker so the lock window is the write itself rather
   than the network round trip.

Neither was Render. Both were this service.

## Endpoints

```
GET  /                  dashboard (ladder histogram + ranked candidates)
GET  /health            lane status, registry size, job schedule, schema drift
GET  /candidates        ranked, filterable by stage / min_score
GET  /candidates/{t}    one ticker: launches + full ladder history
GET  /registry          every tokenized equity discovered
GET  /pools             every meme pool, deepest first (?ticker=&min_liquidity=)
GET  /pools/{pair}/history   timestamped liquidity readings for one pool
GET  /alerts            RAMPING / CLUSTER transitions
GET  /leadlag           measured lead per rung, WITH sample sizes
POST /scan              full sweep now
```

## Honesty box

- **The lead time is a hypothesis with n=1.** Every number in the ladder table
  above comes from the single Farmmi event. `/leadlag` measures the legs going
  forward and marks any leg with n<5 as `interpretable: false`. Nothing here
  has been backtested, because there is no history to backtest against — the
  venue is weeks old.
- **No backtest, no CAGR, no hit rate.** The `hit_rate` on `/leadlag` counts an
  alert as a hit if the equity later cleared the move gate. It says nothing
  about whether the trade made money after slippage, halts, or the reversal.
- **FAMI round-tripped.** +309% intraday to +29% by early afternoon. Anyone
  filling near the high lost ~65% inside two hours. The screen finds attention,
  which is not the same as finding a profitable entry, and says nothing at all
  about exits.
- **"Credible" means the pool, not the person.** DEX Screener's public API
  exposes no deployer wallet, no LP lock state and no holder distribution, so
  nothing here can tell an organic launch from a well-funded one. What it *can*
  see is depth, two-sidedness, breadth of participation, turnover sanity, and
  whether liquidity is arriving or leaving between snapshots. That is a real
  signal about the pool and no signal at all about who made it.
- **Sub-$1 nanocaps carry mechanics this service does not model**: halts (LULD),
  reverse splits, delisting timelines, dilution into strength, hard-to-borrow
  and buy-in risk on the short side. FAMI must still hold $1 for 10 consecutive
  business days from ~$0.15 to save its listing.
- **Not modeled:** on-chain price history (DEX Screener's public API has no
  OHLCV), deployer clustering, social virality, options, borrow.

## Separation of powers

Keyless decision brain per `CLAUDE.md`. No trading credential, no execution
path. It names a ticker and a window; a human places the trade. Any future
automation routes through `ibkr-executor`.

## Tests

```
cd backend && python -m pytest tests/ -q     # 127 gate tests
```

Gates run against **real captured payloads** (the Robinhood-Chain
`/token-pairs/v1` response for tokenized FAMI, the NVDA/MU searches, the SEC
slice, FAMI's history). The merge-blocking ones: ticker squatters must never
classify as equities, an alert must fire while the tape is flat and must be
suppressed once it has run, and a dark equity lane must never fabricate a call.
