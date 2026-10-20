"""Offline tests for the cycle-nowcast v2 data pipelines (vintages, ads, piger, nber).

No network: every fetch goes through an injected transport. Real committed data is used where
the spec names it (data/alfred_first_vintage_2026.csv, data/alfred_shutdown/*, the Piger
history workbook, the F6/F7 derived tables). Nothing here computes a v2 metric; the only
"gate" exercised is the §5 comparator reproduction gate on the committed F7 panel.
Run: python3 -m pytest test_pipelines.py -q
"""
from __future__ import annotations

import csv
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
sys.path.insert(0, HERE)

import ads  # noqa: E402
import nber  # noqa: E402
import piger  # noqa: E402
import vintages as V  # noqa: E402


# ----------------------------------------------------------------------------- helpers

def csv_body(sid: str, vdate: str, rows) -> bytes:
    lines = [f"observation_date,{sid}_{vdate.replace('-', '')}"] + [f"{d},{v}" for d, v in rows]
    return ("\n".join(lines) + "\n").encode()


class Transport:
    """url -> list of (status, body) replies consumed in order (last one repeats); a reply of
    'timeout' raises TimeoutError. Counts calls."""

    def __init__(self, replies: dict):
        self.replies = {k: list(v) for k, v in replies.items()}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        q = self.replies[url]
        rep = q.pop(0) if len(q) > 1 else q[0]
        if rep == "timeout":
            raise TimeoutError("simulated")
        return rep


class Sleeper:
    def __init__(self):
        self.calls = []

    def __call__(self, s):
        self.calls.append(s)


def url(sid, d):
    return V.ALFRED_CSV_URL.format(sid=sid, d=d)


ROWS = [("2025-07-01", "100.0"), ("2025-08-01", "101.0"), ("2025-09-01", "102.5")]


# ----------------------------------------------------------------------------- §4.4 validation

def test_valid_vintage_is_validated_and_cached(tmp_path):
    t = Transport({url("PAYEMS", "2025-11-20"): [(200, csv_body("PAYEMS", "2025-11-20", ROWS))]})
    meta = V.fetch_vintage("PAYEMS", "2025-11-20", "1955-05-06", str(tmp_path), t, sleep=Sleeper())
    assert meta["last_obs_month"] == "2025-09" and meta["n_rows"] == 3 and meta["first_obs"] == "2025-07-01"
    p = V.cache_path(str(tmp_path), "PAYEMS", "2025-11-20")
    assert os.path.exists(p) and os.path.exists(p[:-4] + ".meta.json")
    assert meta["sha256"] == V.sha256_file(p)
    # second call: served from cache, no request
    n = len(t.calls)
    meta2 = V.fetch_vintage("PAYEMS", "2025-11-20", "1955-05-06", str(tmp_path), t, sleep=Sleeper())
    assert meta2["from_cache"] is True and len(t.calls) == n
    # the cached file re-parses with full validation
    rec = V.read_cached(str(tmp_path), "PAYEMS", "2025-11-20")
    assert rec["obs"] == [(d, v) for d, v in ROWS]


def test_header_date_mismatch_fails_and_is_not_cached(tmp_path):
    # the server echoes a different date than the listed one -> content/identity failure
    t = Transport({url("PAYEMS", "2025-11-20"): [(200, csv_body("PAYEMS", "2025-11-19", ROWS))]})
    with pytest.raises(V.ValidationFail) as e:
        V.fetch_vintage("PAYEMS", "2025-11-20", "1955-05-06", str(tmp_path), t, sleep=Sleeper())
    assert e.value.kind == "header_mismatch"
    assert not os.listdir(tmp_path)


def test_header_series_mismatch_fails(tmp_path):
    t = Transport({url("PAYEMS", "2025-11-20"): [(200, csv_body("INDPRO", "2025-11-20", ROWS))]})
    with pytest.raises(V.ValidationFail) as e:
        V.fetch_vintage("PAYEMS", "2025-11-20", "1955-05-06", str(tmp_path), t, sleep=Sleeper())
    assert e.value.kind == "header_mismatch" and not os.listdir(tmp_path)


def test_no_data_rows_fails(tmp_path):
    body = csv_body("PAYEMS", "2025-11-20", [("2025-07-01", "."), ("2025-08-01", ".")])
    t = Transport({url("PAYEMS", "2025-11-20"): [(200, body)]})
    with pytest.raises(V.ValidationFail) as e:
        V.fetch_vintage("PAYEMS", "2025-11-20", "1955-05-06", str(tmp_path), t, sleep=Sleeper())
    assert e.value.kind == "no_rows" and not os.listdir(tmp_path)
    t = Transport({url("PAYEMS", "2025-11-20"): [(200, csv_body("PAYEMS", "2025-11-20", []))]})
    with pytest.raises(V.ValidationFail):
        V.fetch_vintage("PAYEMS", "2025-11-20", "1955-05-06", str(tmp_path), t, sleep=Sleeper())


def test_non_csv_body_retries_with_backoff_then_hard_fails(tmp_path):
    html = b"<!DOCTYPE html><html><body>blocked</body></html>"
    t = Transport({url("ICSA", "2025-11-20"): [(200, html)]})
    s = Sleeper()
    with pytest.raises(V.HardFail) as e:
        V.fetch_vintage("ICSA", "2025-11-20", "2009-05-28", str(tmp_path), t, tries=4, sleep=s)
    assert e.value.kind == "non_csv" and len(t.calls) == 4
    assert s.calls == [1.0, 2.0, 4.0]            # exponential backoff between attempts
    assert not os.listdir(tmp_path)
    # recovers when the body turns into CSV on a later attempt
    t = Transport({url("ICSA", "2025-11-20"): [(200, html), (200, csv_body("ICSA", "2025-11-20", ROWS))]})
    st = {}
    meta = V.fetch_vintage("ICSA", "2025-11-20", "2009-05-28", str(tmp_path), t, tries=4, sleep=Sleeper(), stats=st)
    assert meta["last_obs_month"] == "2025-09" and st["retry_reasons"] == {"non_csv": 1}


