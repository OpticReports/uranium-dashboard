"""GET /labor/sahm — Sahm-Rule time series + NBER bands for the labor chart."""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.labor import _sahm_from_unrate
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["labor"])

SAHM_TRIGGER = 0.50


@router.get("/labor/sahm")
def sahm_series():
    bundle = fetch_bundle()
    sd, sv = bundle.get("sahm", ([], []))
    if not any(v is not None for v in sv):        # fall back to computing from UNRATE
        ud, uv = bundle.get("unrate", ([], []))
        sd, sv = _sahm_from_unrate(ud, uv)
        source = "computed from FRED:UNRATE"
    else:
        source = "FRED:SAHMREALTIME"

    series = [{"date": d.isoformat(), "value": v} for d, v in zip(sd, sv) if v is not None]
    latest = series[-1]["value"] if series else None

    # NBER recession bands
    rd, rv = bundle.get("recession", ([], []))
    bands, run_start, prev = [], None, 0.0
    for d, v in zip(rd, rv):
        cur = v or 0.0
        if cur == 1.0 and prev != 1.0:
            run_start = d
        if cur != 1.0 and prev == 1.0 and run_start:
            bands.append({"start": run_start.isoformat(), "end": d.isoformat()})
            run_start = None
        prev = cur
    if run_start and rd:
        bands.append({"start": run_start.isoformat(), "end": rd[-1].isoformat()})

    step = max(1, len(series) // 3000)
    return {
        "series": series[::step], "recessions": bands, "trigger": SAHM_TRIGGER,
        "current": latest, "triggered": (latest is not None and latest >= SAHM_TRIGGER),
        "source": source,
        "note": "Sahm gap = 3mo-avg unemployment minus its 12mo low. On current-vintage data "
                ">=0.50 lit within 3 months of the start of 5 of 7 recessions since 1972 "
                "(late in 1973 and 1981), and also in 2003 and Jul-2024 without one "
                "(studies/labor-stress-board.md).",
    }


# ── Labor Stress Board (studies/labor-stress-board.md) ───────────────────────
# Series fetched on their own long histories (the shared bundle starts 1976):
# SOS needs 78 weeks of warm-up and the strip's percentiles use full history.
BOARD_SERIES = {
    # rule inputs
    "iursa": "IURSA", "ccnsa": "CCNSA", "covemp": "COVEMP",
    "job_losers": "LNS13023621", "clf": "CLF16OV", "epop_prime": "LNS12300060",
    "lfpr_prime": "LNS11300060", "pop_prime": "LNU00000060", "unemploy": "UNEMPLOY",
    "unrate": "UNRATE", "sahm": "SAHMREALTIME",
    # strip-only
    "u6": "U6RATE", "nilfwjn": "NILFWJN", "nei": "NEIM156SFRBRIC",
    "ue_flow": "LNS17100000", "jolts_hires": "JTSHIR", "jolts_quits": "JTSQUR",
    "jolts_layoffs": "JTSLDR", "lt_share": "LNS13025703", "lt_level": "UEMP27OV",
    "med_dur": "UEMPMED", "hours": "AWHNONAG", "fb_lfpr": "LNU01373395",
    "nb_lfpr": "LNU01373413",
}
BOARD_START = "1967-01-01"
BOARD_CHART_MONTHS = 180


def _board_series() -> dict:
    from concurrent.futures import ThreadPoolExecutor

    from ..sources.fred import fetch_series
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {k: ex.submit(fetch_series, sid, BOARD_START)
                for k, sid in BOARD_SERIES.items()}
        return {k: f.result() for k, f in futs.items()}


# Frozen backtest record (studies/labor-stress-board.md RESULTS, one
# pre-registered run; gated against labor_stress/results.json in tests).
BOARD_RECORD = {
    "hits": 5, "peaks": 7, "false_alarms_1972_2020": 0,
    "sahm_false_alarms_1972_2020": 1, "paired_timing_vs_sahm": -2,
    "fired_2024": "2024-08", "red_gate": "fail",
    "hits_ex2020": 4, "best_single": {"id": "A2", "hits": 6, "false_alarms_1972_2020": 0,
                                      "fired_2024": "2024-08"},
    "text": ("In-sample backtest (thresholds set with this history in view): since 1972 "
             "the Board flagged 5 of 7 recessions (4 of 6 excluding 2020) between 3 "
             "months before and 1 month after they began — typically 1 month after — "
             "a median 2 months before the Sahm rule where both caught one. It was "
             "late for 1973 and 1981. It never started an alert without a recession "
             "nearby 1972-2020 — but it did in Aug 2024, with no recession. Job losers "
             "alone, one of its six rules, did as well (6 of 7, same Aug-2024 misfire). "
             "A confirmation signal, not an early warning."),
}
LEDGER_FROM = (2026, 9)     # out-of-sample begins with this data month (spec v1 A1)


def board_payload(series: dict, *, sahm_from: str = "series") -> dict:
    """Pure: raw FRED observations -> the panel payload (testable offline).
    Evaluated on the monthly jobs-report grid: the Board's month is the last
    month the slack leg is observed (weekly legs map to that grid, spec A6).
    A rule with no value for that month is MISSING, never counted as unlit:
    the state is then INCOMPLETE, not CLEAR (a missing rule can only lower
    the count, so an ALERT on the rules present stands)."""
    from ..metrics import labor_stress as L
    c1_source = "SAHMREALTIME" if sahm_from == "series" else "UNRATE (current vintage)"
    if sahm_from == "series" and not any(v is not None for v in series.get("sahm", ([], []))[1]):
        sahm_from, c1_source = "unrate", "UNRATE (SAHMREALTIME unavailable)"
    vals = L.rule_values(series, sahm_from=sahm_from)
    lit = L.lit(vals)
    states = L.board(lit)
    grid = sorted(k for k in states if k in vals.get("C1", {}))
    months = grid[-BOARD_CHART_MONTHS:]
    last = months[-1] if months else None
    missing = [rid for rid in L.RULES if last is None or last not in vals.get(rid, {})]
    rules = []
    for rid, spec in L.RULES.items():
        v = vals.get(rid, {})
        k = last if last in v else (max(v) if v else None)
        rules.append({
            "id": rid, "leg": spec["leg"], "label": spec["label"],
            "threshold": spec["threshold"], "unit": spec["unit"],
            "watch": spec.get("watch"),
            "value": v[k] if k else None,
            "month": L.ym_str(k) if k else None,
            "stale": k is not None and k != last,          # shown, never counted
            "lit": lit[rid].get(last) if last in v else None,
            "ratio": round(v[k] / spec["threshold"], 3) if k else None,
        })
    history = []
    for k in months:
        row = {"month": L.ym_str(k), "state": states[k]}
        for rid, spec in L.RULES.items():
            x = vals.get(rid, {}).get(k)
            row[rid] = round(x / spec["threshold"], 3) if x is not None else None
        history.append(row)
    # Out-of-sample ledger (spec v1 A1), recomputed on current data: ALERT
    # onsets (>= 6 non-ALERT months first) and each rule's onsets (>= 6
    # observed unlit months first). The first-sight record is persisted by
    # board_ledger_events -> EventLog, so R2 scores what was seen at the time.
    ledger, quiet = [], 0
    for k in grid:
        if states[k] == "ALERT":
            if quiet >= 6 and k >= LEDGER_FROM:
                ledger.append({"month": L.ym_str(k), "kind": "ALERT", "event": "ALERT onset"})
            quiet = 0
        else:
            quiet += 1
    for rid, spec in L.RULES.items():
        for k in L.onsets(lit[rid]):
            if k >= LEDGER_FROM:
                ledger.append({"month": L.ym_str(k), "kind": rid,
                               "event": f"{rid} onset", "value": vals[rid][k]})
    ledger.sort(key=lambda r: (r["month"], r["kind"]))
    if last is None:
        state = None
    elif states[last] == "ALERT":
        state = "ALERT"
    else:
        state = "INCOMPLETE" if missing else "CLEAR"
    strip = L.strip(series)
    return {
        "state": state,
        "n_lit": sum(1 for r in rules if r["lit"]), "n_rules": len(rules),
        "n_evaluated": len(rules) - len(missing), "missing": missing,
        "c1_source": c1_source,
        "month": L.ym_str(last) if last else None,
        "rules": rules, "history": history, "strip": strip,
        "strip_verdict": L.strip_verdict(strip),
        "record": BOARD_RECORD, "ledger": ledger,
        "ledger_from": L.ym_str(LEDGER_FROM),
        "note": ("ALERT = a layoff rule (A) AND a slack rule (B/C) lit in the same "
                 "month. Any single rule was lit in 40% of months since 2021 (32% in "
                 "1972-2020), above the spec's 33% ceiling, so the panel shows a count, "
                 "not a WATCH state. The Board answers 'is a layoff-driven downturn "
                 "confirmed?'; the strip answers 'is the headline rate too good?' — "
                 "they can disagree."),
    }


def _rule_reading(r: dict) -> str:
    u = "%" if r["unit"] == "%" else "pp"
    return f"{r['id']} {r['label']} {r['value']:+.2f}{u} (line {r['threshold']:g})"


def board_alert_event(payload: dict, today):
    """A WARN event when the latest month starts a new ALERT episode."""
    from ..scoring.events import Event
    if not payload.get("history") or payload.get("state") != "ALERT":
        return None
    hist = payload["history"]
    prior = [h["state"] for h in hist[-7:-1]]
    if len(prior) < 6 or any(p == "ALERT" for p in prior):
        return None
    lit = "; ".join(_rule_reading(r) for r in payload["rules"]
                    if r["lit"] and not r.get("stale"))
    return Event(
        event_type="labor_board_alert", severity="WARN", asof=today,
        dedup_key=f"labor_board:{payload['month']}",
        rationale=(f"Labor Stress Board ALERT for {payload['month']}: a layoff rule and a "
                   f"slack rule are lit together ({lit}). {BOARD_RECORD['text']}"),
        detail={"month": payload["month"], "n_lit": payload["n_lit"]})


def board_ledger_events(payload: dict, today) -> list:
    """INFO events that persist each out-of-sample onset the first time it is
    seen (EventLog is idempotent per dedup_key, so a later refresh — or a
    January CPS revision that moves the onset — never rewrites the first
    sighting; a revision that creates a new onset is logged with its own,
    later first_seen date). INFO never pages."""
    from ..scoring.events import Event
    out = []
    for row in payload.get("ledger", []):
        v = row.get("value")
        out.append(Event(
            event_type="labor_board_onset", severity="INFO", asof=today,
            dedup_key=f"{row['kind']}:{row['month']}",
            rationale=(f"Labor Stress Board out-of-sample ledger: {row['event']} in data "
                       f"month {row['month']}"
                       + (f" (value {v:+.3f})" if v is not None else "")
                       + f", first seen {today.isoformat()}."),
            detail={**row, "first_seen": today.isoformat(),
                    "board_month": payload.get("month")}))
    return out


@router.get("/labor/board")
def labor_board():
    return board_payload(_board_series())
