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
LEG_CLASS = {"SQQQ": "inverse", "TLT": "bonds", "UVXY": "vol", "SOXL": "long", "TECL": "long"}


def leg_class(w):
    """what KMLM's 75% leg is in: 3x long tech, half long + half SVIX, 3x inverse, bonds, long vol"""
    leg = {t: x for t, x in (w or {}).items() if t not in ("PULS", "ZVOL", "VXZ") and x > 0.05}
    if not leg:
        return None
    if "SVIX" in leg:
        return "half"
    return LEG_CLASS.get(max(leg, key=leg.get), "other")


def bar_kind(s):
    c = s.get("cause") or ""
    if any(s["d0"] < d <= s["date"] for d in NO_REBALANCE):
        return "norebal"
    if c.startswith("different holdings") or c.startswith("the holdings split"):
        return "apart"
    if c.startswith("no ledger row") or c.startswith("Composer pay-date"):
        return "note"
    return "plain"


def _classes(dis):
    out = {}
    for x in dis:
        out[x["class"]] = out.get(x["class"], 0) + 1
    return out


def minute_rows(blk):
    rows = [{"label": "close", "decide": "close", "fill": "close", **blk["close_same_sessions"]["headline"]}]
    for lab, v in blk["variants"].items():
        rows.append({"label": lab, "decide": v["decide"], "fill": v["fill"], "info": {k: v["info"].get(k) for k in (
            "covered", "fallbacks", "orders", "fallback_tickers", "stopped", "unavailable", "unpriced_skips", "labels")},
            "classes": _classes(v["disagreements"]), **v["headline"]})
    return rows


def main(src=SRC, page=PAGE):
    r = json.load(open(src))
    C, M, F = r["close"], r["minute"], r.get("minute_full")
    sessions = sorted({x["date"] for x in C["rows"]})
    eng = {}
    for e in ENGINES:
        rows = [x for x in C["rows"] if x["engine"] == e]
        comp = [x for x in r["composer_record"].get(e, []) if x["dav"]]
        base = next(x["date"] for x in comp if any(y["date"] == x["date"] for y in rows))
        b_idx = next(y["index_px"] for y in rows if y["date"] == base)
        b_dav = next(x["dav"] for x in comp if x["date"] == base)
        level, mirror = 1.0, []
        for y in rows:
            if y["date"] > base:
                level *= 1 + (y["ret"] or 0.0)
            if y["date"] >= base:
                mirror.append([y["date"], round(y["index_px"] / b_idx - 1, 5), round(level - 1, 5)])
        blk = C["engines"][e]
        eng[e] = {"base": base, "mirror": mirror,
                  "composer": [[x["date"], round(x["dav"] / b_dav - 1, 5)] for x in comp if x["date"] >= base],
                  "bars": [{"d0": s["d0"], "d": s["date"], "n": s["n"], "v": s["diff_bps"], "k": bar_kind(s), "c": s.get("cause"),
                            "m": s["mirror"], "o": s["composer"]} for s in blk["series"]],
                  "knife": [x["date"] for x in C["disagreements"] if x["engine"] == e and x["class"] == "knife-edge"],
                  "t": blk["tracking"], "tx": blk["tracking_ex_no_rebalance"], "tg": blk["tracking_gross"],
                  "tc": blk["tracking_with_pay_date_credits"], "tt": blk["tracking_total_basis"],
                  "costs": blk["costs"], "dist": {k: v for k, v in blk["distributions"].items() if k != "events"},
                  "flow_days": blk["flow_days"], "by_cause": blk["by_cause"], "actions": blk["actions"],
                  "avg_equity": blk["avg_equity"]}
    cls = {(x["date"], x["engine"]): x["class"] for x in C["disagreements"]}
    kmlm = [{"d": k["date"], "ml": k["mirror_leg"], "cl": k["composer_leg"], "mc": leg_class(k["mirror"]), "cc": leg_class(k["composer"]),
             "dist": k["dist"], "a": k["action"], "m": k["mirror"], "c": k["composer"], "gap": k["gap"],
             "cls": cls.get((k["date"], "KMLM"))} for k in r["kmlm_path"]]
    edge = r["edge"]
    data = {"generated": r["generated"], "window": r["window"], "capital": r["capital"], "fractions": r["fractions"],
            "slip_bps": r["slip_bps"], "sessions": sessions, "eng": eng, "kmlm": kmlm,
            "book": {k: v for k, v in C["book"].items() if k != "series"}, "decisions": C["decisions"], "dis": C["disagreements"],
            "episodes": C["episodes"].get("KMLM", []), "noise": C["headline"]["noise_floor"],
            "minute": {"start": M["start"], "rows": minute_rows(M), "dis": M["variants"]["15:55"]["disagreements"]},
            "full": {"start": F["start"], "rows": minute_rows(F), "dis": F["variants"]["15:55"]["disagreements"],
                     "episodes": (F["variants"]["15:55"].get("episodes") or {}).get("KMLM", []),
                     "late": [x for x in F["variants"]["15:45 -> close (MOC)"]["disagreements"] if x["class"] == "decision-minute"]}
            if F else None,
            "sens": r["sensitivity"], "fills": r.get("composer_fills"),
            "edge": {"timing": edge["fill_timing"].get("summary"), "timing_1555": edge["fill_timing"].get("from_1555"),
                     "knife": {e: {k: v for k, v in x.items() if k != "days"} for e, x in edge["knife_edge_carry"].items()},
                     "asof": {k: v for k, v in edge["replay_as_of"].items() if k != "changed"},
                     "asof_changed": len(edge["replay_as_of"].get("changed") or []),
                     "asof_months": sorted({x["date"][:7] for x in edge["replay_as_of"].get("changed") or []})}}
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
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}td.n{white-space:nowrap}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px;vertical-align:bottom}.tablewrap{overflow-x:auto}
td.lab,th.lab{min-width:210px}td.note{color:var(--ink2);white-space:normal}#tbE td:first-child,#tbE3 td:first-child{min-width:185px}
details{margin-top:8px;font-size:13.5px}summary{cursor:pointer;color:var(--ink2)}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.neg{color:var(--neg)}
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
<p class="sub-h">KMLM rebalances only when a holding sits more than 10pp from its target, so the two books can drift apart without disagreeing on the logic. Lines: the weight of the switcher's leg (target 75%; the corridor's edges are outside this zoomed axis). Strips: what that leg held after each session. Shaded sessions: the two books' holdings differ by more than 3% (half-L1). Close mode.</p>
<div class="legend" id="lgC"></div>
<svg id="chC" role="img" aria-label="KMLM leveraged-leg weight over time for Composer and the mirror, with a strip of what the leg held and the sessions where they differ shaded"></svg>
<div class="tablewrap" style="margin-top:10px"><table id="tbC"></table></div>
</section>

