#!/usr/bin/env python3
"""Exhibit for results.md addendum 50: the shadow runner's decision-time check on FMP 1-minute prices.
Reads results/shadow-minutes-2026-11-01.json (minutes_calib.py) and the frozen 2026-10-30 inputs
(scripts/tests/fixtures/shadow-minutes-2026-10-30.json.gz); writes results/shadow-minutes-2026-11-01.html."""
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import shadow_runner as sr  # noqa: E402

RES = os.path.join(HERE, "..", "..", "results")
SRC = os.path.join(RES, "shadow-minutes-2026-11-01.json")
FX = os.path.join(HERE, "..", "..", "scripts", "tests", "fixtures", "shadow-minutes-2026-10-30.json.gz")
PAGE = os.path.join(RES, "shadow-minutes-2026-11-01.html")
BASES = ["fmp-1m", "yahoo-5m", "search", "mismatch"]


def basis(label):
    if label.startswith("knife-edge ("):
        return label[len("knife-edge ("):-1]
    return label


def main():
    r = json.load(open(SRC))
    with gzip.open(FX) as f:
        fx = json.load(f)
    man = sr.load_manifest()
    era = next(e for e in man["HARV"]["eras"] if e["version"] == fx["era"])
    tree, d = sr.load_tree(era), fx["date"]
    sim, target, _ = sr.run_engine(fx["prices"], tree, d)
    lo, hi = 0.0, 0.003                                    # SPY above its close that turns HARV to 52/48
    for _ in range(40):
        mid = (lo + hi) / 2
        if sr.distance(sim.what_if(tree, d, "SPY", mid), fx["composer"])[0] < 0.01:
            hi = mid
        else:
            lo = mid
    close = fx["prices"]["SPY"][d]
    spy = fx["minutes"]["SPY"]
    pts = [{"t": sr._hm(sr._min(k) + 1), "c": v} for k, v in sorted(spy.items(), key=lambda kv: sr._min(kv[0]))
           if "15:30" <= k <= "15:59"]                     # price at the end of each minute
    snaps = [[hh, sr.minute_price(spy, hh)] for hh in sr.decision_times()]
    nonagree = [x for x in r["rows"] if x["old"] != "agree" or x["new"] != "agree"]
    evid = {k: {b: sum(1 for x in nonagree if basis(x[k]) == b) for b in BASES} for k in ("old", "new")}
    plc = {k: {b: v for b, v in ((basis(lb), n) for lb, n in r["placebo"][k].items()) if b in BASES} for k in ("old", "new")}
    exc = {k: sum(v for b, v in plc[k].items() if b != "mismatch") for k in plc}
    wrong = r["placebo"]["pairs"] - r["placebo"]["old"].get("agree", 0)
    data = {"pts": pts, "thr": round(close * (1 + hi), 2), "close": round(close, 2), "snaps": snaps,
            "evid": evid, "plc": plc, "exc": exc, "wrong": wrong, "pairs": r["placebo"]["pairs"],
            "agree_pairs": r["placebo"]["old"].get("agree", 0), "n_rows": len(r["rows"]), "n_nonagree": len(nonagree),
            "changed": [x for x in nonagree if x["old"] != x["new"] or x["new"] != "agree"],
            "sessions": r["sessions"], "n_sessions": r["n_sessions"], "window": [r["window"][0], r["window"][-1]],
            "placebo_changed": r["placebo"]["changed"], "profile": [x for x in r["profile"] if x["t"] >= "15:40"],
            "windows": r["windows"], "not_wrong": r["placebo_not_wrong"]}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(PAGE, "w") as f:
        f.write(html)
    print("wrote", PAGE, f"({len(html) // 1024} KB); threshold {data['thr']}")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shadow runner minutes</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#8c63c9;--band:rgba(42,120,214,.12);--crit:#d03b3b;--code:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#9a72d6;--band:rgba(57,135,229,.16);--code:#232321}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#9a72d6;--band:rgba(57,135,229,.16);--code:#232321}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:650}h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub-h{color:var(--ink2);margin:0 0 12px;font-size:14px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px;margin:0 0 16px;min-width:0}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0 16px}