def test_5xx_retries_then_hard_fails_never_cached(tmp_path):
    t = Transport({url("INDPRO", "2025-12-23"): [(503, b"Service Unavailable")]})
    s, st = Sleeper(), {}
    with pytest.raises(V.HardFail) as e:
        V.fetch_vintage("INDPRO", "2025-12-23", "1927-01-26", str(tmp_path), t, tries=3, sleep=s, stats=st)
    assert e.value.kind == "server_error" and len(t.calls) == 3 and s.calls == [1.0, 2.0]
    assert st["retry_reasons"] == {"server_error": 3} and not os.listdir(tmp_path)


def test_5xx_then_200_recovers(tmp_path):
    t = Transport({url("INDPRO", "2025-12-23"): [(502, b""), (504, b""), (200, csv_body("INDPRO", "2025-12-23", ROWS))]})
    st = {}
    meta = V.fetch_vintage("INDPRO", "2025-12-23", "1927-01-26", str(tmp_path), t, sleep=Sleeper(), stats=st)
    assert meta["last_obs_month"] == "2025-09" and st["retries"] == 2 and st["retried_ok"] == 1


def test_timeout_retries_then_hard_fails(tmp_path):
    t = Transport({url("W875RX1", "2026-01-22"): ["timeout"]})
    with pytest.raises(V.HardFail) as e:
        V.fetch_vintage("W875RX1", "2026-01-22", "2010-05-28", str(tmp_path), t, tries=2, sleep=Sleeper())
    assert e.value.kind == "timeout" and len(t.calls) == 2 and not os.listdir(tmp_path)


def test_404_rules(tmp_path):
    # empty 404 strictly before the first listed vintage: allowed, not cached
    t = Transport({url("CMRMTSPL", "2013-01-15"): [(404, b"")]})
    with pytest.raises(V.NotYetArchived):
        V.fetch_vintage("CMRMTSPL", "2013-01-15", "2013-06-14", str(tmp_path), t, sleep=Sleeper())
    # empty 404 at/after the first listed date: a failure, never "no vintage"
    t = Transport({url("CMRMTSPL", "2013-06-24"): [(404, b"")]})
    with pytest.raises(V.ValidationFail) as e:
        V.fetch_vintage("CMRMTSPL", "2013-06-24", "2013-06-14", str(tmp_path), t, sleep=Sleeper())
    assert e.value.kind == "not_found"
    # 404 with a body before the first listed date is not the allowed case either
    t = Transport({url("CMRMTSPL", "2013-01-15"): [(404, b"<html>not found</html>")]})
    with pytest.raises(V.ValidationFail):
        V.fetch_vintage("CMRMTSPL", "2013-01-15", "2013-06-14", str(tmp_path), t, sleep=Sleeper())
    assert not os.listdir(tmp_path)


def test_other_4xx_retries_then_hard_fails(tmp_path):
    t = Transport({url("PAYEMS", "2025-11-20"): [(429, b"rate limited")]})
    with pytest.raises(V.HardFail) as e:
        V.fetch_vintage("PAYEMS", "2025-11-20", "1955-05-06", str(tmp_path), t, tries=2, sleep=Sleeper())
    assert e.value.kind == "http_status" and len(t.calls) == 2


def test_parse_alfred_csv_rejects_unsorted_and_bad_values():
    with pytest.raises(V.ValidationFail):
        V.parse_alfred_csv(csv_body("PAYEMS", "2025-11-20", [("2025-08-01", "1"), ("2025-07-01", "2")]), "PAYEMS", "2025-11-20")
    with pytest.raises(V.ValidationFail):
        V.parse_alfred_csv(csv_body("PAYEMS", "2025-11-20", [("2025-08-01", "abc")]), "PAYEMS", "2025-11-20")
    rec = V.parse_alfred_csv(csv_body("PAYEMS", "2025-11-20", [("2025-08-01", "1"), ("2025-09-01", ".")]), "PAYEMS", "2025-11-20")
    assert rec["last_obs_month"] == "2025-08" and rec["n_rows"] == 2 and rec["n_numeric"] == 1
    # an EMPTY field is a served missing-value form (ALFRED's daily-rate vintages carry
    # hundreds: T10Y3M 2014-01-27 has 348 empty rows and no '.'), accepted like '.'
    rec = V.parse_alfred_csv(csv_body("PAYEMS", "2025-11-20", [("2025-08-01", "1"), ("2025-09-01", "")]), "PAYEMS", "2025-11-20")
    assert rec["last_obs_month"] == "2025-08" and rec["n_numeric"] == 1
    # a transfer cut mid-row lacks the trailing newline every served body ends with: refused
    # as non_csv (retried), never parsed — a cut last row would shift last_obs_month
    cut = csv_body("PAYEMS", "2025-11-20", [("2025-08-01", "1"), ("2025-09-01", "15")])[:-1]
    with pytest.raises(V.ValidationFail) as e:
        V.parse_alfred_csv(cut, "PAYEMS", "2025-11-20")
    assert e.value.kind == "non_csv"
    with pytest.raises(V.ValidationFail) as e:
        V.parse_alfred_csv(cut[:-1], "PAYEMS", "2025-11-20")                      # '2025-09-01,1' cut mid-value
    assert e.value.kind == "non_csv"
    for bad in ("nan", "inf", "-inf", "NaN"):                                   # float() parses these; the contract does not
        with pytest.raises(V.ValidationFail):
            V.parse_alfred_csv(csv_body("PAYEMS", "2025-11-20", [("2025-08-01", "1"), ("2025-09-01", bad)]), "PAYEMS", "2025-11-20")
    with pytest.raises(V.ValidationFail):                                        # duplicate observation dates
        V.parse_alfred_csv(csv_body("PAYEMS", "2025-11-20", [("2025-07-01", "1"), ("2025-07-01", "2")]), "PAYEMS", "2025-11-20")
    with pytest.raises(V.ValidationFail):                                        # empty body
        V.parse_alfred_csv(b"", "PAYEMS", "2025-11-20")


