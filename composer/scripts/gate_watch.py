#!/usr/bin/env python3
"""Gate watch for HG's SPY 200-day gate (live since 2026-10-19; results.md addendum 45).

Event-driven, not daily: it speaks when SPY is getting close to its 200-day average, when it
crosses, when the gate is actually overriding what HG would otherwise hold, and when the gate
re-opens. Reporting only — nothing here trades or edits a symphony. Called from monitor.py
(alerts -> exit 2 -> the daily routine summarises and pushes). When Composer is unreachable, or
re-serves a session already assessed (holiday, same-day close not in yet), it prints a note and
changes nothing: no event is ever inferred from missing data.

Distance = SPY close / 200-day SMA - 1 on adjusted prices (what Composer's condition reads).
Zones above the line: far (> 3%), near (0..3%), tight (0..1.5%); at or below: closed.
Hysteresis: near re-arms only above 4%, tight only above 2.5%, so a wobble around a threshold
does not repeat a report. Crossings have no hysteresis: each one changes what HG may hold.

Events (alert lines):
  GATE APPROACH       far -> near          GATE IMMINENT   -> tight
  GATE CLOSED         cross below          GATE REOPENED   cross above
  GATE OVERRIDE START live HG in BIL where the pre-gate logic holds a trend basket; ... END
  GATE STILL CLOSED   Mondays while closed GATE APPROACH ENDED  back above 4% without a cross

Base rates quoted in the reports: SPY 1993-11..2026-10 (8,281 sessions, Yahoo adjusted
closes, 200-day SMA; research/leverage data, 2026-10-18):
  closing within 1.5% above the line  -> below it within 10 / 20 sessions: 62% / 69%
  1.5%..3% above                       -> 28% / 41%
  3%..5% above                         -> 11% / 20%
  5%..8% above                         -> 3% / 9%
  within 1.5% below                    -> back above within 10 / 20 sessions: 78% / 85%
  1.5%..3% below                       -> 46% / 66%
  3%..5% below                         -> 26% / 47%
  107 stretches below the line: median 3 sessions, mean 18, half last <= 3 sessions, longest 313
  (2000-09..2002-01; 2008-09 was 257). The gate pays in the long stretches and whipsaws in the
  short ones (add. 42).

Usage: gate_watch.py            # print today's assessment, no state written
"""
import datetime
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import composerlib as cl  # noqa: E402

HG = "mbkiXcuNDjueXpiox5Av"
TREND = {"TQQQ", "UPRO", "UDOW", "SSO", "TNA"}
DIP = {"TECL", "QLD", "LABU", "USD", "SMH"}
LONGVOL = {"UVXY", "VIXY", "VIXM"}
NEAR, TIGHT, NEAR_REARM, TIGHT_REARM = 0.03, 0.015, 0.04, 0.025
PRE_GATE_TREE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures",
                             "hg-live-pre-gate-2026-10-18.raw.json")
# (lo, hi] bands of distance -> P(cross within 10 sessions), P(within 20)
ABOVE_RATES = [(0.0, 0.015, 0.62, 0.69), (0.015, 0.03, 0.28, 0.41), (0.03, 0.05, 0.11, 0.20), (0.05, 0.08, 0.03, 0.09)]
BELOW_RATES = [(0.0, 0.015, 0.78, 0.85), (0.015, 0.03, 0.46, 0.66), (0.03, 0.05, 0.26, 0.47)]


# ----------------------------------------------------------------- pure logic
def zone_of(dist, prev):
    """zone from today's distance, with hysteresis against the previous zone"""
    if dist <= 0:
        return "closed"
    if prev == "tight":
        return "tight" if dist <= TIGHT_REARM else ("near" if dist <= NEAR_REARM else "far")
    if prev == "near":
        return "tight" if dist <= TIGHT else ("near" if dist <= NEAR_REARM else "far")
    return "tight" if dist <= TIGHT else ("near" if dist <= NEAR else "far")


