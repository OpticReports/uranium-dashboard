"""Render results/leverage-gate-canary-2026-10-17.html from canary_gates.json (+ a panel-B rebuild of the
signals for the timeline and today's readings)."""
import html as _html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levgate as lg              # noqa: E402
import canary_gates as cg         # noqa: E402

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results', 'leverage-gate-canary-2026-10-17.html')
FAM = [('EMA', 'Moving averages (EMA)'), ('CAPE', 'Valuation (CAPE level)'), ('Y10', 'Bond yields'), ('dY', 'Bond yields'), ('TIPS', 'Bond yields'),
       ('dTP', 'Bond yields'), ('RS', 'Yield curve (canary headline)'), ('M', 'Retail leverage (FINRA margin debt)'), ('FSI', 'Financial stress (OFR)'), ('LS', 'Leading stack')]
SHORT = {'EMA50 SPY>EMA50': 'SPY above 50-day EMA', 'EMA100 SPY>EMA100': 'SPY above 100-day EMA', 'EMA200 SPY>EMA200': 'SPY above 200-day EMA',
         'EMAx EMA50>EMA200': '50-day EMA above 200-day EMA', 'CAPE<25': 'CAPE below 25', 'CAPE<30': 'CAPE below 30', 'CAPE<35': 'CAPE below 35',
         'Y10<5% 10y yield level': '10y yield below 5%', 'Y10<6% 10y yield level': '10y yield below 6%', 'dY10<+1.0pp 10y 12m change': '10y up less than 1pp in 12m',
         'dY10<+1.5pp 10y 12m change': '10y up less than 1.5pp in 12m', 'dY2<+1.5pp 2y 12m change (Fed pace)': '2y up less than 1.5pp in 12m',
         'dY2<+2.0pp 2y 12m change (Fed pace)': '2y up less than 2pp in 12m', 'TIPS10<2% real yield': 'real 10y below 2%',
         'dTP<+0.5pp ACM term premium 6m change': 'term premium up less than 0.5pp in 6m', 'RS12 not in 12m after a dis-inversion (canary headline)': 'not in the 12m after a curve dis-inversion',
         'RSinv not inverted and not in 12m after': 'curve not inverted, nor in the 12m after', 'MG40 margin YoY<40%': 'margin debt growth below 40%',
         'MX25 margin excess growth<25pp (canary cell)': 'margin growth less than 25pp over the S&P', 'MX15 margin excess growth<15pp': 'margin growth less than 15pp over the S&P',
         'MX25SB excess>=25pp only with stock-bond corr>0 is off': 'margin excess plus positive stock-bond correlation', 'MDEL off while margin is deleveraging (YoY<0)': 'margin debt not shrinking',
         'FSI<0 OFR stress below average': 'OFR stress below average', 'FSI<1 OFR stress below +1': 'OFR stress below +1', 'LS50 canary leading stack not in alarm': 'leading stack not in alarm'}


def fam(n):
    for k, lab in FAM:
        if n.startswith(k):
            return lab
    return 'Other'


