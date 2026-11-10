"""Every saved run: recompute the two rails from the saved per-bar arrays and
confirm (a) the saved margins are internally consistent, (b) no armed bar's
worst intrabar equity is below either line (the 'no executor halt' claim),
(c) the drawdown rail's closest approach per headline cell."""
import glob, json, os, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
BAR, DAY = 14400, 86400
def d(ts): return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))
bad = 0; rows = []
for f in sorted(glob.glob(os.path.join(STRESS, "runs", "*.json"))):
    r = json.load(open(f))
    ts = np.asarray(r["ts"]); tot = np.asarray(r["equity_total"]); w = np.asarray(r["worst_intrabar_equity"])
    ds = np.asarray(r["day_start"]); md = np.asarray(r["margin_daily"]); mdd = np.asarray(r["margin_drawdown"]); armed = np.asarray(r["rails_armed"])
    dpct = r["daily_loss_pct"]
    # (a) daily margin == worst - (day_start - dpct*base)
    e1 = np.abs(md - (w - (ds - dpct * 1e5))).max()
    # day_start changes only at 00:00 bars (and the seed)
    chg = [j for j in range(1, len(ts)) if ds[j] != ds[j - 1]]
    e2 = all(ts[j] % DAY == 0 for j in chg)
    # (b) implied HW from the saved dd margin: hw_j = worst - margin + 30k; must be >= running max of closes up to j-1 and of start 100k, and non-decreasing
    hw = w - mdd + 30000.0
    run_peak = np.maximum.accumulate(np.concatenate([[100000.0], tot]))[:-1]
    e3 = (hw + 1e-6 >= run_peak).all() and (np.diff(hw) >= -1e-6).all()
    # (c) no armed bar below a line
    min_md = md[armed].min(); min_mdd = mdd[armed].min()
    e4 = min_md > 0 and min_mdd > 0 and r["halts_count"] == 0
    # worst intrabar equity never above the close
    e5 = (w <= tot + 1e-6).all()
    ok = e1 < 0.02 and e2 and e3 and e4 and e5
    bad += (not ok)
    rows.append((os.path.basename(f)[:48], round(e1, 4), e2, bool(e3), bool(e4), bool(e5), round(float(min_md)), round(float(min_mdd)), d(int(ts[armed][np.argmin(mdd[armed])])), round(float(hw[armed][np.argmin(mdd[armed])])), round(float(w[armed][np.argmin(mdd[armed])]))))
for row in rows: print(*row)
print("runs", len(rows), "inconsistent", bad)
