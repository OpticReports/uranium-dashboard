"""Exhibit for book1997.py: $100k in the current four-engine book from 1997.  Reads the scratch outputs
(book1997_<mode>.json, engines_ts_synth.json, fidelity1997.json) and the long panel's splice fidelity;
writes results/book-since-1997-2026-10-20.html and prints the numbers it shows."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import book1997 as bk   # noqa: E402

lp, lg = bk.lp, bk.lg
OUT = bk.OUT
PAGE = os.path.join(HERE, '..', '..', 'results', 'book-since-1997-2026-10-20.html')
CAPACITY = 10_000_000      # results.md add. 15: practical ceiling of the current strategy set ~$5-10M


def era_split(R):
    by = R['book']['by_year']
    m1 = math.prod(1 + by[y] for y in by if y <= '2014')
    m2 = math.prod(1 + by[y] for y in by if y >= '2015')
    return {'end2014': bk.START_VALUE * m1, 'cagr_9714': m1 ** (1 / 18) - 1, 'mult_1526': m2, 'cagr_1526': m2 ** (1 / (R['book']['years'] - 18)) - 1,
            'final': bk.START_VALUE * R['book']['final_multiple']}


def crossings(E):
    eng = {e: E[e]['rets'] for e in bk.ENGINES}
    days = sorted(set().union(*[set(E[e]['days']) for e in bk.ENGINES]))
    days = [d for d in days if d >= bk.BOOK0]
    book = lg.book(eng, days)
    w, out, marks = bk.START_VALUE, {}, [1e6, 1e7, 1e8, 1e9, 1e10]
    for d in days:
        w *= 1 + book[d]
        for m in marks:
            if m not in out and w >= m:
                out[m] = d
    return {f'{int(m):,}': out.get(m) for m in marks}


def harvester_alternatives(E):
    """the book with the harvester's 15% in T-bills, and with its share spread over the other three engines"""
    import sens1997 as sv
    eng = {e: E[e]['rets'] for e in bk.ENGINES}
    days = [d for d in sorted(set().union(*[set(E[e]['days']) for e in bk.ENGINES])) if d >= bk.BOOK0]
    out = {}
    for lab, mod in (('as is', None), ('harvester share in T-bills', 'bills'), ('harvester share spread over the other three', 'spread')):
        e2 = dict(eng)
        tgt = dict(sv.TARGET)
        if mod == 'bills':
            e2['HARV'] = {d: lp.cash.get(d, 0.0) for d in days}
        elif mod == 'spread':
            k = 1 / (1 - tgt['HARV'])
            tgt = {e: (0.0 if e == 'HARV' else w * k) for e, w in tgt.items()}
        sv.TARGET = tgt
        b = sv.book(e2, days, 0.40, 1)
        sv.TARGET = dict(lg.TARGET)
        s = bk.stats(b, days)
        out[lab] = {'final': bk.START_VALUE * s['final_multiple'], 'sharpe': s['sharpe'], 'maxdd': s['maxdd'], 'cagr': s['cagr']}
    return out


def cap_resets(E):
    eng = {e: E[e]['rets'] for e in bk.ENGINES}
    days = [d for d in sorted(set().union(*[set(E[e]['days']) for e in bk.ENGINES])) if d >= bk.BOOK0]
    w, pending, n, by = dict(lg.TARGET), False, 0, {}
    for d in days:
        r = sum(w[e] * eng[e].get(d, 0.0) for e in w)
        w = {e: w[e] * (1 + eng[e].get(d, 0.0)) / (1 + r) for e in w}
        if pending:
            w, pending = dict(lg.TARGET), False
        if max(w.values()) > 0.40:
            pending = True
            n += 1
            top = max(w, key=w.get)
            by[top] = by.get(top, 0) + 1
    return {'n': n, 'by_engine': by}


