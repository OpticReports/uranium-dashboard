#!/usr/bin/env python3 -I
"""Build data/dollar_monthly.csv, data/gold_monthly.csv, data/dxy_daily.csv, data/gold_daily.csv
from raw/ fetched files. Run: python3 -I scripts/build_series.py  (from finderA/)
Sources (all free, fetched 2026-11-02):
  Yahoo DX-Y.NYB daily  https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?period1=0&period2=1800000000&interval=1d
  FRED DTWEXM, TWEXMMTH, DTWEXBGS, DTWEXAFEGS, DTWEXB  https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID>
  BIS WS_EER M.N.N.US (narrow, 1964+) / M.N.B.US (broad, 1994+)  https://stats.bis.org/api/v1/data/WS_EER/M.N.N.US/all?format=csv
  World Bank Pink Sheet monthly gold ($/toz)  https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx
  datahub gold monthly (WB-derived, cross-check)  https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv
  Yahoo GC=F daily (COMEX front month, 2000-08-30+)  https://query1.finance.yahoo.com/v8/finance/chart/GC=F?period1=0&period2=1800000000&interval=1d
"""
import csv, json, datetime as dt, os, re, zipfile, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, 'raw'); DATA = os.path.join(ROOT, 'data')
os.makedirs(DATA, exist_ok=True)

def ym(d): return f"{d.year:04d}-{d.month:02d}"

def yahoo_daily(fn):
    r = json.load(open(os.path.join(RAW, fn)))['chart']['result'][0]
    q = r['indicators']['quote'][0]
    out = []
    for t, o, h, l, c in zip(r['timestamp'], q['open'], q['high'], q['low'], q['close']):
        if c is None: continue
        d = dt.datetime.utcfromtimestamp(t).date()
        out.append((d, o, h, l, c))
    return out

def fred_daily(fn):
    out = {}
    with open(os.path.join(RAW, fn)) as f:
        rd = csv.reader(f); next(rd)
        for d, v in rd:
            if v in ('', '.'): continue
            out[dt.date.fromisoformat(d)] = float(v)
    return out

def bis_monthly(fn):
    out = {}
    with open(os.path.join(RAW, fn)) as f:
        for row in csv.DictReader(f):
            out[row['TIME_PERIOD']] = float(row['OBS_VALUE'])
    return out

def monthly_from_daily(rows):
    """rows: list of (date, open, high, low, close) -> {ym: dict(close, avg, high, low, high_date, low_date, last_date)}"""
    m = {}
    for d, o, h, l, c in rows:
        k = ym(d); e = m.setdefault(k, {'closes': [], 'high': -1e9, 'low': 1e9})
        e['closes'].append(c); e['last'] = c; e['last_date'] = d
        hh = h if h is not None else c; ll = l if l is not None else c
        if hh > e['high']: e['high'], e['high_date'] = hh, d
        if ll < e['low']: e['low'], e['low_date'] = ll, d
    for k, e in m.items():
        e['avg'] = statistics.mean(e['closes']); e['n'] = len(e['closes'])
    return m

def daily_to_monthly_avg_eom(dd):
    m = {}
    for d in sorted(dd):
        k = ym(d); e = m.setdefault(k, {'vals': []}); e['vals'].append(dd[d]); e['eom'] = dd[d]
    for e in m.values(): e['avg'] = statistics.mean(e['vals'])
    return m

