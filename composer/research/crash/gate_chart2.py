"""Chart for the gate study: 1990-2026 HG curves (as built / binary / vote / oil), the
risk-adjusted table for both panels, CAGR-vs-maxDD frontier, and per-window bars."""
import os, json, math, html, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_study as gs
SP = gs.SP
G = json.load(open(f'{SP}/gate_study.json'))
PL = gs.build_lh_prices(); days, h, px = gs.base_run(PL, '1990-01-02', '2026-10-06')
spy = PL['SPY']; T, ma50, ma100, ma200 = gs.gates_trend(spy); M = gs.build_macro_allows(spy, ma50, ma100, ma200, days)
ds_ = sorted(d for d in spy if d in ma200); g6 = {}
for d in ds_:
    vote = (float(spy[d] > ma50[d]) + float(spy[d] > ma100[d]) + float(spy[d] > ma200[d]))/3.0
    g6[d] = 0.0 if spy[d] < ma200[d] else vote
SHOW = [('B0 as built', {}, '#c2410c'), ('B1 binary SPY<200d', T['B1 binary SPY<200d'], '#1f5fa8'), ('G2 vote 50/100/200d', T['G2 vote 50/100/200d'], '#0f766e'), ('G6 off below 200d, vote above', g6, '#b45309'), ('M4 oil +50% yoy -> 100d', M['M4 oil +50% yoy -> 100d'], '#7c3aed')]
PL2 = json.load(open(f'{SP}/gate_placebo.json')); BG = json.load(open(f'{SP}/boot_gate.json')); EX = json.load(open(f'{SP}/gate_extra.json'))
curves = {}
for name, al, col in SHOW:
    r, _, _ = gs.variant_returns(days, h, px, al); c = [1.0]
    for d in days[1:]: c.append(c[-1]*(1+r[d]))
    curves[name] = c
