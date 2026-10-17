"""How far the HG 200-day gate was backtested: what each held leg's prices were made of in each year (the
actual fund, or rebuilt from its 1x ETF or index), the 1990-2026 curves with those eras marked, and the
gate's effect inside each era.  Reads the ratified gate-lab output (LEVGATE_DATA/levgate.json, base_B.json)
and the price files' first dates; writes results/hg-gate-backtest-coverage-2026-10-17.html and prints the
era table."""
import json
import math
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levgate as lg   # noqa: E402

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results', 'hg-gate-backtest-coverage-2026-10-17.html')
K = {'as built': 'A0 always levered (as built)', '200d -> 1x': 'T200 SPY>200d [trend only]',
     '200d -> half': 'T200 SPY>200d -> half 1x half cash [trend only]', '200d -> cash': 'T200 SPY>200d -> cash [trend only]'}
HG_LIVE = '2025-12-05'   # first HG version (0DeB193g) created 2025-12-05 11:46 ET; see lev_study.SCHEDULE
# price layers per held ticker, oldest first, as gate_study.build_lh_prices splices them:
# (kind, label, ticker whose first date opens the layer; None = the panel start)
LAYERS = {
    'TQQQ': [('index', 'Nasdaq-100 x3', None), ('etf1x', 'QQQ x3', 'QQQ'), ('actual', 'TQQQ', 'TQQQ')],
    'TNA': [('index', 'Russell 2000 x3', None), ('etf1x', 'IWM x3', 'IWM'), ('actual', 'TNA', 'TNA')],
    'UDOW': [('standin', 'S&P 500 x3', None), ('index', 'Dow x3', '^DJI'), ('etf1x', 'DIA x3', 'DIA'), ('actual', 'UDOW', 'UDOW')],
    'SSO': [('index', 'S&P 500 x2', None), ('etf1x', 'SPY x2', 'SPY'), ('actual', 'SSO', 'SSO')],
    'UPRO': [('index', 'S&P 500 x3', None), ('etf1x', 'SPY x3', 'SPY'), ('actual', 'UPRO', 'UPRO')],
    'TECL': [('standin', 'Nasdaq-100 x3', None), ('etf1x', 'XLK x3', 'XLK'), ('actual', 'TECL', 'TECL')],
    'LABU': [('standin', 'Nasdaq-100 x3', None), ('index', 'Nasdaq Biotech x3', '^NBI'), ('etf1x', 'XBI x3', 'XBI'), ('actual', 'LABU', 'LABU')],
    'QLD': [('index', 'Nasdaq-100 x2', None), ('etf1x', 'QQQ x2', 'QQQ'), ('actual', 'QLD', 'QLD')],
    'USD': [('standin', 'Nasdaq-100 x2', None), ('index', 'PHLX Semis x2', '^SOX'), ('actual', 'USD', 'USD')],
    'SMH': [('standin', 'Nasdaq-100', None), ('index', 'PHLX Semis', '^SOX'), ('actual', 'SMH', 'SMH')],
    'UVXY': [('model', 'modelled from VIX', None), ('actual', 'UVXY', 'UVXY')],
    'VIXM': [('model', 'modelled from VIX', None), ('actual', 'VIXM', 'VIXM')],
    'VIXY': [('model', 'modelled from VIX', None), ('actual', 'VIXY', 'VIXY')],
    'BIL': [('index', '3-month T-bill', None), ('actual', 'BIL', 'BIL')],
    'SPY': [('index', 'S&P 500 + dividends', None), ('actual', 'SPY', 'SPY')],
}
GROUPS = [('Switched by the gate (trend baskets)', ['TQQQ', 'TNA', 'UDOW', 'SSO', 'UPRO']),
          ('Dip-buys (stay leveraged)', ['TECL', 'LABU', 'QLD', 'USD']),
          ('Other holdings', ['SMH', 'UVXY', 'VIXM', 'VIXY', 'BIL']),
          ('Gate signal', ['SPY'])]


