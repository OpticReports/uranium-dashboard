"""Async job store. Coding tasks take minutes; an HTTP caller cannot hold
a connection that long, and a caller that times out mid-task has no way to
learn what happened.

So: POST returns a job id immediately, GET reports on it. Deliberately
in-memory - a job is only meaningful while the process that is running it
is alive, and a persisted "running" record surviving a restart would be a
lie about work that is no longer happening.
"""
from __future__ import annotations

import threading
import uuid
from collections import OrderedDict

MAX_JOBS = 50          # newest N; the rest are the caller's problem to have read


class Jobs:
    def __init__(self):
        self._d: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def create(self, task: str) -> str:
        jid = uuid.uuid4().hex[:12]
        with self._lock:
            self._d[jid] = {"id": jid, "task": task, "state": "running",
                            "result": None, "error": None}
            while len(self._d) > MAX_JOBS:
                self._d.popitem(last=False)
        return jid

    def finish(self, jid: str, result=None, error=None, files=None) -> None:
        with self._lock:
            j = self._d.get(jid)
            if j is None:
                return
            j["state"] = "error" if error else "done"
            j["result"], j["error"] = result, error
            if files:
                j["files"] = files

    def get(self, jid: str):
        with self._lock:
            j = self._d.get(jid)
            return dict(j) if j else None

    def recent(self, n: int = 10):
        with self._lock:
            return [dict(v) for v in list(self._d.values())[-n:]]
