from datetime import date, timedelta
from unittest.mock import patch

from app.api.routes_margin_fast import (
    FAST_PLAYBOOK, _z_series, fast_state, margin_fast,
)
from app.sources.cftc import parse_emini_pct_oi


def test_parse_emini_pct_oi():
    rows = [
        {"report_date_as_yyyy_mm_dd": "2026-07-21T00:00:00.000",
         "lev_money_positions_long": "146834",
         "lev_money_positions_short": "469699",
         "open_interest_all": "1939493"},
        {"report_date_as_yyyy_mm_dd": "2026-07-14T00:00:00.000",
         "lev_money_positions_long": "100",
         "lev_money_positions_short": "50",
         "open_interest_all": "0"},          # zero OI -> dropped
        {"report_date_as_yyyy_mm_dd": "bad-date",
         "lev_money_positions_long": "1", "lev_money_positions_short": "1",
         "open_interest_all": "10"},          # unparseable -> dropped
    ]
    d, v = parse_emini_pct_oi(rows)
    assert d == [date(2026, 7, 21)]
    assert round(v[0], 1) == -16.6            # structurally net short, as % of OI


def test_z_series_warmup_and_value():
    vals = [0.0] * 51
    z = _z_series(vals, window=156, min_n=52)
    assert all(x is None for x in z)          # below min_n -> no z yet
    vals = [0.0] * 60 + [10.0]
    z = _z_series(vals, window=156, min_n=52)
    assert z[50] is None and z[51] is not None
    assert z[-1] > 3.0                        # a 10-sigma-ish outlier scores high


def test_fast_state_pre_registered_rules():
    # order: FLUSH beats WASHED_OUT beats RISK_BUILD beats CALM
    assert fast_state(None, -1.0, 9.0) is None
    assert fast_state(-2.0, -1.0, 9.0) == "FLUSH"        # both flush legs met
    assert fast_state(-1.5, 0.2, -1.0) == "WASHED_OUT"   # flushed z, calm vol
    assert fast_state(-1.5, 0.2, 3.0) == "CALM"          # z low but vix20 > 0
    assert fast_state(1.4, 0.3, 2.0) == "RISK_BUILD"
    assert fast_state(1.4, 0.3, 6.0) == "CALM"           # vol already moving
    assert fast_state(0.0, 0.0, 0.0) == "CALM"
    for s in ("FLUSH", "WASHED_OUT", "RISK_BUILD", "CALM"):
        pb = FAST_PLAYBOOK[s]
        assert pb["stats"]["fwd12m"]["n"] > 0 and pb["action"]


def test_margin_fast_endpoint_shape():
    # 60 weeks of COT (flat then a plunge), 300 days of VIX & HY
    # weeks chosen so the plunge weeks overlap the VIX range below — the
    # historical state_series needs both legs alignable per report date
    weeks = [date(2024, 10, 7) + timedelta(weeks=i) for i in range(60)]
    # noisy base (sd ~2) then a 5-week plunge: dz4 << -0.5 with a sane z scale
    cot_vals = ([-10.0 + (2.0 if i % 2 else -2.0) for i in range(55)]
                + [-13.0, -16.0, -19.0, -22.0, -25.0])
    days = [date(2025, 6, 1) + timedelta(days=i) for i in range(300)]
    bundle = {
        "vix": (days, [15.0] * 280 + [15.0 + i for i in range(20)]),  # spiking
        "hy_oas": (days, [3.0] * 300),                                # % -> 300bp
    }
    perp = {"mark_price": 63000.0, "oi_usd": 7.2e8, "funding_8h": -1e-4,
            "funding_ann_pct": -10.95}
    with patch("app.api.routes_margin_fast.fetch_bundle", return_value=bundle), \
         patch("app.api.routes_margin_fast.fetch_emini_leveraged",
               return_value=(weeks, cot_vals)), \
         patch("app.api.routes_margin_fast.fetch_btc_perp", return_value=perp), \
         patch("app.api.routes_margin_fast.fetch_funding_history",
               return_value=([date(2026, 7, 27)], [-10.95])), \
         patch("app.api.routes_margin_fast._persist_oi_snapshot",
               return_value=[{"date": "2026-07-28", "oi_usd": 7.2e8}]):
        r = margin_fast()
    # plunging positioning + spiking vol -> FLUSH under pre-registered rules
    assert r["state"] == "FLUSH"
    # historical band series uses VIX AS-OF each report date — the fixture's
    # VIX was still calm on the plunge weeks' dates, so those weeks read
    # WASHED_OUT even though the CURRENT composite (today's spiking VIX +
    # latest COT) reads FLUSH. Pins the as-of semantics.
    assert r["state_series"] and r["state_series"][-1]["state"] == "WASHED_OUT"
    assert r["cot"]["z"] is not None and r["cot"]["dz4"] < -0.5
    assert r["vix"]["d20"] >= 8
    assert r["hy"]["current_bp"] == 300
    assert r["btc"]["perp"]["funding_ann_pct"] < 0
    assert r["cross_read"]["FLUSH"]["BLOWOFF"]
    assert r["relationship"] and r["playbook"]["WASHED_OUT"]["stats"]["fwd12m"]["pct_pos"] == 95