<section class="card">
<h2>D. Every disagreement, classified</h2>
<p class="sub-h" id="subD"></p>
<div class="tablewrap"><table id="tbD1"></table></div>
<details><summary>Table: the engine-days that differ, close mode</summary><div class="tablewrap"><table id="tbD"></table></div></details>
<details><summary>Table: the engine-days that differ, deciding at 15:55 (whole window)</summary><div class="tablewrap"><table id="tbD2"></table></div></details>
</section>

<section class="card">
<h2>E. Minute mode vs close mode on the same sessions</h2>
<p class="sub-h" id="subE"></p>
<div class="tablewrap"><table id="tbE"></table></div>
<p class="sub-h" id="subE3" style="margin-top:14px"></p>
<div class="tablewrap"><table id="tbE3"></table></div>
</section>

<section class="card">
<h2>F. Where the difference comes from, and whether any of it is an edge</h2>
<p class="sub-h">Close mode. Each stretch between Composer snapshots is put under the first cause that applies; sums are in bps of the sleeve over the window. Then the systematic candidates: a later fill (the close instead of 15:53, where Composer's fills cluster) with its placebo, deciding on the close (the session after a knife-edge), and the distributions.</p>
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
function legend(id, items){document.getElementById(id).innerHTML = items.map(([n, c, line]) => `<span>${c ? `<i class="sw${line ? ' ln' : ''}" style="background:${c}"></i>` : ''}${n}</span>`).join('');}
const pc = (v, k = 1) => v == null ? '–' : (v * 100).toFixed(k) + '%', sg = (v, k = 1) => v == null ? '–' : (v >= 0 ? '+' : '−') + Math.abs(v * 100).toFixed(k) + '%';
const bp = (v, k = 1) => v == null ? '–' : (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(k), n0 = v => v == null ? '–' : Math.round(v).toLocaleString('en-US'), f2 = v => v == null ? '–' : v.toFixed(2);
const cls = v => v == null ? ' class="n"' : (v < 0 ? ' class="n neg"' : ' class="n"');
const usd = v => v == null ? '–' : (v < 0 ? '−$' : '$') + Math.abs(Math.round(v)).toLocaleString('en-US');
const fw = w => !w ? '–' : Object.entries(w).sort((a, b) => b[1] - a[1]).map(([t, x]) => `${t} ${Math.round(x * 100)}%`).join(', ');
const S = D.sessions, SI = Object.fromEntries(S.map((d, i) => [d, i])), B = D.book, T = B.tracking, TX = B.tracking_ex_no_rebalance;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const R55 = D.minute.rows.find(r => r.label === '15:55'), F55 = D.full ? D.full.rows.find(r => r.label === '15:55') : null;
const NAMES = {'agree': 'same holdings (within 3%)', 'knife-edge': 'knife-edge (the ledger says so)', 'composer-no-rebalance': 'Composer no-rebalance day', 'corridor-path': 'KMLM corridor path', 'decision-minute': 'the call flipped after the mirror\'s decision minute', 'late-snapshot': 'Composer\'s holdings read the next afternoon', 'whole-share': 'whole shares / cash reserve', 'mirror-skip': 'the mirror had no decision', 'other': 'other (unexplained)'};
function monthTicks(svg, X, y, i0 = 0){ let last = S[i0].slice(5, 7); S.forEach((d, i) => { const m = d.slice(5, 7); if (i > i0 && m !== last) { el('text', {x: X(i), y, 'text-anchor': 'middle', class: 'ax'}, svg, MON[+m - 1]); last = m; } }); }
function width(node){ return Math.max(300, Math.floor(node.getBoundingClientRect().width)); }
function niceStep(span, n){ const raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))); return [1, 2, 5, 10].map(k => k * p).find(s => s >= raw); }
const worst = xs => usd(Math.min(...xs.flatMap(o => Object.values(o).filter(v => typeof v === 'number'))));

