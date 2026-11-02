#!/usr/bin/env python3 -I
"""Parse Reinhart-Rogoff 'Global Crises Data by Country' (HBS BFFS, 20160923_global_crisis_data.xlsx, 70 countries, 1800-2016)
into per-year counts: data/rr_crisis_counts_by_year.csv and the per-country flags 1970+: data/rr_country_year_flags.csv
Source: https://www.hbs.edu/behavioral-finance-and-financial-stability/Documents/ChartData/MapCharts/20160923_global_crisis_data.xlsx"""
import zipfile, re, csv, os, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
z = zipfile.ZipFile(os.path.join(ROOT, 'raw', 'rr_global_crisis_data.xlsx'))
ss = [re.sub(r'<[^>]+>', '', s) for s in re.findall(r'<si>(.*?)</si>', z.read('xl/sharedStrings.xml').decode(), re.S)]
x = z.read('xl/worksheets/sheet1.xml').decode()
rows = re.findall(r'<row [^>]*r="(\d+)"[^>]*>(.*?)</row>', x, re.S)
def cells(r):
    out = {}
    for m in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*)>(?:<v>(.*?)</v>)?', r):
        col, attrs, v = m.groups()
        if v is None: continue
        if 't="s"' in attrs: v = ss[int(v)]
        out[col] = v
    return out
def flag(v):
    try: return 1 if float(v) >= 1 else 0
    except: return 0
recs = []
for rn, r in rows[2:]:
    c = cells(r)
    try: yr = int(float(c.get('D', '')))
    except: continue
    if yr < 1970: continue
    recs.append(dict(country=c.get('C', ''), year=yr, banking=flag(c.get('E', '0')), systemic=flag(c.get('G', '0')),
                     ext_default=flag(c.get('T', '0')), dom_default=flag(c.get('Q', '0')), currency=flag(c.get('Z', '0')), inflation=flag(c.get('AA', '0'))))
with open(os.path.join(ROOT, 'data', 'rr_country_year_flags.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(recs[0].keys())); w.writeheader(); w.writerows(recs)
by = collections.defaultdict(lambda: collections.Counter())
ncty = collections.defaultdict(set)
# new-start flags: banking crisis year where previous year was 0
prev = {}
for r in sorted(recs, key=lambda r: (r['country'], r['year'])):
    k = r['country']
    for fld in ['banking', 'systemic', 'ext_default', 'currency']:
        by[r['year']][fld] += r[fld]
        if r[fld] and not prev.get((k, fld), 0): by[r['year']][fld + '_new'] += 1
        prev[(k, fld)] = r[fld]
    ncty[r['year']].add(k)
with open(os.path.join(ROOT, 'data', 'rr_crisis_counts_by_year.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['year', 'n_countries', 'banking', 'banking_new', 'systemic', 'systemic_new', 'ext_default', 'ext_default_new', 'currency', 'currency_new'])
    for y in sorted(by):
        b = by[y]; w.writerow([y, len(ncty[y]), b['banking'], b['banking_new'], b['systemic'], b['systemic_new'], b['ext_default'], b['ext_default_new'], b['currency'], b['currency_new']])
        print(y, len(ncty[y]), 'bank', b['banking'], 'new', b['banking_new'], 'curr', b['currency'], 'new', b['currency_new'], 'extdef', b['ext_default'], 'new', b['ext_default_new'])
