"""Read-only web view of Barbell Lab, served behind the optic.capital gate
hub at /portfolio-optimizer (the hub strips the prefix and forwards here,
exactly like the Treasury Canary).

The platform stays CLI-first: this app renders what the CLI produced (reports
directory + SQLite) and runs the nightly job (ingest → validate → gates →
monitors) when RUN_SCHEDULER=true. It never runs backtests or optimizations
on request — those are deliberate, registered-trial actions.

All internal links are RELATIVE so the app works both bare (onrender.com)
and behind the /portfolio-optimizer prefix without a build-time base path.
"""
from __future__ import annotations

import html
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse

from .. import db
from ..config import REPORT_DIR, ensure_dirs

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def _nightly_job() -> None:
    """ingest → validation → acceptance gates → monitors. Failures alert."""
    con = db.connect()
    try:
        from ..ingest.runner import full_ingest
        from ..monitor.run import run_monitors
        full_ingest(con, datetime.now(timezone.utc).date().isoformat(), gate=True)
        run_monitors(con, "all")
        logger.info("nightly job complete")
    except Exception as exc:  # noqa: BLE001 — fail LOUDLY, keep serving
        logger.critical("NIGHTLY JOB FAILED: %s", exc)
        con.execute("INSERT INTO alerts (ts_utc, kind, message, details) VALUES (?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), "job_failure",
                     f"nightly job failed: {exc}", "{}"))
        con.commit()
    finally:
        con.close()


def _scheduler_loop() -> None:
    hour = int(os.environ.get("MONITOR_UTC_HOUR", "9"))
    while True:
        now = datetime.now(timezone.utc)
        nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        time.sleep(max(60.0, (nxt - now).total_seconds()))
        _nightly_job()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    if os.environ.get("RUN_SCHEDULER", "false").lower() == "true":
        if os.environ.get("INGEST_ON_STARTUP", "false").lower() == "true":
            threading.Thread(target=_nightly_job, daemon=True, name="startup-job").start()
        threading.Thread(target=_scheduler_loop, daemon=True, name="scheduler").start()
        logger.info("nightly scheduler armed (%s:00 UTC)", os.environ.get("MONITOR_UTC_HOUR", "9"))
    yield


app = FastAPI(title="Barbell Lab", lifespan=lifespan)

_STYLE = """
<style>
 body{font-family:ui-monospace,Menlo,monospace;background:#0b1120;color:#d8e1ef;
      max-width:1080px;margin:2rem auto;padding:0 1rem;line-height:1.55}
 a{color:#7cc0ff} h1,h2{color:#9ecbff} code,pre{background:#111a2e;padding:2px 5px;border-radius:4px}
 pre{padding:1rem;overflow-x:auto} table{border-collapse:collapse;margin:.6rem 0}
 td,th{border:1px solid #2a3a58;padding:4px 10px;text-align:right}
 td:first-child,th:first-child{text-align:left}
 .warn{color:#ffb454}.ok{color:#7ce38b}.bad{color:#ff7b72}
 .card{background:#111a2e;border:1px solid #2a3a58;border-radius:8px;padding:1rem;margin:1rem 0}
</style>
"""


def _md_table_to_html(md: str) -> str:
    """Minimal markdown → HTML (headers, tables, bold, lists). Report bodies
    are trusted (we generate them) but escaped anyway."""
    out, in_table = [], False
    for raw in md.splitlines():
        line = html.escape(raw)
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue  # separator row
            tag = "td"
            if not in_table:
                out.append("<table>")
                in_table, tag = True, "th"
            out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if s.startswith("# "):
            out.append(f"<h1>{s[2:]}</h1>")
        elif s.startswith("## "):
            out.append(f"<h2>{s[3:]}</h2>")
        elif s.startswith("### "):
            out.append(f"<h3>{s[4:]}</h3>")
        elif s.startswith("- "):
            out.append(f"<div>• {s[2:]}</div>")
        elif s.startswith("&gt; "):
            out.append(f"<div class='warn'>{s[5:]}</div>")
        elif s == "":
            out.append("<br>")
        else:
            out.append(f"<div>{line}</div>")
    if in_table:
        out.append("</table>")
    text = "\n".join(out)
    while "**" in text:
        text = text.replace("**", "<b>", 1).replace("**", "</b>", 1)
    return text


