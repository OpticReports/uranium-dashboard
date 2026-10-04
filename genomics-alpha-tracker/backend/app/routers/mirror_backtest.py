"""Executor-mirror backtest serving — GET/POST under /blend3070/mirror-backtest.

Serves the results of scripts/backtest_executor_mirror.py (the blend3070
book replayed with the executor's mechanics on the R2-A fire set) and lets
the dashboard launch the replay on the host.

  GET  /blend3070/mirror-backtest         the results JSON (+ served_from)
  GET  /blend3070/mirror-backtest/status  running / last run / error tail
  POST /blend3070/mirror-backtest/run     start the replay (202; 409 while running)

Auth: nothing per-route — the app-wide Basic middleware (main.py) gates
every route except /health, exactly like POST /calls/generate. The
BLEND_API_TOKEN exception applies only to GET /blend3070/intents.

Files: the results are read from the persistent data disk first
(Path(settings.cache_dir).parent — CACHE_DIR=/app/data/cache on Render, so
/app/data/backtest_executor_mirror_results.json; backend/data/ locally),
then from the committed backend/data/ file, else 404 with a clear message.
POST /run writes to the disk path so a result survives redeploys without a
commit. The replay runs as a SUBPROCESS watched by a daemon thread (the
main.py startup-backfill pattern) rather than in-process: a GIL-bound
minute of pure Python inside the API worker would starve /health. Single
flight via a module lock. It needs the gitignored bars cache on the host —
without it the script exits non-zero and the error tail says so.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import BACKEND_DIR, settings

router = APIRouter(prefix="/mirror-backtest", tags=["blend"])

RESULTS_NAME = "backtest_executor_mirror_results.json"
LOG_NAME = "backtest_executor_mirror.log"
NOT_RUN_DETAIL = (
    "executor mirror backtest not run yet — POST /blend3070/mirror-backtest/run on the "
    "host (rebuilds backend/data/backtest_bars.json on the FMP dividend-adjusted lane when "
    "absent; needs FMP_API_KEY) or commit backend/data/backtest_executor_mirror_results.json"
)
ERROR_TAIL_LINES = 20

# Module-level run state (single flight). Tests monkeypatch `popen`,
# `disk_path` and `committed_path`.
_lock = threading.Lock()
_state: dict = {"running": False, "started_at": None, "finished_at": None,
                "returncode": None, "error": None, "pid": None}
popen = subprocess.Popen   # indirection so tests can stub the process


def disk_path() -> Path:
    return Path(settings.cache_dir).parent / RESULTS_NAME


def bars_cache_path() -> Path:
    """The replay's bars cache (gitignored; on the data disk once refreshed)."""
    return BACKEND_DIR / "data" / "backtest_bars.json"


def committed_path() -> Path:
    return BACKEND_DIR / "data" / RESULTS_NAME


def seed_path() -> Path:
    """The committed copy as baked into the image. On Render the persistent
    disk is mounted AT /app/data and shadows the image's backend/data, so a
    committed results file is invisible there; the Dockerfile also copies
    backend/data to /app/seed_data for exactly this fallback."""
    return BACKEND_DIR / "seed_data" / RESULTS_NAME


def log_path() -> Path:
    return disk_path().parent / LOG_NAME


def _resolve() -> tuple[Path, str] | None:
    disk, committed, seed = disk_path(), committed_path(), seed_path()
    if disk.exists():
        return disk, ("disk (same path as committed)"
                      if disk.resolve() == committed.resolve() else "disk")
    if committed.exists():
        return committed, "committed"
    if seed.exists():
        return seed, "seed (committed, image copy)"
    return None


def _log_tail(n: int = ERROR_TAIL_LINES) -> str | None:
    try:
        lines = log_path().read_text(errors="replace").splitlines()
    except OSError:
        return None
    return "\n".join(lines[-n:]) if lines else None


def _watch(proc) -> None:
    rc = None
    try:
        rc = proc.wait()
    except Exception as exc:  # noqa: BLE001
        rc = -1
        err = f"watcher failed: {exc}"
    else:
        err = None
    with _lock:
        _state["running"] = False
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        _state["returncode"] = rc
        if rc != 0:
            _state["error"] = err or _log_tail() or f"replay exited with code {rc} (no log)"
        else:
            _state["error"] = None


@router.get("")
def get_results():
    found = _resolve()
    if found is None:
        raise HTTPException(404, NOT_RUN_DETAIL)
    path, served_from = found
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"results file unreadable: {exc}") from exc
    data["served_from"] = served_from
    return data


@router.get("/status")
def get_status():
    found = _resolve()
    last_run = None
    if found is not None:
        try:
            last_run = json.loads(found[0].read_text()).get("generated")
        except (OSError, ValueError):
            last_run = None
    with _lock:
        st = dict(_state)
    return {
        "running": st["running"],
        "started_at": st["started_at"],
        "finished_at": st["finished_at"],
        "returncode": st["returncode"],
        "error": st["error"],
        "last_run": last_run,
        "results_present": found is not None,
        "served_from": found[1] if found else None,
    }


@router.post("/run", status_code=202)
def run_replay():
    """Launch the 10-year replay on the host (writes to the data disk)."""
    with _lock:
        if _state["running"]:
            raise HTTPException(409, "replay already running since %s" % _state["started_at"])
        out = disk_path()
        out.parent.mkdir(parents=True, exist_ok=True)
        log = log_path()
        # --no-report: the doc lives outside the container's writable tree
        # on the host; the results JSON is the deliverable there
        cmd = [sys.executable, "-m", "scripts.backtest_executor_mirror",
               "--out", str(out), "--fetch-missing", "--no-report"]
        if not bars_cache_path().exists():
            # the August campaign cache is gone; the script rebuilds the FMP
            # dividend-adjusted lane itself (needs FMP_API_KEY on the host)
            cmd.append("--refresh-bars")
        try:
            log_fh = open(log, "w")  # noqa: SIM115 — handed to the subprocess
            try:
                proc = popen(cmd, cwd=str(BACKEND_DIR), stdout=log_fh, stderr=subprocess.STDOUT)
            finally:
                log_fh.close()      # the child holds its own descriptor
        except OSError as exc:
            raise HTTPException(500, f"could not start replay: {exc}") from exc
        started = datetime.now(timezone.utc).isoformat()
        _state.update({"running": True, "started_at": started, "finished_at": None,
                       "returncode": None, "error": None, "pid": getattr(proc, "pid", None)})
    threading.Thread(target=_watch, args=(proc,), daemon=True,
                     name="mirror-backtest-watch").start()
    return {"started_at": started, "log": str(log), "out": str(out)}
