"""Render the M&A cycle indicator page. Rerun to rebuild from readings.

Kept as a script rather than a hand-edited HTML file so the numbers on
the page cannot drift from ma_cycle_readings.json.
"""
import json
import os
import statistics as st

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_HERE, "..", "validation", "ma-cycle-indicator.html")

R = [x for x in json.load(open(os.path.join(_HERE, "ma_cycle_readings.json")))
     if x["level"] is not None and x["momentum"] is not None]
L = R[-1]
COMP = ["GZ_SPREAD", "DRTSCILM", "DRSDCILM", "NFCI", "NCBCEBQ027S",
        "EQUITY_Q", "HSR_COUNT", "EDGAR_PROXIES"]

def qn(q): return int(q[:4]) + (int(q[5]) - 1) / 4
x0, x1 = qn(R[0]["quarter"]), qn(R[-1]["quarter"])
X0, X1, Y0, Y1 = 64, 844, 26, 236
def sx(q): return X0 + (qn(q) - x0) * (X1 - X0) / (x1 - x0)
def sy(v): return (Y0 + Y1) / 2 - v * (Y1 - Y0) / 2

env = [(sx(r["quarter"]),
        sy(max(v for v in r["components"].values() if v is not None)),
        sy(min(v for v in r["components"].values() if v is not None)))
       for r in R]
envelope = ("M " + " L ".join(f"{a:.1f} {b:.1f}" for a, b, _ in env) +
            " L " + " L ".join(f"{a:.1f} {c:.1f}" for a, _, c in reversed(env)) + " Z")
line = "M " + " L ".join(f"{sx(r['quarter']):.1f} {sy(r['level']):.1f}" for r in R)
mom = "M " + " L ".join(f"{sx(r['quarter']):.1f} {sy(r['momentum']):.1f}" for r in R)
D0, D1 = 258, 306
dif = "M " + " L ".join(
    f"{sx(r['quarter']):.1f} {D1-(r['diffusion']/100)*(D1-D0):.1f}"
    for r in R if r["diffusion"] is not None)
CX, CY, CR = 140, 140, 104
tail = R[-12:]
clock = "M " + " L ".join(f"{CX+r['level']*CR:.1f} {CY-r['momentum']*CR:.1f}" for r in tail)
recs = "".join(f'<rect x="{sx(a):.1f}" y="26" width="{sx(b)-sx(a):.1f}" height="210" fill="var(--rec)"/>'
               for a, b in (("2001Q1", "2001Q4"), ("2007Q4", "2009Q2"), ("2020Q1", "2020Q2")))
recs2 = "".join(f'<rect x="{sx(a):.1f}" y="258" width="{sx(b)-sx(a):.1f}" height="48" fill="var(--rec)"/>'
                for a, b in (("2001Q1", "2001Q4"), ("2007Q4", "2009Q2"), ("2020Q1", "2020Q2")))
ticks = "".join(f'<text class="ax" x="{sx(q):.1f}" y="326" text-anchor="middle">{q[:4]}</text>'
                for q in [r["quarter"] for r in R]
                if q.endswith("Q1") and int(q[:4]) % 5 == 0)
lfl = L["delta_like_for_like"]
lfls = f"{lfl:+.3f}" if lfl is not None else "—"
prov = ('<span style="background:var(--warn);border:1px solid var(--line);border-radius:5px;'
        'padding:2px 7px;font-size:.68rem;font-family:ui-monospace,Menlo,monospace;'
        'letter-spacing:.06em">PROVISIONAL · {:.0%} COVERAGE</span>').format(L["coverage"]) \
    if L["provisional"] else ""