def main():
    J = json.load(open(os.path.join(lg.OUT, 'levgate.json')))
    B = J['panels']['B']['HG']
    S = {lab: B['series_keep'][k] for lab, k in K.items()}
    days = json.load(open(os.path.join(lg.OUT, 'base_B.json')))['HG']['days']
    hold = json.load(open(os.path.join(lg.OUT, 'base_B.json')))['HG']['hold']
    first = {t: min(lg.gs.yh(t)) for t in {x for L in LAYERS.values() for _, _, x in L if x}}
    p0, p1 = days[0], days[-1]

    held = Counter()
    for d in days[1:]:
        for t, x in hold[d].items():
            held[t] += x
    rows = []
    for g, tks in GROUPS:
        for t in tks:
            segs = []
            for i, (kind, lab, src) in enumerate(LAYERS[t]):
                a = p0 if src is None else max(p0, first[src])
                nxt = LAYERS[t][i + 1][2] if i + 1 < len(LAYERS[t]) else None
                b = p1 if nxt is None else first[nxt]
                if a < b:
                    segs.append({'kind': kind, 'label': lab, 'a': a, 'b': b})
            rows.append({'t': t, 'group': g, 'held': held[t] / (len(days) - 1), 'segs': segs})

    # eras by what the five gated legs were made of
    trend = GROUPS[0][1]
    e2, e3, e4 = first['QQQ'], max(first[t] for t in trend), J['panels']['A']['HG']['first']
    prev = {days[i]: days[i - 1] for i in range(1, len(days))}
    nxt_day = lambda d: next(x for x in days if x >= d)   # noqa: E731
    bounds = [p0, nxt_day(e2), nxt_day(e3), nxt_day(e4)]
    ERAS = [('1990 to 1999', 'Rebuilt from index levels (SPY- and DIA-based once those exist)'),
            ('1999 to 2010', 'Rebuilt from QQQ, SPY, DIA and IWM (from 2000); SSO, TNA, UPRO actual from 2006, 2008, 2009'),
            ('2010 to 2015', "Actual 3x/2x funds; before the data HG's rules were built on"),
            ('2015 to 2026', "Actual funds; the stretch HG's rules were built on (in sample)")]
    spy = lg.gs.build_lh_prices()['SPY']
    ma = lg.ma_series(spy, 200)
    eras = []
    for i, (lab, basis) in enumerate(ERAS):
        a = bounds[i]
        b = prev[bounds[i + 1]] if i + 1 < len(bounds) else p1
        ds = [d for d in days if a <= d <= b]
        off = sum(1 for d in ds if spy[d] <= ma[d]) / len(ds)
        m = {k: lg.gs.metrics(S[k], ['x'] + sorted(S[k]), a, b) for k in K}
        lw = {k: sum(math.log1p(S[k][d]) for d in ds if d in S[k]) for k in K}
        eras.append({'label': lab, 'basis': basis, 'a': a, 'b': b, 'years': len(ds) / 252, 'off': off, 'm': m,
                     'vs': {k: math.exp(lw[k] - lw['as built']) for k in K}})
    full = {k: B['rows'][K[k]]['full'] for k in K}

    # curves: daily wealth and drawdown, thinned to 5-session buckets (last wealth, deepest drawdown)
    cd = sorted(S['as built'])
    curves, dds = {}, {}
    for k in K:
        v, pk, w, dd = 1.0, 1.0, [], []
        for d in cd:
            v *= 1 + S[k][d]
            pk = max(pk, v)
            w.append(v)
            dd.append(v / pk - 1)
        curves[k] = [round(w[min(i + 4, len(w) - 1)], 4) for i in range(0, len(w), 5)]
        dds[k] = [round(min(dd[i:i + 5]), 4) for i in range(0, len(dd), 5)]
    cdates = [cd[min(i + 4, len(cd) - 1)] for i in range(0, len(cd), 5)]

    print(f'panel B {p0}..{p1}: {len(days)} sessions, {len(days) / 252:.1f} yrs; trend legs all actual from {e3}; every leg actual from {e4}')
    for e in eras:
        print(f"{e['label']:13s} {e['a']}..{e['b']} {e['years']:5.1f}y below200 {e['off']:4.0%}  " +
              '  '.join(f"{k} {e['m'][k]['cagr']:+.1%}/{e['m'][k]['sharpe']:.2f}/{e['m'][k]['maxdd']:.0%} x{e['vs'][k]:.2f}" for k in K))
    D = {'rows': rows, 'eras': eras, 'full': full, 'p0': p0, 'p1': p1, 'n': len(days), 'live': HG_LIVE, 'e3': e3, 'e4': e4,
         'dates': cdates, 'curves': curves, 'dds': dds}
    open(PAGE, 'w').write(TEMPLATE.replace('__DATA__', json.dumps(D)))
    print('wrote', os.path.normpath(PAGE))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gate backtest coverage</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--b1:#898781;--b2:#52514e;--band:rgba(11,11,11,.035)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--b1:#898781;--b2:#c3c2b7;--band:rgba(255,255,255,.04)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--b1:#898781;--b2:#c3c2b7;--band:rgba(255,255,255,.04)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}
