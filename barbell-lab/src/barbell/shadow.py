"""BARBELL-SHADOW — keyless live shadow tracker for the BARBELL-TIMER
champion (relmom_cash) and the pre-registered s16-gated refinement.

Spec: BARBELL_SHADOW_SPEC.md, frozen 2026-08-12 before any live evidence.
This module computes and RECORDS monthly decisions on live tradeable
instruments (GDE / SPY / BOXX; XLU signal-only). It places no orders and
holds no credentials — ever. The IBKR path is a separate, separately-gated
executor build that would only CONSUME this module's output.

Parity law: the decision functions here must reproduce the research
implementation exactly on the frozen study fixture — pinned by
tests/test_shadow.py against research/barbell_timer/rules_results.json.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import db

# Frozen constants (BARBELL_SHADOW_SPEC.md — change spec + tests together).
FREEZE_DECISION = pd.Period("2026-08", "M")  # first decision month scored live
SWITCH_COST = 0.0005                         # 5bp x one-way turnover
LATE_DAY = 5                                 # logged after day 5 of held month -> LATE
VARIANTS = ("relmom_cash", "relmom_s16gated")
HELD_TICKERS = {"gde": "GDE", "spy": "SPY", "boxx": "BOXX"}
SIGNAL_TICKER = "XLU"
BILL_SERIES = "DTB3"

_W = {"gde": np.array([1.0, 0.0, 0.0]), "spy": np.array([0.0, 1.0, 0.0]),
      "boxx": np.array([0.0, 0.0, 1.0]), "5050": np.array([0.5, 0.5, 0.0])}

# Frozen reference numbers from the study (OOS 1990-02 -> 2026-07, synthetic
# GDE, monthly closes) — display-only context, never recomputed here.
STUDY_REFERENCE = {
    "window": "OOS 1990-02 -> 2026-07 (synthetic GDE, monthly)",
    "relmom_cash": {"cagr": 0.1523, "maxdd": -0.227, "calmar": 0.67},
    "relmom_cash_lagged_1m": {"cagr": 0.1290, "maxdd": -0.493, "calmar": 0.26,
                              "note": "KILL — one late month (Oct-2008) erases the edge"},
    "bh_spy": {"cagr": 0.1103, "maxdd": -0.508, "calmar": 0.22},
    "bh_gde_synth": {"cagr": 0.1398, "maxdd": -0.442, "calmar": 0.32},
    "static_5050": {"cagr": 0.1277, "maxdd": -0.449, "calmar": 0.28},
    "s16_isolation": {"hit_rate": 0.618, "p_adj": 0.08,
                      "note": "French Utils - eq-weight mkt; live proxy is "
                              "XLU - SPY (deviation flagged in spec)"},
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shadow_log (
    held_month     TEXT NOT NULL,   -- month the decided state is held for
    variant        TEXT NOT NULL,
    state          TEXT NOT NULL,   -- gde | spy | boxx
    decision_month TEXT NOT NULL,   -- month-end the decision was computed from
    logged_at_utc  TEXT NOT NULL,
    PRIMARY KEY (held_month, variant)
);
"""


class ShadowDataError(RuntimeError):
    pass


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)


# ------------------------------------------------------------- primitives --
def complete_monthly_closes(px: pd.Series) -> pd.Series:
    """Month-end closes for COMPLETE months only (PeriodIndex[M]).
    Frozen rule: a month is complete iff the data contains a later-month
    observation — the last month present is always dropped. Conservative on
    purpose: no business-day-calendar guessing at month boundaries."""
    px = px.dropna()
    if px.empty:
        return pd.Series(dtype=float)
    me = px.groupby(px.index.to_period("M")).last()
    return me.iloc[:-1]


def monthly_returns(px: pd.Series) -> pd.Series:
    return complete_monthly_closes(px).pct_change().dropna()


def mom121(r: pd.Series) -> pd.Series:
    """12-1 momentum: compounded monthly returns t-11..t-1, SKIPPING month t
    (repo-standard convention, identical to the research code)."""
    c = (1.0 + r).cumprod()
    return c.shift(1) / c.shift(12) - 1.0


