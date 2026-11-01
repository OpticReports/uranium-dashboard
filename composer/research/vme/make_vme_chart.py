#!/usr/bin/env python3
"""Exhibit for results.md addendum 51: Value and Momentum Everywhere read against this book.
Reads results/vme-2026-11-01.json (vme_study.py); writes results/vme-2026-11-01.html."""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")
SRC = os.path.join(RES, "vme-2026-11-01.json")
PAGE = os.path.join(RES, "vme-2026-11-01.html")


def growth(rets, months):
    out, eq = [], 1.0
    for m, r in zip(months, rets):
        if r is None:
            out.append(None)
            continue
        eq *= 1 + r
        out.append(round(eq, 4))
    return out


def main():
    r = json.load(open(SRC))
    fp = r["factor_paths"]
    combo = [(a + b) / 2 for a, b in zip(fp["VAL_ALL"], fp["MOM_ALL"])]
    # every 3rd month is enough for a 54-year line (the JSON keeps the monthly data)
    A = {"months": fp["months"], "series": {"Value everywhere": growth(fp["VAL_ALL"], fp["months"]),
                                            "Momentum everywhere": growth(fp["MOM_ALL"], fp["months"]),
                                            "50/50 combination": growth(combo, fp["months"]),
                                            "US stock value": growth(fp["VAL_US"], fp["months"])}}
    f = r["factors"]
    A["table"] = [[k, f[k]["paper"]["sharpe"], f[k]["since"]["sharpe"], f[k]["all"]["sharpe"], f[k]["all"]["maxdd"]]
                  for k in ("VAL_ALL", "MOM_ALL", "COMBO_ALL", "VAL_US", "MOM_US", "VAL_SS", "MOM_SS", "VAL_AA", "MOM_AA")]
    ex = r["exposure"]
    B = [{"name": n, "val": ex[n]["AQR everywhere"]["1997-2025"]["beta"]["VAL_ALL"], "mom": ex[n]["AQR everywhere"]["1997-2025"]["beta"]["MOM_ALL"],
          "tval": ex[n]["AQR everywhere"]["1997-2025"]["t"]["VAL_ALL"], "tmom": ex[n]["AQR everywhere"]["1997-2025"]["t"]["MOM_ALL"],
          "r2": ex[n]["AQR everywhere"]["1997-2025"]["r2"], "cv": ex[n]["AQR everywhere"]["1997-2025"]["corr"]["VAL_ALL"],
          "cm": ex[n]["AQR everywhere"]["1997-2025"]["corr"]["MOM_ALL"]} for n in ("book", "HG", "KMLM", "SLEEVE", "HARV", "SPY", "QQQ")]
    p = r["paths"]
    C = {"months": p["months"], "series": {"Momentum sleeve": growth(p["mom"], p["months"]), "Value sleeve": growth(p["val"], p["months"]),
                                           "50/50": growth(p["combo"], p["months"]), "SPY": growth(p["spy"], p["months"])},
         "stats": {k: v["2012-2026"] for k, v in r["buyable_vme"].items() if isinstance(v, dict) and "2012-2026" in v},
         "blend": r["buyable_vme"]["book blend 2012-2026"]}
    liq = r["liquidity"]["TED"]
    D = [{"name": n, "worse": liq[n]["next_month"]["worse"]["sharpe"], "better": liq[n]["next_month"]["better"]["sharpe"],
          "nw": liq[n]["next_month"]["worse"]["n"], "nb": liq[n]["next_month"]["better"]["n"], "beta_t": liq[n]["t"]}
         for n in ("book", "HG", "KMLM", "SLEEVE", "HARV", "SPY", "VAL_ALL", "MOM_ALL")]
    kpi = {"combo_paper": f["COMBO_ALL"]["paper"]["sharpe"], "combo_since": f["COMBO_ALL"]["since"]["sharpe"],
           "cv": B[0]["cv"], "cm": B[0]["cm"], "vme": C["stats"]["50/50"]["sharpe"], "spy": C["stats"]["SPY"]["sharpe"],
           "book_worse": D[0]["worse"], "book_better": D[0]["better"]}
    data = {"A": A, "B": B, "C": C, "D": D, "kpi": kpi, "generated": r["generated"]}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(PAGE, "w").write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Value and momentum vs the book</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--ctx:#b9b7ae;--band:rgba(42,120,214,.10)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--band:rgba(57,135,229,.14)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--band:rgba(57,135,229,.14)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 12px;font-size:14px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:0 0 16px;min-width:0}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0 16px}