LIST_HTML = """<html><body><select id="form_units"><option value="lin">x</option></select>
<select id="form_selected_vintage_dates" name="form[selected_vintage_dates][]" multiple="multiple">
<option value="2013-06-14">2013-06-14</option>
<option value="2013-06-24">2013-06-24</option>
<option value="2013-06-26">2013-06-26</option>
</select><p>seid=CMRMTSPL 1967-01-01 to 2026-07-01</p></body></html>"""


def test_parse_vintage_list_takes_only_the_select_options():
    dates = V.parse_vintage_list(LIST_HTML, "CMRMTSPL")
    assert dates == ["2013-06-14", "2013-06-24", "2013-06-26"]      # not the obs-range dates
    with pytest.raises(V.ValidationFail):
        V.parse_vintage_list("<html><body>blocked</body></html>", "CMRMTSPL")
    with pytest.raises(V.ValidationFail):
        V.parse_vintage_list(LIST_HTML.replace("2013-06-26", "2013-06-01"), "CMRMTSPL")


def test_fetch_vintage_list_retries_non_list_pages():
    u = V.ALFRED_LIST_URL.format(sid="CMRMTSPL")
    t = Transport({u: [(200, b"<html>interstitial</html>"), (200, LIST_HTML.encode())]})
    dates, raw = V.fetch_vintage_list("CMRMTSPL", t, sleep=Sleeper())
    assert dates[0] == "2013-06-14" and len(t.calls) == 2
    t = Transport({u: [(502, b"")]})
    with pytest.raises(V.HardFail):
        V.fetch_vintage_list("CMRMTSPL", t, tries=2, sleep=Sleeper())


# ----------------------------------------------------------------------------- issue dates / IS label

def _vt(sid, items):
    return [{"series": sid, "vintage_date": d, "sha256": f"h{d}", "bytes": 1, "n_rows": 1,
             "first_obs": "1959-01-01", "last_obs": m + "-01", "last_obs_month": m} for d, m in items]


def test_issue_dates_synthetic_rules():
    vt = _vt("X", [("2025-09-05", "2025-08"),      # left-censored (first cached)
                   ("2025-09-16", "2025-08"),      # revision-only: not an issue date
                   ("2025-11-20", "2025-09"),      # issue date for 2025-09
                   ("2025-12-16", "2025-11"),      # multi-month: 2025-10 never latest
                   ("2026-01-09", "2025-12")])
    out = {r["month"]: r for r in V.issue_dates(vt)}
    assert out["2025-08"]["status"] == "left_censored" and out["2025-08"]["issue_date"] == "2025-09-05"
    assert out["2025-09"] == {"series": "X", "month": "2025-09", "issue_date": "2025-11-20",
                              "issue_sha256": "h2025-11-20", "first_vintage_containing": "2025-11-20", "status": "issue"}
    assert out["2025-10"]["status"] == "never_latest" and out["2025-10"]["issue_date"] == "" \
        and out["2025-10"]["first_vintage_containing"] == "2025-12-16"
    assert out["2025-11"]["issue_date"] == "2025-12-16" and out["2025-12"]["issue_date"] == "2026-01-09"
    assert sorted(out) == ["2025-08", "2025-09", "2025-10", "2025-11", "2025-12"]


def _committed_vintage_tables():
    rows = []
    for fn in ("vintage_table.csv", "calendar_check_vintages.csv"):
        with open(os.path.join(DATA, "vintages_panel", fn), newline="") as f:
            rows += list(csv.DictReader(f))
    return rows


def test_issue_dates_reproduce_the_2026_calendar_including_corrected_awhman_row():
    """DT-17: content-decided issue dates on the committed F6 tables vs alfred_first_vintage_2026.csv
    (AWHMAN 2026-04 -> 2026-05-08 is the corrected row). PERMIT/UMCSENT were not pulled (DT-13)."""
    with open(os.path.join(DATA, "alfred_first_vintage_2026.csv"), newline="") as f:
        ref = list(csv.DictReader(f))
    assert any(r["series"] == "AWHMAN" and r["ref_month"] == "2026-04" and r["first_vintage_date"] == "2026-05-08" for r in ref)
    res = V.calendar_check(_committed_vintage_tables(), ref)
    checked = [r for r in res["rows"] if r["pass"] is not None]
    assert res["pass"] and len(checked) == 42, [r for r in res["rows"] if r["pass"] is False]
    assert {r["series"] for r in checked} == {"PAYEMS", "AWHMAN", "INDPRO", "W875RX1", "CMRMTSPL", "RECPROUSM156N"}
    assert {r["series"] for r in res["rows"] if r["pass"] is None} == {"PERMIT", "UMCSENT"}
    byk = {(r["series"], r["month"]): r for r in res["rows"]}
    assert byk[("AWHMAN", "2026-04")]["computed"] == "2026-05-08"
    assert byk[("W875RX1", "2026-09")]["computed"] is None            # NOT_YET_BY_2026-10-20
    assert byk[("CMRMTSPL", "2026-07")]["computed"] == "2026-09-30"


