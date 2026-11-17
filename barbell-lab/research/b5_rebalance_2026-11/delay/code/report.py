import sys, json, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
D = sys.argv[1]
A = json.load(open(f'{D}/out_analysis.json')); BS = json.load(open(f'{D}/out_bootstrap.json'))
SRC = json.load(open(f'{D}/data/sources.json'))
C = {'D': '#2a78d6', 'M': '#eb6834', 'MB': '#1baf7a'}; CU = {'A': '#2a78d6', 'B': '#eb6834'}
FN = {'D': 'T-D daily band', 'M': 'T-M month-end (live rule)', 'MB': 'T-MB month-end, band-gated'}
INK, INK2, GRID = '#0b0b0b', '#52514e', '#e4e3df'
plt.rcParams.update({'font.size': 10, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2, 'ytick.color': INK2,
                     'axes.spines.top': False, 'axes.spines.right': False, 'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb'})
cells = A['cells']; ks = np.arange(11)

# ---------- table + pass bar
table = []
for key, c in cells.items():
    U, fam, sg = key.split('|'); b = BS[key]
    for k in ks:
        if k == 1: continue
        pk = c['per_k'].get(str(k), {})
        table.append(dict(universe=U, trigger=fam, segment=sg, k=int(k), start=c['det']['start'], end=c['det']['end'],
            cagr_diff_bps=c['det']['cagr_diff_bps'][k], boot_mean_bps=b['mean_bps'][k], boot_ci95_bps=[b['lo_bps'][k], b['hi_bps'][k]],
            n_events=c['events']['n'], event_mean_bps=pk.get('mean_bps'), p_signflip_1s=pk.get('p_signflip_1s'),
            p_signflip_2s=pk.get('p_signflip_2s'), p_t_2s=pk.get('p_t_2s'), p_wilcoxon_1s=pk.get('p_wilcoxon_1s'),
            holm_primary=pk.get('holm_primary'), holm_secondary=pk.get('holm_secondary'),
            sharpe=c['det']['sharpe'][k], sharpe_k1=c['det']['sharpe'][1], maxdd=c['det']['maxdd'][k],
            turnover_pa=c['det']['turnover_pa'][k], costdrag_bps_pa=c['det']['costdrag_bps_pa'][k], fills=c['det']['fills'][k]))
passbar = {}
for fam in ['D', 'M', 'MB']:
    passbar[fam] = {}
    for k in (3, 4, 5):
        cond = {}
        cl = [f'{U}|{fam}|{s}' for U in 'AB' for s in ('full', 'H1', 'H2')]
        cond['1_holm_p_lt_05_all_cells'] = {x: cells[x]['per_k'][str(k)]['holm_primary'] for x in cl}
        cond['2_boot_lo_gt0_all_cells'] = {x: BS[x]['lo_bps'][k] for x in cl}
        cond['5_pre2013_cagr_diff'] = {U: cells[f'{U}|{fam}|pre2013']['det']['cagr_diff_bps'][k] for U in 'AB'}
        cond['6_placebos'] = {U: cells[f'{U}|{fam}|full']['placebo'][str(k)] for U in 'AB'}
        cond['7_mirrored'] = {U: {s: cells[f'{U}|{fam}|full']['per_k'][str(k)]['mirrored'][s]['mean_bps'] for s in ('up', 'down')} for U in 'AB'}
        cond['8_events'] = {x: cells[x]['events']['n'] for x in cl}
        cond['9_cagr_diff_at_10bps'] = {U: A['sens'][f'{U}|{fam}|cost10']['cagr_diff_bps'][k] for U in 'AB'}
        ok = {'1': all(v < .05 for v in cond['1_holm_p_lt_05_all_cells'].values()),
              '2': all(v > 0 for v in cond['2_boot_lo_gt0_all_cells'].values()),
              '3_4': None, '5': all(v > 0 for v in cond['5_pre2013_cagr_diff'].values()),
              '6': all(v['beats_p1'] and v['beats_p2'] for v in cond['6_placebos'].values()),
              '7': all(np.sign(v['up']) == np.sign(v['down']) and v['up'] > 0 for v in cond['7_mirrored'].values()),
              '8': all(v >= 30 for v in cond['8_events'].values()),
              '9': all(v >= 10 for v in cond['9_cagr_diff_at_10bps'].values())}
        ok['3_4'] = ok['1'] and ok['2']
        passbar[fam][k] = dict(conditions=cond, ok=ok, PASS=all(ok.values()))