@media (max-width:760px){.kpis{grid-template-columns:1fr 1fr}}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:22px;font-weight:650}.kpi span{color:var(--ink2);font-size:13px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 8px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}.sw{display:inline-block;width:14px;height:12px;border-radius:3px}
.chartwrap{overflow-x:auto}.chartwrap svg{min-width:680px}
svg{display:block;width:100%;height:auto}.ax{fill:var(--muted);font-size:11px}.lb{fill:var(--ink2);font-size:12px}.lbb{fill:var(--ink);font-size:12px;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--grid)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}.tablewrap{overflow-x:auto}
details{margin-top:8px;font-size:13.5px}summary{cursor:pointer;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:320px}
</style>
</head>
<body>
<main>
<h1>Value and momentum everywhere, read against this book</h1>
<p class="sub-h">Asness, Moskowitz and Pedersen (2013) find value and momentum premia in eight markets, negatively correlated with each other, so that a 50/50 blend has a far higher Sharpe than either. This page tests what that means for our four symphonies: AQR's own updated factor series (1972-2025), add. 47's book history (1997-2026, rebuilt prices before launch, the rules' own years after 2015), buyable ETF proxies, and FRED's funding-liquidity spreads.</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>A. The paper's factors, before and after it was published</h2>
<p class="sub-h">Growth of $1 in AQR's rank-weighted long-short factors (excess returns), log scale. The paper's sample ends July 2011 (marked). Both premia and their combination are thinner since.</p>
<div class="legend" id="lgA"></div>
<div class="chartwrap"><svg id="chA" role="img" aria-label="Cumulative growth of value, momentum, their 50/50 blend and US stock value, 1972 to 2025, log scale"></svg></div>
<details><summary>Table: Sharpe ratios (annualized, excess returns)</summary><div class="tablewrap"><table id="tbA"></table></div></details>
</section>

<section class="card">
<h2>B. Does the book carry value or momentum risk? No.</h2>
<p class="sub-h">Monthly excess returns 1997-2025 regressed on the market and AQR's value and momentum everywhere. Bars are the factor betas; labels carry the t-statistic (Newey-West). SPY and QQQ are controls: the market and growth load as they should, the book and its engines do not load on either factor.</p>
<div class="legend" id="lgB"></div>
<div class="chartwrap"><svg id="chB" role="img" aria-label="Value and momentum betas of the book, each engine, SPY and QQQ"></svg></div>
<details><summary>Table: betas, t-statistics, correlations, R-squared</summary><div class="tablewrap"><table id="tbB"></table></div></details>
</section>

<section class="card">
<h2>C. A buyable version: value and momentum on asset-class ETFs</h2>
<p class="sub-h">Nine ETFs (SPY EFA EEM IEF TLT GLD DBC VNQ UUP). Each month-end: the momentum sleeve holds the top 3 by 12-1 month return; the value sleeve the top 3 by the paper's non-stock value signal (the worst 5-year return); 50/50 of the two. Growth of $1 since 2012, log scale; SPY in gray for context.</p>
<div class="legend" id="lgC"></div>
<div class="chartwrap"><svg id="chC" role="img" aria-label="Growth of the momentum sleeve, value sleeve, their blend and SPY since 2012"></svg></div>
<details open><summary>Table: 2012-2026, monthly</summary><div class="tablewrap"><table id="tbC"></table></div></details>
</section>

<section class="card">
<h2>D. Funding liquidity as a gate? The book earns after liquidity worsens.</h2>
<p class="sub-h">The paper's liquidity shock (AR(2) residual of the TED spread, signed as liquidity), 1997-2022. Bars: the annualized Sharpe of each series in the month AFTER a worsening shock vs after an improving one. The factors behave as the paper says (value after worsening, momentum after improving); the book and every engine do better after worsening, so a de-risking gate would remove the months they earn.</p>
<div class="legend" id="lgD"></div>
<div class="chartwrap"><svg id="chD" role="img" aria-label="Next-month Sharpe after worsening versus improving funding-liquidity shocks, by series"></svg></div>
<details><summary>Table: next-month Sharpe and month counts; contemporaneous beta t-statistic</summary><div class="tablewrap"><table id="tbD"></table></div></details>
</section>

<section class="card notes">
<h2 style="color:var(--ink)">Basis and limits</h2>
<ul id="basis"></ul>
</section>
</main>
<div class="tt" id="tt"></div>
<script>
const D = __DATA__, NS = 'http://www.w3.org/2000/svg', tt = document.getElementById('tt');
function el(t, a, p, x){const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); if (x != null) e.textContent = x; p.appendChild(e); return e;}
function tip(ev, h){tt.innerHTML = h; tt.style.display = 'block'; tt.style.left = Math.min(ev.clientX + 12, innerWidth - tt.offsetWidth - 8) + 'px'; tt.style.top = ev.clientY + 12 + 'px';}
function untip(){tt.style.display = 'none';}
function legend(id, items){document.getElementById(id).innerHTML = items.map(([n, c]) => `<span><i class="sw" style="background:${c}"></i>${n}</span>`).join('');}
const f2 = v => v == null ? '–' : v.toFixed(2), pc = v => v == null ? '–' : (v * 100).toFixed(0) + '%';
const K = D.kpi;
[[`${f2(K.combo_paper)} → ${f2(K.combo_since)}`, `Sharpe of the 50/50 value+momentum factor: the paper's sample (1972-2011) → since (2011-2025)`],
 [`${K.cv >= 0 ? '+' : ''}${f2(K.cv)} / ${K.cm >= 0 ? '+' : ''}${f2(K.cm)}`, `the book's monthly correlation with value / momentum everywhere, 1997-2025: not a factor bet`],
 [`${f2(K.vme)} vs ${f2(K.spy)}`, `Sharpe of a buyable 50/50 value+momentum on asset-class ETFs vs SPY, 2012-2026`],
 [`${f2(K.book_worse)} vs ${f2(K.book_better)}`, `the book's next-month Sharpe after a worsening vs an improving funding-liquidity shock`]]
 .forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; k.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(k); });