def base_rate(dist):
    table, x = (ABOVE_RATES, dist) if dist > 0 else (BELOW_RATES, -dist)
    for lo, hi, p10, p20 in table:
        if lo <= x <= hi:
            return p10, p20
    return None


def hg_context(hg_holding, ungated_holding, gate_open):
    """one sentence on what the gate means for HG right now"""
    h, u = hg_holding, ungated_holding
    if h in TREND and gate_open:
        return (f"HG holds {h} through its trend branch: a close below the line would move it to BIL at the "
                f"next rebalance, and keep it there until SPY closes back above.")
    if h in TREND:
        return (f"HG still holds {h} from its trend branch; with SPY at or below the line it moves to BIL at "
                f"the next rebalance and stays there until SPY closes back above.")
    if h == "BIL" and u in TREND:
        return f"The gate is overriding: HG sits in BIL where its pre-gate logic would hold {u}."
    if h in DIP:
        return (f"HG is in its oversold dip-buy ({h}), which the gate does not touch; the gate matters again "
                f"once HG's trend branch re-engages (TQQQ's 10-day average back above its 20-day).")
    if h in LONGVOL:
        return f"HG is in its long-vol pop ({h}); the gate does not touch that branch."
    if h == "BIL":
        return "HG is in cash by its own rules (not the gate)."
    return f"HG holds {h}."


def describe(date, dist, dist_5d, slope20, hg_holding, ungated_holding, gate_open):
    """the common descriptive core of every report"""
    side = "above" if dist > 0 else "below"
    s = (f"SPY closed {abs(dist):.1%} {side} its 200-day average on {date}"
         + (f" ({dist - dist_5d:+.1%} over five sessions)" if dist_5d is not None else "") + ". ")
    if dist > 0:
        s += f"A one-day fall of {1 - 1 / (1 + dist):.1%} would close below it. "
    else:
        s += f"A one-day rise of {1 / (1 + dist) - 1:.1%} would close back above it. "
    if slope20 is not None:
        s += (f"The line itself is {'rising' if slope20 > 0 else 'falling'} {abs(slope20):.1%} per 20 sessions"
              f"{', so the gap narrows even on flat days' if dist > 0 and slope20 > 0 else ''}. ")
    br = base_rate(dist)
    if br:
        what = "closed below within 10 / 20 sessions" if dist > 0 else "closed back above within 10 / 20 sessions"
        s += f"Since 1993, from this distance SPY {what} {br[0]:.0%} / {br[1]:.0%} of the time. "
    return s + hg_context(hg_holding, ungated_holding, gate_open)


