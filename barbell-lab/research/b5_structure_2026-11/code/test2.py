"""Gate tests for the structure study. Run: python -m pytest -q test2.py (needs _cache/panel2.pkl from prep2.py)."""
import copy, os, pickle
import numpy as np, pandas as pd, pytest
import lib2 as L, run2 as RUN
from lib2 import C, E, IX, LIVE


@pytest.fixture(scope="module")
def panel():
    return L.load()


@pytest.fixture(scope="module")
def tape(panel):
    return L.build(panel, "T1")


def _truncate(p, end):
    q = copy.copy(p); end = pd.Timestamp(end)
    q["cal"] = p["cal"][p["cal"] <= end]; q["end"] = end
    for k in ("adj", "vol", "ret"):
        q[k] = p[k].loc[p[k].index <= end]
    q["fred"] = {k: v.loc[v.index <= end] for k, v in p["fred"].items()}
    return q


def test_live_book_reproduces_the_verified_series(panel):
    S = pickle.load(open(os.path.join(os.environ["B5_CACHE"], "series.pkl"), "rb"))
    for v in ("T1", "T2"):
        t = L.build(panel, v); assert np.abs(L.sim(t, L.path(t["cal"], LIVE)) - S[v]["live"]).max() == 0.0


@pytest.mark.parametrize("cut", ["2012-06-29", "2018-06-29", "2023-03-31"])
def test_p1_weights_use_no_future_data(panel, tape, cut):
    for mode, shrink in (("cov", .5), ("cov", 0.0), ("semi", .5)):
        full, _ = RUN.p1_changes(tape, mode, shrink); tr, _ = RUN.p1_changes(L.build(_truncate(panel, cut), "T1"), mode, shrink)
        assert len(tr) >= 3
        for (d1, w1), (d2, w2) in zip(full, tr):
            assert d1 == d2 and np.allclose(w1, w2, atol=1e-10)
        assert all(pd.Timestamp(d) <= pd.Timestamp(cut) for d, _ in tr)


def test_p1_respects_cap_and_keeps_tail(tape):
    for mode, shrink in (("cov", .5), ("cov", 0.0), ("semi", .5)):
        ch, _ = RUN.p1_changes(tape, mode, shrink)
        assert pd.Timestamp(ch[0][0]).year == 2009                     # 52 weeks of real KMLM-chain data first exist at year-end 2008
        for d, w in ch:
            assert abs(w.sum() - 1) < 1e-9 and w.max() <= .25 + 1e-6 and abs(w[IX["TAIL"]] - .059) < 1e-12 and w.min() >= 0


def test_erc_equalises_risk_and_caps():
    rng = np.random.default_rng(3); A = rng.normal(size=(400, 5)) * np.array([1, 2, .5, 1.5, 3]); cov = np.cov(A.T)
    w = L.erc(cov); rc = w * (cov @ w); rc /= rc.sum(); assert np.abs(rc - .2).max() < 1e-5 and abs(w.sum() - 1) < 1e-9
    w = L.erc(cov, cap=.30); rc = w * (cov @ w); free = w < .30 - 1e-9
    assert w.max() <= .30 + 1e-9 and abs(w.sum() - 1) < 1e-9 and w.min() > 0 and np.ptp(rc[free]) < 1e-6 * rc.sum()


def test_erc_handles_a_negatively_correlated_asset():
    """The case that broke the first solver (2008: trend negatively correlated with equity): the hedge must get a
    positive weight with an equal risk share, not be driven to zero."""
    v = np.array([.25, .18, .12]); corr = np.array([[1, .8, -.5], [.8, 1, -.4], [-.5, -.4, 1.0]]); cov = corr * np.outer(v, v)
    w = L.erc(cov); rc = w * (cov @ w); rc /= rc.sum()
    assert w.min() > .05 and np.abs(rc - 1 / 3).max() < 1e-5 and w[2] == w.max()


def test_gross_one_reproduces_the_unlevered_book(tape):
    ch, _ = RUN.p1_changes(tape); W = L.path(tape["cal"], LIVE, ch)
    assert np.abs(L.sim(tape, W) - L.sim(tape, W, spread=.015)).max() == 0.0     # no loan drawn -> no financing cost


def test_leverage_costs_the_analytic_drag(tape):
    """D14/D15: constant-gross leverage costs exactly the financing drag; an unmanaged loan drifts and costs more."""
    cal = tape["cal"]; c = tape["R"]["BIL"].values; i0 = int(cal.searchsorted(C.EXT0))
    rl = L.sim(tape, L.path(cal, LIVE)); w = LIVE * 1.2; w[-1] = -.2
    for s in (.005, .015):
        r = L.lever(rl, c, 1.2, s)
        sh_l = E.sharpe(rl[i0:] - c[i0:]); sh = E.sharpe(r[i0:] - c[i0:]); drag = .2 * s / (1.2 * rl[i0:].std() * np.sqrt(252))
        assert abs((sh_l - sh) - drag) < .005
        assert abs(r[i0:].std() / rl[i0:].std() - 1.2) < .01
        drift = L.sim(tape, L.path(cal, w), spread=s)
        assert E.sharpe(drift[i0:] - c[i0:]) < sh + 1e-9                      # the unmanaged loan is never better
    assert np.abs(L.lever(rl, c, 1.0, .015) - rl).max() == 0.0


def test_bootstrap_identity_draw_equals_direct():
    rng = np.random.default_rng(1); a = rng.normal(.0004, .01, (2100, 2)); b = rng.normal(.0003, .01, (2100, 2)); V = np.ones((2100, 2), np.bool_); V[:400, 1] = False
    dS, dO = L.boot2(a, b, V, np.arange(2100, dtype=np.int32)[None, :])
    assert dS[0, 0] == pytest.approx(E.sharpe(a[:, 0]) - E.sharpe(b[:, 0]), rel=1e-9)
    assert dO[0, 0] == pytest.approx(L.sortino(a[:, 0]) - L.sortino(b[:, 0]), rel=1e-9)
    assert dS[0, 1] == pytest.approx(E.sharpe(a[400:, 1]) - E.sharpe(b[400:, 1]), rel=1e-9)
    assert dO[0, 1] == pytest.approx(L.sortino(a[400:, 1]) - L.sortino(b[400:, 1]), rel=1e-9)


def test_no_arm_holds_an_instrument_before_it_exists(panel):
    t = L.build(panel, "T1"); cal = t["cal"]
    for col, d in t["first"].items():
        i = int(cal.searchsorted(d))
        assert (t["R"][col].values[:i] == 0).all()
    b0 = t["first"]["BTAL"]; W = L.path(cal, LIVE, [(b0, RUN.swap(TAIL=-.059, BTAL=.059))])
    assert W[:int(cal.searchsorted(b0)), IX["BTAL"]].max() == 0 and W[-1, IX["BTAL"]] == pytest.approx(.059)
