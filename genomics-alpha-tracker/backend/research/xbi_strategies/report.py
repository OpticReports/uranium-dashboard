"""Render the results tables of docs/RESEARCH_XBI_STRATEGIES.md from
results.json between the RESULTS markers, so the doc never carries a
hand-typed number."""
from __future__ import annotations

import json
import re

from research.xbi_strategies.xbi_lib import BACKEND, HERE

DOC = BACKEND.parent / "docs" / "RESEARCH_XBI_STRATEGIES.md"
BEGIN, END = "<!-- RESULTS:BEGIN -->", "<!-- RESULTS:END -->"
ORDER = ["B0", "B1", "B2", "B3", "T1", "T2", "T3", "T4", "T5", "V1", "V2", "V3", "D1", "D2", "S1", "S2",
         "M1", "P1", "P2", "P3", "P4", "P5", "N1", "N2", "R1", "C1a", "C1b", "C1c", "C1d"]


def pct(x, d=1):
    return "—" if x is None else f"{x * 100:+.{d}f}%" if x < 0 or d else f"{x * 100:.{d}f}%"


def p(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def render(r: dict) -> str:
    v = r["variants"]
    lines = [f"_Window 2007-09-04 → {r['window_end']} unless the start column says later. Costs per PREREG.md. "
             f"Judge: max DD ≥ {r['judge']['dd_improvement_pp']*100:.0f} pp shallower than XBI on the same window, "
             f"CAGR within {r['judge']['cagr_giveup_pp']*100:.0f} pp, DD shallower in ≥ {r['judge']['subperiods_needed']} of 3 sub-periods._",
             "", "| id | rule | start | CAGR | max DD | Sharpe | Sortino | Calmar | underwater | worst yr | turnover/yr | pass |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for vid in ORDER:
        if vid not in v:
            continue
        x, f = v[vid], v[vid]["full"]
        j = x.get("judge", {})
        tag = "bench" if vid == "B0" else ("**PASS (post-hoc)**" if j.get("passes") and x.get("post_hoc")
                                            else "**PASS**" if j.get("passes") else "no")
        uw = f"{f['underwater_days']}d{'*' if f['underwater_open'] else ''}"
        wy = f"{f['worst_year']} {p(f['worst_year_ret'])}" if f.get("worst_year") else "—"
        note = x["note"].replace("POST-HOC: ", "")
        lines.append(f"| {vid} | {note} | {x['start'][:7]} | {pct(f['cagr'])} | {p(f['max_dd'])} | {f['sharpe']:.2f} | "
                     f"{f['sortino']:.2f} | {f['calmar']:.2f} | {uw} | {wy} | {x['turnover_py']:.1f}× | {tag} |")
    lines += ["", "_* still underwater at the window end. Post-hoc rows (C1x) were designed after the table above was read: in-sample selection, not evidence._", ""]
    # sub-periods for the rows that matter
    keys = list(r["subperiods"])
    lines += ["**Sub-periods (CAGR / max DD), the ride not the average:**", "",
              "| id | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
    for vid in ["B0", "B1", "B2", "R1", "D1", "S2", "V3", "T4", "C1a", "C1b", "C1c", "C1d"]:
        if vid not in v:
            continue
        cells = []
        for k in keys:
            s = v[vid]["subperiods"].get(k)
            cells.append(f"{pct(s['cagr'])} / {p(s['max_dd'])}" if s else "—")
        lines.append(f"| {vid} | " + " | ".join(cells) + " |")
    pm = r.get("param_maps", {})
    if pm:
        lines += ["", "**Parameter maps (full window):**", ""]
        for name, rows in pm.items():
            lines.append(f"- {name}: " + "; ".join(f"{k} → {pct(s['cagr'])} / DD {p(s['max_dd'])} / Sh {s['sharpe']:.2f}"
                                                  for k, s in rows.items()))
    return "\n".join(lines)


def main() -> None:
    r = json.loads((HERE / "results.json").read_text())
    body = render(r)
    text = DOC.read_text()
    new = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END), f"{BEGIN}\n{body}\n{END}", text, flags=re.S)
    DOC.write_text(new)
    print("rendered", DOC.relative_to(BACKEND.parent))


if __name__ == "__main__":
    main()