def assess(date, dist, dist_5d, slope20, hg_holding, ungated_holding, state, weekday, ov_hg="same"):
    """Pure state machine. state is the persisted gate dict (mutated and returned).
    ov_hg: live HG's holding on the pre-gate model's date, for the override check ("same" = hg_holding;
    None = unknown, the previous override state is kept). Returns (alerts, notes, state)."""
    alerts, notes = [], []
    prev = state.get("zone")
    zone = zone_of(dist, prev)
    gate_open = dist > 0
    core = lambda: describe(date, dist, dist_5d, slope20, hg_holding, ungated_holding, gate_open)  # noqa: E731
    first = prev is None
    if first:
        notes.append(f"gate watch initialised: zone {zone}, {core()}")
    elif prev != "closed" and zone == "closed":
        alerts.append("GATE CLOSED — SPY closed at or below its 200-day average; HG's trend baskets are gated to "
                      "cash until it closes back above. " + core() + " Half of all stretches below the line since "
                      "1993 lasted three sessions or fewer (whipsaw); the gate's payoff is the long ones (median 3, "
                      "mean 18; longest 313 sessions in 2000-02, 257 in 2008-09).")
        state["closed_since"] = date
    elif prev == "closed" and zone != "closed":
        n = state.get("closed_days", 0)
        alerts.append(f"GATE REOPENED — SPY closed back above its 200-day average after {n} session(s) below. "
                      f"HG may hold its trend baskets at 3x again from the next rebalance. " + core())
        state["closed_since"] = None
        state["closed_days"] = 0
    elif prev == "far" and zone == "near":
        alerts.append("GATE APPROACH — SPY is within 3% of its 200-day average. " + core())
    elif prev in ("far", "near") and zone == "tight":
        alerts.append("GATE IMMINENT — SPY is within 1.5% of its 200-day average. " + core())
    elif prev in ("near", "tight") and zone == "far":
        alerts.append(f"GATE APPROACH ENDED — SPY is back more than 4% above its 200-day average. "
                      f"SPY closed {dist:.1%} above the line on {date}.")
    if zone == "closed" and not first:
        if prev == "closed":
            state["closed_days"] = state.get("closed_days", 0) + 1
        else:
            state["closed_days"] = 1
        if prev == "closed" and weekday == 0:
            alerts.append(f"GATE STILL CLOSED — session {state['closed_days']} below the line (weekly note). " + core())
    # override: live HG in BIL where the pre-gate logic holds a trend basket; missing data keeps the
    # previous answer (no start or end is inferred from an outage)
    was = bool(state.get("override"))
    hg_o = hg_holding if ov_hg == "same" else ov_hg
    if hg_o is None or ungated_holding is None:
        ov = was
    else:
        ov = bool(hg_o == "BIL" and ungated_holding in TREND)
    if ov and not was:
        alerts.append(f"GATE OVERRIDE START — HG is in BIL where its pre-gate logic would hold {ungated_holding}; "
                      f"from here the two diverge until SPY closes back above the line or HG's own rules leave the "
                      f"trend branch. " + (core() if first or not alerts else ""))
        state["override_since"] = date
    elif was and not ov:
        alerts.append(f"GATE OVERRIDE END — HG and its pre-gate logic hold the same again ({hg_o}); the override "
                      f"ran from {state.get('override_since')} to {date}.")
        state["override_since"] = None
    state.update({"override": ov, "zone": zone, "last_dist": round(dist, 5), "last_date": date})
    return alerts, notes, state


# ------------------------------------------------------------------ data I/O
def _single_asset_tree(ticker):
    return {"id": str(uuid.uuid4()), "step": "root", "name": f"probe {ticker}", "description": "",
            "rebalance": "daily", "children": [{"id": str(uuid.uuid4()), "step": "wt-cash-equal", "children": [
                {"id": str(uuid.uuid4()), "step": "asset", "ticker": ticker}]}]}


def spy_distance(today):
    """(date, dist, dist_5d_ago, slope20) from Composer's adjusted SPY path (one ad-hoc backtest)"""
    start = (today - datetime.timedelta(days=460)).isoformat()
    bt = cl.backtest_tree(_single_asset_tree("SPY"), start=start, end=today.isoformat())
    days, vals = cl.equity_curve(bt)
    if len(vals) < 221:
        raise RuntimeError(f"only {len(vals)} SPY sessions returned")
    sma = lambda i: sum(vals[i - 199:i + 1]) / 200  # noqa: E731
    L = len(vals) - 1
    dist = vals[L] / sma(L) - 1
    dist5 = vals[L - 5] / sma(L - 5) - 1
    slope20 = sma(L) / sma(L - 20) - 1
    return cl.epoch_day_to_date(days[L]).isoformat(), dist, dist5, slope20


def ungated_holding(today):
    """(date, ticker) the pre-gate HG logic holds at the latest close Composer has (ad-hoc backtest of the
    archived pre-gate tree)"""
    with open(PRE_GATE_TREE) as f:
        tree = json.load(f)
    tree["id"] = str(uuid.uuid4())
    start = (today - datetime.timedelta(days=120)).isoformat()
    bt = cl.backtest_tree(tree, start=start, end=today.isoformat())
    raw = bt.get("tdvm_weights") or {}
    first = next(iter(raw))
    if first.isdigit():                       # {day: {ticker: w}}
        d = max(raw, key=int)
        row = raw[d]
    else:                                     # {ticker: {day: w}}
        d = max((dd for m in raw.values() for dd in m), key=int)
        row = {t: m.get(d, 0.0) for t, m in raw.items()}
    top = max(row, key=row.get) if row else None
    return cl.epoch_day_to_date(int(d)).isoformat(), top


