// Dollar watch tab: what each reading is, how to read it, and what it does not tell you.
// Rendered by <InfoTip entry={DW.x} />. Descriptive only: every count is in-sample; nothing here is a forecast.
import type { GlossaryEntry } from "./glossary";

export const DW: Record<string, GlossaryEntry> = {
  // ── layers ────────────────────────────────────────────────────────────────
  layer_state: {
    title: "Layer 1: dollar state",
    what: "Where the dollar sits against its own history: its level, its trend, what bonds and safe havens are doing alongside it, and how emerging-market currencies are holding up.",
    read: "Context, not timing. Nothing in this layer has a validated edge: the band showed none, and momentum's in-sample edge depends on the crisis list. Treat it as background for layers 2 and 3.",
    caveat: "All the counts beside these readings are in-sample on 1971-2026; the crisis lists were drawn up knowing the dollar's path.",
  },
  layer_funding: {
    title: "Layer 2: dollar-funding nowcast",
    what: "The plumbing of dollar borrowing: what banks and companies pay for short-term dollars, how stressed overnight repo is, and how much foreign central banks borrow from the Fed.",
    read: "This is the mechanism behind a dollar scramble: when dollar borrowers abroad cannot roll their debt, these gauges jump first or alongside the dollar. Quiet gauges mean no sign of a funding squeeze on the free gauges. They were also quiet through the 2015-16 and 2018 EM scares, and the cross-currency basis (the direct price of offshore dollars) is paid-only and not shown.",
    read2: "The summary's one word: under strain = the CP spread's 5-print average above 1pp (the crisis dating's line); elevated = below that line, but CP's 5-print average or the OFR funding index at or above the 80th percentile of its own history; quiet = both at or below their 1-year medians; in its usual range = the rest, about three days in five since 2020. Swap-line borrowing is a lagging stock and never sets the word.",
    caveat: "Each gauge is ranked against its own history, from the start year the table shows; for most of them that includes 2008 (CP since 1997, the OFR index since 2000, NFCI since 1971, swap lines since Dec-2007); the SOFR tail starts in 2018 (its base holds the Sep-2019 repo spike and March 2020, not 2008); SOFR minus IORB starts in 2021, with no crisis in its base. They moved with or ahead of the dollar's peak, but their first alarms came roughly with the crisis's start (2007, 2022; n = 2): coincident, not early.",
  },
  layer_scramble: {
    title: "Layer 3: dollar-scramble peak gauge",
    what: "Casey's deceleration rule, with its parameters fixed, run live every day on the Fed's broad dollar index. It looks for the top of a dollar SCRAMBLE: a sharp dollar climb with Treasury yields falling, then the climb slowing while the dollar stays near its high.",
    read: "Closed = no scramble on this definition, and nothing to read. Open = a 4%+ climb with yields falling within the last 60 index days: a scramble under way or just past, and the readings beneath tell which. They are shown separately and never added up. Index days are the days both the broad dollar and the 10-year yield are published, about 250 a year.",
    caveat: "An untested hypothesis. In-sample: 6 firings since 2006, one clean call (2020) and two first-wave firings (2008, 2022, after which the dollar rose another 18% and 5%); no edge on 1973-2005 monthly data. It says nothing about when a crisis ends.",
  },
  layer_slow: {
    title: "Layer 4: slow state",
    what: "The backdrop that moves over quarters: how much dollar debt sits outside the US, the stock of FX swaps, policy rates abroad against the Fed's, the 2-year yield against the Fed's ceiling, and who holds Treasuries.",
    read: "Sizes how exposed the world is to a dollar squeeze; it does not time one. Records in these series have come in calm years and before crises alike.",
  },
  ledger: {
    title: "Forward ledger",
    what: "An append-only record of every live firing of the rule and every momentum episode after the reference cut-off, written the day the panel first sees it and never edited.",
    read: "Outcomes (S&P, EM currencies, credit spreads, the dollar) are frozen into each row 3, 6 and 12 months later, measured from the first close after the firing became public.",
    caveat: "With about one scored unit every four to five years, the record needs decades before it can say anything.",
  },
  prereg: {
    title: "Pre-registration (frozen 2026-11-03)",
    what: "The rules that will grade the deceleration rule on future data only, written and frozen before any of that data exists, so nobody can tune them to the outcome.",
    calc: "A firing counts only if it comes after the freeze and showed on first publication. A 'unit' is a firing plus any within 250 index days of it. A hit is the broad dollar rising at most 3% further over the next 250 index days. Each hit is compared with a no-information volatility model, judged as if the dollar drifted -1% a year for a PASS and +1% for a FAIL.",
    read: "Looks come at 8, 16 and 24 matured units, around 2060-2067, 2093-2107 and 2126-2147. A unit is a firing plus its 250-index-day outcome window (later firings inside the window join it); it matures when the window closes. Only a PASS could ever license anything beyond description: one neutral colour on the deceleration reading (3a) and a notification, reading 'dollar scramble peaking: beat a no-information model (deceleration-specific: not tested)'. Every other reading stays descriptive under any outcome.",
    caveat: "With no real edge the most likely end is 'undecided'. If the dollar keeps its 2016-26 volatility and drifts down 1% a year, a false PASS runs about 0.07, above the 0.05 the test is meant to allow (Q19 kept this as frozen).",
  },
  onset_months: {
    title: "Crisis months, dated mechanically",
    what: "Each month from 2026-11 gets one row, written once after its data are fully published. The row records which of five markers tripped: VIX at 40 or above; the OFR stress index above its own 5-year 95th percentile for 5 days; the EM currency basket 10% weaker in 63 days; the S&P 20% below its 252-day high; a Fed emergency action.",
    read: "Two or more markers with no onset in the prior 12 months = an onset. On 2000-2026 this dates 8 onsets: 2001-04, 2002-07, 2007-12, 2009-01, 2010-05, 2011-09, 2020-03 and 2022-06.",
    caveat: "Designed by people who know 2000-2026, so the count is a sanity check, not validation. A long crisis re-dates itself at month 13.",
  },
  placebo: {
    title: "The placebo rule",
    what: "The same rule with its deceleration step removed: it fires on the first day of a 4% dollar climb near the high with yields falling, instead of waiting for the climb to slow.",
    read: "Scored the same way beside the real rule. If the placebo does as well, any PASS is about post-scramble reversals in general, not deceleration.",
    caveat: "It is a diagnostic, not a certificate: under a generic reversal it matches or beats the rule in only about 3 in 10 PASSes, so the PASS wording never claims deceleration.",
  },

  // ── layer 1 readings ──────────────────────────────────────────────────────
  dxy: {
    title: "ICE US Dollar Index (DXY)",
    what: "The dollar against six major currencies, weighted by 1970s trade: euro 57.6%, yen 13.6%, pound 11.9%, Canadian dollar 9.1%, krona 4.2%, Swiss franc 3.6%. March 1973 = 100. Up = the dollar stronger.",
    read: "The percentile ranks today's level among month-end closes since 1971: 70th means higher than 70% of them. The momentum line this tab watches is a 12-month rise of more than 10% in the monthly-average DXY (the tile's own 12-month change is on daily closes and can differ).",
    caveat: "Heavy on the euro and blind to China and most emerging markets. The Fed's broad index (next tile) is the better gauge of the dollar the world actually borrows in.",
  },
  band: {
    title: "Johnson's 85-105 band",
    what: "A rule of thumb from the October 2026 talk this study started from: a DXY below 85 or above 105 is supposed to signal trouble.",
    read: "Tested here on three crisis lists, 1971-2026: the 17 excursions outside the band were followed by a crisis no more often than any month was: within one excursion of the base on A25 and N5, below it on C16. The band is shown because it was claimed, not because it works.",
    caveat: "No edge on any list (for example 8 excursions followed by an A25 crisis within 12 months, against 7.2 expected).",
  },
  broad: {
    title: "Fed broad dollar index (DTWEXBGS)",
    what: "The Federal Reserve's nominal trade-weighted dollar against 26 currencies, including China, Mexico and other emerging markets. January 2006 = 100. Published weekly in the H.10 release, the Monday after the data week.",
    read: "The index the scramble rule runs on. The percentile is against the last 10 years. The high since 2006 is the reference for 'how stretched'.",
    caveat: "Weekly publication: it can lag the DXY by up to two weeks.",
  },
  afe_eme: {
    title: "Against advanced vs emerging economies",
    what: "The broad index split in two: the dollar against advanced foreign economies (euro, yen, pound, ...) and against emerging-market economies (yuan, peso, won, ...).",
    read: "A dollar rising faster against emerging-market currencies points the strain at dollar borrowers there; a rise led by the advanced currencies is more often about rate differentials. That is a general pattern, not one tested here.",
  },
  quadrant: {
    title: "Dollar-yield quadrant",
    what: "The direction of the DXY and of the 10-year Treasury yield over the last 3 months, giving four combinations.",
    read: "'Dollar up, 10-year down' is the flight-to-safety mix: investors want dollars and Treasuries at once. In-sample, 9 of 16 dollar-stress onsets began in that quadrant, against 22% of all months; the other three quadrants share the remaining 7, each at or below its base rate.",
    caveat: "16 onsets is a small sample and the list was drawn up knowing the dollar's path: a label, not a forecast.",
  },
  momentum: {
    title: "12-month momentum (+10% line)",
    what: "The change in the DXY's monthly average over 12 months. An 'episode' starts when it first rises above +10% after a year below.",
    read: "In-sample, 5 of 11 episodes were followed by a dollar-stress onset (C16) within 12 months, against 28% of all months. That sounds like an edge, but 11 episodes is below the ~15 the study needs before showing a rate, the 41 of 85 months are overlapping readings rather than independent ones, 8 of the 11 began during a crisis already on the 25-crisis list, and a 6-month version of the test falls below its base (28% vs 42%).",
    caveat: "Never tested: a fair test needs about 40 independent episodes, roughly 400 years of data.",
  },
  base_rate: {
    title: "Base rate",
    what: "The share of all months (1971-2026) that were followed by a crisis onset within the same window. It is what a signal has to beat.",
    read: "A count like '8 of 12 (67%)' means nothing on its own: if 60% of all months were followed by an onset in that window, the signal added little. Every 'X of N were followed by...' count on this page is shown beside its base rate.",
  },
  crisis_lists: {
    title: "The three crisis lists",
    what: "A25: 25 crises of all kinds (broad). C16: 16 onsets of multi-country dollar stress, the primary list. N5: the 5 acute dollar-funding squeezes.",
    read: "A finding that holds on one list but flips on another is fragile. C16 decides; A25 and N5 are shown so you can see whether a result depends on how crises were dated.",
  },
  gold: {
    title: "Gold",
    what: "Spot gold in dollars per ounce (FMP; COMEX futures as a fallback).",
    read: "In the 2008 and 2020 dollar-funding squeezes gold fell in the liquidation weeks before recovering. Across all 24 completed crises on the 25-crisis list it ended higher in 14 (58%), against 61% of same-length windows: no better than gold's own drift. A fall with no sign of a funding squeeze does not fit that pattern; the tile says so when it happens.",
    caveat: "Daily gold before 2000 is not available free, so the early record is monthly.",
  },
  emfx: {
    title: "EM currency basket",
    what: "An equal-weight average of 8 emerging-market currencies against the dollar (Brazilian real, Mexican peso, South African rand, Indian rupee, Korean won, Thai baht, Chinese yuan, Malaysian ringgit). Up = EM currencies weaker.",
    read: "A fast rise means EM currencies are falling against the dollar, from a dollar squeeze or from EM-specific stress (2015-16 and 2018 came with dollar funding quiet). A 10% rise in 63 trading days is one of the five crisis-dating markers.",
    caveat: "Turkey and Indonesia are not on FRED daily. Several of these currencies are managed, which damps the basket.",
  },
  chf_jpy: {
    title: "Swiss franc and yen per dollar",
    what: "The two traditional safe-haven currencies, quoted per dollar. Up = franc or yen weaker.",
    read: "In a pure risk-off shock they often rise against the dollar (these numbers fall). In a dollar-funding scramble the dollar can rise against everything, havens included.",
  },
  brent: {
    title: "Brent crude",
    what: "The global oil benchmark, in dollars per barrel (EIA via FRED).",
    read: "Context for the dollar story: an oil shock can drive inflation and rates without any dollar-funding stress.",
  },
  // ── layer 2 gauges (keyed by the funding row id) ─────────────────────────
  cp_fin: {
    title: "Financial CP minus 3-month T-bill",
    what: "What banks and finance companies pay to borrow unsecured for 3 months in commercial paper, minus the Treasury bill yield. It is the price of bank credit risk in dollar money markets.",
    read: "Usually between about 0.05 and 0.6 points (median 0.18 since 1997; 0.09 since 2019). In the dollar-funding onsets of 2007-12, 2009-01 and 2020-03 its average over 5 prints passed 1 percentage point (1.78, 1.14 and 1.12). The crisis dating uses that 1pp line to mark an onset as dollar-funding.",
    caveat: "The own-history percentile runs from the start year the table shows (1997 for this series with its full history loaded), so it includes 2008; the last-10-years column does not. Single prints can jump, month-ends especially, so the summaries judge it on the average of its last 5 prints, as the crisis dating does. The Fed publishes no rate (n.a.) when too few trades print: for weeks in March-May 2020, and on about two days in five since 2021. When the newest print is over a week old, or the five straddle a blank of more than three weeks (March-May 2020, February 2024), the summaries say so and set no word from CP.",
  },
  cp_nonfin: {
    title: "Nonfinancial CP minus 3-month T-bill",
    what: "The same spread for nonfinancial companies' commercial paper.",
    read: "Usually calmer than the financial spread; a rise here says the strain has spread beyond banks.",
  },
  ofr_funding: {
    title: "OFR financial stress index: funding",
    what: "The funding part of the Office of Financial Research's daily stress index, built from money-market and interbank spreads. 0 = average stress; positive = above average.",
    read: "One of the two inputs to the scramble gauge's 'funding easing' reading: below its 1-year median counts as easing.",
  },
  ofr_em: {
    title: "OFR stress index: emerging markets",
    what: "The emerging-markets contribution to the OFR stress index. 0 = average.",
    read: "Rises when stress reaches EM assets, often the second leg of a dollar squeeze.",
  },
  ofr_safe: {
    title: "OFR stress index: safe assets",
    what: "The safe-assets part of the OFR stress index (demand for Treasuries, gold, the yen and the franc). 0 = average.",
    read: "High = a flight to safety. On its own it does not distinguish a growth scare from a funding scare.",
  },
  nfci_risk: {
    title: "Chicago Fed NFCI: risk subindex",
    what: "The risk part of the Chicago Fed's National Financial Conditions Index: volatility and funding risk across markets. 0 = average; positive = tighter than average.",
    read: "A broad, slow-moving read on financial conditions; useful as a cross-check on the faster gauges above.",
  },
  sofr_tail: {
    title: "SOFR tail: 99th percentile minus SOFR",
    what: "How much the most expensive overnight repo trades (the 99th percentile) pay over the median repo rate (SOFR), in basis points.",
    read: "A wide tail means some borrowers are paying up for overnight dollars, strain in the repo market that funds Treasuries. Its history starts in 2018: it holds the Sep-2019 repo spike and March 2020 but not 2008, and no lead was tested.",
  },
  sofr_iorb: {
    title: "SOFR minus interest on reserves",
    what: "The overnight repo rate minus the rate the Fed pays banks on their reserves, in basis points.",
    read: "Repo trading above the reserve rate means cash is getting scarcer relative to collateral: as in 2019 before the September repo spike (an observation, not tested here; this series starts in 2021). A few basis points is not a scramble.",
    caveat: "History starts in 2021, so its percentile is against a short and unusually cash-rich window.",
  },
  swap_lines: {
    title: "Fed central-bank liquidity swaps",
    what: "Dollars the Fed has lent to foreign central banks (ECB, BoJ, ...), which lend them on to their own banks. Weekly, from the Fed's H.4.1 balance sheet.",
    read: "Near zero in normal times. It jumps when banks abroad cannot get dollars any other way: hundreds of billions in 2008 and 2020. Above $50 billion is the dollar-funding threshold in the crisis dating.",
  },
  emb: {
    title: "EM dollar bonds (EMB)",
    what: "The price of the iShares JP Morgan USD Emerging Markets Bond ETF: government bonds emerging markets have issued in dollars.",
    read: "Falls when EM dollar borrowing costs rise. Closing above its prior 20-day high is half of the scramble gauge's 'risk turn' reading, with gold.",
  },
  percentile: {
    title: "Percentile of its own history",
    what: "Where today's value ranks among the series' own past values: the 90th percentile means higher than 90% of them.",
    read: "It answers 'is this unusual for this series?'. It does not say whether the level is extreme in absolute terms: a series with a calm history can sit at its 99th percentile at an ordinary level.",
  },

  // ── layer 3 readings ──────────────────────────────────────────────────────
  gate: {
    title: "The gate",
    what: "The gauge opens when the broad dollar's largest 20-day climb in the last 60 index days is at least 4% AND the 10-year yield is below where it stood before that climb.",
    read: "That pairing (dollars and Treasuries bought together) is what separates a scramble for safety from an ordinary rally on higher rates. Closed = nothing to read.",
  },
  decel: {
    title: "(a) Deceleration",
    what: "The rule's core step: the current 20-day climb has slowed to half its peak or less while the dollar is still within 3% of its 60-day high.",
    read: "When met, the gauge reads 'dollar scramble peaking', and only that: it is a statement about the top of the dollar's climb, not about markets or the crisis.",
  },
  funding_easing: {
    title: "(b) Funding easing",
    what: "Financial CP minus bills AND the OFR funding stress index both below their 1-year medians.",
    read: "Says the plumbing is loosening. In 2008 the dollar's peak and funding relief came months apart, so this is shown separately, never combined with (a).",
  },
  risk_turn: {
    title: "(c) Gold and EM bonds turning",
    what: "Gold AND the EM dollar-bond ETF both closing above their prior 20-day highs (completed sessions only).",
    read: "The assets sold to raise dollars in the scramble start to recover. Shown separately; never summed with (a) or (b).",
  },
  confirmations: {
    title: "Confirmations",
    what: "Two after-the-fact checks: the broad dollar 3% off its episode peak, and swap-line usage below 10% of the episode's peak (shown only if that peak was at least $10 billion).",
    read: "These arrive after the peak by construction: they confirm, they do not anticipate.",
  },
  firings_table: {
    title: "Every in-sample firing",
    what: "The rule run on 2006-2026 with its frozen parameters: 6 firings under the default (unpatched) rule, plus the re-arm variant's 2008-11-06, added after the 2008-09-22 firing came too early.",
    read: "'Dollar rose further' is how much more the broad dollar climbed in the next 250 index days: small = the rule was near the top. 'S&P to next low' is how far stocks fell afterwards, from the firing day and from the first day the firing was publicly visible.",
    caveat: "In-sample: the parameters were chosen on this same history.",
  },
  null_box: {
    title: "The null (shown permanently)",
    what: "The rule's monthly analogue run on 1973-2005, data the parameter choice did not use (though the study had seen it): 10 firings.",
    read: "The dollar peaked within 3 months either side of 3 of them, against 42% of all months: no edge. This box stays on the page whatever the forward record later shows.",
  },

  // ── layer 4 readings ──────────────────────────────────────────────────────
  usd_credit: {
    title: "Dollar credit outside the US",
    what: "Dollar loans and bonds owed by non-bank borrowers outside the United States (BIS global liquidity indicators). The tile shows the latest total and the emerging-market share.",
    read: "The size of the potential scramble: these borrowers need dollars to roll their debt. Growth (Johnson's 're-dollarising') raises exposure, but the stock has hit records in calm years and before crises alike.",
    caveat: "Quarterly, published with about a 5-month lag.",
  },
  fx_swaps: {
    title: "FX forwards and swaps outstanding",
    what: "The notional stock of FX forwards, FX swaps and currency swaps (BIS), mostly with a dollar leg: the 'hidden' dollar debt that does not show on balance sheets.",
    read: "A large stock means many institutions must deliver dollars on fixed dates, which is how a scramble spreads.",
    caveat: "Gross notional, not a net shortfall; semiannual with about a 5-month lag.",
  },
  two_year: {
    title: "US 2-year yield vs the Fed's ceiling",
    what: "The 2-year Treasury yield against the upper bound of the fed funds target range.",
    read: "A 2-year well below the ceiling means markets expect rate cuts; well above means hikes. Sudden falls often come with flights to safety.",
  },
  custody: {
    title: "Foreign official custody holdings",
    what: "Marketable Treasury securities the New York Fed holds in custody for foreign central banks and official accounts (H.4.1, weekly; agencies not included).",
    read: "Falling holdings can mean official holders selling Treasuries to raise dollars, as in March 2020, or simply moving custody elsewhere. The percentile is against the last 10 years.",
  },
  treasury: {
    title: "10-year yield and term premium",
    what: "The 10-year Treasury yield and the Kim-Wright 10-year term premium (Federal Reserve Board model, via FRED): the extra yield investors demand to hold a long bond rather than roll short ones.",
    read: "A rising term premium alongside a rising dollar points to a Treasury-supply or confidence story, not a funding scramble (in a scramble, yields usually fall).",
  },
  policy_rates: {
    title: "Policy rates vs the Fed",
    what: "Central-bank policy rates (BIS) for the main economies, with the gap to the Fed's rate in the same month.",
    read: "Rate gaps drive the dollar in normal times: a widening gap in the Fed's favour supports the dollar without any stress. That is why rate-driven rallies and scrambles have to be told apart (see the gate).",
  },
};