@media (max-width:760px){.kpis{grid-template-columns:1fr}}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:22px;font-weight:650}.kpi span{color:var(--ink2);font-size:13px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 8px;font-size:13px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}.sw{display:inline-block;width:14px;height:12px;border-radius:3px}
svg{display:block;width:100%;height:auto}.chartwrap{overflow-x:auto}.chartwrap svg{min-width:680px}.ax,.ax text{fill:var(--muted);font-size:11px}.lb{fill:var(--ink2);font-size:12px}.lbb{fill:var(--ink);font-size:12px;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--grid)}
thead th{color:var(--ink2);font-weight:600;font-size:12.5px}.tablewrap{overflow-x:auto}
.notes{font-size:13.5px;color:var(--ink2)}.notes li{margin:3px 0}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:6px 9px;font-size:13px;display:none;z-index:5}
</style>
</head>
<body>
<main>
<h1>Shadow runner: checking Composer's decision minute by minute</h1>
<p class="sub-h">When the approved logic on closing prices disagrees with what Composer bought, the runner asks whether the logic, re-run on prices from Composer's decision window, gives what Composer holds (a knife-edge). It used to try three 5-minute snapshots from Yahoo; it now tries every minute from 15:50 to 15:55 on FMP 1-minute bars, with the old checks as fallbacks. The window is measured, not assumed: Composer's holdings match the logic best at 15:54.</p>
<div class="kpis" id="kpis"></div>

<section class="card">
<h2>Friday 10-30: the decision fell between the snapshots</h2>
<p class="sub-h">SPY, price at the end of each minute (FMP). Above the red line, HARV's and KMLM's approved logic gives exactly the 52/48 ZVOL/PULS split Composer bought. The three 5-minute snapshots (black) were all below it, so the old check reported two mismatches. In the window, only the 15:54 minute (red) is above it.</p>
<div class="chartwrap"><svg id="fri" role="img" aria-label="SPY one-minute prices 15:30-16:00 on 2026-10-30 against the 52/48 threshold"></svg></div>
</section>

<section class="card">
<h2>Where Composer's decision prices sit</h2>
<p class="sub-h">For each minute, the approved logic re-run on that minute's prices, against what Composer bought: how many of the 272 engine-sessions it contradicts. 15:54 contradicts one. The shaded window, 15:50-15:55, is the 15:51-15:54 low a minute either side.</p>
<div class="chartwrap"><svg id="prof" role="img" aria-label="Bars: engine-sessions the logic at each minute 15:40-16:00 contradicts"></svg></div>
<div class="tablewrap" style="margin-top:10px"><table id="win"></table></div>
</section>

<section class="card">
<h2>Every disagreement since July 15, by the evidence that settled it</h2>
<p class="sub-h">Engine-sessions where the logic on closing prices differed from Composer's holdings, old rule vs new. "Search" means no price data, only a hypothetical one-ticker move within 0.3 sigma.</p>
<div class="legend" id="lg"></div>
<div class="chartwrap"><svg id="evid" role="img" aria-label="Stacked bars: evidence basis of the disagreements under the old and new rules"></svg></div>
</section>

<section class="card">
<h2>The control: deliberately wrong pairs</h2>
<p class="sub-h">The logic on one session against Composer's holdings from another (the day before, after, or five sessions later) where those holdings differ. Every one should be a mismatch; each one excused as a knife-edge is a way a real error could hide.</p>
<div class="chartwrap"><svg id="plc" role="img" aria-label="Bars: wrong pairs excused under the old and new rules"></svg></div>
</section>

