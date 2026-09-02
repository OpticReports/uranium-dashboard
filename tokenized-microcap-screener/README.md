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

## Scores

Four orthogonal axes, kept separate so it is visible which one failed.
`earliness` **multiplies** rather than adds: a setup perfect on every other axis
that has already run scores zero, not "still pretty good".

- **credibility** — pool depth, liquidity/FDV, two-sidedness, breadth, turnover
- **heat** — acceleration, not level
- **pumpability** — cheap, thin, beaten down, small
- **earliness** — how much of the equity move is still ahead

## Data lanes (all public; one optional key)

| lane | source | auth |
|---|---|---|
| pairs, launches | DEX Screener | none |
| ticker → company | SEC `company_tickers.json` | none (needs contact in UA) |
| quote, history | stockanalysis.com | none |
| market cap, float | FMP `/stable/profile` | **optional** `FMP_API_KEY` |

Every lane degrades to a logged warning; a dark lane never takes a scan down or
fabricates a call. `/health` reports which optional lanes are live.

`sec.gov` returns **403** to a User-Agent without a contact address — set
`SEC_CONTACT` to a monitored mailbox.

## Endpoints

```
GET  /                  dashboard (ladder histogram + ranked candidates)
GET  /health            lane status, registry size, job schedule
GET  /candidates        ranked, filterable by stage / min_score
GET  /candidates/{t}    one ticker: launches + full ladder history
GET  /registry          every tokenized equity discovered
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
- **"Credible creator" is a pool-quality proxy, not creator identity.** DEX
  Screener's public API exposes no deployer wallet, no LP lock state and no
  holder distribution. A screen cannot distinguish an organic launch from a
  well-funded one, and this one does not claim to.
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
cd backend && python -m pytest tests/ -q     # 75 gate tests
```

Gates run against **real captured payloads** (the Robinhood-Chain
`/token-pairs/v1` response for tokenized FAMI, the NVDA/MU searches, the SEC
slice, FAMI's history). The merge-blocking ones: ticker squatters must never
classify as equities, an alert must fire while the tape is flat and must be
suppressed once it has run, and a dark equity lane must never fabricate a call.
