#!/usr/bin/env python3
"""Export the frozen history + the study's record for the dashboard's
Distress panel -> backend/app/sources/distress_history.json.

    python3 export_history.py

The panel recomputes the live readings with the same rules (gate tests in
backend/tests/test_distress.py); the record (role labels, per-recession
outcomes) comes from results.json and is never recomputed live.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import load as D  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "backend", "app", "sources", "distress_history.json")
RES = json.load(open(os.path.join(HERE, "results.json")))
BANK = {"DRALACBS": "All loans - delinquency", "DRBLACBS": "Business (C&I) loans - delinquency",
        "DRCLACBS": "Consumer loans - delinquency", "DRCCLACBS": "Credit cards - delinquency",
        "DRSFRMACBS": "Home mortgages - delinquency", "DRCRELEXFACBS": "Commercial real estate - delinquency",
        "CORALACBS": "All loans - charge-offs", "CORBLACBS": "Business (C&I) loans - charge-offs",
        "CORCCACBS": "Credit cards - charge-offs"}
FLOOR = {k: (0.05 if k.startswith("COR") else 0.10) for k in BANK}


def qs(i: int) -> str:
    return D.qstr(i)


def peaks_text(per_peak):
    out = []
    for x in per_peak:
        o = x["outcome"]
        if o == "LEAD":
            out.append(f"{x['peak'][:4]}: led by {x['lead_months']}m")
        elif o == "COINCIDENT":
            out.append(f"{x['peak'][:4]}: at the start")
        elif o == "LATE":
            out.append(f"{x['peak'][:4]}: late")
        elif o == "LIT-THROUGH":
            out.append(f"{x['peak'][:4]}: already rising (no fresh signal)")
        else:
            out.append(f"{x['peak'][:4]}: missed")
    return out


def main():
    qn, qc, qh, qr = RES["Q_N"], RES["Q_C"], RES["Q_H"], RES["Q_R"]
    abi_b = D.abi_quarterly_business()
    f2b = D.f2_national("3month", "bus_all")
    n1 = dict(abi_b)
    n1.update({t: v for t, v in f2b.items() if t >= D.qi(2026, 1)})
    # ABI's 1995 quarters sum 1,000 below its printed total; the study scored all
    # four placements (identical onsets) and charts the Q4 one - so does the panel
    n1[D.qi(1995, 4)] += 1000
    nbq = {t: v for t, v in D.abi_quarterly_nonbusiness().items() if t < D.qi(2001, 1)}
    nbq.update(D.f2_national("3month", "nb_all"))
    ch11 = D.f2_national("3month", "bus_ch11")
    s12_nb, s12_b7 = D.f2_state("12month", "nb_all"), D.f2_state("12month", "bus_ch7")
    nat12_nb = D.f2_national("12month", "nb_all")
    pop = D.state_pop()
    ann = D.abi_annual()
    last = D.qi(2026, 2)
    state_12m = {qs(t): {s: {"nb_all": s12_nb[s][t], "bus_ch7": s12_b7[s][t]} for s in D.STATES}
                 for t in range(last - 4, last + 1)}
    bank_hist = {sid: {qs(t): v for t, v in sorted(D.fred_quarterly(sid).items())} for sid in BANK}

    n1c = qn["N1_combos"]["N1|1995Q4"]
    n2 = qn["N2_annual"]
    rec_bank = {}
    for sid, label in BANK.items():
        v = qc["series"][sid]
        g = v["grade"]
        role = "leads" if v["ALERT"] else ("confirms" if v["PANEL"] else "does not lead")
        rec_bank[sid] = {"label": label, "role": role, "per_peak": peaks_text(g["primary"]["per_peak"]),
                         "false_alarms": g["primary"]["false_alarms"], "rotation_p": g["rotation"]["p"],
                         "holm_p": qc["holm"][sid], "floor_pp": FLOOR[sid],
                         "qualifiers": v.get("qualifiers", [])}
        if "transform-sensitive" in v.get("qualifiers", []):
            rr = v["robust_qyoy_record"]
            rec_bank[sid]["variant_note"] = ("on point-in-time year-on-year growth (not the pre-registered "
                                             "4-quarter average) it led every recession: "
                                             + ", ".join(peaks_text(rr["per_peak"]))
                                             + f" (size p {rr['rotation_p']:.3f})")
    ship = qr["ship"]
    record = {
        "business_filings": {
            "role": "does not lead",
            "summary": "Rose after the 1990-91 and 2001 recessions ended, never before them; 3 false alarms "
                       "(1986, 1992, 2002) in 33 scored years.",
            "per_peak": peaks_text(n1c["primary"]["per_peak"]), "false_alarms": n1c["primary"]["false_alarms"],
            "rotation_p": qn["N1_rotation_p_worst"]},
        "consumer_filings": {
            "role": "does not lead",
            "summary": "Already rising through 1987-91 (no fresh warning before 1990); rose after 2001 began; "
                       "3 false alarms (1986, 1996, 2002).",
            "per_peak": peaks_text(n2["primary"]["per_peak"]), "false_alarms": n2["primary"]["false_alarms"],
            "rotation_p": n2["rotation"]["p"]},
        "failure_liabilities": {
            "role": "does not lead (alert rule)",
            "summary": "D&B liabilities of failing firms, tested out of sample 1967-83: the +25% rule fired after "
                       "the 1969 and 1973 recessions began and missed 1980 and 1981. As turning points, "
                       "liabilities bottomed 8-31 months before peaks 1957-80 - too long and erratic to time.",
            "per_peak": peaks_text(qh["primary_real_cpi"]["primary"]["per_peak"]),
            "rotation_p": qh["primary_real_cpi"]["rotation"]["p"]},
        "states": {
            "role": "no evidence of a lead",
            "summary": "A state's filing growth predicted its own next-year job losses in 1981-2000 but not in "
                       "2002-2025 (the test needed both eras, and showed no out-of-sample gain).",
            "decisive_p": {s: ship[s]["decisive_p"] for s in ship},
            "panel_A_p": {k: v["wcb_division"]["p"] for k, v in qr["panel_A"].items()},
            "panel_B_p": {k: v["wcb_division"]["p"] for k, v in qr["panel_B"].items()}},
        "bank": rec_bank,
        "headline": "No bankruptcy or credit-distress series passed the pre-registered test as a recession "
                    "warning. Filings confirm or follow recessions; all-loan charge-offs confirm.",
    }
    out = {
        "study": {"doc": "treasury-canary/studies/distress-signals.md", "run": "2026-10-12", "spec": "SPEC v1.1"},
        "rules": {"theta": 0.10, "quiet_quarters": 4, "lead_months": 18,
                  "court_raw_masks": [["2005Q2", "2008Q4"], ["2020Q2", "2021Q4"]],
                  "bank_raw_masks": {"all": [["2020Q2", "2021Q4"]],
                                     "fas_2010Q1": ["DRCCLACBS", "CORCCACBS", "DRCLACBS", "DRALACBS", "CORALACBS"],
                                     "bapcpa_chargeoff": {"CORCCACBS": ["2005Q3", "2006Q4"]}},
                  "release_lag_months": {"filings": 1, "bank": 2}},
        "history_end": qs(last),
        "national_business_q": {qs(t): v for t, v in sorted(n1.items())},
        "national_nonbusiness_q": {qs(t): v for t, v in sorted(nbq.items())},
        "national_bus_ch11_q": {qs(t): v for t, v in sorted(ch11.items())},
        "national_nonbusiness_12m": {qs(t): v for t, v in sorted(nat12_nb.items())},
        "national_annual": {str(y): {"business": v["business"], "nonbusiness": v["nonbusiness"]}
                            for y, v in sorted(ann.items())},
        "state_12m": state_12m,
        "us_pop_k": {str(y): round(sum(pop[s][y] for s in D.STATES), 3) for y in range(1980, 2026)},
        "state_pop_k": {s: pop[s][2025] for s in D.STATES},
        "bank_history": bank_hist,
        "bank_labels": BANK,
        "record": record,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=0, separators=(",", ":"))
    print("wrote", os.path.relpath(OUT), os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
