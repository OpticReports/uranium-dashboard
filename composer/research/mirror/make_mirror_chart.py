#!/usr/bin/env python3
"""Exhibit for the IBKR mirror's DRY parity measurement (composer/IBKR_MIRROR.md).
Reads results/mirror/backfill-2026-11-10.json (research/mirror/parity_study.py);
writes results/mirror-parity-2026-11-10.html (one self-contained file, no network)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")
SRC = os.path.join(RES, "mirror", "backfill-2026-11-10.json")
PAGE = os.path.join(RES, "mirror-parity-2026-11-10.html")
ENGINES = ("HG", "KMLM", "SLEEVE", "HARV")
NO_REBALANCE = ("2026-10-26", "2026-10-27", "2026-10-28")
LEG_CLASS = (("SQQQ", "inverse"), ("TLT", "bonds"), ("UVXY", "vol"), ("SVIX", "half"), ("SOXL", "long"), ("TECL", "long"))


def leg_class(w):
    """what KMLM's 75% leg is in: 3x long tech, half long + half SVIX, 3x inverse, bonds, long vol"""
    if not w:
        return None
    leg = {t: x for t, x in w.items() if t not in ("PULS", "ZVOL", "VXZ") and x > 0.05}
    if not leg:
        return None
    if "SVIX" in leg:
        return "half"
    top = max(leg, key=leg.get)
    return dict(LEG_CLASS).get(top, "other")


def bar_kind(s):
    c = s.get("cause") or ""
    if any(s["d0"] < d <= s["date"] for d in NO_REBALANCE):
        return "norebal"
    if c.startswith("different holdings") or c.startswith("the holdings split"):
        return "apart"
    if c.startswith("no ledger row"):
        return "gap"
    if c.startswith("Composer pay-date"):
        return "credit"
    return "plain"


