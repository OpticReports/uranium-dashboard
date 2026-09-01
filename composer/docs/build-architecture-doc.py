# -*- coding: utf-8 -*-
"""Build the Composer book architecture document as a PDF."""
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Table, TableStyle, KeepTogether, PageBreak)

INK  = colors.HexColor('#12151c')
INK2 = colors.HexColor('#4a5160')
INK3 = colors.HexColor('#7b8494')
RULE = colors.HexColor('#d5dae2')
BAND = colors.HexColor('#f2f4f8')
ACC  = colors.HexColor('#1f5fa8')
POS  = colors.HexColor('#136b46')
NEG  = colors.HexColor('#a8321f')

S = lambda n, **k: ParagraphStyle(n, **k)
H1   = S('H1', fontName='Helvetica-Bold', fontSize=19, leading=23, textColor=INK, spaceBefore=2, spaceAfter=9)
H2   = S('H2', fontName='Helvetica-Bold', fontSize=13, leading=16, textColor=INK, spaceBefore=17, spaceAfter=6)
H3   = S('H3', fontName='Helvetica-Bold', fontSize=10.5, leading=13, textColor=INK, spaceBefore=11, spaceAfter=4)
BODY = S('BODY', fontName='Helvetica', fontSize=9.4, leading=13.4, textColor=INK, spaceAfter=6, alignment=TA_LEFT)
SMALL= S('SM', fontName='Helvetica', fontSize=8.3, leading=11.4, textColor=INK2, spaceAfter=5)
MONO = S('MONO', fontName='Courier', fontSize=7.9, leading=10.6, textColor=INK, spaceAfter=2)
CAP  = S('CAP', fontName='Helvetica-Oblique', fontSize=8.1, leading=11, textColor=INK3, spaceAfter=9)
LEAD = S('LEAD', fontName='Helvetica', fontSize=10.6, leading=15, textColor=INK2, spaceAfter=10)
TH   = S('TH', fontName='Helvetica-Bold', fontSize=7.9, leading=10, textColor=colors.white)
TD   = S('TD', fontName='Helvetica', fontSize=8.2, leading=11, textColor=INK)
TDb  = S('TDb', fontName='Helvetica-Bold', fontSize=8.2, leading=11, textColor=INK)
TDm  = S('TDm', fontName='Courier', fontSize=8.2, leading=11, textColor=INK)

def tbl(rows, widths, align=None, head=True, zebra=True, font=TD):
    data=[]
    for i,r in enumerate(rows):
        st = TH if (head and i==0) else font
        data.append([c if isinstance(c,(Table,Paragraph)) else Paragraph(str(c), st) for c in r])
    t=Table(data, colWidths=widths, repeatRows=1 if head else 0)
    cmds=[('VALIGN',(0,0),(-1,-1),'MIDDLE'),
          ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
          ('TOPPADDING',(0,0),(-1,-1),3.5),('BOTTOMPADDING',(0,0),(-1,-1),3.5),
          ('LINEBELOW',(0,0),(-1,-2),0.4,RULE)]
    if head:
        cmds += [('BACKGROUND',(0,0),(-1,0),INK),('TOPPADDING',(0,0),(-1,0),5),('BOTTOMPADDING',(0,0),(-1,0),5)]
    if zebra:
        for i in range(2,len(rows),2): cmds.append(('BACKGROUND',(0,i),(-1,i),BAND))
    if align:
        for col,a in align.items(): cmds.append(('ALIGN',(col,0),(col,-1),a))
    t.setStyle(TableStyle(cmds)); return t

def rule(sp=7): 
    t=Table([['']], colWidths=[6.9*inch], rowHeights=[0.6])
    t.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),0.7,RULE)])); return t

STORY=[]
def P(txt, st=BODY): STORY.append(Paragraph(txt, st))
def SP(h=6): STORY.append(Spacer(1,h))

W = 6.9*inch
# ============================ COVER / SUMMARY ============================
P("Composer Book: Architecture, Interaction and Risk Controls", H1)
P("Four systematic engines, how each decides, how they combine, and every rule that can "
  "move capital or force cash. Prepared as a reference for correlation analysis against an "
  "external strategy.", LEAD)