h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 12px;font-size:14px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:0 0 16px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0 16px}
@media (max-width:820px){.kpis{grid-template-columns:1fr 1fr}}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:22px;font-weight:650;font-variant-numeric:tabular-nums}
.kpi span{color:var(--ink2);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:5px 7px;text-align:right;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums;white-space:nowrap}
th[scope=row]{text-align:left;font-weight:500;white-space:normal;min-width:190px}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}
td.pos{color:var(--s3)} td.neg{color:var(--s2)}
.dim{color:var(--muted);font-size:12px;font-weight:400}
.tablewrap{overflow-x:auto}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 4px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.key{display:inline-block;width:16px;height:2px;border-radius:1px}
.sw{display:inline-block;width:14px;height:10px;border-radius:2px}
svg{display:block;width:100%;height:auto;overflow:visible}
.tt{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:5;min-width:170px;max-width:320px}
.tt .d{color:var(--ink2);margin-bottom:4px}
.tt .r{display:flex;align-items:center;gap:8px;justify-content:space-between}
.tt .r b{font-variant-numeric:tabular-nums}
.tt .n{display:inline-flex;align-items:center;gap:6px;color:var(--ink2)}
.axis text{fill:var(--muted);font-size:11px}
.lbl{fill:var(--ink2);font-size:12px}
.grp{fill:var(--ink);font-size:12px;font-weight:600}
.notes{font-size:13.5px;color:var(--ink2)}
.notes li{margin:3px 0}
</style>
</head>
<body>
<main class="viz-root">
<h1>How far the HG 200-day gate was backtested</h1>
<p class="sub-h">HG with the 200-day gate on its five trend baskets, run on one daily price panel from 1990 to 2026. The leveraged funds launched between 2006 and 2015, so the earlier years use prices rebuilt from each fund's 1x ETF or index. This page shows which years are actual fund prices and what the gate did in each stretch.</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>What each leg's prices were made of</h2>
<p class="sub-h">One row per fund HG holds, with the share of sessions it held that fund. A rebuilt leg is 2x or 3x the daily return of its 1x ETF or index, minus financing at the T-bill rate and a fee drag (fitted where the fund and its base overlap; a fixed 1.8% a year on the index and IWM rebuilds).</p>
<div class="legend" id="lg-g"></div>
<svg id="gantt" role="img" aria-label="Timeline from 1990 to 2026 of where each held fund's prices come from: actual fund, rebuilt from its 1x ETF, rebuilt from an index, a stand-in index, or a VIX model"></svg>
</section>

<section class="card">
<h2>Growth of $1 (log scale) and drawdown, 1990 to 2026, by data era</h2>
<div class="legend" id="lg-eq"></div>
<svg id="eq" role="img" aria-label="Growth of one dollar on a log scale for HG as built and with the 200-day gate, with the four data eras shaded"></svg>
<svg id="dd" role="img" aria-label="Drawdown from peak for the same series"></svg>
</section>

<section class="card">
<h2>The gate inside each data era</h2>
<p class="sub-h">CAGR / Sharpe / max drawdown inside each stretch; "x" is the gated version's ending wealth over the stretch divided by as built's (above 1 means the gate added money).</p>
<div class="tablewrap"><table>
<thead><tr><th>Era</th><th>Years</th><th>SPY below 200d</th><th>As built</th><th>200d, 1x below</th><th>200d, cash below</th><th>Gate vs as built (1x / cash)</th></tr></thead>
<tbody id="eras"></tbody></table></div>
</section>