function lineChart(svgId, months, series, colors, opts){
  const svg = document.getElementById(svgId), W = 900, H = 340, l = 50, r = 205, t = 14, b = 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const names = Object.keys(series), n = months.length;
  const vals = names.flatMap(k => series[k].filter(v => v != null));
  const lo = Math.log10(Math.min(...vals) * 0.95), hi = Math.log10(Math.max(...vals) * 1.05);
  const X = i => l + i / (n - 1) * (W - l - r), Y = v => t + (hi - Math.log10(v)) / (hi - lo) * (H - t - b);
  const ticks = []; for (let e = Math.floor(lo); e <= Math.ceil(hi); e++) [1, 2, 5].forEach(m => { const v = m * Math.pow(10, e); if (Math.log10(v) >= lo && Math.log10(v) <= hi) ticks.push(v); });
  ticks.forEach(v => { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, v >= 1 ? '$' + v : '$' + v.toFixed(2)); });
  const years = months.map((m, i) => [m, i]).filter(([m, i]) => m.endsWith('-01') && (+m.slice(0, 4)) % (opts.yearStep || 5) === 0);
  years.forEach(([m, i]) => el('text', {x: X(i), y: H - 8, 'text-anchor': 'middle', class: 'ax'}, svg, m.slice(0, 4)));
  if (opts.mark) { const i = months.indexOf(opts.mark); if (i >= 0) { el('line', {x1: X(i), x2: X(i), y1: t, y2: H - b, stroke: 'var(--axis)', 'stroke-dasharray': '4 4'}, svg); el('text', {x: X(i) + 4, y: H - b - 6, class: 'lb'}, svg, opts.markLabel); } }
  names.forEach(k => {
    const pts = series[k].map((v, i) => v == null ? null : `${X(i)},${Y(v)}`).filter(Boolean).join(' ');
    const ctx = (opts.context || []).includes(k);
    el('polyline', {points: pts, fill: 'none', stroke: colors[k], 'stroke-width': ctx ? 1.5 : 2, 'stroke-linejoin': 'round', opacity: ctx ? .9 : 1}, svg);
    const last = series[k].map((v, i) => [v, i]).filter(([v]) => v != null).pop();
    el('text', {x: W - r + 6, y: Y(last[0]) + 4, class: ctx ? 'lb' : 'lbb', fill: ctx ? 'var(--ink2)' : 'var(--ink)'}, svg, `${(opts.short || {})[k] || k} $${last[0] < 10 ? last[0].toFixed(2) : Math.round(last[0])}`);
  });
  // crosshair + tooltip
  const cross = el('line', {x1: 0, x2: 0, y1: t, y2: H - b, stroke: 'var(--axis)', opacity: 0}, svg);
  const zone = el('rect', {x: l, y: t, width: W - l - r, height: H - t - b, fill: 'transparent'}, svg);
  zone.addEventListener('mousemove', e => { const bb = svg.getBoundingClientRect(); const px = (e.clientX - bb.left) / bb.width * W; const i = Math.max(0, Math.min(n - 1, Math.round((px - l) / (W - l - r) * (n - 1))));
    cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.setAttribute('opacity', 1);
    tip(e, `<b>${months[i]}</b><br>` + names.map(k => series[k][i] == null ? '' : `${k}: $${series[k][i].toFixed(2)}`).filter(Boolean).join('<br>')); });
  zone.addEventListener('mouseleave', () => { cross.setAttribute('opacity', 0); untip(); });
}
// A
const colA = {'Value everywhere': 'var(--s1)', 'Momentum everywhere': 'var(--s2)', '50/50 combination': 'var(--s3)', 'US stock value': 'var(--s4)'};
legend('lgA', Object.entries(colA));
lineChart('chA', D.A.months, D.A.series, colA, {mark: '2011-07', markLabel: "paper's sample ends 2011-07", yearStep: 5, short: {'Value everywhere': 'Value', 'Momentum everywhere': 'Momentum', '50/50 combination': '50/50', 'US stock value': 'US stock value'}});
document.getElementById('tbA').innerHTML = '<thead><tr><th>Factor</th><th class="n">1972-2011 (paper)</th><th class="n">2011-2025</th><th class="n">1972-2025</th><th class="n">max drawdown</th></tr></thead><tbody>' +
  D.A.table.map(([k, a, b, c, d]) => `<tr><td>${k}</td><td class="n">${f2(a)}</td><td class="n">${f2(b)}</td><td class="n">${f2(c)}</td><td class="n">${pc(d)}</td></tr>`).join('') + '</tbody>';

