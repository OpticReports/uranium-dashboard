#!/usr/bin/env python3
"""Exhibit for results.md addendum 48: the shadow decision runner's baseline. Reads
results/shadow-backfill-2026-10-29.json (backfill.py) and results/shadow-calibration-2026-10-29.json
(calibrate.py); writes results/shadow-runner-baseline-2026-10-29.html."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import shadow_runner as sr  # noqa: E402

RES = os.path.join(HERE, "..", "..", "results")
PAGE = os.path.join(RES, "shadow-runner-baseline-2026-10-29.html")
ENGINES = ["HG", "KMLM", "SLEEVE", "HARV"]


def main():
    bf = json.load(open(os.path.join(RES, "shadow-backfill-2026-10-29.json")))
    cal = json.load(open(os.path.join(RES, "shadow-calibration-2026-10-29.json")))
    man = sr.load_manifest()
    rows = [r for r in bf["rows"] if r["engine"] in ENGINES]
    dates = sorted({r["date"] for r in rows})
    cells = [{"d": r["date"], "e": r["engine"], "s": r["status"], "live": sr.fmt_w(r.get("live") or {}),
              "logic": sr.fmt_w(r.get("target") or {}), "chk": r.get("corridor_check"),
              "edge": r.get("edge") and ({"b": "intraday", "time": r["edge"]["time"]} if r["edge"]["basis"] == "intraday" else
                                         {"b": "search", "t": r["edge"]["ticker"], "m": r["edge"]["move"], "k": r["edge"]["sigma_ratio"]})}
             for r in rows]
    counts = {e: {} for e in ENGINES}
    for r in rows:
        counts[r["engine"]][r["status"]] = counts[r["engine"]].get(r["status"], 0) + 1
    live_rows = [r for r in rows if r["status"] != "no-rebalance"]
    rep = cal["reproduction"]
    rep_ok = sum(v["agree"] for v in rep.values())
    rep_strict = sum(v["strict"] for v in rep.values())
    rep_n = sum(v["n"] for v in rep.values())
    rep_sh = sum(v["shifted_agree"] for v in rep.values()) / max(1, sum(v["shifted_n"] for v in rep.values()))
    ch = sum(v["changes"] for v in rep.values())
    ch_ok = sum(v["changes_followed"] for v in rep.values())
    late = cal["late_moves"]["pooled"]["15:45"]
    knives = [r for r in rows if r["status"] == "knife-edge"]
    search = sorted(r["edge"]["sigma_ratio"] for r in knives if r["edge"]["basis"] == "search")
    intra = sorted(({"d": r["date"], "e": r["engine"], "t": r["edge"]["time"]} for r in knives if r["edge"]["basis"] == "intraday"),
                   key=lambda x: (x["d"], ENGINES.index(x["e"])))
    pl = cal["placebo"]
    eras = []
    for e, cfg in man.items():
        for era in cfg["eras"][1:]:
            if dates[0] <= era["from"] <= dates[-1]:
                eras.append({"e": e, "d": era["from"], "v": era["version"][:8]})
    lapse = {}
    for r in rows:
        if r["status"] == "no-rebalance":
            lapse.setdefault(r["engine"], {"frozen": sr.fmt_w(r["live"]), "days": []})["days"].append(
                {"d": r["date"], "logic": sr.fmt_w(r["target"]),
                 "ok": sr.agrees(r["target"], r["live"], man[r["engine"]].get("corridor"))})
    qd = max(r["date"] for r in rows if r["status"] != "no-rebalance")
    qrows = [r for r in rows if r["date"] == qd]
    n, rec = sr.record([r for r in rows if r["date"] <= qd])
    quiet = {"date": qd,
             "line": f"shadow {qd}: " + " | ".join(f"{r['engine']} {r['status']}" + (f" @{r['edge']['time']}" if r.get("edge", {}).get("basis") == "intraday" else "")
                                                    + f" {sr.fmt_w(r['target'])}" for r in qrows),
             "record": f"shadow record, last {n} session(s): " + ", ".join(f"{v} {k}" for k, v in sorted(rec.items()))}
    kmlm = [r for r in rows if r["engine"] == "KMLM" and r["status"] != "no-rebalance"]
    data = {"dates": dates, "cells": cells, "counts": counts, "eras": eras, "late": late["values"], "quiet": quiet,
            "late_q": {k: late[k] for k in ("p50", "p95", "p99", "max", "n")}, "search": search, "intra": intra,
            "placebo_search": pl["search_sigma_ratios"], "placebo": pl["total"], "K": sr.KNIFE_SIGMA,
            "rep": {"ok": rep_ok, "strict": rep_strict, "n": rep_n, "shifted": rep_sh, "changes": ch, "changes_ok": ch_ok},
            "lapse": lapse, "n_live": len(live_rows), "agree": sum(r["status"] == "agree" for r in live_rows),
            "knife": len(knives), "mismatch": sum(r["status"] == "mismatch" for r in live_rows),
            "kmlm_path": sum(r.get("corridor_check") == "path" for r in kmlm), "kmlm_n": len(kmlm),
            "window": [dates[0], dates[-1]], "late_window": cal["late_moves"].get("window")}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(PAGE, "w") as f:
        f.write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shadow runner baseline</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--agree:#d3d2cb;--none:transparent;--warn:#fab219;--serious:#ec835a;--crit:#d03b3b;--code:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--agree:#3b3b38;--code:#232321}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--agree:#3b3b38;--code:#232321}
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
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--grid);vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}
.tablewrap{overflow-x:auto}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 8px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{display:inline-block;width:14px;height:12px;border-radius:3px;border:1px solid var(--ring)}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%}
svg{display:block;width:100%;height:auto;overflow:visible}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.scroll svg{min-width:640px}
.tt{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:5;max-width:340px}
.tt .d{color:var(--ink2);margin-bottom:3px}
.axis text{fill:var(--muted);font-size:11px}
.lbl{fill:var(--ink2);font-size:12px}
.lblb{fill:var(--ink);font-size:12px;font-weight:600}
.notes{font-size:13.5px;color:var(--ink2)}
.notes li{margin:3px 0}
pre{background:var(--code);border-radius:8px;padding:10px 12px;font-size:12.5px;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0 10px}
.ok{color:var(--ink2)} .bad{font-weight:600}
#intra{min-width:560px} #intra td:last-child{white-space:nowrap}
</style>
</head>
<body>
<main class="viz-root">
<h1>Shadow decision runner: does Composer hold what the rules say?</h1>
<p class="sub-h">Every session the runner works out what each symphony's approved logic says to hold, on its own prices, and compares that with Composer's actual holdings. This page is its baseline: replayed against every daily snapshot of the live book since July, and against Composer's own backtests.</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>Live holdings vs approved logic, session by session</h2>
<p class="sub-h">One cell per engine and session, from the daily monitor's snapshots (taken after Composer's ~15:50 ET rebalance). Hover a cell for what Composer held and what the logic said.</p>
<div class="legend" id="lg-strip"></div>
<div class="scroll"><svg id="strip" role="img" aria-label="Grid of sessions from July 15 to October 28 by engine, colored by whether Composer's holdings matched the approved logic"></svg></div>
<div class="tablewrap" style="margin-top:10px"><table id="counts"></table></div>
</section>

<section class="card">
<h2>How each knife-edge was confirmed</h2>
<p class="sub-h">Composer decides on prices from about 15:45-15:55 ET; the runner uses the official close. A difference counts as a knife-edge when the approved logic, re-run with every ticker at its actual 15:45, 15:50 or 15:55 price (Yahoo 5-minute bars), gives exactly what Composer holds. Bars go back about 60 sessions; before that, and on any day bars are missing, a one-ticker move of at most 0.3&sigma; must explain it instead. The placebo row is the same test on deliberately wrong pairs inside the bar window.</p>
<div class="tablewrap"><table id="intra"></table></div>
<p class="sub-h" style="margin-top:12px">The fallback's radius: how far decisive tickers actually move from 15:45 to the close (top), and the move each fallback-confirmed knife-edge needed, against the same search run on deliberately wrong pairs (bottom).</p>
<div class="legend" id="lg-k"></div>
<div class="scroll">
<svg id="hist" role="img" aria-label="Histogram of the measured 15:45 to close move in units of daily sigma, with the 0.3 sigma fallback radius marked"></svg>
<svg id="dots" role="img" aria-label="Dot rows: the move each fallback-confirmed knife-edge needed, and placebo cases the fallback excused, on the same sigma axis"></svg>
</div>
</section>

<section class="card">
<h2>The October 26-28 lapse, as the runner would have reported it</h2>
<p class="sub-h">Composer made no rebalance attempt on these three sessions (last attempt October 23). The runner's no-rebalance alert fires on the first such session. What the logic wanted each day, against the frozen holdings:</p>
<div class="tablewrap"><table id="lapse"></table></div>
</section>

<section class="card">
<h2>What arrives in the daily report</h2>
<p class="sub-h">Quiet days print one line inside the monitor run. These lines raise the monitor's alert exit and reach you as a push:</p>
<pre id="samples"></pre>
</section>

<section class="card notes">
<h2 style="color:var(--ink)">Basis and limits</h2>
<ul id="basis"></ul>
</section>
</main>
<div class="tt" id="tt" role="status" aria-live="polite"></div>
<script>
const D = __DATA__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tt = document.getElementById('tt');
function tip(ev, html){tt.innerHTML = html; tt.style.display='block';
  const x = Math.min(ev.clientX + 14, window.innerWidth - tt.offsetWidth - 8), y = Math.min(ev.clientY + 14, window.innerHeight - tt.offsetHeight - 8);
  tt.style.left = x + 'px'; tt.style.top = y + 'px';}
function untip(){tt.style.display='none';}
const NS = 'http://www.w3.org/2000/svg';
function el(tag, attrs, parent, text){const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; if (parent) parent.appendChild(e); return e;}
const pct = x => (100 * x).toFixed(0) + '%';
const ST = {'agree': ['var(--agree)', '✓ agree'], 'knife-edge': ['var(--warn)', '! knife-edge'], 'mismatch': ['var(--crit)', '✕ mismatch'],
            'no-rebalance': ['var(--serious)', '‖ no rebalance attempt'], 'unavailable': ['var(--muted)', '? unavailable']};

// KPIs
const k = document.getElementById('kpis');
[[`${D.agree} / ${D.n_live}`, `engine-sessions where Composer held what the approved logic says on closing prices (${pct(D.agree / D.n_live)}), ${D.window[0].slice(5)} to 10-23`],
 [`${D.mismatch}`, `mismatches. ${D.knife} knife-edges: ${D.intra.length} confirmed on Composer's actual 15:45-15:55 prices, ${D.search.length} (before 5-minute bars) by the fallback`],
 [`${D.rep.strict.toLocaleString()} / ${D.rep.n.toLocaleString()}`, `Composer's own backtest decisions reproduced exactly (every approved tree, Apr 1 to Oct 28)`],
 ['First session', 'the Oct 26-28 lapse (no rebalance attempts) would have alerted on Oct 26, not via API errors']]
 .forEach(([b, s]) => { const d = document.createElement('div'); d.className = 'kpi'; d.innerHTML = `<b>${b}</b><span>${s}</span>`; k.appendChild(d); });

// strip legend + counts table
const lg = document.getElementById('lg-strip');
['agree', 'knife-edge', 'mismatch', 'no-rebalance'].forEach(s => { const n = Object.values(D.counts).reduce((a, c) => a + (c[s] || 0), 0);
  lg.insertAdjacentHTML('beforeend', `<span><i class="sw" style="background:${ST[s][0]}"></i>${ST[s][1]} (${n})</span>`); });
lg.insertAdjacentHTML('beforeend', `<span><i class="sw" style="background:transparent"></i>not live yet</span>`);
const ct = document.getElementById('counts');
ct.innerHTML = '<thead><tr><th>Engine</th><th class="n">agree</th><th class="n">knife-edge</th><th class="n">mismatch</th><th class="n">no rebalance</th></tr></thead><tbody>' +
  Object.entries(D.counts).map(([e, c]) => `<tr><td>${e}</td>${['agree', 'knife-edge', 'mismatch', 'no-rebalance'].map(s => `<td class="n">${c[s] || 0}</td>`).join('')}</tr>`).join('') + '</tbody>';

// strip chart
(function(){
  const svg = document.getElementById('strip'), E = ['HG', 'KMLM', 'SLEEVE', 'HARV'];
  const L = 62, T = 34, W = 1060, cw = (W - L - 8) / D.dates.length, ch = 22, gap = 2, H = T + E.length * (ch + gap) + 26;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const xi = d => L + D.dates.indexOf(d) * cw;
  E.forEach((e, i) => el('text', {x: L - 8, y: T + i * (ch + gap) + ch / 2 + 4, 'text-anchor': 'end', class: 'lblb'}, svg, e));
  const byKey = {}; D.cells.forEach(c => byKey[c.e + c.d] = c);
  E.forEach((e, i) => D.dates.forEach(d => {
    const c = byKey[e + d], x = xi(d), y = T + i * (ch + gap);
    const r = el('rect', {x: x + 1, y, width: Math.max(1, cw - 2), height: ch, rx: 3, fill: c ? ST[c.s][0] : 'transparent',
      stroke: c ? 'none' : 'var(--grid)', 'stroke-width': c ? 0 : 1}, svg);
    if (!c) return;
    el('rect', {x, y: y - 1, width: cw, height: ch + 2, fill: 'transparent'}, svg).addEventListener('mousemove', ev => {
      let h = `<div class="d">${d} · ${e}</div><b>${ST[c.s][1]}</b><br>Composer: ${c.live}<br>Logic: ${c.logic}`;
      if (c.edge && c.edge.b === 'intraday') h += `<br>The logic on ${c.edge.time} ET prices gives Composer's holding`;
      if (c.edge && c.edge.b === 'search') h += `<br>No 5-minute bars; explained by ${c.edge.t} ${(100 * c.edge.m).toFixed(2)}% (${c.edge.k.toFixed(2)}σ)`;
      if (c.chk) h += `<br>Corridor check: ${c.chk === 'path' ? 'path (from the previous session)' : 'lenient (no previous session)'}`;
      if (c.s === 'no-rebalance') h += '<br>No rebalance attempt: holdings frozen since 10-23';
      tip(ev, h); });
    svg.lastChild.addEventListener('mouseleave', untip);
  }));
  // month ticks
  let last = '';
  D.dates.forEach(d => { const m = d.slice(0, 7); if (m !== last) { last = m; const x = xi(d);
    el('line', {x1: x, x2: x, y1: T + E.length * (ch + gap), y2: T + E.length * (ch + gap) + 6, stroke: 'var(--axis)'}, svg);
    el('text', {x: x + 2, y: T + E.length * (ch + gap) + 18, class: 'axis'}, svg).textContent = new Date(d + 'T12:00').toLocaleString('en', {month: 'short', day: 'numeric'}); } });
  // era markers
  const seen = {};
  D.eras.forEach(r => { (seen[r.d] = seen[r.d] || []).push(r.e); });
  Object.entries(seen).forEach(([d, es]) => { const x = xi(d); if (x < L) return;
    const right = x > W * 0.7;
    el('line', {x1: x, x2: x, y1: T - 6, y2: T + E.length * (ch + gap) - gap, stroke: 'var(--ink2)', 'stroke-dasharray': '3 3'}, svg);
    el('text', {x: right ? x - 4 : x + 4, y: T - 12, 'text-anchor': right ? 'end' : 'start', class: 'lbl'}, svg).textContent =
      (d === '2026-10-19' ? 'HG 200-day gate' : es.join(' + ') + ' edits') + ` (${d.slice(5)})`; });
})();

// knife-edge chart
(function(){
  const it = document.getElementById('intra'), times = ['15:45', '15:50', '15:55'];
  it.innerHTML = '<thead><tr><th>Confirmed on actual prices</th>' + times.map(t => `<th class="n">${t} ET</th>`).join('') + '<th>Sessions</th></tr></thead><tbody>' +
    ['HG', 'KMLM', 'SLEEVE', 'HARV'].map(e => { const xs = D.intra.filter(x => x.e === e);
      return `<tr><td>${e}</td>${times.map(t => `<td class="n">${xs.filter(x => x.t === t).length}</td>`).join('')}<td>${xs.map(x => x.d.slice(5)).join(', ') || '-'}</td></tr>`; }).join('') +
    `<tr><td>Placebo (wrong-day pairs)</td><td class="n" colspan="3">${D.placebo.bars['knife-edge'] || 0} of ${Object.values(D.placebo.bars).reduce((a, b) => a + b, 0)} excused</td><td></td></tr></tbody>`;
  const lgk = document.getElementById('lg-k');
  lgk.innerHTML = `<span><i class="sw" style="background:var(--s1)"></i>measured 15:45 ET → official close move (${D.late_q.n} ticker-sessions)</span>` +
    `<span><i class="dot" style="background:var(--s2)"></i>live knife-edges confirmed by the fallback (${D.search.length})</span>` +
    `<span><i class="dot" style="background:var(--s3)"></i>placebo cases the fallback excused (${D.placebo_search.length} of ${Object.values(D.placebo['no bars']).reduce((a, b) => a + b, 0)})</span>`;
  const W = 1060, L = 170, R = 20, X1 = 1.0, x = v => L + Math.min(v, X1) / X1 * (W - L - R);
  // histogram
  const h = document.getElementById('hist'), H = 170, T = 14, B = 26;
  h.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const bins = Array(20).fill(0); D.late.forEach(v => bins[Math.min(19, Math.floor(v / 0.05))]++);
  const mx = Math.max(...bins), y = c => H - B - c / mx * (H - B - T);
  [0, .25, .5, .75, 1].forEach(t => { el('line', {x1: x(t), x2: x(t), y1: T, y2: H - B, stroke: 'var(--grid)'}, h);
    el('text', {x: x(t), y: H - 8, 'text-anchor': 'middle', class: 'axis'}, h).textContent = t.toFixed(2) + 'σ'; });
  el('line', {x1: L, x2: W - R, y1: H - B, y2: H - B, stroke: 'var(--axis)'}, h);
  el('text', {x: L - 10, y: T + 10, 'text-anchor': 'end', class: 'lbl'}, h).textContent = 'share of sessions';
  bins.forEach((c, i) => { if (!c) return; const x0 = x(i * 0.05) + 1, w = x(0.05) - x(0) - 2;
    const r = el('rect', {x: x0, y: y(c), width: w, height: H - B - y(c), rx: 2, fill: 'var(--s1)'}, h);
    r.addEventListener('mousemove', ev => tip(ev, `<div class="d">${(i * .05).toFixed(2)}-${((i + 1) * .05).toFixed(2)}σ</div>${c} of ${D.late.length} ticker-sessions (${pct(c / D.late.length)})`));
    r.addEventListener('mouseleave', untip); });
  el('line', {x1: x(D.K), x2: x(D.K), y1: T - 6, y2: H - B, stroke: 'var(--ink)', 'stroke-width': 1.5}, h);
  el('text', {x: x(D.K) + 6, y: T + 4, class: 'lbl'}, h).textContent = `fallback radius ${D.K}σ ≈ p95 of the measured move (p99 ${D.late_q.p99.toFixed(2)}σ, median ${D.late_q.p50.toFixed(2)}σ)`;
  // dot rows
  const s = document.getElementById('dots'), rows = [['Live', D.search, 'var(--s2)'], ['Placebo', D.placebo_search, 'var(--s3)']];
  const RH = 44, H2 = rows.length * RH + 30;
  s.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  [0, .25, .5, .75, 1].forEach(t => { el('line', {x1: x(t), x2: x(t), y1: 0, y2: rows.length * RH, stroke: 'var(--grid)'}, s);
    el('text', {x: x(t), y: rows.length * RH + 18, 'text-anchor': 'middle', class: 'axis'}, s).textContent = t.toFixed(2) + 'σ'; });
  el('line', {x1: x(D.K), x2: x(D.K), y1: 0, y2: rows.length * RH, stroke: 'var(--ink)', 'stroke-width': 1.5}, s);
  rows.forEach(([name, vals, col], i) => {
    const cy = i * RH + RH / 2;
    el('text', {x: L - 10, y: cy + 4, 'text-anchor': 'end', class: 'lblb'}, s).textContent = `${name} (${vals.length})`;
    vals.forEach((v, j) => { const c = el('circle', {cx: x(v), cy: cy + ((j * 7) % 5 - 2) * 3.2, r: 4.5, fill: col, stroke: 'var(--surface)', 'stroke-width': 1.5}, s);
      c.addEventListener('mousemove', ev => tip(ev, `<div class="d">${name}</div>needed a ${v.toFixed(3)}σ move`)); c.addEventListener('mouseleave', untip); });
    const med = vals.slice().sort((a, b) => a - b)[Math.floor(vals.length / 2)];
    el('text', {x: W - R, y: cy - 12, 'text-anchor': 'end', class: 'lbl'}, s).textContent = `median ${med.toFixed(2)}σ`;
  });
})();

// lapse table
(function(){
  const t = document.getElementById('lapse'), days = [...new Set(Object.values(D.lapse).flatMap(v => v.days.map(x => x.d)))].sort();
  t.innerHTML = `<thead><tr><th>Engine</th><th>Composer held (frozen)</th>${days.map(d => `<th>Logic on ${d.slice(5)}</th>`).join('')}</tr></thead><tbody>` +
    Object.entries(D.lapse).map(([e, v]) => `<tr><td>${e}</td><td>${v.frozen}</td>${v.days.map(x => `<td class="${x.ok ? 'ok' : 'bad'}">${x.ok ? '✓ same' : '✕ ' + x.logic}</td>`).join('')}</tr>`).join('') + '</tbody>';
})();

document.getElementById('samples').textContent = [
  'quiet (as it would have read on ' + D.quiet.date + '):',
  '  ' + D.quiet.line,
  '  ' + D.quiet.record,
  '',
  'COMPOSER DID NOT REBALANCE — no rebalance attempt on 2026-10-28 for HG, KMLM, SLEEVE, HARV (last attempt 2026-10-23); holdings are frozen. Approved logic now: HG BIL 100%; KMLM SOXL 38%, SVIX 38%, PULS 16%, VXZ 9% (frozen at SOXL 78%, ZVOL 11%, PULS 10%); SLEEVE BOXX 100%; HARV PULS 64%, VXZ 36% (frozen at ZVOL 52%, PULS 48%). ...',
  'COMPOSER STILL NOT REBALANCING — HG session 2 without an attempt (since 2026-10-26); ...      COMPOSER REBALANCING RESUMED on D — HG after 3 session(s) ...',
  'SHADOW MISMATCH — <engine> on D: Composer holds X; its approved logic says Y, on closing prices and on prices at 15:45, 15:50, 15:55 ET. Closest calls: <the decisive checks with their values>. ...',
  'LOGIC DRIFT — <engine>: Composer\'s live logic (version V) differs from the approved V0 at <the node and field>: <approved> -> <live>. ... Approve the change or roll it back.',
  'SHADOW BLIND — <engine>: no comparison for 3 sessions in a row (latest: <why>) ...      SHADOW RUNNER DOWN — 3 runs in a row failed ...',
  'SHADOW KNIFE-EDGE x2 — <engine> on D: ... with no 5-minute bars to check, a -0.15% TQQQ move (0.05 sigma) is the explanation ...'].join('\n');

const B = document.getElementById('basis');
const pb = D.placebo.bars, pn = D.placebo['no bars'], sum = o => Object.values(o).reduce((a, b) => a + b, 0);
[`Live side: Composer's holdings in the daily monitor's git-tracked snapshot (taken after the ~15:50 ET rebalance), mapped to the session they show (taken after 16:00 ET on a session day = that session); ${D.dates.length - 3} sessions from ${D.window[0]} to 10-23 have one (a few sessions in the window have none and are not counted), plus the three lapse sessions from the live API. The snapshots do not record Composer's rebalance-attempt date, so a past skipped session with unchanged logic would read as agree.`,
 `Shadow side: the approved tree for each date (fixtures/approved/manifest.json: HG's three versions, SLEEVE's two, KMLM and HARV one each), evaluated on Yahoo adjusted closes with the add. 27 semantics and Wilder RSI over the whole fetched history.`,
 `Reproduction control: against Composer's own backtests (which, like the runner, decide on closes) the runner matches ${D.rep.strict} of ${D.rep.n} era-tree sessions exactly (same tickers, within 0.5%; KMLM on its corridor path), and follows ${D.rep.changes_ok} of the ${D.rep.changes} days Composer's backtest changed allocation. Compared one day off, agreement drops to ${pct(D.rep.shifted)}. A 250-close RSI warm-up (the first version) missed SLEEVE on 2026-04-07; the full history fixes it.`,
 `Knife-edge rule: the logic re-run on actual 15:45, 15:50 and 15:55 ET prices (5-minute bar closes for every ticker at once). On deliberately wrong pairs (the logic at D against Composer's holdings from another session, where they differ) it excuses ${pb['knife-edge'] || 0} of ${sum(pb)} inside the bar window (mismatch ${pb.mismatch}). Without bars, the fallback (one ticker, at most ${D.K}σ, about the p95 of the measured 15:45 → close move) excuses ${pn['knife-edge'] || 0} of ${sum(pn)}, so two fallback knife-edges in a row on one engine alert.`,
 `KMLM rebalances on a 10% corridor (absolute: Composer's own backtest holdings reproduce on that reading, not the relative one). It is checked on its path: the previous session's holdings drifted to the close, the target if any holding is more than 10 points off it, else the drifted holdings, within 1.5%. ${D.kmlm_path} of its ${D.kmlm_n} sessions had the previous session to do that; the others used the lenient check (every holding within 11 points).`,
 `Not checked: fill prices and trade timing, cash drag, and deposits or withdrawals (KMLM falls back to the lenient check when its net deposits move). A dividend or reverse split that Yahoo books before adjusting its series is applied by the runner itself.`,
 `Counter-agent (add. 48): reproduced every claim; refuted two blocker defects (no-rebalance detection depended on Yahoo; one bad ledger line silenced the runner), the 0.5σ single-ticker knife-edge (too generous: 21% of wrong pairs excused), the 250-close RSI warm-up, the drift check's blind spots and the lenient KMLM check. All fixed; 55 of 55 code mutants now fail the tests.`,
 `Side finding: no saved version of the harvester contains an HYG condition, although its name says "HYG Credit Guard" and add. 12 records the guard as saved. Its only guard is the UVXY RSI(14) > 70 switch to PULS. Nothing was changed.`,
 `Reporting only. The runner holds no broker key and never trades or edits a symphony.`]
 .forEach(s => { const li = document.createElement('li'); li.textContent = s; B.appendChild(li); });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