def test_margin_fast_endpoint_degrades_when_sources_missing():
    with patch("app.api.routes_margin_fast.fetch_bundle", return_value={}), \
         patch("app.api.routes_margin_fast.fetch_emini_leveraged",
               return_value=([], [])), \
         patch("app.api.routes_margin_fast.fetch_btc_perp", return_value=None), \
         patch("app.api.routes_margin_fast.fetch_funding_history",
               return_value=([], [])), \
         patch("app.api.routes_margin_fast._persist_oi_snapshot", return_value=[]):
        r = margin_fast()
    assert r["state"] is None
    assert r["cot"]["z"] is None and r["vix"]["d20"] is None
    assert r["btc"]["perp"] is None


def test_stress_state_75y_proxy():
    import math
    import random
    from app.api.routes_margin_fast import DEEP_MATRIX, stress_state

    def mk(*segments):
        """Fresh seeded walk per fixture — a shared stream would let one
        case's draws shift the next case's classification."""
        rng = random.Random(7)
        px, out = 100.0, []
        for n, sigma in segments:
            for _ in range(n):
                px *= math.exp(rng.gauss(0, sigma))
                out.append(px)
        return out

    assert stress_state([100.0] * 100) is None      # too short

    # quiet half-year after a normal stretch -> vol bottom-decile -> COMPLACENT
    assert stress_state(mk((500, 0.012), (500, 0.003)))["state"] == "COMPLACENT"

    # a violent 21-day stretch at the end -> 20d vol jumps >> 8 ann pts -> SHOCK
    # (21 not 30: the comparison window 41..21 days back must stay pre-shock)
    s = stress_state(mk((709, 0.006), (21, 0.05)))
    assert s["state"] == "SHOCK" and s["dv20"] >= 8

    # moderate crash then a month calming: vol z still high, 20d change <= 0
    a = stress_state(mk((650, 0.006), (50, 0.03), (30, 0.018)))
    assert a["state"] == "AFTERSHOCK" and a["vz"] >= 1 and a["dv20"] <= 0

    # every matrix cell carries the frozen fields
    for fs, row in DEEP_MATRIX.items():
        for ss, c in row.items():
            assert c["episodes"] > 0 and "fwd12m" in c and "fwd3m" in c


def test_margin_fast_includes_deep_block():
    from unittest.mock import patch
    from datetime import date, timedelta
    days = [date(2022, 1, 1) + timedelta(days=i) for i in range(1200)]
    closes = [100.0 * (1.0003 ** i) for i in range(1200)]  # gentle steady drift
    with patch("app.api.routes_margin_fast.fetch_bundle", return_value={}), \
         patch("app.api.routes_margin_fast.fetch_emini_leveraged",
               return_value=([], [])), \
         patch("app.api.routes_margin_fast.fetch_btc_perp", return_value=None), \
         patch("app.api.routes_margin_fast.fetch_funding_history",
               return_value=([], [])), \
         patch("app.api.routes_margin_fast._persist_oi_snapshot", return_value=[]), \
         patch("app.sources.fmp.fetch_spx_long", return_value=(days, closes)):
        r = margin_fast()
    d = r["deep"]
    assert d["live"] is not None and d["live"]["state"] in (
        "SHOCK", "AFTERSHOCK", "COMPLACENT", "NORMAL")
    assert d["baseline"]["fwd12m"]["pct_pos"] == 74
    assert d["matrix"]["COMPLACENT"]["BLOWOFF"]["fwd12m"]["pct_pos"] == 49


