import json, sys
sys.path.insert(0, '/home/user/uranium-dashboard/composer/scripts')
import composerlib as cl
OUT = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/lev'
acct = 'b4ee3fe9-fc12-4991-8df4-de29c857099c'
ph = cl.get(f'/portfolio/accounts/{acct}/portfolio-history')
json.dump(ph, open(f'{OUT}/portfolio_history.json', 'w'))
print('portfolio-history keys:', list(ph.keys()) if isinstance(ph, dict) else type(ph))
for k, v in (ph.items() if isinstance(ph, dict) else []):
    if isinstance(v, list):
        print(' ', k, 'len', len(v), 'first', v[:2], 'last', v[-2:])
    else:
        print(' ', k, str(v)[:200])
meta = cl.get(f'/portfolio/accounts/{acct}/symphony-stats-meta')
json.dump(meta, open(f'{OUT}/stats_meta.json', 'w'))
for s in meta.get('symphonies', []):
    print('SYM', s.get('id'), s.get('name')[:40], {k: s.get(k) for k in ('value', 'deposit_adjusted_value', 'net_deposits', 'last_dollar_change', 'cumulative_return', 'time_weighted_return', 'simple_return', 'created_at', 'invested_since') if k in s})
print('meta symphony keys:', sorted(meta['symphonies'][0].keys()) if meta.get('symphonies') else None)
ts = cl.get(f'/portfolio/accounts/{acct}/total-stats')
json.dump(ts, open(f'{OUT}/total_stats.json', 'w'))
print('total-stats:', json.dumps(ts)[:800])