document.getElementById('lede').textContent = `The mirror would trade $${n0(D.capital)} at IBKR on the four engines' approved logic (HG 29 / KMLM 29 / SLEEVE 27 / HARV 15), through the sleeve, netting and fill code the executor runs (mirror_core, unchanged). Here that code is driven over ${D.window.sessions} sessions (${D.window.start}..${D.window.end}) on public prices and compared with what Composer actually held and earned: ${D.decisions.ALL.n} engine-days from the shadow ledger, and Composer's deposit-adjusted values from the monitor's snapshots. Two ways of deciding: on the close (the ledger's own targets; charts A-C) and at 15:55 ET on minute bars with a fill a minute later, as the executor will (section E). Nothing was traded.`;
(function(){
  const k = [], b = F55 ? F55.book : T, x = F55 ? F55.book_ex : TX, c = F55 ? F55.costs : B.costs;
  k.push([`${pc(F55 ? F55.decisions.ALL.share : D.decisions.ALL.share)} same holdings`, F55 ? `${F55.decisions.ALL.agree} of ${F55.decisions.ALL.n} engine-days within 3% of Composer's holdings when the mirror decides at 15:55; ${D.decisions.ALL.agree} (${pc(D.decisions.ALL.share)}) deciding on the close. Every difference is a knife-edge, a Composer no-rebalance day, KMLM's corridor or a late snapshot` : `${D.decisions.ALL.agree} of ${D.decisions.ALL.n} engine-days, deciding on the close`]);
  k.push([`${b.sd_bps.toFixed(0)} bps a day`, `standard deviation of the book's daily return difference deciding at 15:55 (${b.n_daily} days; mean ${bp(b.mean_bps)} bps, correlation ${b.corr.toFixed(3)}, beta ${b.beta.toFixed(2)}); ${T.sd_bps.toFixed(0)} bps deciding and filling on the close. On days neither side trades, the comparison itself moves ${D.noise.all.sd.toFixed(0)} bps per engine`]);
  k.push([`${sg(x.cum_gap, 2)} gap`, `book, cumulative, net of the mirror's costs, without the 10-23→10-30 stretch in which Composer did not rebalance for three sessions (15:55: mirror ${sg(x.cum_mirror)} vs Composer ${sg(x.cum_composer)}; close mode ${sg(TX.cum_gap, 2)}). With that stretch: ${sg(b.cum_gap, 2)} at 15:55, ${sg(T.cum_gap, 2)} on the close`]);
  k.push([`${n0(c.drag_bps_yr)} bps a year`, `modelled cost drag at 15:55: commission ${n0(c.commission_bps_yr)} + ${D.slip_bps} bps slippage ${n0(c.slippage_bps_yr)}, on ${n0(c.turnover_venue_x_yr)}× yearly turnover (${c.orders} venue orders, ${c.orders_per_session} a session; legs crossed inside the book on ${c.sessions_with_a_cross} session${c.sessions_with_a_cross === 1 ? "" : "s"}). Close mode: ${n0(B.costs.drag_bps_yr)}`]);
  k.forEach(([h, s]) => { const d = document.createElement('div'); d.className = 'kpi'; d.innerHTML = `<b>${h}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(d); });
})();

// ---------- A: cumulative, four panels
legend('lgA', [['Composer (deposit-adjusted)', 'var(--s2)', 1], ['mirror, price basis', 'var(--s1)', 1], ['mirror with distributions', 'var(--ctx2)', 1]]);
function panelA(host, e){
  const E = D.eng[e], W = width(host), H = 230, l = 44, r = 12, t = 10, b = 24;
  host.innerHTML = `<h3>${e}</h3><p>from ${E.base}: Composer ${sg(E.t.cum_composer)}, mirror ${sg(E.t.cum_mirror)} (gap ${sg(E.t.cum_gap, 2)}); with distributions ${sg(E.mirror[E.mirror.length - 1][2])}</p>`;
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${e}: cumulative return of Composer and the mirror`}, host);
  const i0 = SI[E.base], n = S.length - 1 - i0, X = i => l + (i - i0) / n * (W - l - r);
  const all = E.mirror.flatMap(p => [p[1], p[2]]).concat(E.composer.map(p => p[1]), [0]);
  let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const Y = v => t + (hi - v) / (hi - lo) * (H - t - b), step = niceStep(hi - lo, 4), dec = step < 0.0099 ? 1 : 0;
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 5, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (Math.abs(v) < 1e-9 ? 0 : v * 100).toFixed(dec) + '%'); }
  monthTicks(svg, X, H - 7, i0);
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
legend('lgB', [['same holdings into the day', 'var(--s1)'], ['different holdings into the day, or split at that rebalance', 'var(--s2)'], ['the stretch with the no-rebalance days', 'var(--ctx2)'], ['a Composer pay-date credit, or a session without a ledger row', 'var(--s4)'], ['Composer did not rebalance', 'var(--band)'], ['▼ knife-edge session', null]]);
const KCOL = {plain: 'var(--s1)', apart: 'var(--s2)', norebal: 'var(--ctx2)', note: 'var(--s4)'};
function panelB(host, e){
  const E = D.eng[e], W = width(host), H = 190, l = 42, r = 10, t = 16, b = 22, CL = 200;
  host.innerHTML = `<h3>${e}</h3><p>${E.t.n_daily} daily differences: mean ${bp(E.t.mean_bps)} bps, sd ${E.t.sd_bps.toFixed(0)} bps, correlation ${E.t.corr.toFixed(3)}, beta ${E.t.beta.toFixed(2)}</p>`;
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${e}: daily return difference, mirror minus Composer, in basis points`}, host);
  const n = S.length, gw = (W - l - r) / n, X = i => l + (i + 0.5) * gw, Y = v => t + (CL - Math.max(-CL, Math.min(CL, v))) / (2 * CL) * (H - t - b);
  el('rect', {x: X(SI['2026-10-26']) - gw / 2, y: t, width: gw * 3, height: H - t - b, fill: 'var(--band)'}, svg);
  [-200, -100, 0, 100, 200].forEach(v => { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: v === 0 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: l - 5, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v > 0 ? '+' : '') + v); });
  monthTicks(svg, X, H - 6);
  E.knife.forEach(d => { const x = X(SI[d]); el('path', {d: `M${x - 3.5},${t - 10} L${x + 3.5},${t - 10} L${x},${t - 4} Z`, fill: 'var(--ink2)'}, svg); });
  const placed = {top: [], bot: []}, labels = [];
  E.bars.forEach(s => {
    const i1 = SI[s.d], i0 = SI[s.d0] + 1, x0 = l + i0 * gw + Math.min(1, gw * 0.15), wd = Math.max(1.5, (i1 - i0 + 1) * gw - 2 * Math.min(1, gw * 0.15));
    const y0 = Y(Math.max(0, s.v)), h = Math.max(1, Math.abs(Y(s.v) - Y(0)));
    el('rect', {x: x0, y: y0, width: wd, height: h, rx: Math.min(2, wd / 2), fill: KCOL[s.k], opacity: s.n > 1 ? 0.75 : 1}, svg);
    if (Math.abs(s.v) > CL) { const side = s.v > 0 ? 'top' : 'bot', x = Math.min(W - r - 14, Math.max(l + 16, x0 + wd / 2)); let k = 0; while (placed[side].some(p => p.k === k && Math.abs(p.x - x) < 34)) k++; placed[side].push({x, k}); labels.push([x, s.v > 0 ? t + 11 + 12 * k : H - b - 4 - 12 * k, bp(s.v, 0)]); }
    const hr = el('rect', {x: x0 - 1, y: t, width: wd + 2, height: H - t - b, fill: 'transparent'}, svg);
    hr.addEventListener('mousemove', ev => tip(ev, `<b>${e} ${s.n > 1 ? s.d0 + ' → ' + s.d + ' (' + s.n + ' sessions)' : s.d}</b><br>mirror ${sg(s.m, 2)}, Composer ${sg(s.o, 2)}: ${bp(s.v)} bps<br>${s.c || ''}`)); hr.addEventListener('mouseleave', untip);
  });
  labels.forEach(([x, y, txt]) => el('text', {x, y, 'text-anchor': 'middle', class: 'ax', style: 'fill:var(--ink);paint-order:stroke;stroke:var(--surface);stroke-width:3px;pointer-events:none'}, svg, txt));
}
function drawPanels(){
  [['gA', panelA], ['gB', panelB]].forEach(([id, fn]) => { const g = document.getElementById(id); if (!g.children.length) ENG.forEach(() => { const d = document.createElement('div'); d.className = 'panel'; g.appendChild(d); }); ENG.forEach((e, i) => fn(g.children[i], e)); });
}
document.getElementById('tbB').innerHTML = '<thead><tr><th>close mode</th><th class="n">days</th><th class="n">mean, bps</th><th class="n">sd, bps</th><th class="n">t</th><th class="n">corr</th><th class="n">beta</th><th class="n">mirror</th><th class="n">Composer</th><th class="n">gap, net</th><th class="n">gap before costs</th><th class="n">gap without 10-23→10-30</th><th class="n">gap with Composer\'s pay-date credits added</th></tr></thead><tbody>' +
  ENG.map(e => { const E = D.eng[e], t = E.t; return `<tr><td>${e}</td><td class="n">${t.n_daily}</td><td${cls(t.mean_bps)}>${bp(t.mean_bps)}</td><td class="n">${t.sd_bps.toFixed(1)}</td><td class="n">${f2(t.t)}</td><td class="n">${t.corr.toFixed(3)}</td><td class="n">${t.beta.toFixed(2)}</td><td${cls(t.cum_mirror)}>${sg(t.cum_mirror)}</td><td${cls(t.cum_composer)}>${sg(t.cum_composer)}</td><td${cls(t.cum_gap)}>${sg(t.cum_gap, 2)}</td><td${cls(E.tg.cum_gap)}>${sg(E.tg.cum_gap, 2)}</td><td${cls(E.tx.cum_gap)}>${sg(E.tx.cum_gap, 2)}</td><td${cls(E.tc.cum_gap)}>${sg(E.tc.cum_gap, 2)}</td></tr>`; }).join('') +
  `<tr><td>Book</td><td class="n">${T.n_daily}</td><td${cls(T.mean_bps)}>${bp(T.mean_bps)}</td><td class="n">${T.sd_bps.toFixed(1)}</td><td class="n">${f2(T.t)}</td><td class="n">${T.corr.toFixed(3)}</td><td class="n">${T.beta.toFixed(2)}</td><td${cls(T.cum_mirror)}>${sg(T.cum_mirror)}</td><td${cls(T.cum_composer)}>${sg(T.cum_composer)}</td><td${cls(T.cum_gap)}>${sg(T.cum_gap, 2)}</td><td${cls(B.tracking_gross.cum_gap)}>${sg(B.tracking_gross.cum_gap, 2)}</td><td${cls(TX.cum_gap)}>${sg(TX.cum_gap, 2)}</td><td class="n">–</td></tr>` +
  `<tr><td colspan="13" class="note">Book: both sides' engine returns at the mirror's sleeve weights. Worst stretches of the book: ` + T.worst.slice(0, 6).map(w => `${w.n > 1 ? w.d0.slice(5) + '→' : ''}${w.date.slice(5)} ${bp(w.diff_bps, 0)} bps (${(w.cause || '').replace(/ \([^)]*bps of the book\)/, '')})`).join('; ') + '.</td></tr></tbody>';

// ---------- C: KMLM path
const LEG = {long: ['3x long tech (SOXL, TECL)', 'var(--s1)'], half: ['half 3x long, half SVIX', 'var(--s3)'], inverse: ['3x inverse (SQQQ)', 'var(--s2)'], bonds: ['bonds (TLT)', 'var(--ctx)'], vol: ['long volatility (UVXY)', 'var(--s4)'], other: ['other', 'var(--ctx2)']};
legend('lgC', [['Composer leg weight', 'var(--s2)', 1], ['mirror leg weight', 'var(--s1)', 1], ['holdings differ', 'var(--band2)']].concat(Object.values(LEG).slice(0, 5)));
function drawC(){
  const svg = document.getElementById('chC'), W = width(svg.parentNode) - 34, H = 300, l = 58, r = 10, t = 12, pb = 190, sH = 16;
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
    tip(ev, `<b>KMLM ${k.d}</b><br>mirror (${k.a}${k.gap != null ? ', gap ' + (k.gap * 100).toFixed(1) + 'pp' : ''}): ${fw(k.m)}<br>Composer: ${k.c ? fw(k.c) : 'no ledger row'}${k.dist != null ? `<br>half-L1 ${(k.dist * 100).toFixed(1)}%` + (k.cls ? ` · ${NAMES[k.cls] || k.cls}` : '') : ''}`); });
  hit.addEventListener('mouseleave', untip);
}
(function(){
  const row = x => `<tr><td>${x.start}${x.end !== x.start ? ' → ' + x.end : ''}</td><td class="n">${x.sessions}</td><td>${NAMES[x.origin] || x.origin}</td><td${cls(x.returns_known ? x.cost_bps : null)}>${x.returns_known ? bp(x.cost_bps) : 'inside a multi-session stretch'}</td><td class="n">${x.returns_known} of ${x.sessions}</td></tr>`;
  const sum = xs => xs.filter(x => x.returns_known).reduce((s, x) => s + x.cost_bps, 0), big = (D.eng.KMLM.bars.find(b => b.d === '2026-10-30') || {}).v;
  document.getElementById('tbC').innerHTML = '<thead><tr><th>KMLM sessions apart, close mode</th><th class="n">sessions</th><th>how it started</th><th class="n">cost (−) or gain (+), bps of the sleeve</th><th class="n">daily returns known</th></tr></thead><tbody>' + D.episodes.map(row).join('') +
    `<tr><td colspan="5" class="note">Cost: the mirror's return minus Composer's on the sessions entered with different holdings; the known ones sum to ${bp(sum(D.episodes), 0)} bps. The 10-26..10-29 stretch has no daily Composer value; over 10-23→10-30 the KMLM mirror trailed by ${bp(big, 0)} bps (Composer stayed in its 10-23 holdings and that paid). One side rebalanced and the other did not on: ` + (D.dis.filter(x => x.engine === 'KMLM' && x.class === 'corridor-path').map(x => `${x.date.slice(5)} (${x.note})`).join('; ') || 'no session') + '.' +
    (D.full ? ` Deciding at 15:55 instead, KMLM is apart on ${D.full.episodes.length} stretches: ` + D.full.episodes.map(x => `${x.start.slice(5)}${x.end !== x.start ? '→' + x.end.slice(5) : ''} (${NAMES[x.origin] || x.origin}${x.returns_known ? ', ' + bp(x.cost_bps, 0) + ' bps' : ''})`).join('; ') + `; ${F55.classes['corridor-path'] || 0} corridor-path sessions.` : '') + '</td></tr></tbody>';
})();

// ---------- D: disagreements
(function(){
  const keys = Object.keys(NAMES).filter(k => D.decisions.ALL.classes[k] || (F55 && F55.classes[k])), LS = D.window.ledger_status || {};
  document.getElementById('subD').textContent = `The mirror's post-trade weights against Composer's holdings after its rebalance, ${D.decisions.ALL.n} engine-days. Close mode: ${D.decisions.ALL.n - D.decisions.ALL.agree} differ by more than 3%; ${D.decisions.ALL.classes.other || 0} are unexplained and ${D.decisions.ALL.classes['whole-share'] || 0} come from whole shares or the cash reserve. (The ledger itself has ${LS['knife-edge'] || 0} knife-edge and ${LS['no-rebalance'] || 0} no-rebalance engine-days; on some of them the two books still hold the same.)` + (F55 ? ` Deciding at 15:55, ${F55.decisions.ALL.n - F55.decisions.ALL.agree} differ: most of the ledger's knife-edges disappear, and ${F55.classes['decision-minute'] || 0} new ones appear where the call flipped after 15:55.` : '');
  document.getElementById('tbD1').innerHTML = '<thead><tr><th>class</th>' + ENG.map(e => `<th class="n">${e}</th>`).join('') + '<th class="n">all, close mode</th>' + (F55 ? '<th class="n">all, deciding at 15:55</th>' : '') + '</tr></thead><tbody>' +
    keys.map(k => `<tr><td>${NAMES[k]}</td>` + ENG.map(e => `<td class="n">${D.decisions[e].classes[k] || 0}</td>`).join('') + `<td class="n">${D.decisions.ALL.classes[k] || 0}</td>` + (F55 ? `<td class="n">${k === 'agree' ? F55.decisions.ALL.agree : (F55.classes[k] || 0)}</td>` : '') + '</tr>').join('') +
    '<tr><td>engine-days compared</td>' + ENG.map(e => `<td class="n">${D.decisions[e].n}</td>`).join('') + `<td class="n">${D.decisions.ALL.n}</td>` + (F55 ? `<td class="n">${F55.decisions.ALL.n}</td>` : '') + '</tr>' +
    '<tr><td>share with the same holdings</td>' + ENG.map(e => `<td class="n">${pc(D.decisions[e].share)}</td>`).join('') + `<td class="n">${pc(D.decisions.ALL.share)}</td>` + (F55 ? `<td class="n">${pc(F55.decisions.ALL.share)}</td>` : '') + '</tr></tbody>';
  const row = x => `<tr><td>${x.date}</td><td>${x.engine}</td><td>${NAMES[x.class] || x.class}</td><td class="n">${pc(x.dist)}</td><td>${fw(x.mirror)}</td><td>${fw(x.composer)}</td><td>${x.note}</td></tr>`;
  const head = '<thead><tr><th>session</th><th>engine</th><th>class</th><th class="n">half-L1</th><th>mirror holds</th><th>Composer holds</th><th>why</th></tr></thead><tbody>';
  document.getElementById('tbD').innerHTML = head + D.dis.map(row).join('') + '</tbody>';
  document.getElementById('tbD2').innerHTML = head + (D.full ? D.full.dis : D.minute.dis).map(row).join('') + '</tbody>';
})();

