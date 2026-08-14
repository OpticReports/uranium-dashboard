#!/usr/bin/env python3
"""Build the self-contained HTML report (figures embedded as data URIs)."""
import base64
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "figs")
OUT = os.path.join(HERE, "REPORT.html")


def img(name):
    with open(os.path.join(FIGS, name), "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def figure(name, caption, lede=None):
    return f"""<figure>
  <div class="plate"><img src="{img(name)}" alt="{caption}"></div>
  <figcaption>{'<b>' + lede + '</b> ' if lede else ''}{caption}</figcaption>
</figure>"""


CSS = """
:root{
  color-scheme: light;
  --ground:#f6f6f3; --surface:#ffffff; --sunken:#efefea;
  --ink:#15171c; --ink-2:#4b515b; --ink-3:#7b818c;
  --rule:#dedcd5; --rule-2:#c9c7bf;
  --accent:#2a78d6; --accent-soft:#e8f0fb;
  --pos:#1a7f5a; --neg:#c33f3e; --warn:#a97400;
  --plate:#fcfcfb;
  --measure:70ch;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --ground:#14161a; --surface:#1b1e24; --sunken:#22262d;
    --ink:#f2f3f5; --ink-2:#b6bcc6; --ink-3:#868d99;
    --rule:#2c313a; --rule-2:#3a4049;
    --accent:#5f9ff0; --accent-soft:#1d2a3d;
    --pos:#43c191; --neg:#f0736f; --warn:#d9a326;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --ground:#14161a; --surface:#1b1e24; --sunken:#22262d;
  --ink:#f2f3f5; --ink-2:#b6bcc6; --ink-3:#868d99;
  --rule:#2c313a; --rule-2:#3a4049;
  --accent:#5f9ff0; --accent-soft:#1d2a3d;
  --pos:#43c191; --neg:#f0736f; --warn:#d9a326;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:16px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px 96px}
.col{max-width:var(--measure)}
h1,h2,h3{font-family:Georgia,"Iowan Old Style","Times New Roman",serif;
  font-weight:600; text-wrap:balance; letter-spacing:-.01em}
h1{font-size:clamp(2rem,4.4vw,3rem);line-height:1.12;margin:0 0 .4em}
h2{font-size:1.65rem;line-height:1.2;margin:0}
h3{font-size:1.12rem;margin:2.4rem 0 .6rem}
p{margin:0 0 1rem}
a{color:var(--accent)}
.eyebrow{font-size:.72rem;font-weight:600;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-3);
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
header.masthead{border-bottom:2px solid var(--ink);padding:56px 0 24px;margin-bottom:40px}
.dek{font-size:1.12rem;color:var(--ink-2);max-width:62ch;margin:0}
.meta{display:flex;flex-wrap:wrap;gap:8px 22px;margin-top:22px;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:.76rem;color:var(--ink-3)}

/* section headers carry the study's real step order */
section{margin-top:64px}
.shead{display:flex;align-items:baseline;gap:14px;
  border-bottom:1px solid var(--rule);padding-bottom:10px;margin-bottom:26px}
.snum{font-family:ui-monospace,monospace;font-size:.8rem;font-weight:600;
  color:var(--accent)}

/* verdict */
.verdict{background:var(--surface);border:1px solid var(--rule);
  border-radius:3px;padding:28px 30px;margin:0 0 34px}
.verdict .line{font-family:Georgia,serif;font-size:1.4rem;line-height:1.35;
  margin:0 0 18px;text-wrap:balance}
.stats{display:grid;gap:1px;background:var(--rule);
  grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  border:1px solid var(--rule);border-radius:3px;overflow:hidden;margin:26px 0 8px}
.stat{background:var(--surface);padding:16px 18px}
.stat .k{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;
  color:var(--ink-3);font-family:ui-monospace,monospace;margin-bottom:6px}
.stat .v{font-size:1.5rem;font-weight:600;font-variant-numeric:tabular-nums;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;line-height:1.1}
.stat .n{font-size:.78rem;color:var(--ink-3);margin-top:4px}
.v.pos{color:var(--pos)} .v.neg{color:var(--neg)} .v.acc{color:var(--accent)}

/* tables */
.scroll{overflow-x:auto;margin:20px 0 8px;border:1px solid var(--rule);
  border-radius:3px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.83rem;
  font-variant-numeric:tabular-nums}
th,td{padding:9px 13px;text-align:right;white-space:nowrap;
  border-bottom:1px solid var(--rule)}
th:first-child,td:first-child{text-align:left}
thead th{background:var(--sunken);font-size:.7rem;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ink-2);font-weight:600;
  position:sticky;top:0}
tbody tr:last-child td{border-bottom:0}
tr.hi td{background:var(--accent-soft);font-weight:600}
tr.bm td{color:var(--ink-2);font-style:italic}
td.pos{color:var(--pos)} td.neg{color:var(--neg)}
caption{caption-side:top;text-align:left;padding:12px 13px 0;
  font-size:.8rem;color:var(--ink-3)}

/* figures */
figure{margin:34px 0}
.plate{background:var(--plate);border:1px solid var(--rule);border-radius:3px;
  padding:12px;overflow-x:auto}
.plate img{display:block;width:100%;height:auto;min-width:620px}
figcaption{font-size:.83rem;color:var(--ink-2);margin-top:11px;max-width:78ch}
figcaption b{color:var(--ink)}

/* callouts */
.note{border-left:3px solid var(--accent);background:var(--surface);
  padding:16px 20px;margin:24px 0;font-size:.92rem}
.note.warn{border-left-color:var(--warn)}
.note .lbl{font-family:ui-monospace,monospace;font-size:.7rem;font-weight:600;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);
  display:block;margin-bottom:6px}
ul{margin:0 0 1rem;padding-left:1.15rem}
li{margin-bottom:.42rem}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86em;
  background:var(--sunken);padding:1px 5px;border-radius:2px}
.eq{font-family:ui-monospace,monospace;font-size:.86rem;background:var(--sunken);
  padding:14px 16px;border-radius:3px;overflow-x:auto;margin:16px 0}
footer{margin-top:76px;padding-top:22px;border-top:1px solid var(--rule);
  font-size:.8rem;color:var(--ink-3)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (prefers-reduced-motion:no-preference){
  .stat{transition:background .15s ease}
}
"""


def main():
    html = f"""<title>SOXL Dispersion Teardown</title>
<style>{CSS}</style>
<div class="wrap">

<header class="masthead">
  <div class="eyebrow">Quant research &middot; frozen backtest</div>
  <h1>Short SOXL, long the winners</h1>
  <p class="dek">A full teardown of the 25/75 leveraged-ETF dispersion trade:
  where the P&amp;L actually comes from, what survives out of sample, and what
  it would take to run it.</p>
  <div class="meta">
    <span>2010-03-12 &rarr; 2026-08-14</span>
    <span>4,132 trading days</span>
    <span>108-name PIT universe</span>
    <span>Sharpe quoted excess of 3m bill</span>
    <span>16 gate tests green</span>
  </div>
</header>

<div class="verdict">
  <p class="line">The book is genuinely market-neutral &mdash; and the durable
  edge inside it is about <b>1.4% a year</b>. Everything above that is rent on a
  high-volatility regime that 2026 is taking back.</p>
  <div class="stats">
    <div class="stat"><div class="k">Seed strategy CAGR</div>
      <div class="v neg">3.1%</div><div class="n">0.21 Sharpe, &minus;41.5% maxDD</div></div>
    <div class="stat"><div class="k">In-sample &le;2019</div>
      <div class="v neg">&minus;0.7%</div><div class="n">lost money for a decade</div></div>
    <div class="stat"><div class="k">75% basket + cash</div>
      <div class="v pos">20.7%</div><div class="n">0.90 Sharpe &mdash; the thing it loses to</div></div>
    <div class="stat"><div class="k">Net beta to SOXX</div>
      <div class="v acc">&minus;0.07</div><div class="n">not disguised beta</div></div>
    <div class="stat"><div class="k">Harvestable edge</div>
      <div class="v acc">1.35%</div><div class="n">ETF fee drag &times; 25% notional</div></div>
    <div class="stat"><div class="k">Repeatable?</div>
      <div class="v">~20%</div><div class="n">probability it is alpha, not regime</div></div>
  </div>
</div>

{figure("equity.png",
  "The seed strategy (blue) turned $1 into $1.60 over 16 years while the "
  "same basket held long with 25% in cash turned it into $21.80. Rebalancing "
  "weekly instead of monthly (aqua) roughly doubles the result and halves the "
  "drawdown &mdash; cadence, not selection, is the lever.",
  "Growth of $1, net of all modelled costs.")}

<section>
  <div class="shead"><span class="snum">STEP 1</span><h2>What shorting SOXL actually pays</h2></div>
  <div class="col">
  <p>Regressing SOXL on SOXX daily gives &beta; = <b>2.9625</b> and
  &alpha; = <b>&minus;5.39%/yr</b> (SE 1.78%, t = &minus;3.02). That alpha is the
  fund's expense ratio plus the financing spread on its 2&times; borrowed
  notional, and it is the <em>only</em> part of "decay" a hedged book can bank.</p>
  <p>The famous variance drag is a different term entirely:</p>
  </div>
  <div class="eq">log(SOXL_T) &minus; 3&middot;log(SOXX_T) = &minus;(3&sup2;&minus;3)/2 &middot; &sigma;&sup2; &middot; T &minus; fees&middot;T</div>
  <div class="col">
  <p>Realized: <b>&minus;34.4%/yr</b> of log return. Theory at &sigma; = 30.8%:
  28.5% drag + 5.4% fees = 33.9%/yr. The identity holds to half a point. But it
  only accrues to a position you let ride:</p>
  </div>

  <div class="scroll"><table>
    <caption>Short 1&times; SOXL / long 3&times; SOXX on 1&times; capital, gross of costs.</caption>
    <thead><tr><th>Reset cadence</th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>Max DD</th><th>Skew</th></tr></thead>
    <tbody>
      <tr><td>Daily</td><td>6.2%</td><td>7.3%</td><td>0.86</td><td>&minus;13.5%</td><td>+10.4</td></tr>
      <tr><td>Weekly</td><td>9.0%</td><td>10.6%</td><td>0.87</td><td>&minus;13.4%</td><td>+4.6</td></tr>
      <tr><td>Monthly</td><td>9.3%</td><td>16.8%</td><td>0.61</td><td>&minus;25.8%</td><td>+2.6</td></tr>
      <tr><td>Quarterly</td><td colspan="5" style="text-align:left;color:var(--neg);font-weight:600">Wiped out</td></tr>
      <tr><td>Never (static)</td><td colspan="5" style="text-align:left;color:var(--neg);font-weight:600">Wiped out</td></tr>
    </tbody>
  </table></div>

  {figure("cadence.png",
    "The same trade at five rebalance cadences. Variance drag is a "
    "mean-versus-median effect: shorting it converts a positive-skew payoff "
    "into a negative-skew one. Quarterly and static both go to zero.",
    "Decay harvesting is not a carry trade &mdash; it is short gamma.")}

  <h3>The book really is neutral</h3>
  <div class="col">
  <p>Top-8 cap-weighted basket &beta; = 0.895 (below 1, because SOXX's 8%/4%
  caps push weight into smaller high-beta names). Against 0.25 &times; 2.963 on
  the short leg, V0's net beta is <b>&minus;0.069</b> &mdash; measured and implied
  agree. Rolling 126-day beta is positive only 16% of the time. Neutrality
  <em>cost</em> the book 31 points of return in a semis bull market; the alpha
  did all the work.</p>
  </div>

  {figure("attribution.png",
    "The long basket compounds; the short leg is a persistent drag that buys "
    "beta neutrality. The combined book is the difference &mdash; small, and "
    "flat for its first decade.",
    "Cumulative P&amp;L by leg.")}

  <h3>&ldquo;Own the winners&rdquo; is one stock</h3>
  <div class="scroll"><table>
    <thead><tr><th>Basket</th><th>CAGR</th><th>&beta;</th><th>&alpha;/yr</th><th>t(&alpha;)</th><th>IR</th></tr></thead>
    <tbody>
      <tr><td>Top-3 cap-weighted</td><td>27.1%</td><td>0.87</td><td>+5.13%</td><td>1.33</td><td>0.33</td></tr>
      <tr><td>Top-8 cap-weighted</td><td>27.1%</td><td>0.90</td><td>+3.95%</td><td>1.47</td><td>0.36</td></tr>
      <tr><td>Top-12 cap-weighted</td><td>26.8%</td><td>0.91</td><td>+3.26%</td><td>1.37</td><td>0.34</td></tr>
      <tr><td>Top-8 equal-weight</td><td>27.7%</td><td>0.94</td><td>+3.22%</td><td>1.86</td><td>0.46</td></tr>
      <tr><td>Top-8 6mo momentum</td><td>27.4%</td><td>1.08</td><td>+1.10%</td><td>0.35</td><td>0.09</td></tr>
      <tr class="hi"><td>Top-8 <b>excluding NVDA</b></td><td>&mdash;</td><td>0.88</td><td>+1.09%</td><td>0.49</td><td>&mdash;</td></tr>
    </tbody>
  </table></div>
  <div class="note">
    <span class="lbl">Finding</span>
    Nothing clears t = 2. Ex-NVDA the alpha collapses to +1.09%/yr at t = 0.49,
    and re-applying the index's own caps barely moves it (+3.75%) &mdash; so it
    is not &ldquo;we let winners run&rdquo;, it is &ldquo;we owned NVDA&rdquo;.
    Subperiod alphas: +3.51% (2010-14), <b>&minus;1.95%</b> (2015-19), +9.18% (2020-26).
  </div>
</section>

<section>
  <div class="shead"><span class="snum">STEP 3</span><h2>Variants</h2></div>
  <div class="scroll"><table>
    <caption>Full period, net of all modelled costs. Sharpe excess of the 3m bill.</caption>
    <thead><tr><th>Variant</th><th>CAGR net</th><th>CAGR gross</th><th>Vol</th>
      <th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>&beta; SOXX</th>
      <th>Trades/yr</th><th>Turnover</th><th>Worst 12m</th></tr></thead>
    <tbody>
      <tr class="hi"><td>V0 &mdash; seed: 25/75 top-8, monthly</td><td>3.1%</td><td>3.5%</td><td>10.1%</td><td>0.21</td><td>0.27</td><td class="neg">&minus;41.5%</td><td>&minus;0.05</td><td>111</td><td>1.68&times;</td><td>&minus;35.2%</td></tr>
      <tr><td>V1 &mdash; beta-neutral hedge ratio</td><td>5.8%</td><td>6.2%</td><td>9.3%</td><td>0.50</td><td>0.65</td><td>&minus;32.3%</td><td>0.01</td><td>111</td><td>1.92&times;</td><td>&minus;26.1%</td></tr>
      <tr><td>V2 &mdash; vol-targeted 15%</td><td>2.8%</td><td>3.8%</td><td>18.1%</td><td>0.16</td><td>0.23</td><td class="neg">&minus;58.5%</td><td>&minus;0.08</td><td>111</td><td>4.30&times;</td><td>&minus;40.4%</td></tr>
      <tr><td>V3 &mdash; top-8 equal-weight</td><td>4.0%</td><td>4.4%</td><td>7.1%</td><td>0.38</td><td>0.48</td><td>&minus;21.7%</td><td>&minus;0.01</td><td>111</td><td>2.32&times;</td><td>&minus;9.7%</td></tr>
      <tr><td>V4 &mdash; decay-pure, monthly</td><td>2.9%</td><td>3.3%</td><td>4.4%</td><td>0.35</td><td>0.43</td><td>&minus;12.4%</td><td>0.03</td><td>24</td><td>1.52&times;</td><td>&minus;8.4%</td></tr>
      <tr><td>V4.d &mdash; decay-pure, daily</td><td>1.8%</td><td>2.3%</td><td>1.8%</td><td>0.19</td><td>0.28</td><td>&minus;3.6%</td><td>0.01</td><td>504</td><td>5.69&times;</td><td>&minus;0.6%</td></tr>
      <tr><td>V5 &mdash; double decay (SOXL+SOXS)</td><td>20.0%</td><td>21.6%</td><td>20.5%</td><td>0.92</td><td>1.30</td><td>&minus;28.1%</td><td class="neg">0.51</td><td>123</td><td>9.44&times;</td><td>&minus;16.2%</td></tr>
      <tr><td>V7 &mdash; gated (&lt;200dma &amp; vol&gt;med)</td><td>2.2%</td><td>2.5%</td><td>4.1%</td><td>0.19</td><td>0.11</td><td>&minus;12.9%</td><td>&minus;0.01</td><td>26</td><td>1.82&times;</td><td>&minus;7.7%</td></tr>
      <tr><td>V8 &mdash; drift-band &plusmn;5%</td><td>4.1%</td><td>4.6%</td><td>8.7%</td><td>0.34</td><td>0.49</td><td>&minus;27.6%</td><td>&minus;0.06</td><td>166</td><td>2.46&times;</td><td>&minus;20.3%</td></tr>
      <tr class="hi"><td>V0.W &mdash; <b>weekly rebalance</b></td><td>7.2%</td><td>7.7%</td><td>8.9%</td><td>0.67</td><td>0.97</td><td>&minus;23.3%</td><td>&minus;0.06</td><td>476</td><td>4.53&times;</td><td>&minus;15.6%</td></tr>
      <tr><td>V0.D &mdash; daily rebalance</td><td>6.7%</td><td>7.4%</td><td>8.6%</td><td>0.64</td><td>0.93</td><td>&minus;24.1%</td><td>&minus;0.07</td><td>2,271</td><td>9.47&times;</td><td>&minus;17.0%</td></tr>
      <tr><td>V0.Q &mdash; quarterly <b>(1 margin call)</b></td><td>1.5%</td><td>1.9%</td><td>12.7%</td><td>0.07</td><td>0.08</td><td class="neg">&minus;55.9%</td><td>&minus;0.07</td><td>38</td><td>1.11&times;</td><td>&minus;50.6%</td></tr>
      <tr class="bm"><td>Benchmark &mdash; SOXX long-only</td><td>25.2%</td><td>25.2%</td><td>30.8%</td><td>0.84</td><td>1.16</td><td>&minus;45.8%</td><td>1.00</td><td>0</td><td>0.06&times;</td><td>&minus;35.1%</td></tr>
      <tr class="bm"><td>Benchmark &mdash; 75% basket + 25% cash</td><td>20.7%</td><td>20.8%</td><td>22.2%</td><td>0.90</td><td>1.23</td><td>&minus;40.5%</td><td>0.67</td><td>99</td><td>1.48&times;</td><td>&minus;28.7%</td></tr>
    </tbody>
  </table></div>
  <div class="note warn">
    <span class="lbl">Mislabelled by tradition</span>
    V5's &ldquo;double decay&rdquo; is not neutral. Once the two ETF shorts cancel,
    the long basket overlay is unhedged: &beta; 0.51 to SOXX, 0.84 to SPY. Its
    20% CAGR is mostly beta, and it carries the hardest-to-borrow leg in the study.
  </div>

  {figure("yearly.png",
    "Eight losing years, then +66% in 2024 (when SOXX rose 12.9% but SOXL fell "
    "12.3% on 34.6% vol), then &minus;31% in 2026 as SOXL ran +243% YTD. That "
    "sequence is the strategy working exactly as designed.",
    "V0 calendar-year net return.")}

  {figure("convexity.png",
    "Monthly book return against SOXX. Both fits curve downward &mdash; the "
    "book is short convexity &mdash; but weekly rebalancing visibly flattens "
    "the left tail. That is what the extra 4 points of CAGR buys.",
    "The short-gamma signature, and what cadence does to it.")}
</section>

<section>
  <div class="shead"><span class="snum">STEP 2</span><h2>Does it survive out of sample?</h2></div>
  <div class="scroll"><table>
    <thead><tr><th>Variant</th><th>IS &le;2019 CAGR</th><th>IS Sharpe</th>
      <th>OOS 2020+ CAGR</th><th>OOS Sharpe</th></tr></thead>
    <tbody>
      <tr class="hi"><td>V0 (seed)</td><td class="neg">&minus;0.7%</td><td class="neg">&minus;0.14</td><td>8.8%</td><td>0.47</td></tr>
      <tr><td>V0.W (weekly)</td><td>1.5%</td><td>0.19</td><td>16.4%</td><td>1.11</td></tr>
      <tr><td>V1 (beta-neutral)</td><td>1.9%</td><td>0.27</td><td>11.6%</td><td>0.70</td></tr>
      <tr class="bm"><td>75% basket + 25% cash</td><td>13.0%</td><td>0.83</td><td>33.4%</td><td>1.04</td></tr>
    </tbody>
  </table></div>
  <div class="note warn">
    <span class="lbl">Not the usual overfit signature</span>
    This is the reverse of curve-fitting: bad in sample, good out of sample.
    That is <b>regime dependence</b>, and it is worse in one specific way &mdash;
    the standard out-of-sample test cannot detect it, and it reverts when the
    regime does.
  </div>

  {figure("heatmap.png",
    "Sharpe across basket size and rebalance cadence. Read down a column, not "
    "across a row: cadence moves Sharpe far more than the number of names, and "
    "every cell is negative-to-flat in sample.",
    "Parameter sensitivity.")}

  <h3>Confidence intervals and walk-forward</h3>
  <div class="scroll"><table>
    <caption>Block bootstrap, 2,000 resamples, 21-day blocks.</caption>
    <thead><tr><th>Variant</th><th>CAGR median</th><th>5th</th><th>95th</th>
      <th>Sharpe median</th><th>Sharpe 5th</th><th>P(CAGR&lt;0)</th></tr></thead>
    <tbody>
      <tr><td>V0 monthly</td><td>3.1%</td><td class="neg">&minus;1.4%</td><td>7.4%</td><td>0.35</td><td>&minus;0.08</td><td>14%</td></tr>
      <tr class="hi"><td>V0.W weekly</td><td>7.2%</td><td>3.6%</td><td>10.9%</td><td>0.83</td><td>0.44</td><td>0%</td></tr>
      <tr><td>V0.D daily</td><td>6.6%</td><td>3.1%</td><td>10.4%</td><td>0.80</td><td>0.40</td><td>0%</td></tr>
    </tbody>
  </table></div>
  <div class="col">
  <p><b>Walk-forward</b> &mdash; choosing the configuration each year on data seen
  so far, then trading it the next year &mdash; compounds at <b>6.5%/yr, Sharpe
  0.48</b>. The 75% basket + cash alternative compounds at 19.5% over the same
  windows. The configuration changed in 5 of 15 years.</p>
  </div>
</section>

<section>
  <div class="shead"><span class="snum">STEP 4</span><h2>Gates</h2></div>
  <div class="scroll"><table>
    <caption>Applied to the book, net of costs, with the overfit screen.</caption>
    <thead><tr><th>Gate</th><th>% on</th><th>ON annualized</th><th>ON Sharpe</th>
      <th>IS Sharpe</th><th>OOS Sharpe</th><th>Verdict</th></tr></thead>
    <tbody>
      <tr><td>Ungated V0</td><td>100%</td><td>+3.1%</td><td>0.21</td><td class="neg">&minus;0.14</td><td>0.47</td><td>No IS edge</td></tr>
      <tr><td>SOXX &lt; 200dma</td><td>23%</td><td>+6.8%</td><td>0.64</td><td>0.01</td><td>0.16</td><td>~zero IS</td></tr>
      <tr><td>VIX term structure inverted</td><td>8%</td><td>+23.5%</td><td>1.84</td><td class="neg">&minus;0.18</td><td class="neg">&minus;0.57</td><td>No IS edge</td></tr>
      <tr><td>Dispersion &gt; 1y 75th pct</td><td>28%</td><td>+0.6%</td><td>0.06</td><td class="neg">&minus;0.34</td><td>0.44</td><td>No IS edge</td></tr>
      <tr><td>SOX/SPX 6mo momentum &lt; 0</td><td>34%</td><td>+6.8%</td><td>0.74</td><td class="neg">&minus;0.11</td><td>0.60</td><td>No IS edge</td></tr>
      <tr class="hi"><td>&lt;200dma <b>AND</b> vol &gt; median</td><td>18%</td><td>+8.2%</td><td>0.75</td><td>0.17</td><td>0.23</td><td><b>Only survivor</b></td></tr>
    </tbody>
  </table></div>
  <div class="note">
    <span class="lbl">Three things worth stating plainly</span>
    <ul>
      <li><b>Conditional tables flatter rare gates.</b> VIX-inverted looks
      spectacular at 1.84 ON-Sharpe but is on 8% of the time; applied, it
      returns a &minus;0.57 out-of-sample Sharpe.</li>
      <li><b>Gating reduces total return in every case.</b> The book is
      near-neutral and cheap to hold, so time in cash is pure opportunity cost.
      Gates buy Sharpe-per-unit-exposure, not compounding.</li>
      <li><b>Exactly one gate is positive in both halves</b>, and only at ~0.2.</li>
    </ul>
  </div>
</section>

<section>
  <div class="shead"><span class="snum">STEP 5</span><h2>What it is betting on</h2></div>
  <div class="scroll"><table>
    <caption>Empirical forward 12-month outcomes for V0.W, conditioned on the regime at entry.</caption>
    <thead><tr><th>Regime</th><th>Windows</th><th>Median</th><th>5th</th>
      <th>Worst</th><th>Best</th><th>P(loss)</th></tr></thead>
    <tbody>
      <tr class="hi"><td>(a) Semi bull / AI capex melt-up</td><td>1,861</td><td>+1.1%</td><td>&minus;5.9%</td><td>&minus;13.2%</td><td>+66.2%</td><td class="neg">43%</td></tr>
      <tr><td>(b) Sideways high-vol chop</td><td>1,027</td><td>+5.8%</td><td>&minus;6.6%</td><td>&minus;16.0%</td><td>+55.7%</td><td>20%</td></tr>
      <tr><td>(c) Cyclical downturn</td><td>956</td><td>+6.0%</td><td>&minus;6.8%</td><td>&minus;16.0%</td><td>+53.9%</td><td>22%</td></tr>
      <tr><td>(d) Vol spike (top-decile)</td><td>336</td><td class="pos">+9.8%</td><td>&minus;0.3%</td><td>&minus;6.7%</td><td>+46.4%</td><td>5%</td></tr>
      <tr class="bm"><td>Unconditional</td><td>3,879</td><td>+5.0%</td><td>&minus;6.2%</td><td>&minus;16.0%</td><td>+67.0%</td><td>29%</td></tr>
    </tbody>
  </table></div>
  <div class="col">
  <p><b>This strategy is short the melt-up and long volatility.</b> In the regime
  semis have actually been in, it is a coin flip with a +1.1% median. It earns
  its keep in chop and vol spikes.</p>
  </div>

  <h3>Edge attribution</h3>
  <div class="scroll"><table>
    <thead><tr><th>Driver</th><th>Contribution</th><th>Durable?</th></tr></thead>
    <tbody>
      <tr><td>ETF fee / financing harvest</td><td>+1.35%/yr</td><td style="text-align:left"><b>Yes &mdash; structural.</b> Shrinks only if Direxion cuts fees or rates collapse.</td></tr>
      <tr><td>Concentration / &ldquo;winners&rdquo;</td><td>+2.96%/yr</td><td style="text-align:left"><b>No.</b> t = 1.47; ex-NVDA t = 0.49; negative 2015&ndash;19.</td></tr>
      <tr><td>Residual beta</td><td>&minus;1.7%/yr</td><td style="text-align:left">A cost of neutrality, not an edge.</td></tr>
      <tr><td>Rebalancing convexity control</td><td>+4.1%/yr</td><td style="text-align:left"><b>Partly.</b> Mechanical, but it is buying gamma &mdash; payoff depends on realized vol staying high.</td></tr>
    </tbody>
  </table></div>

  <h3>Kill criteria</h3>
  <div class="col"><ul>
    <li>Rolling 24-month Sharpe &lt; 0.</li>
    <li>SOXL borrow &gt; <b>5.4%/yr</b> sustained (short-leg carry edge gone);
    hard stop at 23.5%/yr, where the whole book underperforms cash.</li>
    <li>SOXL's measured &alpha; vs SOXX decays above &minus;2%/yr on a trailing
    2-year window &mdash; the structural edge itself is gone.</li>
    <li>Realized SOXX vol &lt; 20% for six consecutive months.</li>
    <li>Net beta outside &plusmn;0.20 for 20 consecutive days.</li>
    <li>Drawdown &gt; 25% from high-water mark.</li>
  </ul></div>
</section>

<section>
  <div class="shead"><span class="snum">AUDIT</span><h2>What could still be wrong</h2></div>
  <div class="col">
  <p>Findings were attacked before publication. Seven adversarial checks, all
  passed: look-ahead (lagging selection 5 days costs 1.21pp, no collapse),
  survivorship (measured at <b>+0.06pp</b> of fake CAGR), stale marks (max
  internal gap 1 day), engine-vs-closed-form reconciliation, cost monotonicity,
  partial-year dependence, and reconstruction artifact.</p>
  <p>Two engine bugs the pass caught <em>before</em> any number shipped:</p>
  <ul>
    <li><b>No margin model.</b> The engine ran a drifted quarterly book at
    116&times; gross leverage on 5% equity and reported a Sharpe for it. With
    forced liquidation at maintenance breach, V0.Q's honest result is 1.5% CAGR
    and &minus;55.9% maxDD with one margin call.</li>
    <li><b>&ldquo;Gross&rdquo; silently meant &ldquo;earns no interest&rdquo;</b>,
    making gross look worse than net for credit-balance variants.</li>
  </ul>
  </div>
  <div class="note warn">
    <span class="lbl">The one input I could not source</span>
    <b>SOXL borrow-rate history.</b> No IBKR SLB or Markit series was obtainable,
    so borrow is a swept parameter with a solved breakeven, never an assumed
    constant. It does not change the verdict &mdash; the book survives to 23.5%/yr
    &mdash; but <b>send me your actual IBKR borrow rate on SOXL</b> and I will
    re-run the sweep against the real series. Episodic spikes are the risk a
    single current quote will not reveal.
  </div>
  <div class="col">
  <p>Also not modelled: intraday execution (daily closes, parametric 2&ndash;3bp
  slippage), locate availability and forced buy-ins, historical option chains for
  V6, semi-cycle fundamentals, and tax. And the block bootstrap understates
  tails &mdash; it reported P(loss &lt; &minus;20%) = 0% in every regime while the
  book was living through a &minus;31% year, which is why the scenario table uses
  empirical forward windows instead.</p>
  </div>
</section>

<footer>
  Frozen backtest &middot; FMP <code>stable</code> endpoints, fetched 2026-08-14 &middot;
  reproduce with <code>fetch_data.py</code> then <code>variants.py</code>,
  <code>gates.py</code>, <code>validation.py</code>, <code>verify.py</code> &middot;
  gate tests: <code>python3 -m pytest soxl-dispersion-lab/tests -q</code>
</footer>

</div>"""
    with open(OUT, "w") as f:
        f.write(html)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
