"""Exhibit for the HG 200-day gate draft: Composer's own backtest of the saved draft and of the live tree against
the gate-lab model (fidelity_check.py output), the gate's off days on SPY's distance from its 200-day average,
and the numbers side by side.  Writes results/hg-200d-gate-draft-2026-10-18.html."""
import json
import os

D = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/draft'
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results', 'hg-200d-gate-draft-2026-10-18.html')


def episodes(days):
    """consecutive off days grouped into stretches (first, last, count), 'consecutive' = within 4 calendar days"""
    from datetime import date
    out = []
    for d in days:
        dd = date.fromisoformat(d)
        if out and (dd - date.fromisoformat(out[-1][1])).days <= 4:
            out[-1][1] = d
            out[-1][2] += 1
        else:
            out.append([d, d, 1])
    return out


def main():
    F = json.load(open(os.path.join(D, 'fidelity.json')))
    ident = json.load(open(os.path.join(D, 'draft_id.json')))
    ep = episodes(F['gate']['composer_off'])
    print(f"{len(F['gate']['composer_off'])} off days in {len(ep)} stretches:")
    for a, b, n in ep:
        print(f'  {a}..{b} {n}d')
    spy = F['gate']['spy_vs_200d']
    ds = F['chart']['dates']
    data = {'id': ident['symphony_id'], 'version': ident['version_id'], 'name': ident['name'],
            'live': {k: F['live'][k] for k in ('corr', 'drift', 'composer', 'model', 'composer_stats', 'match', 'n_mismatch', 'common_days', 'first', 'last')},
            'draft': {k: F['draft'][k] for k in ('corr', 'drift', 'composer', 'model', 'composer_stats', 'match', 'n_mismatch', 'common_days', 'first', 'last')},
            'dates': ds, 'curves': F['chart']['curves'],
            'spy': [spy.get(d) for d in ds], 'off': sorted(set(F['gate']['composer_off'])), 'episodes': ep,
            'trend_days': F['gate']['composer_trend_days'], 'n_off': len(F['gate']['composer_off']),
            'model_off_same': sorted(F['gate']['model_off']) == sorted(F['gate']['composer_off']),
            'close_off': len(F['gate'].get('model_off_close', []))}
    open(PAGE, 'w').write(TEMPLATE.replace('__DATA__', json.dumps(data)))
    print('wrote', os.path.normpath(PAGE))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HG gate draft</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--b2:#52514e;--wash:rgba(235,104,52,.14)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--b2:#c3c2b7;--wash:rgba(217,89,38,.18)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--b2:#c3c2b7;--wash:rgba(217,89,38,.18)}
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
th[scope=row]{text-align:left;font-weight:500;white-space:normal}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}
thead th:first-child{text-align:left}
.tablewrap{overflow-x:auto}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 4px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.key{display:inline-block;width:16px;height:0;border-top:2px solid;border-radius:1px}
.key.dash{border-top-style:dashed}
.sw{display:inline-block;width:14px;height:10px;border-radius:2px;background:var(--wash)}
svg{display:block;width:100%;height:auto;overflow:visible}
.axis text{fill:var(--muted);font-size:11px}
.lbl{fill:var(--ink2);font-size:12px}
.tt{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:5;min-width:190px}
.tt .d{color:var(--ink2);margin-bottom:4px}
.tt .r{display:flex;align-items:center;gap:8px;justify-content:space-between}
.tt .r b{font-variant-numeric:tabular-nums}
.tt .n{display:inline-flex;align-items:center;gap:6px;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}
.notes li{margin:3px 0}
code{font-size:13px}
</style>
</head>
<body>
<main class="viz-root">
<h1>HG with the 200-day gate: the draft, checked against Composer</h1>
<p class="sub-h" id="sub"></p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>Growth of $1 (log scale), Composer's backtest against the model</h2>
<p class="sub-h">Solid lines are Composer's own backtests of the live tree and of the saved draft (fees and 5 bp slippage); dashed lines are the gate lab's model of the same two. Shaded stretches are the days the draft sits in cash instead of a trend basket.</p>
<div class="legend" id="lg-eq"></div>
<svg id="eq" role="img" aria-label="Growth of one dollar for HG live and the gated draft, Composer backtest and model, with the gate's cash days shaded"></svg>
</section>