verdict = {f: ('PASS at k=' + ','.join(str(k) for k in (3, 4, 5) if passbar[f][k]['PASS'])) if any(passbar[f][k]['PASS'] for k in (3, 4, 5)) else 'NOT PROVEN' for f in passbar}
out = dict(verdict=verdict, verdict_note='Adoption decided on T-M (live rule); T-D supporting only; T-MB reported, not in pass bar. Result DEVIATED FROM PREREG (see DEVIATIONS.md).',
           passbar=passbar, table=table, sensitivities=A['sens'], data=SRC, meta=A['meta'],
           bootstrap_meta=dict(block_days=252, resamples=10000, seed=20261116, month_end_flags='travel with resampled rows', cost_bps=5))
json.dump(out, open(f'{D}/results.json', 'w'), indent=1, default=float)
print(json.dumps(verdict)); 
for f in passbar:
    for k in (3, 4, 5): print(f, k, passbar[f][k]['ok'])

# ---------- delay_curve.png
fig, axs = plt.subplots(1, 2, figsize=(13, 5.2), sharey=True)
for ax, U in zip(axs, 'AB'):
    for fam in ['D', 'M', 'MB']:
        key = f'{U}|{fam}|full'; b = BS[key]; c = cells[key]
        n = c['events']['n']; y = np.array(c['det']['cagr_diff_bps'])
        ax.fill_between(ks, b['lo_bps'], b['hi_bps'], color=C[fam], alpha=.13, lw=0)
        ax.plot(ks, y, color=C[fam], lw=2, marker='o', ms=5, label=f'{FN[fam]} (n={n} events)')
        ax.text(10.15, y[-1], fam if fam != 'MB' else 'T-MB', color=INK2, va='center', fontsize=9)
    ax.axhline(0, color=INK2, lw=1); ax.axvspan(2.5, 5.5, color='#eda100', alpha=.08, lw=0)
    ax.text(4, ax.get_ylim()[1] if False else 0, '', fontsize=8)
    s = cells[f'{U}|M|full']['det']
    title = 'Universe A: B.5 analogues (6 sleeves)' if U == 'A' else 'Universe B: 40 US equity / 40 UST10 / 20 gold'
    ax.set_title(f'{title}\n{s["start"]} to {s["end"]}', fontsize=10.5, color=INK, loc='left')
    ax.set_xticks(ks); ax.set_xlabel('k = trading days from trigger close to fill close (k=1 = live baseline)')
    ax.grid(axis='y', color=GRID, lw=.8); ax.legend(frameon=False, fontsize=8.5, loc='lower left')
axs[0].set_ylabel('CAGR(k) - CAGR(k=1), bps/yr, net 5 bps/side')
axs[0].text(4, axs[0].get_ylim()[1] * .92, 'pre-registered\ntest window k=3-5', ha='center', fontsize=8, color=INK2)
fig.suptitle('Delaying the rebalance fill: no reliable gain at k=3-5 (shaded bands = 95% block-bootstrap CI, 10,000 resamples)', fontsize=11.5, color=INK, x=.01, ha='left')
fig.tight_layout(); fig.savefig(f'{D}/delay_curve.png', dpi=150); plt.close(fig)