// B: horizontal grouped bars around zero
(function(){
  const svg = document.getElementById('chB'), W = 900, rowH = 44, l = 90, r = 40, t = 10, H = D.B.length * rowH + t + 28;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const m = Math.max(1.5, ...D.B.flatMap(x => [Math.abs(x.val), Math.abs(x.mom)])) * 1.4;
  const X = v => l + (v + m) / (2 * m) * (W - l - r);
  for (let v = -Math.floor(m); v <= Math.floor(m); v += 0.5) { el('line', {x1: X(v), x2: X(v), y1: t, y2: H - 28, stroke: v === 0 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: X(v), y: H - 10, 'text-anchor': 'middle', class: 'ax'}, svg, v.toFixed(1)); }
  D.B.forEach((x, i) => {
    const y = t + i * rowH;
    el('text', {x: l - 10, y: y + 24, 'text-anchor': 'end', class: 'lbb'}, svg, x.name);
    [['val', 'tval', 'var(--s1)', 0, 'value'], ['mom', 'tmom', 'var(--s2)', 1, 'momentum']].forEach(([k, tk, c, j, nm]) => {
      const v = x[k], yy = y + 4 + j * 18, x0 = X(Math.min(0, v)), w = Math.abs(X(v) - X(0));
      const rr = el('rect', {x: x0, y: yy, width: Math.max(w, 1), height: 14, rx: 2, fill: c}, svg);
      el('text', {x: v >= 0 ? X(v) + 5 : X(v) - 5, y: yy + 11, 'text-anchor': v >= 0 ? 'start' : 'end', class: 'ax'}, svg, `${v >= 0 ? '+' : ''}${v.toFixed(2)} [t ${x[tk].toFixed(1)}]`);
      rr.addEventListener('mousemove', e => tip(e, `<b>${x.name}</b> beta to ${nm}: ${v.toFixed(2)} (t ${x[tk].toFixed(1)})<br>correlation ${(nm === 'value' ? x.cv : x.cm).toFixed(2)}; model R² ${x.r2.toFixed(2)}`)); rr.addEventListener('mouseleave', untip);
    });
  });
  legend('lgB', [['beta to value everywhere', 'var(--s1)'], ['beta to momentum everywhere', 'var(--s2)']]);
  document.getElementById('tbB').innerHTML = '<thead><tr><th>Series</th><th class="n">β value</th><th class="n">t</th><th class="n">β momentum</th><th class="n">t</th><th class="n">corr value</th><th class="n">corr momentum</th><th class="n">R²</th></tr></thead><tbody>' +
    D.B.map(x => `<tr><td>${x.name}</td><td class="n">${f2(x.val)}</td><td class="n">${x.tval.toFixed(1)}</td><td class="n">${f2(x.mom)}</td><td class="n">${x.tmom.toFixed(1)}</td><td class="n">${f2(x.cv)}</td><td class="n">${f2(x.cm)}</td><td class="n">${f2(x.r2)}</td></tr>`).join('') + '</tbody>';
})();

