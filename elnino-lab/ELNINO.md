# ELNINO.md — El Niño commodity engine (2026 event)

Built 2026-08-06. Four layers per the design memo; the event study is the
honest core and it GATES everything else. n=9 strong events (peak ONI ≥1.5,
1957–2023) — every number here is small-sample and sized accordingly.

## Layer 1 — nowcast & alignment (live)

- Weekly Niño3.4 **+2.3°C and rising** (Jul 29); Niño1+2 **+4.1°C** →
  Eastern-Pacific event, 1997-shape, not 2015-shape. ONI onset: **2026-05**
  (AMJ season first ≥0.5). We are ~week 14; historical majors peak weeks
  26–40 (Nov–Jan). Trajectory currently between 1997 and 2023 paths.
- Data: NOAA CPC weekly SST (keyless), ONI ascii. Refresh: weekly Routine.

## Layer 2 — impact calendar (windows that matter from here)

| window | mechanism | market |
|---|---|---|
| Sep–Nov 2026 | Australian wheat season stress | wheat (weak signal — see L3) |
| Oct 2026–Feb 2027 | US winter demand + Gulf wet/cold south | natgas |
| Nov 2026–Jan 2027 | Peru anchovy season (Niño1+2 +4.1 = high risk) | fishmeal→soymeal chain |
| Nov 2026–Mar 2027 | West Africa dry harmattan risk | cocoa |
| Dec 2026–May 2027 | India/Thailand sugar cycle normalization | sugar (short window) |
| Q1–Q2 2027 | Vietnam/Indonesia robusta drought lag | coffee robusta |

## Layer 3 — event study verdicts (excess vs WB Agriculture index, 9 events)