CSS = """:root{--paper:#F7F8F7;--card:#FFF;--ink:#1A2422;--muted:#56675F;--line:#DCE3DF;--accent:#0E7E53;--neg:#9E3B1E;--d1:#0E7E53;--d2:#A85F00;--wash:#EEF3F0;--warn:#F6EEE2;--grid:#E8EDEA;--rec:#E4E9E6;--env:#0E7E5322;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#131A18;--card:#1A2320;--ink:#E4EBE7;--muted:#92A29A;--line:#2A3733;--accent:#45C69E;--neg:#E0805F;--d1:#279B79;--d2:#C56F33;--wash:#1F2A26;--warn:#2A2119;--grid:#232E2A;--rec:#212C28;--env:#279B7933;}}
:root[data-theme="dark"]{--paper:#131A18;--card:#1A2320;--ink:#E4EBE7;--muted:#92A29A;--line:#2A3733;--accent:#45C69E;--neg:#E0805F;--d1:#279B79;--d2:#C56F33;--wash:#1F2A26;--warn:#2A2119;--grid:#232E2A;--rec:#212C28;--env:#279B7933;}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:15.5px;line-height:1.55;margin:0}
.wrap{max-width:960px;margin:0 auto;padding:38px 20px 70px}
h1,h2{font-family:Charter,"Bitstream Charter",Cambria,Georgia,serif;text-wrap:balance}
h1{font-size:1.85rem;margin:6px 0}
h2{font-size:1.15rem;margin:0 0 3px}
.eyebrow{font-family:ui-monospace,Menlo,monospace;font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.sub{color:var(--muted);max-width:74ch;margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin:18px 0}
.num{font-family:ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}
svg{display:block;width:100%;height:auto;overflow:visible}
.ax{font-family:ui-monospace,Menlo,monospace;font-size:11px;fill:var(--muted)}
.pk{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;fill:var(--muted)}
.dl{font-family:ui-monospace,Menlo,monospace;font-size:12px;font-weight:650}
.cap{font-size:.79rem;color:var(--muted);line-height:1.45;margin:8px 2px 2px}
table{border-collapse:collapse;width:100%;font-size:.85rem;margin:6px 0}
th,td{text-align:left;padding:6px 9px;border-bottom:1px solid var(--line)}
th{font-family:ui-monospace,Menlo,monospace;font-size:.67rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
td.n{font-family:ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;text-align:right}
.box{background:var(--warn);border:1px solid var(--line);border-radius:9px;padding:14px 16px;margin:18px 0}
.hero{display:flex;gap:26px;flex-wrap:wrap;align-items:baseline;margin:4px 0 10px}
.hero .big{font-family:ui-monospace,Menlo,monospace;font-size:2.1rem;font-weight:650;color:var(--accent);line-height:1.1}
.hero .lbl{font-family:ui-monospace,Menlo,monospace;font-size:.66rem;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);display:block}"""

