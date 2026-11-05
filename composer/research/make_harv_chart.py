#!/usr/bin/env python3
"""Exhibit for the HARV-in-backwardation study (harv_backwardation.py).
Reads results/harv-backwardation-2026-11-05.json; writes results/harv-backwardation-2026-11-05.html
(inline SVG, house palette tokens, light/dark, no external libraries)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
SRC = os.path.join(RES, "harv-backwardation-2026-11-05.json")
PAGE = os.path.join(RES, "harv-backwardation-2026-11-05.html")
GROUPS = ("contango", "backwardation", "0..-3%", "-3..-8%", "< -8%")


def pc(x, d=1, sign=True):
    if x is None:
        return "n/a"
    return f"{x * 100:{'+' if sign else ''}.{d}f}%"


def main():
    r = json.load(open(SRC))
    rows = r["entries"]["rows"]
    bw_entries = [e for e in rows if e["depth"] < 0]
    real_entries = [e for e in rows if e["date"] >= "2023-04-19"]
    cond, tr, ps, H, C, L, rc = r["conditional"], r["trades"]["summary"], r["path_split"], r["harvester_number"], r["context_1105"], r["live"], r["regime_counts"]
    real_tr = tr["real ZVOL 2023-04+"]["groups"]
    c_real = cond["real ZVOL"]["horizons"]
    c_all = cond["all since 2006-07"]["horizons"]
    kpis = [
        [f"{pc(real_tr['backwardation']['pnl']['mean'], 2)} per trade, {real_tr['backwardation']['pnl']['win']:.0%} win",
         f"the engine's {real_tr['backwardation']['n']} ZVOL trades entered on an inverted close since ZVOL exists (2023-04), entry to exit, median "
         f"{real_tr['backwardation']['sessions_median']:.0f} session, {real_tr['backwardation']['sum_pnl_pp']:+.1f}pp in all (t {real_tr['backwardation']['pnl']['t']:.1f}); "
         f"since 2018 on real VXZ: {tr['real VXZ 2018-01+']['groups']['backwardation']['n']} trades, {pc(tr['real VXZ 2018-01+']['groups']['backwardation']['pnl']['mean'], 2)}, "
         f"{tr['real VXZ 2018-01+']['groups']['backwardation']['pnl']['win']:.0%} win. The two deep (VIX3M/VIX under −8%) trades both lost: "
         f"{', '.join(pc(e['harv_fwd']['1']) for e in C['deep_entries'] if e['era'] == 'real')}"],
        [f"{pc(c_real['20']['backwardation']['zvol']['mean'])} in 20 sessions",
         f"ZVOL itself after an inverted close, 2023-04..2026-11 ({c_real['20']['backwardation']['zvol']['n']} closes in {c_real['20']['backwardation']['episodes']} episodes, "
         f"t {c_real['20']['backwardation']['zvol']['t']:.1f}, {c_real['20']['backwardation']['placebo']['pct']:.0%} placebo percentile) against {pc(c_real['20']['contango']['zvol']['mean'])} after contango. "
         f"Since 2006 on the proxies the sign flips: {pc(c_all['20']['backwardation']['zvol']['mean'])} (n {c_all['20']['backwardation']['zvol']['n']}, t {c_all['20']['backwardation']['zvol']['t']:.1f}), "
         f"{pc(c_all['20']['< -8%']['zvol']['mean'])} when the inversion is deeper than 8% (n {c_all['20']['< -8%']['zvol']['n']})"],
        [f"×{ps['real ZVOL 2023-04+']['base']['multiple']:.2f} → ×{ps['real ZVOL 2023-04+']['cf_zvol_to_puls_when_inverted']['multiple']:.2f}",
         f"HARV's real-era path if the ZVOL weight went to PULS on every inverted decision close (CAGR {pc(ps['real ZVOL 2023-04+']['base']['cagr'])} → "
         f"{pc(ps['real ZVOL 2023-04+']['cf_zvol_to_puls_when_inverted']['cagr'])}; add. 47 C1 measured ×2.11 → ×2.00): the entries pay. Only on deep inversions: "
         f"×{ps['real ZVOL 2023-04+']['cf_zvol_to_puls_when_deep']['multiple']:.2f} real era ({ps['real ZVOL 2023-04+']['regimes']['< -8%']['n']} days), "
         f"×{ps['real VXZ 2018-01+']['base']['multiple']:.2f} → ×{ps['real VXZ 2018-01+']['cf_zvol_to_puls_when_deep']['multiple']:.2f} since 2018, "
         f"×{ps['2006-07+']['base']['multiple']:.2f} → ×{ps['2006-07+']['cf_zvol_to_puls_when_deep']['multiple']:.2f} since 2006 (modeled 2008 entries)"],
        [f"{pc(H['live_1105'], 2)} = HARV's own day",
         f"\"harvester 0.0202\" is Composer's last_percent_change for the symphony: the VXZ 36% leg held into the crash day earned it (VXZ {pc(H['vxz_ret_1105'])}; "
         f"close-to-close model {pc(H['model_close_to_close_1105'], 2)}, the gap is 15:50 fills). It sits at the {H['history_engine_real_era']['percentile_of_1105']:.0%} percentile of the engine's daily "
         f"returns (sd {pc(H['history_engine_real_era']['sd'], 2, False)}), the largest live day of {H['history_live_snapshots']['n']}; its correlation with ZVOL's next 20 sessions is "
         f"{H['as_a_signal']['real ZVOL 2023-04+']['corr_harv_day_vs_zvol_fwd20']:+.2f}: not a signal"]]
    data = {"kpis": kpis, "series": r["series"]["rows"], "zvol_start": "2023-04-19", "vxz_start": "2018-01-25", "asof": r["asof"],
            "bw_entries": [{"date": e["date"], "depth": e["depth"], "vix": e["vix"], "w": e["zvol_to"], "w0": e["zvol_from"], "era": e["era"], "harv20": e["harv_fwd"]["20"],
                            "harv1": e["harv_fwd"]["1"], "harv5": e["harv_fwd"]["5"], "zvol20": e["zvol_fwd"]["20"], "zvol1": e["zvol_fwd"]["1"], "hold": e.get("hold_len")} for e in bw_entries],
            "real_entries": real_entries, "cond": cond, "filter_effect": r["filter_effect"], "entries_summary": r["entries"]["summary"], "trades": tr, "path": ps, "harv": H, "ctx": C, "live": L, "rc": rc, "rule": r["rule"],
            "guard": r["guard"], "generated": r["generated"]}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(PAGE, "w").write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harvester in backwardation</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--ctx:#b9b7ae;--ctx2:#8e8c84;--neg:#e34948;--band:rgba(42,120,214,.18);--band2:rgba(235,104,52,.12);--band3:rgba(137,135,129,.10)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--band2:rgba(217,89,38,.16);--band3:rgba(137,135,129,.14)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--band2:rgba(217,89,38,.16);--band3:rgba(137,135,129,.14)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 12px;font-size:14px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:0 0 16px;min-width:0}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0 16px}
@media (max-width:760px){.kpis{grid-template-columns:1fr 1fr}}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:21px;font-weight:650}.kpi span{color:var(--ink2);font-size:13px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 8px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}.sw{display:inline-block;width:14px;height:12px;border-radius:3px}
.chartwrap{overflow-x:auto}.chartwrap svg{min-width:680px}
svg{display:block;width:100%;height:auto}.ax{fill:var(--muted);font-size:11px}.lb{fill:var(--ink2);font-size:12px}.lbb{fill:var(--ink);font-size:12px;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--grid)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}.tablewrap{overflow-x:auto}
details{margin-top:8px;font-size:13.5px}summary{cursor:pointer;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.neg{color:var(--neg)}.hl{background:var(--band2)}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:360px}
</style>
</head>
<body>
<main>
<h1>HARV's short-vol entries in VIX backwardation: paying on the way back, bleeding when the inversion is deep</h1>
<p class="sub-h" id="lead"></p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>A. ZVOL compounding only on inverted closes vs only on contango closes</h2>
<p class="sub-h">Each line compounds ZVOL's next-day return only on the days whose previous close had the stated regime (VIX3M/VIX under 1 = backwardation) and is flat on the others; the grey line is every day. Left: the real fund, 2023-04-19 to 2026-11-05. Right: 2006-07 onward on the add. 47 proxies (ZVOL = −0.971 × VXZ before 2023; VXZ itself modeled from the term structure before 2018-01-25), log scale, era bands shaded. In the real era an inverted close has been followed by a rebound; on the longer record it has been followed by more losses, and the deep inversions (2008, 2011, 2020) are where the proxy line falls.</p>
<div class="legend" id="lgA"></div>
<div class="chartwrap"><svg id="chA1" role="img" aria-label="ZVOL cumulative return by regime of the prior close, real fund, 2023 to 2026"></svg></div>
<div class="chartwrap"><svg id="chA2" role="img" aria-label="ZVOL cumulative return by regime of the prior close, proxies since 2006, log scale"></svg></div>
<details><summary>Table: ZVOL's next 1 / 5 / 20 sessions by regime and depth, each era, with the VXZ mirror and the placebo percentile</summary><div class="tablewrap"><table id="tbA"></table></div></details>
</section>

<section class="card">
<h2>B. The engine's entries: every close at which the ZVOL weight rose, by the regime at that close</h2>
<p class="sub-h" id="bLead">The rule holds ZVOL while SPY's short RSIs are under 25, which resolves in a session or two (median hold 1 session after an inverted entry). So the 20-session ZVOL path matters less than what the engine made while it held: the trade table compounds the engine's return from entry to the close that sent the weight back to zero. 11-05 is in the first table with its outcomes pending.</p>
<div class="tablewrap"><table id="tbB0"></table></div>
<div class="tablewrap"><table id="tbB1"></table></div>
<details open><summary>Summary by window and regime: entries (weight up), then trades (fresh entry to exit)</summary><div class="tablewrap"><table id="tbB2"></table></div><div class="tablewrap" style="margin-top:10px"><table id="tbB3"></table></div></details>
</section>

<section class="card">
<h2>C. HARV's next 20 sessions after each inverted-close entry, 2006 to 2026</h2>
<p class="sub-h">One bar per entry on an inverted close (the engine path; proxies before each fund's launch, the regime from the real VIX3M). Hover for the entry's depth, VIX, weight and ZVOL's own 20-session move. The 11-05 entry is the hollow marker at the right: pending.</p>
<div class="legend" id="lgC"></div>
<div class="chartwrap"><svg id="chC" role="img" aria-label="HARV next-20-session return after each backwardation entry since 2006"></svg></div>
</section>

<section class="card">
<h2>D. The "harvester" number: HARV's daily return, with the inverted closes marked</h2>
<p class="sub-h">monitor.py prints Composer's last_percent_change for the symphony next to the backwardation alert, so "harvester 0.0202" is HARV's own +2.02% on 11-05, not a signal: the 36% VXZ leg held into the crash day (decided at the 11-04 close because RSI(SPY,2) read 83) earned it, and at the 11-05 close the rule flipped to short vol. Bars: the engine's daily return 2023-04-19 to 2026-11-04 and the live 11-05; orange bars are days decided on an inverted close.</p>
<div class="legend" id="lgD"></div>
<div class="chartwrap"><svg id="chD" role="img" aria-label="HARV daily return 2023 to 2026 with backwardation-decided days marked and 11-05 highlighted"></svg></div>
<div class="tablewrap"><table id="tbD"></table></div>
</section>

<section class="card">
<h2>E. The live record so far</h2>
<p class="sub-h" id="liveLead"></p>
<div class="tablewrap"><table id="tbE"></table></div>
</section>

<section class="card">
<h2>F. 11-05 in context: the deep entries and the long-vol-to-short-vol flips</h2>
<p class="sub-h" id="ctxLead"></p>
<div class="tablewrap"><table id="tbF1"></table></div>
<details><summary>Table: the nine earlier flips from a VXZ day of +1% or more straight into ZVOL</summary><div class="tablewrap"><table id="tbF2"></table></div></details>
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
const f2 = v => v == null ? '–' : v.toFixed(2), f1 = v => v == null ? '–' : v.toFixed(1), pc = v => v == null ? '–' : (v * 100).toFixed(1) + '%', pc0 = v => v == null ? '–' : (Math.round(v * 100) || 0) + '%';
const sg = v => v == null ? '–' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%', sg2 = v => v == null ? '–' : (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%';
const cls = v => v == null ? ' class="n"' : (v < 0 ? ' class="n neg"' : ' class="n"');
const T = s => new Date(s + 'T12:00:00Z').getTime();
const RC = D.rc, HV = D.harv, CX = D.ctx, LV = D.live, RU = D.rule.decisions ? D.rule.decisions[D.asof] : null;
document.getElementById('lead').textContent = `At the 2026-11-05 close (SPY ${sg(RC.spy_1105)}, VIX ${RC.vix_1105.toFixed(1)}, VIX3M/VIX ${sg(RC.depth_1105)}) HARV rotated PULS 64 / VXZ 36 into ZVOL 60 / PULS 40. ` +
  `The rule has no term-structure input: nine voters on Wilder RSI(SPY, 2..10) weighted 36/16/8/8/8/8/8/4/4 buy ZVOL when their RSI is under 25 (on 11-05: RSI(2) ${f1(RU && RU.rsi_spy['2'])}, RSI(3) ${f1(RU && RU.rsi_spy['3'])}, RSI(4) ${f1(RU && RU.rsi_spy['4'])} fired, RSI(5) ${f2(RU && RU.rsi_spy['5'])} did not, so 36+16+8 = 60%), ` +
  `unless RSI(UVXY,14) is over 70 (it read ${f1(RU && RU.rsi_uvxy_14)}). No saved version has an HYG condition. The question is whether short vol bought on those oversold, inverted closes has paid.`;
D.kpis.forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; k.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(k); });

// ---------- A: cumulative by regime
function cumChart(id, rows, log, bands, yearStep){
  const svg = document.getElementById(id), W = 900, H2 = 300, l = 56, r = 178, t = 18, b = 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  let a = 1, bw = 1, ct = 1; const pts = [];
  rows.forEach(x => { a *= 1 + x[1]; if (x[2] < 0) bw *= 1 + x[1]; else ct *= 1 + x[1]; pts.push({d: x[0], ms: T(x[0]), a, bw, ct, dep: x[2]}); });
  const t0 = pts[0].ms, t1 = pts[pts.length - 1].ms, X = ms => l + (ms - t0) / (t1 - t0) * (W - l - r);
  let lo = Infinity, hi = -Infinity; pts.forEach(p => { lo = Math.min(lo, p.a, p.bw, p.ct); hi = Math.max(hi, p.a, p.bw, p.ct); });
  if (log) { lo = Math.log10(lo * 0.92); hi = Math.log10(hi * 1.08); } else { const pad = (hi - lo) * 0.06; lo -= pad; hi += pad; }
  const Y = v => t + (hi - (log ? Math.log10(v) : v)) / (hi - lo) * (H2 - t - b);
  (bands || []).forEach(bd => { const x0 = X(T(bd.from)), x1 = X(T(bd.to)); el('rect', {x: x0, y: t, width: x1 - x0, height: H2 - t - b, fill: bd.fill}, svg); el('text', {x: x0 + 4, y: t + 11, class: 'ax'}, svg, bd.label); });
  const ticks = log ? [0.2, 0.3, 0.5, 0.7, 1, 1.5, 2, 3, 5, 7, 10].filter(v => Math.log10(v) >= lo && Math.log10(v) <= hi) : (function(){ const s = (hi - lo) > 2 ? 0.5 : (hi - lo) > 1 ? 0.25 : 0.1, o = []; for (let v = Math.ceil(lo / s) * s; v <= hi; v += s) o.push(+v.toFixed(2)); return o; })();
  ticks.forEach(v => { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v - 1) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, '×' + v); });
  const y0 = +rows[0][0].slice(0, 4), y1 = +rows[rows.length - 1][0].slice(0, 4);
  for (let y = y0 + 1; y <= y1; y += yearStep) if (T(y + '-01-01') >= t0) el('text', {x: X(T(y + '-01-01')), y: H2 - 8, 'text-anchor': 'middle', class: 'ax'}, svg, y);
  const S = [['ct', 'var(--s1)', 'contango closes only'], ['bw', 'var(--s2)', 'inverted closes only'], ['a', 'var(--ctx2)', 'every day']];
  const ends = S.map(([k, c, n]) => ({k, c, n, v: pts[pts.length - 1][k], y: Y(pts[pts.length - 1][k])})).sort((p, q) => p.y - q.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  S.forEach(([k, c, n]) => {
    const step = Math.max(1, Math.floor(pts.length / 1800));
    const d = pts.filter((p, i) => i % step === 0 || i === pts.length - 1).map(p => `${X(p.ms).toFixed(1)},${Y(p[k]).toFixed(1)}`).join(' ');
    el('polyline', {points: d, fill: 'none', stroke: c, 'stroke-width': k === 'a' ? 1.3 : 2, 'stroke-linejoin': 'round'}, svg);
    const e = ends.find(x => x.k === k); el('text', {x: W - r + 6, y: e.y + 4, class: k === 'a' ? 'lb' : 'lbb', fill: c}, svg, `${n} ×${e.v.toFixed(2)}`);
  });
  const cross = el('line', {x1: l, x2: l, y1: t, y2: H2 - b, stroke: 'var(--axis)', 'stroke-dasharray': '3 3', visibility: 'hidden'}, svg);
  const hit = el('rect', {x: l, y: t, width: W - l - r, height: H2 - t - b, fill: 'transparent'}, svg);
  hit.addEventListener('mousemove', ev => {
    const bb = svg.getBoundingClientRect(), xs = (ev.clientX - bb.left) / bb.width * W, ms = t0 + (xs - l) / (W - l - r) * (t1 - t0);
    let i = pts.findIndex(p => p.ms >= ms); if (i < 0) i = pts.length - 1; const p = pts[i];
    cross.setAttribute('x1', X(p.ms)); cross.setAttribute('x2', X(p.ms)); cross.setAttribute('visibility', 'visible');
    tip(ev, `<b>${p.d}</b> (prior close ${p.dep < 0 ? 'inverted' : 'contango'} ${sg(p.dep)})<br>contango-only ×${p.ct.toFixed(3)} · inverted-only ×${p.bw.toFixed(3)} · all ×${p.a.toFixed(3)}`);
  });
  hit.addEventListener('mouseleave', () => { untip(); cross.setAttribute('visibility', 'hidden'); });
}
legend('lgA', [['contango closes only', 'var(--s1)'], ['inverted closes only', 'var(--s2)'], ['every day', 'var(--ctx2)']]);
cumChart('chA1', D.series.filter(x => x[0] >= D.zvol_start), false, [], 1);
cumChart('chA2', D.series, true, [{from: D.series[0][0], to: D.vxz_start, label: 'ZVOL = −0.971 × modeled VXZ', fill: 'var(--band3)'}, {from: D.vxz_start, to: D.zvol_start, label: '−0.971 × real VXZ', fill: 'var(--band2)'}, {from: D.zvol_start, to: D.asof, label: 'real ZVOL', fill: 'var(--band)'}], 2);
(function(){
  let h = '<thead><tr><th>era · regime at the close</th><th class="n">closes</th><th class="n">episodes</th><th class="n">next 1</th><th class="n">next 5</th><th class="n">next 20</th><th class="n">t (20)</th><th class="n">win (20)</th><th class="n">placebo pct (20)</th><th class="n">episode-start 20</th><th class="n">VXZ next 20</th></tr></thead><tbody>';
  for (const era in D.cond) {
    const E = D.cond[era]; h += `<tr><td colspan="11" style="color:var(--ink2)">${era}: ${E.from} to ${E.to}</td></tr>`;
    ['contango', 'backwardation', '0..-3%', '-3..-8%', '< -8%'].forEach(g => {
      const g1 = E.horizons['1'][g], g5 = E.horizons['5'][g], g20 = E.horizons['20'][g]; if (!g20 || !g20.zvol.n) return;
      const pl = g20.placebo || {}, es = g20.episode_start || {};
      h += `<tr${g === 'backwardation' ? ' class="hl"' : ''}><td>${g === 'backwardation' ? 'inverted (all depths)' : g}</td><td class="n">${g20.zvol.n}</td><td class="n">${g20.episodes == null ? '–' : g20.episodes}</td><td${cls(g1.zvol.mean)}>${sg2(g1.zvol.mean)}</td><td${cls(g5.zvol.mean)}>${sg2(g5.zvol.mean)}</td><td${cls(g20.zvol.mean)}>${sg(g20.zvol.mean)}</td><td class="n">${f1(g20.zvol.t)}</td><td class="n">${pc0(g20.zvol.win)}</td><td class="n">${pl.pct == null ? '–' : pc0(pl.pct)}</td><td${cls(es.mean)}>${es.mean == null ? '–' : sg(es.mean) + ' (n ' + es.n + ')'}</td><td${cls(g20.vxz.mean)}>${sg(g20.vxz.mean)}</td></tr>`;
    });
  }
  document.getElementById('tbA').innerHTML = h + '<tr><td colspan="11" style="color:var(--ink2)">Means of overlapping windows; t with the sample sd (overstated for 5/20-session windows, which is why the episode-start column, one row per run of inverted closes, is shown). Placebo: 2000 draws of the same number of random closes in the era; pct = share of draws with a lower mean.</td></tr></tbody>';
})();

// ---------- B: entries
(function(){
  const FE = D.filter_effect;
  document.getElementById('tbB0').innerHTML = '<thead><tr><th>inverted closes, by whether the rule is short vol into the next session</th><th class="n">closes</th><th class="n">ZVOL +1</th><th class="n">win (+1)</th><th class="n">ZVOL +5</th><th class="n">ZVOL +20</th><th class="n">deep (under −8%): closes</th><th class="n">ZVOL +1</th><th class="n">ZVOL +5</th><th class="n">ZVOL +20</th></tr></thead><tbody>' +
    Object.entries(FE).flatMap(([w, F]) => [['rule short vol (ZVOL weight > 0)', F.rule_short_vol, F.with, F.deep_with], ['rule not (PULS / VXZ)', F.rule_not, F.without, F.deep_without]].map(([lab, n, s, d], i) =>
      `<tr${i === 0 ? ' class="hl"' : ''}><td>${i === 0 ? w + ': ' : ''}${lab}</td><td class="n">${n}</td><td${cls(s['1'].mean)}>${sg2(s['1'].mean)}</td><td class="n">${pc0(s['1'].win)}</td><td${cls(s['5'].mean)}>${sg2(s['5'].mean)}</td><td${cls(s['20'].mean)}>${sg(s['20'].mean)}</td><td class="n">${d['1'].n}</td><td${cls(d['1'].mean)}>${d['1'].n ? sg2(d['1'].mean) : '–'}</td><td${cls(d['5'].mean)}>${d['5'].n ? sg2(d['5'].mean) : '–'}</td><td${cls(d['20'].mean)}>${d['20'].n ? sg(d['20'].mean) : '–'}</td></tr>`)).join('') +
    '<tr><td colspan="10" style="color:var(--ink2)">The SPY-oversold condition is a selection: of the inverted closes, the ones the rule shorts vol into are followed by a better ZVOL session than the ones it sits out (the 11-05 close is excluded; its next session is pending).</td></tr></tbody>';
  const rows = D.real_entries.filter(e => e.depth < 0);
  document.getElementById('tbB1').innerHTML = `<thead><tr><th>entry close</th><th class="n">VIX3M/VIX</th><th class="n">VIX</th><th class="n">SPY day</th><th class="n">HARV day</th><th class="n">ZVOL weight</th><th class="n">held</th><th class="n">ZVOL +1</th><th class="n">ZVOL +5</th><th class="n">ZVOL +20</th><th class="n">HARV +1</th><th class="n">HARV +5</th><th class="n">HARV +20</th><th class="n">VXZ +20</th></tr></thead><tbody>` +
    rows.map(e => `<tr${e.date === D.asof ? ' class="hl"' : ''}><td>${e.date}${e.date === D.asof ? ' (live, pending)' : ''}${e.vxz_held > 0 ? ' ◆' : ''}</td><td class="n neg">${sg(e.depth)}</td><td class="n">${e.vix.toFixed(1)}</td><td${cls(e.spy_day)}>${sg(e.spy_day)}</td><td${cls(e.harv_day)}>${sg2(e.harv_day)}</td><td class="n">${pc0(e.zvol_from)} → ${pc0(e.zvol_to)}</td><td class="n">${e.hold_len == null ? '–' : e.hold_len}</td><td${cls(e.zvol_fwd['1'])}>${sg(e.zvol_fwd['1'])}</td><td${cls(e.zvol_fwd['5'])}>${sg(e.zvol_fwd['5'])}</td><td${cls(e.zvol_fwd['20'])}>${sg(e.zvol_fwd['20'])}</td><td${cls(e.harv_fwd['1'])}>${sg2(e.harv_fwd['1'])}</td><td${cls(e.harv_fwd['5'])}>${sg2(e.harv_fwd['5'])}</td><td${cls(e.harv_fwd['20'])}>${sg2(e.harv_fwd['20'])}</td><td${cls(e.vxz_fwd['20'])}>${sg(e.vxz_fwd['20'])}</td></tr>`).join('') +
    `<tr><td colspan="14" style="color:var(--ink2)">Real ZVOL era, every inverted-close entry (${rows.length} incl. 11-05). "held" = sessions the engine kept any ZVOL weight afterwards. ◆ = the engine held VXZ that day and flipped straight into ZVOL (11-05 is one). HARV day = the engine's return on the entry day itself; 11-05's is the live +2.02%.</td></tr></tbody>`;
  const ES = D.entries_summary, TR = D.trades;
  let h = '<thead><tr><th>window · regime at entry</th><th class="n">entries</th><th class="n">fresh</th><th class="n">mean weight</th><th class="n">mean VIX</th><th class="n">held (median)</th><th class="n">ZVOL +1</th><th class="n">ZVOL +5</th><th class="n">ZVOL +20</th><th class="n">HARV +1</th><th class="n">HARV +5</th><th class="n">HARV +20</th><th class="n">t (20)</th><th class="n">win (20)</th></tr></thead><tbody>';
  for (const w in ES) { const W = ES[w]; h += `<tr><td colspan="14" style="color:var(--ink2)">${w} (${W.n} entries; ${W.pending} pending)</td></tr>`;
    ['contango', 'backwardation', '0..-3%', '-3..-8%', '< -8%'].forEach(g => { const x = W.groups[g]; if (!x || !x.n) return;
      h += `<tr${g === 'backwardation' ? ' class="hl"' : ''}><td>${g === 'backwardation' ? 'inverted (all depths)' : g}</td><td class="n">${x.n}</td><td class="n">${x.fresh}</td><td class="n">${pc0(x.mean_zvol_to)}</td><td class="n">${f1(x.mean_vix)}</td><td class="n">${x.hold_len_median == null ? '–' : x.hold_len_median}</td><td${cls(x.zvol_1.mean)}>${sg2(x.zvol_1.mean)}</td><td${cls(x.zvol_5.mean)}>${sg2(x.zvol_5.mean)}</td><td${cls(x.zvol_20.mean)}>${sg(x.zvol_20.mean)}</td><td${cls(x.harv_1.mean)}>${sg2(x.harv_1.mean)}</td><td${cls(x.harv_5.mean)}>${sg2(x.harv_5.mean)}</td><td${cls(x.harv_20.mean)}>${sg2(x.harv_20.mean)}</td><td class="n">${f1(x.harv_20.t)}</td><td class="n">${pc0(x.harv_20.win)}</td></tr>`; }); }
  document.getElementById('tbB2').innerHTML = h + '</tbody>';
  let g = '<thead><tr><th>window · regime at the fresh entry</th><th class="n">trades</th><th class="n">sessions (median / mean)</th><th class="n">P&amp;L mean</th><th class="n">median</th><th class="n">t</th><th class="n">win</th><th class="n">sum</th><th class="n">ZVOL-leg contribution</th><th>worst</th></tr></thead><tbody>';
  for (const w in TR) { const W = TR[w]; g += `<tr><td colspan="10" style="color:var(--ink2)">${w} (${W.n} trades)</td></tr>`;
    ['contango', 'backwardation', '0..-3%', '-3..-8%', '< -8%'].forEach(k => { const x = W.groups[k]; if (!x || !x.n) return;
      g += `<tr${k === 'backwardation' ? ' class="hl"' : ''}><td>${k === 'backwardation' ? 'inverted (all depths)' : k}</td><td class="n">${x.n}</td><td class="n">${x.sessions_median} / ${f1(x.sessions_mean)}</td><td${cls(x.pnl.mean)}>${sg2(x.pnl.mean)}</td><td${cls(x.pnl.median)}>${sg2(x.pnl.median)}</td><td class="n">${f1(x.pnl.t)}</td><td class="n">${pc0(x.pnl.win)}</td><td${cls(x.sum_pnl_pp)}>${x.sum_pnl_pp.toFixed(1)}pp</td><td${cls(x.zvol_contrib.mean)}>${sg2(x.zvol_contrib.mean)}</td><td>${x.worst} ${sg(x.worst_pnl)}</td></tr>`; }); }
  document.getElementById('tbB3').innerHTML = g + '<tr><td colspan="10" style="color:var(--ink2)">A trade runs from the close that first gives ZVOL weight to the close that takes it back to zero; P&amp;L is the engine\'s compounded return over those sessions (Composer-equivalent costs inside); the ZVOL-leg contribution is the sum of weight × ZVOL\'s return.</td></tr></tbody>';
})();

// ---------- C: bars per backwardation entry
(function(){
  const svg = document.getElementById('chC'), rows = D.bw_entries, W = 900, H2 = 300, l = 50, r = 16, t = 20, b = 30, n = rows.length;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const vals = rows.map(x => x.harv20).filter(v => v != null), lo = Math.min(-0.02, ...vals) - 0.01, hi = Math.max(0.02, ...vals) + 0.01;
  const gw = (W - l - r) / n, Y = v => t + (hi - v) / (hi - lo) * (H2 - t - b), X = i => l + i * gw;
  const eras = [['model', 'ZVOL = −0.971 × modeled VXZ', 'var(--band3)'], ['vxz', '−0.971 × real VXZ', 'var(--band2)'], ['real', 'real ZVOL', 'var(--band)']];
  eras.forEach(([k, lab, fill]) => { const idx = rows.map((x, i) => x.era === k ? i : -1).filter(i => i >= 0); if (!idx.length) return; const x0 = X(idx[0]), x1 = X(idx[idx.length - 1] + 1); el('rect', {x: x0, y: t, width: x1 - x0, height: H2 - t - b, fill}, svg); el('text', {x: x0 + 4, y: t + 11, class: 'ax'}, svg, `${lab} (${idx.length})`); });
  for (let v = Math.ceil(lo * 20) / 20; v <= hi; v += 0.05) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  let lastYear = null, lastLabelX = -1e9;
  rows.forEach((x, i) => {
    const yr = x.date.slice(0, 4);
    if (yr !== lastYear) { lastYear = yr; if ((+yr) % 2 === 0 && X(i) - lastLabelX >= 44) { el('text', {x: X(i), y: H2 - 10, class: 'ax'}, svg, yr); lastLabelX = X(i); } }
    if (x.harv20 == null) { const m = el('circle', {cx: X(i) + gw / 2, cy: Y(0), r: 5, fill: 'var(--surface)', stroke: 'var(--s1)', 'stroke-width': 2}, svg); el('text', {x: X(i) + gw / 2 - 8, y: t + 30, 'text-anchor': 'end', class: 'lbb'}, svg, '11-05: pending ○');
      m.addEventListener('mousemove', e => tip(e, `<b>${x.date}</b> live entry, outcomes pending<br>VIX3M/VIX ${sg(x.depth)}, VIX ${x.vix.toFixed(1)}, ZVOL ${pc0(x.w0)} → ${pc0(x.w)}`)); m.addEventListener('mouseleave', untip); return; }
    const y0 = Y(Math.max(0, x.harv20)), h = Math.abs(Y(x.harv20) - Y(0));
    const rr = el('rect', {x: X(i) + gw * 0.12, y: y0, width: Math.max(gw * 0.76, 1.2), height: Math.max(h, 1), fill: x.harv20 < 0 ? 'var(--neg)' : 'var(--s3)'}, svg);
    rr.addEventListener('mousemove', e => tip(e, `<b>${x.date}</b> (${x.era === 'real' ? 'real ZVOL' : x.era === 'vxz' ? '−VXZ proxy' : 'modeled proxy'})<br>VIX3M/VIX ${sg(x.depth)}, VIX ${x.vix.toFixed(1)}, ZVOL ${pc0(x.w0)} → ${pc0(x.w)}, held ${x.hold == null ? '–' : x.hold} session(s)<br>HARV next 1 / 5 / 20: ${sg2(x.harv1)} / ${sg2(x.harv5)} / <b>${sg2(x.harv20)}</b><br>ZVOL next 1 / 20: ${sg(x.zvol1)} / ${sg(x.zvol20)}`)); rr.addEventListener('mouseleave', untip);
  });
  legend('lgC', [[`HARV next 20 sessions ≥ 0 (${n} entries, chronological)`, 'var(--s3)'], ['< 0', 'var(--neg)']]);
})();

// ---------- D: harvester daily return
(function(){
  const svg = document.getElementById('chD'), rows = D.series.filter(x => x[0] >= D.zvol_start), W = 900, H2 = 280, l = 50, r = 16, t = 16, b = 30, n = rows.length;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const vals = rows.map(x => x[3]), lo = Math.min(...vals) - 0.004, hi = Math.max(...vals) + 0.006;
  const gw = (W - l - r) / n, Y = v => t + (hi - v) / (hi - lo) * (H2 - t - b), X = i => l + i * gw;
  for (let v = Math.ceil(lo * 100) / 100; v <= hi; v += 0.01) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  let lastYear = null;
  rows.forEach((x, i) => {
    const yr = x[0].slice(0, 4); if (yr !== lastYear) { el('text', {x: X(i), y: H2 - 10, class: 'ax'}, svg, yr); lastYear = yr; }
    const v = x[3], y0 = Y(Math.max(0, v)), h = Math.abs(Y(v) - Y(0)), live = x[0] === D.asof;
    const rr = el('rect', {x: X(i), y: y0, width: Math.max(gw, 1), height: Math.max(h, 0.8), fill: live ? 'var(--s1)' : x[2] < 0 ? 'var(--s2)' : 'var(--ctx2)'}, svg);
    if (live) { el('circle', {cx: X(i) + gw / 2, cy: Y(v) - 6, r: 3.5, fill: 'var(--s1)'}, svg); el('text', {x: X(i) - 6, y: Y(v) - 8, 'text-anchor': 'end', class: 'lbb'}, svg, `11-05 ${sg2(v)} (live): VXZ 36% leg`); }
    rr.addEventListener('mousemove', e => tip(e, `<b>${x[0]}</b> HARV ${sg2(v)}${live ? ' (live)' : ''}<br>decided on a ${x[2] < 0 ? 'inverted' : 'contango'} close (${sg(x[2])}); ZVOL weight ${pc0(x[4])}, VXZ ${pc0(x[5])}; ZVOL that day ${sg(x[1])}`)); rr.addEventListener('mouseleave', untip);
  });
  legend('lgD', [['HARV daily return', 'var(--ctx2)'], ['decided on an inverted close', 'var(--s2)'], ['2026-11-05, live', 'var(--s1)']]);
  const S = HV.as_a_signal, E = HV.history_engine_real_era, LS = HV.history_live_snapshots;
  document.getElementById('tbD').innerHTML = `<thead><tr><th>the number</th><th class="n">value</th><th>note</th></tr></thead><tbody>` +
    [['Composer last_percent_change, 11-05 (what the alert printed)', sg2(HV.live_1105), 'the symphony\'s day return'],
     ['deposit-adjusted value 11-04 → 11-05', sg2(HV.value_based_1105), '$37,310 → $38,078'],
     ['close-to-close model', sg2(HV.model_close_to_close_1105), `0.3594 × VXZ ${sg2(HV.vxz_ret_1105)} + 0.6396 × PULS 0.00%; the ${sg2(HV.gap_live_minus_model)} gap is the 15:50 fills on 11-04 and 11-05 vs the 16:00 closes`],
     ['engine daily returns, real era', `sd ${pc(E.sd)}, p99 ${sg2(E.p99)}, max ${sg2(E.max)}`, `${E.n} sessions ${E.from}..${E.to}; ${E.days_ge_1105} days at or above +2.02% (percentile ${pc0(E.percentile_of_1105)})`],
     ['live sessions in the monitor record', `${LS.n}, max ${sg2(LS.max)}`, `${LS.from}..${LS.to}; 11-05 is the largest`],
     ['as a signal: corr(HARV day, ZVOL next 20), real era', f2(S['real ZVOL 2023-04+'].corr_harv_day_vs_zvol_fwd20), `n ${S['real ZVOL 2023-04+'].n}; since 2006: ${f2(S['2006-07+'].corr_harv_day_vs_zvol_fwd20)} (n ${S['2006-07+'].n})`],
     ['after a HARV day ≥ +1% earned on VXZ', `ZVOL next 20: ${sg(S['real ZVOL 2023-04+'].harv_day_ge_1pct_on_vxz.zvol_fwd20.mean)} (n ${S['real ZVOL 2023-04+'].harv_day_ge_1pct_on_vxz.n})`, `unconditional ${sg(S['real ZVOL 2023-04+'].unconditional_zvol_fwd20.mean)}; since 2006: ${sg(S['2006-07+'].harv_day_ge_1pct_on_vxz.zvol_fwd20.mean)} (n ${S['2006-07+'].harv_day_ge_1pct_on_vxz.n}) vs ${sg(S['2006-07+'].unconditional_zvol_fwd20.mean)}`]]
    .map(([a, b2, c]) => `<tr><td>${a}</td><td class="n">${b2}</td><td style="color:var(--ink2)">${c}</td></tr>`).join('') + '</tbody>';
})();

// ---------- E: live record
(function(){
  document.getElementById('liveLead').textContent = `${LV.sessions} sessions since ${LV.from}; the VIX3M/VIX read has been written into every snapshot since ${LV.first_snapshot_with_contango} (${LV.snapshots_with_contango} snapshots). ` +
    `Closes in backwardation: ${LV.backwardation_closes.length}. BACKWARDATION DAY alerts: ${LV.backwardation_alerts.length} (one was a 14:58 ET midday run on 10-30 that read −3.4% while HARV sat in PULS; the close was +7.0%). Sessions whose close put HARV into ZVOL: ${LV.zvol_sessions_live}. The evidence record therefore holds one inverted-close entry, 11-05, with no outcome yet.`;
  const rows = LV.rows.filter(x => x.depth_close < 0.03 || (x.decided_at_close || {}).ZVOL);
  document.getElementById('tbE').innerHTML = `<thead><tr><th>session</th><th class="n">VIX3M/VIX close</th><th class="n">VIX</th><th class="n">snapshot read</th><th>decided at the close (live)</th><th>shadow</th><th class="n">HARV day</th><th class="n">ZVOL day</th><th class="n">ZVOL +1</th><th class="n">ZVOL +5</th><th class="n">ZVOL +20</th></tr></thead><tbody>` +
    rows.map(x => `<tr${x.depth_close < 0 ? ' class="hl"' : ''}><td>${x.date}</td><td${cls(x.depth_close)}>${sg(x.depth_close)}</td><td class="n">${x.vix.toFixed(1)}</td><td class="n">${x.snapshot_contango == null ? '–' : sg(x.snapshot_contango) + ' @' + x.snapshot_et}</td><td>${x.decided_at_close ? Object.entries(x.decided_at_close).map(([k, v]) => `${k} ${pc0(v)}`).join(', ') : '–'}</td><td>${x.status || '–'}</td><td${cls(x.harv_day)}>${x.harv_day == null ? '–' : sg2(x.harv_day)}</td><td${cls(x.zvol_day)}>${sg(x.zvol_day)}</td><td${cls(x.zvol_fwd['1'])}>${sg(x.zvol_fwd['1'])}</td><td${cls(x.zvol_fwd['5'])}>${sg(x.zvol_fwd['5'])}</td><td${cls(x.zvol_fwd['20'])}>${sg(x.zvol_fwd['20'])}</td></tr>`).join('') +
    `<tr><td colspan="11" style="color:var(--ink2)">Sessions shown: every close within 3% of inversion and every close that put ZVOL into HARV (${rows.length} of ${LV.sessions}). "snapshot read" is the monitor's VIX3M/VIX at its run time (a fixed 21:35 UTC run: 17:35 EDT, 16:35 EST; Yahoo's last print, which can differ from the 16:00 close). Holdings from the shadow ledger (Composer's live weights at that close); "shadow" is the runner's verdict against the approved logic.</td></tr></tbody>`;
})();

// ---------- F: context
(function(){
  const deep = CX.deep_entries, fl = CX.vxz_to_zvol_flips, ds = CX.deep_summary['20'], dz = CX.deep_zvol_20, fs = CX.flip_summary['20'];
  document.getElementById('ctxLead').textContent = `Among the ${CX.n_backwardation_entries_before} earlier inverted-close entries since 2006, 11-05's inversion (${sg(CX.entry.depth)}) is deeper than ${pc0(1 - CX.depth_percentile_among_bw_entries)} of them, its VIX (${CX.entry.vix.toFixed(1)}) sits at the ${pc0(CX.vix_percentile_among_bw_entries)} percentile and its 60% weight at the ${pc0(CX.weight_percentile_among_bw_entries)}. ` +
    `The ${deep.length} earlier entries deeper than −8%: HARV +20 sessions ${sg(ds.mean)} on average, ${pc0(ds.win)} positive, while ZVOL itself averaged ${sg(dz.mean)}; the two in the real era (2024-12-18, 2025-04-03) lost ${sg(deep.filter(e => e.era === 'real')[0].harv_fwd['1'])} and ${sg(deep.filter(e => e.era === 'real')[1].harv_fwd['1'])} on the next session and were out within one. ` +
    `11-05 is also the tenth flip from a +1% VXZ day straight into ZVOL; the nine before averaged ${sg(fs.mean)} over the next 20 sessions (${pc0(fs.win)} positive).`;
  const row = e => `<tr${e.era === 'real' ? ' class="hl"' : ''}><td>${e.date}</td><td>${e.era === 'real' ? 'real' : e.era === 'vxz' ? '−VXZ' : 'modeled'}</td><td class="n neg">${sg(e.depth)}</td><td class="n">${e.vix.toFixed(1)}</td><td${cls(e.spy_day)}>${sg(e.spy_day)}</td><td${cls(e.harv_day)}>${sg2(e.harv_day)}</td><td class="n">${pc0(e.zvol_from)} → ${pc0(e.zvol_to)}</td><td class="n">${e.hold_len == null ? '–' : e.hold_len}</td><td${cls(e.zvol_fwd['1'])}>${sg(e.zvol_fwd['1'])}</td><td${cls(e.zvol_fwd['20'])}>${sg(e.zvol_fwd['20'])}</td><td${cls(e.harv_fwd['1'])}>${sg2(e.harv_fwd['1'])}</td><td${cls(e.harv_fwd['5'])}>${sg2(e.harv_fwd['5'])}</td><td${cls(e.harv_fwd['20'])}>${sg2(e.harv_fwd['20'])}</td></tr>`;
  const head = '<thead><tr><th>entry close</th><th>data</th><th class="n">VIX3M/VIX</th><th class="n">VIX</th><th class="n">SPY day</th><th class="n">HARV day</th><th class="n">ZVOL weight</th><th class="n">held</th><th class="n">ZVOL +1</th><th class="n">ZVOL +20</th><th class="n">HARV +1</th><th class="n">HARV +5</th><th class="n">HARV +20</th></tr></thead>';
  document.getElementById('tbF1').innerHTML = head + '<tbody>' + deep.map(row).join('') + row(Object.assign({}, CX.entry, {era: 'real'})).replace('<td>real</td>', '<td>live, pending</td>') + `<tr><td colspan="13" style="color:var(--ink2)">Entries at a VIX3M/VIX below −8%, 2006 to 2026, with 11-05 last. The 2007-2011 rows run on the modeled VXZ whose 2008 behaviour the add. 27 panel called artifact-grade (the model's contango beta is unidentified in backwardation); 2018-2020 rows on −0.971 × real VXZ; the two 2024-25 rows and 11-05 on the real fund.</td></tr></tbody>`;
  document.getElementById('tbF2').innerHTML = head + '<tbody>' + fl.map(row).join('') + '</tbody>';
})();

[`Rule and data: the live tree fixtures/approved/harv-XVtsDTV1.json (version ${D.rule.version}), evaluated by the shadow runner on Yahoo adjusted closes with the 11-05 closes read at ~22:00 UTC (VIX 28.18, VIX3M 25.55, SPY 733.00, ZVOL 6.82, VXZ 48.21, UVXY 23.61); it reproduces the 11-04 (VXZ 36 / PULS 64) and 11-05 (ZVOL 60 / PULS 40) decisions. Regime = VIX3M/VIX at the close; depth buckets 0..−3%, −3..−8%, under −8%.`,
 `ZVOL's real history is short: ${RC.real_zvol_era_days} closes since 2023-04-19, ${RC.real_zvol_era_backwardation_days} of them inverted in ${RC.real_zvol_era_episodes} episodes (9 deeper than −8%, three episodes). Everything before 2023 is the add. 47 proxy, ZVOL = −0.971 × VXZ (fit corr 0.973, backwardation-day beta 0.98-1.00 on 48 days); VXZ is real from 2018-01-25 and the vix_etp term-structure model on the real VIX3M/VIX6M before that, whose 2008 is kinder than reality (add. 27). The 1995-2006 split uses a synthetic VIX3M fitted from the VIX alone and is shown only for completeness (${D.path['1995-06+ (synthetic curve before 2006-07)'].synthetic_regime_days} such days).`,
 `Measurement basis: the engine path is the add. 47 pipeline with Composer-equivalent costs (5.1 bps per unit of weight traded), rebuilt 2026-11-05 on the live tree; the 11-05 return in the path is the live +2.02%. Trade P&amp;L is close to close on that path, not Composer's fills; add. 38 measured live fills within a few bps of the model on average, and 11-05's +2.02% against the +2.38% close-to-close model shows a 15:50-fill day. The counterfactuals leave the cost of the removed trades in (slightly conservative against the counterfactual).`,
 `Statistics: t with the sample sd on overlapping windows, so the 5- and 20-session t-values are overstated and the episode-start rows are the fairer read; the inverted closes cluster (${RC.since_2006_backwardation_days} closes in ${D.cond['all since 2006-07'].horizons['20'].backwardation.episodes} episodes since 2006). Small n everywhere that matters: 19 inverted-close entries and 15 trades in the real era, 2 of them deep; 29 deep entries since 2006 of which 24 are modeled. In sample: the rule's windows were chosen on 2015-26 data.`,
 `The HYG credit guard in the symphony's name does not exist in any saved version (add. 48): the only guard is RSI(UVXY,14) > 70 → PULS, which read 66.7 on 11-05 (3.3 points from blocking the entry). The add. 12 design (block ZVOL when HYG fell more than 1% that day) lives only in research/harv_sim.py; HYG was −0.31% on 11-05, so it would not have fired either. The guard sim's monthly series (research/harv_guard_sim.json, 2018-02..2023-04, cumulative ${sg(D.guard.harv_guard_sim.cumulative)}) has its worst months in the 2018 chop (${Object.entries(D.guard.harv_guard_sim.worst_months).slice(0, 3).map(([k, v]) => k + ' ' + sg(v)).join(', ')}), not in a crash.`,
 `Prior measurements this study agrees with: add. 25 (the harvester's best contango quartile is low/negative: +18.5 bp/day) and add. 47 C1 (sending ZVOL to PULS when VIX > VIX3M cost the real era ×2.11 → ×2.00 and was killed). What is new: the depth split. Not modeled: fills on a limit-down open, the ZVOL ex-distribution timing (add. 37), anything about VIX futures themselves. Research only; nothing traded, paused or edited.`,
 `Generated ${D.generated}.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