_LAB_HTML = """<!doctype html><html><head><title>Barbell Lab — workbench</title>
""" + _STYLE + """
<style>
 .controls{display:flex;flex-wrap:wrap;gap:.6rem;align-items:end}
 .controls label{display:flex;flex-direction:column;font-size:.8rem;color:#8ea3c0;gap:2px}
 .controls select,.controls input{background:#0b1120;color:#d8e1ef;border:1px solid #2a3a58;
   border-radius:6px;padding:.45rem}
 .controls button{background:#1f6feb;color:#fff;border:0;border-radius:6px;
   padding:.55rem 1rem;cursor:pointer}
 .controls button.alt{background:#26324d}
 #chartwrap{position:relative}
 #tip{position:absolute;pointer-events:none;background:#0b1120;border:1px solid #2a3a58;
   border-radius:6px;padding:4px 8px;font-size:.75rem;display:none;white-space:nowrap}
 .legend{display:flex;gap:1rem;font-size:.8rem;color:#c3c2b7;margin:.3rem 0}
 .chip{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin-right:4px}
</style></head><body>
<h1>⚖️ Barbell Lab — workbench</h1>
<p><a href="./">&larr; dashboard</a> · <a href="chat">💬 analyst chat</a> ·
Interactive runs use exploratory Monte Carlo paths and register trials; the CLI
runs the ≥20k-path versions. Numbers using the modeled bot are flagged.</p>

<div class="card"><div class="controls">
 <label>tail sleeve <select id="tail">
   <option>TAIL</option><option>CAOS</option><option>BTAL</option><option>NONE</option>
   <option>TAIL+CAOS</option><option>TAIL+BTAL</option><option>CAOS+BTAL</option></select></label>
 <label>bot % <input id="frac" type="number" min="0" max="0.45" step="0.05" value="0"/></label>
 <label>kill-switch <select id="ks">
   <option>perfect</option><option>lag1</option><option>fails</option></select></label>
 <button id="b-curve">Equity curve</button>
 <button id="b-sim" class="alt">Simulate</button>
 <button id="b-sweep" class="alt">Sweep fractions</button>
 <button id="b-tear" class="alt">Tearsheet</button>
</div></div>

<div class="card" id="chartcard">
 <div class="legend"><span><span class="chip" style="background:#3987e5"></span>book</span>
  <span><span class="chip" style="background:#008300"></span>SPY (total return)</span>
  <span id="prov" class="warn"></span></div>
 <div id="chartwrap"><svg id="chart" width="100%" height="320"></svg><div id="tip"></div></div>
</div>
<div class="card" id="out"><div class="warn">Pick parameters and run something.</div></div>

<script>
const $=id=>document.getElementById(id);
const params=()=>({tail:$('tail').value, bot_frac:parseFloat($('frac').value)||0,
                   kill_switch:$('ks').value});
function busy(b){for(const id of['b-curve','b-sim','b-sweep','b-tear'])
  $(id).disabled=b;}
async function post(url,body){const r=await fetch(url,{method:'POST',
  headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j=await r.json(); if(!r.ok) throw new Error(j.detail||r.status); return j;}

async function run(kind){
  busy(true); $('out').innerHTML='<div class="warn">running…</div>';
  try{
    if(kind==='sim') $('out').innerHTML=(await post('api/run/book',params())).html;
    else if(kind==='sweep') $('out').innerHTML=(await post('api/run/book',
      {...params(), sweep:true})).html;
    else $('out').innerHTML=(await post('api/run/tearsheet',params())).html;
  }catch(e){$('out').innerHTML='<div class="bad">'+e.message+'</div>';}
  busy(false);
}
$('b-sim').onclick=()=>run('sim'); $('b-sweep').onclick=()=>run('sweep');
$('b-tear').onclick=()=>run('tear');

let series=null;
$('b-curve').onclick=async()=>{
  busy(true);
  try{
    const p=params();
    const r=await fetch('api/equity?tail='+encodeURIComponent(p.tail)
      +'&bot_frac='+p.bot_frac+'&kill_switch='+p.kill_switch);
    const j=await r.json(); if(!r.ok) throw new Error(j.detail||r.status);
    series=j; $('prov').textContent = j.bot_provenance.startsWith('model')
      ? '⚠ bot stream is the parameterized MODEL' : '';
    draw();
  }catch(e){$('out').innerHTML='<div class="bad">'+e.message+'</div>';}
  busy(false);
};

function draw(){
  if(!series) return;
  const svg=$('chart'), W=svg.clientWidth, H=320, L=52, R=14, T=12, B=26;
  const xs=series.dates.map(d=>new Date(d).getTime());
  const all=series.book.concat(series.spy);
  const ymin=Math.min(...all), ymax=Math.max(...all);
  const X=t=>L+(t-xs[0])/(xs[xs.length-1]-xs[0])*(W-L-R);
  const Y=v=>T+(1-(v-ymin)/(ymax-ymin))*(H-T-B);
  const path=a=>a.map((v,i)=>(i?'L':'M')+X(xs[i]).toFixed(1)+' '+Y(v).toFixed(1)).join('');
  let g='';
  const ticks=5;
  for(let i=0;i<=ticks;i++){const v=ymin+(ymax-ymin)*i/ticks, y=Y(v);
    g+=`<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="#26324d" stroke-width="1"/>`
      +`<text x="${L-6}" y="${y+3}" fill="#898781" font-size="10" text-anchor="end">${v.toFixed(1)}x</text>`;}
  const y0=new Date(xs[0]).getFullYear(), y1=new Date(xs[xs.length-1]).getFullYear();
  for(let y=y0;y<=y1;y++){const t=new Date(y,0,1).getTime();
    if(t<xs[0]||t>xs[xs.length-1])continue;
    g+=`<text x="${X(t)}" y="${H-8}" fill="#898781" font-size="10" text-anchor="middle">${y}</text>`;}
  g+=`<path d="${path(series.spy)}" fill="none" stroke="#008300" stroke-width="2"/>`;
  g+=`<path d="${path(series.book)}" fill="none" stroke="#3987e5" stroke-width="2"/>`;
  g+=`<text x="${W-R}" y="${Y(series.book[series.book.length-1])-5}" fill="#3987e5" font-size="10" text-anchor="end">book ${series.book[series.book.length-1].toFixed(2)}x</text>`;
  g+=`<text x="${W-R}" y="${Y(series.spy[series.spy.length-1])+12}" fill="#008300" font-size="10" text-anchor="end">SPY ${series.spy[series.spy.length-1].toFixed(2)}x</text>`;
  g+=`<line id="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="#8ea3c0" stroke-width="1" opacity="0"/>`;
  svg.innerHTML=g;
  svg.onmousemove=e=>{
    const r=svg.getBoundingClientRect(), px=e.clientX-r.left;
    if(px<L||px>W-R){$('tip').style.display='none';$('xh').setAttribute('opacity',0);return;}
    const t=xs[0]+(px-L)/(W-L-R)*(xs[xs.length-1]-xs[0]);
    let i=xs.findIndex(x=>x>=t); if(i<0)i=xs.length-1; if(i>0&&t-xs[i-1]<xs[i]-t)i--;
    const xh=$('xh'); xh.setAttribute('x1',X(xs[i])); xh.setAttribute('x2',X(xs[i]));
    xh.setAttribute('opacity',.5);
    const tip=$('tip'); tip.style.display='block';
    tip.style.left=Math.min(px+10, W-170)+'px'; tip.style.top='10px';
    tip.innerHTML=`<b>${series.dates[i]}</b><br>book ${series.book[i].toFixed(2)}x · SPY ${series.spy[i].toFixed(2)}x`;
  };
  svg.onmouseleave=()=>{$('tip').style.display='none';$('xh').setAttribute('opacity',0);};
}
window.addEventListener('resize',draw);
$('b-curve').click();
</script></body></html>"""


@app.get("/health")
def health():
    from ..chat.agent import openrouter_key_diagnostics
    return {"status": "ok", "app": "barbell-lab",
            "chat_backend": ("anthropic" if os.environ.get("ANTHROPIC_API_KEY")
                             else "openrouter" if os.environ.get("OPENROUTER_API_KEY")
                             else None),
            "openrouter_key": openrouter_key_diagnostics()}


def _pct(v, signed=True):
    if v is None:
        return "n/a"
    return f"{v:+.2%}" if signed else f"{v:.2%}"