def main(src=SRC, page=PAGE):
    r = json.load(open(src))
    C, M = r["close"], r["minute"]
    sessions = sorted({x["date"] for x in C["rows"]})
    eng = {}
    for e in ENGINES:
        rows = [x for x in C["rows"] if x["engine"] == e]
        comp = [x for x in r["composer_record"].get(e, []) if x["dav"]]
        base = next(x["date"] for x in comp if any(y["date"] == x["date"] for y in rows))
        b_idx = next(y["index_px"] for y in rows if y["date"] == base)
        b_dav = next(x["dav"] for x in comp if x["date"] == base)
        level, total = 1.0, []
        for y in rows:
            if y["date"] > base:
                level *= 1 + (y["ret"] or 0.0)
            if y["date"] >= base:
                total.append(level - 1)
        blk = C["engines"][e]
        knife = [x["date"] for x in C["disagreements"] if x["engine"] == e and x["class"] == "knife-edge"]
        eng[e] = {"base": base,
                  "mirror": [[y["date"], round(y["index_px"] / b_idx - 1, 5), round(t, 5)]
                             for y, t in zip([y for y in rows if y["date"] >= base], total)],
                  "composer": [[x["date"], round(x["dav"] / b_dav - 1, 5)] for x in comp if x["date"] >= base],
                  "bars": [{"d0": s["d0"], "d": s["date"], "n": s["n"], "v": s["diff_bps"], "k": bar_kind(s), "c": s.get("cause"),
                            "m": s["mirror"], "o": s["composer"]} for s in blk["series"]],
                  "knife": knife, "t": blk["tracking"], "tx": blk["tracking_ex_no_rebalance"], "tg": blk["tracking_gross"],
                  "tc": blk["tracking_with_pay_date_credits"], "tt": blk["tracking_total_basis"],
                  "costs": blk["costs"], "dist": {k: v for k, v in blk["distributions"].items() if k != "events"},
                  "dist_events": blk["distributions"]["events"], "dec": C["decisions"][e], "by_cause": blk["by_cause"],
                  "actions": blk["actions"], "avg_equity": blk["avg_equity"]}
    kmlm = [{"d": k["date"], "ml": k["mirror_leg"], "cl": k["composer_leg"], "mc": leg_class(k["mirror"]), "cc": leg_class(k["composer"]),
             "dist": k["dist"], "st": k["status"], "a": k["action"], "m": k["mirror"], "c": k["composer"], "gap": k["gap"]}
            for k in r["kmlm_path"]]
    cls = {(x["date"], x["engine"]): x["class"] for x in C["disagreements"]}
    for k in kmlm:
        k["cls"] = cls.get((k["d"], "KMLM"))
    mrows = [{"label": "close mode, same sessions", "decide": "close", "fill": "close", **M["close_same_sessions"]["headline"]}]
    for lab, v in M["variants"].items():
        mrows.append({"label": lab, "decide": v["decide"], "fill": v["fill"], "info": {k: v["info"][k] for k in (
            "covered", "fallbacks", "orders", "fallback_tickers", "stopped", "unavailable")}, **v["headline"],
            "overspent": v.get("overspent") if "overspent" in v else (v.get("book") or {}).get("overspent")})
    data = {"generated": r["generated"], "window": r["window"], "capital": r["capital"], "fractions": r["fractions"],
            "slip_bps": r["slip_bps"], "commission": r["commission"], "sessions": sessions, "eng": eng, "kmlm": kmlm,
            "book": {k: v for k, v in C["book"].items() if k != "series"}, "book_series": C["book"]["series"],
            "decisions": C["decisions"], "dis": C["disagreements"], "episodes": C["episodes"].get("KMLM", []),
            "minute": {"start": M["start"], "rows": mrows, "dis": M["variants"]["15:55"]["disagreements"],
                       "episodes": (M["variants"]["15:55"].get("episodes") or {}).get("KMLM", []),
                       "book": {k: v for k, v in M["variants"]["15:55"]["book"].items() if k != "series"}},
            "sens": r["sensitivity"], "edge": {"timing": r["edge"]["fill_timing"].get("summary"),
                                               "timing_rows": r["edge"]["fill_timing"].get("rows"),
                                               "knife": {e: {k: v for k, v in x.items() if k != "days"}
                                                         for e, x in r["edge"]["knife_edge_carry"].items()},
                                               "asof": r["edge"]["replay_as_of"]},
            "book_usd_k": r["composer_book_2026_11_09_usd_k"], "splits": r.get("splits_in_window"), "extra": r.get("extra") or {}}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(page, "w").write(html)
    print("wrote", page, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mirror parity measured</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--ctx:#b9b7ae;--ctx2:#8e8c84;--neg:#e34948;--band:rgba(42,120,214,.18);--band2:rgba(237,161,0,.22)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--band2:rgba(201,133,0,.28)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--band2:rgba(201,133,0,.28)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}h2{font-size:16px;margin:0 0 2px;font-weight:600}h3{font-size:13.5px;margin:0 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 12px;font-size:14px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:0 0 16px;min-width:0}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0 16px}
@media (max-width:760px){.kpis{grid-template-columns:1fr 1fr}}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px;min-width:0}
.kpi b{display:block;font-size:22px;font-weight:650}.kpi span{color:var(--ink2);font-size:13px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 8px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}.sw{display:inline-block;width:14px;height:12px;border-radius:3px}.sw.ln{height:3px;border-radius:2px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px 18px}
@media (max-width:760px){.grid2{grid-template-columns:1fr}}
.panel{min-width:0}.panel p{margin:0 0 2px;color:var(--ink2);font-size:12.5px}
svg{display:block;width:100%;height:auto;overflow:visible}.ax{fill:var(--muted);font-size:11px}.lb{fill:var(--ink2);font-size:12px}.lbb{fill:var(--ink);font-size:12px;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--grid);vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}.tablewrap{overflow-x:auto}
details{margin-top:8px;font-size:13.5px}summary{cursor:pointer;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.neg{color:var(--neg)}.dim{color:var(--ink2)}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:340px;box-shadow:0 2px 10px rgba(0,0,0,.12)}
</style>
</head>
<body>
<main>
<h1>The IBKR mirror, dry-run against Composer: same decisions, how close a return</h1>
<p class="sub-h" id="lede"></p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>A. Each engine since its first common close: Composer vs the mirror</h2>
<p class="sub-h">Cumulative return, close mode (the ledger's close-price decision, filled at the close, net of the mirror's modelled costs). Composer: its own deposit-adjusted value from the monitor snapshot after each close. Mirror: price basis (distributions left out, as Composer's symphony figure mostly does); the thin line adds the distributions the sleeve would have collected. Each panel has its own range; all are linear from 0%.</p>
<div class="legend" id="lgA"></div>
<div class="grid2" id="gA"></div>
</section>

<section class="card">
<h2>B. The daily return difference, mirror minus Composer</h2>
<p class="sub-h">Close mode, price basis, in basis points of the sleeve; every panel on the same ±200 bps scale (a bar that runs off it carries its value). A wide bar is a stretch of several sessions between two Composer snapshots, compared as one. Triangles mark the sessions the shadow ledger calls a knife-edge (the call flips inside 15:50-15:55); the shaded band is 10-26..10-28, when Composer did not rebalance and the mirror followed the logic.</p>
<div class="legend" id="lgB"></div>
<div class="grid2" id="gB"></div>
<div class="tablewrap" style="margin-top:10px"><table id="tbB"></table></div>
</section>

<section class="card">
<h2>C. KMLM's corridor path: the 75% leg, Composer vs the mirror</h2>
<p class="sub-h">KMLM rebalances only when a holding sits more than 10pp from its target, so the two books can drift apart without disagreeing on the logic. Lines: the weight of the switcher's leg (target 75%; the corridor is far outside this zoomed axis). Strips: what that leg held after each rebalance. Shaded sessions are those where the two books' holdings differ by more than 3% (half-L1).</p>
<div class="legend" id="lgC"></div>
<svg id="chC" role="img" aria-label="KMLM leveraged-leg weight over time for Composer and the mirror, with a strip of what the leg held and the sessions where they differ shaded"></svg>
<div class="tablewrap" style="margin-top:10px"><table id="tbC"></table></div>
</section>

<section class="card">
<h2>D. Every disagreement, classified</h2>
<p class="sub-h" id="subD"></p>
<div class="tablewrap"><table id="tbD1"></table></div>
<details><summary>Table: all engine-days where the holdings differ by more than 3% (close mode)</summary><div class="tablewrap"><table id="tbD"></table></div></details>
</section>

<section class="card">
<h2>E. Minute mode vs close mode on the same sessions</h2>
<p class="sub-h" id="subE"></p>
<div class="tablewrap"><table id="tbE"></table></div>
<details><summary>Table: the engine-days that differ in the 15:55 run</summary><div class="tablewrap"><table id="tbE2"></table></div></details>
</section>

<section class="card">
<h2>F. Where the difference comes from, and whether any of it is an edge</h2>
<p class="sub-h">Close mode. Each stretch between Composer snapshots is put under the first cause that applies; sums are in bps of the sleeve over the window. Then the three systematic candidates: filling at the close instead of ~15:54 (with a placebo), deciding on the close instead of ~15:54 (the session after a knife-edge), and the distributions.</p>
<div class="tablewrap"><table id="tbF"></table></div>
<div class="tablewrap" style="margin-top:12px"><table id="tbF2"></table></div>
<div class="tablewrap" style="margin-top:12px"><table id="tbF3"></table></div>
</section>

<section class="card">
<h2>G. Costs, turnover and sensitivities</h2>
<p class="sub-h">The mirror's modelled costs: IBKR tiered commission ($0.0035 a share, $0.35 minimum, 1% cap) and slippage against the mirror on every venue order. Composer's realised returns already carry its own execution costs.</p>
<div class="tablewrap"><table id="tbG"></table></div>
<div class="tablewrap" style="margin-top:12px"><table id="tbG2"></table></div>
</section>

<section class="card notes">
<h2 style="color:var(--ink)">Basis and limits</h2>
<ul id="basis"></ul>
</section>
</main>
<div class="tt" id="tt"></div>
<script>
const D = __DATA__, NS = 'http://www.w3.org/2000/svg', tt = document.getElementById('tt'), ENG = ['HG', 'KMLM', 'SLEEVE', 'HARV'];
function el(t, a, p, x){const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); if (x != null) e.textContent = x; p.appendChild(e); return e;}
function tip(ev, h){tt.innerHTML = h; tt.style.display = 'block'; tt.style.left = Math.max(8, Math.min(ev.clientX + 12, innerWidth - tt.offsetWidth - 8)) + 'px'; tt.style.top = Math.max(8, Math.min(ev.clientY + 12, innerHeight - tt.offsetHeight - 8)) + 'px';}
function untip(){tt.style.display = 'none';}
function legend(id, items){document.getElementById(id).innerHTML = items.map(([n, c, line]) => `<span><i class="sw${line ? ' ln' : ''}" style="background:${c}"></i>${n}</span>`).join('');}
const pc = (v, k = 1) => v == null ? '–' : (v * 100).toFixed(k) + '%', sg = (v, k = 1) => v == null ? '–' : (v >= 0 ? '+' : '−') + Math.abs(v * 100).toFixed(k) + '%';
const bp = (v, k = 1) => v == null ? '–' : (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(k), n0 = v => v == null ? '–' : Math.round(v).toLocaleString('en-US'), f2 = v => v == null ? '–' : v.toFixed(2);
const cls = v => v == null ? ' class="n"' : (v < 0 ? ' class="n neg"' : ' class="n"');
const usd = v => v == null ? '–' : '$' + Math.round(v).toLocaleString('en-US');
const fw = w => !w ? '–' : Object.entries(w).sort((a, b) => b[1] - a[1]).map(([t, x]) => `${t} ${Math.round(x * 100)}%`).join(', ');
const S = D.sessions, SI = Object.fromEntries(S.map((d, i) => [d, i])), B = D.book, T = B.tracking, TX = B.tracking_ex_no_rebalance;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const m55 = D.minute.rows.find(r => r.label === '15:55'), mClose = D.minute.rows[0];
function monthTicks(svg, X, y){ let last = ''; S.forEach((d, i) => { const m = d.slice(5, 7); if (m !== last && (i === 0 || d.slice(8) <= '07')) { if (i > 0) el('text', {x: X(i), y, 'text-anchor': 'middle', class: 'ax'}, svg, MON[+m - 1]); last = m; } }); }
function width(node){ return Math.max(300, Math.floor(node.getBoundingClientRect().width)); }
function niceStep(span, n){ const raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))); return [1, 2, 2.5, 5, 10].map(k => k * p).find(s => s >= raw); }

