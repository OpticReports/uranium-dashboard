"""Render report.html -- the visual companion to RESEARCH.md.

Charts are hand-built inline SVG (no external libs; the artifact CSP blocks
CDNs). Palette is the validated diverging pair blue #2a78d6 / red #e34948.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from nfp_surprise_study import COVID_END, COVID_START, load  # noqa: E402

D = json.loads((HERE / "data" / "chart_data.json").read_text())
S = json.loads((HERE / "data" / "signal_results.json").read_text())
ROWS = load()
CORE = [r for r in ROWS if not (COVID_START <= r["rel"] <= COVID_END)]


def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


# ------------------------------------------------------- chart 1: timeline --
def chart_timeline() -> str:
    W, H = 1060, 320
    ml, mr, mt, mb = 52, 14, 18, 46
    pw, ph = W - ml - mr, H - mt - mb
    break_at = next(i for i, r in enumerate(CORE) if r["rel"].year >= 2022)
    slots = len(CORE) + 3                      # 3 blank slots for the COVID gap
    step = pw / slots
    bw = max(2.6, step * 0.62)
    lo, hi = -220.0, 350.0
    y0 = mt + ph * (hi / (hi - lo))

    def xi(i: int) -> float:
        return ml + (i + (3 if i >= break_at else 0)) * step + step / 2

    def yv(v: float) -> float:
        return mt + ph * ((hi - v) / (hi - lo))

    p = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" '
         f'aria-label="Payroll surprise versus consensus, each release 2013 to 2026">']
    p.append('<title>Actual minus consensus, thousands of jobs, per release</title>')
    for gv in (-200, -100, 0, 100, 200, 300):
        y = yv(gv)
        cls = "axis-zero" if gv == 0 else "grid"
        p.append(f'<line class="{cls}" x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}"/>')
        lab = "0" if gv == 0 else f"{gv:+d}"
        p.append(f'<text class="tick" x="{ml-9}" y="{y+3.5:.1f}" text-anchor="end">'
                 f'{lab}</text>')
    # COVID gap band
    gx0, gx1 = ml + break_at * step, ml + (break_at + 3) * step
    p.append(f'<rect class="gapband" x="{gx0:.1f}" y="{mt}" '
             f'width="{gx1-gx0:.1f}" height="{ph}"/>')
    p.append(f'<text class="gaplab" x="{(gx0+gx1)/2:.1f}" y="{mt+13}" '
             f'text-anchor="middle">2020–21</text>')
    p.append(f'<text class="gaplab" x="{(gx0+gx1)/2:.1f}" y="{mt+25}" '
             f'text-anchor="middle">excluded</text>')
    for i, r in enumerate(CORE):
        v = max(lo, min(hi, r["surprise"]))
        x, y = xi(i) - bw / 2, min(yv(v), y0)
        h = abs(yv(v) - y0)
        sign = "pos" if r["surprise"] > 0 else "neg"
        p.append(f'<rect class="bar {sign}" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                 f'height="{max(h,1.2):.1f}" rx="1.2"><title>{r["release"]} · '
                 f'consensus {r["consensus"]:.0f}k · actual {r["actual"]:.0f}k · '
                 f'surprise {r["surprise"]:+.0f}k</title></rect>')
    # era brackets
    eras = [(0, break_at - 1, "2013–2019   coin flip"),
            (break_at, len(CORE) - 1, "2022–2026")]
    for a, b, lab in eras:
        x1, x2 = xi(a) - bw / 2, xi(b) + bw / 2
        yb = mt + ph + 14
        p.append(f'<line class="bracket" x1="{x1:.1f}" y1="{yb}" x2="{x2:.1f}" y2="{yb}"/>')
        p.append(f'<text class="eralab" x="{(x1+x2)/2:.1f}" y="{yb+16}" '
                 f'text-anchor="middle">{esc(lab)}</text>')
    p.append(f'<text class="axtitle" x="{ml-9}" y="{mt-6}" text-anchor="end">k</text>')
    p.append("</svg>")
    return "".join(p)


# ------------------------------------------------------ chart 2: era rates --
def chart_eras() -> str:
    W, rowh, mt = 1060, 54, 26
    ml, mr = 210, 96
    H = mt + rowh * len(D["eras"]) + 34
    pw = W - ml - mr

    def x(p: float) -> float:
        return ml + (p - 0.30) / 0.55 * pw       # 30%..85% window

    p = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" '
         f'aria-label="Hit rate of betting above consensus, by era, with 95% intervals">']
    p.append("<title>Share of releases that beat consensus, by era</title>")
    for gv in (0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
        xx = x(gv)
        cls = "axis-zero" if abs(gv - 0.5) < 1e-9 else "grid"
        p.append(f'<line class="{cls}" x1="{xx:.1f}" y1="{mt-8}" x2="{xx:.1f}" y2="{H-30}"/>')
        p.append(f'<text class="tick" x="{xx:.1f}" y="{H-14}" text-anchor="middle">'
                 f'{gv*100:.0f}%</text>')
    p.append(f'<text class="coinflip" x="{x(0.5):.1f}" y="{mt-14}" text-anchor="middle">'
             f'coin flip</text>')
    for i, e in enumerate(D["eras"]):
        cy = mt + i * rowh + rowh / 2
        loo, hii = wilson(e["hits"], e["tot"])
        sig = e["p"] < 0.05
        cls = "pos" if sig else "null"
        p.append(f'<line class="ci {cls}" x1="{x(loo):.1f}" y1="{cy:.1f}" '
                 f'x2="{x(hii):.1f}" y2="{cy:.1f}"/>')
        for xe in (loo, hii):
            p.append(f'<line class="cicap {cls}" x1="{x(xe):.1f}" y1="{cy-6:.1f}" '
                     f'x2="{x(xe):.1f}" y2="{cy+6:.1f}"/>')
        p.append(f'<circle class="dot {cls}" cx="{x(e["rate"]):.1f}" cy="{cy:.1f}" r="6.5">'
                 f'<title>{esc(e["label"])}: {e["hits"]}/{e["tot"]} = '
                 f'{e["rate"]*100:.1f}% (95% CI {loo*100:.0f}–{hii*100:.0f}%), '
                 f'p={e["p"]:.3f}</title></circle>')
        p.append(f'<text class="rowlab" x="{ml-18}" y="{cy-2:.1f}" text-anchor="end">'
                 f'{esc(e["label"])}</text>')
        p.append(f'<text class="rowsub" x="{ml-18}" y="{cy+13:.1f}" text-anchor="end">'
                 f'n={e["tot"]} · p={e["p"]:.2f}</text>')
        p.append(f'<text class="rowval {cls}" x="{W-mr+14}" y="{cy+5:.1f}">'
                 f'{e["rate"]*100:.1f}%</text>')
    p.append("</svg>")
    return "".join(p)


# ---------------------------------------------------- chart 3: month ghost --
def chart_months() -> str:
    W, H = 1060, 250
    ml, mr, mt, mb = 52, 14, 22, 52
    pw, ph = W - ml - mr, H - mt - mb
    step = pw / 12
    bw = step * 0.56

    def y(p: float) -> float:
        return mt + ph * (1 - (p - 0.10) / 0.85)

    p = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" '
         f'aria-label="Share of months beating consensus, by reference month">']
    p.append("<title>Beat rate by calendar reference month</title>")
    for gv in (0.2, 0.4, 0.5, 0.6, 0.8):
        yy = y(gv)
        cls = "axis-zero" if abs(gv - 0.5) < 1e-9 else "grid"
        p.append(f'<line class="{cls}" x1="{ml}" y1="{yy:.1f}" x2="{W-mr}" y2="{yy:.1f}"/>')
        p.append(f'<text class="tick" x="{ml-9}" y="{yy+3.5:.1f}" text-anchor="end">'
                 f'{gv*100:.0f}%</text>')
    y50 = y(0.5)
    for i, m in enumerate(D["months"]):
        rate = m["hits"] / m["n"]
        cx = ml + i * step + step / 2
        yy = y(rate)
        top, h = min(yy, y50), abs(yy - y50)
        sign = "pos" if rate > 0.5 else "neg"
        p.append(f'<rect class="bar {sign}" x="{cx-bw/2:.1f}" y="{top:.1f}" '
                 f'width="{bw:.1f}" height="{max(h,1.5):.1f}" rx="2"><title>'
                 f'{esc(m["m"])}: {m["hits"]}/{m["n"]} beat consensus '
                 f'({rate*100:.0f}%), mean {m["mean"]:+.0f}k</title></rect>')
        p.append(f'<text class="mlab" x="{cx:.1f}" y="{mt+ph+18}" text-anchor="middle">'
                 f'{esc(m["m"])}</text>')
        p.append(f'<text class="mn" x="{cx:.1f}" y="{mt+ph+32}" text-anchor="middle">'
                 f'{m["hits"]}/{m["n"]}</text>')
    p.append("</svg>")
    return "".join(p)


# ------------------------------------------- chart 4: Pearson vs Spearman --
def chart_signals() -> str:
    cands = sorted(S["candidates"], key=lambda c: c["corr"])
    W, rowh, mt = 1060, 40, 30
    ml, mr = 250, 130
    H = mt + rowh * len(cands) + 40
    pw = W - ml - mr

    def x(v: float) -> float:
        return ml + (v + 0.32) / 0.64 * pw

    p = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" '
         f'aria-label="Pearson versus Spearman correlation for each candidate signal">']
    p.append("<title>Each signal's correlation with the payroll surprise</title>")
    for gv in (-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3):
        xx = x(gv)
        cls = "axis-zero" if gv == 0 else "grid"
        p.append(f'<line class="{cls}" x1="{xx:.1f}" y1="{mt-10}" x2="{xx:.1f}" y2="{H-32}"/>')
        p.append(f'<text class="tick" x="{xx:.1f}" y="{H-15}" text-anchor="middle">'
                 f'{gv:+.1f}</text>')
    p.append(f'<text class="coinflip" x="{x(0):.1f}" y="{mt-16}" text-anchor="middle">'
             f'no relationship</text>')
    for i, c in enumerate(cands):
        cy = mt + i * rowh + rowh / 2
        xa, xb = x(c["corr"]), x(c["spearman"])
        p.append(f'<line class="slope" x1="{xa:.1f}" y1="{cy:.1f}" x2="{xb:.1f}" y2="{cy:.1f}"/>')
        p.append(f'<circle class="dotp" cx="{xa:.1f}" cy="{cy:.1f}" r="5.5"><title>'
                 f'{esc(c["label"])} — Pearson {c["corr"]:+.3f} (p={c["p_corr"]:.3f})</title></circle>')
        p.append(f'<circle class="dots" cx="{xb:.1f}" cy="{cy:.1f}" r="6"><title>'
                 f'{esc(c["label"])} — Spearman {c["spearman"]:+.3f} '
                 f'(p={c["p_spearman"]:.3f})</title></circle>')
        p.append(f'<text class="rowlab2" x="{ml-16}" y="{cy+5:.1f}" text-anchor="end">'
                 f'{esc(c["label"])}</text>')
        p.append(f'<text class="rowsub2" x="{W-mr+12}" y="{cy+4:.1f}">n={c["n"]}</text>')
    p.append("</svg>")
    return "".join(p)


def rules_rows() -> str:
    out = []
    for r in D["rules"]:
        out.append(f'<tr><td>{esc(r["label"])}</td>'
                   f'<td class="num">{r["hits"]}/{r["tot"]}</td>'
                   f'<td class="num">{r["rate"]*100:.1f}%</td>'
                   f'<td class="num">{r["p"]:.2f}</td>'
                   f'<td><span class="verdict null">no edge</span></td></tr>')
    return "".join(out)


HTML = f"""<title>The Payrolls Coin Flip</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>
:root {{
  color-scheme: light;
  --bg:#f7f8fa; --panel:#ffffff; --ink:#12141a; --ink2:#565c69; --ink3:#858b98;
  --rule:#e2e5ec; --rule2:#eef0f4;
  --pos:#2a78d6; --neg:#e34948; --null:#858b98; --accent:#2a78d6;
  --band:#eceff4;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --bg:#14161a; --panel:#1b1e24; --ink:#f2f4f7; --ink2:#a8aeb9; --ink3:#7c8391;
    --rule:#2b2f38; --rule2:#23272e;
    --pos:#3987e5; --neg:#e66767; --null:#7c8391; --accent:#3987e5;
    --band:#22262d;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --bg:#14161a; --panel:#1b1e24; --ink:#f2f4f7; --ink2:#a8aeb9; --ink3:#7c8391;
  --rule:#2b2f38; --rule2:#23272e;
  --pos:#3987e5; --neg:#e66767; --null:#7c8391; --accent:#3987e5;
  --band:#22262d;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"Source Serif 4",Georgia,serif; font-size:17px; line-height:1.62;
  -webkit-font-smoothing:antialiased;
}}
.wrap {{ max-width:1140px; margin:0 auto; padding:56px 28px 96px; }}
.prose {{ max-width:68ch; }}
h1,h2,h3,.eyebrow,.stat-v,.mono,th,.tick,.rowval {{
  font-family:Archivo,"Helvetica Neue",Arial,sans-serif;
}}
.eyebrow {{
  font-size:11.5px; font-weight:600; letter-spacing:.14em; text-transform:uppercase;
  color:var(--ink3); margin:0 0 14px;
}}
h1 {{ font-size:clamp(34px,5vw,52px); line-height:1.04; font-weight:700;
     letter-spacing:-.021em; margin:0 0 18px; text-wrap:balance; }}