def test_fast_state_exact_boundaries():
    # thresholds are INCLUSIVE exactly as backtested (>= / <=); a >= -> >
    # regression must fail here (QA: old cases sat 0.5 units inside regions)
    assert fast_state(-2.0, -0.5, 8.0) == "FLUSH"      # dz4, vix20 at bounds
    assert fast_state(-2.0, -0.49, 8.0) == "CALM"
    assert fast_state(-1.0, 0.2, 0.0) == "WASHED_OUT"  # z, vix20 at bounds
    assert fast_state(-0.99, 0.2, 0.0) == "CALM"
    assert fast_state(1.0, 0.2, 4.0) == "RISK_BUILD"   # z, vix20 at bounds
    assert fast_state(1.0, 0.2, 4.01) == "CALM"


def test_frozen_constants_pinned():
    # transcription guards: QA round 2 caught DEEP_BASELINE fwd3m pasted from
    # the wrong (1929-unrestricted) study run. Pin the corrected values plus
    # the headline cells so any future re-freeze must consciously update these.
    from app.api.routes_margin_fast import (
        DEEP_BASELINE, DEEP_MATRIX, FAST_PLAYBOOK,
    )
    assert DEEP_BASELINE["fwd3m"] == {"median": 2.6, "pct_pos": 66, "worst": -41.8}
    assert DEEP_BASELINE["n"] == 3803
    assert DEEP_BASELINE["fwd12m"] == {"median": 10.3, "pct_pos": 74, "worst": -46.3}
    assert FAST_PLAYBOOK["FLUSH"]["stats"]["fwd1m"] == {
        "n": 5, "median": 7.4, "pct_pos": 100, "worst": 0.8}
    assert FAST_PLAYBOOK["WASHED_OUT"]["stats"]["fwd12m"] == {
        "n": 99, "median": 15.6, "pct_pos": 95, "worst": -12.5}
    assert FAST_PLAYBOOK["RISK_BUILD"]["stats"]["fwd12m"]["worst"] == -40.3
    assert DEEP_MATRIX["AFTERSHOCK"]["SQUEEZE"]["fwd12m"] == {
        "median": 22.7, "pct_pos": 89, "worst": -38.3}
    assert DEEP_MATRIX["COMPLACENT"]["BLOWOFF"]["fwd12m"]["pct_pos"] == 49
    assert DEEP_MATRIX["COMPLACENT"]["WASHOUT"]["fwd12m"]["pct_pos"] == 11
    assert DEEP_MATRIX["SHOCK"]["BLOWOFF"]["fwd3m"]["pct_pos"] == 100


def test_deribit_caches_are_independent(monkeypatch):
    # QA finding: a shared cache timestamp let every summary refresh mark the
    # funding history fresh, freezing the funding chart at process start.
    from app.sources import deribit
    calls = {"summary": 0, "funding": 0}

    class R:
        def __init__(self, j):
            self._j = j

        def raise_for_status(self):
            pass

        def json(self):
            return self._j

    def fake_get(url, params=None, timeout=None):
        if "book_summary" in url:
            calls["summary"] += 1
            return R({"result": [{"mark_price": 60000.0, "open_interest": 7e8,
                                  "funding_8h": 1e-5}]})
        calls["funding"] += 1
        return R({"result": [{"timestamp": int(params["end_timestamp"]) - 1000,
                              "interest_8h": 1e-5}]})

    monkeypatch.setattr(deribit, "httpx",
                        type("H", (), {"get": staticmethod(fake_get)}))
    deribit._scache.update({"ts": 0.0, "data": None})
    deribit._fcache.update({"ts": 0.0, "data": None})
    assert deribit.fetch_btc_perp() is not None       # summary cache now fresh
    d, v = deribit.fetch_funding_history(days=60)
    assert calls["funding"] >= 1 and d and v          # funding STILL fetched
    n = calls["funding"]
    deribit.fetch_funding_history(days=60)
    assert calls["funding"] == n                      # its own TTL now caches