def test_committed_issue_dates_flag_months_never_latest():
    with open(os.path.join(DATA, "vintages_panel", "issue_dates.csv"), newline="") as f:
        idt = list(csv.DictReader(f))
    nl = {(r["series"], r["month"]) for r in idt if r["status"] == "never_latest"}
    assert ("PAYEMS", "2025-10") in nl and ("INDPRO", "2025-10") in nl      # §4.3 example
    assert all(r["issue_date"] == "" for r in idt if r["status"] == "never_latest")
    revision_only = {("PAYEMS", "2026-09-01"), ("INDPRO", "2026-09-01"), ("W875RX1", "2026-08-01"), ("CMRMTSPL", "2026-07-01")}
    assert not any((r["series"], r["issue_date"]) in revision_only for r in idt)


def _last_obs_month(path):
    last = None
    with open(path) as f:
        next(f)
        for ln in f:
            d, v = ln.strip().split(",")
            if v not in ("", "."):
                last = d[:7]
    return last


F4 = {"2025-11-20": ("A", {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 2}, []),
      "2025-12-16": ("A", {"PAYEMS": 0, "INDPRO": 2, "W875RX1": 2, "CMRMTSPL": 4}, ["CMRMTSPL"]),
      "2026-01-09": ("A", {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 3, "CMRMTSPL": 3}, []),
      "2026-02-06": ("B", {"PAYEMS": 0, "INDPRO": 0, "W875RX1": 1, "CMRMTSPL": 2}, [])}


def test_is_label_on_the_four_shutdown_dates_from_F4_files():
    """§2.4 expected outputs, from the committed ALFRED vintage files' own content."""
    for d, (label, lags, dropped) in F4.items():
        P = {c: _last_obs_month(os.path.join(DATA, "alfred_shutdown", f"alf_{c}_{d}.csv")) for c in V.COIN_SERIES}
        lab = V.is_label(P)
        assert lab["IS"] == label and lab["lags"] == lags and lab["dropped"] == dropped, (d, lab)
        assert lab["K"] == min(P.values())
    lab = V.is_label({"PAYEMS": "2025-12", "INDPRO": "2025-11", "W875RX1": "2025-09", "CMRMTSPL": "2025-09"})
    assert lab["lag_ge3"] == ["W875RX1", "CMRMTSPL"] and lab["canonical"] is False and lab["K"] == "2025-09"
    assert V.is_label({"PAYEMS": "2026-09", "INDPRO": "2026-08", "W875RX1": "2026-08", "CMRMTSPL": "2026-07"})["canonical"] is True
    assert V.is_label({"PAYEMS": "2026-08", "INDPRO": "2026-08", "W875RX1": "2026-08", "CMRMTSPL": "2026-07"}) \
        == {**V.is_label({"PAYEMS": "2026-08", "INDPRO": "2026-08", "W875RX1": "2026-08", "CMRMTSPL": "2026-07"}), "IS": "C"}
    c2 = V.is_label({"PAYEMS": "2015-08", "INDPRO": "2015-08", "W875RX1": "2015-08", "CMRMTSPL": "2015-06"})
    assert c2["IS"] == "C" and c2["is_c_cmrmtspl_lag2"] is True and c2["K"] == "2015-06"
    # the identity gate keys on IS-C with CMRMTSPL at lag 1 ONLY (lag 2 is the spec-named
    # flag; lag 3 — 2015-09-28 — is neither and must not pass as an identity row)
    assert c2["is_c_identity"] is False
    c1 = V.is_label({"PAYEMS": "2015-08", "INDPRO": "2015-08", "W875RX1": "2015-08", "CMRMTSPL": "2015-07"})
    assert c1["is_c_identity"] is True and c1["is_c_cmrmtspl_lag2"] is False and c1["canonical"] is True
    c3 = V.is_label({"PAYEMS": "2015-08", "INDPRO": "2015-08", "W875RX1": "2015-08", "CMRMTSPL": "2015-05"})
    assert c3["IS"] == "C" and c3["is_c_identity"] is False and c3["is_c_cmrmtspl_lag2"] is False and c3["lag_ge3"] == ["CMRMTSPL"]
    assert c1["members_ahead"] == [] and c3["members_ahead"] == []
    # a member ahead of PAYEMS (outside §2.3) is flagged, never a silent negative lag
    ah = V.is_label({"PAYEMS": "2026-08", "INDPRO": "2026-09", "W875RX1": "2026-07", "CMRMTSPL": "2026-06"})
    assert ah["members_ahead"] == ["INDPRO"] and ah["lags"]["INDPRO"] == -1
    # §4.3 one target per (issue date, IS): row kinds
    assert V.row_kind("2026-01", "2026-01") == "nowcast" and V.row_kind("2025-12", "2026-01") == "completion"
    assert V.row_kind("2026-02", "2026-01") == "trigger_ahead"


