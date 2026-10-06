"""Chart for add. 38 (final): per-engine cumulative live vs model(primary) vs
model(all-stripped) with ex-dates marked, and cumulative gap OLD vs NEW per
engine, plus the Op2 sleeve read from 2026-08-01 (--start).

Data: ONLY the frozen 2026-10-05 repo fixtures
(composer/scripts/tests/fixtures/divergence-{panel,yahoo}-2026-10-05.json)
through divergence.analyze_series. Every number is then cross-checked against
the committed results JSONs (divergence-2026-10-05-distaware.json, full
window; divergence-2026-10-05-sleeve-from-0801.json) and the script exits
non-zero on any mismatch, so the chart cannot drift from the results.

Output: composer/results/divergence-distribution-fix-2026-10-05.html
(self-contained, inline JS/SVG, no CDN). Run from anywhere:
  python3 composer/research/divergence/make_fix_chart.py"""
import json, sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'composer', 'scripts'))
import divergence as dv

FIX = os.path.join(ROOT, 'composer', 'scripts', 'tests', 'fixtures')
RES = os.path.join(ROOT, 'composer', 'results')
with open(os.path.join(FIX, 'divergence-panel-2026-10-05.json')) as f:
    P = json.load(f)
with open(os.path.join(FIX, 'divergence-yahoo-2026-10-05.json')) as f:
    Y = json.load(f)
D = {t: dv.dists_from_chart(c) for t, c in Y.items()}
ORDER = ['HG', 'KMLM', 'SLEEVE', 'HARV']
OP2_START = '2026-08-01'


def run(e, start=None, end=None):
    v = P[e]
    ld, lv, raw, md, mv = v['dates'], v['adj'], v['raw'], v['model_dates'], v['model']
    if end is not None:
        k, j = ld.index(end) + 1, md.index(end) + 1
        ld, lv, raw, md, mv = ld[:k], lv[:k], raw[:k], md[:j], mv[:j]
    return dv.analyze_series(ld, lv, md, mv, v['weights'], D, live_raw=raw, symphony=e,
                             name=e, detail=True, start=start)


R = {e: run(e) for e in ORDER}
S0801 = run('SLEEVE', start=OP2_START)
# the superseded boundary (base 08-03, first return 08-04) = start one
# trading day later; shown only as the before/after comparison
S_OLD = run('SLEEVE', start='2026-08-04')
assert S_OLD['window'][0] == '2026-08-03'
PRE = {e: run(e, start=OP2_START) for e in ('HARV', 'KMLM')}
PEND = {end: run('HARV', end=end) for end in ('2026-09-01', '2026-09-02')}

# ---- cross-check against the committed results JSONs (same fixtures, the
#      mocked analyze() path); any mismatch is a hard failure
SYM = {'HG': 'mbkiXcuNDjueXpiox5Av', 'HARV': 'ORQNCfZnA18wmsMWVhf8',
       'KMLM': 'YPTSJFJwD2ZKfAeYJUbW', 'SLEEVE': 'nNdBk7hc5NiBzeRvbI5T'}
SKIP = {'symphony', 'name', 'daily'}
with open(os.path.join(RES, 'divergence-2026-10-05-distaware.json')) as f:
    J = {r['symphony']: r for r in json.load(f)['results']}
with open(os.path.join(RES, 'divergence-2026-10-05-sleeve-from-0801.json')) as f:
    JS = json.load(f)['results'][0]
_bad = []
for e in ORDER:
    _bad += [(e, k) for k in R[e] if k not in SKIP
             and json.loads(json.dumps(R[e][k])) != J[SYM[e]].get(k)]
_bad += [('SLEEVE-0801', k) for k in S0801 if k not in SKIP
         and json.loads(json.dumps(S0801[k])) != JS.get(k)]
if _bad:
    raise SystemExit(f'chart numbers != results JSON: {_bad[:10]}')

def cum(days, key):
    out, f = [100.0], 1.0
    for d in days:
        f *= 1 + d[key]
        out.append(round(100 * f, 4))
    return out