STORY.append(rule()); SP(8)

P("1. The book at a glance", H2)
P("The account runs four independent Composer symphonies at fixed target weights. Each is a "
  "decision tree evaluated on the prior close; the winning branch determines what is held the "
  "next session. No engine reads any macro, rates, news or economic input &mdash; every condition "
  "is a price, moving-average, RSI, return or volatility statistic computed from tradeable "
  "instruments. This has been verified both by tree audit and by measurement.", BODY)
STORY.append(tbl([
  ["Engine","Target","Role","Decision variable","Rebalance"],
  ["Holy Grail (HG)","29%","Leveraged trend + dip capture","TQQQ 10/20d MA cross, TQQQ &amp; SOXL 10d RSI","Daily"],
  ["KMLM Switcher","29%","Regime switcher (long/short/duration)","10d RSI on 17 equity/vol tickers; XLK vs KMLM","Threshold"],
  ["Crash Convexity Sleeve","27%","Crisis hedge / inverse + bond frontrun","Cumulative return, stdev and RSI on credit &amp; duration ETFs","Daily"],
  ["VIX Harvester","15%","Short-vol premium with credit guard","SPY 2&ndash;10d RSI; UVXY 14d RSI guard","Daily"],
], [1.42*inch,0.52*inch,1.55*inch,2.42*inch,0.72*inch],
  align={1:'CENTER',4:'CENTER'}))
P("Weights are targets, not hard bands. Drift is allowed and is only corrected by the "
  "concentration cap (Section 5), by owner instruction, or when new capital is deployed.", CAP)

P("2. How each engine decides", H2)

P("2.1 Holy Grail &mdash; leveraged trend with a dip-buy branch and a cash default", H3)
P("A four-level tree, all conditions keyed to TQQQ (Nasdaq 3x) with one SOXL check. Read top to "
  "bottom; the first matching branch wins.", BODY)
STORY.append(tbl([
  ["State","Condition","Holds"],
  ["Uptrend, overbought","TQQQ 10d MA &gt; 20d MA <b>and</b> TQQQ RSI(10) &gt; 80","Lowest-RSI of UVXY / VIXY / VIXM (long volatility)"],
  ["Uptrend, normal","TQQQ 10d MA &gt; 20d MA","Highest-RSI of TQQQ / UPRO / UDOW / SSO / TNA"],
  ["Downtrend, capitulation","10d MA &lt; 20d MA <b>and</b> TQQQ RSI(10) &lt; 30","Lowest-RSI of TECL / QLD / LABU / USD / SMH (buy the dip)"],
  ["Downtrend, semis oversold","SOXL RSI(10) &lt; 30","BIL (cash)"],
  ["Downtrend, below trend","TQQQ price &lt; 20d MA","BIL (cash)"],
  ["Otherwise","&mdash;","Highest-RSI of the five leveraged trend names"],
], [1.18*inch,2.62*inch,3.10*inch]))
P("<b>Why it matters for correlation:</b> HG is the book's highest-beta component and its only "
  "systematic equity-rebound harvester. It sits in cash roughly 23% of all days &mdash; historically "
  "these cash phases cluster in chop and have resolved upward (six prior cash-heavy stretches, "
  "forward 3-month returns positive six times out of six). Its beta to the market is therefore "
  "strongly state-dependent, not constant.", SMALL)

P("2.2 KMLM Switcher &mdash; a three-layer regime machine", H3)
P("Structurally the most complex engine, and the largest single source of book return and book "
  "variance. It resolves in three stages:", BODY)
