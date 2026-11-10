#!/usr/bin/env python3
"""Attest Composer's LIVE trees to the mirror brain (composer/IBKR_MIRROR.md; contract schema 2).

The brain (mirror_brain.py) is keyless: it trades the approved trees in its own checkout and cannot see
whether Composer still runs them. This script holds the Composer key instead. Shortly before the
decision (about 15:50 ET) it reads each symphony's live tree and head version from Composer (GET only:
/symphonies/{id}/score and /versions, the calls shadow_runner.check_drift makes; whether a symphony is
paused comes from symphony-stats-meta), hashes the canonical tree with shadow_runner.tree_sha1 (the ONE
function the brain applies to its approved tree) and POSTs

    {"session": "YYYY-MM-DD", "engines": {NAME: {"version", "tree_sha1", "paused"}}}

to MIRROR_BRAIN_URL/mirror/attest with X-Attest-Token: MIRROR_ATTEST_TOKEN. The brain then marks each
engine ok / drift for that session; an engine whose live tree differs from the approved one is not
mirrored that day.

  mirror_attest.py              read Composer, post the attestation
  mirror_attest.py --dry-run    read Composer and compare with the approved trees here; post nothing

One summary line on stdout. Exit 0 when every engine was read and the brain stored it (--dry-run: when
every engine was read), 1 otherwise. An engine that cannot be read is left out (the brain keeps it at
'none') and named. It never trades, never edits a symphony, and prints no key or token.

Env: COMPOSER_API_KEY_ID, COMPOSER_SECRET (composerlib), MIRROR_BRAIN_URL (https; http only for
localhost), MIRROR_ATTEST_TOKEN.
"""
import concurrent.futures
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shadow_runner as sr  # noqa: E402

TIMEOUT_S = 20
LOCAL = ("localhost", "127.0.0.1", "::1")


def one_line(e, n=120):
    return " ".join(str(e).split())[:n]


def live_engine(cfg, get):
    """{'version', 'tree_sha1'} of one symphony as Composer runs it now (two GETs; raises on failure)"""
    tree = get(f"/symphonies/{cfg['symphony']}/score")
    if not isinstance(tree, dict) or not tree.get("step"):
        raise RuntimeError("the live tree is not a tree")
    vs = get(f"/symphonies/{cfg['symphony']}/versions")
    vs = vs if isinstance(vs, list) else (vs or {}).get("versions", [])
    head = vs[0].get("version_id") if vs and isinstance(vs[0], dict) else None
    if not isinstance(head, str) or not head:
        raise RuntimeError("no head version")
    return {"version": head, "tree_sha1": sr.tree_sha1(tree)}


def read_live(cfg_all, get, get_meta=None):
    """({NAME: {'version', 'tree_sha1'[, 'paused']}}, {NAME: why it could not be read}); the engines in
    parallel, one failure never stopping the others (composerlib exits on an HTTP error)"""
    def one(item):
        eng, cfg = item
        try:
            return eng, live_engine(cfg, get), None
        except (Exception, SystemExit) as e:  # noqa: BLE001
            return eng, None, one_line(e)
    engines, failed = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for eng, rec, err in ex.map(one, cfg_all.items()):
            if rec:
                engines[eng] = rec
            else:
                failed[eng] = err
    if get_meta and engines:
        try:
            by_id = {s.get("id"): s for s in get_meta() if isinstance(s, dict)}
            for eng in engines:
                s = by_id.get(cfg_all[eng]["symphony"])
                if s is not None:
                    engines[eng]["paused"] = bool(s.get("is_paused"))
        except (Exception, SystemExit):  # noqa: BLE001  the pause flag is optional in the attestation
            pass
    return engines, failed


def compare(cfg_all, engines, day):
    """{NAME: 'ok' | 'drift'} against the approved tree in use on `day` in THIS checkout"""
    out = {}
    for eng, rec in engines.items():
        era = sr.era_for(cfg_all[eng], day) or cfg_all[eng]["eras"][-1]
        out[eng] = "ok" if rec["tree_sha1"] == sr.tree_sha1(sr.load_tree(era)) else "drift"
    return out


def brain_url(base):
    """the attest endpoint, or raises ValueError: the token is only ever sent over https (or to localhost)"""
    u = urllib.parse.urlparse((base or "").strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("MIRROR_BRAIN_URL must be an http(s) URL")
    if u.scheme != "https" and u.hostname not in LOCAL:
        raise ValueError("MIRROR_BRAIN_URL must be https (http is accepted for localhost only)")
    return f"{u.scheme}://{u.netloc}{u.path.rstrip('/')}/mirror/attest"


def post(url, token, body, timeout=TIMEOUT_S):
    """(HTTP status, parsed JSON body or {})"""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Attest-Token": token,
                                          "user-agent": "composer-mirror-attest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, text = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, text = e.code, e.read()
    try:
        data = json.loads(text)
    except ValueError:
        data = {}
    return code, data if isinstance(data, dict) else {}


def run(argv=None, env=None, get=None, get_meta=None, now=None, send=None):
    """(exit code, the summary line). get / get_meta / send: test seams (Composer GET; symphony list; POST)"""
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    dry = "--dry-run" in argv
    now = now or datetime.datetime.now(datetime.timezone.utc)
    day = sr.et_now(now).date().isoformat()
    head = f"MIRROR ATTEST {day}"
    token, url = env.get("MIRROR_ATTEST_TOKEN", ""), None
    if not dry:
        try:
            url = brain_url(env.get("MIRROR_BRAIN_URL", ""))
        except ValueError as e:
            return 1, f"{head}: not posted ({e})"
        if not token:
            return 1, f"{head}: not posted (MIRROR_ATTEST_TOKEN not set)"
    if get is None:
        import composerlib as cl
        get = lambda p: cl.get(p, timeout=TIMEOUT_S)  # noqa: E731

        def get_meta():
            return cl.get(f"/portfolio/accounts/{cl.default_account()}/symphony-stats-meta", timeout=TIMEOUT_S)["symphonies"]
    cfg_all = sr.load_manifest()
    engines, failed = read_live(cfg_all, get, get_meta)
    here = compare(cfg_all, engines, day)
    parts = [f"{eng} {here[eng]} ({rec['version'][:8]}{', paused' if rec.get('paused') else ''})" for eng, rec in engines.items()]
    parts += [f"{eng} NOT READ ({why})" for eng, why in failed.items()]
    line = f"{head}: " + "; ".join(parts)
    if not engines:
        return 1, line + " | nothing to post"
    if dry:
        return (1 if failed else 0), line + " | dry run: not posted"
    try:
        code, data = (send or post)(url, token, {"session": day, "engines": engines})
    except Exception as e:  # noqa: BLE001
        return 1, line + f" | NOT POSTED ({one_line(e).replace(token, '***')})"
    if code != 200 or not data.get("ok"):
        return 1, line + f" | NOT POSTED (HTTP {code}: {one_line(data.get('error', 'no reason given')).replace(token, '***')})"
    states = {eng: s.get("state") for eng, s in (data.get("sync") or {}).items()}
    lost = sorted(set(engines) - set(data.get("stored") or []))
    brain = ", ".join(f"{eng} {st}" for eng, st in states.items())
    line += f" | posted {len(data.get('stored') or [])} of {len(cfg_all)}; the brain reads: {brain}"
    if lost:
        line += f" | NOT STORED: {', '.join(lost)}"
    return (1 if failed or lost else 0), line


def main():
    code, line = run()
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