h2 {{ font-size:23px; font-weight:600; letter-spacing:-.011em; margin:0 0 6px;
     text-wrap:balance; }}
h3 {{ font-size:15px; font-weight:600; letter-spacing:-.005em; margin:0 0 8px; }}
p {{ margin:0 0 16px; }}
a {{ color:var(--accent); }}
.lede {{ font-size:20px; line-height:1.55; color:var(--ink2); margin-bottom:8px; }}
.meta {{ font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12.5px;
        color:var(--ink3); line-height:1.85; margin-top:26px;
        padding-top:16px; border-top:1px solid var(--rule); }}
section {{ margin-top:56px; }}
.sec-head {{ display:flex; flex-direction:column; gap:2px; margin-bottom:20px; }}
.sec-head .k {{ font-family:"IBM Plex Mono",monospace; font-size:11.5px;
               letter-spacing:.1em; text-transform:uppercase; color:var(--ink3); }}
.verdictcard {{
  display:grid; grid-template-columns:minmax(0,1fr) auto; gap:34px; align-items:center;
  background:var(--panel); border:1px solid var(--rule); border-radius:4px;
  padding:30px 32px; margin-top:34px;
}}
@media (max-width:720px) {{ .verdictcard {{ grid-template-columns:1fr; gap:22px; }} }}
.stat {{ text-align:right; }}
.stat-v {{ font-size:64px; font-weight:700; letter-spacing:-.03em; line-height:1;
          font-variant-numeric:tabular-nums; }}
