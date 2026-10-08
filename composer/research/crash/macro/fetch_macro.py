import urllib.request, json, re, sys, os, datetime as dt
import os; OUT=os.path.join(os.environ.get('CRASH_DATA', os.path.dirname(os.path.abspath(__file__))), 'macro')
def get(url, timeout=60):
    rq=urllib.request.Request(url, headers={"user-agent":"Mozilla/5.0"})
    return urllib.request.urlopen(rq, timeout=timeout).read().decode('utf-8','replace')
res={}
for sid in ('DGS10','DGS3MO','T10Y3M','DCOILWTICO','BAA10Y','BAMLH0A0HYM2','UNRATE','AAA','BAA','TB3MS','GS10'):
    try:
        txt=get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}')
        rows=[l.split(',') for l in txt.strip().splitlines()[1:]]
        ser={r[0]:float(r[1]) for r in rows if len(r)==2 and r[1] not in ('.','')}
        json.dump(ser, open(f'{OUT}/fred_{sid}.json','w')); ds=sorted(ser); res[sid]=(len(ser), ds[0], ds[-1])
    except Exception as e:
        res[sid]=('ERR', str(e)[:80])
print(json.dumps(res, indent=0))
# Shiller CAPE monthly from multpl
try:
    html=get('https://www.multpl.com/shiller-pe/table/by-month')
    rows=re.findall(r'<td class="left">\s*([A-Z][a-z]{2} \d{1,2}, \d{4})\s*</td>\s*<td class="right">\s*([\d.]+)', html)
    cape={}
    for d,v in rows:
        m=dt.datetime.strptime(d,'%b %d, %Y'); cape[m.strftime('%Y-%m')]=float(v)
    json.dump(cape, open(f'{OUT}/cape_multpl.json','w')); ds=sorted(cape); print('CAPE multpl', len(cape), ds[0], ds[-1], cape[ds[-1]])
except Exception as e:
    print('CAPE multpl ERR', str(e)[:120])
# Shiller xls (raw) — just test reachability
try:
    rq=urllib.request.Request('http://www.econ.yale.edu/~shiller/data/ie_data.xls', headers={"user-agent":"Mozilla/5.0"})
    b=urllib.request.urlopen(rq, timeout=60).read(); open(f'{OUT}/ie_data.xls','wb').write(b); print('shiller xls bytes', len(b))
except Exception as e:
    print('shiller xls ERR', str(e)[:120])
