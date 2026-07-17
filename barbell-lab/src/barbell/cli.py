"""Barbell Lab CLI (typer). CLI-first per spec — the web layer only reads
what these commands produce.

    barbell ingest            # fetch + validate + acceptance gates + snapshot
    barbell acceptance        # re-run the hard gates on stored data
    barbell import-bot        # pull the bot's P&L from its SQLite
    barbell backtest ...      # walk-forward run (registers a trial)
    barbell question1 ...     # tail-sleeve adjudication
    barbell question2 ...     # rebalancing bonus
    barbell optimize ...      # geo-CAGR/CVaR optimizer + HRP/NCO cross-checks
    barbell monitor ...       # rebalance bands / regime / triggers
"""
from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

import typer
from rich.console import Console

from . import db
from .config import ROOT, ensure_dirs

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs full request URLs at INFO — which can include apikey/token query
# params. Keep it at WARNING so secrets never land in stdout/host logs.
logging.getLogger("httpx").setLevel(logging.WARNING)


def _load_dotenv() -> None:
    """Tiny .env loader (KEY=VALUE lines); never overrides real env vars."""
    for candidate in (ROOT / ".env", Path.cwd() / ".env"):
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break


@app.callback()
def _init() -> None:
    _load_dotenv()
    ensure_dirs()


@app.command()
def ingest(
    end: str = typer.Option(date.today().isoformat(), help="last date to fetch"),
    no_gate: bool = typer.Option(False, "--no-gate", help="skip acceptance gates (data spelunking only — results remain untrusted)"),
) -> None:
    """Fetch prices + FRED, run the validation suite and acceptance gates."""
    from .ingest.runner import full_ingest
    con = db.connect()
    report = full_ingest(con, end, gate=not no_gate)
    for r in report.results:
        console.print(str(r))
    console.print("[green]ingest complete — validation passed[/green]"
                  + ("" if no_gate else " [green]and acceptance gates passed[/green]"))


@app.command()
def acceptance() -> None:
    """Re-run the four hard acceptance gates against stored data."""
    from .validate.acceptance import run_gates
    con = db.connect()
    gates = run_gates(con)
    for g in gates:
        console.print(str(g))
    if not all(g.passed for g in gates):
        raise typer.Exit(code=1)


@app.command("import-bot")
def import_bot(bot_db: str = typer.Option(None, help="override bot sqlite path")) -> None:
    """Import the short-vol bot's realized/unrealized P&L series."""
    from .ingest.bot import import_bot_pnl
    con = db.connect()
    n = import_bot_pnl(con, bot_db)
    console.print(f"[green]imported {n} bot P&L rows[/green]")


@app.command()
def provenance() -> None:
    """Print the provenance summary (live vs proxy rows) for every ticker."""
    from .config import load
    from .ingest.series import total_return_series
    con = db.connect()
    for t in load("data")["tickers"]:
        console.print(total_return_series(con, t).provenance_summary())


@app.command()
def backtest(
    mode: str = typer.Option("threshold", help="threshold | calendar | none"),
    spliced: bool = typer.Option(True, help="use proxy-extended history"),
    tail: str = typer.Option("TAIL", help="tail-sleeve instrument (TAIL/CAOS/BTAL/NONE)"),
) -> None:
    """Walk-forward backtest of the current target weights. Registers a trial;
    prints trial count, DSR, PBO context and corrected p-value."""
    from .backtest.engine import run_and_report
    con = db.connect()
    console.print(run_and_report(con, mode=mode, spliced=spliced, tail=tail))


@app.command()
def question1(
    kill_switch: str = typer.Option("all", help="perfect | lag1 | fails | all"),
    bot_model: bool = typer.Option(False, "--bot-model", help="EXPLICITLY allow the parameterized bot model where real P&L history is thin"),
) -> None:
    """Q1: does a 5% tail sleeve (TAIL/CAOS/BTAL/none/splits) raise the combined
    book's 5th percentile enough to justify carry, given kill-switch behavior?"""
    from .portfolio.questions import answer_question1
    con = db.connect()
    console.print(answer_question1(con, kill_switch=kill_switch, allow_bot_model=bot_model))


@app.command()
def question2() -> None:
    """Q2: realized rebalancing bonus — threshold vs calendar vs buy-and-hold."""
    from .portfolio.questions import answer_question2
    con = db.connect()
    console.print(answer_question2(con))


