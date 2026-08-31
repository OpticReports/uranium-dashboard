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


# Every endpoint that can CHANGE something. /drill places real orders;
# /coverage/attest writes the record that gates the ramp; /kill and /resume
# move the executor between trading and halted. The read token must open
# none of them, and this list must grow whenever a write endpoint is added.
_WRITE_ENDPOINTS = (("post", "/kill"), ("post", "/resume"),
                    ("post", "/drill"), ("post", "/coverage/attest"),
                    ("get", "/test-alert"))


def test_read_token_opens_status_and_absolutely_nothing_else():
    """THE POINT OF THE READ TOKEN. EXEC_TOKEN is a TRADING credential -
    /drill places real orders - so an assistant that only needs to answer
    "what is the executor holding" must not be handed it. This asserts the
    separation actually holds rather than merely being intended."""
    old, old_r = settings.exec_token, settings.exec_read_token
    settings.exec_token, settings.exec_read_token = "write-sekrit", "read-only"
    try:
        with TestClient(app) as c:
            hdr = {"X-Exec-Token": "read-only"}
            assert c.get("/status", headers=hdr).status_code == 200
            assert c.get("/status", params={"token": "read-only"}).status_code == 200
            for verb, path in _WRITE_ENDPOINTS:
                r = getattr(c, verb)(path, headers=hdr)
                assert r.status_code == 401, (
                    f"the READ token opened {verb.upper()} {path} - it is a "
                    f"write endpoint and must refuse")
                r2 = getattr(c, verb)(path, params={"token": "read-only"})
                assert r2.status_code == 401, (
                    f"the READ token opened {verb.upper()} {path} via query")
    finally:
        settings.exec_token, settings.exec_read_token = old, old_r


def test_write_token_still_reads_so_existing_tooling_is_untouched():
    old, old_r = settings.exec_token, settings.exec_read_token
    settings.exec_token, settings.exec_read_token = "write-sekrit", "read-only"
    try:
        with TestClient(app) as c:
            assert c.get("/status",
                         headers={"X-Exec-Token": "write-sekrit"}).status_code == 200
            assert c.post("/resume",
                          params={"token": "write-sekrit"}).status_code == 200
    finally:
        settings.exec_token, settings.exec_read_token = old, old_r


def test_an_unset_read_token_changes_nothing():
    """Adding a knob must not quietly widen access on a deployment that
    never sets it."""
    old, old_r = settings.exec_token, settings.exec_read_token
    settings.exec_token, settings.exec_read_token = "sekrit", ""
    try:
        with TestClient(app) as c:
            assert c.get("/status").status_code == 401
            assert c.get("/status", params={"token": "sekrit"}).status_code == 200
            assert c.get("/status", params={"token": ""}).status_code == 401
    finally:
        settings.exec_token, settings.exec_read_token = old, old_r


def test_an_empty_read_token_is_not_a_master_key():
    """An empty string must never satisfy a comparison - the classic
    default-open bug, where an unset env var authenticates everyone."""
    old, old_r = settings.exec_token, settings.exec_read_token
    settings.exec_token, settings.exec_read_token = "sekrit", ""
    try:
        with TestClient(app) as c:
            assert c.get("/status", headers={"X-Exec-Token": ""}).status_code == 401
    finally:
        settings.exec_token, settings.exec_read_token = old, old_r


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


def test_pulse_publishes_which_key_is_deployed():
    """A key swap could not be verified from outside: agent_days_left said
    'not an approved agent' but not WHICH key, so 'you pasted the wrong one'
    and 'the new one has not loaded yet' were the same observation. The
    build sha does not change on an env edit and the RED count is a rolling
    window, so neither could break the tie. This can."""
    import app.main as m

    class _V:
        agent_address = "0x243cb2b53aea9d751093f6de7de8028adf19862f"
        address = "0xab533e69e77881d89d0357166851c9653bc551e2"

    class _St:
        halted = None
        events: list = []
        legs: dict = {}
        last_venue_read_ts = 0
        agent_valid_until = None
        auto_drill_off = None

    class _E:
        venue = _V()
        state = _St()
        _auto_drill_wait = None

    old = m.EXEC
    m.EXEC = _E()
    try:
        with TestClient(app) as c:
            body = c.get("/pulse").json()
        assert body["agent_address"] == _V.agent_address
        # BOTH halves, or the diagnosis is ambiguous: "this key is not an
        # approved agent of X" fits a wrong key AND a wrong X equally.
        assert body["account_address"] == _V.address
    finally:
        m.EXEC = old


def test_pulse_agent_address_is_null_on_a_venue_without_one():
    """Coinbase has no agent wallets. Absent must read as null, not crash
    the only unauthenticated monitoring surface."""
    import app.main as m

    class _St:
        halted = None
        events: list = []
        legs: dict = {}
        last_venue_read_ts = 0
        agent_valid_until = None
        auto_drill_off = None

    class _E:
        venue = object()
        state = _St()
        _auto_drill_wait = None

    old = m.EXEC
    m.EXEC = _E()
    try:
        with TestClient(app) as c:
            body = c.get("/pulse").json()
        assert body["agent_address"] is None
        assert body["account_address"] is None
    finally:
        m.EXEC = old
