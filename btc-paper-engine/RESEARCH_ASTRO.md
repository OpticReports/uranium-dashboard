# Astrology vs BTC — 153 pre-registered tests, 15 years (2026-09-04)

**Verdict: no usable astrological signal.** Nothing survives multiplicity
correction on direction; the repaired volatility test finds astrology BELOW
chance while detecting real effects; every folk trading rule loses to
buy-and-hold. Casey asked specifically about full moons and Mercury
retrograde — both are null.

Ask (Casey): "large Chinese whales are rumoured to trade on astrology…
see if there's patterns or indicators we can use to improve CAGR/DD."

## What was tested

Data: Bitstamp BTCUSD daily, **2011-08-18 → 2026-09-04, 5,497 bars** (186
lunations). Ephemeris: pyephem 4.2.1, geocentric, 00:00 UTC.
Pre-registration in `research/astro/PREREG.md`, written before any result
was computed. 153 astrological tests in 6 families (lunar phase/distance/
declination, Mercury retrograde + shadows + stations + cazimi, other
planetary retrogrades, all 7-body aspect pairs × 5 angles at 6° orb,
eclipses, zodiac signs), plus **19 known-REAL controls** (day-of-week,
month) and **30 known-FALSE synthetic cycles** used to measure the
battery's own false-positive rate.

Two outcomes: direction (return of the event day) and volatility
(GARCH(1,1)-standardised |z|, forecast using only prior data).

## Results

| | astrology (153) | known-REAL controls (19) | known-FALSE nulls (30) |
|---|---|---|---|
| direction, p<0.05 | 9.2% | 10.5% | 0% |
| direction, BH-FDR q=0.10 | **0 survive** | 0 | 0 |
| volatility, p<0.05 | **3.9%** | **36.8%** | 0% |
| volatility, BH-FDR q=0.10 | **0 survive** | **7 survive** | 0 |

The volatility row is the strongest evidence. After repair the test
demonstrably **has power** — it finds large, out-of-sample-persistent
day-of-week volatility effects (Saturday −24.6%, Sunday −15.7%, both
p<1e-5 in each half) — and finds the astrological family at *below*
chance.

**The headline claims:**

| | n | direction | volatility |
|---|---|---|---|
| full moon day | 186 | +64.1 bps, p=0.016 | −3.8%, p=0.42 |
| new moon day | 186 | −43.0 bps, p=0.162 | −4.0%, p=0.44 |
| **Mercury retrograde** | 1056 | **+0.3 bps, p=0.983** | −0.8%, p=0.73 |
| waxing half | 2745 | +8.4 bps, p=0.473 | −3.5%, p=0.082 |
| lunar eclipse ±1d | 68 | +16.8 bps, p=0.783 | +10.3%, p=0.354 |

Mercury retrograde is as close to exactly zero as a 1,056-day sample can
produce. Full-moon day is the only nominal hit in the entire lunar family
and it **does not replicate**: in-sample p=0.013, out-of-sample p=0.392.
Across all 153 tests the IS→OOS edge correlation is **−0.00**.

**Trading it** (realistic time-varying costs, 110→12 bps round-trip):

| strategy | CAGR | MaxDD | vol-matched CAGR |
|---|---|---|---|
| buy & hold | **80.7%** | 84.9% | 80.7% |
| B&H minus mercury retro | 56.7% | 80.9% | 58.4% |
| B&H minus full-moon ±3d | 45.0% | 84.4% | 46.2% |
| hold waxing (new→full) | 30.1% | 79.5% | 30.7% |
| long ONLY on full moon | −1.1% | 41.1% | −33.7% |

Even the nominal +64 bps full-moon effect is not tradable: 12 round trips
a year consume it.

## Honesty box

1. **This is a bound, not a proof of zero.** Median MDE at 80% power is
   ~65 bps/day (91 on full-moon days, 41 on Mercury retrograde). Power at
   the pre-registered 10 bps/day materiality threshold is 0.06–0.10. The
   result is "no effect larger than ~40–90 bps/day", not "no effect".
2. **A blocking bug was found in review and fixed.** The first pass flagged
   the bar containing each syzygy and then tested the *next* day's return —
   the event day + 2. Corrected, full-moon day moved from −16 bps (p=0.60)
   to +64 bps (p=0.016). All numbers here are the corrected run.
3. **The volatility family was initially mis-analysed.** On raw |return| the
   known-false nulls fired at 43%, making the test uninterpretable; the
   first pass wrongly declared the family noise instead of repairing it.
   GARCH standardisation fixes calibration (nulls 0%) and supplies the
   power demonstration above.
4. **Eclipses were initially mis-specified** — the mask used declination
   rather than ecliptic latitude and caught only 2 of 13 real lunar
   eclipses (it was effectively a syzygy-near-equinox mask). Rebuilt on the
   node condition; still null.
5. **A near-hit is disclosed.** `moon_saturn_opp` reached p=0.00045 on
   repaired volatility in the reviewer's pass, with IS/OOS persistence and
   a coherent geometric profile. Under the corrected alignment it falls to
   p=0.085 (rank 15/153); it also fails family-wise multiplicity
   (min-p FWER p=0.26). Not a finding — but it is the closest thing to one.
6. Positive controls do **not** demonstrate power on the *direction*
   outcome (2/19, none surviving FDR). Direction power is argued from the
   MDE calculation, not demonstrated empirically.
7. BH-FDR is mildly anti-conservative for this mask family on volatility
   (pure-null P(≥1 survivor)=0.335), so "zero survive" is weaker than it
   sounds. Test correlation is NOT the cause: Meff = 152.6 of 153.
8. Zodiac longitudes are J2000, not tropical-of-date (−0.35° offset).
   Aspects and lunar phase are longitude differences, unaffected.
9. **Not tested / not modelled**: intraday and session-of-day timing (the
   "Chinese whale" mechanism would most plausibly live here, not in daily
   closes), order flow, funding, options IV, cross-asset replication.
   Chinese New Year was tested post-hoc and is null on direction; its lower
   volatility is a holiday-liquidity effect.
10. **EXPLORATORY, not adopted**: full moon × high trailing volatility is
    +134.7 bps (p=0.003, n=91) vs −5.7 bps in low vol. Post-hoc, 4 cells,
    no correction applied. It is the one variant worth a pre-registered
    re-test on other assets before anyone believes it.

## Method note worth keeping

The known-false nulls did the real work twice: they exposed the broken
volatility test (43% false-positive rate) and then confirmed the repaired
one (0%). A battery without planted nulls would have reported "20
astrological volatility effects survive FDR" — completely wrong. Any future
study in this repo that screens many hypotheses should carry the same
known-true and known-false calibration arms.

Counter-agent review: 3 BLOCKING, 3 MAJOR, 5 MINOR findings, all applied
above. Reproduce with `research/astro/*.py`.
