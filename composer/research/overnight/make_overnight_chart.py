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
    ed = json.load(open(os.path.join(RES, "overnight-edge-2026-11-05.json")))
    eng, counts = {}, {}
    for e, E in r["engines"].items():
        allr = E["rules_exit"]
        pos = sorted([(k, v) for k, v in allr.items() if v["delta_cagr"] > 0], key=lambda kv: -kv[1]["delta_cagr"])
        counts[e] = {"total": len(allr), "negative": sum(1 for v in allr.values() if v["delta_cagr"] <= 0),
                     "positives": [{"name": k, "dcagr": v["delta_cagr"], "n": v["n_fires"], "t": v.get("t"), "pct": (v.get("placebo") or {}).get("percentile_of_actual")} for k, v in pos],
                     "improved_dd": sum(1 for v in allr.values() if v["delta_maxdd"] > 0.0005), "raised_sharpe": sum(1 for v in allr.values() if v["delta_sharpe"] > 0),
                     "t": {k: allr[k].get("t") for k in ("fund gap <= -5%", "fund gap <= -2%", "Asia <= -1.0%", "fund gap <= -10%") if k in allr}}
        rows = []
        for name in RULES:
            v = E["rules_exit"].get(name)
            if not v:
                continue
            pl = v.get("placebo") or {}
            rows.append({"name": name, "n": v["n_fires"], "hit": v["hit_rate"], "saved": v["saved_mean"], "t": v.get("t"), "dcagr": v["delta_cagr"],
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
    e1 = {k: {kk: vv for kk, vv in v.items() if kk not in ("best", "by_year")} for k, v in ed["E1"].items() if v.get("n")}
    data = {"eng": eng, "counts": counts, "deciles": ev["gap_deciles"], "pooled": pooled, "corr": ev["pooled_corr_with_intraday"], "events_n": ev["pooled_n"],
            "edge": {"E1": e1, "E2": ed["E2"], "rt_bps": ed["rt_bps"], "events": ed["events"], "event_days": ed["event_days"], "family": ed["family"],
                     "oos": ed["OOS"], "inter": ed["intersection"], "splits": ed["E1_splits"], "overlap": ed["E1_engine_overlap"]},
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
<h2>A. Path-free panel: after an oversold close, the worst overnights were followed by the best sessions</h2>
<p class="sub-h">Every morning after SOXL, TECL, TQQQ, SPXL or LABU closed with Wilder RSI(10) under 30 (the engines' dip-buy trigger), 2008-2026. Bars: the fund's open-to-close move by decile of its overnight gap. The bottom decile (gaps averaging −9%) was followed by +4.7% intraday, positive 70% of the time (t 4.2; +5.2% without 2020); deciles 2-9 are flat (−0.3% to +1.2%), so this is a tail effect, not a gradient. It is conditional on the oversold close: unconditionally, SOXL gap-downs of 5%+ since 2015 (n 197) show no rebound (mean −0.01%, 46% up). Pooled correlation of each pre-open signal with the subsequent open-to-close move is in the table.</p>
<div class="chartwrap"><svg id="chA" role="img" aria-label="Mean open-to-close move of leveraged funds by decile of the overnight gap, mornings after an oversold close"></svg></div>
<div class="tablewrap"><table id="tbA"></table></div>
</section>

<section class="card">
<h2>B. The same rules on the KMLM switcher's own path: 43 of 47 exit rules cost return</h2>
<p class="sub-h">Exit the leveraged long at the 09:30 open when the signal fires, hold cash until the next 15:50 decision; the engine's decisions are unchanged. Bars: change in CAGR over 2015-06..2026-11-04 vs the engine as built (net of the overlay's own costs: 15 bps at the open, 10 bps to re-enter when the engine re-holds the fund; the signs hold before costs). The thin bar is the placebo band (5th-95th percentile of exiting the same number of random leveraged-long mornings): random exits already cost (−6.6%/yr at 100 fires, because the legs earn intraday on average); a rule below the band picks worse mornings than chance. Labels: fires and the share of fires where exiting helped. The four rules with a positive change are mirrored "good overnight" signals (table), t ≤ 1.3.</p>
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
<h2>F. The other side: the morning bounce as a trade — an in-sample anomaly, not an edge yet</h2>
<p class="sub-h">If a bad overnight after an oversold close predicts a better session, buy it. E1: on a morning when a 3x fund closed with RSI(10) under 30 and the signal fires before 09:30, buy the fund at the open and sell at the close (one trade per day, qualifying funds equal-weighted, 30 bps round trip), 2008-2026. Lines: growth of $1 compounding one trade at a time. Read the table's last three columns before the first: the mean without the best three trades, and the family-wise permutation p (13 overlapping rules were tried; the best of 13 reaches t 2.7 by chance one time in twenty). The same rule on seven leveraged funds it was not found on returns nothing; the engine already held the leg on 27 of the 31 qualifying days since 2015. E2 (table below): topping the leveraged leg up to 100% at the open inside the KMLM engine, capped per day and placebo-tested.</p>
<div class="legend" id="lgF"></div>
<div class="chartwrap"><svg id="chF" role="img" aria-label="Growth of one dollar in the morning-bounce trade for three signals and for every oversold morning, 2008 to 2026"></svg></div>
<div class="tablewrap"><table id="tbF"></table></div>
<details><summary>Table: E2, the add-on inside the KMLM engine</summary><div class="tablewrap"><table id="tbF2"></table></div></details>
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
const CK = D.counts.KMLM, CH = D.counts.HG, g5 = K.rules.find(r => r.name === 'fund gap <= -5%');
const dec0 = D.deciles[0];
const E1 = D.edge.E1, e1best = E1['sector gap <= -2%'], e1gap = E1['fund gap <= -5%'];
[[`${sg(dec0.intra_mean)} intraday`, `after the worst overnight gaps (bottom decile, ${pc(dec0.gap_mean)} average) on ${D.events_n} oversold-close mornings since 2008; positive ${pc0(1 - dec0.intra_neg)} of the time (t 4.2); deciles 2-9 flat`],
 [`${CK.negative} of ${CK.total} rules`, `on KMLM's path cost CAGR (HG: ${CH.negative} of ${CH.total}); the exceptions are mirrored "good overnight" signals, best ${sg(CK.positives[0].dcagr)}/yr on ${CK.positives[0].n} fires, t ${f2(CK.positives[0].t)}. Fund gap ≤ −5%: ${sg(g5.dcagr)}/yr, t ${f2(g5.t)} (as built ${pc0(K.base.cagr)}/yr, in sample)`],
 [`${pc0(g5.hit)} hit rate`, `share of KMLM's ${g5.n} mornings with a 5%+ gap-down where exiting at the open beat holding to the close; each exit cost the engine ${pc(-g5.saved)} on average`],
 [`${e1gap.n} trades, ${sg(e1gap.mean)} each`, `the other side (section F): buy the open, sell the close after an oversold close when the fund gaps ≤ −5% — win ${pc0(e1gap.win)}, t ${e1gap.t.toFixed(1)} single-test but family-wise p ${D.edge.family.p_fw['fund gap <= -5%'].toFixed(2)} over the 13 rules tried; ${sg(e1gap.drop_best3.mean)} without the best three trades; the same rule on 7 other leveraged funds: ${sg(D.edge.oos['all 7 pooled, fund gap <= -5%'].mean)}. Not an edge yet`]]
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
  for (let v = Math.ceil(lo * 10) / 10; v <= hi; v += 0.1) { el('line', {x1: X(v), x2: X(v), y1: t, y2: H2 - 30, stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: X(v), y: H2 - 12, 'text-anchor': 'middle', class: 'ax'}, svg, (Math.round(v * 100) || 0) + '%'); }
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
  if (E.short.length) body += `<tr><td colspan="10" style="color:var(--ink2)">Short legs (SQQQ mornings), exit at the open:</td></tr>` + E.short.map(x => `<tr><td>${x.name}</td><td class="n">${x.n}</td><td class="n">${pc0(x.hit)}</td><td></td><td${cls(x.dcagr)}>${sg(x.dcagr)}</td><td></td><td></td><td></td><td class="n">${pc0(x.pct)}</td><td></td></tr>`).join('');
  body += `<tr><td colspan="10" style="color:var(--ink2)">Flip breaker (after N direction changes in M sessions, cash for K sessions):</td></tr>` + Object.entries(E.breaker).map(([k, v]) => `<tr><td>${k}</td><td class="n">${v.trips} trips</td><td class="n">${v.cash_days} cash days</td><td></td><td${cls(v.delta_cagr)}>${sg(v.delta_cagr)}</td><td${cls(v.delta_sharpe)}>${f2(v.delta_sharpe)}</td><td${cls(v.delta_maxdd)}>${sg(v.delta_maxdd)}</td><td colspan="3" class="n">last: ${v.last_trips.join(', ')}</td></tr>`).join('');
  body += `<tr><td colspan="10" style="color:var(--ink2)">As built ${E.from}..${E.to}: CAGR ${pc(E.base.cagr)}, Sharpe ${f2(E.base.sharpe)}, max DD ${pc0(E.base.maxdd)} (in sample); ${E.long_mornings} leveraged-long mornings (${Object.entries(E.funds).map(([k, v]) => `${k} ${v}`).join(', ')}), ${E.short_mornings} short-leg mornings. Direction changes per 25 sessions: mean ${E.flip_rate.mean.toFixed(1)}, p90 ${E.flip_rate.p90}, p99 ${E.flip_rate.p99}, max ${E.flip_rate.max}.</td></tr>`;
  document.getElementById(id).innerHTML = head + '<tbody>' + body + '</tbody>';
}
ruleTable('tbB', K); ruleTable('tbC', H);
// D: recent mornings
document.getElementById('tbD').innerHTML = '<thead><tr><th>morning</th><th>engine</th><th>leg (weight)</th><th class="n">Asia</th><th class="n">DAX open</th><th class="n">VIX</th><th class="n">gap at open</th><th class="n">open→close</th><th class="n">day</th></tr></thead><tbody>' +
  [['KMLM', K.recent], ['HG', H.recent]].flatMap(([e, rows]) => rows.map(m => [e, m])).sort((a, b) => a[1].date.localeCompare(b[1].date)).map(([e, m]) => `<tr><td>${m.date}</td><td>${e}</td><td>${m.fund} (${pc0(m.w)})</td><td${cls(m.asia)}>${sg(m.asia)}</td><td${cls(m.eu_open)}>${sg(m.eu_open)}</td><td class="n">${m.vix == null ? '–' : m.vix.toFixed(1)}</td><td${cls(m.gap)}>${sg(m.gap)}</td><td${cls(m.intra)}>${sg(m.intra)}</td><td${cls(m.day)}>${sg(m.day)}</td></tr>`).join('') +
  '<tr><td>2026-11-05</td><td>KMLM</td><td>SOXL (75%)</td><td class="n neg">−3.4%</td><td class="n">+0.1%</td><td class="n">16.6</td><td class="n neg">−14.6%</td><td class="n neg">−15% to 11:30</td><td class="n neg">–</td></tr></tbody>';
// F: the edge
(function(){
  const E1 = D.edge.E1, names = ['sector gap <= -2%', 'fund gap <= -5%', 'gap <= -5% OR DAX <= -2%', 'any oversold morning (no signal)'];
  const col = {'sector gap <= -2%': 'var(--s3)', 'fund gap <= -5%': 'var(--s1)', 'gap <= -5% OR DAX <= -2%': 'var(--s2)', 'any oversold morning (no signal)': 'var(--ctx2)'};
  legend('lgF', names.map(n => [n, col[n]]));
  const svg = document.getElementById('chF'), W = 900, H2 = 320, l = 54, r = 230, t = 14, b = 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const T = s => new Date(s + 'T12:00:00Z').getTime(), t0 = T('2008-11-01'), t1 = T('2026-11-30');
  const series = {};
  names.forEach(n => { let eq = 1; series[n] = E1[n].trades.map(([d, ret]) => { eq *= 1 + ret; return [T(d), eq]; }); series[n].unshift([t0, 1]); });
  const vals = Object.values(series).flat().map(p => p[1]), lo = Math.log10(Math.min(...vals) * 0.9), hi = Math.log10(Math.max(...vals) * 1.1);
  const X = ms => l + (ms - t0) / (t1 - t0) * (W - l - r), Y = v => t + (hi - Math.log10(v)) / (hi - lo) * (H2 - t - b);
  [0.5, 1, 2, 5, 10].forEach(v => { if (Math.log10(v) >= lo && Math.log10(v) <= hi) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: v === 1 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, '$' + v); } });
  for (let y = 2010; y <= 2026; y += 2) el('text', {x: X(T(y + '-01-01')), y: H2 - 8, 'text-anchor': 'middle', class: 'ax'}, svg, y);
  const ends = names.map(n => { const last = series[n][series[n].length - 1]; return {n, v: last[1], y: Y(last[1])}; }).sort((a, b2) => a.y - b2.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  names.forEach(n => {
    el('polyline', {points: series[n].map(p => `${X(p[0])},${Y(p[1])}`).join(' '), fill: 'none', stroke: col[n], 'stroke-width': n.startsWith('any') ? 1.4 : 2, 'stroke-linejoin': 'round'}, svg);
    series[n].slice(1).forEach(p => el('circle', {cx: X(p[0]), cy: Y(p[1]), r: 2.2, fill: col[n]}, svg));
    const e = ends.find(x => x.n === n); el('text', {x: W - r + 6, y: e.y + 4, class: n.startsWith('any') ? 'lb' : 'lbb', fill: col[n]}, svg, `${n.replace(' (no signal)', '')} $${e.v.toFixed(2)}`);
  });
  const FW = D.edge.family.p_fw, BF = D.edge.family.bonferroni_x16;
  document.getElementById('tbF').innerHTML = `<thead><tr><th>E1 rule (buy the open, sell the close)</th><th class="n">days</th><th class="n">per year</th><th class="n">mean</th><th class="n">median</th><th class="n">win</th><th class="n">t</th><th class="n">without best 3 (t)</th><th class="n">family-wise p</th><th class="n">Bonferroni ×16</th><th class="n">total</th><th class="n">worst run</th><th>worst trades</th></tr></thead><tbody>` +
    Object.entries(E1).map(([n, s]) => { const d3 = s.drop_best3 || {}; return `<tr><td>${n}</td><td class="n">${s.n}</td><td class="n">${s.per_year.toFixed(1)}</td><td${cls(s.mean)}>${sg2(s.mean)}</td><td${cls(s.median)}>${sg2(s.median)}</td><td class="n">${pc0(s.win)}</td><td class="n">${s.t == null ? '–' : s.t.toFixed(1)}</td><td${cls(d3.mean)}>${d3.mean == null ? '–' : sg2(d3.mean) + ' (' + (d3.t == null ? '–' : d3.t.toFixed(1)) + ')'}</td><td class="n">${FW[n] == null ? '–' : FW[n].toFixed(2)}</td><td class="n">${BF[n] == null ? '–' : BF[n].toFixed(2)}</td><td${cls(s.total)}>${sg(s.total)}</td><td class="n neg">${pc0(s.maxdd)}</td><td>${s.worst.slice(0, 2).map(w => `${w.date} ${sg(w.ret)}`).join(', ')}</td></tr>`; }).join('') +
    `<tr><td colspan="13" style="color:var(--ink2)">${D.edge.events} oversold mornings on ${D.edge.event_days} distinct days; ${D.edge.rt_bps} bps round trip; t with the sample sd. Family-wise p: share of ${D.edge.family.perm_n} shuffles of the day returns in which the best of the 13 "bad overnight" rules reaches the rule's observed t (null max t: median ${D.edge.family.null_max_t_p50.toFixed(2)}, 95th pct ${D.edge.family.null_max_t_p95.toFixed(2)}). Splits of the primary rule: LABU-only days ${D.edge.splits['LABU only'].n}, ${sg2(D.edge.splits['LABU only'].mean)} (t ${D.edge.splits['LABU only'].t.toFixed(1)}); days without LABU ${D.edge.splits['without LABU days'].n}, ${sg2(D.edge.splits['without LABU days'].mean)} (t ${D.edge.splits['without LABU days'].t.toFixed(1)}); tech rows only ${D.edge.splits['tech only (SOXL/TECL/TQQQ rows)'].n}, ${sg2(D.edge.splits['tech only (SOXL/TECL/TQQQ rows)'].mean)} (t ${D.edge.splits['tech only (SOXL/TECL/TQQQ rows)'].t.toFixed(1)}). Clustered: 2020-03, 2022-05, 2025-04 carry the worst trades; the best three trades carry half the primary rule's mean. The engine already held a leveraged leg on ${D.edge.overlap.engine_already_long} of the rule's ${D.edge.overlap.primary_days_since_2015} days since 2015-06; on the other ${D.edge.overlap.not_long_trades.length}: ${D.edge.overlap.not_long_trades.map(x => `${x[0]} ${sg(x[1])}`).join(', ')}.</td></tr></tbody>`;
  const I = D.edge.inter, O = D.edge.oos;
  const srow = (n, s) => `<tr><td>${n}</td><td class="n">${s.n}</td><td${cls(s.mean)}>${s.n ? sg2(s.mean) : '–'}</td><td${cls(s.median)}>${s.n ? sg2(s.median) : '–'}</td><td class="n">${s.t == null ? '–' : s.t.toFixed(1)}</td><td class="n">${s.n ? pc0(s.win) : '–'}</td><td${cls((s.drop_best3 || {}).mean)}>${s.drop_best3 ? sg2(s.drop_best3.mean) : '–'}</td></tr>`;
  document.getElementById('tbF').insertAdjacentHTML('afterend', `<p class="sub-h" style="margin-top:14px">Is it the gap, the oversold state, or both? SOXL/TECL/TQQQ, one trade per day, 2010-2026. Then the same rule on the seven leveraged funds the hypothesis was not found on (own RSI(10) under 30, own gap ≤ −5%).</p><div class="tablewrap"><table><thead><tr><th>condition</th><th class="n">days</th><th class="n">mean</th><th class="n">median</th><th class="n">t</th><th class="n">win</th><th class="n">without best 3</th></tr></thead><tbody>` +
    Object.entries(I).map(([n, s]) => srow(n, s)).join('') + `<tr><td colspan="7" style="color:var(--ink2)">Out of sample, seven other leveraged funds:</td></tr>` + Object.entries(O).map(([n, s]) => srow(n, s)).join('') + '</tbody></table></div>');
  const E2 = D.edge.E2;
  document.getElementById('tbF2').innerHTML = `<thead><tr><th>E2 inside KMLM (as built ${pc0(E2.base.cagr)} / ${f2(E2.base.sharpe)} / ${pc0(E2.base.maxdd)}): top the leveraged exposure up to 100% at the open, capped per day</th><th class="n">days</th><th class="n">share oversold mornings</th><th class="n">ΔCAGR</th><th class="n">ΔSharpe</th><th class="n">Δmax DD</th><th class="n">worst extra day</th><th class="n">placebo p05 / p50 / p95</th><th class="n">pct</th></tr></thead><tbody>` +
    Object.entries(E2).filter(([k]) => k !== 'base').map(([k, v]) => `<tr><td>${k}</td><td class="n">${v.n_days}</td><td class="n">${pc0(v.share_oversold)}</td><td${cls(v.dcagr)}>${sg(v.dcagr)}</td><td${cls(v.dsharpe)}>${f2(v.dsharpe)}</td><td${cls(v.dmaxdd)}>${sg(v.dmaxdd)}</td><td class="n neg">${sg(v.worst_extra)} (${v.worst_date})</td><td class="n">${sg(v.placebo.p05)} / ${sg(v.placebo.p50)} / ${sg(v.placebo.p95)}</td><td class="n">${pc0(v.placebo.percentile_of_actual)}</td></tr>`).join('') +
    `<tr><td colspan="9" style="color:var(--ink2)">Placebo = the same number of random leveraged-long mornings with the same top-up. "Share oversold mornings" = the fraction of the fired days on which the topped-up fund had closed with RSI(10) under 30: the engine's long legs are mostly not fresh dip-buys, so E2 is largely a different trade from E1. Every variant deepens the max drawdown (one episode, 2025-04); none raises Sharpe beyond +0.01.</td></tr></tbody>`;
})();
// E: bridge
(function(){
  const B = D.bridge; let h = '<thead><tr><th>fund</th><th class="n">sessions</th><th class="n">04:00 vs open (median, sd)</th><th class="n">08:00 vs open</th><th class="n">09:25 vs open</th><th class="n">gap-downs ≥4%</th><th class="n">share of the gap seen by 08:00</th></tr></thead><tbody>';
  for (const t in B) { const v = B[t], s = k => v.vs_open[k] ? `${sg2(v.vs_open[k].median)}, ${pc(v.vs_open[k].sd)}` : '–'; h += `<tr><td>${t}</td><td class="n">${v.sessions}</td><td class="n">${s('04:00')}</td><td class="n">${s('08:00')}</td><td class="n">${s('09:25')}</td><td class="n">${v.big_gaps.length}</td><td class="n">${v.big_gap_0800_captured == null ? '–' : pc0(v.big_gap_0800_captured)}</td></tr>`; }
  document.getElementById('tbE').innerHTML = h + '</tbody>';
})();
[`Engine paths: the add. 47 pipeline (research/longrun) re-run 2026-11-05 on the live trees (fixtures/approved, the last era per engine), daily 1995-06..2026-11-04 with Composer-equivalent costs; proxies before each fund's launch, the rules' own years after 2015 (in sample). The KMLM path's dominant leg matches Composer's ledger on 59 of 64 sessions since 2026-08-01 (the misses: two knife-edge days and three Composer no-rebalance days). Overlays are applied from 2015-06 on the real funds' raw opens and closes (the engine's own returns use adjusted closes; ex-dividend days differ by the dividend; one December distribution, TECL 2025-12-10, fires the gap rules as a phantom −6.5% gap: a live layer must use adjusted prior closes). "entry day" = the prior session's move of the fund (44% of those fires were legs already held).`,
 `Robustness (counter-agent): per-fire t-statistics −2.8 (fund gap ≤ −5%), −3.7 (≤ −2%), −3.3 (Asia ≤ −1%), −1.0 (≤ −10%, not significant despite the 64% hit rate); the sign is negative in every sub-window (2015-19, 2020-26, 2015-18, 2019-22, 2023-26) on both engines for the seven key rules, and leave-one-year-out never flips it; gross of costs, fund gap ≤ −5% is −0.89% per fire, −21.3%/yr, and would need a +197 bps rebate per fire to break even; of its −23.7%/yr, −6.6 is the cost of any 100 exits and −17.1 is the selection. The day after a 5%+ gap-down the engine averaged +0.83% (exit at the close instead: −16.9%/yr). HG's −10.6% is half three 2016 fires; its −7.2pp drawdown change is one fire (2016-01-20 LABU, +21.8% intraday).`,
 `Overlay mechanics: the leg's close-to-close return on a fired morning becomes its gap (exit) or gap plus the inverse fund's open-to-close (flip), less ${D.exit_bps} bps at the open and ${D.reentry_bps} bps when the engine re-holds the fund at the next close. Placebo: ${2000} draws of the same number of random leveraged-long mornings; "pct" is where the actual rule sits in that distribution (0% = worse than every random draw). Inverse rules fire on the mirrored signal.`,
 'Signals: the fund\'s own gap (09:30 open vs prior close; the pre-market bridge shows the 09:25 print equals it), the sector ETF\'s gap, the mean of the Nikkei, Kospi and Taiwan closes that day (all before 04:00 ET), the DAX open (03:00 ET) vs its prior close, VIX\'s prior close and change, VIX vs VIX3M, and the entry day\'s move. No historical 04:00-08:00 prints exist in our sources (FMP\'s 1-minute bars are 09:30-15:59; Yahoo keeps 60 days).',
 'Panel: Wilder RSI(10) on adjusted closes, the engines\' dip-buy trigger, for the five 3x funds from launch; 893 mornings (180 of them are KMLM long mornings, so "path-free", not independent of the engine); pooled statistics weight funds by their counts; SPXL is the exception (gap ≤ −5%: n 12, −1.6%). Flip counts: the breaker and the flip-rate distribution count long↔short changes only (moves into vol or bond legs are neutral); on that definition the last 25 live KMLM sessions had 8 (10 counting every change of state) against the path\'s mean 1.7, p99 8, max 11; the path itself flips 7 times in the same window, the ledger 7, directions agree on 24 of 25.',
 `The edge (section F), after the second counter-agent pass: an in-sample conditional mean on three tech 3x funds plus LABU — 40 days in 18 years, +3.6% (+1.9% without the best three trades), nominal t 2.0, family-wise p 0.32 over the 13 rules tried, Bonferroni 0.66; the best variant (sector gap ≤ −2%, t 3.1, family-wise p 0.04) is the same 40 days minus 9 losing ones. It needs the fund's own oversold close AND its own gap (gap-downs without the oversold close: −0.6%, t −1.6); it does not transfer to seven other leveraged funds (+0.3%, t 0.2; TNA/FAS negative; only the 2x copies of TQQQ/SOXL agree); the engine already holds the leg on 27 of its 31 days since 2015. Inside the engine the gap-based top-up sits inside the random band; the DAX/Asia top-ups add 5-10 points of CAGR at the 95-100th placebo percentile with a 2-4 point deeper drawdown. Costs: t falls to 2.0 at 37 bps round trip; TECL/LABU fills on a stressed open are 50-80 bps, not 30. Validation would need ~38 trades at the in-sample mean (17 years at 2.2 a year): a log, not a test.`,
 'What this does not test: an engine redesigned to trade futures instead of 3x ETFs (a different strategy, not an overlay); a 15:59 instead of 15:50 decision (add. 50: the 15:54 logic contradicts Composer on 1 of 272 sessions); execution costs (add. 14/14b: Composer measured at 2.9 bps a side, IBKR modeled ~$1.3k/yr worse at $250k). Research only; nothing traded.',
 `Generated ${D.generated}.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
