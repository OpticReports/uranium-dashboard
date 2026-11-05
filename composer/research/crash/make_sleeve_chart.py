#!/usr/bin/env python3
"""Exhibit for the Crash Convexity Sleeve audit (sleeve_audit.py). Reads results/sleeve-audit-2026-11-05.json,
writes results/sleeve-audit-2026-11-05.html: inline SVG, palette tokens, light/dark, no external libraries
(the style of research/overnight/make_overnight_chart.py)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")
SRC = os.path.join(RES, "sleeve-audit-2026-11-05.json")
PAGE = os.path.join(RES, "sleeve-audit-2026-11-05.html")


def main():
    with open(SRC) as f:
        r = json.load(f)
    rows = [{k: v for k, v in x.items() if k not in ("lhs", "rhs")} | {"lhs_ticker": x["lhs"][1], "rhs_ticker": x["rhs"][1] if x["rhs"] else None}
            for x in r["trigger_table"]]
    for x in rows:
        x["fires"] = {k: v for k, v in x["fires"].items() if k != "by_year"}
    crash15 = [x for x in r["crash_days"] if x["date"] >= "2015-06-01"]
    data = {"live": r["live_1105"], "rows": rows, "inner": r["inverse_inner"], "cf": r["counterfactual_legs_1105"], "words": r["rules_words"],
            "crash15": crash15, "crash_all": [{k: x[k] for k in ("date", "spy", "hold", "ret", "f1", "f5", "f20", "next_hold", "era", "proxies")} for x in r["crash_days"]],
            "summary": r["crash_summary"], "episodes": [{k: v for k, v in e.items() if k != "path"} for e in r["episodes"]],
            "conv": r["convexity"], "carry": r["carry"], "years": r["years"], "curves": r["curves"], "scatter": r["scatter"],
            "comp": r["comparator"], "val": r["validation"], "states": r["states"], "trans": r["transitions"], "csig": r["crash_signal"],
            "edges": r["edges"], "launch": r["launch_dates"], "path": r["path"], "generated": r["generated"], "era": r["era"]}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(PAGE, "w") as f:
        f.write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crash sleeve audit</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--ctx:#b9b7ae;--ctx2:#8e8c84;--neg:#e34948;--band:rgba(42,120,214,.18);--pt:rgba(42,120,214,.35)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--pt:rgba(57,135,229,.4)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--pt:rgba(57,135,229,.4)}
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
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--grid);vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}.tablewrap{overflow-x:auto}
#tbA{min-width:1240px}#tbA td:nth-child(7),#tbA td:nth-child(8),#tbA td:nth-child(9),#tbA td:nth-child(2){white-space:nowrap}
#tbB,#tbB2,#tbF,#tbG,#tbG2{min-width:1150px}#tbB td:first-child,#tbG td:nth-child(2){white-space:nowrap}#tbC{min-width:1500px}#tbE{min-width:1700px}#tbE2{min-width:760px}
details{margin-top:8px;font-size:13.5px}summary{cursor:pointer;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.neg{color:var(--neg)}.pos{color:var(--s3)}.dim{color:var(--muted)}
.words li{margin:4px 0;font-size:13.5px;color:var(--ink2)}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:360px}
</style>
</head>
<body>
<main>
<h1>Crash Convexity Sleeve on 2026-11-05: why it stayed in BOXX, and what it has done on every crash day</h1>
<p class="sub-h" id="intro"></p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>A. The rules in words, and every trigger at the 11-05 close</h2>
<ul class="words" id="words"></ul>
<p class="sub-h">Each condition of the approved tree (era yHJkdePZ, BOXX legs) read on Yahoo's 16:00 closes, in the order the tree tests them: the live value, the threshold, the distance, the one-day move of the left-hand ticker that would have flipped it with everything else as it closed, and what the sleeve would then have held at the 11-05 rebalance. The last columns count how often the condition read true on its own (cascade order ignored) since 2015-06 and on the 36 SPY &le; &minus;3% days of that window.</p>
<div class="tablewrap"><table id="tbA"></table></div>
<p class="sub-h" id="cfA" style="margin-top:10px"></p>
</section>

<section class="card">
<h2>B. Every SPY &le; &minus;3% day since 2015-06: SPY vs the sleeve</h2>
<p class="sub-h" id="subB"></p>
<div class="legend" id="lgB"></div>
<div class="chartwrap"><svg id="chB" role="img" aria-label="SPY return and sleeve return on each SPY minus 3 percent day since June 2015"></svg></div>
<div class="tablewrap"><table id="tbB"></table></div>
<details><summary>Table: every crash day since 1995-06 (synthetic path before 2015-06), with the holding, the next holding and the next 1 / 5 / 20 sessions</summary><div class="tablewrap"><table id="tbB2"></table></div></details>
</section>

<section class="card">
<h2>C. The eight episodes</h2>
<p class="sub-h">Returns compound over the sessions listed (from the close before the first). "Left cash after" counts sessions from the first listed day until the sleeve held anything but BOXX; 0 = it was already out. "Next 20" = the sleeve's return over the 20 sessions after the episode (the whipsaw risk of add. 6).</p>
<div class="tablewrap"><table id="tbC"></table></div>
</section>

<section class="card">
<h2>D. Equity curves, log scale: sleeve vs SPY vs a constant BOXX line</h2>
<p class="sub-h">Left: 2015-06 on (the real funds; KMLM's signal is RYMFX until 2020-12; BOXX is BIL throughout the path). Right: the whole synthetic path from 1995-06 (add. 47 panel: VIX funds, inverse funds and bond ETFs modelled before they existed). Ticks under the sleeve line mark SPY &le; &minus;3% days.</p>
<div class="legend" id="lgD"></div>
<div class="chartwrap"><svg id="chD1" role="img" aria-label="Growth of one dollar in the sleeve, SPY and BOXX since June 2015, log scale"></svg></div>
<div class="chartwrap" style="margin-top:10px"><svg id="chD2" role="img" aria-label="Growth of one dollar in the sleeve, SPY and BOXX since June 1995 on the synthetic path, log scale"></svg></div>
</section>

<section class="card">
<h2>E. Is it convex? Daily sleeve return against SPY's, with separate fits on down and up days</h2>
<p class="sub-h" id="subE"></p>
<div class="legend" id="lgE"></div>
<div class="chartwrap"><svg id="chE" role="img" aria-label="Scatter of daily sleeve returns against SPY returns since June 2015 with fitted lines on negative and positive SPY days"></svg></div>
<div class="tablewrap"><table id="tbE"></table></div>
<details><summary>Table: calendar years (calm = no SPY &le; &minus;3% day), the carry question</summary><div class="tablewrap"><table id="tbE2"></table></div></details>
</section>

<section class="card">
<h2>F. The cheap comparator: a static long mid-term-vol sleeve (VIXM, VXZ) on the same days</h2>
<p class="sub-h">Per dollar of sleeve; at the book's 10% sizing divide by ten. The static vol fund pays on almost every crash day; the convexity sleeve pays on about half of them and, in sample, earns its carry back in calm years instead of bleeding it.</p>
<div class="tablewrap"><table id="tbF"></table></div>
</section>

<section class="card">
<h2>G. By-products: what the sleeve's states say about its legs and about SPY (candidate edges, with mirrors)</h2>
<p class="sub-h">Each held leg's own daily return on the days the sleeve held it vs the days it did not (2015-06 on, from each fund's launch; in sample to 2023-03, add. 4, then out of sample), and SPY's next 5 / 20 sessions after the sleeve leaves cash, with the mirror (returning to cash) and the unconditional mean.</p>
<div class="tablewrap"><table id="tbG"></table></div>
<div class="tablewrap" style="margin-top:10px"><table id="tbG2"></table></div>
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
const f1 = v => v == null ? '–' : v.toFixed(1), f2 = v => v == null ? '–' : v.toFixed(2), pc = v => v == null ? '–' : (v * 100).toFixed(1) + '%', pc0 = v => v == null ? '–' : (Math.round(v * 100) || 0) + '%';
const sg = v => v == null ? '–' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%', sg2 = v => v == null ? '–' : (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%';
const cls = v => v == null ? ' class="n"' : (v < 0 ? ' class="n neg"' : ' class="n"'), sf2 = v => v == null ? '–' : (v >= 0 ? '+' : '') + v.toFixed(2);
const fw = w => w ? Object.entries(w).sort((a, b) => b[1] - a[1]).map(([t, x]) => `${t} ${Math.round(x * 100)}%`).join(', ') : '–';
const L = D.live, S = D.summary, C15 = D.conv['2015-06+'], C95 = D.conv['1995-06+'], CR = D.conv['2020-12+ (all legs real)'];
const s3 = S['2015-06+ SPY<=-3%'], s4 = S['2015-06+ SPY<=-4%'], s3x = S['2015-06+ SPY<=-3% ex-2020'], s95 = S['1995-06+ SPY<=-3%'], s95x4 = S['1995-06+ SPY<=-4%'];
const closest = D.rows.slice().sort((a, b) => Math.abs(a.flip_move ?? 9) - Math.abs(b.flip_move ?? 9));
const paid = D.episodes.filter(e => e.sleeve > 0.05);
document.getElementById('intro').textContent = `Symphony nNdBk7hc5NiBzeRvbI5T, $${Math.round(L.sleeve_value).toLocaleString()} on 11-05, sized by POLICY Operation 1 at 10% of the family's crash-exposed assets as a correlation hedge (owner, 2026-07-16). On 11-05 SPY closed ${sg(L.spy)}, SOXL ${sg(L.soxl)}, VIX ${L.vix.toFixed(1)} with VIX3M/VIX at ${sg(L.vix3m_over_vix_minus_1)}; the sleeve held BOXX 100% all day and the 15:16 pre-close preview read "firm: no change". Report only: the approved tree is read with the shadow runner's evaluator on Yahoo's closes; the history is the add. 47 daily path (live tree on the long panel, Composer-equivalent costs) plus the live 11-05 row. Nothing traded, nothing on Composer touched.`;
[[`0 of ${D.rows.length} triggers`, `fired at the 11-05 close. Closest: ${closest[0].label} (live ${f2(closest[0].value)}, ${sg2(closest[0].flip_move)} away → ${fw(closest[0].would_hold)}); then ${closest[1].label} (${sg2(closest[1].flip_move)} → ${fw(closest[1].would_hold)}). No condition reads VIX, VIX3M or SPY: the sleeve moves on bond and credit shocks, and 11-05 had none (HYG ${sg2(L.hyg)}, TLT ${sg2(L.tlt)}, SHY ${sg2(L.shy)}, LQD ${sg2(L.lqd)})`],
 [`${s3.n} crash days since 2015-06`, `SPY ≤ −3%: sleeve ${sg(s3.ret_mean)} mean on the day (median ${sg(s3.ret_median)}, up ${pc0(s3.hit)}), parked in BOXX at the open on ${pc0(s3.parked_share)}. SPY ≤ −4% (n ${s4.n}): ${sg(s4.ret_mean)}, up ${pc0(s4.hit)}. The gain comes after: next 5 sessions ${sg(s3.f5)} mean, positive ${pc0(s3.f5_pos)} (ex-2020: ${sg(s3x.f5)}). Since 1995 (n ${s95.n}): ${sg(s95.ret_mean)} on the day, up ${pc0(s95.hit)}`],
 [`${paid.length} of ${D.episodes.length} episodes paid`, D.episodes.map(e => `${e.label.split(' ')[0]} ${sg(e.sleeve)}`).join(', ') + `. It pays when credit or rates crack (2018-02, 2020, 2022, 2024-08) and sits out equity-only selloffs (2015-08, 2018-12, 2025-04, 11-05)`],
 [`β ${sf2(C15.down.beta)} down / ${sf2(C15.up.beta)} up`, `daily beta to SPY on down vs up days, 2015-06+ (t ${f1(C15.down.t)} / ${f1(C15.up.t)}); all legs real 2020-12+: ${f2(CR.down.beta)} / ${f2(CR.up.beta)}. Convex on the downside: SPY ≤ −3% days ${sg(C15.buckets[0].sleeve)}, −3..−2% ${sg(C15.buckets[1].sleeve)}, +1..+2% ${sg(C15.buckets[5].sleeve)}. ${pc0(C15.parked_share)} of days parked; calm years ${sg(D.carry['2015-06+'].calm_mean)} mean in sample, ${sg(D.carry['1995-06+'].calm_median)} median since 1995`]]
 .forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; k.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(k); });
document.getElementById('words').innerHTML = D.words.map(w => `<li>${w}</li>`).join('');
// A: trigger table
document.getElementById('tbA').innerHTML = '<thead><tr><th>half</th><th>condition</th><th class="n">live 11-05</th><th class="n">needs</th><th class="n">distance</th><th class="n">1-day move that flips</th><th>sleeve would hold</th><th class="n">true since 2015-06</th><th>last true</th><th class="n">on crash days</th></tr></thead><tbody>' +
  D.rows.map(x => { const fc = x.fires; return `<tr><td>${x.half.replace('FrontrunBonds', 'Frontrun')}</td><td>${x.label}</td><td class="n">${f2(x.value)}</td><td class="n">${x.op} ${f2(x.threshold)}</td><td class="n">${f2(x.distance)} ${x.unit}</td><td class="n">${x.flip_move == null ? 'none within ±60%' : sg2(x.flip_move) + (x.rhs_ticker ? ' ' + x.lhs_ticker + ' (or ' + sg2(x.flip_move_rhs) + ' ' + x.rhs_ticker + ')' : '')}</td><td>${fw(x.would_hold)}</td><td class="n">${fc.n_true} / ${fc.n_days} days</td><td>${fc.last || '–'}</td><td class="n">${fc.on_crash3} / ${fc.of_crash3} (${fc.on_crash4} / ${fc.of_crash4} at ≤ −4%)</td></tr>`; }).join('') +
  D.inner.map(x => `<tr><td class="dim">inside the gate</td><td class="dim">${x.label}</td><td class="n dim">${f2(x.value)}</td><td class="n dim">&lt; ${f2(x.threshold)}</td><td class="n dim">${f2(x.value - x.threshold)} RSI pts</td><td class="dim"></td><td class="dim">gate open → ${x.holds}</td><td colspan="3" class="dim">the InverseHold half would still hold BOXX with the gate open: both inverse legs read stronger than KMLM</td></tr>`).join('') + '</tbody>';
const cfo = Object.entries(D.cf).sort((a, b) => b[1].sleeve_ret - a[1].sleeve_ret);
document.getElementById('cfA').innerHTML = `Had a leg been on into 11-05 (decided at the 11-04 close, when nothing read true either): ` + cfo.map(([t, v]) => `${t} ${sg(v.leg_ret)} → sleeve ${sg(v.sleeve_ret)}`).join('; ') + `. Had a Frontrun trigger fired AT the 11-05 close, most branches buy the worst one-day performer of their list: SOXL (${sg(L.soxl)}), a dip-buy for the 11-06 session, not a hedge.`;

// B: crash-day bars
(function(){
  const rows = D.crash15, svg = document.getElementById('chB'), W = 900, H2 = 340, l = 54, r = 16, t = 16, b = 70, n = rows.length;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const vals = rows.flatMap(x => [x.spy, x.ret]), lo = Math.min(...vals) - 0.01, hi = Math.max(...vals) + 0.02;
  const gw = (W - l - r) / n, bw = gw * 0.38, Y = v => t + (hi - v) / (hi - lo) * (H2 - t - b);
  for (let v = Math.ceil(lo * 20) / 20; v <= hi; v += 0.05) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  rows.forEach((x, i) => {
    const x0 = l + i * gw + (gw - 2 * bw) / 2;
    [[x.spy, 'var(--ctx2)', 0], [x.ret, x.ret < 0 ? 'var(--neg)' : 'var(--s1)', bw]].forEach(([v, c, dx]) => {
      const y0 = Y(Math.max(0, v)), h = Math.abs(Y(v) - Y(0));
      const rr = el('rect', {x: x0 + dx, y: y0, width: bw, height: Math.max(h, 1), rx: 1.5, fill: c}, svg);
      rr.addEventListener('mousemove', e => tip(e, `<b>${x.date}</b> SPY ${sg(x.spy)}, sleeve ${sg2(x.ret)}<br>held that day: ${fw(x.hold)}<br>decided at the close: ${fw(x.next_hold)}<br>next 1 / 5 / 20 sessions: ${sg(x.f1)} / ${sg(x.f5)} / ${sg(x.f20)}${x.proxies.length ? '<br>proxies: ' + x.proxies.join(', ') : ''}${x.era === 'live' ? '<br>live row (real BOXX)' : ''}`)); rr.addEventListener('mouseleave', untip);
    });
    if (!Object.keys(x.hold).every(k => k === 'BOXX' || k === 'BIL')) el('circle', {cx: x0 + bw, cy: H2 - b + 6, r: 2.2, fill: 'var(--s4)'}, svg);
    const tx = el('text', {x: x0 + bw, y: H2 - b + 14, class: 'ax', transform: `rotate(-62 ${x0 + bw} ${H2 - b + 14})`, 'text-anchor': 'end'}, svg, x.date.slice(2));
  });
  el('text', {x: W - r, y: H2 - 4, 'text-anchor': 'end', class: 'ax'}, svg, 'each SPY ≤ −3% day, 2015-06..2026-11-05; dot = the sleeve held a leg that day (not 100% BOXX)');
  legend('lgB', [['SPY, close to close', 'var(--ctx2)'], ['sleeve, same day (Composer-equivalent costs)', 'var(--s1)'], ['sleeve, negative', 'var(--neg)']]);
  document.getElementById('subB').textContent = `Bars: SPY's return and the sleeve's on the same session. The sleeve was 100% in BOXX at the open on ${s3.parked_at_open} of the ${s3.n} days and left cash at that day's close on ${s3.entered_at_close} of those; where it already held a leg, the leg was usually UVXY (after a credit shock the day before) or LABD/TMV (the InverseHold half). Its best crash days: ${rows.slice().sort((a, b2) => b2.ret - a.ret).slice(0, 3).map(x => `${x.date} ${sg(x.ret)} (${fw(x.hold)})`).join('; ')}; the only loss worth the name: ${rows.filter(x => x.ret < -0.01).map(x => `${x.date} ${sg(x.ret)} (${fw(x.hold)})`).join('; ') || 'none'}; every other negative day is a BOXX day's −0.0%.`;
  const keys = ['2015-06+ SPY<=-3%', '2015-06+ SPY<=-4%', '2015-06+ SPY<=-3% ex-2020', '2015-06+ SPY<=-3% ex-2020-2022', '2024-06+ (both halves OOS, add. 4b) SPY<=-3%', '1995-06+ SPY<=-3%', '1995-06+ SPY<=-4%', '2015-06+ SPY>=+3%', '2015-06+ top-10 up-days', '1995-06+ SPY>=+3%', '1995-06+ top-10 up-days', '2015-06+ all days', '1995-06+ all days'];
  document.getElementById('tbB').innerHTML = '<thead><tr><th>days</th><th class="n">n</th><th class="n">SPY mean</th><th class="n">sleeve same day: mean</th><th class="n">median</th><th class="n">up</th><th class="n">worst / best</th><th class="n">next 1</th><th class="n">next 5 (median, positive)</th><th class="n">next 20 (median)</th><th class="n">parked at open</th><th class="n">parked after the close</th></tr></thead><tbody>' +
    keys.filter(k => S[k] && S[k].n).map(k => { const v = S[k]; return `<tr><td>${k.replace('<=', '≤ ').replace('>=', '≥ ').replace(/-(\d)%/, '−$1%')}</td><td class="n">${v.n}</td><td${cls(v.spy_mean)}>${sg(v.spy_mean)}</td><td${cls(v.ret_mean)}>${sg2(v.ret_mean)}</td><td${cls(v.ret_median)}>${sg2(v.ret_median)}</td><td class="n">${pc0(v.hit)}</td><td class="n"><span class="neg">${sg(v.ret_min)}</span> / ${sg(v.ret_max)}</td><td${cls(v.f1)}>${sg2(v.f1)}</td><td${cls(v.f5)}>${sg(v.f5)} (${sg(v.f5_median)}, ${pc0(v.f5_pos)})</td><td${cls(v.f20)}>${sg(v.f20)} (${sg(v.f20_median)})</td><td class="n">${pc0(v.parked_share)}</td><td class="n">${pc0(v.parked_next_share)}</td></tr>`; }).join('') +
    `<tr><td colspan="12" class="dim">Forward windows overlap (2020-03 and 2022 cluster crash days), so the "next 5 / 20" means are dominated by those runs: read the medians and the ex-2020 rows. The mirror rows (SPY ≥ +3%, the ten biggest up-days) are mostly rebound days inside the same episodes.</td></tr></tbody>`;
  document.getElementById('tbB2').innerHTML = '<thead><tr><th>date</th><th>era</th><th class="n">SPY</th><th>held that day</th><th class="n">sleeve</th><th>decided at the close</th><th class="n">next 1</th><th class="n">next 5</th><th class="n">next 20</th><th>proxies in use</th></tr></thead><tbody>' +
    D.crash_all.map(x => `<tr><td>${x.date}</td><td class="dim">${x.era}</td><td class="n neg">${sg(x.spy)}</td><td>${fw(x.hold)}</td><td${cls(x.ret)}>${sg2(x.ret)}</td><td>${fw(x.next_hold)}</td><td${cls(x.f1)}>${sg(x.f1)}</td><td${cls(x.f5)}>${sg(x.f5)}</td><td${cls(x.f20)}>${sg(x.f20)}</td><td class="dim">${x.proxies.join(', ')}</td></tr>`).join('') + '</tbody>';
})();

// C: episodes
document.getElementById('tbC').innerHTML = '<thead><tr><th>episode</th><th>sessions</th><th class="n">SPY</th><th class="n">sleeve</th><th class="n">sleeve max DD inside</th><th>biggest leg (weight, day)</th><th>legs held</th><th class="n">left cash after</th><th class="n">share of days 100% BOXX</th><th class="n">best day</th><th class="n">worst day</th><th class="n">next 20 (SPY)</th><th>proxies</th></tr></thead><tbody>' +
  D.episodes.map(e => { const ml = e.max_leg; return `<tr><td>${e.label}</td><td>${e.from}..${e.to} (${e.sessions})</td><td class="n neg">${sg(e.spy)}</td><td${cls(e.sleeve)}><b>${sg(e.sleeve)}</b></td><td class="n">${pc(e.sleeve_maxdd)}</td><td>${ml ? `${ml[1]} ${pc0(ml[0])} on ${ml[2]}` : 'none'}</td><td>${Object.keys(e.legs).join(', ') || '–'}</td><td class="n">${e.days_to_leave_cash == null ? (e.first_out_after_episode == null ? 'never (in window)' : 'after the episode, +' + e.first_out_after_episode) : e.days_to_leave_cash + ' sessions'}</td><td class="n">${pc0(e.parked_share)}</td><td${cls(e.best_day.ret)}>${sg(e.best_day.ret)} ${e.best_day.date.slice(5)} (${fw(e.best_day.hold)})</td><td${cls(e.worst_day.ret)}>${sg(e.worst_day.ret)} ${e.worst_day.date.slice(5)}</td><td${cls(e.next20)}>${e.next20 == null ? '–' : sg(e.next20) + ' (' + sg(e.spy_next20) + ')'}</td><td class="dim">${e.proxies.join(', ')}</td></tr>`; }).join('') +
  `<tr><td colspan="13" class="dim">Prior reads of the same episodes (add. 4c deep-proxy sleeve, different windows): Volmageddon +23.5%, Q4-2018 +4.8%, COVID +172.3%, 2022 bear +82.3%, Aug-2024 +29.4%, Feb-Apr 2025 +1.3%; add. 39: the sleeve's COVID crash window +144..+180% with the UVXY leg paying +80pp of it.</td></tr></tbody>`;

// D: equity curves
function curve(id, pts, title){
  const svg = document.getElementById(id), W = 900, H2 = 300, l = 54, r = 150, t = 16, b = 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const T = s => new Date(s + 'T12:00:00Z').getTime(), t0 = T(pts[0][0]), t1 = T(pts[pts.length - 1][0]);
  const vals = pts.flatMap(p => [p[1], p[2], p[3]]), lo = Math.log10(Math.min(...vals) * 0.9), hi = Math.log10(Math.max(...vals) * 1.15);
  const X = ms => l + (ms - t0) / (t1 - t0) * (W - l - r), Y = v => t + (hi - Math.log10(v)) / (hi - lo) * (H2 - t - b);
  [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000].forEach(v => { if (Math.log10(v) >= lo && Math.log10(v) <= hi) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: v === 1 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, '$' + v); } });
  const y0 = +pts[0][0].slice(0, 4) + 1, y1 = +pts[pts.length - 1][0].slice(0, 4), step = y1 - y0 > 12 ? 4 : 2;
  for (let y = y0 + ((y0 % 2) ? 1 : 0); y <= y1; y += step) el('text', {x: X(T(y + '-01-01')), y: H2 - 8, 'text-anchor': 'middle', class: 'ax'}, svg, y);
  const series = [[3, 'BOXX line', 'var(--ctx2)', 1.4], [2, 'SPY', 'var(--s2)', 1.8], [1, 'sleeve', 'var(--s1)', 2.2]];
  const ends = series.map(([k, n]) => ({k, n, v: pts[pts.length - 1][k], y: Y(pts[pts.length - 1][k])})).sort((a, b2) => a.y - b2.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  series.forEach(([k, n, c, w]) => {
    el('polyline', {points: pts.map(p => `${X(T(p[0]))},${Y(p[k])}`).join(' '), fill: 'none', stroke: c, 'stroke-width': w, 'stroke-linejoin': 'round'}, svg);
    const e = ends.find(x => x.k === k); el('text', {x: W - r + 6, y: e.y + 4, class: 'lbb', fill: c}, svg, `${n} $${e.v >= 100 ? e.v.toFixed(0) : e.v.toFixed(2)}`);
  });
  const cd = new Set(D.crash_all.map(x => x.date));
  pts.filter(p => cd.has(p[0])).forEach(p => el('line', {x1: X(T(p[0])), x2: X(T(p[0])), y1: Y(p[1]) + 4, y2: Y(p[1]) + 10, stroke: 'var(--s4)', 'stroke-width': 1.2}, svg));
  el('text', {x: l + 6, y: t + 10, class: 'lb'}, svg, title);
  const hot = el('rect', {x: l, y: t, width: W - l - r, height: H2 - t - b, fill: 'transparent'}, svg);
  hot.addEventListener('mousemove', e => { const bb = svg.getBoundingClientRect(), ms = t0 + (e.clientX - bb.left) / bb.width * W > l ? t0 + ((e.clientX - bb.left) / bb.width * W - l) / (W - l - r) * (t1 - t0) : t0; let p = pts[0]; for (const q of pts) { if (T(q[0]) <= ms) p = q; else break; } tip(e, `<b>${p[0]}</b><br>sleeve $${p[1].toFixed(2)} · SPY $${p[2].toFixed(2)} · BOXX $${p[3].toFixed(2)}`); });
  hot.addEventListener('mouseleave', untip);
}
legend('lgD', [['sleeve (path, Composer-equivalent costs)', 'var(--s1)'], ['SPY total return', 'var(--s2)'], ['BOXX (BIL before 2022-12, T-bill before 2007)', 'var(--ctx2)'], ['SPY ≤ −3% day', 'var(--s4)']]);
curve('chD1', D.curves['2015-06+'], `2015-06..2026-11-05: sleeve CAGR ${sg(C15.cagr)}, max DD ${pc0(C15.maxdd)}; SPY ${sg(C15.spy_cagr)}, ${pc0(C15.spy_maxdd)}; BOXX ${sg(C15.cash_cagr)}`);
curve('chD2', D.curves['1995-06+'], `1995-06..2026-11-05 (synthetic before 2015): sleeve CAGR ${sg(C95.cagr)}, max DD ${pc0(C95.maxdd)}; SPY ${sg(C95.spy_cagr)}, ${pc0(C95.spy_maxdd)}`);

// E: convexity scatter
(function(){
  const svg = document.getElementById('chE'), W = 900, H2 = 360, l = 54, r = 20, t = 16, b = 40;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const xs = D.scatter.map(p => p[0]), ys = D.scatter.map(p => p[1]);
  const xlo = Math.min(...xs) - 0.005, xhi = Math.max(...xs) + 0.005, ylo = Math.min(...ys) - 0.01, yhi = Math.max(...ys) + 0.01;
  const X = v => l + (v - xlo) / (xhi - xlo) * (W - l - r), Y = v => t + (yhi - v) / (yhi - ylo) * (H2 - t - b);
  for (let v = Math.ceil(ylo * 20) / 20; v <= yhi; v += 0.05) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  for (let v = Math.ceil(xlo * 50) / 50; v <= xhi; v += 0.02) { el('line', {x1: X(v), x2: X(v), y1: t, y2: H2 - b, stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: X(v), y: H2 - b + 14, 'text-anchor': 'middle', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  el('text', {x: W - r, y: H2 - 4, 'text-anchor': 'end', class: 'ax'}, svg, 'SPY daily return → ; sleeve daily return ↑ ; 2015-06..2026-11-05, every session');
  D.scatter.forEach(p => { const c = el('circle', {cx: X(p[0]), cy: Y(p[1]), r: Math.abs(p[0]) >= 0.03 ? 3 : 1.7, fill: Math.abs(p[0]) >= 0.03 ? 'var(--s1)' : 'var(--pt)'}, svg); if (Math.abs(p[0]) >= 0.03) { c.addEventListener('mousemove', e => tip(e, `<b>${p[2]}</b> SPY ${sg(p[0])}, sleeve ${sg2(p[1])}`)); c.addEventListener('mouseleave', untip); } });
  const dn = C15.down, up = C15.up;
  el('line', {x1: X(xlo), y1: Y(dn.alpha + dn.beta * xlo), x2: X(0), y2: Y(dn.alpha), stroke: 'var(--neg)', 'stroke-width': 2.5}, svg);
  el('line', {x1: X(0), y1: Y(up.alpha), x2: X(xhi), y2: Y(up.alpha + up.beta * xhi), stroke: 'var(--s3)', 'stroke-width': 2.5}, svg);
  el('text', {x: X(xlo) + 6, y: Y(dn.alpha + dn.beta * xlo) - 8, class: 'lbb', fill: 'var(--neg)'}, svg, `down days: β ${f2(dn.beta)} (t ${f1(dn.t)}, n ${dn.n})`);
  el('text', {x: X(xhi) - 6, y: Y(up.alpha + up.beta * xhi) - 10, class: 'lbb', fill: 'var(--s3)', 'text-anchor': 'end'}, svg, `up days: β ${sf2(up.beta)} (t ${f1(up.t)}, n ${up.n})`);
  legend('lgE', [['one session', 'var(--pt)'], ['|SPY| ≥ 3%', 'var(--s1)'], ['OLS on SPY < 0 days', 'var(--neg)'], ['OLS on SPY > 0 days', 'var(--s3)']]);
  document.getElementById('subE').textContent = `A convex hedge slopes down on the left and flat or up on the right. The sleeve does: on down days its beta to SPY is ${f2(dn.beta)} (${f2(C15.spy_le_2pct.beta)} on SPY ≤ −2% days), on up days ${f2(up.beta)}; the whole-sample correlation is ${f2(C15.corr_with_spy)}. The buckets below show the same shape as means: large losses pay, small moves earn nothing, moderate rallies cost a little, and the biggest rallies pay again because the dip-buy legs (SOXL, TQQQ) are on. With every leg real (2020-12+) the up-day beta turns negative (${f2(CR.up.beta)}): the InverseHold legs were on ${pc0(CR.inverse_out_share)} of those days and lose on rallies.`;
  const wins = ['2015-06+', '2020-12+ (all legs real)', '1995-06+'];
  let h = '<thead><tr><th>window</th><th class="n">sessions</th><th class="n">β down days (t)</th><th class="n">β up days (t)</th><th class="n">β SPY ≤ −2% (n)</th><th class="n">corr</th>' + C15.buckets.map(bk => `<th class="n">SPY ${bk.lo <= -1 ? '≤ −3%' : bk.hi >= 1 ? '> +3%' : (bk.lo * 100).toFixed(0) + '..' + (bk.hi * 100).toFixed(0) + '%'}</th>`).join('') + '<th class="n">CAGR (SPY, BOXX)</th><th class="n">max DD</th><th class="n">days parked</th><th class="n">Frontrun leg on</th><th class="n">InverseHold leg on</th></tr></thead><tbody>';
  wins.forEach(w => { const v = D.conv[w]; h += `<tr><td>${w}</td><td class="n">${v.n}</td><td class="n">${f2(v.down.beta)} (${f1(v.down.t)})</td><td class="n">${f2(v.up.beta)} (${f1(v.up.t)})</td><td class="n">${f2(v.spy_le_2pct.beta)} (${v.spy_le_2pct.n})</td><td class="n">${f2(v.corr_with_spy)}</td>` + v.buckets.map(bk => `<td${cls(bk.sleeve)}>${sg2(bk.sleeve)}<br><span class="dim">n ${bk.n}, up ${pc0(bk.hit)}</span></td>`).join('') + `<td class="n">${sg(v.cagr)} (${sg(v.spy_cagr)}, ${sg(v.cash_cagr)})</td><td class="n">${pc0(v.maxdd)}</td><td class="n">${pc0(v.parked_share)}</td><td class="n">${pc0(v.frontrun_out_share)}</td><td class="n">${pc0(v.inverse_out_share)}</td></tr>`; });
  const K = D.carry;
  h += `<tr><td colspan="19" class="dim">Carry: calendar years with no SPY ≤ −3% day. 2015-06+: ${K['2015-06+'].calm_years.join(', ')} → sleeve mean ${sg(K['2015-06+'].calm_mean)}, median ${sg(K['2015-06+'].calm_median)}, worst ${sg(K['2015-06+'].calm_min)} (SPY mean ${sg(K['2015-06+'].calm_spy_mean)}); years with such days: mean ${sg(K['2015-06+'].rough_mean)}. Since 1995 (${K['1995-06+'].calm_years.length} calm years): mean ${sg(K['1995-06+'].calm_mean)}, median ${sg(K['1995-06+'].calm_median)}, worst ${sg(K['1995-06+'].calm_min)}; rough years mean ${sg(K['1995-06+'].rough_mean)}. In sample the sleeve costs nothing to hold; on the synthetic years before its authors' data it earned about T-bills.</td></tr></tbody>`;
  document.getElementById('tbE').innerHTML = h;
  document.getElementById('tbE2').innerHTML = '<thead><tr><th>year</th><th class="n">sleeve</th><th class="n">SPY</th><th class="n">BOXX line</th><th class="n">SPY ≤ −3% days</th><th class="n">≤ −4%</th><th class="n">worst SPY day</th><th class="n">days parked</th><th>calm?</th></tr></thead><tbody>' +
    Object.entries(D.years).map(([y, v]) => `<tr><td>${y}${+y < 2015 ? ' <span class="dim">(synthetic)</span>' : ''}</td><td${cls(v.sleeve)}>${sg(v.sleeve)}</td><td${cls(v.spy)}>${sg(v.spy)}</td><td class="n">${sg(v.cash)}</td><td class="n">${v.crash_days}</td><td class="n">${v.crash4_days}</td><td class="n neg">${sg(v.min_spy)}</td><td class="n">${pc0(v.parked)}</td><td>${v.calm ? 'calm' : ''}</td></tr>`).join('') + '</tbody>';
})();

// F: comparator
document.getElementById('tbF').innerHTML = '<thead><tr><th>instrument</th><th>window</th><th class="n">CAGR (sleeve, same window)</th><th class="n">max DD</th><th class="n">SPY ≤ −3% days: n</th><th class="n">mean same day (sleeve)</th><th class="n">share up (sleeve)</th><th class="n">next 5 after a crash day</th><th class="n">calm-year mean (sleeve)</th><th class="n">β down / up</th><th class="n">11-05</th></tr></thead><tbody>' +
  Object.entries(D.comp).map(([t, v]) => { const c = v.crash_days; return `<tr><td>${t} (static long mid-term VIX futures)</td><td>${v.from}..${v.to}</td><td${cls(v.cagr)}>${sg(v.cagr)} (${sg(v.sleeve_cagr_same_window)})</td><td class="n neg">${pc0(v.maxdd)}</td><td class="n">${c.n}</td><td${cls(c.mean)}>${sg(c.mean)} (${sg(c.sleeve_mean_same_days)})</td><td class="n">${pc0(c.hit)} (${pc0(c.sleeve_hit_same_days)})</td><td${cls(c.f5_mean)}>${sg(c.f5_mean)}</td><td${cls(v.calm_year_mean)}>${sg(v.calm_year_mean)} (${sg(v.sleeve_calm_year_mean)})</td><td class="n">${f2(v.down_beta)} / ${f2(v.up_beta)}</td><td${cls(v.d1105)}>${sg(v.d1105)}</td></tr>`; }).join('') +
  `<tr><td colspan="11" class="dim">At a 10% book weight: VIXM would have added about ${sg(D.comp.VIXM.crash_days.mean / 10)} of the book on an average crash day (the sleeve ${sg(D.comp.VIXM.crash_days.sleeve_mean_same_days / 10)}) and cost about ${sg(D.comp.VIXM.calm_year_mean / 10)} of the book per calm year (the sleeve ${sg(D.comp.VIXM.sleeve_calm_year_mean / 10)}, in sample). On 11-05 a 10% VIXM sleeve would have added ${sg(D.comp.VIXM.d1105 / 10)} of the book; the sleeve added nothing.</td></tr></tbody>`;

// G: states and transitions
document.getElementById('tbG').innerHTML = '<thead><tr><th>held leg</th><th>window</th><th class="n">days held</th><th class="n">leg\'s own return on those days</th><th class="n">up</th><th class="n">t</th><th class="n">on the other days</th><th class="n">t of the difference</th><th class="n">leg total while held</th></tr></thead><tbody>' +
  D.states.filter(s => s.window !== 'all' || !D.states.some(x => x.ticker === s.ticker && x.window !== 'all')).map(s => `<tr><td>${s.ticker}</td><td>${s.window} (${s.from.slice(0, 7)}..${s.to.slice(0, 7)})</td><td class="n">${s.n_on}</td><td${cls(s.mean_on)}>${sg2(s.mean_on)}</td><td class="n">${pc0(s.hit_on)}</td><td class="n">${f1(s.t_on)}</td><td${cls(s.mean_off)}>${sg2(s.mean_off)}</td><td class="n">${f1(s.t_diff)}</td><td${cls(s.leg_total)}>${sg(s.leg_total)}</td></tr>`).join('') + '</tbody>';
const TR = D.trans['2015-06+'], TR95 = D.trans['1995-06+'];
document.getElementById('tbG2').innerHTML = '<thead><tr><th>event (decided at the close of day d)</th><th class="n">n 2015-06+</th><th class="n">SPY next 5 (t vs any day)</th><th class="n">SPY next 20 (t)</th><th class="n">sleeve next 5 (positive)</th><th class="n">n 1995+</th><th class="n">SPY next 5 (t)</th><th class="n">SPY next 20 (t)</th></tr></thead><tbody>' +
  Object.keys(TR).map(k => { const v = TR[k], w = TR95[k]; return k === 'unconditional' ? `<tr><td>any day (unconditional)</td><td class="n">${v.n}</td><td class="n">${sg2(v.spy_f5)}</td><td class="n">${sg2(v.spy_f20)}</td><td class="n"></td><td class="n">${w.n}</td><td class="n">${sg2(w.spy_f5)}</td><td class="n">${sg2(w.spy_f20)}</td></tr>` : `<tr><td>${k}</td><td class="n">${v.n}</td><td${cls(v.spy_f5)}>${sg2(v.spy_f5)} (${f1(v.spy_f5_t_vs_uncond)})</td><td${cls(v.spy_f20)}>${sg2(v.spy_f20)} (${f1(v.spy_f20_t_vs_uncond)})</td><td${cls(v.sleeve_f5)}>${sg2(v.sleeve_f5)} (${pc0(v.sleeve_f5_hit)})</td><td class="n">${w.n}</td><td${cls(w.spy_f5)}>${sg2(w.spy_f5)} (${f1(w.spy_f5_t_vs_uncond)})</td><td${cls(w.spy_f20)}>${sg2(w.spy_f20)} (${f1(w.spy_f20_t_vs_uncond)})</td></tr>`; }).join('') +
  `<tr><td colspan="8" class="dim">After a SPY ≤ −3% day the sleeve's next 5 sessions averaged ${sg(D.csig['2015-06+'].sleeve_f5_after_crash)} vs ${sg2(D.csig['2015-06+'].sleeve_f5_any_day)} on any day (t ${f1(D.csig['2015-06+'].t)}, n ${D.csig['2015-06+'].n}; since 1995: ${sg(D.csig['1995-06+'].sleeve_f5_after_crash)} vs ${sg2(D.csig['1995-06+'].sleeve_f5_any_day)}, t ${f1(D.csig['1995-06+'].t)}). Candidate edges (|t| ≥ 2, n ≥ 30): ${D.edges.map(e => e.kind === 'held-leg conditional return' ? `${e.ticker} while held ${sg2(e.mean_on)}/day vs ${sg2(e.mean_off)} (t ${f1(e.t_diff)}, n ${e.n}; out of sample from 2023-04: ${e.oos ? sg2(e.oos.mean_on) + ', t ' + f1(e.oos.t_diff) + ', n ' + e.oos.n_on : 'n/a'})` : `${e.kind}: SPY ${e.horizon} ${sg2(e.spy_fwd)} vs ${sg2(e.uncond)} (t ${f1(e.t)}, n ${e.n})`).join('; ')}. All are the sleeve's own rules read back on the history they were built on; the only use is the sleeve itself, and the only test is its live log.</td></tr></tbody>`;

// basis
const V = D.val;
[`Rules: fixtures/approved/sleeve-yHJkdePZ.json (era from 2026-07-31, BOXX legs; identical logic with BIL legs before), evaluated by scripts/shadow_runner.py (Wilder RSI over the fetched history) on Yahoo adjusted closes fetched ${D.live.daily_json_mtime_utc ? 'at 16:50 ET on 11-05' : ''} (2 years, the production shadow's own window). The scratch daily.json used elsewhere in this batch holds an 11:45 ET print for 11-05 (SPY ${D.live.daily_json_1105_spy.toFixed(2)} vs the 733.00 close, VIX 23.3 vs 28.2): every 11-05 number here is the 16:00 close. The pre-close preview's "firm" label means no 2-sigma market or one-ticker move by 15:50 could flip the answer; on this tree that was correct.`,
 `History: the add. 47 daily path (research/longrun/book1997.py: the live tree on long_panel.py's panel, 1995-06..2026-11-04, Composer-equivalent costs of 5.1 bps per unit turnover; no borrow fees, no limit-down fills) plus a live row for 11-05 (BOXX 100%, real BOXX). Before each fund's launch its leg is a model: UVXY/SVXY from a VIX term-structure fit (from 2011-10 real; 2006-07..2011 on the real VIX3M; before 2006-07 on a synthetic curve from the VIX alone: a market that did not trade), LABD = −3x XBI/NBI before 2015-05, TMV/TMF = ∓3x TLT before 2009-04, SOXS/SOXL = ∓3x SOX before 2010-03, UGL = 2x gold, KMLM's signal = RYMFX 2007..2020-12 and an MLM-style trend proxy before, HYG/LQD/IEF/SHY/TLT = Vanguard funds before 2002-2007, CORP = LQD before 2010-09, PSQ = −1x NDX before 2006-06, KIE/PEJ = Ken French industries before 2005. BOXX is BIL (T-bills before 2007-05) on every day of the path, real BOXX only in the live row. "Since 2015-06" therefore still carries the RYMFX signal to 2020-12; "all legs real" = 2020-12 on.`,
 `In sample: the two components were authored 2023-25 on this history (add. 4: InverseHold's record is out of sample from ~2023-04, FrontrunBonds' Aug-2024 was out of sample; add. 4b's both-OOS slice starts 2024-06). The convexity betas, the crash-day means and the calm-year carry since 2015 are a rule replay on the authors' own data; the 2024-06+ rows (4 crash days) and the live log since 2026-07 are the only out-of-sample evidence. The pre-2015 path is the opposite kind of evidence: rules the authors never saw, on legs that are models.`,
 `Path fidelity: Composer's live holdings (shadow ledger, 2026-07-15..11-04) match the path's decision at the same close on ${V.agree} of ${V.n} sessions (BIL read as BOXX). Misses: ${V.misses.map(m => `${m.date} (${m.status}: live ${fw(m.live)}, path ${fw(m.path)})`).join('; ')}. Three are Composer knife-edge days; the early-October ones are RSI(LQD,14) reading just under 25 on the long panel's RSI seeding and not on Composer's, which the production shadow (2-year seeding) matched. The sleeve's own simulator fidelity vs Composer in the real era is 0.9985 daily (add. 39).`,
 `Fire counts in table A ignore the cascade order (a later condition can read true while an earlier one took the branch) and use the real series with KMLM = RYMFX before 2020-12; the InverseHold gate reads true on about a third of days, and what it then holds depends on the two inner RSI tests. Forward-return means after crash days use overlapping windows and are dominated by 2020-03 and 2022; medians and ex-2020 rows are given.`,
 `The sleeve is a conditional hedge by design: it is paid to be in BOXX most of the time (${pc0(C15.parked_share)} of days since 2015) and to buy vol or inverse funds after a bond or credit shock, which equity-led selloffs with calm Treasuries (2015-08, 2018-12, 2025-04, 2026-11-05) do not supply. Nothing here is a forecast; in-sample CAGRs are not expected returns. The owner's sizing decision (POLICY Op 1: 10% of crash-exposed assets, band 7-15%; Op 2 review 2027-01-22) governs; this audit changes nothing and recommends no trade.`,
 `Generated ${D.generated} by research/crash/sleeve_audit.py and make_sleeve_chart.py; every number is in results/sleeve-audit-2026-11-05.json.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