def main():
    R = {m: json.load(open(os.path.join(OUT, f'book1997_{m}.json'))) for m in ('ts_synth', 'plain', 'level')}
    F = json.load(open(os.path.join(OUT, 'fidelity1997.json')))
    E = json.load(open(os.path.join(OUT, 'engines_ts_synth.json')))
    S = json.load(open(os.path.join(OUT, 'sens1997.json')))
    P, meta = lp.build_long_prices('ts_synth')
    splices = lp.fidelity(P, meta)
    main_r = R['ts_synth']
    eras = {m: era_split(R[m]) for m in R}
    cross = crossings(E)
    harv = harvester_alternatives(E)
    resets = cap_resets(E)
    MAINRULE = 'cap 40%, reset next close (main)'
    rows = [('Main case', eras['ts_synth'], R['ts_synth']['book']['maxdd']),
            ('VIX funds before 2006: constant carry', eras['plain'], R['plain']['book']['maxdd']),
            ('VIX funds before 2006: carry linear in the VIX level', eras['level'], R['level']['book']['maxdd'])]
    LAB = {'pregate': 'HG without its 200-day gate', 'const50': "Switcher's managed-futures RSI pinned at 50 before 2007",
           'mfall': 'Trend proxy instead of RYMFX, 2007-2020', 'uvxy15pre': "UVXY at today's 1.5x before its 2011 launch",
           'uvxy15': "UVXY at today's 1.5x through 2018"}
    for v, lab in LAB.items():
        m = S[v]['rules'][MAINRULE]
        rows.append((lab, {'end2014': m['end2014'], 'cagr_9714': m['cagr_9714'], 'final': m['final']}, m['maxdd']))
    sens_rows = [{'label': lab, 'end2014': e['end2014'], 'cagr_9714': e['cagr_9714'], 'final': e['final'], 'maxdd': dd} for lab, e, dd in rows]
    rule_rows = [{'label': lab, **S['baseline']['rules'][lab]} for lab in S['baseline']['rules']]
    finals = [r['final'] for r in sens_rows] + [r['final'] for r in rule_rows if not r['label'].startswith('no cap') and not r['label'].startswith('daily')]
    c9714 = [r['cagr_9714'] for r in sens_rows]
    rng = {'final_lo': min(finals), 'final_hi': max(finals), 'cagr_lo': min(c9714), 'cagr_hi': max(c9714),
           'end2014_lo': min(r['end2014'] for r in sens_rows), 'end2014_hi': max(r['end2014'] for r in sens_rows)}
    print('eras', json.dumps(eras, indent=0)[:600])
    print('crossings', cross, '\nharvester', harv, '\nresets', resets, '\nrange', rng)
    D = {'main': {k: main_r[k] for k in ('first', 'last', 'n', 'book', 'engines', 'bench', 'paths')},
         'eras': eras, 'cross': cross, 'fid': F, 'splices': splices, 'capacity': CAPACITY, 'harv': harv, 'resets': resets,
         'sens_rows': sens_rows, 'rule_rows': rule_rows, 'range': rng, 'pregate': S['pregate']['rules'][MAINRULE]}
    open(PAGE, 'w').write(TEMPLATE.replace('__DATA__', json.dumps(D)))
    print('wrote', os.path.normpath(PAGE))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Book since 1997</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--b1:#898781;--b2:#52514e;--band:rgba(235,104,52,.08)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--b1:#898781;--b2:#c3c2b7;--band:rgba(217,89,38,.12)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--b1:#898781;--b2:#c3c2b7;--band:rgba(217,89,38,.12)}
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
.kpi b{display:block;font-size:22px;font-weight:650;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.kpi span{color:var(--ink2);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:5px 7px;text-align:right;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums;white-space:nowrap}
th[scope=row]{text-align:left;font-weight:500;white-space:normal}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}
thead th:first-child{text-align:left}
td.pos{color:var(--s3)} td.neg{color:var(--s2)}
tr.insample th,tr.insample td{background:var(--band)}
.tablewrap{overflow-x:auto}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 4px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.key{display:inline-block;width:16px;height:2px;border-radius:1px}
.sw{display:inline-block;width:14px;height:10px;border-radius:2px;background:var(--band);border:1px solid var(--ring)}
svg{display:block;width:100%;height:auto;overflow:visible}
.axis text{fill:var(--muted);font-size:11px}
.lbl{fill:var(--ink2);font-size:12px}
.tt{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:5;min-width:170px}
.tt .d{color:var(--ink2);margin-bottom:4px}
.tt .r{display:flex;align-items:center;gap:8px;justify-content:space-between}
.tt .r b{font-variant-numeric:tabular-nums}
.tt .n{display:inline-flex;align-items:center;gap:6px;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}
.notes li{margin:3px 0}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid2>div,.kpi{min-width:0}
@media (max-width:820px){.grid2{grid-template-columns:1fr}}
</style>
</head>
<body>
<main class="viz-root">
<h1>$100,000 in today's Composer book, from 1997</h1>
<p class="sub-h" id="sub"></p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>Growth of $100,000 (log scale)</h2>
<p class="sub-h">The shaded years (2015 on) are the years the four engines' rules were built on: in sample. The dashed line is the practical ceiling of the current strategy set (about $5-10M, addendum 15); above it the paper path is not investable.</p>
<div class="legend" id="lg-eq"></div>
<svg id="eq" role="img" aria-label="Growth of one hundred thousand dollars on a log scale for the four-engine book, SPY and QQQ since 1997"></svg>
<svg id="dd" role="img" aria-label="Drawdown from peak for the book and SPY"></svg>
</section>

