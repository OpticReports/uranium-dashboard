#!/usr/bin/env python3 -I
"""Band and speed tests on monthly ICE DXY (close), 1971-01..latest, against data/crises.csv.
Outputs: data/band_excursions.csv, data/speed_events.csv, data/band_summary.csv, data/base_rates.csv
Definitions (all re-runnable):
  excursion  = maximal run of consecutive months with monthly CLOSE > upper or < lower band
  followed_by_crisis_Nm = a crisis START (is_crisis=1) in the N months after the excursion START (inclusive of start month)
  ...after_end        = a crisis START in the 12 months after the excursion END
  base rate            = share of all months m (1971-01..last-12) such that a crisis starts within (m, m+12]
  speed event          = first month where 6m % change of monthly close >= thr; event persists while condition holds
Run from finderA/: python3 -I scripts/band_test.py"""
import csv, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D = os.path.join(ROOT, 'data')
dm = [r for r in csv.DictReader(open(os.path.join(D, 'dollar_monthly.csv'))) if r['dxy_close']]
months = [r['month'] for r in dm]; close = {r['month']: float(r['dxy_close']) for r in dm}
avg = {r['month']: float(r['dxy_avg']) for r in dm}
idx = {m: i for i, m in enumerate(months)}
crises = [c for c in csv.DictReader(open(os.path.join(D, 'crises.csv'))) if c['is_crisis'] == '1']
starts = {c['start']: c for c in crises}; peaks = {c['peak_stress']: c for c in crises}
in_crisis = set()
for c in crises:
    e = c['end'] or months[-1]
    for m in months:
        if c['start'] <= m <= e: in_crisis.add(m)
def shift(m, k):
    i = idx[m] + k; return months[i] if 0 <= i < len(months) else None
def crisis_start_within(m, n, inclusive_start=True):
    """crises starting in [m, m+n) if inclusive_start else (m, m+n]"""
    out = []
    rng = range(0, n) if inclusive_start else range(1, n + 1)
    for k in rng:
        mm = shift(m, k)
        if mm in starts: out.append(f"{starts[mm]['id']}:{mm}")
    return out
def peak_within(m, n):
    out = []
    for k in range(0, n):
        mm = shift(m, k)
        if mm in peaks: out.append(f"{peaks[mm]['id']}:{mm}")
    return out
