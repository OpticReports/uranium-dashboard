"""Render results/leverage-ytd-2026-10-16.html from LEV_DATA/lev_study.json (self-contained page)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lev_study import D   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results', 'leverage-ytd-2026-10-16.html')


def main():
    S = json.load(open(f'{D}/lev_study.json'))
    M, Ms = S['metrics']['real'], S['metrics']['self']
    ser = S['series']
    data = {
        'dates': ser['dates'],
        'lines': [
            {'key': 'actual', 'name': 'Actual (live account)', 'cls': 's1', 'v': ser['acct_actual']},
            {'key': 'unlev', 'name': 'Same trades, no leverage', 'cls': 's2', 'v': ser['acct_unlev']},
            {'key': 'upro', 'name': 'UPRO (3x S&P, buy & hold)', 'cls': 'b2', 'v': ser['upro']},
            {'key': 'spy', 'name': 'SPY (buy & hold)', 'cls': 'b1', 'v': ser['spy']},
        ],
        'engines': [
            {'name': e, 'L': M[f'{e} levered (model)'], 'U': M[f'{e} unlevered (model)']} for e in ('HG', 'KMLM', 'SLEEVE', 'HARV')
        ] + [{'name': 'Book as built', 'L': M['BOOK as built, levered (model)'], 'U': M['BOOK as built, unlevered (model)']}],
    }
    rows = [
        ('Account, actual (live)', M['ACCOUNT actual (live)']),
        ('Account, same trades with no leverage', M['ACCOUNT unlevered']),
        ('  check: model holdings, no live inference', M['ACCOUNT unlevered, model holdings (no HG inference)']),
        ('  check: every ETF de-levered from its own returns', Ms['ACCOUNT unlevered']),
        ('Book as built today, levered (model)', M['BOOK as built, levered (model)']),
        ('Book as built today, no leverage (model)', M['BOOK as built, unlevered (model)']),
    ]
    for e in ('HG', 'KMLM', 'SLEEVE', 'HARV'):
        rows.append((f'{e}, levered (model)', M[f'{e} levered (model)']))
        rows.append((f'{e}, no leverage (model)', M[f'{e} unlevered (model)']))
    for b in ('SPY', 'QQQ', 'SSO', 'UPRO'):
        rows.append((f'{b} buy & hold', M[f'{b} buy & hold']))
    tiers = S['tiers']['HG']

    def pct(x, sign=True):
        return f"{x * 100:+.1f}%" if sign else f"{x * 100:.1f}%"

    trs = '\n'.join(
        f"<tr{' class=sub' if n.startswith('  ') else ''}><th scope=row>{n.strip()}</th><td>{pct(m['ytd'])}</td><td>{m['sharpe']:.2f}</td>"
        f"<td>{m['sortino']:.2f}</td><td>{pct(m['maxdd'], False)}</td><td>{pct(m['vol'], False)}</td></tr>" for n, m in rows)
    tier_rows = '\n'.join(
        f"<tr><th scope=row>{g}</th><td>{tiers['levered'][g]['days']}</td><td>{pct(tiers['levered'][g]['ann_excess_contrib'])}</td>"
        f"<td>{tiers['levered'][g]['variance_share'] * 100:.0f}%</td><td>{pct(tiers['unlevered'][g]['ann_excess_contrib'])}</td>"
        f"<td>{tiers['unlevered'][g]['variance_share'] * 100:.0f}%</td></tr>" for g in ('3x', '2x', '1.5x', 'no leverage'))
    A, U, SP, UP = M['ACCOUNT actual (live)'], M['ACCOUNT unlevered'], M['SPY buy & hold'], M['UPRO buy & hold']
    kpi = [('YTD return', pct(A['ytd']), pct(U['ytd']), pct(SP['ytd']), pct(UP['ytd'])),
           ('Sharpe', f"{A['sharpe']:.2f}", f"{U['sharpe']:.2f}", f"{SP['sharpe']:.2f}", f"{UP['sharpe']:.2f}"),
           ('Sortino', f"{A['sortino']:.2f}", f"{U['sortino']:.2f}", f"{SP['sortino']:.2f}", f"{UP['sortino']:.2f}"),
           ('Max drawdown', pct(A['maxdd'], False), pct(U['maxdd'], False), pct(SP['maxdd'], False), pct(UP['maxdd'], False)),
           ('Volatility', pct(A['vol'], False), pct(U['vol'], False), pct(SP['vol'], False), pct(UP['vol'], False))]
    Dl = S['dollars']
    kpi.insert(1, ('Dollar gain YTD', f"${Dl['actual']['gain_recorded_deposits'] / 1000:,.1f}k", f"${Dl['unlevered']['gain_recorded_deposits'] / 1000:,.1f}k", '', ''))
    kpi_rows = '\n'.join(f"<tr><th scope=row>{a}</th><td class=em>{b}</td><td class=em>{c}</td><td>{d}</td><td>{e}</td></tr>" for a, b, c, d, e in kpi)
    lev_pp = (A['ytd'] - U['ytd']) * 100
    html = TEMPLATE.replace('__DATA__', json.dumps(data)).replace('__ROWS__', trs).replace('__TIERS__', tier_rows) \
        .replace('__KPI__', kpi_rows).replace('__LEVPP__', f"{lev_pp:.0f}").replace('__ACT__', pct(A['ytd'])).replace('__UNL__', pct(U['ytd']))
    open(OUT, 'w').write(html)
    print('wrote', os.path.normpath(OUT))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leverage attribution YTD</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--b1:#898781;--b2:#52514e;--wash1:rgba(42,120,214,.10);--wash2:rgba(235,104,52,.10)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--b1:#898781;--b2:#c3c2b7;--wash1:rgba(57,135,229,.12);--wash2:rgba(217,89,38,.12)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--b1:#898781;--b2:#c3c2b7;--wash1:rgba(57,135,229,.12);--wash2:rgba(217,89,38,.12)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1060px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}
h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 14px;font-size:14px}
.lede{font-size:17px;margin:14px 0 18px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:0 0 16px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:760px){.grid2{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums}
th[scope=row]{text-align:left;font-weight:500}
thead th{color:var(--ink2);font-weight:600;font-size:13px}
td.em{font-weight:650}
tr.sub th{padding-left:22px;color:var(--ink2);font-weight:400}
tr.sub td{color:var(--ink2)}
.tablewrap{overflow-x:auto}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 4px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.key{display:inline-block;width:16px;height:2px;border-radius:1px}
.keyb{display:inline-block;width:10px;height:10px;border-radius:2px}
svg{display:block;width:100%;height:auto;overflow:visible}
.tt{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:5;min-width:170px}
.tt .d{color:var(--ink2);margin-bottom:4px}
.tt .r{display:flex;align-items:center;gap:8px;justify-content:space-between}
.tt .r b{font-variant-numeric:tabular-nums}
.tt .n{display:inline-flex;align-items:center;gap:6px;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}
.notes li{margin:3px 0}
.axis text{fill:var(--muted);font-size:11px}
.lbl{fill:var(--ink2);font-size:12px}
.val{fill:var(--ink);font-size:11.5px;font-variant-numeric:tabular-nums}
</style>
</head>
<body>
<main class="viz-root">
<h1>How much of this year's return came from leverage</h1>
<p class="sub-h">Composer account, 2025-12-31 close to 2026-10-15 close (198 sessions), time-weighted. "No leverage" keeps every signal, trade and day, and swaps each 2x/3x ETF for its 1x version at the holding step (TQQQ to QQQ, UDOW to DIA, SQQQ to PSQ, UVXY to VIXY, and so on).</p>
<p class="lede">The account made <b>__ACT__</b>. The same trades without leverage made about <b>__UNL__</b>. Leverage added roughly <b>__LEVPP__ points</b>. It also lifted Sharpe this year, because the 3x positions sat on the strategy's best signals, but nine and a half months is too short to call that gap firm.</p>

<section class="card">
<h2>Actual vs no leverage, with the market for scale</h2>
<p class="sub-h">UPRO is plain 3x S&amp;P at about the same volatility as the account: leverage with no signals. Returns are time-weighted, which counts every day equally; most of the money arrived April to July, so the dollar row is the truer read of what you made ($246k deposited this year, the same deposits replayed through both paths).</p>
<div class="tablewrap"><table>
<thead><tr><th></th><th>Actual</th><th>No leverage</th><th>SPY</th><th>UPRO (3x SPY)</th></tr></thead>
<tbody>__KPI__</tbody></table></div>
</section>

<section class="card">
<h2>Growth of $1</h2>
<div class="legend" id="lg-eq"></div>
<svg id="eq" role="img" aria-label="Growth of one dollar, year to date: actual account, same trades with no leverage, SPY and UPRO"></svg>
</section>

<section class="card">
<h2>Drawdown from peak</h2>
<div class="legend" id="lg-dd"></div>
<svg id="dd" role="img" aria-label="Drawdown from running peak for the same four series"></svg>
</section>

<div class="grid2">
<section class="card">
<h2>By engine: YTD return</h2>
<p class="sub-h">Current versions, Composer model, full year to date. Book = 29/29/27/15 with the 40% cap.</p>
<div class="legend"><span><i class="keyb" style="background:var(--s1)"></i>Levered (as built)</span><span><i class="keyb" style="background:var(--s2)"></i>No leverage</span></div>
<svg id="engret" role="img" aria-label="Year-to-date return by engine, levered vs no leverage"></svg>
</section>
<section class="card">
<h2>By engine: max drawdown</h2>
<p class="sub-h">Same runs. HARV holds nothing leveraged, so its two bars are equal.</p>
<div class="legend"><span><i class="keyb" style="background:var(--s1)"></i>Levered (as built)</span><span><i class="keyb" style="background:var(--s2)"></i>No leverage</span></div>
<svg id="engdd" role="img" aria-label="Maximum drawdown by engine, levered vs no leverage"></svg>
</section>
</div>

<section class="card">
<h2>Why Sharpe falls when leverage comes off (HG, current version)</h2>
<p class="sub-h">Leverage is concentrated on HG's best signal. Taking it off shrinks the 3x days about threefold, but the hedge and bond days barely shrink, so they become a bigger share of the risk.</p>
<div class="tablewrap"><table>
<thead><tr><th>Days holding</th><th>Days</th><th>Excess return/yr, levered</th><th>Share of variance</th><th>Excess return/yr, no leverage</th><th>Share of variance</th></tr></thead>
<tbody>__TIERS__</tbody></table></div>
</section>

<section class="card">
<h2>Table view: every series</h2>
<div class="tablewrap"><table>
<thead><tr><th></th><th>YTD</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Vol</th></tr></thead>
<tbody>__ROWS__</tbody></table></div>
</section>

<section class="card notes">
<h2 style="color:var(--ink)">Basis and limits</h2>
<ul>
<li>Actual = Composer's own time-weighted account return. No leverage = that return minus each day's leverage contribution, computed from the holdings of the symphony version that was live that day. Fills, cash drag and deposit timing stay as they happened.</li>
<li>HG holds one asset at a time. On the 10 days its live return matched a different holding than the model's (a switch made a session early or late at the 15:50 rebalance), the live holding was used.</li>
<li>Sharpe and Sortino are annualised from daily returns over T-bills. On nine and a half months the levels are loose: a block bootstrap puts the actual Sharpe's 90% band at 0.3 to 3.8. The gap between the columns is tighter but not firm: +0.45, with a 90% band of -0.30 to +1.34.</li>
<li>Trading costs are held equal. 1x ETFs trade at tighter spreads, which would add perhaps a point or two to the no-leverage side.</li>
<li>Signals were not re-run on 1x prices. The thresholds are tuned to the leveraged tickers, so that would be a different strategy.</li>
<li>Engine rows use the Composer model. KMLM, SLEEVE and HARV were designed in July on data that includes this year, so their first half is in sample. The account rows are entirely live.</li>
<li>Composer's backtest charges about 8 points this year on HG's 162x turnover. Live paid about 5. That gap is why the costed model reads lower than live. It does not depend on leverage.</li>
</ul>
</section>
</main>
<div class="tt" id="tt" role="status" aria-live="polite"></div>
<script>
const DATA = __DATA__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tt = document.getElementById('tt');
const fmtPct = (x, s=true) => (s && x >= 0 ? '+' : '') + (x*100).toFixed(1) + '%';
const mon = d => ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+d.slice(5,7)-1];
function el(tag, attrs, parent){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e;}
function legend(id, items){const lg=document.getElementById(id);lg.textContent='';for(const it of items){const s=document.createElement('span');const k=document.createElement('i');k.className='key';k.style.background=`var(--${it.cls})`;s.appendChild(k);s.appendChild(document.createTextNode(it.name));lg.appendChild(s);}}
function showTT(x, y, title, rows){tt.textContent='';const d=document.createElement('div');d.className='d';d.textContent=title;tt.appendChild(d);
  for(const r of rows){const row=document.createElement('div');row.className='r';const n=document.createElement('span');n.className='n';const k=document.createElement('i');k.className='key';k.style.background=`var(--${r.cls})`;n.appendChild(k);n.appendChild(document.createTextNode(r.name));const b=document.createElement('b');b.textContent=r.val;row.appendChild(n);row.appendChild(b);tt.appendChild(row);}
  tt.style.display='block';const w=tt.offsetWidth,h=tt.offsetHeight;let left=x+14,top=y-h-10;if(left+w>innerWidth-8)left=x-w-14;if(top<8)top=y+14;tt.style.left=left+'px';tt.style.top=top+'px';}
function hideTT(){tt.style.display='none';}

function lineChart(id, series, opts){
  const svg=document.getElementById(id); svg.textContent='';
  const W=Math.max(320, svg.parentElement.clientWidth-32), H=opts.h, m={l:44,r:opts.rlab?118:12,t:10,b:26};
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const n=DATA.dates.length, xs=i=>m.l+i*(W-m.l-m.r)/(n-1);
  let lo=Infinity,hi=-Infinity; for(const s of series)for(const v of s.v){lo=Math.min(lo,v);hi=Math.max(hi,v);}
  lo=opts.lo!==undefined?Math.min(opts.lo,lo):lo; hi=opts.hi!==undefined?Math.max(opts.hi,hi):hi;
  const ticks=opts.ticks(lo,hi); lo=Math.min(lo,ticks[0]); hi=Math.max(hi,ticks[ticks.length-1]);
  const ys=v=>m.t+(hi-v)*(H-m.t-m.b)/(hi-lo);
  const g=el('g',{class:'axis'},svg);
  for(const t of ticks){el('line',{x1:m.l,x2:W-m.r,y1:ys(t),y2:ys(t),stroke:css(t===opts.base?'--axis':'--grid'),'stroke-width':1},g);const tx=el('text',{x:m.l-6,y:ys(t)+4,'text-anchor':'end'},g);tx.textContent=opts.fmt(t);}
  const step=(W-m.l-m.r)/10<36?2:1;let last='',k=0;DATA.dates.forEach((d,i)=>{const mm=d.slice(0,7);if(mm!==last){last=mm;if(k++%step===0){const tx=el('text',{x:xs(i),y:H-8,'text-anchor':'middle'},g);tx.textContent=mon(d);}}});
  for(const s of series.slice().reverse()){
    if(opts.area && s.wash){let p=`M${xs(0)},${ys(opts.base)}`;s.v.forEach((v,i)=>p+=`L${xs(i)},${ys(v)}`);p+=`L${xs(n-1)},${ys(opts.base)}Z`;el('path',{d:p,fill:`var(--${s.wash})`,stroke:'none'},svg);}
    let p='';s.v.forEach((v,i)=>p+=(i?'L':'M')+xs(i).toFixed(1)+','+ys(v).toFixed(1));
    el('path',{d:p,fill:'none',stroke:`var(--${s.cls})`,'stroke-width':s.cls.startsWith('s')?2:1.5,'stroke-linejoin':'round','stroke-linecap':'round'},svg);
  }
  if(opts.rlab){ // end labels with simple collision push
    const labs=series.map(s=>({s,y:ys(s.v[n-1])})).sort((a,b)=>a.y-b.y);
    for(let i=1;i<labs.length;i++)if(labs[i].y-labs[i-1].y<15)labs[i].y=labs[i-1].y+15;
    for(const L of labs){el('circle',{cx:xs(n-1),cy:ys(L.s.v[n-1]),r:4,fill:`var(--${L.s.cls})`,stroke:css('--surface'),'stroke-width':2},svg);
      const tx=el('text',{x:xs(n-1)+9,y:L.y+4,class:'lbl'},svg);tx.textContent=`${L.s.short} ${opts.endfmt(L.s.v[n-1])}`;}
  }
  if(opts.troughs){ // label the extreme (worst point) of the named series, not every point
    for(const s of series.filter(s=>opts.troughs.includes(s.key))){let j=0;s.v.forEach((v,i)=>{if(v<s.v[j])j=i;});
      el('circle',{cx:xs(j),cy:ys(s.v[j]),r:4,fill:`var(--${s.cls})`,stroke:css('--surface'),'stroke-width':2},svg);
      const txt=`${s.short} worst ${opts.endfmt(s.v[j])}`, right=xs(j)+8+txt.length*6.6>W-2;
      const tx=el('text',{x:right?xs(j)-8:xs(j)+8,y:ys(s.v[j])+14,class:'lbl','text-anchor':right?'end':'start'},svg);tx.textContent=txt;}
  }
  const cross=el('line',{y1:m.t,y2:H-m.b,stroke:css('--axis'),'stroke-width':1,visibility:'hidden'},svg);
  const hit=el('rect',{x:m.l,y:m.t,width:W-m.l-m.r,height:H-m.t-m.b,fill:'transparent',tabindex:0},svg);
  const at=i=>{cross.setAttribute('x1',xs(i));cross.setAttribute('x2',xs(i));cross.setAttribute('visibility','visible');};
  const move=(cx,cy,i)=>{at(i);showTT(cx,cy,DATA.dates[i],series.map(s=>({name:s.name,cls:s.cls,val:opts.ttfmt(s.v[i])})));};
  hit.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect();const x=(e.clientX-r.left)*W/r.width;const i=Math.max(0,Math.min(n-1,Math.round((x-m.l)*(n-1)/(W-m.l-m.r))));move(e.clientX,e.clientY,i);});
  hit.addEventListener('pointerleave',()=>{cross.setAttribute('visibility','hidden');hideTT();});
  let ki=n-1;hit.addEventListener('focus',()=>{const r=svg.getBoundingClientRect();move(r.left+r.width*0.6,r.top+20,ki);});
  hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')ki=Math.max(0,ki-1);else if(e.key==='ArrowRight')ki=Math.min(n-1,ki+1);else return;e.preventDefault();const r=svg.getBoundingClientRect();move(r.left+r.width*0.6,r.top+20,ki);});
  hit.addEventListener('blur',()=>{cross.setAttribute('visibility','hidden');hideTT();});
}

function barChart(id, key, opts){
  const svg=document.getElementById(id); svg.textContent='';
  const W=Math.max(300, svg.parentElement.clientWidth-32), rowH=46, m={l:96,r:62,t:4,b:4}, H=m.t+m.b+DATA.engines.length*rowH;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const mx=Math.max(...DATA.engines.flatMap(e=>[e.L[key],e.U[key]]))*1.02, xs=v=>m.l+v*(W-m.l-m.r)/mx;
  el('line',{x1:m.l,x2:m.l,y1:m.t,y2:H-m.b,stroke:css('--axis'),'stroke-width':1},svg);
  DATA.engines.forEach((e,i)=>{const y0=m.t+i*rowH+6;const tx=el('text',{x:m.l-8,y:y0+19,'text-anchor':'end',class:'lbl'},svg);tx.textContent=e.name;
    [['L','s1','Levered (as built)'],['U','s2','No leverage']].forEach(([k,c,nm],j)=>{const v=e[k][key],y=y0+j*17,bw=Math.max(0,xs(v)-m.l),bh=14;
      const r=Math.min(4,bw/2);const p=`M${m.l},${y}H${m.l+bw-r}Q${m.l+bw},${y} ${m.l+bw},${y+r}V${y+bh-r}Q${m.l+bw},${y+bh} ${m.l+bw-r},${y+bh}H${m.l}Z`;
      const bar=el('path',{d:p,fill:`var(--${c})`,tabindex:0},svg);
      const t=el('text',{x:m.l+bw+5,y:y+11,class:'val'},svg);t.textContent=opts.fmt(v);
      const show=(cx,cy)=>{bar.setAttribute('opacity','0.82');showTT(cx,cy,e.name,[{name:nm,cls:c,val:opts.fmt(v)},{name:'Sharpe',cls:c,val:e[k].sharpe.toFixed(2)},{name:'Sortino',cls:c,val:e[k].sortino.toFixed(2)}]);};
      bar.addEventListener('pointermove',ev=>show(ev.clientX,ev.clientY));bar.addEventListener('pointerleave',()=>{bar.removeAttribute('opacity');hideTT();});
      bar.addEventListener('focus',()=>{const b=bar.getBoundingClientRect();show(b.right,b.top);});bar.addEventListener('blur',()=>{bar.removeAttribute('opacity');hideTT();});
    });});
}

function draw(){
  const short={actual:'Actual',unlev:'No leverage',upro:'UPRO',spy:'SPY'};
  const eq=DATA.lines.map(s=>({...s,short:short[s.key],wash:null}));
  const dd=DATA.lines.map(s=>{let pk=-Infinity;return {...s,short:short[s.key],wash:s.key==='actual'?'wash1':(s.key==='unlev'?'wash2':null),v:s.v.map(v=>{pk=Math.max(pk,v);return v/pk-1;})};});
  legend('lg-eq',eq); legend('lg-dd',dd);
  lineChart('eq',eq,{h:330,rlab:true,base:1,lo:0.8,ticks:(lo,hi)=>{const t=[];for(let v=Math.floor(lo*10)/10;v<=hi+0.1;v+=0.2)t.push(+v.toFixed(1));return t;},fmt:v=>'$'+v.toFixed(2),endfmt:v=>fmtPct(v-1),ttfmt:v=>fmtPct(v-1)});
  lineChart('dd',dd,{h:260,rlab:false,troughs:['actual','unlev','upro'],base:0,hi:0,ticks:(lo,hi)=>{const t=[];for(let v=0;v>=lo-0.05;v-=0.05)t.push(+v.toFixed(2));return t.reverse();},fmt:v=>(v*100).toFixed(0)+'%',endfmt:v=>(v*100).toFixed(1)+'%',ttfmt:v=>(v*100).toFixed(1)+'%',area:true});
  barChart('engret','ytd',{fmt:v=>fmtPct(v)}); barChart('engdd','maxdd',{fmt:v=>(v*100).toFixed(1)+'%'});
}
draw(); let rt; addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,120);});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    main()