@app.command()
def optimize(
    method: str = typer.Option("geocagr", help="geocagr | hrp | nco | all"),
    paths: int = typer.Option(20000, help="Monte Carlo paths (>=20000 per spec)"),
) -> None:
    """Optimizer suite; flags material disagreement between methods."""
    from .portfolio.optimizers import run_optimizers
    con = db.connect()
    console.print(run_optimizers(con, method=method, n_paths=paths))


@app.command()
def book(
    bot_frac: float = typer.Option(0.20, help="bot capital fraction in [0,1); 0 = sleeve only"),
    sweep: bool = typer.Option(False, "--sweep", help="sweep fractions and find the growth-optimal admissible split"),
    tail: str = typer.Option("TAIL", help="tail-sleeve instrument"),
    kill_switch: str = typer.Option("perfect", help="perfect | lag1 | fails"),
    bot_model: bool = typer.Option(False, "--bot-model", help="EXPLICITLY allow the parameterized bot model"),
    paths: int = typer.Option(20000, help="MC paths"),
) -> None:
    """The book, decoupled from 80/20: sleeve in isolation, bot toggled at any
    fraction, or a full fraction sweep under the hard constraints."""
    from .portfolio.book import book_frame, evaluate_fraction, sweep_bot_fraction
    from .config import load
    con = db.connect()
    if sweep:
        console.print(sweep_bot_fraction(con, tail=tail, allow_bot_model=bot_model,
                                         kill_switch=kill_switch, n_paths=paths))
    else:
        mc = load("backtest")["monte_carlo"]
        joint = book_frame(con, bot_frac, tail=tail, allow_bot_model=bot_model,
                           kill_switch=kill_switch)
        r = evaluate_fraction(joint, bot_frac, paths, int(mc["block_len_days"]),
                              int(mc["seed"]))
        for k, v in r.items():
            console.print(f"{k}: {v:+.2%}" if isinstance(v, float) and k != "bot_frac"
                          else f"{k}: {v}")


@app.command()
def analyze(
    tail: str = typer.Option("TAIL", help="tail-sleeve instrument"),
    bot_frac: float = typer.Option(0.0, help="bot overlay fraction; 0 = sleeve only"),
    bot_model: bool = typer.Option(False, "--bot-model", help="allow parameterized bot model"),
) -> None:
    """Fund-grade tearsheet: drawdown anatomy, correlations, risk contributions,
    crisis-episode stress table."""
    from .portfolio.tearsheet import build_tearsheet
    con = db.connect()
    console.print(build_tearsheet(con, tail=tail, bot_frac=bot_frac,
                                  allow_bot_model=bot_model))


@app.command()
def chat() -> None:
    """Interactive grounded quant analyst (Claude with platform tools)."""
    from .chat.agent import answer
    console.print("[bold]Barbell Lab analyst[/bold] — grounded in the platform's own "
                  "data. Ctrl-D to exit.")
    history: list[dict] = []
    while True:
        try:
            q = console.input("[cyan]you>[/cyan] ")
        except (EOFError, KeyboardInterrupt):
            break
        if not q.strip():
            continue
        history.append({"role": "user", "content": q})
        res = answer(history)
        for t in res["tool_trace"]:
            console.print(f"[dim]  ⚙ {t['tool']}({t['input']})[/dim]")
        console.print(res["text"])
        history.append({"role": "assistant", "content": res["text"]})


@app.command()
def walkforward(
    tail: str = typer.Option("TAIL", help="tail-sleeve instrument for both arms"),
    engine: str = typer.Option("bootstrap", help="scenario engine for refits: bootstrap | mvt"),
    paths: int = typer.Option(20000, help="MC paths per refit (>=20000 per spec)"),
) -> None:
    """M5: 'beat the benchmark' — optimizer refit yearly vs current targets,
    out-of-sample, costs paid, corrected stats, verdict."""
    from .portfolio.evaluation import walkforward_eval
    con = db.connect()
    console.print(walkforward_eval(con, tail=tail, n_paths=paths, engine=engine))


@app.command()
def monitor(
    what: str = typer.Argument("all", help="rebalance | regime | triggers | all"),
) -> None:
    """Nightly monitors: rebalance bands, regime dashboard, trigger rules."""
    from .monitor.run import run_monitors
    con = db.connect()
    console.print(run_monitors(con, what))


@app.command()
def trials() -> None:
    """Show the cumulative trial registry (the multiple-testing denominator)."""
    from .stats.trials import trial_summary
    con = db.connect()
    console.print(trial_summary(con))


if __name__ == "__main__":
    app()
