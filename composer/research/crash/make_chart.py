"""Self-contained HTML (inline SVG) report for the crash study."""
import json, math, html
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import SP
OUT = '/home/user/uranium-dashboard/composer/results/crash-sim-2026-10-07.html'
B = json.load(open(f'{SP}/book_sim.json')); S = json.load(open(f'{SP}/boot_scen.json')); H = json.load(open(f'{SP}/hist_replay.json'))
C = json.load(open(f'{SP}/covid_replay.json')); I = json.load(open(f'{SP}/improve.json'))
def yh(t):
    o = json.load(open(f"{SP}/yh/{t.replace('^','_')}.json")); return dict(zip(o['dates'], o['adjclose']))
spx = yh('^GSPC'); START = 303140

PAL = {'book': '#1f5fa8', 'HG': '#c2410c', 'KMLM': '#7c3aed', 'SLEEVE': '#0f766e', 'HARV': '#b45309', 'SPX': '#6b7280', 'band': '#1f5fa8'}

DASH = 'stroke-dasharray="4 3"'

def svg_lines(series, w=900, h=300, log=True, ylab='', title='', bands=None, ref=None, markers=None, xlab='trading days from day 0'):
    """series: list of (label, color, [(x,y)...], width, dash). bands: list of (color, [(x,lo,hi)])."""
    L, R, T, Bm = 58, 14, 28, 34
    xs = [p[0] for s in series for p in s[2]]; ys = [p[1] for s in series for p in s[2] if p[1] > 0]
    if bands:
        for _, pts in bands: ys += [p[1] for p in pts if p[1] > 0] + [p[2] for p in pts]; xs += [p[0] for p in pts]
    x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys)
    if log: y0, y1 = math.log(y0), math.log(y1)
    pad = (y1-y0)*0.06; y0 -= pad; y1 += pad
    X = lambda x: L + (x-x0)/(x1-x0)*(w-L-R)
    Y = lambda y: T + (1-((math.log(y) if log else y)-y0)/(y1-y0))*(h-T-Bm)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px;font-family:system-ui,sans-serif">']
    out.append(f'<text x="{L}" y="16" font-size="13" font-weight="600" fill="#111">{html.escape(title)}</text>')
    # y grid
    if log:
        lo, hi = math.exp(y0), math.exp(y1); ticks = []
        for m in (0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 15, 20):
            if lo <= m*START <= hi: ticks.append(m*START)
        if ref == 1: ticks = [t for t in (0.3, 0.5, 0.7, 1, 1.5, 2, 3, 5, 8) if lo <= t <= hi]
    else:
        step = (y1-y0)/5; ticks = [y0 + i*step for i in range(6)]
    for t in ticks:
        yy = Y(t); out.append(f'<line x1="{L}" x2="{w-R}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#e5e7eb"/>')
        lab = (f'${t/1000:.0f}k' if ref is None else (f'{t:.2g}x' if log else f'{t:.0%}'))
        out.append(f'<text x="{L-6}" y="{yy+4:.1f}" font-size="10" text-anchor="end" fill="#555">{lab}</text>')
    for i in range(0, 5):
        xv = x0 + (x1-x0)*i/4; out.append(f'<text x="{X(xv):.1f}" y="{h-12}" font-size="10" text-anchor="middle" fill="#555">{xv:.0f}</text>')
    out.append(f'<text x="{(L+w-R)/2:.0f}" y="{h-1}" font-size="10" text-anchor="middle" fill="#777">{html.escape(xlab)}</text>')
    if bands:
        for col, pts in bands:
            d = 'M' + ' L'.join(f'{X(x):.1f},{Y(lo):.1f}' for x, lo, hi in pts) + ' L' + ' L'.join(f'{X(x):.1f},{Y(hi):.1f}' for x, lo, hi in reversed(pts)) + ' Z'
            out.append(f'<path d="{d}" fill="{col}" fill-opacity="0.15" stroke="none"/>')
    for lab, col, pts, wd, dash in series:
        d = 'M' + ' L'.join(f'{X(x):.1f},{Y(y):.1f}' for x, y in pts if y > 0)
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{wd}" {DASH if dash else ""}/>')
    if markers:
        for x, y, col, txt in markers:
            out.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="3.5" fill="{col}"/>')
            if txt: out.append(f'<text x="{X(x)+5:.1f}" y="{Y(y)-5:.1f}" font-size="9" fill="{col}">{html.escape(txt)}</text>')
    # legend
    lx = L + 8; ly = T + 10
    for lab, col, pts, wd, dash in series:
        out.append(f'<line x1="{lx}" x2="{lx+16}" y1="{ly}" y2="{ly}" stroke="{col}" stroke-width="{wd}" {DASH if dash else ""}/><text x="{lx+20}" y="{ly+4}" font-size="10" fill="#333">{html.escape(lab)}</text>')
        lx += 26 + 6.2*len(lab)
    out.append('</svg>'); return '\n'.join(out)

