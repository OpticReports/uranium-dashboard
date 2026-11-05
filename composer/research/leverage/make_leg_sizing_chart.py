#!/usr/bin/env python3
"""Exhibit for the KMLM leg-sizing study (research/leverage/leg_sizing.py).
Reads results/leg-sizing-2026-11-05.json; writes results/leg-sizing-2026-11-05.html (inline SVG, no external libs,
light/dark via prefers-color-scheme, palette tokens as in make_overnight_chart.py)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")
SRC = os.path.join(RES, "leg-sizing-2026-11-05.json")
PAGE = os.path.join(RES, "leg-sizing-2026-11-05.html")
EQ_SERIES = ["base", "cap60", "cap50", "cap37.5", "cap25", "vt_m37.5", "two_x", "one_x"]
DD_SERIES = ["base", "cap37.5", "vt_m37.5", "two_x"]
WKEYS = ("cagr", "maxdd", "sharpe", "calmar", "worst_day", "worst_day_date", "worst_month", "worst_month_id", "tuw_longest_sessions",
         "tuw_longest_from", "tuw_longest_to", "tuw_share", "final_multiple", "maxdd_peak", "maxdd_trough", "vol")


def main():
    J = json.load(open(SRC))
    V = J["variants"]
    variants = []
    for vid in J["order"]:
        v = V[vid]
        variants.append({"id": vid, "label": v["label"], "family": v["family"], "legw": v["avg_leg_weight"], "to": v["turnover_yr"], "params": v["params"],
                         "w": {wk: {k: v["windows"][wk].get(k) for k in WKEYS} for wk in ("full", "since2015")},
                         "tr": v["tradeoff"], "ep": v["episodes"],
                         "day": {ps: (None if v["day_2026_11_05"][ps] is None else {k: v["day_2026_11_05"][ps][k] for k in ("day", "leg_weight", "book_day", "leg_instrument")})
                                 for ps in ("as_traded", "close")},
                         "loyo": (None if "loyo" not in v else {wk: {"min": v["loyo"][wk]["min"], "max": v["loyo"][wk]["max"], "no2020": v["loyo"][wk]["by_year"].get("2020"),
                                                                     "no2022": v["loyo"][wk]["by_year"].get("2022")} for wk in ("full", "since2015")}),
                         "book": {wk: {k: v["book"][wk][k] for k in ("cagr", "maxdd", "sharpe")} for wk in ("full", "since2015")}})
    for vid in EQ_SERIES + DD_SERIES:          # every variant is sampled on the same sessions: one date array per window
        for wk in ("full", "since2015"):
            assert J["paths"][vid][wk]["dates"] == J["paths"]["base"][wk]["dates"], (vid, wk)
    paths = {"eq": {"dates": J["paths"]["base"]["full"]["dates"], "series": {vid: J["paths"][vid]["full"]["value"] for vid in EQ_SERIES}},
             "dd": {wk: {"dates": J["paths"]["base"][wk]["dates"], "series": {vid: J["paths"][vid][wk]["dd"] for vid in DD_SERIES}} for wk in ("full", "since2015")}}
    E = J["edge"]
    edge = {"leg_days": E["leg_days"], "leg_mean": E["leg_mean"], "leg_t": E["leg_t"], "q_edges": E["sigma_quartile_edges"],
            "sig": E["by_sigma_quartile"], "vix": E["by_vix"], "branch": E["by_branch"], "branch15": E["by_branch_since2015"],
            "pl_sig": E["placebo_sigma_Q4_minus_Q1"], "pl_vix": E["placebo_vix_gt25_minus_le25"],
            "welch": E["welch_t_Q4_minus_Q1"], "within": E["within_branch_own_quartiles"], "mirror": E["mirror_1x_twins_same_days"],
            "q4comp": E["q4_composition"], "s15q": E["since2015_own_quartiles"], "worst": E["worst_of_branches_placebo"]}
    data = {"generated": J["generated"], "inputs": {k: J["inputs"][k] for k in ("days", "sessions", "cost_bps_per_unit_sum_abs_dw", "leg_weight_distribution", "branch_days",
                                                                             "first_real_date", "book_dollars_2026_11_05", "book_weights", "book_1104_weights", "others_1105",
                                                                             "live_holding_1105", "px_1104", "px_1105", "sigma20_soxl_1104", "vix_1104", "composer_realized_1105",
                                                                             "book_realized_1105", "matched_k", "two_x_map", "one_x_map", "vix_mode", "soxl_1030", "path_1030", "ft_leg_1105")},
            "gate": J["gate_test"], "variants": variants, "paths": paths, "bench": J["bench"], "edge": edge, "honesty": J["honesty"], "windows": J["windows"],
            "ft": J["fallthrough"], "conc": J["concentration"]}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(PAGE, "w").write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KMLM leg sizing</title>
<meta name="description" content="What capping or vol-scaling the KMLM switcher's 75% leveraged leg costs in CAGR per point of max drawdown saved, on the engine's own path.">
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--neg:#e34948;--ctx:#b9b7ae;--ctx2:#8e8c84;--band:rgba(42,120,214,.18);
--c0:#0d366b;--c1:#1c5cab;--c2:#2a78d6;--c3:#5598e7;--c4:#86b6ef}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--neg:#e66767;--ctx:#5a5955;--ctx2:#7a7872;--band:rgba(57,135,229,.22);
--c0:#9ec5f4;--c1:#6da7ec;--c2:#3987e5;--c3:#256abf;--c4:#184f95}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--neg:#e66767;--ctx:#5a5955;--ctx2:#7a7872;--band:rgba(57,135,229,.22);
--c0:#9ec5f4;--c1:#6da7ec;--c2:#3987e5;--c3:#256abf;--c4:#184f95}
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
.legend span{display:inline-flex;align-items:center;gap:6px}.sw{display:inline-block;width:14px;height:12px;border-radius:3px}.ln{display:inline-block;width:18px;height:3px;border-radius:2px}
.chartwrap{overflow-x:auto}.chartwrap svg{min-width:680px}.two .chartwrap svg{min-width:300px}
svg{display:block;width:100%;height:auto}.ax{fill:var(--muted);font-size:11px}.lb{fill:var(--ink2);font-size:12px}.lbb{fill:var(--ink);font-size:12px;font-weight:600}.lbs{fill:var(--ink2);font-size:11px}
table{border-collapse:collapse;width:100%;font-size:11.5px}th,td{padding:2px 3px;text-align:left;border-bottom:1px solid var(--grid);white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;padding-left:2px}
thead th{color:var(--ink2);font-weight:600;font-size:12px}.tablewrap{overflow-x:auto}
tr.base td{font-weight:600}tr.bp td{color:var(--ink2);font-style:italic}
details{margin-top:8px;font-size:13.5px}summary{cursor:pointer;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.neg{color:var(--neg)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media (max-width:760px){.two{grid-template-columns:1fr}}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:360px;line-height:1.35}
.tt i{display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
.tt b{font-variant-numeric:tabular-nums}
</style>
</head>
<body>
<main>
<h1>KMLM switcher: what a smaller leveraged leg costs, in CAGR per point of drawdown saved</h1>
<p class="sub-h">The live symphony runs one leveraged leg at 75% of its value (a 3x fund, or two of TECL / SOXL / SVIX at 37.5% each) and a 25% VIX sleeve. On 2026-11-05 it held SOXL at 75% into a −33% session and lost 26.7%. Every row below re-sizes that leg on the engine's own reconstructed daily path (1995-06..2026-11-04; synthetic before each fund's launch; the rules' own years after 2015-06), with the engine's own costs on the variant's own turnover. Decisions are untouched: only how much of the symphony the leg gets, or which instrument earns it. No winner is picked; the curve is the result.</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>A. Growth of $1, 1995-06..2026-11-04 (log scale)</h2>
<p class="sub-h">As built against four caps (the released weight sits in PULS, the tree's own cash leg), the vol-target with the same mean leg weight as the 37.5% cap, the 2x substitution and the 1x reference. The caps are a pure sizing trade: every cap keeps the path's shape and its Sharpe (<span id="fA"></span>) and gives up CAGR roughly in proportion. The vol-target bends the shape: it cuts exposure after every shock, which on a dip-buying engine is also when the recovery is earned.</p>
<div class="legend" id="lgA"></div>
<div class="chartwrap"><svg id="chA" role="img" aria-label="Growth of one dollar on the KMLM path, as built and under each leg-sizing variant, 1995 to 2026, log scale"></svg></div>
</section>

<section class="card">
<h2>B. Drawdown from the running peak</h2>
<p class="sub-h">Left: 1995-2026, where the as-built path's longest stretch under water runs <span id="fB"></span>, in the synthetic era (2007 −49%, 2011 −38%). Right: 2015-2026, the rules' own years; the 54% hole is Feb-Mar 2020, the as-built and every cap's max drawdown since 2015 (<span id="fB3"></span>). A cap scales the hole; the vol-target shallows the entry and lengthens the exit (longest time under water <span id="fB2"></span> sessions over 31 years).</p>
<div class="legend" id="lgB"></div>
<div class="two">
<div class="chartwrap"><svg id="chB1" role="img" aria-label="Drawdown profiles 1995 to 2026 for as built, cap 37.5, vol-target and 2x"></svg></div>
<div class="chartwrap"><svg id="chB2" role="img" aria-label="Drawdown profiles 2015 to 2026 for as built, cap 37.5, vol-target and 2x"></svg></div>
</div>
</section>

<section class="card">
<h2>C. The trade-off: CAGR against max drawdown, one point per variant</h2>
<p class="sub-h">Right and up is better. The cap family traces a near-straight line from as built toward cash; its slope is the price of a point of drawdown: 1.1-1.6 pp of CAGR per pp over 31 years, 4.1-5.2 pp since 2015. The vol-target family sits to the lower-left of the caps over 31 years (it cuts the recoveries as much as the crashes, so the 2006-11 drawdown barely moves) and to the upper-left since 2015 (it was in the right place in Feb 2020 and Nov 2026). VIX gates, the 2x and 1x substitutions and the single-name cap are single points. Hover a point for its numbers; the full table is below. The 2015-26 ratios are one episode: <span id="fC"></span></p>
<div class="legend" id="lgC"></div>
<div class="chartwrap"><svg id="chC1" role="img" aria-label="Scatter of CAGR against max drawdown for every variant, 1995 to 2026"></svg></div>
<div class="chartwrap"><svg id="chC2" role="img" aria-label="Scatter of CAGR against max drawdown for every variant, 2015 to 2026"></svg></div>
<div class="legend" id="lgC3" style="margin-top:14px"></div>
<div class="chartwrap"><svg id="chC3" role="img" aria-label="CAGR given up per point of max drawdown saved, by variant, both windows"></svg></div>
</section>

<section class="card">
<h2>D. 2026-11-05 under each variant</h2>
<p class="sub-h">The path ends at the 11-04 close, so the session is priced from the live holding into it (SOXL 75%, PULS 16%, VXZ 9%) at Composer's ~15:50 prints: SOXL 66.68 → 44.50 (−33.3%), VXZ +6.6%. The 16:00 close printed 40.87 (−38.7%) after a 7% slide in the last five minutes; that figure is in the table. The vol-target rows read SOXL's realized 20-session vol at the 11-04 close (<span id="fD"></span>), which is why they are smallest; the VIX gates read 16.6 and do nothing. The thin line is Composer's realized session (its own fills). The by-product row (the edited tree) holds the engine's own close decision, SOXL / TECL 37.5 each, and is priced at the 16:00 closes only: no ~15:50 TECL print is on file.</p>
<div class="chartwrap"><svg id="chD" role="img" aria-label="The 2026-11-05 session return under each variant"></svg></div>
</section>

<section class="card">
<h2>E. Metrics, both windows</h2>
<p class="sub-h">CAGR on calendar time; Sharpe daily, rf 0; Calmar = CAGR / max DD; TUW = the longest stretch under water, in sessions; "per pp DD" = CAGR given up per point of max drawdown saved against as built (the headline ratio; "none" where no drawdown is saved, negative where CAGR rose while drawdown fell); episodes compound the variant over the dates; 11-05 is the session at Composer's ~15:50 prints (hover for the 16:00-close figure and the book's day); the book is HG / KMLM / SLEEVE / HARV at the 2026-11-05 dollar weights (31 / 26 / 29 / 14%), drifting, reset to those weights at the next close after any engine passes 40%, with the KMLM variant swapped in. Leg wt = the mean leg weight over every session (the leg is 75% on 80% of them, TLT otherwise); cap 37.5 → 1x keeps the SVIX halves in SVIX, which has no twin, so its leg weight is <span id="fE"></span>, not the cap's.</p>
<div class="tablewrap"><table id="tb15"></table></div>
<details open><summary>1995-06-02..2026-11-04 (synthetic before each fund's launch)</summary><div class="tablewrap"><table id="tbFull"></table></div></details>
</section>

<section class="card">
<h2>F. By-products: where the leg's return comes from (the EDGE rule)</h2>
<p class="sub-h" id="pF"></p>
<div class="two">
<div class="chartwrap"><svg id="chF1" role="img" aria-label="Mean daily leg return by quartile of the holdings' prior-close realized vol"></svg></div>
<div class="chartwrap"><svg id="chF2" role="img" aria-label="Mean daily leg return by prior VIX close bucket"></svg></div>
</div>
<div class="tablewrap"><table id="tbF"></table></div>
<h2 style="margin-top:16px">The SOXL dip-buy branch's real counterfactual: the tree with the branch removed</h2>
<p class="sub-h" id="pFT"></p>
<div class="tablewrap"><table id="tbFT"></table></div>
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
function tip(ev, rows){tt.replaceChildren(); rows.forEach(r => { const d = document.createElement('div'); if (r.c) { const i = document.createElement('i'); i.style.background = r.c; d.appendChild(i); } const b = document.createElement('b'); b.textContent = r.v; d.appendChild(b); d.appendChild(document.createTextNode(' ' + r.l)); tt.appendChild(d); });
  tt.style.display = 'block'; tt.style.left = Math.min(ev.clientX + 12, innerWidth - tt.offsetWidth - 8) + 'px'; tt.style.top = Math.min(ev.clientY + 12, innerHeight - tt.offsetHeight - 8) + 'px';}
function untip(){tt.style.display = 'none';}
function legend(id, items){const g = document.getElementById(id); g.replaceChildren(); items.forEach(([n, c, kind]) => { const s = document.createElement('span'); if (kind !== 'none') { const i = document.createElement('i'); i.className = kind === 'line' ? 'ln' : 'sw'; i.style.background = c; s.appendChild(i); } s.appendChild(document.createTextNode(n)); g.appendChild(s); });}
const f2 = v => v == null ? '–' : v.toFixed(2), pc = v => v == null ? '–' : (v * 100).toFixed(1) + '%', pc0 = v => v == null ? '–' : (Math.round(v * 100) || 0) + '%';
const ordn = p => { const n = Math.round(p * 100), m = n % 100, u = n % 10; return n + ((m >= 11 && m <= 13) ? 'th' : u === 1 ? 'st' : u === 2 ? 'nd' : u === 3 ? 'rd' : 'th'); };
const sg = v => v == null ? '–' : (v >= 0 ? '+' : '−') + (Math.abs(v) * 100).toFixed(1) + '%', sg2 = v => v == null ? '–' : (v >= 0 ? '+' : '−') + (Math.abs(v) * 100).toFixed(2) + '%';
const sgB = v => v == null ? '–' : (v >= 0 ? '+' : '−') + Math.round(Math.abs(v) * 100).toLocaleString() + '%';
const cls = v => v == null ? 'n' : (v < 0 ? 'n neg' : 'n');
const byId = {}; D.variants.forEach(v => byId[v.id] = v);
const COL = {base: 'var(--c0)', cap60: 'var(--c1)', cap50: 'var(--c2)', 'cap37.5': 'var(--c3)', cap25: 'var(--c4)', 'vt_m37.5': 'var(--s2)', two_x: 'var(--s3)', one_x: 'var(--ctx2)'};
const NAME = {base: 'as built (75%)', cap60: 'cap 60%', cap50: 'cap 50%', 'cap37.5': 'cap 37.5%', cap25: 'cap 25%', 'vt_m37.5': 'vol-target, mean leg 37.5%', two_x: '2x substitution', one_x: '1x reference'};
const SHORT = {base: 'as built', cap60: 'cap 60', cap50: 'cap 50', 'cap37.5': 'cap 37.5', cap25: 'cap 25', 'cap37.5_1x': 'cap 37.5 → 1x', 'sn37.5': 'single-name cap 37.5', vt_m60: 'vt k.43 (≈cap 60)', vt_m50: 'vt k.32 (≈cap 50)',
  'vt_m37.5': 'vt k.22 (≈cap 37.5)', vt_m25: 'vt k.15 (≈cap 25)', 'vt_k0.3': 'vt k.30', 'vt_k0.45': 'vt k.45', 'vt_k0.6': 'vt k.60', 'vt_k0.9': 'vt k.90', vix25: 'halve if VIX > 25', vix30: 'halve if VIX > 30', two_x: '2x', one_x: '1x',
  soxl_dip_ft: 'SOXL dip-buy removed'};
const B = byId.base, I = D.inputs;
const c50 = byId.cap50, c375 = byId['cap37.5'], vt60 = byId.vt_m60, vt375 = byId['vt_m37.5'];
const capRatios = w => ['cap60', 'cap50', 'cap37.5', 'cap25'].map(k => byId[k].tr[w].cagr_per_dd);
const rng = a => `${Math.min(...a).toFixed(1)}-${Math.max(...a).toFixed(1)}`;
const sigQ = D.edge.sig, q1 = sigQ['Q1 lowest vol'], q4 = sigQ['Q4 highest vol'];
[[`${rng(capRatios('since2015'))} pp`, `of CAGR per point of max drawdown saved by a cap, 2015-26 (${rng(capRatios('full'))} pp over 1995-2026). The 2015-26 figure is the Feb-Mar 2020 episode: leave 2020 out and cap 37.5 reads ${c375.loyo.since2015.no2020.toFixed(1)}, leave 2022 out ${c375.loyo.since2015.no2022.toFixed(1)}. Cap 50%: CAGR ${pc0(B.w.since2015.cagr)} → ${pc0(c50.w.since2015.cagr)}, max DD ${pc0(B.w.since2015.maxdd)} → ${pc0(c50.w.since2015.maxdd)}; the book gives up ${((B.book.since2015.cagr - c50.book.since2015.cagr) * 100).toFixed(0)} pp of CAGR for ${((B.book.since2015.maxdd - c50.book.since2015.maxdd) * 100).toFixed(1)} pp of drawdown`],
 [`${sg(B.day.as_traded.day)} → ${sg(c375.day.as_traded.day)}`, `the 11-05 session as built vs cap 37.5% (Composer's realized session ${sg(I.composer_realized_1105)}); ${sg(vt60.day.as_traded.day)} under the vol-target with the mean leg weight of a 60% cap, which read SOXL's 20-session vol at ${pc0(I.sigma20_soxl_1104)}; the VIX gates read ${I.vix_1104} and did nothing`],
 [`Sharpe ${f2(B.w.since2015.sharpe)} → ${f2(c375.w.since2015.sharpe)}`, `a cap buys nothing risk-adjusted (2015-26; ${f2(B.w.full.sharpe)} → ${f2(c375.w.full.sharpe)} over 31 years). The vol-target: ${f2(vt60.w.since2015.sharpe)} since 2015 but ${f2(vt60.w.full.sharpe)} over 31 years, with ${vt375.w.full.tuw_longest_sessions.toLocaleString()} sessions of its longest stretch under water against ${B.w.full.tuw_longest_sessions.toLocaleString()}`],
 [`${sg2(q1.mean)} → ${sg2(q4.mean)} a day`, `the leg's return from its lowest to its highest prior-vol quartile (t ${q4.t.toFixed(1)}, n ${q4.n}; Welch t ${D.edge.welch.toFixed(1)}, the gap at the ${ordn(D.edge.pl_sig.percentile_of_observed)} percentile of ${D.edge.pl_sig.draws} block placebos). The leg earns most where a vol-target cuts it, but the engine is vol-timed by construction: the same names' 1x twins show the same gradient on the same days (t ${D.edge.mirror['Q4 highest vol'].t.toFixed(1)}) and within a branch it is weak (section F). The SOXL dip-buy branch (11-05's) has no measured return, and the tree without it is worse since 2015: it stays as built`]]
 .forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; const bb = document.createElement('b'); bb.textContent = b; const ss = document.createElement('span'); ss.textContent = s; k.append(bb, ss); document.getElementById('kpis').appendChild(k); });
// the hand-written sentences' numbers come from the JSON (counter-agent fix 3)
const vtRatios = D.variants.filter(v => v.family === 'vt').map(v => v.tr.full.cagr_per_dd).filter(x => x != null);
const tuwYears = ((Date.parse(B.w.full.tuw_longest_to) - Date.parse(B.w.full.tuw_longest_from)) / 365.25 / 86400000).toFixed(1);
const lo = (id, w) => byId[id].loyo[w], vix30 = byId.vix30, c60 = byId.cap60;
const fills = {
  fA: `${f2(B.w.full.sharpe)} → ${f2(c375.w.full.sharpe)} over 31 years, ${f2(B.w.since2015.sharpe)} → ${f2(c375.w.since2015.sharpe)} since 2015`,
  fB: `${B.w.full.tuw_longest_from} → ${B.w.full.tuw_longest_to} (${tuwYears} years, ${B.w.full.tuw_longest_sessions.toLocaleString()} sessions)`,
  fB2: `${B.w.full.tuw_longest_sessions.toLocaleString()} → ${vt375.w.full.tuw_longest_sessions.toLocaleString()}`,
  fB3: `the ${Object.keys(D.conc.maxdd_since2015_not_2020).length} vol-target and VIX variants cut it below their own 2015-16 or 2018-Q4 holes`,
  fC: `the as-built max drawdown since 2015, every ratio's starting point, is ${D.conc.maxdd_since2015_episode[0]} → ${D.conc.maxdd_since2015_episode[1]} (COVID), as is every cap's (the vol-target and VIX variants cut COVID below their own 2015-16 or 2018-Q4 drawdowns), so "pp per pp" since 2015 is priced on Feb-Mar 2020 alone. Leave one year out (set flat for base and variant) and cap 37.5 reads ${lo('cap37.5', 'since2015').min[1].toFixed(2)} (no ${lo('cap37.5', 'since2015').min[0]}) to ${lo('cap37.5', 'since2015').max[1].toFixed(2)} (no ${lo('cap37.5', 'since2015').max[0]}), vt k${I.matched_k['0.6'].toFixed(2).slice(1)} ${lo('vt_m60', 'since2015').min[1].toFixed(2)} to ${lo('vt_m60', 'since2015').max[1].toFixed(2)} (no ${lo('vt_m60', 'since2015').max[0]}), VIX > 30 ${lo('vix30', 'since2015').min[1].toFixed(2)} (no ${lo('vix30', 'since2015').min[0]}) to ${lo('vix30', 'since2015').max[1].toFixed(2)} (no ${lo('vix30', 'since2015').max[0]}). "VIX gates are the cheapest drawdown since 2015" and "vol-targeting beats caps since 2015" are statements about Feb-Mar 2020: without 2020 the vol-target costs more per pp than the cap at the same mean leg weight (${lo('vt_m60', 'since2015').no2020.toFixed(2)} vs cap 60 ${lo('cap60', 'since2015').no2020.toFixed(2)}). 2022 (${sgB(byId.base.ep['2022 full year'])}) is ${pc0(D.conc.share_2022_of_log_growth_since2015)} of the 2015-26 log growth. Over 31 years the vol-target and VIX ratios divide by ${D.conc.dd_saved_full_pp.vt_m60.toFixed(1)} and ${D.conc.dd_saved_full_pp.vix30.toFixed(1)} pp of drawdown saved and are ill-conditioned (vt k${I.matched_k['0.6'].toFixed(2).slice(1)}: ${lo('vt_m60', 'full').min[1].toFixed(1)} to ${lo('vt_m60', 'full').max[1].toFixed(0)} leave-one-year-out).`,
  fD: `${pc0(I.sigma20_soxl_1104)} annualized after SOXL's ${sg(I.soxl_1030)} session on 10-30, the symphony's ${sg(I.path_1030)}`,
  fE: pc0(byId['cap37.5_1x'].legw)};
for (const k in fills) document.getElementById(k).textContent = fills[k];

const T = s => new Date(s + 'T12:00:00Z').getTime();
function crosshair(svg, X, l, r, t, b, dates, readout){
  const line = el('line', {x1: 0, x2: 0, y1: t, y2: b, stroke: 'var(--axis)', 'stroke-width': 1, style: 'display:none'}, svg);
  const hit = el('rect', {x: l, y: t, width: r - l, height: b - t, fill: 'transparent'}, svg);
  const xs = dates.map(d => X(T(d)));
  hit.addEventListener('mousemove', ev => { const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY; const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    let lo = 0, hi = xs.length - 1; while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] < p.x) lo = m; else hi = m; } const i = (p.x - xs[lo] < xs[hi] - p.x) ? lo : hi;
    line.setAttribute('x1', xs[i]); line.setAttribute('x2', xs[i]); line.style.display = ''; tip(ev, readout(i)); });
  hit.addEventListener('mouseleave', () => { line.style.display = 'none'; untip(); });
}
// A: equity, log
(function(){
  const svg = document.getElementById('chA'), W = 900, H2 = 400, l = 56, r = 200, t = 14, b = 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const S = D.paths.eq.series, ids = Object.keys(S), dates = D.paths.eq.dates, t0 = T(dates[0]), t1 = T(dates[dates.length - 1]);
  const vals = ids.flatMap(k => S[k]), lo = Math.log10(Math.min(...vals) * 0.8), hi = Math.log10(Math.max(...vals) * 1.4);
  const X = ms => l + (ms - t0) / (t1 - t0) * (W - l - r), Y = v => t + (hi - Math.log10(v)) / (hi - lo) * (H2 - t - b);
  for (let e = Math.ceil(lo); e <= hi; e++) { const v = Math.pow(10, e); el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: v === 1 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, '$' + (v >= 1e6 ? (v / 1e6) + 'M' : v >= 1e3 ? (v / 1e3) + 'K' : v)); }
  for (let y = 1995; y <= 2026; y += 5) { const x = X(T(y + '-01-01')); el('line', {x1: x, x2: x, y1: t, y2: H2 - b, stroke: 'var(--grid)'}, svg); el('text', {x, y: H2 - 10, 'text-anchor': 'middle', class: 'ax'}, svg, y); }
  const xs = dates.map(d => X(T(d)));
  ids.forEach(k => el('polyline', {points: S[k].map((v, i) => `${xs[i]},${Y(v)}`).join(' '), fill: 'none', stroke: COL[k], 'stroke-width': k === 'base' ? 2.5 : 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg));
  const lab = ['base', 'cap37.5', 'two_x', 'one_x'].map(k => ({k, v: S[k][S[k].length - 1], y: Y(S[k][S[k].length - 1])})).sort((a, c) => a.y - c.y);
  for (let i = 1; i < lab.length; i++) if (lab[i].y - lab[i - 1].y < 14) lab[i].y = lab[i - 1].y + 14;
  lab.forEach(o => { const y0 = Y(o.v); if (Math.abs(o.y - y0) > 1) el('line', {x1: W - r + 2, x2: W - r + 10, y1: y0, y2: o.y, stroke: 'var(--axis)'}, svg);
    el('circle', {cx: W - r, cy: y0, r: 4, fill: COL[o.k], stroke: 'var(--surface)', 'stroke-width': 2}, svg);
    el('text', {x: W - r + 12, y: o.y + 4, class: 'lbb'}, svg, `${SHORT[o.k]} $${o.v >= 1e6 ? (o.v / 1e6).toFixed(1) + 'M' : o.v >= 1e3 ? (o.v / 1e3).toFixed(0) + 'K' : o.v.toFixed(2)}`); });
  legend('lgA', ids.map(k => [NAME[k], COL[k], 'line']));
  crosshair(svg, X, l, W - r, t, H2 - b, dates, i => [{v: dates[i], l: ''}].concat(ids.map(k => ({c: COL[k], v: '$' + (S[k][i] >= 1e3 ? Math.round(S[k][i]).toLocaleString() : S[k][i].toFixed(2)), l: NAME[k]}))));
})();
// B: drawdowns
function ddChart(id, P, years){
  const svg = document.getElementById(id), W = 450, H2 = 260, l = 44, r = 10, t = 10, b = 26;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const S = P.series, ids = Object.keys(S), dates = P.dates, t0 = T(dates[0]), t1 = T(dates[dates.length - 1]);
  const X = ms => l + (ms - t0) / (t1 - t0) * (W - l - r), Y = v => t + (-v) / 1.0 * (H2 - t - b), xs = dates.map(d => X(T(d)));
  [0, -0.25, -0.5, -0.75, -1].forEach(v => { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: v === 0 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 5, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100) + '%'); });
  years.forEach(y => { const x = X(T(y + '-01-01')); el('text', {x, y: H2 - 8, 'text-anchor': 'middle', class: 'ax'}, svg, y); });
  ids.forEach(k => { const pts = S[k].map((v, i) => `${xs[i]},${Y(v)}`).join(' ');
    el('polygon', {points: `${X(t0)},${Y(0)} ${pts} ${X(t1)},${Y(0)}`, fill: COL[k], opacity: 0.1}, svg);
    el('polyline', {points: pts, fill: 'none', stroke: COL[k], 'stroke-width': k === 'base' ? 2.2 : 1.8, 'stroke-linejoin': 'round'}, svg); });
  crosshair(svg, X, l, W - r, t, H2 - b, dates, i => [{v: dates[i], l: ''}].concat(ids.map(k => ({c: COL[k], v: pc(S[k][i]), l: NAME[k]}))));
}
legend('lgB', Object.keys(D.paths.dd.full.series).map(k => [NAME[k], COL[k], 'line']));
ddChart('chB1', D.paths.dd.full, [1996, 2000, 2004, 2008, 2012, 2016, 2020, 2024]);
ddChart('chB2', D.paths.dd.since2015, [2016, 2018, 2020, 2022, 2024, 2026]);
// C: trade-off scatter
const FAM = {base: 'var(--ink)', cap: 'var(--s1)', vt: 'var(--s2)', other: 'var(--s3)'};
const famOf = v => v.family === 'base' ? 'base' : v.family === 'cap' ? 'cap' : v.family === 'vt' ? 'vt' : 'other';
function scatter(id, w, title){
  const svg = document.getElementById(id), W = 900, H2 = 380, l = 56, r = 16, t = 26, b = 40;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const pts = D.variants.map(v => ({v, x: v.w[w].maxdd, y: v.w[w].cagr, fam: famOf(v)}));
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const xlo = Math.floor(Math.min(...xs) * 10) / 10 - 0.05, xhi = Math.ceil(Math.max(...xs) * 10) / 10 + 0.02, ylo = 0, yhi = Math.ceil(Math.max(...ys) * 4) / 4 + 0.1;
  const X = x => l + (x - xlo) / (xhi - xlo) * (W - l - r), Y = y => t + (yhi - y) / (yhi - ylo) * (H2 - t - b);
  el('text', {x: l, y: 14, class: 'lbb'}, svg, title);
  for (let x = Math.ceil(xlo * 10) / 10; x <= xhi + 1e-9; x += 0.1) { el('line', {x1: X(x), x2: X(x), y1: t, y2: H2 - b, stroke: 'var(--grid)'}, svg); el('text', {x: X(x), y: H2 - b + 14, 'text-anchor': 'middle', class: 'ax'}, svg, Math.round(x * 100) + '%'); }
  const ystep = yhi > 1.5 ? 0.5 : 0.25;
  for (let y = 0; y <= yhi + 1e-9; y += ystep) { el('line', {x1: l, x2: W - r, y1: Y(y), y2: Y(y), stroke: y === 0 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(y) + 4, 'text-anchor': 'end', class: 'ax'}, svg, Math.round(y * 100) + '%'); }
  el('text', {x: W - r, y: H2 - 4, 'text-anchor': 'end', class: 'ax'}, svg, 'max drawdown →');
  el('text', {x: l + 4, y: t + 12, class: 'ax'}, svg, '↑ CAGR');
  ['cap', 'vt'].forEach(f => { const fp = pts.filter(p => p.fam === f || p.fam === 'base').sort((a, c) => a.v.legw - c.v.legw); el('polyline', {points: fp.map(p => `${X(p.x)},${Y(p.y)}`).join(' '), fill: 'none', stroke: FAM[f], 'stroke-width': 1.2, opacity: 0.7}, svg); });
  // labels: try a ring of candidate positions around each point, never over another point or label; a leader line when pushed away
  pts.forEach(p => { p.px = X(p.x); p.py = Y(p.y); p.txt = SHORT[p.v.id] || p.v.id; p.bp = p.v.family === 'byprod'; p.wpx = p.txt.length * (p.bp ? 5.8 : 6.3) + 4; });
  const boxes = pts.map(p => ({x0: p.px - 7, x1: p.px + 7, y0: p.py - 7, y1: p.py + 7}));
  const hits = (bx) => boxes.reduce((n, q) => n + ((bx.x0 < q.x1 && bx.x1 > q.x0 && bx.y0 < q.y1 && bx.y1 > q.y0) ? 1 : 0), 0);
  const cands = [[9, 0, 'start'], [-9, 0, 'end'], [9, -12, 'start'], [9, 12, 'start'], [-9, -12, 'end'], [-9, 12, 'end'], [0, -13, 'middle'], [0, 14, 'middle'],
    [9, -25, 'start'], [9, 25, 'start'], [-9, -25, 'end'], [-9, 25, 'end'], [12, -38, 'start'], [12, 38, 'start'], [-12, -38, 'end'], [-12, 38, 'end'], [14, -51, 'start'], [14, 51, 'start'], [-14, -51, 'end'], [-14, 51, 'end']];
  const dens = p => pts.filter(q => Math.abs(q.px - p.px) < 60 && Math.abs(q.py - p.py) < 40).length;
  pts.slice().sort((a, c) => dens(c) - dens(a)).forEach(p => {
    let best = null;
    for (const [dx, dy, anc] of cands) {
      let x0 = p.px + dx - (anc === 'end' ? p.wpx : anc === 'middle' ? p.wpx / 2 : 0);
      x0 = Math.max(l + 2, Math.min(W - r - p.wpx - 2, x0));
      const bx = {x0, x1: x0 + p.wpx, y0: p.py + dy - 6, y1: p.py + dy + 6};
      if (bx.y0 < t || bx.y1 > H2 - b) continue;
      const n = hits(bx);
      if (!best || n < best.n) best = {bx, dx, dy, n};
      if (n === 0) break;
    }
    boxes.push(best.bx);
    const ly = p.py + best.dy;
    if (Math.abs(best.dy) > 8) el('line', {x1: p.px, y1: p.py, x2: best.bx.x0 + (best.bx.x0 > p.px ? -1 : p.wpx + 1), y2: ly, stroke: 'var(--axis)'}, svg);
    el('text', {x: best.bx.x0, y: ly + 4, class: p.bp ? 'lbs' : 'lb'}, svg, p.txt);
  });
  pts.forEach(p => {
    const x = p.px, y = p.py, bp = p.bp;
    const mark = p.fam === 'base' ? el('rect', {x: x - 5, y: y - 5, width: 10, height: 10, fill: FAM.base, stroke: 'var(--surface)', 'stroke-width': 2}, svg)
      : bp ? el('path', {d: `M${x},${y - 6} L${x + 6},${y} L${x},${y + 6} L${x - 6},${y} Z`, fill: 'var(--surface)', stroke: FAM.other, 'stroke-width': 2}, svg)
      : el('circle', {cx: x, cy: y, r: 5, fill: FAM[p.fam], stroke: 'var(--surface)', 'stroke-width': 2}, svg);
    const hit = el('circle', {cx: x, cy: y, r: 12, fill: 'transparent'}, svg);
    const tr = p.v.tr[w], s = p.v.w[w];
    const rows = () => [{v: p.v.label, l: ''}, {v: pc(s.cagr), l: 'CAGR'}, {v: pc(s.maxdd), l: `max DD (${s.maxdd_peak} → ${s.maxdd_trough})`}, {v: f2(s.sharpe), l: 'Sharpe'}, {v: f2(s.calmar), l: 'Calmar'},
      {v: tr.cagr_per_dd == null ? '–' : tr.cagr_per_dd.toFixed(2) + ' pp', l: 'CAGR per pp of DD saved'},
      {v: p.v.loyo && p.v.loyo[w].min ? `${p.v.loyo[w].min[1].toFixed(2)}..${p.v.loyo[w].max[1].toFixed(2)}` : '–', l: p.v.loyo && p.v.loyo[w].min ? `leave-one-year-out range (no ${p.v.loyo[w].min[0]} .. no ${p.v.loyo[w].max[0]})` : ''},
      {v: pc(p.v.legw), l: 'mean leg weight'}, p.v.day.as_traded ? {v: sg(p.v.day.as_traded.day), l: '2026-11-05'} : {v: sg(p.v.day.close.day), l: '2026-11-05 at the closes (SOXL / TECL 37.5)'}];
    [mark, hit].forEach(h => { h.addEventListener('mousemove', e => tip(e, rows())); h.addEventListener('mouseleave', untip); });
  });
}
legend('lgC', [['as built', 'var(--ink)'], ['cap family (released weight in PULS)', 'var(--s1)'], ['vol-target family', 'var(--s2)'], ['single variants: VIX gates, 2x, 1x, single-name cap, cap → 1x', 'var(--s3)'], ['◇ by-products (section F), not sizing options', null, 'none']]);
scatter('chC1', 'full', '1995-06..2026-11-04 (synthetic before each fund\'s launch)');
scatter('chC2', 'since2015', '2015-06..2026-11-04 (the rules\' own years)');
legend('lgC3', [['1995-2026', 'var(--ctx2)'], ['2015-2026', 'var(--s1)']]);
// C3: the ratio bars
(function(){
  const svg = document.getElementById('chC3'), rows = D.variants.filter(v => v.id !== 'base'), W = 900, rowH = 22, l = 190, r = 150, t = 24, H2 = rows.length * rowH + t + 30;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const vals = rows.flatMap(v => [v.tr.full.cagr_per_dd, v.tr.since2015.cagr_per_dd]).filter(x => x != null), hi = Math.min(20, Math.max(...vals)) + 1;
  const X = v => l + Math.min(v, hi) / hi * (W - l - r);
  el('text', {x: l, y: 14, class: 'lbb'}, svg, 'CAGR given up per point of max drawdown saved (pp per pp; lower = cheaper drawdown)');
  el('text', {x: W - r + 6, y: 14, class: 'ax'}, svg, '1995-2026 · 2015-2026');
  for (let v = 0; v <= hi; v += 2) { el('line', {x1: X(v), x2: X(v), y1: t, y2: H2 - 30, stroke: v === 0 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: X(v), y: H2 - 12, 'text-anchor': 'middle', class: 'ax'}, svg, v); }
  rows.forEach((v, i) => { const y = t + i * rowH;
    el('text', {x: l - 8, y: y + 15, 'text-anchor': 'end', class: v.family === 'byprod' ? 'lbs' : 'lb'}, svg, SHORT[v.id]);
    const notes = [];
    [['full', 'var(--ctx2)', 2], ['since2015', 'var(--s1)', 10]].forEach(([w, c, dy]) => { const tr = v.tr[w], x = tr.cagr_per_dd, lab = w === 'full' ? '1995-2026' : '2015-2026';
      if (x == null) { notes.push(`no drawdown saved (${lab})`); return; }
      if (x < 0) { notes.push(`${lab}: CAGR ${sg(tr.d_cagr)} and DD −${pc(tr.dd_saved)}, both better`); return; }
      const rr = el('rect', {x: X(0), y: y + dy, width: Math.max(1, X(x) - X(0)), height: 6, rx: 2, fill: c}, svg);
      rr.addEventListener('mousemove', e => tip(e, [{v: v.label, l: ''}, {c, v: x.toFixed(2) + ' pp', l: `${lab}: ΔCAGR ${sg(tr.d_cagr)}, DD saved ${pc(tr.dd_saved)}`}])); rr.addEventListener('mouseleave', untip); });
    if (notes.length) el('text', {x: l + 4, y: y + 13, class: 'ax'}, svg, notes.join('; '));
    const a = v.tr.full.cagr_per_dd, c2 = v.tr.since2015.cagr_per_dd;
    el('text', {x: W - r + 6, y: y + 15, class: 'ax'}, svg, `${a == null ? '–' : a.toFixed(1)} · ${c2 == null ? '–' : c2.toFixed(1)}`); });
})();
// D: the 11-05 bars
(function(){
  const svg = document.getElementById('chD'), rows = D.variants, W = 900, rowH = 22, l = 190, r = 120, t = 14, H2 = rows.length * rowH + t + 50;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  const dayOf = v => v.day.as_traded ? v.day.as_traded : v.day.close, atClose = v => !v.day.as_traded;
  const vals = rows.map(v => dayOf(v).day).concat([I.composer_realized_1105, 0.02]), lo = Math.min(...vals) - 0.02, hi = Math.max(...vals) + 0.02;
  const X = v => l + (v - lo) / (hi - lo) * (W - l - r);
  for (let v = Math.ceil(lo * 20) / 20; v <= hi; v += 0.05) { el('line', {x1: X(v), x2: X(v), y1: t, y2: H2 - 30, stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: X(v), y: H2 - 12, 'text-anchor': 'middle', class: 'ax'}, svg, Math.round(v * 100) + '%'); }
  el('line', {x1: X(I.composer_realized_1105), x2: X(I.composer_realized_1105), y1: t, y2: H2 - 30, stroke: 'var(--ink2)', 'stroke-width': 1}, svg);
  el('text', {x: X(I.composer_realized_1105) + 4, y: H2 - 36, class: 'ax'}, svg, `Composer realized ${sg(I.composer_realized_1105)}`);
  rows.forEach((v, i) => { const y = t + i * rowH + 2, dd = dayOf(v), d = dd.day, x0 = X(Math.min(0, d)), w = Math.abs(X(d) - X(0)), cl = atClose(v);
    el('text', {x: l - 8, y: y + 14, 'text-anchor': 'end', class: v.id === 'base' ? 'lbb' : v.family === 'byprod' ? 'lbs' : 'lb'}, svg, SHORT[v.id]);
    const rr = el('rect', {x: x0, y: y + 2, width: Math.max(w, 1.5), height: 14, rx: 2, fill: 'var(--s1)', opacity: cl ? 0.55 : 1}, svg);
    el('text', {x: d < 0 ? x0 - 4 : x0 + w + 4, y: y + 14, 'text-anchor': d < 0 ? 'end' : 'start', class: 'ax'}, svg, sg(d) + (cl ? '*' : ''));
    el('text', {x: W - r + 6, y: y + 14, class: 'ax'}, svg, `leg ${pc0(dd.leg_weight)} ${dd.leg_instrument}${cl ? '*' : ''}`);
    rr.addEventListener('mousemove', e => tip(e, cl ? [{v: v.label, l: ''}, {v: sg(d), l: `symphony, at the 16:00 closes (leg ${pc0(dd.leg_weight)} in ${dd.leg_instrument}, the engine's own close decision; no ~15:50 TECL print on file)`},
      {v: sg(dd.book_day), l: `the book at the closes (KMLM ${pc0(I.book_1104_weights.KMLM)} of it on 11-04; realized ${sg(I.book_realized_1105)})`}]
      : [{v: v.label, l: ''}, {v: sg(d), l: `symphony, at the ~15:50 prints (leg ${pc0(dd.leg_weight)} in ${dd.leg_instrument})`}, {v: sg(v.day.close.day), l: 'at the 16:00 closes'},
      {v: sg(dd.book_day), l: `the book (KMLM ${pc0(I.book_1104_weights.KMLM)} of it on 11-04; realized ${sg(I.book_realized_1105)})`}])); rr.addEventListener('mouseleave', untip); });
})();
// E: tables
function table(id, w){
  const head = ['variant', 'leg wt', 'CAGR', 'max DD', 'Sharpe', 'Calmar', 'worst day', 'worst mo', 'TUW', 'per pp DD', 'COVID', 'Apr-25', '2022', '11-05', 'book CAGR', 'book DD'];
  const tr = document.createElement('tr'); head.forEach((h, i) => { const th = document.createElement('th'); th.textContent = h; if (i) th.className = 'n'; tr.appendChild(th); });
  const thead = document.createElement('thead'); thead.appendChild(tr); const tb = document.createElement('tbody');
  D.variants.forEach(v => { const s = v.w[w], t = v.tr[w], e = Object.values(v.ep), row = document.createElement('tr'); row.className = v.id === 'base' ? 'base' : v.family === 'byprod' ? 'bp' : '';
    const cells = [[SHORT[v.id], ''], [pc0(v.legw), 'n'], [pc(s.cagr), cls(s.cagr)], [pc(s.maxdd), 'n'], [f2(s.sharpe), 'n'], [f2(s.calmar), 'n'], [sg(s.worst_day), cls(s.worst_day)], [sg(s.worst_month), cls(s.worst_month)], [s.tuw_longest_sessions.toLocaleString(), 'n'],
      [t.cagr_per_dd == null ? (v.id === 'base' ? '' : 'none') : t.cagr_per_dd.toFixed(2), 'n'],
      [sg(e[0]), cls(e[0])], [sg(e[1]), cls(e[1])], [sg(e[2]), cls(e[2])], [sg((v.day.as_traded || v.day.close).day) + (v.day.as_traded ? '' : '*'), cls((v.day.as_traded || v.day.close).day)], [pc(v.book[w].cagr), 'n'], [pc(v.book[w].maxdd), 'n']];
    cells.forEach(([x, c], i) => { const td = document.createElement('td'); td.textContent = x; td.className = c; if (!i) td.title = v.label; if (i === 13) td.title = v.day.as_traded ? `at the ~15:50 prints; at the 16:00 closes: ${sg(v.day.close.day)}; the book: ${sg(v.day.as_traded.book_day)}` : `* at the 16:00 closes only: the edited tree holds SOXL / TECL 37.5 each (the engine's own close decision), no ~15:50 TECL print on file; the book: ${sg(v.day.close.book_day)}`; row.appendChild(td); }); tb.appendChild(row); });
  const foot = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = head.length; td.style.color = 'var(--ink2)'; td.style.whiteSpace = 'normal';
  const bn = D.bench;
  td.textContent = `${w === 'full' ? '1995-06-02..2026-11-04' : '2015-06-01..2026-11-04'}. Benchmarks over the window: SPY CAGR ${pc(bn.SPY[w].cagr)}, max DD ${pc0(bn.SPY[w].maxdd)}, Sharpe ${f2(bn.SPY[w].sharpe)}; QQQ ${pc(bn.QQQ[w].cagr)}, ${pc0(bn.QQQ[w].maxdd)}, ${f2(bn.QQQ[w].sharpe)}. Variants: cap C = every leg holding × C/75, released weight in PULS; vt k = each holding × min(1, k / (0.75 × its 20-session vol)); the VIX gates halve the leg on the prior close; 2x = USD, SSO, else 2/3 of the 3x fund; 1x = XLK, SMH, SPY, XBI, PSQ, VIXY. COVID = 2020-02-19..03-23; Apr 2025 = 04-02..04-08; 2022 = the full year (the rules' in-sample peak year: +1,112% as built). ${w === 'since2015' ? 'The as-built and every cap\'s max DD in this window is the Feb-Mar 2020 episode (the vol-target and VIX rows\' own is 2015-16 or 2018-Q4): hover a point in section C for each ratio\'s leave-one-year-out range. ' : ''}The italic row is the section-F by-product (the tree with the SOXL dip-buy removed), not a sizing option; * = its 11-05 at the 16:00 closes. Hover a variant name for its full description.`;
  foot.appendChild(td); tb.appendChild(foot);
  const tab = document.getElementById(id); tab.replaceChildren(thead, tb);
}
table('tb15', 'since2015'); table('tbFull', 'full');
// F: edge
function edgeBars(id, buckets, order, title, sub){
  const svg = document.getElementById(id), W = 450, H2 = 262, l = 46, r = 10, t = 28, b = 70, n = order.length;
  svg.setAttribute('viewBox', `0 0 ${W} ${H2}`);
  el('text', {x: l, y: 14, class: 'lbb'}, svg, title);
  const vals = order.map(k => buckets[k].mean), lo = Math.min(0, ...vals) - 0.001, hi = Math.max(...vals) * 1.25;
  const gw = (W - l - r) / n, bw = Math.min(24, gw * 0.5), Y = v => t + (hi - v) / (hi - lo) * (H2 - t - b);
  for (let v = 0; v <= hi; v += 0.0025) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: v === 0 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 5, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(2) + '%'); }
  order.forEach((k, i) => { const d = buckets[k], x = l + i * gw + (gw - bw) / 2, v = d.mean, y0 = Y(Math.max(0, v)), h = Math.abs(Y(v) - Y(0));
    const rr = el('rect', {x, y: y0, width: bw, height: Math.max(h, 1), rx: 2, fill: 'var(--s1)'}, svg);
    el('text', {x: x + bw / 2, y: y0 - 4, 'text-anchor': 'middle', class: 'ax'}, svg, sg2(v));
    el('text', {x: x + bw / 2, y: H2 - 50, 'text-anchor': 'middle', class: 'lb'}, svg, k.replace(' lowest vol', '').replace(' highest vol', ''));
    el('text', {x: x + bw / 2, y: H2 - 36, 'text-anchor': 'middle', class: 'ax'}, svg, `n ${d.n} · t ${d.t.toFixed(1)}`);
    el('text', {x: x + bw / 2, y: H2 - 22, 'text-anchor': 'middle', class: 'ax'}, svg, `${pc0(d.hit)} up · σ ${pc0(d.mean_sigma)}`);
    rr.addEventListener('mousemove', e => tip(e, [{v: k, l: ''}, {v: sg2(d.mean), l: 'mean daily leg return'}, {v: d.t.toFixed(2), l: 't'}, {v: d.n, l: 'sessions'}, {v: pc0(d.hit), l: 'positive'}, {v: d.mean_ret_per_daily_sigma.toFixed(3), l: 'mean return per unit of daily σ'}, {v: sg(d.worst), l: 'worst day'}, {v: sg(d.per_year_pct), l: 'per year contributed at 75% of the symphony'}])); rr.addEventListener('mouseleave', untip); });
  el('text', {x: l, y: H2 - 4, class: 'ax'}, svg, sub);
}
edgeBars('chF1', D.edge.sig, ['Q1 lowest vol', 'Q2', 'Q3', 'Q4 highest vol'], 'by the holdings\' realized 20-session vol, prior close', `edges ${D.edge.q_edges.map(x => pc0(x)).join(' / ')} · Q4 − Q1 gap: ${ordn(D.edge.pl_sig.percentile_of_observed)} placebo pct`);
edgeBars('chF2', D.edge.vix, ['VIX <= 20', 'VIX 20-25', 'VIX 25-30', 'VIX > 30'], 'by the prior VIX close', `> 25 vs ≤ 25 gap: ${ordn(D.edge.pl_vix.percentile_of_observed)} pct of ${D.edge.pl_vix.draws} block placebos`);
(function(){
  const tab = document.getElementById('tbF'), head = ['branch (what the leg held)', 'n', 'mean / day', 't', 'up', 'worst day', 'per yr at 75%', 'placebo p05..p95', 'pct', 'n since 2015', 'mean', 't', 'per yr'];
  const thead = document.createElement('thead'), tr = document.createElement('tr'); head.forEach((h, i) => { const th = document.createElement('th'); th.textContent = h; if (i) th.className = 'n'; tr.appendChild(th); }); thead.appendChild(tr);
  const tb = document.createElement('tbody');
  const order = Object.keys(D.edge.branch).sort((a, c) => D.edge.branch[c].n - D.edge.branch[a].n);
  order.forEach(k => { const d = D.edge.branch[k], p = d.placebo, e = D.edge.branch15[k] || {}, row = document.createElement('tr');
    [[k, ''], [d.n, 'n'], [sg2(d.mean), cls(d.mean)], [d.t.toFixed(2), 'n'], [pc0(d.hit), 'n'], [sg(d.worst), 'n neg'], [sg(d.per_year_pct), cls(d.per_year_pct)], [`${sg2(p.p05)}..${sg2(p.p95)}`, 'n'], [ordn(p.percentile_of_observed), 'n'],
     [e.n ?? '–', 'n'], [e.n ? sg2(e.mean) : '–', e.n ? cls(e.mean) : 'n'], [e.n ? e.t.toFixed(2) : '–', 'n'], [e.n ? sg(e.per_year_pct) : '–', e.n ? cls(e.per_year_pct) : 'n']]
     .forEach(([x, c]) => { const td = document.createElement('td'); td.textContent = x; td.className = c; row.appendChild(td); }); tb.appendChild(row); });
  const foot = document.createElement('tr'), td = document.createElement('td'); td.colSpan = head.length; td.style.color = 'var(--ink2)'; td.style.whiteSpace = 'normal';
  const bd = D.edge.branch['dip-buy SOXL'], bt = D.edge.branch['dip-buy TECL'], bu = D.edge.branch.UVXY, bs = D.edge.branch['dip-buy SPXL'], bs15 = D.edge.branch15['dip-buy SPXL'], bq = D.edge.branch.SQQQ;
  const pairPct = order.filter(k => k.startsWith('pair')).map(k => D.edge.branch[k].placebo.percentile_of_observed);
  const weak = [`the SPXL dip-buy t ${bs.t.toFixed(1)} (since 2015 t ${bs15.t.toFixed(1)}, n ${bs15.n})`, `SQQQ t ${bq.t.toFixed(1)} at the ${ordn(bq.placebo.percentile_of_observed)} placebo percentile`, `the pairs at the ${ordn(Math.min(...pairPct))}-${ordn(Math.max(...pairPct))}`];
  td.textContent = `All ${D.edge.leg_days} leg sessions: mean ${sg2(D.edge.leg_mean)} a day, t ${D.edge.leg_t.toFixed(1)}. "Per year at 75%" = what the branch's days compounded to per year with the leg at its live 75%. The placebo draws the branch's number of sessions as random 21-session blocks of leg days, 1,000 times: the TECL dip-buy (${sg2(bt.mean)}, t ${bt.t.toFixed(1)}) and the UVXY pops (${sg2(bu.mean)}, t ${bu.t.toFixed(1)}) sit above every draw; the SOXL dip-buy (${bd.n} sessions, ${sg2(bd.mean)}, t ${bd.t.toFixed(1)}) sits at the ${ordn(bd.placebo.percentile_of_observed)} percentile: no measured return, not a measured loss, and not alone (${weak.join('; ')}). It is the minimum of ${D.edge.worst.n_branches} branch t-stats, and the worst of ${D.edge.worst.n_branches} sits at or below the ${ordn(bd.placebo.percentile_of_observed)} percentile ${pc0(D.edge.worst.p_some_branch_at_or_below)} of the time by chance. Its ${bd.n} sessions are ${pc0(bd.eras.synthetic.n / bd.n)} synthetic (n ${bd.eras.synthetic.n}, ${sg2(bd.eras.synthetic.mean)} a day); the real era is positive (n ${bd.eras.real.n}, ${sg2(bd.eras.real.mean)}, t ${bd.eras.real.t.toFixed(1)}). The TECL comparison is not like-for-like: TECL fires on TQQQ RSI < 30 (the index oversold), SOXL only when semis are oversold and QQQ is not. What removing the branch does is simulated below.`;
  foot.appendChild(td); tb.appendChild(foot); tab.replaceChildren(thead, tb);
})();
// F: the section text and the fall-through table (counter-agent fix 1)
(function(){
  const E = D.edge, W4 = E.within, m = E.mirror, s15 = E.s15q, q = E.q4comp;
  const wt = k => W4[k] ? W4[k].welch_t_Q4_minus_Q1.toFixed(1) : '–';
  const others = Object.keys(W4).filter(k => k.startsWith('pair') && k !== 'pair SOXL+TECL').map(k => W4[k].welch_t_Q4_minus_Q1);
  document.getElementById('pF').textContent = `The leg's own daily return (its holdings at 100%) on the ${E.leg_days.toLocaleString()} sessions it is on, split by the holdings' realized 20-session vol at the prior close, by the prior VIX close, and by branch. Two by-products beyond the sizing trade-off, both checked by the counter-agent. (1) The leg earns most when its own vol is highest (${sg2(q1.mean)} → ${sg2(q4.mean)} a day, Q4 − Q1 Welch t ${E.welch.toFixed(1)}), which is why vol-scaling pays ${rng(vtRatios)} pp per point over 31 years. But within a branch, on its own vol quartiles, the gradient is weak (Q4 − Q1 Welch t: SQQQ ${wt('SQQQ')}, TECL dip-buy ${wt('dip-buy TECL')}, UVXY ${wt('UVXY')}, SOXL+TECL ${wt('pair SOXL+TECL')}, the other pairs ${Math.min(...others).toFixed(1)}-${Math.max(...others).toFixed(1)}), the same names' 1x twins show the same gradient on the same days (${sg2(m['Q1 lowest vol'].mean)} → ${sg2(m['Q4 highest vol'].mean)} a day, t ${m['Q4 highest vol'].t.toFixed(1)}), and ${pc0(q.pre_2010_share)} of the Q4 bucket's summed return is pre-2010 synthetic (2022 ${pc0(q.share_2022)}; since 2015 on its own quartiles: ${sg2(s15['Q1 lowest vol'].mean)} (t ${s15['Q1 lowest vol'].t.toFixed(1)}) → ${sg2(s15['Q4 highest vol'].mean)} (t ${s15['Q4 highest vol'].t.toFixed(1)}) still holds). Read: the engine is vol-timed by construction (pops and dip-buys fire in high vol); a book-level size-up-with-vol would be a post-shock-reversal bet, not a new conditional return. The earlier "mirror = the low buckets are the weakest" was not a mirror check; the 1x-twin test is. (2) The SOXL dip-buy branch, the one that fired into 11-05, has no measured return; its real counterfactual (the tree with the branch removed, simulated below) is better over 31 years, all of it in the synthetic era, and worse since 2015: not a candidate edge, the branch stays as built. In sample on the engine's own path; the placebo for a branch draws the same number of random 21-session blocks of leg days.`;
  const F = D.ft, ft = byId.soxl_dip_ft, dl = F.day_level, ld = F.worst_for_fall_through_since2015;
  document.getElementById('pFT').textContent = `${F.edit}, replayed by the engine's own simulator (Wilder RSI) on the same panel and sessions: identical holdings on all ${F.gate.non_branch_sessions.toLocaleString()} sessions where the dip-buy did not fire (${F.gate.mismatches} mismatches), the fall-through holdings on its ${F.branch_sessions} sessions: ${Object.entries(F.holdings).map(([k, v]) => `${k} ${v}`).join(', ')}. SOXL stays in the leg (37.5 in a pair) on only ${F.soxl_in_pair.n} of them (${pc0(F.soxl_in_pair.share)}); SQQQ or TLT on ${F.sqqq_or_tlt.n} (${pc0(F.sqqq_or_tlt.share)}). The edited tree: ${pc(ft.w.full.cagr)} CAGR / ${pc(ft.w.full.maxdd)} max DD / Sharpe ${f2(ft.w.full.sharpe)} over 1995-2026 against ${pc(B.w.full.cagr)} / ${pc(B.w.full.maxdd)} / ${f2(B.w.full.sharpe)} as built (better, all of it in the synthetic era: the hole it cuts is the ${B.w.full.maxdd_peak.slice(0, 4)}-${B.w.full.maxdd_trough.slice(2, 4)} synthetic-SOXL one, and its own worst becomes ${ft.w.full.maxdd_peak} → ${ft.w.full.maxdd_trough}), and ${pc(ft.w.since2015.cagr)} / ${pc(ft.w.since2015.maxdd)} / ${f2(ft.w.since2015.sharpe)} since 2015 against ${pc(B.w.since2015.cagr)} / ${pc(B.w.since2015.maxdd)} / ${f2(B.w.since2015.sharpe)} (worse: ${ld.slice(0, 2).map(x => `${x.date} ${sg(x.as_built)} → ${sg(x.fall_through)} holding ${x.held}`).join(', ')}; COVID ${sg(F.episodes['2020-02-19..03-23 (COVID)'].as_built)} → ${sg(F.episodes['2020-02-19..03-23 (COVID)'].fall_through)}; 2022 ${sgB(F.episodes['2022 full year'].as_built)} → ${sgB(F.episodes['2022 full year'].fall_through)}). Day-level on the branch's sessions (the 75% group's contribution, symphony-level, before costs):`;
  const tab = document.getElementById('tbFT'), head = ['sessions', 'n', 'as built (SOXL 75) / day', 't', 'fall-through / day', 't', 'PULS / day', 'difference / day', 't', '× as built', '× fall-through'];
  const thead = document.createElement('thead'), tr = document.createElement('tr'); head.forEach((h, i) => { const th = document.createElement('th'); th.textContent = h; if (i) th.className = 'n'; tr.appendChild(th); }); thead.appendChild(tr);
  const tb = document.createElement('tbody');
  Object.entries(dl).forEach(([k, d]) => { const row = document.createElement('tr');
    [[k, ''], [d.n, 'n'], [sg2(d.as_built.mean), cls(d.as_built.mean)], [f2(d.as_built.t), 'n'], [sg2(d.fall_through.mean), cls(d.fall_through.mean)], [f2(d.fall_through.t), 'n'], [sg2(d.puls.mean), 'n'],
     [sg2(d.diff.mean), cls(d.diff.mean)], [f2(d.diff.t), 'n'], ['×' + d.compounded_as_built.toFixed(3), 'n'], ['×' + d.compounded_fall_through.toFixed(3), 'n']]
     .forEach(([x, c]) => { const td = document.createElement('td'); td.textContent = x; td.className = c; row.appendChild(td); }); tb.appendChild(row); });
  const foot = document.createElement('tr'), td = document.createElement('td'); td.colSpan = head.length; td.style.color = 'var(--ink2)'; td.style.whiteSpace = 'normal';
  td.textContent = `${F.basis}. Verdict: not a candidate edge; the branch stays as built; this table is the deliverable. Any tree change still goes through the add.-40 build path (draft → fidelity gate → counter-agent → owner approval).`;
  foot.appendChild(td); tb.appendChild(foot); tab.replaceChildren(thead, tb);
})();
// basis
const basis = [
 `Path and gate: the add. 47 pipeline's KMLM run (research/longrun/book1997.py, VIX mode ${I.vix_mode}), ${I.sessions.toLocaleString()} sessions ${I.days[0]}..${I.days[1]}; the daily return was rebuilt here from the holdings earning each session × per-ticker returns (long_panel) minus the engine's own cost (${I.cost_bps_per_unit_sum_abs_dw.toFixed(3)} bps per unit of sum|Δw|, cost_fit.json, add. 38), max |diff| ${D.gate.max_abs_diff.toExponential(1)}. Variants re-size the same holdings; the vol-target reads the fund's 20-session vol at the decision close; k matched to the caps: ${Object.entries(I.matched_k).map(([c, k]) => `cap ${Math.round(c * 100)}% → k ${k.toFixed(2)}`).join(', ')}. 2x map: ${Object.entries(I.two_x_map).map(([a, b]) => `${a} → ${b}`).join(', ')}; 1x map: ${Object.entries(I.one_x_map).map(([a, b]) => `${a} → ${b}`).join(', ')}; SVIX has no twin and is unchanged in both.`,
 `The leg: 75% on ${I.leg_weight_distribution['0.75'].toLocaleString()} sessions, TLT on ${I.leg_weight_distribution['0'].toLocaleString()}; branches: ${Object.entries(I.branch_days).map(([k, v]) => `${k} ${v.toLocaleString()}`).join('; ')}. No branch holds more than 75%.`,
 `Book: HG / KMLM / SLEEVE / HARV at the 2026-11-05 dollar values (${Object.entries(I.book_dollars_2026_11_05).map(([e, v]) => `${e} $${Math.round(v / 1000)}k`).join(', ')}; weights ${Object.entries(I.book_weights).map(([e, v]) => `${e} ${pc0(v)}`).join(' / ')}), drifting, an engine above 40% reset at the next close (POLICY Op 5); the other three engines are their own add. 47 paths. The book's 11-05 session uses the 11-04 dollar weights (KMLM ${pc0(I.book_1104_weights.KMLM)}) and the other engines' realized sessions (HG ${sg(I.others_1105.HG)}, SLEEVE ${sg(I.others_1105.SLEEVE)}, HARV ${sg(I.others_1105.HARV)}); as built it reproduces Composer's ${sg(I.book_realized_1105)}.`].concat(D.honesty).concat([`Generated ${D.generated}. Research only; nothing changes live.`]);
basis.forEach(s => { const li = document.createElement('li'); li.textContent = s; document.getElementById('basis').appendChild(li); });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