<section class="card">
<h2>Sessions whose classification changed</h2>
<div class="tablewrap"><table id="tbl"></table></div>
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
const COL = {'fmp-1m': 'var(--s1)', 'yahoo-5m': 'var(--s3)', 'search': 'var(--s4)', 'mismatch': 'var(--crit)'};
const NAME = {'fmp-1m': 'knife-edge on FMP 1-minute prices', 'yahoo-5m': 'knife-edge on Yahoo 5-minute snapshots', 'search': 'knife-edge by one-ticker search (no prices)', 'mismatch': 'mismatch (alert)'};
const ev = D.evid;
[[`${ev.old.mismatch} → ${ev.new.mismatch}`, `mismatch alerts among the ${D.n_nonagree} disagreements since ${D.sessions[0].slice(5)}: Friday's two were knife-edges at 15:54`],
 [`${ev.old['yahoo-5m'] + ev.old['fmp-1m']} → ${ev.new['fmp-1m'] + ev.new['yahoo-5m']}`, `of the ${D.n_nonagree} explained on actual decision-time prices rather than a hypothetical move (${ev.new.search} left to the search)`],
 [`${D.exc.old} → ${D.exc.new}`, `of ${D.wrong} deliberately wrong pairs excused as knife-edges: the minute check is stricter than the search it replaces`]]
 .forEach(([b, s]) => { const k = document.createElement('div'); k.className = 'kpi'; k.innerHTML = `<b>${b}</b><span>${s}</span>`; document.getElementById('kpis').appendChild(k); });

(function(){
  const svg = document.getElementById('fri'), W = 900, H = 320, l = 50, r = 160, t = 12, b = 28, m = s => +s.slice(0, 2) * 60 + +s.slice(3);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const vals = D.pts.map(p => p.c).concat([D.thr]), lo = Math.floor(Math.min(...vals)) - .5, hi = Math.ceil(Math.max(...vals)) + .3;
  const X = s => l + (m(s) - m('15:30')) / 30 * (W - l - r), Y = v => t + (hi - v) / (hi - lo) * (H - t - b);
  for (let v = Math.ceil(lo); v <= hi; v++) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, v); }
  ['15:30', '15:40', '15:45', '15:50', '15:55', '16:00'].forEach(s => el('text', {x: X(s), y: H - 8, 'text-anchor': 'middle', class: 'ax'}, svg, s));
  el('rect', {x: X(D.window[0]), y: t, width: X(D.window[1]) - X(D.window[0]), height: H - t - b, fill: 'var(--grid)', opacity: .45}, svg);
  el('text', {x: X(D.window[0]) + 4, y: t + 12, class: 'lb'}, svg, `minute window ${D.window[0]}-${D.window[1]}`);
  el('polyline', {points: D.pts.map(p => `${X(p.t)},${Y(p.c)}`).join(' '), fill: 'none', stroke: 'var(--s1)', 'stroke-width': 2, 'stroke-linejoin': 'round'}, svg);
  el('line', {x1: l, x2: W - r, y1: Y(D.thr), y2: Y(D.thr), stroke: 'var(--crit)', 'stroke-width': 1.5, 'stroke-dasharray': '5 4'}, svg);
  el('text', {x: W - r + 6, y: Y(D.thr) + 4, class: 'lbb'}, svg, `${D.thr}: 52/48 above`);
  el('line', {x1: l, x2: W - r, y1: Y(D.close), y2: Y(D.close), stroke: 'var(--muted)', 'stroke-dasharray': '2 3'}, svg);
  el('text', {x: W - r + 6, y: Y(D.close) + 16, class: 'lb'}, svg, `close ${D.close}`);
  D.snaps.forEach(([s, v]) => { el('circle', {cx: X(s), cy: Y(v), r: 5, fill: 'var(--ink)', stroke: 'var(--surface)', 'stroke-width': 2}, svg);
    el('text', {x: X(s), y: Y(v) + 18, 'text-anchor': 'middle', class: 'lb'}, svg, `${s} ${v.toFixed(2)}`); });
  D.pts.filter(p => p.c >= D.thr && p.t >= D.window[0] && p.t <= D.window[1]).forEach(p => {
    el('circle', {cx: X(p.t), cy: Y(p.c), r: 5, fill: 'var(--crit)', stroke: 'var(--surface)', 'stroke-width': 2}, svg);
    el('text', {x: X(p.t), y: Y(p.c) - 10, 'text-anchor': 'middle', class: 'lbb'}, svg, `${p.t} ${p.c.toFixed(2)}`); });
  D.pts.forEach(p => { const z = el('rect', {x: X(p.t) - 7, y: t, width: 14, height: H - t - b, fill: 'transparent'}, svg);
    z.addEventListener('mousemove', e => tip(e, `<b>${p.t}</b> SPY ${p.c.toFixed(2)}${p.c >= D.thr ? '<br>logic: ZVOL 52 / PULS 48 (Composer)' : '<br>logic: ZVOL 60 / PULS 40'}`)); z.addEventListener('mouseleave', untip); });
})();