.stat-l {{ font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--ink3);
          letter-spacing:.06em; margin-top:9px; line-height:1.5; }}
figure {{ margin:0; background:var(--panel); border:1px solid var(--rule);
         border-radius:4px; padding:22px 22px 16px; }}
figcaption {{ font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--ink3);
             margin-top:14px; padding-top:12px; border-top:1px solid var(--rule2);
             line-height:1.65; }}
.chartbox {{ overflow-x:auto; }}
.chart {{ display:block; width:100%; min-width:620px; height:auto; }}
.grid {{ stroke:var(--rule2); stroke-width:1; }}
.axis-zero {{ stroke:var(--ink3); stroke-width:1.25; }}
.bar.pos {{ fill:var(--pos); }}
.bar.neg {{ fill:var(--neg); }}
.bar:hover {{ opacity:.72; }}
.gapband {{ fill:var(--band); }}
.gaplab,.mn {{ font-family:"IBM Plex Mono",monospace; font-size:10.5px; fill:var(--ink3); }}
.tick {{ font-size:11px; fill:var(--ink3); font-variant-numeric:tabular-nums; }}
.axtitle {{ font-family:"IBM Plex Mono",monospace; font-size:10.5px; fill:var(--ink3); }}
.bracket {{ stroke:var(--rule); stroke-width:1.5; }}
.eralab,.mlab {{ font-family:"IBM Plex Mono",monospace; font-size:11.5px; fill:var(--ink2); }}
.coinflip {{ font-family:"IBM Plex Mono",monospace; font-size:11px; fill:var(--ink3); }}
.ci {{ stroke-width:2.5; }} .cicap {{ stroke-width:2; }}
.ci.pos,.cicap.pos {{ stroke:var(--pos); }} .dot.pos {{ fill:var(--pos); }}
.ci.null,.cicap.null {{ stroke:var(--null); }} .dot.null {{ fill:var(--null); }}
.dot {{ stroke:var(--panel); stroke-width:2; }}
.rowlab {{ font-family:Archivo,sans-serif; font-size:14.5px; font-weight:600; fill:var(--ink); }}
.rowsub {{ font-family:"IBM Plex Mono",monospace; font-size:11px; fill:var(--ink3); }}
.rowval {{ font-size:19px; font-weight:700; font-variant-numeric:tabular-nums; }}
.rowval.pos {{ fill:var(--pos); }} .rowval.null {{ fill:var(--ink2); }}
table {{ width:100%; border-collapse:collapse; font-size:14.5px; }}
th {{ text-align:left; font-size:11px; letter-spacing:.09em; text-transform:uppercase;
     color:var(--ink3); font-weight:600; padding:0 12px 9px 0;
     border-bottom:1px solid var(--rule); }}