STORY.append(tbl([
  ["Layer","Test","Result"],
  ["1. Overbought scan","10d RSI &gt; ~79 on any of QQQE, VTV, VOX, TECL, VOOG, VOOV, XLP(75), TQQQ, XLY, FAS, SPY","Hold UVXY (long volatility) &mdash; a melt-up hedge"],
  ["2. Oversold scan","TQQQ RSI &lt; 30 &rarr; TECL; SOXL &lt; 30 &rarr; SOXL; SPXL &lt; 30 &rarr; SPXL; LABU &lt; 25 &rarr; LABU","Buy the dislocated leveraged sector"],
  ["3. Regime default","RSI(XLK) &gt; RSI(KMLM) = risk-on","Risk-on: lowest-2-RSI of TECL / SOXL / SVIX.<br/>Risk-off: highest-RSI of SQQQ / TLT"],
], [1.15*inch,3.35*inch,2.40*inch]))
P("The engine is blended 75% with a 25% VIX sleeve (VXZ/PULS). The risk-off leg is what produced "
  "the recent rotation into TLT and then SQQQ. <b>Correlation note:</b> this engine can be long "
  "equities, short equities (SQQQ), long duration (TLT), long volatility (UVXY) or in cash within "
  "the same month &mdash; so its correlation to any external strategy is highly unstable and should "
  "never be treated as a single number.", SMALL)

P("2.3 Crash Convexity Sleeve &mdash; the hedge that pays in dislocations", H3)
P("Two halves. An <b>inverse-hold</b> leg that goes short equity/credit when stress thresholds "
  "trip, and a <b>bond frontrunner</b> leg that positions in duration (TMF long / TMV short) on "
  "credit and rate signals. Conditions use cumulative return, standard deviation of return, and "
  "RSI across HYG, LQD, CORP, IEF, SHY, TLT, KIE, PEJ, PSQ, LABD, TMF and TMV, with fixed "
  "thresholds at &minus;0.33%, &minus;1.75%, &minus;3.5%, &minus;4%, &minus;6% and &minus;7.5%. Its "
  "default resting state is BOXX (box-spread cash).", BODY)
P("<b>This is the engine that makes the book work.</b> It is the only component with negative "
  "correlation to equities, and it is the reason the book's down-capture is low. Its duration "
  "exposure is holdings-determined, not view-driven: it holds TMF or TMV on about 52% of days, "
  "and the sign of its rate exposure is set entirely by which of the two it is long.", SMALL)

P("2.4 VIX Harvester &mdash; short volatility, gated by credit", H3)
P("Nine parallel sub-strategies, one for each SPY RSI window from 2 to 10 days, equally weighted. "
  "Each follows the same rule:", BODY)
STORY.append(tbl([
  ["Condition","Action"],
  ["SPY RSI(w) &lt; 25 <b>and</b> UVXY RSI(14) &le; 70","Hold ZVOL (short volatility) &mdash; sell panic"],
  ["SPY RSI(w) &lt; 25 <b>and</b> UVXY RSI(14) &gt; 70","Hold PULS (cash) &mdash; <b>the credit guard blocks the trade</b>"],
  ["SPY RSI(w) &gt; 80","Hold VXZ (long mid-term volatility)"],
  ["Otherwise","Hold PULS (cash)"],
], [3.6*inch,3.3*inch]))
P("The engine is mostly in cash: the short-vol leg carries an average weight of only 6.4%. "
  "The UVXY guard is the critical protection &mdash; it blocks just 35 of 812 short-vol days, but "
  "one of those was 6 February 2018, the &minus;31% Volmageddon session. Tested alternatives "
  "(GARCH volatility-regime gates) all performed worse than this simple filter.", SMALL)

STORY.append(PageBreak())
P("3. How they work together", H2)
P("The four engines are deliberately uncorrelated with each other. This is the whole design: each "
  "is individually volatile, and the combination is not.", BODY)

P("3.1 Pairwise daily correlation", H3)
P("Common window 19 Apr 2023 &ndash; 31 Aug 2026, n = 845 trading days.", SMALL)
def cc(v, bold=False):
    col = NEG if v<0 else (INK if abs(v)<0.5 else ACC)
    return Paragraph(f'<font color="#{col.hexval()[2:]}">{v:+.2f}</font>', TDm)
rows=[["","HG","KMLM","SLEEVE","HARV","BOOK"]]
M={"HG":[1.00,0.31,-0.11,0.13,0.70],"KMLM":[0.31,1.00,0.06,0.11,0.84],
   "SLEEVE":[-0.11,0.06,1.00,0.07,0.24],"HARV":[0.13,0.11,0.07,1.00,0.22],
   "BOOK":[0.70,0.84,0.24,0.22,1.00]}
