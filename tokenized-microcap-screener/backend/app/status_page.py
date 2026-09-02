"""Server-rendered status page (no frontend build, catalyst-options-engine
pattern). Deliberately visual: the ladder histogram and the per-row score bars
are there so the state of the board reads at a glance rather than needing the
JSON parsed (CLAUDE.md standing preference for visuals with every study)."""
from __future__ import annotations

import html
from datetime import datetime

from .models import STAGES, Candidate

_STAGE_COLOR = {
    "TOKENIZED": "#4b5563", "PAIRED": "#2563eb", "RAMPING": "#d97706",
    "CLUSTER": "#dc2626", "EQUITY_MOVING": "#7c3aed", "FADED": "#374151",
}


def _bar(value: float, color: str, width: int = 90) -> str:
    pct = max(0.0, min(100.0, float(value or 0.0)))
    return (f'<div class="bar" style="width:{width}px">'
            f'<i style="width:{pct:.0f}%;background:{color}"></i>'
            f'<b>{pct:.0f}</b></div>')


def _fmt_money(x) -> str:
    if not x:
        return "—"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(x) >= div:
            return f"${x/div:,.1f}{unit}"
    return f"${x:,.0f}"


def _fmt_pct(x) -> str:
    return "—" if x is None else f"{x:+.1f}%"


def _ladder_hist(rows: list[Candidate]) -> str:
    counts = {s: 0 for s in STAGES}
    for r in rows:
        counts[r.stage] = counts.get(r.stage, 0) + 1
    top = max(counts.values()) or 1
    cells = []
    for s in STAGES:
        h = int(70 * counts[s] / top)
        cells.append(
            f'<div class="hcell"><span class="hnum">{counts[s]}</span>'
            f'<div class="hbar" style="height:{max(h,2)}px;'
            f'background:{_STAGE_COLOR[s]}"></div>'
            f'<span class="hlab">{s.replace("_", " ").title()}</span></div>')
    return f'<div class="hist">{"".join(cells)}</div>'


def _leadlag_panel(ll: dict) -> str:
    parts = []
    for label, leg in (ll.get("legs") or {}).items():
        n, med = leg.get("n", 0), leg.get("median_hours")
        badge = "" if leg.get("interpretable") else '<em class="thin">n too small</em>'
        parts.append(
            f'<tr><td>{html.escape(label)}</td><td class="num">{n}</td>'
            f'<td class="num">{"—" if med is None else f"{med:.1f}h"}</td>'
            f'<td>{badge}</td></tr>')
    hit = ll.get("hit_rate")
    return f"""
    <table class="mini">
      <tr><th>leg</th><th>n</th><th>median</th><th></th></tr>
      {''.join(parts)}
    </table>
    <p class="thin">alerts fired {ll.get('alerts_fired', 0)} ·
       followed by an equity move {ll.get('alerts_followed_by_move', 0)} ·
       hit rate {'—' if hit is None else f'{hit:.0%}'}</p>
    <p class="thin">{html.escape(ll.get('caveat', ''))}</p>"""


