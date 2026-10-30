#!/usr/bin/env python3
"""Exhibit for results.md addendum 49: the pre-close preview's lead-time study. Reads
results/preclose-leadtime-2026-10-30.json (leadtime.py); writes results/preclose-leadtime-2026-10-30.html."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import preclose as pc  # noqa: E402
import shadow_runner as sr  # noqa: E402

RES = os.path.join(HERE, "..", "..", "results")
SRC = os.path.join(RES, "preclose-leadtime-2026-10-30.json")
PAGE = os.path.join(RES, "preclose-leadtime-2026-10-30.html")
ENGINES = ["HG", "KMLM", "SLEEVE", "HARV"]
SAMPLE = """PRE-CLOSE 2026-10-30 15:27 ET: Composer decides ~15:50 (23 min); SPY -2.15% today
GATE   open (as at yesterday's close): SPY 752.78 vs 200-day 725.97; flips at 725.83 (-3.58%, 45.8 sigma); stale: SPY 14:32 -> via IVV
HG     $86,900 BIL 100% -> QLD 100% ($86,900 moves). could flip: QLD +0.44% (1.4 sigma) -> USD 100%; stale: SMH 14:32 (no fresh sibling: last price used)
KMLM   $92,144 TECL 38%, SOXL 33%, PULS 30% -> TECL 75%, ZVOL 15%, PULS 10% ($48,205 moves). could flip: TQQQ +0.87% (1.9 sigma) -> SOXL 75%, ZVOL 15%, PULS 10%; largest gap 37.3% vs the 10% trigger; stale: SPY 14:32 -> via IVV, VOOV 15:12 (no fresh sibling: last price used)
SLEEVE $81,666 no change (BOXX 100%). firm (no one-ticker move within 3 sigma); stale: CORP 14:27, PEJ 15:00, SHY 14:31 (no fresh sibling: last price used)
HARV   $37,350 PULS 100% -> ZVOL 60%, PULS 40% ($22,410 moves). firm (no one-ticker move within 3 sigma); stale: SPY 14:32 -> via IVV

1 ALERT(S):
  !! BIG DAY — SPY -2.15% at 15:27 ET. What the rebalance at ~15:50 will do is in the preview; overrides are the owner's call in the Composer app."""


def main():
    r = json.load(open(SRC))
    scale = r["labels_1515"]["measured_scale"]
    cells = []
    for x in r["rows"]:
        if x["status"] != "ok" or "15:15" not in x["dist"] or "target_1515" not in x:
            cells.append({"d": x["date"], "e": x["engine"], "l": "n/a"})
            continue
        fl = x.get("flip")
        sig = fl["sigma"] / scale if fl else None
        lab = pc.label({"sigma": sig} if sig is not None and sig <= pc.FLIP_MAX else None)
        cells.append({"d": x["date"], "e": x["engine"], "l": lab, "ch": x["dist"]["15:15"],
                      "a": sr.fmt_w(x["target_1515"]), "b": sr.fmt_w(x["target_1550"]),
                      "f": fl and sig <= pc.FLIP_MAX and {"t": fl["ticker"], "m": fl["move"], "s": round(sig, 2)}})
    data = {"times": r["times"], "acc": r["accuracy"], "lab": r["labels_1515"]["measured"],
            "lab_sqrt": r["labels_1515"]["sqrt_t"], "scale": scale, "moves": r["moves_to_1550"],
            "hist": r["z_hist_1515_liquid"], "cells": cells, "dates": sorted({c["d"] for c in cells}),
            "window": r["sessions"], "n_sessions": r["n_sessions"], "gate_open": r["gate_open_1550"],
            "gate_flips": r["gate_flips_vs_1550"], "sample": SAMPLE, "material": pc.FLIP_MATERIAL}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(PAGE, "w") as f:
        f.write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pre-close preview study</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--firm:#d3d2cb;--warn:#fab219;--serious:#ec835a;--crit:#d03b3b;--code:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--firm:#3b3b38;--code:#232321}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--firm:#3b3b38;--code:#232321}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}
h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 12px;font-size:14px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:0 0 16px;min-width:0}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0 16px}
@media (max-width:820px){.kpis{grid-template-columns:1fr 1fr}}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px;min-width:0;overflow-wrap:anywhere}
.kpi b{display:block;font-size:22px;font-weight:650}
.kpi span{color:var(--ink2);font-size:13px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:820px){.two{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--grid);vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}
.tablewrap{overflow-x:auto}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 8px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{display:inline-block;width:14px;height:12px;border-radius:3px;border:1px solid var(--ring)}
.ln{display:inline-block;width:16px;height:2px;border-radius:1px}
svg{display:block;width:100%;height:auto;overflow:visible}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.scroll svg{min-width:640px}
.tt{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:5;max-width:340px}
.tt .d{color:var(--ink2);margin-bottom:3px}
.axis text,text.axis{fill:var(--muted);font-size:11px}
.lbl{fill:var(--ink2);font-size:12px}
.lblb{fill:var(--ink);font-size:12px;font-weight:600}
.notes{font-size:13.5px;color:var(--ink2)}
.notes li{margin:3px 0}
pre{background:var(--code);border-radius:8px;padding:10px 12px;font-size:12.5px;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0 10px}
</style>
</head>
<body>
<main class="viz-root">
<h1>Pre-close preview: how well does a 15:15 read call the 15:50 rebalance?</h1>
<p class="sub-h">Composer decides each symphony's holdings at about 15:50 ET on live prices. The preview runs the same approved logic 35 minutes earlier, so a change can be seen, and acted on if the owner chooses, before it happens. Below: 59 sessions of 5-minute prices replayed through each engine's logic at five minutes of the afternoon.</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>The earlier the read, the more often the answer moves</h2>
<p class="sub-h">Share of engine-sessions where the logic's answer at each minute equals its answer at 15:50 (all four engines pooled; 15:50 is the reference, 100% by construction). Hover a point for the counts; the table splits it by engine.</p>
<div class="legend" id="lg-acc"></div>
<div class="scroll"><svg id="acc" role="img" aria-label="Line chart: share of engine-sessions whose answer at 15:00, 15:15, 15:30 and 15:40 equals the 15:50 answer"></svg></div>
<div class="tablewrap" style="margin-top:10px"><table id="acc-t"></table></div>
</section>

