# Finder C — the dollar as crisis predictor: what the literature establishes, with numbers

Date: 2026-11-02. Lens: academic / central-bank literature on the global dollar cycle + a free-data
reality check of the Johnson "band" claims. Everything numeric below was read from the paper
text in `raw/*.txt` (pdftotext) or computed by `scripts/*.py` from files in `raw/data/`. Items
marked UNVERIFIED could not be opened (IMF site is Akamai-blocked from this container; I did not
circumvent it) and rest on abstracts / secondary summaries.

Status: NOT yet counter-agent reviewed (CLAUDE.md rule). Spot-check list at the end.

Chart: `dxy_band_crises.png` (DXY with band + 16 onsets; 12m momentum; gold; US 10y).

---

## 0. Headline (cut to the meat)

1. The strongest result in the literature is CAUSAL and CONTEMPORANEOUS-TO-LAGGING: a broad-dollar
   appreciation shock is followed by EM output/investment/credit declines over 4–8 quarters
   (Obstfeld-Zhou: 10% shock → EM GDP −1.5% at ~8q; Hofmann-Park: 1ppt shock → EM growth
   −0.3ppt, growth-at-risk −0.6ppt after 1y). That is a dollar→EM-recession channel, NOT a
   dollar→crisis-onset early warning.
2. The dollar's rise in a crisis is mostly the crisis itself (safe-haven / convenience-yield demand:
   JKL, Kekre-Lenel, LMNS). On free monthly data, 9 of 16 onsets since 1973 show "USD up + US 10y
   DOWN" in the 3 months into onset — the flight-to-safety signature — and the dollar does NOT lead
   the VIX or the TED spread (Granger F ≈ 0.05–0.6; VIX→DXY borderline instead).