<section class="card">
<h2>Where the gate fires: SPY's distance from its 200-day average</h2>
<p class="sub-h" id="gatesub"></p>
<svg id="spy" role="img" aria-label="SPY distance from its 200-day moving average with the days the draft held cash marked"></svg>
</section>

<section class="card">
<h2>Numbers side by side, 2015-06-12 to 2026-10-07</h2>
<div class="tablewrap"><table>
<thead><tr><th>Series</th><th>CAGR</th><th>Sharpe</th><th>Max DD</th><th>Correlation with the model</th><th>Drift vs the model</th><th>Same holding as the model</th></tr></thead>
<tbody id="tbl"></tbody></table></div>
<p class="sub-h" style="margin-top:8px" id="tblnote"></p>
</section>

<section class="card notes">
<h2 style="color:var(--ink)">What was built, and what was not</h2>
<ul id="notes"></ul>
</section>
</main>
<div class="tt" id="tt" role="status" aria-live="polite"></div>
<script>
const D = __DATA__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tt = document.getElementById('tt');
const pct = (x, s=true) => (s && x >= 0 ? '+' : '') + (x*100).toFixed(1) + '%';
const yr = d => +d.slice(0,4) + ((+d.slice(5,7)-1)*30.44 + (+d.slice(8,10)-1))/365.25;
const SER = [['composer live','s1',false,'live HG, Composer'],['model live','s1',true,'live HG, model'],['composer draft','s3',false,'gated draft, Composer'],['model draft','s3',true,'gated draft, model']];
function el(tag, attrs, parent){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e;}
function txt(p,x,y,s,cls,anchor){const t=el('text',{x,y,class:cls||'lbl','text-anchor':anchor||'start'},p);t.textContent=s;return t;}
function showTT(x,y,title,rows){tt.textContent='';const d=document.createElement('div');d.className='d';d.textContent=title;tt.appendChild(d);
  for(const r of rows){const row=document.createElement('div');row.className='r';const n=document.createElement('span');n.className='n';if(r.cls){const k=document.createElement('i');k.className='key'+(r.dash?' dash':'');k.style.borderColor=`var(--${r.cls})`;n.appendChild(k);}n.appendChild(document.createTextNode(r.name));const b=document.createElement('b');b.textContent=r.val;row.appendChild(n);row.appendChild(b);tt.appendChild(row);}
  tt.style.display='block';const w=tt.offsetWidth,h=tt.offsetHeight;let left=x+14,top=y-h-10;if(left+w>innerWidth-8)left=x-w-14;if(top<8)top=y+14;tt.style.left=left+'px';tt.style.top=top+'px';}
const hide=()=>{tt.style.display='none';};
const money=v=>v>=1e6?'$'+(v/1e6).toFixed(1)+'M':(v>=1000?'$'+(v/1000).toFixed(0)+'k':'$'+v.toFixed(v<10?2:0));
const offSet=new Set(D.off);
const X0=yr(D.dates[0]), X1=yr(D.dates[D.dates.length-1]);

function offBands(svg, X, H, m){
  for(const [a,b] of D.episodes){const x1=X(yr(a)), x2=X(yr(b));el('rect',{x:x1-1,y:m.t,width:Math.max(2,x2-x1+2),height:H-m.t-m.b,fill:css('--wash')},svg);}
}
function xaxis(g, X, H, m, W){for(let y=2016;y<=2026;y+=(W<600?2:1)){const x=X(y);el('line',{x1:x,x2:x,y1:m.t,y2:H-m.b,stroke:css('--grid'),'stroke-width':1},g);txt(g,x,H-8,String(y),null,'middle');}}

