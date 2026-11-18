"""Gate tests for the B.5 overlay study. Run: python -m pytest -q test_engine.py  (needs _cache/panel.pkl from prep.py)"""
import copy
import numpy as np, pandas as pd, pytest
import common as C, arms as A, engine as E

NOMASK = np.zeros(8, bool)


@pytest.fixture(scope="module")
def panel():
    return C.load_panel()


def _truncate(p, end):
    q = copy.copy(p); end = pd.Timestamp(end)
    q["cal"] = p["cal"][p["cal"] <= end]; q["end"] = end
    for k in ("adj", "vol", "ret"):
        q[k] = p[k].loc[p[k].index <= end]
    q["fred"] = {k: v.loc[v.index <= end] for k, v in p["fred"].items()}
    q["cape"] = p["cape"].loc[p["cape"].index <= end]
    return q


def _base_nav(tape):
    R = np.ascontiguousarray(tape["R"].values); T = len(R)
    r = E.simulate(R, np.repeat(C.BASE[None, :], T, 0), C.COST, tape["me"], C.BAND, C.CAL_DAYS, 1e-9, True, NOMASK, 0.0, 0, T)[0]
    return pd.Series(np.cumprod(1 + r), index=tape["cal"])


def _reference_static(R, w, cost, me, band, cal_days):
    """Independent, deliberately naive re-implementation of the live rule for a static book."""
    T, N = R.shape; h = w * (1 - (cost * w).sum()); out = np.empty(T); prev = 1.0; pending = False; since = 0
    for t in range(T):
        h = h * (1 + R[t]); tot = h.sum(); since += 1
        if t > 0 and pending:
            tr = np.abs(w * tot - h); tot = tot - (cost * tr).sum(); h = w * tot; since = 0
        pending = False
        if me[t]:
            cur = h / tot
            pending = bool(since >= cal_days or (np.abs(cur[w > .005] / w[w > .005] - 1) > band).any())
        out[t] = tot / prev - 1; prev = tot
    return out


def test_static_engine_matches_reference(panel):
    tape = C.build_tape(panel, "T1"); R = np.ascontiguousarray(tape["R"].values); T = len(R)
    a = E.simulate(R, np.repeat(C.BASE[None, :], T, 0), C.COST, tape["me"], C.BAND, C.CAL_DAYS, 1e-9, True, NOMASK, 0.0, 0, T)[0]
    b = _reference_static(R, C.BASE, C.COST, tape["me"], C.BAND, C.CAL_DAYS)
    assert np.abs(a - b).max() < 1e-12


@pytest.mark.parametrize("cut", ["2012-06-29", "2019-03-15", "2022-10-31"])
def test_no_lookahead_in_any_arm(panel, cut):
    """Decisions up to the cut date must be identical whether or not later data exists (every one of the 53 arms
    and its mirror). The last 2 rows are excluded only for the month-end flag, which needs the next row to exist."""
    full = C.build_tape(panel, "T1"); arms_full, _ = A.build(panel, full, _base_nav(full))
    q = _truncate(panel, cut); tr = C.build_tape(q, "T1"); arms_tr, _ = A.build(q, tr, _base_nav(tr))
    n = len(tr["cal"]) - 2
    assert (full["cal"][:n + 2] == tr["cal"]).all()
    bad = [k for k in arms_full if not np.allclose(arms_full[k]["mult"][:n], arms_tr[k]["mult"][:n], atol=1e-12)
           or not np.allclose(arms_full[k]["mirror"][:n], arms_tr[k]["mirror"][:n], atol=1e-12)]
    assert bad == []


def test_tail_model_is_the_only_lookahead_and_only_in_T2(panel):
    """T2's modelled TAIL is fitted on 2017+ by design (D1); T1 must not change before 2017 when later data is cut."""
    q = _truncate(panel, "2016-12-30")
    a = C.build_tape(panel, "T1")["R"].loc[:"2016-12-30"]; b = C.build_tape(q, "T1")["R"]
    assert np.allclose(a.values, b.values)


def test_lag_and_weights():
    m = np.ones((5, 7)); m[2:, 0] = 0
    W = A.weights(m); assert np.allclose(W.sum(1), 1) and abs(W[3, -1] - C.BASE[0]) < 1e-12
    Wl = A.lagged(W, 1); assert np.allclose(Wl[3], W[2]) and np.allclose(Wl[2], W[1]) and np.allclose(Wl[0], W[0])