<section class="card notes">
<h2 style="color:var(--ink)">Basis and limits</h2>
<ul>
<li>Engine and numbers: the add. 42 gate lab (levgate.py; counter-agent reviewed). Trades at the close on the prior close's signal; Composer trades at about 15:50. Costed at HG's measured 5.1 bp per unit of turnover, including the gate's switches.</li>
<li>Rebuilt legs track the actual funds within 1.2% a year where both exist (add. 40 counter-agent check). Index rebuilds add a dividend yield (the S&amp;P's monthly yield; 0.5% a year for the Nasdaq-100, 1.5% for the Russell 2000; none for the biotech and semiconductor indices). Where a sector index did not exist yet, the Nasdaq-100 or S&amp;P 500 stands in. VIX funds before 2011 are a regression on the VIX index, cruder before mid-2006. T-bills stand in for BIL before 2007.</li>
<li>HG's rules were built on 2015 to 2026 data, so that stretch is in sample; 1990 to 2015 is out of sample for the rules. The 200-day shape was fixed from the literature in add. 40, not fitted here.</li>
<li>Research only. Nothing live changes.</li>
</ul>
</section>
</main>
<div class="tt" id="tt" role="status" aria-live="polite"></div>
<script>
const D = __DATA__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tt = document.getElementById('tt');
const pct = (x, s=true) => (s && x >= 0 ? '+' : '') + (x*100).toFixed(1) + '%';
const yr = d => +d.slice(0,4) + ((+d.slice(5,7)-1)*30.44 + (+d.slice(8,10)-1))/365.25;
const KIND = {actual:['actual fund','s1'], etf1x:['rebuilt from its 1x ETF','s3'], index:['rebuilt from an index','s4'], standin:['stand-in index (sector index not published yet)','s2'], model:['modelled from the VIX index','b1']};
const SER = [['as built','b2','as built'],['200d -> 1x','s4','200d, 1x below'],['200d -> cash','s3','200d, cash below']];
function el(tag, attrs, parent){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e;}
function txt(parent, x, y, s, cls, anchor){const t=el('text',{x,y,class:cls||'lbl','text-anchor':anchor||'start'},parent);t.textContent=s;return t;}
function showTT(x, y, title, rows){tt.textContent='';const d=document.createElement('div');d.className='d';d.textContent=title;tt.appendChild(d);
  for(const r of rows){const row=document.createElement('div');row.className='r';const n=document.createElement('span');n.className='n';if(r.cls){const k=document.createElement('i');k.className='key';k.style.background=`var(--${r.cls})`;n.appendChild(k);}n.appendChild(document.createTextNode(r.name));const b=document.createElement('b');b.textContent=r.val;row.appendChild(n);row.appendChild(b);tt.appendChild(row);}
  tt.style.display='block';const w=tt.offsetWidth,h=tt.offsetHeight;let left=x+14,top=y-h-10;if(left+w>innerWidth-8)left=x-w-14;if(top<8)top=y+14;tt.style.left=left+'px';tt.style.top=top+'px';}
function hideTT(){tt.style.display='none';}
function legend(id, items, sw){const lg=document.getElementById(id);lg.textContent='';for(const [name,cls] of items){const s=document.createElement('span');const k=document.createElement('i');k.className=sw?'sw':'key';k.style.background=`var(--${cls})`;s.appendChild(k);s.appendChild(document.createTextNode(name));lg.appendChild(s);}}
const X0 = yr(D.p0), X1 = yr(D.p1);
function xaxis(svg, g, X, H, m, W){for(let y=1990;y<=2026;y+=(W<600?6:2)){const x=X(y);if(x<m.l-1||x>W-m.r+1)continue;el('line',{x1:x,x2:x,y1:m.t,y2:H-m.b,stroke:css('--grid'),'stroke-width':1},g);txt(g,x,H-8,String(y),null,'middle');}}

function kpis(){
  const k=document.getElementById('kpis'); k.textContent='';
  const ys=(a,b)=>((yr(b)-yr(a))).toFixed(1);
  const items=[[ys(D.p0,D.p1)+' years',`${D.p0} to ${D.p1}, ${D.n.toLocaleString()} sessions`],
               [ys(D.e3,D.p1)+' years',`on the actual 3x/2x funds for all five gated legs (from ${D.e3})`],
               [ys(D.e4,D.p1)+' years',`with every leg actual (from ${D.e4}); the stretch HG's rules were built on`],
               [ys(D.live,D.p1)+' years','HG live since '+D.live+'; the gate itself has not run live']];
  for(const [b,s] of items){const d=document.createElement('div');d.className='kpi';const bb=document.createElement('b');bb.textContent=b;const ss=document.createElement('span');ss.textContent=s;d.appendChild(bb);d.appendChild(ss);k.appendChild(d);}
}

function gantt(){
  const svg=document.getElementById('gantt'); svg.textContent='';
  const W=Math.max(320, svg.parentElement.clientWidth-32), narrow=W<600, rowH=20, gapH=22, m={l:narrow?56:70,r:narrow?38:46,t:30,b:26};
  const groups=[...new Set(D.rows.map(r=>r.group))];
  const H=m.t+D.rows.length*rowH+groups.length*gapH+m.b;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const X=v=>m.l+(v-X0)*(W-m.l-m.r)/(X1-X0);
  const g=el('g',{class:'axis'},svg); xaxis(svg,g,X,H,m,W);
  let y=m.t, cur='';
  for(const r of D.rows){
    if(r.group!==cur){cur=r.group;y+=gapH;txt(svg,m.l,y-6,r.group,'grp');}
    txt(svg,m.l-8,y+rowH/2+4,r.t,'lbl','end');
    txt(svg,W-m.r+6,y+rowH/2+4,(r.held*100).toFixed(r.held<0.01?1:0)+'%','lbl');
    for(const s of r.segs){
      const x1=X(yr(s.a)), x2=X(yr(s.b));
      const rc=el('rect',{x:x1,y:y+3,width:Math.max(1,x2-x1-1),height:rowH-6,rx:2,fill:`var(--${KIND[s.kind][1]})`,tabindex:0},svg);
      const show=(cx,cy)=>showTT(cx,cy,`${r.t}: ${s.label}`,[{name:KIND[s.kind][0],val:''},{name:'from',val:s.a},{name:'to',val:s.b}]);
      rc.addEventListener('pointermove',e=>show(e.clientX,e.clientY));rc.addEventListener('pointerleave',hideTT);
      rc.addEventListener('focus',()=>{const b=rc.getBoundingClientRect();show(b.left+b.width/2,b.top);});rc.addEventListener('blur',hideTT);
    }
    y+=rowH;
  }
  for(const [d,lab,anchor] of [[D.e4,narrow?'all actual':'every leg actual','end'],[D.live,'HG live','start']]){
    const x=X(yr(d)); el('line',{x1:x,x2:x,y1:m.t-4,y2:H-m.b,stroke:css('--ink2'),'stroke-width':1.5,'stroke-dasharray':'4 3'},svg);
    txt(svg,anchor==='end'?x-4:x+4,m.t-8,lab,'lbl',anchor);
  }
  txt(svg,W-m.r+6,m.t-8,'held','lbl');
}

function eraBands(svg, X, H, m, labels, narrow){
  D.eras.forEach((e,i)=>{const x1=X(yr(e.a)), x2=X(yr(e.b));if(i%2===0)el('rect',{x:x1,y:m.t,width:x2-x1,height:H-m.t-m.b,fill:css('--band')},svg);
    if(labels&&!narrow)txt(svg,(x1+x2)/2,m.t+12,e.label,'lbl','middle');});
}

function lines(id, dd){
  const svg=document.getElementById(id); svg.textContent='';
  const W=Math.max(320, svg.parentElement.clientWidth-32), narrow=W<600, H=dd?220:330, m={l:52,r:dd?16:(narrow?70:150),t:dd?8:20,b:26};
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const n=D.dates.length, xs=D.dates.map(yr), X=v=>m.l+(v-X0)*(W-m.l-m.r)/(X1-X0);
  const src=dd?D.dds:D.curves; let lo=Infinity,hi=-Infinity;
  for(const [k] of SER)for(const v of src[k]){lo=Math.min(lo,v);hi=Math.max(hi,v);}
  if(dd)hi=0;
  const tr=dd?(v=>v):Math.log10, Y=v=>m.t+(tr(hi)-tr(v))*(H-m.t-m.b)/(tr(hi)-tr(lo));
  eraBands(svg,X,H,m,!dd,narrow);
  const g=el('g',{class:'axis'},svg); xaxis(svg,g,X,H,m,W);
  const ticks=dd?[0,-0.2,-0.4,-0.6,-0.8]:[0.1,1,10,100,1000,1e4,1e5,1e6,1e7].filter(t=>t>=lo/1.01&&t<=hi*1.01);
  const money=v=>v>=1e6?'$'+(v/1e6).toFixed(v>=1e7?0:1)+'M':(v>=1000?'$'+(v/1000).toFixed(0)+'k':'$'+v.toFixed(v<10?2:0));
  const fmt=dd?(v=>(v*100).toFixed(0)+'%'):money;
  for(const t of ticks){if(t<lo||t>hi)continue;el('line',{x1:m.l,x2:W-m.r,y1:Y(t),y2:Y(t),stroke:css(t===(dd?0:1)?'--axis':'--grid'),'stroke-width':1},g);txt(g,m.l-6,Y(t)+4,fmt(t),null,'end');}
  for(const [k,cls] of SER.slice().reverse()){let p='';src[k].forEach((v,i)=>p+=(i?'L':'M')+X(xs[i]).toFixed(1)+','+Y(v).toFixed(1));el('path',{d:p,fill:'none',stroke:`var(--${cls})`,'stroke-width':k==='as built'?1.6:2,'stroke-linejoin':'round'},svg);}
  if(!dd){const labs=SER.map(([k,cls,name])=>({k,cls,name,y:Y(src[k][n-1])})).sort((a,b)=>a.y-b.y);
    for(let i=1;i<labs.length;i++)if(labs[i].y-labs[i-1].y<14)labs[i].y=labs[i-1].y+14;
    for(const L of labs){el('circle',{cx:X(xs[n-1]),cy:Y(src[L.k][n-1]),r:4,fill:`var(--${L.cls})`,stroke:css('--surface'),'stroke-width':2},svg);txt(svg,X(xs[n-1])+8,L.y+4,narrow?money(src[L.k][n-1]):`${L.name} ${money(src[L.k][n-1])}`);}}
  const cross=el('line',{y1:m.t,y2:H-m.b,stroke:css('--axis'),'stroke-width':1,visibility:'hidden'},svg);
  const hit=el('rect',{x:m.l,y:m.t,width:W-m.l-m.r,height:H-m.t-m.b,fill:'transparent',tabindex:0},svg);
  const ttf=dd?(v=>(v*100).toFixed(1)+'%'):money;
  const move=(cx,cy,i)=>{cross.setAttribute('x1',X(xs[i]));cross.setAttribute('x2',X(xs[i]));cross.setAttribute('visibility','visible');showTT(cx,cy,D.dates[i],SER.map(([k,cls,name])=>({name,cls,val:ttf(src[k][i])})));};
  const idx=x=>{let lo_=0,hi_=n-1;const v=X0+(x-m.l)*(X1-X0)/(W-m.l-m.r);while(lo_<hi_){const mid=(lo_+hi_)>>1;if(xs[mid]<v)lo_=mid+1;else hi_=mid;}return lo_;};
  hit.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect();move(e.clientX,e.clientY,idx((e.clientX-r.left)*W/r.width));});
  hit.addEventListener('pointerleave',()=>{cross.setAttribute('visibility','hidden');hideTT();});
  let ki=n-1;const key=()=>{const r=svg.getBoundingClientRect();move(r.left+r.width*0.6,r.top+20,ki);};
  hit.addEventListener('focus',key);hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')ki=Math.max(0,ki-1);else if(e.key==='ArrowRight')ki=Math.min(n-1,ki+1);else return;e.preventDefault();key();});
  hit.addEventListener('blur',()=>{cross.setAttribute('visibility','hidden');hideTT();});
}

