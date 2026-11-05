#!/usr/bin/env python3
"""Exhibit for the conditioned-exit study (results.md addendum 53 follow-up, study 2): reads
results/conditioned-exits-2026-11-05.json, writes results/conditioned-exits-2026-11-05.html.
Inline SVG, the house palette tokens, light/dark, no external libraries (make_overnight_chart.py style)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")
SRC = os.path.join(RES, "conditioned-exits-2026-11-05.json")
PAGE = os.path.join(RES, "conditioned-exits-2026-11-05.html")
# the bar chart's rows: every gate for the two own-gap rules the study is about, the key gates for the rest, the mirrors
CHART_ROWS = [("gap <= -5%", None), ("gap <= -8%", None),
              ("gap <= -3%", ["ungated (add. 53)", "held RSI >= 30", "held RSI >= 50", "held RSI < 30 (converse)", "RSI >= 30 & no trigger & switcher"]),
              ("sector gap <= -1%", ["ungated (add. 53)", "held RSI >= 30", "held RSI >= 50", "held RSI < 30 (converse)"]),
              ("sector gap <= -2%", ["ungated (add. 53)", "held RSI >= 30", "held RSI >= 50", "held RSI < 30 (converse)", "RSI >= 30 & no trigger & switcher"]),
              ("MIRROR gap >= +5%", None), ("MIRROR gap >= +8%", None)]


def trim_rule(v):
    pl = v.get("placebo") or {}
    return {"signal": v["signal"], "gate": v["gate"], "n": v["n"], "intra": v["intra"].get("mean"), "intra_t": v["intra"].get("t"), "intra_win": v["intra"].get("win"),
            "t_saved": v.get("t_saved"), "saved": v["saved_mean"], "hit": v["hit"], "dcagr": v["delta_cagr"], "dsharpe": v["delta_sharpe"], "dmaxdd": v["delta_maxdd"],
            "p05": pl.get("p05"), "p95": pl.get("p95"), "pct": pl.get("percentile_of_actual"), "p_fw": v.get("p_fw"),
            "c2515": v["costs"]["25+15"]["delta_cagr"], "gross": v["costs"]["0+0"]["delta_cagr"], "dip": v.get("share_dip_leg"), "two": v.get("share_two_leg_days"),
            "worst": v.get("worst_fire"), "best": v.get("best_fire"), "by_year": v.get("by_year")}


def main():
    r = json.load(open(SRC))
    eng = {}
    for e, E in r["engines"].items():
        rules = {k: trim_rule(v) for k, v in E["rules"].items()}
        chart = []
        for sig, gates in CHART_ROWS:
            names = [k for k, v in rules.items() if v["signal"] == sig and (gates is None or v["gate"] in gates)]
            if names:
                chart.append({"group": sig, "rules": names})
        eng[e] = {"base": E["base"], "from": E["from"], "to": E["to"], "sessions": E["sessions"], "long_mornings": E["long_mornings"], "long_all": E["long_mornings_all"],
                  "phantom": E["excluded_phantom"], "funds": E["funds"], "legs": E["legs"], "leg_check": E["leg_check"], "saved_dist": E["saved_dist"],
                  "family": E["family"], "rules": rules, "chart": chart, "states": E["states"], "fires": E.get("fires", {})}
    P = r["panel"]
    data = {"eng": eng, "generated": r["generated"], "exit_bps": r["exit_bps"], "reentry_bps": r["reentry_bps"], "placebo_n": r["placebo_n"], "perm_n": r["perm_n"],
            "signals": r["signals"], "gates": r["gates"], "dipbuy": r["dipbuy_triggers"], "bridge": r.get("bridge_0925_vs_open", {}),
            "panel": {"start": P["start"], "n": P["n"], "pooled": P["pooled"], "daily": P["pooled_daily"], "funds": P["funds"], "check": P["add53_cell_check"], "cell": P["cell_2010"]}}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(PAGE, "w").write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conditioned overnight exits</title>
<meta name="description" content="Do overnight exit rules gated on the held fund not being oversold help the KMLM and HG engines? Rule bars with placebo bands, the gap-by-RSI panel, costs.">
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--ctx:#b9b7ae;--ctx2:#8e8c84;--neg:#e34948;--band:rgba(42,120,214,.18);--mid:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--mid:#383835}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--mid:#383835}
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
svg{display:block;width:100%;height:auto}.ax{fill:var(--muted);font-size:11px}.lb{fill:var(--ink2);font-size:12px}.lbb{fill:var(--ink);font-size:12px;font-weight:600}.gh{fill:var(--ink);font-size:12.5px;font-weight:650}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--grid)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}.tablewrap{overflow-x:auto}
details{margin-top:8px;font-size:13.5px}summary{cursor:pointer;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.neg{color:var(--neg)}
.filters{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:8px 0 10px;font-size:13.5px;color:var(--ink2)}
select{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--ring);border-radius:6px;padding:3px 6px}
.heat td{text-align:center;padding:4px 4px;border-bottom:2px solid var(--surface);border-right:2px solid var(--surface);min-width:92px}
.heat td.rowh{text-align:left;color:var(--ink2);font-weight:600;min-width:80px;background:transparent}
.heat th{text-align:center}.heat th.rowh{text-align:left}
.heat .v{display:block;font-weight:650;font-size:14px;font-variant-numeric:tabular-nums}.heat .m{display:block;font-size:11px;color:var(--ink2);font-variant-numeric:tabular-nums}
.heat td.hot{outline:2px solid var(--ink);outline-offset:-2px}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:360px}
</style>
</head>
<body>
<main>
<h1>Conditioned overnight exits: does gating on "not oversold" rescue the exit rule?</h1>
<p class="sub-h">Addendum 53 found that every unconditional overnight exit loses on the engines' leveraged legs because bad overnights after oversold closes are followed by better sessions, and its edge section showed the untested cell: a 5%+ gap-down when the fund was <em>not</em> oversold ran −0.9% open-to-close (t −2.5, n 208, SOXL/TECL/TQQQ 2010-26; an in-sample cell from the same data). This study puts that gate on the exit rule and runs it on the KMLM switcher's and HG's own paths, 2015-06..2026-11-04, with add. 53's harness unchanged: exit the leveraged long at the 09:30 open when its own gap (or the sector ETF's) is below a threshold AND the held fund's RSI(10) at the prior close was ≥ 30 (also ≥ 40, ≥ 50; the converse; no dip-buy trigger oversold; the leg a switcher pick rather than a dip-buy branch), 15 + 10 bps, a 2,000-draw same-side placebo per rule, and a family-wise permutation p over every rule tried. Then, model-free, every 2x/3x fund's open-to-close by gap bucket × RSI state, 2010-26.</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>A. KMLM's path: the gate removes most of the damage, it does not create a gain, except in one small tail cell</h2>
<p class="sub-h">Bars: change in CAGR over 2015-06..2026-11-04 from exiting the leveraged long at the open whenever the rule fires (net of 15 bps at the open and 10 bps to re-enter when the engine re-holds the fund). The thin bar is the placebo band (5th-95th percentile of exiting the same number of random leveraged-long mornings). Labels: fires, the exited leg's mean open-to-close move (negative = exiting was right gross of costs), and the family-wise p where the rule beats its placebo. "MIRROR" rules exit on a gap-up gated on not-overbought: the control.</p>
<div class="legend" id="lgA"></div>
<div class="chartwrap"><svg id="chA" role="img" aria-label="Change in CAGR from each conditioned exit rule on the KMLM path, with placebo bands"></svg></div>
<details><summary>Table: all rules on KMLM, with costs and the family-wise test</summary><div class="tablewrap"><table id="tbA"></table></div></details>
<details><summary>Every fire of the gated 5% and 8% rules on KMLM</summary><div class="tablewrap"><table id="tbAf"></table></div></details>
</section>

<section class="card">
<h2>B. HG's path: nothing to rescue</h2>
<p class="sub-h">HG's legs (TQQQ, UDOW, TNA, SSO, UPRO, and the dip-buy picks TECL/QLD/LABU/USD) over the same window, same construction. The gated rules fire 7-53 times; the 8% rules once.</p>
<div class="chartwrap"><svg id="chB" role="img" aria-label="Change in CAGR from each conditioned exit rule on the HG path, with placebo bands"></svg></div>
<details><summary>Table: all rules on HG</summary><div class="tablewrap"><table id="tbB"></table></div></details>
</section>

<section class="card">
<h2>C. Model-free: open-to-close by overnight gap × RSI state at the prior close, 2010-2026</h2>
<p class="sub-h">Every morning of every 2x/3x fund in the data (12 long, 4 inverse), the fund's own gap and its own Wilder RSI(10) on adjusted closes — the engines' indicator. Cell: mean open-to-close that session (blue = the fund rose from the open, red = it fell); beneath it n · t (sample sd) · share positive. "One per day" averages the qualifying funds on each day before the statistics (the honest t: the same day shows up in several funds). The ≥ 70 column is the overbought mirror. Ex-distribution mornings excluded.</p>
<div class="filters"><label>Funds <select id="selGrp"></select></label><label>Pooling <select id="selPool"><option value="rows">fund-mornings</option><option value="daily">one per day</option></select></label><span id="panelNote"></span></div>
<div class="tablewrap"><table class="heat" id="heat"></table></div>
<div class="legend" style="margin-top:8px"><span><i class="sw" style="background:color-mix(in oklab, var(--s1) 55%, var(--surface))"></i>rose from the open</span><span><i class="sw" style="background:var(--mid)"></i>flat</span><span><i class="sw" style="background:color-mix(in oklab, var(--neg) 55%, var(--surface))"></i>fell from the open (saturates at ±3%)</span><span>outlined: the cells the exit rules live in (gap ≤ −5%, RSI ≥ 30)</span></div>
<details><summary>The engines' own mornings on the same grid (KMLM and HG leveraged-long legs, 2015-06..2026-11)</summary><div class="tablewrap"><table class="heat" id="heatK"></table></div><div class="tablewrap" style="margin-top:10px"><table class="heat" id="heatH"></table></div></details>
</section>

<section class="card">
<h2>D. Costs, the pre-open proxy, and what a candidate would need</h2>
<div class="tablewrap"><table id="tbD"></table></div>
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
const K = D.eng.KMLM, H = D.eng.HG, P = D.panel;
const k5 = K.rules['gap <= -5% & held RSI >= 30'], k5u = K.rules['gap <= -5% & ungated (add. 53)'], k8 = K.rules['gap <= -8% & held RSI >= 30'], k84 = K.rules['gap <= -8% & held RSI >= 40'];
const h5 = H.rules['gap <= -5% & held RSI >= 30'], h5u = H.rules['gap <= -5% & ungated (add. 53)'], h3 = H.rules['gap <= -3% & held RSI >= 30'];
const bestH = Object.values(H.rules).filter(v => v.n >= 5 && !v.signal.startsWith('MIRROR') && !v.gate.includes('converse')).sort((a, b) => b.dcagr - a.dcagr)[0];
const c8 = P.pooled['long all 12']['<= -8%'], c8d = P.daily['long all 12']['<= -8%'], c58 = P.pooled['long all 12']['-8..-5%'], c58d = P.daily['long all 12']['-8..-5%'];
[[`${sg(k5.dcagr)}/yr`, `KMLM, exit on an own gap ≤ −5% when the held fund's RSI(10) ≥ 30 (the add. 53 cell on the engine's path): ${k5.n} fires, the leg still went ${sg2(k5.intra)} open-to-close on average (t ${f1(k5.intra_t)}), exiting helped ${pc0(k5.hit)} of the time, ${pc0(k5.pct)} placebo percentile. Ungated the same rule cost ${sg(k5u.dcagr)}/yr: the gate removes the dip-buy mornings, not the loss`],
 [`${sg(k8.dcagr)}/yr on ${k8.n} fires`, `the one cell that beats its placebo: gap ≤ −8% & RSI ≥ 30 on KMLM, leg ${sg2(k8.intra)} open-to-close (t ${f1(k8.intra_t)}), ${pc0(k8.hit)} helped, ${pc0(k8.pct)} placebo pct, family-wise p ${f2(k8.p_fw)}; RSI ≥ 40: ${k84.n} fires, ${sg(k84.dcagr)}/yr, p ${f2(k84.p_fw)}. Three episodes (2020, 2025, 2026) carry it; the ≤ −5% version is negative. A tail cell, in sample`],
 [`${sg(bestH.dcagr)}/yr best on HG`, `HG's best gated rule with 5+ fires (${bestH.signal} & ${bestH.gate}, n ${bestH.n}, ${pc0(bestH.pct)} placebo pct); gap ≤ −5% & RSI ≥ 30: ${h5.n} fires, ${sg(h5.dcagr)}/yr, leg ${sg2(h5.intra)}; the 8% rules fire once. Nothing on HG survives`],
 [`${sg2(c8['>=50'].mean)} after a −8% gap`, `model-free, 12 leveraged long funds 2010-26: open-to-close when the fund gapped ≤ −8% and was not oversold (RSI ≥ 50): n ${c8['>=50'].n}, t ${f1(c8['>=50'].t)} by fund-mornings, ${sg2(c8d['>=50'].mean)} t ${f1(c8d['>=50'].t)} one-per-day; oversold (RSI < 30): ${sg2(c8['<30'].mean)} (t ${f1(c8['<30'].t)}). The state matters; the gated exit still only pays in the deepest tail`]]
 .forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; k.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(k); });

function ruleChart(svgId, E){
  const svg = document.getElementById(svgId), W = 900, rowH = 22, gh = 24, l = 250, r = 300, t = 8;
  const items = [];
  E.chart.forEach(g => { items.push({head: g.group}); g.rules.forEach(n => items.push({rule: n})); });
  let y = t; const ys = items.map(it => { const yy = y; y += it.head ? gh : rowH; return yy; });
  const H2 = y + 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const rr = items.filter(it => it.rule).map(it => E.rules[it.rule]);
  const vals = rr.flatMap(x => [x.dcagr, x.p05 ?? 0, x.p95 ?? 0]), lo = Math.min(...vals) - 0.02, hi = Math.max(0.03, ...vals) + 0.02;
  const X = v => l + (v - lo) / (hi - lo) * (W - l - r);
  const step = (hi - lo) > 0.5 ? 0.1 : 0.05;
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) { el('line', {x1: X(v), x2: X(v), y1: t, y2: H2 - 26, stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: X(v), y: H2 - 10, 'text-anchor': 'middle', class: 'ax'}, svg, (Math.round(v * 100) || 0) + '%'); }
  items.forEach((it, i) => {
    const yy = ys[i];
    if (it.head) { el('text', {x: 0, y: yy + 17, class: 'gh'}, svg, it.head.replace('MIRROR ', 'mirror: ').replace('<=', '≤').replace('>=', '≥') + (it.head.startsWith('MIRROR') ? ' (control)' : '')); return; }
    const x = E.rules[it.rule], mirror = x.signal.startsWith('MIRROR'), conv = x.gate.includes('converse');
    el('text', {x: l - 8, y: yy + 15, 'text-anchor': 'end', class: (mirror || conv) ? 'lb' : 'lbb'}, svg, x.gate.replace(' (add. 53)', '').replace('RSI >= 30 & no trigger & switcher', 'RSI ≥ 30 & no trigger & switcher').replace('>=', '≥').replace('<=', '≤'));
    if (x.p05 != null) el('rect', {x: X(x.p05), y: yy + 8, width: Math.max(1, X(x.p95) - X(x.p05)), height: 6, fill: 'var(--band)'}, svg);
    const x0 = X(Math.min(0, x.dcagr)), w = Math.abs(X(x.dcagr) - X(0));
    const bar = el('rect', {x: x0, y: yy + 4, width: Math.max(w, 1.5), height: 14, rx: 2, fill: x.dcagr < 0 ? 'var(--neg)' : 'var(--s3)', opacity: (mirror || conv) ? 0.55 : 1}, svg);
    const beat = x.pct != null && x.pct >= 0.95 && x.dcagr > 0;
    el('text', {x: W - r + 6, y: yy + 15, class: 'ax'}, svg, `${sg(x.dcagr)}/yr · ${x.n} fires · leg ${sg2(x.intra)}` + (beat ? ` · p_fw ${f2(x.p_fw)}` : ''));
    bar.addEventListener('mousemove', e => tip(e, `<b>${x.signal} & ${x.gate}</b><br>${x.n} fires; the exited leg's mean open-to-close ${sg2(x.intra)} (t ${f1(x.intra_t)}, ${pc0(x.intra_win)} up); exiting helped ${pc0(x.hit)}; ${sg2(x.saved)} of the engine per fire (t ${f1(x.t_saved)})<br>CAGR ${sg(x.dcagr)}/yr (25+15 bps ${sg(x.c2515)}, gross ${sg(x.gross)}), Sharpe ${f2(x.dsharpe)}, max DD ${sg(x.dmaxdd)}<br>placebo band ${sg(x.p05)}..${sg(x.p95)}, actual at the ${pc0(x.pct)} percentile; family-wise p ${f2(x.p_fw)}<br>dip-buy legs among the fires ${pc0(x.dip)}; two-leg days ${pc0(x.two)}`)); bar.addEventListener('mouseleave', untip);
  });
}
legend('lgA', [['change in CAGR, exit at the open (red = cost, green = gain)', 'var(--neg)'], ['placebo band: 5th-95th pct of random same-count exits', 'var(--band)']]);
ruleChart('chA', K); ruleChart('chB', H);

function ruleTable(id, E){
  const head = '<thead><tr><th>signal</th><th>gate</th><th class="n">fires</th><th class="n">leg open→close</th><th class="n">t</th><th class="n">helped</th><th class="n">per fire</th><th class="n">ΔCAGR 15+10</th><th class="n">25+15</th><th class="n">gross</th><th class="n">ΔSharpe</th><th class="n">Δmax DD</th><th class="n">placebo p05..p95</th><th class="n">pct</th><th class="n">family-wise p</th><th class="n">dip-buy legs</th></tr></thead>';
  const body = Object.values(E.rules).map(x => `<tr><td>${x.signal}</td><td>${x.gate}</td><td class="n">${x.n}</td><td${cls(x.intra)}>${sg2(x.intra)}</td><td class="n">${f1(x.intra_t)}</td><td class="n">${pc0(x.hit)}</td><td${cls(x.saved)}>${sg2(x.saved)}</td><td${cls(x.dcagr)}>${sg(x.dcagr)}</td><td${cls(x.c2515)}>${sg(x.c2515)}</td><td${cls(x.gross)}>${sg(x.gross)}</td><td${cls(x.dsharpe)}>${f2(x.dsharpe)}</td><td${cls(x.dmaxdd)}>${sg(x.dmaxdd)}</td><td class="n">${x.p05 == null ? '–' : sg(x.p05) + '..' + sg(x.p95)}</td><td class="n">${pc0(x.pct)}</td><td class="n">${f2(x.p_fw)}</td><td class="n">${pc0(x.dip)}</td></tr>`).join('') +
    `<tr><td colspan="16" style="color:var(--ink2)">As built ${E.from}..${E.to}: CAGR ${pc(E.base.cagr)}, Sharpe ${f2(E.base.sharpe)}, max DD ${pc0(E.base.maxdd)} (in sample). ${E.long_mornings} eligible leveraged-long mornings of ${E.long_all} (${E.phantom} ex-distribution mornings excluded): ${Object.entries(E.funds).map(([k, v]) => `${k} ${v}`).join(', ')}; ${E.legs.switcher || 0} switcher legs, ${E.legs.dip || 0} dip-buy legs (leg labels vs the tree's triggers at the prior close on this study's RSI: ${Object.entries(E.leg_check).map(([k, v]) => `${k} ${v.agree}/${v.n}`).join('; ')}). Family-wise p: share of ${D.perm_n} shuffles of the per-fire exit gains across the eligible mornings in which the best of the ${E.family.rules.length} rules reaches the rule's observed t (null max t: median ${f2(E.family.null_max_t_p50)}, 95th pct ${f2(E.family.null_max_t_p95)}); 1.00 means the rule's t is negative. Per-fire gain across all eligible mornings: sd ${pc(E.saved_dist.sd)}, ${E.saved_dist.n_abs_gt_10pct} mornings beyond ±10%, ${E.saved_dist.two_leg_days} two-leg mornings (the permutation treats legs as independent).</td></tr>`;
  document.getElementById(id).innerHTML = head + '<tbody>' + body + '</tbody>';
}
ruleTable('tbA', K); ruleTable('tbB', H);
(function(){
  const F = K.fires, names = Object.keys(F);
  if (!names.length) return;
  let h = '<thead><tr><th>rule</th><th>date</th><th>fund</th><th class="n">weight</th><th class="n">RSI(10) prior close</th><th class="n">gap at the open</th><th class="n">open→close</th><th class="n">engine gain from exiting</th></tr></thead><tbody>';
  names.forEach(n => { h += `<tr><td colspan="8" style="color:var(--ink2)">${n}: ${F[n].length} fires</td></tr>` + F[n].map(f => `<tr><td></td><td>${f[0]}</td><td>${f[1]}</td><td class="n">${pc0(f[2])}</td><td class="n">${f1(f[3])}</td><td${cls(f[4])}>${sg(f[4])}</td><td${cls(f[5])}>${sg(f[5])}</td><td${cls(f[6])}>${sg2(f[6])}</td></tr>`).join(''); });
  document.getElementById('tbAf').innerHTML = h + '</tbody>';
})();

// C: heat tables
const GAPS = ['<= -8%', '-8..-5%', '-5..-3%', '-3..-1%', '-1..+1%', '+1..+3%', '+3..+5%', '+5..+8%', '> +8%'], STATES = ['<30', '30-50', '>=50', '>=70', 'all'];
const SLAB = {'<30': 'RSI < 30 (oversold)', '30-50': 'RSI 30-50', '>=50': 'RSI ≥ 50', '>=70': 'RSI ≥ 70 (overbought, mirror)', 'all': 'all'};
function cellStyle(m){ if (m == null) return 'background:var(--mid)'; const a = Math.min(1, Math.abs(m) / 0.03) * 55; return `background:color-mix(in oklab, ${m >= 0 ? 'var(--s1)' : 'var(--neg)'} ${a.toFixed(0)}%, var(--surface))`; }
function heat(id, grid, hot){
  let h = '<thead><tr><th class="rowh">overnight gap</th>' + STATES.map(s => `<th>${SLAB[s]}</th>`).join('') + '</tr></thead><tbody>';
  GAPS.forEach(g => { h += `<tr><td class="rowh">${g.replace('<=', '≤').replace('>', '>')}</td>` + STATES.map(s => { const c = grid[g][s]; const isHot = hot && (g === '<= -8%' || g === '-8..-5%') && (s === '30-50' || s === '>=50'); return c.n ? `<td class="${isHot ? 'hot' : ''}" style="${cellStyle(c.mean)}" data-tip="${g} × ${SLAB[s]}: n ${c.n}, mean ${sg2(c.mean)}, median ${sg2(c.median)}, t ${f1(c.t)}, ${pc0(c.win)} positive"><span class="v">${sg2(c.mean)}</span><span class="m">n ${c.n} · t ${f1(c.t)} · ${pc0(c.win)} up</span></td>` : `<td style="background:var(--mid)"><span class="m">–</span></td>`; }).join('') + '</tr>'; });
  const T = document.getElementById(id); T.innerHTML = h + '</tbody>';
  T.querySelectorAll('td[data-tip]').forEach(td => { td.addEventListener('mousemove', e => tip(e, td.dataset.tip)); td.addEventListener('mouseleave', untip); });
}
(function(){
  const sel = document.getElementById('selGrp'), pool = document.getElementById('selPool');
  Object.keys(P.pooled).forEach(g => sel.insertAdjacentHTML('beforeend', `<option value="pooled:${g}">${g}</option>`));
  Object.keys(P.funds).forEach(f => sel.insertAdjacentHTML('beforeend', `<option value="fund:${f}">${f} alone (${P.funds[f].n} mornings)</option>`));
  sel.value = 'pooled:long all 12';
  function draw(){
    const [kind, name] = sel.value.split(/:(.*)/s);
    const grid = kind === 'fund' ? P.funds[name].grid : (pool.value === 'daily' ? P.daily[name] : P.pooled[name]);
    pool.disabled = kind === 'fund';
    heat('heat', grid, true);
    document.getElementById('panelNote').textContent = kind === 'fund' ? `${name}: ${P.funds[name].from}..${P.funds[name].to}` : `${P.n.rows} fund-mornings in all, ${P.n.phantom_excluded} ex-distribution excluded; add. 53's cell reproduced: n ${P.check.n}, ${sg2(P.check.mean)}, t ${f2(P.check.t)}`;
  }
  sel.addEventListener('change', draw); pool.addEventListener('change', draw); draw();
  heat('heatK', K.states, true); heat('heatH', H.states, true);
  document.getElementById('heatK').insertAdjacentHTML('afterbegin', `<caption style="text-align:left;color:var(--ink2);font-size:13px;padding:0 0 6px">KMLM's leveraged-long mornings (${K.long_mornings}), the held leg's own gap × its RSI(10) at the prior close</caption>`);
  document.getElementById('heatH').insertAdjacentHTML('afterbegin', `<caption style="text-align:left;color:var(--ink2);font-size:13px;padding:0 0 6px">HG's leveraged-long mornings (${H.long_mornings})</caption>`);
})();

// D: costs and the proxy
(function(){
  const rows = ['gap <= -5% & held RSI >= 30', 'gap <= -8% & held RSI >= 30', 'gap <= -8% & held RSI >= 40', 'gap <= -5% & RSI >= 30 & no trigger & switcher', 'sector gap <= -2% & held RSI >= 30', 'gap <= -5% & ungated (add. 53)'];
  let h = '<thead><tr><th>rule</th><th>engine</th><th class="n">fires</th><th class="n">ΔCAGR at 15 + 10 bps</th><th class="n">at 25 + 15 bps</th><th class="n">gross</th><th class="n">Δmax DD</th><th class="n">placebo pct</th><th class="n">family-wise p</th></tr></thead><tbody>';
  [['KMLM', K], ['HG', H]].forEach(([e, E]) => rows.forEach(n => { const x = E.rules[n]; if (!x) return; h += `<tr><td>${n}</td><td>${e}</td><td class="n">${x.n}</td><td${cls(x.dcagr)}>${sg(x.dcagr)}</td><td${cls(x.c2515)}>${sg(x.c2515)}</td><td${cls(x.gross)}>${sg(x.gross)}</td><td${cls(x.dmaxdd)}>${sg(x.dmaxdd)}</td><td class="n">${pc0(x.pct)}</td><td class="n">${f2(x.p_fw)}</td></tr>`; }));
  const B = D.bridge, bl = Object.entries(B).map(([t, v]) => `${t} ${pc(v.sd)} sd (median ${sg2(v.median)}, ${v.sessions} sessions)`).join('; ');
  const k8 = K.rules['gap <= -8% & held RSI >= 30'];
  const need = k8.intra != null && k8.intra < 0 ? Math.ceil(Math.pow(2 * (Math.abs(k8.intra / k8.intra_t) * Math.sqrt(k8.n)) / Math.abs(k8.intra), 2)) : null;
  h += `<tr><td colspan="9" style="color:var(--ink2)">The exit print is the 09:30 open; the pre-open signal an IBKR layer would read is the 09:25 indicative, which add. 53's 60-session bridge puts at the open to within 0.1%: ${bl}. Costs are the add. 53 assumptions (Composer's measured fills are 2.9 bps a side); the signs hold gross. What the one surviving cell would need before it is a rule: pre-registration (own gap ≤ −8%, own RSI(10) ≥ 30 at the prior close, switcher leg), an execution log with the 09:25 print, and about ${need == null ? '–' : need} fires at the in-sample mean for t 2 on its own — at ${(k8.n / 11.4).toFixed(1)} fires a year, ${need == null ? '–' : Math.round(need / (k8.n / 11.4))} years. It adds ${sg(k8.dcagr)}/yr to a ${pc0(K.base.cagr)}/yr in-sample engine.</td></tr>`;
  document.getElementById('tbD').innerHTML = h + '</tbody>';
})();
[`Hypothesis origin: the add. 53 edge study's intersection block (the same daily.json, the same funds, the same 2010-26 years) — so the engine-path test here is an in-sample refinement of a cell found in the data, not an out-of-sample test; the family-wise p counts the ${K.family.rules.length} rules tried in this study, not the 47 + 16 tried in add. 53 before it.`,
 `Engine paths: the add. 47 pipeline (live trees, Composer-equivalent costs) 2015-06..2026-11-04, in sample, proxies before each fund's launch; the overlay is evaluated on the real funds' raw opens and closes from launch, with add. 53's mechanics unchanged (exit = the leg's close-to-close return replaced by its gap less ${D.exit_bps} bps, ${D.reentry_bps} bps when the engine re-holds the fund; placebo ${D.placebo_n} draws of the same number of random leveraged-long mornings). Leg types from the holdings: KMLM 0.75 = a dip-buy branch (TQQQ/SOXL/SPXL RSI(10) < 30, LABU < 25 at the prior close), 0.375 = a switcher pick (bottom-2 RSI of TECL/SOXL/SVIX); HG by ticker (TQQQ/UPRO/UDOW/SSO/TNA the momentum pick, TECL/QLD/LABU/USD the dip-buy pick). The labels agree with the trees' triggers on this study's RSI as stated under each table.`,
 `RSI: edge_study's Wilder RSI(10) on Yahoo adjusted closes (the engines' definition; the engines run on the add. 47 caches, so the two can differ on a knife-edge day). The gap is the raw 09:30 open vs the raw prior close (as add. 53); mornings where the raw and adjusted day returns differ by more than 5 bps (distributions: the phantom gaps add. 53's counter-agent flagged) are excluded from firing and from the placebo pool.`,
 `Statistics: t with the sample sd on the fired legs' open-to-close and on the engine's per-fire gain; the placebo percentile is per rule; the family-wise permutation shuffles per-fire gains across mornings and treats two legs held on the same day as independent (${K.saved_dist.two_leg_days} of KMLM's eligible mornings are two-leg days), so its p is slightly optimistic; per-fire gains are fat-tailed (${K.saved_dist.n_abs_gt_10pct} KMLM mornings beyond ±10%), which makes small-n t-statistics less extreme under the null than a normal table would say. The model-free panel pools fund-mornings (the same day across funds) and, as the honest alternative, one trade per day; both are gross of costs.`,
 `Costs: 15 + 10 and 25 + 15 bps are assumptions; add. 53 put TECL/LABU fills on a stressed open at 50-80 bps. The 2026 fires are the live year (the flip-heavy tape of add. 53 section 5). Research only; nothing traded, paused or edited on Composer.`,
 `Generated ${D.generated}.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