// C
const colC = {'Momentum sleeve': 'var(--s2)', 'Value sleeve': 'var(--s1)', '50/50': 'var(--s3)', 'SPY': 'var(--ctx)'};
legend('lgC', Object.entries(colC));
lineChart('chC', D.C.months, D.C.series, colC, {context: ['SPY'], yearStep: 2, short: {'Momentum sleeve': 'Momentum', 'Value sleeve': 'Value'}});
(function(){
  const S = D.C.stats, order = ['MOM sleeve', 'VAL sleeve', '50/50', 'equal weight', '60/40', 'SPY', 'book'];
  document.getElementById('tbC').innerHTML = '<thead><tr><th>Series</th><th class="n">CAGR</th><th class="n">vol</th><th class="n">Sharpe</th><th class="n">max DD</th><th class="n">corr book</th><th class="n">corr SPY</th></tr></thead><tbody>' +
    order.filter(k => S[k]).map(k => { const s = S[k]; return `<tr><td>${k}</td><td class="n">${pc(s.cagr)}</td><td class="n">${pc(s.vol_ann)}</td><td class="n">${f2(s.sharpe)}</td><td class="n">${pc(s.maxdd)}</td><td class="n">${s.corr_book == null ? '–' : f2(s.corr_book)}</td><td class="n">${f2(s.corr_spy)}</td></tr>`; }).join('') +
    `<tr><td colspan="7" style="color:var(--ink2)">Book with the 50/50 blended in, 2012-2026: ` + Object.entries(D.C.blend).map(([w, v]) => `${Math.round(w * 100)}% → Sharpe ${f2(v.sharpe)}, DD ${pc(v.maxdd)}, CAGR ${pc(v.cagr)}`).join('; ') + '</td></tr></tbody>';
})();