// ---------- E: minute vs close
(function(){
  const lab = r => r.label === 'close' ? 'on the close, filled at the close (close mode)' : r.fill === 'close' ? `${r.decide}, filled at the close` : `${r.decide}, filled a minute later`;
  const head = '<thead><tr><th>decided</th><th class="n">same holdings</th><th class="n">share</th><th class="n">HG · KMLM · SLEEVE · HARV</th><th class="n">days</th><th class="n">mean, bps</th><th class="n">sd, bps</th><th class="n">corr</th><th class="n">gap</th><th class="n">gap without 10-23→10-30</th><th class="n">orders filled at the close instead</th><th class="n">sessions with cash below zero (worst)</th></tr></thead><tbody>';
  const over = r => r.overspent && r.overspent.length ? `${r.overspent.length} (${worst(r.overspent)})` : '0';
  const row = r => `<tr><td>${lab(r)}</td><td class="n">${r.decisions.ALL.agree}/${r.decisions.ALL.n}</td><td class="n">${pc(r.decisions.ALL.share)}</td><td class="n">${ENG.map(e => r.decisions[e].agree).join(' · ')}</td><td class="n">${r.book.n_daily}</td><td${cls(r.book.mean_bps)}>${bp(r.book.mean_bps)}</td><td class="n">${r.book.sd_bps.toFixed(1)}</td><td class="n">${r.book.corr.toFixed(3)}</td><td${cls(r.book.cum_gap)}>${sg(r.book.cum_gap, 2)}</td><td${cls(r.book_ex.cum_gap)}>${sg(r.book_ex.cum_gap, 2)}</td><td class="n">${r.info ? (r.fill === 'close' ? 'all' : `${r.info.fallbacks} of ${r.info.orders}`) : 'all'}</td><td class="n">${over(r)}</td></tr>`;
  const foot = x => `<tr><td colspan="12" class="note">Deciding at 15:55, by engine (mean / sd of the daily difference in bps, t, cumulative gap): ` + ENG.map(e => `${e} ${bp(x.engines[e].mean_bps)} / ${x.engines[e].sd_bps.toFixed(0)} / ${f2(x.engines[e].t)} / ${sg(x.engines[e].cum_gap, 2)}`).join('; ') + `. Orders that fell back to the close, by fund: ${Object.entries(x.info.fallback_tickers).map(([t, k]) => `${t} ${k}`).join(', ') || 'none'}. Cash below zero: the fill was above the sizing reference by more than mirror_core's 0.3% buy cushion, so the sleeve spent cash it did not have.</td></tr>`;
  document.getElementById('subE').textContent = `Sessions ${D.minute.start}..${D.window.end} (${R55.info.covered}); the book arrives from close mode, invested. Minute mode decides with mirror_brain.build() on FMP's 1-minute trades up to the decision time (15:55 reads the bar that starts 15:54: the executor's decision instant) and fills at the close of the bar that starts then, or at the day's close when the fund did not trade that minute. The last rows fill at the official close instead (a market-on-close order; deciding near 15:45 and filling at the close was the first draft of the design, since replaced by the 15:54 bar and market orders). Tracking is the book at the mirror's weights, net of costs.`;
  document.getElementById('tbE').innerHTML = head + D.minute.rows.map(row).join('') + foot(R55) + '</tbody>';
  if (D.full) {
    const r45 = D.full.rows.find(r => r.label === '15:45');
    document.getElementById('subE3').textContent = `The same over the whole window (${D.full.start}..${D.window.end}, ${F55.info.covered} sessions, the book seeded in cash on the first): three times the engine-days, same construction. HARV has no approved tree before 07-22, so the brain gives it no decision on the first ${F55.info.unavailable.length} sessions.`;
    document.getElementById('tbE3').innerHTML = head + D.full.rows.map(row).join('') + foot(F55) +
      `<tr><td colspan="12" class="note">Why the 15:45 runs trail: mostly one session. Their worst stretches: ` + (r45.book_worst || []).slice(0, 3).map(w => `${w.n > 1 ? w.d0.slice(5) + '→' : ''}${w.date.slice(5)} ${bp(w.diff_bps, 0)} bps of the book (${(w.cause || '').replace(/ \([^)]*bps of the book\)/, '')})`).join('; ') + `. On 10-30 the tree read TECL at 15:45 and SQQQ by 15:54, as Composer did; the 15:55 run's worst after the no-rebalance stretch is ${(F55.book_worst || []).slice(1, 2).map(w => `${w.date.slice(5)} ${bp(w.diff_bps, 0)} bps`).join('')}.</td></tr></tbody>`;
  }
})();