(function(){
  const BASES = ['fmp-1m', 'yahoo-5m', 'search', 'mismatch'];
  BASES.forEach(b => document.getElementById('lg').insertAdjacentHTML('beforeend', `<span><i class="sw" style="background:${COL[b]}"></i>${NAME[b]}</span>`));
  const svg = document.getElementById('evid'), W = 900, rowH = 46, l = 110, r = 280, H = 2 * rowH + 24;
  const SHORT = {'fmp-1m': 'FMP minutes', 'yahoo-5m': 'snapshots', 'search': 'search', 'mismatch': 'mismatch'};
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const tot = D.n_nonagree, sx = v => (W - l - r) * v / tot;
  [['old', 'old rule'], ['new', 'new rule']].forEach(([k, name], i) => {
    const y = 6 + i * rowH; let x = l;
    el('text', {x: l - 10, y: y + 20, 'text-anchor': 'end', class: 'lbb'}, svg, name);
    BASES.forEach(b => { const n = ev[k][b] || 0; if (!n) return;
      const w = sx(n);
      const rr = el('rect', {x: x, y: y + 4, width: Math.max(1, w - 2), height: 24, fill: COL[b]}, svg);
      rr.addEventListener('mousemove', e => tip(e, `<b>${name}</b><br>${NAME[b]}: ${n} of ${tot}`)); rr.addEventListener('mouseleave', untip);
      x += w; });
    el('text', {x: x + 8, y: y + 20, class: 'lb'}, svg, BASES.filter(b => ev[k][b]).map(b => `${ev[k][b]} ${SHORT[b]}`).join(' · '));
  });
  el('text', {x: l, y: H - 4, class: 'ax'}, svg, `${tot} engine-sessions, ${D.sessions[0]} to ${D.sessions[1]}`);
})();

(function(){
  const svg = document.getElementById('plc'), W = 900, rowH = 46, l = 110, r = 200, H = 2 * rowH + 24;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const max = Math.max(D.exc.old, D.exc.new, 1), sx = v => (W - l - r) * v / max;
  [['old', 'old rule'], ['new', 'new rule']].forEach(([k, name], i) => {
    const y = 6 + i * rowH; let x = l;
    el('text', {x: l - 10, y: y + 20, 'text-anchor': 'end', class: 'lbb'}, svg, name);
    ['fmp-1m', 'yahoo-5m', 'search'].forEach(b => { const n = D.plc[k][b] || 0; if (!n) return;
      const w = sx(n);
      const rr = el('rect', {x: x, y: y + 4, width: Math.max(1, w - 2), height: 24, fill: COL[b]}, svg);
      rr.addEventListener('mousemove', e => tip(e, `<b>${name}</b><br>${NAME[b]}: ${n} wrong pairs`)); rr.addEventListener('mouseleave', untip);
      x += w; });
    el('text', {x: x + 8, y: y + 20, class: 'lb'}, svg, `${D.exc[k]} of ${D.wrong} excused`);
  });
  el('text', {x: l, y: H - 4, class: 'ax'}, svg, `${D.pairs} pairs; ${D.agree_pairs} are not wrong pairs and are left out (${D.not_wrong['logic-equal'] || 0} equal the logic's own answer, ${D.not_wrong['kmlm-lenient'] || 0} sit inside KMLM's corridor)`);
})();

