# Crash simulations (results.md addendum 39, 2026-10-07)

What a COVID-type, a 2008-type and a 2000-type crash do to the live book
(four symphonies, 29/29/27/15, POLICY guards), starting from today's balance.

Pure stdlib. Data (Yahoo histories, Composer backtests, intermediate JSONs)
lives outside the repo in `CRASH_DATA` (`_paths.py`; default = the session
scratchpad). Run from this directory in this order:

| step | script | what it does |
|---|---|---|
| 1 | `yh_fetch.py <tickers>` | cache Yahoo daily close/adjclose/dividends per ticker |
| 2 | (inline, see addendum) | fetch the four live trees (`/symphonies/{id}/score`) to `trees.json`; Composer backtests to `composer_bt.json` / `boot_inputs.json` |
| 3 | `replay.py` | tree-simulator fidelity vs Composer (real era), synthetic SVIX/ZVOL, KMLM-flag proxies, COVID in-kind daily replay (4 proxies, from-today holdings variant) |
| 4 | `costfit_proxy.py` | Composer slippage-setting drag fit (intercept + per-turnover) and proxy agreement rates |
| 5 | `vixmodel.py` | term-structure VIX-ETP models (dVIX, dVIX3M, prior-close slope) with OOS check |
| 6 | `hist_replay.py` | HG 2000-02 / 2008 and SLEEVE 2008 daily replays on reconstructed leveraged ETFs; HARV/KMLM 2008 mechanism exhibits |
| 7 | `attrib.py` | per-ticker / per-state attribution; sleeve vol-leg sensitivity |
| 8 | `boot_scen.py` | regime bootstrap along each crash's actual month sequence (house method), both lenses, guards on/off |
| 9 | `book_sim.py` | book-level daily simulation with cap-40 and the sleeve band from $303,140 |
| 10 | `improve.py` | improvement candidates with placebo tests (C1 backwardation block, C2 HG trend gate, C3 PULS->BIL) |
| 11 | `make_chart.py` | self-contained HTML report -> `composer/results/crash-sim-2026-10-07.html` |

Simulator: `../synth/tree_sim.py` (Wilder RSI), subclassed in `replay.py` to
accept >=60 closes for RSI warm-up (young proxies). Missing data -> condition
False, never flat-filled (add. 27 fix list).

Known limits (see the addendum's honesty box): KMLM's regime flag cannot be
reconstructed before 2020-12 (proxies agree 79-90% of days; results shown as
a range); KMLM/HARV vol legs do not exist before 2018, so 2008/2000 book
numbers use the conservative lens (KMLM = HG) or labelled exhibits; every
number is a rule replay on historical prices, not a forecast.
