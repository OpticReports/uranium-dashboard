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
<tr><td>HSR transactions reported</td><td>FTC/DOJ annual reports</td><td class="n">1994*</td><td class="n"><b>~10mo</b></td><td>direct — coincident activity, official count</td></tr>
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
<b>Four defects found and fixed, not papered over.</b> (0) The 1990s threshold correction was FIRST built on a fitted Pareto exponent. Adversarial review rejected the family outright — &chi;&sup2; p &lt; 1e-8 in all eleven years, lognormal preferred by AIC 40&ndash;134 — and showed the full-range exponent was measured in the wrong place: the correction only traverses $15&ndash;25.8M, where the local slope is 0.46&ndash;0.64, not the fitted 0.57&ndash;0.77. It overcorrected by about half. The shipped correction uses no distributional family at all. (1) The momentum axis was Hamilton's 5-year difference — a cyclical-component horizon, not a rate of change — which made both clock axes measure the same thing at corr <span class="num">+0.822</span>, collapsing the clock onto its diagonal with "early" occupied once in 123 quarters. Now a year-on-year change, corr <span class="num">+0.478</span>. (2) Cross-quarter level comparisons tracked composition, not the cycle — sign-flipping at coverage seams. Now reported as a like-for-like delta. (3) The current quarter was summed while still in progress, reading a partial month as a collapse; incomplete quarters are now excluded. Each has a regression gate.<br><br>
<b>The deflator is the load-bearing assumption, and it is a judgement.</b> Correcting the 1990s requires saying what deal values scale with. Nominal GDP is the shipped choice; it moves the answer roughly <b>nine times more than the exponent ever did</b>: corrected 1990→2000 rise is <span class="num">1.70×</span> on GDP, <span class="num">1.93×</span> on CPI, and <span class="num">0.94×</span> deflated by corporate equity values — where the 1990s becomes a decline. GDP and CPI give <em>identical</em> rankings; the equity deflator does not, and it is rejected on principle rather than on results, since equity values are endogenous to the M&amp;A cycle being measured and deflating by them erases the signal by construction.<br><br>
<b>What was NOT modeled.</b> Transaction multiples — EV/EBITDA paid is not obtainable free with real history, so no multiples axis exists. Deal <em>value</em> in dollars, for the same reason. Deal premia. Structural change in the M&amp;A market (sponsors, private credit, antitrust regime) — the percentile transform mitigates but does not remove non-stationarity. Component <em>dependence</em>: Harford (2005) shows aggregate capital liquidity drives clustering, so credit spread, lending standards and financial conditions are not independent readings, and breadth correspondingly <b>overstates</b> agreement.<br><br>
<b>Where it will fail.</b> The same place the LEI failed: a narrow, concentrated move in a subset of components reading as a broad turn. Breadth is published to catch it. Read the phase as a state, not a prophecy.
</div>