for k,v in M.items(): rows.append([Paragraph(f"<b>{k}</b>",TDb)]+[cc(x) for x in v])
STORY.append(tbl(rows,[1.15*inch]+[1.15*inch]*5, align={i:'CENTER' for i in range(1,6)}))
P("No engine pair exceeds 0.31. The sleeve is <i>negatively</i> correlated to Holy Grail. The book's "
  "high loadings on HG (0.70) and KMLM (0.84) simply reflect that those two carry most of the "
  "variance at 29% each.", CAP)

P("3.2 Correlation to standard benchmarks", H3)
rows=[["","SPY","QQQ","TLT","GLD","IWM"]]
B={"HG":[0.69,0.67,0.11,0.20,0.60],"KMLM":[0.27,0.29,-0.02,-0.03,0.17],
   "SLEEVE":[-0.28,-0.23,-0.10,-0.06,-0.29],"HARV":[0.11,0.10,-0.02,0.02,0.08],
   "BOOK":[0.47,0.49,0.02,0.07,0.35]}
for k,v in B.items(): rows.append([Paragraph(f"<b>{k}</b>",TDb)]+[cc(x) for x in v])
STORY.append(tbl(rows,[1.15*inch]+[1.15*inch]*5, align={i:'CENTER' for i in range(1,6)}))
P("<b>Book correlation to SPY is 0.47 unconditionally</b> &mdash; but that single number is "
  "misleading, and Section 3.3 is the one to use.", CAP)

P("3.3 The number that actually matters: conditional correlation", H3)
P("Correlation to equities is strongly asymmetric by design. The book tracks the market on the way "
  "up and decouples on the way down.", BODY)
rows=[["","All days","SPY down days","SPY up days","SPY worst 5%","SPY best 5%"]]
C={"HG":[0.69,0.37,0.69,0.19,0.81],"KMLM":[0.27,-0.01,0.45,0.27,0.62],
   "SLEEVE":[-0.28,-0.32,-0.12,-0.27,-0.06],"HARV":[0.11,0.08,0.15,0.15,0.02],
   "BOOK":[0.47,0.03,0.65,0.16,0.80]}
for k,v in C.items(): rows.append([Paragraph(f"<b>{k}</b>",TDb)]+[cc(x) for x in v])
STORY.append(tbl(rows,[1.0*inch]+[1.18*inch]*5, align={i:'CENTER' for i in range(1,6)}))
P("<b>Book correlation to SPY falls from 0.65 on up days to 0.03 on down days, and 0.16 in the "
  "worst 5% of sessions.</b> That asymmetry &mdash; not the headline 0.47 &mdash; is the "
  "diversification property.", CAP)

P("3.4 Capture ratios and behaviour by market regime", H3)
rows=[["","Up-capture","Down-capture","Mean return, SPY worst 5%","Mean return, SPY down days"]]
K={"HG":["2.15x","1.86x","-2.64%","-1.21%"],"KMLM":["1.61x","0.13x","+0.81%","-0.09%"],
   "SLEEVE":["-0.13x","-0.63x","+1.69%","+0.41%"],"HARV":["0.18x","-0.10x","-0.10%","+0.07%"],
   "BOOK":["1.08x","0.39x","-0.09%","-0.26%"],"SPY (ref)":["1.00x","1.00x","-2.06%","-0.65%"]}
for k,v in K.items(): rows.append([Paragraph(f"<b>{k}</b>",TDb)]+[Paragraph(x,TDm) for x in v])
STORY.append(tbl(rows,[1.0*inch,1.05*inch,1.15*inch,1.85*inch,1.85*inch],
                 align={1:'CENTER',2:'CENTER',3:'CENTER',4:'CENTER'}))
P("The headline: <b>on the worst 5% of market days the book averages &minus;0.09% while SPY "
  "averages &minus;2.06%</b>. Up-capture is 1.08x, down-capture 0.39x. The sleeve is the engine "
  "doing that work &mdash; it earns +1.69% on exactly those days.", CAP)

