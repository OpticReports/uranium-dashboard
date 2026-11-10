"""Telegram alerts — same bot, same chat as treasury-canary and the executors.

Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID on this service too; unset = no-op.
Fire-and-forget on a daemon thread so a slow Telegram never stalls a scan
(treasury-canary/backend/app/alerts.py is the pattern this follows).

SEVERITY IS RANKED BY HOW MUCH TIME THE RUNG LEAVES YOU, not by how dramatic
it looks. That inverts the obvious ordering, and deliberately:

  CRITICAL  RAMPING   — the meme rung. On the Farmmi timeline this left ~13
                        minutes before the tape moved. Act now or not at all.
  RED       TOKENIZED — a nanocap has been wrapped on-chain and nothing is
                        built on it yet. ~15.8h of lead in the one case
                        observed. This is the rung worth waking up for.
  WARN      CLUSTER   — six memes against one ticker is the screenshot
                        moment, and on that same timeline it arrived 1.9h
                        AFTER the move. Context, not a call.

TELEGRAM_MIN_SEVERITY (default WARN) filters what reaches the phone. Set it to
RED to drop the cluster notices and keep only the two actionable rungs.
"""
from __future__ import annotations

import logging
import os
import threading

import httpx

logger = logging.getLogger(__name__)

_RANK = {"INFO": 0, "WARN": 1, "RED": 2, "CRITICAL": 3}
_ICON = {"INFO": "ℹ️", "WARN": "🟡", "RED": "🔴", "CRITICAL": "🚨"}

# Rung -> severity. See the module docstring for why this is not the intuitive
# ordering: it ranks by remaining runway, not by how loud the rung looks.
STAGE_SEVERITY = {
    "RAMPING": "CRITICAL",
    "TOKENIZED": "RED",
    "CLUSTER": "WARN",
}


def min_severity() -> str:
    return os.environ.get("TELEGRAM_MIN_SEVERITY", "WARN").upper()


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN")
                and os.environ.get("TELEGRAM_CHAT_ID"))


def should_send(severity: str) -> bool:
    if not configured():
        return False
    return _RANK.get(severity.upper(), 0) >= _RANK.get(min_severity(), 1)


def send(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return

    def _post():
        try:
            httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat, "text": text[:4000],
                             "disable_web_page_preview": True}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram send failed: %s", exc)

    threading.Thread(target=_post, daemon=True).start()


def _money(x) -> str:
    if not x:
        return "-"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(x) >= div:
            return f"${x/div:,.1f}{unit}"
    return f"${x:,.0f}"


def format_alert(alert: dict) -> str:
    """One message: what fired, why, the equity state, and THE POOLS.

    The pool links are the point of the message — a ticker with no way to look
    at what is actually trading against it is not actionable.
    """
    stage = alert.get("stage", "")
    severity = STAGE_SEVERITY.get(stage, "INFO")
    icon = _ICON.get(severity, "ℹ️")

    px = alert.get("equity_price")
    chg = alert.get("equity_change_pct")
    rvol = alert.get("equity_rvol")
    tape = (f"${px:,.4f}" if isinstance(px, (int, float)) else "?")
    if isinstance(chg, (int, float)):
        tape += f" ({chg:+.1f}%)"
    if isinstance(rvol, (int, float)):
        tape += f" · {rvol:,.0f}x vol"

    lines = [
        f"{icon} screener {stage} [{severity}]",
        f"{alert.get('ticker','?')} — {alert.get('company','')}",
        f"score {alert.get('score','?')} · {alert.get('issuer_class','')}",
        f"tape: {tape}",
    ]
    fl = alert.get("float_shares")
    ft = alert.get("float_turnover")
    if fl:
        line = f"float: {fl/1e6:,.1f}M sh"
        if isinstance(ft, (int, float)):
            line += f" · {ft:,.1f}x turned over today"
        lines.append(line)

    facs = alert.get("pump_factors") or []
    if facs:
        top = " · ".join(f"{f['label']} {f['display']}" for f in facs[:3])
        lines.append(f"why pumpable: {top}")

    dil = alert.get("dilution_flag")
    if dil:
        lines.append(f"⚠ dilution: {dil}")

    wrapper = alert.get("wrapper_url")
    if wrapper:
        lines.append("")
        lines.append(f"wrapper: {wrapper}")

    pools = alert.get("pools") or []
    if pools:
        lines.append("")
        lines.append(f"pools ({len(pools)} shown):")
        for p in pools:
            lines.append(
                f"• {p.get('symbol','?')} — liq {_money(p.get('liquidity_usd'))}"
                f" · 24h {_money(p.get('volume_h24'))}"
                f" · {p.get('trend','')}".rstrip(" ·"))
            if p.get("url"):
                lines.append(f"  {p['url']}")
    else:
        lines.append("")
        lines.append("pools: none yet — the wrapper exists, nothing built on it")

    for reason in (alert.get("reasons") or [])[:3]:
        lines.append(f"· {reason}")
    return "\n".join(lines)


def push(alert: dict) -> bool:
    """Send if severity clears the floor. Returns whether it was sent."""
    severity = STAGE_SEVERITY.get(alert.get("stage", ""), "INFO")
    if not should_send(severity):
        return False
    send(format_alert(alert))
    return True
