"""Distress panel (studies/distress-signals.md): national bankruptcy filings,
bank loan stress and the state map, each labelled by its measured role.

Nothing here alerts. No series passed the pre-registered test as a recession
warning; the record (role labels, per-recession outcomes) is frozen in
sources/distress_history.json from the study's results.json and is never
recomputed live. The live readings use the study's own rules - growth of the
4-quarter sum (filings) or 4-quarter average (bank rates) vs a year earlier,
on at >= 10%, masks applied to the whole 8-quarter input footprint, a masked
block resetting the 4-quarter quiet run - so the panel shows exactly what the
study scored (gate tests: tests/test_distress.py).
"""
from __future__ import annotations

from datetime import date

THETA = 0.10
QUIET = 4


def qidx(s: str) -> int:
    return 4 * int(s[:4]) + int(s[5]) - 1


def qstr(i: int) -> str:
    return f"{i // 4}Q{i % 4 + 1}"


def _masked(i: int, raws: list[tuple[int, int]]) -> bool:
    return any(a <= i <= b for a, b in raws)


def rule_path(values: dict[int, float], raws: list[tuple[int, int]], theta: float = THETA,
              floor: float | None = None) -> list[dict]:
    """Per quarter: g = sum(t-3..t)/sum(t-7..t-4) - 1 (equivalently the ratio of
    4-quarter averages), d = change in the 4-quarter average, on = g >= theta
    (and d >= floor when a floor is given); None where not computable or any
    of the 8 input quarters is masked."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    out = []
    for t in range(lo, hi + 1):
        fp = range(t - 7, t + 1)
        g = d = on = None
        if all(k in values for k in fp) and not any(_masked(k, raws) for k in fp):
            a1 = sum(values[k] for k in range(t - 3, t + 1))
            a0 = sum(values[k] for k in range(t - 7, t - 3))
            g, d = a1 / a0 - 1, (a1 - a0) / 4
            on = g >= theta and (floor is None or d >= floor)
        out.append({"q": t, "g": g, "d": d, "on": on})
    return out


def onsets(path: list[dict], quiet: int = QUIET) -> list[int]:
    """Quarter indices of onsets: first ON after >= `quiet` observed OFF
    quarters; a masked/uncomputable quarter resets the count (SPEC v1)."""
    out, off = [], 0
    for p in path:
        if p["on"] is None:
            off = 0
        elif p["on"]:
            if off >= quiet:
                out.append(p["q"])
            off = 0
        else:
            off += 1
    return out


def _state(path: list[dict]) -> dict:
    """Latest computable reading and whether it is a fresh onset."""
    comp = [p for p in path if p["on"] is not None]
    if not comp:
        return {"asof": None, "g": None, "on": None, "onset_quarters": []}
    last = comp[-1]
    ons = onsets(path)
    return {"asof": qstr(last["q"]), "g": round(last["g"], 4), "on": bool(last["on"]),
            "fresh_onset": bool(ons and ons[-1] == last["q"]),
            "onset_quarters": [qstr(o) for o in ons]}


def _pop_k(hist: dict, year: float, state: str | None = None) -> float:
    """Population (thousands) of the 50 states + DC, or of one state, at a
    fractional year. Census July-1 estimates sit at year + 0.5: linear between
    them, extrapolated at the last year's growth rate (the study's load.pop_at)."""
    src = hist["us_pop_k"] if state is None else hist["state_pop_k"][state]
    pop = {int(y): v for y, v in src.items()}
    y0 = int(year - 0.5)
    if y0 in pop and y0 + 1 in pop:
        w = year - 0.5 - y0
        return pop[y0] * (1 - w) + pop[y0 + 1] * w
    ys = sorted(pop)
    last, prev = ys[-1], ys[-2]
    return pop[last] * (pop[last] / pop[prev]) ** (year - 0.5 - last)


def merge_live(hist: dict, live: dict[str, dict]) -> dict:
    """Fold quarters published since the frozen history into copies of its
    national and state series. live: uscourts_f2.new_quarters() output."""
    nb = {qidx(k): v for k, v in hist["national_nonbusiness_q"].items()}
    bus = {qidx(k): v for k, v in hist["national_business_q"].items()}
    ch11 = {qidx(k): v for k, v in hist["national_bus_ch11_q"].items()}
    nb12 = {qidx(k): v for k, v in hist["national_nonbusiness_12m"].items()}
    st12 = {qidx(k): v for k, v in hist["state_12m"].items()}
    for k, tabs in sorted(live.items()):
        t = qidx(k)
        n3, n12 = tabs["3month"]["national"], tabs["12month"]["national"]
        bus[t], nb[t], ch11[t] = n3["bus_all"], n3["nb_all"], n3["bus_ch11"]
        nb12[t] = n12["nb_all"]
        st12[t] = {s: {"nb_all": v["nb_all"], "bus_ch7": v["bus_ch7"]}
                   for s, v in tabs["12month"]["states"].items()}
    return {"bus": bus, "nb": nb, "ch11": ch11, "nb12": nb12, "st12": st12}


def _raws(pairs) -> list[tuple[int, int]]:
    return [(qidx(a), qidx(b)) for a, b in pairs]


def bank_raws(hist: dict, sid: str) -> list[tuple[int, int]]:
    rules = hist["rules"]["bank_raw_masks"]
    raws = _raws(rules["all"])
    if sid in rules["fas_2010Q1"]:
        raws.append((qidx("2010Q1"), qidx("2010Q1")))
    if sid in rules["bapcpa_chargeoff"]:
        raws.append(tuple(qidx(x) for x in rules["bapcpa_chargeoff"][sid]))
    return raws


def build_distress(hist: dict, live: dict[str, dict] | None = None,
                   bank_live: dict[str, dict[int, float]] | None = None) -> dict:
    """The /distress payload. bank_live: {FRED id: {quarter index: rate}}
    from the bundle; missing series fall back to the frozen history."""
    m = merge_live(hist, live or {})
    court = _raws(hist["rules"]["court_raw_masks"])
    rec = hist["record"]

    bus_path = rule_path(m["bus"], court)
    nb_path = rule_path(m["nb"], court)
    ch11_path = rule_path(m["ch11"], court)
    # one per-capita basis (studies/distress-signals.md): 50 states + DC filings over
    # 50 states + DC population at the 12-month window's midpoint
    t12 = max(m["st12"])
    mid = t12 // 4 + (t12 % 4 + 1) * 0.25 - 0.5               # window midpoint as a fractional year
    nb50 = sum(v["nb_all"] for v in m["st12"][t12].values())
    prev50 = sum(v["nb_all"] for v in m["st12"][t12 - 4].values()) if t12 - 4 in m["st12"] else None
    per_1000 = nb50 / _pop_k(hist, mid)
    yoy = nb50 / prev50 - 1 if prev50 else None
    annual = {int(y): v / hist["us_pop_k"][y]
              for y, v in hist["nonbusiness_annual_50dc"].items() if y in hist["us_pop_k"]}
    national = {
        "consumer": {
            "asof": qstr(t12), "filings_12m": m["nb12"].get(t12), "filings_12m_50dc": nb50,
            "per_1000": round(per_1000, 3), "yoy_12m": round(yoy, 4) if yoy is not None else None,
            "per_1000_by_year": {str(y): round(v, 3) for y, v in sorted(annual.items())},
            "rule": _state(nb_path), "role": rec["consumer_filings"]["role"],
            "record": rec["consumer_filings"],
            "g_path": [{"q": qstr(p["q"]), "g": round(p["g"], 4) if p["g"] is not None else None}
                       for p in nb_path if p["q"] >= qidx("1995Q4")],
        },
        "business": {
            "rule": _state(bus_path), "role": rec["business_filings"]["role"],
            "record": rec["business_filings"],
            "g_path": [{"q": qstr(p["q"]), "g": round(p["g"], 4) if p["g"] is not None else None}
                       for p in bus_path if p["q"] >= qidx("1981Q4")],
        },
        "chapter11": {"rule": _state(ch11_path),
                      "note": "Business Chapter 11 is display-only and untested: large cases file where they "
                              "choose (DE, SDTX, SDNY, NJ), and the series starts in 2001."},
    }
    bank = []
    for sid, label in hist["bank_labels"].items():
        vals = (bank_live or {}).get(sid) or {qidx(k): v for k, v in hist["bank_history"][sid].items()}
        r = rec["bank"][sid]
        path = rule_path(vals, bank_raws(hist, sid), floor=r["floor_pp"])
        last = max(vals)
        bank.append({"id": sid, "label": label, "asof": qstr(last), "latest": vals[last],
                     "rule": _state(path), "role": r["role"], "per_peak": r["per_peak"],
                     "false_alarms": r["false_alarms"], "rotation_p": r["rotation_p"],
                     "qualifiers": r.get("qualifiers", []), "variant_note": r.get("variant_note")})
    # state map: latest 12-month consumer and business Ch 7 filings vs a year earlier
    t = t12
    rows = []
    for s, v in sorted(m["st12"][t].items()):
        prev = m["st12"].get(t - 4, {}).get(s)
        rows.append({"state": s,
                     "per_1000": round(v["nb_all"] / _pop_k(hist, mid, s), 3) if s in hist["state_pop_k"] else None,
                     "consumer_yoy": round(v["nb_all"] / prev["nb_all"] - 1, 4) if prev and prev["nb_all"] else None,
                     "business_ch7_yoy": (round(v["bus_ch7"] / prev["bus_ch7"] - 1, 4)
                                          if prev and prev["bus_ch7"] else None),
                     "business_ch7_12m": v["bus_ch7"]})
    return {
        "headline": rec["headline"],
        "study": hist["study"],
        "history_end": hist["history_end"],
        "live_quarters": sorted((live or {}).keys()),
        "national": national,
        "bank": bank,
        "states": {"asof": qstr(t), "rows": rows, "role": rec["states"]["role"],
                   "business_role": rec["states"].get("business_role"),
                   "summary": rec["states"]["summary"]},
        "failure_liabilities": rec["failure_liabilities"],
        "alert": None,
    }


def bank_from_bundle(bundle: dict, hist: dict) -> dict[str, dict[int, float]]:
    """{FRED id: {quarter index: value}} from the FRED bundle (logical keys)."""
    from ..config import FRED_DISTRESS

    out: dict[str, dict[int, float]] = {}
    for key, sid in FRED_DISTRESS.items():
        d, v = bundle.get(key, ([], []))
        vals = {4 * x.year + (x.month - 1) // 3: float(y) for x, y in zip(d, v) if y is not None}
        if vals:
            out[sid] = vals
    return out


def today_quarter(today: date | None = None) -> tuple[int, int]:
    today = today or date.today()
    return today.year, (today.month - 1) // 3 + 1