def main():
    J = json.load(open(os.path.join(lg.OUT, 'canary_gates.json')))
    R = J['B']['HG']['rows']
    sigs = [k[:-len(' [alone]')] for k in R if k.endswith(' [alone]')]
    forest = []
    for s in sigs:
        for use, key in (('alone', f'{s} [alone]'), ('with the 200-day', f'{s} [& 200d]')):
            r = R[key]
            forest.append({'sig': SHORT.get(s, s), 'fam': fam(s), 'use': use, 'lo': r['gap_vs_200d'][0][0], 'hi': r['gap_vs_200d'][0][1],
                           'p': r['gap_vs_200d'][1], 'sharpe': r['full']['sharpe'], 'cagr': r['full']['cagr'], 'dd': r['full']['maxdd'],
                           'mid': round(r['full']['sharpe'] - R['T200 SPY>200d (reference)']['full']['sharpe'], 3)})
    # timeline: rebuild the panel-B signals
    P, P1, runs = lg.engine_runs('B')
    days, h = runs['HG']
    F = cg.build(P, days)
    sets = lg.leg_sets('HG', sorted({t for d in h for t in h[d] if t in lg.LEG}))
    base = lg.gate_run(days, h, P, P1, {}, sets['trend'], lg.COST['HG'])[0]
    v, pk, dd = 1.0, 1.0, []
    for d in days[1:]:
        v *= 1 + base[d]
        pk = max(pk, v)
        dd.append(round(v / pk - 1, 4))
    idx = list(range(0, len(dd), 5)) + [len(dd) - 1]
    strips = {}
    for key, lab in (('T200 SPY>200d (reference)', 'SPY below its 200-day'), ('CAPE<35', 'CAPE 35 or higher'),
                     ('MX25 margin excess growth<25pp (canary cell)', 'margin growth 25pp+ over the S&P'),
                     ('RS12 not in 12m after a dis-inversion (canary headline)', '12 months after a curve dis-inversion'), ('Y10<5% 10y yield level', '10y yield 5% or higher')):
        lam, spans, start = F[key], [], None
        for d in days[1:]:
            off = lam.get(d, 1.0) < 1
            if off and start is None:
                start = d
            if not off and start is not None:
                spans.append([start, prev])
                start = None
            prev = d
        if start:
            spans.append([start, days[-1]])
        strips[lab] = spans
    tl = {'dates': [days[1:][i] for i in idx], 'dd': [dd[i] for i in idx], 'strips': strips}
    # today's readings (as the gates see them on the last session)
    cur = J['B']['HG']['current']
    last = days[-1]
    mg = cg.load('FINRA_DEBIT')
    mgy = cg.yoy_m(mg)
    spx = cg.yoy_m(cg.month_end(cg.yh('^GSPC')))
    km = max(k for k in mgy if k in spx)
    y10 = cg.load('UST_10Y')
    y2 = cg.load('UST_2Y')
    tips = cg.load('TIPS_10Y')
    fsi = cg.load('OFR_FSI')
    cape = json.load(open(os.path.join(lg.MAC, 'cape_multpl.json')))
    lk = lambda s: s[max(s)]   # noqa: E731

    def chg12(s):
        ks = sorted(s)
        a = s[ks[-1]]
        b = next(s[k] for k in reversed(ks) if k <= f'{int(ks[-1][:4]) - 1}{ks[-1][4:]}')
        return a - b
    spy = P['SPY']
    ma200 = lg.ma_series(spy, 200)
    reads = [('SPY vs its 200-day average', f"{(spy[last] / ma200[last] - 1) * 100:+.1f}% above", cur['T200 SPY>200d (reference)']),
             ('SPY vs its 200-day EMA', 'above', cur['EMA200 SPY>EMA200']),
             ('CAPE (latest month)', f"{cape[max(cape)]:.1f} ({max(cape)})", cur['CAPE<35']),
             ('10-year Treasury yield', f"{lk(y10):.2f}% ({max(y10)})", cur['Y10<5% 10y yield level']),
             ('10-year change over 12 months', f"{chg12(y10):+.2f}pp", cur['dY10<+1.0pp 10y 12m change']),
             ('2-year change over 12 months', f"{chg12(y2):+.2f}pp", cur['dY2<+1.5pp 2y 12m change (Fed pace)']),
             ('Real 10-year yield (TIPS)', f"{lk(tips):.2f}%", cur['TIPS10<2% real yield']),
             ('Margin debt growth (FINRA)', f"{mgy[km] * 100:+.1f}% YoY ({km})", cur['MG40 margin YoY<40%']),
             ('Margin growth over the S&P', f"{(mgy[km] - spx[km]) * 100:+.1f}pp ({km})", cur['MX25 margin excess growth<25pp (canary cell)']),
             ('OFR financial stress index', f"{lk(fsi):+.2f} ({max(fsi)})", cur['FSI<0 OFR stress below average']),
             ('Curve re-steepening window', 'closed Sep 2026 (dis-inversion Dec 2024)', cur['RS12 not in 12m after a dis-inversion (canary headline)'])]
    read_rows = ''.join(f"<tr><th scope=row>{_html.escape(a)}</th><td>{_html.escape(b)}</td><td class='{'on' if c >= 1 else 'off'}'>{'leveraged' if c >= 1 else 'de-lever'}</td></tr>" for a, b, c in reads)

    def pct(x, s=True):
        return f"{x * 100:+.1f}%" if s else f"{x * 100:.1f}%"
    all_rows = ''.join(
        f"<tr><th scope=row>{_html.escape(k)}</th><td>{pct(r['full']['cagr'])}</td><td>{r['full']['sharpe']:.2f}</td><td>{r['full']['sortino']:.2f}</td>"
        f"<td>{pct(r['full']['maxdd'], False)}</td><td>{(str(r['gap_vs_200d'][0][0]) + ' to ' + str(r['gap_vs_200d'][0][1]) + ' (P ' + str(r['gap_vs_200d'][1]) + ')') if 'gap_vs_200d' in r else ''}</td></tr>"
        for k, r in R.items())
    wins = ''.join(
        f"<tr><th scope=row>{_html.escape(n)}</th>" + ''.join(f"<td>{pct(R[k]['windows'][w]['cagr'])} <span class=dim>{pct(R[k]['windows'][w]['maxdd'], False)}</span></td>" for w in lg.WINDOWS_B) + '</tr>'
        for n, k in (('As built', 'as built'), ('200-day gate (trend baskets)', 'T200 SPY>200d (reference)'), ('CAPE below 35, with the 200-day', 'CAPE<35 [& 200d]'),
                     ('Margin growth under 25pp over the S&P, with the 200-day', 'MX25 margin excess growth<25pp (canary cell) [& 200d]'),
                     ('SPY above 100-day EMA, with the 200-day', 'EMA100 SPY>EMA100 [& 200d]')))
    page = (TEMPLATE.replace('__FOREST__', json.dumps(forest)).replace('__TL__', json.dumps(tl)).replace('__READS__', read_rows)
            .replace('__ALL__', all_rows).replace('__WINS__', wins).replace('__WINHEAD__', ''.join(f'<th>{w}</th>' for w in lg.WINDOWS_B))
            .replace('__LAST__', last))
    open(PAGE, 'w').write(page)
    print('wrote', os.path.normpath(PAGE))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canary leverage gates</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--wash:rgba(82,81,78,.14);--good:#006300;--warn:#a14b00}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--wash:rgba(195,194,183,.16);--good:#0ca30c;--warn:#ec835a}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--wash:rgba(195,194,183,.16);--good:#0ca30c;--warn:#ec835a}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1060px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}
