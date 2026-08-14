"""Persistent chat memory + context-window management.

Three layers, all server-side in SQLite (survive reloads, redeploys and
different clients — web UI and CLI share the same store):

1. **Transcripts** — every conversation is persisted verbatim
   (chat_conversations / chat_messages). Nothing the analyst said or was told
   is ever silently lost.
2. **Rolling summaries** — when a conversation's verbatim tail outgrows the
   context budget, the oldest overflow turns are folded into a per-conversation
   summary by the LLM (extractive fallback if the LLM is unavailable). The
   summary + recent tail is what the model actually sees, so long sessions
   keep working instead of blowing the window.
3. **Durable notes** (chat_memory) — cross-conversation facts worth keeping
   ("investor prefers X", "v1.2 filed to attack the CVaR breach"). The agent
   writes them via its remember_note tool and every new conversation starts
   with them in context.

Grounding rule carried over: summaries are context, not evidence — the agent's
numeric claims must still come from tool calls in the current conversation.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Verbatim-tail budget per conversation (chars, ~4 chars/token). Beyond this,
# oldest turns are folded into the rolling summary.
TAIL_CHAR_BUDGET = 48_000
# Always keep at least this many recent messages verbatim, budget or not —
# the model needs the immediate exchange un-summarized to answer coherently.
MIN_TAIL_MESSAGES = 6
# Caps for the cross-conversation context block.
MAX_NOTES = 25
MAX_PAST_CONVERSATIONS = 5
PAST_BLOCK_CHAR_BUDGET = 6_000
SUMMARY_CHAR_CAP = 8_000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------- conversations
def create_conversation(con: sqlite3.Connection, title: str | None = None) -> int:
    ts = _now()
    cur = con.execute(
        "INSERT INTO chat_conversations (title, created_at, updated_at) VALUES (?,?,?)",
        (title, ts, ts))
    con.commit()
    return int(cur.lastrowid)


def get_conversation(con: sqlite3.Connection, cid: int) -> dict:
    row = con.execute(
        "SELECT id, title, summary, summary_upto_id, created_at, updated_at "
        "FROM chat_conversations WHERE id=?", (int(cid),)).fetchone()
    if row is None:
        raise ValueError(f"no conversation {cid}")
    return {"id": row[0], "title": row[1], "summary": row[2],
            "summary_upto_id": row[3], "created_at": row[4], "updated_at": row[5]}


def list_conversations(con: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = con.execute(
        "SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) "
        "FROM chat_conversations c LEFT JOIN chat_messages m ON m.conversation_id=c.id "
        "GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?", (int(limit),)).fetchall()
    return [{"id": r[0], "title": r[1] or "(untitled)", "created_at": r[2],
             "updated_at": r[3], "n_messages": r[4]} for r in rows]


def append_message(con: sqlite3.Connection, cid: int, role: str, content: str,
                   tool_trace: list | None = None) -> int:
    if role not in ("user", "assistant"):
        raise ValueError(f"bad role {role}")
    ts = _now()
    cur = con.execute(
        "INSERT INTO chat_messages (conversation_id, role, content, tool_trace, created_at) "
        "VALUES (?,?,?,?,?)",
        (int(cid), role, content, json.dumps(tool_trace) if tool_trace else None, ts))
    con.execute("UPDATE chat_conversations SET updated_at=? WHERE id=?", (ts, int(cid)))
    # auto-title from the first user message
    if role == "user":
        row = con.execute("SELECT title FROM chat_conversations WHERE id=?",
                          (int(cid),)).fetchone()
        if row and not row[0]:
            title = " ".join(content.split())[:80]
            con.execute("UPDATE chat_conversations SET title=? WHERE id=?",
                        (title, int(cid)))
    con.commit()
    return int(cur.lastrowid)


def get_messages(con: sqlite3.Connection, cid: int,
                 after_id: int = 0) -> list[dict]:
    rows = con.execute(
        "SELECT id, role, content, tool_trace, created_at FROM chat_messages "
        "WHERE conversation_id=? AND id>? ORDER BY id", (int(cid), int(after_id))).fetchall()
    return [{"id": r[0], "role": r[1], "content": r[2],
             "tool_trace": json.loads(r[3]) if r[3] else None, "created_at": r[4]}
            for r in rows]


# ------------------------------------------------------------- durable notes
def add_note(con: sqlite3.Connection, content: str,
             source_conversation_id: int | None = None) -> int:
    content = " ".join(str(content).split())
    if not content:
        raise ValueError("empty note")
    cur = con.execute(
        "INSERT INTO chat_memory (content, source_conversation_id, created_at) "
        "VALUES (?,?,?)", (content, source_conversation_id, _now()))
    con.commit()
    return int(cur.lastrowid)


def list_notes(con: sqlite3.Connection, limit: int = MAX_NOTES) -> list[dict]:
    rows = con.execute(
        "SELECT id, content, source_conversation_id, created_at FROM chat_memory "
        "ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [{"id": r[0], "content": r[1], "source_conversation_id": r[2],
             "created_at": r[3]} for r in reversed(rows)]


def search_history(con: sqlite3.Connection, query: str, limit: int = 12,
                   exclude_conversation: int | None = None) -> list[dict]:
    """Case-insensitive substring search across past messages, conversation
    summaries and durable notes. Returns labeled snippets."""
    q = f"%{str(query).strip()}%"
    out: list[dict] = []
    ex = int(exclude_conversation) if exclude_conversation else -1
    for r in con.execute(
            "SELECT m.conversation_id, c.title, m.role, m.content, m.created_at "
            "FROM chat_messages m JOIN chat_conversations c ON c.id=m.conversation_id "
            "WHERE m.content LIKE ? COLLATE NOCASE AND m.conversation_id != ? "
            "ORDER BY m.id DESC LIMIT ?", (q, ex, int(limit))).fetchall():
        snippet = r[3] if len(r[3]) <= 400 else r[3][:400] + " …"
        out.append({"kind": "message", "conversation_id": r[0],
                    "conversation_title": r[1], "role": r[2], "snippet": snippet,
                    "at": r[4]})
    for r in con.execute(
            "SELECT id, title, summary, updated_at FROM chat_conversations "
            "WHERE summary LIKE ? COLLATE NOCASE AND id != ? "
            "ORDER BY updated_at DESC LIMIT ?", (q, ex, int(limit))).fetchall():
        out.append({"kind": "summary", "conversation_id": r[0],
                    "conversation_title": r[1],
                    "snippet": r[2][:400] + (" …" if len(r[2]) > 400 else ""),
                    "at": r[3]})
    for r in con.execute(
            "SELECT id, content, created_at FROM chat_memory "
            "WHERE content LIKE ? COLLATE NOCASE ORDER BY id DESC LIMIT ?",
            (q, int(limit))).fetchall():
        out.append({"kind": "note", "note_id": r[0], "snippet": r[1], "at": r[2]})
    return out[:int(limit)]


# ----------------------------------------------------- context-window manager
def _fold_into_summary(con: sqlite3.Connection, convo: dict,
                       overflow: list[dict], summarize_fn) -> str:
    """Fold `overflow` messages into the conversation's rolling summary.
    summarize_fn(text) -> str runs the LLM; on failure we fall back to an
    extractive digest so the fold NEVER loses the fact that turns existed."""
    transcript = "\n".join(f"[{m['role']}] {m['content']}" for m in overflow)
    prompt = (
        "Update this running summary of an earlier portion of a quant-research "
        "conversation. Preserve: decisions made, numeric results with their "
        "source (which tool/report), candidate portfolios discussed, open "
        "questions, and the investor's stated preferences. Be dense; drop "
        "pleasantries. Return only the updated summary.\n\n"
        f"CURRENT SUMMARY:\n{convo['summary'] or '(none)'}\n\n"
        f"NEW TURNS TO FOLD IN:\n{transcript}"
    )
    try:
        new_summary = str(summarize_fn(prompt)).strip()
        if not new_summary:
            raise ValueError("empty summary")
    except Exception as exc:  # noqa: BLE001 — degrade, never drop turns silently
        logger.warning("LLM summary fold failed (%s); extractive fallback", exc)
        digest = "; ".join(" ".join(m["content"].split())[:160] for m in overflow)
        new_summary = (convo["summary"] + "\n" if convo["summary"] else "") \
            + f"(unsummarized turns, extractive digest): {digest}"
    new_summary = new_summary[-SUMMARY_CHAR_CAP:]
    last_id = overflow[-1]["id"]
    con.execute("UPDATE chat_conversations SET summary=?, summary_upto_id=? WHERE id=?",
                (new_summary, last_id, convo["id"]))
    con.commit()
    return new_summary


def conversation_window(con: sqlite3.Connection, cid: int, summarize_fn,
                        tail_char_budget: int = TAIL_CHAR_BUDGET
                        ) -> tuple[str, list[dict]]:
    """The context window for one conversation: (rolling_summary, tail).
    Folds overflow into the summary first if the verbatim tail exceeds the
    budget. `tail` is [{"role","content"}] ready for the LLM."""
    convo = get_conversation(con, cid)
    msgs = get_messages(con, cid, after_id=convo["summary_upto_id"])
    total = sum(len(m["content"]) for m in msgs)
    if total > tail_char_budget and len(msgs) > MIN_TAIL_MESSAGES:
        # keep at least MIN_TAIL_MESSAGES; fold the oldest of the rest until
        # the tail fits (never fold a user msg away from its assistant reply
        # mid-pair: fold whole leading chunk)
        keep = len(msgs)
        while keep > MIN_TAIL_MESSAGES and \
                sum(len(m["content"]) for m in msgs[len(msgs) - keep:]) > tail_char_budget:
            keep -= 2 if keep - 2 >= MIN_TAIL_MESSAGES else 1
        overflow = msgs[: len(msgs) - keep]
        if overflow:
            summary = _fold_into_summary(con, convo, overflow, summarize_fn)
            convo = dict(convo, summary=summary)
            msgs = msgs[len(msgs) - keep:]
    tail = [{"role": m["role"], "content": m["content"]} for m in msgs]
    return convo["summary"], tail


def context_block(con: sqlite3.Connection, cid: int) -> str:
    """The persistent-memory block appended to the system prompt: durable
    notes + digests of other recent conversations + this conversation's
    rolling summary (if any)."""
    parts: list[str] = []
    notes = list_notes(con)
    if notes:
        lines = "\n".join(f"- ({n['created_at'][:10]}) {n['content']}" for n in notes)
        parts.append(f"DURABLE MEMORY NOTES (saved across conversations):\n{lines}")
    others, used = [], 0
    for c in list_conversations(con, limit=MAX_PAST_CONVERSATIONS + 1):
        if c["id"] == int(cid):
            continue
        full = get_conversation(con, c["id"])
        gist = full["summary"] or _first_exchange_gist(con, c["id"])
        if not gist:
            continue
        entry = f"- [{c['updated_at'][:10]}] \"{c['title']}\" (id {c['id']}): {gist}"
        if used + len(entry) > PAST_BLOCK_CHAR_BUDGET:
            break
        others.append(entry)
        used += len(entry)
        if len(others) >= MAX_PAST_CONVERSATIONS:
            break
    if others:
        parts.append("RECENT PAST CONVERSATIONS (use search_past_conversations "
                     "for details):\n" + "\n".join(others))
    convo = get_conversation(con, cid)
    if convo["summary"]:
        parts.append("EARLIER IN THIS CONVERSATION (rolling summary of turns "
                     f"no longer shown verbatim):\n{convo['summary']}")
    if not parts:
        return ""
    return (
        "\n\n--- PERSISTENT MEMORY ---\n"
        "Context recalled from the platform's chat memory store. Use it for "
        "continuity, but numeric claims must still come from tool calls in "
        "THIS conversation — memory is context, not evidence.\n\n"
        + "\n\n".join(parts)
    )


def _first_exchange_gist(con: sqlite3.Connection, cid: int) -> str:
    row = con.execute(
        "SELECT content FROM chat_messages WHERE conversation_id=? AND role='user' "
        "ORDER BY id LIMIT 1", (int(cid),)).fetchone()
    return " ".join(row[0].split())[:200] if row else ""
