#!/usr/bin/env python3
"""Exhibit for results.md addendum 52: a long-only value / momentum stock sleeve in IBKR.
Reads results/vm-ibkr-2026-11-03.json (vm_ibkr.py); writes results/vm-ibkr-2026-11-03.html."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")
SRC = os.path.join(RES, "vm-ibkr-2026-11-03.json")
PAGE = os.path.join(RES, "vm-ibkr-2026-11-03.html")

ROWS = ["MKT", "BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+Q", "BIG V+M+Q", "BIG V+M net", "BIG V+M+Q net",
        "BIG-MOM20", "BIG-VAL20", "BIG-QUAL20", "BIG V+M (20)", "BIG V+M+Q (20)",
        "MOM10", "VAL10", "QUAL10", "V+M", "V+M+Q", "BIG-LOMOM", "BIG-GROWTH"]
LABEL = {"MKT": "US market (CRSP, value-weighted)",
         "BIG-MOM": "Big caps, top 30% momentum", "BIG-VAL": "Big caps, top 30% book-to-market", "BIG-QUAL": "Big caps, top 30% profitability",
         "BIG V+M": "Big value + momentum 50/50", "BIG V+Q": "Big value + profitability 50/50", "BIG V+M+Q": "Big value + momentum + profitability, thirds",
         "BIG V+M net": "  ... 50/50 net of assumed costs", "BIG V+M+Q net": "  ... thirds net of assumed costs",
         "BIG-MOM20": "Concentrated: big caps, top 20% momentum (5x5 cell)", "BIG-VAL20": "Concentrated: big caps, top 20% book-to-market (5x5 cell, 6-31 names)",
         "BIG-QUAL20": "Concentrated: big caps, top 20% profitability (5x5 cell)", "BIG V+M (20)": "Concentrated 50/50 (5x5 cells)",
         "BIG V+M+Q (20)": "Concentrated thirds (5x5 cells)",
         "MOM10": "All caps, top momentum decile", "VAL10": "All caps, top value decile", "QUAL10": "All caps, top profitability decile",
         "V+M": "All-cap value + momentum 50/50", "V+M+Q": "All-cap thirds",
         "BIG-LOMOM": "Big caps, BOTTOM 30% momentum (the other side)", "BIG-GROWTH": "Big caps, bottom 30% book-to-market (growth)"}
ETF_LABEL = {"MTUM": "MTUM (MSCI USA momentum)", "VLUE": "VLUE (MSCI USA value)", "MTUM+VLUE": "MTUM + VLUE 50/50", "SPMO": "SPMO (S&P 500 momentum)",
             "SPMO+VLUE": "SPMO + VLUE 50/50", "QVAL": "QVAL (Alpha Architect value)", "QMOM": "QMOM (Alpha Architect momentum)", "QVAL+QMOM": "QVAL + QMOM 50/50",
             "VFMO": "VFMO (Vanguard momentum)", "VFVA": "VFVA (Vanguard value)", "VFMO+VFVA": "VFMO + VFVA 50/50", "VTV": "VTV (Vanguard value)",
             "IWD": "IWD (Russell 1000 value)", "IWF": "IWF (Russell 1000 growth)", "QQQ": "QQQ", "RSP": "RSP (S&P 500 equal weight)",
             "ARKG": "ARKG (genomics, active)", "XBI": "XBI (biotech, equal weight)", "IBB": "IBB (biotech, cap weight)", "GNOM": "GNOM (genomics)", "SPY": "SPY"}
COMPONENTS = {"BIG V+M": ["BIG-VAL", "BIG-MOM"], "BIG V+Q": ["BIG-VAL", "BIG-QUAL"], "BIG V+M+Q": ["BIG-VAL", "BIG-MOM", "BIG-QUAL"],
              "BIG V+M net": ["BIG-VAL", "BIG-MOM"], "BIG V+M+Q net": ["BIG-VAL", "BIG-MOM", "BIG-QUAL"],
              "BIG V+M (20)": ["BIG-VAL20", "BIG-MOM20"], "BIG V+M+Q (20)": ["BIG-VAL20", "BIG-MOM20", "BIG-QUAL20"],
              "V+M": ["VAL10", "MOM10"], "V+M+Q": ["VAL10", "MOM10", "QUAL10"]}


def names_text(firms, k):
    comps = COMPONENTS.get(k, [k])
    parts = []
    for c in comps:
        if c in firms:
            parts.append(f"{firms[c]['median']:.0f} / {firms[c]['latest']}")
    return " + ".join(parts) if parts else ("all" if k == "MKT" else "–")


def main():
    r = json.load(open(SRC))
    p = r["paths"]
    firms = r["firms"]
    months = p["A"]["MKT"]["months"]
    for k in p["A"]:
        assert p["A"][k]["months"] == months, k
    A = {"months": months, "series": {LABEL[k]: p["A"][k]["levels"] for k in ["MKT", "BIG-MOM", "BIG-VAL", "BIG V+M", "BIG V+M+Q"]}}
    rk = [m for m in sorted(r["rolling"]["BIG V+M"]) if m >= "1973-06"]
    B = {"months": rk, "series": {LABEL[k]: [r["rolling"][k].get(m) for m in rk] for k in ["BIG-MOM", "BIG-VAL", "BIG V+M", "BIG V+M+Q"]}}
    DD = {"months": p["B"]["months"], "series": {"US market": p["B"]["MKT"], "Big value + momentum 50/50": p["B"]["BIG V+M"]}}
    cm = p["C"]["SPY"]["months"]
    C = {"months": cm, "series": {ETF_LABEL[k]: p["C"][k]["levels"] for k in ["SPY", "QQQ", "MTUM", "VLUE", "MTUM+VLUE"]}}
    gm = p["D"]["SPY"]["months"]
    G = {"months": gm, "series": {ETF_LABEL[k]: p["D"][k]["levels"] for k in ["SPY", "ARKG", "XBI", "IBB"]}}
    F = r["french"]
    tables = {era: [[LABEL[k], F[era][k], names_text(firms, k)] for k in ROWS if k in F[era]] for era in ["1963-2026", "1993-2026", "2010-2026"]}
    etfs = [[ETF_LABEL.get(k, k), v] for k, v in r["etfs"].items()]
    com = {k: v for k, v in r["etfs_common"].items() if k != "window"}
    common_rows = [[ETF_LABEL.get(k, k), v] for k, v in com.items()]
    fr_win = [[LABEL[k], v] for k, v in r["french_on_etf_window"].items()]
    dec = r["decades"]
    decs = sorted({d for k in dec for d in dec[k]})
    decades = {"cols": decs, "months": [dec["BIG-MOM"].get(d, {}).get("n") for d in decs],
               "rows": [[LABEL[k], [dec[k].get(d, {}).get("excess") for d in decs]] for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q", "BIG-VAL20", "BIG V+M (20)", "MOM10", "VAL10"]]}
    e63, e10 = F["1963-2026"], F["2010-2026"]
    oct_ = r["october_2026"]
    kpi = {"vm_ex": e63["BIG V+M"]["excess_cagr"], "vm_ex_net": e63["BIG V+M net"]["excess_cagr"], "vm_cagr": e63["BIG V+M"]["cagr"], "mkt_cagr": e63["MKT"]["cagr"],
           "vm_2010": e10["BIG V+M"]["excess_cagr"], "vm_2010_net": e10["BIG V+M net"]["excess_cagr"],
           "vm_share": e63["BIG V+M"]["roll10"]["share_positive"], "vm_windows": e63["BIG V+M"]["roll10"]["windows"], "vm_worst": e63["BIG V+M"]["roll10"]["worst"],
           "vm_2010s": dec["BIG V+M"]["2010s"]["excess"], "vm_2020s": dec["BIG V+M"]["2020s"]["excess"],
           "mv_live": r["etfs"]["MTUM+VLUE"]["excess_cagr"], "qq_live": r["etfs"]["QVAL+QMOM"]["excess_cagr"], "spmo_live": r["etfs"]["SPMO"]["excess_cagr"],
           "spmo_oct": oct_["SPMO"]["excess_to_oct"], "mv_oct": oct_["MTUM+VLUE"]["excess_to_oct"],
           "arkg": r["etfs"]["ARKG"]["excess_cagr"], "arkg_dd": r["etfs"]["ARKG"]["maxdd"], "xbi": r["etfs"]["XBI"]["excess_cagr"],
           "xbi_dd": r["etfs"]["XBI"]["maxdd"], "xbi_spy_dd": r["etfs"]["XBI"]["bench_maxdd"], "gnom": r["etfs"]["GNOM"]["excess_cagr"]}
    rally_labels = {k: LABEL[k] for k in ["BIG-MOM", "BIG-VAL", "BIG-QUAL", "BIG V+M", "BIG V+M+Q", "BIG-VAL20", "BIG V+M (20)"]}
    rally_labels.update({k: ETF_LABEL[k] for k in ["MTUM", "VLUE", "MTUM+VLUE", "SPMO", "QVAL", "QMOM"]})
    data = {"A": A, "B": B, "DD": DD, "C": C, "G": G, "tables": tables, "etfs": etfs, "common": common_rows, "common_window": r["etfs_common"]["window"],
            "fr_win": fr_win, "blends": r["blends"], "decades": decades, "costs": r["drag_pct_per_year"], "kpi": kpi, "generated": r["generated"],
            "spy_vs_mkt": r["spy_vs_mkt"], "rally": r["rally"], "rallyLabels": rally_labels, "firms": firms, "sources": r["sources"], "october": oct_}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(PAGE, "w").write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Value and momentum in IBKR</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--ctx:#b9b7ae;--ctx2:#8e8c84;--neg:#e34948;--band:rgba(42,120,214,.10)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.14)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.14)}
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
.neg{color:var(--neg)}.pos{color:var(--ink)}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:340px}
</style>
</head>
<body>
<main>
<h1>A long-only value / momentum stock sleeve in IBKR: what it has earned</h1>
<p class="sub-h">Two kinds of evidence. Ken French's long-only portfolios (CRSP/Compustat, survivorship-free, point-in-time, value-weighted, gross of costs): big-cap rows of the 2x3 sorts, i.e. stocks above the NYSE size median in the top 30% on momentum (~300 names), book-to-market (~140) or profitability (~310), which is what an IBKR sleeve would actually hold; the concentrated 5x5 corner cells (top 20% x top 20%; the value corner is 6-31 names, bank-heavy) are shown as a sensitivity. Then the live ETFs that implement the same ideas, net of fees, as they traded. Benchmark: the US market (SPY where it exists; SPY and the CRSP market track at 0.99 correlation).</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>A. Growth of $1 since 1963: big-cap value, momentum and their blends vs the market (log scale, gross)</h2>
<p class="sub-h">The 50/50 of the big-cap top-30% value and top-30% momentum rows, rebalanced monthly, and the thirds version with profitability. Costs are not in these lines; the table carries the net-of-assumed-cost rows, the concentrated cells and the all-cap deciles. "names" = median / latest firm count in the row since 1963.</p>
<div class="legend" id="lgA"></div>
<div class="chartwrap"><svg id="chA" role="img" aria-label="Growth of one dollar in the US market, big-cap momentum, big-cap value and their blends, 1963 to 2026, log scale"></svg></div>
<details open><summary>Table: by era (CAGR, Sharpe on excess returns, max drawdown, excess CAGR vs the market, tracking error, beta, calendar years ahead, rolling 10-year windows: share ahead / worst / latest)</summary>
<div id="tabs"></div></details>
</section>

<section class="card">
<h2>B. The honest chart: rolling 10-year excess return vs the market</h2>
<p class="sub-h">Annualized CAGR of each sleeve minus the market's over the trailing 120 months, gross (overlapping windows). Above zero = the sleeve beat the market over the previous decade. Momentum rarely dips below; value spends whole decades below; the blends sit between.</p>
<div class="legend" id="lgB"></div>
<div class="chartwrap"><svg id="chB" role="img" aria-label="Rolling ten-year excess annual return of big-cap momentum, value and their blends versus the market, 1973 to 2026"></svg></div>
<div class="tablewrap"><table id="tbDec"></table></div>
<p class="sub-h" style="margin-top:14px">The last 21 months carry the modern-era numbers. Excess CAGR over the market (French rows) or SPY (ETFs), with the recent windows stopped at 2024-12 and then run through 2026-09, and the 2025-01..2026-09 rally months alone (annualized from 21 months). Stopped at 2024-12 the big-cap 50/50 had lost to the market since 2010 and the live MTUM+VLUE blend had lagged SPY by 2%/yr; the 2025-26 value rally put them back to even and ahead. The concentrated value cell's rally number is 9-13 names.</p>
<div class="tablewrap"><table id="tbRally"></table></div>
</section>

<section class="card">
<h2>C. Drawdowns: the sleeve falls with the market</h2>
<p class="sub-h">Drawdown from the prior peak, monthly, gross. A long-only sleeve has a beta near 1 (1.06 since 2010, 1.08 in the 2025-26 months; the concentrated value cell 1.8); it does not protect in a crash, it is a different way to hold stocks.</p>
<div class="legend" id="lgDD"></div>
<div class="chartwrap"><svg id="chDD" role="img" aria-label="Drawdowns of the US market and the big-cap value plus momentum blend since 1963"></svg></div>
</section>

<section class="card">
<h2>D. What the buyable versions actually did, net of fees</h2>
<p class="sub-h">Growth of $1 since mid-2013 in MTUM and VLUE (the largest US momentum and value ETFs), their 50/50, SPY and QQQ for context. Below: every value / momentum ETF with a record, each on its own window against SPY, then all of them on one window with the French rows beside them. Momentum shows no implementation gap (MTUM and SPMO matched or beat the French big-cap momentum row); the value funds (sector-neutral, diluted, index-constrained) sit between the broad French value row and nothing.</p>
<div class="legend" id="lgC"></div>
<div class="chartwrap"><svg id="chC" role="img" aria-label="Growth of one dollar in MTUM, VLUE, their blend, SPY and QQQ since 2013, log scale"></svg></div>
<details open><summary>Table: each ETF on its own window vs SPY (through 2026-09; October 2026 below)</summary><div class="tablewrap"><table id="tbE"></table></div></details>
<details><summary>Table: the same funds on one window, plus the French rows on that window (gross)</summary><div class="tablewrap"><table id="tbE2"></table></div></details>
<details><summary>Table: the ETFs' October 2026 (a complete month the French cut discards)</summary><div class="tablewrap"><table id="tbOct"></table></div></details>
</section>

<section class="card">
<h2>E. Genomics, for context (not the owner's sleeve)</h2>
<p class="sub-h">Growth of $1 since the end of 2014 in ARKG, XBI and IBB against SPY. The owner's IBKR genomics sleeve is a different, hand-picked book; its record is the input this page is missing.</p>
<div class="legend" id="lgG"></div>
<div class="chartwrap"><svg id="chG" role="img" aria-label="Growth of one dollar in ARKG, XBI, IBB and SPY since the end of 2014, log scale"></svg></div>
</section>

<section class="card">
<h2>F. SPY with a sleeve bolted on</h2>
<p class="sub-h">SPY plus x of the big-cap sleeve (net of assumed costs), monthly rebalanced. CAGR / Sharpe / max drawdown.</p>
<div class="tablewrap"><table id="tbBl"></table></div>
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
const sg = v => v == null ? '–' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
const cls = v => v == null ? '' : (v < 0 ? ' class="n neg"' : ' class="n"');
const K = D.kpi;
[[`${sg(K.vm_ex)} / yr`, `big-cap value + momentum 50/50 over the US market, 1963-2026, gross (${sg(K.vm_ex_net)} net of assumed costs): ${pc(K.vm_cagr)} vs ${pc(K.mkt_cagr)}. Since 2010: ${sg(K.vm_2010)} gross, ${sg(K.vm_2010_net)} net`],
 [`${pc0(K.vm_share)} of 10-year windows`, `overlapping windows since 1963 (${K.vm_windows}) in which the 50/50 beat the market; worst window ${sg(K.vm_worst)}/yr; the 2010s ${sg(K.vm_2010s)}/yr, the 2020s so far ${sg(K.vm_2020s)}/yr`],
 [`${sg(K.mv_live)} / ${sg(K.qq_live)}`, `MTUM+VLUE (2013-) and QVAL+QMOM (2016-) vs SPY, net, as they actually traded, through 2026-09; SPMO alone ${sg(K.spmo_live)} (${sg(K.spmo_oct)} with October 2026)`],
 [`${sg(K.arkg)} / yr`, `ARKG vs SPY since 2015 with a ${pc0(K.arkg_dd)} drawdown; GNOM ${sg(K.gnom)}; XBI ${sg(K.xbi)} since 2006 (drawdown ${pc0(K.xbi_dd)} vs SPY's ${pc0(K.xbi_spy_dd)}). Context only: the owner's genomics sleeve is the missing input`]]
 .forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; k.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(k); });

function lineChart(svgId, months, series, colors, opts){
  const svg = document.getElementById(svgId), W = 900, H = 360, l = 54, r = 250, t = 14, b = 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const names = Object.keys(series), n = months.length;
  const vals = names.flatMap(k => series[k].filter(v => v != null));
  const lo = Math.log10(Math.min(...vals) * 0.95), hi = Math.log10(Math.max(...vals) * 1.05);
  const X = i => l + i / (n - 1) * (W - l - r), Y = v => t + (hi - Math.log10(v)) / (hi - lo) * (H - t - b);
  const ticks = []; for (let e = Math.floor(lo); e <= Math.ceil(hi); e++) [1, 2, 5].forEach(m => { const v = m * Math.pow(10, e); if (Math.log10(v) >= lo && Math.log10(v) <= hi) ticks.push(v); });
  ticks.forEach(v => { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, v >= 1 ? '$' + v.toLocaleString() : '$' + v.toFixed(2)); });
  const years = months.map((m, i) => [m, i]).filter(([m, i]) => m.endsWith('-01') && (+m.slice(0, 4)) % (opts.yearStep || 5) === 0);
  years.forEach(([m, i]) => el('text', {x: X(i), y: H - 8, 'text-anchor': 'middle', class: 'ax'}, svg, m.slice(0, 4)));
  const ends = names.map(k => { const last = series[k].map((v, i) => [v, i]).filter(([v]) => v != null).pop(); return {k, v: last[0], y: Y(last[0])}; }).sort((a, b2) => a.y - b2.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  names.forEach(k => {
    const pts = series[k].map((v, i) => v == null ? null : `${X(i)},${Y(v)}`).filter(Boolean).join(' ');
    const ctx = (opts.context || []).includes(k);
    el('polyline', {points: pts, fill: 'none', stroke: colors[k], 'stroke-width': ctx ? 1.6 : 2, 'stroke-linejoin': 'round'}, svg);
    const e = ends.find(x => x.k === k);
    el('text', {x: W - r + 6, y: e.y + 4, class: ctx ? 'lb' : 'lbb', fill: ctx ? 'var(--ink2)' : 'var(--ink)'}, svg, `${(opts.short || {})[k] || k} $${e.v < 10 ? e.v.toFixed(2) : Math.round(e.v).toLocaleString()}`);
  });
  const cross = el('line', {x1: 0, x2: 0, y1: t, y2: H - b, stroke: 'var(--axis)', opacity: 0}, svg);
  const zone = el('rect', {x: l, y: t, width: W - l - r, height: H - t - b, fill: 'transparent'}, svg);
  zone.addEventListener('mousemove', e => { const bb = svg.getBoundingClientRect(); const px = (e.clientX - bb.left) / bb.width * W; const i = Math.max(0, Math.min(n - 1, Math.round((px - l) / (W - l - r) * (n - 1))));
    cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.setAttribute('opacity', 1);
    tip(e, `<b>${months[i]}</b><br>` + names.map(k => series[k][i] == null ? '' : `${k}: $${series[k][i] < 10 ? series[k][i].toFixed(2) : Math.round(series[k][i]).toLocaleString()}`).filter(Boolean).join('<br>')); });
  zone.addEventListener('mouseleave', () => { cross.setAttribute('opacity', 0); untip(); });
}
function linChart(svgId, months, series, colors, opts){
  const svg = document.getElementById(svgId), W = 900, H = 300, l = 54, r = 250, t = 14, b = 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const names = Object.keys(series), n = months.length;
  const vals = names.flatMap(k => series[k].filter(v => v != null));
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals); const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
  const X = i => l + i / (n - 1) * (W - l - r), Y = v => t + (hi - v) / (hi - lo) * (H - t - b);
  const step = opts.step || 0.02;
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) { const z = Math.abs(v) < 1e-9; el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: z ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (Math.round(v * 100) || 0) + '%'); }
  const years = months.map((m, i) => [m, i]).filter(([m, i]) => m.endsWith('-01') && (+m.slice(0, 4)) % (opts.yearStep || 5) === 0);
  years.forEach(([m, i]) => el('text', {x: X(i), y: H - 8, 'text-anchor': 'middle', class: 'ax'}, svg, m.slice(0, 4)));
  const ends = names.map(k => { const last = series[k].map((v, i) => [v, i]).filter(([v]) => v != null).pop(); return {k, v: last[0], y: Y(last[0])}; }).sort((a, b2) => a.y - b2.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  names.forEach(k => {
    const ctx = (opts.context || []).includes(k);
    if (opts.fill) { const pts = series[k].map((v, i) => v == null ? null : `${X(i)},${Y(v)}`).filter(Boolean); el('polygon', {points: `${X(0)},${Y(0)} ` + pts.join(' ') + ` ${X(n - 1)},${Y(0)}`, fill: colors[k], opacity: ctx ? .18 : .28}, svg); }
    const pts = series[k].map((v, i) => v == null ? null : `${X(i)},${Y(v)}`).filter(Boolean).join(' ');
    el('polyline', {points: pts, fill: 'none', stroke: colors[k], 'stroke-width': ctx ? 1.4 : 1.8, 'stroke-linejoin': 'round'}, svg);
    const e = ends.find(x => x.k === k);
    el('text', {x: W - r + 6, y: e.y + 4, class: ctx ? 'lb' : 'lbb', fill: ctx ? 'var(--ink2)' : 'var(--ink)'}, svg, `${(opts.short || {})[k] || k} ${(e.v >= 0 ? '+' : '')}${(e.v * 100).toFixed(1)}%`);
  });
  const cross = el('line', {x1: 0, x2: 0, y1: t, y2: H - b, stroke: 'var(--axis)', opacity: 0}, svg);
  const zone = el('rect', {x: l, y: t, width: W - l - r, height: H - t - b, fill: 'transparent'}, svg);
  zone.addEventListener('mousemove', e => { const bb = svg.getBoundingClientRect(); const px = (e.clientX - bb.left) / bb.width * W; const i = Math.max(0, Math.min(n - 1, Math.round((px - l) / (W - l - r) * (n - 1))));
    cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.setAttribute('opacity', 1);
    tip(e, `<b>${months[i]}</b>${opts.tipNote || ''}<br>` + names.map(k => series[k][i] == null ? '' : `${k}: ${(series[k][i] >= 0 ? '+' : '')}${(series[k][i] * 100).toFixed(1)}%`).filter(Boolean).join('<br>')); });
  zone.addEventListener('mouseleave', () => { cross.setAttribute('opacity', 0); untip(); });
}
function statRow(name, s, names){
  const r10 = s.roll10 || {};
  return `<tr><td>${name}</td><td class="n">${names == null ? '' : names}</td><td class="n">${pc(s.cagr)}</td><td class="n">${pc(s.vol)}</td><td class="n">${f2(s.sharpe)}</td><td class="n">${pc0(s.maxdd)}</td><td${cls(s.excess_cagr)}>${sg(s.excess_cagr)}</td><td class="n">${pc(s.te)}</td><td class="n">${f2(s.beta)}</td><td class="n">${s.years_beating}/${s.years}</td><td class="n">${r10.share_positive == null ? '–' : pc0(r10.share_positive)}</td><td${cls(r10.worst)}>${sg(r10.worst)}</td><td${cls(r10.latest)}>${sg(r10.latest)}</td></tr>`;
}
const HEAD = (bench) => `<thead><tr><th>Portfolio</th><th class="n">names</th><th class="n">CAGR</th><th class="n">vol</th><th class="n">Sharpe</th><th class="n">max DD</th><th class="n">vs ${bench}</th><th class="n">TE</th><th class="n">beta</th><th class="n">years ahead</th><th class="n">10y windows ahead</th><th class="n">worst 10y</th><th class="n">last 10y</th></tr></thead>`;

// A
const nA = Object.keys(D.A.series), colA = {}; colA[nA[0]] = 'var(--ctx2)'; colA[nA[1]] = 'var(--s2)'; colA[nA[2]] = 'var(--s1)'; colA[nA[3]] = 'var(--s3)'; colA[nA[4]] = 'var(--s4)';
legend('lgA', Object.entries(colA));
lineChart('chA', D.A.months, D.A.series, colA, {context: [nA[0]], yearStep: 5, short: {[nA[0]]: 'Market', [nA[1]]: 'Big momentum', [nA[2]]: 'Big value', [nA[3]]: '50/50', [nA[4]]: 'Thirds'}});
document.getElementById('tabs').innerHTML = Object.entries(D.tables).map(([era, rows]) => `<h3 style="font-size:14px;margin:12px 0 4px">${era.replace('-', ' to ')} (from ${rows[0][1].from} to ${rows[0][1].to})</h3><div class="tablewrap"><table>${HEAD('market')}<tbody>${rows.map(([n, s, nm]) => statRow(n, s, nm)).join('')}</tbody></table></div>`).join('');

// B rolling
const nB = Object.keys(D.B.series), colB = {}; colB[nB[0]] = 'var(--s2)'; colB[nB[1]] = 'var(--s1)'; colB[nB[2]] = 'var(--s3)'; colB[nB[3]] = 'var(--s4)';
legend('lgB', Object.entries(colB));
linChart('chB', D.B.months, D.B.series, colB, {yearStep: 5, step: 0.02, short: {[nB[0]]: 'Big momentum', [nB[1]]: 'Big value', [nB[2]]: '50/50', [nB[3]]: 'Thirds'}, tipNote: ' (trailing 10 years, annualized)'});
document.getElementById('tbDec').innerHTML = `<thead><tr><th>Excess CAGR vs the market, by decade (gross)</th>${D.decades.cols.map((c, i) => `<th class="n">${c}${D.decades.months[i] && D.decades.months[i] < 120 ? `<br><span style="font-weight:400">(${D.decades.months[i]} m)</span>` : ''}</th>`).join('')}</tr></thead><tbody>` +
  D.decades.rows.map(([n, vals]) => `<tr><td>${n}</td>${vals.map(v => `<td${v == null ? ' class="n"' : cls(v)}>${v == null ? '–' : sg(v)}</td>`).join('')}</tr>`).join('') + '</tbody>';
(function(){
  const wins = Object.keys(D.rally), keys = ['BIG-MOM', 'BIG-VAL', 'BIG-QUAL', 'BIG V+M', 'BIG V+M+Q', 'BIG-VAL20', 'BIG V+M (20)', 'MTUM', 'VLUE', 'MTUM+VLUE', 'SPMO', 'QVAL', 'QMOM'];
  const nm = k => (D.rallyLabels[k] || k);
  const wl = w => w === '2025-01..2026-09' ? `${w}<br><span style="font-weight:400">(21 m, annualized)</span>` : w;
  let h = `<thead><tr><th>excess CAGR</th>${wins.map(w => `<th class="n">${wl(w)}</th>`).join('')}</tr></thead><tbody>`;
  h += `<tr><td>market CAGR (French rows' benchmark)</td>${wins.map(w => `<td class="n">${pc(D.rally[w].MKT.cagr)}</td>`).join('')}</tr>`;
  h += `<tr><td>SPY CAGR (the ETFs' benchmark)</td>${wins.map(w => `<td class="n">${pc(D.rally[w].SPY.cagr)}</td>`).join('')}</tr>`;
  keys.forEach(k => { h += `<tr><td>${nm(k)}</td>${wins.map(w => { const v = D.rally[w][k]; return v ? `<td${cls(v.excess)} title="from ${v.from}, ${v.n} months, beta ${f2(v.beta)}, cumulative ${sg(v.total)}">${sg(v.excess)}</td>` : '<td class="n">–</td>'; }).join('')}</tr>`; });
  document.getElementById('tbRally').innerHTML = h + '</tbody>';
})();

// drawdowns
const nDD = Object.keys(D.DD.series), colDD = {}; colDD[nDD[0]] = 'var(--ctx2)'; colDD[nDD[1]] = 'var(--s3)';
legend('lgDD', Object.entries(colDD));
linChart('chDD', D.DD.months, D.DD.series, colDD, {yearStep: 5, step: 0.1, fill: true, context: [nDD[0]], short: {[nDD[0]]: 'Market', [nDD[1]]: '50/50'}});

// C live ETFs
const nC = Object.keys(D.C.series), colC = {}; colC[nC[0]] = 'var(--ctx2)'; colC[nC[1]] = 'var(--ctx)'; colC[nC[2]] = 'var(--s2)'; colC[nC[3]] = 'var(--s1)'; colC[nC[4]] = 'var(--s3)';
legend('lgC', Object.entries(colC));
lineChart('chC', D.C.months, D.C.series, colC, {context: [nC[0], nC[1]], yearStep: 2, short: {[nC[0]]: 'SPY', [nC[1]]: 'QQQ', [nC[2]]: 'MTUM', [nC[3]]: 'VLUE', [nC[4]]: '50/50'}});
document.getElementById('tbE').innerHTML = `<thead><tr><th>ETF</th><th class="n">window</th><th class="n">CAGR</th><th class="n">SPY</th><th class="n">vs SPY</th><th class="n">Sharpe</th><th class="n">SPY</th><th class="n">max DD</th><th class="n">SPY</th><th class="n">TE</th><th class="n">beta</th><th class="n">years ahead</th></tr></thead><tbody>` +
  D.etfs.map(([n, s]) => `<tr><td>${n}</td><td class="n">${s.from}..${s.to}</td><td class="n">${pc(s.cagr)}</td><td class="n">${pc(s.bench_cagr)}</td><td${cls(s.excess_cagr)}>${sg(s.excess_cagr)}</td><td class="n">${f2(s.sharpe)}</td><td class="n">${f2(s.bench_sharpe)}</td><td class="n">${pc0(s.maxdd)}</td><td class="n">${pc0(s.bench_maxdd)}</td><td class="n">${pc(s.te)}</td><td class="n">${f2(s.beta)}</td><td class="n">${s.years_beating}/${s.years}</td></tr>`).join('') + '</tbody>';
document.getElementById('tbE2').innerHTML = `<thead><tr><th>${D.common_window}</th><th class="n">CAGR</th><th class="n">vol</th><th class="n">Sharpe</th><th class="n">max DD</th><th class="n">vs SPY</th><th class="n">TE</th><th class="n">beta</th><th class="n">years ahead</th></tr></thead><tbody>` +
  D.common.map(([n, s]) => `<tr><td>${n}</td><td class="n">${pc(s.cagr)}</td><td class="n">${pc(s.vol)}</td><td class="n">${f2(s.sharpe)}</td><td class="n">${pc0(s.maxdd)}</td><td${cls(s.excess_cagr)}>${sg(s.excess_cagr)}</td><td class="n">${pc(s.te)}</td><td class="n">${f2(s.beta)}</td><td class="n">${s.years_beating}/${s.years}</td></tr>`).join('') +
  `<tr><td colspan="9" style="color:var(--ink2)">French rows on the same window, gross:</td></tr>` +
  D.fr_win.map(([n, s]) => `<tr><td>${n}</td><td class="n">${pc(s.cagr)}</td><td class="n">${pc(s.vol)}</td><td class="n">${f2(s.sharpe)}</td><td class="n">${pc0(s.maxdd)}</td><td${cls(s.excess_cagr)}>${sg(s.excess_cagr)}</td><td class="n">${pc(s.te)}</td><td class="n">${f2(s.beta)}</td><td class="n">${s.years_beating}/${s.years}</td></tr>`).join('') + '</tbody>';
(function(){
  const O = D.october, ks = Object.keys(O).filter(k => k !== 'month');
  document.getElementById('tbOct').innerHTML = `<thead><tr><th>fund</th><th class="n">${O.month} return</th><th class="n">vs SPY, CAGR to 2026-09</th><th class="n">vs SPY, CAGR to ${O.month}</th></tr></thead><tbody>` +
    ks.map(k => { const v = O[k]; const lbl = ({SPY: 'SPY', QQQ: 'QQQ'})[k] || (D.rallyLabels[k] || k); return `<tr><td>${lbl}</td><td${cls(v.ret)}>${sg(v.ret)}</td><td${cls(v.excess_to_sep)}>${v.excess_to_sep == null ? '–' : sg(v.excess_to_sep)}</td><td${cls(v.excess_to_oct)}>${sg(v.excess_to_oct)}</td></tr>`; }).join('') + '</tbody>';
})();

// G genomics
const nG = Object.keys(D.G.series), colG = {}; colG[nG[0]] = 'var(--ctx2)'; colG[nG[1]] = 'var(--s2)'; colG[nG[2]] = 'var(--s1)'; colG[nG[3]] = 'var(--s3)';
legend('lgG', Object.entries(colG));
lineChart('chG', D.G.months, D.G.series, colG, {context: [nG[0]], yearStep: 2, short: {[nG[0]]: 'SPY', [nG[1]]: 'ARKG', [nG[2]]: 'XBI', [nG[3]]: 'IBB'}});

// blends
(function(){
  const xs = ['0.0', '0.2', '0.4', '0.6', '1.0'];
  let h = `<thead><tr><th>era / sleeve</th>${xs.map(x => `<th class="n">x = ${x}</th>`).join('')}</tr></thead><tbody>`;
  for (const era in D.blends) for (const sl in D.blends[era]) h += `<tr><td>${era}, ${sl}</td>` + xs.map(x => { const v = D.blends[era][sl][x]; return `<td class="n">${pc(v.cagr)} / ${f2(v.sharpe)} / ${pc0(v.maxdd)}</td>`; }).join('') + '</tr>';
  document.getElementById('tbBl').innerHTML = h + '</tbody>';
})();

// phone: show the recent end of each chart first
document.querySelectorAll('.chartwrap').forEach(w => { w.scrollLeft = w.scrollWidth; });

const Fm = D.firms;
[`French portfolios: Ken French's data library, downloaded 2026-11-03 (CRSP vintage 202609), value-weighted monthly returns through 2026-09. Sleeve rows are the BIG side of the 2x3 sorts (size above the NYSE median x the top 30% by NYSE breakpoints): momentum (prior 12-2 month return, monthly rebalance; ${Fm['BIG-MOM'].min}-${Fm['BIG-MOM'].max} names since 1963, median ${Math.round(Fm['BIG-MOM'].median)}), book-to-market (June; ${Fm['BIG-VAL'].min}-${Fm['BIG-VAL'].max}, median ${Math.round(Fm['BIG-VAL'].median)}) and operating profitability (June; median ${Math.round(Fm['BIG-QUAL'].median)}). The concentrated rows are the 5x5 corner cells (largest size quintile x top signal quintile): the value corner holds ${Fm['BIG-VAL20'].min}-${Fm['BIG-VAL20'].max} names (median ${Math.round(Fm['BIG-VAL20'].median)}, ${Fm['BIG-VAL20'].latest} in ${Fm['BIG-VAL20'].latest_month}) and loads ~1.15x on large financials (counter-agent); the momentum corner ${Fm['BIG-MOM20'].min}-${Fm['BIG-MOM20'].max}. The all-cap deciles hold hundreds of names including microcaps and are not holdable at this size. Blends are monthly-rebalanced equal mixes. Market = Mkt-RF + RF; Sharpe uses French's risk-free rate. SPY vs the CRSP market ${D.spy_vs_mkt.from}..${D.spy_vs_mkt.to}: ${pc(D.spy_vs_mkt.cagr)} vs ${pc(D.spy_vs_mkt.bench_cagr)}, correlation ${f2(D.spy_vs_mkt.corr)}.`,
 `Costs: the French rows are gross. "Net" rows subtract an ASSUMED drag of ${Object.entries(D.costs).filter(([k]) => ['BIG-MOM', 'BIG-VAL', 'BIG-QUAL'].includes(k)).map(([k, v]) => `${k} ${v.toFixed(2)}%`).join(', ')} a year. A monthly 12-2 sort keeps a top-30% name with probability ~0.8 a month, i.e. roughly 250% one-way turnover a year; at 10-20 bps a round trip in mega caps that is ~0.4-0.5%/yr for a $150k sleeve and more for $50k (IBKR Pro's $1 minimum per order on 300 names); the June sorts turn over 20-30% a year. A sensitivity, not a measurement; taxes are not in it (Act 60 makes them moot for the owner).`,
 'Live ETFs: Yahoo monthly adjusted closes (month-end, dividends included), net of fees; each fund\'s first return month is dropped. French\'s series end 2026-09, so every window stops there; the ETFs\' complete October 2026 is in the separate table (MTUM and SPMO fell ~10% in that month against SPY -0.9%). The funds implement different definitions from the French sorts: index value is sector-neutral, multi-metric and diluted, so the gap between the French value rows and the value funds is mostly definition, not trading cost; momentum funds show no gap.',
 'A long-only sleeve carries market beta ~1 (the 50/50: 0.99 since 1963, 1.06 since 2010, 1.08 in the 2025-26 rally months; the concentrated value cell 1.8 and VLUE 1.4 in those months): it is a different way to own stocks, not a diversifier for the Composer book (which has no measurable value or momentum loading, add. 51). Rolling 10-year windows overlap: 62 years hold six independent decades; the calendar-year counts are the independent tally. The rolling chart is the risk to read: value spent the 2010s behind the market; momentum\'s worst decade was the 2000s.',
 `Generated ${D.generated}. Research only; nothing traded.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