function eqChart(){
  const svg=document.getElementById('eq'); svg.textContent='';
  const W=Math.max(320, svg.parentElement.clientWidth-32), narrow=W<600, H=340, m={l:52,r:narrow?62:150,t:12,b:26};
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const xs=D.dates.map(yr), X=v=>m.l+(v-X0)*(W-m.l-m.r)/(X1-X0);
  let lo=Infinity,hi=-Infinity;for(const [k] of SER)for(const v of D.curves[k]){lo=Math.min(lo,v);hi=Math.max(hi,v);}
  const Y=v=>m.t+(Math.log10(hi)-Math.log10(v))*(H-m.t-m.b)/(Math.log10(hi)-Math.log10(lo));
  offBands(svg,X,H,m);
  const g=el('g',{class:'axis'},svg); xaxis(g,X,H,m,W);
  for(const t of [0.5,1,3,10,30,100,300,1000,3000,10000]){if(t<lo||t>hi)continue;el('line',{x1:m.l,x2:W-m.r,y1:Y(t),y2:Y(t),stroke:css(t===1?'--axis':'--grid'),'stroke-width':1},g);txt(g,m.l-6,Y(t)+4,money(t),null,'end');}
  const n=xs.length;
  for(const [k,cls,dash] of SER.slice().reverse()){let p='';D.curves[k].forEach((v,i)=>p+=(i?'L':'M')+X(xs[i]).toFixed(1)+','+Y(v).toFixed(1));el('path',{d:p,fill:'none',stroke:`var(--${cls})`,'stroke-width':dash?1.6:2.2,'stroke-dasharray':dash?'5 4':'','stroke-linejoin':'round'},svg);}
  const labs=SER.filter(s=>!s[2]).map(([k,cls,,name])=>({k,cls,name,y:Y(D.curves[k][n-1])})).sort((a,b)=>a.y-b.y);
  for(let i=1;i<labs.length;i++)if(labs[i].y-labs[i-1].y<14)labs[i].y=labs[i-1].y+14;
  for(const L of labs){el('circle',{cx:X(xs[n-1]),cy:Y(D.curves[L.k][n-1]),r:4,fill:`var(--${L.cls})`,stroke:css('--surface'),'stroke-width':2},svg);txt(svg,X(xs[n-1])+8,L.y+4,narrow?money(D.curves[L.k][n-1]):`${L.name.replace(', Composer','')} ${money(D.curves[L.k][n-1])}`);}
  const cross=el('line',{y1:m.t,y2:H-m.b,stroke:css('--axis'),'stroke-width':1,visibility:'hidden'},svg);
  const hit=el('rect',{x:m.l,y:m.t,width:W-m.l-m.r,height:H-m.t-m.b,fill:'transparent',tabindex:0},svg);
  const idx=x=>{const v=X0+(x-m.l)*(X1-X0)/(W-m.l-m.r);let lo_=0,hi_=n-1;while(lo_<hi_){const mid=(lo_+hi_)>>1;if(xs[mid]<v)lo_=mid+1;else hi_=mid;}return lo_;};
  const move=(cx,cy,i)=>{cross.setAttribute('x1',X(xs[i]));cross.setAttribute('x2',X(xs[i]));cross.setAttribute('visibility','visible');
    showTT(cx,cy,D.dates[i]+(offSet.has(D.dates[i])?' (gate: cash)':''),SER.map(([k,cls,dash,name])=>({name,cls,dash,val:money(D.curves[k][i])})));};
  hit.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect();move(e.clientX,e.clientY,idx((e.clientX-r.left)*W/r.width));});
  hit.addEventListener('pointerleave',()=>{cross.setAttribute('visibility','hidden');hide();});
  let ki=n-1;const key=()=>{const r=svg.getBoundingClientRect();move(r.left+r.width*0.6,r.top+20,ki);};
  hit.addEventListener('focus',key);hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')ki=Math.max(0,ki-1);else if(e.key==='ArrowRight')ki=Math.min(n-1,ki+1);else return;e.preventDefault();key();});
  hit.addEventListener('blur',()=>{cross.setAttribute('visibility','hidden');hide();});
}

