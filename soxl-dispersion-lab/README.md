# soxl-dispersion-lab

Teardown of the "short 25% SOXL / long 75% top semiconductor constituents"
dispersion trade: analytical decomposition, survivorship-free backtest,
variant sweep, regime gates, forward scenarios, and an IBKR production spec.

**Verdict in one line:** the book is genuinely market-neutral (net β −0.07) and
the durable edge inside it is ≈1.4%/yr — the leveraged ETF's fee and financing
drag. Everything above that is regime rent. The seed strategy as specified
returns 3.1% CAGR at a −41.5% drawdown and lost money in-sample (≤2019); a 75%
long basket plus cash returned 20.7% at a 0.90 Sharpe.

Read **[REPORT.md](REPORT.md)** for the study, **[SPEC.md](SPEC.md)** for the
production spec. `REPORT.html` is the same study with charts, self-contained.

## Layout

| file | what it does |
|---|---|
| `universe.py` | 108-name candidate universe incl. 20 acquired/delisted names; ICE-style 8%/4% capping |
| `fetch_data.py` | **only** networked script — freezes every input to `fixtures/` |
| `datalib.py` | offline data layer + share-level backtest engine (drift, financing, borrow, margin calls) |
| `signals.py` | regime signals and gate factories, all causally shifted |
| `validate_universe.py` | proves the PIT reconstruction against actual SOXX (corr 0.992, 26/30 membership) |
| `decomposition.py` | Step 1: fee alpha vs variance drag, beta accounting, dispersion alpha, convexity |
| `variants.py` | Step 3: V0–V8 comparison table, gross and net, full/IS/OOS |
| `gates.py` | Step 4: gates conditional + applied, with the overfit screen |
| `validation.py` | sensitivity grid, borrow sweep, block bootstrap, walk-forward, forward scenarios |
| `options_leg.py` | V6 put-replacement — a **model**, not a backtest (no option chain available) |
| `verify.py` | adversarial pass: look-ahead, survivorship, stale marks, reconciliation, monotonicity |
| `make_charts.py` / `make_report.py` | figures and the HTML report |
| `tests/` | merge-blocking gate tests freezing every published number |

## Reproduce

```bash
export FMP_API_KEY=...
python3 fetch_data.py          # ~15 min, writes fixtures/market_data.json
python3 validate_universe.py
python3 decomposition.py
python3 variants.py --split
python3 gates.py
python3 validation.py
python3 options_leg.py
python3 verify.py
python3 make_charts.py && python3 make_report.py
python3 -m pytest tests -q     # 16 gate tests
```

Everything after `fetch_data.py` is offline and reads only `fixtures/`.

## Known gaps

- **SOXL borrow-rate history is not sourced.** It is a swept parameter with a
  solved breakeven (5.4%/yr for the short leg's carry edge; 23.5%/yr for the
  whole book), never an assumed constant. Supplying a real IBKR SLB series is
  the single highest-value input upgrade.
- 14 pre-2016 delisted names have no vendor history (ALTR, NVLS, VSEA, TQNT,
  RFMD, IRF, VTSS, SIMG, ISSI, IDTI, ISIL, NANO, PLXT, SNDK). Measured effect on
  the result: survivorship-free vs survivor-only universes differ by 0.06pp of
  CAGR, so the gap is immaterial for a top-8 mega-cap basket.
- No option chain history (V6 is modelled), no intraday execution, no locate /
  buy-in modelling, no tax.
- 2026 is a partial year (through 2026-08-14).