document.getElementById('lede').textContent = `The mirror would trade $${n0(D.capital)} at IBKR on the four engines' approved logic (HG 29 / KMLM 29 / SLEEVE 27 / HARV 15), through the sleeve, netting and fill code the executor will run. This is that code driven over ${D.window.sessions} sessions (${D.window.start}..${D.window.end}) on public prices, compared with what Composer actually held and earned: ${D.decisions.ALL.n} engine-days from the shadow ledger, Composer's deposit-adjusted values from the monitor's snapshots. Nothing was traded.`;
[[`${pc(D.decisions.ALL.share)} same holdings`, `${D.decisions.ALL.agree} of ${D.decisions.ALL.n} engine-days within 3% of Composer's holdings, deciding on the close. Deciding at 15:55 on minute bars: ${m55.decisions.ALL.agree} of ${m55.decisions.ALL.n} (${pc(m55.decisions.ALL.share)}) since ${D.minute.start}, against ${mClose.decisions.ALL.agree} for close mode on those sessions`],
 [`${T.sd_bps.toFixed(0)} bps a day`, `standard deviation of the book's daily return difference (mirror − Composer, ${T.n_daily} days, engines at the mirror's weights); mean ${bp(T.mean_bps)} bps, correlation ${T.corr.toFixed(3)}, beta ${T.beta.toFixed(2)}. 15:55 run: ${m55.book.sd_bps.toFixed(0)} bps over ${m55.book.n_daily} days`],
 [`${sg(TX.cum_gap, 2)} gap`, `book, cumulative, net of the mirror's costs, leaving out the stretch around 10-26..10-28 when Composer did not rebalance (mirror ${sg(TX.cum_mirror)} vs Composer ${sg(TX.cum_composer)}). With that stretch: ${sg(T.cum_gap, 2)} (${sg(T.cum_mirror)} vs ${sg(T.cum_composer)})`],
 [`${n0(B.costs.drag_bps_yr)} bps a year`, `modelled cost drag: commission ${n0(B.costs.commission_bps_yr)} + ${D.slip_bps} bps slippage ${n0(B.costs.slippage_bps_yr)}, on ${n0(B.costs.turnover_venue_x_yr)}× yearly turnover (${B.costs.orders} venue orders, ${B.costs.orders_per_session} a session; legs crossed inside the book on ${B.costs.sessions_with_a_cross} sessions)`]]
 .forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; k.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(k); });