// ---------- F: causes and edges
(function(){
  const causes = {}; ENG.forEach(e => Object.entries(D.eng[e].by_cause).forEach(([k, v]) => { const key = k.replace(/ on [0-9, -]+$/, ''); const c = (causes[key] = causes[key] || {}); c[e] = {n: ((c[e] || {}).n || 0) + v.n, s: ((c[e] || {}).s || 0) + v.sum_bps}; }));
  const tot = k => ENG.reduce((s, e) => s + Math.abs((causes[k][e] || {}).s || 0), 0), order = Object.keys(causes).sort((a, b) => tot(b) - tot(a));
  document.getElementById('tbF').innerHTML = '<thead><tr><th class="lab">cause of the stretch\'s difference (bps of the sleeve, summed; stretches)</th>' + ENG.map(e => `<th class="n">${e}</th>`).join('') + '</tr></thead><tbody>' +
    order.map(k => `<tr><td class="lab">${k}</td>` + ENG.map(e => { const c = causes[k][e]; return c ? `<td${cls(c.s)}>${bp(c.s, 0)} (${c.n})</td>` : '<td class="n">–</td>'; }).join('') + '</tr>').join('') +
    '<tr><td class="lab">all stretches</td>' + ENG.map(e => { const s = D.eng[e].bars.reduce((a, b) => a + b.v, 0); return `<td${cls(s)}>${bp(s, 0)} (${D.eng[e].bars.length})</td>`; }).join('') + '</tr>' +
    '<tr><td class="lab">of which the mirror\'s modelled costs</td>' + ENG.map(e => { const c = -(D.eng[e].costs.commission + D.eng[e].costs.slippage) / D.eng[e].avg_equity * 1e4; return `<td${cls(c)}>${bp(c, 0)}</td>`; }).join('') + '</tr></tbody>';
  const Tm = D.edge.timing, K = D.edge.knife, st = s => s && s.n ? `${bp(s.mean)} (t ${f2(s.t)}, n ${s.n})` : '–', FL = D.fills;
  if (Tm) document.getElementById('tbF2').innerHTML = '<thead><tr><th class="lab">candidate: a fill at the close instead of at 15:53 (Composer\'s rotation engine-days; bps of the sleeve per rotation; + favours the close)</th><th class="n">actual</th><th class="n">placebo: the same trades on the previous session\'s last minutes</th></tr></thead><tbody>' +
    [['all rotation engine-days', Tm.all], ...ENG.map(e => [e, Tm[e]]), ['days SPY fell', Tm.spy_down_day], ['days SPY rose', Tm.spy_up_day], ['SPY moved 1% or more', Tm.spy_move_over_1pct], ['SPY moved under 1%', Tm.spy_move_under_1pct]].map(([n, s]) => `<tr><td class="lab">${n}</td><td class="n">${st(s)}</td><td class="n">${st(s.placebo)}</td></tr>`).join('') +
    `<tr><td class="lab">without the three largest (${Tm.without_top3.dropped.map(x => `${x[0].slice(5)} ${x[1]} ${bp(x[2], 0)}`).join(', ')})</td><td class="n">${st(Tm.without_top3)}</td><td class="n"></td></tr>` +
    `<tr><td class="lab">one observation per day (engines averaged)</td><td class="n">${st(Tm.by_day_mean)}</td><td class="n"></td></tr>` +
    (D.edge.timing_1555 ? `<tr><td class="lab">measured from 15:55 instead (the last five minutes only)</td><td class="n">${st(D.edge.timing_1555.all)}</td><td class="n">${st(D.edge.timing_1555.all.placebo)}</td></tr>` : '') +
    `<tr><td colspan="3" class="note">` + (FL ? `Composer's own fills, ${FL.from}..${FL.to}: ${Object.entries(FL.by_minute).map(([m, k]) => `${m} ${k}`).join(', ')} (results/slippage-ledger.json). ` : '') + (Tm.vs_realised ? `Check against the realised difference on the same engine-days (close-mode mirror before its costs − Composer): correlation ${f2(Tm.vs_realised.corr)}, realised mean ${bp(Tm.vs_realised.realised_mean_bps)} bps vs ${bp(Tm.vs_realised.timing_mean_bps)} bps from the minute prices. ` : '') + `Read: the sign favours the later fill for HG and HARV, but HG's placebo is as large with the opposite sign, the pooled t is ${f2(Tm.all.t)}, and one observation per day gives t ${f2(Tm.by_day_mean.t)}. A candidate, not an edge.</td></tr></tbody>`;
  document.getElementById('tbF3').innerHTML = '<thead><tr><th class="lab">other candidates</th>' + ENG.map(e => `<th class="n">${e}</th>`).join('') + '<th class="n">all</th></tr></thead><tbody>' +
    '<tr><td class="lab">deciding on the close instead of in Composer\'s minutes: the session after a knife-edge, mirror − Composer, bps</td>' + ENG.map(e => `<td class="n">${st(K[e])}</td>`).join('') + `<td class="n">${st(K.all)}</td></tr>` +
    '<tr><td class="lab">no trade on either side: the comparison\'s own noise, bps a day (mean ± sd, days)</td>' + [...ENG, 'all'].map(e => { const s = D.noise[e]; return `<td class="n">${s.n ? bp(s.mean) + ' ± ' + s.sd.toFixed(1) + ' (' + s.n + ')' : '–'}</td>`; }).join('') + '</tr>' +
    '<tr><td class="lab">distributions the mirror sleeve would have collected (share of the average sleeve)</td>' + ENG.map(e => `<td class="n">${usd(D.eng[e].dist.usd)} (${pc(D.eng[e].dist.pct_of_sleeve, 2)})</td>`).join('') + `<td class="n">${usd(B.distributions_usd)} (${pc(B.distributions_usd / B.avg_equity, 2)})</td></tr>` +
    '<tr><td class="lab">… that Composer books inside the symphony on the pay date (payer still held; add. 38 pay lags)</td>' + ENG.map(e => `<td class="n">${usd(D.eng[e].dist.held_through_usd)}</td>`).join('') + `<td class="n">${usd(ENG.reduce((s, e) => s + D.eng[e].dist.held_through_usd, 0))}</td></tr>` +
    '<tr><td class="lab">… that lands in Composer\'s ACCOUNT cash, outside the symphony\'s figure</td>' + ENG.map(e => `<td class="n">${usd(D.eng[e].dist.leaked_usd + D.eng[e].dist.ambiguous_usd)}</td>`).join('') + `<td class="n">${usd(ENG.reduce((s, e) => s + D.eng[e].dist.leaked_usd + D.eng[e].dist.ambiguous_usd, 0))}</td></tr>` +
    '<tr><td class="lab">gap on the total basis (mirror with distributions − Composer\'s symphony figure)</td>' + ENG.map(e => `<td${cls(D.eng[e].tt.cum_gap)}>${sg(D.eng[e].tt.cum_gap, 2)}</td>`).join('') + '<td class="n">–</td></tr></tbody>';
})();

