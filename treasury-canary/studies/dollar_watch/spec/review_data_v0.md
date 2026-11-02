# Counter-agent review of SPEC v0 — lens: DATA, LOOK-AHEAD, CONTAMINATION (2026-11-02)

**Overall verdict: NOT_PASS — 1 BLOCKING.** D-1's "unseen" premise and the "clean" subset are wrong, and both feed the
dollar-layer licence. **Code equivalence (decel_realtime.py vs build_reference.py scramble_firings): PASS** (N1).

Counts: **BLOCKING 1 · SERIOUS 6 · MINOR 4 · NOTE 5.**
Scripts and outputs: `review_data_work/scripts/` (equiv, replay, vintages, regimes, sclip, clean_share, ref_keys).
No outcome was computed on any D-1 pair or on DXY 1973–2005 (N4 lists exactly what this review touched).

---

## BLOCKING

### B1. The ledger misses most of what was seen of the D-1 currencies, and "clean" is tested on the wrong object
SPEC l.6–7, 18, 36–37, 44, 67–68, 78, 224–225, 241–243, 293, 338–339.

Evidence:
1. **build_reference.py** (the main session read its output; it ships on the panel in `dollar_reference.json`) computes
   the 3/6/12-month change of the 8-pair basket after 14 anchors. Seven of the 8 pairs are D-1 currencies (BRL, MXN, ZAR, INR,
   KRW, THB, MYR). The anchors are the 7 US firings (2008-09-22, 2008-11-06, 2010-06-03, 2011-11-01, 2012-06-07,
   2020-04-09, 2022-07-28) and 7 MOM months (1997-03, 2000-08, 2005-12, 2008-11, 2012-06, 2014-12, 2022-05). The 4
   MOM months before 1995 are null because DEXBZUS starts in 1995. **None of this is in §1.** The spans this adds outside
   the SPEC's windows are 1997-03..1998-03 (the Asian crisis), 2000-08..2001-08, 2005-12..2006-12, 2009-07..11,
   2010-06..2011-06, 2011-11..2013-06, 2014-12..2015-05, 2020-07..2021-04 and 2023-01..07.
2. **Finder B saw full paths, not trough dates.** The committed `figs/fig_funding_leadlag_finderB.png` plots the basket
   daily over 2007-06..2009-06, 2014-07..2016-06, 2018-01..2019-03, 2020-01..2020-09 and 2022-01..2023-03
   (`finderB_chart.py` l.3). `analyze_out.json` adds the extreme date and value, the start value and the 5-year-95th
   alarm for **7** windows, including 2023-02..05 and 2025-01..2026-11 (`finderB_analyze.py` l.47). The SPEC's windows
   (l.224–225) are narrower in 4 of 5 cases and leave out 2 windows.
3. **Aggregates that contain other D-1 pairs:**
   - EME (TWD, SGD) and AFE (AUD, CAD, SEK) extremes in the same 7 windows.
   - DTWEXBGS, the series DECEL was tuned on (2006–2026), has **11 of the 15** D-1 pairs as components: all but ZAR,
     NZD, NOK and LKR.
   - The monthly null ran on TWEXMMTH (`dollar_scoping.py` l.2). That index contains **AUD** as well as CAD and SEK, yet
     AUD sits in the clean set while CAD and SEK are excluded.
4. **Famous EM-FX crises are known in outline.** `crises.csv` dates the baht float (1997-07-02), the peso devaluation
   (1994-12-20), Brazil (1999-01) and the ruble crisis (2014-12-16). The SPEC labels DXY 1973–2005 SEMI for exactly this
   reason (l.19), so these episodes need the same label.
5. **"Raw files deleted" (l.7, 68).** Byte-identical copies of the 8 basket pairs and DTWEXBGS (hash prefixes = `probe_manifest.txt`)
   sit untracked in `data/fred/`, and build_reference.py reads them.
6. **"Clean" is tested on the firing date only (l.224), but S1 depends on (k, k+250].** A firing in 2019-06 counts as
   clean even though its outcome window runs through the charted 2020 window.

Size of the problem (calendar arithmetic only, `clean_share.py`):
- About 625 eligible currency-years in total.
- The SPEC's rule keeps **459** as clean.
- Requiring [k−60, k+250] to avoid the spans in items 1–3 keeps **310**.
- Also treating 2006+ as in-sample for the 11 DTWEXBGS components keeps **266**.
- That remainder is mostly NZD (49), NOK (49), LKR (36) and the managed Asian regimes before 1997 (S3). Firings of
  floating EM currencies after 1997 fall almost entirely in seen spans.