h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 12px;font-size:14px}
.lede{font-size:17px;margin:14px 0 18px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:0 0 16px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:5px 7px;text-align:right;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums;white-space:nowrap}
th[scope=row]{text-align:left;font-weight:500;white-space:normal}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}
td.on{color:var(--good);font-weight:600} td.off{color:var(--warn);font-weight:600}
.dim{color:var(--muted);font-size:12px}
.tablewrap{overflow-x:auto}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 4px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%}
svg{display:block;width:100%;height:auto;overflow:visible}
.axis text{fill:var(--muted);font-size:11px}
.lbl{fill:var(--ink2);font-size:12px}
.fam{fill:var(--ink);font-size:12.5px;font-weight:600}
.tt{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:5;max-width:320px}
.tt .r{display:flex;gap:12px;justify-content:space-between}.tt b{font-variant-numeric:tabular-nums}
.notes{font-size:13.5px;color:var(--ink2)} .notes li{margin:3px 0}
details summary{cursor:pointer;color:var(--ink2);font-size:14px}
</style>
</head>
<body>
<main>
<h1>Canary signals as a leverage gate</h1>
<p class="sub-h">EMAs, CAPE levels, bond yields, the curve's re-steepening window, retail leverage (FINRA margin debt) and OFR stress, each tested as the switch that holds HG's five trend baskets at 1x instead of 3x. HG on the 1990 to 2026 proxy panel, out of sample for its rules; the dip-buys stay levered (addendum 42). Every signal is read with its publication lag.</p>
<p class="lede">None of them beats the plain 200-day gate. Used alone, the best (EMAs, CAPE below 35, OFR stress) tie it at best; bond yields, the curve window and margin growth do no better than staying levered. On top of the 200-day, CAPE and margin excess add a little, and all of it comes from one episode: they stepped down before the 2000 top. One episode out of about ninety tests is what chance alone produces, so no EV+ gate beyond the 200-day is established.</p>