def test_signal_trade_is_next_close_and_partial():
    """Leg 0 jumps +10% on day 3. A decision made on day 2 (lagged to row 3) must still earn that jump;
    a decision made on day 3 must not avoid it; only the signalled leg trades and cost is charged on it."""
    T = 6; R = np.zeros((T, 3)); R[3, 0] = .10
    cost = np.array([.001, .001, 0.0]); me = np.zeros(T, bool); base = np.array([.5, .5, 0.0])
    dec = np.repeat(base[None, :], T, 0); dec[2:] = [0.0, .5, .5]            # decide at close of day 2: leg 0 off
    out, turn, cst, trig, _ = E.simulate(R, A.lagged(dec, 1), cost, me, .2, 252, 1e-9, True, np.zeros(3, bool), 0.0, 0, T)
    assert trig[3] == 2 and trig[2] == 0                                    # trades at the close of day 3
    assert out[3] == pytest.approx(.05, abs=1e-3)                           # earned the jump (less the sale cost)
    nav3 = (1 - .001) * 1.05
    assert cst[3] == pytest.approx(.001 * (.5 * (1 - .001) * 1.10) / nav3, rel=1e-9)   # cost on the leg sold only
    assert turn[3] == pytest.approx(2 * (.5 * (1 - .001) * 1.10) / nav3, rel=1e-9)     # leg sold + cash bought
    out0 = E.simulate(R, A.lagged(dec, 0), cost, me, .2, 252, 1e-9, True, np.zeros(3, bool), 0.0, 0, T)[0]
    assert out0[3] == pytest.approx(0.0, abs=2e-3)                          # same-close variant sells before the jump


def test_bootstrap_identity_draw_equals_direct():
    rng = np.random.default_rng(1); a = rng.normal(.0004, .01, (900, 2)); b = rng.normal(.0003, .01, (900, 2))
    idx = np.arange(900, dtype=np.int32)[None, :]
    dS, dM, dD, dU = E.boot_pairs(a, b, idx)
    for k in range(2):
        assert dS[0, k] == pytest.approx(E.sharpe(a[:, k]) - E.sharpe(b[:, k]), rel=1e-9)
        assert dD[0, k] == pytest.approx(E.maxdd(a[:, k]) - E.maxdd(b[:, k]), rel=1e-9)
        assert dM[0, k] == pytest.approx((a[:, k].mean() - b[:, k].mean()) * 252, rel=1e-9)


def test_placebo_preserves_target_weights(panel):
    tape = C.build_tape(panel, "T1"); R = np.ascontiguousarray(tape["R"].values); T = len(R)
    arms, _ = A.build(panel, tape, _base_nav(tape)); W = A.lagged(A.weights(arms["A2"]["mult"]), 1)
    i0 = int(tape["cal"].searchsorted(C.EXT0)); n = T - i0
    for off in (63, 1000, n - 63):
        rolled = np.roll(W[i0:], -off, axis=0)
        assert np.allclose(rolled.mean(0), W[i0:].mean(0))
    pl = E.placebo_shift(R, np.ascontiguousarray(W[i0:]), C.BASE.copy(), C.COST, tape["me"], C.BAND, C.CAL_DAYS, 1e-9, True,
                         NOMASK, 0.0, i0, T, np.array([n], dtype=np.int64), R[:, -1].copy())
    Wz = W.copy(); Wz[:i0] = C.BASE
    r = E.simulate(R, Wz, C.COST, tape["me"], C.BAND, C.CAL_DAYS, 1e-9, True, NOMASK, 0.0, i0, T)[0]
    assert pl[0, 1] == pytest.approx(E.maxdd(r[i0:]), rel=1e-9)             # a full-cycle shift is the arm itself


def test_weights_and_arm_count(panel):
    tape = C.build_tape(panel, "T1"); arms, _ = A.build(panel, tape, _base_nav(tape))
    assert len(arms) == 53 and sum(a["primary"] for a in arms.values()) == 8
    for a in arms.values():
        for m in (a["mult"], a["mirror"]):
            W = A.weights(m); assert np.allclose(W.sum(1), 1) and W.min() >= 0 and np.isfinite(W).all()
