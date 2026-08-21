"""Server-rendered HTML status page (no build step, no JS framework).

One dark page, three tables: radar (scored setups + lane-health flags), open
paper positions, closed positions + book summary. Aesthetic matches the hub
(slate #0f172a background, #60a5fa accents).
"""
from __future__ import annotations

import html
from datetime import date

from .engine.ledger import BookSummary
from .models import EquityPoint, PaperPosition, Setup

_CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;
  background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%); color:#e2e8f0;
  line-height:1.5; min-height:100vh; padding:32px 20px; }
.container { max-width:1280px; margin:0 auto; }
h1 { color:#60a5fa; font-size:1.9em; margin-bottom:2px;
  text-shadow:0 0 30px rgba(96,165,250,.3); }
.tagline { color:#94a3b8; margin-bottom:8px; }
.law { color:#86efac; background:rgba(34,197,94,.08); border:1px solid #14532d;
  display:inline-block; padding:4px 12px; border-radius:8px; font-size:.85em;
  margin-bottom:24px; }
h2 { color:#93c5fd; font-size:1.15em; margin:28px 0 10px; }
.card { background:rgba(30,41,59,.8); border:1px solid #334155;
  border-radius:12px; padding:18px; overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:.86em; }
th { text-align:left; color:#94a3b8; font-weight:600; padding:6px 10px;
  border-bottom:1px solid #334155; white-space:nowrap; }
td { padding:6px 10px; border-bottom:1px solid #1e293b; white-space:nowrap; }
tr:hover td { background:rgba(96,165,250,.05); }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.good { color:#4ade80; } .bad { color:#f87171; } .dim { color:#64748b; }
.flag { color:#fbbf24; font-size:.9em; }
.watch { color:#c084fc; }
.badge { display:inline-block; padding:1px 8px; border-radius:6px;
  font-size:.85em; border:1px solid #334155; }
.badge.ask { border-color:#166534; color:#86efac; }
.badge.bs { border-color:#92400e; color:#fbbf24; }
.kpis { display:flex; gap:18px; flex-wrap:wrap; margin-bottom:6px; }
.kpi { background:rgba(30,41,59,.8); border:1px solid #334155;
  border-radius:10px; padding:12px 18px; }
.kpi .v { font-size:1.4em; color:#60a5fa; font-variant-numeric:tabular-nums; }
.kpi .l { color:#94a3b8; font-size:.8em; }
footer { color:#475569; font-size:.8em; margin-top:26px; }
"""


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _f(v, nd=2, suffix="") -> str:
    if v is None:
        return '<span class="dim">—</span>'
    return f"{v:.{nd}f}{suffix}"


def _money(v) -> str:
    if v is None:
        return '<span class="dim">—</span>'
    cls = "good" if v > 0 else ("bad" if v < 0 else "")
    return f'<span class="{cls}">${v:,.0f}</span>'


def _basis_badge(basis: str | None) -> str:
    if not basis:
        return '<span class="dim">—</span>'
    cls = "ask" if str(basis).startswith("chain") else "bs"
    return f'<span class="badge {cls}">{_esc(basis)}</span>'


def _setup_rows(setups: list[Setup]) -> str:
    def sort_key(s: Setup):
        return (-(s.score if s.score is not None else -1), s.symbol)

    out = []
    for s in sorted(setups, key=sort_key):
        score = (f'<b>{s.score:.1f}</b>' if s.score is not None
                 else ('<span class="watch">watch</span>' if s.watch
                       else '<span class="dim">—</span>'))
        flags = ", ".join(s.flags or [])
        out.append(
            f"<tr><td><b>{_esc(s.symbol)}</b></td>"
            f'<td class="num">{score}</td>'
            f'<td class="num">{_esc(s.days_to_event) or "—"}</td>'
            f"<td>{_esc(s.event_date) or '—'}</td>"
            f"<td>{_esc(s.event_type) or '—'}</td>"
            f'<td class="num">{_f(s.impact_weight)}</td>'
            f'<td class="num">{_f(s.drift_z10)}</td>'
            f'<td class="num">{_f(s.iv_ratio)}</td>'
            f'<td class="num">{_f(s.atm_iv)}</td>'
            f'<td class="num">{_f(s.rv20)}</td>'
            f'<td class="num">{_f(s.spot)}</td>'
            f'<td class="flag">{_esc(flags)}</td></tr>')
    return "".join(out)


def _position_rows(positions: list[PaperPosition]) -> str:
    out = []
    for p in positions:
        pnl = (p.realized_pnl if p.status == "closed"
               else (p.mark_value - p.entry_cost if p.mark_value is not None else None))
        out.append(
            f"<tr><td><b>{_esc(p.symbol)}</b></td>"
            f"<td>{_esc(p.structure)}</td>"
            f'<td class="num">{_f(p.strike, 2)}</td>'
            f"<td>{_esc(p.expiry)}</td>"
            f"<td>{_esc(p.event_date) or '—'}</td>"
            f'<td class="num">{p.contracts}</td>'
            f"<td>{_esc(p.entry_date)}</td>"
            f'<td class="num">{_f(p.entry_unit_premium)}</td>'
            f'<td class="num">{_money(p.entry_cost)}</td>'
            f"<td>{_basis_badge(p.pricing_basis)}</td>"
            f'<td class="num">{_money(p.mark_value if p.status == "open" else p.close_proceeds)}</td>'
            f"<td>{_basis_badge(p.mark_basis if p.status == 'open' else p.close_basis)}</td>"
            f'<td class="num">{_money(pnl)}</td>'
            f"<td>{_esc(p.status)}</td></tr>")
    return "".join(out)


def render_status_page(setups: list[Setup], positions: list[PaperPosition],
                       book: BookSummary, equity: list[EquityPoint],
                       asof: date) -> str:
    open_pos = [p for p in positions if p.status == "open"]
    closed_pos = [p for p in positions if p.status == "closed"]
    hit = "—" if book.hit_rate is None else f"{100 * book.hit_rate:.0f}%"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Catalyst Options Engine</title><style>{_CSS}</style></head><body>
<div class="container">
<h1>Catalyst Options Engine</h1>
<div class="tagline">Pre-catalyst asymmetry radar — biotech/pharma binary events vs. quiet tape vs. option pricing</div>
<div class="law">PAPER ONLY &middot; KEYLESS &middot; no execution path exists in this service (house law: executors hold the keys)</div>

<div class="kpis">
<div class="kpi"><div class="v">${book.equity:,.0f}</div><div class="l">book equity (start ${book.starting_equity:,.0f})</div></div>
<div class="kpi"><div class="v">${book.cash:,.0f}</div><div class="l">cash</div></div>
<div class="kpi"><div class="v">{_money(book.realized_pnl)}</div><div class="l">realized P&amp;L</div></div>
<div class="kpi"><div class="v">{book.open_positions}</div><div class="l">open positions</div></div>
<div class="kpi"><div class="v">{book.closed_positions}</div><div class="l">graded setups</div></div>
<div class="kpi"><div class="v">{hit}</div><div class="l">hit rate</div></div>
</div>

<h2>Radar — latest scan ({asof.isoformat()})</h2>
<div class="card"><table>
<tr><th>Symbol</th><th class="num">Score</th><th class="num">Days</th><th>Event date</th>
<th>Event</th><th class="num">Impact</th><th class="num">Drift z10</th>
<th class="num">IV ratio</th><th class="num">ATM IV</th><th class="num">RV 20d</th>
<th class="num">Spot</th><th>Flags</th></tr>
{_setup_rows(setups) or '<tr><td colspan="12" class="dim">no scan yet — scheduler runs at boot, or POST /scan</td></tr>'}
</table></div>

<h2>Open paper positions</h2>
<div class="card"><table>
<tr><th>Symbol</th><th>Structure</th><th class="num">Strike</th><th>Expiry</th>
<th>Event</th><th class="num">Qty</th><th>Entered</th><th class="num">Unit prem</th>
<th class="num">Cost</th><th>Entry basis</th><th class="num">Mark</th>
<th>Mark basis</th><th class="num">Unrlzd</th><th>Status</th></tr>
{_position_rows(open_pos) or '<tr><td colspan="14" class="dim">none</td></tr>'}
</table></div>

<h2>Closed positions</h2>
<div class="card"><table>
<tr><th>Symbol</th><th>Structure</th><th class="num">Strike</th><th>Expiry</th>
<th>Event</th><th class="num">Qty</th><th>Entered</th><th class="num">Unit prem</th>
<th class="num">Cost</th><th>Entry basis</th><th class="num">Proceeds</th>
<th>Exit basis</th><th class="num">Realized</th><th>Status</th></tr>
{_position_rows(closed_pos) or '<tr><td colspan="14" class="dim">none yet</td></tr>'}
</table></div>

<footer>Entries at ASK, exits at BID when real quotes exist; bs_scenario rows are
Black-Scholes at scenario IV (chain lane dark), not market prices. Max loss is
always the premium paid. API: /health /radar /setups /paper/book
/paper/positions &middot; POST /catalysts /scan /paper/close/&#123;id&#125;</footer>
</div></body></html>"""