def dd_series(vals):
    pk = vals[0]; out = []
    for i, v in enumerate(vals): pk = max(pk, v); out.append((i, -(1-v/pk)))
    return out

def svg_dd(series, w=900, h=150, title='drawdown from running peak'):
    L, R, T, Bm = 58, 14, 24, 26; ymin = min(p[1] for s in series for p in s[2]) - 0.02
    x1 = max(p[0] for s in series for p in s[2])
    X = lambda x: L + x/x1*(w-L-R); Y = lambda y: T + (0-y)/(0-ymin)*(h-T-Bm)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px;font-family:system-ui,sans-serif"><text x="{L}" y="14" font-size="12" font-weight="600" fill="#111">{html.escape(title)}</text>']
    for t in (0, -0.1, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7):
        if t >= ymin: out.append(f'<line x1="{L}" x2="{w-R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="#e5e7eb"/><text x="{L-6}" y="{Y(t)+4:.1f}" font-size="10" text-anchor="end" fill="#555">{t:.0%}</text>')
    for lab, col, pts, wd, dash in series:
        d = 'M' + ' L'.join(f'{X(x):.1f},{Y(y):.1f}' for x, y in pts)
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{wd}" {DASH if dash else ""}/>')
    out.append('</svg>'); return '\n'.join(out)

def spx_path(d0, n):
    ds = [d for d in sorted(spx) if d >= d0][:n+1]; return [(i, START*spx[d]/spx[ds[0]]) for i, d in enumerate(ds)]

def strip(hold, days, title, w=900):
    """holdings timeline strip: one row, colored segments by main holding."""
    cols = {}; palette = ['#1f5fa8', '#c2410c', '#0f766e', '#7c3aed', '#b45309', '#be123c', '#0891b2', '#4d7c0f', '#6b7280', '#a16207', '#9333ea', '#dc2626']
    out = [f'<svg viewBox="0 0 {w} 46" width="100%" style="max-width:{w}px;font-family:system-ui,sans-serif"><text x="0" y="11" font-size="11" font-weight="600" fill="#111">{html.escape(title)}</text>']
    n = len(days); x = lambda i: 110 + i/n*(w-120)
    for i, d in enumerate(days):
        key = '/'.join(f'{k}{int(round(v*100))}' for k, v in sorted(hold.get(d, {}).items(), key=lambda kv: -kv[1]))
        main = max(hold.get(d, {'?': 1}).items(), key=lambda kv: kv[1])[0]
        if main not in cols: cols[main] = palette[len(cols) % len(palette)]
        out.append(f'<rect x="{x(i):.1f}" y="16" width="{(w-120)/n+0.3:.2f}" height="18" fill="{cols[main]}"><title>{d}: {html.escape(key)}</title></rect>')
    lx = 110;
    for k, c in cols.items():
        out.append(f'<rect x="{lx}" y="38" width="9" height="7" fill="{c}"/><text x="{lx+12}" y="45" font-size="9" fill="#333">{k}</text>'); lx += 18 + 6*len(k)
    out.append('</svg>'); return '\n'.join(out)

def pct(x): return f'{x:+.0%}' if abs(x) >= 0.1 else f'{x:+.1%}'
def money(x): return f'${x/1000:,.0f}k'

