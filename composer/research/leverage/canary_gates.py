"""Treasury-canary signals as leverage gates (add. 43 candidate; research pass, no live change).

Owner question (2026-10-17): EMAs, CAPE levels, bond yields, retail leverage (margin debt) and the
other things the canary tracks — is any of them an EV+ gate for when to turn leverage off?

Same engine as levgate.py (same 1x twins, costs, cached HG/KMLM holdings).  Every gate is applied
to HG's five trend baskets only (add. 42: never gate the dip-buys) and tested three ways:
  alone       the canary signal is the gate (1 = leveraged, 0 = 1x)
  & 200d      leveraged only when the signal AND SPY>200d agree (does it ADD to the 200d gate?)
  -> 200d     the 200d gate is applied only while the signal says risk (macro conditioning,
              add. 40's mirror design); its mirror applies it only while the signal says safe.
Point in time: daily market series lagged one session (Treasury/NY Fed/OFR publish after the
15:50 trade); FINRA month m used from the first session of month m+2; CAPE with a two-month lag;
leading stack month m from m+2.  Before a series exists the gate is on (as built); each row also
reports the window from the series' first usable date.
Nulls per signal: inverse, 100 monthly re-dated placebos, paired 20-day-block bootstrap of the
Sharpe gap vs as built AND vs the 200d gate alone.  Output: LEVGATE_DATA/canary_gates.json.
"""
import bisect
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levgate as lg                       # noqa: E402
from levgate import OUT, gate_run, leg_sets, metrics, placebo, inverse, ma_series, vol_series, WINDOWS_B, COST, book   # noqa: E402
from replay import yh                      # noqa: E402

CD = os.path.join(OUT, 'canary')


def load(name):
    p = os.path.join(CD, f'{name}.json')
    return json.load(open(p)) if os.path.exists(p) else None


def ema(px, n):
    ds, a, out, e = sorted(px), 2.0 / (n + 1), {}, None
    for i, d in enumerate(ds):
        e = px[d] if e is None else a * px[d] + (1 - a) * e
        if i >= n:
            out[d] = e
    return out


def lagged(ser, days, k=1):
    """value known at the decision close days[i]: last observation dated <= days[i-k]."""
    ks = sorted(ser)
    out = {}
    for i, d in enumerate(days):
        j = i - k
        if j < 0:
            continue
        p = bisect.bisect_right(ks, days[j]) - 1
        if p >= 0:
            out[d] = ser[ks[p]]
    return out


def monthly_known(mser, days, lag_months):
    """monthly {YYYY-MM: v}: month m usable from the first session of month m+lag_months."""
    out = {}
    for d in days:
        y, m = int(d[:4]), int(d[5:7]) - lag_months
        while m < 1:
            y, m = y - 1, m + 12
        k = f'{y:04d}-{m:02d}'
        if k in mser:
            out[d] = mser[k]
    return out


def month_end(px):
    out = {}
    for d in sorted(px):
        out[d[:7]] = px[d]
    return out


def yoy_m(mser):
    out = {}
    for k, v in mser.items():
        y, m = int(k[:4]), int(k[5:7])
        k0 = f'{y - 1:04d}-{m:02d}'
        if k0 in mser and mser[k0]:
            out[k] = v / mser[k0] - 1
    return out


def flag(days, cond):
    return {d: (1.0 if cond(d) else 0.0) for d in days}


