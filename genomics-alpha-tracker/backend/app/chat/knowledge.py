"""Curated knowledge base for the Analyst Chat.

Markdown notes under backend/knowledge/ hold CITED biotech base rates (clinical
success probabilities, FDA/catalyst statistics, market-structure patterns) that
the chat agent reads on demand so its probability/EV sections are calibrated to
real data instead of unmoored priors — and auditable (every number in the notes
carries a source).

Design: files are the source of truth (git-versioned, human-editable, refreshed
by the periodic research pass). This module indexes them into topics + sections
and serves small, relevant slices to the agent — never the whole corpus, to keep
tokens bounded. No LLM here; pure parsing + keyword scoring.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"

# Topic keywords steer a query to the right file(s) even when wording differs.
TOPIC_HINTS = {
    "clinical_base_rates": [
        "phase", "trial", "readout", "success", "probability", "approval odds",
        "loa", "likelihood of approval", "oncology", "rare disease", "gene therapy",
        "crispr", "gene editing", "rnai", "antisense", "mrna", "cell therapy",
        "biomarker", "pivotal", "endpoint", "efficacy",
    ],
    "fda_catalyst_stats": [
        "fda", "pdufa", "adcom", "advisory committee", "crl", "complete response",
        "bla", "nda", "breakthrough", "accelerated approval", "priority review",
        "catalyst", "implied move", "sell the news", "financing", "offering",
        "dilution", "atm", "regulatory",
    ],
    "market_structure": [
        "short interest", "squeeze", "days to cover", "insider", "insider buying",
        "revision", "drift", "liquidity", "float", "slippage", "adv", "market impact",
        "beta", "relative strength", "xbi", "regime", "atr", "stop", "volatility",
        "momentum", "positioning",
    ],
}


@dataclass
class Section:
    file: str
    title: str      # the note's document title
    heading: str    # the section heading
    body: str


def _split_sections(text: str, filename: str) -> tuple[str, list[Section]]:
    lines = text.splitlines()
    doc_title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), filename)
    sections: list[Section] = []
    cur_head, cur_buf = None, []

    def flush():
        if cur_head is not None and cur_buf:
            sections.append(Section(filename, doc_title, cur_head, "\n".join(cur_buf).strip()))

    for line in lines:
        m = re.match(r"^(#{2,3})\s+(.*)", line)
        if m:
            flush()
            cur_head, cur_buf = m.group(2).strip(), []
        elif cur_head is not None:
            cur_buf.append(line)
    flush()
    return doc_title, sections


@lru_cache(maxsize=1)
def _index() -> tuple[list[Section], dict[str, str]]:
    """(all sections, {file_stem: doc_title}). Cached; cleared by reload()."""
    sections: list[Section] = []
    titles: dict[str, str] = {}
    if not KNOWLEDGE_DIR.is_dir():
        return sections, titles
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        if path.name.upper() in ("README.MD", "INDEX.MD"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        doc_title, secs = _split_sections(text, path.stem)
        titles[path.stem] = doc_title
        sections.extend(secs)
    return sections, titles


def reload() -> None:
    _index.cache_clear()


def available() -> bool:
    secs, _ = _index()
    return bool(secs)


def topics() -> list[dict]:
    _, titles = _index()
    return [{"file": stem, "title": title} for stem, title in titles.items()]


def _score(query: str, section: Section) -> float:
    q = query.lower()
    terms = [t for t in re.findall(r"[a-z0-9\-]+", q) if len(t) > 2]
    hay = f"{section.heading}\n{section.body}".lower()
    score = 0.0
    for t in terms:
        score += hay.count(t)
    # Topic-hint boost: if the query trips a file's hints, favor that file.
    for stem, hints in TOPIC_HINTS.items():
        if section.file == stem and any(h in q for h in hints):
            score += 3.0
    # Heading matches are worth more than body matches.
    score += 2.0 * sum(1 for t in terms if t in section.heading.lower())
    return score


def search(query: str, max_sections: int = 4, max_chars: int = 6000) -> dict:
    """Return the most relevant knowledge sections for a query.

    Bounded output (few sections, capped chars) so a chat turn's token cost
    stays predictable regardless of corpus size.
    """
    sections, _ = _index()
    if not sections:
        return {"available": False,
                "note": "No curated knowledge base is installed.", "sections": []}
    ranked = sorted(sections, key=lambda s: _score(query, s), reverse=True)
    picked, out, used = [], [], 0
    for s in ranked:
        if _score(query, s) <= 0:
            break
        body = s.body if len(s.body) <= max_chars - used else s.body[: max_chars - used] + " …"
        out.append({"source_file": s.file, "document": s.title,
                    "section": s.heading, "content": body})
        used += len(body)
        picked.append(s)
        if len(out) >= max_sections or used >= max_chars:
            break
    return {
        "available": True,
        "note": ("Curated, source-cited base rates. Use to CALIBRATE probability/EV — "
                 "they are priors to adjust for the specific name, not verdicts. Cite the "
                 "document when you lean on a figure."),
        "sections": out,
    }