td {{ padding:11px 12px 11px 0; border-bottom:1px solid var(--rule2); color:var(--ink2); }}
td:first-child {{ color:var(--ink); }}
.num {{ font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums;
       text-align:right; white-space:nowrap; }}
.verdict {{ font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.05em;
           padding:2.5px 8px; border-radius:3px; border:1px solid var(--rule);
           color:var(--ink3); white-space:nowrap; }}
blockquote {{ margin:0 0 18px; padding:2px 0 2px 20px; border-left:2px solid var(--accent);
             font-size:18px; color:var(--ink); }}
.honesty {{ background:var(--panel); border:1px solid var(--rule); border-radius:4px;
           padding:26px 30px; }}
.honesty h2 {{ margin-bottom:14px; }}
.honesty ul {{ margin:0; padding-left:19px; }}
.honesty li {{ margin-bottom:11px; color:var(--ink2); font-size:15.5px; line-height:1.58; }}
.honesty li strong {{ color:var(--ink); font-weight:600; }}
.bar-note {{ display:flex; gap:20px; flex-wrap:wrap; font-family:"IBM Plex Mono",monospace;
            font-size:11.5px; color:var(--ink3); margin-top:2px; }}
.key {{ display:inline-flex; align-items:center; gap:7px; }}
.sw {{ width:11px; height:11px; border-radius:2px; display:inline-block; }}
.slope {{ stroke:var(--rule); stroke-width:2; }}
.dotp {{ fill:var(--panel); stroke:var(--null); stroke-width:2; }}
.dots {{ fill:var(--pos); stroke:var(--panel); stroke-width:1.5; }}
.rowlab2 {{ font-family:Archivo,sans-serif; font-size:13.5px; fill:var(--ink); }}
.rowsub2 {{ font-family:"IBM Plex Mono",monospace; font-size:11px; fill:var(--ink3); }}
.gate {{ border:1px solid var(--accent); border-radius:4px; padding:20px 24px;
        background:var(--panel); }}
