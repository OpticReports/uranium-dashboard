"""Portfolio Register lifecycle tests (against the real ingested store —
the register needs return history to evaluate candidates)."""
from __future__ import annotations

import pytest

from barbell import db


@pytest.mark.network
class TestRegistry:
    @pytest.fixture()
    def con(self, tmp_path, monkeypatch):
        # isolated register DB, but reading price data from the real store:
        # attach the real prices by copying the ingested store, keeping the
        # register tables empty
        import shutil
        if not db.DB_PATH.exists():
            pytest.skip("no ingested store")
        p = tmp_path / "reg.db"
        shutil.copy(db.DB_PATH, p)
        c = db.connect(p)
        c.execute("DELETE FROM portfolio_versions")
        c.execute("DELETE FROM portfolio_metrics")
        c.commit()
        return c

    def test_seed_and_live(self, con):
        from barbell.portfolio import registry
        live = registry.get_live(con)
        assert live["label"] == "v1.0" and live["status"] == "LIVE"
        assert abs(sum(live["weights"].values()) - 1.0) < 1e-9
        assert live["bot_frac"] == pytest.approx(0.20)

    def test_metrics_snapshot_and_cache(self, con):
        from barbell.portfolio import registry
        live = registry.get_live(con)
        m1 = registry.version_metrics(con, live, n_paths=2000)
        assert m1["cagr_realized"] is not None
        assert set(m1["constraints"]) == {"cvar5", "maxdd_p5", "max_position"}
        m2 = registry.version_metrics(con, live, n_paths=2000)  # cached
        assert m1["as_of"] == m2["as_of"]

    def test_propose_evaluate_promote_cycle(self, con):
        from barbell.portfolio import registry
        live = registry.get_live(con)
        w = dict(live["weights"])
        # shift 3pp from AVUV to KMLM
        w["AVUV"] = round(w["AVUV"] - 0.03, 4)
        w["KMLM"] = round(w["KMLM"] + 0.03, 4)
        cand = registry.propose_candidate(con, weights=w, rationale="test shift",
                                          n_paths=2000)
        assert cand["status"] == "CANDIDATE" and cand["label"] == "v1.1"
        assert cand["evidence"]["verdict"] in ("IMPROVED", "NO_CHANGE", "INCONCLUSIVE")
        # wrong confirmation refused
        with pytest.raises(ValueError, match="confirmation mismatch"):
            registry.promote(con, cand["id"], "v9.9")
        promoted = registry.promote(con, cand["id"], "v1.1")
        assert promoted["status"] == "LIVE"
        assert registry.get_live(con)["id"] == cand["id"]
        old = registry.get_version(con, live["id"])
        assert old["status"] == "RETIRED" and old["retired_at"]
        # ledger shows both with lineage
        led = registry.ledger(con)
        assert [r["label"] for r in led] == ["v1.0", "v1.1"]

    def test_bad_candidates_rejected(self, con):
        from barbell.portfolio import registry
        registry.get_live(con)
        with pytest.raises(ValueError, match="sum"):
            registry.propose_candidate(con, weights={"AVUV": 0.5}, rationale="x")
        with pytest.raises(ValueError, match="universe"):
            registry.propose_candidate(con, weights={"GME": 1.0}, rationale="x")
        with pytest.raises(ValueError, match="bot_frac"):
            registry.propose_candidate(con, bot_frac=1.5, rationale="x")