<section class="card">
<h2>Sharpe gain over the 200-day gate, with the 90% band</h2>
<p class="sub-h">Each row: the signal used alone (orange) or added to the 200-day gate (blue). Right of zero means it beat the plain 200-day gate over 36 years; a band that crosses zero means it did not, reliably. Paired 20-day-block bootstrap, 300 draws.</p>
<div class="legend"><span><i class="dot" style="background:var(--s2)"></i>signal alone</span><span><i class="dot" style="background:var(--s1)"></i>signal and the 200-day together</span></div>
<svg id="forest" role="img" aria-label="Sharpe gain over the 200-day gate for each canary signal, alone and combined, with 90 percent bands"></svg>
</section>

<section class="card">
<h2>When each signal would have switched leverage off, against HG's drawdowns</h2>
<p class="sub-h">Grey area: HG as built, drawdown from peak. Strips: the days each signal held the trend baskets at 1x.</p>
<svg id="tl" role="img" aria-label="HG drawdown from 1990 to 2026 with strips marking when the 200-day, CAPE, margin-excess, curve and 10-year-yield signals were off"></svg>
</section>

<section class="card">
<h2>By market regime: the only place the add-ons differ is 2000 to 2002</h2>
<div class="tablewrap"><table>
<thead><tr><th></th>__WINHEAD__</tr></thead>
<tbody>__WINS__</tbody></table></div>
<p class="sub-h" style="margin:8px 0 0">CAGR per year, max drawdown in grey. HG trend baskets gated; dip-buys levered throughout.</p>
</section>

<section class="card">
<h2>What the signals say today</h2>
<p class="sub-h">Readings are the latest published values; the gate column is each signal's state at the panel's last session (__LAST__), after its publication lag.</p>
<div class="tablewrap"><table>
<thead><tr><th>Signal</th><th>Reading</th><th>Gate</th></tr></thead>
<tbody>__READS__</tbody></table></div>
<p class="sub-h" style="margin:8px 0 0">The valuation and yield signals all say de-lever; the trend, margin, stress and curve signals all say stay levered. The one combination with a weak long-history edge (CAPE below 35 with the 200-day) would hold the trend baskets at 1x today, on the strength of a single episode.</p>
</section>

<section class="card">
<details><summary>Table view: every variant (HG, 1990 to 2026)</summary>
<div class="tablewrap"><table>
<thead><tr><th></th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Sharpe gap vs 200-day, 90% band</th></tr></thead>
<tbody>__ALL__</tbody></table></div>
</details>
</section>

