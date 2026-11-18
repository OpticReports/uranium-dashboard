"""Tape construction and causal indicator helpers for the B.5 overlay study."""
import os, pickle
import numpy as np, pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
LAB = os.path.dirname(os.path.dirname(STUDY))
CACHE = os.environ.get("B5_CACHE", os.path.join(STUDY, "_cache"))
BT = yaml.safe_load(open(f"{LAB}/config/backtest.yaml"))

LEGS = ["AVUV", "PHYS", "QUAL", "KMLM", "AVDV", "AVEM", "TAIL"]
COLS = LEGS + ["BIL"]
BASE = np.array([0.235, 0.235, 0.153, 0.141, 0.118, 0.059, 0.059, 0.0])
assert abs(BASE.sum() - 1) < 1e-12
RISK = ["AVUV", "AVDV", "AVEM", "QUAL", "PHYS"]
EQ = ["AVUV", "AVDV", "AVEM", "QUAL"]
HEDGE = ["KMLM", "TAIL"]
IX = {l: i for i, l in enumerate(COLS)}
COST = np.array([BT["costs_bps"][l] for l in LEGS] + [1.0]) / 1e4
BAND = float(BT["rebalance"]["band_relative"]); CAL_DAYS = 252
TAPE_START = pd.Timestamp("2005-01-03")
EXT0 = pd.Timestamp("2007-06-01"); CONF0 = pd.Timestamp("2017-04-07")
SPLICE = {"AVUV": ("DFSVX", "2019-10-01"), "AVDV": ("DISVX", "2019-10-01"), "AVEM": ("DFEMX", "2019-10-01"),
          "PHYS": ("GLD", "2010-03-01")}
VOLSRC = {"AVUV": ["IWN", "AVUV"], "AVDV": ["EFA", "SCZ", "AVDV"], "AVEM": ["EEM", "AVEM"], "QUAL": ["SPY", "QUAL"],
          "PHYS": ["GLD", "PHYS"]}


def load_panel():
    return pickle.load(open(os.path.join(CACHE, "panel.pkl"), "rb"))


def cash_series(p, cal):
    """BIL from its first return; before that DTB3 accrued daily (lagged one day)."""
    bil = p["ret"]["BIL"].reindex(cal)
    d = p["fred"]["DTB3"]
    full = p["cal"]
    y = d.reindex(full.union(d.index)).ffill().reindex(full).shift(1).reindex(cal)
    syn = (1 + y / 100.0) ** (1 / 252.0) - 1
    out = bil.where(bil.notna(), syn)
    src = pd.Series(np.where(bil.notna(), "BIL", "DTB3"), index=cal)
    return out, src


def tail_model(p, cal):
    """D1: TAIL = b*IEF + c*(PPUT - SPXTR), no intercept, OLS on real TAIL days; returns (series, fit dict)."""
    r = p["ret"]
    pl = (1 + r["PPUT"].fillna(0)).cumprod()                    # PPUT has a few missing days: use its own dates
    obs = r["PPUT"].dropna().index
    sp = (1 + r["^SP500TR"].fillna(0)).cumprod()
    ov = (pl.reindex(obs).pct_change() - sp.reindex(obs).pct_change()).reindex(cal).fillna(0.0)
    ief = r["IEF"].reindex(cal)
    y = r["TAIL"].reindex(cal)
    m = y.notna() & ief.notna()
    X = np.column_stack([ief[m].values, ov[m].values])
    beta, *_ = np.linalg.lstsq(X, y[m].values, rcond=None)
    fit = pd.Series(X @ beta, index=y[m].index)
    mod = beta[0] * ief + beta[1] * ov
    info = dict(b_ief=float(beta[0]), c_put=float(beta[1]), n=int(m.sum()),
                r2=float(1 - ((y[m] - fit) ** 2).sum() / ((y[m] - y[m].mean()) ** 2).sum()),
                corr_daily=float(np.corrcoef(fit.values, y[m].values)[0, 1]),
                ann_ret_real=float((1 + y[m]).prod() ** (252 / m.sum()) - 1),
                ann_ret_model=float((1 + fit).prod() ** (252 / m.sum()) - 1))
    return mod, info