def _badge(ok: bool) -> str:
    return "<span class='ok'>PASS</span>" if ok else "<span class='bad'>BREACH</span>"


@app.get("/", response_class=HTMLResponse)
def index():
    from ..portfolio import registry
    from ..portfolio.tearsheet import risk_contributions
    from ..ingest.series import returns_matrix

    con = db.connect()
    try:
        live = registry.get_live(con)
        m = registry.version_metrics(con, live)
        weights = live["weights"]
        try:
            mat = returns_matrix(con, list(weights.keys()), spliced=True).dropna()
            rc = risk_contributions(mat, weights)
        except Exception:  # noqa: BLE001
            rc = None
        rows = "".join(
            f"<tr><td>{t}</td><td>{w:.1%}</td>"
            f"<td>{(f'{rc[t]:.1%}' if rc is not None else 'n/a')}</td></tr>"
            for t, w in sorted(weights.items(), key=lambda kv: -kv[1]))

        regime = con.execute(
            "SELECT date, quadrant, labor_z, inflation_z, credit_z, dollar_z "
            "FROM regime_log ORDER BY date DESC LIMIT 1").fetchone()
        regime_html = "n/a"
        if regime:
            regime_html = (f"<b>{html.escape(regime[1].upper())}</b> ({regime[0]})<br>"
                           f"<small>labor {regime[2]:+.2f} · infl {regime[3]:+.2f} · "
                           f"credit {regime[4]:+.2f} · dollar {regime[5]:+.2f}</small>")

        cons = m["constraints"]
        tiles = f"""
<div class="tiles">
 <div class="tile"><small>realized CAGR (since {m['history_start'][:4]})</small>
   <b>{_pct(m['cagr_realized'])}</b></div>
 <div class="tile"><small>CAGR 1y / 3y</small>
   <b>{_pct(m['cagr_1y'])} / {_pct(m['cagr_3y'])}</b></div>
 <div class="tile"><small>expected CAGR (MC 10y median)</small>
   <b>{_pct(m['cagr_expected_10y'])}</b></div>
 <div class="tile"><small>Sharpe (ann.)</small><b>{m['sharpe']:.2f}</b></div>
 <div class="tile"><small>max drawdown (realized)</small>
   <b>{_pct(m['maxdd_realized'])}</b></div>
 <div class="tile"><small>regime</small><b style="font-size:1rem">{regime_html}</b></div>
</div>
<div class="tiles">
 <div class="tile">{_badge(cons['cvar5']['pass'])}<small>CVaR(5%, 1y) vs floor</small>
   <b>{_pct(cons['cvar5']['value'])} <small>/ {_pct(cons['cvar5']['floor'])}</small></b></div>
 <div class="tile">{_badge(cons['maxdd_p5']['pass'])}<small>p5 max drawdown vs floor</small>
   <b>{_pct(cons['maxdd_p5']['value'])} <small>/ {_pct(cons['maxdd_p5']['floor'])}</small></b></div>
 <div class="tile">{_badge(cons['max_position']['pass'])}<small>largest position vs cap</small>
   <b>{_pct(cons['max_position']['value'], False)} <small>/ {_pct(cons['max_position']['cap'], False)}</small></b></div>
 <div class="tile"><small>p5 one-year outcome</small><b>{_pct(m['p5_1y'])}</b></div>
</div>"""

        led_rows = ""
        for r in registry.ledger(con):
            d = r["deltas"] or {}
            delta_txt = (f"ΔE[CAGR] {_pct(d.get('cagr_expected_10y'))} · "
                         f"ΔCVaR {_pct(d.get('cvar5_mc'))}"
                         if d else "—")
            led_rows += (f"<tr><td><b>{r['label']}</b></td><td>{r['status']}</td>"
                         f"<td>{r['adopted_at'] or r['created_at']}</td>"
                         f"<td>{html.escape((r['rationale'] or '')[:80])}</td>"
                         f"<td>{r['verdict'] or '—'}</td><td>{delta_txt}</td></tr>")

        trials = con.execute("SELECT COUNT(*) FROM trials").fetchone()[0]
        gates_ok, gates_n = 0, 0
        try:
            from ..validate.acceptance import run_gates
            gs = run_gates(con)
            gates_n, gates_ok = len(gs), sum(g.passed for g in gs)
        except Exception:  # noqa: BLE001
            pass
        alerts = con.execute(
            "SELECT ts_utc, kind, message FROM alerts ORDER BY id DESC LIMIT 5").fetchall()
        alerts_html = "".join(
            f"<div><code>{a[0][:10]}</code> <b>{html.escape(a[1])}</b> "
            f"{html.escape(a[2][:90])}</div>" for a in alerts) or "<div class='ok'>none</div>"
        bot_note = ("" if m["bot_provenance"] in ("real", "none") else
                    "<span class='warn'>⚠ bot stream is the parameterized model — "
                    "import real P&L for final numbers</span>")
    finally:
        con.close()

    reports = sorted(REPORT_DIR.glob("latest-*.md")) if REPORT_DIR.exists() else []
    rep_links = " · ".join(
        f"<a href='reports/{r.name}'>{r.name.removeprefix('latest-').removesuffix('.md')}</a>"
        for r in reports) or "none yet"

    body = f"""
<h1>⚖️ {html.escape(live['name'])} — {live['label']} <small style="color:#7ce38b">LIVE</small></h1>
<p>adopted {(live['adopted_at'] or live['created_at'])[:10]} · metrics as of {m['as_of']}
· MC {m['n_paths']} paths {bot_note}<br>
<a href="lab">🧪 workbench</a> · <a href="chat">💬 analyst chat</a>
· <a href="versions">📒 full ledger</a></p>

{tiles}

<div class="row">
<div class="card" style="flex:1;min-width:300px"><h2>Holdings ({1 - live['bot_frac']:.0%} sleeve · {live['bot_frac']:.0%} bot)</h2>
<table><tr><th>ticker</th><th>weight</th><th>risk contrib</th></tr>{rows}</table></div>
<div class="card" style="flex:2;min-width:420px"><h2>Equity curve vs SPY</h2>
<div id="chartwrap" style="position:relative"><svg id="chart" width="100%" height="260"></svg></div>
<div class="legend"><span><span class="chip" style="background:#3987e5"></span>book</span>
<span><span class="chip" style="background:#008300"></span>SPY</span></div></div>
</div>

<div class="card"><h2>Improvement ledger</h2>
<table><tr><th>version</th><th>status</th><th>date</th><th>rationale</th><th>verdict</th><th>vs parent</th></tr>
{led_rows}</table>
<p><small>Propose candidates from the <a href="lab">workbench</a> or
<a href="chat">chat</a>; promotion always requires typed confirmation.</small></p></div>

<div class="card"><h2>Platform health</h2>
<div>acceptance gates: <b class="{'ok' if gates_ok == gates_n and gates_n else 'bad'}">{gates_ok}/{gates_n}</b>
 · cumulative trials: <b>{trials}</b> · reports: {rep_links}</div>
<div style="margin-top:.4rem">{alerts_html}</div></div>

<script>
fetch('api/equity?version=live').then(r=>r.json()).then(j=>{{
 const svg=document.getElementById('chart'),W=svg.clientWidth,H=260,L=44,R=10,T=10,B=22;
 const xs=j.dates.map(d=>new Date(d).getTime()),all=j.book.concat(j.spy);
 const ymin=Math.min(...all),ymax=Math.max(...all);
 const X=t=>L+(t-xs[0])/(xs[xs.length-1]-xs[0])*(W-L-R);
 const Y=v=>T+(1-(v-ymin)/(ymax-ymin))*(H-T-B);
 const path=a=>a.map((v,i)=>(i?'L':'M')+X(xs[i]).toFixed(1)+' '+Y(v).toFixed(1)).join('');
 let g='';
 for(let i=0;i<=4;i++){{const v=ymin+(ymax-ymin)*i/4,y=Y(v);
  g+=`<line x1="${{L}}" x2="${{W-R}}" y1="${{y}}" y2="${{y}}" stroke="#26324d"/>`+
     `<text x="${{L-5}}" y="${{y+3}}" fill="#898781" font-size="10" text-anchor="end">${{v.toFixed(1)}}x</text>`;}}
 g+=`<path d="${{path(j.spy)}}" fill="none" stroke="#008300" stroke-width="2"/>`;
 g+=`<path d="${{path(j.book)}}" fill="none" stroke="#3987e5" stroke-width="2"/>`;
 svg.innerHTML=g;
}});
</script>"""
    return HTMLResponse(f"<!doctype html><html><head><title>{html.escape(live['name'])} — Barbell Lab</title>"
                        f"{_STYLE}<style>.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));"
                        f"gap:.6rem;margin:.8rem 0}}.tile{{background:#111a2e;border:1px solid #2a3a58;"
                        f"border-radius:8px;padding:.7rem}}.tile small{{display:block;color:#8ea3c0;font-size:.72rem}}"
                        f".tile b{{font-size:1.25rem}}.row{{display:flex;gap:1rem;flex-wrap:wrap}}"
                        f".legend{{font-size:.8rem;color:#c3c2b7}}.chip{{display:inline-block;width:14px;height:3px;"
                        f"border-radius:2px;vertical-align:middle;margin-right:4px}}</style>"
                        f"</head><body>{body}</body></html>")


