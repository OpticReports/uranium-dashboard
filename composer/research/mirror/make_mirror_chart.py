#!/usr/bin/env python3
"""Exhibit for the IBKR mirror's DRY parity measurement (composer/IBKR_MIRROR.md).
Reads results/mirror/backfill-2026-11-10.json (research/mirror/parity_study.py);
writes results/mirror-parity-2026-11-10.html (one self-contained file, no network).

The first screen answers three questions with charts: does the mirror hold what Composer holds, does
it earn what Composer earns, what does running on IBKR cost. Everything else is in collapsed sections."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")
SRC = os.path.join(RES, "mirror", "backfill-2026-11-10.json")
PAGE = os.path.join(RES, "mirror-parity-2026-11-10.html")
ENGINES = ("HG", "KMLM", "SLEEVE", "HARV")
LEG_CLASS = {"SQQQ": "inverse", "TLT": "bonds", "UVXY": "vol", "SOXL": "long", "TECL": "long"}


def leg_class(w):
    """what KMLM's 75% leg is in: 3x long tech, half long + half SVIX, 3x inverse, bonds, long vol"""
    leg = {t: x for t, x in (w or {}).items() if t not in ("PULS", "ZVOL", "VXZ") and x > 0.05}
    if not leg:
        return None
    if "SVIX" in leg:
        return "half"
    return LEG_CLASS.get(max(leg, key=leg.get), "other")


def chain(series):
    """[[date, mirror cumulative, Composer cumulative]] from the chained spans, starting at 0"""
    if not series:
        return []
    pts, m, c = [[series[0]["d0"], 0.0, 0.0]], 1.0, 1.0
    for s in series:
        m, c = m * (1 + s["mirror"]), c * (1 + s["composer"])
        pts.append([s["date"], round(m - 1, 5), round(c - 1, 5)])
    return pts


def bars(series, stretch):
    out = []
    for s in series:
        c = s.get("cause") or ""
        k = "norebal" if any(s["d0"] < d <= s["date"] for d in stretch) else \
            "apart" if ("different holdings" in c or "the holdings split" in c) else "plain"
        out.append({"d0": s["d0"], "d": s["date"], "n": s["n"], "v": s["diff_bps"], "k": k, "c": s.get("cause"),
                    "m": s["mirror"], "o": s["composer"]})
    return out


def paired(rows, a, b, key="gain_bps"):
    """mean, t (per engine-day and with one observation a day) of filling at minute a instead of minute b"""
    import math

    def st(xs):
        n = len(xs)
        if n < 2:
            return {"n": n, "mean": None, "t": None}
        m = sum(xs) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
        return {"n": n, "mean": round(m, 3), "t": round(m / (sd / math.sqrt(n)), 2) if sd > 0 else None}
    d = [r[key][a] - r[key][b] for r in rows]
    by = {}
    for r in rows:
        by.setdefault(r["date"], []).append(r[key][a] - r[key][b])
    return dict(st(d), by_day=st([sum(v) / len(v) for v in by.values()]))


def run_row(lab, v):
    h, f = v["headline"], v["every_buy_fills"]
    return {"label": lab, "decide": v["decide"], "fill": v["fill"], "limit_at": v["limit_at"], "dec": h["decisions"], "book": h["book"],
            "ex": h["book_ex"], "gross_ex": h["book_gross_ex"], "gross": h["book_gross"], "costs": h["costs"], "limit": h["limit_buys"],
            "cash": h["cash"], "dist": h["distributions"], "info": v.get("info"), "problems": h["problems"],
            "overspent": len(h["overspent"]),
            "filled": {"gap": f["book"]["cum_gap"], "ex": f["book_ex"]["cum_gap"], "sd": f["book"]["sd_bps"],
                       "agree": f["decisions"]["ALL"]["agree"]}}


def slim_headline(h):
    return {"dec": h["decisions"]["ALL"], "book": h["book"], "ex": h["book_ex"], "gross_ex": h["book_gross_ex"],
            "costs": {k: h["costs"][k] for k in ("commission_bps_yr", "slippage_bps_yr", "drag_bps_yr")},
            "limit": h["limit_buys"], "dist": h["distributions"], "overspent": len(h["overspent"])}