// ---------- A: cumulative, four panels
legend('lgA', [['Composer (deposit-adjusted)', 'var(--s2)', 1], ['mirror, price basis', 'var(--s1)', 1], ['mirror with distributions', 'var(--ctx2)', 1]]);
function panelA(host, e){
  const E = D.eng[e], W = width(host), H = 230, l = 42, r = 12, t = 10, b = 24;
  host.innerHTML = `<h3>${e}</h3><p>from ${E.base}: Composer ${sg(E.t.cum_composer)}, mirror ${sg(E.t.cum_mirror)} (gap ${sg(E.t.cum_gap, 2)}); with distributions ${sg(E.mirror[E.mirror.length - 1][2])}</p>`;
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${e}: cumulative return of Composer and the mirror`}, host);
  const i0 = SI[E.base], n = S.length - 1 - i0, X = i => l + (i - i0) / n * (W - l - r);
  const all = E.mirror.flatMap(p => [p[1], p[2]]).concat(E.composer.map(p => p[1]), [0]);
  let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const Y = v => t + (hi - v) / (hi - lo) * (H - t - b), step = niceStep(hi - lo, 4);
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 5, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(step < 0.01 ? 1 : 0) + '%'); }
  monthTicks(svg, X, H - 7);
  const line = (pts, col, wd) => el('polyline', {points: pts.map(p => `${X(SI[p[0]]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' '), fill: 'none', stroke: col, 'stroke-width': wd, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
  line(E.mirror.map(p => [p[0], p[2]]), 'var(--ctx2)', 1.2); line(E.composer, 'var(--s2)', 2); line(E.mirror, 'var(--s1)', 2);
  const cm = Object.fromEntries(E.composer.map(p => [p[0], p[1]])), mm = Object.fromEntries(E.mirror.map(p => [p[0], p]));
  const cross = el('line', {y1: t, y2: H - b, stroke: 'var(--axis)', 'stroke-width': 1, visibility: 'hidden'}, svg);
  const hit = el('rect', {x: l, y: t, width: W - l - r, height: H - t - b, fill: 'transparent'}, svg);
  hit.addEventListener('mousemove', ev => { const bx = svg.getBoundingClientRect(), x = (ev.clientX - bx.left) / bx.width * W; const i = Math.max(i0, Math.min(S.length - 1, Math.round(i0 + (x - l) / (W - l - r) * n))), d = S[i], p = mm[d];
    cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.setAttribute('visibility', 'visible');
    tip(ev, `<b>${e} ${d}</b><br>mirror ${p ? sg(p[1], 2) : '–'} (with distributions ${p ? sg(p[2], 2) : '–'})<br>Composer ${cm[d] == null ? 'no snapshot that day' : sg(cm[d], 2)}`); });
  hit.addEventListener('mouseleave', () => { cross.setAttribute('visibility', 'hidden'); untip(); });
}
// ---------- B: daily difference bars, four panels on one scale
legend('lgB', [['same holdings into the day', 'var(--s1)'], ['different holdings into the day, or split at that rebalance', 'var(--s2)'], ['stretch with the no-rebalance days', 'var(--ctx2)'], ['Composer pay-date credit / ledger gap', 'var(--s4)'], ['Composer did not rebalance', 'var(--band)'], ['▼ knife-edge session', 'transparent']]);
const KCOL = {plain: 'var(--s1)', apart: 'var(--s2)', norebal: 'var(--ctx2)', credit: 'var(--s4)', gap: 'var(--s4)'};
function panelB(host, e){
  const E = D.eng[e], W = width(host), H = 190, l = 42, r = 10, t = 16, b = 22, CL = 200;
  host.innerHTML = `<h3>${e}</h3><p>${E.t.n_daily} daily differences: mean ${bp(E.t.mean_bps)} bps, sd ${E.t.sd_bps.toFixed(0)} bps, correlation ${E.t.corr.toFixed(3)}, beta ${E.t.beta.toFixed(2)}</p>`;
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${e}: daily return difference, mirror minus Composer, in basis points`}, host);
  const n = S.length, gw = (W - l - r) / n, X = i => l + (i + 0.5) * gw, Y = v => t + (CL - Math.max(-CL, Math.min(CL, v))) / (2 * CL) * (H - t - b);
  el('rect', {x: X(SI['2026-10-26']) - gw / 2, y: t, width: gw * 3, height: H - t - b, fill: 'var(--band)'}, svg);
  [-200, -100, 0, 100, 200].forEach(v => { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: v === 0 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 5, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v > 0 ? '+' : '') + v); });
  monthTicks(svg, X, H - 6);
  E.knife.forEach(d => { const x = X(SI[d]); el('path', {d: `M${x - 3.5},${t - 10} L${x + 3.5},${t - 10} L${x},${t - 4} Z`, fill: 'var(--ink2)'}, svg); });
  E.bars.forEach(s => {
    const i1 = SI[s.d], i0 = SI[s.d0] + 1, x0 = l + i0 * gw + Math.min(1, gw * 0.15), wd = Math.max(1.5, (i1 - i0 + 1) * gw - 2 * Math.min(1, gw * 0.15));
    const y0 = Y(Math.max(0, s.v)), h = Math.max(1, Math.abs(Y(s.v) - Y(0)));
    const rr = el('rect', {x: x0, y: y0, width: wd, height: h, rx: Math.min(2, wd / 2), fill: KCOL[s.k], opacity: s.n > 1 ? 0.75 : 1}, svg);
    if (Math.abs(s.v) > CL) el('text', {x: Math.min(W - r - 2, Math.max(l + 18, x0 + wd / 2)), y: s.v > 0 ? t + 11 : H - b - 4, 'text-anchor': 'middle', class: 'ax', style: 'fill:var(--ink);paint-order:stroke;stroke:var(--surface);stroke-width:3px'}, svg, bp(s.v, 0));
    const hr = el('rect', {x: x0 - 1, y: t, width: wd + 2, height: H - t - b, fill: 'transparent'}, svg);
    hr.addEventListener('mousemove', ev => tip(ev, `<b>${e} ${s.n > 1 ? s.d0 + ' → ' + s.d + ' (' + s.n + ' sessions)' : s.d}</b><br>mirror ${sg(s.m, 2)}, Composer ${sg(s.o, 2)}: ${bp(s.v)} bps<br>${s.c || ''}`)); hr.addEventListener('mouseleave', untip);
  });
}
function drawPanels(){
  [['gA', panelA], ['gB', panelB]].forEach(([id, fn]) => { const g = document.getElementById(id); if (!g.children.length) ENG.forEach(() => { const d = document.createElement('div'); d.className = 'panel'; g.appendChild(d); }); ENG.forEach((e, i) => fn(g.children[i], e)); });
}
document.getElementById('tbB').innerHTML = '<thead><tr><th>return tracking, close mode</th><th class="n">days</th><th class="n">mean bps</th><th class="n">sd bps</th><th class="n">t</th><th class="n">corr</th><th class="n">beta</th><th class="n">mirror</th><th class="n">Composer</th><th class="n">gap, net</th><th class="n">gap, before costs</th><th class="n">gap without the no-rebalance stretch</th><th class="n">… with Composer\'s pay-date credits added</th></tr></thead><tbody>' +
  ENG.map(e => { const E = D.eng[e], t = E.t; return `<tr><td>${e}</td><td class="n">${t.n_daily}</td><td${cls(t.mean_bps)}>${bp(t.mean_bps)}</td><td class="n">${t.sd_bps.toFixed(1)}</td><td class="n">${f2(t.t)}</td><td class="n">${t.corr.toFixed(3)}</td><td class="n">${t.beta.toFixed(2)}</td><td${cls(t.cum_mirror)}>${sg(t.cum_mirror)}</td><td${cls(t.cum_composer)}>${sg(t.cum_composer)}</td><td${cls(t.cum_gap)}>${sg(t.cum_gap, 2)}</td><td${cls(E.tg.cum_gap)}>${sg(E.tg.cum_gap, 2)}</td><td${cls(E.tx.cum_gap)}>${sg(E.tx.cum_gap, 2)}</td><td${cls(E.tc.cum_gap)}>${sg(E.tc.cum_gap, 2)}</td></tr>`; }).join('') +
  `<tr><td>Book, engines at the mirror's weights</td><td class="n">${T.n_daily}</td><td${cls(T.mean_bps)}>${bp(T.mean_bps)}</td><td class="n">${T.sd_bps.toFixed(1)}</td><td class="n">${f2(T.t)}</td><td class="n">${T.corr.toFixed(3)}</td><td class="n">${T.beta.toFixed(2)}</td><td${cls(T.cum_mirror)}>${sg(T.cum_mirror)}</td><td${cls(T.cum_composer)}>${sg(T.cum_composer)}</td><td${cls(T.cum_gap)}>${sg(T.cum_gap, 2)}</td><td class="n">–</td><td${cls(TX.cum_gap)}>${sg(TX.cum_gap, 2)}</td><td class="n">–</td></tr>` +
  `<tr><td colspan="13" class="dim">Worst stretches of the book: ` + T.worst.slice(0, 6).map(w => `${w.n > 1 ? w.d0.slice(5) + '→' : ''}${w.date.slice(5)} ${bp(w.diff_bps, 0)} bps (${(w.cause || '').replace(/ \([^)]*bps of the book\)/, '')})`).join('; ') + '.</td></tr></tbody>';

// ---------- C: KMLM path
const LEG = {long: ['3x long tech (SOXL, TECL)', 'var(--s1)'], half: ['half 3x long, half SVIX', 'var(--s3)'], inverse: ['3x inverse (SQQQ)', 'var(--s2)'], bonds: ['bonds (TLT)', 'var(--ctx)'], vol: ['long volatility (UVXY)', 'var(--s4)'], other: ['other', 'var(--ctx2)']};
legend('lgC', [['Composer leg weight', 'var(--s2)', 1], ['mirror leg weight', 'var(--s1)', 1], ['holdings differ', 'var(--band2)']].concat(Object.values(LEG).slice(0, 5)));
function drawC(){
  const svg = document.getElementById('chC'), W = width(svg.parentNode) - 34, H = 300, l = 46, r = 10, t = 12, pb = 190, sH = 16;
  svg.innerHTML = ''; svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const K = D.kmlm, n = S.length, gw = (W - l - r) / n, X = i => l + (i + 0.5) * gw, lo = 0.66, hi = 0.84, Y = v => t + (hi - Math.max(lo, Math.min(hi, v))) / (hi - lo) * (pb - t);
  K.forEach(k => { if (k.dist != null && k.dist > 0.03) el('rect', {x: l + SI[k.d] * gw, y: t, width: gw, height: H - 26 - t, fill: 'var(--band2)'}, svg); });
  [0.70, 0.75, 0.80].forEach(v => { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: v === 0.75 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 5, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); });
  const step = (key, col) => { let d = '', pen = false; K.forEach(k => { const v = k[key]; if (v == null) { pen = false; return; } const x0 = l + SI[k.d] * gw, y = Y(v); d += (pen ? 'L' : 'M') + x0.toFixed(1) + ',' + y.toFixed(1) + 'L' + (x0 + gw).toFixed(1) + ',' + y.toFixed(1); pen = true; }); el('path', {d, fill: 'none', stroke: col, 'stroke-width': 2, 'stroke-linejoin': 'round'}, svg); };
  step('cl', 'var(--s2)'); step('ml', 'var(--s1)');
  [['cc', 'Composer', pb + 14], ['mc', 'mirror', pb + 14 + sH + 6]].forEach(([key, name, y]) => {
    el('text', {x: l - 5, y: y + 12, 'text-anchor': 'end', class: 'ax'}, svg, name);
    K.forEach(k => { if (k[key]) el('rect', {x: l + SI[k.d] * gw + 0.5, y, width: Math.max(1, gw - 1), height: sH, rx: 1.5, fill: LEG[k[key]][1]}, svg); });
  });
  monthTicks(svg, X, H - 8);
  const hit = el('rect', {x: l, y: t, width: W - l - r, height: H - 26 - t, fill: 'transparent'}, svg);
  hit.addEventListener('mousemove', ev => { const bx = svg.getBoundingClientRect(), x = (ev.clientX - bx.left) / bx.width * W, i = Math.max(0, Math.min(n - 1, Math.floor((x - l) / gw))), k = K.find(q => q.d === S[i]); if (!k) return;
    tip(ev, `<b>KMLM ${k.d}</b><br>mirror (${k.a}${k.gap != null ? ', gap ' + (k.gap * 100).toFixed(1) + 'pp' : ''}): ${fw(k.m)}<br>Composer: ${k.c ? fw(k.c) : 'no ledger row'}${k.dist != null ? `<br>half-L1 ${(k.dist * 100).toFixed(1)}%` + (k.cls ? ` · ${k.cls}` : '') : ''}`); });
  hit.addEventListener('mouseleave', untip);
}
document.getElementById('tbC').innerHTML = '<thead><tr><th>sessions apart (close mode)</th><th class="n">sessions</th><th>how it started</th><th>classes</th><th class="n">what it cost (−) or made (+), bps of the sleeve</th><th class="n">daily returns known</th></tr></thead><tbody>' +
  D.episodes.map(x => `<tr><td>${x.start}${x.end !== x.start ? ' → ' + x.end : ''}</td><td class="n">${x.sessions}</td><td>${x.origin}</td><td>${x.classes.join(', ')}</td><td${cls(x.returns_known ? x.cost_bps : null)}>${x.returns_known ? bp(x.cost_bps) : 'inside a multi-session stretch'}</td><td class="n">${x.returns_known} of ${x.sessions}</td></tr>`).join('') +
  `<tr><td colspan="6" class="dim">Cost: the mirror's return minus Composer's on the sessions entered with different holdings. The 10-26..10-29 stretch has no daily Composer value (no snapshots 10-26..10-29); over 10-23→10-30 the KMLM mirror trailed by ${bp((D.eng.KMLM.bars.find(b => b.d === '2026-10-30') || {}).v, 0)} bps. One side rebalanced and the other did not on: ` + (D.dis.filter(x => x.engine === 'KMLM' && x.class === 'corridor-path').map(x => `${x.date} (${x.note})`).join('; ') || 'no session') + '.</td></tr></tbody>';

// ---------- D: disagreements
(function(){
  const names = {'agree': 'same holdings (within 3%)', 'knife-edge': 'knife-edge (ledger)', 'composer-no-rebalance': 'Composer no-rebalance day', 'corridor-path': 'KMLM corridor path', 'late-snapshot': 'Composer holdings read the next afternoon', 'whole-share': 'whole shares / cash reserve', 'mirror-skip': 'mirror had no decision', 'other': 'other'};
  const keys = Object.keys(names).filter(k => ENG.some(e => D.decisions[e].classes[k]));
  document.getElementById('subD').textContent = `Close mode, ${D.decisions.ALL.n} engine-days: the mirror's post-trade weights against Composer's holdings after its rebalance. ${D.decisions.ALL.n - D.decisions.ALL.agree} differ by more than 3%; none is unexplained and none is a whole-share or cash-reserve effect. (The ledger itself counts 24 knife-edges and 12 no-rebalance engine-days; on some of them the two books still hold the same.)`;
  document.getElementById('tbD1').innerHTML = '<thead><tr><th>class</th>' + ENG.map(e => `<th class="n">${e}</th>`).join('') + '<th class="n">all</th></tr></thead><tbody>' +
    keys.map(k => `<tr><td>${names[k]}</td>` + ENG.map(e => `<td class="n">${D.decisions[e].classes[k] || 0}</td>`).join('') + `<td class="n">${D.decisions.ALL.classes[k] || 0}</td></tr>`).join('') +
    '<tr><td>engine-days compared</td>' + ENG.map(e => `<td class="n">${D.decisions[e].n}</td>`).join('') + `<td class="n">${D.decisions.ALL.n}</td></tr>` +
    '<tr><td>share with the same holdings</td>' + ENG.map(e => `<td class="n">${pc(D.decisions[e].share)}</td>`).join('') + `<td class="n">${pc(D.decisions.ALL.share)}</td></tr></tbody>`;
  const row = x => `<tr><td>${x.date}</td><td>${x.engine}</td><td>${names[x.class] || x.class}</td><td class="n">${pc(x.dist)}</td><td>${fw(x.mirror)}</td><td>${fw(x.composer)}</td><td>${x.note}</td></tr>`;
  const head = '<thead><tr><th>session</th><th>engine</th><th>class</th><th class="n">half-L1</th><th>mirror holds</th><th>Composer holds</th><th>why</th></tr></thead><tbody>';
  document.getElementById('tbD').innerHTML = head + D.dis.map(row).join('') + '</tbody>';
  document.getElementById('tbE2').innerHTML = head + D.minute.dis.map(row).join('') + '</tbody>';
})();

// ---------- E: minute vs close
(function(){
  const R = D.minute.rows, lab = r => r.label === 'close mode, same sessions' ? 'decide on the close, fill at the close (close mode)' : r.fill === 'close' ? `decide ${r.decide}, fill at the close` : `decide ${r.decide}, fill a minute later`;
  document.getElementById('subE').textContent = `Sessions ${D.minute.start}..${D.window.end} (${m55.info.covered}). Minute mode decides with mirror_brain.build() on FMP's 1-minute trades up to the decision time and fills at the close of the bar that starts then, or at the day's close when the fund did not trade that minute; the book arrives from close mode, invested. The last rows fill at the official close instead (a market-on-close order, the design's plan). Tracking is the book at the mirror's weights, net of costs.`;
  document.getElementById('tbE').innerHTML = '<thead><tr><th>run</th>' + ENG.map(e => `<th class="n">${e} same</th>`).join('') + '<th class="n">all</th><th class="n">share</th><th class="n">days</th><th class="n">mean bps</th><th class="n">sd bps</th><th class="n">corr</th><th class="n">gap</th><th class="n">gap without 10-26..28</th><th class="n">orders</th><th class="n">fills at the close instead</th><th class="n">cash below zero</th></tr></thead><tbody>' +
    R.map(r => `<tr><td>${lab(r)}</td>` + ENG.map(e => `<td class="n">${r.decisions[e].agree}/${r.decisions[e].n}</td>`).join('') + `<td class="n">${r.decisions.ALL.agree}/${r.decisions.ALL.n}</td><td class="n">${pc(r.decisions.ALL.share)}</td><td class="n">${r.book.n_daily}</td><td${cls(r.book.mean_bps)}>${bp(r.book.mean_bps)}</td><td class="n">${r.book.sd_bps.toFixed(1)}</td><td class="n">${r.book.corr.toFixed(3)}</td><td${cls(r.book.cum_gap)}>${sg(r.book.cum_gap, 2)}</td><td${cls(r.book_ex.cum_gap)}>${sg(r.book_ex.cum_gap, 2)}</td><td class="n">${r.costs.orders}</td><td class="n">${r.info ? (r.fill === 'close' ? 'all' : r.info.fallbacks) : 'all'}</td><td class="n">${r.overspent ? r.overspent.length + ' sessions' : '0'}</td></tr>`).join('') +
    `<tr><td colspan="16" class="dim">15:55 run by engine (mean / sd of the daily difference in bps, cumulative gap): ` + ENG.map(e => `${e} ${bp(m55.engines[e].mean_bps)} / ${m55.engines[e].sd_bps.toFixed(0)} / ${sg(m55.engines[e].cum_gap, 2)}`).join('; ') + `. Fills that fell back to the close, by fund: ${Object.entries(m55.info.fallback_tickers).map(([t, k]) => `${t} ${k}`).join(', ') || 'none'}. "Cash below zero": sessions where a fill above the reference by more than mirror_core's 0.3% buy cushion left a sleeve's cash negative` + (m55.overspent && m55.overspent.length ? ` (15:55 run: worst ${usd(Math.min(...m55.overspent.flatMap(o => Object.values(o).filter(v => typeof v === 'number'))))})` : '') + '.</td></tr></tbody>';
})();

// ---------- F: causes and edges
(function(){
  const causes = {}; ENG.forEach(e => Object.entries(D.eng[e].by_cause).forEach(([k, v]) => { const key = k.replace(/ on [0-9, -]+$/, ''); (causes[key] = causes[key] || {})[e] = {n: ((causes[key][e] || {}).n || 0) + v.n, s: ((causes[key][e] || {}).s || 0) + v.sum_bps}; }));
  const order = Object.keys(causes).sort((a, b) => ENG.reduce((s, e) => s + Math.abs((causes[b][e] || {}).s || 0), 0) - ENG.reduce((s, e) => s + Math.abs((causes[a][e] || {}).s || 0), 0));
  document.getElementById('tbF').innerHTML = '<thead><tr><th>cause of the stretch\'s difference</th>' + ENG.map(e => `<th class="n">${e} bps (stretches)</th>`).join('') + '</tr></thead><tbody>' +
    order.map(k => `<tr><td>${k}</td>` + ENG.map(e => { const c = causes[k][e]; return c ? `<td${cls(c.s)}>${bp(c.s, 0)} (${c.n})</td>` : '<td class="n">–</td>'; }).join('') + '</tr>').join('') +
    '<tr><td>all stretches (sum of differences)</td>' + ENG.map(e => { const s = D.eng[e].bars.reduce((a, b) => a + b.v, 0); return `<td${cls(s)}>${bp(s, 0)} (${D.eng[e].bars.length})</td>`; }).join('') + '</tr></tbody>';
  const Tm = D.edge.timing, K = D.edge.knife, st = s => s && s.n ? `${bp(s.mean)} (sd ${s.sd.toFixed(0)}, t ${f2(s.t)}, n ${s.n})` : '–';
  if (Tm) document.getElementById('tbF2').innerHTML = '<thead><tr><th>candidate: fill at the close instead of ~15:54 (Composer\'s rotation engine-days, bps of the sleeve per rotation; + favours the close)</th><th class="n">actual</th><th class="n">placebo: same trades, previous session\'s last minutes</th></tr></thead><tbody>' +
    [['all rotation engine-days', Tm.all], ...ENG.map(e => [e, Tm[e]]), ['days SPY fell', Tm.spy_down_day], ['days SPY rose', Tm.spy_up_day], ['SPY moved 1% or more', Tm.spy_move_over_1pct], ['SPY moved under 1%', Tm.spy_move_under_1pct]].map(([n, s]) => `<tr><td>${n}</td><td class="n">${st(s)}</td><td class="n">${st(s.placebo)}</td></tr>`).join('') +
    `<tr><td>without the three largest</td><td class="n">${st(Tm.without_top3)}</td><td class="n dim">dropped: ${Tm.without_top3.dropped.map(x => `${x[0].slice(5)} ${x[1]} ${bp(x[2], 0)}`).join(', ')}</td></tr>` +
    `<tr><td>one observation per day (engines averaged)</td><td class="n">${st(Tm.by_day_mean)}</td><td class="n"></td></tr>` +
    (Tm.vs_realised ? `<tr><td colspan="3" class="dim">Check against the realised difference on the same engine-days (close-mode mirror before its costs − Composer): correlation ${f2(Tm.vs_realised.corr)}, realised mean ${bp(Tm.vs_realised.realised_mean_bps)} bps vs ${bp(Tm.vs_realised.timing_mean_bps)} bps from the minute prices; the rest (${st(Tm.vs_realised.residual)}) is Composer's own execution cost, its fills away from 15:54, and snapshot marks.</td></tr>` : '') + '</tbody>';
  document.getElementById('tbF3').innerHTML = '<thead><tr><th>candidate</th>' + ENG.map(e => `<th class="n">${e}</th>`).join('') + '<th class="n">all</th></tr></thead><tbody>' +
    '<tr><td>decide on the close instead of ~15:54: the session after a knife-edge, mirror − Composer, bps</td>' + ENG.map(e => `<td class="n">${st(K[e])}</td>`).join('') + `<td class="n">${st(K.all)}</td></tr>` +
    '<tr><td>distributions the mirror sleeve would have collected</td>' + ENG.map(e => `<td class="n">${usd(D.eng[e].dist.usd)} (${pc(D.eng[e].dist.pct_of_sleeve, 2)})</td>`).join('') + `<td class="n">${usd(B.distributions_usd)} (${pc(B.distributions_usd / B.avg_equity, 2)})</td></tr>` +
    '<tr><td>… of which Composer books inside the symphony on the pay date (payer held through; add. 38 pay lags)</td>' + ENG.map(e => `<td class="n">${usd(D.eng[e].dist.held_through_usd)}</td>`).join('') + `<td class="n">${usd(ENG.reduce((s, e) => s + D.eng[e].dist.held_through_usd, 0))}</td></tr>` +
    '<tr><td>… of which lands in Composer\'s ACCOUNT cash, outside the symphony\'s figure</td>' + ENG.map(e => `<td class="n">${usd(D.eng[e].dist.leaked_usd + D.eng[e].dist.ambiguous_usd)}</td>`).join('') + `<td class="n">${usd(ENG.reduce((s, e) => s + D.eng[e].dist.leaked_usd + D.eng[e].dist.ambiguous_usd, 0))}</td></tr>` +
    '<tr><td>gap on the total basis (mirror with distributions − Composer\'s symphony figure)</td>' + ENG.map(e => `<td${cls(D.eng[e].tt.cum_gap)}>${sg(D.eng[e].tt.cum_gap, 2)}</td>`).join('') + '<td class="n">–</td></tr></tbody>';
})();

// ---------- G: costs and sensitivities
(function(){
  document.getElementById('tbG').innerHTML = '<thead><tr><th>close mode, ' + D.window.sessions + ' sessions</th><th class="n">average sleeve</th><th class="n">commission</th><th class="n">slippage</th><th class="n">drag, bps a year</th><th class="n">of which commission</th><th class="n">turnover a year</th><th class="n">trades / holds / no decision</th></tr></thead><tbody>' +
    ENG.map(e => { const c = D.eng[e].costs, a = D.eng[e].actions; return `<tr><td>${e}</td><td class="n">${usd(D.eng[e].avg_equity)}</td><td class="n">${usd(c.commission)}</td><td class="n">${usd(c.slippage)}</td><td class="n">${n0(c.drag_bps_yr)}</td><td class="n">${n0(c.commission_bps_yr)}</td><td class="n">${n0(c.turnover_venue_x_yr)}×</td><td class="n">${a.trade || 0} / ${a.hold || 0} / ${a.skip || 0}</td></tr>`; }).join('') +
    `<tr><td>Book</td><td class="n">${usd(B.avg_equity)}</td><td class="n">${usd(B.costs.commission)}</td><td class="n">${usd(B.costs.slippage)}</td><td class="n">${n0(B.costs.drag_bps_yr)}</td><td class="n">${n0(B.costs.commission_bps_yr)}</td><td class="n">${n0(B.costs.turnover_venue_x_yr)}×</td><td class="n">${B.costs.orders} orders; ${B.costs.crosses} crosses (${usd(B.costs.crossed)}) on ${B.costs.sessions_with_a_cross} sessions</td></tr></tbody>`;
  const SL = D.sens.slip_bps, SD = D.sens.seed, GF = D.sens.ledger_gaps_filled_from_the_tree;
  const rowS = (n, h) => `<tr><td>${n}</td><td${cls(h.book.cum_mirror)}>${sg(h.book.cum_mirror)}</td><td${cls(h.book.cum_composer)}>${sg(h.book.cum_composer)}</td><td${cls(h.book.cum_gap)}>${sg(h.book.cum_gap, 2)}</td><td${cls(h.book_ex.cum_gap)}>${sg(h.book_ex.cum_gap, 2)}</td><td${cls(h.book.mean_bps)}>${bp(h.book.mean_bps)}</td><td class="n">${h.book.sd_bps.toFixed(1)}</td><td class="n">${n0(h.costs.drag_bps_yr)}</td><td class="n">${h.decisions.ALL.agree}/${h.decisions.ALL.n}</td></tr>`;
  const rowO = (n, v) => { const t = v.vs_composer_own_book, x = v.vs_composer_own_book_ex_no_rebalance; return `<tr><td>${n}</td><td${cls(t.cum_mirror)}>${sg(t.cum_mirror)}</td><td${cls(t.cum_composer)}>${sg(t.cum_composer)}</td><td${cls(t.cum_gap)}>${sg(t.cum_gap, 2)}</td><td${cls(x.cum_gap)}>${sg(x.cum_gap, 2)}</td><td${cls(t.mean_bps)}>${bp(t.mean_bps)}</td><td class="n">${t.sd_bps.toFixed(1)}</td><td class="n">–</td><td class="n">–</td></tr>`; };
  document.getElementById('tbG2').innerHTML = '<thead><tr><th>sensitivity (close mode, book)</th><th class="n">mirror</th><th class="n">Composer</th><th class="n">gap</th><th class="n">gap without 10-26..28</th><th class="n">mean bps a day</th><th class="n">sd</th><th class="n">cost drag, bps a year</th><th class="n">same holdings</th></tr></thead><tbody>' +
    Object.entries(SL).map(([k, h]) => rowS(`slippage ${k} bps` + (+k === D.slip_bps ? ' (base)' : ''), h)).join('') + rowS('ledger gaps decided from the approved tree instead of standing still', GF) +
    `<tr><td colspan="9" class="dim">Against Composer's OWN book (its real engine weights, ${Object.entries(SD.composer_weights).map(([e, w]) => `${e} ${Math.round(w * 100)}`).join(' / ')} on ${SD.from}, drifting to ${Object.entries(SD.composer_weights_end).map(([e, w]) => `${e} ${Math.round(w * 100)}`).join(' / ')}), from ${SD.from}:</td></tr>` +
    Object.entries(SD.runs).map(([k, v]) => rowO('seed ' + k, v)).join('') + '</tbody>';
})();

// ---------- basis
(function(){
  const A = D.edge.asof || {}, X = D.extra || {}, E55 = m55.info || {};
  [`In sample, and short: ${D.window.sessions} sessions (${D.window.start}..${D.window.end}), ${T.n_daily} daily book observations, one window that contains a −27% KMLM day (11-05) and the three sessions Composer did not rebalance. The close-mode decisions are the shadow ledger's targets, i.e. the approved trees evaluated on that day's CLOSE with today's code: no live mirror could have decided on the close and also filled at it. It measures the sleeve, netting and booking code and the cost of running it; minute mode (section E) is the realistic timing, on ${E55.covered} sessions.`,
   `Composer's daily return = deposit_adjusted_value(D) / deposit_adjusted_value(D−1) − 1 from the monitor snapshot taken after each close (16:35 or 17:35 ET; 74 of the 83 sessions have one; older snapshots are read from the git history of last-snapshot.json). Sessions without a snapshot (07-17, 07-22, 07-23, 09-11, 09-14, 10-26..10-29) are bridged as one multi-session stretch and never split into days, so 10-26..10-28 cannot be shown day by day: "without the no-rebalance stretch" removes 10-23→10-30 whole. Composer's last_percent_change was not used (it differs from the value ratio by up to 37 bps and is the wrong day on late snapshots). On sessions when neither side trades the two series still differ by a few bps a day (snapshot marks vs official closes): that is the floor of this measurement.`,
   `Deposit days: a symphony's raw value moved beyond its deposit-adjusted return on ${ENG.map(e => `${e} ${D.eng[e].t.n_spans ? (D.eng[e].bars.filter(b => /deposit/.test(b.c || '')).map(b => b.d.slice(5)).join(', ') || 'none') : 'none'}`).join('; ')}. Those days use Composer's own adjustment; they are flagged, not removed.`,
   `Modelled, not observed: every venue order fills whole, at the day's raw close (close mode) or at the close of one 1-minute bar (minute mode), ${D.slip_bps} bps against the mirror, plus IBKR's tiered commission; no partial fills, no auction imbalance, no borrow or margin, no exchange or regulatory fees, fractional cash earns nothing. A market-on-close order cannot be sized on a price known only at the close: mirror_core sizes on the reference price and a 0.3% cushion. Whole shares and the 0.3% cash reserve are as the executor will run them.`,
   `Distributions: credited on the ex-date on the shares held at the prior close (Yahoo's dividend events), not on the pay date; the price basis takes them out again for the comparison. Composer credits a distribution inside the symphony 1-5 sessions after the ex-date only if the payer is still held, otherwise it lands in account cash outside the symphony's figure (add. 38); the pay-date credits are identified from the mirror's own holdings and the observed pay lags, and a fund without an observed lag is never guessed. Either way the owner receives the cash at both brokers: the distribution rows are an accounting difference, not a return the mirror adds.`,
   `Book level: both sides' engine returns are combined at the MIRROR's sleeve weights at the start of each stretch, so the book numbers measure tracking, not allocation. Composer's own book ran different engine weights and moved capital between symphonies (HG −$64.5k on 07-21, SLEEVE +$16.9k on 07-16, HARV funded on 07-21); that comparison is the seed rows of section G, from the first session all four engines existed.`,
   `Decision agreement compares weights at the close; Composer's holdings for 08-05 and 10-29 were read during the next session and carry that session's drift. HARV has no Composer record before 07-24: its sleeve waits in cash until then. Five sessions have no shadow-ledger row; the mirror stands still on them (the gap-filled variant is in section G).`,
   `Minute mode replays mirror_brain.build() with Yahoo's history rebased to the replayed day (as a live run saw it). Left as fetched today, the replay would read a raw 15:54 price against a history already lowered by later distributions: ${A.changed ? A.changed.length : '–'} of ${A.engine_days || '–'} engine-days decide differently that way in this window. FMP 1-minute bars are trades only; a fund with no trade in the fill minute fills at the day's close (${E55.fallbacks} of ${E55.orders} orders in the 15:55 run).`,
   `Small numbers: ${D.dis.filter(x => x.class === 'knife-edge').length} knife-edge engine-days, ${D.episodes.length} KMLM stretches apart, ${D.edge.timing ? D.edge.timing.all.n : '–'} rotation engine-days on ${D.edge.timing ? D.edge.timing.by_day_mean.n : '–'} days for the fill-timing check. None of the t-statistics here survives a multiple-comparison correction; read them as sizes, not findings.`,
   `Generated ${D.generated}. Research only; nothing traded, Composer and IBKR untouched.`]
   .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
})();

function drawAll(){ drawPanels(); drawC(); }
drawAll();
let rz; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(drawAll, 120); });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main(*sys.argv[1:3])