<section class="card">
<h2>Year by year</h2>
<p class="sub-h">Calendar-year returns; each engine standalone; the book is 29/29/27/15 with drift and the 40% cap. Shaded rows: in sample.</p>
<div class="tablewrap"><table>
<thead><tr><th>Year</th><th>Book</th><th>HG</th><th>KMLM switcher</th><th>Sleeve</th><th>Harvester</th><th>SPY</th></tr></thead>
<tbody id="years"></tbody></table></div>
</section>

<section class="card">
<h2>Each engine alone, and the benchmarks</h2>
<div class="tablewrap"><table>
<thead><tr><th>Series</th><th>$100k becomes</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Worst year</th><th>Longest underwater</th></tr></thead>
<tbody id="engines"></tbody></table></div>
</section>

<section class="card">
<h2>How much of this is the proxies and the rules</h2>
<p class="sub-h">One change at a time against the main case. The first group changes a proxy or a rule; the second changes only how the book's 40% cap is applied.</p>
<div class="tablewrap"><table>
<thead><tr><th>Change</th><th>End 2014</th><th>1997-2014 a year</th><th>Final (paper)</th><th>Max DD</th></tr></thead>
<tbody id="sens"></tbody></table></div>
<div class="tablewrap" style="margin-top:10px"><table>
<thead><tr><th>Book rule (main case)</th><th>End 2014</th><th>1997-2014 a year</th><th>Final (paper)</th><th>Max DD</th></tr></thead>
<tbody id="rules"></tbody></table></div>
</section>

<section class="card">
<h2>Checks against Composer and the earlier study</h2>
<p class="sub-h">Composer's own backtest of each live symphony against this simulator, real-fund years only.</p>
<div class="tablewrap"><table>
<thead><tr><th>Engine</th><th>Window</th><th>Correlation</th><th>CAGR Composer / here</th></tr></thead>
<tbody id="fid"></tbody></table></div>
<ul class="notes" id="fidnotes"></ul>
</section>

<section class="card notes">
<h2 style="color:var(--ink)">What this is, and what it is not</h2>
<ul id="honest"></ul>
</section>
</main>
<div class="tt" id="tt" role="status" aria-live="polite"></div>
<script>
const D = __DATA__;
const M = D.main;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tt = document.getElementById('tt');
const pct = (x, s=true, dp=1) => (s && x >= 0 ? '+' : '') + (x*100).toFixed(dp) + '%';
const yr = d => +d.slice(0,4) + ((+d.slice(5,7)-1)*30.44 + (+d.slice(8,10)-1))/365.25;
const money = v => v >= 1e12 ? '$' + (v/1e12).toFixed(1) + 'T' : v >= 1e9 ? '$' + (v/1e9).toFixed(v >= 1e11 ? 0 : 1) + 'B' : v >= 1e6 ? '$' + (v/1e6).toFixed(v >= 1e8 ? 0 : 1) + 'M' : v >= 1e3 ? '$' + (v/1e3).toFixed(0) + 'k' : '$' + v.toFixed(0);
const pctY = v => Math.abs(v) < 0.005 ? '0%' : pct(v, true, 0);
const span = (a, b) => a.slice(0,4) === b.slice(0,4) ? a.slice(0,4) : `${a.slice(0,4)}-${b.slice(0,4)}`;
const longMoney = v => '$' + Math.round(v).toLocaleString();
function el(tag, attrs, parent){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e;}
function txt(p,x,y,s,cls,anchor){const t=el('text',{x,y,class:cls||'lbl','text-anchor':anchor||'start'},p);t.textContent=s;return t;}
function showTT(x,y,title,rows){tt.textContent='';const d=document.createElement('div');d.className='d';d.textContent=title;tt.appendChild(d);
  for(const r of rows){const row=document.createElement('div');row.className='r';const n=document.createElement('span');n.className='n';const k=document.createElement('i');k.className='key';k.style.background=`var(--${r.cls})`;n.appendChild(k);n.appendChild(document.createTextNode(r.name));const b=document.createElement('b');b.textContent=r.val;row.appendChild(n);row.appendChild(b);tt.appendChild(row);}
  tt.style.display='block';const w=tt.offsetWidth,h=tt.offsetHeight;let left=x+14,top=y-h-10;if(left+w>innerWidth-8)left=x-w-14;left=Math.max(8,Math.min(left,innerWidth-w-8));if(top<8)top=y+14;tt.style.left=left+'px';tt.style.top=top+'px';}
