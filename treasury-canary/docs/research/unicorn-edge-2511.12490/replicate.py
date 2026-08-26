"""Unicorn Edge (arXiv 2511.12490) replication — the pre-registered sin ladder.

Registered protocol: treasury-canary/docs/research/unicorn-edge-2511.12490/
REPLICATION_PREREGISTRATION.md (commit eb4b62a, BEFORE this file existed).
Ladder extension registered there: the adjusted-price look-ahead rung
(1/price on split-adjusted prices makes future splitters look cheap early).

Interpretive choices the paper leaves open (fixed here, stated in the memo):
- weights proportional to |z| within each side, sides normalized to 0.5;
- value rank computed across the full valid universe, then gated;
- UpFraction over r_{t-1}..r_{t-63} (Eq. 2 excludes day t);
- test windows approximated as calendar 2010/2015/2020 (the paper's own
  window dating is internally ambiguous);
- costs charged as cost_per_unit * sum|w_t - w_{t-1}|.
"""
import glob
import os
import numpy as np
import pandas as pd

SC = os.path.dirname(os.path.abspath(__file__))


def load_panel(sub, col):
    frames = {}
    for f in sorted(glob.glob(f"{SC}/{sub}/*.csv")):
        sym = os.path.basename(f)[:-4]
        try:
            df = pd.read_csv(f, parse_dates=["date"]).set_index("date")
            if col in df.columns:
                frames[sym] = df[col]
        except Exception:
            continue
    p = pd.DataFrame(frames).sort_index()
    return p[(p.index >= "2004-01-01") & (p.index <= "2024-12-31")]


def build_signals(P_sig, R):
    """EDGE matrix from a signal-price panel and the return panel."""
    value_rank = (1.0 / P_sig).rank(axis=1, pct=True)
    rev = -(P_sig / P_sig.shift(10) - 1.0)
    rev_z = rev.sub(rev.mean(axis=1), axis=0).div(rev.std(axis=1), axis=0)
    base = 0.7 * value_rank + 0.3 * rev_z
    pos_day = (R > 0).astype(float).where(R.notna())
    upfrac = pos_day.shift(1).rolling(63, min_periods=63).mean()
    regime = upfrac > 0.60
    return base.where(regime), regime


def build_weights(edge):
    z = edge.sub(edge.mean(axis=1), axis=0).div(edge.std(axis=1), axis=0)
    lng = z.clip(lower=0.0)
    sht = (-z).clip(lower=0.0)
    lsum = lng.sum(axis=1)
    ssum = sht.sum(axis=1)
    w = 0.5 * lng.div(lsum.replace(0, np.nan), axis=0) \
        - 0.5 * sht.div(ssum.replace(0, np.nan), axis=0)
    return w.fillna(0.0)


def run(w, R, lag, cost_per_unit, label):
    """weights known at close t; fills at close t+lag; earn R_{t+lag+1}."""
    wl = w.shift(lag)
    gross = (wl * R.shift(-1)).sum(axis=1).shift(1)  # align: w_t*R_{t+1} at t+1
    to = (wl - wl.shift(1)).abs().sum(axis=1)
    net = gross - to.shift(1).fillna(0.0) * cost_per_unit
    net = net.dropna()
    net = net[net.index >= "2006-01-03"]              # warm-up burn
    return {"label": label, "ret": net, "turnover": to.mean()}


def metrics(ret, name, years=None):
    r = ret if years is None else ret[ret.index.year.isin(years)]
    if len(r) < 50:
        return None
    mu, sd = r.mean(), r.std()
    curve = (1 + r).cumprod()
    dd = (curve / curve.cummax() - 1).min()
    return {"window": name, "sharpe": round(mu / sd * np.sqrt(252), 2),
            "ann_ret_arith": round(mu * 252 * 100, 1),
            "cagr": round((curve.iloc[-1] ** (252 / len(r)) - 1) * 100, 1),
            "vol": round(sd * np.sqrt(252) * 100, 1),
            "maxDD": round(dd * 100, 1),
            "median_daily": round(np.median(r) * 100, 3), "days": len(r)}


if __name__ == "__main__":
    P_div = load_panel("prices_div", "adjClose")  # split+dividend adjusted
    # non-split-adjusted endpoint also names its price field adjClose;
    # the VALUES are true traded closes (AAPL Jan-2004 = 21.28, pre-splits)
    P_raw = load_panel("prices_raw", "adjClose")
    print(f"panel: {P_div.shape[1]} symbols x {len(P_div)} days")
    R = P_div.pct_change(fill_method=None)
    R = R.where(R.abs() < 1.0)                     # guard data errors

    edge_adj, regime = build_signals(P_div, R)
    edge_raw, _ = build_signals(P_raw, R)
    w_adj = build_weights(edge_adj)
    w_raw = build_weights(edge_raw)

    census = regime.sum(axis=1) / regime.notna().sum(axis=1).replace(0, np.nan)
    print(f"regime census: mean {census.mean():.1%}  "
          f"2008-11 {census.loc['2008-11'].mean():.1%}  "
          f"2021-03 {census.loc['2021-03'].mean():.1%}")

    ladder = [
        run(w_adj, R, 0, 0.00006, "L0 paper-likely (adj-price signal, same-close, 0.6bp)"),
        run(w_raw, R, 0, 0.00006, "L0b true-price signal, same-close, 0.6bp"),
        run(w_adj, R, 1, 0.00006, "L1 adj-price signal, t+1-close fill, 0.6bp"),
        run(w_raw, R, 1, 0.00006, "L1b true-price signal, t+1-close fill, 0.6bp"),
        run(w_raw, R, 1, 0.00035, "L2 honest: true price, t+1 fill, 3.5bp"),
    ]
    # open-fill variant (open-to-open marks, split-adjusted opens from the
    # /full endpoint; dividend-blind — flagged in the memo)
    try:
        O_full = load_panel("prices_full", "open")
        Ro = O_full.pct_change(fill_method=None)
        Ro = Ro.where(Ro.abs() < 1.0)
        ladder.append(run(w_raw, Ro, 1, 0.00035,
                          "L2o honest, t+1-OPEN fill (open-to-open)"))
    except Exception as exc:
        print("open-fill rung skipped:", exc)

    rows, peryear = [], {}
    for lad in ladder:
        m = metrics(lad["ret"], "FULL 2006-2024")
        m["label"] = lad["label"]
        m["avg_turnover"] = round(lad["turnover"], 2)
        rows.append(m)
        t3 = metrics(lad["ret"], "their-3-windows", years=[2010, 2015, 2020])
        rows.append({**t3, "label": "   ... windows 2010/2015/2020"})
        peryear[lad["label"]] = lad["ret"].groupby(lad["ret"].index.year).apply(
            lambda r: round(r.mean() / r.std() * np.sqrt(252), 1))
    out = pd.DataFrame(rows)[["label", "window", "sharpe", "ann_ret_arith",
                              "cagr", "vol", "maxDD", "median_daily",
                              "avg_turnover", "days"]]
    print(out.to_string(index=False))
    py = pd.DataFrame(peryear)
    py.to_csv(f"{SC}/per_year_sharpe.csv")
    print("\nper-year Sharpe:")
    print(py.to_string())
    for lad in ladder:
        lad["ret"].to_csv(f"{SC}/ret_{lad['label'][:3].strip().replace(' ', '')}.csv")
