"""Service + adapter-logic gates: offline mode, auth, kill; pure helpers."""
from fastapi.testclient import TestClient

from app.config import settings
from app.ib_adapter import DryAdapter, pick_expiry, pick_strike, size_combos
from app.service import app


def test_gate_adapter_helpers():
    assert pick_expiry(["20270115", "20270219", "20270319"], "2027-02") == "20270219"
    assert pick_expiry(["20261218"], "2027-02") == "20261218"   # best available
    assert pick_expiry([], "2027-02") is None
    assert pick_strike([2.5, 2.75, 3.0, 3.25], 2.9) == 3.0
    # $10k at $0.55 net debit on NG's 10,000 multiplier -> 1 combo ($5.5k each)
    assert size_combos(10_000, 0.55, 10_000) == 1
    assert size_combos(10_000, 0.04, 1_120) == 223          # sugar-scale
    assert size_combos(10_000, 0.0, 100) == 0               # degenerate quote


def test_gate_dry_adapter_lifecycle():
    a = DryAdapter()
    r = a.open_spread({"underlying": "NG", "kind": "call_spread"}, 9_500)
    assert r["premium"] == 9_500
    assert a.mark(r["order_ref"]) == 9_500
    out = a.close_spread(r["order_ref"])
    assert out["value"] == 9_500
    assert a.mark(r["order_ref"]) is None
    assert [e["action"] for e in a.log] == ["open_spread", "close_spread"]


def test_gate_offline_service_and_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200            # public
        assert c.get("/status").status_code == 401
        assert c.post("/kill").status_code == 401
        r = c.get("/status", params={"token": "sekrit"})
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is True
        assert set(body["ladder"]) == {"NG", "SB", "SLV"}
        # kill halts the ladder even with nothing open
        r = c.post("/kill", params={"token": "sekrit"})
        assert r.json()["halted"] == "KILL"
        r = c.post("/resume", params={"token": "sekrit"})
        assert r.json()["ok"] is True


# --- corrective round: B3 (the open control surface) and the deploy config ---


def test_gate_b3_mutations_refuse_GET(tmp_path, monkeypatch):
    """B3 (live-blocker): `/kill` answered GET, so ANY GET of the URL
    flattened the book — a crawler, a Telegram/Slack link unfurl, a mail
    client prefetch, a browser address-bar prediction. The operator's own
    habit is what made it reachable: the token travels as a QUERY parameter,
    so the tokenised URL is exactly the string that gets pasted into a chat
    that unfurls links. `/resume` is a mutation too and goes the same way.

    Reads stay GET; nothing else about either handler changes."""
    monkeypatch.setattr(settings, "state_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    monkeypatch.setattr(settings, "tws_userid", "")
    with TestClient(app) as c:
        assert c.get("/kill", params={"token": "sekrit"}).status_code == 405
        assert c.get("/resume", params={"token": "sekrit"}).status_code == 405
        # ...and the POST form still works, unchanged
        assert c.post("/kill", params={"token": "sekrit"}
                      ).json()["halted"] == "KILL"
        assert c.post("/resume", params={"token": "sekrit"}).json()["ok"]
        # the reads are untouched
        assert c.get("/health").status_code == 200
        assert c.get("/status", params={"token": "sekrit"}).status_code == 200


def test_gate_b3_an_unset_exec_token_fails_closed_off_offline(monkeypatch):
    """B3: `if settings.exec_token and ...` SHORT-CIRCUITED on a falsy
    token, so an unset EXEC_TOKEN left /status, /kill and /resume
    UNAUTHENTICATED. render.yaml marks EXEC_TOKEN `sync: false` — it is
    dashboard-owned, so an unset or accidentally cleared one is a routine
    misconfiguration, not an exotic one.

    Fail closed in any mode that can reach a broker; OFFLINE (no
    credentials, no gateway, no orders) stays open by explicit scope."""
    import pytest
    from fastapi import HTTPException

    from app import service

    monkeypatch.setattr(settings, "exec_token", "")
    monkeypatch.setattr(settings, "tws_userid", "u")
    monkeypatch.setattr(settings, "tws_password", "p")
    with pytest.raises(HTTPException) as exc:
        service._auth(None, None)
    assert exc.value.status_code == 503
    assert "EXEC_TOKEN" in exc.value.detail
    # a supplied token cannot talk its way past an unset one either
    with pytest.raises(HTTPException):
        service._auth("anything", None)

    # OFFLINE: no credentials -> DryAdapter, nothing to protect
    monkeypatch.setattr(settings, "tws_userid", "")
    monkeypatch.setattr(settings, "tws_password", "")
    service._auth(None, None)                      # no raise

    # and with a token set, the compare is exact (and constant-time)
    monkeypatch.setattr(settings, "exec_token", "sekrit")
    service._auth("sekrit", None)
    service._auth(None, "sekrit")
    with pytest.raises(HTTPException) as exc:
        service._auth("sekri", None)
    assert exc.value.status_code == 401


# --- deploy configuration (B2, B10, B8's pin) --------------------------------

def _ibkr_executor_env_block() -> str:
    """The `ibkr-executor` service block of the repo's render.yaml, as text.
    Parsed by hand on purpose: the suite must not grow a YAML dependency to
    assert a deploy fact."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(os.path.dirname(here), "render.yaml")
    with open(path) as fh:
        text = fh.read()
    start = text.index("name: ibkr-executor")
    nxt = text.find("\n  - type:", start)
    return text[start:] if nxt == -1 else text[start:nxt]


def test_gate_b2_blend_state_path_is_declared_onto_the_mounted_disk():
    """B2 (live-blocker): BLEND_STATE_PATH was UNDECLARED, so the live blend
    book fell back to app/config.py's `./data/blend_state.json` — the
    container's EPHEMERAL layer, NOT the ibkr-data disk mounted at /app/data
    that STATE_PATH has always used. With autoDeploy on, every deploy
    destroyed the book and re-seeded a FRESH one on top of shares the
    account still held. It is also what makes B1's restart-boundary
    double-sell routine rather than exotic: a deploy IS a restart."""
    block = _ibkr_executor_env_block()
    assert "mountPath: /app/data" in block
    assert "key: BLEND_STATE_PATH" in block
    assert "value: /app/data/blend_state.json" in block


def test_gate_b10_ib_client_id_is_declared_and_not_the_shared_default():
    """B10 (live-blocker): IB_CLIENT_ID was undeclared and defaults to 17.
    A TWS/API session already holding that id costs 20 connect attempts x
    15s and then KILLS the loop thread."""
    from app.config import Settings

    block = _ibkr_executor_env_block()
    assert "key: IB_CLIENT_ID" in block
    declared = [ln.split("value:")[1].strip().strip('"')
                for ln in block.splitlines()
                if "value:" in ln and "IB_CLIENT_ID" in block]
    assert any(v.isdigit() for v in declared)
    # and it is deliberately not the code default a human TWS may hold
    assert 'value: "1701"' in block
    assert Settings.model_fields["ib_client_id"].default == 17


def test_gate_b8_ib_async_is_pinned_to_a_major():
    """B8: `ib_async>=1.0` floated across a MAJOR. `Ticker.marketPrice()`
    lost its previous-close fallback between majors, so an unpinned rebuild
    could silently change what a MARK IS on a live-money book."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "requirements.txt")) as fh:
        req = [ln.strip() for ln in fh if ln.strip()
               and not ln.strip().startswith("#")]
    (pin,) = [ln for ln in req if ln.startswith("ib_async")]
    assert "<3" in pin and ">=2" in pin, pin
