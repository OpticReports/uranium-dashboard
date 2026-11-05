#!/usr/bin/env python3
"""Exhibit for results.md addendum 53: overnight / pre-open overlays on the engines' leveraged legs.
Reads results/overnight-2026-11-05.json and results/overnight-events-2026-11-05.json;
writes results/overnight-2026-11-05.html."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")
PAGE = os.path.join(RES, "overnight-2026-11-05.html")
RULES = ["fund gap <= -2%", "fund gap <= -5%", "fund gap <= -8%", "fund gap <= -10%", "sector gap <= -1.0%", "sector gap <= -2.0%",
         "Asia <= -1.0%", "Asia <= -2.0%", "Asia semis (KS11+TWII) <= -2.0%", "Europe open (DAX) <= -1.0%", "Europe open (DAX) <= -2.0%",
         "VIX close > 25", "VIX close > 30", "VIX backwardation (VIX > VIX3M)", "entry day <= -8% (bought a crash)",
         "combo: fund gap <= -5% AND Asia <= -1%", "combo: fund gap <= -5% AND sector gap <= -1.5%", "combo: Asia <= -1% AND Europe open <= -1%",
         "combo: fund gap <= -3% AND VIX > 25", "INVERSE fund gap >= +5%", "INVERSE Asia >= +1.0%"]


def main():
    r = json.load(open(os.path.join(RES, "overnight-2026-11-05.json")))
    ev = json.load(open(os.path.join(RES, "overnight-events-2026-11-05.json")))
    eng = {}
    for e, E in r["engines"].items():
        rows = []
        for name in RULES:
            v = E["rules_exit"].get(name)
            if not v:
                continue
            pl = v.get("placebo") or {}
            rows.append({"name": name, "n": v["n_fires"], "hit": v["hit_rate"], "saved": v["saved_mean"], "dcagr": v["delta_cagr"],
                         "dsharpe": v["delta_sharpe"], "dmaxdd": v["delta_maxdd"], "p05": pl.get("p05"), "p95": pl.get("p95"), "pct": pl.get("percentile_of_actual"),
                         "flip": (E["rules_flip"].get(name) or {}).get("delta_cagr")})
        short = [{"name": k, "n": v["n_fires"], "hit": v["hit_rate"], "dcagr": v["delta_cagr"], "pct": (v.get("placebo") or {}).get("percentile_of_actual")}
                 for k, v in E["rules_short_exit"].items() if v["n_fires"]]
        eng[e] = {"base": E["base"], "from": E["from"], "to": E["to"], "sessions": E["sessions"], "long_mornings": E["long_mornings"], "short_mornings": E["short_mornings"],
                  "funds": E["funds"], "legs": E["legs"], "rules": rows, "short": short, "breaker": E["breaker"], "flip_rate": E["flip_rate"], "recent": E["recent"]}
    pooled = []
    for key, lab in (("by_gap", "fund gap"), ("by_sector_gap", "sector gap"), ("by_asia", "Asia"), ("by_eu", "DAX open"), ("by_vix", "VIX"), ("by_entry", "entry day")):
        for thr in ev["funds"]["SOXL"][key]:
            n = sum(ev["funds"][f][key][thr]["n"] for f in ev["funds"])
            if not n:
                continue
            intra = sum(ev["funds"][f][key][thr]["n"] * ev["funds"][f][key][thr]["intra"] for f in ev["funds"] if ev["funds"][f][key][thr]["n"]) / n
            neg = sum(ev["funds"][f][key][thr]["n"] * ev["funds"][f][key][thr]["intra_neg"] for f in ev["funds"] if ev["funds"][f][key][thr]["n"]) / n
            pooled.append({"signal": f"{lab} {thr}", "n": n, "intra": intra, "neg": neg})
    alln = sum(ev["funds"][f]["all"]["n"] for f in ev["funds"])
    pooled.insert(0, {"signal": "all dip-buy mornings", "n": alln, "intra": sum(ev["funds"][f]["all"]["n"] * ev["funds"][f]["all"]["intra"] for f in ev["funds"]) / alln,
                      "neg": sum(ev["funds"][f]["all"]["n"] * ev["funds"][f]["all"]["intra_neg"] for f in ev["funds"]) / alln})
    data = {"eng": eng, "deciles": ev["gap_deciles"], "pooled": pooled, "corr": ev["pooled_corr_with_intraday"], "events_n": ev["pooled_n"],
            "bridge": r.get("premarket_bridge", {}), "exit_bps": r["exit_bps"], "reentry_bps": r["reentry_bps"], "generated": r["generated"],
            "funds_ev": {f: {"n": v["n"], "from": v["from"], "to": v["to"], "all": v["all"], "gap5": v["by_gap"]["<= -5%"], "gap10": v["by_gap"]["<= -10%"]} for f, v in ev["funds"].items()}}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(PAGE, "w").write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Overnight overlays tested</title>
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
details{margin-top:8px;font-size:13.5px}summary{cursor:pointer;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.neg{color:var(--neg)}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:340px}
</style>
</head>
<body>
<main>
<h1>Overnight and pre-open overlays on the engines' leveraged legs: what an IBKR layer could have added</h1>
<p class="sub-h">The engines' 15:50 decisions are left as they are. The test is what an IBKR engine could do between decisions: on the morning after a leveraged entry, read what is known before 09:30 (Asia's closes, the DAX open, VIX, the fund's own pre-open gap, the sector's gap) and exit at the open, flip into the inverse fund for the session, or sit out after a run of flips. Applied to the KMLM switcher's and HG's reconstructed daily paths (add. 47 pipeline, the live trees) 2015-06..2026-11-04 on the real funds' opens and closes, with assumed costs, placebo and inverse tests; and, model-free, to every morning after any 3x fund closed oversold since 2008.</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>A. Model-free: after an oversold close, the worse the overnight, the better the day</h2>
<p class="sub-h">Every morning after SOXL, TECL, TQQQ, SPXL or LABU closed with Wilder RSI(10) under 30 (the engines' dip-buy trigger), 2008-2026. Bars: the fund's open-to-close move by decile of its overnight gap. The bottom decile (gaps averaging −9%) was followed by +4.7% intraday, positive 70% of the time. Pooled correlation of each pre-open signal with the subsequent open-to-close move is in the table: all negative for "bad news" signals.</p>
<div class="chartwrap"><svg id="chA" role="img" aria-label="Mean open-to-close move of leveraged funds by decile of the overnight gap, mornings after an oversold close"></svg></div>
<div class="tablewrap"><table id="tbA"></table></div>
</section>

<section class="card">
<h2>B. The same rules on the KMLM switcher's own path: every exit costs return</h2>
<p class="sub-h">Exit the leveraged long at the 09:30 open when the signal fires, hold cash until the next 15:50 decision; the engine's decisions are unchanged. Bars: change in CAGR over 2015-06..2026-11-04 vs the engine as built (gross of the overlay's own costs: 15 bps at the open, 10 bps to re-enter when the engine re-holds the fund). The thin bar is the placebo band (5th-95th percentile of exiting the same number of random leveraged-long mornings): a rule inside or below the band has no information or picks the wrong mornings. Labels: fires and the share of fires where exiting helped.</p>
<div class="legend" id="lgB"></div>
<div class="chartwrap"><svg id="chB" role="img" aria-label="Change in CAGR from each overnight exit rule on the KMLM path, with placebo bands"></svg></div>
<details><summary>Table: every rule on KMLM (exit and flip), the short-leg mirror, the flip breaker</summary><div class="tablewrap"><table id="tbB"></table></div></details>
</section>

<section class="card">
<h2>C. The same on HG's leveraged legs</h2>
<p class="sub-h">HG's long legs (TQQQ, UDOW, TNA, SSO and the rest) over the same window. Same construction.</p>
<div class="chartwrap"><svg id="chC" role="img" aria-label="Change in CAGR from each overnight exit rule on the HG path, with placebo bands"></svg></div>
<details><summary>Table: every rule on HG</summary><div class="tablewrap"><table id="tbC"></table></div></details>
</section>

<section class="card">
<h2>D. This week, morning by morning</h2>
<p class="sub-h">What the engine held into each morning (as reconstructed; it matches Composer's ledger), the overnight signals, and the leg's gap and intraday move. 2026-11-05 (SOXL: gap −14.6%, −15% more by 11:30) is outside the reconstructed path, which ends at the 11-04 close.</p>
<div class="tablewrap"><table id="tbD"></table></div>
</section>

<section class="card">
<h2>E. Pre-market prints vs the open (the exit price an IBKR engine could actually get)</h2>
<p class="sub-h">Sixty sessions of 5-minute pre-market data (all our sources keep). The 09:25 print is the open to within 0.1%; the 08:00 print sits within 1-3% of the open and, on gap-downs of 4% or more, already shows ~70-80% of the gap. So "exit at the open" is a fair stand-in for a pre-market exit; a 04:00-08:00 exit would have sold a little higher on the big gap-downs and lower on the others.</p>
<div class="tablewrap"><table id="tbE"></table></div>
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
const f2 = v => v == null ? '–' : v.toFixed(2), pc = v => v == null ? '–' : (v * 100).toFixed(1) + '%', pc0 = v => v == null ? '–' : (Math.round(v * 100) || 0) + '%';
const sg = v => v == null ? '–' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%', sg2 = v => v == null ? '–' : (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%';
const cls = v => v == null ? ' class="n"' : (v < 0 ? ' class="n neg"' : ' class="n"');
const K = D.eng.KMLM, H = D.eng.HG;
const worstK = K.rules.filter(r => r.n >= 20).sort((a, b) => a.dcagr - b.dcagr)[0];
const bestK = K.rules.filter(r => r.n >= 20).sort((a, b) => b.dcagr - a.dcagr)[0];
const dec0 = D.deciles[0];
[[`${sg(dec0.intra_mean)} intraday`, `after the worst overnight gaps (bottom decile, ${pc(dec0.gap_mean)} average) on ${D.events_n} oversold-close mornings since 2008; positive ${pc0(1 - dec0.intra_neg)} of the time`],
 [`${K.rules.filter(r => r.n >= 10 && r.dcagr < 0).length} of ${K.rules.filter(r => r.n >= 10).length} rules`, `on KMLM's path cost CAGR; best with 20+ fires: ${bestK.name} ${sg(bestK.dcagr)}/yr; worst: ${worstK.name} ${sg(worstK.dcagr)}/yr (as built ${pc0(K.base.cagr)}/yr, in sample)`],
 [`${pc0(K.rules.find(r => r.name === 'fund gap <= -5%').hit)} hit rate`, `share of KMLM's ${K.rules.find(r => r.name === 'fund gap <= -5%').n} mornings with a 5%+ gap-down where exiting at the open beat holding to the close; the exit lost ${sg2(K.rules.find(r => r.name === 'fund gap <= -5%').saved)} of the engine per fire`],
 [`${K.flip_rate.mean.toFixed(1)} → 10`, `KMLM direction changes per 25 sessions: the 2015-26 path's mean → the last 25 live sessions (its 99th percentile is ${K.flip_rate.p99}, max ${K.flip_rate.max}); the breaker that would have sat out such runs costs ${sg(K.breaker['3 flips in 5 -> cash 5'].delta_cagr)}/yr`]]
 .forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; k.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(k); });

// A: decile bars
(function(){
  const svg = document.getElementById('chA'), W = 900, H2 = 300, l = 54, r = 20, t = 16, b = 56, n = D.deciles.length;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const vals = D.deciles.map(d => d.intra_mean), lo = Math.min(0, ...vals) - 0.005, hi = Math.max(...vals) + 0.008;
  const gw = (W - l - r) / n, bw = gw * 0.62, Y = v => t + (hi - v) / (hi - lo) * (H2 - t - b);
  for (let v = Math.ceil(lo * 100) / 100; v <= hi; v += 0.01) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  D.deciles.forEach((d, i) => {
    const x = l + i * gw + (gw - bw) / 2, v = d.intra_mean, y0 = Y(Math.max(0, v)), h = Math.abs(Y(v) - Y(0));
    const rr = el('rect', {x, y: y0, width: bw, height: Math.max(h, 1), rx: 2, fill: v < 0 ? 'var(--neg)' : 'var(--s1)'}, svg);
    el('text', {x: x + bw / 2, y: v >= 0 ? y0 - 4 : y0 + h + 12, 'text-anchor': 'middle', class: 'ax'}, svg, sg(v));
    el('text', {x: x + bw / 2, y: H2 - 34, 'text-anchor': 'middle', class: 'lb'}, svg, `gap ${sg(d.gap_mean)}`);
    el('text', {x: x + bw / 2, y: H2 - 18, 'text-anchor': 'middle', class: 'ax'}, svg, `${pc0(1 - d.intra_neg)} up`);
    rr.addEventListener('mousemove', e => tip(e, `decile ${i + 1}: ${d.n} mornings, mean gap ${sg(d.gap_mean)}, mean open→close ${sg2(d.intra_mean)}, positive ${pc0(1 - d.intra_neg)}`)); rr.addEventListener('mouseleave', untip);
  });
  el('text', {x: W - r, y: H2 - 4, 'text-anchor': 'end', class: 'ax'}, svg, 'deciles of the overnight gap, worst → best; bar = mean open-to-close that day');
  document.getElementById('tbA').innerHTML = '<thead><tr><th>Mornings after an oversold close, pooled across the five funds</th><th class="n">n</th><th class="n">mean open→close</th><th class="n">share up</th></tr></thead><tbody>' +
    D.pooled.map(p => `<tr><td>${p.signal}</td><td class="n">${p.n}</td><td${cls(p.intra)}>${sg2(p.intra)}</td><td class="n">${pc0(1 - p.neg)}</td></tr>`).join('') +
    `<tr><td colspan="4" style="color:var(--ink2)">Correlation of each pre-open signal with the subsequent open→close move: ` + Object.entries(D.corr).map(([k, v]) => `${k} ${f2(v.corr)} (n ${v.n})`).join('; ') + '</td></tr></tbody>';
})();

function ruleChart(svgId, rows){
  const svg = document.getElementById(svgId), W = 900, rowH = 24, l = 300, r = 235, t = 10, H2 = rows.length * rowH + t + 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const vals = rows.flatMap(x => [x.dcagr, x.p05 ?? 0, x.p95 ?? 0]), lo = Math.min(...vals) - 0.02, hi = Math.max(0.02, ...vals) + 0.02;
  const X = v => l + (v - lo) / (hi - lo) * (W - l - r);
  for (let v = Math.ceil(lo * 10) / 10; v <= hi; v += 0.1) { el('line', {x1: X(v), x2: X(v), y1: t, y2: H2 - 30, stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: X(v), y: H2 - 12, 'text-anchor': 'middle', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  rows.forEach((x, i) => {
    const y = t + i * rowH;
    el('text', {x: l - 8, y: y + 16, 'text-anchor': 'end', class: x.name.startsWith('INVERSE') ? 'lb' : 'lbb'}, svg, x.name.replace('combo: ', '').replace(' (bought a crash)', ''));
    if (x.p05 != null) el('rect', {x: X(x.p05), y: y + 9, width: Math.max(1, X(x.p95) - X(x.p05)), height: 6, fill: 'var(--band)'}, svg);
    const x0 = X(Math.min(0, x.dcagr)), w = Math.abs(X(x.dcagr) - X(0));
    const rr = el('rect', {x: x0, y: y + 5, width: Math.max(w, 1.5), height: 14, rx: 2, fill: x.dcagr < 0 ? 'var(--neg)' : 'var(--s3)'}, svg);
    el('text', {x: W - r + 6, y: y + 16, class: 'ax'}, svg, `${sg(x.dcagr)}/yr · ${x.n} fires · ${pc0(x.hit)} helped`);
    rr.addEventListener('mousemove', e => tip(e, `<b>${x.name}</b><br>${x.n} fires, exiting helped on ${pc0(x.hit)}; ${sg2(x.saved)} of the engine per fire<br>CAGR ${sg(x.dcagr)}/yr, Sharpe ${sg2(x.dsharpe).replace('%', '')}, max DD ${sg(x.dmaxdd)}<br>placebo band ${sg(x.p05)}..${sg(x.p95)}; actual at the ${pc0(x.pct)} percentile${x.flip != null ? `<br>flip into the inverse fund instead: ${sg(x.flip)}/yr` : ''}`)); rr.addEventListener('mouseleave', untip);
  });
}
legend('lgB', [['change in CAGR, exit at the open', 'var(--neg)'], ['placebo band: 5th-95th pct of random same-count exits', 'var(--band)']]);
ruleChart('chB', K.rules);
ruleChart('chC', H.rules);
function ruleTable(id, E){
  const head = '<thead><tr><th>rule (exit the long at the open)</th><th class="n">fires</th><th class="n">helped</th><th class="n">per fire</th><th class="n">ΔCAGR</th><th class="n">ΔSharpe</th><th class="n">Δmax DD</th><th class="n">placebo p05..p95</th><th class="n">pct</th><th class="n">flip variant ΔCAGR</th></tr></thead>';
  let body = E.rules.map(x => `<tr><td>${x.name}</td><td class="n">${x.n}</td><td class="n">${pc0(x.hit)}</td><td${cls(x.saved)}>${sg2(x.saved)}</td><td${cls(x.dcagr)}>${sg(x.dcagr)}</td><td${cls(x.dsharpe)}>${f2(x.dsharpe)}</td><td${cls(x.dmaxdd)}>${sg(x.dmaxdd)}</td><td class="n">${sg(x.p05)}..${sg(x.p95)}</td><td class="n">${pc0(x.pct)}</td><td${cls(x.flip)}>${x.flip == null ? '–' : sg(x.flip)}</td></tr>`).join('');
  if (E.short.length) body += `<tr><td colspan="10" style="color:var(--ink2)">Short legs (SQQQ / TLT / UVXY mornings), exit at the open:</td></tr>` + E.short.map(x => `<tr><td>${x.name}</td><td class="n">${x.n}</td><td class="n">${pc0(x.hit)}</td><td></td><td${cls(x.dcagr)}>${sg(x.dcagr)}</td><td></td><td></td><td></td><td class="n">${pc0(x.pct)}</td><td></td></tr>`).join('');
  body += `<tr><td colspan="10" style="color:var(--ink2)">Flip breaker (after N direction changes in M sessions, cash for K sessions):</td></tr>` + Object.entries(E.breaker).map(([k, v]) => `<tr><td>${k}</td><td class="n">${v.trips} trips</td><td class="n">${v.cash_days} cash days</td><td></td><td${cls(v.delta_cagr)}>${sg(v.delta_cagr)}</td><td${cls(v.delta_sharpe)}>${f2(v.delta_sharpe)}</td><td${cls(v.delta_maxdd)}>${sg(v.delta_maxdd)}</td><td colspan="3" class="n">last: ${v.last_trips.join(', ')}</td></tr>`).join('');
  body += `<tr><td colspan="10" style="color:var(--ink2)">As built ${E.from}..${E.to}: CAGR ${pc(E.base.cagr)}, Sharpe ${f2(E.base.sharpe)}, max DD ${pc0(E.base.maxdd)} (in sample); ${E.long_mornings} leveraged-long mornings (${Object.entries(E.funds).map(([k, v]) => `${k} ${v}`).join(', ')}), ${E.short_mornings} short-leg mornings. Direction changes per 25 sessions: mean ${E.flip_rate.mean.toFixed(1)}, p90 ${E.flip_rate.p90}, p99 ${E.flip_rate.p99}, max ${E.flip_rate.max}.</td></tr>`;
  document.getElementById(id).innerHTML = head + '<tbody>' + body + '</tbody>';
}
ruleTable('tbB', K); ruleTable('tbC', H);
// D: recent mornings
document.getElementById('tbD').innerHTML = '<thead><tr><th>morning</th><th>engine</th><th>leg (weight)</th><th class="n">Asia</th><th class="n">DAX open</th><th class="n">VIX</th><th class="n">gap at open</th><th class="n">open→close</th><th class="n">day</th></tr></thead><tbody>' +
  [['KMLM', K.recent], ['HG', H.recent]].flatMap(([e, rows]) => rows.map(m => [e, m])).sort((a, b) => a[1].date.localeCompare(b[1].date)).map(([e, m]) => `<tr><td>${m.date}</td><td>${e}</td><td>${m.fund} (${pc0(m.w)})</td><td${cls(m.asia)}>${sg(m.asia)}</td><td${cls(m.eu_open)}>${sg(m.eu_open)}</td><td class="n">${m.vix == null ? '–' : m.vix.toFixed(1)}</td><td${cls(m.gap)}>${sg(m.gap)}</td><td${cls(m.intra)}>${sg(m.intra)}</td><td${cls(m.day)}>${sg(m.day)}</td></tr>`).join('') +
  '<tr><td>2026-11-05</td><td>KMLM</td><td>SOXL (69%)</td><td class="n neg">−0.5%</td><td class="n">+0.1%</td><td class="n">20.8</td><td class="n neg">−14.6%</td><td class="n neg">−15% to 11:30</td><td class="n neg">–</td></tr></tbody>';
// E: bridge
(function(){
  const B = D.bridge; let h = '<thead><tr><th>fund</th><th class="n">sessions</th><th class="n">04:00 vs open (median, sd)</th><th class="n">08:00 vs open</th><th class="n">09:25 vs open</th><th class="n">gap-downs ≥4%</th><th class="n">share of the gap seen by 08:00</th></tr></thead><tbody>';
  for (const t in B) { const v = B[t], s = k => v.vs_open[k] ? `${sg2(v.vs_open[k].median)}, ${pc(v.vs_open[k].sd)}` : '–'; h += `<tr><td>${t}</td><td class="n">${v.sessions}</td><td class="n">${s('04:00')}</td><td class="n">${s('08:00')}</td><td class="n">${s('09:25')}</td><td class="n">${v.big_gaps.length}</td><td class="n">${v.big_gap_0800_captured == null ? '–' : pc0(v.big_gap_0800_captured)}</td></tr>`; }
  document.getElementById('tbE').innerHTML = h + '</tbody>';
})();
[`Engine paths: the add. 47 pipeline (research/longrun) re-run 2026-11-05 on the live trees (fixtures/approved, the last era per engine), daily 1995-06..2026-11-04 with Composer-equivalent costs; proxies before each fund's launch, the rules' own years after 2015 (in sample). The KMLM path's dominant leg matches Composer's ledger on 56 of 58 comparable sessions since August. Overlays are applied from 2015-06 on the real funds' raw opens and closes (the engine's own returns use adjusted closes; ex-dividend days differ by the dividend).`,
 `Overlay mechanics: the leg's close-to-close return on a fired morning becomes its gap (exit) or gap plus the inverse fund's open-to-close (flip), less ${D.exit_bps} bps at the open and ${D.reentry_bps} bps when the engine re-holds the fund at the next close. Placebo: ${2000} draws of the same number of random leveraged-long mornings; "pct" is where the actual rule sits in that distribution (0% = worse than every random draw). Inverse rules fire on the mirrored signal.`,
 'Signals: the fund\'s own gap (09:30 open vs prior close; the pre-market bridge shows the 09:25 print equals it), the sector ETF\'s gap, the mean of the Nikkei, Kospi and Taiwan closes that day (all before 04:00 ET), the DAX open (03:00 ET) vs its prior close, VIX\'s prior close and change, VIX vs VIX3M, and the entry day\'s move. No historical 04:00-08:00 prints exist in our sources (FMP\'s 1-minute bars are 09:30-15:59; Yahoo keeps 60 days).',
 'Model-free panel: Wilder RSI(10) on adjusted closes, the engines\' dip-buy trigger, for the five 3x funds from launch; 893 mornings; pooled statistics weight funds by their counts.',
 'What this does not test: an engine redesigned to trade futures instead of 3x ETFs (a different strategy, not an overlay); a 15:59 instead of 15:50 decision (add. 50: the 15:54 logic contradicts Composer on 1 of 272 sessions); execution costs (add. 14/14b: Composer measured at 2.9 bps a side, IBKR modeled ~$1.3k/yr worse at $250k). Research only; nothing traded.',
 `Generated ${D.generated}.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