def live_holding(meta):
    """(decision date, ticker): the holding reflects the last rebalance ATTEMPT (daily), not the last
    trade; last_rebalance_on only moves when HG trades, so a held position would look stale"""
    s = next((x for x in meta if x["id"] == HG), None)
    if not s or not s.get("holdings"):
        return None, None
    h = max(s["holdings"], key=lambda x: x["allocation"])
    return s.get("last_rebalance_attempted_on") or s.get("last_rebalance_on"), h["ticker"]


def check_gate(state, alerts, snap, meta, now):
    """monitor.py hook: runs the watch, appends alert lines, records a snapshot block.
    Any failure degrades to a printed note (no alert, state untouched)."""
    today = now.date()
    try:
        date, dist, dist5, slope20 = spy_distance(today)
        g = state.setdefault("gate", {})
        reb_date, hg = live_holding(meta)
        if reb_date and hg:
            # live HG's holding by decision date: the pre-gate model lags a session, so the override
            # check compares like dates (the model's latest date against the live holding of that date)
            hist = g.setdefault("live_hist", {})
            hist[reb_date] = hg
            for k in sorted(hist)[:-10]:
                del hist[k]
        if g.get("last_date") == date:
            # holiday, or today's close not in Composer yet: the same session must not be counted twice
            print(f"  (gate watch: no session newer than {date}; nothing re-assessed)")
            snap["gate"] = {"date": date, "spy_vs_200d": g.get("last_dist"), "zone": g.get("zone"), "stale": True}
            return
        try:
            ug_date, ug = ungated_holding(today)
        except (Exception, SystemExit) as e:  # composerlib exits on HTTP errors
            ug_date, ug = None, None
            print(f"  (gate watch: pre-gate model unavailable: {e})")
        ov_hg = g.get("live_hist", {}).get(ug_date) if ug_date else None
        new_alerts, notes, g = assess(date, dist, dist5, slope20, hg, ug, g, now.weekday(), ov_hg=ov_hg)
        state["gate"] = g
        if ug_date and ov_hg is None:
            notes.append(f"gate watch: no live HG record for {ug_date} (the pre-gate model's latest date); override state kept")
        for n in notes:
            print(f"  ({n})")
        print(f"  gate watch: SPY {dist:+.2%} vs 200d on {date}, zone {g['zone']}; HG {hg} on {reb_date}; "
              f"on {ug_date}: HG {ov_hg}, pre-gate logic {ug}")
        alerts.extend(new_alerts)
        snap["gate"] = {"date": date, "spy_vs_200d": round(dist, 5), "zone": g["zone"], "hg_holding": hg,
                        "ungated_holding": ug, "override": g.get("override", False),
                        "closed_days": g.get("closed_days", 0)}
    except (Exception, SystemExit) as e:  # composerlib exits on HTTP errors; never take the monitor down
        print(f"  (gate watch unavailable: {e})")


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    acct = cl.default_account()
    meta = cl.get(f"/portfolio/accounts/{acct}/symphony-stats-meta")["symphonies"]
    state, alerts, snap = {}, [], {}
    check_gate(state, alerts, snap, meta, now)
    # a dry assessment as if the watch had been running (zone 'far' yesterday) so the report text is visible
    g = dict(state.get("gate") or {})
    if g:
        probe = {"zone": "far", "override": False}
        a2, _, _ = assess(g["last_date"], g["last_dist"], None, None, snap["gate"]["hg_holding"],
                          snap["gate"]["ungated_holding"], probe, now.weekday())
        print("\nreport text the next event would carry:\n  " + (a2[0] if a2 else describe(
            g["last_date"], g["last_dist"], None, None, snap["gate"]["hg_holding"], snap["gate"]["ungated_holding"], g["last_dist"] > 0)))
    print("\nalerts now:", alerts or "none")
    print("state:", json.dumps(state.get("gate")))


if __name__ == "__main__":
    main()