(function(){
  const svg = document.getElementById('prof'), W = 900, H = 230, l = 40, r = 12, t = 16, b = 30, P = D.profile;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const max = Math.max(...P.map(x => x.bad)) + 2, bw = (W - l - r) / P.length, Y = v => t + (1 - v / max) * (H - t - b);
  const iw = P.findIndex(x => x.t === D.window[0]), jw = P.findIndex(x => x.t === D.window[1]);
  el('rect', {x: l + iw * bw, y: t - 10, width: (jw - iw + 1) * bw, height: H - t - b + 10, fill: 'var(--band)'}, svg);
  el('text', {x: l + iw * bw + 4, y: t - 1, class: 'lb'}, svg, `window ${D.window[0]}-${D.window[1]}`);
  for (let v = 0; v <= max; v += 5) { el('line', {x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: 'var(--grid)'}, svg); el('text', {x: l - 6, y: Y(v) + 4, 'text-anchor': 'end', class: 'ax'}, svg, v); }
  P.forEach((x, i) => {
    const best = x.bad === Math.min(...P.map(y => y.bad));
    const rr = el('rect', {x: l + i * bw + 2, y: Y(x.bad), width: bw - 4, height: Y(0) - Y(x.bad), rx: 2, fill: best ? 'var(--s3)' : 'var(--s1)'}, svg);
    el('text', {x: l + i * bw + bw / 2, y: Y(x.bad) - 4, 'text-anchor': 'middle', class: best ? 'lbb' : 'ax'}, svg, x.bad);
    if (i % 2 === 0 || best) el('text', {x: l + i * bw + bw / 2, y: H - 10, 'text-anchor': 'middle', class: 'ax'}, svg, x.t);
    rr.addEventListener('mousemove', e => tip(e, `<b>${x.t}</b><br>the logic on this minute's prices contradicts Composer on ${x.bad} of ${x.n} engine-sessions`)); rr.addEventListener('mouseleave', untip);
  });
})();
document.getElementById('win').innerHTML = '<thead><tr><th>Window</th><th>Disagreements explained</th><th>Wrong pairs excused</th></tr></thead><tbody>' +
  Object.entries(D.windows).map(([k, v]) => `<tr><td>${k}</td><td>${v.explained} of ${v.of}</td><td>${v.placebo_excused} of ${v.placebo_of}</td></tr>`).join('') +
  `<tr><td>old rule (Yahoo snapshots, then the search)</td><td>${D.evid.old['yahoo-5m'] + D.evid.old.search} of ${D.n_nonagree}</td><td>${D.exc.old} of ${D.wrong}</td></tr></tbody>`;

document.getElementById('tbl').innerHTML = '<thead><tr><th>Session</th><th>Engine</th><th>Old rule</th><th>New rule</th><th>Composer held</th><th>Logic on closes</th></tr></thead><tbody>' +
  D.changed.map(x => `<tr><td>${x.date}</td><td>${x.engine}</td><td>${x.old}</td><td>${x.new}${x.new_time ? ' @' + x.new_time : ''}</td><td>${x.live}</td><td>${x.logic}</td></tr>`).join('') + '</tbody>';
[`Prices: FMP 1-minute bars (price at a minute = the close of the bar ending then; a fund with no trade that minute keeps its last trade, none older than 30 minutes), scaled onto Yahoo's adjusted series by the official close. Window ${D.window[0]}-${D.window[1]} ET, 10 to 5 minutes before the close (12:50-12:55 on a half-day). FMP's day is used only if SPY is complete (through the close and every window minute) and no dense feed stops early; otherwise the older checks decide and the row says why.`,
 `Old rule: Yahoo 5-minute snapshots at 15:45/15:50/15:55, available for the last ~60 sessions; before that, the one-ticker search within 0.3 sigma. New rule: FMP minutes, then the Yahoo snapshots, then the search.`,
 `Sessions: ${D.n_sessions} sessions with a committed holdings snapshot, ${D.sessions[0]} to ${D.sessions[1]} (the 10-26..28 no-rebalance sessions are judged on Composer's record and left out).`,
 `The control mostly measures the price source, not the window: the new rule excuses ${D.exc.new} of ${D.wrong} wrong pairs against ${D.exc.old} for the old one, because real minute prices replace the permissive search on older sessions. Across windows (table above) the excused count moves by one or two.`,
 `In-sample: the window was chosen from the profile on the same 69 sessions it is scored on, all summer-time full days. Composer does not publish its decision time.`]
 .forEach(s => document.getElementById('basis').insertAdjacentHTML('beforeend', `<li>${s}</li>`));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