function spyChart(){
  const svg=document.getElementById('spy'); svg.textContent='';
  const W=Math.max(320, svg.parentElement.clientWidth-32), H=220, m={l:52,r:16,t:10,b:26};
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const xs=D.dates.map(yr), X=v=>m.l+(v-X0)*(W-m.l-m.r)/(X1-X0);
  const vals=D.spy.map(v=>v==null?null:v);
  let lo=-0.05, hi=0.05; for(const v of vals){if(v==null)continue;lo=Math.min(lo,v);hi=Math.max(hi,v);}
  lo=Math.floor(lo*20)/20; hi=Math.ceil(hi*20)/20;
  const Y=v=>m.t+(hi-v)*(H-m.t-m.b)/(hi-lo);
  el('rect',{x:m.l,y:Y(0),width:W-m.l-m.r,height:Y(lo)-Y(0),fill:css('--wash'),opacity:0.5},svg);
  const g=el('g',{class:'axis'},svg); xaxis(g,X,H,m,W);
  for(let t=lo;t<=hi+1e-9;t+=0.05){el('line',{x1:m.l,x2:W-m.r,y1:Y(t),y2:Y(t),stroke:css(Math.abs(t)<1e-9?'--axis':'--grid'),'stroke-width':1},g);txt(g,m.l-6,Y(t)+4,(t*100).toFixed(0)+'%',null,'end');}
  let p='';vals.forEach((v,i)=>{if(v==null)return;p+=(p?'L':'M')+X(xs[i]).toFixed(1)+','+Y(v).toFixed(1);});
  el('path',{d:p,fill:'none',stroke:`var(--b2)`,'stroke-width':1.4,'stroke-linejoin':'round'},svg);
  D.dates.forEach((d,i)=>{if(offSet.has(d)&&vals[i]!=null)el('circle',{cx:X(xs[i]),cy:Y(vals[i]),r:2.2,fill:`var(--s2)`},svg);});
}

