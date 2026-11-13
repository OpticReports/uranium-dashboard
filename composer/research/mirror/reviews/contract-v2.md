# Mirror brain <-> executor contract, schema 2 (after reviewer B)

The executor (ibkr-executor/app/mirror.py) is being changed to this contract by the lead; the brain
(composer/scripts) by the brain-fix agent. Field names here are binding on both.

## GET /mirror/session  (X-API-Token)

    {"schema": 2, "kind": "composer-mirror-session", "now_utc": ISO,
     "session": "YYYY-MM-DD" | null,
     "reason": str            # only when session is null for a reason other than weekend / listed holiday
                              # (e.g. the calendar table ends before this year): the executor reports it
     "open_utc": ISO, "close_utc": ISO, "close_et": "16:00",
     "decide_et": "15:54",    # the decision instant in ET
     "decide_utc": ISO}       # = close - shadow_runner.DECISION_MINUTE minutes EXACTLY: the END of the
                              # decision bar (the bar that starts 15:53 and ends 15:54:00 ET), the
                              # instant shadow_runner.minute_price(day, "15:54") reads. No "+ 1 minute".

ISO = "YYYY-MM-DDTHH:MM:SSZ".

## GET /mirror/intents?after=T  (X-API-Token)  -- the only form the executor uses

A PINNED build: the decision AS OF the instant T, reproducible. Whatever second it is computed, it
reads only 1-minute bars ENDING at or before T and no Yahoo last sale later than T (the replay
path's horizon = now = T), so two builds for the same T give the same targets and the live answer
equals `mirror_brain.py --at`.

- T later than the wall clock + 5 s -> 409. Malformed -> 400.
- Until SPY's traded 1-minute bar ending exactly at T is available from FMP -> 503
  {"error": "decision bar not published yet"}; the executor retries every 3 s. (No FMP key at all:
  503 with a reason; the mirror needs minute bars.)
- A complete pinned payload for T is cached by T and never rebuilt (immutable); concurrent
  requests share ONE build (re-check after taking the flight lock).
- The build's own FMP budget is at most ~10 s (not preclose's 90 s); a ticker FMP does not answer
  in time falls back as preview already does and is flagged.

Payload:

    {"schema": 2, "kind": "composer-mirror-intents", "session": "YYYY-MM-DD",
     "pinned": true,
     "asof_utc": T,                    # the instant the decision is as of
     "built_utc": ISO,                 # wall clock when the build FINISHED
     "decision_bar": {"end_utc": T, "spy_utc": ISO, "complete": true},
                                       # spy_utc: end of the bar SPY's price is from; complete: it is T.
                                       # NYSE HALF-DAY (amended 2026-11-13; the brain's shadow_runner.HALF_DAYS):
                                       # complete may also hold with spy_utc BEFORE T, by at most 15 minutes,
                                       # when FMP's SPY bar ending at T has no volume (FMP drops volume on
                                       # half-days) and SPY is priced at its own last trade: only while SPY's
                                       # bars without volume since that trade moved off its price, closed at 2
                                       # or more prices and not 3 or more in a row at one price up to T (amended
                                       # 2026-11-13, round 5: SPY's own, stricter rule), and at least half the
                                       # trees' tickers really traded in the 2 minutes to T (mirror_brain.py's
                                       # docstring). On a full day spy_utc == end_utc == T.
     "replay": false, "close_et": "16:00",
     "engines": {NAME: {"status": "ok" | "unavailable", "symphony", "version", "rule", "corridor",
                        "target": {ticker: weight}, "label", "stale": [...], "caveats": [...],
                        "note": str (when unavailable)}},
     "prices": {ticker: price},        # every ticker of ANY era of the approved manifest (a sleeve may
                                       # still hold a ticker a newer tree dropped), raw tradeable price
     "price_times": {ticker: ISO},     # end of the bar / time of the trade each price is from
     "price_notes": {ticker: str},     # only for estimates (rebuilt from a sibling, or carried)
     "dividends": [{"ticker", "ex_date": "YYYY-MM-DD", "pay_date": "YYYY-MM-DD" | null, "amount": float}],
                                       # cash per share; every manifest ticker; ex_date in
                                       # [session - 10 calendar days, session]; Yahoo events UNION FMP's list
     "splits": [{"ticker", "date": "YYYY-MM-DD", "ratio": float}],
                                       # ratio = new shares per old share (2:1 -> 2.0; 1:5 reverse -> 0.2);
                                       # same window
     "sync": {NAME: {"state": "ok" | "drift" | "none", "approved_version", "approved_sha1",
                     "live_version": str | null, "attested_utc": ISO | null}},
     "quotes": {...}, "problems": [...]}

Engine status rules (brain):
- every engine "unavailable" unless decision_bar.complete (SPY priced from the bar ending at T; on a
  half-day, as amended above) and the feed is alive (breadth rule, measured: see the fix brief; on a
  half-day quotes.breadth gives the real trades ('recent') and the ones counted on bars without volume
  ('leaned') apart, and 'frozen': those weighed and NOT counted, every bar without volume since the
  ticker's last trade at that trade's own price - SPY: or failing its stricter rule. A ticker of the book
  stuck at another price is counted, bounded by the floor of real trades and the 15-minute age; the
  floor is the book's, not each engine's);
- an engine is "unavailable" when its indicators are a session short (a decision ticker in `short`);
- an engine is "unavailable" with a note naming both versions when sync state is "drift"; when the
  state is "none" (no attestation for this session) it trades with a line in `problems`, unless env
  MIRROR_REQUIRE_ATTESTATION is truthy, in which case it is "unavailable".

Without `after` the build is ad hoc: "pinned": false, "decision_bar": null, asof_utc = build start.
For monitoring only; the executor refuses an unpinned payload.

## POST /mirror/attest  (X-Attest-Token == env MIRROR_ATTEST_TOKEN; unset -> 404, wrong -> 401)

    body {"session": "YYYY-MM-DD", "engines": {NAME: {"version": str, "tree_sha1": str, "paused": bool?}}}

Stored in memory for that session. tree_sha1 is the hash of the symphony's canonical LIVE tree, by
the same function the brain applies to the approved tree in use (one shared function).
composer/scripts/mirror_attest.py (run by the Composer-keyed routine, never by the brain) computes
and posts it.

## Executor checks (lead)

schema == 2, kind, pinned is true, replay false, session == today's, asof_utc == decide_utc,
decision_bar.complete with end_utc == decide_utc and spy_utc == end_utc - or, ONLY on an early close
by the executor's OWN calendar (app/blend.py NYSE_EARLY_CLOSES) that the payload's close_et and the
brain's clock (/mirror/session close_utc) also give, spy_utc before end_utc by at most 15 minutes
(HALF_DAY_SPY_MAX_S = the brain's QUIET_TRADE_MAX_S, tied by E11 / composer H10; app/mirror.py
_validate; tests/test_mirror_halfday.py E5, E8) - built_utc not in the future and not before the
instant it decides, each within the 60 s clock-skew allowance (its age is NOT checked: a pinned payload
is immutable, and a restart late in the window trades the one built at the instant), engines and prices
are dicts. Default decide offset 25 s (FMP publishes a bar 10-25 s after it ends). The two calendars
(shadow_runner.HALF_DAYS / NYSE_HOLIDAYS and blend's) are tied by a test on each side (E6; composer H10).
Dividends: a receivable per sleeve from the shares it held at the prior close of the ex-date;
credited from the pay date. Splits: sleeve shares rescaled before the pre-trade check.