**Fix:**
- (a) Add rows 1–5 to §1. Correct l.6–7, 37, 44 and 338–339: "no outcome statistic computed on unseen series" is false.
- (b) Freeze a per-currency seen-spans CSV, with its sha256 recorded in freeze.json.
- (c) Define a clean firing as one whose [k−60, k+250] index days avoid that currency's seen spans. Add AUD to CAD/SEK.
  Tag 2006+ as IN-SAMPLE (aggregate) for the DTWEXBGS components.
- (d) The blind count reports K_clean and K_global∩clean. The dollar licence needs a pre-registered K_clean minimum and a
  T_clean bar; "T_clean > 0" on a handful of clusters is not a test. T_global, which is almost all seen clusters,
  becomes DESCRIPTIVE.
- (e) Log this review's access (N4).

---

## SERIOUS

### S1. The panel will show Casey D-1-relevant outcomes before he answers the D-1 design questions
SPEC l.386 (step 3); `freeze_template` Q7–Q13.

The untracked `dollar_reference.json` (built for GET /dollar-watch) carries `emfx_pct` for all 14 anchors, and the memo
recommends deploying the panel descriptively now. If it deploys before the freeze, Casey's answers on yield, scaling,
currency set, clean windows and S1 are given with these numbers in view.

**Fix:** strip `emfx_pct` from `firings[].outcomes` and `momentum_ledger`, or hold the deploy, until `freeze.json` is
committed. Otherwise record Casey as a viewer in §1.

### S2. D-2 is not semi-clean: its outcome already exists at monthly resolution
SPEC l.19, 33–35, 112, 285–291, 296–298, 340.

Already computed:
- `decel_monthly_oos.json` gives `dollar_more_rise_pct` for the 10 firings in 1973–2005. That is the 12-month forward
  maximum rise, the monthly S1 quantity, computed on the majors index that shares DXY's core. The orchestrator printed it.
- `dollar_summary.json` `speed_episodes` gives the peak month and real-time turn for 8 fast rises before 2006.
- `crises_metrics.csv` gives `dxy_episode_peak_month` and the intraday-high date.
- `speed_events.csv` has 49 runs before 2006, with `max_month`.

Under §1's own rule (l.41–43, which withdrew the 1973–2007 fit because the NSR table had been seen), D-2 is pseudo-OOS.
Its s, tolerance and yield choices are made with these values within reach. At the blind count, D-2 firing dates plus
this peak calendar reveal most S1 outcomes.

**Fix:** relabel D-2 "SEEN (monthly resolution)" and make it DESCRIPTIVE by removing it from the D-1 × D-2 table. At
most, keep it as a veto, with its expected outcome written down from the monthly table before the run.

### S3. The "15 floating currencies" include roughly 150–200 currency-years of crawl, basket and band regimes that the peg filter misses
SPEC l.18, 92, 165–167, 176–177.

Evidence (`regimes.py` and `sclip.py`; zero-change shares and σ only).

What the ≥50%-zeros filter removes:
- 0% of BRL, MXN, SGD, NOK, SEK and CAD days.
- AUD and NZD in 1973–74 only; KRW 1981–83; THB 1981–84; INR 1974–79 and 1993; MYR 1999–2005.
- 28% of LKR days.

What passes as "floating": AUD 1975–83, NZD 1975–85, NOK and SEK to 1992, INR 1980–92, KRW to 1997-12, THB to 1997-07,
MYR 1973–97, TWD to 1989, SGD throughout (managed), LKR to 2001, MXN 1993–94 and BRL 1995–99.

Consequences:
- Peg breaks enter D-1 as "scrambles": MXN 1994-12, THB 1997-07, KRW 1997-12, BRL 1999-01, NZD 1984–85, SEK and NOK
  1992.
- A σ window that spans a peg pins s at the 0.25 clip: MYR 2005–06 after the de-peg, and KRW 1985 and 1988–91.
- After B1's accounting, these managed spans make up most of what remains clean.

**Fix:**
- Before the blind count, freeze a de jure regime-change table: announced float and peg dates, with sources, all of
  them knowable in real time.
- Eligible days = announced float or managed-float spans. The σ window must lie wholly inside one eligible span and
  start on or after 1973-03.