.gate .k {{ font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.1em;
           text-transform:uppercase; color:var(--accent); }}
.gate p {{ margin:8px 0 0; font-size:17px; }}
:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
@media (prefers-reduced-motion:reduce) {{ * {{ transition:none!important; }} }}
</style>

<div class="wrap">
<p class="eyebrow">Uranium Dashboard · Research note</p>
<h1>The payrolls trade is a coin flip</h1>
<p class="lede prose">Joe Lonsdale's non-farm-payrolls story is real, but it
describes an information edge inside the BLS seasonal-adjustment machinery —
not a rule you can adopt. Tested on 160 releases, "bet the market is wrong"
wins 50.0% of the time.</p>
<div class="meta prose">
2026-08-23 · 160 releases, 2013-04-05 → 2026-08-07 · consensus vs <b>first print</b><br>
reproducible: <code>nfp_surprise_study.py</code> · gates: <code>tests/test_gates.py</code> (15 passing)
</div>

<div class="verdictcard">
  <div>
    <h2>The clean sample is exactly a coin flip</h2>
    <p style="margin:6px 0 0;color:var(--ink2);font-size:16px;">
    Over 2013–2019 — no pandemic distortion, no reopening surge — betting that
    payrolls beat consensus won 40 of 80 decisions. You cannot get closer to
    nothing than this.</p>
  </div>
  <div class="stat">
    <div class="stat-v">50.0<span style="font-size:32px;">%</span></div>
    <div class="stat-l">40 / 80 · p = 1.00<br>2013–2019</div>
  </div>