def main(src=SRC, page=PAGE):
    with open(src) as f:
        r = json.load(f)
    P = r["primary_run"]
    stretch = r["window"]["no_rebalance"]
    sessions = sorted({x["date"] for x in P["rows"]})
    eng = {}
    for e in ENGINES:
        blk = P["engines"][e]
        eng[e] = {"pts": chain(blk["series"]), "bars": bars(blk["series"], stretch), "t": blk["tracking"],
                  "tx": blk["tracking_ex_no_rebalance"], "tg": blk["tracking_gross"], "tp": blk["tracking_price_basis"],
                  "costs": blk["costs"], "cash": blk["cash"], "dist": {k: v for k, v in blk["distributions"].items() if k != "events"},
                  "events": blk["distributions"]["events"], "actions": blk["actions"], "avg_equity": blk["avg_equity"],
                  "holder": r["sensitivity"]["dividend_rule"]["holder"]["engines"][e]}
    B = P["book"]
    sens = r["sensitivity"]
    fm = r["edge"]["fill_minute"]
    data = {
        "generated": r["generated"], "window": r["window"], "capital": r["capital"], "fractions": r["fractions"],
        "slip_bps": r["slip_bps"], "core": r["core"], "commission": r["commission"], "sessions": sessions,
        "dec": P["decisions"],
        "misses": [{"d": x["date"], "e": x["engine"], "c": x["class"], "note": x["note"], "dist": x["dist"], "m": x["mirror"],
                    "o": x["composer"]} for x in P["disagreements"]],
        "book": {"pts": chain(B["series"]), "bars": bars(B["series"], stretch), "t": B["tracking"], "tx": B["tracking_ex_no_rebalance"],
                 "tg": B["tracking_gross"], "tgx": B["tracking_gross_ex_no_rebalance"], "tp": B["tracking_price_basis"],
                 "tpx": B["tracking_price_basis_ex_no_rebalance"], "costs": B["costs"], "avg_equity": B["avg_equity"],
                 "final_equity": B["final_equity"], "problems": B["problems"], "overspent": B["overspent"]},
        "eng": eng, "costs": r["costs"], "info": P["info"],
        "noise": P["headline"]["noise_floor"],
        "runs": [run_row(lab, r["runs"][lab]) for lab in r["run_order"]],
        "kmlm": [{"d": k["date"], "mc": leg_class(k["mirror"]), "cc": leg_class(k["composer"]), "dist": k["dist"], "a": k["action"],
                  "m": k["mirror"], "c": k["composer"], "gap": k["gap"]} for k in r["kmlm_path"]],
        "episodes": (P["episodes"] or {}).get("KMLM", []),
        "unfilled": P["unfilled"], "unallocated": P["unallocated"],
        "sens": {"rule": {"holder": slim_headline(sens["dividend_rule"]["holder"]["headline"]),
                          "holder_minus_composer_bps": sens["dividend_rule"]["holder_minus_composer_bps"]},
                 "limit": {"requote": slim_headline(sens["buy_limit"]["requoted_at_the_fill"]),
                           "none": slim_headline(sens["buy_limit"]["no_limit"]),
                           "unfilled_cost_bps": sens["buy_limit"]["unfilled_cost_bps"], "vs_requoted_bps": sens["buy_limit"]["vs_requoted_bps"]},
                 "slip": {k: slim_headline(v) for k, v in sens["slip_bps"].items()},
                 "gaps": slim_headline(sens["ledger_gaps_filled_from_the_tree"]), "seed": sens["seed"]},
        "edge": {"minutes": fm.get("times"), "base": fm.get("base"), "n": len(fm.get("rows") or []),
                 "days": len({x["date"] for x in fm.get("rows") or []}),
                 "summary": {k: {kk: vv for kk, vv in v.items() if kk != "by_engine"} for k, v in (fm.get("summary") or {}).items()},
                 "close_vs_minute": r["edge"]["fill_at_the_close_vs_a_minute_later"],
                 "later": r["edge"]["later_fill_same_decisions"]["rows"],
                 "vs_mirror": {x: {"actual": paired(fm.get("rows") or [], x, "15:55"),
                                   "placebo": paired(fm.get("rows") or [], x, "15:55", "placebo_bps")}
                               for x in ("15:56", "15:57", "15:58", "15:59", "16:00")},
                 "knife": {e: {k: v for k, v in x.items() if k != "days"} for e, x in r["edge"]["knife_edge_carry"].items()}},
        "fills": r.get("composer_fills"),
        "replay": {k: v for k, v in r["replay_paths"].items() if k != "differ"}, "replay_differ": r["replay_paths"]["differ"][:12],
        "replay_n": len(r["replay_paths"]["differ"]),
        "cross": r["brain_cross_check"], "events": r["events"], "splits": r["splits_in_window"],
        "splits_applied": len(P["splits_applied"])}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(page, "w") as f:
        f.write(html)
    print("wrote", page, f"({len(html) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mirror parity measured</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--ctx:#b9b7ae;--ctx2:#8e8c84;--neg:#e34948;--band:rgba(42,120,214,.18);--band2:rgba(237,161,0,.20);--track:#ecebe5}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--band2:rgba(201,133,0,.26);--track:#262624}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ctx:#5a5955;--ctx2:#7a7872;--neg:#e66767;--band:rgba(57,135,229,.22);--band2:rgba(201,133,0,.26);--track:#262624}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1068px;margin:0 auto;padding:18px 16px 40px}
h1{font-size:22px;margin:0 0 2px;font-weight:650;line-height:1.25}h2{font-size:16px;margin:0 0 2px;font-weight:650}h3{font-size:13.5px;margin:10px 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 10px;font-size:14px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px 16px;min-width:0}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:10px 0}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:10px 14px;min-width:0}
.kpi b{display:block;font-size:26px;font-weight:650;line-height:1.15;font-variant-numeric:tabular-nums}.kpi span{color:var(--ink2);font-size:13px;display:block;margin-top:2px;line-height:1.35}
.top{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,8fr);gap:10px;align-items:start}
.stack{display:grid;gap:10px;min-width:0}
@media (max-width:820px){.kpis{grid-template-columns:1fr 1fr}.top{grid-template-columns:minmax(0,1fr)}}
.q{color:var(--ink2);font-size:13px;margin:0 0 6px;line-height:1.35}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;margin:4px 0 6px;font-size:12.5px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}.sw{display:inline-block;width:12px;height:12px;border-radius:3px}.sw.ln{height:3px;border-radius:2px;width:16px}
.arow{display:grid;grid-template-columns:62px 74px minmax(0,1fr);gap:8px;align-items:center;padding:3px 0;font-size:14px}
.arow b{font-weight:650}.arow .ct{font-variant-numeric:tabular-nums;white-space:nowrap}.arow .ct small{color:var(--ink2);font-size:12px}
.bar{height:12px;background:var(--track);border-radius:4px;overflow:hidden}.bar i{display:block;height:100%;background:var(--s1);border-radius:4px}
.miss{display:flex;flex-wrap:wrap;gap:3px;margin-top:4px;min-height:14px}.miss i{width:14px;height:14px;border-radius:3px;display:block;cursor:default}
.crow{display:grid;grid-template-columns:minmax(0,186px) minmax(0,1fr) 54px;gap:8px;align-items:center;padding:3px 0;font-size:13.5px;line-height:1.25}
@media (max-width:820px){.crow{grid-template-columns:minmax(0,150px) minmax(0,1fr) 54px}}
.crow .v{text-align:right;font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}.crow small{display:block;color:var(--ink2);font-size:12px}
.cbar{height:14px;border-radius:4px;background:var(--s1);min-width:2px}.cbar.ctx{background:var(--ctx2)}
.sum{border-top:1px solid var(--grid);margin-top:4px;padding-top:6px;font-size:13.5px;display:flex;justify-content:space-between;gap:8px}.sum b{font-variant-numeric:tabular-nums}
.sm{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px 12px;margin-top:6px}
@media (max-width:820px){.sm{grid-template-columns:1fr 1fr}}
.sm h3{margin:0}.sm p{margin:0;color:var(--ink2);font-size:12px}
.cap{color:var(--ink2);font-size:12.5px;margin:6px 0 0;line-height:1.35}
svg{display:block;width:100%;height:auto;overflow:visible}.ax{fill:var(--muted);font-size:11px}.lb{fill:var(--ink2);font-size:12px}.lbb{fill:var(--ink);font-size:12.5px;font-weight:600}
.honest{margin:10px 0 0;padding:0;list-style:none;color:var(--ink2);font-size:13px;display:grid;gap:2px}
.honest li::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--ctx2);margin:0 8px 2px 2px}
details{background:var(--surface);border:1px solid var(--ring);border-radius:10px;margin-top:8px;padding:0 16px}
summary{cursor:pointer;padding:10px 0;font-weight:600;font-size:14.5px}summary span{font-weight:400;color:var(--ink2);margin-left:6px;font-size:13.5px}
details[open]{padding-bottom:14px}details p{margin:4px 0 8px;font-size:13.5px;color:var(--ink2)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--grid);vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}td.n{white-space:nowrap}
thead th{color:var(--ink2);font-weight:600;font-size:12px;vertical-align:bottom}.tablewrap{overflow-x:auto}
td.lab{min-width:150px}td.note{color:var(--ink2);min-width:220px}
.notes{font-size:13.5px;color:var(--ink2);margin:6px 0;padding-left:18px}.notes li{margin:3px 0}
.neg{color:var(--neg)}.mut{color:var(--ink2)}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5;max-width:340px;box-shadow:0 2px 10px rgba(0,0,0,.12)}
</style>
</head>
<body>
<main>
<h1>The IBKR mirror on paper, against Composer</h1>
<p class="sub-h" id="lede"></p>
<div class="kpis" id="kpis"></div>
<div class="top">
  <div class="stack">
    <section class="card">
      <h2>Does it hold what Composer holds?</h2>
      <p class="q" id="qa"></p>
      <div id="agree"></div>
      <div class="legend" id="lgA"></div>
    </section>
    <section class="card">
      <h2>What does running on IBKR cost?</h2>
      <p class="q" id="qc"></p>
      <div id="cost"></div>
      <p class="cap" id="capc"></p>
    </section>
  </div>
  <section class="card">
    <h2>Does it earn what Composer earns?</h2>
    <p class="q" id="qb"></p>
    <div class="legend" id="lgB"></div>
    <div id="cum"></div>
    <h3>Daily difference, mirror minus Composer (bps of the book)</h3>
    <div class="legend" id="lgD"></div>
    <div id="diff"></div>
    <div class="sm" id="sm"></div>
  </section>
</div>
<ul class="honest" id="honest"></ul>

<details id="dRuns"><summary>Every run: decision time and fill time<span id="sRuns"></span></summary>
  <div class="tablewrap"><table id="tbRuns"></table></div>
  <p id="pRuns"></p>
</details>
<details id="dMiss"><summary>The engine-days that differ, each one named<span id="sMiss"></span></summary>
  <div class="tablewrap"><table id="tbMiss"></table></div>
</details>
<details id="dWorst"><summary>Largest return differences and their causes<span id="sWorst"></span></summary>
  <div class="tablewrap"><table id="tbWorst"></table></div>
  <h3>Per engine</h3>
  <div class="tablewrap"><table id="tbEng"></table></div>
  <p id="pWorst"></p>
</details>
<details id="dCost"><summary>Limit buys and distributions<span id="sCost"></span></summary>
  <h3>Buys left unfilled at their limit</h3>
  <div class="tablewrap"><table id="tbUnf"></table></div>
  <p id="pUnf"></p>
  <h3>Distributions, per engine</h3>
  <div class="tablewrap"><table id="tbDiv"></table></div>
  <p id="pDiv"></p>
  <div class="tablewrap"><table id="tbEv"></table></div>
</details>
<details id="dKmlm"><summary>KMLM's corridor path<span id="sKmlm"></span></summary>
  <div class="legend" id="lgK"></div>
  <div id="kmlm"></div>
  <p id="pKmlm"></p>
</details>
<details id="dEdge"><summary>Candidate edge: a later fill<span id="sEdge"></span></summary>
  <div class="legend" id="lgE"></div>
  <div id="edge"></div>
  <div class="tablewrap"><table id="tbEdge"></table></div>
  <h3>The mirror's own decisions, filled later</h3>
  <div class="tablewrap"><table id="tbEdge2"></table></div>
  <ul class="notes" id="nEdge"></ul>
</details>
<details id="dSens"><summary>Sensitivities<span id="sSens"></span></summary>
  <div class="tablewrap"><table id="tbSens"></table></div>
  <p id="pSens"></p>
</details>
<details id="dReplay"><summary>Is the replay the brain's own decision?<span id="sReplay"></span></summary>
  <div class="tablewrap"><table id="tbCross"></table></div>
  <ul class="notes" id="nReplay"></ul>