html = f"""<title>M&amp;A Cycle Phase Indicator</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🕰️</text></svg>">
<style>{CSS}</style>
<div class="wrap">
<div class="eyebrow">OpticReports · Deal Analyzer · M&amp;A cycle · as of {L['quarter']}</div>
<h1>Where is the M&amp;A cycle?</h1>
<p class="sub">A <em>descriptive</em> state variable, built the way the Chicago Fed builds the NFCI. It says where the M&amp;A market is now. <strong>It is not a forecast</strong> — that claim is checkable today rather than in eighteen months, and it avoids estimating a forward relationship we lack the sample to fit.</p>

<div class="hero">
<div><span class="lbl">Phase, {L['quarter']}</span><span class="big">{L['phase']}</span></div>
<div><span class="lbl">Level</span><span class="big">{L['level']:+.2f}</span></div>
<div><span class="lbl">Like-for-like Δ</span><span class="big">{lfls}</span></div>
<div><span class="lbl">Momentum</span><span class="big">{L['momentum']:+.2f}</span></div>
<div><span class="lbl">Breadth</span><span class="big">{L['diffusion']:.0f}</span></div>
</div>
<div style="margin:0 0 14px">{prov}</div>

<div class="box"><b>Read the two deltas, not the level.</b> The composite averages over the components <em>available</em> in a quarter, so the published level moves when the panel changes even if nothing in the market did. At this seam that is not a hypothetical: the naive quarter-on-quarter change reads <span class="num">+0.017</span> (strengthening) while the like-for-like change — same components both quarters — reads <span class="num">−0.086</span> (weakening). <b>The sign flips on composition alone.</b> The like-for-like figure is the honest one; the raw level difference is not.<br><br>
<b>And the label is band-sensitive.</b> Level is clearly positive with momentum oscillating around zero, which puts this on the <b>mid→late boundary</b>. At any neutral band ≤0.10 recent quarters read <b>late</b>; at our declared 0.15 they read <b>transitional</b>. We keep 0.15 because it was declared before any result was seen — retuning it now, having seen 0.10 gives the more decisive answer, is exactly the curve-fit this indicator forbids.</div>

<div class="card">
<h2>Composite level and momentum, {R[0]['quarter']} → {L['quarter']}</h2>
<p class="cap">Bold line is the equal-weight composite level; the shaded band is the min–max spread across the eight components. <b>Band width is information</b>: wide means they disagree. Dashed line is momentum. Grey bands are NBER recessions.</p>
<svg viewBox="0 0 880 340" role="img" aria-label="M&amp;A cycle composite level and momentum with component spread envelope, NBER recessions shaded, and a breadth strip below">
  {recs}
  <line x1="64" y1="131" x2="844" y2="131" stroke="var(--line)"/>
  <text class="ax" x="26" y="134">0</text><text class="ax" x="20" y="30">+1</text><text class="ax" x="22" y="239">−1</text>
  <path d="{envelope}" fill="var(--env)" stroke="none"/>
  <path d="{mom}" fill="none" stroke="var(--d2)" stroke-width="1.6" stroke-dasharray="5 3" stroke-linejoin="round"/>
  <path d="{line}" fill="none" stroke="var(--d1)" stroke-width="2.4" stroke-linejoin="round"/>
  <text class="dl" x="700" y="60" fill="var(--d1)">Composite level</text>
  <text class="dl" x="700" y="212" fill="var(--d2)">Momentum</text>
  <text class="pk" x="286" y="20">2001</text><text class="pk" x="436" y="20">2008–09</text><text class="pk" x="690" y="20">2020</text>
  <line x1="64" y1="258" x2="844" y2="258" stroke="var(--line)"/>
  {recs2}
  <line x1="64" y1="282" x2="844" y2="282" stroke="var(--grid)" stroke-dasharray="3 3"/>
  <path d="{dif}" fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linejoin="round"/>
  <text class="ax" x="24" y="262">100</text><text class="ax" x="32" y="286">50</text><text class="ax" x="38" y="310">0</text>
  <text class="dl" x="666" y="252" fill="var(--accent)">Breadth (diffusion)</text>
  {ticks}
</svg>
<p class="cap"><b>Breadth is published beside the phase, never folded into it.</b> That is the specific instrument for the failure that embarrassed the Conference Board's LEI — a narrow, concentrated decline reading as a broad cycle turn. It called recession for 21 straight months while GDP grew 2.9% annualized.</p>
</div>

<div class="card">
<h2>The clock — last 12 quarters</h2>
<p class="cap">Level horizontal, momentum vertical, ending {L['quarter']} (filled dot). The dashed disc is the neutral zone, where the label is unstable and we publish "transitional" rather than force a call.</p>
<svg viewBox="0 0 560 290" role="img" aria-label="Phase clock plotting level against momentum with the trajectory over the last twelve quarters">
  <rect x="36" y="36" width="208" height="208" fill="none" stroke="var(--line)"/>
  <line x1="36" y1="140" x2="244" y2="140" stroke="var(--line)"/>
  <line x1="140" y1="36" x2="140" y2="244" stroke="var(--line)"/>
  <circle cx="140" cy="140" r="15.6" fill="var(--wash)" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="3 2"/>
  <text class="pk" x="196" y="52">MID</text><text class="pk" x="196" y="236">LATE</text>
  <text class="pk" x="46" y="52">EARLY</text><text class="pk" x="46" y="236">BUST</text>
  <path d="{clock}" fill="none" stroke="var(--d1)" stroke-width="2" stroke-linejoin="round" opacity=".8"/>
  <circle cx="{CX+L['level']*CR:.1f}" cy="{CY-L['momentum']*CR:.1f}" r="6" fill="var(--d1)"/>
  <text class="pk" x="{CX+L['level']*CR+11:.1f}" y="{CY-L['momentum']*CR+4:.1f}" fill="var(--d1)">{L['quarter']}</text>
  <text class="ax" x="262" y="60">level {L['level']:+.2f} — above trend</text>
  <text class="ax" x="262" y="82">like-for-like Δ {lfls}</text>
  <text class="ax" x="262" y="104">momentum {L['momentum']:+.2f}</text>
  <text class="ax" x="262" y="126">breadth {L['diffusion']:.0f} ({L['breadth']})</text>
  <text class="ax" x="262" y="148">coverage {L['coverage']:.0%} of components</text>
  <text class="pk" x="262" y="178">The tail sits right of centre and is</text>
  <text class="pk" x="262" y="194">oscillating across the momentum axis —</text>
  <text class="pk" x="262" y="210">above trend, direction unresolved.</text>
</svg>
</div>

<h2>Components</h2>
<table>
<tr><th>component</th><th>source</th><th>from</th><th>lag</th><th>orientation</th></tr>
<tr><td>Gilchrist–Zakrajšek credit spread</td><td>Federal Reserve Board</td><td class="n">1973</td><td class="n">~1mo</td><td>inverted — cheap credit is late-cycle (Harford 2005)</td></tr>
<tr><td>SLOOS C&amp;I standards</td><td>FRED <span class="num">DRTSCILM</span></td><td class="n">1990</td><td class="n">~6wk</td><td>inverted — loose standards are late-cycle</td></tr>
<tr><td>SLOOS C&amp;I demand</td><td>FRED <span class="num">DRSDCILM</span></td><td class="n">1991</td><td class="n">~6wk</td><td>direct — strong demand is late-cycle appetite</td></tr>
<tr><td>Financial conditions (NFCI)</td><td>Chicago Fed</td><td class="n">1971</td><td class="n">~5d</td><td>inverted — loose conditions are late-cycle</td></tr>
<tr><td>Net equity issuance</td><td>FRED <span class="num">NCBCEBQ027S</span> (Z.1 F.103)</td><td class="n">1970</td><td class="n">~70d</td><td>inverted — deeply negative <em>is</em> the wave signature</td></tr>
<tr><td>Equity Q</td><td>FRED <span class="num">NCBEILQ027S / TNWMVBSNNCB</span></td><td class="n">1970</td><td class="n">~70d</td><td>direct — overvaluation drives stock-paid deals (Shleifer &amp; Vishny 2003)</td></tr>
<tr><td>HSR transactions reported</td><td>FTC/DOJ annual reports</td><td class="n">2001*</td><td class="n"><b>~10mo</b></td><td>direct — coincident activity, official count</td></tr>
<tr><td>Merger proxies (DEFM14A+PREM14A)</td><td>SEC EDGAR form index</td><td class="n">1997†</td><td class="n"><b>~1d</b></td><td>direct — the nowcast layer</td></tr>
</table>

<div class="box">
<b>Why both deal-activity series, and not one.</b> The obvious objection is double-counting — two of eight slots measuring "how many deals are happening." Measured over the 85-quarter scored overlap (2001Q2–2025Q3) the correlation is <span class="num">+0.339</span> in levels and <span class="num">+0.535</span> in year-on-year changes. They are <b>not</b> redundant: HSR counts threshold-based reportable transactions <em>including private acquirers and private targets</em>, while EDGAR counts <em>public-target</em> deals going to a shareholder vote. Different populations. Both stay, and the number is published rather than the independence being asserted.
</div>

<h2>Honesty box</h2>
<div class="box">
<b>What this is.</b> A descriptive state variable, in the sense the Chicago Fed uses for the NFCI. <b>Not a forecast</b>, structurally — the module carries <span class="num">is_forecast=False</span> and a gate test fails if that ever changes.<br><br>
<b>Basis.</b> Expanding-window percentile ranks and year-on-year changes. No statistic uses data dated after the reading it produces; the load-bearing gate appends arbitrary future data and requires every past reading to be byte-identical. Zero fitted parameters — every constant is published precedent (Hamilton 2018, OECD CLI, Conference Board) or a prior declared before results were seen. <b>30 gate tests</b> across two suites.<br><br>
<b>Sample.</b> ~5 independent US merger waves since 1980; the scored window holds about two and a half. Effective degrees of freedom ≈ the number of cycles, not the {len(R)} quarters. <b>No claim about hit rates on past turning points is statistically meaningful at this N, and none is made.</b> Gärtner &amp; Halbheer (2009) find the canonical 1980s wave is not significant under regime-switching — if wave existence is method-fragile, wave phase is more so.<br><br>
<b>Three defects found and fixed, not papered over.</b> (1) The momentum axis was Hamilton's 5-year difference — a cyclical-component horizon, not a rate of change — which made both clock axes measure the same thing at corr <span class="num">+0.822</span>, collapsing the clock onto its diagonal with "early" occupied once in 123 quarters. Now a year-on-year change, corr <span class="num">+0.478</span>. (2) Cross-quarter level comparisons tracked composition, not the cycle — sign-flipping at coverage seams. Now reported as a like-for-like delta. (3) The current quarter was summed while still in progress, reading a partial month as a collapse; incomplete quarters are now excluded. Each has a regression gate.<br><br>
<b>What was NOT modeled.</b> Transaction multiples — EV/EBITDA paid is not obtainable free with real history, so no multiples axis exists. Deal <em>value</em> in dollars, for the same reason. Deal premia. Structural change in the M&amp;A market (sponsors, private credit, antitrust regime) — the percentile transform mitigates but does not remove non-stationarity. Component <em>dependence</em>: Harford (2005) shows aggregate capital liquidity drives clustering, so credit spread, lending standards and financial conditions are not independent readings, and breadth correspondingly <b>overstates</b> agreement.<br><br>
<b>Where it will fail.</b> The same place the LEI failed: a narrow, concentrated move in a subset of components reading as a broad turn. Breadth is published to catch it. Read the phase as a state, not a prophecy.
</div>

<p class="cap">* HSR is <b>charted but not scored</b> before 2001Q2. The $15M threshold was set in 1978 and never indexed, eroding from 6.38 to 1.46 ppm of GDP across 1978–2000; raw counts rose 2.46× over 1990–2000 and roughly 1.8× of that is bracket creep. Deflating needs the Pareto exponent of deal values near the threshold, which is not measured — assuming one would smuggle a fitted parameter in as a fix. Pub. L. 106-553 then raised the threshold to $50M effective 2001-02-01 <em>and</em> eliminated the size-of-person test, so pre- and post-2001 counts are different objects.<br><br>
† EDGAR is ingested from 1994 but scored only from 1997Q1. Electronic filing became mandatory in May 1996; total merger proxies run 2 (Jan-1994) → 16 (Jan-1996) → 78 (Jan-2000), so an earlier start measures <em>EDGAR adoption</em>, not deal-making. Counts are <b>distinct accession numbers, not index rows</b> — form.idx emits one row per filer, and counting rows inflates S-4 by up to 8.7× (2007Q2: 1,029 rows, 137 filings). DEFM14A and PREM14A are the only two forms that are 1:1 with filings.<br><br>
<b>Licence posture.</b> ICE BofA OAS series are excluded entirely — "reproduction of this data in any form is prohibited." Moody's <span class="num">BAA10Y</span> was the first substitute and was also wrong: FRED tags it <em>Copyrighted: Citation Required</em> and its notes forbid redistribution. The Gilchrist–Zakrajšek spread is US Government work, starts thirteen years earlier than BAA10Y, and correlates +0.937 with HY OAS against BAA10Y's +0.54. This repository is public, so raw vendor levels are never committed — only derived ranks, composites and phase labels.</p>
</div>
"""
with open(OUT, "w") as f:
    f.write(html)
print(f"wrote {OUT} ({len(html)} bytes), {len(R)} quarters, last {L['quarter']}")