def test_committed_issue_panel_carries_the_shutdown_rows():
    with open(os.path.join(DATA, "vintages_panel", "issue_panel_wide.csv"), newline="") as f:
        w = {(r["issue_date"], r["trigger"]): r for r in csv.DictReader(f)}
    for d, (label, lags, dropped) in F4.items():
        if d == "2026-02-06":
            assert not any(k[0] == d for k in w)       # an engine gate, not an issue date (§2.4)
            continue
        r = w[(d, "PAYEMS")]
        assert r["IS"] == label and {c: int(r[f"{c}_lag"]) for c in V.COIN_SERIES} == lags
        assert r["dropped"] == "|".join(dropped)
    assert all(r["IS"] in "ABC" for r in w.values()) and all(r["PAYEMS_lag"] == "0" for r in w.values())
    # IS-C rows with CMRMTSPL at lag 2 are flagged (DT-2: 2013-2017 and the shutdown)
    flagged = [k[0] for k, r in w.items() if r["is_c_cmrmtspl_lag2"] == "1"]
    assert flagged and all(r["IS"] == "C" and r["CMRMTSPL_lag"] == "2" for k, r in w.items() if r["is_c_cmrmtspl_lag2"] == "1")
    # identity rows = IS-C with CMRMTSPL at lag 1, and nothing else (the lag-3 row 2015-09-28 is neither)
    ident = {k for k, r in w.items() if r["is_c_identity"] == "1"}
    assert ident == {k for k, r in w.items() if r["IS"] == "C" and r["CMRMTSPL_lag"] == "1"} and len(ident) > 100
    assert w[("2015-09-28", "W875RX1")]["is_c_identity"] == "0" and w[("2015-09-28", "W875RX1")]["is_c_cmrmtspl_lag2"] == "0"
    # §4.3: a trigger month != M is a completion row, never a second nowcast row for M
    for r in w.values():
        assert r["row_kind"] == ("nowcast" if r["trigger_month"] == r["M"] else "completion"), r["issue_date"]
        assert r["row_kind"] == "nowcast" or r["trigger_month_ne_M"] == "1"
    now_keys = [(r["issue_date"], r["IS"]) for r in w.values() if r["row_kind"] == "nowcast"]
    assert len(now_keys) == len(set(now_keys))                  # exactly one nowcast target per (issue date, IS)
    assert sum(1 for r in w.values() if r["row_kind"] == "completion") == 10
    assert all(r["members_ahead"] == "" for r in w.values())    # no member ahead of PAYEMS in 2013-2026
    with open(os.path.join(DATA, "vintages_panel", "issue_panel_long.csv"), newline="") as f:
        long_ = list(csv.DictReader(f))
    assert {r["row_kind"] for r in long_} == {"nowcast", "completion"}
    assert all(w[(r["issue_date"], r["trigger"])]["row_kind"] == r["row_kind"] for r in long_)


def test_committed_raw_cache_tarball_matches_vintage_table(tmp_path):
    """F6 (DT-4): the raw ALFRED cache is frozen in git as data/vintages_raw.tar.xz; every
    row of vintage_table.csv must re-hash identically from the extracted files, and
    as_of() must read from it when no cache directory is given."""
    if not os.path.exists(V.RAW_TARBALL):
        pytest.skip("raw cache archive not present")
    cache = V.cache_from_tarball(V.RAW_TARBALL, str(tmp_path))
    with open(os.path.join(DATA, "vintages_panel", "vintage_table.csv"), newline="") as f:
        vt = list(csv.DictReader(f))
    assert len(vt) == 1571
    bad = []
    for r in vt:
        p = V.cache_path(cache, r["series"], r["vintage_date"])
        if not os.path.exists(p) or V.sha256_file(p) != r["sha256"] or os.path.getsize(p) != int(r["bytes"]):
            bad.append((r["series"], r["vintage_date"]))
    assert bad == []
    with open(os.path.join(DATA, "vintages_panel", "build_summary.json")) as f:
        bs = json.load(f)
    assert bs["raw_tarball"]["sha256"] == V.sha256_file(V.RAW_TARBALL) and bs["raw_tarball"]["bytes"] == os.path.getsize(V.RAW_TARBALL)
    V._tar_caches.clear()
    V._tar_caches[V.RAW_TARBALL] = cache                         # reuse this extraction
    st = V.as_of("2025-12-16", None, None)
    assert st["PAYEMS"]["vintage_date"] == "2025-12-16" and st["ICSA"]["vintage_date"] == "2025-12-11"
    assert st["CMRMTSPL"]["last_obs_month"] == "2025-07" and st["ICSA"]["sha256"] == next(
        r["sha256"] for r in vt if r["series"] == "ICSA" and r["vintage_date"] == "2025-12-11")
    V._tar_caches.clear()
    # a crafted archive member outside the <root>/<ID>/<ID>_<date>.csv contract is refused
    import tarfile
    evil = tmp_path / "evil.tar.xz"
    with tarfile.open(evil, "w:xz") as tf:
        p = tmp_path / "x.csv"
        p.write_text("observation_date,PAYEMS_20250101\n2025-01-01,1\n")
        tf.add(p, arcname="vintages_raw/PAYEMS/../../PAYEMS_2025-01-01.csv")
    with pytest.raises(V.VintageError):
        V.cache_from_tarball(str(evil), str(tmp_path / "out"))


def test_as_of_reads_latest_listed_vintage_from_cache(tmp_path):
    cache, lists = str(tmp_path / "cache"), str(tmp_path / "lists")
    os.makedirs(lists)
    for sid, vints in {"PAYEMS": [("2025-11-20", "2025-09"), ("2025-12-16", "2025-11")],
                       "ICSA": [("2025-11-20", None)]}.items():
        with open(os.path.join(lists, f"vd_{sid}.txt"), "w") as f:
            f.write("\n".join(d for d, _ in vints) + "\n")
        for d, m in vints:
            rows = ([("2025-11-01", "198000"), ("2025-11-08", "201000"), ("2025-11-15", "199000")] if sid == "ICSA"
                    else [(f"{m}-01", "150000"), ("2025-07-01", "149000")][::-1])
            V._atomic_write(V.cache_path(cache, sid, d), csv_body(sid, d, rows))
            V._atomic_write(V.cache_path(cache, sid, d)[:-4] + ".meta.json", b"{}")
    out = V.as_of("2025-12-15", cache, lists, series=("PAYEMS", "ICSA"))
    assert out["PAYEMS"]["vintage_date"] == "2025-11-20" and out["PAYEMS"]["last_obs_month"] == "2025-09"
    assert V.as_of("2025-12-16", cache, lists, series=("PAYEMS",))["PAYEMS"]["vintage_date"] == "2025-12-16"
    assert V.as_of("2025-11-19", cache, lists, series=("PAYEMS",))["PAYEMS"] is None
    assert V.monthly(out["ICSA"]["obs"], "mean") == {"2025-11": (198000 + 201000 + 199000) / 3}
    assert V.monthly(out["PAYEMS"]["obs"], "last") == {"2025-07": 149000.0, "2025-09": 150000.0}
    os.remove(V.cache_path(cache, "PAYEMS", "2025-12-16"))
    with pytest.raises(V.VintageError):            # listed but uncached: never substitutes
        V.as_of("2025-12-16", cache, lists, series=("PAYEMS",))