function fill(){
  const live=D.live, dr=D.draft;
  document.getElementById('sub').textContent=`Saved in Composer as "${D.name}" (symphony ${D.id}, version ${D.version}, no capital). It is the live HG tree with one condition in front of each of its two trend-basket filters: SPY above its 200-day moving average keeps the basket, otherwise BIL. Composer's own backtest of the draft and of the live tree are compared with the gate lab's model over ${live.common_days.toLocaleString()} common days.`;
  const k=document.getElementById('kpis'); k.textContent='';
  const cs=dr.composer_stats, ls=live.composer_stats;
  const items=[[`${pct(ls.annualized_rate_of_return,false)} → ${pct(cs.annualized_rate_of_return,false)}`,'CAGR, live → draft (Composer backtest 2015-06 to 2026-10)'],
               [`${ls.sharpe_ratio.toFixed(2)} → ${cs.sharpe_ratio.toFixed(2)}`,`Sharpe (Composer's convention); max drawdown ${pct(ls.max_drawdown,false)} → ${pct(cs.max_drawdown,false)}`],
               [`${dr.corr.toFixed(4)}`,`correlation of Composer's draft with the model; same holding on ${dr.match['1'][0].toLocaleString()} of ${dr.match['1'][1].toLocaleString()} days`],
               [`${D.n_off} / ${D.n_off}`,`days in cash instead of a trend basket, Composer vs model (of ${D.trend_days.toLocaleString()} trend days)`]];
  for(const [b,s] of items){const d=document.createElement('div');d.className='kpi';const bb=document.createElement('b');bb.textContent=b;const ss=document.createElement('span');ss.textContent=s;d.appendChild(bb);d.appendChild(ss);k.appendChild(d);}
  const lg=document.getElementById('lg-eq'); lg.textContent='';
  for(const [,cls,dash,name] of SER){const s=document.createElement('span');const i=document.createElement('i');i.className='key'+(dash?' dash':'');i.style.borderColor=`var(--${cls})`;s.appendChild(i);s.appendChild(document.createTextNode(name));lg.appendChild(s);}
  const s2=document.createElement('span');const i2=document.createElement('i');i2.className='sw';s2.appendChild(i2);s2.appendChild(document.createTextNode('draft in cash'));lg.appendChild(s2);
  document.getElementById('gatesub').textContent=`Above zero the trend baskets are held at 3x; below zero (shaded) the draft holds BIL on the days it would otherwise hold a trend basket. Each dot is such a day: ${D.n_off} of them in ${D.episodes.length} stretches since 2015, the same days in Composer and in the model (a gate on unadjusted prices would give ${D.close_off}; Composer uses adjusted prices).`;
  const tb=document.getElementById('tbl'); tb.textContent='';
  const row=(lab,m,extra)=>{const tr=document.createElement('tr');const th=document.createElement('th');th.scope='row';th.textContent=lab;tr.appendChild(th);
    for(const v of [pct(m.cagr),m.sharpe.toFixed(2),pct(m.maxdd,false),...extra]){const td=document.createElement('td');td.textContent=v;tr.appendChild(td);}tb.appendChild(tr);};
  row('live HG, Composer backtest',live.composer,[live.corr.toFixed(4),(live.drift*100>=0?'+':'')+(live.drift*100).toFixed(2)+'% a year',`${live.match['1'][0].toLocaleString()} / ${live.match['1'][1].toLocaleString()}`]);
  row('live HG, model',live.model,['','','']);
  row('gated draft, Composer backtest',dr.composer,[dr.corr.toFixed(4),(dr.drift*100>=0?'+':'')+(dr.drift*100).toFixed(2)+'% a year',`${dr.match['1'][0].toLocaleString()} / ${dr.match['1'][1].toLocaleString()}`]);
  row('gated draft, model',dr.model,['','','']);
  document.getElementById('tblnote').textContent=`Sharpe here is in the house convention (daily excess over T-bills, annualised), computed from each equity curve on the common days; Composer's own Sharpe field reads ${live.composer_stats.sharpe_ratio.toFixed(2)} and ${dr.composer_stats.sharpe_ratio.toFixed(2)}. The two days the holdings differ (both trees) are 2017-05-10 and 2017-05-12, VIXY against UVXY in the long-vol filter, a near-tie in RSI.`;
  const notes=[`Built from the live tree (version bP4mvRy6) on 2026-10-18: 51 nodes became 63. The twelve new nodes are two copies of the gate; every original node keeps its id and settings. Dip-buys, the long-vol branch and the existing cash defaults are untouched.`,
    `The draft holds no money and nothing live has changed. Putting it live would mean replacing HG's tree with this one (same symphony, same capital; it applies at the next rebalance), as the July edits were done. That needs the owner's approval and has not been done.`,
    `The gate is open today (SPY above its 200-day average), so the swap itself would trade nothing.`,
    `Composer backtest: v2 engine, regulatory and TAF fees, 0.05% slippage, $10,000, from 2015-06-01 (Composer starts LABU's window functions on 2015-06-11). The +0.2% a year drift of Composer over the model is the same for the live tree and the draft: it is the engine, not the gate.`,
    `In sample: HG's rules were built on these years; add. 44 has the 1990-2026 picture.`];
  const ul=document.getElementById('notes'); ul.textContent='';for(const t of notes){const li=document.createElement('li');li.textContent=t;ul.appendChild(li);}
}
function draw(){fill();eqChart();spyChart();}
draw(); let rt; addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,120);});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    main()