// D: grouped vertical bars
(function(){
  const svg = document.getElementById('chD'), W = 900, H = 300, l = 50, r = 12, t = 16, b = 40, n = D.D.length;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const vals = D.D.flatMap(x => [x.worse, x.better]), lo = Math.min(0, ...vals) - 0.2, hi = Math.max(...vals) + 0.3;
  const gw = (W - l - r) / n, bw = gw * 0.34, Y = v => t + (hi - v) / (hi - lo) * (H - t - b);
  for (let v = Math.ceil(lo * 2) / 2; v <= hi; v += 0.5) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: v === 0 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, v.toFixed(1)); }
  D.D.forEach((x, i) => {
    const cx = l + i * gw + gw / 2;
    [['worse', 'var(--s1)', -1, x.nw, 'after a worsening shock'], ['better', 'var(--s2)', 1, x.nb, 'after an improving shock']].forEach(([k, c, s, cnt, nm]) => {
      const v = x[k], xx = cx + (s < 0 ? -bw - 1 : 1), y0 = Y(Math.max(0, v)), h = Math.abs(Y(v) - Y(0));
      const rr = el('rect', {x: xx, y: y0, width: bw, height: Math.max(h, 1), rx: 2, fill: c}, svg);
      el('text', {x: xx + bw / 2, y: v >= 0 ? y0 - 4 : y0 + h + 12, 'text-anchor': 'middle', class: 'ax'}, svg, v.toFixed(2));
      rr.addEventListener('mousemove', e => tip(e, `<b>${x.name}</b> ${nm}: next-month Sharpe ${v.toFixed(2)} (${cnt} months)<br>contemporaneous beta t-stat ${x.beta_t.toFixed(1)}`)); rr.addEventListener('mouseleave', untip);
    });
    el('text', {x: cx, y: H - 14, 'text-anchor': 'middle', class: 'lbb'}, svg, x.name);
  });
  legend('lgD', [['next month after a WORSENING liquidity shock', 'var(--s1)'], ['next month after an IMPROVING shock', 'var(--s2)']]);
  document.getElementById('tbD').innerHTML = '<thead><tr><th>Series</th><th class="n">Sharpe after worsening</th><th class="n">months</th><th class="n">Sharpe after improving</th><th class="n">months</th><th class="n">beta t (same month)</th></tr></thead><tbody>' +
    D.D.map(x => `<tr><td>${x.name}</td><td class="n">${f2(x.worse)}</td><td class="n">${x.nw}</td><td class="n">${f2(x.better)}</td><td class="n">${x.nb}</td><td class="n">${x.beta_t.toFixed(1)}</td></tr>`).join('') + '</tbody>';
})();

['Factors: AQR, "Value and Momentum Everywhere: Factors, Monthly" (the paper\'s rank-weighted long-short factors, updated to 2025-12; the paper\'s Table I reports 1.42 (P3-P1) and 1.59 (factor) for the global 50/50 with equal-volatility weights across asset classes; AQR\'s published everywhere series gives 1.25 on the same dates). US stock value and momentum are the US90 series. Risk-free rate and market: Ken French.',
 'Book: add. 47\'s rebuilt four-engine history, weekly points turned into calendar-month returns, 1997-01 to 2025-12; prices before each fund\'s launch are proxies, and the rules were built on 2015-2026, so the book\'s own Sharpe there (2.1) is in sample. The regressions ask only what its returns covary with.',
 'Buyable VME: Yahoo monthly adjusted closes; the universe, top-3 rule and 12-1 / 5-year signals follow the paper and were not tuned (and no alternatives were tried). 2012-2026 is one US-equity-led period. Long-only sleeves carry market beta (corr with SPY 0.5-0.65); the paper\'s factors are long-short and market neutral.',
 'Liquidity: FRED TEDRATE (ends 2022-01), monthly average, signed as liquidity (-TED), AR(2) residual as in the paper. "Worsening" = a negative shock this month; the bars are the next month\'s returns, so this is a gate test, not the paper\'s contemporaneous regression. 1997-2022, about 150 months a leg: differences of 0.3-0.5 in Sharpe are within noise.',
 `Generated ${D.generated}. Research only; no symphony changed.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
