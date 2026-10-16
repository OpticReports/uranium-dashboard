import json, sys, urllib.error
sys.path.insert(0, '/home/user/uranium-dashboard/composer/scripts')
import composerlib as cl
OUT = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/lev'
acct = 'b4ee3fe9-fc12-4991-8df4-de29c857099c'
SYMS = {'HG': 'mbkiXcuNDjueXpiox5Av', 'ORIG': 'rhZ9oDAUvN26v5Ra5qql', 'KMLM': 'YPTSJFJwD2ZKfAeYJUbW', 'SLEEVE': 'nNdBk7hc5NiBzeRvbI5T', 'HARV': 'ORQNCfZnA18wmsMWVhf8'}
# use call() without sys.exit on HTTP errors
import urllib.request
def safe_get(path):
    req = urllib.request.Request(cl.BASE + path, headers=cl._headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'_error': e.code, '_detail': e.read().decode(errors='replace')[:300]}
live = {}
for k, sid in SYMS.items():
    pos = safe_get(f'/portfolio/accounts/{acct}/symphonies/{sid}')
    if '_error' in pos:
        print(k, 'ERROR', pos); continue
    live[k] = pos
    d = [cl.epoch_ms_to_date(ms).isoformat() for ms in pos['epoch_ms']]
    if not d:
        print(k, 'EMPTY live series', {kk: (len(vv) if isinstance(vv, list) else vv) for kk, vv in pos.items()}); continue
    print(k, 'keys', sorted(pos.keys()), 'n', len(d), d[0], '->', d[-1])
    for key in ('series', 'deposit_adjusted_series'):
        s = pos.get(key)
        if s: print('   ', key, s[:3], '...', s[-3:])
json.dump(live, open(f'{OUT}/live_symphonies.json', 'w'))
vers = {}
for k in ('HG', 'ORIG', 'KMLM', 'SLEEVE', 'HARV'):
    v = safe_get(f'/symphonies/{SYMS[k]}/versions')
    vers[k] = v
    if isinstance(v, list):
        print(k, 'versions', len(v))
        for x in v[-12:]:
            print('   ', {kk: x.get(kk) for kk in ('version_id', 'created_at', 'semantic_update', 'is_semantic', 'name') if kk in x} or str(x)[:200])
    else:
        print(k, 'versions resp', str(v)[:300])
json.dump(vers, open(f'{OUT}/versions.json', 'w'))