# ---- base rates ----
last_eval = months[-13]
elig = [m for m in months if m <= last_eval]
br12 = sum(1 for m in elig if crisis_start_within(m, 12, False)) / len(elig)
elig24 = [m for m in months if m <= months[-25]]
br24 = sum(1 for m in elig24 if crisis_start_within(m, 24, False)) / len(elig24)
br_in = sum(1 for m in months if m in in_crisis) / len(months)
br_peak12 = sum(1 for m in elig if peak_within(shift(m, 1), 12)) / len(elig)
with open(os.path.join(D, 'base_rates.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['metric', 'value', 'n_months', 'definition'])
    w.writerow(['P(crisis start within next 12m | random month)', f"{br12:.3f}", len(elig), 'any is_crisis=1 start in (m, m+12]'])
    w.writerow(['P(crisis start within next 24m | random month)', f"{br24:.3f}", len(elig24), 'any start in (m, m+24]'])
    w.writerow(['P(crisis peak-stress month within next 12m | random month)', f"{br_peak12:.3f}", len(elig), 'any peak_stress in (m, m+12]'])
    w.writerow(['P(month is inside a crisis window)', f"{br_in:.3f}", len(months), 'start<=m<=end'])
print(f"BASE RATES: P(start within 12m)={br12:.3f}  P(start within 24m)={br24:.3f}  P(peak within 12m)={br_peak12:.3f}  P(in crisis)={br_in:.3f}  (n crises={len(crises)}, months={len(months)})")
# ---- excursions ----
bands = [(85, 105), (90, 110), (83, 102)]
exc_rows = []; summ = []
for lo, hi in bands:
    for basis_name, series in [('close', close), ('avg', avg)]:
        runs = []; cur = None
        for m in months:
            side = 'above' if series[m] > hi else ('below' if series[m] < lo else None)
            if side and cur and cur['side'] == side: cur['months'].append(m)
            else:
                if cur: runs.append(cur)
                cur = {'side': side, 'months': [m]} if side else None
        if cur: runs.append(cur)
        n = len(runs); n12 = n24 = n12e = npk = 0
        for r in runs:
            s, e = r['months'][0], r['months'][-1]
            ext_m = max(r['months'], key=lambda m: series[m]) if r['side'] == 'above' else min(r['months'], key=lambda m: series[m])
            c12 = crisis_start_within(s, 12); c24 = crisis_start_within(s, 24); c12e = crisis_start_within(shift(e, 1) or e, 12) if shift(e, 1) else []
            pk12 = peak_within(s, 12)
            during = sorted({starts[m]['id'] for m in r['months'] if m in starts})
            already = 'yes' if s in in_crisis else 'no'
            n12 += bool(c12); n24 += bool(c24); n12e += bool(c12e); npk += bool(pk12)
            exc_rows.append({'band': f"{lo}-{hi}", 'basis': basis_name, 'side': r['side'], 'start': s, 'end': e, 'months': len(r['months']), 'extreme': f"{series[ext_m]:.2f}", 'extreme_month': ext_m,
                             'level_at_start': f"{series[s]:.2f}", 'already_in_crisis_at_start': already, 'crisis_starts_during': ';'.join(during),
                             'crisis_start_within_12m_of_start': ';'.join(c12), 'crisis_start_within_24m_of_start': ';'.join(c24), 'crisis_start_within_12m_after_end': ';'.join(c12e), 'crisis_peak_within_12m_of_start': ';'.join(pk12)})
        summ.append({'test': f"excursion outside {lo}-{hi} ({basis_name})", 'n_events': n, 'followed_by_crisis_start_12m': n12, 'pct_12m': f"{100*n12/n:.0f}" if n else '', 'followed_24m': n24, 'pct_24m': f"{100*n24/n:.0f}" if n else '',
                     'crisis_start_12m_after_end': n12e, 'crisis_peak_within_12m': npk, 'base_rate_12m_pct': f"{100*br12:.0f}", 'base_rate_24m_pct': f"{100*br24:.0f}"})
# merged variant: runs outside 85-105 (close) separated by <= 3 in-band months are one excursion (closer to a chart-reader's count)
for gap in (3, 6):
    base = [r for r in exc_rows if r['band'] == '85-105' and r['basis'] == 'close']
    merged = []
    for r in base:
        if merged and merged[-1]['side'] == r['side'] and idx[r['start']] - idx[merged[-1]['end']] - 1 <= gap:
            merged[-1]['end'] = r['end']; merged[-1]['months'] = idx[r['end']] - idx[merged[-1]['start']] + 1
            if (r['side'] == 'above' and float(r['extreme']) > float(merged[-1]['extreme'])) or (r['side'] == 'below' and float(r['extreme']) < float(merged[-1]['extreme'])): merged[-1]['extreme'], merged[-1]['extreme_month'] = r['extreme'], r['extreme_month']
        else: merged.append(dict(r))
    n = len(merged); n12 = n24 = nin = 0
    for r in merged:
        s_, e_ = r['start'], r['end']
        c12 = crisis_start_within(s_, 12); c24 = crisis_start_within(s_, 24)
        r['crisis_start_within_12m_of_start'] = ';'.join(c12); r['crisis_start_within_24m_of_start'] = ';'.join(c24)
        r['crisis_start_within_12m_after_end'] = ';'.join(crisis_start_within(shift(e_, 1), 12)) if shift(e_, 1) else ''
        r['band'] = f"85-105 merged(gap<={gap})"; r['crisis_starts_during'] = ';'.join(sorted({starts[m]['id'] for m in months if s_ <= m <= e_ and m in starts}))
        n12 += bool(c12); n24 += bool(c24); nin += r['already_in_crisis_at_start'] == 'yes'
        exc_rows.append(r)
    summ.append({'test': f"excursion outside 85-105 (close, runs merged if gap<={gap}m)", 'n_events': n, 'followed_by_crisis_start_12m': n12, 'pct_12m': f"{100*n12/n:.0f}", 'followed_24m': n24, 'pct_24m': f"{100*n24/n:.0f}",
                 'crisis_start_12m_after_end': '', 'crisis_peak_within_12m': f"started_inside_crisis={nin}", 'base_rate_12m_pct': f"{100*br12:.0f}", 'base_rate_24m_pct': f"{100*br24:.0f}"})
    print(f"MERGED gap<={gap}: {n} excursions, {nin} began inside a crisis window, {n12} followed by crisis start within 12m, {n24} within 24m")
    for r in merged: print(f"   {r['side']:5} {r['start']}..{r['end']} ({r['months']:>3}m) ext {r['extreme']} @{r['extreme_month']} inCrisis={r['already_in_crisis_at_start']} during=[{r['crisis_starts_during']}] +12m=[{r['crisis_start_within_12m_of_start']}] +24m=[{r['crisis_start_within_24m_of_start']}]")
nin_all = sum(1 for r in exc_rows if r['band'] == '85-105' and r['basis'] == 'close' and r['already_in_crisis_at_start'] == 'yes')
print('85-105 close unmerged: excursions beginning inside a crisis window =', nin_all)
with open(os.path.join(D, 'band_excursions.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(exc_rows[0].keys())); w.writeheader(); w.writerows(exc_rows)
# ---- speed events ----
sp_rows = []
for thr in (8, 10, 15):
    trig = {}
    for m in months:
        b = shift(m, -6)
        if b: trig[m] = 100 * (close[m] / close[b] - 1) >= thr
    runs = []; cur = None
    for m in months:
        if trig.get(m):
            if cur: cur.append(m)
            else: cur = [m]
        elif cur: runs.append(cur); cur = None
    if cur: runs.append(cur)
    n12 = n24 = npk = 0
    for r in runs:
        s, e = r[0], r[-1]
        mx_m = max(r, key=lambda m: 100 * (close[m] / close[shift(m, -6)] - 1)); mx = 100 * (close[mx_m] / close[shift(mx_m, -6)] - 1)
        c12 = crisis_start_within(s, 12); c24 = crisis_start_within(s, 24); pk12 = peak_within(s, 12)
        n12 += bool(c12); n24 += bool(c24); npk += bool(pk12)
        sp_rows.append({'threshold_6m_pct': thr, 'first_trigger_month': s, 'last_trigger_month': e, 'months_triggered': len(r), 'max_6m_rise_pct': f"{mx:.1f}", 'max_month': mx_m, 'dxy_close_at_first_trigger': f"{close[s]:.2f}",
                        'already_in_crisis_at_first_trigger': 'yes' if s in in_crisis else 'no', 'crisis_starts_during_run': ';'.join(sorted({starts[m]['id'] for m in r if m in starts})),
                        'crisis_start_within_12m': ';'.join(c12), 'crisis_start_within_24m': ';'.join(c24), 'crisis_peak_within_12m': ';'.join(pk12)})
    n = len(runs)
    summ.append({'test': f"6m DXY rise >= {thr}% (close)", 'n_events': n, 'followed_by_crisis_start_12m': n12, 'pct_12m': f"{100*n12/n:.0f}" if n else '', 'followed_24m': n24, 'pct_24m': f"{100*n24/n:.0f}" if n else '',
                 'crisis_start_12m_after_end': '', 'crisis_peak_within_12m': npk, 'base_rate_12m_pct': f"{100*br12:.0f}", 'base_rate_24m_pct': f"{100*br24:.0f}"})
with open(os.path.join(D, 'speed_events.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(sp_rows[0].keys())); w.writeheader(); w.writerows(sp_rows)
with open(os.path.join(D, 'band_summary.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)
for s in summ: print(s)
print('\nEXCURSIONS 85-105 close:')
for r in exc_rows:
    if r['band'] == '85-105' and r['basis'] == 'close':
        print(f"  {r['side']:5} {r['start']}..{r['end']} ({r['months']:>3}m) ext {r['extreme']} @{r['extreme_month']} inCrisis@start={r['already_in_crisis_at_start']} during=[{r['crisis_starts_during']}] +12m=[{r['crisis_start_within_12m_of_start']}] +24m=[{r['crisis_start_within_24m_of_start']}] afterEnd12=[{r['crisis_start_within_12m_after_end']}]")
print('\nSPEED >=10%:')
for r in sp_rows:
    if r['threshold_6m_pct'] == 10:
        print(f"  {r['first_trigger_month']}..{r['last_trigger_month']} max {r['max_6m_rise_pct']}% @{r['max_month']} inCrisis={r['already_in_crisis_at_first_trigger']} during=[{r['crisis_starts_during_run']}] +12m=[{r['crisis_start_within_12m']}] peak12=[{r['crisis_peak_within_12m']}]")