def bill_monthly_returns(dtb3_daily: pd.Series) -> pd.Series:
    """Bill return for month t = de-annualized DTB3 month-end yield of t-1
    (known at the start of t). Filter hurdle only — the held cash instrument
    is the real BOXX fund."""
    y = dtb3_daily.dropna()
    me = y.groupby(y.index.to_period("M")).last()
    return ((1.0 + me / 100.0) ** (1.0 / 12.0) - 1.0).shift(1).dropna()


# -------------------------------------------------------- decision brains --
def relmom_states(gde_r: pd.Series, spy_r: pd.Series, bill_r: pd.Series) -> pd.Series:
    """V1, the study champion: 12-1 relmom picks GDE or SPY; winner held only
    if its own 12-1 beats bills' 12-1, else BOXX. Must stay in exact parity
    with research rules.py rule 2 (gate-tested against the frozen fixture)."""
    g, s, b = mom121(gde_r), mom121(spy_r), mom121(bill_r)
    df = pd.concat({"g": g, "s": s, "b": b}, axis=1).dropna()
    winner = np.where(df["g"] > df["s"], "gde", "spy")
    ok = np.where(winner == "gde", df["g"] > df["b"], df["s"] > df["b"])
    return pd.Series(np.where(ok, winner, "boxx"), index=df.index)


def s16_riskoff(xlu_r: pd.Series, spy_r: pd.Series) -> pd.Series:
    """Live s16 proxy: XLU 12-1 minus SPY 12-1 > 0 -> utilities leading ->
    risk-off. Frozen deviation from the study's French Utils/eq-weight-mkt
    construction (spec, 'Variants tracked')."""
    d = (mom121(xlu_r) - mom121(spy_r)).dropna()
    return d > 0


def gate_states(states: pd.Series, riskoff: pd.Series) -> pd.Series:
    """V2: V1's state, except GDE + risk-off -> BOXX. SPY/BOXX states are
    never touched (A17 rule-10 shape, s16-only gate)."""
    idx = states.index.intersection(riskoff.index)
    st = states.reindex(idx)
    fire = riskoff.reindex(idx) & (st == "gde")
    return pd.Series(np.where(fire, "boxx", st), index=idx)


def decisions_frame(gde_r: pd.Series, spy_r: pd.Series, bill_r: pd.Series,
                    xlu_r: pd.Series) -> pd.DataFrame:
    """All decision months where BOTH variants are defined, with diagnostics.
    Index = decision month t; the state is held for month t+1."""
    v1 = relmom_states(gde_r, spy_r, bill_r)
    ro = s16_riskoff(xlu_r, spy_r)
    v2 = gate_states(v1, ro)
    idx = v1.index.intersection(v2.index)
    g, s, b = mom121(gde_r), mom121(spy_r), mom121(bill_r)
    x = mom121(xlu_r)
    return pd.DataFrame({
        "relmom_cash": v1.reindex(idx), "relmom_s16gated": v2.reindex(idx),
        "s16_riskoff": ro.reindex(idx).astype(bool),
        "mom121_gde": g.reindex(idx), "mom121_spy": s.reindex(idx),
        "mom121_bills": b.reindex(idx), "mom121_xlu": x.reindex(idx),
    }, index=idx)