</div>

<section>
  <div class="sec-head">
    <span class="k">Chart 1 · every release</span>
    <h2>Surprises are noise around zero</h2>
  </div>
  <figure>
    <div class="bar-note" style="margin-bottom:14px;">
      <span class="key"><span class="sw" style="background:var(--pos)"></span>actual above consensus</span>
      <span class="key"><span class="sw" style="background:var(--neg)"></span>actual below consensus</span>
      <span>hover any bar for the print</span>
    </div>
    <div class="chartbox">{chart_timeline()}</div>
    <figcaption>Actual minus consensus, thousands of jobs, per release. The
    2020–21 window is excluded throughout — single prints missed by millions
    (up to +10,509k) and would swamp every scale. Mean absolute surprise in the
    core sample is 63k.</figcaption>
  </figure>
</section>

<section>
  <div class="sec-head">
    <span class="k">Chart 2 · where "75%" comes from</span>
    <h2>One era clears chance — in hindsight</h2>
  </div>
  <figure>
    <div class="chartbox">{chart_eras()}</div>
    <figcaption>Hit rate of "bet above consensus" with 95% Wilson intervals.
    Only 2022–2024 separates from the coin-flip line, and that window was
    chosen after seeing the data — the definition of an in-sample result. Every
    other era's interval straddles 50%.</figcaption>
  </figure>
</section>

<section>
  <div class="sec-head">
    <span class="k">Chart 3 · the closest living descendant</span>
    <h2>Residual seasonality is a ghost</h2>
  </div>
  <figure>
    <div class="chartbox">{chart_months()}</div>
    <figcaption>Share of releases beating consensus by calendar reference
    month — the modern analogue of the seasonal-adjustment error Clarium traded.
    November looks strong at 9/11 (p = 0.065), but it is one of twelve
    simultaneous tests. Šidák-corrected: <b>p = 0.556</b>. Noise.</figcaption>
  </figure>
</section>

