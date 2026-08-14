"""Tests for the curated knowledge loader (app/chat/knowledge.py)."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app.chat import knowledge


@pytest.fixture
def kb(tmp_path, monkeypatch):
    """Point the loader at a temp knowledge dir with two small notes."""
    (tmp_path / "clinical_base_rates.md").write_text(
        "# Clinical Base Rates\n\n"
        "## Phase transition success rates\n"
        "Phase 3 to approval is approximately 58% industry-wide [BIO 2021]. "
        "Oncology is far lower, near 40% [Lo 2019].\n\n"
        "## Modality notes\n"
        "Gene therapy (AAV) carries durability and immunogenicity risk [Nature 2020].\n",
        encoding="utf-8",
    )
    (tmp_path / "market_structure.md").write_text(
        "# Market Structure\n\n"
        "## Short interest and squeezes\n"
        "High short interest predicts negative average forward returns [Boehmer 2008].\n\n"
        "## Insider buying\n"
        "Cluster buys by multiple insiders carry a modest positive edge [Lakonishok-Lee 2001].\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# ignore me\n", encoding="utf-8")
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path)
    knowledge.reload()
    yield knowledge
    knowledge.reload()


def test_available_and_topics(kb):
    assert kb.available() is True
    stems = {t["file"] for t in kb.topics()}
    assert stems == {"clinical_base_rates", "market_structure"}  # README excluded


def test_search_routes_to_right_file(kb):
    res = kb.search("what is the phase 3 oncology success rate")
    assert res["available"] is True
    top = res["sections"][0]
    assert top["source_file"] == "clinical_base_rates"
    assert "58%" in top["content"] or "40%" in top["content"]


def test_search_short_interest_hits_market_structure(kb):
    res = kb.search("is high short interest bullish or a squeeze setup")
    files = [s["source_file"] for s in res["sections"]]
    assert files[0] == "market_structure"
    assert any("negative" in s["content"] for s in res["sections"])


def test_search_is_bounded(kb):
    res = kb.search("phase approval oncology gene therapy insider short interest", max_sections=2)
    assert len(res["sections"]) <= 2


def test_search_char_cap(kb):
    res = kb.search("insider", max_sections=4, max_chars=40)
    total = sum(len(s["content"]) for s in res["sections"])
    assert total <= 60  # cap + ellipsis slack


def test_empty_when_no_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path / "nope")
    knowledge.reload()
    assert knowledge.available() is False
    res = knowledge.search("anything")
    assert res["available"] is False and res["sections"] == []
    knowledge.reload()


def test_dispatch_wires_read_knowledge(kb, monkeypatch):
    # The chat dispatcher should route read_knowledge to the loader.
    from app.chat import agent

    out = agent._dispatch(None, "read_knowledge", {"query": "insider buying edge"})
    assert out["available"] is True
    assert any(s["source_file"] == "market_structure" for s in out["sections"])
