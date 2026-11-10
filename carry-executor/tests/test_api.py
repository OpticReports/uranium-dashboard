"""API surface: auth on everything that reveals state or changes it."""
import os

os.environ["CARRY_NO_LOOP"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app import main as M  # noqa: E402


def test_health_and_pulse_before_boot():
    with TestClient(M.app) as c:
        assert c.get("/health").json() == {"ok": True}
        assert c.get("/pulse").json()["ready"] is False


def test_status_and_controls_need_tokens(monkeypatch):
    monkeypatch.setattr(M.settings, "exec_token", "w")
    monkeypatch.setattr(M.settings, "exec_read_token", "r")
    with TestClient(M.app) as c:
        assert c.get("/status").status_code == 401
        assert c.get("/status", headers={"X-Exec-Token": "r"}).status_code == 503
        assert c.post("/halt", headers={"X-Exec-Token": "r"}).status_code == 401
        assert c.post("/resume").status_code == 401


def test_no_token_configured_refuses_rather_than_opening(monkeypatch):
    monkeypatch.setattr(M.settings, "exec_token", "")
    monkeypatch.setattr(M.settings, "exec_read_token", "")
    with TestClient(M.app) as c:
        assert c.post("/halt").status_code == 403


def test_config_fails_safe():
    from app.config import Settings
    s = Settings(_env_file=None)
    assert s.dry_run is True and s.carry_notional_usd == 0.0
