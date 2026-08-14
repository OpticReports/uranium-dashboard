"""Canonical-domain middleware: alias hosts 308 to research.optic.capital
with the path preserved; /health stays exempt for Render checks."""
from fastapi.testclient import TestClient

from app.main import app


def test_alias_host_redirects_with_path():
    c = TestClient(app)
    r = c.get("/exit/", headers={"host": "genomics.optic.capital"},
              follow_redirects=False)
    assert r.status_code == 308
    assert "research.optic.capital/exit/" in r.headers["location"]


def test_canonical_and_health_not_redirected():
    c = TestClient(app)
    r = c.get("/health", headers={"host": "genomics.optic.capital"},
              follow_redirects=False)
    assert r.status_code != 308                        # health check exempt
    r2 = c.get("/health", headers={"host": "research.optic.capital"},
               follow_redirects=False)
    assert r2.status_code != 308
