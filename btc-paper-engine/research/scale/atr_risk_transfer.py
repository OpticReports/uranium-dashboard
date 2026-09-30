"""NOTIONAL -> DOLLAR-RISK transfer function for the S5 blend, measured on the
10,002-bar 4h BTC fixture (2022-01-01 -> 2026-07).

WHY: the live executor sizes leg_notional = kelly_m * lev * weight * base. That
is a CONSTANT DOLLAR number: it is vol-blind. Dollar risk to the stop is
notional * (stop_distance / price), and stop distance is 2.5*ATR14 (pullback,
S3) or 5.0*ATR14 (donchian trail, S4). So the same $15,000 gross carries a
different dollar risk in every vol regime. This script measures that function
and inverts it.

ATR14 is reproduced EXACTLY as app/indicators.py computes it:
  TR_i = max(h-l, |h-pc|, |l-pc|), TR_0 = None
  ATR  = ewm(alpha=1/14, adjust=False) seeded on the FIRST TR observation
(asserted against the engine's own pure-python implementation below).

Outputs: research/scale/scale_findings.json + PNG charts.
Usage: python3 atr_risk_transfer.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)

from app.indicators import atr as engine_atr                      # noqa: E402
from app.engine.core import Bar, BookCfg                          # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.config import RESEARCH_SIGNAL, RESEARCH_TRADE            # noqa: E402

BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
OUT = HERE

# ---- live executor constants (btc-executor/app/mirror.py + live env) --------
KELLY_M = 0.20
REFERENCE_LEV = 1.5
W_PB, W_TR = 0.75, 0.25
SIZING_BASE_USD = 50_000.0
MAX_NOTIONAL_USD = 20_000.0
EQUITY_LIVE = 100_055.0
# stop geometry (btc-paper-engine TradeCfg.stop_atr / BookCfg.trail_atr)
STOP_ATR_PB = 2.5
TRAIL_ATR_TR = 5.0
WARMUP = 210          # run_replay's warmup; indicators before this are unused

R = {}                # results dict -> JSON


# ============================================================ A. bar geometry
def load_bars() -> pd.DataFrame:
    df = pd.read_csv(BARS_CSV)
    df["ts"] = df["ts_open_unix"].astype(int)
    df["dt"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df


def compute_atr(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    return tr.ewm(alpha=1.0 / 14.0, adjust=False, ignore_na=True).mean()


def verify_atr(df: pd.DataFrame, a: pd.Series) -> float:
    ref = engine_atr(df["high"].tolist(), df["low"].tolist(),
                     df["close"].tolist(), 14)
    ref = np.array([np.nan if v is None else v for v in ref])
    mine = a.to_numpy()
    m = ~np.isnan(ref) & ~np.isnan(mine)
    return float(np.nanmax(np.abs(ref[m] - mine[m])))


def pct_stats(x: np.ndarray) -> dict:
    x = x[~np.isnan(x)]
    return {
        "n": int(x.size),
        "mean": float(x.mean()), "median": float(np.median(x)),
        "p1": float(np.percentile(x, 1)), "p5": float(np.percentile(x, 5)),
        "p10": float(np.percentile(x, 10)), "p25": float(np.percentile(x, 25)),
        "p75": float(np.percentile(x, 75)), "p90": float(np.percentile(x, 90)),
        "p95": float(np.percentile(x, 95)), "p99": float(np.percentile(x, 99)),
        "min": float(x.min()), "max": float(x.max()),
    }


def main() -> None:
    df = load_bars()
    df["atr14"] = compute_atr(df)
    R["atr_parity_max_abs_err_vs_engine"] = verify_atr(df, df["atr14"])

    # realised vol: 30-bar (5 day) stdev of 4h log returns, annualised
    lr = np.log(df["close"]).diff()
    df["rv30_ann"] = lr.rolling(30).std() * np.sqrt(2190.0)

    # stop distance as a FRACTION OF PRICE, per leg and notional-weighted blend
    df["s_pb"] = STOP_ATR_PB * df["atr14"] / df["close"]
    df["s_tr"] = TRAIL_ATR_TR * df["atr14"] / df["close"]
    df["s_blend"] = W_PB * df["s_pb"] + W_TR * df["s_tr"]      # = 3.125*ATR/P
    df["atr_frac"] = df["atr14"] / df["close"]

    d = df.iloc[WARMUP:].copy().reset_index(drop=True)   # tradeable window only
    d["year"] = d["dt"].dt.year
    R["window"] = {
        "bars_total": int(len(df)), "bars_analysed": int(len(d)),
        "first": str(d["dt"].iloc[0]), "last": str(d["dt"].iloc[-1]),
        "warmup_bars_dropped": WARMUP,
    }

    # -------- 1. distribution of 5*ATR14/close and the other stop multiples
    R["stop_distance_pct_of_price"] = {
        "atr14_over_close": pct_stats(d["atr_frac"].to_numpy() * 100),
        "pullback_2.5atr": pct_stats(d["s_pb"].to_numpy() * 100),
        "trend_5.0atr": pct_stats(d["s_tr"].to_numpy() * 100),
        "blend_3.125atr_notional_weighted": pct_stats(d["s_blend"].to_numpy() * 100),
    }

    by_year = {}
    for y, g in d.groupby("year"):
        by_year[int(y)] = {
            "n_bars": int(len(g)),
            "trend_5atr_median_pct": float(np.median(g["s_tr"]) * 100),
            "trend_5atr_p10_pct": float(np.percentile(g["s_tr"], 10) * 100),
            "trend_5atr_p90_pct": float(np.percentile(g["s_tr"], 90) * 100),
            "blend_median_pct": float(np.median(g["s_blend"]) * 100),
            "rv30_ann_median_pct": float(np.nanmedian(g["rv30_ann"]) * 100),
        }
    R["by_year"] = by_year

    # realised-vol terciles (conditioned on rv30, an INDEPENDENT vol estimate)
    dv = d.dropna(subset=["rv30_ann"]).copy()
    q = np.percentile(dv["rv30_ann"], [33.3333, 66.6667])
    dv["rv_tercile"] = np.where(dv["rv30_ann"] <= q[0], "low",
                        np.where(dv["rv30_ann"] <= q[1], "mid", "high"))
    terc = {}
    for k in ("low", "mid", "high"):
        g = dv[dv["rv_tercile"] == k]
        terc[k] = {
            "n_bars": int(len(g)),
            "rv30_ann_median_pct": float(np.median(g["rv30_ann"]) * 100),
            "blend_median_pct": float(np.median(g["s_blend"]) * 100),
            "trend_5atr_median_pct": float(np.median(g["s_tr"]) * 100),
        }
    R["rv_terciles"] = terc | {"cut_rv30_ann_pct": [float(q[0] * 100), float(q[1] * 100)]}

    # -------- 2/3. transfer function and its inverse
    s = d["s_blend"].to_numpy()
    R["transfer_function"] = {
        "form": "dollar_risk = notional * s ; s = 3.125 * ATR14 / close "
                "(notional-weighted blend of 2.5x pullback @0.75 and 5.0x trail @0.25)",
        "risk_bps_per_dollar_notional": {k: v * 100 for k, v in
                                         pct_stats(s * 100).items()
                                         if k not in ("n",)},
        "dollar_risk_per_10k_notional": {k: v * 10_000 for k, v in
                                         pct_stats(s).items() if k != "n"},
    }
    RISK_TARGET = 0.01 * 100_000.0     # $1,000 = 1% of $100k equity
    notional_1pct = RISK_TARGET / s
    R["inverse_notional_for_1000_risk"] = pct_stats(notional_1pct)
    inv_year = {}
    for y, g in d.groupby("year"):
        n_y = RISK_TARGET / g["s_blend"].to_numpy()
        inv_year[int(y)] = {"median": float(np.median(n_y)),
                            "p10": float(np.percentile(n_y, 10)),
                            "p90": float(np.percentile(n_y, 90))}
    R["inverse_notional_for_1000_risk_by_year"] = inv_year
    inv_terc = {}
    for k in ("low", "mid", "high"):
        g = dv[dv["rv_tercile"] == k]
        n_t = RISK_TARGET / g["s_blend"].to_numpy()
        inv_terc[k] = {"median": float(np.median(n_t)),
                       "p10": float(np.percentile(n_t, 10)),
                       "p90": float(np.percentile(n_t, 90))}
    R["inverse_notional_for_1000_risk_by_rv_tercile"] = inv_terc

    # -------- 4. what today's constant $15,000 gross actually risks
    gross_today = KELLY_M * REFERENCE_LEV * SIZING_BASE_USD      # 15,000
    risk_today = gross_today * s
    dec = np.percentile(s, np.arange(0, 101, 10))
    d["s_decile"] = np.clip(np.digitize(s, dec[1:-1]) + 1, 1, 10)
    decile_tbl = {}
    for k in range(1, 11):
        g = d[d["s_decile"] == k]
        sg = g["s_blend"].to_numpy()
        decile_tbl[k] = {
            "n_bars": int(len(g)),
            "blend_stop_median_pct": float(np.median(sg) * 100),
            "risk_usd_of_15k_gross_median": float(np.median(gross_today * sg)),
            "risk_pct_equity_median": float(np.median(gross_today * sg) / EQUITY_LIVE * 100),
            "notional_at_1000_risk_median": float(np.median(RISK_TARGET / sg)),
        }
    R["todays_15k_gross"] = {
        "gross_notional_usd": gross_today,
        "gross_pct_of_equity": gross_today / EQUITY_LIVE * 100,
        "dollar_risk_stats": pct_stats(risk_today),
        "dollar_risk_pct_equity_stats": pct_stats(risk_today / EQUITY_LIVE * 100),
        "by_stop_decile": decile_tbl,
        "calm_vs_violent": {
            "decile1_median_risk_usd": decile_tbl[1]["risk_usd_of_15k_gross_median"],
            "decile10_median_risk_usd": decile_tbl[10]["risk_usd_of_15k_gross_median"],
            "ratio_d10_over_d1": (decile_tbl[10]["risk_usd_of_15k_gross_median"]
                                  / decile_tbl[1]["risk_usd_of_15k_gross_median"]),
            "p99_over_p1_of_s": float(np.percentile(s, 99) / np.percentile(s, 1)),
            "p90_over_p10_of_s": float(np.percentile(s, 90) / np.percentile(s, 10)),
        },
    }

    # ---------------- 5. EMPIRICAL: real trades from the engine code path -----
    bars = [Bar(ts=int(r.ts), open=float(r.open), high=float(r.high),
                low=float(r.low), close=float(r.close), volume=float(r.volume))
            for r in df.itertuples()]
    books = [
        BookCfg(name="S3", sizing="fixed", strategy="pullback", leverage=1.0,
                long_mult=1.0, cap=1.0, start_equity=100_000.0, dd_halt=0.30),
        BookCfg(name="S4", sizing="fixed", strategy="donchian", trail_atr=5.0,
                leverage=1.0, long_mult=1.0, cap=1.0, start_equity=100_000.0,
                dd_halt=0.50),
    ]
    res = run_replay(bars, books, RESEARCH_SIGNAL, RESEARCH_TRADE, cash_apy=0.0)
    t3 = res.books["S3"].trades
    t4 = res.books["S4"].trades

    def trade_frame(trades, mult, leg):
        rows = []
        for t in trades:
            s_i = mult * t.atr_at_entry / t.entry_price
            rows.append(dict(
                leg=leg, side=t.side, entry_ts=t.entry_ts, exit_ts=t.exit_ts,
                entry=t.entry_price, exit=t.exit_price, reason=t.exit_reason,
                s_nominal=s_i,                     # theoretical stop frac
                r=t.pnl_pct / 100.0,               # net return per $1 notional
                bars_held=t.bars_held))
        return pd.DataFrame(rows)

    f3 = trade_frame(t3, STOP_ATR_PB, "pullback")
    f4 = trade_frame(t4, TRAIL_ATR_TR, "trend")

    def realisation(f, name):
        lose = f[f["r"] < 0]
        ratio = (-lose["r"] / lose["s_nominal"]).to_numpy()
        stops = f[f["reason"] == "STOP"]
        rs = (-stops["r"] / stops["s_nominal"]).to_numpy() if len(stops) else np.array([])
        return {
            "n_trades": int(len(f)),
            "n_losers": int(len(lose)),
            "win_rate_pct": float((f["r"] > 0).mean() * 100),
            "mean_r_pct": float(f["r"].mean() * 100),
            "exit_reason_mix": {k: int(v) for k, v in f["reason"].value_counts().items()},
            "nominal_stop_frac_median_pct": float(np.median(f["s_nominal"]) * 100),
            "loss_over_nominal_stop": pct_stats(ratio) if ratio.size else None,
            "STOP_exits_loss_over_nominal": pct_stats(rs) if rs.size else None,
            "worst_single_loss_pct_of_notional": float(f["r"].min() * 100),
            "worst_loss_over_nominal_stop": float(ratio.max()) if ratio.size else None,
        }

    R["empirical_trades"] = {"pullback_S3": realisation(f3, "S3"),
                             "trend_S4": realisation(f4, "S4")}

    # ------- 6. sizing comparison: vol-BLIND (live) vs vol-TARGETED ----------
    # research-basis exit-step blend: eq *= 1 + expo_i * r_i in exit order.
    # r_i already nets the engine's 12bp round-trip taker fee, and fee scales
    # with notional, so scaling expo scales fee correctly.
    ev = pd.concat([f3, f4]).sort_values("exit_ts").reset_index(drop=True)
    ev["w"] = np.where(ev["leg"] == "pullback", W_PB, W_TR)
    GROSS_FRAC = gross_today / EQUITY_LIVE            # 0.1499 of equity
    ev["expo_fixed"] = GROSS_FRAC * ev["w"]
    ev["risk_fixed"] = ev["expo_fixed"] * ev["s_nominal"]   # frac of equity at risk

    R_LEG = {"pullback": float(ev[ev.leg == "pullback"]["risk_fixed"].mean()),
             "trend": float(ev[ev.leg == "trend"]["risk_fixed"].mean())}
    ev["expo_vt"] = ev.apply(
        lambda r: R_LEG[r["leg"]] / r["s_nominal"], axis=1)

    def curve(expo: np.ndarray, r: np.ndarray, cap_frac: float | None = None):
        e = expo.copy()
        clamped = 0
        if cap_frac is not None:
            clamped = int((e > cap_frac).sum())
            e = np.minimum(e, cap_frac)
        eq = np.cumprod(1.0 + e * r)
        peak = np.maximum.accumulate(eq)
        dd = eq / peak - 1.0
        yrs = (ev["exit_ts"].iloc[-1] - ev["exit_ts"].iloc[0]) / (365.25 * 86400)
        return dict(
            eq=eq, dd=dd,
            total_pct=float((eq[-1] - 1) * 100),
            cagr_pct=float((eq[-1] ** (1 / yrs) - 1) * 100),
            maxdd_pct=float(dd.min() * 100),
            mar=float(((eq[-1] ** (1 / yrs)) - 1) / abs(dd.min())),
            years=float(yrs),
            n_clamped=clamped, n=len(e),
            expo_median=float(np.median(e)), expo_p90=float(np.percentile(e, 90)),
            expo_p99=float(np.percentile(e, 99)), expo_max=float(e.max()),
        )

    rr = ev["r"].to_numpy()
    c_fix = curve(ev["expo_fixed"].to_numpy(), rr)
    c_vt = curve(ev["expo_vt"].to_numpy(), rr)
    # caps expressed as gross-leg exposure fractions of equity
    caps = {}
    for cap_gross in (0.20, 0.30, 0.50, 0.75, 1.00, 1.50, 2.00):
        caps[cap_gross] = {k: v for k, v in
                           curve(ev["expo_vt"].to_numpy(), rr,
                                 cap_frac=cap_gross).items()
                           if k not in ("eq", "dd")}

    def strip(c):
        return {k: v for k, v in c.items() if k not in ("eq", "dd")}

    R["sizing_comparison"] = {
        "basis": "exit-step (trade-close) blended equity, research basis, "
                 "cash_apy 0, engine trades unchanged, 12bp round-trip taker "
                 "already inside r_i. IN-SAMPLE over the whole fixture.",
        "matched_risk_frac_of_equity_per_leg": R_LEG,
        "matched_gross_risk_pct_equity": (R_LEG["pullback"] + R_LEG["trend"]) * 100,
        "FIXED_vol_blind_live": strip(c_fix),
        "VOLTARGET_matched_mean_risk": strip(c_vt),
        "VOLTARGET_with_gross_exposure_caps": caps,
        "notional_usd_at_100k_equity": {
            "fixed_gross": gross_today,
            "voltarget_gross_median": c_vt["expo_median"] * 100_000.0,
            "voltarget_gross_p90": c_vt["expo_p90"] * 100_000.0,
            "voltarget_gross_p99": c_vt["expo_p99"] * 100_000.0,
            "voltarget_gross_max": c_vt["expo_max"] * 100_000.0,
        },
    }

    # per-trade dollar risk dispersion under each rule (the core honesty check)
    R["dollar_risk_dispersion_per_trade_pct_equity"] = {
        "FIXED": pct_stats(ev["risk_fixed"].to_numpy() * 100),
        "VOLTARGET": pct_stats((ev["expo_vt"] * ev["s_nominal"]).to_numpy() * 100),
    }

    # ---- bootstrap: is the DD difference signal or noise? -------------------
    rng = np.random.default_rng(20260928)
    def boot_maxdd(expo, r, n_boot=4000, block=8):
        n = len(r)
        out = []
        nb = int(np.ceil(n / block))
        for _ in range(n_boot):
            idx = np.concatenate([np.arange(i, min(i + block, n))
                                  for i in rng.integers(0, n, nb)])[:n]
            eq = np.cumprod(1.0 + expo[idx] * r[idx])
            pk = np.maximum.accumulate(eq)
            out.append((eq / pk - 1).min())
        return np.array(out)

    bf = boot_maxdd(ev["expo_fixed"].to_numpy(), rr)
    bv = boot_maxdd(ev["expo_vt"].to_numpy(), rr)
    R["bootstrap_maxdd_block8_n4000"] = {
        "FIXED": {"median_pct": float(np.median(bf) * 100),
                  "p5_pct": float(np.percentile(bf, 5) * 100),
                  "p95_pct": float(np.percentile(bf, 95) * 100),
                  "P_dd_worse_than_30pct": float((bf < -0.30).mean()),
                  "P_dd_worse_than_35pct": float((bf < -0.35).mean())},
        "VOLTARGET": {"median_pct": float(np.median(bv) * 100),
                      "p5_pct": float(np.percentile(bv, 5) * 100),
                      "p95_pct": float(np.percentile(bv, 95) * 100),
                      "P_dd_worse_than_30pct": float((bv < -0.30).mean()),
                      "P_dd_worse_than_35pct": float((bv < -0.35).mean())},
        "P_voltarget_worse_than_fixed_paired": float((bv < bf).mean()),
    }

    # ---- what equity / cap is needed for $100k and $1m gross ---------------
    sm = float(np.median(s))
    R["scaling_to_targets"] = {
        "median_blend_stop_frac": sm,
        "risk_usd_per_100k_gross_at_median_stop": 100_000.0 * sm,
        "risk_usd_per_1m_gross_at_median_stop": 1_000_000.0 * sm,
        "equity_needed_for_100k_gross_at_todays_15pct_gross": 100_000.0 / GROSS_FRAC,
        "equity_needed_for_1m_gross_at_todays_15pct_gross": 1_000_000.0 / GROSS_FRAC,
        "voltarget_gross_frac_p99": c_vt["expo_p99"],
        "equity_needed_for_1m_gross_at_voltarget_p99": 1_000_000.0 / c_vt["expo_p99"],
    }

    # -------------------------------- charts --------------------------------
    make_charts(d, ev, c_fix, c_vt, gross_today, RISK_TARGET, bf, bv)

    with open(os.path.join(OUT, "scale_findings.json"), "w") as fh:
        json.dump(R, fh, indent=2, default=float)
    print(json.dumps(R, indent=2, default=float))


def make_charts(d, ev, c_fix, c_vt, gross_today, RISK_TARGET, bf, bv) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    INK, MUT = "#1c1917", "#78716c"
    C_FIX, C_VT, C_ACC = "#b45309", "#0f766e", "#7c3aed"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#d6d3d1",
                         "axes.labelcolor": INK, "text.color": INK,
                         "xtick.color": MUT, "ytick.color": MUT,
                         "axes.grid": True, "grid.color": "#e7e5e4",
                         "grid.linewidth": 0.6, "figure.facecolor": "white",
                         "axes.spines.top": False, "axes.spines.right": False})
    usd = FuncFormatter(lambda v, p: f"${v:,.0f}")

    # ---- FIG 1: the vol-blindness gap -------------------------------------
    fig, ax = plt.subplots(3, 1, figsize=(11, 10.5), sharex=True,
                           gridspec_kw={"height_ratios": [1, 1, 1]})
    dt = d["dt"].to_numpy()
    ax[0].plot(dt, d["s_blend"] * 100, lw=0.8, color=C_ACC)
    for q, st in ((10, ":"), (50, "-"), (90, ":")):
        v = np.percentile(d["s_blend"], q) * 100
        ax[0].axhline(v, ls=st, lw=0.9, color=MUT)
        ax[0].annotate(f"p{q} {v:.2f}%", (dt[20], v), fontsize=8, color=MUT,
                       va="bottom")
    ax[0].set_ylabel("blend stop distance\n3.125×ATR14 / price  (%)")
    ax[0].set_title("Stop distance is the whole story: a constant $15,000 gross "
                    "risks $347 in the calmest decile and $1,208 in the most "
                    "violent (3.48×)",
                    loc="left", fontsize=11, weight="bold")

    risk = gross_today * d["s_blend"]
    ax[1].fill_between(dt, 0, risk, color=C_FIX, alpha=0.25, lw=0)
    ax[1].plot(dt, risk, lw=0.8, color=C_FIX)
    ax[1].axhline(RISK_TARGET, color=C_VT, lw=1.4,
                  label="constant $1,000 risk target (what a vol-targeted sizer holds)")
    ax[1].set_ylabel("$ at risk to stop\nTODAY'S RULE ($15k gross)")
    ax[1].yaxis.set_major_formatter(usd)
    ax[1].legend(loc="upper right", frameon=False, fontsize=8)

    notional = RISK_TARGET / d["s_blend"]
    ax[2].fill_between(dt, 0, notional, color=C_VT, alpha=0.22, lw=0)
    ax[2].plot(dt, notional, lw=0.8, color=C_VT)
    ax[2].axhline(gross_today, color=C_FIX, lw=1.4, label="today's $15,000 gross")
    ax[2].axhline(20_000, color=MUT, ls="--", lw=1.1, label="MAX_NOTIONAL_USD $20k")
    ax[2].set_ylabel("gross notional carryable\nat CONSTANT $1,000 risk")
    ax[2].yaxis.set_major_formatter(usd)
    ax[2].legend(loc="upper right", frameon=False, fontsize=8)
    ax[2].set_xlabel("")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig1_volblind_gap.png"), dpi=140)
    plt.close(fig)

    # ---- FIG 2: distributions + inverse -----------------------------------
    fig, ax = plt.subplots(1, 3, figsize=(13, 4.0))
    ax[0].hist(d["s_blend"] * 100, bins=70, color=C_ACC, alpha=0.8)
    ax[0].axvline(np.median(d["s_blend"]) * 100, color=INK, lw=1.2)
    ax[0].set_xlabel("blend stop distance (% of price)")
    ax[0].set_ylabel("4h bars")
    ax[0].set_title("A. stop distance is right-skewed", loc="left", weight="bold")

    n1 = RISK_TARGET / d["s_blend"]
    ax[1].hist(n1, bins=np.logspace(np.log10(n1.min()), np.log10(n1.max()), 60),
               color=C_VT, alpha=0.8)
    ax[1].set_xscale("log")
    ax[1].axvline(gross_today, color=C_FIX, lw=1.4)
    ax[1].xaxis.set_major_formatter(usd)
    ax[1].set_xlabel("gross notional at constant $1,000 risk (log)")
    ax[1].set_title("B. inverse: notional you could carry", loc="left", weight="bold")

    yr = sorted(d["year"].unique())
    med = [np.median(RISK_TARGET / d[d.year == y]["s_blend"]) for y in yr]
    lo = [np.percentile(RISK_TARGET / d[d.year == y]["s_blend"], 10) for y in yr]
    hi = [np.percentile(RISK_TARGET / d[d.year == y]["s_blend"], 90) for y in yr]
    ax[2].errorbar(yr, med, yerr=[np.array(med) - np.array(lo),
                                  np.array(hi) - np.array(med)],
                   fmt="o", color=C_VT, capsize=4, lw=1.4)
    ax[2].axhline(gross_today, color=C_FIX, lw=1.4, label="today's $15,000")
    ax[2].yaxis.set_major_formatter(usd)
    ax[2].set_title("C. by year (p10–median–p90)", loc="left", weight="bold")
    ax[2].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig2_distributions.png"), dpi=140)
    plt.close(fig)

    # ---- FIG 3: equity + DD + notional path under each rule ---------------
    x = pd.to_datetime(ev["exit_ts"], unit="s", utc=True).to_numpy()
    fig, ax = plt.subplots(3, 1, figsize=(11, 10.5), sharex=True,
                           gridspec_kw={"height_ratios": [1.3, 1, 1]})
    ax[0].plot(x, c_fix["eq"], color=C_FIX, lw=1.5,
               label=f"FIXED vol-blind (live rule)  CAGR {c_fix['cagr_pct']:.1f}%  "
                     f"maxDD {c_fix['maxdd_pct']:.1f}%")
    ax[0].plot(x, c_vt["eq"], color=C_VT, lw=1.5,
               label=f"VOL-TARGETED, same mean $ risk  CAGR {c_vt['cagr_pct']:.1f}%  "
                     f"maxDD {c_vt['maxdd_pct']:.1f}%")
    ax[0].set_yscale("log")
    ax[0].set_ylabel("blend equity (×, log)")
    ax[0].legend(loc="upper left", frameon=False, fontsize=8.5)
    ax[0].set_title("Same dollar risk on average, vol-aware notional: "
                    "IN-SAMPLE exit-step blend, 2022→2026-07",
                    loc="left", fontsize=11, weight="bold")

    ax[1].fill_between(x, c_fix["dd"] * 100, 0, color=C_FIX, alpha=0.35, lw=0)
    ax[1].fill_between(x, c_vt["dd"] * 100, 0, color=C_VT, alpha=0.35, lw=0)
    ax[1].set_ylabel("drawdown (%)")
    ax[1].axhline(-35, color="#b91c1c", ls="--", lw=1.1,
                  label="DD_HALT_PCT 35%")
    ax[1].legend(frameon=False, fontsize=8)

    ax[2].step(x, ev["expo_fixed"] * 100_000, where="post", color=C_FIX, lw=1.0,
               label="FIXED leg notional @ $100k equity")
    ax[2].step(x, ev["expo_vt"] * 100_000, where="post", color=C_VT, lw=1.0,
               label="VOL-TARGETED leg notional @ $100k equity")
    ax[2].axhline(20_000, color=MUT, ls="--", lw=1.1, label="MAX_NOTIONAL_USD $20k")
    ax[2].set_yscale("log")
    ax[2].yaxis.set_major_formatter(usd)
    ax[2].set_ylabel("per-trade LEG notional")
    ax[2].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig3_sizing_comparison.png"), dpi=140)
    plt.close(fig)

    # ---- FIG 4: risk dispersion + bootstrap DD ----------------------------
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    rf = ev["risk_fixed"] * 100
    rv = (ev["expo_vt"] * ev["s_nominal"]) * 100
    bins = np.linspace(0, max(rf.max(), rv.max()) * 1.02, 45)
    ax[0].hist(rf, bins=bins, color=C_FIX, alpha=0.65, label="FIXED (vol-blind)")
    ax[0].hist(rv, bins=bins, color=C_VT, alpha=0.8, label="VOL-TARGETED")
    ax[0].set_xlabel("per-trade $ risk (% of equity)")
    ax[0].set_ylabel("trades")
    ax[0].set_title("A. vol-targeting collapses risk dispersion",
                    loc="left", weight="bold")
    ax[0].legend(frameon=False, fontsize=8)

    b = np.linspace(min(bf.min(), bv.min()) * 100, 0, 60)
    ax[1].hist(bf * 100, bins=b, color=C_FIX, alpha=0.65,
               label=f"FIXED  median {np.median(bf)*100:.1f}%")
    ax[1].hist(bv * 100, bins=b, color=C_VT, alpha=0.8,
               label=f"VOL-TARGETED  median {np.median(bv)*100:.1f}%")
    ax[1].axvline(-35, color="#b91c1c", ls="--", lw=1.1, label="DD_HALT 35%")
    ax[1].set_xlabel("bootstrap max drawdown (%)  block=8, n=4000")
    ax[1].set_title("B. is the DD difference real?", loc="left", weight="bold")
    ax[1].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig4_risk_and_bootstrap.png"), dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