// ---------- G: costs and sensitivities
(function(){
  document.getElementById('tbG').innerHTML = '<thead><tr><th>close mode, ' + D.window.sessions + ' sessions</th><th class="n">average sleeve</th><th class="n">commission</th><th class="n">slippage</th><th class="n">drag, bps a year</th><th class="n">of which commission</th><th class="n">turnover a year</th><th class="n">trades / holds / no decision</th></tr></thead><tbody>' +
    ENG.map(e => { const c = D.eng[e].costs, a = D.eng[e].actions; return `<tr><td>${e}</td><td class="n">${usd(D.eng[e].avg_equity)}</td><td class="n">${usd(c.commission)}</td><td class="n">${usd(c.slippage)}</td><td class="n">${n0(c.drag_bps_yr)}</td><td class="n">${n0(c.commission_bps_yr)}</td><td class="n">${n0(c.turnover_venue_x_yr)}×</td><td class="n">${a.trade || 0} / ${a.hold || 0} / ${a.skip || 0}</td></tr>`; }).join('') +
    `<tr><td>Book</td><td class="n">${usd(B.avg_equity)}</td><td class="n">${usd(B.costs.commission)}</td><td class="n">${usd(B.costs.slippage)}</td><td class="n">${n0(B.costs.drag_bps_yr)}</td><td class="n">${n0(B.costs.commission_bps_yr)}</td><td class="n">${n0(B.costs.turnover_venue_x_yr)}×</td><td class="n">–</td></tr>` +
    `<tr><td colspan="8" class="note">${B.costs.orders} venue orders (${B.costs.orders_per_session} a session); opposite legs crossed inside the book on ${B.costs.sessions_with_a_cross} sessions (${usd(B.costs.crossed)} of ${usd(B.costs.traded + B.costs.crossed)} traded). The commission is per share, so the cheap funds carry it: ZVOL near $7 pays about 5 bps a side, which is why HARV's commission alone is ${n0(D.eng.HARV.costs.commission_bps_yr)} bps a year.</td></tr></tbody>`;
  const SL = D.sens.slip_bps, SD = D.sens.seed, GF = D.sens.ledger_gaps_filled_from_the_tree;
  const rowS = (n, h) => `<tr><td class="lab">${n}</td><td${cls(h.book.cum_mirror)}>${sg(h.book.cum_mirror)}</td><td${cls(h.book.cum_composer)}>${sg(h.book.cum_composer)}</td><td${cls(h.book.cum_gap)}>${sg(h.book.cum_gap, 2)}</td><td${cls(h.book_ex.cum_gap)}>${sg(h.book_ex.cum_gap, 2)}</td><td${cls(h.book.mean_bps)}>${bp(h.book.mean_bps)}</td><td class="n">${h.book.sd_bps.toFixed(1)}</td><td class="n">${n0(h.costs.drag_bps_yr)}</td><td class="n">${h.decisions.ALL.agree}/${h.decisions.ALL.n}</td></tr>`;
  const rowO = (n, v) => { const t = v.vs_composer_own_book, x = v.vs_composer_own_book_ex_no_rebalance; return `<tr><td class="lab">${n}</td><td${cls(t.cum_mirror)}>${sg(t.cum_mirror)}</td><td${cls(t.cum_composer)}>${sg(t.cum_composer)}</td><td${cls(t.cum_gap)}>${sg(t.cum_gap, 2)}</td><td${cls(x.cum_gap)}>${sg(x.cum_gap, 2)}</td><td${cls(t.mean_bps)}>${bp(t.mean_bps)}</td><td class="n">${t.sd_bps.toFixed(1)}</td><td class="n">–</td><td class="n">–</td></tr>`; };
  document.getElementById('tbG2').innerHTML = '<thead><tr><th class="lab">sensitivity (close mode, book)</th><th class="n">mirror</th><th class="n">Composer</th><th class="n">gap</th><th class="n">gap without 10-23→10-30</th><th class="n">mean, bps a day</th><th class="n">sd</th><th class="n">cost drag, bps a year</th><th class="n">same holdings</th></tr></thead><tbody>' +
    Object.entries(SL).map(([k, h]) => rowS(`slippage ${k} bps` + (+k === D.slip_bps ? ' (base)' : ''), h)).join('') + rowS('ledger gaps decided from the approved tree instead of standing still', GF) +
    `<tr><td colspan="9" class="note">Against Composer's OWN book (its real engine weights: ${Object.entries(SD.composer_weights).map(([e, w]) => `${e} ${Math.round(w * 100)}`).join(' / ')} on ${SD.from}, drifting to ${Object.entries(SD.composer_weights_end).map(([e, w]) => `${e} ${Math.round(w * 100)}`).join(' / ')}), from ${SD.from}, the first session all four engines existed:</td></tr>` +
    Object.entries(SD.runs).map(([k, v]) => rowO('seed: ' + k, v)).join('') + '</tbody>';
})();