# ---------------- COVID ----------------
prox = ['AQMIX', 'WTMF', 'FMF', 'DBMF', 'RYMFX', 'DBC']
cov = {p: B['covid'][f'{p}|from_today|composer|guards'] for p in prox}
n_cov = min(len(cov[p]['path']) for p in prox)
book_band = [(i, min(cov[p]['path'][i][1] for p in prox), max(cov[p]['path'][i][1] for p in prox)) for i in range(n_cov)]
ser = [('book (DBMF proxy)', PAL['book'], [(i, cov['DBMF']['path'][i][1]) for i in range(n_cov)], 2.2, False)]
for k, j in (('HG', 2), ('KMLM', 3), ('SLEEVE', 4), ('HARV', 5)):
    ser.append((k, PAL[k], [(i, cov['DBMF']['path'][i][j]/cov['DBMF']['path'][0][j]*START) for i in range(n_cov)], 1.2, False))
ser.append(('S&P 500', PAL['SPX'], spx_path('2020-02-19', n_cov-1), 1.4, True))
fires = [(next(i for i, p in enumerate(cov['DBMF']['path']) if p[0] == f['day']), cov['DBMF']['path'][next(i for i, p in enumerate(cov['DBMF']['path']) if p[0] == f['day'])][1], '#111', ('cap' if 'cap' in f['kind'] else 'band')) for f in cov['DBMF']['fires'][:12]]
covid_svg = '<h2>A. COVID-type crash from today ($303k, 2026-10-06 holdings)</h2><p class="note">Book across the four KMLM-proxy variants (shaded band; DBMF line), each engine indexed to $303k (DBMF proxy), S&amp;P 500 dashed. Dots: guard firings (cap-40 / sleeve band).</p>' + svg_lines(ser, title='',
                      bands=[(PAL['band'], book_band)], markers=fires)
covid_dd = svg_dd([('book (DBMF)', PAL['book'], dd_series([p[1] for p in cov['DBMF']['path'][:n_cov]]), 2, False),
                   ('book (DBC, worst proxy)', '#dc2626', dd_series([p[1] for p in cov['DBC']['path'][:n_cov]]), 1.4, True),
                   ('S&P 500', PAL['SPX'], dd_series([y for _, y in spx_path('2020-02-19', n_cov-1)]), 1.2, True)])
# holdings strips (crash month)
days_c = [d for d in C['covid']['DBMF']['HG']['days'] if '2020-02-19' <= d <= '2020-04-30']
strips = '\n'.join(strip(C['covid']['DBMF'][e]['hold'], days_c, f'{e} holdings, 2020-02-19 .. 04-30 (hover for exact weights)') for e in ('HG', 'KMLM', 'SLEEVE', 'HARV'))

# ---------------- GFC ----------------
gk = 'from_peak|KMLM=HG(conservative)|HARV=T-bill|SLEEVE=recon|guards'; ge = 'from_peak|KMLM=exhibit|HARV=exhibit|SLEEVE=recon|guards'; gkb = 'from_peak|KMLM=HG(conservative)|HARV=T-bill|SLEEVE=recon,vol-legs->BIL|guards'
gp = B['gfc'][gk]['path']; gpe = B['gfc'][ge]['path']; n_g = min(len(gp), len(gpe))
ser = [('book, conservative (KMLM=HG, HARV=T-bill)', PAL['book'], [(i, gp[i][1]) for i in range(n_g)], 2.2, False),
       ('book, mechanism exhibits (KMLM, HARV modelled)', '#60a5fa', [(i, gpe[i][1]) for i in range(n_g)], 1.2, True),
       ('HG (recon)', PAL['HG'], [(i, gp[i][2]/gp[0][2]*START) for i in range(n_g)], 1.2, False),
       ('SLEEVE (recon)', PAL['SLEEVE'], [(i, gp[i][4]/gp[0][4]*START) for i in range(n_g)], 1.2, False),
       ('book, sleeve vol legs -> BIL', '#0f766e', [(i, B['gfc'][gkb]['path'][i][1]) for i in range(min(n_g, len(B['gfc'][gkb]['path'])))], 1.2, True),
       ('S&P 500', PAL['SPX'], spx_path('2007-10-09', n_g-1), 1.4, True)]
