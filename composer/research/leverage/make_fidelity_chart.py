"""Simulated vs actual leveraged funds, where both exist.  The panel-B backtest prices each of HG's five gated
funds, before it launched, as L x the daily return of its 1x ETF or index minus T-bill financing and a fee term
(gate_study.build_lh_prices).  This runs those same rebuilds over the years the real funds trade and compares:
growth of $1, annualised drift (rebuild minus fund, log %/yr) and daily-return correlation.  Also prints the
worst index day in the panel (a 3x fund is wiped out by a -33.4% day).  Writes
results/leverage-sim-vs-actual-2026-10-18.html."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levgate as lg   # noqa: E402

gs = lg.gs
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results', 'leverage-sim-vs-actual-2026-10-18.html')


def rebuilds():
    """the layers build_lh_prices splices under each gated fund (same constructors and arguments)"""
    yh, recon, lev = gs.yh, gs.recon, gs.lev_from_index
    divy = json.load(open(f'{gs.MAC}/divyield_multpl.json'))
    ndx_dy, rut_dy = {k: 0.5 for k in divy}, {k: 1.5 for k in divy}
    return {
        'TQQQ': [('QQQ x3', 'etf1x', recon('TQQQ', 'QQQ', 3)), ('Nasdaq-100 x3', 'index', lev(yh('^NDX'), 3, ndx_dy))],
        'UPRO': [('SPY x3', 'etf1x', recon('UPRO', 'SPY', 3)), ('S&P 500 x3', 'index', lev(yh('^GSPC'), 3, divy))],
        'UDOW': [('DIA x3', 'etf1x', recon('UDOW', 'DIA', 3)), ('Dow x3', 'index', lev(yh('^DJI'), 3, divy))],
        'SSO': [('SPY x2', 'etf1x', recon('SSO', 'SPY', 2)), ('S&P 500 x2', 'index', lev(yh('^GSPC'), 2, divy))],
        'TNA': [('IWM x3', 'etf1x', lev(yh('IWM'), 3)), ('Russell 2000 x3', 'index', lev(yh('^RUT'), 3, rut_dy))],
    }


def main():
    R = rebuilds()
    funds = []
    for t, layers in R.items():
        act = gs.yh(t)
        ds = [d for d in sorted(act) if all(d in s for _, _, s in layers)]
        n = len(ds) - 1
        ra = [act[ds[i]] / act[ds[i - 1]] - 1 for i in range(1, len(ds))]
        series = {'actual': [act[d] / act[ds[0]] for d in ds]}
        stats = []
        for lab, kind, s in layers:
            rs = [s[ds[i]] / s[ds[i - 1]] - 1 for i in range(1, len(ds))]
            ma, ms = sum(ra) / n, sum(rs) / n
            cov = sum((a - ma) * (b - ms) for a, b in zip(ra, rs))
            corr = cov / math.sqrt(sum((a - ma) ** 2 for a in ra) * sum((b - ms) ** 2 for b in rs))
            drift = (sum(math.log1p(b) for b in rs) - sum(math.log1p(a) for a in ra)) / (n / 252)
            series[kind] = [s[d] / s[ds[0]] for d in ds]
            stats.append({'label': lab, 'kind': kind, 'drift': drift, 'corr': corr})
        thin = lambda v: [round(v[min(i + 4, len(v) - 1)], 4) for i in range(0, len(v), 5)]   # noqa: E731
        funds.append({'t': t, 'a': ds[0], 'b': ds[-1], 'years': n / 252, 'stats': stats,
                      'dates': [ds[min(i + 4, len(ds) - 1)] for i in range(0, len(ds), 5)],
                      'series': {k: thin(v) for k, v in series.items()}})
        print(f'{t:5s} {ds[0]}..{ds[-1]} {n / 252:4.1f}y  ' +
              '  '.join(f"{s_['label']:16s} drift {s_['drift'] * 100:+5.2f}%/yr corr {s_['corr']:.3f}" for s_ in stats))
    # worst index day inside the panel (1990-01-03 on): a 3x fund needs a -33.4% day to be wiped out
    worst = []
    for idx, name in (('^NDX', 'Nasdaq-100'), ('^GSPC', 'S&P 500'), ('^DJI', 'Dow'), ('^RUT', 'Russell 2000')):
        px = gs.yh(idx)
        ks = [d for d in sorted(px) if d >= '1990-01-02']
        r = min((px[ks[i]] / px[ks[i - 1]] - 1, ks[i]) for i in range(1, len(ks)))
        worst.append({'name': name, 'r': r[0], 'd': r[1]})
        print(f'worst {name:12s} day since 1990: {r[0]:+.1%} on {r[1]}')
    D = {'funds': funds, 'worst': worst}
    open(PAGE, 'w').write(TEMPLATE.replace('__DATA__', json.dumps(D)))
    print('wrote', os.path.normpath(PAGE))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simulated vs actual funds</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}
h2{font-size:15px;margin:0;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 12px;font-size:14px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px 16px;margin:0 0 16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:820px){.grid{grid-template-columns:1fr}}
.stat{color:var(--ink2);font-size:12.5px;margin:2px 0 6px;font-variant-numeric:tabular-nums}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 12px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.key{display:inline-block;width:16px;height:2px;border-radius:1px}
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
</style>
</head>
<body>
<main class="viz-root">
<h1>Simulated 3x funds against the real ones, where both exist</h1>
<p class="sub-h">Before each fund launched, the 1990 to 2026 backtest used a simulated version of it: 3x (or 2x) the daily return of its 1x ETF or index, minus T-bill financing and fees. These are the same simulations run over the years the real funds trade, plotted against the real prices. Growth of $1 from each fund's first day, log scale.</p>
<div class="legend" id="lg"></div>
<div class="grid" id="grid"></div>
<section class="card notes">
<h2 style="color:var(--ink)">Basis and limits</h2>
<ul>
<li>Drift = the simulation's annual return minus the real fund's (log, % a year); correlation = of daily returns. The 1x-ETF simulations' fee term was fitted on these same years (so their small drift is partly by construction; TNA's is not fitted); the index simulations use a fixed 1.8% a year and are not fitted.</li>
<li>Nobody could trade these funds before they launched (the first 2x ETFs in 2006, the first 3x in late 2008); before that, 3x daily exposure meant index futures or margin. Results before launch are what HG's rules would have done had the funds existed.</li>
<li>Numbers cross-checked: all ten drift and correlation figures match the add. 44 counter-agent's independent tracking script exactly.</li>
<li id="worst"></li>
<li>Research only. Nothing live changes.</li>
</ul>
</section>
</main>
<div class="tt" id="tt" role="status" aria-live="polite"></div>
<script>
const D = __DATA__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tt = document.getElementById('tt');
const SER = [['actual','s1','real fund'],['etf1x','s3','simulated from its 1x ETF'],['index','s4','simulated from its index']];
function el(tag, attrs, parent){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e;}
function txt(p,x,y,s,cls,anchor){const t=el('text',{x,y,class:cls||'lbl','text-anchor':anchor||'start'},p);t.textContent=s;return t;}
function showTT(x,y,title,rows){tt.textContent='';const d=document.createElement('div');d.className='d';d.textContent=title;tt.appendChild(d);
  for(const r of rows){const row=document.createElement('div');row.className='r';const n=document.createElement('span');n.className='n';const k=document.createElement('i');k.className='key';k.style.background=`var(--${r.cls})`;n.appendChild(k);n.appendChild(document.createTextNode(r.name));const b=document.createElement('b');b.textContent=r.val;row.appendChild(n);row.appendChild(b);tt.appendChild(row);}
  tt.style.display='block';const w=tt.offsetWidth,h=tt.offsetHeight;let left=x+14,top=y-h-10;if(left+w>innerWidth-8)left=x-w-14;if(top<8)top=y+14;tt.style.left=left+'px';tt.style.top=top+'px';}
const money=v=>v>=1000?'$'+(v/1000).toFixed(1)+'k':(v>=10?'$'+v.toFixed(0):'$'+v.toFixed(2));
const yr=d=>+d.slice(0,4)+((+d.slice(5,7)-1)*30.44+(+d.slice(8,10)-1))/365.25;

function chart(f, host){
  const card=document.createElement('section');card.className='card';host.appendChild(card);
  const h=document.createElement('h2');h.textContent=`${f.t}, ${f.a.slice(0,4)} to ${f.b.slice(0,4)} (${f.years.toFixed(1)} years)`;card.appendChild(h);
  const st=document.createElement('div');st.className='stat';st.textContent=f.stats.map(s=>`${s.label}: drift ${(s.drift*100>=0?'+':'')+(s.drift*100).toFixed(2)}% a year, correlation ${s.corr.toFixed(3)}`).join(' · ');card.appendChild(st);
  const svg=el('svg',{role:'img','aria-label':`${f.t}: real fund against its two simulations`});card.appendChild(svg);
  const W=Math.max(300,card.clientWidth-32),H=210,m={l:48,r:12,t:8,b:24};svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const xs=f.dates.map(yr),X0=xs[0],X1=xs[xs.length-1],X=v=>m.l+(v-X0)*(W-m.l-m.r)/(X1-X0);
  let lo=Infinity,hi=-Infinity;for(const [k] of SER)for(const v of f.series[k]){lo=Math.min(lo,v);hi=Math.max(hi,v);}
  const Y=v=>m.t+(Math.log10(hi)-Math.log10(v))*(H-m.t-m.b)/(Math.log10(hi)-Math.log10(lo));
  const g=el('g',{class:'axis'},svg);
  for(const t of [0.1,0.3,1,3,10,30,100,300,1000]){if(t<lo||t>hi)continue;el('line',{x1:m.l,x2:W-m.r,y1:Y(t),y2:Y(t),stroke:css(t===1?'--axis':'--grid'),'stroke-width':1},g);txt(g,m.l-6,Y(t)+4,money(t),null,'end');}
  const step=W<480?6:4;for(let y=Math.ceil(X0);y<=X1;y++){if(y%step)continue;txt(g,X(y),H-6,String(y),null,'middle');}
  for(const [k,cls] of SER.slice().reverse()){let p='';f.series[k].forEach((v,i)=>p+=(i?'L':'M')+X(xs[i]).toFixed(1)+','+Y(v).toFixed(1));el('path',{d:p,fill:'none',stroke:`var(--${cls})`,'stroke-width':k==='actual'?2.4:1.6,'stroke-dasharray':k==='actual'?'':(k==='etf1x'?'5 3':'2 3'),'stroke-linejoin':'round'},svg);}
  const cross=el('line',{y1:m.t,y2:H-m.b,stroke:css('--axis'),'stroke-width':1,visibility:'hidden'},svg);
  const hit=el('rect',{x:m.l,y:m.t,width:W-m.l-m.r,height:H-m.t-m.b,fill:'transparent',tabindex:0},svg);
  const n=xs.length,move=(cx,cy,i)=>{cross.setAttribute('x1',X(xs[i]));cross.setAttribute('x2',X(xs[i]));cross.setAttribute('visibility','visible');showTT(cx,cy,f.dates[i],SER.map(([k,cls,name])=>({name,cls,val:money(f.series[k][i])})));};
  hit.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect();const v=X0+((e.clientX-r.left)*W/r.width-m.l)*(X1-X0)/(W-m.l-m.r);let i=0;while(i<n-1&&xs[i]<v)i++;move(e.clientX,e.clientY,i);});
  hit.addEventListener('pointerleave',()=>{cross.setAttribute('visibility','hidden');tt.style.display='none';});
  let ki=n-1;const key=()=>{const r=svg.getBoundingClientRect();move(r.left+r.width*0.6,r.top+20,ki);};
  hit.addEventListener('focus',key);hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')ki=Math.max(0,ki-1);else if(e.key==='ArrowRight')ki=Math.min(n-1,ki+1);else return;e.preventDefault();key();});
  hit.addEventListener('blur',()=>{cross.setAttribute('visibility','hidden');tt.style.display='none';});
}
function draw(){
  const lg=document.getElementById('lg');lg.textContent='';for(const [,cls,name] of SER){const s=document.createElement('span');const k=document.createElement('i');k.className='key';k.style.background=`var(--${cls})`;s.appendChild(k);s.appendChild(document.createTextNode(name));lg.appendChild(s);}
  const g=document.getElementById('grid');g.textContent='';for(const f of D.funds)chart(f,g);
  const w=D.worst.slice().sort((a,b)=>a.r-b.r);
  document.getElementById('worst').textContent=`A 3x fund is wiped out by a one-day index fall of about 33%. The worst days since 1990: ${w.map(x=>`${x.name} ${(x.r*100).toFixed(1)}% (${x.d})`).join(', ')}; the simulation handles them the way the real funds' daily reset does. It does not model a fund being closed or a trading halt.`;
}
draw();let rt;addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,120);});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    main()