</details>
<details id="dBasis"><summary>Basis and limits<span> what was measured, what was not</span></summary>
  <ul class="notes" id="nBasis"></ul>
</details>
<div class="tt" id="tt"></div>
</main>
<script>
const D = __DATA__, NS = 'http://www.w3.org/2000/svg', tt = document.getElementById('tt'), ENG = ['HG', 'KMLM', 'SLEEVE', 'HARV'];
const $ = id => document.getElementById(id);
function el(t, a, p, x){const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); if (x != null) e.textContent = x; p.appendChild(e); return e;}
function tip(ev, h){tt.innerHTML = h; tt.style.display = 'block'; tt.style.left = Math.max(8, Math.min(ev.clientX + 12, innerWidth - tt.offsetWidth - 8)) + 'px'; tt.style.top = Math.max(8, Math.min(ev.clientY + 12, innerHeight - tt.offsetHeight - 8)) + 'px';}
function untip(){tt.style.display = 'none';}
function legend(id, items){$(id).innerHTML = items.map(([n, c, line]) => `<span>${c ? `<i class="sw${line ? ' ln' : ''}" style="background:${c}"></i>` : ''}${n}</span>`).join('');}
const pc = (v, k = 1) => v == null ? '–' : (v * 100).toFixed(k) + '%', sg = (v, k = 1) => v == null ? '–' : (v >= 0 ? '+' : '−') + Math.abs(v * 100).toFixed(k) + '%';
const bp = (v, k = 1) => v == null ? '–' : (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(k), f2 = v => v == null ? '–' : (v < 0 ? '−' : '') + Math.abs(v).toFixed(2);
const cls = v => v == null ? ' class="n"' : (v < 0 ? ' class="n neg"' : ' class="n"');
const usd = v => v == null ? '–' : (v < 0 ? '−$' : '$') + Math.abs(Math.round(v)).toLocaleString('en-US');
const fw = w => !w ? '–' : (typeof w === 'string' ? w : Object.entries(w).sort((a, b) => b[1] - a[1]).map(([t, x]) => `${t} ${Math.round(x * 100)}%`).join(', '));
const md = d => d ? d.slice(5) : '–';
const S = D.sessions, SI = Object.fromEntries(S.map((d, i) => [d, i])), B = D.book, T = B.t, TX = B.tx, W = D.window, C = D.costs;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const P0 = D.runs[0];
const NAMES = {'agree': 'same holdings', 'knife-edge': 'knife-edge call', 'composer-no-rebalance': 'Composer did not rebalance', 'corridor-path': 'KMLM corridor path', 'decision-minute': 'the call flipped after 15:54', 'late-snapshot': 'Composer read a day late', 'whole-share': 'whole shares / idle cash', 'mirror-skip': 'the mirror had no decision', 'other': 'unexplained'};
const SHORT = {'knife-edge': 'knife-edge', 'composer-no-rebalance': 'Composer skipped', 'corridor-path': 'corridor path', 'decision-minute': 'flipped after 15:54', 'late-snapshot': 'read a day late', 'whole-share': 'whole shares', 'mirror-skip': 'no decision', 'other': 'unexplained'};
const CCOL = {'composer-no-rebalance': 'var(--ctx2)', 'late-snapshot': 'var(--ctx)', 'decision-minute': 'var(--s4)', 'knife-edge': 'var(--s3)', 'corridor-path': 'var(--s2)', 'whole-share': 'var(--neg)', 'mirror-skip': 'var(--neg)', 'other': 'var(--neg)'};
function width(node){ return Math.max(280, Math.floor(node.getBoundingClientRect().width)); }
function niceStep(span, n){ const raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))); return [1, 2, 5, 10].map(k => k * p).find(s => s >= raw); }
function monthTicks(svg, X, y, i0, i1){ let last = S[i0].slice(5, 7); for (let i = i0 + 1; i <= i1; i++) { const m = S[i].slice(5, 7); if (m !== last) { el('text', {x: X(i), y, 'text-anchor': 'middle', class: 'ax'}, svg, MON[+m - 1]); last = m; } } }
const stretch = [S[SI[W.no_rebalance[0]] - 1], S[SI[W.no_rebalance[W.no_rebalance.length - 1]] + 2] || S[S.length - 1]];

// ---------- headline
const yrs = W.annual_factor, costYr = (C.commission_bps_yr + C.slippage_bps_yr) / 100;
$('lede').textContent = `${W.sessions} sessions, ${W.start} to ${W.end}, on $${D.capital.toLocaleString('en-US')} split ${ENG.map(e => Math.round(D.fractions[e] * 100)).join(' / ')}. ` +
  `Each session the executor's own core decides at ${D.core.decide}:00 ET from the brain's pinned build, sells at market and buys with limit orders, filled at the bar ending a minute later.`;
$('kpis').innerHTML = [
  [`${D.dec.ALL.agree} / ${D.dec.ALL.n}`, `engine-days holding what Composer holds (${pc(D.dec.ALL.share)})`],
  [`${T.sd_bps.toFixed(0)} bps`, `standard deviation of the book's daily return difference (correlation ${T.corr.toFixed(3)})`],
  [sg(T.cum_gap), `mirror minus Composer; ${sg(TX.cum_gap)} without the no-rebalance stretch`],
  [`${costYr.toFixed(1)}% a year`, `modelled cost on IBKR: slippage ${(C.slippage_bps_yr / 100).toFixed(1)}%, commission ${(C.commission_bps_yr / 100).toFixed(1)}%`]
].map(([b, s]) => `<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join('');

// ---------- (a) agreement
function drawA(){
  const present = [...new Set(D.misses.map(m => m.c))];
  $('qa').textContent = `Weights within 3% of Composer's after each rebalance. One square per engine-day that differs (${D.misses.length}).`;
  $('agree').innerHTML = ENG.map(e => { const d = D.dec[e]; const ms = D.misses.filter(m => m.e === e);
    return `<div class="arow"><b>${e}</b><span class="ct">${d.agree} <small>/ ${d.n}</small></span><div><div class="bar"><i style="width:${(d.share * 100).toFixed(1)}%"></i></div>` +
      `<div class="miss">${ms.map((m, i) => `<i data-e="${e}" data-i="${i}" style="background:${CCOL[m.c] || 'var(--neg)'}"></i>`).join('')}</div></div></div>`; }).join('');
  $('agree').querySelectorAll('.miss i').forEach(n => { const m = D.misses.filter(x => x.e === n.dataset.e)[+n.dataset.i];
    n.addEventListener('mousemove', ev => tip(ev, `<b>${m.e} ${m.d}</b>: ${NAMES[m.c] || m.c}<br>mirror ${fw(m.m)}<br>Composer ${fw(m.o)}`)); n.addEventListener('mouseleave', untip); });
  legend('lgA', present.map(c => [`${SHORT[c] || c} (${D.misses.filter(m => m.c === c).length})`, CCOL[c] || 'var(--neg)']));
}

