"""Counter-agent (ruin/implementation lens): live-like fixed-base replay with
executor halts, H2a blend range, gap/crash exposure. Read-only research."""
import sys, os, time, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import numpy as np
import harness as H, candidates as C

W = C.World()
bars = W.bars["btcusd"]; by = {b.ts: b for b in bars}
BASE = 100_000.0; F = 4.32e-4
d = lambda t: time.strftime("%Y-%m-%d %H", time.gmtime(t))

def live_sim(legs, k, t0, t1, dd_halt=0.30, daily=0.06, stop_on_halt=True, compound=False, basis="extreme"):
    """Fixed-base sizing (live) unless compound. MTM at close and at the bar's
    adverse extreme (low for longs / high for shorts). Breach tests use the
    extreme (the executor polls every 20s, so intrabar breaches are seen).
    stop_on_halt: first DRAWDOWN, or DAILY_LOSS when k>0.30 (manual resume),
    flattens at the extreme and freezes the book."""
    ent, ext = {}, {}
    for li, lg in enumerate(legs):
        for t in lg.trades:
            if t.entry_ts < t0 or t.entry_ts > t1: continue
            ent.setdefault(t.entry_ts, []).append((li, t))
            if t.exit_ts is not None and t.exit_ts <= t1:
                ext.setdefault(t.exit_ts, []).append((li, t))
    cash = BASE; op = {}; eqc = []; hwm = BASE; day = None; dstart = BASE
    dd_ev, dl_ev = [], []; halted = None; worst = (0.0, None); gmax = 0.0
    last_day_hit = None
    ts_list = sorted(t for t in by if t0 <= t <= t1)
    for ts in ts_list:
        b = by[ts]
        prev = eqc[-1] if eqc else BASE
        dk = ts // 86400
        if dk != day:
            day = dk; dstart = prev
        if halted is None:
            for li, t in ext.get(ts, []):
                p = op.pop((li, t.entry_ts), None)
                if p is None: continue
                q, s, ep = p
                cash += q*(t.exit_price-ep)*s - F*q*t.exit_price
            e_now = cash + sum(q*(b.open-ep)*s for q, s, ep in op.values())
            for li, t in ent.get(ts, []):
                lg = legs[li]
                w = lg.weight_fn(t.entry_ts) if lg.weight_fn else lg.weight
                n = w*k*(e_now if compound else BASE)
                cash -= F*n
                op[(li, t.entry_ts)] = (n/t.entry_price, 1 if t.side == "L" else -1, t.entry_price)
        ex = cash + sum(q*(((b.low if s > 0 else b.high) if basis == "extreme" else b.close)-ep)*s for q, s, ep in op.values())
        ec = cash + sum(q*(b.close-ep)*s for q, s, ep in op.values())
        g = sum(q*b.close for q, s, ep in op.values()); gmax = max(gmax, g/ max(ec, 1))
        if ex - prev < worst[0]: worst = (ex - prev, ts)
        if op and halted is None:
            base_h = (hwm if compound else BASE)
            if ex < hwm - dd_halt*base_h:
                dd_ev.append((d(ts), round(ex-hwm)))
                if stop_on_halt:
                    halted = "DD"
            if ex < dstart - daily*(prev if compound else BASE) and last_day_hit != dk:
                dl_ev.append((d(ts), round(ex-dstart))); last_day_hit = dk
                if stop_on_halt and k > 0.30:
                    halted = halted or "DAILY"
            if halted:
                cash = ex - F*g; op = {}; ec = cash
        hwm = max(hwm, ec)
        eqc.append(ec)
    path = np.concatenate([[BASE], np.array(eqc)])
    pk = np.maximum.accumulate(path)
    yrs = (ts_list[-1]-ts_list[0]+H.BAR_S)/(365.25*86400)
    tot = path[-1]/BASE
    return dict(final=round(path[-1]), cagr=round((tot**(1/yrs)-1)*100, 2) if tot > 0 else -100.0,
                maxdd_pct=round(((path/pk)-1).min()*100, 1), maxdd_usd=round((path-pk).min()),
                worst_bar_usd=round(worst[0]), worst_bar=d(worst[1]) if worst[1] else None,
                peak_gross_x=round(gmax, 2), halted=halted,
                n_dd=len(dd_ev), dd_first=dd_ev[:1], n_daily=len(dl_ev), daily_first=dl_ev[:6])

if __name__ == "__main__":
    END = H.ts_of("2026-09-28")
    WIN = {"FULL13": (H.ts_of("2013-01-01"), END), "2019+": (H.ts_of("2019-01-01"), END),
           "E5+E6 2024H2-": (H.ts_of("2024-07-01"), END)}
    out = {}
    for name in ["baseline", "H5a H1+H2a", "H5b H1+H2b"]:
        for wn, (t0, t1) in WIN.items():
            legs, _ = C.CANDIDATES[name](W, t0, t1)
            for k in (0.20, 0.30, 0.39, 0.45):
                for mode in ("count", "halt"):
                    r = live_sim(legs, k, t0, t1, stop_on_halt=(mode == "halt"))
                    print(name, wn, k, mode, json.dumps(r), flush=True)
            rc = live_sim(legs, 0.45, t0, t1, stop_on_halt=False, compound=True)
            print(name, wn, 0.45, "COMPOUND", json.dumps(rc), flush=True)