<section class="card notes">
<h2 style="color:var(--ink)">Basis and limits</h2>
<ul>
<li>Each signal is used three ways: alone, together with the 200-day (leveraged only when both agree), and as a condition on when the 200-day applies (and its mirror). The conditional use never beat the plain 200-day, the same verdict as addendum 40.</li>
<li>Publication lags: Treasury yields and the New York Fed term premium one session; OFR stress two sessions; FINRA margin month m from the start of month m+2; CAPE two months. Before a series exists the gate stays on.</li>
<li>Margin growth reproduces the canary's own numbers (June 2026: +49.0% a year, +28.2 points over the S&amp;P). It has cooled since: +31.4% and +17.0 points in September.</li>
<li>About 90 variants were run (22 signals, four uses each) and all are shown. The best result, CAPE below 35 with the 200-day, has a 97% chance of beating the 200-day alone on its own bootstrap; across 90 correlated tries that is expected by chance.</li>
<li>Not tested: the canary's seven-indicator leading stack. Its data comes from FRED, which did not respond from this session; it is retried in the background and will be added when it does.</li>
<li>Research only. Nothing here changes a live symphony.</li>
</ul>
</section>
</main>
<div class="tt" id="tt"></div>
<script>
const FOREST = __FOREST__, TL = __TL__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tt = document.getElementById('tt');
function el(tag, a, p){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e;}
function show(x,y,title,rows){tt.textContent='';const t=document.createElement('div');t.style.color=css('--ink2');t.textContent=title;tt.appendChild(t);
  for(const [n,v] of rows){const r=document.createElement('div');r.className='r';const a=document.createElement('span');a.textContent=n;const b=document.createElement('b');b.textContent=v;r.appendChild(a);r.appendChild(b);tt.appendChild(r);}
  tt.style.display='block';const w=tt.offsetWidth,h=tt.offsetHeight;let l=x+14,tp=y-h-10;if(l+w>innerWidth-8)l=x-w-14;if(tp<8)tp=y+14;tt.style.left=l+'px';tt.style.top=tp+'px';}