def build(P, days):
    """{name: (lam, first_usable_date, current_reading)} — lam 1 = leveraged."""
    spy = P['SPY']
    ma200 = ma_series(spy, 200)
    F, first = {}, {}
    on = lambda s, d: d not in s   # noqa: E731
    F['T200 SPY>200d (reference)'] = flag(days, lambda d: on(ma200, d) or spy[d] > ma200[d])
    # 1. EMAs
    for n in (50, 100, 200):
        e = ema(spy, n)
        F[f'EMA{n} SPY>EMA{n}'] = flag(days, lambda d, e=e: on(e, d) or spy[d] > e[d])
    e50, e200 = ema(spy, 50), ema(spy, 200)
    F['EMAx EMA50>EMA200'] = flag(days, lambda d: on(e200, d) or e50[d] > e200[d])
    # 2. CAPE levels (two-month lag)
    cape = monthly_known(json.load(open(os.path.join(lg.MAC, 'cape_multpl.json'))), days, 2)
    for lv in (25, 30, 35):
        F[f'CAPE<{lv}'] = flag(days, lambda d, lv=lv: on(cape, d) or cape[d] < lv)
    # 3. bond yields (Treasury par / real curves, NY Fed ACM), one-session lag
    y10, y2 = lagged(load('UST_10Y'), days), lagged(load('UST_2Y'), days)
    tips, acm = lagged(load('TIPS_10Y'), days), lagged(load('ACM_TP10'), days)
    idx = {d: i for i, d in enumerate(days)}

    def chg(ser, d, n):
        i = idx[d]
        return (ser[d] - ser[days[i - n]]) if (i >= n and d in ser and days[i - n] in ser) else None
    for lv in (5.0, 6.0):
        F[f'Y10<{lv:.0f}% 10y yield level'] = flag(days, lambda d, lv=lv: on(y10, d) or y10[d] < lv)
    for bp in (1.0, 1.5):
        F[f'dY10<+{bp:.1f}pp 10y 12m change'] = flag(days, lambda d, bp=bp: (chg(y10, d, 252) is None) or chg(y10, d, 252) < bp)
    for bp in (1.5, 2.0):
        F[f'dY2<+{bp:.1f}pp 2y 12m change (Fed pace)'] = flag(days, lambda d, bp=bp: (chg(y2, d, 252) is None) or chg(y2, d, 252) < bp)
    F['TIPS10<2% real yield'] = flag(days, lambda d: on(tips, d) or tips[d] < 2.0)
    F['dTP<+0.5pp ACM term premium 6m change'] = flag(days, lambda d: (chg(acm, d, 126) is None) or chg(acm, d, 126) < 0.5)
    # 4. curve: the canary's headline re-steepening window (monthly 3m10y, sustained inversion = 3+ months)
    u3 = load('UST_3M')
    sp_m = {}
    for d, v in load('UST_10Y').items():
        if d in u3:
            sp_m.setdefault(d[:7], []).append(v - u3[d])
    sp_m = {k: sum(v) / len(v) for k, v in sp_m.items()}
    months = sorted(sp_m)
    off_rs, off_rsi, run = set(), set(), 0
    for i, k in enumerate(months):
        run = run + 1 if sp_m[k] < 0 else 0
        if run >= 3:
            for j in range(i + 1, min(i + 2, len(months))):
                off_rsi.add(months[j])          # inversion known at month end -> off next month
        if sp_m[k] >= 0 and i >= 3 and all(sp_m[months[i - q]] < 0 for q in (1, 2, 3)):
            for j in range(i + 1, min(i + 13, len(months))):
                off_rs.add(months[j]); off_rsi.add(months[j])
    F['RS12 not in 12m after a dis-inversion (canary headline)'] = flag(days, lambda d: d[:7] not in off_rs)
    F['RSinv not inverted and not in 12m after'] = flag(days, lambda d: d[:7] not in off_rsi)
    # 5. retail leverage: FINRA margin debt (1997+), month m from m+2
    mg = load('FINRA_DEBIT')
    mg_y = yoy_m(mg)
    spx_y = yoy_m(month_end(yh('^GSPC')))
    exc = {k: mg_y[k] - spx_y[k] for k in mg_y if k in spx_y}
    mgy_d, exc_d = monthly_known(mg_y, days, 2), monthly_known(exc, days, 2)
    tlt, spyr = yh('TLT'), spy
    rs = lambda px: {sorted(px)[i]: px[sorted(px)[i]] / px[sorted(px)[i - 1]] - 1 for i in range(1, len(px))}   # noqa: E731
    rt, rsy = rs(tlt), rs(spyr)
    sb = {}
    q = []
    for d in days:
        if d in rt and d in rsy:
            q.append((rsy[d], rt[d]))
            q = q[-63:]
            if len(q) == 63:
                ma_, mb_ = sum(x for x, _ in q) / 63, sum(y for _, y in q) / 63
                cv = sum((x - ma_) * (y - mb_) for x, y in q)
                sa_ = math.sqrt(sum((x - ma_) ** 2 for x, _ in q)); sb_ = math.sqrt(sum((y - mb_) ** 2 for _, y in q))
                sb[d] = cv / (sa_ * sb_) if sa_ and sb_ else 0.0
    sb = lagged(sb, days, 1)
    F['MG40 margin YoY<40%'] = flag(days, lambda d: on(mgy_d, d) or mgy_d[d] < 0.40)
    F['MX25 margin excess growth<25pp (canary cell)'] = flag(days, lambda d: on(exc_d, d) or exc_d[d] < 0.25)
    F['MX15 margin excess growth<15pp'] = flag(days, lambda d: on(exc_d, d) or exc_d[d] < 0.15)
    F['MX25SB excess>=25pp only with stock-bond corr>0 is off'] = flag(days, lambda d: on(exc_d, d) or exc_d[d] < 0.25 or sb.get(d, -1) <= 0)
    F['MDEL off while margin is deleveraging (YoY<0)'] = flag(days, lambda d: on(mgy_d, d) or mgy_d[d] >= 0)
    # 6. OFR Financial Stress Index (2000+), two-session lag
    fsi = lagged(load('OFR_FSI'), days, 2)
    F['FSI<0 OFR stress below average'] = flag(days, lambda d: on(fsi, d) or fsi[d] < 0)
    F['FSI<1 OFR stress below +1'] = flag(days, lambda d: on(fsi, d) or fsi[d] < 1)
    # 7. canary leading stack (needs FRED; skipped with a note when the series are missing)
    LEADS = {'PERMIT': ('yoy', -10.0), 'TEMPHELPS': ('yoy', -2.0), 'HTRUCKSSAAR': ('off_peak', -10.0), 'NEWORDER': ('yoy', 0.0),
             'CFNAI': ('ma3', -0.35), 'IC4WSA': ('yoy_up', 10.0), 'SAHMREALTIME': ('level', 0.30)}
    ser = {s: load(s) for s in LEADS}
    if all(ser.values()):
        mser = {s: {k[:7]: v for k, v in sorted(ser[s].items())} for s in LEADS}

        def add_m(k, n):
            y, m = int(k[:4]), int(k[5:7]) + n
            while m < 1:
                y, m = y - 1, m + 12
            while m > 12:
                y, m = y + 1, m - 12
            return f'{y:04d}-{m:02d}'

        def flash(s, k):
            mode, thr = LEADS[s]
            sv = mser[s]
            cur = sv.get(k)
            if cur is None:
                return None
            if mode == 'level':
                return cur >= thr
            if mode == 'ma3':
                vals = [sv.get(add_m(k, -j)) for j in range(3)]
                return None if any(v is None for v in vals) else sum(vals) / 3 <= thr
            prev = sv.get(add_m(k, -12))
            if mode == 'off_peak':
                win = [sv.get(add_m(k, -j)) for j in range(12)]
                win = [w for w in win if w is not None]
                return (cur - max(win)) / max(win) * 100 <= thr if win else None
            if not prev:
                return None
            yoy = (cur - prev) / prev * 100
            return yoy <= thr if mode == 'yoy' else yoy >= thr
        allm = sorted(set().union(*[set(m) for m in mser.values()]))
        br = {}
        for k in allm:
            fl = [flash(s, k) for s in LEADS]
            live = [f for f in fl if f is not None]
            if len(live) >= 4:
                br[k] = sum(1 for f in live if f) / len(live)
        alarm = {}
        ks = sorted(br)
        for i in range(1, len(ks)):
            alarm[ks[i]] = 1.0 if (br[ks[i]] >= 0.5 and br[ks[i - 1]] >= 0.5) else 0.0
        al_d = monthly_known(alarm, days, 2)
        F['LS50 canary leading stack not in alarm'] = flag(days, lambda d: on(al_d, d) or al_d[d] < 1)
    for name, lam in F.items():
        ds_off = [d for d in days if lam.get(d, 1.0) < 1]
        first[name] = None
    return F