<div class="two">
<section class="card">
<h2>The 15:15 labels: where the misses sat</h2>
<p class="sub-h">Each engine-session's label at 15:15 (the nearest one-ticker move that changes a quarter of the holdings, in sigmas of the move left), and how many then changed materially by 15:50.</p>
<div class="legend" id="lg-lab"></div>
<svg id="lab" role="img" aria-label="Bars: sessions per 15:15 label, with the ones that changed materially by 15:50"></svg>
</section>
<section class="card">
<h2>The last 35 minutes move about half as much as a daily sigma implies</h2>
<p class="sub-h">15:15 to 15:50 move of every decision ticker (liquid ones, ~2,200 ticker-sessions), in units of the plain random-walk scale: daily sigma &times; &radic;(35/390). The spread is 0.52 of that; the preview uses 0.52.</p>
<svg id="hist" role="img" aria-label="Histogram of 35-minute moves in random-walk units, with the measured spread and the assumed one marked"></svg>
<div class="tablewrap" style="margin-top:8px"><table id="mv-t"></table></div>
</section>
</div>

<section class="card">
<h2>Session by session</h2>
<p class="sub-h">Each cell is one engine on one session, shaded by its 15:15 label. A red cross marks the sessions where the 15:50 answer differed materially (a quarter or more of the holdings); a dot marks a smaller change. Hover for the 15:15 and 15:50 answers.</p>
<div class="legend" id="lg-strip"></div>
<div class="scroll"><svg id="strip" role="img" aria-label="Grid of sessions by engine, shaded by the 15:15 label, with material changes marked"></svg></div>
</section>

