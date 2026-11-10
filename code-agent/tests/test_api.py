"""API gates. This endpoint can write to a repo that deploys a live trading
book, so the auth story matters as much as the coding story.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGENT_TOKEN", "s3cret-token-value")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc1234567")
    return TestClient(main.app)


def test_gate_task_requires_the_token(client):
    r = client.post("/task", json={"task": "do a thing"})
    assert r.status_code == 401


def test_gate_task_rejects_a_wrong_token(client):
    r = client.post("/task", json={"task": "x"},
                    headers={"X-Agent-Token": "nope"})
    assert r.status_code == 401


def test_gate_reads_require_the_token_too(client):
    """A job record carries the task text and the branch name. Leaving reads
    open would publish what is being worked on to anyone who asks."""
    assert client.get("/task/anything").status_code == 401
    assert client.get("/tasks").status_code == 401


def test_gate_refuses_to_serve_when_no_token_is_configured(monkeypatch):
    """An unset AGENT_TOKEN must not mean 'no auth required'. That is the
    default-open failure that turns a missing env var into an open endpoint
    that can push to a repo deploying real money."""
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    c = TestClient(main.app)
    r = c.post("/task", json={"task": "x"}, headers={"X-Agent-Token": ""})
    assert r.status_code == 503
    r2 = c.post("/task", json={"task": "x"}, headers={"X-Agent-Token": "guess"})
    assert r2.status_code == 503, "an unset token was satisfiable by guessing"


def test_gate_health_is_public_and_leaks_nothing(client, monkeypatch):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["build"] == "abc1234"
    assert body["auth_ready"] is True and body["github_ready"] is True
    blob = str(body)
    assert "s3cret-token-value" not in blob and "ghp_x" not in blob


def test_gate_health_reports_the_edit_format_in_force(client, monkeypatch):
    """Whether the editor can produce an edit AT ALL depends on this, and it
    was invisible from outside - two rounds went on guessing whether an env
    change had taken effect."""
    monkeypatch.delenv("AIDER_EDIT_FORMAT", raising=False)
    assert client.get("/health").json()["edit_format"] == "default"
    monkeypatch.setenv("AIDER_EDIT_FORMAT", "whole")
    assert client.get("/health").json()["edit_format"] == "whole"


def test_gate_task_runs_and_reports_through_the_job_store(client, monkeypatch):
    monkeypatch.setattr(main, "do_task",
                        lambda *a, **k: {"ok": True, "branch": "agent/x-1",
                                         "files": ["a.py"], "tests": "316 passed"})
    r = client.post("/task", json={"task": "add a test"},
                    headers={"X-Agent-Token": "s3cret-token-value"})
    assert r.status_code == 200
    jid = r.json()["id"]
    for _ in range(200):
        j = client.get(f"/task/{jid}",
                       headers={"X-Agent-Token": "s3cret-token-value"}).json()
        if j["state"] != "running":
            break
    assert j["state"] == "done"
    assert j["result"]["branch"] == "agent/x-1"
    assert "compare/agent/x-1" in j["result"]["compare"]


def test_gate_a_refusal_is_reported_as_an_outcome_not_a_crash(client, monkeypatch):
    """A gate saying no is an ANSWER. Reported as a 500 it would look like a
    bug and invite a retry into the same refusal."""
    from app.guard import Refused

    def refusing(*a, **k):
        raise Refused("refusing to modify render.yaml")
    monkeypatch.setattr(main, "do_task", refusing)
    r = client.post("/task", json={"task": "edit render.yaml"},
                    headers={"X-Agent-Token": "s3cret-token-value"})
    jid = r.json()["id"]
    for _ in range(200):
        j = client.get(f"/task/{jid}",
                       headers={"X-Agent-Token": "s3cret-token-value"}).json()
        if j["state"] != "running":
            break
    assert j["state"] == "error"
    # The PREFIX is the point, not the text. The generic handler also
    # catches Refused and produces a message containing the same words, so
    # asserting only on the words passed against code that had lost the
    # refusal branch entirely - which is how this mutant survived.
    assert j["error"].startswith("refused: "), \
        f"a gate refusal is not distinguishable from a bug: {j['error']}"
    assert "refusing to modify render.yaml" in j["error"]


def test_gate_a_second_task_is_refused_while_one_runs(client, monkeypatch):
    """Two aiders in one checkout interleave their edits into a single diff,
    and the gates would then judge a mixture of two tasks."""
    import threading
    hold = threading.Event()
    monkeypatch.setattr(main, "do_task",
                        lambda *a, **k: (hold.wait(5),
                                         {"ok": False, "reason": "x"})[1])
    h = {"X-Agent-Token": "s3cret-token-value"}
    assert client.post("/task", json={"task": "one"}, headers=h).status_code == 200
    assert client.post("/task", json={"task": "two"}, headers=h).status_code == 409
    hold.set()


def test_gate_empty_task_is_rejected(client):
    r = client.post("/task", json={"task": "   "},
                    headers={"X-Agent-Token": "s3cret-token-value"})
    assert r.status_code == 400


def test_gate_the_token_is_compared_in_constant_time():
    """Not observable from behaviour - == and compare_digest agree on every
    input, so no black-box test can tell them apart, and a timing test would
    be flaky. Asserted STRUCTURALLY instead, the same way this repo gates
    SDK-method existence. `==` on a secret leaks its prefix, and this
    endpoint can push to a repo that deploys a live trading book."""
    import ast, inspect
    from app import main
    src = inspect.getsource(main._auth)
    calls = [n.func for n in ast.walk(ast.parse(src.lstrip()))
             if isinstance(n, ast.Call)]
    names = {getattr(c, "attr", getattr(c, "id", "")) for c in calls}
    assert "compare_digest" in names, \
        "the shared secret is compared with ==, which leaks its prefix by timing"


def test_gate_an_unlisted_repo_is_rejected_without_taking_the_lock(client):
    """400, not 409-then-fail: an unknown repo is a caller error, and
    holding the service busy for one would block real work."""
    r = client.post("/task", json={"task": "x", "repo": "attacker/evil"},
                    headers={"X-Agent-Token": "s3cret-token-value"})
    assert r.status_code == 400 and "allowlist" in r.json()["detail"]
    assert not main.BUSY.locked(), "an invalid repo left the service busy"


def test_gate_the_accepted_task_says_which_repo_and_where_it_pushes(client,
                                                                   monkeypatch):
    """The caller is an LLM relaying to a human. It must not have to infer
    which repo it just aimed at, or whether that repo publishes."""
    monkeypatch.setattr(main, "do_task",
                        lambda *a, **k: {"ok": True, "branch": "agent/x-1",
                                         "files": ["a.py"], "tests": "1 passed"})
    r = client.post("/task", json={"task": "add a test"},
                    headers={"X-Agent-Token": "s3cret-token-value"})
    body = r.json()
    assert body["repo"] == "OpticReports/uranium-dashboard"
    assert body["pushes_to"] == "agent/*"


def test_gate_health_lists_the_repos_and_whether_each_token_is_present(client,
                                                                      monkeypatch):
    """A repo configured without its token is reachable in theory and not
    in practice. That belongs here, not at first use."""
    monkeypatch.delenv("SLAV_LAB_TOKEN", raising=False)
    repos = {r["repo"]: r for r in client.get("/health").json()["repos"]}
    assert repos["OpticReports/uranium-dashboard"]["token_ready"] is True
    assert repos["OpticReports/slav-lab"]["token_ready"] is False


def test_gate_a_refusal_reports_which_files_were_touched(client, monkeypatch):
    """The first live refusal said the suite failed but not WHAT had been
    edited - so there was no way to tell whether the editor had touched the
    intended file at all. It had not, and that took a second run to learn."""
    from app.guard import Refused

    def refusing(*a, **k):
        raise Refused("refusing to push: the test suite failed.")
    monkeypatch.setattr(main, "do_task", refusing)
    monkeypatch.setattr(main, "_touched", lambda wd: ["btc-executor/app/hl.py"])
    r = client.post("/task", json={"task": "x"},
                    headers={"X-Agent-Token": "s3cret-token-value"})
    jid = r.json()["id"]
    for _ in range(200):
        j = client.get(f"/task/{jid}",
                       headers={"X-Agent-Token": "s3cret-token-value"}).json()
        if j["state"] != "running":
            break
    assert j["files"] == ["btc-executor/app/hl.py"], \
        "a refusal that cannot be attributed to a change is hard to act on"


def test_gate_boot_refuses_when_the_test_gate_cannot_run(monkeypatch):
    """A gate that cannot RUN is not a gate. Without pytest every task
    refuses forever - safe and useless - and it surfaced at first USE
    rather than at deploy, which is the wrong end to find it."""
    import importlib.util
    from fastapi.testclient import TestClient
    from app.guard import Refused
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda n, *a, **k: None if n == "pytest" else real(n, *a, **k))
    with pytest.raises(Refused, match="pytest is not installed"):
        with TestClient(main.app):
            pass