def boot_gap(r_a, r_b, ds, rng, n=300, L=20):
    """paired block bootstrap of Sharpe(a) - Sharpe(b) on the same resampled days (prefix sums)."""
    ea = [r_a[d] - lg.cash.get(d, 0.0) for d in ds]
    eb = [r_b[d] - lg.cash.get(d, 0.0) for d in ds]

    def prefix(x):
        s, s2 = [0.0], [0.0]
        for v in x:
            s.append(s[-1] + v); s2.append(s2[-1] + v * v)
        return s, s2
    pa, pb = prefix(ea), prefix(eb)
    nb, N = len(ds) // L, len(ds)
    gaps = []
    for _ in range(n):
        st = [rng.randrange(0, N - L) for _ in range(nb)]
        out = []
        for (s, s2) in (pa, pb):
            sm = sum(s[i + L] - s[i] for i in st); sq = sum(s2[i + L] - s2[i] for i in st)
            m = nb * L
            mu = sm / m
            var = (sq - m * mu * mu) / (m - 1)
            out.append(mu / math.sqrt(var) * math.sqrt(252) if var > 0 else 0.0)
        gaps.append(out[0] - out[1])
    gaps.sort()
    return [round(gaps[int(0.05 * n)], 3), round(gaps[int(0.95 * n)], 3)], round(sum(1 for g in gaps if g > 0) / n, 3)


def current(F, days):
    return {n: lam.get(days[-1], 1.0) for n, lam in F.items()}


