# PRE-REGISTRATION — astrology vs BTC (written BEFORE any result was computed)
Date: 2026-09-04. Data: Bitstamp BTCUSD daily, 2011-08-18..2026-09-04, 5497 bars.
Ephemeris: pyephem 4.2.1, geocentric, UTC at 00:00 of each bar.

## Hypotheses (all two-sided unless noted)
Primary outcome: next-day log return (close-to-close), i.e. the signal is
KNOWN BEFORE the bar it predicts. No same-bar lookahead anywhere.
Secondary outcome: absolute return (volatility), same construction.

Families:
A. LUNAR      - full/new moon day, +/-1d, +/-3d windows; waxing vs waning;
                phase sin/cos regression; 8 phase octiles; perigee/apogee;
                declination extremes.
B. MERCURY    - retrograde vs direct; first/last 3 days of retro; station
                days +/-1; pre- and post-shadow; inferior conjunction.
C. RETROGRADES- Venus, Mars, Jupiter, Saturn retro vs direct.
D. ASPECTS    - all pairs among Sun,Moon,Mercury,Venus,Mars,Jupiter,Saturn
                x aspects {0,60,90,120,180} deg, 6 deg orb.
E. ECLIPSES   - solar and lunar eclipse +/-3d windows.
F. ZODIAC     - Sun sign (12), Moon sign (12).
G. CONTROLS   - day-of-week (7), month-of-year (12): KNOWN-REAL calendar
                effects, used to check the battery can detect a true signal.
H. NULLS      - 30 synthetic periodic variables with periods drawn to mimic
                astrological cycles but with random phase: KNOWN-FALSE, used
                to measure the battery's own false-positive rate.

## Decision rules (fixed in advance)
1. Test statistic: Welch t on mean(on) - mean(off) of next-day log returns.
2. p-values ALSO computed by stationary block bootstrap (block=20d, 10k reps)
   because daily crypto returns are autocorrelated in volatility; the Welch p
   is reported but the bootstrap p is the one that counts.
3. Multiplicity: Benjamini-Hochberg FDR at q=0.10 across the ENTIRE battery
   (families A-F together; G and H excluded from the correction and used only
   as calibration). Bonferroni also reported.
4. A hypothesis is ADOPTABLE only if ALL of:
   a. survives BH-FDR q=0.10 on the full sample, AND
   b. same sign and p<0.10 in BOTH halves of a 50/50 chronological split, AND
   c. effect is economically material: |mean edge| >= 10 bps/day, AND
   d. it survives as an overlay on the live S3/S4 blend, improving CAGR or
      MaxDD without degrading the other by more than 10% relative.
5. If the number of family A-F "hits" at raw p<0.05 is within the range
   produced by family H nulls, the entire battery is declared NOISE
   regardless of which individual tests look impressive.
6. No test will be added, dropped, or re-specified after results are seen.
   Any post-hoc test is labelled EXPLORATORY and cannot be adopted.

## Prior
Astrological bodies have no known causal channel to BTC price. The only
mechanism worth entertaining is REFLEXIVE: enough traders believing a
calendar rule could make it self-fulfilling. That predicts effects on
widely-known dates (full moon, Mercury retrograde) and NOT on obscure ones
(Saturn-Uranus trine). This asymmetry is itself a test and is pre-registered
as such: obscure-aspect hits are evidence of data mining, not of a mechanism.