# ---------- delay_events.png (k=4 vs k=1)
fig, axs = plt.subplots(2, 4, figsize=(17, 8.2))
for r, fam in enumerate(['D', 'M']):
    ax = axs[r, 0]
    for U in 'AB':
        d = np.array(cells[f'{U}|{fam}|full']['events']['d'])[:, 4] * 1e4
        lim = np.percentile(np.abs(d), 98) if len(d) else 1
        ax.hist(np.clip(d, -lim, lim), bins=30 if fam == 'M' else 15, histtype='step', lw=2, color=CU[U],
                label=f'{U}: n={len(d)}, mean {d.mean():+.2f} bps')
    ax.axvline(0, color=INK2, lw=1); ax.set_title(f'{FN[fam]}\nper-event d = logret(k=4) - logret(k=1), 11-day window', fontsize=9.5, loc='left')
    ax.set_xlabel('bps per event (tails clipped at 98th pct)'); ax.set_ylabel('events'); ax.legend(frameon=False, fontsize=8)
    ax = axs[r, 1]; xs = 0
    for U in 'AB':
        m = cells[f'{U}|{fam}|full']['per_k']['4']['mirrored']
        for s, mk in (('up', '^'), ('down', 'v')):
            v = m[s]; ax.errorbar(xs, v['mean_bps'], yerr=[[v['mean_bps'] - v['ci95_bps'][0]], [v['ci95_bps'][1] - v['mean_bps']]],
                                  fmt=mk, ms=9, color=CU[U], capsize=4, lw=2)
            ax.text(xs, v['ci95_bps'][1], f" n={v['n']}", fontsize=8, color=INK2, va='bottom', ha='center'); xs += 1
        xs += .5
    ax.axhline(0, color=INK2, lw=1); ax.set_xticks([0, 1, 2.5, 3.5]); ax.set_xticklabels(['A up', 'A down', 'B up', 'B down'])
    ax.set_ylabel('mean d, bps/event (95% CI)'); ax.set_title('Mirrored check: overweight (up) vs\nunderweight (down) breach', fontsize=9.5, loc='left')
    for j, (pkey, nm) in enumerate((('placebo1_k4_bps', 'Placebo 1: random trigger dates'), ('placebo2_bps', 'Placebo 2: random delay k~U{1..10}'))):
        ax = axs[r, 2 + j]
        for U in 'AB':
            e = cells[f'{U}|{fam}|full']['events']; pl = np.array(e[pkey]); real = cells[f'{U}|{fam}|full']['per_k']['4']['mean_bps']
            ax.hist(pl, bins=40, histtype='stepfilled', alpha=.25, color=CU[U]); ax.hist(pl, bins=40, histtype='step', color=CU[U], lw=1.2)
            ax.axvline(real, color=CU[U], lw=2.5); ax.axvline(np.percentile(pl, 95), color=CU[U], lw=1, ls='--')
            ax.text(.02, .97 if U == 'A' else .85, f'{U}: real {real:+.2f}, at {100*(pl<real).mean():.0f}th pct', transform=ax.transAxes, color=CU[U], fontsize=8.5, va='top', fontweight='bold')
        ax.set_title(f'{nm}\n1,000 draws; solid = real k=4 mean, dashed = 95th pct', fontsize=9.5, loc='left'); ax.set_xlabel('mean d, bps/event')
fig.suptitle('k=4 vs k=1, per event, full sample, net 5 bps/side.  Blue = Universe A, orange = Universe B', fontsize=11.5, x=.01, ha='left', color=INK)
fig.tight_layout(); fig.savefig(f'{D}/delay_events.png', dpi=150); plt.close(fig)

# ---------- equity_curves.png (prereg sec 7)
import datetime as dt
fig, axs = plt.subplots(2, 2, figsize=(13, 7.5), sharex='col', gridspec_kw=dict(height_ratios=[2.2, 1]))
for j, U in enumerate('AB'):
    e = A['equity'][f'{U}|M']; dates = np.array([dt.date.fromisoformat(x) for x in e['dates']])
    cd = cells[f'{U}|M|full']['det']['cagr_diff_bps']; best = int(3 + np.argmax(cd[3:6]))
    v1 = np.array(e['V']['1']); vb = np.array(e['V'][str(best)])
    axs[0, j].semilogy(dates, v1, color=CU['A'], lw=1.6, label=f'k=1 (live)  CAGR {100*cells[f"{U}|M|full"]["det"]["cagr"][1]:.2f}%')
    axs[0, j].semilogy(dates, vb, color=CU['B'], lw=1.2, label=f'k={best} (best of 3-5)  CAGR {100*cells[f"{U}|M|full"]["det"]["cagr"][best]:.2f}%')
    axs[0, j].legend(frameon=False, fontsize=9); axs[0, j].grid(color=GRID, lw=.7); axs[0, j].set_title(f'Universe {U}, T-M (live monthly rule), growth of $1, log', loc='left', fontsize=10)
    axs[1, j].plot(dates, (vb / v1 - 1) * 100, color=INK2, lw=1.3); axs[1, j].axhline(0, color=INK2, lw=.8)
    axs[1, j].set_ylabel(f'k={best} vs k=1, cum. %'); axs[1, j].grid(color=GRID, lw=.7)
fig.tight_layout(); fig.savefig(f'{D}/equity_curves.png', dpi=150); plt.close(fig)
