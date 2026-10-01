"""Casey 2026-10-01: "the early years of BTC don't matter, completely different
market size and regime - need a fair comparison." Re-judges every Sharpe-study
candidate on modern windows only (2019+ and 2020+), and re-derives the size
that fits -30% on those windows. The window choice is Casey's, made AFTER the
2013+ results were seen - recorded as such in RESEARCH_SHARPE.md.
python3 modern.py -> modern.json"""
import csv, json, os, sys, datetime as dt
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sharpe_lib as S, run as R                                    # noqa: E402
H = S.H
END = "2026-07-31"
W = S.World()

rows = [r for r in csv.reader(open(os.path.join(HERE, "data", "dtb3.csv")))][1:]
TB = {}
for d, v in rows:
    if v not in ("", "."): TB[d] = float(v)
def tbill_daily(days):                     # $ per day on $30k, last known DTB3
    keys = sorted(TB); out = []; j = 0; last = TB[keys[0]]
    for d in days:
        ds = dt.datetime.utcfromtimestamp(int(d) * 86400).strftime("%Y-%m-%d")
        while j < len(keys) and keys[j] < ds: last = TB[keys[j]]; j += 1
        out.append(last / 100 * 30_000 / 365)
    return np.array(out)

def acct(spec, a, m_hi=None):
    old = S.M_HI
    if m_hi is not None: S.M_HI = m_hi
    try: return R.account(W, spec, a, END)
    finally: S.M_HI = old

def years_beaten(base, x):
    yy = np.array([dt.datetime.utcfromtimestamp(int(d) * 86400).year for d in base["days"]])
    ys = sorted(set(yy)); n = 0
    for y in ys:
        m = yy == y
        if S.sharpe(x["d"][m]) > S.sharpe(base["d"][m]): n += 1
    return f"{n}/{len(ys)}"

CFG = {"live engine": (set(), None), "H1 vol-target (registered)": ({"vol"}, None),
       "H1 down-only": ({"vol"}, 1.0), "H2 200d gate": ({"gate"}, None),
       "H3a carry static": ({"carry_s"}, None), "H3b carry gated": ({"carry_g"}, None),
       "H1 down-only + H3a": ({"vol", "carry_s"}, 1.0)}
out = {}
for st in ("2019-01-01", "2020-01-01"):
    base = acct(set(), st)
    tb = tbill_daily(base["days"])
    out[st] = {}
    for name, (spec, mh) in CFG.items():
        x = acct(spec, st, mh)
        lo, hi = S.boot_delta(base["d"], x["d"])
        r = dict(sharpe=x["sharpe"], d_sharpe=x["sharpe"] - base["sharpe"], ci90=(lo, hi),
                 per_yr=x["per_yr"], maxdd=x["maxdd"], years_beaten=years_beaten(base, x))
        if "carry" in "".join(spec):   # versus the same $30k in T-bills
            bt = base["d"] + tb
            l2, h2 = S.boot_delta(bt, x["d"])
            r["vs_tbill"] = dict(base_plus_tbill_sharpe=S.sharpe(bt), d=x["sharpe"] - S.sharpe(bt), ci90=(l2, h2))
        out[st][name] = r
        print(f"{st[:4]}+ {name:28s} Sharpe {x['sharpe']:.2f} (d {r['d_sharpe']:+.2f} [{lo:+.2f},{hi:+.2f}]) "
              f"${x['per_yr']:>7,.0f}/yr DD ${x['maxdd']:>8,.0f} yrs {r['years_beaten']}"
              + (f" | vs T-bill d {r['vs_tbill']['d']:+.2f} [{r['vs_tbill']['ci90'][0]:+.2f},{r['vs_tbill']['ci90'][1]:+.2f}]" if "vs_tbill" in r else ""), flush=True)

# size that fits -$30k on the modern windows (fixed $100k base), and what it costs
def sized(spec, st, k, m_hi=None):
    old = S.M_HI
    if m_hi is not None: S.M_HI = m_hi
    try:
        t0, t1 = S.ts_of(st), S.ts_of(END) + 86399
        r = H.simulate(W.legs(t0, t1, vol="vol" in spec), W.closes, k=k, start_ts=t0, end_ts=t1,
                       fixed_base=S.BASE, start_equity=S.BASE)
    finally: S.M_HI = old
    pnl = r.equity - S.BASE
    eq = np.concatenate([[S.BASE], r.equity]); day = r.ts // 86400; brk = 0
    for d in np.unique(day):
        idx = np.where(day == d)[0]
        if eq[idx[0]] - eq[idx + 1].min() > 6000: brk += 1
    yrs = (r.ts[-1] - r.ts[0] + H.BAR_S) / (365.25 * 86400)
    _, dd = S.daily_pnl(r.ts, pnl)
    return dict(k=k, per_yr=float(pnl[-1] / yrs), maxdd=S.max_dd_usd(pnl), daily_loss_halts=brk,
                sharpe=S.sharpe(dd), peak_gross=float(np.nanmax(r.gross_lev * r.equity)))
def k30(spec, st, m_hi=None):
    lo, hi = 0.05, 3.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if sized(spec, st, mid, m_hi)["maxdd"] >= -30_000: lo = mid
        else: hi = mid
    return lo
out["sizing"] = {}
for st in ("2019-01-01", "2020-01-01"):
    for name, spec, mh in [("live engine", set(), None), ("H1 down-only", {"vol"}, 1.0)]:
        kk = k30(spec, st, mh)
        rows_ = {"0.30 (today)": sized(spec, st, 0.30, mh), "k at -$30k": sized(spec, st, kk, mh)}
        out["sizing"][f"{st[:4]}+ {name}"] = rows_
        for lab, v in rows_.items():
            print(f"SIZE {st[:4]}+ {name:14s} {lab:13s} k {v['k']:.2f}  ${v['per_yr']:>7,.0f}/yr  DD ${v['maxdd']:>8,.0f}  "
                  f"daily>$6k {v['daily_loss_halts']}  peak gross ${v['peak_gross']:,.0f}", flush=True)
json.dump(out, open(os.path.join(HERE, "modern.json"), "w"), indent=1, default=float)

# bootstrap-safe size (the CAGR study's criterion: P(maxDD > 30% over any
# 2 years) <= 10%), because sizing to the window's own worst drawdown is
# in-sample by construction - the next worst will be worse.
out["k_safe"] = {}
for st in ("2019-01-01", "2020-01-01"):
    for name, spec, mh in [("live engine", set(), None), ("H1 down-only", {"vol"}, 1.0)]:
        old = S.M_HI
        if mh is not None: S.M_HI = mh
        try:
            t0, t1 = S.ts_of(st), S.ts_of(END) + 86399
            r1 = H.simulate(W.legs(t0, t1, vol="vol" in spec), W.closes, k=1.0, start_ts=t0, end_ts=t1)
        finally: S.M_HI = old
        path = np.concatenate([[r1.start_equity], r1.equity])
        ks, meta = H.k_safe(np.diff(path) / path[:-1])
        v = sized(spec, st, ks, mh)
        out["k_safe"][f"{st[:4]}+ {name}"] = v
        print(f"KSAFE {st[:4]}+ {name:14s} k {ks:.2f}  ${v['per_yr']:>7,.0f}/yr  realised DD ${v['maxdd']:>8,.0f}  "
              f"daily>$6k {v['daily_loss_halts']}  peak gross ${v['peak_gross']:,.0f}", flush=True)
json.dump(out, open(os.path.join(HERE, "modern.json"), "w"), indent=1, default=float)