def build_tape(p, variant="T1", start=TAPE_START):
    """Leg returns with config proxies + study stand-ins. variant T1 (registered) or T2 (strong hedge, D1)."""
    r = p["ret"]; cal = p["cal"][(p["cal"] >= start) & (p["cal"] <= p["end"])]
    cash, csrc = cash_series(p, cal)
    R = pd.DataFrame(index=cal, columns=COLS, dtype=float); S = pd.DataFrame(index=cal, columns=COLS, dtype=object)
    for leg, (px, sd) in SPLICE.items():
        live = r[leg].reindex(cal); pr = r[px].reindex(cal)
        use = (cal >= pd.Timestamp(sd)) & live.notna().values
        R[leg] = np.where(use, live, pr); S[leg] = np.where(use, leg, px)
    q = r["QUAL"].reindex(cal); spy = r["SPY"].reindex(cal)
    R["QUAL"] = np.where(q.notna(), q, spy); S["QUAL"] = np.where(q.notna(), "QUAL", "SPY")
    k = r["KMLM"].reindex(cal); a = r["ASFYX"].reindex(cal); ry = r["RYMFX"].reindex(cal)
    ry_use = ry if variant == "T1" else cash + 2.0 * (ry - cash)
    km = np.where(k.notna(), k, np.where(a.notna(), a, np.where(ry.notna(), ry_use, cash)))
    R["KMLM"] = km
    S["KMLM"] = np.where(k.notna(), "KMLM", np.where(a.notna(), "ASFYX", np.where(ry.notna(),
                         "RYMFX" if variant == "T1" else "2xRYMFX", "cash")))
    t = r["TAIL"].reindex(cal)
    info = None
    if variant == "T1":
        R["TAIL"] = np.where(t.notna(), t, cash); S["TAIL"] = np.where(t.notna(), "TAIL", "cash")
    else:
        mod, info = tail_model(p, cal)
        R["TAIL"] = np.where(t.notna(), t, mod); S["TAIL"] = np.where(t.notna(), "TAIL", "model")
    R["BIL"] = cash; S["BIL"] = csrc
    if R.isna().any().any():
        raise RuntimeError(f"NaN in tape: {R.isna().sum().to_dict()}")
    me = np.zeros(len(cal), bool)
    ym = cal.year * 12 + cal.month
    me[:-1] = ym[1:] != ym[:-1]                                   # last trading day of each completed month
    return dict(cal=cal, R=R, S=S, me=me, tail_fit=info, variant=variant)


# ---------- causal indicator helpers (value at t uses data <= t) ----------
def sma(x, n):
    return x.rolling(n, min_periods=n).mean()


def rsi(px, n=14):
    d = px.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + g / l)


def monthly_hold(cond, me):
    """cond evaluated on month-end days, held until the next month-end; 1.0 (invested) before the first valid one."""
    c = cond.astype(float).where(cond.notna())
    c = c.where(pd.Series(me, index=cond.index))
    return c.ffill().fillna(1.0)


def latch(on_to_off, off_to_on, init=1.0, off_val=0.0):
    """State machine: from ON go OFF when on_to_off[t]; from OFF go ON when off_to_on[t]. NaN conditions = False."""
    a = np.nan_to_num(np.asarray(on_to_off, float)) > 0; b = np.nan_to_num(np.asarray(off_to_on, float)) > 0
    out = np.empty(len(a)); st = init
    for t in range(len(a)):
        if st == init:
            if a[t]:
                st = off_val
        elif b[t]:
            st = init
        out[t] = st
    return out


def stop_state(px, dist, sma100=None, timeout=0):
    """Trailing stop. px, dist (fractional stop distance, scalar or array). Exit when px < peak*(1-dist).
    Re-entry (D11): timeout>0 -> after `timeout` days out; else fresh upward cross of SMA100 (px <= SMA at some
    point since exit, then px > SMA) or px > exit peak. Peak resets to px at re-entry."""
    px = np.asarray(px, float); n = len(px)
    dist = np.full(n, dist) if np.isscalar(dist) else np.nan_to_num(np.asarray(dist, float), nan=1e9)
    sm = None if sma100 is None else np.asarray(sma100, float)
    out = np.ones(n); st = 1; peak = px[0]; out_days = 0; was_below = False; exit_peak = 0.0
    for t in range(n):
        if st == 1:
            if px[t] > peak:
                peak = px[t]
            if px[t] < peak * (1 - dist[t]):
                st = 0; out_days = 0; exit_peak = peak
                was_below = sm is not None and not np.isnan(sm[t]) and px[t] <= sm[t]
        else:
            out_days += 1
            if timeout > 0:
                if out_days >= timeout:
                    st = 1; peak = px[t]
            else:
                if not np.isnan(sm[t]) and px[t] <= sm[t]:
                    was_below = True
                if (was_below and not np.isnan(sm[t]) and px[t] > sm[t]) or px[t] > exit_peak:
                    st = 1; peak = px[t]
        out[t] = st
    return out


def fred_daily(p, sid, cal, lag):
    s = p["fred"][sid]; full = p["cal"]
    return s.reindex(full.union(s.index)).ffill().reindex(full).shift(lag).reindex(cal)


def monthly_avail(flag, cal, months=None, day=None):
    """Map a month-labelled boolean (index = any day in the reference month) onto the calendar.
    months=k: usable from the 1st of month M+k. day=d: usable from the d-th of month M+1."""
    lab = flag.index.to_period("M").to_timestamp()
    if months is not None:
        av = lab + pd.DateOffset(months=months)
    else:
        av = lab + pd.DateOffset(months=1) + pd.Timedelta(days=day - 1)
    s = pd.Series(flag.values.astype(float), index=av)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(cal.union(s.index)).ffill().reindex(cal)