// ---------- (b) returns
function lineChart(host, pts, o){
  host.innerHTML = '';
  const Wd = width(host), H = o.h, m = {l: o.small ? 34 : 42, r: o.small ? 6 : rightM(Wd), t: 8, b: 20};
  const svg = el('svg', {viewBox: `0 0 ${Wd} ${H}`, role: 'img', 'aria-label': o.label}, host);
  const i0 = SI[pts[0][0]], i1 = SI[pts[pts.length - 1][0]], X = i => m.l + (i - i0) / Math.max(1, i1 - i0) * (Wd - m.l - m.r);
  const vals = pts.flatMap(p => [p[1], p[2]]); let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const step = niceStep((hi - lo) || 0.01, o.small ? 3 : 4); lo = Math.floor(lo / step + 1e-9) * step; hi = Math.ceil(hi / step - 1e-9) * step;
  const Y = v => m.t + (hi - v) / (hi - lo) * (H - m.t - m.b);
  for (let v = lo; v <= hi + 1e-9; v += step) { el('line', {x1: m.l, x2: Wd - m.r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v * 100).toFixed(0) + '%'); }
  if (SI[stretch[0]] >= i0) { const a = X(SI[stretch[0]]), b = X(Math.min(SI[stretch[1]], i1)); el('rect', {x: a, y: m.t, width: Math.max(2, b - a), height: H - m.t - m.b, fill: 'var(--band2)'}, svg); }
  monthTicks(svg, X, H - 5, i0, i1);
  const path = k => pts.map((p, j) => (j ? 'L' : 'M') + X(SI[p[0]]).toFixed(1) + ' ' + Y(p[k]).toFixed(1)).join('');
  el('path', {d: path(2), fill: 'none', stroke: 'var(--s2)', 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
  el('path', {d: path(1), fill: 'none', stroke: 'var(--s1)', 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
  const last = pts[pts.length - 1];
  if (!o.small) { let ym = Y(last[1]), yc = Y(last[2]); if (Math.abs(ym - yc) < 15) { const mid = (ym + yc) / 2; if (ym <= yc) { ym = mid - 7.5; yc = mid + 7.5; } else { ym = mid + 7.5; yc = mid - 7.5; } }
    [[1, 'var(--s1)', ym, 'mirror'], [2, 'var(--s2)', yc, 'Composer']].forEach(([k, c, y, n]) => { el('circle', {cx: X(i1), cy: Y(last[k]), r: 4, fill: c, stroke: 'var(--surface)', 'stroke-width': 2}, svg); el('text', {x: Wd - m.r + 9, y: y + 4, class: 'lbb'}, svg, sg(last[k]) + (Wd >= 560 ? ' ' + n : '')); }); }
  const vl = el('line', {y1: m.t, y2: H - m.b, stroke: 'var(--ctx2)', 'stroke-dasharray': '3 3', visibility: 'hidden'}, svg);
  const hit = el('rect', {x: m.l, y: m.t, width: Wd - m.l - m.r, height: H - m.t - m.b, fill: 'transparent'}, svg);
  hit.addEventListener('mousemove', ev => { const r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) * Wd / r.width; let best = 0, bd = 1e9; pts.forEach((p, j) => { const dx = Math.abs(X(SI[p[0]]) - x); if (dx < bd) { bd = dx; best = j; } });
    const p = pts[best]; vl.setAttribute('x1', X(SI[p[0]])); vl.setAttribute('x2', X(SI[p[0]])); vl.setAttribute('visibility', 'visible');
    tip(ev, `<b>${p[0]}</b>${o.name ? ' ' + o.name : ''}<br>mirror ${sg(p[1])}<br>Composer ${sg(p[2])}<br>gap ${sg(p[1] - p[2], 2)}`); });
  hit.addEventListener('mouseleave', () => { vl.setAttribute('visibility', 'hidden'); untip(); });
}
const KCOL = {plain: 'var(--s1)', apart: 'var(--s4)', norebal: 'var(--ctx2)'};
function rightM(Wd){ return Wd >= 560 ? 124 : 60; }
function diffBars(host, bars, clip){
  host.innerHTML = '';
  const Wd = width(host), H = 100, m = {l: 42, r: rightM(Wd), t: 12, b: 8};
  const svg = el('svg', {viewBox: `0 0 ${Wd} ${H}`, role: 'img', 'aria-label': 'Daily return difference, mirror minus Composer, in basis points'}, host);
  const i0 = SI[bars[0].d0], i1 = SI[bars[bars.length - 1].d], X = i => m.l + (i - i0) / Math.max(1, i1 - i0) * (Wd - m.l - m.r);
  const Y = v => m.t + (clip - v) / (2 * clip) * (H - m.t - m.b), w1 = (Wd - m.l - m.r) / Math.max(1, i1 - i0);
  [-clip, 0, clip].forEach(v => { el('line', {x1: m.l, x2: Wd - m.r, y1: Y(v), y2: Y(v), stroke: v ? 'var(--grid)' : 'var(--axis)'}, svg); el('text', {x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v > 0 ? '+' : '') + v); });
  let lastLab = null;
  bars.forEach(b => { const a = X(SI[b.d0]), z = X(SI[b.d]), v = Math.max(-clip, Math.min(clip, b.v)), y0 = Y(0), y1 = Y(v);
    const g = el('rect', {x: a + 1, width: Math.max(1.5, z - a - 1.5), y: Math.min(y0, y1), height: Math.max(1, Math.abs(y1 - y0)), fill: KCOL[b.k], rx: 1.5}, svg);
    if (Math.abs(b.v) > clip) { const x = (a + z) / 2, near = lastLab != null && x - lastLab < 34; lastLab = x;      // two clipped bars side by side: the labels step apart
      el('text', {x: near ? x + 4 : x, y: b.v < 0 ? (near ? H - 14 : H - 1) : (near ? 22 : 9), 'text-anchor': near ? 'start' : 'middle', class: 'lb'}, svg, bp(b.v, 0)); }
    const hit = el('rect', {x: a, width: Math.max(4, z - a), y: m.t, height: H - m.t - m.b, fill: 'transparent'}, svg);
    hit.addEventListener('mousemove', ev => tip(ev, `<b>${b.n > 1 ? b.d0 + ' → ' : ''}${b.d}</b>${b.n > 1 ? ` (${b.n} sessions)` : ''}<br>mirror ${sg(b.m, 2)}, Composer ${sg(b.o, 2)}: ${bp(b.v)} bps<br>${b.c || ''}`));
    hit.addEventListener('mouseleave', untip); });
  el('text', {x: Wd - m.r + 9, y: Y(0) - 3, class: 'lb'}, svg, Wd >= 560 ? `mean ${bp(T.mean_bps)} bps` : bp(T.mean_bps));
  el('text', {x: Wd - m.r + 9, y: Y(0) + 12, class: 'lb'}, svg, Wd >= 560 ? `SD ${T.sd_bps.toFixed(1)} bps` : '±' + T.sd_bps.toFixed(0));
}
function drawB(){
  $('qb').textContent = `Cumulative return of the book, both sides at the mirror's sleeve weights. Before costs the gap is ${sg(B.tg.cum_gap)}, and ${sg(B.tgx.cum_gap)} outside the shaded stretch.`;
  legend('lgB', [['mirror on paper, after costs', 'var(--s1)', 1], ['Composer, deposit-adjusted', 'var(--s2)', 1], [`Composer did not rebalance (${md(W.no_rebalance[0])} to ${md(W.no_rebalance[W.no_rebalance.length - 1])})`, 'var(--band2)']]);
  lineChart($('cum'), B.pts, {h: 200, label: 'Cumulative return of the book, mirror and Composer'});
  legend('lgD', [['same holdings into the day', KCOL.plain], ['different holdings into the day', KCOL.apart], ['the no-rebalance stretch', KCOL.norebal]]);
  diffBars($('diff'), B.bars, 60);
  $('sm').innerHTML = ENG.map(e => { const t = D.eng[e].t; return `<div><h3>${e} <span class="mut" style="font-weight:400">${sg(t.cum_gap)}</span></h3><p>${sg(t.cum_mirror)} vs ${sg(t.cum_composer)}</p><div id="sm${e}"></div></div>`; }).join('');
  ENG.forEach(e => lineChart($('sm' + e), D.eng[e].pts, {h: 104, small: 1, name: e, label: `${e}: cumulative return, mirror and Composer`}));
}

// ---------- (c) costs
function drawC(){
  const U = C.unfilled, dist = C.distributions, cash = C.cash;
  const rows = [
    ['Slippage', `${D.slip_bps} bps a trade, assumed`, C.slippage_bps_yr, 0],
    ['Commission', `IBKR tiered, ${C.orders} orders`, C.commission_bps_yr, 0],
    ['Idle cash', `${pc(cash.mean_share_invested, 2)} of a sleeve, on average`, cash.drag_bps_yr, 0],
    ['Unfilled limit buys', `${U.unfilled_orders} of ${U.buy_orders} buy orders`, U.cost_bps_yr, 0],
    ['Dividends left unallocated', `${usd(dist.leaked_usd)} of ${usd(dist.accrued_usd)}`, dist.leaked_bps_yr, 1]];
  const mx = Math.max(...rows.map(r => Math.abs(r[2])));
  $('qc').textContent = `Percent of the book a year, at this window's ${C.turnover_x_yr.toFixed(0)}x turnover.`;
  $('cost').innerHTML = rows.map(([n, s, v, ctx]) => `<div class="crow"><div>${n}<small>${s}</small></div><div><div class="cbar${ctx ? ' ctx' : ''}" style="width:${(Math.abs(v) / mx * 100).toFixed(1)}%"></div></div><div class="v">${(v / 100).toFixed(2)}%</div></div>`).join('') +
    `<div class="sum"><span>Loss against Composer (the first two)</span><b>${costYr.toFixed(2)}%</b></div>`;
  const bm = Object.entries(U.by_decision_minute).filter(([k]) => k !== D.core.decide).map(([, v]) => v.unfilled_orders);
  $('capc').textContent = `A missed buy idles its sleeve for a session (${Math.min(...bm)} to ${Math.max(...bm)} at other decision minutes). Unallocated dividends stay in the account, as on Composer.`;
}

// ---------- honesty, one line each
$('honest').innerHTML = [
  `In sample, one window: ${W.sessions} sessions in which Composer's book rose ${pc(T.cum_composer)}. Nothing here is a forecast.`,
  `Fills are modelled, never executed: 1-minute bar closes, ${D.slip_bps} bps of slippage assumed, IBKR's tiered commission.`,
  `Composer's side is its deposit-adjusted value in the monitor's snapshots: ${T.n_daily} one-day comparisons; sessions without a closing snapshot are compared as multi-day stretches.`
].map(x => `<li>${x}</li>`).join('');

// ---------- collapsed: every run
function runRow(r){ const d = r.dec, b = r.book;
  return `<tr><td class="lab">${r.label === 'close' ? 'Close: the ledger\'s target, filled at the close' : r.fill === 'close' ? `${r.decide}, filled at the close` : `${r.decide}, filled a minute later`}</td>` +
    `<td class="n">${d.ALL.agree} / ${d.ALL.n} (${pc(d.ALL.share)})</td><td class="n">${ENG.map(e => d[e].agree).join(' / ')}</td>` +
    `<td${cls(b.mean_bps)}>${bp(b.mean_bps, 2)}</td><td class="n">${f2(b.sd_bps)}</td><td class="n">${b.corr == null ? '–' : b.corr.toFixed(3)}</td><td class="n">${f2(b.beta)}</td>` +
    `<td${cls(b.cum_gap)}>${sg(b.cum_gap, 2)}</td><td${cls(r.ex.cum_gap)}>${sg(r.ex.cum_gap, 2)}</td><td${cls(r.gross_ex.cum_gap)}>${sg(r.gross_ex.cum_gap, 2)}</td>` +
    `<td class="n">${r.limit_at === 'fill' ? 're-quoted' : r.limit.unfilled_orders + ' / ' + r.limit.buy_orders}</td><td${cls(r.filled.ex)}>${sg(r.filled.ex, 2)}</td></tr>`; }
function drawRuns(){
  $('sRuns').textContent = ` ${D.runs.length} runs; holdings agree on ${Math.min(...D.runs.map(r => r.dec.ALL.agree))} to ${Math.max(...D.runs.map(r => r.dec.ALL.agree))} of ${D.dec.ALL.n} engine-days`;
  $('tbRuns').innerHTML = `<thead><tr><th>Run</th><th class="n">Same holdings</th><th class="n">HG / KMLM / SLEEVE / HARV</th><th class="n">Mean, bps a day</th><th class="n">SD</th><th class="n">Corr</th><th class="n">Beta</th><th class="n">Gap</th><th class="n">Gap without ${md(stretch[0])} to ${md(stretch[1])}</th><th class="n">The same before costs</th><th class="n">Buys unfilled</th><th class="n">Gap without the stretch if every buy fills</th></tr></thead><tbody>${D.runs.map(runRow).join('')}</tbody>`;
  const fb = D.info.fallback_tickers, worst = D.runs.filter(r => r.limit_at !== 'fill').sort((a, b) => b.book.sd_bps - a.book.sd_bps)[0];
  $('pRuns').textContent = `Book level, ${T.n_daily} one-day comparisons, booked basis against Composer's deposit-adjusted value, both sides at the mirror's sleeve weights, after modelled costs unless stated. ` +
    `A buy left unfilled leaves its sleeve in cash until the next session: in the ${worst.label} run ${worst.limit.unfilled_orders} such buys make the SD ${f2(worst.book.sd_bps)} bps (${f2(worst.filled.sd)} when every buy fills). ` +
    `The last column re-quotes each limit at the fill, as the live executor does after its sells, so every buy fills and only the timing differs; a fill at the close is shown that way only. ` +
    `In the ${P0.decide} run ${D.info.fallbacks} of ${D.info.orders} orders had no trade in their fill minute and filled at the close (${Object.entries(fb).map(([t, n]) => `${t} ${n}`).join(', ')}).`;
}

// ---------- collapsed: the misses
function drawMiss(){
  const by = {}; D.misses.forEach(m => by[m.c] = (by[m.c] || 0) + 1);
  $('sMiss').textContent = ' ' + Object.entries(by).sort((a, b) => b[1] - a[1]).map(([c, n]) => `${n} ${NAMES[c] || c}`).join(', ');
  $('tbMiss').innerHTML = `<thead><tr><th>Day</th><th>Engine</th><th>Cause</th><th>Mirror holds</th><th>Composer holds</th><th class="n">Apart</th><th>Note</th></tr></thead><tbody>` +
    D.misses.map(m => `<tr><td class="n">${m.d}</td><td>${m.e}</td><td>${NAMES[m.c] || m.c}</td><td>${fw(m.m)}</td><td>${fw(m.o)}</td><td class="n">${pc(m.dist, 0)}</td><td class="note">${m.note}</td></tr>`).join('') + '</tbody>';
}

// ---------- collapsed: worst days, per engine
function drawWorst(){
  const w = T.worst || [];
  $('sWorst').textContent = w.length ? ` the largest: ${bp(w[0].diff_bps, 0)} bps over ${md(w[0].d0)} to ${md(w[0].date)}` : '';
  $('tbWorst').innerHTML = `<thead><tr><th>From</th><th>To</th><th class="n">Sessions</th><th class="n">Mirror</th><th class="n">Composer</th><th class="n">Difference, bps</th><th>Largest part and its cause</th></tr></thead><tbody>` +
    w.map(x => `<tr><td class="n">${x.d0}</td><td class="n">${x.date}</td><td class="n">${x.n}</td><td class="n">${sg(x.mirror, 2)}</td><td class="n">${sg(x.composer, 2)}</td><td${cls(x.diff_bps)}>${bp(x.diff_bps)}</td><td class="note">${x.cause || '–'}</td></tr>`).join('') + '</tbody>';
  $('tbEng').innerHTML = `<thead><tr><th>Engine</th><th class="n">Same holdings</th><th class="n">Mirror</th><th class="n">Composer</th><th class="n">Gap</th><th class="n">Gap without the stretch</th><th class="n">Before costs</th><th class="n">Mean, bps a day</th><th class="n">SD</th><th class="n">Costs, % a year</th><th class="n">Turnover a year</th><th class="n">Idle cash</th></tr></thead><tbody>` +
    ENG.map(e => { const x = D.eng[e], d = D.dec[e]; return `<tr><td>${e}</td><td class="n">${d.agree} / ${d.n}</td><td class="n">${sg(x.t.cum_mirror)}</td><td class="n">${sg(x.t.cum_composer)}</td><td${cls(x.t.cum_gap)}>${sg(x.t.cum_gap, 2)}</td><td${cls(x.tx.cum_gap)}>${sg(x.tx.cum_gap, 2)}</td><td${cls(x.tg.cum_gap)}>${sg(x.tg.cum_gap, 2)}</td><td${cls(x.t.mean_bps)}>${bp(x.t.mean_bps, 2)}</td><td class="n">${f2(x.t.sd_bps)}</td><td class="n">${(x.costs.drag_bps_yr / 100).toFixed(2)}</td><td class="n">${x.costs.turnover_venue_x_yr.toFixed(0)}x</td><td class="n">${pc(x.cash.mean_share_invested, 2)}</td></tr>`; }).join('') + '</tbody>';
  const nf = D.noise.all;
  $('pWorst').textContent = `On days neither side traded the difference still has an SD of ${nf.sd == null ? '–' : nf.sd.toFixed(1)} bps (${nf.n} engine-days): Composer's snapshot marks against official closes. That is the floor of this comparison.`;
}

// ---------- collapsed: limit buys and distributions
function drawCost(){
  const U = C.unfilled, dist = C.distributions, L = D.sens.limit;
  $('sCost').textContent = ` ${U.unfilled_orders} of ${U.buy_orders} buys unfilled; ${usd(dist.credited_usd)} credited, ${usd(dist.leaked_usd)} left unallocated`;
  $('tbUnf').innerHTML = D.unfilled.length ? `<thead><tr><th>Day</th><th>Buy</th><th>Sleeve</th><th class="n">Reference</th><th class="n">Limit</th><th class="n">Fill bar</th><th class="n">Over the limit, bps</th><th class="n">Dollars</th><th>While it kept working</th></tr></thead><tbody>` +
    D.unfilled.map(u => `<tr><td class="n">${u.date}</td><td>${u.qty} ${u.symbol}</td><td>${Object.keys(u.asks).join(', ')}</td><td class="n">${f2(u.ref)}</td><td class="n">${f2(u.limit)}</td><td class="n">${f2(u.px)}</td><td class="n">${bp(u.over_limit_bps)}</td><td class="n">${usd(u.usd)}</td><td>${u.later ? `at or under the limit by ${u.later.at} (${f2(u.later.px)})` : 'never back under the limit before 15:59'}</td></tr>`).join('') + '</tbody>'
    : '<tbody><tr><td>No buy was left unfilled.</td></tr></tbody>';
  const bm = U.by_decision_minute;
  $('pUnf').textContent = `A buy's limit is the ${D.core.decide}:00 reference price plus ${pc(D.core.buy_cushion)}, floored to the cent; it fills only if the bar ending a minute later closes at or under it. ` +
    `Cost of the rule in this run: ${bp(L.unfilled_cost_bps)} bps of the book over the window against filling regardless, ${bp(L.vs_requoted_bps)} against a limit re-quoted at the fill, which is what the live executor does after its sells. ` +
    `One small miss is luck: at the other decision minutes ` + Object.entries(bm).filter(([k]) => k !== D.core.decide).map(([k, v]) => `${k} left ${v.unfilled_orders} of ${v.buy_orders} unfilled (largest ${usd(v.largest_usd)}, SD of the daily difference ${f2(v.sd_bps)} bps against ${f2(v.sd_bps_every_buy_fills)} when every buy fills)`).join('; ') +
    `. A missed buy leaves its sleeve in cash until the next session's plan; nothing retries it. The simulator's test is stricter than live (one bar, a limit set a minute early).`;
  $('tbDiv').innerHTML = `<thead><tr><th>Engine</th><th class="n">Entitled</th><th class="n">Credited on the pay date</th><th class="n">Left unallocated</th><th class="n">Still owed</th><th class="n">Composer books inside, by its observed pay lags</th><th class="n">Composer leaves in account cash</th><th class="n">Rule "holder" credits</th></tr></thead><tbody>` +
    ENG.map(e => { const x = D.eng[e].dist, h = D.eng[e].holder; return `<tr><td>${e}</td><td class="n">${usd(x.accrued_usd)}</td><td class="n">${usd(x.credited_usd)}</td><td class="n">${usd(x.leaked_usd)}</td><td class="n">${usd(x.open_usd)}</td><td class="n">${usd(x.observed_in_symphony_usd)}</td><td class="n">${usd(x.observed_account_cash_usd + x.observed_ambiguous_usd)}</td><td class="n">${usd(h.credited_usd)}</td></tr>`; }).join('') +
    `<tr><td><b>Book</b></td><td class="n">${usd(dist.accrued_usd)}</td><td class="n">${usd(dist.credited_usd)}</td><td class="n">${usd(dist.leaked_usd)}</td><td class="n">${usd(dist.open_usd)}</td><td class="n">${usd(dist.observed_in_symphony_usd)}</td><td class="n">${usd(dist.observed_account_cash_usd + dist.observed_ambiguous_usd)}</td><td class="n">${usd(D.sens.rule.holder.dist.credited_usd)}</td></tr></tbody>`;
  const ev = ENG.flatMap(e => D.eng[e].events.map(x => Object.assign({e}, x)));
  const same = ev.filter(x => (x.core === 'credited') === (x.treatment === 'HELD_THROUGH')).length;
  const odd = ev.filter(x => (x.core === 'credited') !== (x.treatment === 'HELD_THROUGH'));
  $('pDiv').textContent = `Rule "composer", the executor's default: a dividend is a receivable for the sleeve that held the payer at the close before the ex-date, credited on the first session on or after the pay date only if the sleeve still holds it. ` +
    `${same} of ${ev.length} entitlements land where Composer's own observed pay lags put them` +
    (odd.length ? `; not ${odd.map(x => `${x.e}'s ${x.ticker} ex ${md(x.ex)} (${usd(x.usd)}: the core ${x.core === 'credited' ? 'credits it, held again on the pay date after a sale' : 'leaves it out'}; the observed lag says ${x.treatment === 'HELD_THROUGH' ? 'inside the symphony' : 'account cash'})`).join(', ')}` : '') +
    `. Rule "holder" would credit all of it and move the gap by ${bp(D.sens.rule.holder_minus_composer_bps)} bps over the window. ` +
    `Entitled: ${(dist.accrued_bps_yr / 100).toFixed(2)}% of the book a year.`;
  $('tbEv').innerHTML = `<thead><tr><th>Ex-date</th><th>Pay date</th><th>Engine</th><th>Fund</th><th class="n">Dollars</th><th class="n">bps of the sleeve</th><th>The core</th><th>Composer, by its observed lag</th></tr></thead><tbody>` +
    ev.sort((a, b) => a.ex < b.ex ? -1 : a.ex > b.ex ? 1 : 0).map(x => `<tr><td class="n">${x.ex}</td><td class="n">${x.pay || '–'}</td><td>${x.e}</td><td>${x.ticker}</td><td class="n">${usd(x.usd)}</td><td class="n">${x.bps.toFixed(0)}</td><td>${x.core || '–'}${x.settled ? ' ' + md(x.settled) : ''}</td><td>${x.treatment === 'HELD_THROUGH' ? 'inside the symphony' + (x.credit_on ? ' ' + md(x.credit_on) : '') : x.treatment === 'LEAKED' ? 'account cash' : 'unknown lag'}</td></tr>`).join('') + '</tbody>';
}

// ---------- collapsed: KMLM
const LEG = {long: ['3x long tech', 'var(--s1)'], half: ['half 3x long, half SVIX', 'var(--s3)'], inverse: ['3x inverse', 'var(--s2)'], bonds: ['bonds', 'var(--ctx)'], vol: ['long volatility', 'var(--s4)'], other: ['other', 'var(--ctx2)']};
function drawK(){
  const K = D.kmlm, apart = K.filter(k => k.dist != null && k.dist > 0.03).length, tr = K.filter(k => k.a === 'trade').length;
  $('sKmlm').textContent = ` ${D.dec.KMLM.agree} of ${D.dec.KMLM.n} sessions the same; the mirror rebalanced on ${tr} of ${K.length}`;
  const host = $('kmlm'); host.innerHTML = '';
  if (!host.getBoundingClientRect().width) return;
  const Wd = width(host), H = 96, m = {l: 74, r: 8, t: 6, b: 20}, cw = (Wd - m.l - m.r) / K.length;
  const svg = el('svg', {viewBox: `0 0 ${Wd} ${H}`, role: 'img', 'aria-label': 'What the 75% leg of KMLM is in, the mirror and Composer, session by session'}, host);
  [['mirror', 'mc', 'm'], ['Composer', 'cc', 'c']].forEach(([n, k, wk], r) => { const y = m.t + r * 28;
    el('text', {x: m.l - 8, y: y + 15, 'text-anchor': 'end', class: 'lb'}, svg, n);
    K.forEach((x, i) => { if (!x[k]) return; const c = el('rect', {x: m.l + i * cw + 0.5, y, width: Math.max(1, cw - 1), height: 22, fill: LEG[x[k]][1], rx: 1.5}, svg);
      c.addEventListener('mousemove', ev => tip(ev, `<b>${x.d}</b><br>mirror ${fw(x.m)}${x.a === 'hold' ? ' (held' + (x.gap != null ? `, gap ${(x.gap * 100).toFixed(1)}pp` : '') + ')' : ''}<br>Composer ${fw(x.c)}`)); c.addEventListener('mouseleave', untip); }); });
  K.forEach((x, i) => { if (x.dist != null && x.dist > 0.03) el('rect', {x: m.l + i * cw + 0.5, y: m.t + 60, width: Math.max(1, cw - 1), height: 5, fill: 'var(--neg)'}, svg); });
  el('text', {x: m.l - 8, y: m.t + 66, 'text-anchor': 'end', class: 'ax'}, svg, 'apart');
  monthTicks(svg, i => m.l + (i + 0.5) * cw, H - 4, 0, S.length - 1);
  legend('lgK', [...new Set(K.flatMap(k => [k.mc, k.cc]).filter(Boolean))].map(c => LEG[c]).concat([['holdings more than 3% apart', 'var(--neg)']]));
  const ep = D.episodes;
  $('pKmlm').textContent = `KMLM rebalances only when an asset's invested weight is more than 10pp from its target; the core now reads that on invested weights, as Composer does, and trades a sleeve idling over ${pc(D.core.max_idle_cash_frac, 0)} in cash. ` +
    (ep.length ? `${apart} session${apart === 1 ? '' : 's'} apart, in ${ep.length} run${ep.length === 1 ? '' : 's'}: ` + ep.map(x => `${md(x.start)}${x.end !== x.start ? ' to ' + md(x.end) : ''} (${x.classes.map(c => NAMES[c] || c).join(', ')}; ${bp(x.cost_bps, 0)} bps on the days that followed)`).join('; ') + '.' : 'No session apart.');
}

// ---------- collapsed: candidate edge
function drawE(){
  const E = D.edge, s = E.summary, c = s['16:00'], m55 = s['15:55'];
  $('sEdge').textContent = c ? ` filling at the close instead of ${E.base}: ${bp(c.mean)} bps per rotation (n ${c.n}, t ${f2(c.t)}); placebo ${bp(c.placebo.mean)}` : '';
  const host = $('edge'); host.innerHTML = '';
  if (!host.getBoundingClientRect().width || !c) return;
  const Wd = width(host), H = 190, m = {l: 42, r: 16, t: 10, b: 24}, X = i => m.l + i / (E.minutes.length - 1) * (Wd - m.l - m.r);
  const svg = el('svg', {viewBox: `0 0 ${Wd} ${H}`, role: 'img', 'aria-label': 'Mean gain of filling at each minute instead of 15:53, with the placebo'}, host);
  const vals = E.minutes.flatMap(x => [s[x].mean, s[x].placebo.mean]); let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const step = niceStep((hi - lo) || 1, 4); lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
  const Y = v => m.t + (hi - v) / (hi - lo) * (H - m.t - m.b);
  for (let v = lo; v <= hi + 1e-9; v += step) { el('line', {x1: m.l, x2: Wd - m.r, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? 'var(--axis)' : 'var(--grid)'}, svg); el('text', {x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, (v > 0 ? '+' : '') + v); }
  E.minutes.forEach((x, i) => { if (i % 2 === 0 || Wd > 560) el('text', {x: X(i), y: H - 6, 'text-anchor': 'middle', class: 'ax'}, svg, x === '16:00' ? 'close' : x); });
  [['placebo', 'var(--ctx2)', x => s[x].placebo.mean], ['actual', 'var(--s1)', x => s[x].mean]].forEach(([n, col, f]) => {
    el('path', {d: E.minutes.map((x, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(f(x)).toFixed(1)).join(''), fill: 'none', stroke: col, 'stroke-width': 2, 'stroke-linejoin': 'round'}, svg);
    E.minutes.forEach((x, i) => { const p = el('circle', {cx: X(i), cy: Y(f(x)), r: 4, fill: col, stroke: 'var(--surface)', 'stroke-width': 2}, svg);
      const h = el('circle', {cx: X(i), cy: Y(f(x)), r: 12, fill: 'transparent'}, svg);
      h.addEventListener('mousemove', ev => tip(ev, `<b>${x === '16:00' ? 'the close' : x}</b> instead of ${E.base}<br>actual ${bp(s[x].mean)} bps (t ${f2(s[x].t)}, n ${s[x].n})<br>placebo ${bp(s[x].placebo.mean)} bps (t ${f2(s[x].placebo.t)})<br>by day: t ${f2(s[x].by_day_mean.t)} (${s[x].by_day_mean.n} days)`)); h.addEventListener('mouseleave', untip); }); });
  legend('lgE', [['rotation days: gain of filling at that minute instead of ' + E.base + ', bps of the sleeve', 'var(--s1)', 1], ['placebo: the same weights on the previous session', 'var(--ctx2)', 1]]);
  $('tbEdge').innerHTML = `<thead><tr><th>Fill at</th><th class="n">Mean, bps of the sleeve</th><th class="n">t</th><th class="n">t, one observation a day</th><th class="n">Without the 3 largest</th><th class="n">Per dollar traded, bps</th><th class="n">Placebo</th><th class="n">Placebo t</th></tr></thead><tbody>` +
    ['15:50', '15:55', '15:56', '15:58', '15:59', '16:00'].filter(x => s[x]).map(x => `<tr><td>${x === '16:00' ? 'the close' : x}${x === '15:55' ? ' (the mirror)' : ''}</td><td${cls(s[x].mean)}>${bp(s[x].mean, 2)}</td><td class="n">${f2(s[x].t)}</td><td class="n">${f2(s[x].by_day_mean.t)}</td><td${cls(s[x].without_top3.mean)}>${bp(s[x].without_top3.mean, 2)}</td><td${cls(s[x].per_traded_bps.mean)}>${bp(s[x].per_traded_bps.mean, 2)}</td><td${cls(s[x].placebo.mean)}>${bp(s[x].placebo.mean, 2)}</td><td class="n">${f2(s[x].placebo.t)}</td></tr>`).join('') + '</tbody>';
  const LR = E.later, l56 = LR['+2'], lc = LR['close'];
  $('tbEdge2').innerHTML = `<thead><tr><th>The ${D.core.decide} decisions, filled at</th><th class="n">Gap</th><th class="n">Gap without the stretch</th><th class="n">Against the 15:55 fill, bps of the book</th><th class="n">Mean, bps a day</th><th class="n">SD</th><th class="n">Same holdings</th></tr></thead><tbody>` +
    Object.values(LR).map(x => `<tr><td>${x.fill_et === 'close' ? 'the close' : 'the bar ending ' + x.fill_et}</td><td${cls(x.cum_gap)}>${sg(x.cum_gap, 2)}</td><td${cls(x.cum_gap_ex)}>${sg(x.cum_gap_ex, 2)}</td><td${cls(x.vs_first_bps)}>${bp(x.vs_first_bps, 0)}</td><td${cls(x.mean_bps)}>${bp(x.mean_bps, 2)}</td><td class="n">${f2(x.sd_bps)}</td><td class="n">${x.agree}</td></tr>`).join('') + '</tbody>';
  const F = D.fills, near = F ? ['15:52', '15:53'].reduce((a, k) => a + (F.by_minute[k] || 0), 0) : null;
  $('nEdge').innerHTML = [
    `What it is: on the ${E.n} engine-days Composer rotated (${E.days} sessions), what Composer bought was on average cheaper later in the last ten minutes than at ${E.base}, its usual fill minute${F ? ` (${near} of its ${F.n} recorded fills are at 15:52 or 15:53)` : ''}.`,
    `Size: ${bp(c.mean)} bps of the sleeve per rotation by the close (t ${f2(c.t)}; ${f2(c.by_day_mean.t)} with one observation a day; ${bp(c.without_top3.mean)} without the three largest). The mirror's own minute, 15:55, is worth ${bp(m55.mean)} (t ${f2(m55.t)}).`,
    `Placebo, the same weights a session earlier: ${bp(c.placebo.mean)} bps (t ${f2(c.placebo.t)}). The sign differs, but neither clears two standard errors.`,
    `Against the mirror's own minute: on those rotation days a fill at 15:56 instead of 15:55 was worth ${bp(E.vs_mirror['15:56'].actual.mean)} bps of the sleeve (t ${f2(E.vs_mirror['15:56'].actual.t)}; ${f2(E.vs_mirror['15:56'].actual.by_day.t)} with one observation a day; placebo ${bp(E.vs_mirror['15:56'].placebo.mean)}, t ${f2(E.vs_mirror['15:56'].placebo.t)}), at the close ${bp(E.vs_mirror['16:00'].actual.mean)} (t ${f2(E.vs_mirror['16:00'].actual.t)}).`,
    `In the simulator, with the mirror's own ${P0.decide} decisions and every buy filled: the bar ending 15:56 instead of 15:55 moves the book's gap by ${bp(l56.vs_first_bps, 0)} bps over the window, the close by ${bp(lc.vs_first_bps, 0)} (second table; one path, ${W.sessions} sessions, no standard error).`,
    `What it would take to use: the decision stays at ${P0.decide}:00; only the executor's order time moves (a minute or more later, still ahead of its 15:59 cancel). First a forward test fixed in advance, alternating the order time by session, measured on real fills. One window, bar closes and no spread are not enough to move it on.`
  ].map(x => `<li>${x}</li>`).join('');
}

// ---------- collapsed: sensitivities
function drawSens(){
  const X = D.sens, row = (lab, h, note) => `<tr><td class="lab">${lab}</td><td class="n">${h.dec.agree} / ${h.dec.n}</td><td${cls(h.book.cum_gap)}>${sg(h.book.cum_gap, 2)}</td><td${cls(h.ex.cum_gap)}>${sg(h.ex.cum_gap, 2)}</td><td${cls(h.gross_ex.cum_gap)}>${sg(h.gross_ex.cum_gap, 2)}</td><td class="n">${f2(h.book.sd_bps)}</td><td class="n">${(h.costs.drag_bps_yr / 100).toFixed(2)}</td><td class="note">${note}</td></tr>`;
  const base = {dec: D.dec.ALL, book: T, ex: TX, gross_ex: B.tgx, costs: B.costs};
  $('sSens').textContent = ` slippage 0 to 5 bps moves the gap from ${sg(X.slip['0'].book.cum_gap)} to ${sg(X.slip['5'].book.cum_gap)}`;
  $('tbSens').innerHTML = `<thead><tr><th>Change to the ${P0.decide} run</th><th class="n">Same holdings</th><th class="n">Gap</th><th class="n">Without the stretch</th><th class="n">Before costs</th><th class="n">SD, bps</th><th class="n">Costs, % a year</th><th>What changes</th></tr></thead><tbody>` +
    row('None (the run above)', base, 'rule "composer", limit at the reference, 2 bps') +
    row('Slippage 0 bps', X.slip['0'], 'commission only') + row('Slippage 5 bps', X.slip['5'], '') +
    row('Dividend rule "holder"', X.rule.holder, `every entitlement credited: ${usd(X.rule.holder.dist.credited_usd)}`) +
    row('Buy limit re-quoted at the fill', X.limit.requote, `the live path; ${X.limit.requote.limit.unfilled_orders} unfilled`) +
    row('No buy limit', X.limit.none, `a buy fills whatever its bar; a sleeve's cash below zero on ${X.limit.none.overspent} sessions`) +
    row('Close mode, ledger gaps filled from the tree', X.gaps, 'decisions and fills at the close') + '</tbody>';
  const sd = X.seed, a = sd.runs['policy 29/29/27/15'], b = sd.runs["Composer's weights that day"];
  $('pSens').textContent = `Book mix, from ${sd.from}: seeded 29/29/27/15 the mirror is ${sg(a.vs_composer_own_book.cum_gap)} against Composer's own book (its real engine weights); seeded at Composer's weights that day (${ENG.map(e => Math.round(sd.composer_weights[e] * 100)).join(' / ')}) it is ${sg(b.vs_composer_own_book.cum_gap)}. The mix is an owner decision, not tracking error.`;
}

// ---------- collapsed: replay cross-checks
function drawReplay(){
  const R = D.replay, v = R.targets_vs_composer_holdings, X = D.cross;
  $('sReplay').textContent = ` ${R.engine_sessions - D.replay_n} of ${R.engine_sessions} engine-sessions identical on both replay paths` + (X.length ? `; ${X.filter(x => x.engines_same === 4).length} of ${X.length} sessions match the brain's own --at` : '');
  $('tbCross').innerHTML = X.length ? `<thead><tr><th>mirror_brain.py --at</th><th class="n">Engines with the same target</th><th class="n">Prices in both</th><th class="n">Identical</th><th class="n">Largest price difference</th><th>Dividends</th><th>Splits</th></tr></thead><tbody>` +
    X.map(x => x.error ? `<tr><td>${x.at}</td><td colspan="6">not run: ${x.error}</td></tr>` : `<tr><td>${x.at} ET</td><td class="n">${x.engines_same} / 4</td><td class="n">${x.prices.both}</td><td class="n">${x.prices.identical}</td><td class="n">${x.prices.largest_rel_diff == null ? '–' : (x.prices.largest_rel_diff * 1e4).toFixed(2) + ' bps' + (x.prices.largest_rel_diff > 0 ? ' (' + x.prices.largest_on + ')' : '')}</td><td>${x.dividends.same ? 'same ' + x.dividends.brain + ' rows' : `differ (${x.dividends.simulator} vs ${x.dividends.brain})`}</td><td>${x.splits.same ? 'same' : 'differ'}</td></tr>`).join('') + '</tbody>' : '';
  $('nReplay').innerHTML = [
    `The numbers on this page use the simulator's own history path: the brain's build, pinned at ${D.core.decide}:00, fed FMP's traded 1-minute bars from a cache and Yahoo's daily history as it stood on the replayed day (nothing after it, rebased), with FMP's dividend and split lists applied as the brain applies them.`,
    `Against the brain's own offline path (history as fetched today, the minute price scaled by the day's factor): ${D.replay_n} of ${R.engine_sessions} engine-sessions give a different target${D.replay_n ? ' (' + D.replay_differ.map(x => `${x.engine} ${md(x.date)}`).join(', ') + ')' : ''}; the largest price difference is ${(R.largest_price_difference.rel * 1e4).toFixed(2)} bps.`,
    `Targets against Composer's holdings on the engine-sessions it rebalanced: ${v.as_of.same_or_within_3pct} of ${v.as_of.of} within 3% on this page's path and ${v.as_fetched.same_or_within_3pct} of ${v.as_fetched.of} on the brain's (${v.as_of.same} by the shadow runner's tighter 1.5% test for KMLM).`,
    X.length ? `The table is the brain's own command line, run live (its own Yahoo and FMP fetch) against the simulator's payload for the same instant.` : `No live cross-check was run for this file.`
  ].map(x => `<li>${x}</li>`).join('');
}

// ---------- collapsed: basis and limits
$('nBasis').innerHTML = [
  `Basis: each sleeve's booked return (equity as the executor's core books it, dividend credits included on the day they settle) against Composer's deposit-adjusted value. On a price-only basis the gap is ${sg(B.tp.cum_gap, 2)} (${sg(B.tpx.cum_gap, 2)} without the stretch).`,
  `The book compares both sides at the mirror's sleeve weights, so the difference is tracking, not allocation. Marked at official closes (measurement basis: mark-to-market, daily).`,
  `Code under test: ibkr-executor/app/mirror_core.py, unchanged, called in the executor's order (splits, receivables, settlement, plan, crosses, sells, transfers, buys sized at their limit, finish). After every session the book was checked against an independently kept account and its cash reconciled: ${B.problems.length} problems, ${B.overspent.length} sessions with a sleeve's cash below zero.`,
  `Decision: mirror_brain.build pinned at ${D.core.decide}:00 ET on every session, no attestation (the approved trees). ${D.info.unavailable.length} sessions had an engine without a decision${D.info.unavailable.length ? ' (HARV before its first approved tree, ' + md(D.info.unavailable[0].date) + ' to ' + md(D.info.unavailable[D.info.unavailable.length - 1].date) + ')' : ''}.`,
  `Limit buys in the simulator are stricter than live: the limit is set off the ${D.core.decide}:00 price and tested against one bar; the executor re-quotes after its sells and leaves the order working until 15:59.`,
  `Events: Yahoo's chart events union FMP's dividend and split lists (${D.events.dividends_in_window} dividends in the window, ${D.events.fmp_only.length} listed by FMP only, ${D.events.without_pay_date} without a pay date). The split path ran ${D.splits_applied} times (no fund the book held split in the window); it is covered by tests only.`,
  `Not modelled: the bid-ask spread beyond the ${D.slip_bps} bps assumed, partial fills, exchange and regulatory fees, market impact, borrow, taxes, the executor's venue-quote band, halts, and a brain or feed outage.`,
  `Composer's record: ${Object.entries(W.composer_snapshots).map(([e, n]) => `${e} ${n}`).join(', ')} closing snapshots of ${W.sessions} sessions. A deposit or transfer day is in Composer's deposit-adjusted figure as it reports it.`,
  `The no-rebalance stretch: on ${W.no_rebalance.map(md).join(', ')} Composer made no rebalance attempt and the mirror followed the logic. The stretch is shown, and every total is given with and without it.`,
  `Generated ${D.generated} by composer/research/mirror/parity_study.py; deterministic from its cache.`
].map(x => `<li>${x}</li>`).join('');

// ---------- draw, redraw on resize and when a section opens
const LAZY = {dRuns: drawRuns, dMiss: drawMiss, dWorst: drawWorst, dCost: drawCost, dKmlm: drawK, dEdge: drawE, dSens: drawSens, dReplay: drawReplay};
function drawAll(){ drawA(); drawB(); drawC(); Object.values(LAZY).forEach(f => f()); }
Object.entries(LAZY).forEach(([id, f]) => $(id).addEventListener('toggle', () => { if ($(id).open) f(); }));
drawAll();
let rz, lastW = innerWidth;      // a phone fires resize while it scrolls (its toolbar hides): redraw only when the width changed
addEventListener('resize', () => { if (innerWidth === lastW) return; lastW = innerWidth; clearTimeout(rz); rz = setTimeout(drawAll, 120); });
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
