# nfp-surprise-lab

Does the "bet the market is wrong on non-farm payrolls" trade exist?
**No.** See [`RESEARCH.md`](RESEARCH.md) for the study and honesty box,
`report.html` for the charts.

Headline: on the clean 2013–2019 sample, betting that payrolls beat consensus
wins **40/80 = 50.0%** (p = 1.00). Every out-of-sample rule we tested fails, and no public leading indicator
(ADP, claims, ISM, Challenger, NFIB) tilts the odds either — consensus already
impounds them.
The Lonsdale/Clarium edge was an *information* edge in the BLS
seasonal-adjustment machinery, not a behavioural rule.

## Layout

| file | what |
|---|---|
| `RESEARCH.md` | the study, verdict, and honesty box |
| `report.html` | visual companion (inline SVG, no external libs) |
| `nfp_surprise_study.py` | reproducible analysis — prints every number in the writeup |
| `build_dataset.py` | rebuilds `data/nfp_surprises.json` (`--refetch` re-pulls FMP) |
| `signal_study.py` | do other pre-release indicators tilt the odds? (no) |
| `build_report.py` | renders `report.html` |
| `data/nfp_surprises.json` | 160 releases, 2013-04 → 2026-08, consensus vs first print |
| `data/signals_raw.json` | 5,652 US indicator prints for the signal study |
| `tests/test_gates.py` | 15 merge-blocking gates (data integrity + honesty) |

## Run

```sh
python3 nfp_surprise_study.py       # all statistics
python3 signal_study.py             # leading-indicator tests
python3 -m pytest tests/ -q         # gates
python3 build_dataset.py            # rebuild frozen dataset
python3 build_report.py             # re-render report.html
```

## Gotchas worth knowing

- **FMP's economic calendar truncates wide windows.** It caps rows per response
  and silently drops the oldest part of the range — half-year queries returned
  6 prints/year instead of 12. `build_dataset.py` queries one month at a time.
- **FMP's `previous` field is back-filled** with revised values, so it cannot be
  used to measure revisions as-published. Any revision work needs ALFRED vintages.
- **Pearson lies here.** Several candidate signals look significant on Pearson
  and collapse to zero on Spearman — the correlation was a handful of outliers.
  Rank-check every correlation in this dataset.
- **October 2025 has no standalone release**, and the 2025-11-20 release is the
  *September* report, which FMP mislabels. Both are overridden and gated.

No credentials, no execution path — this is a keyless research lab.