def render_status_page(rows: list[Candidate], leadlag: dict, registry_size: int,
                       cfg: dict) -> str:
    body = []
    for r in rows:
        colour = _STAGE_COLOR.get(r.stage, "#4b5563")
        official = r.issuer_class.startswith("OFFICIAL")
        wrapper = ('<span class="tag ok">official</span>' if official
                   else '<span class="tag warn">unofficial</span>')
        body.append(f"""
        <tr>
          <td><b>{html.escape(r.ticker)}</b><div class="thin">
              {html.escape((r.company or '')[:32])}</div></td>
          <td><span class="stage" style="background:{colour}">
              {html.escape(r.stage.replace('_', ' '))}</span><br>{wrapper}</td>
          <td>{_bar(r.alert_score, '#16a34a')}</td>
          <td>{_bar(r.heat, '#d97706')}</td>
          <td>{_bar(r.earliness, '#2563eb')}</td>
          <td>{_bar(r.credibility, '#64748b')}</td>
          <td>{_bar(r.pumpability, '#9333ea')}</td>
          <td class="num">{r.meme_count}<div class="thin">
              {html.escape(r.top_meme_symbol or '')}</div></td>
          <td class="num">{_fmt_money(r.onchain_volume_h24)}<div class="thin">
              liq {_fmt_money(r.onchain_liquidity_usd)}</div></td>
          <td class="num">{'dark' if r.equity_dark else
              (f'${r.equity_price:,.4f}' if r.equity_price else '—')}
              <div class="thin">{_fmt_pct(r.equity_change_pct)}
              {'' if r.equity_rvol is None else f' · {r.equity_rvol:,.0f}x vol'}</div></td>
          <td class="thin">{html.escape(' · '.join((r.reasons or [])[:2]))}</td>
        </tr>""")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Tokenized Microcap Screener</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root {{ color-scheme: dark; }}
 body {{ background:#0b0f17; color:#e5e7eb; font:13px/1.5 ui-sans-serif,
        system-ui,-apple-system,"Segoe UI",sans-serif; margin:0; padding:24px; }}
 h1 {{ font-size:18px; margin:0 0 2px; }}
 h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.08em;
       color:#9ca3af; margin:28px 0 8px; }}
 .thin {{ color:#9ca3af; font-size:11px; font-style:normal; }}
 .wrap {{ max-width:1400px; margin:0 auto; }}
 .note {{ background:#1f2937; border-left:3px solid #d97706; padding:10px 14px;
          margin:16px 0; border-radius:4px; }}
 table {{ border-collapse:collapse; width:100%; }}
 th,td {{ text-align:left; padding:7px 9px; border-bottom:1px solid #1f2937;
          vertical-align:top; }}
 th {{ color:#9ca3af; font-weight:600; font-size:11px; text-transform:uppercase;
       letter-spacing:.05em; }}
 td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
 .stage {{ display:inline-block; padding:1px 7px; border-radius:3px;
           font-size:10px; font-weight:700; letter-spacing:.04em; }}
 .tag {{ display:inline-block; margin-top:3px; padding:0 5px; border-radius:3px;
         font-size:10px; }}
 .tag.ok {{ background:#064e3b; color:#6ee7b7; }}
 .tag.warn {{ background:#4c1d24; color:#fca5a5; }}
 .bar {{ position:relative; height:14px; background:#1f2937; border-radius:2px; }}
 .bar i {{ position:absolute; left:0; top:0; bottom:0; border-radius:2px; }}
 .bar b {{ position:absolute; right:4px; top:-1px; font-size:10px; color:#e5e7eb; }}
 .hist {{ display:flex; gap:18px; align-items:flex-end; height:110px;
          padding:8px 0; }}
 .hcell {{ display:flex; flex-direction:column; align-items:center;
           justify-content:flex-end; width:96px; }}
 .hbar {{ width:44px; border-radius:3px 3px 0 0; }}
 .hnum {{ font-size:12px; font-weight:700; margin-bottom:4px; }}
 .hlab {{ font-size:10px; color:#9ca3af; margin-top:6px; text-align:center; }}
 table.mini {{ max-width:520px; }}
</style></head><body><div class="wrap">
<h1>Tokenized Microcap Screener</h1>
<div class="thin">{registry_size} tokenized equities in the registry ·
  {len(rows)} candidates · generated {datetime.utcnow():%Y-%m-%d %H:%M} UTC</div>

<div class="note"><b>What this is.</b> A screen for memecoins pooled against a
 tokenized share of a listed company, ranked by how much of the equity move
 looks still to come. It is a <b>watchlist generator, not a signal</b>: the
 lead time it depends on has been observed once (Farmmi, 2026-09-02) and is
 being measured below, not assumed. An <b>unofficial</b> wrapper has no
 mint/redeem path, so nothing mechanically transmits on-chain buying to the
 tape — the only link is people seeing it. Sub-$1 nanocaps round-trip: FAMI
 printed +321% intraday and gave most of it back the same session.</div>

<h2>Ladder</h2>
{_ladder_hist(rows)}

<h2>Candidates</h2>
<table>
 <tr><th>ticker</th><th>stage</th><th>alert</th><th>heat</th><th>early</th>
     <th>cred</th><th>pump</th><th>memes</th><th>onchain 24h</th>
     <th>equity</th><th>why</th></tr>
 {''.join(body) or '<tr><td colspan="11" class="thin">no candidates yet — the first sweep seeds the registry</td></tr>'}
</table>

<h2>Lead-lag (measured, not assumed)</h2>
{_leadlag_panel(leadlag)}
</div></body></html>"""
