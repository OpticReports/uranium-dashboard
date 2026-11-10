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
import engine as E  # noqa: E402
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


def bottoms_record() -> dict | None:
    """The distress-bottoms study's record (context for the panel's bottoming watch)."""
    path = os.path.join(HERE, "bottoms_results.json")
    if not os.path.exists(path):
        return None
    br = json.load(open(path))
    bp = json.load(open(os.path.join(HERE, "bottoms_posthoc.json")))
    conf = br["P"]["shots"]["CONFIRMS-trough"]
    eq = br["P"]["shots"]["MARKS-equity"]
    fired = [e for e in conf["episodes"] if e["e"] is not None]
    after = sum(1 for e in fired if 0 <= e["e"] <= 9)
    lows = [m for m in (br["equity_targets"][e["peak"]] for e in conf["episodes"]) if m["status"] == "valid"]
    lead = sorted(int(m["b"][:4]) * 12 + int(m["b"][5:]) - (int(e["trough"][:4]) * 12 + int(e["trough"][5:]))
                  for e, m in ((e, br["equity_targets"][e["peak"]]) for e in conf["episodes"])
                  if m["status"] == "valid")
    lead_med = lead[len(lead) // 2] if len(lead) % 2 else (lead[len(lead) // 2 - 1] + lead[len(lead) // 2]) / 2
    g6 = bp["g_peak_vs_trough_by_w"]["6"]["median"]
    return {
        "role": "does not mark the bottom",
        "grade": f"tested 'confirms the trough': fails ({conf['hits']} of {conf['n']}, needs {conf['need_hits']})",
        "summary": (f"Tested on {conf['n']} recessions 1895-1961 (D&B failures): failure growth turns at about the "
                    f"economic bottom (6-month sums, median {g6:+.0f} months) - after the stock market had already "
                    f"bottomed (a median {abs(lead_med):.0f} months earlier). A rule that confirms the slowing fired in "
                    f"{len(fired)}, {after} of them 0-9 months after the trough ({len(fired) - after} early), and in "
                    f"none at a recession stock low ({eq['hits']} of {eq['n']}). The tested grade fails; a post-hoc "
                    f"variant (not graded) fires more often with the same timing. Jobless claims mark troughs "
                    f"sooner."),
        "court_signals": br["R"]["primary"]["signals"],
        "doc": "treasury-canary/studies/distress-bottoms.md",
    }


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
    us_pop = D.us_pop(pop)
    nb_annual = D.nonbusiness_annual_50dc()
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
            leads = [x["lead_months"] for x in rr["per_peak"] if x["outcome"] == "LEAD"]
            assert len(leads) == len(rr["per_peak"]), sid
            # the variant's size p, Holm-adjusted as if it stood in the nine-series family
            holm_v = E.holm({k: (rr["rotation_p"] if k == sid else qc["series"][k]["grade"]["rotation"]["p"])
                             for k in BANK})[sid]
            rec_bank[sid]["variant_note"] = (
                "on point-in-time year-on-year growth (not the pre-registered 4-quarter average) it led all "
                f"{len(leads)} scored recessions ({', '.join(map(str, leads[:-1]))} and {leads[-1]} months) with "
                f"{len(rr['false_alarms'])} false alarms ({', '.join(x[:4] for x in rr['false_alarms'])}); "
                f"raw size p {rr['rotation_p']:.3f}, about {holm_v:.2f} after Holm across the nine")
    ship = qr["ship"]
    record = {
        "business_filings": {
            "role": "does not lead",
            "summary": "No +10% onset in the 18 months before the 1990-91 or 2001 recessions: two came just "
                       "after each ended (1992-01, 2002-01), one years early (1986-01) - 3 false alarms in 33 "
                       "scored years.",
            "per_peak": peaks_text(n1c["primary"]["per_peak"]), "false_alarms": n1c["primary"]["false_alarms"],
            "rotation_p": qn["N1_rotation_p_worst"]},
        "consumer_filings": {
            "role": "does not lead",
            "summary": "Rising from 1985 through 1990-91 with no fresh warning (its Jan-1986 onset is a false "
                       "alarm); the 2001 rise was published Jan-2002, after the recession ended (missed). 3 false "
                       "alarms (1986, 1996, 2002); tested on annual data.",
            "per_peak": peaks_text(n2["primary"]["per_peak"]), "false_alarms": n2["primary"]["false_alarms"],
            "rotation_p": n2["rotation"]["p"]},
        "failure_liabilities": {
            "role": "does not lead (alert rule)",
            "summary": "D&B liabilities of failing firms led reliably only as turning points: a +25%-growth "
                       "alert fired late at 8 of 10 peaks in 1896-1938 and at both clean peaks out of sample in "
                       "1967-83 (after the 1969 and 1973 recessions began; missed 1980 and 1981); it led once "
                       "(1957, by 8 months) in the 1948-66 context run. Liabilities bottomed 8-31 months before "
                       "the 1957-80 peaks, dated after the fact - too long and erratic to time.",
            "per_peak": peaks_text(qh["primary_real_cpi"]["primary"]["per_peak"]),
            "rotation_p": qh["primary_real_cpi"]["rotation"]["p"]},
        "states": {
            "role": "no evidence of a lead",
            "business_role": "confirms" if ship["S2"]["verdict"].startswith("confirms") else "no evidence of a lead",
            "summary": "A state's filing growth predicted its own next-year job losses mainly in the 1980s "
                       "(1981-90; with the pre-registered claims control, 1988-2000, none is significant at 5% - "
                       "the job-loss tests are borderline, p 0.055 / 0.062). "
                       "Since 2002 the only hit is business filings -> job losses (p 0.047), the out-of-sample "
                       "check is uninformative, and a state's rising unemployment predicts its later filings. "
                       "Business Ch 7 filings move with the state's unemployment over the same year (confirm, "
                       "p 0.046); consumer filings show no evidence of a lead.",
            "decisive_p": {s_: ship[s_]["decisive_p"] for s_ in ship},
            "power_vs_1981_2000_effect": {k: v["power"] for k, v in qr["power_panelB_vs_panelA_beta"].items()},
            "panel_A_p": {k: v["wcb_division"]["p"] for k, v in qr["panel_A"].items()},
            "panel_B_p": {k: v["wcb_division"]["p"] for k, v in qr["panel_B"].items()}},
        "bank": rec_bank,
        "bottoms": bottoms_record(),
        "headline": "No bankruptcy or credit-distress series passed the pre-registered test as a recession "
                    "warning. Filings do not lead recessions (they rose with them or after); state business "
                    "Ch 7 filings move with state unemployment; all-loan charge-offs confirm.",
    }
    out = {
        "study": {"doc": "treasury-canary/studies/distress-signals.md",
                  "run": "2026-10-12, pre-registered run + one correction run", "spec": "SPEC v1.1"},
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
        # one per-capita basis: 50 states + DC filings over 50 states + DC population
        "nonbusiness_annual_50dc": {str(y): v for y, v in nb_annual.items()},
        "state_12m": state_12m,
        "us_pop_k": {str(y): round(v, 3) for y, v in us_pop.items() if y >= 1980},
        "state_pop_k": {s: {str(y): pop[s][y] for y in (2023, 2024, 2025)} for s in D.STATES},
        "bank_history": bank_hist,
        "bank_labels": BANK,
        "record": record,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=0, separators=(",", ":"))
    print("wrote", os.path.relpath(OUT), os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
