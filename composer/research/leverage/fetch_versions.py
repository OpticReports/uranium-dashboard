"""Fetch every version tree of the five symphonies live in 2026, list held (leaf) tickers
and every ticker referenced in conditions.  Saves version_trees.json."""
import json, sys
sys.path.insert(0, '/home/user/uranium-dashboard/composer/scripts')
import composerlib as cl
OUT = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/lev'
SYMS = {'HG': 'mbkiXcuNDjueXpiox5Av', 'ORIG': 'rhZ9oDAUvN26v5Ra5qql', 'KMLM': 'YPTSJFJwD2ZKfAeYJUbW', 'SLEEVE': 'nNdBk7hc5NiBzeRvbI5T', 'HARV': 'ORQNCfZnA18wmsMWVhf8'}
vers = json.load(open(f'{OUT}/versions.json'))
out = {}
for k, sid in SYMS.items():
    out[k] = []
    for v in vers[k]:
        tree = cl.get(f"/symphonies/{sid}/versions/{v['version_id']}/score")
        leaves, refs = set(), set()
        def visit(n, parents):
            if n.get('step') == 'asset' and n.get('ticker'):
                leaves.add(n['ticker'])
            for key in ('lhs-val', 'rhs-val'):
                x = n.get(key)
                if isinstance(x, str) and x and not n.get('rhs-fixed-value?', False) or (key == 'lhs-val' and isinstance(x, str)):
                    if isinstance(x, str) and not x.replace('.', '', 1).isdigit():
                        refs.add(x)
        cl.walk_tree(tree, visit)
        out[k].append({'version_id': v['version_id'], 'created_at': v['created_at'], 'tree': tree, 'leaves': sorted(leaves), 'cond_refs': sorted(refs)})
        print(k, v['version_id'], v['created_at'][:16], 'held:', ' '.join(sorted(leaves)))
        print('   cond refs:', ' '.join(sorted(refs - leaves)))
json.dump(out, open(f'{OUT}/version_trees.json', 'w'))
alll = sorted({t for k in out for v in out[k] for t in v['leaves']})
print('\nALL HELD TICKERS (any version):', len(alll)); print(' '.join(alll))