- Exclude a peg-break day and the 60 days after it, or treat them as their own stratum.
- Use the Ilzetzki–Reinhart–Rogoff de facto codes as a DESCRIPTIVE sensitivity only. They are ex post ("freely falling"
  is defined from realised inflation), so using them as the filter would be look-ahead.

### S4. Survivorship biases D-1 toward PASS, not just toward "milder episodes"
SPEC l.88–89, 351–352.

- The universe is today's H.10 list, and its start dates follow stabilisation: BRL 1995-01 (after the Real Plan) and MXN
  1993-11.
- 1982 is one of the L-narrow squeezes, but no LatAm pair covers it. After the 3-year σ warm-up, the only EM pairs
  eligible in 1982 are the managed INR, MYR and LKR.
- TRY, IDR, ARS and RUB are absent, and VEF is excluded.
- The survivors are the currencies whose scrambles ended, so S1 ("no further +3%·s rise") is more likely to hit in them.

Free daily USD rates exist at the BIS (WS_XRU; availability probed only): TRY from 1950, IDR from 1988, ARS and RUB from
1992.

**Fix:**
- State the direction of the bias in §2.2 and §6.
- Pre-register a DESCRIPTIVE non-survivor panel on the BIS data under the frozen rule, printed beside D-1.
- Consider a stricter bar for the EM row.

### S5. The frozen calendar cannot be applied outside 2006–2026, and the D-1/D-2 calendars are unspecified
SPEC l.138–140, 165, 219, 285.

- §3.2 makes VIXCLS part of the calendar, but VIXCLS starts on 1990-01-02. Read literally, D-1 and D-2 lose 1973–89,
  which holds 5 of the 10 monthly-null firings.
- Tested: the B∩Y and B∩Y∩V calendars differ only on 7 Good Fridays and give identical firings, so VIX does no work in
  the rule.
- Also unspecified:
  - how k is counted in D-1;
  - the "126 US trading days" calendar before 2006;
  - whether the σ warm-up may use 1971–73 data.
- Internal gaps that a 20-index-day roc would silently bridge: TWD 31 days (1991-02-12 to 03-15), THB 16 days (1991-12),
  LKR 13–20 days (1991–92).

**Fix:**
- Remove VIXCLS from the rule's calendar.
- Pin the calendars: D-0 = DTWEXBGS∩DGS10; D-2 = DXY∩DGS10; D-1 = the pair's own valid H.10 days from 1973-03-01;
  cluster gaps counted in NYSE days.
- Add a gap guard: roc20 and σ are undefined across any gap longer than 10 calendar days.

### S6. The admitted post-hoc choices matter first-order, and "alternatives reported, never decide" stops a rescue but not a favourable pre-selection
SPEC l.161–174, 195, 237–238, 343–348; Q7, Q8, Q13.

- Vol scaling moves thresholds about 4× across currencies. Median s runs from 0.81 (TWD) to 2.95 (BRL), so the local
  gate runs from 3.2% to 11.8% and the hit tolerance from 2.4% to 8.9%. Within KRW alone, s runs 0.26–3.78 (p10–p90).
- Scaling and dropping the yield condition therefore reshape the episode set.
- The 3%/250-day hit was chosen on DTWEXBGS 2006+.
- All three choices were made by someone who had seen the basket in 7 windows and 14 anchor spans.

**Fix:** make the variants a one-way robustness gate. A PASS (EM row or dollar licence) also requires T > 0 in each of
the 4 transpositions (scaled or raw, × yield dropped or kept) and with the S1 tolerance at 0.02·s and at 0.04·s. A
variant can remove a PASS but never create one. Print the minimum-T variant beside the primary.

---

## MINOR

### M1. decel_realtime.py never evaluates the last index day — no historical effect, but a real-time one (the coordinator's question)
SPEC l.10, 136, 157–158, 321.

- Replay test (`replay.py`): on data truncated at each of the 7 firing days, the builder fires on that day and the frozen
  script does not. Add one more index day and the frozen script fires, with the same date stamp.
- Historical dates are unaffected. The rule is causal: 0 of 975 future-perturbation runs changed an earlier firing.
- Live, the frozen script reports a firing one index day late. That becomes a full weekly H.10 release when the firing
  day ends a release batch. Example: the 2020-04-13 release ends on Good Friday 04-10, which is off the rule calendar. So
  2020-04-09 surfaces at the 2020-04-20 release under the frozen script, against 2020-04-13 for the builder.