# ----------------------------------------------------------------------------- ADS

def _ads_rows():
    hdr = ["Date", "ADS_INDEX_022615", "ADS_INDEX_030615", "ADS_INDEX_102325"]
    rows = []
    import datetime as dt
    d = dt.date(2015, 1, 1)
    while d <= dt.date(2015, 3, 7):
        s = d.strftime("%Y:%m:%d")
        v1 = float(d.day) / 10 if d <= dt.date(2015, 2, 21) else None
        v2 = float(d.day) / 10 + 1.0 if d <= dt.date(2015, 3, 7) else None
        v3 = -1.0
        rows.append((s, v1, v2, v3))
        d += dt.timedelta(days=1)
    return hdr, rows


def test_ads_derive_panel_synthetic_and_readings():
    hdr, rows = _ads_rows()
    panel, ref, months, S, C, vd, n = ads.derive_panel(hdr, rows, ref_vintage="2015-03-06")
    assert vd == ["2015-02-26", "2015-03-06", "2025-10-23"] and n == len(rows) and months == ["2015-01", "2015-02", "2015-03"]
    p = {r["vintage_date"]: r for r in panel}
    a = p["2015-02-26"]
    assert a["last_date"] == "2015-02-21" and float(a["last_value"]) == 2.1
    assert a["m0"] == "2015-02" and a["m0_n"] == 21 and a["m0_complete"] == 0 and abs(float(a["m0_avg"]) - 1.1) < 1e-12
    assert a["m1"] == "2015-01" and a["m1_n"] == 31 and a["m1_complete"] == 1 and abs(float(a["m1_avg"]) - 1.6) < 1e-12
    assert a["m2"] == "2014-12" and a["m2_avg"] == "" and a["m2_n"] == 0
    b = p["2015-03-06"]
    assert b["last_date"] == "2015-03-07" and b["m1"] == "2015-02" and b["m1_complete"] == 1 and abs(float(b["m1_avg"]) - 2.45) < 1e-12
    assert p["2025-10-23"]["claims_only"] == 1 and a["claims_only"] == 0
    assert len(ref) == len(rows) and ref[0] == ("2015-01-01", 1.1)
    # readings through load/select (write + read the panel to exercise the typed loader)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "ads_vintage_panel.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=ads.PANEL_FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(panel)
        P = ads.load_panel(path)
    assert ads.ads_last(P, "2015-03-06")["vintage_date"] == "2015-03-06"              # same-day included
    assert ads.ads_last(P, "2015-03-06", strict=True)["vintage_date"] == "2015-02-26"  # "< d" sensitivity
    assert ads.ads_last(P, "2015-02-25") is None
    r = ads.ads_avg(P, "2015-02", "2015-03-06")
    assert r["vintage_date"] == "2015-03-06" and abs(r["value"] - 2.45) < 1e-12 and r["complete"] and r["n_days"] == 28
    r = ads.ads_avg(P, "2015-02", "2015-02-26")
    assert r["n_days"] == 21 and r["complete"] is False and abs(r["value"] - 1.1) < 1e-12
    assert ads.ads_avg(P, "2015-03", "2015-02-26")["value"] is None
    assert ads.ads_avg(P, "2014-11", "2015-03-06")["value"] is None
    assert ads.prev_complete_month(P[0]) == ("2015-01", P[0]["m1_avg"])


def test_ads_column_and_date_parsers():
    assert ads.vintage_date_of("ADS_INDEX_120508") == "2008-12-05" and ads.vintage_date_of("ADS_INDEX_101626") == "2026-10-16"
    assert ads.iso_of("2008:11:30") == "2008-11-30"
    with pytest.raises(ads.AdsError):
        ads.vintage_date_of("ADS_INDEX")
    with pytest.raises(ads.AdsError):
        ads.iso_of("2008-11-30")


def test_ads_comparator_gate_reproduces_committed_result():
    """§5 gate on the committed F7 panel: the spec-literal sample (every vintage 2008-11..2010-10)
    and the accuracy note's own sample (IP-release-day updates). The committed gate_ads.json is
    the record; this re-derives it deterministically (sans the INDPRO cache, so note-literal is
    checked from the stored rows)."""
    panel = ads.load_panel(os.path.join(DATA, "ads_panel", "ads_vintage_panel.csv"))
    ref = ads.load_ref_daily(os.path.join(DATA, "ads_panel", f"ads_vintage_{ads.REF_VINTAGE}.csv"))
    with open(os.path.join(DATA, "ads_panel", "gate_ads.json")) as f:
        stored = json.load(f)
    ind = [{"vintage_date": r["g17_date"], "last_obs_month": ads.prev_month(m)}
           for m, r in stored["note_literal"]["ip_days"].items() if r["g17_date"]]
    res = ads.comparator_gate(panel, ref, ind)
    for key in ("last_point", "prev_complete_month_avg"):
        assert res[key]["n"] == stored[key]["n"] and abs(res[key]["corr"] - stored[key]["corr"]) < 1e-12
        assert res[key]["pass"] == stored[key]["pass"]
    for key in ("last_point", "prev_month_avg"):
        assert abs(res["note_literal"][key]["corr"] - stored["note_literal"][key]["corr"]) < 1e-12
        assert res["note_literal"][key]["n"] == 24
    assert res["pass"] == stored["pass"]
    assert len(panel) == 1575 and panel[0]["vintage_date"] == "2008-12-05" and panel[-1]["vintage_date"] == "2026-10-16"