// ---------- basis
(function(){
  const A = D.edge.asof || {}, I = F55 ? F55.info : R55.info, snaps = (D.window.composer_snapshots || {}).HG, moc = D.full ? D.full.rows.find(r => r.label === '15:45 -> close (MOC)') : null;
  [`In sample, and short: ${D.window.sessions} sessions (${D.window.start}..${D.window.end}), ${T.n_daily} daily book observations, one window that holds a −27% KMLM day (11-05) and the three sessions Composer did not rebalance. The close-mode decisions are the shadow ledger's targets: the approved trees on that day's CLOSE, which no live mirror could know when it fills at that close. Close mode measures the sleeve, netting and booking code and its costs; the 15:55 runs are the realistic timing.`,
   `Composer's daily return = deposit_adjusted_value(D) / deposit_adjusted_value(D−1) − 1 from the monitor snapshot taken after each close (16:35 or 17:35 ET; ${snaps} of the ${D.window.sessions} sessions have closing values; older snapshots are read from the git history of last-snapshot.json). Sessions without one (07-17, 07-22, 07-23, 09-11, 09-14, 10-26..10-29) are bridged as one stretch and never split into days, so 10-26..10-28 cannot be shown day by day: "without 10-23→10-30" removes that stretch whole. Composer's last_percent_change was not used (it differs from the value ratio by up to 37 bps and is the wrong day on a late snapshot).`,
   `Deposit days: a symphony's raw value moved beyond its deposit-adjusted return on ${ENG.map(e => `${e} ${D.eng[e].flow_days.map(d => d.slice(5)).join(', ') || 'none'}`).join('; ')} (transfers between symphonies; the account's net deposits never changed). Those days use Composer's own adjustment; they are flagged, not removed.`,
   `Modelled, not observed: every venue order fills whole at one price (the day's raw close, or the close of one 1-minute bar), ${D.slip_bps} bps against the mirror, plus IBKR's tiered commission; no partial fills, no auction imbalance, no margin, no exchange or regulatory fees, idle cash earns nothing, and the executor's venue-quote cross-check (1.5% band) is not simulated. The minute fill is the close of the bar that starts at the decision time, about a minute after it; the executor sends market orders 5 seconds after the decision bar ends, so its sells should fill nearer the reference than modelled here and its buys after the sells are booked. The executor's own paper stage fills at the brain's price with no slippage: it will read better than this simulation by the move in the fill minute and the ${D.slip_bps} bps.`,
   `Distributions: credited on the ex-date on the shares held at the prior close (Yahoo's dividend events), not on the pay date; the price basis takes them out for the comparison. Composer credits a distribution inside the symphony 1-5 sessions after the ex-date only if the payer is still held, otherwise it lands in account cash outside the symphony's figure (add. 38); those pay-date credits are identified from the mirror's own holdings and the observed pay lags, never guessed for a fund without one. The owner receives the cash at either broker: the distribution rows are an accounting difference, not a return the mirror adds. At IBKR a sleeve only sees a distribution when it is posted through the executor's /mirror/credit.`,
   `Book level: both sides' engine returns are combined at the MIRROR's sleeve weights at the start of each stretch, so the book numbers measure tracking, not allocation. Composer's own book ran other engine weights and moved capital between symphonies (HG −$64.5k on 07-21, SLEEVE +$16.9k on 07-16, HARV funded 07-21); that comparison is the seed rows of section G.`,
   `Decision agreement compares weights at the close; Composer's holdings for 08-05 and 10-29 were read during the next session and carry its drift. HARV has no Composer record before 07-24. Five sessions have no shadow-ledger row: in close mode the mirror stands still on them (the gap-filled variant is in section G); the 15:55 runs decide on them, but there is nothing of Composer's to compare.`,
   `Minute mode replays mirror_brain.build() with Yahoo's history rebased to the replayed day, as a live run saw it. The brain's own replay does not rebase: it reads a raw minute price against a history already lowered by every distribution paid since, so the replayed day opens with a jump that never happened. Left that way, ${D.edge.asof_changed} of ${A.engine_days} engine-days decide differently (all in ${D.edge.asof_months.map(m => MON[+m.slice(5) - 1]).join(', ')}; none in the last six weeks) and the whole-window agreement falls from ${A.as_of ? A.as_of.decisions.ALL.agree : '–'} to ${A.as_fetched_today ? A.as_fetched_today.decisions.ALL.agree : '–'} of ${A.as_of ? A.as_of.decisions.ALL.n : '–'}. A same-day run is not affected.`,
   `Fills: FMP's 1-minute bars are trades only; a fund with no trade in the fill minute fills at the day's close (${I.fallbacks} of ${I.orders} orders at 15:55 over the whole window: ${Object.entries(I.fallback_tickers).map(([t, k]) => `${t} ${k}`).join(', ')}). mirror_core sizes buys on the reference price plus a 0.3% cushion: with a fill a minute later no sleeve's cash went negative in ${I.covered} sessions; with a fill at the close it did on ${moc ? moc.overspent.length : '–'} sessions of the 15:45 run (worst ${moc && moc.overspent.length ? worst(moc.overspent) : '–'}).`,
   `Small numbers: ${D.dis.filter(x => x.class === 'knife-edge').length} knife-edge engine-days, ${D.episodes.length} KMLM stretches apart, ${D.edge.timing ? D.edge.timing.all.n : '–'} rotation engine-days on ${D.edge.timing ? D.edge.timing.by_day_mean.n : '–'} days for the fill-timing check, and the cumulative gaps turn on a handful of sessions (10-23→10-30, 11-04, 11-05, 08-31). No t-statistic here survives a correction for the comparisons made; read them as sizes, not findings.`,
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