const hide=()=>{tt.style.display='none';};
const SER=[['book','s1','book (4 engines)'],['QQQ','b1','QQQ'],['SPY','b2','SPY']];
const dates=M.paths.dates, xs=dates.map(yr), X0=xs[0], X1=xs[xs.length-1], n=dates.length;

function lines(id, dd){
  const svg=document.getElementById(id); svg.textContent='';
  const W=Math.max(320, svg.parentElement.clientWidth-32), narrow=W<600, H=dd?200:360, m={l:56,r:narrow?60:120,t:dd?8:14,b:26};
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const X=v=>m.l+(v-X0)*(W-m.l-m.r)/(X1-X0);
  const keys=dd?[['book','s1','book'],['SPY','b2','SPY']]:SER;
  let lo=Infinity,hi=-Infinity;for(const [k] of keys)for(const v of M.paths[k][dd?'dd':'value']){lo=Math.min(lo,v);hi=Math.max(hi,v);}
  if(dd){hi=0;lo=Math.min(lo,-0.6);}
  const tr=dd?(v=>v):Math.log10, Y=v=>m.t+(tr(hi)-tr(v))*(H-m.t-m.b)/(tr(hi)-tr(lo));
  const x15=X(2015);el('rect',{x:x15,y:m.t,width:X(X1)-x15,height:H-m.t-m.b,fill:css('--band')},svg);
  if(!dd)txt(svg,(x15+X(X1))/2,m.t+12,narrow?'in sample':'in sample (rules built on these years)','lbl','middle');
  const g=el('g',{class:'axis'},svg);
  for(let y=1998;y<=2026;y+=(W<600?6:2)){const x=X(y);el('line',{x1:x,x2:x,y1:m.t,y2:H-m.b,stroke:css('--grid'),'stroke-width':1},g);txt(g,x,H-8,String(y),null,'middle');}
  const ticks=dd?[0,-0.2,-0.4,-0.6,-0.8]:[1e5,1e6,1e7,1e8,1e9,1e10,1e11].filter(t=>t>=lo/1.01&&t<=hi*1.01);
  for(const t of ticks){if(t<lo||t>hi)continue;el('line',{x1:m.l,x2:W-m.r,y1:Y(t),y2:Y(t),stroke:css('--grid'),'stroke-width':1},g);txt(g,m.l-6,Y(t)+4,dd?(t*100).toFixed(0)+'%':money(t),null,'end');}
  if(!dd){const yc=Y(D.capacity);el('line',{x1:m.l,x2:W-m.r,y1:yc,y2:yc,stroke:css('--ink2'),'stroke-width':1.2,'stroke-dasharray':'5 4'},svg);txt(svg,m.l+6,yc-6,narrow?'~$10M ceiling':'~$10M: practical ceiling of the current strategy set','lbl');}
  for(const [k,cls] of keys.slice().reverse()){let p='';M.paths[k][dd?'dd':'value'].forEach((v,i)=>p+=(i?'L':'M')+X(xs[i]).toFixed(1)+','+Y(v).toFixed(1));el('path',{d:p,fill:'none',stroke:`var(--${cls})`,'stroke-width':k==='book'?2.2:1.5,'stroke-linejoin':'round'},svg);}
  if(!dd){const labs=keys.map(([k,cls,name])=>({k,cls,name,y:Y(M.paths[k].value[n-1])})).sort((a,b)=>a.y-b.y);
    for(let i=1;i<labs.length;i++)if(labs[i].y-labs[i-1].y<14)labs[i].y=labs[i-1].y+14;
    for(const L of labs){el('circle',{cx:X(X1),cy:Y(M.paths[L.k].value[n-1]),r:4,fill:`var(--${L.cls})`,stroke:css('--surface'),'stroke-width':2},svg);txt(svg,X(X1)+8,L.y+4,narrow?money(M.paths[L.k].value[n-1]):`${L.name.split(' (')[0]} ${money(M.paths[L.k].value[n-1])}`);}}
  const cross=el('line',{y1:m.t,y2:H-m.b,stroke:css('--axis'),'stroke-width':1,visibility:'hidden'},svg);
  const hit=el('rect',{x:m.l,y:m.t,width:W-m.l-m.r,height:H-m.t-m.b,fill:'transparent',tabindex:0},svg);
  const idx=x=>{const v=X0+(x-m.l)*(X1-X0)/(W-m.l-m.r);let a=0,b=n-1;while(a<b){const c=(a+b)>>1;if(xs[c]<v)a=c+1;else b=c;}return a;};
  const move=(cx,cy,i)=>{cross.setAttribute('x1',X(xs[i]));cross.setAttribute('x2',X(xs[i]));cross.setAttribute('visibility','visible');showTT(cx,cy,dates[i],keys.map(([k,cls,name])=>({name,cls,val:dd?(M.paths[k].dd[i]*100).toFixed(1)+'%':money(M.paths[k].value[i])})));};
  hit.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect();move(e.clientX,e.clientY,idx((e.clientX-r.left)*W/r.width));});
  hit.addEventListener('pointerleave',()=>{cross.setAttribute('visibility','hidden');hide();});
  let ki=n-1;const key=()=>{const r=svg.getBoundingClientRect();move(r.left+r.width*0.6,r.top+20,ki);};
  hit.addEventListener('focus',key);hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')ki=Math.max(0,ki-1);else if(e.key==='ArrowRight')ki=Math.min(n-1,ki+1);else return;e.preventDefault();key();});
  hit.addEventListener('blur',()=>{cross.setAttribute('visibility','hidden');hide();});
}

