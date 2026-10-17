"""Render results/leverage-gate-2026-10-17.html from LEVGATE_DATA/levgate.json (self-contained page)."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from levgate import OUT, WINDOWS_B   # noqa: E402

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results', 'leverage-gate-2026-10-17.html')
FAMILY = [('A', 'constant blend'), ('T', 'trend'), ('V', 'realized vol'), ('E', 'own equity / own vol'), ('X', 'VIX'),
          ('L', 'per-leg vol'), ('R', 'literature shapes'), ('D', 'drawdown'), ('F', 'financing'), ('C', 'credit'), ('Y', 'curve'), ('K', 'CAPE')]


def fam(name):
    if name.endswith('-> cash'):
        return 'cash fallback'
    if name.startswith('vote') or '&' in name or '|' in name or name.startswith('VT16x') or name.startswith('VT20 floor'):
        return 'combination'
    if name.startswith('VT'):
        return 'vol target'
    for k, lab in FAMILY:
        if name.startswith(k):
            return lab
    return 'other'


def main():
    S = json.load(open(f'{OUT}/levgate.json'))
    B = S['panels']['B']['HG']
    A = S['panels']['A']
    # scatter: the sweep on every leveraged long, plus the trend-baskets-only version of each gate (dip-buys left levered)
    rowsB = {k: v for k, v in B['rows'].items() if '[' not in k or k.endswith('[trend only]')}
    pts = [{'name': k, 'fam': ('trend baskets only' if k.endswith('[trend only]') else fam(k)), 'allow': v['mean_allow'],
            **{m: v['full'][m] for m in ('cagr', 'sharpe', 'sortino', 'calmar', 'maxdd', 'worst_year', 'vol')}, 'to': v['turnover']}
           for k, v in rowsB.items() if v['full']]
    blends = [p for p in pts if p['fam'] == 'constant blend']
    blends.sort(key=lambda p: p['allow'])
    keep = B['series_keep']
    days = sorted(next(iter(keep.values())))
    curves = {}
    for k, r in keep.items():
        v, out = 1.0, []
        for d in days:
            v *= 1 + r.get(d, 0.0)
            out.append(round(v, 4))
        curves[k] = out
    # sample the curves weekly for the page (9k points x 11 series is heavy)
    idx = list(range(0, len(days), 5)) + ([len(days) - 1] if (len(days) - 1) % 5 else [])
    cdata = {'dates': [days[i] for i in idx], 'curves': {k: [c[i] for i in idx] for k, c in curves.items()}}
    nulls = {k: v['nulls'] for k, v in B['rows'].items() if v.get('nulls')}
    short = S['shortlist_B']

    def pct(x, sign=True):
        return ('n/a' if x is None else (f"{x * 100:+.1f}%" if sign else f"{x * 100:.1f}%"))

    def row(name, v, win=False):
        m = v['full']
        cells = f"<th scope=row>{name}</th><td>{v['mean_allow']:.2f}</td><td>{pct(m['cagr'])}</td><td>{m['sharpe']:.2f}</td><td>{m['sortino']:.2f}</td><td>{pct(m['maxdd'], False)}</td><td>{pct(m['worst_year'])}</td><td>{v['turnover']:.0f}</td>"
        if win:
            cells += ''.join(f"<td>{pct(v['windows'][w]['cagr'])} <span class=dim>{pct(v['windows'][w]['maxdd'], False)}</span></td>" for w in WINDOWS_B)
        return f"<tr class='{'hl' if name.startswith('A0') or name.startswith('A1 never levered') else ''}'>{cells}</tr>"

    win_names = ['A0 always levered (as built)'] + [n for n in short if n in B['rows']] + [n for n in B['rows'] if n.endswith('-> cash')] + ['A1 never levered']
    seen, win_rows = set(), []
    for n in win_names:
        if n not in seen and B['rows'][n].get('windows'):
            seen.add(n)
            win_rows.append(row(n, B['rows'][n], win=True))
    null_rows = ''.join(
        f"<tr><th scope=row>{n}</th><td>{pct(B['rows'][n]['full']['cagr'])} / {B['rows'][n]['full']['sharpe']:.2f} / {pct(B['rows'][n]['full']['maxdd'], False)}</td>"
        f"<td>{pct(v['inverse']['cagr'])} / {v['inverse']['sharpe']:.2f} / {pct(v['inverse']['maxdd'], False)}</td>"
        f"<td>{v['placebo_pct']['cagr']:.2f} / {v['placebo_pct']['sharpe']:.2f} / {v['placebo_pct']['dd_better']:.2f}</td>"
        f"<td>{v['sharpe_gap_ci90'][0]:+.2f} to {v['sharpe_gap_ci90'][1]:+.2f} (P {v['p_gap_gt0']:.2f})</td></tr>" for n, v in nulls.items())
    allB = ''.join(row(n, v) for n, v in B['rows'].items() if v['full'] and '[' not in n)
    allBt = ''.join(row(n, v) for n, v in B['rows'].items() if v['full'] and n.endswith('[trend only]'))
    appB = ''.join(row(n, v) for n, v in B['rows'].items() if v['full'] and ('[' in n and not n.endswith('[trend only]')))
    eng_rows = ''
    for e in ('HG', 'KMLM', 'SLEEVE', 'HARV'):
        if e not in A:
            continue
        R = A[e]['rows']
        for n in ('A0 always levered (as built)', 'A1 never levered', 'A3 fixed 1/2 (~2x)', 'T200 SPY>200d', 'T200h hysteresis +-2%', 'V20<25 SPY 20d vol',
                  'VT16 vol target 16% on SPY vol', 'ET40 vol target 40% on own vol', 'R4 inverse-leg panic (base DD>10% & vol pct>80)', 'T200 SPY>200d -> cash',
                  'A1 never levered [all legs]', 'T200 SPY>200d [all legs]', 'V20<25 SPY 20d vol [all legs]'):
            if n in R and R[n]['full']:
                m = R[n]['full']
                eng_rows += f"<tr><th scope=row>{e}: {n}</th><td>{R[n]['mean_allow']:.2f}</td><td>{pct(m['cagr'])}</td><td>{m['sharpe']:.2f}</td><td>{m['sortino']:.2f}</td><td>{pct(m['maxdd'], False)}</td><td>{pct(m['worst_year'])}</td></tr>"
    book = S.get('book_A', {}).get('rows', {})
    book_rows = ''.join(f"<tr><th scope=row>{k}</th><td>{pct(m['cagr'])}</td><td>{m['sharpe']:.2f}</td><td>{m['sortino']:.2f}</td><td>{pct(m['maxdd'], False)}</td><td>{pct(m['worst_year'])}</td></tr>" for k, m in book.items() if m)
    meta = {'B': f"{B['first']} to {B['last']}, {B['n_days']} sessions", 'A': (f"{A['HG']['first']} to {A['HG']['last']}" if 'HG' in A else ''),
            'bookwin': ' to '.join(S.get('book_A', {}).get('window', ['', '']))}
    html = (TEMPLATE.replace('__PTS__', json.dumps(pts)).replace('__BLENDS__', json.dumps(blends)).replace('__CURVES__', json.dumps(cdata))
            .replace('__WINROWS__', ''.join(win_rows)).replace('__NULLROWS__', null_rows).replace('__ALLB__', allB).replace('__ENG__', eng_rows)
            .replace('__BOOK__', book_rows).replace('__ALLBT__', allBt).replace('__APPB__', appB).replace('__META_B__', meta['B']).replace('__META_A__', meta['A']).replace('__BOOKWIN__', meta['bookwin'])
            .replace('__WINHEAD__', ''.join(f'<th>{w}</th>' for w in WINDOWS_B)))
    open(PAGE, 'w').write(html)
    print('wrote', os.path.normpath(PAGE))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leverage gate lab</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--b1:#898781;--b2:#52514e;--wash1:rgba(42,120,214,.10)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--b1:#898781;--b2:#c3c2b7;--wash1:rgba(57,135,229,.12)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--b1:#898781;--b2:#c3c2b7;--wash1:rgba(57,135,229,.12)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}
h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 12px;font-size:14px}
.lede{font-size:17px;margin:14px 0 18px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:0 0 16px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:820px){.grid2{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:5px 7px;text-align:right;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums;white-space:nowrap}
th[scope=row]{text-align:left;font-weight:500;white-space:normal}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}
tr.hl th,tr.hl td{font-weight:650}
.dim{color:var(--muted);font-size:12px}
.tablewrap{overflow-x:auto}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 4px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.key{display:inline-block;width:16px;height:2px;border-radius:1px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%}
svg{display:block;width:100%;height:auto;overflow:visible}
.tt{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:5;min-width:170px;max-width:320px}
.tt .d{color:var(--ink2);margin-bottom:4px}
.tt .r{display:flex;align-items:center;gap:8px;justify-content:space-between}
.tt .r b{font-variant-numeric:tabular-nums}
.tt .n{display:inline-flex;align-items:center;gap:6px;color:var(--ink2)}
.axis text{fill:var(--muted);font-size:11px}
.lbl{fill:var(--ink2);font-size:12px}
.notes{font-size:13.5px;color:var(--ink2)}
.notes li{margin:3px 0}
details summary{cursor:pointer;color:var(--ink2);font-size:14px}
</style>
</head>
<body>
<main class="viz-root">
<h1>Timing leverage on and off: the gate lab</h1>
<p class="sub-h">Same signals, same trades. On days a factor says risk-off, each leveraged long leg is held as its 1x version instead (TQQQ as QQQ, UDOW as DIA, and so on), or as a blend. HG on a 1990 to 2026 proxy panel (__META_B__; out of sample for HG's rules, synthetic legs before the ETFs exist), then all four engines on real tickers __META_A__. Costed at the engines' measured slippage, including the switching trades.</p>
<p class="lede" id="lede"></p>

<section class="card">
<h2>Every gate against the constant-blend line (HG, 1990 to 2026)</h2>
<p class="sub-h">The line joins fixed blends from never levered to always levered. A gate earns its keep only if it sits above and to the left of that line: more Sharpe, or less drawdown, than simply holding less leverage all the time. Blue, orange and grey dots gate every leveraged long leg; yellow dots gate only the five trend baskets and leave HG's oversold dip-buys at full leverage. Hover a dot for its name.</p>
<div class="legend" id="lg-sc"></div>
<div class="grid2">
<svg id="sc1" role="img" aria-label="Sharpe against maximum drawdown for every gate variant, with the constant-blend line"></svg>
<svg id="sc2" role="img" aria-label="Compound growth rate against maximum drawdown for every gate variant, with the constant-blend line"></svg>
</div>
</section>

<section class="card">
<h2>Growth of $1 (log scale) and drawdown, HG 1990 to 2026</h2>
<div class="legend" id="lg-eq"></div>
<svg id="eq" role="img" aria-label="Growth of one dollar on a log scale for the as-built engine, three gates and the never-levered version"></svg>
<svg id="dd" role="img" aria-label="Drawdown from peak for the same series"></svg>
</section>

<section class="card">
<h2>By market regime (CAGR per year, max drawdown in grey)</h2>
<div class="tablewrap"><table>
<thead><tr><th></th><th>allow</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Worst yr</th><th>TO/yr</th>__WINHEAD__</tr></thead>
<tbody>__WINROWS__</tbody></table></div>
</section>

<section class="card">
<h2>Nulls: inverse gate, re-dated placebos, paired bootstrap against as built</h2>
<p class="sub-h">Inverse = 1 minus the gate. Placebo = the gate's monthly allowance pattern randomly re-dated, 100 draws; the cells are the share of draws the real gate beats (CAGR / Sharpe / drawdown better). Bootstrap = 20-day paired blocks, 400 draws, Sharpe gap vs as built.</p>
<div class="tablewrap"><table>
<thead><tr><th>gate</th><th>real: CAGR / Sharpe / DD</th><th>inverse</th><th>placebo pct</th><th>Sharpe gap, 90% band</th></tr></thead>
<tbody>__NULLROWS__</tbody></table></div>
</section>

<section class="card">
<h2>All four engines, 2015 to 2026 (Composer-like simulator, in sample for KMLM, SLEEVE and HARV)</h2>
<p class="sub-h">Gates apply to the long trend legs unless marked [all legs]; the panic gate applies to the inverse legs only.</p>
<div class="tablewrap"><table>
<thead><tr><th></th><th>allow</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Worst yr</th></tr></thead>
<tbody>__ENG__</tbody></table></div>
</section>

<section class="card">
<h2>Book level, 29/29/27/15 with the 40% cap, __BOOKWIN__</h2>
<p class="sub-h">Which engines get the gate.</p>
<div class="tablewrap"><table>
<thead><tr><th></th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Worst yr</th></tr></thead>
<tbody>__BOOK__</tbody></table></div>
</section>

<section class="card">
<details><summary>Table view: every variant on every leveraged long, HG 1990 to 2026</summary>
<div class="tablewrap"><table>
<thead><tr><th></th><th>allow</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Worst yr</th><th>TO/yr</th></tr></thead>
<tbody>__ALLB__</tbody></table></div>
</details>
<details><summary>Table view: the same gates on the trend baskets only (dip-buys stay levered)</summary>
<div class="tablewrap"><table>
<thead><tr><th></th><th>allow</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Worst yr</th><th>TO/yr</th></tr></thead>
<tbody>__ALLBT__</tbody></table></div>
</details>
<details><summary>Table view: which legs the gate touches (dip-buys only, all legs, long-vol only)</summary>
<div class="tablewrap"><table>
<thead><tr><th></th><th>allow</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Worst yr</th><th>TO/yr</th></tr></thead>
<tbody>__APPB__</tbody></table></div>
</details>
</section>

<section class="card notes" id="notes">
<h2 style="color:var(--ink)">Basis and limits</h2>
<ul>
<li>allow = the share of the leveraged legs' weight that stayed leveraged, averaged over the window. TO/yr = total turnover including the leverage switches, costed at 5.1 bp per unit for HG.</li>
<li>Decisions are the engines' own; the gate only changes which share class of a leg is held. Signals are read at the prior close; Composer trades at 15:50, so live switches lag these by one session in the worst case.</li>
<li>Before 1999 the leveraged legs are index reconstructions (3x index minus financing, S&amp;P dividend yield accrued) and the 1x twins are the same indices; VIX funds are modelled. Out of sample for HG's rules, which were set on 2015 to 2026 data.</li>
<li>Fifty variants were examined and are all shown. The placebo and inverse tests are per variant; the best of fifty is expected to beat its own placebo even when nothing works, so read the family, not the top row.</li>
<li>Research pass only. Nothing here changes a live symphony.</li>
</ul>
</section>
</main>
<div class="tt" id="tt" role="status" aria-live="polite"></div>
<script>
const PTS = __PTS__, BLENDS = __BLENDS__, C = __CURVES__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tt = document.getElementById('tt');
const pct = (x, s=true) => (s && x >= 0 ? '+' : '') + (x*100).toFixed(1) + '%';
function el(tag, attrs, parent){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e;}
function showTT(x, y, title, rows){tt.textContent='';const d=document.createElement('div');d.className='d';d.textContent=title;tt.appendChild(d);
  for(const r of rows){const row=document.createElement('div');row.className='r';const n=document.createElement('span');n.className='n';if(r.cls){const k=document.createElement('i');k.className='key';k.style.background=`var(--${r.cls})`;n.appendChild(k);}n.appendChild(document.createTextNode(r.name));const b=document.createElement('b');b.textContent=r.val;row.appendChild(n);row.appendChild(b);tt.appendChild(row);}
  tt.style.display='block';const w=tt.offsetWidth,h=tt.offsetHeight;let left=x+14,top=y-h-10;if(left+w>innerWidth-8)left=x-w-14;if(top<8)top=y+14;tt.style.left=left+'px';tt.style.top=top+'px';}
function hideTT(){tt.style.display='none';}
const FAMCLS = {'trend':'s1','realized vol':'s2','vol target':'s2','cash fallback':'s3','trend baskets only':'s4','constant blend':'b2'};
const famCls = f => FAMCLS[f] || 'b1';
function legendDots(id, items){const lg=document.getElementById(id);lg.textContent='';for(const [name,cls,line] of items){const s=document.createElement('span');const k=document.createElement('i');k.className=line?'key':'dot';k.style.background=`var(--${cls})`;s.appendChild(k);s.appendChild(document.createTextNode(name));lg.appendChild(s);}}

function scatter(id, ykey, ylab, yfmt){
  const svg=document.getElementById(id); svg.textContent='';
  const W=Math.max(300, svg.parentElement.clientWidth/ (innerWidth>820?2:1) - 24), H=320, m={l:46,r:14,t:10,b:30};
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const xs_=PTS.map(p=>p.maxdd), ys_=PTS.map(p=>p[ykey]);
  const x0=Math.floor(Math.min(...xs_)*10)/10-0.05, x1=Math.ceil(Math.max(...xs_)*10)/10;
  const y0=Math.floor(Math.min(...ys_)*10)/10, y1=Math.ceil(Math.max(...ys_)*10)/10;
  const X=v=>m.l+(v-x0)*(W-m.l-m.r)/(x1-x0), Y=v=>m.t+(y1-v)*(H-m.t-m.b)/(y1-y0);
  const g=el('g',{class:'axis'},svg);
  for(let v=y0; v<=y1+1e-9; v+=(y1-y0)/4){el('line',{x1:m.l,x2:W-m.r,y1:Y(v),y2:Y(v),stroke:css('--grid'),'stroke-width':1},g);const t=el('text',{x:m.l-6,y:Y(v)+4,'text-anchor':'end'},g);t.textContent=yfmt(v);}
  for(let v=Math.ceil(x0*10)/10; v<=x1+1e-9; v+=0.1){const t=el('text',{x:X(v),y:H-10,'text-anchor':'middle'},g);t.textContent=(v*100).toFixed(0)+'%';}
  const xl=el('text',{x:(m.l+W-m.r)/2,y:H+2,'text-anchor':'middle',class:'lbl'},svg); xl.textContent='max drawdown (left is better)';
  const yl=el('text',{x:m.l,y:m.t-1,class:'lbl'},svg); yl.textContent=ylab;
  let p='';BLENDS.forEach((b,i)=>p+=(i?'L':'M')+X(b.maxdd).toFixed(1)+','+Y(b[ykey]).toFixed(1));
  el('path',{d:p,fill:'none',stroke:css('--b2'),'stroke-width':1.5,'stroke-linejoin':'round'},svg);
  const order=['other','drawdown','financing','credit','curve','CAPE','per-leg vol','own equity / own vol','VIX','combination','literature shapes','realized vol','vol target','trend','trend baskets only','cash fallback','constant blend'];
  const sorted=PTS.slice().sort((a,b)=>order.indexOf(a.fam)-order.indexOf(b.fam));
  for(const q of sorted){
    const isB=q.fam==='constant blend';
    const c=el('circle',{cx:X(q.maxdd),cy:Y(q[ykey]),r:isB?5:4.5,fill:`var(--${famCls(q.fam)})`,stroke:css('--surface'),'stroke-width':2,tabindex:0},svg);
    const hit=el('circle',{cx:X(q.maxdd),cy:Y(q[ykey]),r:12,fill:'transparent'},svg);
    const show=(x,y)=>{c.setAttribute('r',7);showTT(x,y,q.name,[{name:'CAGR',val:pct(q.cagr)},{name:'Sharpe',val:q.sharpe.toFixed(2)},{name:'Sortino',val:q.sortino.toFixed(2)},{name:'max DD',val:pct(q.maxdd,false)},{name:'worst year',val:pct(q.worst_year)},{name:'allow',val:q.allow.toFixed(2)},{name:'family',val:q.fam}]);};
    const hide=()=>{c.setAttribute('r',isB?5:4.5);hideTT();};
    hit.addEventListener('pointermove',e=>show(e.clientX,e.clientY));hit.addEventListener('pointerleave',hide);
    c.addEventListener('focus',()=>{const b=c.getBoundingClientRect();show(b.right,b.top);});c.addEventListener('blur',hide);
  }
  for(const q of PTS){ const short={'A0 always levered (as built)':'as built','A1 never levered':'never levered','T200h hysteresis +-2%':'200d band, all longs','VT16 vol target 16% on SPY vol':'vol target 16%','T200 SPY>200d -> cash':'200d, to cash, all longs','T200h hysteresis +-2% [trend only]':'200d band, trend only','A1 never levered [trend only]':'trend baskets at 1x'}[q.name]; if(short){
    const t=el('text',{x:X(q.maxdd)+8,y:Y(q[ykey])-7,class:'lbl'},svg);t.textContent=short;}}
}

function lineChart(id, keys, opts){
  const svg=document.getElementById(id); svg.textContent='';
  const W=Math.max(320, svg.parentElement.clientWidth-32), H=opts.h, m={l:52,r:120,t:10,b:26};
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const n=C.dates.length, xs=i=>m.l+i*(W-m.l-m.r)/(n-1);
  const series=keys.map(k=>({k, name:opts.names[k], cls:opts.cls[k], v:opts.dd?(()=>{let pk=-1;return C.curves[k].map(v=>{pk=Math.max(pk,v);return v/pk-1;});})():C.curves[k]}));
  let lo=Infinity,hi=-Infinity; for(const s of series)for(const v of s.v){lo=Math.min(lo,v);hi=Math.max(hi,v);}
  const tr=opts.log?Math.log10:(v=>v), ys=v=>m.t+(tr(hi)-tr(v))*(H-m.t-m.b)/(tr(hi)-tr(lo));
  const g=el('g',{class:'axis'},svg);
  const ticks=opts.ticks(lo,hi);
  for(const t of ticks){if(t<lo||t>hi)continue;el('line',{x1:m.l,x2:W-m.r,y1:ys(t),y2:ys(t),stroke:css(t===opts.base?'--axis':'--grid'),'stroke-width':1},g);const tx=el('text',{x:m.l-6,y:ys(t)+4,'text-anchor':'end'},g);tx.textContent=opts.fmt(t);}
  let last='';C.dates.forEach((d,i)=>{const y=d.slice(0,4);if(y!==last&&(+y)%(innerWidth>820?3:6)===0){last=y;const tx=el('text',{x:xs(i),y:H-8,'text-anchor':'middle'},g);tx.textContent=y;}else if(y!==last)last=y;});
  for(const s of series.slice().reverse()){let p='';s.v.forEach((v,i)=>p+=(i?'L':'M')+xs(i).toFixed(1)+','+ys(v).toFixed(1));el('path',{d:p,fill:'none',stroke:`var(--${s.cls})`,'stroke-width':s.cls==='b1'?1.5:2,'stroke-linejoin':'round','stroke-linecap':'round'},svg);}
  const labs=series.map(s=>({s,y:ys(s.v[n-1])})).sort((a,b)=>a.y-b.y);
  for(let i=1;i<labs.length;i++)if(labs[i].y-labs[i-1].y<14)labs[i].y=labs[i-1].y+14;
  for(const L of labs){el('circle',{cx:xs(n-1),cy:ys(L.s.v[n-1]),r:4,fill:`var(--${L.s.cls})`,stroke:css('--surface'),'stroke-width':2},svg);const tx=el('text',{x:xs(n-1)+8,y:L.y+4,class:'lbl'},svg);tx.textContent=`${L.s.name} ${opts.endfmt(L.s.v[n-1])}`;}
  const cross=el('line',{y1:m.t,y2:H-m.b,stroke:css('--axis'),'stroke-width':1,visibility:'hidden'},svg);
  const hit=el('rect',{x:m.l,y:m.t,width:W-m.l-m.r,height:H-m.t-m.b,fill:'transparent',tabindex:0},svg);
  const move=(cx,cy,i)=>{cross.setAttribute('x1',xs(i));cross.setAttribute('x2',xs(i));cross.setAttribute('visibility','visible');showTT(cx,cy,C.dates[i],series.map(s=>({name:s.name,cls:s.cls,val:opts.ttfmt(s.v[i])})));};
  hit.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect();const x=(e.clientX-r.left)*W/r.width;const i=Math.max(0,Math.min(n-1,Math.round((x-m.l)*(n-1)/(W-m.l-m.r))));move(e.clientX,e.clientY,i);});
  hit.addEventListener('pointerleave',()=>{cross.setAttribute('visibility','hidden');hideTT();});
  let ki=n-1;hit.addEventListener('focus',()=>{const r=svg.getBoundingClientRect();move(r.left+r.width*0.6,r.top+20,ki);});
  hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')ki=Math.max(0,ki-1);else if(e.key==='ArrowRight')ki=Math.min(n-1,ki+1);else return;e.preventDefault();const r=svg.getBoundingClientRect();move(r.left+r.width*0.6,r.top+20,ki);});
  hit.addEventListener('blur',()=>{cross.setAttribute('visibility','hidden');hideTT();});
}

function draw(){
  legendDots('lg-sc',[['trend gates','s1'],['realized-vol and vol-target gates','s2'],['same gate, cash instead of 1x','s3'],['gate on the trend baskets only','s4'],['other factors','b1'],['constant blends (line)','b2',true]]);
  scatter('sc1','sharpe','Sharpe',v=>v.toFixed(2)); scatter('sc2','cagr','CAGR',v=>(v*100).toFixed(0)+'%');
  const names={'A0 always levered (as built)':'as built','A1 never levered':'never levered','T200h hysteresis +-2%':'200d band, all longs','T200h hysteresis +-2% [trend only]':'200d band, trend only','VT16 vol target 16% on SPY vol':'vol target 16%','T200 SPY>200d -> cash [trend only]':'200d to cash, trend only'};
  const cls={'A0 always levered (as built)':'b2','A1 never levered':'b1','T200h hysteresis +-2%':'s1','T200h hysteresis +-2% [trend only]':'s4','VT16 vol target 16% on SPY vol':'s2','T200 SPY>200d -> cash [trend only]':'s3'};
  const keys=Object.keys(names).filter(k=>C.curves[k]);
  legendDots('lg-eq',keys.map(k=>[names[k],cls[k],true]));
  lineChart('eq',keys,{h:340,log:true,names,cls,base:1,ticks:(lo,hi)=>[1,10,100,1000,10000,100000,1e6,1e7].filter(t=>t>=lo/2&&t<=hi*2),fmt:v=>'$'+(v>=1000?(v/1000).toFixed(0)+'k':v.toFixed(0)),endfmt:v=>'$'+(v>=1000?(v/1000).toFixed(0)+'k':v.toFixed(0)),ttfmt:v=>'$'+(v>=1000?(v/1000).toFixed(1)+'k':v.toFixed(2))});
  lineChart('dd',keys,{h:230,dd:true,names,cls,base:0,ticks:(lo,hi)=>[0,-0.2,-0.4,-0.6,-0.8],fmt:v=>(v*100).toFixed(0)+'%',endfmt:v=>(v*100).toFixed(0)+'%',ttfmt:v=>(v*100).toFixed(1)+'%'});
  const byName=Object.fromEntries(PTS.map(p=>[p.name,p]));
  const a0=byName['A0 always levered (as built)'], a1=byName['A1 never levered'], th=byName['T200h hysteresis +-2%'], tt_=byName['T200h hysteresis +-2% [trend only]'], tc=byName['T200 SPY>200d -> cash [trend only]'], dip=byName['A1 never levered [dip only]'];
  const L=document.getElementById('lede');
  if(a0&&a1&&th&&tt_){L.textContent=`Over 36 years, as built HG compounds at ${pct(a0.cagr)} with a ${pct(a0.maxdd,false)} worst drawdown and Sharpe ${a0.sharpe.toFixed(2)}; never levered, ${pct(a1.cagr)}, ${pct(a1.maxdd,false)} and ${a1.sharpe.toFixed(2)}. Where the gate is applied matters more than which factor drives it. Gating only the five trend baskets below the 200-day average (dip-buys left at 3x) gives ${pct(tt_.cagr)}, ${pct(tt_.maxdd,false)} and ${tt_.sharpe.toFixed(2)}: more return and more Sharpe than as built, confirmed against inverse, placebo and bootstrap. Gating every leveraged long with the same signal gives ${pct(th.cagr)}, ${pct(th.maxdd,false)} and ${th.sharpe.toFixed(2)}: the biggest drawdown cut, paid for in the bull years.`+(dip?` De-levering only the dip-buys is the one thing that hurts everywhere (${pct(dip.cagr)}, ${pct(dip.maxdd,false)}, ${dip.sharpe.toFixed(2)}).`:'')+(tc?` Cash instead of 1x below the 200-day (addendum 40's gate) is ${pct(tc.cagr)}, ${pct(tc.maxdd,false)}, ${tc.sharpe.toFixed(2)}: better in the two long bears, worse since 2015, a tie over the whole history.`:'');}
}
draw(); let rt; addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,120);});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    main()
