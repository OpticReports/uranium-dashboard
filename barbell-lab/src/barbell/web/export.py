"""Read-only research export for the Tier-0 lab box (mac-mini-lab).

The lab Mac mini trains models on our research data. It is a KEYLESS BRAIN in
exactly the sense btc-paper-engine is: it holds no exchange credential, no
EXEC_TOKEN and no market-data API key, and it can reach nothing but this
endpoint. It PULLS; nothing here ever pushes to it or calls into it.

Auth is LAB_READ_TOKEN via the X-Lab-Token header — a third credential,
weaker than both EXEC_TOKEN (can move a book) and READ_TOKEN (can read live
book state). It can read research tables and nothing else. An unset
LAB_READ_TOKEN keeps every route here a 404, so nothing is exposed until
Casey deliberately sets the token — the same default-closed shape the
executor's /blend/feed uses.

What may leave this service is an EXPLICIT ALLOW-LIST, never a prefix or
pattern match. A table added to the schema later is NOT exportable until
someone adds it here on purpose, which is the whole security property:
chat_conversations / chat_messages / chat_memory carry conversation content
and must never appear in this dict. test_export.py enforces that at merge.
"""
from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from .. import db

router = APIRouter(prefix="/api/export")

# name -> (columns exported, time column for incremental pulls or None).
# Adding an entry here is a deliberate decision to let that data leave the
# service. Anything not listed is a 404 even with a valid token.
EXPORTABLE: dict[str, tuple[tuple[str, ...], str | None]] = {
    "prices": (("ticker", "date", "close_adj", "close_raw", "volume", "source"), "date"),
    "fred": (("series_id", "date", "value"), "date"),
    "bot_pnl": (("date", "realized", "unrealized"), "date"),
    "trials": (("trial_id", "ts_utc", "config_hash", "module", "description",
                "sharpe", "n_obs", "metrics"), "ts_utc"),
    "regime_log": (("date", "labor_z", "inflation_z", "credit_z", "dollar_z",
                    "quadrant", "details"), "date"),
    "portfolio_metrics": (("version_id", "computed_at", "metrics"), "computed_at"),
    "validation_log": (("id", "ts_utc", "check_name", "ticker", "passed", "detail"),
                       "ts_utc"),
}

# Tables that must NEVER be exportable regardless of future edits. Listed
# explicitly so the gate test fails loudly rather than relying on someone
# remembering why chat_* is absent from EXPORTABLE.
NEVER_EXPORTABLE = ("chat_conversations", "chat_messages", "chat_memory")

MAX_LIMIT = 2_000_000


def _authorize(supplied: str | None) -> None:
    """Default-closed: no token configured means these routes do not exist."""
    token = os.environ.get("LAB_READ_TOKEN", "")
    if not token:
        raise HTTPException(status_code=404, detail="not found")
    # compare_digest: constant-time, so a wrong token leaks no prefix info.
    if not secrets.compare_digest((supplied or "").encode("utf-8"),
                                  token.encode("utf-8")):
        raise HTTPException(status_code=401, detail="bad lab token")


@router.get("/manifest")
def manifest(x_lab_token: str | None = Header(default=None)) -> dict:
    """What the lab box can pull, and how much of it. Cheap enough to poll."""
    _authorize(x_lab_token)
    con = db.connect()
    try:
        datasets = {}
        for name, (cols, tcol) in EXPORTABLE.items():
            # Table names come from OUR dict keys, never from the request, so
            # the interpolation below cannot be influenced by a caller.
            rows = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            latest = None
            if tcol and rows:
                latest = con.execute(f"SELECT MAX({tcol}) FROM {name}").fetchone()[0]
            datasets[name] = {"rows": rows, "columns": list(cols),
                              "time_column": tcol, "latest": latest}
    finally:
        con.close()
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "datasets": datasets}


def _stream(name: str, cols: tuple[str, ...], tcol: str | None,
            since: str | None, limit: int) -> Iterator[str]:
    """NDJSON, one row per line, streamed so a big table never lands in RAM.

    Owns its own connection: a StreamingResponse body runs AFTER the handler
    returns, so a connection closed in the handler's finally would already be
    gone by the time the first row is pulled.
    """
    con = db.connect()
    try:
        sql = f"SELECT {', '.join(cols)} FROM {name}"
        params: list = []
        if since and tcol:
            sql += f" WHERE {tcol} >= ?"
            params.append(since)
        if tcol:
            sql += f" ORDER BY {tcol}"
        sql += " LIMIT ?"
        params.append(limit)
        for row in con.execute(sql, params):
            yield json.dumps(dict(zip(cols, row)), separators=(",", ":")) + "\n"
    finally:
        con.close()


@router.get("/table/{name}")
def table(name: str,
          x_lab_token: str | None = Header(default=None),
          since: str | None = None,
          limit: int = MAX_LIMIT) -> StreamingResponse:
    """One allow-listed table as NDJSON. `since` filters on the time column."""
    _authorize(x_lab_token)
    entry = EXPORTABLE.get(name)
    if entry is None:
        # Same 404 whether the table exists and is withheld or doesn't exist:
        # the allow-list is not a directory to enumerate.
        raise HTTPException(status_code=404, detail="not exportable")
    cols, tcol = entry
    limit = max(1, min(limit, MAX_LIMIT))
    return StreamingResponse(_stream(name, cols, tcol, since, limit),
                             media_type="application/x-ndjson")