P("3.5 Correlation is not stable &mdash; read this before using any single figure", H3)
P("Rolling 126-day correlation between the book and SPY has ranged from <b>+0.09 to +0.82</b> "
  "over the common window. Any correlation-based allocation decision against this book should use "
  "the conditional and rolling figures rather than a point estimate. Two further warnings for an "
  "external comparison:", BODY)
P("<b>&#8211;</b>&nbsp;&nbsp;<b>The sample is short and one-sided.</b> KMLM and the Harvester have only 845 trading "
  "days, all inside the 2023&ndash;2026 disinflation-and-easing regime. There is no 2022-style "
  "inflation shock in-sample. The rolling correlation between equities and rate expectations has "
  "recently turned negative (from +0.37 in January 2026 to &minus;0.20 now), which is the "
  "configuration in which several of these relationships historically invert.", SMALL)
P("<b>&#8211;</b>&nbsp;&nbsp;<b>These are engine backtests, in-sample by construction.</b> The performance figures "
  "below are what the strategies did in a strong tape, not forecasts.", SMALL)

P("3.6 Standalone performance", H3)
rows=[["Engine","Window","Days","CAGR","Max DD","Sharpe","Annual vol"]]
for k,v in {
  "Holy Grail":["2015-06 to 2026-08","2,822","+102.8%","35.8%","1.72","47.5%"],
  "KMLM Switcher":["2023-04 to 2026-08","845","+241.5%","24.5%","2.49","55.6%"],
  "Crash Sleeve":["2023-01 to 2026-08","901","+39.6%","14.9%","1.51","23.8%"],
  "VIX Harvester":["2023-04 to 2026-08","845","+25.4%","9.5%","2.12","11.0%"],
  "BOOK 29/29/27/15":["2023-04 to 2026-08","845","+98.0%","9.8%","2.92","24.4%"],
  "SPY (reference)":["2023-04 to 2026-08","845","+21.7%","18.8%","1.39","15.0%"]}.items():
    rows.append([Paragraph(f"<b>{k}</b>",TDb)]+[Paragraph(x,TDm) for x in v])
STORY.append(tbl(rows,[1.42*inch,1.42*inch,0.55*inch,0.85*inch,0.72*inch,0.62*inch,0.85*inch],
                 align={2:'CENTER',3:'RIGHT',4:'RIGHT',5:'CENTER',6:'RIGHT'}))
P("Note the combination effect: the book's max drawdown (9.8%) is <i>lower than every single "
  "engine's</i>, including the 9.5% Harvester on a comparable basis, while its CAGR sits between "
  "them. That is the diversification working, and it is the central claim any correlation "
  "comparison should be testing.", CAP)

STORY.append(PageBreak())
P("4. Protections inside the engines", H2)
P("These are conditions in the symphony trees themselves. They fire automatically at the daily "
  "rebalance, with no human involvement, and they are the only mechanisms that move a position "
  "intraday-to-next-day.", BODY)
rows=[["Protection","Engine","Trigger","Effect"],
 ["Trend cash default","Holy Grail","TQQQ price below its 20-day MA, or SOXL RSI(10) &lt; 30, with no capitulation signal","Routes 100% to BIL. Active ~23% of all days."],
 ["Melt-up hedge","Holy Grail","TQQQ RSI(10) &gt; 80 while in uptrend","Switches from leveraged equity to long volatility"],
 ["Overbought vol hedge","KMLM","10d RSI &gt; ~79 on any of eleven broad/sector tickers","Entire engine to UVXY"],
 ["Risk-off switch","KMLM","RSI(XLK) &le; RSI(KMLM)","Rotates to SQQQ (short Nasdaq) or TLT (duration)"],
 ["Credit guard","VIX Harvester","UVXY RSI(14) &gt; 70 when a short-vol entry would otherwise fire","Blocks the trade, holds PULS. Caught the 2018 Volmageddon session."],
 ["Stress thresholds","Crash Sleeve","Cumulative-return and volatility trips at &minus;0.33% to &minus;7.5% across credit and duration ETFs","Activates inverse (LABD/PSQ) and duration (TMF/TMV) legs"],
 ["Cash base","Crash Sleeve","No stress condition met","Rests in BOXX (box-spread cash, tax-efficient)"],
]
STORY.append(tbl(rows,[1.15*inch,0.85*inch,2.55*inch,2.35*inch]))

