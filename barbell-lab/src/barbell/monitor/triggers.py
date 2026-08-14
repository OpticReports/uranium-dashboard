"""Config-driven trigger rules from prior research. Monitors flag; they never
trade. The Fed-dovish-pivot leg of the AVEM rule is a manual flag in
``data/flags.json`` ({"fed_dovish_pivot": true}) until an automated
classifier earns trust.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .. import db
from ..config import ROOT, load


def _manual_flags() -> dict:
    p = ROOT / "data" / "flags.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def evaluate_triggers(con: sqlite3.Connection) -> list[dict]:
    fired: list[dict] = []
    flags = _manual_flags()

    dxy = db.read_fred(con, "DTWEXBGS").dropna()
    hy = db.read_fred(con, "BAMLH0A0HYM2").dropna()
    vix = db.read_prices(con, "^VIX")["close_raw"].dropna()
    vix3m = db.read_prices(con, "^VIX3M")["close_raw"].dropna()
    for name, s in [("DTWEXBGS", dxy), ("HY OAS", hy), ("^VIX", vix), ("^VIX3M", vix3m)]:
        if s.empty:
            raise RuntimeError(f"trigger inputs missing: {name} — run `barbell ingest`")

    # 1. DXY < 98 AND Fed dovish pivot -> reverse AVEM trim
    dxy_last = float(dxy.iloc[-1])
    if dxy_last < 98.0 and bool(flags.get("fed_dovish_pivot")):
        fired.append({"id": "avem_reverse_trim",
                      "action": "reverse AVEM trim",
                      "detail": f"DTWEXBGS {dxy_last:.1f} < 98 and fed_dovish_pivot flag set"})

    # 2. VIX term-structure backwardation -> bot kill-switch zone
    last_common = min(vix.index.max(), vix3m.index.max())
    v, v3 = float(vix.loc[:last_common].iloc[-1]), float(vix3m.loc[:last_common].iloc[-1])
    if v > v3:
        fired.append({"id": "bot_kill_switch_zone",
                      "action": "bot kill-switch zone",
                      "detail": f"VIX {v:.2f} > VIX3M {v3:.2f} ({last_common:%Y-%m-%d})"})

    # 3. HY OAS > 400bp -> credit stress, recheck sleeve CVaR
    hy_last = float(hy.iloc[-1])
    if hy_last > 4.0:
        fired.append({"id": "credit_stress",
                      "action": "credit stress — recheck sleeve CVaR",
                      "detail": f"HY OAS {hy_last:.2f}% > 4.00%"})

    now = datetime.now(timezone.utc).isoformat()
    for f in fired:
        con.execute("INSERT INTO alerts (ts_utc, kind, message, details) VALUES (?,?,?,?)",
                    (now, "trigger", f["action"], json.dumps(f)))
    con.commit()
    return fired


def format_triggers(fired: list[dict]) -> str:
    if not fired:
        return "Triggers: none fired"
    lines = ["Triggers FIRED:", ""]
    for f in fired:
        lines.append(f"- **{f['action']}** — {f['detail']}")
    return "\n".join(lines)