**Robust and NOT priced (the trades):**
- **LONG US natgas** — +6m median +14.0%, 7/9 positive; deregulated era
  (1982+) is 5/5 positive averaging +33%. 2026 realized: −2.4% (score
  −0.85, the board's only real laggard). Failures: 1972 (regulated), 2014
  (shale glut) — supply-regime risk is the honest bear case. Note the
  excess-vs-Ag construction: cleanest expression is long NG / short ag
  basket; outright long NG is the simple version.
- **SHORT sugar (window opens ~+4m, matures +9m)** — 9m median −16.1%,
  only 2/9 positive; last five events clustered −13%…−18%. 2026 slightly
  ahead of path (+4.7% excess) = better short entry. Mechanism (year-2
  supply normalization + India export cycles) is plausible but unproven.

**Robust but CROWDED (no entry):**
- Cocoa: 8/9 positive at 9m (median +17%) — but 2026 already +39% excess in
  3 months, 2.3x the typical full-path move. The market has front-run the
  most famous El Niño trade. Revisit only on a >20% retrace with the event
  still strong.

**Popular narrative, NO robust signal (avoid):**
- Palm oil (1/9 positive at 3m excess — moves with ag complex, no alpha),
  coffee arabica (negative at 9–12m!), rice (noise + 2026 already +23%),
  wheat, soybeans/meal, maize, copper (2026 +15.6% is non-ENSO drivers).
- Coffee ROBUSTA is the one 12m long candidate (+9.1%, 6/9) — watch, don't
  chase; window is Q1-Q2 2027.

## Layer 4 — paper validation book (live from 2026-08-06)

Two positions, paper-only, marked weekly by Routine (Fridays 15:00 UTC):

| # | position | proxy | entry mark | window | target (excess) | kill conditions |
|---|---|---|---|---|---|---|
| 1 | LONG natgas | NG=F (tradable: UNG — contango drag ~1-2%/mo, modeled) | 2026-08-06 close | now → 2027-02 | +25% vs DBA | weekly Niño3.4 < +1.0; or −15% stop; or window expiry |
| 2 | SHORT sugar | SB=F (tradable: short CANE/futures) | 2026-08-06 close | now → 2027-05 | −15% vs DBA | weekly Niño3.4 < +1.0; or +12% adverse; or window expiry |

Weekly mark records: NG=F, SB=F, DBA, weekly Niño3.4/1+2, and Open-Meteo
precipitation anomalies for confirm regions (US Gulf coast; Indian sugar
belt). Thesis upgrades/downgrades logged, never resized mid-flight.

## Layer 3c — wide sweep: the uncrowded universe (2026-08-06)

Same machinery over 23 Pink-Sheet series nobody puts in an El Nino listicle
(ag vs Agriculture index; metals vs Base Metals index; silver vs gold), all
9 strong events plus an EP-flavor subset (1972/82/97/2023, n=4, descriptive).

**Survivors (consistent + mechanism + uncrowded):**

1. **SHORT nickel — the tightest signal in the entire study**: 12m median
   −16.2% vs base metals, **0/8 events positive**; monotone decay from +6m.
   Mechanism: El Nino DROUGHT is good weather for Indonesian/Philippine
   laterite mining (the wet disruptions are La Nina's problem) -> relative
   supply tailwind while peers get Peru-flood squeezed. Instrument problem:
   no clean retail vehicle (LME futures; equity proxies impure) — flagged
   as the signal without a seat.
2. **LONG lauric-oil complex (coconut/palm-kernel) at 12m**: coconut oil
   +24.2% median, 7/8 positive; palm-kernel oil 4/4 at every horizon.
   Mechanism: Philippine coconut-belt drought + typhoon tree damage hits
   copra supply with a 9-15 month tree-stress lag — the market prices palm
   and soy oil, not laurics. Instrument problem: cash markets only.
3. **LONG silver / SHORT gold (the tradable one)**: EP subset +17-22% at
   6-12m (3/4); full sample milder (+5.2 at 6m, 4/8). Mechanism: Peru is
   the world's #1-2 silver producer and EP-event coastal floods hit mines
   and haulage; gold has no Peru concentration -> the ratio isolates the
   supply shock from monetary noise. Fully liquid (SLV/GLD).
   **Added as paper position #3** (entry ratio 0.14333, window to 2027-05,
   +15% target / −10% stop) — explicitly an n=4-grade EP-conditional bet.

Honorable mentions: zinc 7/8 positive at 6m vs base metals (Peru flood
exposure; zinc/copper spread is the pure Peru-vs-Chile expression, futures
only); DAP fertilizer mildly positive 5/7; Tea Colombo EP subset +17-28%
(Sri Lanka drought — real but the instrument is a Colombo auction lot).
Rejected: bananas/shrimp (Ecuador thesis DOES NOT show up — 1-3/8),
Malaysian logs short (0/4 EP at 12m but illiquid), orange (+3m pop 6/8 but
sign-flips by 9m).

## Layer 3b — equities (vs SPY, events 1997/2009/2014/2023, n=3-4)

The insurance intuition INVERTS: El Niño's dominant insurer effect is
Atlantic hurricane suppression (benign cat years), while the California
damage everyone pictures is mostly NOT private-insured (mudslide = earth-
movement exclusion; flood = federal NFIP). Private-lines leakage is auto
comprehensive (flooded vehicles) — real but small.

| ticker | +6m median (pos/n) | +12m median | verdict |
|---|---|---|---|
| ACGL (reinsurer) | +4.9 (3/4) | **+10.7 (4/4)** | only suggestive LONG; watchlist |
| ALL (Allstate) | +3.8 (4/4) | −3.1 (1/4) | 6m pop fades; no trade |
| RNR (cat reinsurer) | −1.4 (1/4) | +0.2 (2/4) | hurricane benefit NOT systematic — cat-pricing cycle dominates |
| MTN (Vail) | +3.3 (2/4) | +5.9 (2/4) | mixed (2023: −24); no signal |
| BG (Bunge) | −5.9 (0/3) | **−22.5 (0/3)** | crush-margin story REJECTED — if anything a fade |

MCY/PGR/TRV/EQT/GNRC: keyless history only reaches ~2012 (2 events) — no
verdict possible; qualitative map only:
- Plausible winners (unbacktested): natgas producers (EQT/AR/RRC — the
  equity expression of the commodity signal), CA repair/aggregates
  (VMC/MLM post-storm rebuild), CA hydro-exposed utilities.
- Plausible losers (unbacktested): GNRC (quiet Atlantic = fewer outage-
  driven generator sales), heating-oil/propane distributors (warm north
  winter), PNW-weighted ski (MTN's Whistler), salmon farmers (fishmeal
  feed-cost spike if Peru anchovy season fails).

Equity verdict: NO paper positions added. n=4 with sector cycles
overwhelming the ENSO signal in most names; ACGL is the single watch
candidate (4/4 at 12m), reviewed at the Layer-4 weekly marks.

## Honesty box

- n=9 events (5 in the modern era for natgas). These are S4-grade
  statistics: suggestive, clustered, and absolutely capable of being wrong.
  Paper first; any real sizing follows the Kelly discipline at heavy
  shrinkage.
- Excess-vs-Agriculture controls common shocks but creates spread
  semantics: "natgas up" historically includes "ag down" — the 1972/2014
  losses show outright NG can diverge badly from the spread.
- The 2026 event could still collapse (1.39 peak-so-far vs 1.5 strong
  threshold — weekly +2.3 says it won't, but ONI is the arbiter).
- Climate drift: 1957 teleconnections ≠ 2026's; shale rewired natgas;
  cocoa 2023-24 was confounded by West African disease.
- Instrument drag (UNG roll, CANE spread) is real and NOT in the study's
  numbers; the paper book marks futures and notes the ETF gap.