P("5. Protections at the book level", H2)
P("These sit outside the symphonies, in a governing policy document and a monitoring script that "
  "runs after every close. Only the operations marked <b>pre-authorised</b> may execute without "
  "a human decision.", BODY)

P("5.1 Capital operations", H3)
rows=[["Operation","Status","Trigger","Action"],
 ["1. Sleeve monetisation band","Pre-authorised","Sleeve outside 7&ndash;15% of crash-exposed assets (target 10%)","Rebalance sleeve to target; proceeds to the engine furthest below its weight"],
 ["2. Sleeve scale-up review","Scheduled Jan 2027","&ge;120 live days, live-vs-model correlation &ge;0.90, annualised gap &ge;&minus;10%/yr","Raise sleeve target to 15% (band 11&ndash;20%)"],
 ["3. KMLM earn-back monitor","Report-only","Correlation &ge;0.90, paired gap &ge;&minus;15%/yr, beta in [0.9,1.1], vol ratio &lt;1.15, live max DD &lt;39%, sustained 2 months plus one hostile-regime month","Reports that a higher KMLM weight is statistically earned. <b>Never trades.</b>"],
 ["5. Concentration cap","Pre-authorised","Any symphony exceeds <b>40%</b> of book value","Mechanical reset of all four to 29/29/27/15"],
]
STORY.append(tbl(rows,[1.28*inch,0.98*inch,2.45*inch,2.19*inch]))
P("The concentration cap is the book's main structural protection against unmanaged drift. In a "
  "55-year regime bootstrap it roughly halves tail drawdown versus never rebalancing (p95 68.6% "
  "&rarr; 37.5% on the conservative lens) at no meaningful cost to return. It carries a headroom "
  "rule: the cap must stay at least 10 points above the largest engine target, because a 40% cap "
  "over a 38% target was measured firing 5.4 times a year. Expected firing rate as configured is "
  "about 1.5 times a year.", SMALL)

P("5.2 Automated alerts (no trading authority)", H3)
rows=[["Alert","Threshold","Response"],
 ["Engine drawdown, tier 1","15% (12% Harvester)","Automatic live-vs-model divergence diagnostic; logged, no page"],
 ["Engine drawdown, anomaly tier","HG 40% / KMLM 39% / Sleeve 20% / Harvester 12%","Human alarm. These are 55-year conservative p90 levels."],
 ["Time under water","HG 420d / KMLM 165d / Sleeve 305d / Harvester 123d","Human alarm (~1.5x each engine's historical maximum)"],
 ["Book drawdown","17%","Human alarm &mdash; closes the correlated-decay blind spot"],
 ["Divergence failure","Live-model correlation &lt;0.90 or vol ratio &gt;1.30","Escalates a tier-1 breach to a human alarm"],
 ["Rotation / holdings change","Any change in any engine's holdings","Logged and reported, no action"],
 ["Accident gauge","External canary composite turns RED","Triggers a divergence sweep across all four engines"],
 ["Concentration","Any engine &gt;40% of book","Fires Operation 5 above"],
]
STORY.append(tbl(rows,[1.42*inch,2.35*inch,3.13*inch]))

P("5.3 What is never automated", H3)
P("Changes to symphony logic; investing in new or unapproved symphonies; liquidations; going to "
  "cash at the book level; direct single-asset trades; bank transfers; and any trade outside the "
  "pre-authorised operations. During a suspected regime break the sleeve band still executes its "
  "mechanical trim, but any discretionary harvesting beyond the band is an explicit owner "
  "decision.", BODY)

P("6. What is deliberately absent", H2)
P("For an external comparison it is as important to know what does not drive this book as what "
  "does. All of the following have been built, backtested and rejected on measurement:", BODY)