gfc_svg = '<h2>B. 2008-type crash from today: daily hybrid replay from the 2007-10-09 peak</h2><p class="note">HG replayed on leveraged ETFs reconstructed from their real indices (fit 0.995-0.999). The sleeve is replayed the same way for its equity/bond legs, but its UVXY/SVXY legs come from a VIX term-structure model and carry most of its 2008 gain — the dashed line sets those legs to cash. Conservative book: KMLM = HG (house lens), HARV = T-bill. The light dashed line uses the KMLM/HARV mechanism exhibits (vol legs modelled before they existed; artefact-grade).</p>' + svg_lines(ser, title='')
gfc_dd = svg_dd([('book (conservative)', PAL['book'], dd_series([p[1] for p in gp[:n_g]]), 2, False), ('HG', PAL['HG'], dd_series([p[2] for p in gp[:n_g]]), 1.2, False),
                 ('SLEEVE', PAL['SLEEVE'], dd_series([p[4] for p in gp[:n_g]]), 1.2, False), ('S&P 500', PAL['SPX'], dd_series([y for _, y in spx_path('2007-10-09', n_g-1)]), 1.2, True)])
# ---------------- dotcom ----------------
dk = 'from_ndx_peak|KMLM=HG(conservative)|SLEEVE,HARV=T-bill|guards'; dp = B['dotcom'][dk]['path']; n_d = len(dp)
hgd = H['runs']['HG_dotcom']['rets']; dsd = [d for d in sorted(hgd) if d >= '2000-03-10']
hg_curve = [START];
for d in dsd[:n_d-1]: hg_curve.append(hg_curve[-1]*(1+hgd[d]))
ser = [('book (HG recon + KMLM=HG, sleeve/HARV = T-bill)', PAL['book'], [(i, dp[i][1]) for i in range(n_d)], 2.2, False),
       ('HG (recon)', PAL['HG'], [(i, v) for i, v in enumerate(hg_curve)], 1.3, False),
       ('S&P 500', PAL['SPX'], spx_path('2000-03-10', n_d-1), 1.4, True)]
dot_svg = '<h2>C. 2000-type crash from today: HG reconstructed through the dotcom bust (NDX peak 2000-03-10)</h2><p class="note">Only HG is replayable in kind (credit/vol ETFs did not exist). Book assumption: KMLM = HG (conservative), sleeve and HARV at the actual 13-week T-bill (~5.7%).</p>' + svg_lines(ser, title='')
dot_dd = svg_dd([('book', PAL['book'], dd_series([p[1] for p in dp]), 2, False), ('HG', PAL['HG'], dd_series(hg_curve), 1.2, False), ('S&P 500', PAL['SPX'], dd_series([y for _, y in spx_path('2000-03-10', n_d-1)]), 1.2, True)])

# ---------------- bootstrap fans ----------------
fans = []
for name, r in S['scenarios'].items():
    for lens, col in (('conservative', '#1f5fa8'), ('as_measured', '#9ca3af')):
        bal = r[lens]['balance']; hs = sorted(int(h) for h in bal)
        pts = [(0, START, START)] + [(h, bal[str(h)]['0.05'], bal[str(h)]['0.95']) for h in hs]
        med = [(0, START)] + [(h, bal[str(h)]['0.5']) for h in hs]
        fans.append((name, lens, col, pts, med))
fan_html = ''
for name in S['scenarios']:
    f = [x for x in fans if x[0] == name]
    ser = [(f'{lens} p50', col, med, 2 if lens == 'conservative' else 1.2, lens != 'conservative') for _, lens, col, pts, med in f]
    fan_html += svg_lines(ser, w=440, h=230, title=name, bands=[(col, pts) for _, lens, col, pts, med in f if lens == 'conservative'], xlab='months')

# ---------------- tables ----------------
def row_from_summary(s, label):
    cells = [label] + [f"{money(s[f'm{h}']['value'])} ({pct(s[f'm{h}']['ret'])})" if f'm{h}' in s else '—' for h in (3, 6, 9, 12)]
    return cells + [f"{s['maxdd']:.0%}", f"{s['worst_5d']:+.0%}" if s.get('worst_5d') is not None else '—']
rows = []
rng = lambda key: [B['covid'][f'{p}|{key}'] for p in prox]
for key, lab in (('from_today|composer|guards', 'COVID-type, from today\'s holdings, guards on'), ('from_today|composer|noguards', 'COVID-type, from today, guards OFF'), ('historical_state|composer|guards', 'COVID-type, engines in their Feb-2020 state, guards on')):
    ss = [b['summary'] for b in rng(key)]
    cells = [lab]
    for h in (3, 6, 9, 12):
        v = [s[f'm{h}']['value'] for s in ss if f'm{h}' in s]; cells.append(f"{money(min(v))} – {money(max(v))} ({pct(min(v)/START-1)} to {pct(max(v)/START-1)})")
    cells += [f"{min(s['maxdd'] for s in ss):.0%} – {max(s['maxdd'] for s in ss):.0%}", f"{min(s['worst_5d'] for s in ss):+.0%} to {max(s['worst_5d'] for s in ss):+.0%}"]
    rows.append(cells)
