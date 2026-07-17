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
from fastapi.responses import HTMLResponse, PlainTextResponse

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


@app.get("/health")
def health():
    return {"status": "ok", "app": "barbell-lab"}


@app.get("/", response_class=HTMLResponse)
def index():
    con = db.connect()
    try:
        trials = con.execute("SELECT COUNT(*) FROM trials").fetchone()[0]
        regime = con.execute(
            "SELECT date, quadrant, labor_z, inflation_z, credit_z, dollar_z "
            "FROM regime_log ORDER BY date DESC LIMIT 1").fetchone()
        alerts = con.execute(
            "SELECT ts_utc, kind, message FROM alerts ORDER BY id DESC LIMIT 10").fetchall()
        vrows = con.execute(
            "SELECT check_name, COUNT(*), SUM(passed) FROM validation_log "
            "WHERE ts_utc >= (SELECT MAX(ts_utc) FROM validation_log) "
            "GROUP BY check_name").fetchall()
        gates_html = ""
        try:
            from ..validate.acceptance import run_gates
            gates = run_gates(con)
            gates_html = "".join(
                f"<div class='{'ok' if g.passed else 'bad'}'>{html.escape(str(g))}</div>"
                for g in gates)
        except Exception as exc:  # noqa: BLE001
            gates_html = f"<div class='bad'>gates unavailable: {html.escape(str(exc))}</div>"
    finally:
        con.close()

    reports = sorted(REPORT_DIR.glob("latest-*.md")) if REPORT_DIR.exists() else []
    rep_links = "".join(
        f"<li><a href='reports/{r.name}'>{r.name.removeprefix('latest-').removesuffix('.md')}</a></li>"
        for r in reports) or "<li>none yet — run the CLI</li>"

    regime_html = "<div class='warn'>no regime snapshot yet</div>"
    if regime:
        d, q, lz, iz, cz, dz = regime
        regime_html = (f"<b>{html.escape(q.upper())}</b> ({d}) — labor z {lz:+.2f}, "
                       f"inflation z {iz:+.2f}, credit z {cz:+.2f}, dollar z {dz:+.2f}")
    alerts_html = "".join(
        f"<div><code>{a[0][:19]}</code> <b>{html.escape(a[1])}</b> {html.escape(a[2])}</div>"
        for a in alerts) or "<div class='ok'>no alerts</div>"
    val_html = "".join(
        f"<div>{html.escape(c)}: {int(p)}/{int(n)} passed</div>" for c, n, p in vrows) \
        or "<div class='warn'>no validation runs recorded</div>"

    body = f"""
<h1>⚖️ Barbell Lab</h1>
<p>Personal quant research platform — B.5 Enhanced sleeve + short-vol bot.
CLI-first; this page is a read-only view. <b>Cumulative trials: {trials}</b>
&nbsp;·&nbsp; <a href="chat">💬 analyst chat</a></p>
<div class="card"><h2>Acceptance gates (platform trust)</h2>{gates_html}</div>
<div class="card"><h2>Regime</h2>{regime_html}</div>
<div class="card"><h2>Latest validation</h2>{val_html}</div>
<div class="card"><h2>Reports</h2><ul>{rep_links}</ul></div>
<div class="card"><h2>Recent alerts</h2>{alerts_html}</div>
"""
    return HTMLResponse(f"<!doctype html><html><head><title>Barbell Lab</title>"
                        f"{_STYLE}</head><body>{body}</body></html>")


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


# ------------------------------------------------------------------ chat
@app.post("/api/chat")
def api_chat(payload: dict):
    """Grounded quant analyst. Body: {"messages": [{"role","content"}...]}.
    Runs the platform-tool agent loop; heavy sims are exploratory-path and
    register trials like everything else."""
    msgs = payload.get("messages")
    if not isinstance(msgs, list) or not msgs:
        raise HTTPException(400, "messages must be a non-empty list")
    if any(m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str)
           for m in msgs):
        raise HTTPException(400, "each message needs role user|assistant and string content")
    from ..chat.agent import answer
    try:
        return answer([{"role": m["role"], "content": m["content"]} for m in msgs])
    except RuntimeError as exc:  # e.g. missing ANTHROPIC_API_KEY
        raise HTTPException(503, str(exc)) from None


@app.get("/chat", response_class=HTMLResponse)
def chat_page():
    body = """
<h1>⚖️ Barbell Lab — analyst chat</h1>
<p><a href="./">&larr; dashboard</a> · Grounded in the platform's own data; heavy
simulations run at exploratory path counts and register trials. Slow answers are
normal — the analyst is running real computations.</p>
<div id="log"></div>
<div class="card" style="display:flex;gap:.5rem">
 <input id="q" style="flex:1;background:#0b1120;color:#d8e1ef;border:1px solid #2a3a58;
  border-radius:6px;padding:.6rem" placeholder="e.g. sweep the bot fraction under a failing kill-switch"/>
 <button id="send" style="background:#1f6feb;color:#fff;border:0;border-radius:6px;
  padding:.6rem 1.2rem;cursor:pointer">Ask</button>
</div>
<script>
const log = document.getElementById('log'), q = document.getElementById('q'),
      send = document.getElementById('send'); let history = [];
function add(cls, html){const d=document.createElement('div');d.className='card '+cls;
  d.innerHTML=html;log.appendChild(d);d.scrollIntoView();}
async function ask(){
  const text = q.value.trim(); if(!text) return;
  q.value=''; add('', '<b>you</b><br>'+text.replace(/</g,'&lt;'));
  history.push({role:'user', content:text});
  send.disabled=true; send.textContent='…';
  try{
    const r = await fetch('api/chat', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({messages: history})});
    const j = await r.json();
    if(!r.ok) throw new Error(j.detail || r.status);
    const tools = (j.tool_trace||[]).map(t=>'⚙ '+t.tool).join(' · ');
    add('', (tools?'<div class="warn">'+tools+'</div>':'') +
        '<b>analyst</b><br>'+ j.text.replace(/</g,'&lt;').replace(/\\n/g,'<br>'));
    history.push({role:'assistant', content:j.text});
  }catch(e){ add('bad', 'error: '+e.message); history.pop(); }
  send.disabled=false; send.textContent='Ask'; q.focus();
}
send.onclick=ask; q.addEventListener('keydown', e=>{if(e.key==='Enter')ask();});
</script>"""
    return HTMLResponse(f"<!doctype html><html><head><title>Barbell Lab chat</title>"
                        f"{_STYLE}</head><body>{body}</body></html>")