@app.get("/reports/{name}", response_class=HTMLResponse)
def report(name: str):
    if "/" in name or ".." in name or not name.endswith(".md"):
        raise HTTPException(400, "bad report name")
    path = REPORT_DIR / name
    if not path.exists():
        raise HTTPException(404, "no such report")
    body = _md_table_to_html(path.read_text())
    return HTMLResponse(f"<!doctype html><html><head><title>{html.escape(name)}</title>"
                        f"{_STYLE}</head><body><p><a href='../'>&larr; back</a></p>"
                        f"{body}</body></html>")


@app.get("/api/regime")
def api_regime():
    con = db.connect()
    try:
        row = con.execute(
            "SELECT date, quadrant, labor_z, inflation_z, credit_z, dollar_z, details "
            "FROM regime_log ORDER BY date DESC LIMIT 1").fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404, "no regime snapshot")
    return {"date": row[0], "quadrant": row[1], "labor_z": row[2], "inflation_z": row[3],
            "credit_z": row[4], "dollar_z": row[5], "levels": json.loads(row[6] or "{}")}


@app.get("/api/alerts")
def api_alerts(limit: int = 50):
    con = db.connect()
    try:
        rows = con.execute(
            "SELECT ts_utc, kind, message, details FROM alerts ORDER BY id DESC LIMIT ?",
            (min(limit, 500),)).fetchall()
    finally:
        con.close()
    return [{"ts_utc": r[0], "kind": r[1], "message": r[2],
             "details": json.loads(r[3] or "{}")} for r in rows]


@app.get("/api/trials")
def api_trials():
    con = db.connect()
    try:
        n = con.execute("SELECT COUNT(*) FROM trials").fetchone()[0]
        rows = con.execute(
            "SELECT trial_id, ts_utc, module, description, sharpe, n_obs FROM trials "
            "ORDER BY trial_id DESC LIMIT 25").fetchall()
    finally:
        con.close()
    return {"cumulative_trials": n,
            "recent": [{"trial_id": r[0], "ts_utc": r[1], "module": r[2],
                        "description": r[3], "sharpe": r[4], "n_obs": r[5]} for r in rows]}


@app.get("/reports.txt", response_class=PlainTextResponse)
def reports_index():
    if not REPORT_DIR.exists():
        return ""
    return "\n".join(sorted(p.name for p in REPORT_DIR.glob("*.md")))


# ------------------------------------------------------------------ lab
# Interactive workbench: the same grounded functions the chat analyst uses,
# driven by form controls. Runs are exploratory-path and register trials.

def _lab_con():
    return db.connect()


@app.post("/api/run/tearsheet")
def api_run_tearsheet(payload: dict):
    from ..chat.agent import _tool_get_tearsheet
    con = _lab_con()
    try:
        md = _tool_get_tearsheet(con, tail=str(payload.get("tail", "TAIL")),
                                 bot_frac=float(payload.get("bot_frac", 0.0)))
        return {"html": _md_table_to_html(md)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, str(exc)) from None
    finally:
        con.close()


