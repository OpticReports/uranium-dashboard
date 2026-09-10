# Reproducing the astrology study

    pip install ephem scipy numpy
    # daily bars: Bitstamp OHLC, step=86400, paginated back to 2011-08-18
    python3 build_features.py      # -> features.json (ephemeris per bar)
    python3 corrected.py           # -> corrected_results.json  THE RESULT
    python3 charts2.py             # -> astro_final.png

`corrected.py` supersedes `battery.py` / `final.py` / `analyze.py` /
`rotate_test.py`, which are kept only so the counter-agent's three blocking
findings can be re-derived:

- `battery.py` + `final.py` — the ORIGINAL run, misaligned by +2 days on
  every syzygy mask and using raw |return| for volatility. Its published
  numbers ("full moon p=0.60") are WRONG; see RESEARCH_ASTRO.md honesty
  box items 2-4.
- `rotate_test.py` — a circular-rotation permutation null that is INVALID
  for periodic masks: a 29.5-day mask has only ~30 distinct rotations, so
  5000 rotations are not 5000 independent draws. Every p-value it emits is
  understated. Kept as a worked example of the failure mode.
