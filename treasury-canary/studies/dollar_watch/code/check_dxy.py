import json, csv, sys, datetime as dt
raw = sys.argv[1]; a_daily = sys.argv[2]
j = json.load(open(raw))
r = j['chart']['result'][0]
ts = r['timestamp']; q = r['indicators']['quote'][0]
rows = []
for t, o, h, l, c in zip(ts, q['open'], q['high'], q['low'], q['close']):
    if c is None: continue
    d = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()  # check tz
    rows.append((d, o, h, l, c))
print('fresh rows', len(rows), rows[0][0], rows[-1][0])
# tz check: show a timestamp
print('first ts', ts[0], dt.datetime.fromtimestamp(ts[0], dt.timezone.utc), 'meta gmtoffset', r['meta'].get('gmtoffset'), r['meta'].get('exchangeTimezoneName'))
byd = {d: (o, h, l, c) for d, o, h, l, c in rows}
def near(dstr):
    d = dt.date.fromisoformat(dstr)
    for k in range(0, 4):
        dd = d + dt.timedelta(days=k)
        if dd in byd: return dd, byd[dd]
    return None, None
for dstr in ['2026-11-02', '1985-02-25', '2008-03-17', '2022-09-27', '2022-09-28', '2025-01-13', '2026-01-27', '2026-10-12', '2026-01-29', '2022-02-28', '2022-08-26','2022-08-29','2022-08-30', '2009-03-03', '2009-03-04', '2020-03-09','2020-03-20', '1987-10-02','1987-10-30','1987-12-31', '1995-04-19', '2011-05-04', '1998-08-28','1998-10-08','2023-03-08','2023-03-31','2024-07-31','2024-08-05','2025-04-01','2025-04-21','2026-02-27','2026-04-30','2001-07-06','2026-10-30']:
    dd, v = near(dstr)
    print(dstr, '->', dd, None if v is None else tuple(round(x, 3) for x in v))
# global extremes
mx = max(rows, key=lambda x: x[4]); mn = min(rows, key=lambda x: x[4])
print('max close', mx[0], round(mx[4],3), 'max high', max(rows, key=lambda x: x[2])[0], round(max(rows, key=lambda x: x[2])[2],3))
print('min close', mn[0], round(mn[4],3), 'min low', min(rows, key=lambda x: x[3])[0], round(min(rows, key=lambda x: x[3])[3],3))
# 2026 low
r26 = [x for x in rows if x[0].year == 2026]
print('2026 min close', min(r26, key=lambda x: x[4])[:1], round(min(r26, key=lambda x: x[4])[4],3), 'min low', min(r26, key=lambda x: x[3])[0], round(min(r26, key=lambda x: x[3])[3],3))
print('2026 max close', max(r26, key=lambda x: x[4])[0], round(max(r26, key=lambda x: x[4])[4],3))
r25 = [x for x in rows if x[0].year == 2025]
print('2025 max high', max(r25, key=lambda x: x[2])[0], round(max(r25, key=lambda x: x[2])[2],3), 'max close', max(r25, key=lambda x: x[4])[0], round(max(r25, key=lambda x: x[4])[4],3))
r22 = [x for x in rows if x[0].year == 2022]
print('2022 max close', max(r22, key=lambda x: x[4])[0], round(max(r22, key=lambda x: x[4])[4],3), 'max high', max(r22, key=lambda x: x[2])[0], round(max(r22, key=lambda x: x[2])[2],3))
r08 = [x for x in rows if 2007 <= x[0].year <= 2009]
print('07-09 min close', min(r08, key=lambda x: x[4])[0], round(min(r08, key=lambda x: x[4])[4],3), 'min low', min(r08, key=lambda x: x[3])[0], round(min(r08, key=lambda x: x[3])[3],3))
# compare with finder A daily
A = {}
for rr in csv.DictReader(open(a_daily)):
    A[dt.date.fromisoformat(rr['date'])] = float(rr['close'])
print('A rows', len(A), min(A), max(A))
diff = [(d, A[d], byd[d][3]) for d in A if d in byd and abs(A[d]-byd[d][3])>1e-6]
missA = [d for d in byd if d not in A]; missF = [d for d in A if d not in byd]
print('close diffs', len(diff), diff[:5]); print('in fresh not A', len(missA), missA[:5]); print('in A not fresh', len(missF), missF[:5])
# write clean csv
w = csv.writer(open('raw/dxy_daily_fresh.csv','w')); w.writerow(['date','open','high','low','close'])
for d,o,h,l,c in rows: w.writerow([d,o,h,l,c])
