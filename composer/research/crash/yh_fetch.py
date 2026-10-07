import json, urllib.request, datetime as dt, os, sys, time
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import SP
def fetch(t, force=False):
    fn=f"{SP}/{t.replace('^','_').replace('=','_')}.json"
    if os.path.exists(fn) and not force: return json.load(open(fn))
    url=(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}?period1=0&period2=4102444800&interval=1d&events=div%7Csplit")
    for k in range(3):
        try:
            rq=urllib.request.Request(url,headers={"user-agent":"Mozilla/5.0"})
            res=json.load(urllib.request.urlopen(rq,timeout=60))["chart"]["result"][0]; break
        except Exception as ex:
            err=ex; time.sleep(2); res=None
    if res is None: print('FAIL',t,err); return None
    ts=res['timestamp']; q=res['indicators']['quote'][0]; ac=(res['indicators'].get('adjclose') or [{}])[0].get('adjclose')
    dates=[dt.datetime.fromtimestamp(x,tz=dt.timezone.utc).date().isoformat() for x in ts]
    out={'dates':[],'close':[],'adjclose':[]}
    for i,d in enumerate(dates):
        c=q['close'][i]; a=(ac[i] if ac else None)
        if c is None: continue
        out['dates'].append(d); out['close'].append(float(c)); out['adjclose'].append(float(a if a is not None else c))
    json.dump(out,open(fn,'w')); return out
import urllib.parse
if __name__=='__main__':
    for t in sys.argv[1:]:
        o=fetch(t)
        if o: print(f"{t:8s} {len(o['dates']):6d} {o['dates'][0]} .. {o['dates'][-1]}")