<section class="card">
<h2>What arrives at 15:15</h2>
<p class="sub-h">The first live read (2026-10-30, a -2% day; run at 15:27 ET while the feature was being built). Yahoo's quotes for 11 tickers were ~50 minutes stale that afternoon, so the preview rebuilt SPY from IVV and named the stale ones it could not rebuild.</p>
<pre id="sample"></pre>
</section>

<section class="card notes">
<h2 style="color:var(--ink)">Basis and limits</h2>
<ul id="basis"></ul>
</section>
</main>
<div class="tt" id="tt" role="status" aria-live="polite"></div>
<script>
const D = __DATA__;
const tt = document.getElementById('tt');
function tip(ev, html){tt.innerHTML = html; tt.style.display='block';
  const x = Math.min(ev.clientX + 14, window.innerWidth - tt.offsetWidth - 8), y = Math.min(ev.clientY + 14, window.innerHeight - tt.offsetHeight - 8);
  tt.style.left = x + 'px'; tt.style.top = y + 'px';}
function untip(){tt.style.display='none';}
const NS = 'http://www.w3.org/2000/svg';
function el(tag, attrs, parent, text){const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; if (parent) parent.appendChild(e); return e;}
const pct = (a, b) => (100 * a / b).toFixed(1) + '%';
const LB = {'firm': ['var(--firm)', 'firm (> 2σ)'], 'could flip': ['var(--warn)', 'could flip (1-2σ)'], 'coin-flip': ['var(--serious)', 'coin-flip (≤ 1σ)'], 'n/a': ['transparent', 'no 15:15 read']};
const A = D.acc.all, t15 = A['15:15'], L = D.lab;
const nLab = k => (L[k] || {n: 0}).n, mLab = k => (L[k] || {material: 0}).material;

// KPIs
[[`${t15.same} / ${t15.n}`, `engine-sessions where the 15:15 answer equals 15:50's (${pct(t15.same, t15.n)}); ${t15.no_material} with no material change`],
 [`${mLab('coin-flip')} of ${nLab('coin-flip')}`, `coin-flip calls that changed materially by 15:50; ${mLab('firm') + mLab('could flip')} of ${nLab('firm') + nLab('could flip')} firm or could-flip calls did`],
 [`${D.scale.toFixed(2)}×`, `the measured late-session move against the random-walk scale from a daily sigma (0.52-0.57 from 10 to 50 minutes)`],
 [`${D.gate_open} / ${D.n_sessions}`, `sessions with HG's gate open at 15:50: no gate crossing in this window, so gate timing is not tested here`]]
 .forEach(([b, s]) => { const d = document.createElement('div'); d.className = 'kpi'; d.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(d); });