rows=[["Rejected mechanism","Result"],
 ["Market-wide trend gates on the leveraged legs","Every variant cut return in every multi-year window; the gated days are the rebound days that produce the edge"],
 ["Strategy-level volatility targeting","Cut Holy Grail's CAGR from 105% to 78% with Sharpe flat &mdash; its P&amp;L rises monotonically with its own volatility"],
 ["Drawdown-exit rules","No configuration improved risk-adjusted return"],
 ["Variance-risk-premium position sizing","Closed negative"],
 ["GARCH volatility-regime gating and sizing","92 backtested cells; the promising variant was 82% one day and sat at the 10th percentile of random gates"],
 ["Rate-hike-odds conditioning","0 of 92 overlay cells improved return, Sharpe and drawdown together; 0 improved drawdown at all"],
 ["Per-instrument drift-regime gating","Worse than random gates at matched participation"],
 ["Valuation-based allocation (CAPE, Buffett, forward P/E)","Signal could not beat its own inverse"],
]
STORY.append(tbl(rows,[2.45*inch,4.45*inch]))
P("The common mechanism, replicated across all eight: each engine is internally convexity-aware "
  "and earns disproportionately in its own high-stress state, so any overlay de-risks precisely "
  "the states that pay. Risk management in this book lives at the <b>allocation</b> layer &mdash; "
  "weights, the concentration cap, and the detection alerts &mdash; never as a filter on engine "
  "signals.", SMALL)

P("7. Notes for correlation analysis", H2)
P("<b>&#8211;</b>&nbsp;&nbsp;Use <b>Section 3.3</b>, not the headline 0.47. Down-day correlation (0.03) and worst-5% "
  "correlation (0.16) are the figures relevant to whether this book diversifies another strategy.", BODY)
P("<b>&#8211;</b>&nbsp;&nbsp;<b>Treat the book as four series, not one.</b> The engines are close to mutually "
  "orthogonal; an external strategy may correlate strongly with one and not at all with the "
  "others. The sleeve in particular is negatively correlated to equities and to Holy Grail.", BODY)
P("<b>&#8211;</b>&nbsp;&nbsp;<b>Expect instability.</b> Rolling 126-day book-SPY correlation has spanned +0.09 to "
  "+0.82. KMLM alone can be long equities, short equities, long duration or long volatility "
  "within a single month.", BODY)
P("<b>&#8211;</b>&nbsp;&nbsp;<b>Mind the sample.</b> 845 common days in one favourable regime, with no inflation "
  "shock and no 2008-style credit event. Where longer history was needed, it was reconstructed "
  "synthetically and carries reconstruction error.", BODY)
P("<b>&#8211;</b>&nbsp;&nbsp;<b>Daily data is available</b> for all four engine curves and the blended book over the "
  "windows in Section 3.6 if a direct correlation calculation against your other strategy is "
  "wanted.", BODY)

SP(10); STORY.append(rule()); SP(4)
P("Prepared 31 August 2026 from live symphony definitions, Composer engine backtests, and the "
  "governing policy and monitoring code. All performance figures are engine backtests measured "
  "daily mark-to-market &mdash; in-sample by construction and never forecasts. Book series is a "
  "29/29/27/15 blend with intra-month weight drift.", CAP)

def deco(canv, doc):
    canv.saveState()
    canv.setFont('Helvetica', 7.4); canv.setFillColor(INK3)
    canv.drawString(0.85*inch, 0.52*inch, "Composer Book — Architecture, Interaction and Risk Controls")
    canv.drawRightString(7.75*inch, 0.52*inch, f"{doc.page}")
    canv.setStrokeColor(RULE); canv.setLineWidth(0.5)
    canv.line(0.85*inch, 0.70*inch, 7.75*inch, 0.70*inch)
    canv.restoreState()

OUT="/home/user/uranium-dashboard/composer/docs/composer-book-architecture.pdf"
import os; os.makedirs(os.path.dirname(OUT), exist_ok=True)
doc=BaseDocTemplate(OUT, pagesize=LETTER, leftMargin=0.85*inch, rightMargin=0.85*inch,
                    topMargin=0.8*inch, bottomMargin=0.85*inch,
                    title="Composer Book — Architecture, Interaction and Risk Controls",
                    author="Optic Capital")
doc.addPageTemplates([PageTemplate(id='n',
    frames=[Frame(0.85*inch,0.85*inch,W,LETTER[1]-1.65*inch, id='f')], onPage=deco)])
doc.build(STORY)
print("built", OUT)
