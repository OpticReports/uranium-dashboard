"""Inline-JS syntax gate: every <script> block on every page must parse.

A single syntax error kills a page's whole script block silently — buttons go
dead with no visible error (exactly how the chat page and the versions page's
promote buttons broke). Node's parser is the arbiter; skipped if node is absent.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")

PAGES = ("index", "chat_page", "versions_page", "lab_page")


def _scripts(html: str) -> list[str]:
    return re.findall(r"<script>(.*?)</script>", html, re.S)


@pytest.mark.parametrize("page", PAGES)
def test_page_scripts_parse(page):
    from barbell.web import app as web
    fn = getattr(web, page, None)
    if fn is None:
        pytest.skip(f"no page {page}")
    try:
        html = fn().body.decode()
    except Exception as exc:  # page needs ingested data this checkout lacks
        pytest.skip(f"{page} needs data to render: {exc}")
    blocks = _scripts(html)
    assert blocks, f"{page} has no inline script (unexpected for these pages)"
    for i, script in enumerate(blocks):
        p = Path(tempfile.mkdtemp()) / f"{page}_{i}.js"
        p.write_text(script)
        r = subprocess.run(["node", "--check", str(p)],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"{page} script {i} syntax error:\n{r.stderr}"