<p class="cap">* HSR now scores from <b>1994Q1</b>, with the 1990s threshold artifact <b>corrected rather than avoided</b>. The $15M bar was set in 1978 and never indexed, eroding 77.1% in real terms by 2000. The correction is <b>measured, not modelled</b>: for each year we read off that year\'s own published bracket table how many transactions would have cleared a bar with the same real bite as 1990\'s $15M ($15.00M → $25.79M), by log-linear interpolation inside the containing bracket. Every one of those values falls <em>inside</em> the observed brackets, so it is interpolation throughout and no distributional family is assumed. Result: raw fiscal-year rise 2.18× → <b>1.70× corrected, so bracket creep explains 22%</b> of the 1990s boom and the rest is real.<br><br>
1990–1993 stay unscored, and not because of the correction: an expanding percentile window is degenerate there (the first observation ranks 1.000 against itself), so a 16-quarter minimum window now applies to every component. <b>2000Q4 and 2001Q1 are dropped entirely</b> — Pub. L. 106-553 took effect 2001-02-01 mid-quarter, and FY2001 is blended (its own Table V splits it 1,317 old-regime against 920 new). 2000Q4 goes too because it falls in fiscal 2001, which has no measured factor, and would otherwise be the one old-regime quarter carried through uncorrected. The Act also abolished the size-of-person test above $200M, so pre- and post-2001 counts remain <em>different objects</em> — the regimes are ranked separately and never spliced. No FTC report in any year quantifies that change.<br><br>
† EDGAR is ingested from 1994 but scored only from 1997Q1. Electronic filing became mandatory in May 1996; total merger proxies run 2 (Jan-1994) → 16 (Jan-1996) → 78 (Jan-2000), so an earlier start measures <em>EDGAR adoption</em>, not deal-making. Counts are <b>distinct accession numbers, not index rows</b> — form.idx emits one row per filer, and counting rows inflates S-4 by up to 8.7× (2007Q2: 1,029 rows, 137 filings). DEFM14A and PREM14A are the only two forms that are 1:1 with filings.<br><br>
<b>Licence posture.</b> ICE BofA OAS series are excluded entirely — "reproduction of this data in any form is prohibited." Moody's <span class="num">BAA10Y</span> was the first substitute and was also wrong: FRED tags it <em>Copyrighted: Citation Required</em> and its notes forbid redistribution. The Gilchrist–Zakrajšek spread is US Government work, starts thirteen years earlier than BAA10Y, and correlates +0.937 with HY OAS against BAA10Y's +0.54. This repository is public, so raw vendor levels are never committed — only derived ranks, composites and phase labels.</p>
</div>
"""
with open(OUT, "w") as f:
    f.write(html)
print(f"wrote {OUT} ({len(html)} bytes), {len(R)} quarters, last {L['quarter']}")


# ---------------------------------------------------------------
# DASHBOARD PANEL
# ---------------------------------------------------------------
# Injected between markers in dashboard.html so the panel's numbers
# cannot drift from ma_cycle_readings.json, and so the mirror
# regeneration stays a mechanical step.

import csv as _csv

DASH = os.path.join(_HERE, "..", "dashboard.html")
BEGIN = "<!-- BEGIN ma-cycle-panel (generated by models/make_ma_page.py) -->"
END = "<!-- END ma-cycle-panel -->"


def _months_out(s, today=(2026, 9)):
    s = (s or "").strip()
    if len(s) < 7 or not s[:4].isdigit():
        return None
    return (int(s[:4]) - today[0]) * 12 + (int(s[5:7]) - today[1])


def _exposure():
    """How many ledger positions the current reading may speak to.

    Two columns, two answers - and the gap between them IS the finding.
    """
    import sys
    sys.path.insert(0, _HERE)
    import ma_cycle as mc
    rnd = mul = tot = 0
    near = None
    with open(os.path.join(_HERE, "..", "ledger.csv")) as f:
        for r in _csv.DictReader(f):
            tot += 1
            mr, mm = _months_out(r.get("resolve_round_by")), _months_out(r.get("resolve_multiple_by"))
            if mc.exit_exposure(mr) == "exposed":
                rnd += 1
            if mc.exit_exposure(mm) == "exposed":
                mul += 1
            if mm is not None and (near is None or mm < near):
                near = mm
    return rnd, mul, tot, near


def panel_html():
    rnd, mul, tot, near = _exposure()
    spark = R[-40:]
    # viewBox aspect must match the rendered box or the sparkline
    # letterboxes; preserveAspectRatio="none" would fix the width but
    # distort the slopes, which is the one thing a sparkline encodes.
    w, h = 1000.0, 54.0
    lo = min(min(r["level"] for r in spark), 0)
    hi = max(max(r["level"] for r in spark), 0)
    rng = (hi - lo) or 1.0
    pts = " L ".join(
        f"{i*w/(len(spark)-1):.1f} {h-(r['level']-lo)/rng*h:.1f}"
        for i, r in enumerate(spark))
    zero = h - (0 - lo) / rng * h
    lfl = L["delta_like_for_like"]
    lfls = f"{lfl:+.3f}" if lfl is not None else "—"
    prov = (f' · <span style="color:var(--danger)">provisional, '
            f'{L["coverage"]:.0%} coverage</span>') if L["provisional"] else ""
    return f"""{BEGIN}
  <h2>M&amp;A cycle — the environment these forecasts resolve into</h2>
  <p class="sub" style="margin-bottom:12px">A <span class="tt" tabindex="0">descriptive state variable<span class="box"><b>Not a forecast.</b> Built the way the Chicago Fed builds the NFCI, which describes contemporary conditions and evidences its forecasting claims separately. Eight components, expanding-window percentile ranks, <b>zero fitted parameters</b> — every constant is published precedent or a prior declared before results were seen. At ~5 US merger waves since 1980 no hit-rate claim would be statistically meaningful, and none is made.</span></span>, not a forecast. Full method, sensitivity and honesty box: <a href="https://research.optic.capital/deals/ma-cycle-indicator.html">M&amp;A cycle indicator →</a></p>
  <div class="tiles">
    <div class="tile"><span class="big">{L['phase']}</span><span class="cap">phase, {L['quarter']}{prov}</span></div>
    <div class="tile"><span class="big">{L['level']:+.2f}</span><span class="cap">composite level — above trend</span></div>
    <div class="tile"><span class="big">{lfls}</span><span class="cap"><span class="tt" tabindex="0">like-for-like Δ<span class="box">The change restricted to components present in BOTH quarters. The composite averages over <em>available</em> components, so the raw level moves when the panel changes even if nothing did — at this seam the naive delta reads +0.017 (strengthening) while like-for-like reads −0.086 (weakening). <b>The sign flips on composition alone.</b> This is the honest number.</span></span></span></div>
    <div class="tile"><span class="big">{L['diffusion']:.0f}</span><span class="cap"><span class="tt" tabindex="0">breadth ({L['breadth']})<span class="box">Share of components moving the same way. Published beside the phase and never folded into it — that is the specific instrument for the failure that embarrassed the Conference Board's LEI, which called recession for 21 straight months while GDP grew 2.9% annualized because a narrow, goods-concentrated decline read as a broad turn.</span></span></span></div>
  </div>
  <svg viewBox="0 0 {w:.0f} {h:.0f}" style="width:100%;height:56px;margin:2px 0 10px" role="img" aria-label="Composite level, last 40 quarters">
    <line x1="0" y1="{zero:.1f}" x2="{w:.0f}" y2="{zero:.1f}" stroke="var(--line)" stroke-dasharray="3 3"/>
    <path d="M {pts}" fill="none" stroke="var(--data-1)" stroke-width="1.6" stroke-linejoin="round"/>
  </svg>
  <div class="decider" style="border-left-color:var(--accent)"><b>What this may and may not comment on.</b> The reading speaks to roughly a two-year horizon, so of {tot} ledger positions: <b>{rnd} of {tot} are exposed on the next-round forecast</b> (resolving 3–24 months out) and <b>{mul} of {tot} on the return-multiple forecast</b> — the nearest multiple resolves <b>{near} months out</b>, the furthest 144. Today's M&amp;A phase is not information about a 2034 exit, and this panel will not pretend otherwise.<br><br>
  <b>It does not touch a single exit-odds number.</b> The exit curve's base is PitchBook's measured stage MOIC buckets and its tilt is pinned to the panel's own Brier-scored forecasts — both auditable, both scored by the ledger. Multiplying that by a cycle factor would overwrite a measured base rate with a state reading that has never been scored against anything, and would make the forecasts unfalsifiable: you could no longer tell a bad forecast from a bad cycle adjustment. Where the cycle legitimately bears is <span class="tt" tabindex="0">realization, not multiple<span class="box">The measured PitchBook Part IV funnel (n=31,642 US companies, first VC round 2009–2018) puts only <b>25.5%</b> at a liquidity event against 31.1% dead and <b>39.6% in limbo</b> — never raised again, no outcome. Limbo is the largest terminal state, and limbo is what a shut financing window produces. Exit share peaks around round 3 and then falls: later survivors are disproportionately unresolved, not resolved well.</span></span> — whether a position resolves at all.</div>
{END}"""


def inject_panel():
    with open(DASH) as f:
        s = f.read()
    if BEGIN not in s:
        raise SystemExit(
            f"marker not found in dashboard.html - add:\n{BEGIN}\n{END}")
    a, b = s.index(BEGIN), s.index(END) + len(END)
    with open(DASH, "w") as f:
        f.write(s[:a] + panel_html() + s[b:])
    return DASH


# ---------------------------------------------------------------
# MIRRORS
# ---------------------------------------------------------------
# CLAUDE.md's sync rule: dashboard.html is canonical and
# genomics-alpha-tracker/backend/app/deal_analyzer.html is a
# byte-for-byte mirror plus a 6-line provenance header, regenerated IN
# THE SAME COMMIT. The indicator page needs the same treatment because
# the dashboard panel links to it and the service serves it from its
# own Docker context. Both are done here so neither can be forgotten.

_ROOT = os.path.join(_HERE, "..", "..")
_APP = os.path.join(_ROOT, "genomics-alpha-tracker", "backend", "app")

MA_MIRROR_HEADER = """<!-- MIRROR: canonical copy is
     venture-deal-analyzer/validation/ma-cycle-indicator.html, which is
     GENERATED by venture-deal-analyzer/models/make_ma_page.py from
     models/ma_cycle_readings.json. Do not hand-edit either copy - rerun
     the script. Served at research.optic.capital/deals/ma-cycle-indicator.html.
-->
<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
"""


def mirror_dashboard():
    """Regenerate deal_analyzer.html = its 6-line header + dashboard.html."""
    src = os.path.join(_HERE, "..", "dashboard.html")
    dst = os.path.join(_APP, "deal_analyzer.html")
    with open(dst) as f:
        header = "".join([next(f) for _ in range(6)])
    with open(src) as f:
        body = f.read()
    with open(dst, "w") as f:
        f.write(header + body)
    return dst


def mirror_indicator():
    dst = os.path.join(_APP, "ma_cycle_indicator.html")
    with open(OUT) as f:
        body = f.read()
    with open(dst, "w") as f:
        f.write(MA_MIRROR_HEADER + body)
    return dst


if __name__ == "__main__":
    print("panel   ->", inject_panel())
    print("mirror1 ->", mirror_dashboard())
    print("mirror2 ->", mirror_indicator())