def test_ads_claims_only_flags_in_committed_panel():
    panel = ads.load_panel(os.path.join(DATA, "ads_panel", "ads_vintage_panel.csv"))
    co = [r["vintage_date"] for r in panel if r["claims_only"]]
    assert co == ["2025-10-16", "2025-10-23", "2025-10-30", "2025-11-06", "2025-11-13"]
    assert all("2025-11-20" <= r["vintage_date"] <= "2025-12-23" for r in panel if r["shutdown_partial"])


# ----------------------------------------------------------------------------- Piger

def test_fix_headers_corrects_the_one_year_typo_and_refuses_the_rest():
    fixed, flags = piger.fix_headers(["2025-11-26", "2025-12-29", "2025-01-30", "2026-03-02"])
    assert fixed == ["2025-11-26", "2025-12-29", "2026-01-30", "2026-03-02"] and flags == [False, False, True, False]
    with pytest.raises(piger.PigerError):
        piger.fix_headers(["2025-11-26", "2025-11-26"])


def _rel(date, months_probs):
    ms = [m for m, _ in months_probs]
    ps = [p for _, p in months_probs]
    return {"release_date": date, "header_as_in_file": date, "header_corrected": False,
            "months": ms, "probs": ps, "latest_month": ms[-1], "latest_prob": ps[-1]}


def test_rule_3x80_synthetic_peak_and_trough_dating():
    base = [("2007-10", 0.1), ("2007-11", 0.2), ("2007-12", 0.4), ("2008-01", 0.45)]
    r1 = _rel("2008-12-01", base + [("2008-02", 0.52), ("2008-03", 0.6), ("2008-04", 0.85), ("2008-05", 0.9), ("2008-06", 0.7)])
    r2 = _rel("2009-01-01", base + [("2008-02", 0.52), ("2008-03", 0.6), ("2008-04", 0.85), ("2008-05", 0.9), ("2008-06", 0.81), ("2008-07", 0.3)])
    r3 = _rel("2009-07-01", base + [("2008-02", 0.52), ("2008-03", 0.6), ("2008-04", 0.85), ("2008-05", 0.9), ("2008-06", 0.81),
                                    ("2008-07", 0.6), ("2008-08", 0.4), ("2008-09", 0.1), ("2008-10", 0.1), ("2008-11", 0.1)])
    events, states = piger.rule_3x80([r1, r2, r3], scan_from="2007-01")
    assert states == ["expansion", "recession", "expansion"]
    s, e = events
    assert s["release_date"] == "2009-01-01" and s["trigger_months"] == ["2008-04", "2008-05", "2008-06"]
    assert s["first_recession_month"] == "2008-02" and s["peak_month"] == "2008-01"
    assert e["release_date"] == "2009-07-01" and e["trigger_months"] == ["2008-09", "2008-10", "2008-11"] \
        and e["first_below_half_month"] == "2008-08" and e["trough_month"] == "2008-07"
    # strict '>' vs '>=': a month at exactly 0.80 does not count under the published rule
    r4 = _rel("2010-01-01", [("2009-01", 0.8), ("2009-02", 0.9), ("2009-03", 0.9)])
    assert piger.rule_3x80([r4], scan_from="2009-01")[0] == []
    assert len(piger.rule_3x80([r4], scan_from="2009-01", strict=False)[0]) == 1
    sens = piger.rule_1m50([r1, r2, r3])
    assert [(x["release_date"], x["episode"]) for x in sens] == [("2008-12-01", 1)]


def test_parse_rows_rejects_bad_values_and_dates():
    import datetime as dt
    hdr = [None, dt.datetime(2020, 4, 30), dt.datetime(2020, 5, 29)]
    rows = [(dt.datetime(2020, 2, 1), 0.01, 0.02), (dt.datetime(2020, 3, 1), 1.0, 1.0), (dt.datetime(2020, 4, 1), None, 1.0)]
    rel = piger.parse_rows(hdr, rows)
    assert [r["latest_month"] for r in rel] == ["2020-03", "2020-04"] and rel[0]["latest_prob"] == 1.0
    with pytest.raises(piger.PigerError):
        piger.parse_rows(hdr, [(dt.datetime(2020, 2, 1), 1.5, 0.02)])
    with pytest.raises(piger.PigerError):           # a release dated before its latest month
        piger.parse_rows([None, dt.datetime(2020, 2, 15)], [(dt.datetime(2020, 3, 1), 0.5)])