# ---------- Dollar ----------
dxy = yahoo_daily('yahoo_dxy_1d_full.json')
with open(os.path.join(DATA, 'dxy_daily.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['date', 'open', 'high', 'low', 'close'])
    for d, o, h, l, c in dxy: w.writerow([d, o, h, l, c])
dxy_m = monthly_from_daily(dxy)
dtwexm = daily_to_monthly_avg_eom(fred_daily('fred_DTWEXM.csv'))
twexmmth = {ym(d): v for d, v in fred_daily('fred_TWEXMMTH.csv').items()}
bgs = daily_to_monthly_avg_eom(fred_daily('fred_DTWEXBGS.csv'))
afe = daily_to_monthly_avg_eom(fred_daily('fred_DTWEXAFEGS.csv'))
dtwexb = daily_to_monthly_avg_eom(fred_daily('fred_DTWEXB.csv'))
bis_n = bis_monthly('bis_eer_narrow_us.csv'); bis_b = bis_monthly('bis_eer_broad_us.csv')

# Splice: a long "major-currency" monthly-average series.  DTWEXM (Fed majors, Mar-1973=100) through 2019-12,
# then DTWEXAFEGS (Fed advanced foreign economies, Jan-2006=100) chained at the 2019-12 ratio.
splice = {}
ratio = dtwexm['2019-12']['avg'] / afe['2019-12']['avg']
for k in sorted(set(dtwexm) | set(afe)):
    if k in dtwexm: splice[k] = dtwexm[k]['avg']
    elif k in afe: splice[k] = afe[k]['avg'] * ratio

months = []
y, m = 1971, 1
today = dt.date.today()
while (y, m) <= (today.year, today.month):
    months.append(f"{y:04d}-{m:02d}"); m += 1
    if m == 13: y, m = y + 1, 1

with open(os.path.join(DATA, 'dollar_monthly.csv'), 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['month', 'dxy_close', 'dxy_avg', 'dxy_high', 'dxy_high_date', 'dxy_low', 'dxy_low_date', 'dxy_ndays',
                'fed_major_DTWEXM_avg', 'fed_major_DTWEXM_eom', 'fed_TWEXMMTH', 'fed_broad_DTWEXBGS_avg', 'fed_afe_DTWEXAFEGS_avg',
                'fed_broad_old_DTWEXB_avg', 'bis_narrow_neer', 'bis_broad_neer', 'fed_major_spliced_afe'])
    for k in months:
        e = dxy_m.get(k, {})
        w.writerow([k,
                    f"{e['last']:.3f}" if e else '', f"{e['avg']:.3f}" if e else '',
                    f"{e['high']:.3f}" if e else '', e.get('high_date', ''), f"{e['low']:.3f}" if e else '', e.get('low_date', ''), e.get('n', ''),
                    f"{dtwexm[k]['avg']:.3f}" if k in dtwexm else '', f"{dtwexm[k]['eom']:.3f}" if k in dtwexm else '',
                    f"{twexmmth[k]:.3f}" if k in twexmmth else '',
                    f"{bgs[k]['avg']:.3f}" if k in bgs else '', f"{afe[k]['avg']:.3f}" if k in afe else '',
                    f"{dtwexb[k]['avg']:.3f}" if k in dtwexb else '',
                    f"{bis_n[k]:.2f}" if k in bis_n else '', f"{bis_b[k]:.2f}" if k in bis_b else '',
                    f"{splice[k]:.3f}" if k in splice else ''])

# ---------- Gold ----------
def pinksheet_gold():
    z = zipfile.ZipFile(os.path.join(RAW, 'wb_pinksheet.xlsx'))
    ss = [re.sub(r'<[^>]+>', '', s) for s in re.findall(r'<si>(.*?)</si>', z.read('xl/sharedStrings.xml').decode(), re.S)]
    x = z.read('xl/worksheets/sheet2.xml').decode()
    rows = re.findall(r'<row [^>]*r="(\d+)"[^>]*>(.*?)</row>', x, re.S)
    out = {}
    for rn, r in rows:
        cells = {}
        for mm in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*)>(?:<v>(.*?)</v>)?', r):
            col, attrs, v = mm.groups()
            if v is None: continue
            if 't="s"' in attrs: v = ss[int(v)]
            cells[col] = v
        a = cells.get('A', '')
        if re.match(r'^\d{4}M\d{2}$', a) and 'BR' in cells:
            try: out[a[:4] + '-' + a[5:]] = float(cells['BR'])
            except ValueError: pass
    return out
wb_gold = pinksheet_gold()
dh = {}
with open(os.path.join(RAW, 'datahub_gold2.csv')) as f:
    rd = csv.reader(f); next(rd)
    for d, p in rd: dh[d] = float(p)
gc = yahoo_daily('yahoo_gc_1d.json')
with open(os.path.join(DATA, 'gold_daily.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['date', 'open', 'high', 'low', 'close'])
    for d, o, h, l, c in gc: w.writerow([d, o, h, l, c])
gc_m = monthly_from_daily(gc)
with open(os.path.join(DATA, 'gold_monthly.csv'), 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['month', 'wb_pinksheet_avg', 'datahub_avg', 'gcf_close', 'gcf_avg', 'gcf_high', 'gcf_low', 'gcf_low_date', 'gold_best'])
    for k in months:
        e = gc_m.get(k, {})
        best = wb_gold.get(k, dh.get(k, e.get('avg')))
        w.writerow([k, wb_gold.get(k, ''), dh.get(k, ''),
                    f"{e['last']:.2f}" if e else '', f"{e['avg']:.2f}" if e else '', f"{e['high']:.2f}" if e else '', f"{e['low']:.2f}" if e else '', e.get('low_date', ''),
                    f"{best:.2f}" if best is not None else ''])

# ---------- S&P 500 (severity proxy) ----------
spx = yahoo_daily('yahoo_gspc_1d.json')   # https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?period1=0&period2=1800000000&interval=1d
with open(os.path.join(DATA, 'spx_daily.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['date', 'close'])
    for d, o, h, l, c in spx: w.writerow([d, c])
# ---------- report ----------
last = dxy[-1]
def dxy_close_on_or_before(d):
    c = None
    for row in dxy:
        if row[0] <= d: c = row[4]
        else: break
    return c
c6 = dxy_close_on_or_before(last[0] - dt.timedelta(days=182)); c12 = dxy_close_on_or_before(last[0] - dt.timedelta(days=365))
print(f"DXY last {last[0]} close {last[4]:.3f}; 6m chg {100*(last[4]/c6-1):+.2f}% (from {c6:.3f}); 12m chg {100*(last[4]/c12-1):+.2f}% (from {c12:.3f})")
print('DXY daily rows', len(dxy), dxy[0][0], '->', dxy[-1][0])
print('DXY 1973-03 avg', round(dxy_m['1973-03']['avg'], 2), '| DTWEXM 1973-03 avg', round(dtwexm['1973-03']['avg'], 2))
for k in ['2026-08', '2026-09', '2026-10']:
    print(k, 'dxy_close', round(dxy_m[k]['last'], 2), 'BGS', round(bgs[k]['avg'], 2) if k in bgs else None, 'AFE', round(afe[k]['avg'], 2) if k in afe else None, 'BIS broad', bis_b.get(k), 'BIS narrow', bis_n.get(k))
bl = sorted(bgs)[-1]; print('FRED DTWEXBGS last month', bl, round(bgs[bl]['eom'], 2), ' max of series', max((v['avg'], k) for k, v in bgs.items()))
print('WB gold months', len(wb_gold), min(wb_gold), max(wb_gold), '| datahub', min(dh), max(dh))
diffs = [abs(wb_gold[k] - dh[k]) / wb_gold[k] for k in wb_gold if k in dh]
print('WB vs datahub max rel diff', max(diffs))
print('GC=F last', gc[-1][0], gc[-1][4])