@app.post("/api/run/book")
def api_run_book(payload: dict):
    from ..chat.agent import _tool_simulate_book, _tool_sweep_bot_fraction
    con = _lab_con()
    try:
        if payload.get("sweep"):
            md = _tool_sweep_bot_fraction(
                con, tail=str(payload.get("tail", "TAIL")),
                kill_switch=str(payload.get("kill_switch", "perfect")))
            return {"html": _md_table_to_html(md)}
        out = _tool_simulate_book(
            con, bot_frac=float(payload.get("bot_frac", 0.2)),
            tail=str(payload.get("tail", "TAIL")),
            kill_switch=str(payload.get("kill_switch", "perfect")))
        r = json.loads(out)
        rows = "".join(
            f"<tr><td>{k}</td><td>{v:+.2%}</td></tr>" if isinstance(v, float) and k != "bot_frac"
            else f"<tr><td>{k}</td><td>{html.escape(str(v))}</td></tr>"
            for k, v in r.items())
        return {"html": f"<table><tr><th>metric</th><th>value</th></tr>{rows}</table>"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, str(exc)) from None
    finally:
        con.close()


@app.post("/api/run/window")
def api_run_window(payload: dict):
    from ..chat.agent import _tool_window_stats
    con = _lab_con()
    try:
        out = _tool_window_stats(con, payload.get("tickers", []),
                                 str(payload.get("start")), str(payload.get("end")))
        return json.loads(out)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, str(exc)) from None
    finally:
        con.close()


@app.get("/api/equity")
def api_equity(tail: str = "TAIL", bot_frac: float = 0.0,
               kill_switch: str = "perfect", version: str | None = None):
    """Weekly wealth curves for the book and SPY. version='live' or a numeric
    register id uses that portfolio version's explicit weights instead of the
    tail/bot_frac parameters."""
    from ..portfolio.book import book_frame
    from ..portfolio import registry
    con = _lab_con()
    try:
        if version is not None:
            v = (registry.get_live(con) if version == "live"
                 else registry.get_version(con, int(version)))
            joint = registry.version_book(con, v, kill_switch=kill_switch)
            bot_frac = v["bot_frac"]
        else:
            joint = book_frame(con, bot_frac, tail=tail, allow_bot_model=True,
                               kill_switch=kill_switch)
        book = (1 + joint["combined"]).cumprod()
        spy_px = db.read_prices(con, "SPY")["close_adj"]
        spy = spy_px.loc[joint.index.min():joint.index.max()]
        spy = spy / spy.iloc[0]
        bw = book.resample("W").last().dropna()
        sw = spy.resample("W").last().reindex(bw.index).ffill()
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in bw.index],
            "book": [round(float(v), 4) for v in bw.values],
            "spy": [round(float(v), 4) for v in sw.values],
            "label": ("sleeve only" if bot_frac == 0
                      else f"{1 - bot_frac:.0%} sleeve + {bot_frac:.0%} bot"),
            "bot_provenance": joint.attrs.get("bot_provenance", "none"),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, str(exc)) from None
    finally:
        con.close()


@app.get("/lab", response_class=HTMLResponse)
def lab_page():
    return HTMLResponse(_LAB_HTML)


@app.get("/api/phase")
def api_phase():
    from .. import phase
    return phase.board()