def test_piger_known_events_on_the_committed_history_file():
    """Research pass §1 row 7 and verify_R3: the 3x80% rule declares at the 2009-01-01 release
    (Jul/Aug/Sep-2008 = 88.3/97.7/98.0%) with the >= 50% chain starting 2008-02 (51.98%), i.e.
    first recession month 2008-02 (Hamilton) and, under §6's rule as written, peak 2008-01; it
    never fires for 2020; the 2021-10-29 release printed Sep-2021 = 44.4% (no fire under either
    rule); the 1-month >= 50% sensitivity catches Mar-2020 at 2020-04-30."""
    rel = piger.load_history(os.path.join(DATA, "piger", "History_of_Real_Time_Recession_Probabilities.xlsx"))
    assert len(rel) == 240 and rel[0]["release_date"] == "2006-08-01" and rel[-1]["release_date"] == "2026-09-30"
    assert [r["release_date"] for r in rel if r["header_corrected"]] == ["2026-01-30"]
    events, _ = piger.rule_3x80(rel)
    starts = [e for e in events if e["kind"] == "recession_start"]
    assert len(starts) == 1 and starts[0]["release_date"] == "2009-01-01"
    assert starts[0]["trigger_months"] == ["2008-07", "2008-08", "2008-09"] and starts[0]["trigger_pct"] == [88.26, 97.68, 98.04]
    assert starts[0]["first_recession_month"] == "2008-02" and starts[0]["peak_month"] == "2008-01"
    assert starts[0]["chain_pct"]["2008-02"] == 51.98 and starts[0]["chain_pct"]["2008-01"] == 39.28
    ends = [e for e in events if e["kind"] == "recession_end"]
    assert len(ends) == 1 and ends[0]["release_date"] == "2010-01-01" and ends[0]["trough_month"] == "2009-06"
    r = next(x for x in rel if x["release_date"] == "2021-10-29")
    assert r["latest_month"] == "2021-09" and abs(100 * r["latest_prob"] - 44.4) < 1e-9
    sens = piger.rule_1m50(rel)
    assert sens[0]["release_date"] == "2008-11-01" and sens[0]["latest_month"] == "2008-08"
    assert any(s["release_date"] == "2020-04-30" and s["latest_month"] == "2020-03" for s in sens)
    assert not any(s["release_date"] == "2021-10-29" for s in sens)
    assert not any("2019-06" <= e["latest_month"] <= "2021-12" for e in starts)


def test_committed_realtime_path_matches_the_history_file():
    with open(os.path.join(DATA, "piger", "realtime_path.csv"), newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 240 and rows[0]["release_date"] == "2006-08-01"
    r = next(x for x in rows if x["release_date"] == "2021-10-29")
    assert r["latest_month"] == "2021-09" and abs(float(r["piger_latest_pct"]) - 44.4) < 1e-9 and r["rule_1m50_fires"] == "0"
    assert next(x for x in rows if x["release_date"] == "2026-01-30")["header_as_in_file"] == "2025-01-30"
    alf = [x for x in rows if x["value_source"] == "alfred"]
    assert alf and alf[0]["release_date"] == "2012-09-01" and alf[0]["alfred_vintage_date"] == "2012-09-04"
    assert all(x["alfred_vintage_date"] >= x["release_date"] and x["alfred_latest_month"] == x["latest_month"] for x in alf)
    with open(os.path.join(DATA, "piger", "realtime_events.json")) as f:
        ev = json.load(f)
    assert ev["release_lag_days"]["median"] == 60.0 and ev["rule_3x80"]["same_on_spec_vectors"] is True


# ----------------------------------------------------------------------------- NBER

def test_nber_turning_points_and_onsets():
    res = nber.build(os.path.join(DATA, "nber", "nber_turning_points_announcements.csv"),
                     os.path.join(DATA, "fred_2026-10-20", "USREC.csv"))
    assert res["cross_check_pass"] and len(res["turning_points"]) == 12
    assert res["onsets_scored_in_august_study"] == ["1973-12", "1980-02", "1981-08", "1990-08", "2001-04", "2008-01", "2020-03"]
    tp = {(r["type"], r["month"]): r for r in res["turning_points"]}
    assert tp[("peak", "2007-12")]["announcement_date"] == "2008-12-01" and tp[("peak", "2020-02")]["announcement_lag_months"] == 4
    assert tp[("trough", "2009-06")]["announcement_date"] == "2010-09-20"
    with pytest.raises(nber.NberError):
        nber.load_turning_points(os.path.join(DATA, "piger", "piger_first_release_by_month.csv"))


# ----------------------------------------------------------------------------- determinism

def test_determinism_of_every_derivation():
    hdr, rows = _ads_rows()
    a = ads.derive_panel(hdr, rows, ref_vintage="2015-03-06")
    b = ads.derive_panel(hdr, rows, ref_vintage="2015-03-06")
    assert a[0] == b[0] and a[1] == b[1] and (a[3] == b[3]).all() and (a[4] == b[4]).all()
    vt = _committed_vintage_tables()
    assert V.issue_dates(vt) == V.issue_dates(vt)
    rel = piger.load_history(os.path.join(DATA, "piger", "History_of_Real_Time_Recession_Probabilities.xlsx"))
    assert piger.rule_3x80(rel) == piger.rule_3x80(rel) and piger.rule_1m50(rel) == piger.rule_1m50(rel)
    panel = ads.load_panel(os.path.join(DATA, "ads_panel", "ads_vintage_panel.csv"))
    ref = ads.load_ref_daily(os.path.join(DATA, "ads_panel", f"ads_vintage_{ads.REF_VINTAGE}.csv"))
    g1, g2 = ads.comparator_gate(panel, ref), ads.comparator_gate(panel, ref)
    g1.pop("computed"), g2.pop("computed")
    assert json.dumps(g1, sort_keys=True) == json.dumps(g2, sort_keys=True)


def test_no_model_or_product_identifiers_in_study_files():
    # vendor / model-family names assembled from fragments so this file does not carry them
    bad = tuple("".join(x) for x in (("cla", "ude"), ("anth", "ropic"), ("open", "ai"), ("gpt", "-"), ("gem", "ini")))
    files = [os.path.join(HERE, fn) for fn in sorted(os.listdir(HERE))
             if fn.endswith((".py", ".md", ".json")) and fn != os.path.basename(__file__)]
    for root, _, fns in os.walk(DATA):                     # committed data: text files only
        files += [os.path.join(root, fn) for fn in sorted(fns) if fn.endswith((".csv", ".json", ".md", ".txt"))]
    hits = []
    for p in files:
        with open(p, encoding="utf-8", errors="replace") as f:
            txt = f.read().lower()
        hits += [(os.path.relpath(p, HERE), b) for b in bad if b in txt]
    assert hits == [], hits