function table(){
  const tb=document.getElementById('eras'); tb.textContent='';
  const cell=(tr,s,cls)=>{const td=document.createElement('td');td.textContent=s;if(cls)td.className=cls;tr.appendChild(td);};
  const trip=m=>`${pct(m.cagr)} / ${m.sharpe.toFixed(2)} / ${pct(m.maxdd,false)}`;
  const rows=D.eras.map(e=>({lab:e.label,basis:e.basis,years:e.years.toFixed(1),off:pct(e.off,false),m:e.m,vs:e.vs}));
  rows.push({lab:'Whole panel',basis:`${D.p0} to ${D.p1}`,years:(D.n/252).toFixed(1),off:'',m:D.full,vs:null});
  for(const r of rows){
    const tr=document.createElement('tr');const th=document.createElement('th');th.scope='row';th.textContent=r.lab+' ';
    const sp=document.createElement('span');sp.className='dim';sp.textContent=r.basis;th.appendChild(document.createElement('br'));th.appendChild(sp);tr.appendChild(th);
    cell(tr,r.years);cell(tr,r.off);cell(tr,trip(r.m['as built']));cell(tr,trip(r.m['200d -> 1x']));cell(tr,trip(r.m['200d -> cash']));
    if(r.vs){const a=r.vs['200d -> 1x'],b=r.vs['200d -> cash'];cell(tr,`x${a.toFixed(2)} / x${b.toFixed(2)}`,(a>=1&&b>=1)?'pos':((a<1&&b<1)?'neg':''));}else cell(tr,'');
    tb.appendChild(tr);
  }
}

function draw(){
  kpis();
  legend('lg-g',Object.values(KIND).map(([n,c])=>[n,c]),true); gantt();
  legend('lg-eq',SER.map(([k,c,n])=>[n,c])); lines('eq',false); lines('dd',true); table();
}
draw(); let rt; addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,120);});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    main()
