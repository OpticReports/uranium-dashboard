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


def test_pulse_is_public_and_minimal():
    old = settings.exec_token
    settings.exec_token = "sekrit"
    try:
        with TestClient(app) as c:
            r = c.get("/pulse")                 # no token needed
            assert r.status_code == 200
            body = r.json()
            assert "equity" not in body and "venue_position_btc" not in body
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


def test_build_sha_is_published_and_never_guessed(monkeypatch):
    """A live diagnosis stalled on exactly this: a rail reported a fault, a
    fix was pushed, and nothing outside could say whether the next reading
    came from the old build or the new one - so 'unchanged value' and
    'deploy has not landed' were the same observation."""
    monkeypatch.setenv("RENDER_GIT_COMMIT", "a61ffae1234567890abcdef")
    with TestClient(app) as c:
        assert c.get("/health").json()["build"] == "a61ffae"
        assert c.get("/pulse").json()["build"] == "a61ffae"


def test_build_sha_is_null_when_the_runtime_does_not_set_it(monkeypatch):
    """Null is the honest answer off Render. A guess here would be worse
    than nothing: it would attribute readings to a build we invented."""
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    with TestClient(app) as c:
        assert c.get("/health").json()["build"] is None
