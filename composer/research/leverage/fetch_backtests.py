"""Composer backtests (v2, reg+TAF fees, 5bp slippage) of each version that was live in 2026,
2025-12-01 .. 2026-10-15, to get the model's daily holdings (tdvm_weights) and equity curve."""
import json, sys
sys.path.insert(0, '/home/user/uranium-dashboard/composer/scripts')
import composerlib as cl
OUT = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/lev'
VT = json.load(open(f'{OUT}/version_trees.json'))
WANT = {'HG': ['0DeB193gVf6uIq2osLmL', '6jq2MZNfQcEWZjQFq5v9', 'bP4mvRy6YHHejuPGUBNY'], 'ORIG': ['wt3G61qcuOZ8MVYJ64v4'],
        'KMLM': ['MVfHI8OgKae5EaC3W9oE'], 'SLEEVE': ['GtCP9qywDB4E5kxj6ScN', 'yHJkdePZUWBT6eMCgO9m'], 'HARV': ['XVtsDTV1R6iuYDEg8XZK']}
res = {}
for k, vids in WANT.items():
    for v in VT[k]:
        if v['version_id'] not in vids: continue
        bt = cl.backtest_tree(v['tree'], start='2025-12-01', end='2026-10-15')
        json.dump(bt, open(f"{OUT}/bt_raw_{k}_{v['version_id']}.json", 'w'))
        days, vals = cl.equity_curve(bt)
        # tdvm_weights may be {ticker: {day: w}} — normalise to {date: {ticker: w}}
        raw = bt.get('tdvm_weights') or {}
        hold = {}
        if raw and isinstance(next(iter(raw.values())), dict):
            first_key = next(iter(raw))
            if first_key.isdigit():   # {day: {ticker: w}}
                for d, m in raw.items(): hold[cl.epoch_day_to_date(int(d)).isoformat()] = {t: x for t, x in m.items() if x}
            else:                      # {ticker: {day: w}}
                for t, m in raw.items():
                    for d, x in m.items():
                        if x: hold.setdefault(cl.epoch_day_to_date(int(d)).isoformat(), {})[t] = x
        eq = {cl.epoch_day_to_date(d).isoformat(): x for d, x in zip(days, vals)}
        res[f"{k}:{v['version_id']}"] = {'sym': k, 'version_id': v['version_id'], 'created_at': v['created_at'], 'equity': eq, 'holdings': hold}
        ds = sorted(eq); hs = sorted(hold)
        print(k, v['version_id'], 'equity', ds[0], '..', ds[-1], len(ds), '| holdings', hs[0], '..', hs[-1], len(hs), '| last', hold[hs[-1]])
json.dump(res, open(f'{OUT}/backtests.json', 'w')); print('saved')