spyc = [spy[d]/spy[days[0]] for d in days]
def svg_curves(w=940, h=360):
    L, R, Tm, Bm = 60, 16, 26, 36; n = len(days)
    allv = [v for c in curves.values() for v in c] + spyc; y0, y1 = math.log(min(allv)), math.log(max(allv)); pad = (y1-y0)*0.04; y0 -= pad; y1 += pad
    X = lambda i: L + i/(n-1)*(w-L-R); Y = lambda v: Tm + (1-(math.log(v)-y0)/(y1-y0))*(h-Tm-Bm)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px;font-family:system-ui,sans-serif">']
    on = False; x0 = None
    for i, d in enumerate(days):
        bear = d in ma200 and spy[d] < ma200[d]
        if bear and not on: on = True; x0 = X(i)
        if (not bear or i == n-1) and on: on = False; out.append(f'<rect x="{x0:.1f}" y="{Tm}" width="{X(i)-x0:.1f}" height="{h-Tm-Bm}" fill="#f59e0b" fill-opacity="0.12"/>')
    for m in (0.5, 1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000):
        if math.exp(y0) <= m <= math.exp(y1): out.append(f'<line x1="{L}" x2="{w-R}" y1="{Y(m):.1f}" y2="{Y(m):.1f}" stroke="#e5e7eb"/><text x="{L-6}" y="{Y(m)+4:.1f}" font-size="10" text-anchor="end" fill="#555">{m:g}x</text>')
    for i in range(0, n, n//9): out.append(f'<text x="{X(i):.1f}" y="{h-20}" font-size="10" text-anchor="middle" fill="#555">{days[i][:4]}</text>')
    d = 'M' + ' L'.join(f'{X(i):.1f},{Y(v):.1f}' for i, v in enumerate(spyc)); out.append(f'<path d="{d}" fill="none" stroke="#6b7280" stroke-width="1.2" stroke-dasharray="4 3"/>')
    for name, al, col in SHOW:
        d = 'M' + ' L'.join(f'{X(i):.1f},{Y(v):.1f}' for i, v in enumerate(curves[name])); out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.8"/>')
    lx = L+8; ly = Tm+12
    for name, al, col in SHOW + [('S&P 500 (total return)', None, '#6b7280')]:
        out.append(f'<line x1="{lx}" x2="{lx+16}" y1="{ly}" y2="{ly}" stroke="{col}" stroke-width="2"/><text x="{lx+20}" y="{ly+4}" font-size="10.5" fill="#333">{html.escape(name)}</text>'); ly += 14
    out.append('</svg>'); return '\n'.join(out)
def table(head, rows):
    s = '<table class="t"><thead><tr>' + ''.join(f'<th>{html.escape(c)}</th>' for c in head) + '</tr></thead><tbody>'
    for r in rows: s += '<tr>' + ''.join(f'<td>{html.escape(str(c))}</td>' for c in r) + '</tr>'
    return s + '</tbody></table>'
def frontier(pan, w=460, h=330):
    R = G['panels'][pan]['results']; full = list(R['B0 as built']['windows'])[0]
    pts = [(k, v['windows'][full]) for k, v in R.items() if v['windows'][full]]
    xs = [m['maxdd'] for _, m in pts]; ys = [m['cagr'] for _, m in pts]
    L, Rr, Tm, Bm = 50, 14, 26, 36; x0, x1 = min(xs)-0.02, max(xs)+0.02; y0, y1 = min(ys)-0.05, max(ys)+0.05
    X = lambda x: L + (x-x0)/(x1-x0)*(w-L-Rr); Y = lambda y: Tm + (1-(y-y0)/(y1-y0))*(h-Tm-Bm)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px;font-family:system-ui,sans-serif"><text x="{L}" y="14" font-size="12" font-weight="600" fill="#111">{"Panel A: real tickers 2015-26" if pan=="A" else "Panel B: long-history proxy 1990-2026"} — CAGR vs max drawdown, every variant</text>']
    for t in [x0 + (x1-x0)*i/4 for i in range(5)]: out.append(f'<text x="{X(t):.1f}" y="{h-20}" font-size="10" text-anchor="middle" fill="#555">{t:.0%}</text>')
    for t in [y0 + (y1-y0)*i/4 for i in range(5)]: out.append(f'<line x1="{L}" x2="{w-Rr}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="#e5e7eb"/><text x="{L-5}" y="{Y(t)+4:.1f}" font-size="10" text-anchor="end" fill="#555">{t:.0%}</text>')
    out.append(f'<text x="{(L+w)/2:.0f}" y="{h-6}" font-size="10" text-anchor="middle" fill="#777">max drawdown (lower is better)</text>')
    for k, m in pts:
        col = '#c2410c' if k.startswith('B0') else '#1f5fa8' if k.startswith('B1') else '#0f766e' if k.startswith('G') else '#9ca3af' if k.startswith('INV') else '#7c3aed'
        out.append(f'<circle cx="{X(m["maxdd"]):.1f}" cy="{Y(m["cagr"]):.1f}" r="4" fill="{col}"><title>{html.escape(k)}: CAGR {m["cagr"]:+.1%}, maxDD {m["maxdd"]:.0%}, Sharpe {m["sharpe"]}</title></circle>')
        if not k.startswith('INV'): out.append(f'<text x="{X(m["maxdd"])+6:.1f}" y="{Y(m["cagr"])+3:.1f}" font-size="8.5" fill="{col}">{html.escape(k.split(" ")[0])}</text>')
    out.append(f'<text x="{L+6}" y="{Tm+12}" font-size="9.5" fill="#9ca3af">grey = inverse signals (loosen where the rule tightens)</text></svg>'); return '\n'.join(out)
rows = {}
for pan in ('B', 'A'):
    R = dict(G['panels'][pan]['results']); R.update(EX[pan]); full = list(R['B0 as built']['windows'])[0]; rows[pan] = []
    order = [k for k in R if not k.startswith('INV')] + [k for k in R if k.startswith('INV')]
    for k in order:
        v = R[k]; m = v['windows'][full]
        if not m: continue
        pz = PL2[pan].get(k, {})
        pl = (f"CAGR p{pz['real_pct']['cagr']*100:.0f} · Sharpe p{pz['real_pct']['sharpe']*100:.0f} · DD better than {pz['real_pct_maxdd_lower']*100:.0f}%" if pz else '')
        rows[pan].append([k, f"{m['cagr']:+.1%}", f"{m['vol']:.0%}", f"{m['sharpe']:.2f}", f"{m['sortino']:.2f}", f"{m['calmar']:.2f}" if m['calmar'] else '', f"{m['maxdd']:.0%}", f"{m['worst_year']:+.0%}", f"{v['mean_allow']:.2f}", pl])
boot_rows = []
for k, v in BG.items():
    a, c = v['as_measured'], v['conservative']
    boot_rows.append([k, f"{a['cagr_p05']:+.0%} / {a['cagr_p50']:+.0%}", f"{a['maxdd_p50']:.0%} / {a['maxdd_p95']:.0%}", f"{a['sharpe_p50']:.2f}", f"{c['cagr_p05']:+.0%} / {c['cagr_p50']:+.0%}", f"{c['maxdd_p50']:.0%} / {c['maxdd_p95']:.0%}", f"{c['sharpe_p50']:.2f}", f"{c['GFC 2007-10 12m']['cagr_p05']:+.0%} / {c['GFC 2007-10 12m']['cagr_p50']:+.0%}"])
# per-window table (B)
RB = G['panels']['B']['results']; wins = list(RB['B0 as built']['windows'])
wrows = []
for k in ('B0 as built', 'B1 binary SPY<200d', 'G1 ramp +-5% of 200d', 'G2 vote 50/100/200d', 'G3 persistence (tightens over 40d below 200d)', 'G4 drawdown ramp 5%->15%', 'M4 oil +50% yoy -> 100d', 'M5 count of M1-M4 flags -> 200/100/50/50d (near-permanent 50d gate)'):
    wrows.append([k] + [f"{RB[k]['windows'][w]['cagr']:+.0%} / {RB[k]['windows'][w]['sharpe']:.2f} / {RB[k]['windows'][w]['maxdd']:.0%}" for w in wins])
page = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HG gate variants</title>
<style>body{{margin:0;padding:16px;font-family:system-ui,sans-serif;color:#111;background:#fff;max-width:980px;margin:auto}}h1{{font-size:18px;margin:4px 0 8px}}h2{{font-size:14px;margin:18px 0 6px}}p{{font-size:12.5px;line-height:1.45}}.t{{border-collapse:collapse;font-size:11px;margin:4px 0 12px;width:100%}}.t th{{text-align:left;background:#111;color:#fff;padding:3px 5px}}.t td{{padding:3px 5px;border-bottom:1px solid #e5e7eb;white-space:nowrap}}
@media (prefers-color-scheme: dark){{body{{background:#0f1115;color:#e5e7eb}}svg text{{fill:#d1d5db!important}}.t td{{border-color:#2a2f3a}}}}</style></head><body>
<h1>HG bear gate: binary vs graded vs macro-conditioned, 1990-2026 proxy and 2015-26 real tickers</h1>
<p>Gates act at the decision close on HG's trend baskets only (TQQQ/UPRO/UDOW/SSO/TNA weight x allow, remainder to BIL); dip-buys, long-vol and cash defaults untouched. Composer-equivalent cost on each variant's own turnover. Panel B is a proxy (leveraged legs reconstructed from their indices; pre-1999 bases are index proxies; VIX ETPs modelled); HG's rules never ran before 2015, so panel B is out of sample for the rules and panel A is in sample. Shaded = SPY below its 200-day average.</p>
{svg_curves()}
<h2>Panel B (1990-2026 proxy): full-window risk-adjusted metrics (excess over T-bills)</h2>
{table(['variant', 'CAGR', 'vol', 'Sharpe', 'Sortino', 'Calmar', 'max DD', 'worst year', 'mean allow', 'vs 200 placebos (same pattern, random dates)'], rows['B'])}
<h2>Panel A (2015-2026 real tickers, in sample)</h2>
{table(['variant', 'CAGR', 'vol', 'Sharpe', 'Sortino', 'Calmar', 'max DD', 'worst year', 'mean allow', 'vs 200 placebos'], rows['A'])}
<p>Placebo (200 draws): trend gates — the variant's monthly allow pattern randomly re-dated; macro gates — the variant's monthly flag-level pattern (200d/100d/50d) randomly re-dated, each month tightened at its own level. The columns give the real variant's percentile (p100 = better than every placebo; p50 = indistinguishable from random). Inverse rows: trend gates = 1 − allow; macro gates = mirror image (flag ON → 200d, flag OFF → the variant's own tightening level). A signal that cannot beat its inverse carries no information. Rebuilt after the counter-agent found the first placebo tightened at the wrong level and under-counted flag months.</p>
<h2>Book level, house method: 55-year regime bootstrap with HG swapped for the variant (HG months from the 2015-26 real-ticker sim; other engines as in the study; cap-40)</h2>
{table(['HG variant', 'as-measured CAGR p05 / p50', 'as-measured maxDD p50 / p95', 'Sharpe p50', 'conservative CAGR p05 / p50', 'conservative maxDD p50 / p95', 'Sharpe p50', 'GFC-sequence 12m p05 / p50 (cons.)'], boot_rows)}
<p>The bootstrap only knows HG's 2015-26 months, so it reflects panel A's regime; the 2000/2008-type benefit in panel B is outside its buckets.</p>
<h2>Where the gate pays and where it costs (panel B, CAGR / Sharpe / max DD by window)</h2>
{table(['variant'] + wins, wrows)}
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:8px">{frontier('B')}{frontier('A')}</div>
<p>Prepared 2026-10-08. Scripts: composer/research/crash/gate_study.py, placebo2.py, boot_gate.py.</p></body></html>'''
open('/home/user/uranium-dashboard/composer/results/hg-gate-variants-2026-10-08.html', 'w').write(page); print('wrote')