for key, lab in ((gk, '2008-type from the Oct-2007 peak — conservative: KMLM=HG, HARV=T-bill, sleeve recon, guards on'),
                 (gkb, '2008-type from peak — conservative, sleeve vol legs (UVXY/SVXY) set to cash'),
                 ('from_lehman|KMLM=HG(conservative)|HARV=T-bill|SLEEVE=recon|guards', '2008-type from Lehman (acute) — conservative, guards on'),
                 ('from_lehman|KMLM=HG(conservative)|HARV=T-bill|SLEEVE=recon,vol-legs->BIL|guards', '2008-type from Lehman — conservative, sleeve vol legs to cash'),
                 ('from_peak|KMLM=HG(conservative)|HARV=T-bill|SLEEVE=recon|noguards', '2008-type from peak — conservative, guards OFF')):
    rows.append(row_from_summary(B['gfc'][key]['summary'], lab))
for key, lab in ((dk, '2000-type from the NDX peak — HG recon, KMLM=HG, sleeve/HARV = T-bill, guards on'), ('acute|KMLM=HG(conservative)|SLEEVE,HARV=T-bill|guards', '2000-type from Sep-2000 (acute) — same assumptions')):
    rows.append(row_from_summary(B['dotcom'][key]['summary'], lab))
exh_rows = []
for key, lab in ((ge, '2008 from peak — KMLM and HARV mechanism exhibits'), ('from_lehman|KMLM=exhibit|HARV=exhibit|SLEEVE=recon|guards', '2008 from Lehman — KMLM and HARV mechanism exhibits'),
                 ('from_peak|KMLM=HG(conservative)|HARV=exhibit|SLEEVE=recon|guards', '2008 from peak — KMLM=HG, HARV exhibit')):
    exh_rows.append(row_from_summary(B['gfc'][key]['summary'], lab))
boot_rows = []
for name, r in S['scenarios'].items():
    for lens in ('conservative', 'as_measured'):
        bal = r[lens]['balance']; md = r[lens]['maxdd']
        boot_rows.append([f'{name} — {lens}'] + [f"{money(bal['12']['0.05'])} / {money(bal['12']['0.5'])} / {money(bal['12']['0.95'])}" if '12' in bal else '—',
                          f"{money(bal['3']['0.5'])} · {money(bal['6']['0.5'])} · {money(bal['9']['0.5'])}", f"{md['0.5']:.0%} / {md['0.95']:.0%}", f"{r[lens]['p_loss']['12']:.0%}", f"{r['spx_cum']:+.0%}"])
def table(head, rows, small=False):
    h = '<table class="t"><thead><tr>' + ''.join(f'<th>{html.escape(c)}</th>' for c in head) + '</tr></thead><tbody>'
    for r in rows: h += '<tr>' + ''.join(f'<td>{html.escape(str(c))}</td>' for c in r) + '</tr>'
    return h + '</tbody></table>'
imp_rows = []
for k, v in I.items():
    for wn, w in v['windows'].items():
        imp_rows.append([v['label'], wn, f"{w['base']['cum']:.2f}x / {w['base']['maxdd']:.0%}", f"{w['gated']['cum']:.2f}x / {w['gated']['maxdd']:.0%}", f"{w['gated']['cum']/w['base']['cum']-1:+.0%}",
                         (f"p{v['placebo']['real_percentile']*100:.0f} of 60 random gates" if 'placebo' in v and wn.startswith(('real era', 'crash')) else '')])
