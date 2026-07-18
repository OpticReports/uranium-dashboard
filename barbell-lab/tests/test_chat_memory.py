"""Chat memory + context-window management (pure SQLite, no network)."""
from __future__ import annotations

import pytest

from barbell import db
from barbell.chat import memory


@pytest.fixture()
def con(tmp_path):
    return db.connect(tmp_path / "mem.db")


class TestConversations:
    def test_create_append_autotitle(self, con):
        cid = memory.create_conversation(con)
        memory.append_message(con, cid, "user", "trim AVUV, what breaks?")
        memory.append_message(con, cid, "assistant", "Running the battery…")
        convo = memory.get_conversation(con, cid)
        assert convo["title"] == "trim AVUV, what breaks?"
        msgs = memory.get_messages(con, cid)
        assert [m["role"] for m in msgs] == ["user", "assistant"]

    def test_tool_trace_roundtrip(self, con):
        cid = memory.create_conversation(con)
        trace = [{"tool": "get_portfolio", "input": {}, "error": False}]
        memory.append_message(con, cid, "assistant", "done", tool_trace=trace)
        assert memory.get_messages(con, cid)[0]["tool_trace"] == trace

    def test_list_ordering_and_counts(self, con):
        a = memory.create_conversation(con)
        b = memory.create_conversation(con)
        memory.append_message(con, a, "user", "first convo")
        memory.append_message(con, b, "user", "second convo")
        memory.append_message(con, a, "user", "back to first")  # bumps updated_at
        lst = memory.list_conversations(con)
        assert lst[0]["id"] == a and lst[0]["n_messages"] == 2
        assert lst[1]["id"] == b

    def test_bad_role_and_missing_convo(self, con):
        cid = memory.create_conversation(con)
        with pytest.raises(ValueError, match="bad role"):
            memory.append_message(con, cid, "system", "nope")
        with pytest.raises(ValueError, match="no conversation"):
            memory.get_conversation(con, 999)


class TestContextWindow:
    def test_under_budget_no_fold(self, con):
        cid = memory.create_conversation(con)
        memory.append_message(con, cid, "user", "hello")
        memory.append_message(con, cid, "assistant", "hi")
        summary, tail = memory.conversation_window(
            con, cid, summarize_fn=lambda p: pytest.fail("must not summarize"))
        assert summary == "" and len(tail) == 2

    def test_overflow_folds_into_summary(self, con):
        cid = memory.create_conversation(con)
        for i in range(10):
            memory.append_message(con, cid, "user", f"q{i} " + "x" * 500)
            memory.append_message(con, cid, "assistant", f"a{i} " + "y" * 500)
        calls: list[str] = []

        def fake_summarize(prompt):
            calls.append(prompt)
            return "SUMMARY: early turns folded"

        summary, tail = memory.conversation_window(con, cid, fake_summarize,
                                                   tail_char_budget=3000)
        assert summary == "SUMMARY: early turns folded"
        assert len(calls) == 1 and "q0" in calls[0]
        assert len(tail) >= memory.MIN_TAIL_MESSAGES
        assert sum(len(m["content"]) for m in tail) <= 3000 + 600
        # tail is the most recent messages
        assert tail[-1]["content"].startswith("a9")
        # fold is persisted: a second call with the same budget re-folds nothing new
        summary2, tail2 = memory.conversation_window(
            con, cid, summarize_fn=lambda p: pytest.fail("re-fold"), tail_char_budget=99999)
        assert summary2 == summary and len(tail2) == len(
            memory.get_messages(con, cid, memory.get_conversation(con, cid)["summary_upto_id"]))

    def test_summarizer_failure_extractive_fallback(self, con):
        cid = memory.create_conversation(con)
        for i in range(8):
            memory.append_message(con, cid, "user", f"question {i} " + "z" * 400)
            memory.append_message(con, cid, "assistant", f"answer {i} " + "w" * 400)

        def broken(prompt):
            raise RuntimeError("LLM down")

        summary, tail = memory.conversation_window(con, cid, broken,
                                                   tail_char_budget=2000)
        assert "extractive digest" in summary and "question 0" in summary
        assert len(tail) >= memory.MIN_TAIL_MESSAGES


class TestNotesAndSearch:
    def test_notes_roundtrip(self, con):
        memory.add_note(con, "  investor prefers   monthly rebalance  ")
        notes = memory.list_notes(con)
        assert notes[0]["content"] == "investor prefers monthly rebalance"
        with pytest.raises(ValueError, match="empty"):
            memory.add_note(con, "   ")

    def test_search_across_layers(self, con):
        cid = memory.create_conversation(con)
        memory.append_message(con, cid, "user", "what did KMLM do in 2022?")
        con.execute("UPDATE chat_conversations SET summary='discussed AVUV trim' "
                    "WHERE id=?", (cid,))
        con.commit()
        memory.add_note(con, "AVUV capped at 25% by mandate")
        kinds = {h["kind"] for h in memory.search_history(con, "avuv")}
        assert kinds == {"summary", "note"}
        hits = memory.search_history(con, "kmlm")
        assert hits and hits[0]["kind"] == "message"
        # exclusion of the current conversation
        assert memory.search_history(con, "kmlm", exclude_conversation=cid) == []

    def test_context_block_composition(self, con):
        old = memory.create_conversation(con)
        memory.append_message(con, old, "user", "compare TAIL vs CAOS carry drag")
        cur = memory.create_conversation(con)
        memory.append_message(con, cur, "user", "new question")
        memory.add_note(con, "Act 60: rebalancing is tax-free")
        block = memory.context_block(con, cur)
        assert "PERSISTENT MEMORY" in block
        assert "Act 60" in block
        assert "TAIL vs CAOS" in block          # past-conversation gist
        assert "memory is context, not evidence" in block

    def test_context_block_empty_store(self, con):
        cid = memory.create_conversation(con)
        assert memory.context_block(con, cid) == ""


class TestAgentMemoryTools:
    def test_remember_and_search_handlers(self, con, monkeypatch):
        import json
        from barbell.chat import agent
        cid = memory.create_conversation(con)
        other = memory.create_conversation(con)
        memory.append_message(con, other, "user", "sweep bot fraction to 30%")
        token = agent._CURRENT_CID.set(cid)
        try:
            out = json.loads(agent._tool_remember_note(con, content="note A"))
            assert out["saved"] and memory.list_notes(con)[0]["content"] == "note A"
            assert memory.list_notes(con)[0]["source_conversation_id"] == cid
            hits = json.loads(agent._tool_search_past_conversations(
                con, query="bot fraction"))["hits"]
            assert hits and hits[0]["conversation_id"] == other
        finally:
            agent._CURRENT_CID.reset(token)

    def test_tools_registered(self):
        from barbell.chat.agent import TOOLS, _HANDLERS
        names = {t["name"] for t in TOOLS}
        assert {"remember_note", "search_past_conversations"} <= names
        assert set(_HANDLERS) == names