- Effect: only on D-3 observable-date stamps and on whether the panel and the ledger agree.

**Fix:**
- Define DECEL by the §3.2 condition table, "evaluated on every index day k ≥ 80 through the latest available".
- Freeze the harness's pure function (sha256) as the rule. Treat the `len(B)-1` bound as an artefact of the outcome code.
- Add a G1b gate: run on data truncated at each historical firing, the harness fires on the last day.
- Ledger observable date = the date of the H.10 release (weekly, Mondays) that first contains the data date.

### M2. DTWEXBGS is a revised series first published in 2019: pin the vintage, the calendar and σ_B
SPEC l.163, 321, 331.

From ALFRED (`vintages.py`):
- The first vintage is 2019-02-04, so 2006–2019 is a backcast.
- History is revised about once a year: daily changes by up to 5.6 bp, levels by up to 0.5%. The first vintage also
  carried 128 holiday rows that were later deleted.
- Firing dates are identical across all 15 vintages pulled. roc20-max moves by at most 0.3 pp (2020-04-09: 7.7, now
  7.4).
- σ_B moves with the calendar (0.3405% on DTWEXBGS's own days vs 0.3422% on the rule calendar) and with the vintage.
- The repo copy equals the ALFRED 2026-10-26 vintage, but `data/fred/` is untracked, so G1's "committed raw" does not
  exist yet.
- The H.10 bilaterals are not revised: KRW, LKR, INR and THB show 0 differing values between 2014-03-18 and 2026-10-26.

**Fix:**
- Commit `data/fred/` together with SPEC v1.
- Put σ_B in freeze.json as a number, with its vintage, calendar and sd convention.
- Use the same fixture bytes for the blind count and the scored run.
- D-3 rows record the vintage at firing and score on the vintage at window close, keeping both.

### M3. G2 contradicts the definition of E_f (l.211–214 vs l.322)
E_f spans the whole episode, including gate-on days after f, so "E_f uses no forward data" cannot pass. That is fine for
a benchmark. Say so explicitly (E_f is ex post and used only as the benchmark) and exempt it in G2. Otherwise someone will
"fix" the gate by redefining E_f after seeing the data.

### M4. Forward onset rule (l.259): the OFR FSI is model-based
Whether its history is revised was not checked here. Archive the as-published file daily, and compute the trailing
5-year 95th percentile on as-published history only.

---

## NOTE

**N1. Equivalence: PASS** (`equiv.py`, run on the real code).
- Method: decel_realtime.py run as is, using a header-only SP500.csv, since `data/fred` has none. `scramble_firings` and
  `RULE` extracted by `ast` and run unmodified on the current file (index B∩Y∩V).
- Inputs: DTWEXBGS 8080a7d9…, DGS10 55e2559f…, VIXCLS 38e4dee3….
- Unpatched: 6 firings (2008-09-22, 2010-06-03, 2011-11-01, 2012-06-07, 2020-04-09, 2022-07-28).
- Re-arm: 7 firings (the 6 plus 2008-11-06).
- Identical roc20-max, argmax day and roc20 at firing under both implementations, on both calendars (B∩Y: 5,174 days;
  B∩Y∩V: 5,167; the 7 extra days are Good Fridays).
- A fresh decel_realtime.py run equals the committed `decel_realtime*.json` in every compared field.
- The only difference between the two implementations is M1.

**N2.** The §2.2 start dates, the common end date 2026-10-23, and all 16 probe hash prefixes reproduce exactly.

**N3. Price bases.** H.10 is the NY noon buying rate (outside local trading hours for the Asian currencies). DGS10 is set
around 15:30, and DXY is a closing value. This is immaterial for 20-day windows; record it.

**N4. This review's own access, for the ledger:**
- Read: the committed `analyze_out.json` (entries for the basket, EME, AFE, JPY and CHF), `decel_monthly_oos.json` and
  finder B's figure.
- Computed on the 15 D-1 pairs: coverage, gaps, zero-change shares, peg-filter exclusions, trailing-σ ratios, clip
  incidence and calendar-only clean shares.
- Computed firing dates on 15 DTWEXBGS vintages.
- Read `dollar_reference.json` for keys and non-null flags only, never the `emfx` values.
- No returns, gates, episodes or firings on any D-1 pair or on DXY 1973–2005.

**N5. Panel label.** The panel's `variant_live` is re-arm, while the SPEC's primary is unpatched. Label the panel so the
post-hoc variant is not presented as the frozen rule.
