"""CLI (--help for every command; every command end-to-end offline on the
synthetic cache) and report writers."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from holygrail import report
from holygrail.cli import build_parser, main

COMMANDS = ["curve", "score", "backtest", "forward", "stress", "envs"]


@pytest.mark.parametrize("cmd", COMMANDS)
def test_help(cmd, capsys):
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args([cmd, "--help"])
    assert e.value.code == 0
    assert "usage" in capsys.readouterr().out


def test_curve_command(tmp_path, capsys):
    assert main(["curve", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "8.050%" in out and "4.648%" in out and "3.873" in out
    rows = json.loads((tmp_path / "dalio_curve.json").read_text())
    assert len(rows) == 6 * 20 and (tmp_path / "dalio_curve.png").stat().st_size > 1000
    assert (tmp_path / "neff_vs_rho.csv").exists()


def _common(tmp_path, offline_loader):
    return ["--cache-dir", str(offline_loader.cache_dir), "--offline", "--out", str(tmp_path / "o")]


def test_score_command_offline(tmp_path, test_book_yaml, offline_loader, capsys):
    assert main(["score", "--book", str(test_book_yaml), *_common(tmp_path, offline_loader)]) == 0
    assert "Holy Grail scorecard" in capsys.readouterr().out
    sc = json.loads((tmp_path / "o" / "scorecard.json").read_text())
    assert sc["view"] == "investable" and (tmp_path / "o" / "risk_vs_dollar.png").exists()


def test_backtest_command_offline(tmp_path, offline_loader, capsys):
    args = ["backtest", "--tickers", "EQA,BND,GLDX,CRYX", "--allocator", "erc", "--target-vol", "0.1",
            "--max-leverage", "2", "--benchmark", "EQA", *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "CAGR" in out and "IN-SAMPLE" in out
    bt = json.loads((tmp_path / "o" / "backtest.json").read_text())
    assert bt["rf"]["basis"] == "measured" and bt["metrics"]["n_periods"] > 500
    assert (tmp_path / "o" / "equity.png").exists() and (tmp_path / "o" / "drawdown.csv").exists()


def test_backtest_book_weights_offline(tmp_path, test_book_yaml, offline_loader, capsys):
    args = ["backtest", "--book", str(test_book_yaml), "--view", "investable", "--exclude-tags", "x",
            "--allocator", "book", "--rebalance", "Q", *_common(tmp_path, offline_loader)]
    # the book holds a parametric stream (LOAN): it has no history, so the backtest must refuse loudly
    assert main(args) == 2
    assert "parametric" in capsys.readouterr().err


def test_forward_command_offline(tmp_path, test_book_yaml, offline_loader, capsys):
    args = ["forward", "--book", str(test_book_yaml), "--paths", "500", "--years", "3", "--target-vol", "0.1",
            *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    assert "Forward MC" in capsys.readouterr().out
    f = json.loads((tmp_path / "o" / "forward.json").read_text())
    assert f["book_leverage"] > 0 and "LOAN" in f["labels"]
    args = ["forward", "--tickers", "EQA,BND,GLDX", "--method", "bootstrap", "--paths", "300", "--years", "2",
            *_common(tmp_path, offline_loader)]
    assert main(args) == 0


def test_stress_and_envs_commands_offline(tmp_path, test_book_yaml, offline_loader, capsys):
    args = ["stress", "--tickers", "EQA,BND,LATE", "--scenarios", "covid,inflation_2022,gfc", "--corr-rho", "0.8",
            *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "gfc: NOT RUN" in out and "covid" in out and "N_eff" in out  # LATE has no 2008 history
    # book mode: parametric LOAN has no history -> explicit --missing policy; composites kept in corr stress
    args = ["stress", "--book", str(test_book_yaml), "--scenarios", "covid", "--corr-rho", "0.5",
            *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "no history (parametric): ['LOAN']" in out and "covid: NOT RUN" in out and "LOAN" in out
    assert main(args + ["--missing", "cash"]) == 0
    out = capsys.readouterr().out
    assert "covid (2020-02-19..2020-03-23)" in out and "NOT modelled in this window" in out
    args = ["envs", "--tickers", "EQA,BND,GLDX", *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    assert (tmp_path / "o" / "environment_heatmap.png").exists()


def test_report_writers(tmp_path):
    idx = pd.bdate_range("2020-01-01", periods=300)
    rng = np.random.default_rng(0)
    a = pd.Series(np.cumprod(1 + rng.normal(0.0005, 0.01, 300)), index=idx)
    b = pd.Series(np.cumprod(1 + rng.normal(0.0003, 0.008, 300)), index=idx)
    f = report.equity_curves(tmp_path, {"a": a, "b": b})
    df = pd.read_csv(f["csv"])
    assert df["a"].iloc[0] == pytest.approx(1.0) and len(df) == 300
    d = report.drawdowns(tmp_path, {"a": a})
    assert pd.read_csv(d["csv"])["a"].max() <= 0
    rv = report.risk_vs_dollar(tmp_path, [{"stream": "x", "dollar_share": 0.6, "risk_share": 0.8},
                                          {"stream": "y", "dollar_share": 0.4, "risk_share": 0.2}])
    assert json.loads(Path(rv["json"]).read_text())[0]["stream"] == "x"
    qt = pd.DataFrame([{"stream": s, "quadrant": q, "ann_mean": v} for s in "ab"
                       for q, v in zip(["growth_up_inflation_up", "growth_down_inflation_down"], [0.1, -0.05])])
    assert report.environment_heatmap(tmp_path, qt)["png"].endswith(".png")
    bands = {"0.05": np.linspace(1, 0.9, 24), "0.5": np.linspace(1, 1.2, 24), "0.95": np.linspace(1, 1.5, 24)}
    ff = report.forward_fan(tmp_path, bands, 12)
    assert len(pd.read_csv(ff["csv"])) == 24
    p = report.write_json({"x": float("nan"), "t": pd.Timestamp("2024-01-02"), "a": np.arange(2)}, tmp_path / "j.json")
    assert json.loads(p.read_text()) == {"x": None, "t": "2024-01-02", "a": [0, 1]}
    assert "| a | b |" in report.markdown_table([{"a": 1.0, "b": None}], ["a", "b"], {"a": ".1f"})