// accuracy line chart
(function(){
  const svg = document.getElementById('acc'), W = 1060, H = 260, l = 54, r = 150, t = 16, b = 34;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const xs = D.times, x = i => l + i * (W - l - r) / (xs.length - 1), y = v => t + (1 - (v - 0.94) / 0.06) * (H - t - b);
  [0.94, 0.96, 0.98, 1.0].forEach(v => { el('line', {x1: l, x2: W - r, y1: y(v), y2: y(v), stroke: 'var(--grid)'}, svg);
    el('text', {x: l - 8, y: y(v) + 4, 'text-anchor': 'end', class: 'axis'}, svg).textContent = (v * 100).toFixed(0) + '%'; });
  xs.forEach((tm, i) => el('text', {x: x(i), y: H - 12, 'text-anchor': 'middle', class: 'axis'}, svg, tm + ' ET'));
  const S = [['same', 'var(--s1)', 'same holdings (within 3%)'], ['no_material', 'var(--s2)', 'no material change (under 25%)']];
  S.forEach(([k, c, name]) => {
    document.getElementById('lg-acc').insertAdjacentHTML('beforeend', `<span><i class="ln" style="background:${c}"></i>${name}</span>`);
    const pts = xs.map((tm, i) => [x(i), y(A[tm][k] / A[tm].n)]);
    el('polyline', {points: pts.map(p => p.join(',')).join(' '), fill: 'none', stroke: c, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
    xs.forEach((tm, i) => { const [px, py] = pts[i];
      el('circle', {cx: px, cy: py, r: 4.5, fill: c, stroke: 'var(--surface)', 'stroke-width': 2}, svg);
      el('circle', {cx: px, cy: py, r: 14, fill: 'transparent'}, svg).addEventListener('mousemove', ev =>
        tip(ev, `<div class="d">${tm} ET vs 15:50</div><b>${name}</b><br>${A[tm][k]} of ${A[tm].n} engine-sessions (${pct(A[tm][k], A[tm].n)})`));
      svg.lastChild.addEventListener('mouseleave', untip); });
    const last = pts[1];
    el('text', {x: W - r + 10, y: y(A[xs[xs.length - 2]][k] / A[xs[xs.length - 2]].n) + (k === 'same' ? 12 : -4), class: 'lbl'}, svg,
       k === 'same' ? 'same holdings' : 'no material change');
  });
  const x15 = x(1);
  el('line', {x1: x15, x2: x15, y1: t, y2: H - b, stroke: 'var(--ink2)', 'stroke-dasharray': '3 3'}, svg);
  el('text', {x: x15 + 6, y: t + 10, class: 'lbl'}, svg, 'the preview runs here (35 min before)');
  const tb = document.getElementById('acc-t');
  tb.innerHTML = '<thead><tr><th>Engine</th>' + xs.slice(0, -1).map(tm => `<th class="n">${tm}: same / no material / n</th>`).join('') + '</tr></thead><tbody>' +
    Object.entries(D.acc).map(([e, v]) => `<tr><td>${e === 'all' ? '<b>all</b>' : e}</td>` + xs.slice(0, -1).map(tm => `<td class="n">${v[tm].same} / ${v[tm].no_material} / ${v[tm].n}</td>`).join('') + '</tr>').join('') + '</tbody>';
})();

// label bars
(function(){
  const svg = document.getElementById('lab'), W = 520, rowH = 34, l = 118, r = 120, t = 6, ks = ['firm', 'could flip', 'coin-flip'];
  const H = t + ks.length * rowH + 22, max = Math.max(...ks.map(nLab));
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const sx = v => (W - l - r) * v / max;
  document.getElementById('lg-lab').innerHTML = `<span><i class="sw" style="background:var(--s1)"></i>unchanged or under 25% by 15:50</span><span><i class="sw" style="background:var(--crit)"></i>changed materially by 15:50</span>`;
  ks.forEach((k, i) => { const y = t + i * rowH, n = nLab(k), m = mLab(k);
    el('text', {x: l - 10, y: y + 17, 'text-anchor': 'end', class: 'lblb'}, svg, k);
    const w1 = sx(n - m), w2 = sx(m);
    el('rect', {x: l, y: y + 4, width: Math.max(0, w1 - (m ? 1 : 0)), height: 20, rx: 0, fill: 'var(--s1)'}, svg);
    if (m) el('rect', {x: l + w1 + 1, y: y + 4, width: Math.max(2, w2 - 1), height: 20, fill: 'var(--crit)'}, svg);
    el('text', {x: l + sx(n) + 8, y: y + 18, class: 'lbl'}, svg, `${m} of ${n} changed`);
    el('rect', {x: l, y, width: W - l, height: rowH, fill: 'transparent'}, svg).addEventListener('mousemove', ev =>
      tip(ev, `<div class="d">labelled ${k} at 15:15</div>${n} engine-sessions<br>${m} changed materially by 15:50 (${n ? pct(m, n) : '-'})<br>${(L[k] || {}).changed || 0} changed at all (over 3%)`));
    svg.lastChild.addEventListener('mouseleave', untip); });
  el('text', {x: l, y: H - 4, class: 'axis'}, svg, `engine-sessions, 15:15 reads (sigma scale ${D.scale})`);
})();

// histogram
(function(){
  const svg = document.getElementById('hist'), W = 520, H = 230, l = 40, r = 10, t = 22, b = 30, h = D.hist;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const n = h.counts.length, lo = h.edges[0], hi = h.edges[n], max = Math.max(...h.counts);
  const x = v => l + (v - lo) / (hi - lo) * (W - l - r), y = c => t + (1 - c / max) * (H - t - b);
  [0, Math.round(max / 2), max].forEach(c => { el('line', {x1: l, x2: W - r, y1: y(c), y2: y(c), stroke: 'var(--grid)'}, svg);
    el('text', {x: l - 6, y: y(c) + 4, 'text-anchor': 'end', class: 'axis'}, svg, c); });
  h.counts.forEach((c, i) => { const x0 = x(h.edges[i]) + 1, w = Math.max(1, x(h.edges[i + 1]) - x(h.edges[i]) - 2);
    if (c) el('path', {d: `M${x0},${y(0)}V${y(c) + 3}q0,-3 3,-3h${Math.max(0, w - 6)}q3,0 3,3V${y(0)}Z`, fill: 'var(--s1)'}, svg);
    el('rect', {x: x0 - 1, y: t, width: w + 2, height: H - t - b, fill: 'transparent'}, svg).addEventListener('mousemove', ev =>
      tip(ev, `<div class="d">move ${h.edges[i].toFixed(1)} to ${h.edges[i + 1].toFixed(1)} random-walk sigmas</div>${c} ticker-sessions`));
    svg.lastChild.addEventListener('mouseleave', untip); });
  [[-3, '-3'], [-1, '-1'], [0, '0'], [1, '+1'], [3, '+3']].forEach(([v, s]) => el('text', {x: x(v), y: H - 12, 'text-anchor': 'middle', class: 'axis'}, svg, s));
  [[D.scale, 'var(--ink)', `measured ±${D.scale}`], [1, 'var(--muted)', 'assumed ±1']].forEach(([v, c, s], j) => {
    [-v, v].forEach(z => el('line', {x1: x(z), x2: x(z), y1: t - 4, y2: y(0), stroke: c, 'stroke-dasharray': j ? '3 3' : '0'}, svg));
    el('text', {x: x(v) + 4, y: t - 8 + j * 12 + 12 * j, class: 'lbl'}, svg, s); });
  const mt = document.getElementById('mv-t'), M = D.moves.liquid;
  mt.innerHTML = '<thead><tr><th>minutes to 15:50</th><th class="n">n</th><th class="n">measured / √t</th><th class="n">p95, p99 in rms</th></tr></thead><tbody>' +
    Object.entries(M).map(([k, v]) => `<tr><td>${k.replace(' min', '')}</td><td class="n">${v.n.toLocaleString()}</td><td class="n">${v.scale.toFixed(2)}</td><td class="n">${v.p95_over_rms}, ${v.p99_over_rms}</td></tr>`).join('') + '</tbody>';
})();

// session strip
(function(){
  const svg = document.getElementById('strip'), L0 = 62, T = 10, W = 1060, cw = (W - L0 - 8) / D.dates.length, ch = 22, gap = 2;
  const H = T + ENG.length * (ch + gap) + 26;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  ['firm', 'could flip', 'coin-flip'].forEach(k => document.getElementById('lg-strip').insertAdjacentHTML('beforeend', `<span><i class="sw" style="background:${LB[k][0]}"></i>${LB[k][1]}</span>`));
  document.getElementById('lg-strip').insertAdjacentHTML('beforeend', `<span style="color:var(--ink)">✕ changed materially by 15:50</span><span style="color:var(--ink)">• changed under 25%</span>`);
  const by = {}; D.cells.forEach(c => by[c.e + c.d] = c);
  ENG.forEach((e, i) => el('text', {x: L0 - 8, y: T + i * (ch + gap) + ch / 2 + 4, 'text-anchor': 'end', class: 'lblb'}, svg, e));
  ENG.forEach((e, i) => D.dates.forEach((d, j) => {
    const c = by[e + d], x = L0 + j * cw, y = T + i * (ch + gap);
    if (!c) return;
    el('rect', {x: x + 1, y, width: Math.max(1, cw - 2), height: ch, rx: 3, fill: LB[c.l][0], stroke: c.l === 'n/a' ? 'var(--grid)' : 'none'}, svg);
    if (c.ch >= D.material) el('text', {x: x + cw / 2, y: y + ch / 2 + 5, 'text-anchor': 'middle', fill: 'var(--crit)', 'font-size': 14, 'font-weight': 700}, svg, '✕');
    else if (c.ch > 0.03) el('circle', {cx: x + cw / 2, cy: y + ch / 2, r: 3, fill: 'var(--ink)'}, svg);
    el('rect', {x, y: y - 1, width: cw, height: ch + 2, fill: 'transparent'}, svg).addEventListener('mousemove', ev => {
      let s = `<div class="d">${d} · ${e}</div><b>${LB[c.l][1]}</b>`;
      if (c.l !== 'n/a') { s += `<br>15:15 logic: ${c.a}<br>15:50 logic: ${c.b}`;
        if (c.f) s += `<br>nearest flip: ${c.f.t} ${(100 * c.f.m).toFixed(2)}% (${c.f.s}σ)`;
        s += `<br>difference by 15:50: ${(100 * c.ch).toFixed(0)}%`; }
      tip(ev, s); });
    svg.lastChild.addEventListener('mouseleave', untip);
  }));
  let last = '';
  D.dates.forEach((d, j) => { const m = d.slice(0, 7); if (m !== last) { last = m; const x = L0 + j * cw;
    el('line', {x1: x, x2: x, y1: T + ENG.length * (ch + gap), y2: T + ENG.length * (ch + gap) + 6, stroke: 'var(--axis)'}, svg);
    el('text', {x: x + 2, y: T + ENG.length * (ch + gap) + 18, class: 'axis'}, svg, new Date(d + 'T12:00').toLocaleString('en', {month: 'short', day: 'numeric'})); } });
})();

document.getElementById('sample').textContent = D.sample;
[`Window: ${D.window[0]} to ${D.window[1]}, ${D.n_sessions} sessions (all Yahoo still has 5-minute bars for). Each engine runs the approved era in force that day. Some SLEEVE sessions lack a 15:15 read: a thin decision ticker had no 5-minute bar within 30 minutes.`,
 `Prices at a minute = the close of the 5-minute bar ending then, scaled onto the adjusted series by the official close (the shadow runner's method). 15:50 stands in for Composer's decision minute (it decides at about 15:45-15:55).`,
 `Logic only: the targets are compared. Composer's actual holdings, KMLM's 10pp corridor (which absorbs small target changes) and live-feed problems (stale quotes, as on 10-30) are not part of this study.`,
 `In-sample: the 0.52 sigma scale was measured on these same sessions (on ~2,200 liquid ticker-moves, a different quantity from the 3 material changes the labels are graded on). The label result rests on 3 events: indicative, not a rate.`,
 `HG's 200-day gate was open at 15:50 on all ${D.n_sessions} sessions (no crossing in the window), so how often a 15:15 gate reading flips by 15:50 is not measured here; the preview alerts within 2 sigma of the flip price.`,
 `Under the plain random-walk scale (no 0.52), the same reads label ${D.lab_sqrt['coin-flip'].n} engine-sessions coin-flip (vs ${nLab('coin-flip')}), with the same ${D.lab_sqrt['coin-flip'].material} material changes in that group: the scale only changes how many calls are flagged, not which ones changed.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""
TEMPLATE = TEMPLATE.replace("const D = __DATA__;", "const D = __DATA__;\nconst ENG = " + json.dumps(ENGINES) + ";")

if __name__ == "__main__":
    main()