_PHASE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phase allocation — Barbell Lab</title><style>
body{background:#0b0f17;color:#e2e8f0;font:14px/1.5 -apple-system,Segoe UI,
Roboto,sans-serif;margin:0;padding:24px;max-width:980px;margin:auto}
h1{font-size:18px} h2{font-size:14px;color:#93a4bd;margin:18px 0 6px}
.card{background:#111a2e;border:1px solid #26334e;border-radius:10px;
padding:14px 16px;margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{padding:4px 8px;text-align:right;border-top:1px solid #1e293b}
td:first-child,th:first-child{text-align:left}
.pill{display:inline-block;border-radius:99px;padding:2px 12px;
font-weight:600;font-size:12px;cursor:pointer;border:1px solid #26334e;
color:#64748b;margin-right:6px}
.pill.on{border-color:#38bdf8;color:#7dd3fc;background:#0c4a6e33}
.phase{font-size:22px;font-weight:700}
.EXPANSION{color:#34d399}.LATE_CYCLE{color:#fbbf24}.STALL{color:#fb923c}
.SLOWDOWN{color:#f87171}.CONTRACTION{color:#dc2626}
.w{font-size:26px;font-weight:700}.wl{font-size:11px;color:#64748b}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;text-align:center}
.small{font-size:11px;color:#64748b;line-height:1.55}
.warn{color:#fbbf24}.an{cursor:pointer}
.an.sel{outline:1px solid #38bdf8;border-radius:6px}
a{color:#7dd3fc}</style></head><body>
<h1>Phase-aware allocation <span class="small">— suggestion from the frozen
study (PHASE_BARBELL_SPEC.md); nothing here trades</span></h1>
<div class="card" id="cur">loading…</div>
<div class="card"><h2>Suggested weights — <span id="scenlbl">current phase</span></h2>
<div style="margin:6px 0">
<span class="pill" data-r="defensive">defensive ×0.5</span>
<span class="pill on" data-r="balanced">balanced ×1.0</span>
<span class="pill" data-r="aggressive">aggressive ×1.5</span></div>
<div class="grid" id="wts"></div></div>
<div class="card"><h2>Scenario: what if today is really one of its analogs?</h2>
<div class="small" style="margin-bottom:6px">Top matches from the cycle
tracker's analog layer. Click one to see the allocation ITS phase implies;
click again to return to today. Caveats: top-10 spans few distinct
episodes; the analog has over-predicted recession since 2023.</div>
<table id="antbl"></table></div>
<div class="card"><h2>What the 91-year study says (corrected, panel-approved)</h2>
<table id="study"></table>
<div class="small" id="caveat" style="margin-top:8px"></div></div>
<script>
let B=null, risk="balanced", scen=null;
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function wcards(w){
  const C={stocks:'#4c9be8',bonds:'#8a93a5',gold:'#fbbf24',cash:'#34d399'};
  return Object.entries(w).map(([k,v])=>
    `<div><div class="w" style="color:${C[k]}">${v}%</div>
     <div class="wl">${k.toUpperCase()}</div></div>`).join('');
}
function draw(){
  if(!B)return;
  const ph = scen ? scen.phase_then : B.phase;
  const src = scen ? scen : B;
  document.getElementById('scenlbl').textContent =
    scen ? `analog ${scen.month} (${scen.phase_then})` : `current phase`;
  document.getElementById('wts').innerHTML =
    src.weights ? wcards(src.weights[risk]) : 'canary unreachable';
  document.getElementById('cur').innerHTML = B.phase ?
    `<span class="phase ${B.phase}">${B.phase.replace('_',' ')}</span>
     <span class="small">as of ${B.phase_month} · coincident ${B.coincident}
     · leading ${B.leading}</span>` +
    (B.nowcast_phase ? `<div class="small">nowcast ${B.nowcast_month}:
     <b class="${B.nowcast_phase}">${B.nowcast_phase}</b> — acting on the
     nowcast is the one-month-early variant; the study's headline uses the
     slower label</div>` : '') +
    (B.canary_reachable ? '' : '<div class="warn">showing cached canary data</div>')
    : '<span class="warn">cycle feed unreachable</span>';
  let h='<tr><th>analog</th><th>phase then</th><th>match</th><th>rec ≤12m</th><th></th></tr>';
  (B.analogs||[]).forEach((a,i)=>{
    h+=`<tr class="an ${scen&&scen.month===a.month?'sel':''}" data-i="${i}">
    <td>${esc(a.month)}</td><td class="${a.phase_then}">${esc(a.phase_then||'—')}</td>
    <td>${a.closer_than_pct}%</td>
    <td>${a.recession_within_12m==null?'—':a.recession_within_12m?'YES':'no'}</td>
    <td class="small">view →</td></tr>`;});
  document.getElementById('antbl').innerHTML=h;
  document.querySelectorAll('.an').forEach(tr=>tr.onclick=()=>{
    const a=B.analogs[+tr.dataset.i];
    scen = (scen&&scen.month===a.month)?null:a; draw();});
  let s='<tr><th></th><th>CAGR</th><th>max DD</th><th>Sharpe</th><th>worst 36m</th></tr>';
  B.study.rows.forEach(r=>{s+=`<tr><td>${esc(r[0])}</td><td>${r[1]}%</td>
    <td>${r[2]}%</td><td>${r[3]}</td><td>${r[4]}%</td></tr>`;});
  document.getElementById('study').innerHTML=s;
  document.getElementById('caveat').textContent=B.study.window+'. '+B.study.caveat;
}
document.querySelectorAll('.pill').forEach(p=>p.onclick=()=>{
  document.querySelectorAll('.pill').forEach(q=>q.classList.remove('on'));
  p.classList.add('on'); risk=p.dataset.r; draw();});
fetch('api/phase').then(r=>r.json()).then(b=>{B=b;draw();})
  .catch(()=>document.getElementById('cur').textContent='phase api failed');
</script></body></html>"""


@app.get("/phase", response_class=HTMLResponse)
def phase_page():
    return HTMLResponse(_PHASE_HTML)


# ------------------------------------------------------------------ register
@app.get("/api/portfolio")
def api_portfolio():
    from ..portfolio import registry
    con = _lab_con()
    try:
        live = registry.get_live(con)
        return {"version": live, "metrics": registry.version_metrics(con, live)}
    finally:
        con.close()


@app.get("/api/versions")
def api_versions():
    from ..portfolio import registry
    con = _lab_con()
    try:
        return registry.ledger(con)
    finally:
        con.close()


@app.post("/api/propose")
def api_propose(payload: dict):
    """File a candidate: {"weights": {..}?, "bot_frac": f?, "rationale": str}."""
    from ..portfolio import registry
    con = _lab_con()
    try:
        cand = registry.propose_candidate(
            con,
            weights={str(k).upper(): float(v) for k, v in (payload.get("weights") or {}).items()} or None,
            bot_frac=payload.get("bot_frac"),
            rationale=str(payload.get("rationale") or ""))
        return cand
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        con.close()


@app.get("/api/compare")
def api_compare(a: int, b: int):
    from ..portfolio import registry
    con = _lab_con()
    try:
        return registry.compare(con, a, b)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    finally:
        con.close()


@app.post("/api/promote")
def api_promote(payload: dict):
    """Promote a candidate: {"version_id": n, "confirm": "<exact label>"}.
    Typed confirmation is mandatory — this changes the live book's targets."""
    from ..portfolio import registry
    con = _lab_con()
    try:
        return registry.promote(con, int(payload["version_id"]),
                                str(payload.get("confirm", "")))
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        con.close()


@app.get("/versions", response_class=HTMLResponse)
def versions_page():
    from ..portfolio import registry
    con = _lab_con()
    try:
        versions = registry.list_versions(con)
    finally:
        con.close()
    rows = ""
    for v in versions:
        ev = v["evidence"] or {}
        w = " ".join(f"{t}:{x:.0%}" for t, x in
                     sorted(v["weights"].items(), key=lambda kv: -kv[1]))
        btn = ""
        if v["status"] == "CANDIDATE":
            btn = (f"<button class='pbtn' data-id='{v['id']}' "
                   f"data-label='{v['label']}'>promote</button>")
        rows += (f"<tr><td><b>{v['label']}</b></td><td>{v['status']}</td>"
                 f"<td>{v['created_at'][:10]}</td>"
                 f"<td style='font-size:.75rem'>{html.escape(w)} · bot {v['bot_frac']:.0%}</td>"
                 f"<td>{html.escape((v['rationale'] or '')[:70])}</td>"
                 f"<td>{ev.get('verdict') or '—'}</td>"
                 f"<td>{btn}</td></tr>")
    body = f"""
<h1>📒 Portfolio ledger</h1>
<p><a href="./">&larr; dashboard</a> · every version of the book, forever.
Promotion requires typing the exact version label.</p>
<div class="card"><table>
<tr><th>version</th><th>status</th><th>created</th><th>weights</th><th>rationale</th><th>verdict</th><th></th></tr>
{rows}</table></div>
<div class="card"><h2>Propose a candidate</h2>
<p><small>JSON weights (must sum to 1). Leave weights empty to only change the bot fraction.</small></p>
<textarea id="w" style="width:100%;height:90px;background:#0b1120;color:#d8e1ef;
 border:1px solid #2a3a58;border-radius:6px;padding:.5rem"
 placeholder='{{"AVUV":0.22,"AVDV":0.19,"PHYS":0.18,"KMLM":0.16,"AVEM":0.10,"QUAL":0.10,"TAIL":0.05}}'></textarea>
<div style="display:flex;gap:.5rem;margin-top:.4rem">
 <input id="bf" type="number" min="0" max="0.45" step="0.05" placeholder="bot frac (blank = keep)"
  style="background:#0b1120;color:#d8e1ef;border:1px solid #2a3a58;border-radius:6px;padding:.5rem"/>
 <input id="why" placeholder="rationale (why this change?)" style="flex:1;background:#0b1120;
  color:#d8e1ef;border:1px solid #2a3a58;border-radius:6px;padding:.5rem"/>
 <button id="go" style="background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:.5rem 1.2rem">
  Propose &amp; evaluate</button>
</div><div id="out" style="margin-top:.6rem"></div></div>
<script>
document.getElementById('go').onclick=async()=>{{
 const out=document.getElementById('out'); out.innerHTML='<span class="warn">evaluating…</span>';
 let w=null; const raw=document.getElementById('w').value.trim();
 if(raw){{ try{{w=JSON.parse(raw);}}catch(e){{out.innerHTML='<span class="bad">bad JSON</span>';return;}} }}
 const bf=document.getElementById('bf').value;
 try{{
  const r=await fetch('api/propose',{{method:'POST',headers:{{'Content-Type':'application/json'}},
   body:JSON.stringify({{weights:w, bot_frac: bf===''?null:parseFloat(bf),
    rationale:document.getElementById('why').value}})}});
  const j=await r.json(); if(!r.ok) throw new Error(j.detail||r.status);
  const ev=j.evidence||{{}};
  out.innerHTML='<b>'+j.label+'</b> filed — verdict <b>'+(ev.verdict||'?')+'</b>: '+
   (ev.basis||'')+' <a href="versions">reload ledger</a>';
 }}catch(e){{out.innerHTML='<span class="bad">'+e.message+'</span>';}}
}};
document.querySelectorAll('.pbtn').forEach(b=>b.onclick=async()=>{{
 const label=b.dataset.label;
 const typed=prompt('Type the exact label to promote to LIVE (this changes the book targets): '+label);
 if(typed===null) return;
 const r=await fetch('api/promote',{{method:'POST',headers:{{'Content-Type':'application/json'}},
  body:JSON.stringify({{version_id:parseInt(b.dataset.id), confirm:typed}})}});
 const j=await r.json();
 alert(r.ok? (j.label+' is now LIVE') : ('refused: '+(j.detail||r.status)));
 if(r.ok) location.reload();
}});
</script>"""
    return HTMLResponse(f"<!doctype html><html><head><title>Portfolio ledger</title>"
                        f"{_STYLE}</head><body>{body}</body></html>")


# ------------------------------------------------------------------ chat
@app.post("/api/chat")
def api_chat(payload: dict):
    """Grounded quant analyst with persistent memory.

    Preferred body: {"message": str, "conversation_id": int|null} — the server
    persists both turns, manages the context window (rolling summaries) and
    injects durable memory. Returns {conversation_id, text, tool_trace}.

    Legacy body {"messages": [...]} still works (stateless, no memory)."""
    text = payload.get("message")
    if isinstance(text, str) and text.strip():
        con = _lab_con()
        try:
            from ..chat.agent import answer_in_conversation
            cid = payload.get("conversation_id")
            return answer_in_conversation(con, int(cid) if cid else None, text.strip())
        except RuntimeError as exc:  # e.g. missing LLM key
            raise HTTPException(503, str(exc)) from None
        finally:
            con.close()
    msgs = payload.get("messages")
    if not isinstance(msgs, list) or not msgs:
        raise HTTPException(400, "body needs 'message' (preferred) or 'messages'")
    if any(m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str)
           for m in msgs):
        raise HTTPException(400, "each message needs role user|assistant and string content")
    from ..chat.agent import answer
    try:
        return answer([{"role": m["role"], "content": m["content"]} for m in msgs])
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None


@app.post("/api/chat/stream")
def api_chat_stream(payload: dict):
    """Streaming variant: NDJSON progress events while the analyst works.

    Lines: {"event":"memory"|"thinking"|"tool"|"tool_done"|"hb"} then a final
    {"event":"done","conversation_id","text","tool_trace"} or
    {"event":"error","detail"}. Heartbeats every 10s keep proxies from timing
    out during long LLM turns."""
    text = payload.get("message")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(400, "body needs 'message' (string)")
    cid = payload.get("conversation_id")
    import queue
    from ..chat.agent import answer_in_conversation
    events: queue.Queue = queue.Queue()

    def on_event(kind: str, detail: dict) -> None:
        events.put({"event": kind, **{k: v for k, v in detail.items()
                                      if k in ("turn", "tool", "detail", "error")}})

    def run() -> None:
        con = _lab_con()
        try:
            res = answer_in_conversation(con, int(cid) if cid else None,
                                         text.strip(), on_event=on_event)
            events.put({"event": "done", "conversation_id": res["conversation_id"],
                        "text": res["text"], "tool_trace": res["tool_trace"]})
        except Exception as exc:  # noqa: BLE001 — surfaced as an error event
            events.put({"event": "error", "detail": str(exc)})
        finally:
            con.close()
            events.put(None)

    threading.Thread(target=run, daemon=True).start()

    def gen():
        while True:
            try:
                item = events.get(timeout=10)
            except queue.Empty:
                yield json.dumps({"event": "hb"}) + "\n"
                continue
            if item is None:
                break
            yield json.dumps(item) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"cache-control": "no-cache",
                                      "x-accel-buffering": "no"})


@app.get("/api/conversations")
def api_conversations():
    from ..chat import memory
    con = _lab_con()
    try:
        return {"conversations": memory.list_conversations(con)}
    finally:
        con.close()


@app.get("/api/conversations/{cid}")
def api_conversation(cid: int):
    from ..chat import memory
    con = _lab_con()
    try:
        convo = memory.get_conversation(con, cid)
        return {"conversation": convo, "messages": memory.get_messages(con, cid)}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    finally:
        con.close()


@app.get("/api/memory")
def api_memory():
    from ..chat import memory
    con = _lab_con()
    try:
        return {"notes": memory.list_notes(con, limit=100)}
    finally:
        con.close()


@app.get("/chat", response_class=HTMLResponse)
def chat_page():
    body = """
<h1>⚖️ Barbell Lab — analyst chat</h1>
<p><a href="./">&larr; dashboard</a> · Grounded in the platform's own data; heavy
simulations run at exploratory path counts and register trials. Conversations
are <b>persisted with memory</b>: the analyst carries durable notes and can
recall past conversations. Slow answers are normal — it runs real computations.</p>
<div style="display:flex;gap:1rem;align-items:flex-start">
 <div style="flex:0 0 240px">
  <div class="card">
   <button id="newc" style="width:100%;background:#1f6feb;color:#fff;border:0;
    border-radius:6px;padding:.5rem;cursor:pointer">+ New conversation</button>
   <div id="convos" style="margin-top:.5rem"></div>
  </div>
 </div>
 <div style="flex:1;min-width:0">
  <div id="log"></div>
  <div class="card" style="display:flex;gap:.5rem">
   <input id="q" style="flex:1;background:#0b1120;color:#d8e1ef;border:1px solid #2a3a58;
    border-radius:6px;padding:.6rem" placeholder="e.g. sweep the bot fraction under a failing kill-switch"/>
   <button id="send" style="background:#1f6feb;color:#fff;border:0;border-radius:6px;
    padding:.6rem 1.2rem;cursor:pointer">Ask</button>
  </div>
 </div>
</div>
<script>
const log=document.getElementById('log'), q=document.getElementById('q'),
      send=document.getElementById('send'), convos=document.getElementById('convos');
let cid = parseInt(localStorage.getItem('barbell_cid')) || null;
function esc(s){return s.replace(/</g,'&lt;');}
function add(cls, html){const d=document.createElement('div');d.className='card '+cls;
  d.innerHTML=html;log.appendChild(d);d.scrollIntoView();}
function renderMsg(m){
  if(m.role==='user') add('', '<b>you</b><br>'+esc(m.content).replace(/\\n/g,'<br>'));
  else {
    const tools=(m.tool_trace||[]).map(t=>'⚙ '+t.tool).join(' · ');
    add('', (tools?'<div class="warn">'+tools+'</div>':'') +
      '<b>analyst</b><br>'+esc(m.content).replace(/\\n/g,'<br>'));
  }
}
async function loadConvos(){
  try{
    const j = await (await fetch('api/conversations')).json();
    convos.innerHTML = (j.conversations||[]).map(c=>
      `<div class="convo" data-id="${c.id}" style="padding:.35rem;border-radius:6px;cursor:pointer;
        margin-top:.2rem;font-size:.85rem;${c.id===cid?'background:#1c2b47':''}">
        ${esc(c.title||'(untitled)').slice(0,60)}<br>
        <span style="color:#7d8aa5;font-size:.75rem">${(c.updated_at||'').slice(0,10)} · ${c.n_messages} msgs</span>
       </div>`).join('') || '<div style="color:#7d8aa5;font-size:.85rem">no conversations yet</div>';
    convos.querySelectorAll('.convo').forEach(el=>el.onclick=()=>openConvo(parseInt(el.dataset.id)));
  }catch(e){}
}
async function openConvo(id){
  cid=id; localStorage.setItem('barbell_cid', id); log.innerHTML='';
  try{
    const j = await (await fetch('api/conversations/'+id)).json();
    (j.messages||[]).forEach(renderMsg);
  }catch(e){ add('bad','could not load conversation'); }
  loadConvos();
}
document.getElementById('newc').onclick=()=>{cid=null;
  localStorage.removeItem('barbell_cid'); log.innerHTML='';
  add('','<span style="color:#7d8aa5">new conversation — memory notes and past-conversation context carry over automatically</span>');
  loadConvos(); q.focus();};
async function ask(){
  const text=q.value.trim(); if(!text) return;
  q.value=''; renderMsg({role:'user', content:text});
  send.disabled=true; send.textContent='…';
  const st=document.createElement('div'); st.className='card';
  log.appendChild(st); st.scrollIntoView();
  const t0=Date.now(); let acts=['🧠 analyst thinking…'];
  const paint=()=>{st.innerHTML='<span class="warn">'+acts.map(esc).join('<br>')+
    '</span><br><span style="color:#7d8aa5;font-size:.8rem">'+
    Math.round((Date.now()-t0)/1000)+'s — long runs are normal, real computations</span>';};
  paint(); const tick=setInterval(paint, 1000);
  let finished=false;
  try{
    const r = await fetch('api/chat/stream', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message:text, conversation_id:cid})});
    if(!r.ok || !r.body){
      const t=await r.text(); let d=t;
      try{d=JSON.parse(t).detail||t;}catch(_e){}
      throw new Error(String(d).slice(0,300));
    }
    const rd=r.body.getReader(), dec=new TextDecoder(); let buf='';
    while(true){
      const {value, done}=await rd.read(); if(done) break;
      buf+=dec.decode(value,{stream:true});
      let nl;
      while((nl=buf.indexOf('\\n'))>=0){
        const line=buf.slice(0,nl).trim(); buf=buf.slice(nl+1);
        if(!line) continue;
        let j; try{j=JSON.parse(line);}catch(_e){continue;}
        if(j.event==='memory') acts.push('📚 recalling memory…');
        else if(j.event==='thinking') acts.push('🧠 thinking (round '+j.turn+')…');
        else if(j.event==='tool') acts.push('⚙ running '+j.tool+'…');
        else if(j.event==='tool_done' && j.error) acts.push('⚠ '+j.tool+' errored — analyst will handle it');
        else if(j.event==='error') throw new Error(String(j.detail).slice(0,300));
        else if(j.event==='done'){
          finished=true; cid=j.conversation_id; localStorage.setItem('barbell_cid', cid);
          clearInterval(tick); st.remove();
          renderMsg({role:'assistant', content:j.text, tool_trace:j.tool_trace});
          loadConvos();
        }
        if(!finished) paint();
      }
    }
    if(!finished) throw new Error('stream ended without a final answer — check the conversation list; the reply may have been saved');
  }catch(e){
    clearInterval(tick); st.remove();
    if(!finished) add('bad', 'error: '+esc(String(e.message||e)));
  }
  clearInterval(tick);
  send.disabled=false; send.textContent='Ask'; q.focus();
}
send.onclick=ask; q.addEventListener('keydown', e=>{if(e.key==='Enter')ask();});
if(cid) openConvo(cid); else loadConvos();
</script>"""
    return HTMLResponse(f"<!doctype html><html><head><title>Barbell Lab chat</title>"
                        f"{_STYLE}</head><body>{body}</body></html>")
