"""Control-surface auth: /status, /kill, /resume require EXEC_TOKEN when set;
/health stays public."""
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_control_endpoints_require_token():
    old = settings.exec_token
    settings.exec_token = "sekrit"
    try:
        with TestClient(app) as c:
            assert c.get("/health").status_code == 200          # public
            assert c.get("/status").status_code == 401
            assert c.post("/kill").status_code == 401
            assert c.post("/resume").status_code == 401
            assert c.get("/status", params={"token": "wrong"}).status_code == 401
            assert c.get("/status", params={"token": "sekrit"}).status_code == 200
            assert c.get("/status",
                         headers={"X-Exec-Token": "sekrit"}).status_code == 200
            assert c.post("/resume", params={"token": "sekrit"}).status_code == 200
    finally:
        settings.exec_token = old


def test_open_when_no_token_configured():
    old = settings.exec_token
    settings.exec_token = ""
    try:
        with TestClient(app) as c:
            assert c.get("/status").status_code == 200
    finally:
        settings.exec_token = old