data = {}
for e in ORDER:
    r = R[e]
    days = r['daily']
    dates = [r['window'][0]] + [d['date'] for d in days]
    data[e] = {
        'dates': dates,
        'live': cum(days, 'live_ret'),
        'model_tr': cum(days, 'model_ret_total_return'),
        'model_primary': cum(days, 'model_ret'),
        'model_px': cum(days, 'model_ret_price_only'),
        'gap_old': [round(d['gap_bps_total_return_basis'], 2) for d in days],
        'gap_new': [round(d['gap_bps'], 2) for d in days],
        'ledger': [{'date': x['date'], 'ticker': x['ticker'], 'treatment': x['treatment'],
                    'term_bps': round(x['term_bps'], 1), 'weight': round(x['weight'], 3),
                    'income': x['expected_income_usd']} for x in r['distribution_ledger']],
        'stats': {
            'cum_gap_old': r['cumulative_gap_total_return_basis'],
            'cum_gap_new': r['cumulative_gap'],
            'corr_old': r['daily_return_correlation_total_return_basis'],
            'corr_new': r['daily_return_correlation'],
            'beta': r['live_beta_to_model'], 'volr': r['live_model_vol_ratio'],
            'maxdd': r['live_max_drawdown'],
            'ann_old': r['annualized_gap_total_return_basis'],
            'ann_new': r['annualized_gap'],
            'ann_allx': r['annualized_gap_all_exdates_stripped'],
            'income': r['distribution_totals']['expected_income_usd'],
            'leaked_usd': round(sum(x['expected_income_usd'] or 0 for x in r['distribution_ledger']
                                    if x['treatment'] == 'LEAKED'), 2),
            'n_leaked': r['distribution_totals']['n_leaked'],
            'n_held': r['distribution_totals']['n_held_through'],
            'worst': r['worst_daily_gap_bps'], 'worst_date': r['worst_daily_gap_date'],
            'window': r['window'], 'n_days': r['n_days'],
            'n_trading_days': r['n_trading_days'],
            'live_cum': r['live_cumulative_return'],
            'model_cum_tr': r['model_total_return_cumulative'],
            'model_cum_new': r['model_cumulative_return'],
            'model_cum_px': r['model_cumulative_return_all_exdates_stripped'],
        }}

# Op2 panel: the sleeve from its base close (07-31), live vs model (primary)
_d = S0801['daily']
data['OP2'] = {
    'dates': [S0801['window'][0]] + [x['date'] for x in _d],
    'live': cum(_d, 'live_ret'), 'model_primary': cum(_d, 'model_ret'),
    'gap_new': [round(x['gap_bps'], 2) for x in _d],
    'ledger': [{'date': x['date'], 'ticker': x['ticker'], 'treatment': x['treatment'],
                'term_bps': round(x['term_bps'], 1), 'weight': round(x['weight'], 3)}
               for x in S0801['distribution_ledger']],
    'first': {'date': _d[0]['date'], 'gap': round(_d[0]['gap_bps'], 2)},
    'stats': {k: S0801[k] for k in ('window', 'n_trading_days', 'n_days', 'annualized_gap',
                                     'cumulative_gap', 'daily_return_correlation',
                                     'live_beta_to_model', 'live_model_vol_ratio',
                                     'live_cumulative_return', 'model_cumulative_return',
                                     'window_first_return_date')},
    'old': {k: S_OLD[k] for k in ('annualized_gap', 'cumulative_gap', 'n_days',
                                   'daily_return_correlation', 'live_beta_to_model',
                                   'live_model_vol_ratio')},
}

for e in ORDER:
    s = data[e]['stats']
    print(f"{e:6s} gap {s['cum_gap_old']:+.4f} -> {s['cum_gap_new']:+.4f}  corr {s['corr_old']:.3f} -> {s['corr_new']:.3f}  "
          f"beta {s['beta']:.3f} volr {s['volr']:.3f} ann {s['ann_old']:+.4f} -> {s['ann_new']:+.4f}  "
          f"income ${s['income']:,.0f} leaked ${s['leaked_usd']:,.0f} ({s['n_leaked']}L/{s['n_held']}H)")

HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Divergence distribution fix</title>
<meta name="description" content="Addendum 38: live vs backtest after the distribution-aware fix to divergence.py, 2026-10-05 frozen panel.">
<style>
:root {
  color-scheme: light;
  --surface-1:#fcfcfb; --surface-2:#f3f2ef; --border:#e2e1dc;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#7a7975;
  --grid:#e8e7e2; --axis:#b8b7b1;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100;
  --mark-leak:#52514e; --mark-held:#52514e;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-1:#1a1a19; --surface-2:#232322; --border:#33332f;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8d8c85;
    --grid:#2c2c2a; --axis:#5a5955;
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500;
    --mark-leak:#c3c2b7; --mark-held:#c3c2b7;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-1:#1a1a19; --surface-2:#232322; --border:#33332f;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8d8c85;
  --grid:#2c2c2a; --axis:#5a5955;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500;
  --mark-leak:#c3c2b7; --mark-held:#c3c2b7;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--surface-1); color:var(--text-primary);
  font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
main { max-width:980px; margin:0 auto; padding:16px; }
h1 { font-size:20px; margin:0 0 4px; }
h2 { font-size:16px; margin:28px 0 8px; }
p.sub { color:var(--text-secondary); margin:0 0 12px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; margin:12px 0 4px; }
.tile { background:var(--surface-2); border:1px solid var(--border); border-radius:8px; padding:10px 12px; }
.tile .k { font-size:12px; color:var(--text-secondary); }
.tile .v { font-size:20px; font-weight:600; font-variant-numeric:tabular-nums; }
.tile .d { font-size:12px; color:var(--text-muted); font-variant-numeric:tabular-nums; }
.legend { display:flex; flex-wrap:wrap; gap:6px 16px; font-size:12px; color:var(--text-secondary); margin:6px 0 4px; }
.legend span::before { content:""; display:inline-block; width:14px; height:3px; border-radius:2px; vertical-align:middle; margin-right:6px; background:var(--c); }
.legend span.mk::before { height:0; width:0; border-left:6px solid transparent; border-right:6px solid transparent; border-bottom:9px solid var(--mark-held); background:none; border-radius:0; }
.legend span.ln::before { height:0; width:12px; border-top:2px dashed var(--mark-leak); background:none; border-radius:0; }
.chart { width:100%; margin:4px 0 2px; }
.chart svg { display:block; width:100%; height:auto; overflow:visible; }
.grid { stroke:var(--grid); stroke-width:1; }
.axis { stroke:var(--axis); stroke-width:1; }
.tick { font-size:11px; fill:var(--text-muted); }
.lbl { font-size:11px; fill:var(--text-secondary); }
.lbl.b { font-weight:600; fill:var(--text-primary); }
.line { fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
.hit { fill:transparent; }
.hit:hover { fill:var(--text-primary); fill-opacity:0.06; }
.leak { stroke:var(--mark-leak); stroke-width:1; stroke-dasharray:3 3; }
.held { fill:var(--mark-held); }
.eng { border-top:1px solid var(--border); padding-top:10px; margin-top:10px; }
.eng h3 { font-size:14px; margin:0 0 2px; }
.eng .meta { font-size:12px; color:var(--text-secondary); font-variant-numeric:tabular-nums; }
.bar { stroke:var(--surface-1); stroke-width:2; }
table { border-collapse:collapse; width:100%; font-size:12.5px; font-variant-numeric:tabular-nums; margin:6px 0; }
th,td { padding:5px 6px; text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
th:first-child,td:first-child { text-align:left; }
th { color:var(--text-secondary); font-weight:600; }
.wrap { overflow-x:auto; }
.note { font-size:12.5px; color:var(--text-secondary); }
.note li { margin:2px 0; }
details summary { cursor:pointer; color:var(--text-secondary); font-size:13px; }
</style>
</head>
<body data-palette="#2a78d6,#eb6834,#1baf7a,#eda100">
<main>
<h1>divergence.py after the distribution fix (add. 38)</h1>
<p class="sub">Frozen 2026-10-05 panel, all four invested engines. Live = Composer deposit-adjusted curve (a price path). Model = Composer backtest (total return). NEW = model with LEAKED distribution terms removed; corr on live-plus-income vs model total return.</p>

<div class="tiles" id="tiles"></div>

<h2>A. Cumulative return, indexed to 100 at window start</h2>
<div class="legend">
  <span style="--c:var(--s1)">live (deposit-adjusted, price path)</span>
  <span style="--c:var(--s2)">model total return (add. 36 basis, OLD)</span>
  <span style="--c:var(--s3)">model, LEAKED terms removed (PRIMARY, NEW)</span>
  <span style="--c:var(--s4)">model, every term removed (all-stripped, lenient)</span>
  <span class="mk">HELD_THROUGH ex-date (income re-enters live on pay date)</span>
  <span class="ln">LEAKED ex-date (income went to account cash)</span>
</div>
<div id="lines"></div>

<h2>B. Cumulative gap live minus model, OLD vs NEW, with daily-return correlation</h2>
<div class="legend">
  <span style="--c:var(--s2)">OLD (live price path vs model total return)</span>
  <span style="--c:var(--s3)">NEW (primary: leaked terms removed)</span>
</div>
<div class="chart" id="bars"></div>

<h2>C. Table view</h2>
<div class="wrap"><table id="tbl">
<thead><tr><th>engine</th><th>window</th><th>trading days</th><th>live cum</th><th>model cum OLD</th><th>model cum NEW</th><th>gap OLD</th><th>gap NEW</th><th>corr OLD</th><th>corr NEW</th><th>beta</th><th>vol ratio</th><th>live maxDD</th><th>ann gap OLD</th><th>ann gap NEW</th><th>ann gap all-stripped</th><th>worst day NEW</th><th>ex-rows L/H</th><th>$ model entitlement</th><th>$ of it LEAKED</th></tr></thead>
<tbody></tbody></table></div>

<h2>D. Op2 sleeve read: from the 07-31 base close (<code>--start 2026-08-01</code>)</h2>
<div class="legend">
  <span style="--c:var(--s1)">live (deposit-adjusted)</span>
  <span style="--c:var(--s3)">model, LEAKED terms removed (PRIMARY)</span>
</div>
<div class="tiles" id="op2tiles"></div>
<div id="op2"></div>
<p class="note">__OP2BASE__</p>

<details><summary>Distribution ledger (every ex-date the model held into)</summary>
<div class="wrap"><table id="ledger"><thead><tr><th>engine</th><th>ex-date</th><th>ticker</th><th>w(t-1)</th><th>term bps</th><th>treatment</th><th>$ model entitlement</th></tr></thead><tbody></tbody></table></div>
</details>

<h2>Read it right</h2>
<ul class="note">
<li>Basis: gap = live price path vs model with LEAKED terms (w(t-1) x D/P_prev x (1+r_adj), Yahoo multiplicative convention) removed; HELD_THROUGH terms stay in the model because that income re-enters the live curve on pay date. Corr/beta/vol-ratio: live + every term vs model total return.</li>
<li>HARV 2026-08-19 still reads -61 bps after the fix: ZVOL sold at 7.4502 vs the 7.55 close. That is a genuine fill shortfall, not a distribution artefact.</li>
<li>Not modeled: pay dates as such (held-through recredit days stay in the daily series as +w*y), per-symphony live share counts (model-only rows such as KMLM TLT 09-01 read in live's favour), intraday fill timing, the ~10.3 bps x one-way turnover the backtest charges itself, decision-divergence days, the HG/SLEEVE live edits of 2026-07-30/31 (full-window numbers mix two strategies before 08-01), and pre-window credits under <code>--start</code> (flagged instead: __PRE__).</li>
<li>Observed-lag table: HELD/LEAKED is classified from the MODEL's continuity against a pay lag L <em>observed on the fund's own credit</em> in the cash trail (account-cash residual + fills; not issuer documentation, no issuer-family inheritance): ZVOL 1, PULS 2, BIL 3, TQQQ 4, SSO 4, LABD 5, TMV 5 trading days. HELD_THROUGH iff the model holds the payer on ex..ex+L-1 (the credit lands at the ex+L open, before that day's rebalance). It reproduces the cash trail 14/14 on this panel; one pre-edit model-only row flips vs the first ex..ex+4 build, HG BIL 2026-04-01 (held ex..ex+3) to HELD_THROUGH, so HG's gap reads 0.35 pp/yr lower.</li>
<li>Unknown lag = AMBIGUOUS, strict: every other payer gets no guessed lag. That includes SOXL and TNA (held live into an ex-date, credit not identified: SOXL's 2.6 bps term is below the 3-bps match tolerance and its candidate days are noisy; TNA 2026-06-23's credit is masked by ~$50k of account flows), QLD/UDOW/TECL (never held live into an ex-date), TLT, SQQQ and any new holding. Sold at the ex-date close = LEAKED; held ex..ex+4 = HELD_THROUGH; anything in between = AMBIGUOUS. An AMBIGUOUS row stays in the model (the strict, lower gap), the lenient number is shown, and the account-cash residual must be checked before acting on a gate. There are none on this panel. Dropping the five unobserved entries changed no label and no number: KMLM SOXL 09-22 was held ex..ex+4 and HG TNA was sold on its ex-dates.</li>
<li>Credit pending: a held row stays provisional until model day ex+L, the credit day, is inside the window. Until then the primary gap carries live's -w*y dip with no recredit (__PEND__). Nothing is pending on this panel: the latest row is PULS 09-30, whose credit on 10-02 is the window end.</li>
<li><strong>Op2 sleeve read now starts 2026-08-01</strong> (<code>divergence.py nNdBk7hc5NiBzeRvbI5T --start 2026-08-01</code>; the sleeve was edited live on 07-31, and the backtest is always the current version): __OP2__. The full-window SLEEVE numbers above mix two strategy versions.</li>
</ul>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
const DATA = JSON.parse(document.getElementById('data').textContent);
const ORDER = ['HG','KMLM','SLEEVE','HARV'];
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const pct = (x,d=2) => (x>=0?'+':'')+(100*x).toFixed(d)+'%';
const fx = n => n.toFixed(3);
const usd = n => '$'+Math.round(n).toLocaleString();
const NS = 'http://www.w3.org/2000/svg';
function el(tag, attrs, text){ const e=document.createElementNS(NS,tag); for(const k in attrs) e.setAttribute(k,attrs[k]); if(text!=null) e.textContent=text; return e; }

// stat tiles
const tiles = document.getElementById('tiles');
ORDER.forEach(e=>{ const s=DATA[e].stats; const t=document.createElement('div'); t.className='tile';
  t.innerHTML = `<div class="k">${e} cum gap OLD → NEW</div><div class="v">${pct(s.cum_gap_old)} → ${pct(s.cum_gap_new)}</div><div class="d">corr ${fx(s.corr_old)} → ${fx(s.corr_new)} · ${s.n_leaked} leaked / ${s.n_held} held</div>`;
  tiles.appendChild(t); });

// line charts
function drawLines(hostId, keys){
  const host=document.getElementById(hostId); host.innerHTML='';
  const W = Math.max(300, host.clientWidth || 320);
  const phone = W < 560;
  const H = phone ? 230 : 280, ML = 40, MR = phone ? 10 : 14, MT = 10, MB = 52;
  keys.forEach(e=>{
    const d=DATA[e], s=d.stats, n=d.dates.length, op2=(e==='OP2');
    const box=document.createElement('div'); box.className='eng';
    box.innerHTML=op2
      ? `<h3>SLEEVE from ${s.window[0]} (base close)</h3><div class="meta">first counted return ${s.window_first_return_date} (gap ${d.first.gap} bps) · ${s.n_trading_days} trading days of the &ge;120 Op2 needs · live ${pct(s.live_cumulative_return)} · model ${pct(s.model_cumulative_return)}</div>`
      : `<h3>${e}</h3><div class="meta">${s.window[0]} .. ${s.window[1]} (${s.n_trading_days} trading days) · live ${pct(s.live_cum)} · model OLD ${pct(s.model_cum_tr)} · NEW ${pct(s.model_cum_new)} · all-stripped ${pct(s.model_cum_px)}</div>`;
    const ch=document.createElement('div'); ch.className='chart'; box.appendChild(ch); host.appendChild(box);
    const series=op2 ? [['live',d.live,'--s1'],['model_primary',d.model_primary,'--s3']]
      : [['live',d.live,'--s1'],['model_tr',d.model_tr,'--s2'],['model_primary',d.model_primary,'--s3'],['model_px',d.model_px,'--s4']];
    let lo=Infinity,hi=-Infinity; series.forEach(([,v])=>v.forEach(x=>{lo=Math.min(lo,x);hi=Math.max(hi,x);}));
    const pad=(hi-lo)*0.06||1; lo-=pad; hi+=pad;
    const xs=i=>ML+(W-ML-MR)*i/(n-1), ys=v=>MT+(H-MT-MB)*(hi-v)/(hi-lo);
    const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,width:W,height:H,role:'img','aria-label':e+' cumulative return indexed to 100'});
    // grid
    const ticks=5; for(let k=0;k<ticks;k++){ const v=lo+(hi-lo)*k/(ticks-1), y=ys(v);
      svg.appendChild(el('line',{x1:ML,x2:W-MR,y1:y,y2:y,class:'grid'}));
      svg.appendChild(el('text',{x:ML-5,y:y+4,class:'tick','text-anchor':'end'},v.toFixed(0))); }
    const step=Math.max(1,Math.round(n/(phone?4:7)));
    for(let i=0;i<n;i+=step) svg.appendChild(el('text',{x:xs(i),y:H-MB+14,class:'tick','text-anchor':'middle'},d.dates[i].slice(5)));
    // ex-date markers (behind the lines)
    const y0=ys(lo)+0, idx={}; d.dates.forEach((x,i)=>idx[x]=i);
    const lab=[];
    d.ledger.forEach(r=>{ let i=idx[r.date]; if(i==null) return; const x=xs(i);
      if(r.treatment==='LEAKED'){ svg.appendChild(el('line',{x1:x,x2:x,y1:MT,y2:H-MB,class:'leak'})); }
      else { svg.appendChild(el('path',{d:`M${x-5},${H-MB} L${x+5},${H-MB} L${x},${H-MB-8} Z`,class:'held'})); }
      lab.push([x,r]); });
    // marker labels (collision-avoid: stagger rows)
    let lastx=-1e9,row=0;
    lab.forEach(([x,r])=>{ if(x-lastx<46){row=(row+1)%2;} else row=0; lastx=x;
      const t=el('text',{x:x,y:H-MB+28+row*11,class:'lbl','text-anchor':'middle'},r.ticker+(r.treatment==='LEAKED'?' L':''));
      t.appendChild(el('title',{},`${r.date} ${r.ticker} ${r.treatment} term ${r.term_bps} bps w(t-1) ${r.weight}`));
      svg.appendChild(t); });
    // lines
    series.forEach(([k,v,c])=>{ let p=''; v.forEach((y,i)=>{p+=(i?'L':'M')+xs(i).toFixed(1)+','+ys(y).toFixed(1);});
      svg.appendChild(el('path',{d:p,class:'line',stroke:css(c)})); });
    // direct end labels: value at end, staggered by rank
    const ends=series.map(([k,v,c])=>({k,v:v[v.length-1],c})).sort((a,b)=>b.v-a.v);
    let prevy=-1e9; ends.forEach(o=>{ let y=ys(o.v); if(y-prevy<12) y=prevy+12; prevy=y;
      const t=el('text',{x:W-MR-2,y:y-4,class:'lbl b','text-anchor':'end'},(o.v-100>=0?'+':'')+(o.v-100).toFixed(2)+'%');
      svg.appendChild(el('circle',{cx:W-MR,cy:ys(o.v),r:3.5,fill:css(o.c),stroke:css('--surface-1'),'stroke-width':2}));
      svg.appendChild(t); });
    // hover layer
    const bw=(W-ML-MR)/(n-1);
    for(let i=0;i<n;i++){ const r=el('rect',{x:xs(i)-bw/2,y:MT,width:bw,height:H-MT-MB,class:'hit'});
      r.appendChild(el('title',{},op2
        ? `${d.dates[i]}\nlive ${(d.live[i]-100).toFixed(2)}%\nmodel ${(d.model_primary[i]-100).toFixed(2)}%`+(i?`\ngap ${d.gap_new[i-1]} bps`:' (base close)')
        : `${d.dates[i]}\nlive ${(d.live[i]-100).toFixed(2)}%\nmodel OLD ${(d.model_tr[i]-100).toFixed(2)}%\nmodel NEW ${(d.model_primary[i]-100).toFixed(2)}%\nall-stripped ${(d.model_px[i]-100).toFixed(2)}%`+(i?`\ngap OLD ${d.gap_old[i-1]} bps · NEW ${d.gap_new[i-1]} bps`:'')));
      svg.appendChild(r); }
    ch.appendChild(svg);
  });
}

// bar chart
function drawBars(){
  const host=document.getElementById('bars'); host.innerHTML='';
  const W=Math.max(300,host.clientWidth||320), phone=W<560;
  const H=phone?250:280, ML=44, MR=10, MT=16, MB=56;
  const vals=[]; ORDER.forEach(e=>{vals.push(DATA[e].stats.cum_gap_old*100,DATA[e].stats.cum_gap_new*100);});
  let lo=Math.min(0,...vals), hi=Math.max(0,...vals); const pad=(hi-lo)*0.15; lo-=pad; hi+=pad;
  const ys=v=>MT+(H-MT-MB)*(hi-v)/(hi-lo), y0=ys(0);
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,width:W,height:H,role:'img','aria-label':'cumulative gap old vs new per engine'});
  for(let k=0;k<5;k++){ const v=lo+(hi-lo)*k/4,y=ys(v); svg.appendChild(el('line',{x1:ML,x2:W-MR,y1:y,y2:y,class:'grid'})); svg.appendChild(el('text',{x:ML-5,y:y+4,class:'tick','text-anchor':'end'},v.toFixed(0)+'%')); }
  svg.appendChild(el('line',{x1:ML,x2:W-MR,y1:y0,y2:y0,class:'axis'}));
  const gw=(W-ML-MR)/ORDER.length, bw=Math.min(44,gw*0.3);
  ORDER.forEach((e,g)=>{ const s=DATA[e].stats, cx=ML+gw*(g+0.5);
    [[s.cum_gap_old*100,'--s2','OLD'],[s.cum_gap_new*100,'--s3','NEW']].forEach(([v,c,nm],j)=>{
      const x=cx-bw-1+j*(bw+2), y=ys(v), top=Math.min(y,y0), h=Math.abs(y-y0);
      const r=el('rect',{x:x,y:top,width:bw,height:Math.max(h,0.5),rx:3,fill:css(c),class:'bar'});
      r.appendChild(el('title',{},`${e} ${nm}: cumulative gap ${v.toFixed(2)}%`)); svg.appendChild(r);
      svg.appendChild(el('text',{x:x+bw/2,y:v>=0?top-4:top+h+12,class:'lbl b','text-anchor':'middle'},(v>=0?'+':'')+v.toFixed(2)+'%'));
    });
    svg.appendChild(el('text',{x:cx,y:H-MB+16,class:'lbl b','text-anchor':'middle'},e));
    svg.appendChild(el('text',{x:cx,y:H-MB+30,class:'lbl','text-anchor':'middle'},'corr '+fx(s.corr_old)+' → '+fx(s.corr_new)));
    svg.appendChild(el('text',{x:cx,y:H-MB+43,class:'tick','text-anchor':'middle'},'ann '+pct(s.ann_old,1)+' → '+pct(s.ann_new,1)+'/yr'));
  });
  host.appendChild(svg);
}

// tables
const tb=document.querySelector('#tbl tbody');
ORDER.forEach(e=>{ const s=DATA[e].stats; const tr=document.createElement('tr');
  tr.innerHTML=[e,`${s.window[0]}..${s.window[1]}`,s.n_trading_days,pct(s.live_cum),pct(s.model_cum_tr),pct(s.model_cum_new),pct(s.cum_gap_old),pct(s.cum_gap_new),fx(s.corr_old),fx(s.corr_new),fx(s.beta),fx(s.volr),pct(s.maxdd,1),pct(s.ann_old,1),pct(s.ann_new,1),pct(s.ann_allx,1),`${s.worst} bps ${s.worst_date}`,`${s.n_leaked}/${s.n_held}`,usd(s.income),usd(s.leaked_usd)].map(x=>`<td>${x}</td>`).join('');
  tb.appendChild(tr); });
const lb=document.querySelector('#ledger tbody');
ORDER.forEach(e=>DATA[e].ledger.forEach(r=>{ const tr=document.createElement('tr');
  tr.innerHTML=[e,r.date,r.ticker,r.weight.toFixed(3),r.term_bps.toFixed(1),r.treatment,r.income==null?'n/a':usd(r.income)].map(x=>`<td>${x}</td>`).join(''); lb.appendChild(tr); }));

// Op2 tiles: boundary before/after
const o=DATA.OP2, ot=document.getElementById('op2tiles');
[['ann gap (gate &ge; -10%/yr)', pct(o.old.annualized_gap,2)+' → '+pct(o.stats.annualized_gap,2), `cum ${pct(o.old.cumulative_gap)} → ${pct(o.stats.cumulative_gap)}`],
 ['corr (gate &ge; 0.90)', fx(o.old.daily_return_correlation)+' → '+fx(o.stats.daily_return_correlation), `beta ${fx(o.old.live_beta_to_model)} → ${fx(o.stats.live_beta_to_model)} · vol-ratio ${fx(o.old.live_model_vol_ratio)} → ${fx(o.stats.live_model_vol_ratio)}`],
 ['daily returns counted', o.old.n_days+' → '+o.stats.n_days, `base 08-03 (superseded) → ${o.stats.window[0]}`]
].forEach(([k,v,dd])=>{ const t=document.createElement('div'); t.className='tile';
  t.innerHTML=`<div class="k">${k}</div><div class="v">${v}</div><div class="d">${dd}</div>`; ot.appendChild(t); });

function draw(){ drawLines('lines', ORDER); drawLines('op2', ['OP2']); drawBars(); }
draw();
let t; window.addEventListener('resize',()=>{clearTimeout(t); t=setTimeout(draw,120);});
const mq=window.matchMedia('(prefers-color-scheme: dark)'); if(mq.addEventListener) mq.addEventListener('change',draw);
})();
</script>
</body>
</html>
'''
s = S0801
OP2 = (f"base close {s['window'][0]}, first counted return {s['window_first_return_date']}, "
       f"to {s['window'][1]}: {s['n_trading_days']} trading days on/after {OP2_START} (of the "
       f"&ge;120 Op2 needs; {s['n_days']} daily returns), corr {s['daily_return_correlation']:.3f}, beta "
       f"{s['live_beta_to_model']:.3f}, vol-ratio {s['live_model_vol_ratio']:.3f}, "
       f"ann gap {100 * s['annualized_gap']:+.2f}%/yr, cum gap {100 * s['cumulative_gap']:+.2f}% "
       f"(live {100 * s['live_cumulative_return']:+.2f}% vs model "
       f"{100 * s['model_cumulative_return']:+.2f}%), live maxDD {100 * s['live_max_drawdown']:.1f}%")
o = S_OLD
OP2BASE = (f"Why the base is the 07-31 close: the 07-31 close holdings are already the edited "
           f"strategy (fills: BOXX bought 07-31 15:53 to 0.75 of the sleeve = the model's BOXX "
           f"0.75 / LABD 0.25; LABD &rarr; BOXX 08-03 15:53 = the model's move), so the "
           f"07-31 &rarr; 08-03 return is a clean post-edit day. Its "
           f"{s['daily'][0]['gap_bps']:+.2f} bps is mostly LABD fill timing (~-12 bps: sold 9.245 at 15:53 vs the "
           f"9.29 close), the shortfall Op2 measures. The superseded boundary (base 08-03) dropped it "
           f"and read ann {100 * o['annualized_gap']:+.2f}%/yr, cum "
           f"{100 * o['cumulative_gap']:+.2f}% on {o['n_days']} returns: lenient by "
           f"{100 * (o['annualized_gap'] - s['annualized_gap']):.2f} pp/yr. Verdict unchanged (both far "
           f"above -10%/yr and corr 0.90). In-sample, {s['n_days']} returns; not a forecast.")
PRETXT = "; ".join(
    f"{e} from {OP2_START}: {x['ticker']} {x['date']} credit {x['credit_day']}, gap high by up to "
    f"{100 * r['pre_window_credit_bias_annualized_max']:.1f} pp/yr "
    f"({100 * r['annualized_gap']:+.1f}%/yr read, {100 * r['annualized_gap_pre_window_credits_offset']:+.1f}%/yr offset)"
    for e, r in PRE.items() for x in r['pre_window_credit_rows'])
PRETXT += "; SLEEVE (Op2): none" if not S0801['pre_window_credit_rows'] else ""
a, b = PEND['2026-09-01'], PEND['2026-09-02']
PENDTXT = (f"HARV PULS 08-31, L=2: window ending 09-01 reads {100 * a['annualized_gap']:+.2f}%/yr "
           f"and is flagged pending; ending 09-02, {100 * b['annualized_gap']:+.2f}%/yr")
assert next(x for x in a['distribution_ledger'] if x['date'] == '2026-08-31')['credit_pending']
assert not next(x for x in b['distribution_ledger'] if x['date'] == '2026-08-31')['credit_pending']
print(f"SLEEVE from {OP2_START}: {OP2}")
print(f"pending: {PENDTXT}")
print(f"boundary: {OP2BASE}")
print(f"pre-window: {PRETXT}")

out = os.path.join(RES, 'divergence-distribution-fix-2026-10-05.html')
with open(out, 'w') as f:
    f.write(HTML.replace('__DATA__', json.dumps(data, separators=(',', ':')))
            .replace('__OP2__', OP2).replace('__PEND__', PENDTXT)
            .replace('__OP2BASE__', OP2BASE).replace('__PRE__', PRETXT))
print('wrote', out, os.path.getsize(out), 'bytes')