3. Among crisis early-warning indicators, the REAL exchange rate (deviation from trend — a
   country's own overvaluation, not DXY) has the best noise-to-signal ratio ever reported
   (KLR 0.19; Edison re-run 0.22–0.26) but calls only ~44–57% of crises; the dollar index itself is
   not a KLR indicator, and "US interest rate" / "oil" as global indicators had NSR ≈ 0.97–0.99
   (useless).
4. Johnson's "16 excursions, 75% ended in crisis": NOT reproducible and he himself calls the band
   "ad hoc ... 105 to 85 ... I don't know if that's the exact number". On a synthetic DXY
   (1973–2026) and a 16-event frozen list: 22 excursions, 9 (41%) coincide with/precede an onset
   within 12m, against a 31% base rate for any random month. Nothing survives the base rate
   unless you also require the excursion to be a large, multi-year one (1981–86, 2000–02,
   2006–08, 2010–14, 2022), which gives 5 of 5 — but N = 5.
5. "Dollar rises in every crisis / gold falls in every crisis": FALSE on monthly data. DXY was
   higher 3 months after onset in 8/16 cases; gold was lower 3 months after onset in 5/16.
   Both are true for the two genuine dollar-funding squeezes (Sep-2008, Mar-2020 on daily data)
   and for 2022 — i.e., they describe a SUBTYPE of crisis, not crises.
6. What a defensible panel can show: dollar level/percentile vs band, 12m-momentum percentile
   (the one dollar signal with NSR < 0.5 in-sample: >+10% in 12m → P(onset in next 12m) 48% vs
   29% base, but on ~5 independent episodes), the dollar–yield sign quadrant, BIS USD-credit
   growth, swap-line usage, and crisis-conditional base rates with N shown. It cannot show a
   crisis date or a probability for "the next crisis".

---

## 1. Literature with numbers

Format: claim | sample | method | effect size | OOS evidence | free data to replicate | source.

### 1.1 Dollar → EM real economy (the "dollar cycle" papers)

**Obstfeld & Zhou (2022) "The Global Dollar Cycle", BPEA Fall 2022, 361–427** (read: published
PDF https://www.brookings.edu/wp-content/uploads/2022/09/BPEA-FA22_WEB_Obstfeld-Zhou.pdf ; NBER
w31004 https://www.nber.org/papers/w31004)
- Claim: exogenous dollar appreciation (vs advanced-economy currencies) is contractionary for EMDEs
  over and above US monetary policy and US financial conditions.
- Sample: 26 EMDEs (~90% of 2021 EMDE GDP), quarterly, late-1990s–2019.
- Method: panel local projections (Jordà) of cumulative change in y from t−1 to t+h on Δ(log Fed
  H.10 "major currencies" AE dollar index), controlling for effective fed funds / Wu-Xia shadow
  rate and the Chicago Fed ANFCI, country FE, lags. State-dependent LPs for pegs vs floats,
  inflation targeters vs not, high vs low external dollar liabilities (Bénétrix et al. data).
- Effect sizes (Fig. 8, 10% AE-dollar appreciation): real GDP trough ≈ −1.5% vs trend after ~8
  quarters; investment falls; GDP-deflator inflation falls for 4q; immediate and continuing
  bilateral depreciation; equity prices fall sharply; EMBI spread rises; domestic credit falls;
  policy rate rises slowly (significant only after several quarters). Variance decomposition
  (fn 27): dollar shocks explain 25–30% of consumption/exports/output variance after 2q, ~20% of
  equity-price variance after 8q. Worse for pegs, non-targeters, and high-dollar-liability
  countries (Figs 9–11; high-exposure countries: bigger GDP fall after ~4q, steeper equity fall,
  persistently higher EMBI).
- Table 1 (annual correlations of broad-dollar % change with growth): EMDE output growth −0.63
  (1980–2021), world trade volume −0.32 (−0.61 in 2001–21), world investment/GDP −0.45, AE output
  −0.05 (−0.36 post-2001).
- Dollar vs Fed (Section III, Tables 2–3, 1999–2021 quarterly): 1 sd rise in the excess bond
  premium → 31bp same-quarter dollar appreciation; 1 sd in log VIX → 4.4bp (insignificant;
  7.2bp post-crisis); a 10bp rise in the 1y Treasury differential → 40.7bp appreciation over the
  year; a 10bp rise in the Treasury (convenience-yield) basis → ≈97bp same-quarter appreciation
  (Table 3, col 1). I.e., the dollar is driven by risk premia and safe-asset demand far more than
  by the VIX.
- OOS: none (LP impulse responses, in-sample).
- Replicate: FRED DTWEXAFEGS (AE index, 2006–) spliced to TWEXMMTH (1973–2019); FEDFUNDS; ANFCI;
  EM GDP from IMF IFS.

**Hofmann & Park (2020) "The broad dollar exchange rate as an EME risk factor", BIS QR Dec 2020**
(read: https://www.bis.org/publ/qtrpdf/r_qt2012b.pdf)
- 21 EMEs, 1990Q1–2019Q4, panel LP + quantile LP (growth-at-risk). Controls: VIX, US GDP, PMI,
  Δ10y and Δ1y Treasury, commodity prices, country financial conditions, 3y credit growth.
- 1ppt broad-dollar appreciation shock → cumulative EME GDP growth −0.3ppt after 1y; 5th-percentile
  growth (GaR) −0.6ppt; investment growth-at-risk hit hardest; even export growth falls. Effects
  fade after ~6 quarters. Dollar effect holds "over and above the VIX".
- Replicate: FRED DTWEXBGS/TWEXBMTH, VIXCLS, EM GDP.

**Shousha (2019) Fed IFDP 1258** (read) — SVAR: dollar appreciations lead to declines in EME GDP,
investment and private credit; transmission via financial conditions not net exports; worse
with higher dollar-credit exposure and lower monetary credibility. (No single elasticity quoted
in text; Hofmann-Park note their linear results are "similar".)

**Avdjiev, Bruno, Koch & Shin (2018) BIS WP 695 "The dollar exchange rate as a global risk factor:
evidence from investment"** (read: https://www.bis.org/publications/working-paper-695-...pdf)
- SPVAR, EMEs, 2002Q1–2015Q3: a 1 sd dollar appreciation vs local currency → −5ppt growth of
  gross capital formation next quarter, significant for >2 years. Firm-level: a 1ppt dollar
  appreciation cuts capex/assets by 0.003 (5.5% of mean) more in finance-dependent industries.

**Druck, Magud & Mariscal (2015) IMF WP 15/179 "Collateral damage"** — UNVERIFIED (IMF blocked).
Abstract: 1970–2014; dollar appreciation cycles dampen EM real GDP growth mainly through a
commodity-income channel. Cited by Obstfeld-Zhou as the trade-channel complement.

**Erik, Lombardi, Mihaljek & Shin (2020) BIS WP 847 "The dollar, bank leverage and real economic
activity: an evolving relationship"** (read) — the broad dollar is a nowcaster of global PMI
(Table 1: PC of equities/spreads/VIX/dollar, R² 0.936 for 2/1998–10/2019; coefficient on the
financial PC 0.200 pre-GFC vs 0.077 post-GFC — the link weakened); IRFs: dollar appreciation →
global PMI ex-US and world trade growth decline. Nowcast, not forecast.

### 1.2 Dollar → bank leverage, CIP basis, EM bond spreads (the BIS "risk-taking channel")

**Bruno & Shin (2015) "Cross-border banking and global liquidity", RES; BIS WP 458** (read)
- 46 countries, quarterly from 1996Q1, panel FE; dep. var = quarterly log change in BIS
  bank-to-bank cross-border claims. Table 1: Global leverage (US broker-dealer) 0.0043***; Δlog
  real exchange rate (price of dollars) −0.22*** (local real appreciation in q−1 → faster bank
  inflows in q→q+1); R² ≈ 0.07–0.10. Theory: dollar appreciation = global financial tightening.
- OOS: none. Replicate: BIS LBS Table A6 (bis.org SDMX API works from here, see §1.8).

**Avdjiev, Du, Koch & Shin (2019) "The dollar, bank leverage and deviations from covered interest
parity", AER:Insights; BIS WP 592** (read)
- Daily, 10 currencies vs USD, Jan-2007–2016. Table 2: a 1ppt broad-dollar appreciation →
  3m cross-currency basis −2.6bp (−2.1bp with controls); daily sd of basis ≈ 7bp; the bilateral
  rate is small/insignificant once the broad dollar is in. 5y basis: same sign (quarterly).
  SPVAR 2002Q1–2015Q3: dollar appreciation → decline in USD cross-border bank lending. Dollar
  beta priced in CIP returns: +1 beta → +11bp (3m) / +26bp (5y) expected return. The "triangle":
  dollar ↑ ⇒ basis wider ⇒ dollar lending ↓.
- Replicate: basis needs Bloomberg/Refinitiv — NOT free. Proxies: Fed swap-line usage (FRED
  SWPT), TED (FRED TEDRATE to Jan-2022), STLFSI4.

**Hofmann, Shim & Shin (2016) BIS WP 538 "Sovereign yields and the risk-taking channel of currency
appreciation"** (read): 20 EMEs, monthly; 1% appreciation of local currency vs USD → EM bond-fund
flows +4.7bp of NAV, FC sovereign spread −1.9bp, LC spread −1.7bp (all 1%); it is the BILATERAL
dollar rate, not the NEER, that matters (Table 2); a 1 sd FX move (2.5%) moves spreads 3.75–7.5bp.
**Hofmann, Shim & Shin (2022) BIS WP 1031** (read): 1% appreciation shock of the broad USD →
EM LC bond spread +11bp at peak vs +5bp for the bilateral rate.

**Shin (2016) "The bank/capital markets nexus goes global", BIS speech 15-Nov-2016** (read:
https://www.bis.org/speeches/20161114-bankcapital-markets-nexus-goes-global.pdf): "the barometer
of risk appetite and leverage has slipped from the VIX, and has passed to the dollar"; "When the
dollar is strong, risk appetite is weak". This is the origin of the "dollar as barometer" line —
it is a contemporaneous-indicator claim, explicitly NOT a lead claim.

### 1.3 Dominant currency paradigm (trade channel)

**Gopinath, Boz, Casas, Díez, Gourinchas & Plagborg-Møller (2020) "Dominant Currency Paradigm",
AER; NBER w22943** (read) and **Boz, Gopinath & Plagborg-Møller (2017) NBER w23988** (read)
- 2,500+ country pairs, 91% of world trade, 1989–2015. A 1% USD appreciation against all
  currencies predicts a 0.6% decline in rest-of-world trade volume within a year; contemporaneous
  dollar-rate volume elasticity −0.19 vs −0.03 for the bilateral rate; dollar invoicing share
  explains 15% of the cross-pair variance in dollar pass-through.
- **Georgiadis & Schumann (2019/2021) ECB WP 2308** (read): 46 economies 1995–2018; output
  spillovers from USD appreciation decline with an economy's export-minus-import dollar-invoicing
  share; robust to US demand, US MP and exogenous FX shocks as triggers.
- Replicate: IMF DOTS/WEO trade volumes; invoicing shares from Boz et al. (2020) IMF dataset.

### 1.4 Safe haven / convenience yield: the dollar's rise IS the crisis

**Jiang, Krishnamurthy & Lustig "Foreign safe asset demand and the dollar", JF 2021; NBER w24439**
(read): a rise in the Treasury convenience yield (Treasury basis) appreciates the dollar; IV: a
10bp FFR surprise widens the average Treasury basis by >5.8bp (first stage) and the induced basis
move appreciates the dollar. Foreigners' extra convenience yield on Treasuries ≈ 2.06pp of real
return in their PPP calculation (fn 7).
**JKL "Dollar safety and the global financial cycle", NBER w27682 (rev. 2023; RES 2024)** (read):
model with one ingredient — international demand for safe dollar assets — matching dollar
borrowing/mismatch, exorbitant privilege, US MP spillovers and the dollar as a global risk factor;
"the global financial cycle is a dollar cycle".
**Kekre & Lenel "The flight to safety and international risk sharing", NBER w29238 (rev. 2024)**
(read): a flight-to-safety shock (rise in demand for safe dollar bonds) generates dollar
appreciation AND a global recession simultaneously — the dollar is the symptom.
**Lilley, Maggiori, Neiman & Schreger "Exchange Rate Reconnect", REStat 2022; NBER w26046** (read;
note: the title "Exorbitant privilege in the time of COVID" in the brief does not exist under
these authors — w27772 is Broner et al.; LMNS's reconnect paper is the one meant):
rolling 5y/10y regressions of broad-dollar changes on risk measures (VIX, credit spreads, US
foreign-bond purchases…): R² a few % pre-2007 (peaks 5–10%), 10–60% after 2007 (5y windows peak
30–70% in 2007–12); 1 sd fall in corporate credit spreads ↔ 1.25% dollar depreciation. Diebold-
Mariano: only some measures beat a random walk at 5%. Comovement is CONTEMPORANEOUS.
- Takeaway for the panel: in-crisis, "dollar up + US yields down + credit spreads up" is one
  factor (safe-asset demand). Any lead the dollar shows in that regime is lead over the OTHER
  symptoms, not over the cause.

### 1.5 Early-warning literature that uses exchange rates / dollar debt

**Kaminsky, Lizondo & Reinhart (1998) "Leading indicators of currency crises", IMF Staff Papers
45(1)** — the MPRA scan (https://mpra.ub.uni-muenchen.de/6981/) is image-only; numbers below are
KLR's own, as reproduced in **Edison (2000) Fed IFDP 675 "Do indicators of financial crises work?"**
(read: https://www.federalreserve.gov/pubs/ifdp/2000/675/ifdp675.pdf, Table 5 "Original KLR
Results" and Edison's re-run/benchmark).
- Design: 20 countries (KLR) / 28 (Edison), monthly 1970–1995, 72 / 89 currency crises (exchange
  market pressure index > mean + 3 sd), 24-month signal window, threshold = percentile (10–20%)
  minimising noise-to-signal ratio NSR = [B/(B+D)]/[A/(A+C)].
- KLR original: real exchange rate (deviation from trend) NSR 0.19, P(crisis|signal) 0.67, share
  of crises called 0.57; exports NSR 0.42 / called 0.85; M2/reserves 0.48 / 0.80; reserves 0.57 /
  0.75; equity prices 0.47 / 0.64; M2 multiplier 0.61; output 0.52; domestic credit/GDP 0.62;
  real interest rate 0.77; bank deposits 1.2; lending/deposit 1.69; imports 1.16; real interest
  differential 0.99. Edison benchmark (89 crises) adds global variables: US interest rate NSR
  0.97, G-7 output 0.58, oil prices 0.99 (all weak); Δ short-term debt/reserves NSR 0.40 and
  called 92% but on 12 crises.
- OOS (Edison Fig. 4, Dec-1996): highest probabilities Pakistan, S. Africa, Brazil, Colombia,
  then Malaysia, Philippines, Turkey, India; Indonesia and Korea LOW. Verdict in text: "the
  performance of the early warning system is mixed. The model gives rise to many false alarms".
- Replicate: BIS REER (RBxxBIS on FRED from 1994), IFS reserves/M2/exports.

**Bussière & Fratzscher (2002/2006) ECB WP 145** (read: https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp145.pdf)
- 32 EMEs, monthly 1993–2001, 12-month horizon, pooled logit then multinomial logit (tranquil /
  pre-crisis / post-crisis) to remove "post-crisis bias". Table 5 (32 countries): obs correctly
  called 82.4%, crises called 57.8%, false alarms 57.3% of alarms, P(crisis|alarm) 42.7%,
  P(crisis|no alarm) 7.7%. For comparison IMF-KLR (Berg-Borensztein-Pattillo 2001, Table 8):
  crises called 59.8%, false alarms 70.3%, P(crisis|alarm) 29.7%. REER overvaluation coef
  0.128*** (Table 3).
- OOS (Table 18): model estimated to Dec-1996 gives Indonesia 0.48, Philippines 0.68, Thailand
  0.34, Malaysia 0.31 (all > 20% = alarm), Korea 0.17 (missed), Colombia 0.69 and Russia 0.33
  (early alarms, crises came 1998); Dec-1997: Russia 0.88, HK 0.71, Brazil 0.36, Chile 0.37;
  Dec-2000: Turkey 0.91 (alarm since Nov-1999), Argentina 0.13 (missed), Mexico 0.56 (false).
- Replicate: not with dollar data alone — these are country-fundamentals models.

**Gourinchas & Obstfeld (2012) "Stories of the twentieth century for the twenty-first", AEJ Macro;
NBER w17252** (read)
- 1973–2010 panel logit, crisis within 3 years. EMEs (Table 4): 1 sd rise in domestic credit/GDP
  (≈ +9pp) raises the 3-year probability of default +11.5pp, banking crisis +6.4pp, currency crisis
  +9.4pp; 1 sd REAL DEPRECIATION (≈19%) LOWERS them by 4.3 / 4.7 / 2.5pp (so real appreciation
  raises crisis odds); +5pp short-term debt/GDP → default +6.4pp; output gap +4% → banking +7.3pp;
  reserves marginal effect −1.099 vs credit +0.468 (banking, 3y). AEs: 7% real depreciation cuts
  currency-crisis probability 8.8% → 3.3%; credit +23% of GDP raises it 8.8% → 11.9%.
- Pseudo-OOS: predicted EME currency-crisis probability rose from 9.3% in 2003 into 2007 (text,
  §4). Replicate: WB/IFS credit, BIS REER, IFS reserves.

**Catão & Milesi-Ferretti (2014) "External liabilities and crises", JIE; IMF WP 13/113** (read via
NBER-conference copy https://conference.nber.org/conf_papers/f69839/f69839.pdf)
- 70 countries 1970–2011, external crises (default/rescheduling or large IMF program), probit with
  1-year lags. AUROC: NFA/GDP alone 0.73; split into debt/equity/FDI 0.75; + reserves 0.76;
  + income vs US 0.82; + current account 0.86; + REER gap 0.88; + VIX 0.89; + fiscal gap 0.90.
  Threshold: risk rises sharply when net foreign liabilities exceed ~50% of GDP and when NFA is
  ~20pp below the country's own mean. In-sample at the max-signal/noise 10.5% cut-off: 42/61
  crises called, 5% false-alarm share, 94% correct. OOS 2008–11 (Table 10): Greece-2010 92%,
  Portugal-2011 56%, Latvia-2008 21%, but Hungary-2008 0%, Ecuador-2008 0%, Turkey-2008 2% — i.e.
  the model misses dollar-funding/contagion crises in countries without large net liabilities.
- Replicate: Lane–Milesi-Ferretti EWN database (free), IFS.

**Reserves**: Obstfeld, Shambaugh & Taylor (2010) NBER w14217 (read): reserves explained by M2,
financial openness and peg (financial-stability motive); 2008: low reserves/M2 ↔ larger
depreciations. Aizenman, Cheung & Ito (2014) NBER w20386 (read): countries whose reserves were
BELOW the model's prediction were more vulnerable to external shocks (prediction-error metric).
Aizenman & Hutchison (2012) NBER w16260 (downloaded; pdftotext partial): EMP absorbed by reserves
vs depreciation in 2008–09.

**Growth-at-risk**: Adrian, Boyarchenko & Giannone (NY Fed SR 794 → AER 2019) (read): tighter
NFCI lowers the 5th percentile of US GDP growth far more than the median (quantile regression,
skewed-t fit); IMF GFSR Oct-2017 Ch.3 applies this — the IMF WP copies (Adrian et al. 18/180,
Prasad et al. 19/36) are UNVERIFIED (blocked). Hofmann-Park (§1.1) is the dollar version.

### 1.6 Dollar funding stress: basis, swap lines, off-balance-sheet dollar debt

**Du, Tepper & Verdelhan (2018) "Deviations from covered interest rate parity", JF; NBER w23170**
(read): post-2008 CIP deviations are persistent: average |basis| 24bp (3m) and 27bp (5y) over
2010–16; JPY 5y ≈ −90bp; DKK 3m −61bp avg post-crisis; 3m basis reached −200bp in 2008; arbitrage
profits 11–19bp after costs; quarter-end spikes tied to bank balance-sheet regulation.
**Cerutti, Obstfeld & Zhou (2019/2021) "CIP deviations: macrofinancial determinants", JIE; NBER
w26129** (read): post-GFC basis co-moves with VIX (higher VIX → more negative basis), broad dollar
strength, intermediary leverage proxies, and regulation; year-ends add ~260bp spikes, other
quarter-ends ~20bp.
**Bahaj & Reis (2022) "Central bank swap lines", RES 89(4)** (read: https://personal.lse.ac.uk/reisr/papers/22-cbswaps.pdf)
- The swap-line rate puts a CEILING on CIP deviations (Prop. 1); sterling-dollar ceiling 100bp
  Mar-2009–Nov-2011, 50bp after; the Nov-2011 50bp cut lowered the mean CIP quote by 0.28pp and
  the top decile by 0.59pp relative to uncovered currencies (Table 1); swap-line access lowers ex
  post bank borrowing costs and raises dollar lending. This is the clean "crisis ending" mechanism.
- Free data: FRED SWPT (central bank liquidity swaps, weekly, 2002–). Peaks: $583bn Dec-2008
  (fell below 10% of peak by Oct-2009); $449bn May-2020 (<10% by Oct-2020); $11bn Oct-2022; $1bn
  Dec-2023; $0.16bn on 2026-10-28. DXY peaks: Feb-2009 (2 months AFTER the swap peak); Apr-2020
  (1 month BEFORE); Oct-2022 (same month). Swap usage is therefore a lagging CONFIRMATION that
  the squeeze is over, not a timing tool.
**Borio, McCauley & McGuire (2022) "Dollar debt in FX swaps and forwards: huge, missing and
growing", BIS QR Dec 2022** (read: https://www.bis.org/publ/qtrpdf/r_qt2212h.pdf)
- Definition: dollar payment obligations embedded in FX swaps, forwards and currency swaps
  (the forward leg is a dollar debt), recorded off-balance-sheet and absent from debt statistics.
  Numbers (end-June 2022, from the 2022 Triennial): all-currency outstanding $97tn (vs $67tn in
  2016; ≈ world GDP $96tn, 3× world trade); with USD on one side $85tn ("$80 trillion-plus");
  non-banks outside the US owe $26tn (vs $17tn in 2016), DOUBLE their $13tn on-balance-sheet dollar
  debt; non-US banks owe $39tn vs $15tn on-balance sheet; >3/4 matures within 1 year; turnover
  ≈ $5tn/day (Apr-2022). 2017 precursor (BIS QR Sep-2017, read): $58tn outstanding end-2016,
  missing non-bank dollar debt "approaching, and probably exceeding, the $10.7tn" on-balance-sheet.
  No 2024/25 update found (next Triennial = 2025; search returned nothing newer).

### 1.7 Gold in crises

**Baur & McDermott (2010) "Is gold a safe haven? International evidence", JBF 34(8); IIIS DP 310**
(read: https://www.tcd.ie/triss/assets/PDFs/iiis/iiisdp310.pdf)
- 1979–2009 daily/weekly/monthly, 13 stock markets; quantile-dummy regressions. Gold is a hedge
  and strong safe haven (negative conditional correlation at 1–5% tails) for US and major European
  markets, NOT for Australia, Canada, Japan or BRICs; 7/13 markets strong-form on daily data.
  Crisis windows (20 trading days from the start): 1987 crash — strong safe haven for US/Canada,
  weak elsewhere; Asian crisis Oct-1997 — NO safe-haven effect anywhere; GFC from 10-Sep-2008 —
  strong safe haven for most developed markets. Gold–world-stock correlation 0.35 (1979–2009) →
  −0.19 (from Aug-2007) → −0.42 (from Sep-2008); gold–GSCI 0.55 → 0.20 → −0.32. "Gold is not a
  safe haven for extreme levels of global uncertainty."
- My free-data check (World Bank CMO monthly gold, London PM fix avg; `scripts/analysis.py`):
  gold −3m..onset negative in 10/16 onsets; onset..+3m negative in 5/16; largest 6-month
  drawdowns after onset: Asia-1997 −10.9%, Taper-2013 −9.8%, Lehman-2008 −8.3% (monthly averages;
  daily peak-to-trough Mar–Oct 2008 was ≈ −30%), Black-Monday −5.0%; ZERO drawdown in 1982, 1998,
  2010, 2020 (monthly; daily gold fell ≈12% 9–19 Mar 2020 then recovered within the month), 2023.
  Gold–DXY monthly log-change correlation −0.37 over 1973–2024, by decade −0.26 (1970s), −0.44,
  −0.27, −0.47, −0.39, −0.45 (2020s): there is NO regime where it turns positive on a decade
  average. Conclusion: gold sells off in dollar-LIQUIDITY squeezes (2008, 2020 intramonth, 2013
  taper) and rallies in solvency/inflation crises (1974, 1982, 2010, 2023).

### 1.8 The "band" idea — any academic analogue?

- There is no academic threshold on a NOMINAL dollar index. The closest instruments are (i) KLR's
  real-exchange-rate deviation from trend (a COUNTRY's own REER, percentile threshold ~10%), (ii)
  Gourinchas-Obstfeld's REER gap in a logit, (iii) Catão-MF's REER gap (adds 0.02 AUROC), (iv)
  the IMF External Balance Assessment (EBA) REER-gap model (country-level norms; UNVERIFIED — IMF
  site blocked), (v) BIS REER indices (FRED RBUSBIS: US real broad EER, 1994–; value 108.25 in
  Jul-2026 vs 1994 base 88.7). All are about a currency being over/undervalued relative to its own
  fundamentals, not about a global tolerance band.
- Johnson's own statement (Monetary Metals podcast transcript, fetched 2026-11-02:
  https://www.monetary-metals.com/insights/podcasts/brent-johnson-how-long-can-dollar-dominance-last/):
  "we've kind of ad hoc set the band at 105 to 85 ... I don't know if that's the exact number. I'm
  not going to die on that hill". No count of excursions and no 75% figure appears in that
  transcript, in the ZeroHedge 8-Jun-2026 write-up, or in any search hit; the 16/75% statistic is
  UNVERIFIED and I could not find its source.
- Reproduction (`scripts/band_test.py`, synthetic monthly-average DXY from FRED bilaterals with
  ICE weights, spliced at 1999 — checkpoints: Feb-1985 158.4, Mar-2008 72.4, Sep-2022 110.7,
  Sep-2026 100.0; frozen 16-onset list in §3.1):

  | band | excursions | with onset during or ≤12m after | base rate P(onset ≤12m from any month) | months in band |
  |---|---|---|---|---|
  | 85–105, any length | 22 | 9 (41%) | 31% | 62% |
  | 85–105, ≥3 months | 14 | 8 (57%) | 31% | 62% |
  | 85–105, 24m window | 22 | 15 (68%) | ≈50% | 62% |
  | 80–110 | 14 | 9 (64%) | 31% | 81% |
  | 85–100 | 27 | 12 (44%) | 31% | 49% |
  | 90–105 | 25 | 10 (40%) | 31% | 47% |

  Share of onsets with DXY outside 85–105 at some point in the prior 12m: 11/16. The five big
  excursions (1981–86 above, 2000–02 above, 2006–08 below, 2010–14 below, 2022 above) all contain
  or precede an onset — but every 5-year window since 1973 contains an onset, so this is not
  evidence. Base-rate inflation explains most of any "75%".

### 1.9 BIS USD-credit data (free; the "re-/de-dollarisation" claim)

BIS global liquidity indicators are reachable via SDMX (`https://stats.bis.org/api/v1/data/WS_GLI/Q.USD.3P.N.A.I.B.USD/all?format=csv`):
USD credit to non-banks outside the US $2.34tn (2000Q1) → $15.13tn (2026Q2), +8.1% yoy in 2026Q2
(+2.9% in 2024Q4). corr(DXY 12m change at t, USD-credit yoy growth at t) = −0.39; at t+2q −0.41;
t+4q −0.21; t+6q −0.10 (n ≈ 100 quarters). USD credit growth went NEGATIVE only in 2008Q3+4q
(−1.5%) and 2022Q3–2023Q1 (−2.7%, −5.5%). So: a strong dollar does coincide with and slightly lead
slower dollar-credit growth (Bruno-Shin / Avdjiev et al. mechanism), and Johnson's "falling dollar
= dollar credit expands" is directionally right (corr −0.4) but it is a 2-quarter, not a
multi-year, relationship and the magnitude is modest.

---

## 2. The predictive question, honestly

**Does dollar LEVEL predict crises ahead of time?** No evidence in the literature. The level is
never a regressor in the LP/logit papers (they use changes or REER gaps). My band test: 41% vs
31% base.

**Does dollar MOMENTUM (6–12m change) predict?** Weak-to-moderate, in-sample only, and
concentrated in a handful of episodes:
- Literature: Obstfeld-Zhou / Hofmann-Park horizons are 4–8 quarters for OUTPUT, i.e. a dollar
  shock today predicts weaker EM growth over the next 1–2 years — that is a "lead" in the sense of
  the growth-at-risk literature (Hofmann-Park: 1ppt → GaR −0.6ppt at 4q), but these papers do not
  model crisis ONSET and their IRFs are in-sample.
- Bruno-Shin: the RER coefficient is on the PRIOR quarter's change (q−1 → q+1): one-quarter lead
  for bank flows. Avdjiev et al.: daily contemporaneous for the basis; SPVAR lending response
  builds over 1–4 quarters.
- Free-data signals test (`scripts/analysis.py`; 1974–2026 monthly, 16 frozen onsets, outcome =
  onset in the NEXT 12 months, strict lead; base rate 29%):

  | signal | A hits | B false | NSR | P(onset ≤12m \| signal) | share of crisis-months called |
  |---|---|---|---|---|---|
  | 12m ΔDXY > +5% | 78 | 112 | 0.57 | 41% | 44% |
  | > +10% | 41 | 44 | 0.42 | 48% | 23% |
  | > +15% | 21 | 13 | 0.24 | 62% | 12% |
  | 12m ΔDXY < −5% | 44 | 131 | 1.17 | 25% | 25% |
  | < −10% | 23 | 51 | 0.87 | 31% | 13% |
  | \|12m ΔDXY\| > 10% | 64 | 95 | 0.59 | 40% | — |

  Upward momentum has a KLR-grade NSR (0.42 ≈ exports in KLR); downward momentum carries no
  information (NSR ≈ 1). CAVEATS: in-sample; the 41 hit-months come from ~5 clusters (1981–82,
  1997–98, 2000–01, 2015, 2022); the crisis list was fixed by me knowing the dollar history
  (2022-09 is itself "the dollar peak"); monthly-average synthetic DXY.

**Does the dollar lead VIX / basis / EM spreads?** No. Monthly 1990–2026: Granger F for
ΔDXY→ΔlogVIX = 0.05 (1 lag), 0.12 (3), 0.64 (6) vs 5% critical ≈ 3.85/2.6/2.1; VIX→DXY 3.71 at 1
lag (borderline). ΔDXY↔ΔTED 1986–2021: F ≤ 1.3 both ways. All cross-correlations |ρ| < 0.1 at
every lead/lag ±6. Avdjiev et al. is daily and contemporaneous. Lilley et al.: contemporaneous R².
The dollar is coincident with risk-off, not ahead of it. EM OAS: FRED's ICE BofA series
(BAMLEMCBPIOAS, BAMLH0A0HYM2) now only carry data from 2023-11 (observed 2026-11-02) — too short;
a long EM-spread history is not free.

**Cause vs symptom vs policy — what free series separate them:**
| regime | signature | free series | episodes (3m into onset) |
|---|---|---|---|
| SYMPTOM (safe-haven / convenience yield) | DXY ↑, US 10y ↓, credit spreads ↑, swap-line usage ↑, gold ↓ intramonth | DGS10, DTWEXBGS, SWPT, STLFSI4 | 9/16: 1982, 1997, 1998, 2008, 2010, 2013, 2015, 2018, 2020 |
| POLICY (Fed tightening) | DXY ↑, US 2y/10y ↑, 2s10s flattening, EM FX ↓ with rising US real rates | FEDFUNDS, DGS2, T10Y2Y | 2/16: 1994 Tequila, 2022 |
| CAUSE (dominant-currency / dollar-debt channel) | sustained DXY ↑ (12m > +10%) with BIS USD-credit growth slowing/negative and EM investment falling; takes 4–8q to show in output | BIS GLI, DTWEXBGS, EM IP | 1981–82, 2000–01, 2015, 2022 |
| neither | DXY ↓ into onset | — | 1974, 1987, 1992, 2001, 2023 (5/16) |

The quadrant is cheap, honest, and historically informative: "USD up / yields down" is the
dominant crisis signature; "USD up / yields up" is the Fed-driven minority; "USD down" into onset
happens in a third of cases, which kills "the dollar rises in every crisis".

---

## 3. Pre-registrable study on free data (monthly, 1973-01 → 2026-09, 645 months)

### 3.1 Frozen crisis list (freeze BEFORE any fitting; publish with sources)
L-broad (16 onsets; global or multi-country EM dollar-funding stress): 1974-06 Herstatt/Franklin
National; 1982-08 Mexico/LatAm debt; 1987-10 crash; 1992-09 ERM; 1994-12 Tequila; 1997-07 Asia;
1998-08 Russia/LTCM; 2001-02 Turkey (Argentina 2001-12 same episode); 2008-09 Lehman; 2010-05
Greece/euro; 2013-05 taper tantrum; 2015-08 China deval/commodities; 2018-08 Turkey/Argentina;
2020-03 COVID; 2022-09 UK LDI / EM FX stress at the dollar peak; 2023-03 SVB/CS.
L-narrow (5; dollar-funding squeezes proper, by swap-line/basis evidence): 1982-08, 1998-08,
2008-09, 2020-03, 2022-09.
Mechanical alternatives for robustness: Laeven-Valencia systemic banking crises (IMF WP 18/206 —
UNVERIFIED here, blocked), Baron-Verner-Xiong bank-equity crashes (NBER w26908, read; 46 countries
1870–2016), and a market rule: equal-weighted EM FX basket (FRED EXBZUS, EXMXUS, EXKOUS, EXINUS,
EXSFUS, EXTAUS, EXTHUS, EXMAUS, EXCHUS) falling >10% in 3 months. Report results under ALL lists;
the pre-registered primary is L-broad.

### 3.2 Outcomes
- Y1 (binary): onset in months t+1..t+12 (strict lead; no same-month credit).
- Y2 (continuous): 12m-forward max drawdown of the EM FX basket; 12m-forward max of STLFSI4
  (1993–) and NFCI (1971–); 12m-forward max VIX (1990–).

### 3.3 Predictors (≤ 6, fixed ex ante)
1. DXY band state: 1{DXY>105}, 1{DXY<85}, distance to band edge (synthetic DXY as built).
2. DXY 6m and 12m % change; its rolling 10-year percentile.
3. Dollar–yield quadrant: sign(Δ3m DXY) × sign(Δ3m GS10).
4. BIS USD credit to non-banks ex-US, yoy % (2000Q1–, interpolated monthly) — sub-sample only.
5. Fed hiking indicator: FEDFUNDS 12m change > +100bp.
6. Oil: Brent/WTI 12m % change (WTISPLC 1946–).
Optional controls, not signals: US 2s10s (GS10−GS2, 1976–), RBUSBIS (1994–).

### 3.4 Methods
- Signals approach (KLR): for each predictor, choose the threshold on a 10–30% percentile grid
  that minimises NSR on 1973–2007 ONLY; evaluate frozen thresholds on 2008–2026 (pseudo-OOS).
  Report A/B/C/D, NSR, P(crisis|signal), share of crisis-months called, and the same for a
  "random signal of equal frequency" (benchmark).
- Logit with leave-one-crisis-out: drop each onset and ±24 months, refit, predict the held-out
  window; pool predictions → AUROC with Hanley-McNeil SE and 1,000-draw block bootstrap; Brier
  score vs the unconditional base rate; multinomial (tranquil/pre/post) or drop 12 post-onset
  months to avoid Bussière-Fratzscher post-crisis bias.
- Lead-lag: Granger/cross-correlation of ΔDXY vs ΔVIX, ΔSTLFSI, ΔSWPT, EM-FX returns, at 1/3/6
  lags, full sample and post-2007.
- Base rate and power: 16 onsets in 645 months; P(onset ≤12m) = 29%. With n+ = 16 events the
  AUROC SE is ≈ 0.07 at AUROC 0.70, so anything below ≈ 0.70 is indistinguishable from 0.5; a
  conditional hit rate needs ≈ 18 independent alarm episodes to separate 50% from the 29% base
  at 95% — we have ~5–8. State this in the panel. L-narrow (5 events) supports no inference at all.
- Pre-register: predictor list, thresholds grid, crisis lists, the 2007 split, and the metrics.

### 3.5 End-of-crisis rule and how to score it
Define END(t) = first month after onset where ALL hold: (a) DXY ≥ 3% below its post-onset peak for
2 consecutive months; (b) SWPT < 10% of episode peak (2002–; before that, TED < pre-onset median
for 2 months); (c) STLFSI4 < 0 (1993–) / NFCI < 0. Score each component by its lead/lag (months)
against two reference "ends": the EM FX basket trough and the first month VIX < 25. Historical
calibration from this pass: 2008 — DXY-peak rule fires ~May-2009, swap rule Oct-2009, EM FX trough
Mar-2009 (dollar-peak rule leads swap rule by ~5 months); 2020 — DXY rule ~Jun-2020, swap rule
Oct-2020, EM FX trough Mar/Apr-2020; 2022 — DXY rule Dec-2022, swap rule Nov-2022. Expect the
dollar-peak rule to be the earliest and noisiest; swap-line usage is the confirmation.

### 3.6 Two designs
MAXIMAL: all of §3.2–3.5, 3 crisis lists, 6 predictors, signals + LOCO logit + lead-lag,
quarterly BIS GLI sub-sample, charts: DXY with band/onsets, momentum percentile, quadrant map,
ROC curves with CIs, end-rule timing table. ~2 days incl. counter-agent.
MINIMAL (what the panel needs): synthetic DXY + band + 12m momentum percentile + quadrant +
SWPT + BIS USD-credit yoy; signals-approach table for 12m momentum only, frozen L-broad,
1973–2007 threshold / 2008–26 test; the quadrant table; the gold-at-onset table. ~half a day.

### 3.7 What the panel may and may not display
MAY: DXY level, band shading, 10y percentile; 12m momentum and its percentile; the current
quadrant with the historical onset counts per quadrant (9/2/3/2 of 16); BIS USD-credit yoy (with
the −0.4 correlation and "re-dollarising / de-dollarising" labels Johnson-style, clearly marked as
coincident); SWPT usage and the end-rule status; crisis-CONDITIONAL base rates with N and the
unconditional 29% beside them; gold's realised drawdown table. Current readings (FRED, as of
2026-10-28/09): synthetic DXY 100.0 (Sep-26 avg; in band; 12m change +2.4%), DTWEXBGS 121.3,
10y 4.98%, VIX 19.4, SWPT $0.16bn, NFCI −0.49, STLFSI −0.58, USD credit +8.1% yoy, Brent $114
(Sep-26 avg), WTI $103 — i.e. "in band, no momentum, funding calm, dollar credit expanding".
MUST NOT: a date or countdown; "probability of the next crisis" (16 events cannot support it);
any claim that a band breach "ends in crisis 75% of the time"; gold or dollar direction as a
crisis rule; a dollar→VIX lead.

---

## 4. Five decision-relevant facts; five open questions

Facts
1. The dollar's crisis role is causal for EM GROWTH over 4–8 quarters (10% ↑ → EM GDP −1.5%;
   1ppt ↑ → GaR −0.6ppt) and coincident for market STRESS; nobody has shown it leads crisis onset.
2. Upward 12m dollar momentum > +10% is the only dollar signal with a KLR-grade NSR (0.42, P=48%
   vs 29% base) — in-sample, ~5 episodes; downward momentum is noise (NSR ≈ 1).
3. 9/16 onsets show USD ↑ + US 10y ↓ (safe-haven); only 1994 and 2022 show USD ↑ + yields ↑
   (policy); 5/16 had the dollar FALLING into onset. The dollar was higher 3 months after onset in
   only 8/16 cases and gold lower in only 5/16.
4. The $85tn (USD leg) / $26tn (non-bank ex-US, 2× on-balance-sheet) FX-swap dollar debt with >3/4
   under 1 year is the mechanism that makes dollar squeezes abrupt; Fed swap lines cap the basis
   (0.28–0.59pp effects) and their usage (peak $583bn Dec-08, $449bn May-20) is a lagging
   confirmation of the end, 1–5 months after the dollar peak.
5. Johnson's band is self-described as ad hoc; the 16/75% figure is unsourced and not
   reproducible (41% vs 31% base). BIS USD credit growth is coincident with/2q behind the dollar
   (corr −0.4), not a multi-year regime switch.

Open questions
1. Which crisis list? Results change materially between L-broad (16), L-narrow (5) and mechanical
   lists; the choice must be frozen with Casey before any fitting.
2. Is there any free long-history EM spread series now that FRED's ICE BofA OAS feeds start in
   2023-11? (Candidates: World Bank GEM EMBI history, Fed FEDS notes data, academic replication
   packages — unchecked.)
3. Is the post-2007 "reconnect" (LMNS R² 10–60%) a permanent regime, i.e. should thresholds be
   fitted post-2007 only (≤ 7 onsets)?
4. Does the +10% momentum signal survive a true OOS split at 2007 and a mechanical crisis list?
   (Not run — needs the pre-registration first.)
5. What is the right real-time DXY? ICE daily DXY is not on FRED; the synthetic (monthly-average,
   ICE weights, 1999 splice) tracks known levels within ~1–2 points, but daily intramonth spikes
   (Mar-2020) are invisible in it.

---

## 5. Counter-agent spot-check list (not yet done)
- Obstfeld-Zhou −1.5%/8q (BPEA text p.382–383); Table 1 correlations; fn 53 (31bp EBP) and
  Table 3 col 1 (389.75/4 ≈ 97bp).
- Hofmann-Park 0.3/0.6ppt (BIS QR Dec-2020 p.3 & Graph 3).
- Avdjiev et al. Table 2 col 1/6 (−2.641 / −2.080).
- Edison Table 5 "Original KLR" column (RER 0.19/0.57/0.67; exports 0.42/0.85).
- Bussière-Fratzscher Tables 5, 8, 18.
- Gourinchas-Obstfeld p.34 marginal effects (11.5/6.4/9.4; 4.3/4.7/2.5).
- Catão-MF Table 1 AUROCs, Table 8 (42/61), Table 10 rows.
- Bahaj-Reis Table 1 (0.28 / 0.59pp).
- BMM 2022 ($97tn, $85tn, $26tn/$13tn, $39tn/$15tn).
- `scripts/band_test.py` and `scripts/analysis.py` outputs (22/9/31%; quadrant 9/2/3/2;
  Granger F's; gold table) and the synthetic-DXY checkpoints in `scripts/build_dxy.py`.

## 6. Files
- Deliverable: this file. Chart: `dxy_band_crises.png`.
- `raw/*.txt`: pdftotext extracts (34 papers); `raw/*.html`: BIS landing pages; `raw/data/`:
  FRED CSVs, `dxy_synthetic_monthly.csv`, `wb_cmo_monthly.xlsx`, `bis_gli_usd_credit_nonbanks_exUS.csv`.
- `scripts/dl.sh`, `build_dxy.py`, `band_test.py`, `analysis.py` (run with `python3 -I`).
- Could not open (UNVERIFIED): IMF-hosted PDFs (KLR 97/79 — used Edison's reproduction; Druck et
  al. 15/179; Laeven-Valencia 18/206; Adrian et al. 18/180; Prasad et al. 19/36); Rey 2013 Jackson
  Hole PDF (KC Fed timed out — used NBER w21162 "Dilemma not trilemma"); stooq/Yahoo DXY downloads
  (blocked/rate-limited — hence the synthetic index).