def main(n_placebo=100, seed=7):
    rng = random.Random(seed)
    res = {'B': {}, 'A': {}}
    for panel in ('B', 'A'):
        P, P1, runs = lg.engine_runs(panel)
        for e in (('HG',) if panel == 'B' else ('HG', 'KMLM')):
            days, h = runs[e]
            legs_held = sorted({t for d in h for t in h[d] if t in lg.LEG})
            sets = leg_sets(e, legs_held)
            G = sets['trend']
            F = build(P, days)
            run = lambda lam: gate_run(days, h, P, P1, lam, G, COST[e])[0]   # noqa: E731
            base = run({})
            t200 = F['T200 SPY>200d (reference)']
            r200 = run(t200)
            rows = {'as built': {'full': metrics(base, days)}, 'T200 SPY>200d (reference)': {'full': metrics(r200, days)}}
            if panel == 'B':
                for k in rows:
                    rows[k]['windows'] = {w: lg.gs.metrics(base if k == 'as built' else r200, days, a, b) for w, (a, b) in WINDOWS_B.items()}
            ds = days[1:]
            for name, lam in F.items():
                if name.startswith('T200'):
                    continue
                first_off = next((d for d in days if lam.get(d, 1.0) < 1), None)
                variants = {'alone': lam,
                            '& 200d': {d: min(lam.get(d, 1.0), t200.get(d, 1.0)) for d in days},
                            '-> 200d only in risk': {d: (t200.get(d, 1.0) if lam.get(d, 1.0) < 1 else 1.0) for d in days},
                            '-> 200d only in safe (mirror)': {d: (t200.get(d, 1.0) if lam.get(d, 1.0) >= 1 else 1.0) for d in days}}
                for vn, vl in variants.items():
                    r = run(vl)
                    row = {'full': metrics(r, days), 'mean_allow': round(sum(vl.get(d, 1.0) for d in days) / len(days), 3), 'first_off': first_off}
                    if panel == 'B':
                        row['windows'] = {w: lg.gs.metrics(r, days, a, b) for w, (a, b) in WINDOWS_B.items()}
                        row['gap_vs_built'] = boot_gap(r, base, ds, rng)
                        row['gap_vs_200d'] = boot_gap(r, r200, ds, rng)
                        if vn == 'alone':
                            mi = metrics(run(inverse(vl, days)), days)
                            draws = [metrics(run(placebo(vl, days, rng)), days) for _ in range(n_placebo)]
                            real = row['full']
                            row['inverse'] = mi
                            row['placebo_pct'] = {k: sum(1 for x in draws if x[k] < real[k]) / n_placebo for k in ('cagr', 'sharpe')}
                            row['placebo_pct']['dd_better'] = sum(1 for x in draws if x['maxdd'] > real['maxdd']) / n_placebo
                        if first_off and first_off > days[0]:
                            row['own_window'] = {'from': first_off, 'gate': metrics(r, days, first_off), 'built': metrics(base, days, first_off),
                                                 't200': metrics(r200, days, first_off)}
                    rows[f'{name} [{vn}]'] = row
            res[panel][e] = {'rows': rows, 'current': current(F, days), 'last_day': days[-1], 'trend_legs': sorted(G)}
            print(f'\n== panel {panel} / {e} ({days[0]}..{days[-1]}), gate on trend legs {sorted(G)}')
            print(f"   {'variant':70s}  CAGR    Sharpe  maxDD | gap vs built [90%] P | gap vs 200d [90%] P | placebo CAGR/Sh/DD | inverse")
            for k, row in rows.items():
                m = row['full']
                extra = ''
                if 'gap_vs_built' in row:
                    gb, gt = row['gap_vs_built'], row['gap_vs_200d']
                    extra = f" | {gb[0][0]:+.2f},{gb[0][1]:+.2f} {gb[1]:.2f} | {gt[0][0]:+.2f},{gt[0][1]:+.2f} {gt[1]:.2f}"
                if 'placebo_pct' in row:
                    pp, iv = row['placebo_pct'], row['inverse']
                    extra += f" | {pp['cagr']:.2f}/{pp['sharpe']:.2f}/{pp['dd_better']:.2f} | {iv['cagr']:+.1%}/{iv['sharpe']:.2f}"
                print(f"   {k[:70]:70s} {m['cagr']:+6.1%} {m['sharpe']:5.2f} {m['maxdd']:5.1%}{extra}")
            print('   current readings (1 = leverage on):', {k: v for k, v in res[panel][e]['current'].items()})
    json.dump(res, open(os.path.join(OUT, 'canary_gates.json'), 'w'))
    print('\nsaved', os.path.join(OUT, 'canary_gates.json'))


if __name__ == '__main__':
    main()