fid = C['fidelity']
page = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Crash simulations</title>
<style>:root{{--ink:#111;--bg:#fff}}body{{margin:0;padding:16px;font-family:system-ui,-apple-system,sans-serif;color:#111;background:#fff;max-width:960px;margin:auto;line-height:1.4}}
h1{{font-size:20px;margin:6px 0}}h2{{font-size:15px;margin:22px 0 6px}}p,li{{font-size:13px}}.t{{border-collapse:collapse;width:100%;font-size:11.5px;margin:6px 0 10px}}.t th{{text-align:left;background:#111;color:#fff;padding:5px 6px;font-weight:600}}.t td{{padding:4px 6px;border-bottom:1px solid #e5e7eb;vertical-align:top}}
.note{{font-size:12px;color:#444;background:#f3f4f6;padding:8px 10px;border-radius:6px}}.k{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px;margin:8px 0}}.k div{{border:1px solid #e5e7eb;border-radius:6px;padding:8px}}.k b{{font-size:17px}}.k span{{font-size:11px;color:#555}}
@media (prefers-color-scheme: dark){{body{{background:#0f1115;color:#e5e7eb}}.t td{{border-color:#2a2f3a}}.note{{background:#1b1f27;color:#cbd5e1}}.k div{{border-color:#2a2f3a}}.k span{{color:#9ca3af}}svg text{{fill:#d1d5db!important}}}}</style></head><body>
<h1>Crash simulations: COVID-type, 2008-type, 2000-type, applied to the live book ($303,140, 2026-10-06)</h1>
<p>Composer book 29/29/27/15 with the live trees, POLICY guards (cap-40, sleeve band with IBKR $346k held constant), Composer-equivalent costs. Day 0 = crash onset. Every number is a replay of rules on historical prices (real where the instruments existed, reconstructed on the underlying indices where they did not), never a forecast.</p>
<div class="k">
<div><span>COVID-type, 12 months, from today's holdings</span><br><b>{money(min(b['summary']['m12']['value'] for b in rng('from_today|composer|guards')))} – {money(max(b['summary']['m12']['value'] for b in rng('from_today|composer|guards')))}</b><br><span>worst 5 days {min(b['summary']['worst_5d'] for b in rng('from_today|composer|guards')):+.0%}; max DD {max(b['summary']['maxdd'] for b in rng('from_today|composer|guards')):.0%}</span></div>
<div><span>2008-type from peak, 12 months (conservative)</span><br><b>{money(B['gfc'][gk]['summary']['m12']['value'])}</b><br><span>max DD {B['gfc'][gk]['summary']['maxdd']:.0%}; from Lehman {money(B['gfc']['from_lehman|KMLM=HG(conservative)|HARV=exhibit|SLEEVE=recon|guards']['summary']['m12']['value'])}</span></div>
<div><span>2000-type from NDX peak, 12 months</span><br><b>{money(B['dotcom'][dk]['summary']['m12']['value'])}</b><br><span>max DD {B['dotcom'][dk]['summary']['maxdd']:.0%}; HG alone: see panel C</span></div>
<div><span>House lens (55y regime bootstrap, conservative), 12m p05 / p50</span><br><b>{money(S['scenarios']['GFC from peak (2007-10)']['conservative']['balance']['12']['0.05'])} / {money(S['scenarios']['GFC from peak (2007-10)']['conservative']['balance']['12']['0.5'])}</b><br><span>GFC sequence; max DD p95 {S['scenarios']['GFC from peak (2007-10)']['conservative']['maxdd']['0.95']:.0%} (monthly)</span></div></div>
<h2>Balances at 3 / 6 / 9 / 12 months (start $303,140)</h2>
{table(['scenario', '+3m', '+6m', '+9m', '+12m', 'max DD', 'worst 5d'], rows)}
<p class="note">COVID rows: range across six stand-ins for KMLM's regime flag (five managed-futures funds AQMIX/WTMF/FMF/DBMF/RYMFX, 78-84% day-agreement with the real flag, plus DBC — a long-only commodity index kept as the wrong-sign stress case). The flag is a coin-flip in a crash; the range is the honest answer. The 12-month multiples are the engines' in-sample reaction to the 2020 melt-up (HG and the sleeve were authored after 2020); the first 3-6 weeks are the stress-test part. Sims start from the live split (29/32/26/12), not the 29/29/27/15 targets. 2008/2000 rows: HG replayed daily on leveraged ETFs reconstructed from their real indices (fit 0.995-0.999; HG with every leg reconstructed vs real tickers 2015-26: corr 0.96, maxDD 42% vs 36%, level ~10%/yr pessimistic on average with ±15pp errors in single windows). The sleeve's equity/bond legs are reconstructed the same way; its UVXY/SVXY legs are a VIX term-structure model and carry most of its 2008 gain, hence the vol-legs-to-cash rows. KMLM and HARV have no measurable 2008/2000 behaviour (their vol legs did not exist): conservative rows set KMLM = HG (house lens) and HARV = T-bill; the mechanism exhibits are in the appendix table. The HG 12-month number from 2000-03-10 is window-fragile (+22% at 2001-03-09, −12% one session later when a biotech dip-buy lost 28%).</p>
<h3>Appendix: mechanism exhibits (artefact-grade — KMLM/HARV vol legs modelled before they existed)</h3>
{table(['scenario', '+3m', '+6m', '+9m', '+12m', 'max DD', 'worst 5d'], exh_rows)}
<h2>Regime bootstrap along each crash's actual month sequence (house method, add. 13)</h2>
{table(['sequence — lens', '12m p05 / p50 / p95', 'p50 at 3m · 6m · 9m', 'max DD p50 / p95 (monthly)', 'P(loss at 12m)', 'S&P over sequence'], boot_rows)}
<p class="note">Why the bootstrap is kinder than the daily replays: it draws each month independently from the engines' measured crash/chop buckets (short sharp 2018/2020/2022/2025 episodes that mean-reverted within weeks), so a 12-18 month crash sequence compounds spike-months with no give-back, and monthly resolution hides intra-month drawdowns (COVID replay DD 14-21% vs bootstrap monthly p95 6% as-measured / 23% conservative). Use it as the house ranking lens, not as the stress number.</p>
{covid_svg}{covid_dd}
<h2>Holdings through the COVID crash (what the gates actually did)</h2>{strips}
{gfc_svg}{gfc_dd}
{dot_svg}{dot_dd}
<h2>Bootstrap fans (conservative lens shaded; as-measured p50 dashed)</h2><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:6px">{fan_html}</div>
<h2>Improvement candidates, tested (base → gated; real era 2023-26 with placebo, COVID replay, 2000/2008 reconstructions)</h2>
{table(['candidate', 'window', 'base cum / maxDD', 'gated cum / maxDD', 'Δ cum', 'placebo'], imp_rows)}
<h2>Fidelity of the instruments used</h2>
<ul><li>Tree simulator vs Composer's own engine, real era 2023-26, real tickers: daily corr HG {fid['HG_real_realtickers']['corr']}, KMLM {fid['KMLM_real_realtickers']['corr']}, SLEEVE {fid['SLEEVE_real_realtickers']['corr']}, HARV {fid['HARV_real_realtickers']['corr']} (level gap = Composer's 5-bps slippage setting, ~3 bps/day, fitted and applied).</li>
<li>COVID window: HG sim vs Composer backtest corr {fid['HG_covid_vs_composer']['corr']}; sleeve (BOXX→BIL, KMLM→DBMF) {fid['SLEEVE_covid_vs_composer_DBMF']['corr']}. Composer's cost is its 5-bps slippage setting: 5.1 bps per unit sum|dw| charged on the trade day (10.2 bps per full switch, zero on no-trade days — addendum 38 confirmed), fitted per engine and applied to every replay.</li>
<li>Synthetic SVIX (from SVXY) corr 0.993 with the real product; synthetic ZVOL (from VXZ) 0.973 incl. backwardation days; KMLM regime-flag stand-ins 78-84% day agreement — the one unresolved input (KMLM real-era with a proxy flag: corr 0.75-0.84, i.e. the engine's edge is concentrated on exact flag timing).</li>
<li>VIX-ETP term-structure models (2008 sleeve vol legs and the exhibits): OOS 2019-26 corr 0.96-0.97 short-term, 0.89-0.90 mid-term; COVID spike captured ~77%. In 2008 the model runs mostly in backwardation (74% of Lehman-to-trough days vs 7% of its fit days), so the sleeve's 2008 vol-leg gain is model-driven — read the vol-legs-to-cash rows as the floor.</li>
<li>Improvement placebos: 60 random gate draws of matched size on scattered days — a weak null for a clustered gate; "no measurable effect" means inside that band, not "free".</li></ul>
<p class="note">Prepared 2026-10-07; corrected after the adversarial counter-agent review (two blocking defects fixed: a cold-start gap in the from-today sleeve, and a one-day misalignment in the cost model). Scripts: composer/research/crash/. Review log: results.md addendum 39.</p></body></html>'''
open(OUT, 'w').write(page); print('wrote', OUT, len(page))
