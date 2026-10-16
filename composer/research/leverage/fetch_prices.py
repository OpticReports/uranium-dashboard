"""Yahoo daily close + adjclose, 2025-06-01 .. 2026-10-15 (last complete close), for every held
ticker, every 1x substitute, SPY and ^IRX.  Refuses a series without adjclose (no silent
fallback to close).  Cache: lev/yh/<T>.json"""
import json, os, sys, time, urllib.request, urllib.parse, datetime as dt
OUT = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/lev/yh'
P1 = int(dt.datetime(2025, 6, 1, tzinfo=dt.timezone.utc).timestamp()); P2 = int(dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc).timestamp())
END = '2026-10-15'
def fetch(t):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}?period1={P1}&period2={P2}&interval=1d&events=div%7Csplit"
    err = None
    for k in range(4):
        try:
            rq = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
            res = json.load(urllib.request.urlopen(rq, timeout=60))["chart"]["result"][0]; break
        except Exception as ex:
            err = ex; time.sleep(2 * (k + 1)); res = None
    if res is None:
        return None, f'fetch failed: {err}'
    ts = res['timestamp']; q = res['indicators']['quote'][0]
    ac = (res['indicators'].get('adjclose') or [{}])[0].get('adjclose')
    if t != '^IRX' and not ac:
        return None, 'no adjclose'
    out = {'dates': [], 'close': [], 'adjclose': [], 'divs': {}}
    for i, x in enumerate(ts):
        d = dt.datetime.fromtimestamp(x, tz=dt.timezone.utc).date().isoformat()
        c = q['close'][i]
        if c is None or d > END: continue
        a = ac[i] if ac else c
        if a is None: return None, f'adjclose missing on {d}'
        out['dates'].append(d); out['close'].append(float(c)); out['adjclose'].append(float(a))
    for v in (res.get('events', {}).get('dividends') or {}).values():
        out['divs'][dt.datetime.fromtimestamp(v['date'], tz=dt.timezone.utc).date().isoformat()] = v['amount']
    return out, None
if __name__ == '__main__':
    bad = []
    for t in sys.argv[1:]:
        o, e = fetch(t)
        if o is None:
            bad.append((t, e)); print(f'{t:6s} FAIL {e}'); continue
        json.dump(o, open(f"{OUT}/{t.replace('^', '_')}.json", 'w'))
        print(f"{t:6s} {len(o['dates']):4d} {o['dates'][0]} .. {o['dates'][-1]}  divs {len(o['divs'])}")
    if bad: print('FAILED:', bad); sys.exit(1)
