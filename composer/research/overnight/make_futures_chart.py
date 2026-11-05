#!/usr/bin/env python3
"""Exhibit for the futures-and-volume study (futures_signals.py -> results/futures-signals-2026-11-05.json):
composer/results/futures-signals-2026-11-05.html. Inline SVG, no external libraries, light/dark."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")
PAGE = os.path.join(RES, "futures-signals-2026-11-05.html")


def main():
    r = json.load(open(os.path.join(RES, "futures-signals-2026-11-05.json")))
    B, A, Dv, rth = r["B_overnight_session"], r["A_prior_session_volume"], r["D_opening_volume"], r["C_rth_paths"]
    nights = [{k: x.get(k) for k in ("date", "es", "es_volr", "es_rec", "zn", "SPY_gap", "SPY_oc", "tech3_oc", "kmlm_leg", "kmlm_oc")} for x in r["nights"]]
    opening = {f: {"rows": v.get("rows", []), "t_oc": (v.get("corr_ratio_vs_oc") or {}).get("t"), "t_abs": (v.get("corr_ratio_vs_abs_oc") or {}).get("t")}
               for f, v in Dv.items() if isinstance(v, dict)}
    data = {"B": {k: v for k, v in B.items()}, "A": A, "opening": opening, "rth": rth, "nights": nights,
            "coverage": r["coverage"], "generated": r["generated"]}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(PAGE, "w").write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Futures volume overnight</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--ctx:#b9b7ae;--ctx2:#8e8c84;--neg:#e34948;--band:rgba(42,120,214,.18)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22)}
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
tr.grp td{color:var(--ink);font-weight:600;background:var(--page)}
details{margin-top:8px;font-size:13.5px}summary{cursor:pointer;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.neg{color:var(--neg)}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media (max-width:760px){.two{grid-template-columns:1fr}}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:340px}
</style>
</head>
<body>
<main>
<h1>Futures volume and the overnight session: what the futures tape adds to the overnight signals</h1>
<p class="sub-h">Add. 53 read prices only and no futures. This adds the futures tape on two horizons: the Globex overnight session itself (ES, NQ, 10-year note, gold, yen; hourly bars with volume, June 2024 to November 2026, the only free intraday futures history) and the prior session's volume (ES, NQ, the fund's own, SPY's) back to 2015 on the mornings add. 53 studied. Outcomes are the next regular session's open-to-close move of SPY and of the three tech 3x funds, and of the KMLM leg when it held one. Every split is permutation-tested; the family-wise p counts all the splits tried on a sample.</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>A. The 11-05 crash was not an overnight event: the futures tape was flat until 09:00</h2>
<p class="sub-h">ES futures from the prior cash close, hour by hour, for 11-04 (the night before KMLM flipped bullish) and 11-05. Bars: ES volume per hour on 11-05 (the shaded band is the cash session). Overnight into 11-05 the ES was +0.04% at 09:00 on normal volume (1.0x its 20-night median) and a normal range; NQ was −0.9%, gold +1.5%. The −4.4% came between 09:00 and 16:00, three quarters of it by 11:00. No pre-open read of the futures, price or volume, had it; the funds' own 09:30 prints did (SMH gap −4.4%, SOXL −14.6%: add. 53's signal, which the engines' legs bounce from on average and did not that day).</p>
<div class="legend" id="lgA"></div>
<div class="chartwrap"><svg id="chA" role="img" aria-label="ES futures cumulative return by hour from the prior close on 2026-11-04 and 2026-11-05, with hourly volume on 11-05"></svg></div>
</section>

<section class="card">
<h2>B. The overnight tape predicts the size of the session, not its direction, and the size read is the range</h2>
<p class="sub-h">582 nights. Above: the session's open-to-close move of SPY against the overnight ES move; the line is the fit over all nights (the overnight move reverses on average: slope −0.13, t −2.2; for the tech 3x funds −0.68, t −2.4), high-volume nights in orange. Below: the absolute session move by tercile of overnight volume (blue) and of overnight range (orange). Heavy overnight volume is followed by a bigger session either way, but volume and range move together, and once the range is known volume adds nothing. Neither says which way (the fit on high-volume nights is the same reversal, t −1.8).</p>
<p class="sub-h" id="bDbl"></p>
<div class="legend" id="lgB"></div>
<div class="chartwrap"><svg id="chB" role="img" aria-label="Scatter of SPY session open-to-close against the overnight ES move, 582 nights, high-volume nights highlighted"></svg></div>
<div class="chartwrap" style="margin-top:10px"><svg id="chB2" role="img" aria-label="Mean absolute SPY session move by tercile of overnight ES volume"></svg></div>
</section>

<section class="card">
<h2>C. Down nights: what the futures tape says about the coming session</h2>
<p class="sub-h">Nights when ES was down 0.5% or more at 09:00 (n 73) and 1% or more (n 30). The session continued down about half the time, and the mean session move was positive. Each row splits the sample by one futures signal; the difference of means carries a single-test permutation p, and the family-wise p at the top of each block is for the largest difference among the splits tried, given over the splits with at least eight nights a side (the 2-6-night splits, a V already under way by 09:00, are shown as means only: the n 6 "recovered" cell at 0.5% is one night, 2025-04-09, the tariff pause, +11.2% for SPY; +1.0% without it). Nothing survives family-wise. The one split near p 0.05 single-test is the 10-year note up overnight at ES ≤ −1% (15 vs 15 nights, bonds confirming the risk-off: no bounce); volume and range splits are p 0.3-0.9.</p>
<div id="tbCwrap"></div>
<details open><summary>The ten worst nights, and this week</summary><div class="tablewrap"><table id="tbW"></table></div></details>
</section>

<section class="card">
<h2>D. Back to 2015: the prior session's volume on gap-down mornings</h2>
<p class="sub-h">The mornings add. 53 studied, now split by the prior session's volume relative to its 20-session median: the fund's own, ES, NQ, SPY. Paired bars: mean open-to-close when the condition holds (dark) and when it does not (light), with n and the single-test p. On the oversold-close sample the bounce does not depend on volume (family-wise p 0.81). On all 3%+ gap-downs the one split that survives is SPY climax volume (2x or more) the session before.</p>
<p class="sub-h" id="dRob"></p>
<div class="legend" id="lgD"></div>
<h2 style="font-size:14px;margin-top:8px" id="hD1"></h2><div class="chartwrap"><svg id="chD1" role="img" aria-label="Paired bars: mean open-to-close by volume condition, all 3% gap-downs"></svg></div>
<h2 style="font-size:14px;margin-top:8px" id="hD2"></h2><div class="chartwrap"><svg id="chD2" role="img" aria-label="Paired bars: mean open-to-close by volume condition, oversold-close 5% gap-downs"></svg></div>
<div id="dCont"></div>
<details><summary>Table: every condition and split, 2015-06..2026-11-05</summary><div class="tablewrap"><table id="tbA"></table></div></details>
</section>

<section class="card">
<h2>E. On the engines' own legs: volume does not rescue the exit rules</h2>
<p class="sub-h" id="eText"></p>
<div class="tablewrap"><table id="tbE"></table></div>
</section>

<section class="card">
<h2>F. Opening-minutes volume (illustration, last 30 sessions)</h2>
<p class="sub-h">The first five minutes' volume of SOXL and TECL against its 30-session median, from FMP's 1-minute bars. A heavy open is a read an IBKR layer could take at 09:35. Thirty sessions is an illustration, not a test; the full history would need one FMP call per fund-day.</p>
<div class="tablewrap"><table id="tbF"></table></div>
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
const cls = v => v == null ? ' class="n"' : (v < 0 ? ' class="n neg"' : ' class="n"');
const xr = v => v == null ? '–' : v.toFixed(2) + 'x', pc2 = v => v == null ? '–' : (v * 100).toFixed(2) + '%';
const B = D.B, A = D.A;
const c5 = B.case_1105 || {}, d05 = B.down['-0.5%'], d10 = B.down['-1.0%'], sv = B.size_by_volume.es_volr, rg = B.size_by_volume.es_ranger, sj = B.size_joint;
const a3 = A.conditions['any state AND own gap <= -3%'], e1 = A.conditions['oversold AND own gap <= -5% (the E1 sample)'], mir = A.conditions['MIRROR: any state AND own gap >= +3%'];
const spyClimax = n => (A.conditions[n].splits || {})['SPY volume >= 2x (climax)'] || {};
const fundClimax = n => (A.conditions[n].splits || {})['fund volume >= 2x (climax)'] || {};
const sc = spyClimax('any state AND own gap <= -3%'), scm = spyClimax('MIRROR: any state AND own gap >= +3%');
const nc5 = A.conditions['NOT oversold AND own gap <= -5%'], cc5 = fundClimax('NOT oversold AND own gap <= -5%'), nc3 = A.conditions['NOT oversold AND own gap <= -3%'], cc3 = fundClimax('NOT oversold AND own gap <= -3%'), cm5 = fundClimax('MIRROR: NOT overbought (RSI < 70) AND own gap >= +5%');
[[`${sg(c5.es.value)} overnight`, `ES at 09:00 ET on 11-05 vs the prior close, on ${xr(c5.es_volr.value)} its median overnight volume (${pc0(c5.es_volr.pct_rank)} percentile) and ${xr(c5.es_ranger.value)} its median range; NQ ${sg(c5.nq.value)}. The session then did ${sg(c5.SPY_oc.value)} (${pc0(c5.SPY_oc.pct_rank)} percentile of 582): the crash was intraday. The futures tape had nothing; the funds' own 09:30 prints did (SOXL −14.6%)`],
 [`${pc2(rg.abs_SPY_oc[0].mean)} → ${pc2(rg.abs_SPY_oc[2].mean)}`, `mean absolute SPY session move, lowest to highest tercile of the overnight RANGE (t ${f1(sj.range_alone.t)}). By overnight volume ${pc2(sv.abs_SPY_oc[0].mean)} → ${pc2(sv.abs_SPY_oc[2].mean)} (t ${f1(sj.volume_alone.t)}), but the two move together (r ${f2(sj.joint_abs_SPY_oc.r12)}) and jointly volume adds nothing (t ${f1(sj.joint_abs_SPY_oc.t1)}; range t ${f1(sj.joint_abs_SPY_oc.t2)}). Size is a price read; direction: none (the overnight move reverses, slope ${f2(B.carry_all.SPY_oc.slope)}, t ${f1(B.carry_all.SPY_oc.t)})`],
 [`${pc0(d05.continuation_rate.SPY_oc)} continuation`, `share of the ${d05.n} nights with ES down 0.5%+ at 09:00 on which SPY's session closed below its open; mean session ${sg2(d05.SPY_oc.base.mean)} (t ${f1(d05.SPY_oc.base.t)}). Volume ≥ 1.5x median: ${sg2(d05.SPY_oc.splits['ES volume >= 1.5x median'].yes.mean)} vs ${sg2(d05.SPY_oc.splits['ES volume >= 1.5x median'].no.mean)}, p ${f2(d05.SPY_oc.splits['ES volume >= 1.5x median'].p_perm)}; nothing in the twelve splits survives family-wise (p ${f2(d05.SPY_oc.p_family_n8)} over the splits with 8+ nights a side)`],
 [`${sg(sc.yes.mean)} / ${sg(cc5.yes.mean)}`, `climax volume the session before, two readings since 2015: 3%+ gap-downs after SPY traded 2x its median volume bounce (n ${sc.yes.n} vs ${sg(sc.no.mean)} on ${sc.no.n}; p ${f2(sc.p_perm)}, family-wise ${f2(a3.p_family)}; median ${sg(sc.yes_extra.median)}, ${sg(sc.yes_extra.wo_best3)} without the best three) — but a 5%+ gap-down on the fund's OWN climax volume when it was NOT oversold continues down (n ${cc5.yes.n}, median ${sg(cc5.yes_extra.median)}, ${pc0(cc5.yes_extra.win)} up; p ${f2(cc5.p_perm)}, family-wise ${f2(nc5.p_family)}; mirror none). Both to log, neither an edge`]]
 .forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; k.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(k); });

// A: the two nights hour by hour
(function(){
  const svg = document.getElementById('chA'), W = 900, H2 = 320, l = 54, r = 170, t = 16, b = 34;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const P = D.rth, days = ['2026-11-04', '2026-11-05'], col = {'2026-11-04': 'var(--ctx2)', '2026-11-05': 'var(--s2)'};
  legend('lgA', [['ES vs prior cash close, 11-05', 'var(--s2)'], ['same, 11-04', 'var(--ctx2)'], ['ES volume per hour, 11-05', 'var(--band)']]);
  const allv = days.flatMap(d => P[d].cum_ret_by_hour_end.map(p => p[1]));
  const lo = Math.min(...allv, 0) - 0.004, hi = Math.max(...allv, 0) + 0.004;
  const X = h => l + h / 17 * (W - l - r), Y = v => t + (hi - v) / (hi - lo) * (H2 - t - b);
  el('rect', {x: X(9.5), y: t, width: X(16) - X(9.5), height: H2 - t - b, fill: 'var(--grid)', opacity: 0.45}, svg);
  el('text', {x: X(12.75), y: t + 12, 'text-anchor': 'middle', class: 'ax'}, svg, 'cash session 09:30-16:00');
  const vol = P['2026-11-05'].vol_by_hour_start, vmax = Math.max(...vol.map(v => v[1]));
  vol.forEach(([h, v]) => { const hh = parseInt(h), hgt = v / vmax * (H2 - t - b) * 0.32; const rr = el('rect', {x: X(hh) + 2, y: H2 - b - hgt, width: Math.max(1, X(hh + 1) - X(hh) - 4), height: hgt, fill: 'var(--band)'}, svg);
    rr.addEventListener('mousemove', e => tip(e, `11-05 ${h}-${String(hh + 1).padStart(2, '0')}:00 ET: ${(v / 1000).toFixed(0)}k contracts`)); rr.addEventListener('mouseleave', untip); });
  for (let v = Math.ceil(lo * 100) / 100; v <= hi; v += 0.01) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  [0, 3, 6, 9, 12, 16].forEach(h => el('text', {x: X(h), y: H2 - 10, 'text-anchor': 'middle', class: 'ax'}, svg, h === 0 ? '00:00 ET' : String(h).padStart(2, '0') + ':00'));
  days.forEach(d => {
    const pts = [[0, null]].concat(P[d].cum_ret_by_hour_end.map(([h, v]) => [parseInt(h), v])).filter(p => p[1] != null);
    el('polyline', {points: pts.map(p => `${X(p[0])},${Y(p[1])}`).join(' '), fill: 'none', stroke: col[d], 'stroke-width': d.endsWith('05') ? 2.4 : 1.6, 'stroke-linejoin': 'round'}, svg);
    pts.forEach(p => { const c = el('circle', {cx: X(p[0]), cy: Y(p[1]), r: 2.6, fill: col[d]}, svg); c.addEventListener('mousemove', e => tip(e, `${d} at ${String(p[0]).padStart(2, '0')}:00 ET: ${sg2(p[1])} vs the prior cash close`)); c.addEventListener('mouseleave', untip); });
    const last = pts[pts.length - 1]; el('text', {x: W - r + 6, y: Y(last[1]) + 4, class: 'lbb', fill: col[d]}, svg, `${d.slice(5)} close ${sg(last[1])}`);
    const nine = pts.find(p => p[0] === 9); if (nine) el('text', {x: X(9) - 4, y: Y(nine[1]) - 8, 'text-anchor': 'end', class: 'lb', fill: col[d]}, svg, `09:00 ${sg2(nine[1])}`);
  });
})();

// B: scatter + terciles
(function(){
  legend('lgB', [['night with overnight ES volume above the median', 'var(--s2)'], ['below', 'var(--s1)'], ['fit, all nights', 'var(--ink2)']]);
  const N = D.nights.filter(n => n.es != null && n.SPY_oc != null), vm = B.carry_by_volume.es_volr_median;
  const svg = document.getElementById('chB'), W = 900, H2 = 380, l = 48, r = 20, t = 14, b = 36;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const xs = N.map(n => n.es), ys = N.map(n => n.SPY_oc);
  const xlo = Math.min(...xs) - 0.002, xhi = Math.max(...xs) + 0.002, ylo = Math.min(...ys) - 0.002, yhi = Math.max(...ys) + 0.002;
  const X = v => l + (v - xlo) / (xhi - xlo) * (W - l - r), Y = v => t + (yhi - v) / (yhi - ylo) * (H2 - t - b);
  for (let v = Math.ceil(ylo * 100) / 100; v <= yhi; v += 0.01) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 5, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  for (let v = Math.ceil(xlo * 100) / 100; v <= xhi; v += 0.01) { el('line', {x1: X(v), x2: X(v), y1: t, y2: H2 - b, stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: X(v), y: H2 - b + 14, 'text-anchor': 'middle', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  el('text', {x: W - r, y: H2 - 4, 'text-anchor': 'end', class: 'ax'}, svg, 'overnight ES move to 09:00 ET  →  SPY open-to-close that session (vertical)');
  N.forEach(n => { const c = el('circle', {cx: X(n.es), cy: Y(n.SPY_oc), r: 3, fill: (n.es_volr || 0) >= vm ? 'var(--s2)' : 'var(--s1)', opacity: 0.7}, svg);
    c.addEventListener('mousemove', e => tip(e, `<b>${n.date}</b><br>overnight ES ${sg2(n.es)}, volume ${xr(n.es_volr)}, recovered ${n.es_rec == null ? '–' : pc0(n.es_rec)} of the drop<br>SPY gap ${sg2(n.SPY_gap)}, open→close ${sg2(n.SPY_oc)}; tech 3x ${sg2(n.tech3_oc)}${n.kmlm_leg ? `<br>KMLM held ${n.kmlm_leg}: ${sg2(n.kmlm_oc)}` : ''}`)); c.addEventListener('mouseleave', untip); });
  const mx = xs.reduce((a, v) => a + v, 0) / xs.length, my = ys.reduce((a, v) => a + v, 0) / ys.length, sl = B.carry_all.SPY_oc.slope, ic = my - sl * mx;
  el('line', {x1: X(xlo), x2: X(xhi), y1: Y(ic + sl * xlo), y2: Y(ic + sl * xhi), stroke: 'var(--ink2)', 'stroke-width': 1.5, 'stroke-dasharray': '5 4'}, svg);
  ['2026-11-05', '2024-08-05', '2025-04-07', '2025-04-04'].forEach(d => { const n = N.find(x => x.date === d); if (!n) return; el('circle', {cx: X(n.es), cy: Y(n.SPY_oc), r: 6, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 1.2}, svg); el('text', {x: X(n.es) + 8, y: Y(n.SPY_oc) + 4, class: 'lb'}, svg, d.slice(2)); });
  const s2 = document.getElementById('chB2'), W2 = 900, Hh = 250, l2 = 48, r2 = 20, t2 = 14, b2 = 50;
  s2.setAttribute('viewBox', `0 0 ${W2} ${Hh}`);
  const rows = [['volume: lowest', sv.abs_SPY_oc[0], `< ${xr(sv.terciles[0])}`, 'var(--s1)', 'volume'], ['middle', sv.abs_SPY_oc[1], `${xr(sv.terciles[0])} – ${xr(sv.terciles[1])}`, 'var(--s1)', 'volume'], ['highest', sv.abs_SPY_oc[2], `≥ ${xr(sv.terciles[1])}`, 'var(--s1)', 'volume'],
                ['range: lowest', rg.abs_SPY_oc[0], `< ${xr(rg.terciles[0])}`, 'var(--s2)', 'range'], ['middle', rg.abs_SPY_oc[1], `${xr(rg.terciles[0])} – ${xr(rg.terciles[1])}`, 'var(--s2)', 'range'], ['highest', rg.abs_SPY_oc[2], `≥ ${xr(rg.terciles[1])}`, 'var(--s2)', 'range']];
  const hi2 = Math.max(...rows.map(x => x[1].mean)) * 1.25, gw = (W2 - l2 - r2) / 6, bw = gw * 0.6, Y2 = v => t2 + (hi2 - v) / hi2 * (Hh - t2 - b2);
  for (let v = 0; v <= hi2; v += 0.002) { el('line', {x1: l2, x2: W2 - r2, y1: Y2(v), y2: Y2(v), stroke: v === 0 ? 'var(--axis)' : 'var(--grid)'}, s2); el('text', {x: l2 - 5, y: Y2(v) + 4, 'text-anchor': 'end', class: 'ax'}, s2, (v * 100).toFixed(1) + '%'); }
  rows.forEach(([n, s, lab, col, kind], i) => { const x = l2 + i * gw + (gw - bw) / 2 + (i >= 3 ? 10 : -10); const rr = el('rect', {x, y: Y2(s.mean), width: bw, height: Hh - b2 - Y2(s.mean), rx: 2, fill: col}, s2);
    el('text', {x: x + bw / 2, y: Y2(s.mean) - 5, 'text-anchor': 'middle', class: 'lbb'}, s2, pc2(s.mean)); el('text', {x: x + bw / 2, y: Hh - b2 + 16, 'text-anchor': 'middle', class: 'lb'}, s2, n); el('text', {x: x + bw / 2, y: Hh - b2 + 31, 'text-anchor': 'middle', class: 'ax'}, s2, `${lab} · n ${s.n}`);
    rr.addEventListener('mousemove', e => tip(e, `overnight ES ${kind} ${lab} its 20-night median: mean |SPY open→close| ${pc2(s.mean)}, median ${pc2(s.median)}, n ${s.n}`)); rr.addEventListener('mouseleave', untip); });
  el('text', {x: W2 - r2, y: Hh - 4, 'text-anchor': 'end', class: 'ax'}, s2, 'mean absolute SPY open-to-close by tercile of overnight volume (blue) and overnight range (orange)');
  const dsr = B.size_double_sort.rows;
  document.getElementById('bDbl').innerHTML = `Range or volume? Jointly, |SPY open→close| on both ratios: range t ${f1(sj.joint_abs_SPY_oc.t2)}, volume t ${f1(sj.joint_abs_SPY_oc.t1)} (alone: range t ${f1(sj.range_alone.t)}, volume t ${f1(sj.volume_alone.t)}; the ratios correlate r ${f2(sj.joint_abs_SPY_oc.r12)}). Double sort, within each range tercile the above-median-volume half minus the rest: ${dsr.map((d, i) => `${['narrowest', 'middle', 'widest'][i]} ${sg2(d.diff)} (t ${f1(d.t)})`).join(', ')}. The size read is the range.`;
})();

// C: down-night splits
(function(){
  let h = '';
  for (const [thr, blk] of Object.entries(B.down)) {
    const S = blk.SPY_oc, T = blk.tech3_oc;
    h += `<div class="tablewrap"><table><thead><tr><th>ES down ${thr.replace('-', '')} or more at 09:00: n ${blk.n} · continuation ${pc0(blk.continuation_rate.SPY_oc)} (SPY) / ${pc0(blk.continuation_rate.tech3_oc)} (tech 3x) · session mean SPY ${sg2(S.base.mean)} (t ${f1(S.base.t)}), tech 3x ${sg2(T.base.mean)} (t ${f1(T.base.t)}) · family-wise p over the splits with 8+ nights a side: SPY ${f2(S.p_family_n8)}, tech ${f2(T.p_family_n8)} (over all twelve, which the 2-6-night splits dominate: ${f2(S.p_family)} / ${f2(T.p_family)})</th><th class="n">yes n</th><th class="n">SPY yes</th><th class="n">SPY no</th><th class="n">diff</th><th class="n">p</th><th class="n">tech 3x yes</th><th class="n">tech 3x no</th><th class="n">diff</th><th class="n">p</th></tr></thead><tbody>`;
    for (const name of Object.keys(S.splits || {})) { const s = S.splits[name], u = (T.splits || {})[name] || {yes: {}, no: {}};
      h += `<tr><td>${name}${s.small ? ' <span style="color:var(--muted)">(under 8 nights a side: means only)</span>' : ''}</td><td class="n">${s.yes.n} / ${s.no.n}</td><td${cls(s.yes.mean)}>${sg2(s.yes.mean)}</td><td${cls(s.no.mean)}>${sg2(s.no.mean)}</td><td${cls(s.diff)}>${sg2(s.diff)}</td><td class="n">${s.small ? '–' : f2(s.p_perm)}</td><td${cls(u.yes.mean)}>${sg2(u.yes.mean)}</td><td${cls(u.no.mean)}>${sg2(u.no.mean)}</td><td${cls(u.diff)}>${sg2(u.diff)}</td><td class="n">${u.small ? '–' : f2(u.p_perm)}</td></tr>`; }
    const k = blk.kmlm_leg;
    h += `<tr><td colspan="10" style="color:var(--ink2)">KMLM held a leveraged leg on ${k.n} of these nights: leg open→close ${sg2(k.oc.mean)} (t ${f1(k.oc.t)}); on the ${k.by_volume_high.n} with overnight volume ≥ 1.5x ${sg2(k.by_volume_high.mean)}, on the ${k.by_volume_low.n} others ${sg2(k.by_volume_low.mean)}. Exiting at the open would have lost on average either way.</td></tr></tbody></table></div>`;
  }
  const U = B.up_mirror;
  h += `<p class="sub-h" style="margin-top:8px">Mirror, ES up 0.5%+ overnight (n ${U.n}): SPY session ${sg2(U.SPY_oc.mean)} (t ${f1(U.SPY_oc.t)}), continuation ${pc0(U.continuation_rate_SPY)}; tech 3x ${sg2(U.tech3_oc.mean)}.</p>`;
  document.getElementById('tbCwrap').innerHTML = h;
  const rows = B.worst_nights.concat(B.this_week.filter(w => w.date >= '2026-11-04'));
  document.getElementById('tbW').innerHTML = '<thead><tr><th>night into</th><th class="n">ES overnight</th><th class="n">volume</th><th class="n">range</th><th class="n">recovered by 09:00</th><th class="n">low, hours before 09:00</th><th class="n">NQ</th><th class="n">10y note</th><th class="n">gold</th><th class="n">yen</th><th class="n">SPY gap</th><th class="n">SPY open→close</th><th class="n">tech 3x open→close</th><th>KMLM leg</th><th class="n">leg open→close</th></tr></thead><tbody>' +
    rows.map(x => `<tr><td>${x.date}</td><td${cls(x.es)}>${sg2(x.es)}</td><td class="n">${xr(x.es_volr)}</td><td class="n">${xr(x.es_ranger)}</td><td class="n">${x.es_rec == null || x.es >= 0 ? '–' : pc0(Math.min(x.es_rec, 1))}</td><td class="n">${x.es_lowh == null ? '–' : f1(x.es_lowh)}</td><td${cls(x.nq)}>${sg2(x.nq)}</td><td${cls(x.zn)}>${sg2(x.zn)}</td><td${cls(x.gc)}>${sg2(x.gc)}</td><td${cls(x.jpy)}>${sg2(x.jpy)}</td><td${cls(x.SPY_gap)}>${sg2(x.SPY_gap)}</td><td${cls(x.SPY_oc)}>${sg2(x.SPY_oc)}</td><td${cls(x.tech3_oc)}>${sg2(x.tech3_oc)}</td><td>${x.kmlm_leg || '–'}${x.kmlm_w ? ` (${pc0(x.kmlm_w)})` : ''}</td><td${cls(x.kmlm_oc)}>${sg2(x.kmlm_oc)}</td></tr>`).join('') + '</tbody>';
})();

// D: paired bars for two conditions + the full table
function pairChart(svgId, cond, title){
  const C = A.conditions[cond], names = Object.keys(C.splits || {}), rows = names.map(n => ({name: n, s: C.splits[n]}));
  document.getElementById(title).textContent = `${cond}: ${C.days} days, mean open→close ${sg2(C.base.mean)} (t ${f1(C.base.t)}), family-wise p ${f2(C.p_family)}`;
  const svg = document.getElementById(svgId), W = 900, rowH = 30, l = 290, r = 240, t = 8, H2 = rows.length * rowH + t + 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const vals = rows.flatMap(x => [x.s.yes.mean || 0, x.s.no.mean || 0]), lo = Math.min(0, ...vals) - 0.005, hi = Math.max(0.005, ...vals) + 0.005;
  const X = v => l + (v - lo) / (hi - lo) * (W - l - r), step = (hi - lo) > 0.08 ? 0.02 : 0.01;
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) { el('line', {x1: X(v), x2: X(v), y1: t, y2: H2 - 30, stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: X(v), y: H2 - 12, 'text-anchor': 'middle', class: 'ax'}, svg, (Math.round(v * 100) || 0) + '%'); }
  rows.forEach((x, i) => {
    const y = t + i * rowH, s = x.s;
    el('text', {x: l - 8, y: y + 18, 'text-anchor': 'end', class: 'lbb'}, svg, x.name);
    [[s.yes, 'var(--s1)', 3], [s.no, 'var(--ctx)', 15]].forEach(([st, c, dy]) => { if (st.n == null) return; const v = st.mean || 0, x0 = X(Math.min(0, v)), w = Math.abs(X(v) - X(0));
      const rr = el('rect', {x: x0, y: y + dy, width: Math.max(w, 1.5), height: 10, rx: 2, fill: c}, svg);
      rr.addEventListener('mousemove', e => tip(e, `<b>${x.name}</b> — ${st === s.yes ? 'holds' : 'does not hold'}: n ${st.n}, mean ${sg2(st.mean)}, median ${sg2(st.median)}, win ${pc0(st.win)}, t ${f1(st.t)}`)); rr.addEventListener('mouseleave', untip); });
    el('text', {x: W - r + 6, y: y + 18, class: 'ax'}, svg, `${sg(s.yes.mean)} (n ${s.yes.n}) vs ${sg(s.no.mean)} (n ${s.no.n}) · p ${f2(s.p_perm)}`);
  });
}
legend('lgD', [['condition holds', 'var(--s1)'], ['condition does not hold', 'var(--ctx)']]);
pairChart('chD1', 'any state AND own gap <= -3%', 'hD1');
pairChart('chD2', 'oversold AND own gap <= -5% (the E1 sample)', 'hD2');
document.getElementById('dRob').innerHTML = `Robustness of that split: ${sc.yes.n} days in ${sc.yes_extra.months} distinct months (not one crash); median ${sg(sc.yes_extra.median)}, ${pc0(sc.yes_extra.win)} up, ${sg(sc.yes_extra.wo_best3)} without the best three days; leave-one-month-out keeps the difference at ${sg(sc.lomo[0])}..${sg(sc.lomo[1])}; SPY itself on those mornings ${sg2(sc.spy_oc_yes.mean)} (t ${f1(sc.spy_oc_yes.t)}) vs ${sg2(sc.spy_oc_no.mean)}. The gap-up mirror (${scm.yes.n} days): mean ${sg(scm.yes.mean)} vs ${sg(scm.no.mean)} (p ${f2(scm.p_perm)}) but median ${sg(scm.yes_extra.median)} and ${pc0(scm.yes_extra.win)} closed up: a mean made by a few days of −10% or worse (${sg(scm.yes_extra.wo_worst3)} without the worst three), not a reversal rule. A tail effect to log, not an edge.`;
document.getElementById('dCont').innerHTML = `<h2 style="font-size:14px;margin-top:14px">The complement: a 5%+ gap-down on climax volume when the fund is NOT oversold continues down</h2><p class="sub-h">Found by the counter-agent in this study's own table. Fund-level mornings where the fund closed with RSI(10) at or above 30, gapped 5% or more at the open and had traded 2x its median volume the session before: ${cc5.yes.n} days in ${cc5.yes_extra.months} months, mean ${sg(cc5.yes.mean)}, median ${sg(cc5.yes_extra.median)}, ${pc0(cc5.yes_extra.win)} up, ${sg(cc5.yes_extra.wo_best3)} without the best three, vs ${sg(cc5.no.mean)} on the other ${cc5.no.n}; p ${f2(cc5.p_perm)} single-test, family-wise ${f2(nc5.p_family)} over ${Object.keys(nc5.splits).length} splits; leave-one-month-out ${sg(cc5.lomo[0])}..${sg(cc5.lomo[1])}; SPY itself ${sg2(cc5.spy_oc_yes.mean)} (t ${f1(cc5.spy_oc_yes.t)}) vs ${sg2(cc5.spy_oc_no.mean)}. At 3%+: ${cc3.yes.n} days, ${sg(cc3.yes.mean)} vs ${sg(cc3.no.mean)}, p ${f2(cc3.p_perm)}, family-wise ${f2(nc3.p_family)}. Mirror (5%+ gap-up on climax volume, fund not overbought): ${sg(cm5.yes.mean)} (n ${cm5.yes.n}, median ${sg(cm5.yes_extra.median)}) vs ${sg(cm5.no.mean)}, p ${f2(cm5.p_perm)}: no continuation up; the asymmetry is one-sided. It is the exact complement of add. 53's "oversold → bounce" (the engine's dip-buy legs are the oversold case) and the only rule in section E that would have exited 11-05: SOXL traded 2.5x its median volume on 11-04 and closed with RSI(10) 30.2. Twelve days, in sample, after a search: a pre-registered log of the next ten fund-level occurrences before any rule.</p>`;
(function(){
  let h = '<thead><tr><th>condition · split</th><th class="n">days</th><th class="n">yes n</th><th class="n">yes mean</th><th class="n">no n</th><th class="n">no mean</th><th class="n">diff</th><th class="n">p</th></tr></thead><tbody>';
  for (const [cond, C] of Object.entries(A.conditions)) {
    const v = C.volume_on_those_days;
    h += `<tr class="grp"><td>${cond}</td><td class="n">${C.days}</td><td colspan="6">mean open→close ${sg2(C.base.mean)} (t ${f1(C.base.t)}, win ${pc0(C.base.win)}); median volume on those days: fund ${xr(v.fund_volr.median)}, ES ${xr(v.es_volr.median)}, SPY ${xr(v.spy_volr.median)}${C.p_family != null ? `; family-wise p ${f2(C.p_family)} (largest: ${C.family_best})` : ''}</td></tr>`;
    for (const [n, s] of Object.entries(C.splits || {})) h += `<tr><td style="padding-left:22px">${n}</td><td></td><td class="n">${s.yes.n}</td><td${cls(s.yes.mean)}>${sg2(s.yes.mean)}</td><td class="n">${s.no.n}</td><td${cls(s.no.mean)}>${sg2(s.no.mean)}</td><td${cls(s.diff)}>${sg2(s.diff)}</td><td class="n">${f2(s.p_perm)}</td></tr>`;
  }
  document.getElementById('tbA').innerHTML = h + '</tbody>';
})();

// E: engine rules
(function(){
  let h = '<thead><tr><th>exit the leg at the open when…</th><th class="n">fires</th><th class="n">leg open→close, mean</th><th class="n">t</th><th class="n">win</th><th class="n">exit value, pp</th><th class="n">placebo pct</th></tr></thead><tbody>';
  for (const [e, E] of Object.entries(A.engines)) {
    h += `<tr class="grp"><td colspan="7">${e}: ${E.mornings} leveraged-long mornings ${E.window[0]}..${E.window[1]}; exiting every one of them would be worth ${E.base_exit_value_pp_all_mornings.toFixed(0)} pp</td></tr>`;
    for (const [n, r] of Object.entries(E.rules)) h += `<tr><td>${n}</td><td class="n">${r.n}</td><td${cls(r.leg_oc.mean)}>${sg2(r.leg_oc.mean)}</td><td class="n">${f1(r.leg_oc.t)}</td><td class="n">${pc0(r.leg_oc.win)}</td><td${cls(r.exit_value_pp)}>${r.exit_value_pp.toFixed(1)}</td><td class="n">${r.placebo_pct == null ? '–' : pc0(r.placebo_pct)}</td></tr>`;
  }
  document.getElementById('tbE').innerHTML = h + '</tbody>';
  const kx3 = A.engines.KMLM.rules['gap <= -3% AND fund volume >= 2x (climax) AND leg NOT oversold'] || {}, kx5 = A.engines.KMLM.rules['gap <= -5% AND fund volume >= 2x (climax) AND leg NOT oversold'] || {}, hx3 = A.engines.HG.rules['gap <= -3% AND fund volume >= 2x (climax) AND leg NOT oversold'] || {};
  const kc3 = A.engines.KMLM.rules['gap <= -3% AND fund volume >= 2x (climax) AND any state'] || {}, kco = A.engines.KMLM.rules['gap <= -3% AND fund volume >= 2x (climax) AND leg oversold'] || {};
  const ev = r => r.exit_value_pp == null ? '–' : r.exit_value_pp.toFixed(1);
  document.getElementById('eText').textContent = `Exit the KMLM or HG leveraged leg at the open when the gap and a volume condition both hold (25 bps round trip as add. 53). "Exit value" is the summed, not compounded, weight × (−open→close − 25 bps) over the fired mornings, in points of the symphony; the placebo percentile is the share of same-count draws of random leveraged-long mornings that score below the rule (higher is better). Volume does not rescue the exit rules: on any leg or on an oversold leg the climax-volume rules are among the worst in the table (KMLM gap ≤ −3% and fund volume ≥ 2x: ${kc3.n} fires, leg ${sg2((kc3.leg_oc || {}).mean)}, ${ev(kc3)} pp; on oversold legs ${kco.n} fires, ${ev(kco)} pp), because the legs bounce on exactly those mornings. The exception is the complement above: on legs that were NOT oversold the climax rules are positive on KMLM (gap ≤ −3%: ${kx3.n} fires, ${ev(kx3)} pp, ${kx3.exit_value_pp_ex_1105 == null ? '–' : kx3.exit_value_pp_ex_1105.toFixed(1)} without 11-05; gap ≤ −5%: ${kx5.n} fires, ${ev(kx5)} pp) and negative on HG (${hx3.n} fires, ${ev(hx3)} pp): too few fires to be more than a log line.`;
})();

// F: opening volume
(function(){
  const O = D.opening, funds = Object.keys(O);
  if (!funds.length) { document.getElementById('tbF').innerHTML = '<tbody><tr><td>not available in this run</td></tr></tbody>'; return; }
  const dates = [...new Set(funds.flatMap(f => O[f].rows.map(r => r.date)))].sort();
  let h = `<thead><tr><th>session</th>${funds.map(f => `<th class="n">${f} open 5-min volume vs median</th><th class="n">${f} gap</th><th class="n">${f} open→close</th>`).join('')}</tr></thead><tbody>`;
  for (const d of dates) h += `<tr><td>${d}</td>` + funds.map(f => { const r = O[f].rows.find(x => x.date === d) || {}; return `<td class="n">${r.open5_ratio == null ? '–' : xr(r.open5_ratio)}</td><td${cls(r.gap)}>${sg(r.gap)}</td><td${cls(r.oc)}>${sg(r.oc)}</td>`; }).join('') + '</tr>';
  h += `<tr><td colspan="${1 + 3 * funds.length}" style="color:var(--ink2)">Over these sessions, the opening-volume ratio against the session's open→close: ` + funds.map(f => `${f} t ${f1(O[f].t_oc)} (vs the absolute move t ${f1(O[f].t_abs)})`).join('; ') + '.</td></tr>';
  document.getElementById('tbF').innerHTML = h + '</tbody>';
})();

[`Futures data: Yahoo continuous front-month contracts (ES=F, NQ=F, ZN=F, GC=F, 6J=F). Hourly bars with volume exist for 730 days only (${D.coverage.nights} overnight sessions, ${B.first}..${B.last}; ${D.coverage.nights_dropped} sessions dropped where the bars do not frame the night: half-day sessions on :30 bars, five quarterly-expiry Fridays missing the 15:00 bar, one gap); 1-minute for 7 days. The overnight session is read from the cash close (the 15:00 bar's close, 16:00 ET) to the 08:00 bar's close (09:00 ET), half an hour before the open; add. 53's bridge covers 09:25, not 09:00. Daily futures volume (2000-) is the whole 23-hour session of the continuous contract: roll weeks distort it (the Tuesday to Thursday before expiry print 0.3-0.7x; 14% of "quiet" flags are roll days against a 12.6% base; no climax flag is), which the 20-session median ratio only partly removes. Yahoo repeats the prior session's volume on some days (ES: ${(D.coverage.patched_volume['ES=F'] || []).map(p => p[0]).join(', ')}); where the hourly bars cover the session the print was replaced by their sum x 1.06, else dropped — before the patch the 11-05 morning was filed under "ES volume < 1x" and alone made two rules positive. The first bar of each weeknight session (18:00 ET) prints zero volume.`,
 `Outcomes: raw opens and closes from the daily dataset (11-04/05 refreshed to the 16:00 closes); "tech 3x" is the equal-weighted open-to-close of SOXL, TECL and TQQQ. The KMLM leg is the reconstructed path's leveraged long (add. 47 pipeline) earning on the day; 11-05 uses the live holding (SOXL 75%), which the path does not yet contain. SPY's daily volume matches FMP's on 2,833 days (counter-agent).`,
 `Statistics: t with the sample sd; each split's p is a permutation of the outcome across the conditioning sample (4,000 shuffles); the family-wise p is the share of shuffles in which the largest absolute difference across the splits in that block reaches the observed largest, given over the splits with at least 8 observations a side (over all splits the largest difference is always a 2-6-night split, so that number says nothing). In section E the exit value is summed, not compounded (add. 53 compounded on the path), re-entry is always charged, and the placebo percentile is the share of random same-count draws below the rule.`,
 `What the tape adds: the SIZE of the coming session, read from the overnight range (t ${f1(sj.range_alone.t)}; volume alone t ${f1(sj.volume_alone.t)}, jointly t ${f1(sj.joint_abs_SPY_oc.t1)}), a sizing input, not a direction. Two climax-volume patterns since 2015, both found while searching 12 splits on each of 10 conditions: (1) SPY climax volume (≥ 2x its median) the session before a 3%+ gap-down → bounce (${sc.yes.n} days in ${sc.yes_extra.months} months, ${sg(sc.yes.mean)} vs ${sg(sc.no.mean)}, p ${f2(sc.p_perm)}, family-wise ${f2(a3.p_family)}; median ${sg(sc.yes_extra.median)}, ${sg(sc.yes_extra.wo_best3)} without the best three; the gap-up mirror's ${sg(scm.yes.mean)} is a mean made by six days of −10%, ${pc0(scm.yes_extra.win)} of those days closed up); (2) the fund's own climax volume before a 5%+ gap-down on a fund NOT oversold → continuation (${cc5.yes.n} days, ${sg(cc5.yes.mean)}, p ${f2(cc5.p_perm)}, family-wise ${f2(nc5.p_family)}; no mirror). They are add. 53's "oversold → bounce" and its complement seen through volume; on the engines' own mornings (section E) exiting on climax volume loses on oversold legs and pays on the 4 + 3 not-oversold fires. Candidates to log, not edges: the next ten occurrences of each, pre-registered. On 11-05 the futures had nothing overnight; the funds' own 09:30 prints did (SMH gap −4.4%, SOXL −14.6%, add. 53's signal), and the continuation pattern is the one rule that would have exited.`,
 `Not available free and not tested: VIX futures intraday (CBOE daily settlements only), open interest, the ES-SPY basis intraday, order flow and cumulative delta, options volume. FMP 1-minute bars run back to 2016 with volume but one call per fund-day, so the opening-volume read (section F) is 30 sessions.`,
 `Research only; nothing traded. Generated ${D.generated}.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
