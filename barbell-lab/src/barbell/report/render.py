"""Report generators (markdown). Integrity rules enforced here:

* every report carries the config hash and data provenance line;
* every backtest report prints: cumulative trial count, DSR, PBO (or the
  explicit reason it doesn't apply), and Holm-corrected p-value;
* every research report ends with a VERDICT field: IMPROVED / NO_CHANGE /
  INCONCLUSIVE plus its statistical basis. "No improvement found" is a
  first-class outcome, not a failure.

Reports are written to REPORT_DIR (served read-only by the web layer) and
returned as strings for the CLI.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..config import REPORT_DIR, ensure_dirs

VERDICTS = ("IMPROVED", "NO_CHANGE", "INCONCLUSIVE")


def _write(name: str, text: str) -> Path:
    ensure_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"{stamp}-{name}.md"
    path.write_text(text)
    # also refresh a stable "latest" pointer per report family
    (REPORT_DIR / f"latest-{name}.md").write_text(text)
    return path


def _fmt_stats(stats: dict) -> str:
    rows = [
        ("period", f"{stats['start']} → {stats['end']} ({stats['n_days']} days)"),
        ("CAGR", f"{stats['cagr']:+.2%}"),
        ("ann. vol", f"{stats['ann_vol']:.2%}"),
        ("Sharpe (annualized)", f"{stats['sharpe_annual']:.2f}"),
        ("max drawdown", f"{stats['max_drawdown']:+.2%}"),
        ("CVaR 5% (overlapping annual windows)",
         f"{stats['cvar5_annual_overlapping']:+.2%}" if stats.get("cvar5_annual_overlapping") is not None else "n/a"),
        ("worst day", f"{stats['worst_day']:+.2%}"),
    ]
    return "\n".join(f"| {k} | {v} |" for k, v in rows)


def significance_section(sig: dict, pbo: dict | None, pbo_note: str = "") -> str:
    lines = [
        "## Statistical honesty block",
        "",
        f"- **Cumulative trials to date:** {sig['trial_count']}",
        f"- **Selection-bias hurdle SR0 (per-period):** {sig['sr0']:.4f}",
        f"- **Deflated Sharpe Ratio:** {sig['dsr']:.3f}",
        f"- **p-value (raw / Holm-corrected):** {sig['p_raw']:.4f} / {sig['p_holm']:.4f}",
    ]
    if pbo is not None:
        lines.append(
            f"- **PBO (CSCV, {pbo['n_splits']} splits{', sampled' if pbo['sampled'] else ''}):** "
            f"{pbo['pbo']:.2f} — IS-winner Sharpe {pbo['winner_is_sharpe_mean']:.3f} → "
            f"OOS {pbo['winner_oos_sharpe_mean']:.3f}"
        )
    else:
        lines.append(f"- **PBO:** n/a — {pbo_note}")
    return "\n".join(lines)


def backtest_report(title: str, config_hash: str, provenance: str, stats: dict,
                    sim, sig: dict, pbo: dict | None, pbo_note: str = "") -> str:
    text = f"""# {title}

*generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} — config `{config_hash}` — data: {provenance}*

| metric | value |
|---|---|
{_fmt_stats(stats)}
| turnover (× wealth / yr, incl. initial buy) | {sim.turnover:.2f} |
| rebalances | {sim.n_rebalances} |
| cost drag (CAGR vs zero-cost) | {sim.cost_drag_annual:.3%} |

{significance_section(sig, pbo, pbo_note)}

> All returns net of configured per-ticker spread costs. No zero-cost backtests.
"""
    _write("backtest", text)
    return text


def verdict_block(verdict: str, basis: str) -> str:
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    return f"\n## VERDICT: {verdict}\n\n{basis}\n"


def research_report(name: str, title: str, body: str, config_hash: str,
                    provenance: str, verdict: str, basis: str) -> str:
    text = f"""# {title}

*generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} — config `{config_hash}` — data: {provenance}*

{body}
{verdict_block(verdict, basis)}"""
    _write(name, text)
    return text
