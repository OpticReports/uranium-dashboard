import json, math, html
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import SP
G = json.load(open(f'{SP}/gate_explain.json'))
def yh(t):
    o = json.load(open(f"{SP}/yh/{t.replace('^','_')}.json")); return dict(zip(o['dates'], o['adjclose']))
spy = yh('SPY'); sds = sorted(spy); MA = {sds[i]: sum(spy[x] for x in sds[i-199:i+1])/200 for i in range(199, len(sds))}
def panel(lab, w=940, h=330):
    g = G[lab]; days = g['days']; n = len(days)
    L, R, T, Bm = 60, 16, 30, 40
    allv = g['base'] + g['gated']; y0, y1 = math.log(min(allv)), math.log(max(allv)); pad = (y1-y0)*0.05; y0 -= pad; y1 += pad
    X = lambda i: L + i/(n-1)*(w-L-R); Y = lambda v: T + (1-(math.log(v)-y0)/(y1-y0))*(h-T-Bm)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px;font-family:system-ui,sans-serif">']
    out.append(f'<text x="{L}" y="16" font-size="13" font-weight="600" fill="#111">{html.escape(lab)}: HG as built vs HG with the bear gate (shaded = SPY below its 200-day average, gate ON)</text>')
    # shading
    on = False; x0 = None
    for i, d in enumerate(days):
        bear = d in MA and spy[d] < MA[d]
        if bear and not on: on = True; x0 = X(i)
        if (not bear or i == n-1) and on:
            on = False; out.append(f'<rect x="{x0:.1f}" y="{T}" width="{X(i)-x0:.1f}" height="{h-T-Bm}" fill="#f59e0b" fill-opacity="0.13"/>')
    lo, hi = math.exp(y0), math.exp(y1)
    for m in (0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 50, 100, 300, 1000, 3000):
        if lo <= m <= hi:
            out.append(f'<line x1="{L}" x2="{w-R}" y1="{Y(m):.1f}" y2="{Y(m):.1f}" stroke="#e5e7eb"/><text x="{L-6}" y="{Y(m)+4:.1f}" font-size="10" text-anchor="end" fill="#555">{m:g}x</text>')
    for i in range(0, n, max(1, n//6)):
        out.append(f'<text x="{X(i):.1f}" y="{h-22}" font-size="10" text-anchor="middle" fill="#555">{days[i][:7]}</text>')
    for key, col, wd in (('base', '#c2410c', 2.0), ('gated', '#1f5fa8', 2.0)):
        d = 'M' + ' L'.join(f'{X(i):.1f},{Y(v):.1f}' for i, v in enumerate(g[key]))
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{wd}"/>')
    out.append(f'<text x="{L+8}" y="{T+14}" font-size="11" fill="#c2410c">as built: {g["base_cum"]:.2f}x, {g["base_cagr"]:+.0%}/yr, max DD {g["base_mdd"]:.0%}</text>')
    out.append(f'<text x="{L+8}" y="{T+28}" font-size="11" fill="#1f5fa8">with gate: {g["gated_cum"]:.2f}x, {g["gated_cagr"]:+.0%}/yr, max DD {g["gated_mdd"]:.0%}  (gate on {g["gate_days"]}/{g["n"]} days; HG moved to cash on {g["extra_cash_days"]} of them)</text>')
    out.append('</svg>')
    yrs = ''.join(f'<td>{y}</td>' for y in sorted(g['by_year']))
    b = ''.join(f'<td>{v[0]:+.0%}</td>' for y, v in sorted(g['by_year'].items())); gg = ''.join(f'<td>{v[1]:+.0%}</td>' for y, v in sorted(g['by_year'].items()))
    tbl = f'<table class="t"><tr><th>year</th>{yrs}</tr><tr><th>as built</th>{b}</tr><tr><th>with gate</th>{gg}</tr></table>'
    return '\n'.join(out) + tbl
body = ''.join(panel(k) for k in ('dotcom 1999-06..2003-12', 'GFC 2007-01..2010-12', 'real tickers 2015-06..2026-10'))
page = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HG bear gate</title>
<style>body{{margin:0;padding:16px;font-family:system-ui,sans-serif;color:#111;background:#fff;max-width:980px;margin:auto}}h1{{font-size:18px;margin:4px 0 10px}}p{{font-size:13px;line-height:1.45}}.t{{border-collapse:collapse;font-size:11.5px;margin:4px 0 18px;width:100%}}.t th{{text-align:left;background:#111;color:#fff;padding:3px 6px}}.t td{{padding:3px 6px;border-bottom:1px solid #e5e7eb;text-align:right}}
@media (prefers-color-scheme: dark){{body{{background:#0f1115;color:#e5e7eb}}svg text{{fill:#d1d5db!important}}.t td{{border-color:#2a2f3a}}}}</style></head><body>
<h1>The HG bear gate (candidate C2): what it does, what it costs, what it saves</h1>
<p>Rule: at the decision close, if SPY is below its 200-day moving average, HG's <b>trend baskets</b> (the "10-day MA above 20-day MA" branch and the "otherwise" branch, both of which hold the highest-RSI of TQQQ/UPRO/UDOW/SSO/TNA) go to BIL instead. The dip-buy branch (TQQQ RSI below 30 — TECL/QLD/LABU/USD/SMH), the long-vol branch and the existing cash defaults are untouched. Composer-equivalent costs. 2000-02 and 2008 use reconstructed leveraged ETFs (the rules never ran then — out of sample); 2015-26 uses real tickers (in sample).</p>
{body}
<p>Reading: the orange shading is when the gate is on. In the long bears it is on most of the time and HG sits out the failed rallies that cost it 70%. In the bull decade it is on ~18% of days — the pullbacks inside bull markets — and HG misses the first weeks of each V-shaped rebound (2019, 2020, 2022, 2023, 2025), which is where its 3x trend branch earns most.</p>
</body></html>'''
open('/home/user/uranium-dashboard/composer/results/hg-bear-gate-2026-10-07.html', 'w').write(page); print('wrote')