def shadow_backtest(states: pd.Series, assets: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Decision month t earns month t+1; drift-aware one-way turnover,
    SWITCH_COST x turnover charged in the traded month; initial buy-in
    uncharged. Identical accounting to the research backtest."""
    av = assets[["gde", "spy", "boxx"]]
    rets, tos, prev = {}, {}, None
    for t in states.index:
        h = t + 1
        if h not in av.index:
            continue
        w = _W[states.loc[t]]
        to = 0.0 if prev is None else 0.5 * float(np.abs(w - prev).sum())
        r = av.loc[h].values
        rets[h] = float(w @ r - SWITCH_COST * to)
        tos[h] = to
        grown = w * (1.0 + r)
        prev = grown / grown.sum()
    return pd.Series(rets), pd.Series(tos)


# ------------------------------------------------------------ data access --
def _assert_contiguous(name: str, s: pd.Series) -> None:
    """mom121 and shift(1) are POSITIONAL — a whole missing month would make
    them silently span 12+ calendar months (referee finding, 2026-08-12).
    Monthly inputs must therefore be gap-free or the run dies loudly."""
    if s.empty:
        return
    want = pd.period_range(s.index.min(), s.index.max(), freq="M")
    gaps = want.difference(s.index)
    if len(gaps):
        raise ShadowDataError(
            f"{name}: monthly series has gap months {[str(g) for g in gaps[:6]]}"
            " — positional 12-1 windows would silently misalign; fix the feed")


def load_inputs(con: sqlite3.Connection) -> dict:
    """Live inputs from the ingest DB. Missing feeds raise loudly — a shadow
    decision computed from partial data is worse than none."""
    missing, rets = [], {}
    for key, tkr in {**HELD_TICKERS, "xlu": SIGNAL_TICKER}.items():
        px = db.read_prices(con, tkr, source="yahoo")
        if px.empty:
            missing.append(tkr)
            continue
        rets[key] = monthly_returns(px["close_adj"])
    dtb3 = db.read_fred(con, BILL_SERIES)
    if dtb3.dropna().empty:
        missing.append(BILL_SERIES)
    if missing:
        raise ShadowDataError(
            f"shadow inputs missing: {missing} — run `barbell ingest` "
            "(config/data.yaml declares them)")
    rets["bills"] = bill_monthly_returns(dtb3)
    for k, v in rets.items():
        _assert_contiguous(k, v)
    return rets


# ------------------------------------------------------------ log + board --
def log_decisions(con: sqlite3.Connection,
                  now: datetime | None = None) -> list[dict]:
    """Append the latest decision (held month = last complete month + 1) for
    both variants. Append-only + idempotent: an existing (held_month, variant)
    row is NEVER overwritten, so later data revisions cannot rewrite history.
    Returns the rows actually inserted."""
    ensure_schema(con)
    x = load_inputs(con)
    dec = decisions_frame(x["gde"], x["spy"], x["bills"], x["xlu"])
    if dec.empty:
        raise ShadowDataError("no decision months computable yet")
    t = dec.index.max()
    now = now or datetime.now(timezone.utc)
    inserted = []
    for v in VARIANTS:
        row = (str(t + 1), v, str(dec.loc[t, v]), str(t), now.isoformat())
        cur = con.execute(
            "INSERT OR IGNORE INTO shadow_log "
            "(held_month, variant, state, decision_month, logged_at_utc) "
            "VALUES (?,?,?,?,?)", row)
        if cur.rowcount:
            inserted.append(dict(zip(
                ("held_month", "variant", "state", "decision_month",
                 "logged_at_utc"), row)))
    con.commit()
    return inserted


def _late(held_month: pd.Period, logged_at_utc: str) -> bool:
    ts = datetime.fromisoformat(logged_at_utc)
    start = held_month.to_timestamp()  # first day of held month
    return (ts.replace(tzinfo=None) - start).days + 1 > LATE_DAY


def board(con: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Everything the /shadow page shows. Live evidence = LOGGED states only;
    recomputed history is used solely to (a) show current posture and (b)
    tripwire-diff against the log (data-revision detection)."""
    ensure_schema(con)
    now = now or datetime.now(timezone.utc)
    x = load_inputs(con)
    dec = decisions_frame(x["gde"], x["spy"], x["bills"], x["xlu"])
    if dec.empty:
        raise ShadowDataError("no decision months computable yet")
    t = dec.index.max()

    logged = pd.read_sql_query(
        "SELECT held_month, variant, state, decision_month, logged_at_utc "
        "FROM shadow_log ORDER BY held_month", con)

    # tripwire 1: recomputed state vs logged state for every logged month.
    # recompute_ok is TRI-STATE (referee 2026-08-12): True = matches, False =
    # MISMATCH (vendor revised history), None = UNRECOMPUTABLE (decision month
    # no longer in the recomputed frame — e.g. vendor truncated history).
    # Unrecomputable is a warning, never a silent pass.
    mismatches, unrecomputable, ledger = [], [], []
    for _, r in logged.iterrows():
        d = pd.Period(r["decision_month"], "M")
        recomputed = str(dec.loc[d, r["variant"]]) if d in dec.index else None
        ok: bool | None = None if recomputed is None else recomputed == r["state"]
        if ok is False:
            mismatches.append({**r.to_dict(), "recomputed": recomputed})
        if ok is None:
            unrecomputable.append(r.to_dict())
        ledger.append({
            **r.to_dict(),
            "live": bool(d >= FREEZE_DECISION),
            "late": _late(pd.Period(r["held_month"], "M"), r["logged_at_utc"]),
            "recompute_ok": ok,
        })

    # tripwire 2 (referee 2026-08-12, the Oct-2008 class): a live-scored month
    # with NO logged row past its day-LATE_DAY deadline is a RED failure —
    # stale feeds or a dead scheduler must scream, not vanish. Wall-clock
    # based on purpose: stale data cannot hide a month by shrinking dec.
    have = {(r["held_month"], r["variant"]) for _, r in logged.iterrows()}
    now_naive = now.replace(tzinfo=None)
    cur_m = pd.Period(f"{now.year}-{now.month:02d}", "M")
    missing_logs = []
    first_live_held = FREEZE_DECISION + 1
    if cur_m >= first_live_held:
        for h in pd.period_range(first_live_held, cur_m, freq="M"):
            past_deadline = (now_naive - h.to_timestamp()).days + 1 > LATE_DAY
            if not past_deadline:
                continue
            for v in VARIANTS:
                if (str(h), v) not in have:
                    missing_logs.append({"held_month": str(h), "variant": v})

    # live shadow performance from LOGGED states (held months since freeze
    # whose returns are complete). Benchmarks are computed over EXACTLY each
    # variant's own scored held months (referee: a ragged log must not be
    # compared against a longer benchmark window).
    assets = pd.concat({k: x[k] for k in ("gde", "spy", "boxx")}, axis=1).dropna()
    live: dict[str, dict] = {}
    for v in VARIANTS:
        rows = logged[(logged["variant"] == v)]
        states = pd.Series(
            {pd.Period(r["decision_month"], "M"): r["state"]
             for _, r in rows.iterrows()
             if pd.Period(r["decision_month"], "M") >= FREEZE_DECISION}
        ).sort_index()
        if states.empty:
            live[v] = {"months": 0}
            continue
        r_live, to = shadow_backtest(states, assets)
        if not len(r_live):
            live[v] = {"months": 0}
            continue
        held = r_live.index
        win = assets.loc[held]
        r5050, _ = shadow_backtest(pd.Series("5050", index=held - 1), assets)
        live[v] = {
            "months": int(len(r_live)),
            "equity": float((1.0 + r_live).prod()),
            "returns": {str(k): float(vv) for k, vv in r_live.items()},
            "turnover": float(to.sum()),
            "held_months": [str(h) for h in held],
            "benchmarks": {
                "bh_gde": float((1 + win["gde"]).prod()),
                "bh_spy": float((1 + win["spy"]).prod()),
                "static_5050": float((1 + r5050.loc[held]).prod()),
            },
        }

    d_row = dec.loc[t]
    return {
        "spec": "BARBELL_SHADOW_SPEC.md (frozen 2026-08-12)",
        "freeze_decision_month": str(FREEZE_DECISION),
        "decision_month": str(t),
        "held_month": str(t + 1),
        "current": {
            "relmom_cash": str(d_row["relmom_cash"]),
            "relmom_s16gated": str(d_row["relmom_s16gated"]),
            "s16_riskoff": bool(d_row["s16_riskoff"]),
            "mom121": {k: float(d_row[f"mom121_{k}"])
                       for k in ("gde", "spy", "bills", "xlu")},
        },
        "ledger": ledger,
        "mismatches": mismatches,
        "unrecomputable": unrecomputable,
        "missing_logs": missing_logs,
        "live": live,
        "study_reference": STUDY_REFERENCE,
        "data_asof": {k: str(x[k].index.max()) for k in
                      ("gde", "spy", "boxx", "xlu", "bills")},
    }