<section>
  <div class="sec-head">
    <span class="k">Out-of-sample</span>
    <h2>Every rule we tested fails</h2>
  </div>
  <figure>
    <table>
      <thead><tr><th>Rule (no lookahead)</th><th class="num">Hits</th>
      <th class="num">Rate</th><th class="num">p</th><th>Verdict</th></tr></thead>
      <tbody>
        {rules_rows()}
        <tr><td>Follow last month's surprise sign</td><td class="num">ρ = −0.04</td>
        <td class="num">—</td><td class="num">—</td>
        <td><span class="verdict null">no persistence</span></td></tr>
        <tr><td>CES 4-week vs 5-week reference gap</td><td class="num">−16.9k</td>
        <td class="num">—</td><td class="num">t = −1.19</td>
        <td><span class="verdict null">no edge</span></td></tr>
      </tbody>
    </table>
    <figcaption>Walk-forward means each bet uses only data available before that
    release. Nothing survives.</figcaption>
  </figure>
</section>

<section>
  <div class="sec-head">
    <span class="k">Chart 4 · other signals</span>
    <h2>Every candidate collapses when you rank it</h2>
  </div>
  <figure>
    <div class="bar-note" style="margin-bottom:14px;">
      <span class="key"><span class="sw" style="background:transparent;border:2px solid var(--null)"></span>Pearson (outlier-sensitive)</span>
      <span class="key"><span class="sw" style="background:var(--pos)"></span>Spearman (rank, robust)</span>
    </div>
    <div class="chartbox">{chart_signals()}</div>
    <figcaption>Eight pre-specified indicators, each measured as its own
    surprise from the last print strictly before the payroll release. ADP looks
    like a real find on Pearson (−0.229, p = 0.007) and evaporates on Spearman
    (+0.037, p = 0.67) — the whole correlation was two or three outliers. Every
    other candidate sits on top of zero. Walk-forward, all land between 42% and
    53%.</figcaption>
  </figure>
  <div class="prose" style="margin-top:26px;">
    <h3>Testing "the survey is misaligned with the hard data" directly</h3>
    <p>Split every month by how far consensus sat from the freshest hard read
    (ADP's actual). If misalignment were a tell, the beat rate would slope
    across the terciles. It does not:</p>
  </div>
  <figure style="margin-top:14px;">
    <table>
      <thead><tr><th>Consensus vs ADP actual</th><th class="num">n</th>
      <th class="num">NFP beat</th></tr></thead>
      <tbody>
        <tr><td>Survey well <b>below</b> ADP</td><td class="num">45</td><td class="num">58%</td></tr>
        <tr><td>Middle</td><td class="num">45</td><td class="num">51%</td></tr>
        <tr><td>Survey well <b>above</b> ADP</td><td class="num">45</td><td class="num">58%</td></tr>
      </tbody>
    </table>
    <figcaption>Flat to U-shaped, not monotonic. Pearson +0.224 (p = 0.008),
    Spearman −0.020 (p = 0.82), rule hit rate 49.6%.</figcaption>
  </figure>
  <div class="prose" style="margin-top:26px;">
    <p><b>This is the expected answer, and it is the useful one.</b> Economists
    set their payroll forecast <i>after</i> reading ADP, claims, ISM and
    Challenger. Consensus already impounds them — which is exactly <i>why</i>
    it comes out unbiased. Any public pre-release indicator is priced in by
    construction. Only information consensus does not already have can work.</p>
  </div>
</section>

<section class="prose">
  <div class="sec-head">
    <span class="k">What the trade actually was</span>
    <h2>An edge in the algorithm, not in the crowd</h2>
  </div>
  <p>From Lonsdale's April 2024 <i>My First Million</i> interview, describing
  his stint at <b>Clarium Capital</b> — Peter Thiel's global-macro fund —
  around 2003–04:</p>
  <blockquote>"Kevin Harrington, the head of research, discovered an error in
  the seasonal adjustment of the numbers, allowing them to predict whether the
  number would hit or miss."</blockquote>
  <p>First Friday of the month, desk in at 5:30am PT for the 8:30am ET print,
  large bets on <b>the market's reaction</b> — mostly bonds.</p>
  <p>The mechanism is the whole finding. This was not "the market is usually
  wrong, so fade it." It was: <i>we model the BLS's own seasonal-adjustment
  machinery better than anyone else, so we know the print before it lands.</i>
  A behavioural rule you can state in one sentence gets arbitraged away. A
  modelling edge in a government statistical process does not — but it also
  isn't something you can acquire by hearing about it.</p>
  <p>And it is harder now than in 2004: BLS moved CES to <b>concurrent</b>
  seasonal adjustment, recomputing factors every month with all data through
  the current month, which shrinks exactly the stale-factor error a static
  model could exploit. The factors and methodology are published. Nowcasting
  desks, ADP, and prediction markets all compete for the same gap.</p>
</section>

<section>
  <div class="sec-head">
    <span class="k">If we build it</span>
    <h2>The only honest version, and its gate</h2>
  </div>
  <div class="prose"><p>Rebuild the <i>information</i> edge, not the rule: a
  genuine payrolls nowcast from independent high-frequency inputs — ADP, initial
  claims in the reference week, ISM and PMI employment, withholding-tax
  receipts, Indeed postings, WARN filings — plus our own seasonal reconstruction
  from unadjusted payrolls. The bar is unambiguous:</p></div>
  <div class="gate">
    <span class="k">Merge-blocking gate</span>
    <p>Beat the consensus median on out-of-sample RMSE across <b>≥ 24
    consecutive releases</b> before any capital is committed.</p>
  </div>
  <div class="prose"><p style="margin-top:18px;">Absent that, there is nothing
  here to trade. Venue if it ever clears: Kalshi has listed monthly payroll
  contracts since March 2023, and the Fed's own working paper <i>Kalshi and the
  Rise of Macro Markets</i> (FEDS 2026-010) treats them as a well-behaved
  benchmark. Mind the arithmetic — a 56% edge on a ~50c binary is about 6c
  gross, and spread plus fees eat most of it.</p></div>
</section>

<section>
  <div class="honesty">
    <h2>Honesty box</h2>
    <ul>
      <li><strong>Measurement basis.</strong> First print vs consensus captured
      at release. No transaction costs, slippage, or sizing — raw directional
      hit rates, an upper bound on any real strategy.</li>
      <li><strong>The 72% is in-sample.</strong> The 2022–24 window was selected
      after seeing the data. It is shown to explain where a "75%" impression
      comes from, not as a forecast. Do not size anything off it.</li>
      <li><strong>Not modelled: the market's reaction.</strong> That was
      Lonsdale's actual P&amp;L driver — bonds can rally on a hot number. We
      measured only whether the print beats consensus. A reaction study needs
      intraday futures tick data we do not have.</li>
      <li><strong>Not modelled: revisions.</strong> FMP's <code>previous</code>
      field is back-filled with revised values, so it cannot measure
      revision-at-the-time. We ran the test, got a result contradicting the
      well-documented 2024–25 downward revisions, and <b>discarded it</b> rather
      than publish a number the data could not support. Doing it properly needs
      ALFRED vintages.</li>
      <li><strong>Consensus source.</strong> FMP's survey median, spot-checked
      against known Bloomberg consensus (Mar-24 200k/303k, Apr-24 243k/175k,
      May-24 185k/272k) — all match. Not audited beyond that.</li>
      <li><strong>Data gaps, both gated.</strong> October 2025 has no standalone
      release (folded into the 2025-12-16 print), and the 2025-11-20 release is
      the <b>September</b> report — FMP labels it October, and we override it.</li>
      <li><strong>Sample starts 2013.</strong> FMP's calendar reaches no
      further back, so the Clarium-era claim <b>cannot be tested directly</b>
      with this data.</li>
    </ul>
  </div>
</section>
</div>
"""

if __name__ == "__main__":
    (HERE / "report.html").write_text(HTML)
    print(f"wrote {HERE / 'report.html'} ({len(HTML):,} bytes)")