function hide(){tt.style.display='none';}
function forest(){
  const svg=document.getElementById('forest'); svg.textContent='';
  const W=Math.max(320, svg.parentElement.clientWidth-32), narrow=W<620, lw=narrow?150:290, m={l:lw,r:16,t:22,b:30}, rowH=narrow?15:13;
  const fams=[...new Set(FOREST.map(f=>f.fam))]; let y=m.t; const rows=[];
  for(const f of fams){rows.push({head:f,y}); y+=18; const sigs=[...new Set(FOREST.filter(r=>r.fam===f).map(r=>r.sig))];
    for(const s of sigs){rows.push({sig:s,y}); y+=rowH*2+6;}}
  const H=y+m.b; svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const lo=Math.min(-0.3,...FOREST.map(f=>f.lo)), hi=Math.max(0.2,...FOREST.map(f=>f.hi));
  const X=v=>m.l+(v-lo)*(W-m.l-m.r)/(hi-lo);
  const g=el('g',{class:'axis'},svg);
  for(let v=Math.ceil(lo*10)/10; v<=hi+1e-9; v+=0.1){el('line',{x1:X(v),x2:X(v),y1:m.t-6,y2:H-m.b,stroke:css(Math.abs(v)<1e-9?'--axis':'--grid'),'stroke-width':Math.abs(v)<1e-9?1.5:1},g);
    const t=el('text',{x:X(v),y:H-m.b+16,'text-anchor':'middle'},g);t.textContent=(v>0?'+':'')+v.toFixed(1);}
  const xl=el('text',{x:X(0),y:H-2,'text-anchor':'middle',class:'lbl'},svg);xl.textContent='Sharpe gain over the 200-day gate (left of 0 = worse)';
  for(const r of rows){
    if(r.head){const t=el('text',{x:4,y:r.y+12,class:'fam'},svg);t.textContent=r.head;continue;}
    const t=el('text',{x:narrow?4:12,y:r.y+rowH+3,class:'lbl'},svg);t.textContent=narrow&&r.sig.length>24?r.sig.slice(0,23)+'…':r.sig;
    FOREST.filter(f=>f.sig===r.sig).forEach((f,j)=>{const yy=r.y+6+j*rowH, c=f.use==='alone'?'--s2':'--s1';
      el('line',{x1:X(f.lo),x2:X(f.hi),y1:yy,y2:yy,stroke:css(c),'stroke-width':2,'stroke-linecap':'round'},svg);
      const d=el('circle',{cx:X(f.mid),cy:yy,r:4,fill:css(c),stroke:css('--surface'),'stroke-width':2,tabindex:0},svg);
      const hit=el('rect',{x:X(f.lo)-6,y:yy-7,width:Math.max(14,X(f.hi)-X(f.lo)+12),height:14,fill:'transparent'},svg);
      const sh=(x,yv)=>show(x,yv,`${f.sig} (${f.use})`,[['Sharpe gain vs 200-day',(f.mid>=0?'+':'')+f.mid.toFixed(2)],['90% band',`${f.lo.toFixed(2)} to ${f.hi.toFixed(2)}`],['chance it beats the 200-day',Math.round(f.p*100)+'%'],['CAGR',(f.cagr*100).toFixed(1)+'%'],['Sharpe',f.sharpe.toFixed(2)],['max DD',(f.dd*100).toFixed(1)+'%']]);
      hit.addEventListener('pointermove',e=>sh(e.clientX,e.clientY));hit.addEventListener('pointerleave',hide);
      d.addEventListener('focus',()=>{const b=d.getBoundingClientRect();sh(b.right,b.top);});d.addEventListener('blur',hide);});
  }
}
function timeline(){
  const svg=document.getElementById('tl'); svg.textContent='';
  const W=Math.max(320, svg.parentElement.clientWidth-32), narrow=W<620, m={l:narrow?6:230,r:12,t:8,b:24}, ddH=170, sH=16, labs=Object.keys(TL.strips);
  const H=m.t+ddH+14+labs.length*(sH+(narrow?16:6))+m.b; svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const n=TL.dates.length, xs=i=>m.l+i*(W-m.l-m.r)/(n-1), lo=-0.8, ys=v=>m.t+(0-v)*ddH/(0-lo);
  const pos={}; TL.dates.forEach((d,i)=>pos[d]=i);
  const xd=d=>{let lo_=0,hi_=n-1;while(lo_<hi_){const mid=(lo_+hi_)>>1;if(TL.dates[mid]<d)lo_=mid+1;else hi_=mid;}return xs(lo_);};
  const g=el('g',{class:'axis'},svg);
  for(const v of [0,-0.2,-0.4,-0.6,-0.8]){el('line',{x1:m.l,x2:W-m.r,y1:ys(v),y2:ys(v),stroke:css('--grid'),'stroke-width':1},g);const t=el('text',{x:m.l+2,y:ys(v)-3},g);t.textContent=(v*100).toFixed(0)+'%';}
  let p=`M${xs(0)},${ys(0)}`; TL.dd.forEach((v,i)=>p+=`L${xs(i).toFixed(1)},${ys(v).toFixed(1)}`); p+=`L${xs(n-1)},${ys(0)}Z`;
  el('path',{d:p,fill:css('--wash'),stroke:css('--muted'),'stroke-width':1},svg);
  if(!narrow){const t=el('text',{x:m.l-8,y:m.t+14,'text-anchor':'end',class:'lbl'},svg);t.textContent='HG as built, drawdown';}
  let last='';TL.dates.forEach((d,i)=>{const yr=d.slice(0,4);if(yr!==last){last=yr;if(+yr%(narrow?8:4)===2){const t=el('text',{x:xs(i),y:H-6,'text-anchor':'middle'},g);t.textContent=yr;}}});
  labs.forEach((lab,j)=>{const y0=m.t+ddH+14+j*(sH+(narrow?16:6))+(narrow?14:0);
    const t=el('text',{x:narrow?m.l:m.l-8,y:narrow?y0-3:y0+12,'text-anchor':narrow?'start':'end',class:'lbl'},svg);t.textContent=lab;
    el('rect',{x:m.l,y:y0,width:W-m.l-m.r,height:sH,fill:css('--grid'),opacity:0.5},svg);
    for(const [a,b] of TL.strips[lab]){const x1=xd(a),x2=Math.max(xd(b),x1+1.5);const r=el('rect',{x:x1,y:y0,width:x2-x1,height:sH,fill:css('--s1')},svg);
      r.addEventListener('pointermove',e=>show(e.clientX,e.clientY,lab,[['de-levered from',a],['until',b]]));r.addEventListener('pointerleave',hide);}});
}
function draw(){forest();timeline();}
draw(); let rt; addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,120);});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    main()
