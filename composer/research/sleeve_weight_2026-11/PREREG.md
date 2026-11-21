# Pre-registration: the sleeve's weight in the book (2026-11-21)

Owner, 2026-11-21: "yes, study the sleeve weight next". The question left open by addendum 59: is the
sleeve's weak rebuilt record (1994-2020: about +10% a year, a 47% fall, no hedge of Holy Grail and KMLM
together) the rebuilt DATA or the RULE, and what does that say about its 31.8% weight? Written before any
of the numbers below was computed. Seen before: addendum 59's sleeve paths by stretch and its hedge table;
addenda 4/4b (the sleeve's design and weights), 54.3 (how to read it).

## Q1. Data or rule?
The sleeve's simulated path (addendum 59's live-rule path, unchanged) is cut by how real its inputs are:

| Era | Dates | What is real |
|---|---|---|
| E1 | 1994-06..2002-07 | nothing: bond signals are mutual-fund proxies, every held fund rebuilt |
| E2 | 2002-08..2011-10 | bond ETFs real (HYG from 2007, PSQ 2006); held funds rebuilt until their 2008-2011 launches |
| E3 | 2011-11..2015-05 | every held fund real except LABD; KMLM signal rebuilt |
| E4 | 2015-06..2020-12-01 | EVERY traded fund real; only the KMLM signal is rebuilt; BOXX is T-bills |
| E5 | 2020-12-02..2023-01 | real KMLM; BOXX is T-bills |
| E6 | 2023-02..2026-11 | all real |

Reported per era: return, volatility, deepest fall, share of days out of cash; a 90% bootstrap interval on
the yearly log return; the same for each half alone (InverseHold, FrontrunBonds, each run as its own
tree); and where the money came from, by fund held.
E4 is the test. Its one rebuilt input is varied to bound it: the addendum-58 synthetic (base), the old
RYMFX stand-in, and the two inverse-fund tests forced always true and always false.
- "The data": E4 looks like the real years (its yearly log return within the real years' 90% interval).
- "The rule or the period": E4 is weak under every KMLM variant (interval below the real years' and
  including zero). Then the report says which funds made the real years' return, and whether those are
  one-off moves (rates in 2022, biotech in 2021-22).
- In between: reported as unresolved, with what would resolve it.

## Q2. Hedge, by era
The sleeve's average return on the worst 5% of days of (a) Holy Grail and KMLM together, (b) each alone,
against its other days, with the mirror (their best 5%), per era and for each half.

## Q3. The weight
Book = sleeve at weight w, the rest split equally between Holy Grail and KMLM, rebalanced daily, for
w = 0, 10, 20, 31.8 (live), 40, 50%. Two controls at the same w: T-bills in the sleeve's place, and
nothing (w = 0). Per era with all three engines (KMLM's paths leave 2020-12..2021-05 uncovered):
return, deepest fall, Sharpe. At the live weight, sleeve against T-bills and against w = 0: difference in
yearly log growth with a 90% paired block-bootstrap interval, and the share of resampled paths on which
the sleeve book's deepest fall is the smaller.
The sleeve "earns its 31.8%" on a stretch if, against T-bills at the same weight, growth is higher with
the interval excluding zero, or the fall is smaller on at least 90% of paths with growth not lower.
- Earns it on E4 and on the real years (2021-06 on): supported.
- On the real years only: supported only by the years it was built on; stated as such.
- On neither: not supported.
No weight is recommended from a surface maximum; any change is the owner's decision, on both brokers.

## Honesty box
The sleeve was assembled in 2026-07 from two community strategies whose own backtests start in 2022-23,
so the real years are in sample for it. Before 2020-12 its KMLM signal is the addendum-58 rebuild (shape
only) and the KMLM engine's own path in the book is on that rebuild too. Rebuilt funds are index times
leverage. Simulated at the close, 5.856 bps per unit of turnover. Nothing here is a forecast.