function fill(){
  const B=M.book, E=D.eras.ts_synth, R=D.range, PG=D.pregate;
  document.getElementById('sub').textContent=`The four live symphonies at 29/29/27/15 (HG with today's 200-day gate, the KMLM switcher with its VIX sleeve, the crash sleeve, the VIX harvester), drifting, with the 40% cap. $100,000 invested at the 1996-12-31 close, run to ${M.last}. Every fund before its launch is a proxy or a model (see below); costs at each engine's measured Composer rate. A paper result, not a forecast.`;
  const k=document.getElementById('kpis');k.textContent='';
  const items=[[`~${money(E.final)}`,`on paper by ${M.last} in the main case (${pct(B.cagr)} a year, Sharpe ${B.sharpe.toFixed(2)}, Sortino ${B.sortino.toFixed(2)}); ${money(R.final_lo)} to ${money(R.final_hi)} across the proxy and rule choices below`],
    [`${money(R.end2014_lo)} to ${money(R.end2014_hi)}`,`by end-2014, before the years the rules were built on: ${pct(R.cagr_lo,true,0)} to ${pct(R.cagr_hi,true,0)} a year (the low end without HG's 200-day gate)`],
    [`${pct(B.maxdd,false,0)} / ${pct(B.worst_year[0],true,0)}`,`book max drawdown (${B.maxdd_peak.slice(0,7)} to ${B.maxdd_trough.slice(0,7)}) / worst calendar year (${B.worst_year[1]})`],
    [money(M.bench.SPY.final_multiple*1e5),`SPY over the same years (${pct(M.bench.SPY.cagr)} a year, max DD ${pct(M.bench.SPY.maxdd,false,0)}); QQQ ${money(M.bench.QQQ.final_multiple*1e5)}`]];
  for(const [b,s] of items){const d=document.createElement('div');d.className='kpi';const bb=document.createElement('b');bb.textContent=b;const ss=document.createElement('span');ss.textContent=s;d.appendChild(bb);d.appendChild(ss);k.appendChild(d);}
  const lg=document.getElementById('lg-eq');lg.textContent='';
  for(const [,cls,name] of SER){const s=document.createElement('span');const i=document.createElement('i');i.className='key';i.style.background=`var(--${cls})`;s.appendChild(i);s.appendChild(document.createTextNode(name));lg.appendChild(s);}
  const s2=document.createElement('span');const i2=document.createElement('i');i2.className='sw';s2.appendChild(i2);s2.appendChild(document.createTextNode('in sample (2015 on)'));lg.appendChild(s2);
  const ty=document.getElementById('years');ty.textContent='';
  const cell=(tr,v,cls)=>{const td=document.createElement('td');td.textContent=v;if(cls)td.className=cls;tr.appendChild(td);};
  for(const y of Object.keys(B.by_year)){const tr=document.createElement('tr');if(y>='2015')tr.className='insample';const th=document.createElement('th');th.scope='row';th.textContent=y;tr.appendChild(th);
    for(const v of [B.by_year[y],M.engines.HG.by_year[y],M.engines.KMLM.by_year[y],M.engines.SLEEVE.by_year[y],M.engines.HARV.by_year[y],M.bench.SPY.by_year[y]])cell(tr,pctY(v),Math.abs(v)<0.005?'':(v>=0?'pos':'neg'));
    ty.appendChild(tr);}
  const te=document.getElementById('engines');te.textContent='';
  const rows=[['Book (29/29/27/15, 40% cap)',B],['HG (with the 200-day gate)',M.engines.HG],['KMLM switcher + VIX sleeve',M.engines.KMLM],['Crash sleeve',M.engines.SLEEVE],['VIX harvester',M.engines.HARV],['SPY',M.bench.SPY],['QQQ',M.bench.QQQ]];
  for(const [lab,s] of rows){const tr=document.createElement('tr');const th=document.createElement('th');th.scope='row';th.textContent=lab;tr.appendChild(th);
    for(const v of [money(s.final_multiple*1e5),pct(s.cagr),s.sharpe.toFixed(2),s.sortino.toFixed(2),`${pct(s.maxdd,false,0)} (${span(s.maxdd_peak,s.maxdd_trough)})`,`${pct(s.worst_year[0],true,0)} (${s.worst_year[1]})`,`${(s.longest_underwater_sessions/252).toFixed(1)} yrs`])cell(tr,v);
    te.appendChild(tr);}
  const fillRows=(id,list)=>{const t=document.getElementById(id);t.textContent='';for(const r of list){const tr=document.createElement('tr');const th=document.createElement('th');th.scope='row';th.textContent=r.label;tr.appendChild(th);
    for(const v of [money(r.end2014),pct(r.cagr_9714),money(r.final),pct(r.maxdd,false,0)])cell(tr,v);t.appendChild(tr);}};
  fillRows('sens',D.sens_rows);fillRows('rules',D.rule_rows);
  const tf=document.getElementById('fid');tf.textContent='';
  const NM={HG:'HG',KMLM:'KMLM switcher',SLEEVE:'Crash sleeve',HARV:'VIX harvester'};
  for(const e of ['HG','KMLM','SLEEVE','HARV']){const f=D.fid.real_era[e];const tr=document.createElement('tr');const th=document.createElement('th');th.scope='row';th.textContent=NM[e];tr.appendChild(th);
    for(const v of [`${f.from.slice(0,7)} to ${f.to.slice(0,7)}`,f.corr.toFixed(4),`${pct(f.composer_cagr,true,0)} / ${pct(f.model_cagr,true,0)}`])cell(tr,v);tf.appendChild(tr);}
  const k2=D.fid.kmlm_signal.KMLM, hb=D.fid.hg_vs_panel_b, S=D.splices, H=D.harv, RS=D.resets;
  const fn=[`The KMLM switcher's main decision (XLK's 10-day RSI against the managed-futures fund's) uses a trend proxy before 2007 (12-month moving-average signs on Treasuries, the dollar index and the S&P GSCI). It matches the RYMFX/KMLM-based decision on ${(S['KMLM flag agreement, proxy vs real, 2007-16']*100).toFixed(0)}% of days in 2007-16 and ${(S['KMLM flag agreement, proxy vs real, 2017-26']*100).toFixed(0)}% in 2017-26, barely better than a constant RSI of 50 (${(S['KMLM flag agreement, constant 50 vs real, 2007-16']*100).toFixed(0)}% and ${(S['KMLM flag agreement, constant 50 vs real, 2017-26']*100).toFixed(0)}%): the switcher's pre-2007 decisions are close to unknowable, which is why the table carries both. Over 2007-26 the proxy changes that engine by ${pct(k2.proxy_cagr-k2.main_cagr,true,0)} a year overall, with large offsetting errors by sub-period.`,
    `HG on this panel, with the constant-carry VIX funds of the earlier study, reproduces the reviewed 1990-2026 gate study exactly (correlation ${hb.corr.toFixed(4)}, ${pct(hb.long_panel_cagr)} a year in both).`,
    `Bond ETFs before launch: Vanguard Treasury, investment-grade and high-yield funds scaled on the overlap (TLT correlation ${S['TLT <- VUSTX x1.109'].corr}). Sector and style ETFs before their launch (1998-2005): Ken French's CRSP industry and size/value portfolios (correlations 0.84-0.98 where both exist). Leveraged funds: 2x/3x the daily return of their 1x base, financed at T-bills. UVXY before its 2011 launch is modelled at its original 2x; today's fund is 1.5x (both in the table).`,
    `Known modelling limits: the switcher is simulated with a daily rebalance where Composer uses a 10% corridor; the book's ${RS.n} cap resets (${Object.entries(RS.by_engine).map(([e,n])=>`${e} ${n}`).join(', ')}) are not costed (about -0.6% of the final at 5 bp); before 2007 the sleeve's HYG signal reads a stale-NAV mutual fund (correlation 0.52); gold before 2000 is a miners index (gold is held on 0.0% of days).`];
  const ul=document.getElementById('fidnotes');ul.textContent='';for(const t of fn){const li=document.createElement('li');li.textContent=t;ul.appendChild(li);}
  const c=D.cross;
  const hb2=H['harvester share in T-bills'], hs=H['harvester share spread over the other three'];
  const hn=[`In sample: HG's rules were set by its author on 2015-2026 data; the KMLM switcher (2022) and the sleeve's components (2023-25) were written by community authors on recent data; the four were combined in July 2026 on 2015-2026 backtests; HG's 200-day gate was chosen on 1990-2026 (add. 40). The years from 2015 turn $${(E.end2014/1e6).toFixed(1)}M into ~$${(E.final/1e9).toFixed(0)}B (${pct(E.cagr_1526,true,0)} a year). Before 2015 the book compounds at ${pct(R.cagr_lo,true,0)} to ${pct(R.cagr_hi,true,0)} a year; the low end drops the in-sample gate.`,
    `Capacity: the book passes $1M on ${c['1,000,000']}, $10M on ${c['10,000,000']} and $1B on ${c['1,000,000,000']}. The current strategy set's practical ceiling is about $5-10M (addendum 15: ZVOL, VXZ and VIXM run out of daily volume first). Nothing above that line could have been done.`,
    `Proxies: before each fund existed its prices are rebuilt (leveraged funds from their 1x base; VIX funds from a model of a futures curve that did not trade before 2004; the switcher's managed-futures signal from a trend proxy). HG's 2x/3x funds launched 2006-2010 (LABU 2015) and the VIX funds 2009-2023; VIX futures first traded in 2004.`,
    `The 40% cap: it trades terminal wealth for drawdown. Without it the paper path ends near ${money(D.rule_rows.find(r=>r.label.startsWith('no cap')).final)} with a ${pct(D.rule_rows.find(r=>r.label.startsWith('no cap')).maxdd,false,0)} drawdown; small changes to its timing move the final by tens of billions, so read the headline as an order of magnitude.`,
    `The VIX harvester earns little alone (${pct(M.engines.HARV.cagr,true,1)} a year, ${(M.engines.HARV.longest_underwater_sessions/252).toFixed(1)} years underwater from ${M.engines.HARV.underwater_from.slice(0,4)}), but holding its 15% in T-bills instead would end lower (${money(hb2.final)}, Sharpe ${hb2.sharpe.toFixed(2)} vs ${B.sharpe.toFixed(2)}); spreading its share over the other three ends higher (${money(hs.final)}) with a deeper drawdown (${pct(hs.maxdd,false,0)}).`,
    `Costs are Composer's measured rate per unit of turnover; no market impact, no taxes, no withdrawals; signals and trades at the same close.`];
  const uh=document.getElementById('honest');uh.textContent='';for(const t of hn){const li=document.createElement('li');li.textContent=t;uh.appendChild(li);}
}
function draw(){fill();lines('eq',false);lines('dd',true);}
draw(); let rt; addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,120);});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    main()
