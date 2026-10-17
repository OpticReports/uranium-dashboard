"""Fetch the treasury-canary inputs used as leverage-gate candidates (keyless).

FRED (fredgraph CSV): DGS2, DGS10, DFII10, THREEFYTP10, T10Y3M, and the canary's leading stack
(PERMIT, TEMPHELPS, HTRUCKSSAAR, NEWORDER, CFNAI, IC4WSA, SAHMREALTIME).
FINRA margin statistics workbook (1997-01..), parsed with the standard library (no openpyxl).
OFR Financial Stress Index (2000-..).
Downloads are written to LEVGATE_DATA/canary/raw/ and parsed into canary/<name>.json {date: value};
nothing downloaded is executed.
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from levgate import OUT   # noqa: E402

DIR = os.path.join(OUT, 'canary')
RAW = os.path.join(DIR, 'raw')
os.makedirs(RAW, exist_ok=True)
FRED = ['DGS2', 'DGS10', 'DFII10', 'THREEFYTP10', 'T10Y3M', 'PERMIT', 'TEMPHELPS', 'HTRUCKSSAAR', 'NEWORDER', 'CFNAI', 'IC4WSA', 'SAHMREALTIME']
FINRA = 'https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx'
OFR = 'https://www.financialresearch.gov/financial-stress-index/data/fsi.csv'


def curl(url, path):
    r = subprocess.run(['curl', '-sSL', '--http1.1', '--retry', '2', '--retry-delay', '3', '--retry-all-errors', '--connect-timeout', '20', '--max-time', '90', '-A', 'Mozilla/5.0', '-o', path, url], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) < 200:
        raise RuntimeError(f'fetch failed {url}: {r.stderr.strip()[:200]}')


def parse_fred(path):
    out = {}
    for row in csv.reader(io.StringIO(open(path).read())):
        if len(row) != 2 or not re.match(r'\d{4}-\d{2}-\d{2}', row[0]):
            continue
        try:
            out[row[0]] = float(row[1])
        except ValueError:
            pass
    return out


def parse_xlsx(path):
    """FINRA workbook: Year-Month | debit balances | free credit cash | free credit margin (newest first)."""
    z = zipfile.ZipFile(path)
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', ns):
            shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % ns['m'])))
    sheet = sorted(n for n in z.namelist() if n.startswith('xl/worksheets/sheet'))[0]
    rows = []
    for r in ET.fromstring(z.read(sheet)).iter('{%s}row' % ns['m']):
        vals = {}
        for c in r.findall('m:c', ns):
            col = re.match(r'[A-Z]+', c.get('r')).group(0)
            if c.get('t') == 'inlineStr':
                vals[col] = ''.join(t.text or '' for t in c.iter('{%s}t' % ns['m']))
                continue
            v = c.find('m:v', ns)
            if v is None:
                continue
            txt = v.text
            vals[col] = shared[int(txt)] if c.get('t') == 's' else txt
        rows.append(vals)
    out = {}
    for vals in rows:
        ym, debit = vals.get('A'), vals.get('B')
        if ym is None or debit is None:
            continue
        m = re.match(r'(\d{4})-(\d{2})', str(ym))
        if m:
            key = f'{m.group(1)}-{m.group(2)}'
        else:
            try:     # Excel serial date
                d = date(1899, 12, 30) + timedelta(days=int(float(ym)))
                key = f'{d.year:04d}-{d.month:02d}'
            except ValueError:
                continue
        try:
            out[key] = float(debit)
        except ValueError:
            pass
    return out


def parse_ofr(path):
    out = {}
    rd = csv.reader(io.StringIO(open(path).read()))
    hdr = next(rd)
    col = next((i for i, h in enumerate(hdr) if h.strip().upper() in ('OFR FSI', 'OFRFSI', 'FSI')), 1)
    for row in rd:
        if row and re.match(r'\d{4}-\d{2}-\d{2}', row[0]):
            try:
                out[row[0]] = float(row[col])
            except (ValueError, IndexError):
                pass
    return out


def fetch_treasury(kind, years):
    """Treasury daily par (nominal) or real yield curve, one CSV per year (keyless)."""
    out = {}
    for y in years:
        p = os.path.join(RAW, f'treasury_{kind}_{y}.csv')
        if not os.path.exists(p) or y >= 2026:
            curl(f'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all'
                 f'?type={kind}&field_tdr_date_value={y}&page&_format=csv', p)
        rd = csv.reader(io.StringIO(open(p).read()))
        hdr = [h.strip().upper() for h in next(rd)]
        for row in rd:
            m = re.match(r'(\d{2})/(\d{2})/(\d{4})', row[0])
            if not m:
                continue
            d = f'{m.group(3)}-{m.group(1)}-{m.group(2)}'
            for i, h in enumerate(hdr[1:], 1):
                try:
                    out.setdefault(h, {})[d] = float(row[i])
                except (ValueError, IndexError):
                    pass
    return out


def fetch_acm():
    """NY Fed ACM term premium (daily sheet), keyless .xls."""
    import xlrd
    p = os.path.join(RAW, 'ACMTermPremium.xls')
    curl('https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls', p)
    wb = xlrd.open_workbook(p)
    sh = next((wb.sheet_by_name(n) for n in wb.sheet_names() if 'daily' in n.lower()), wb.sheet_by_index(0))
    hdr = [str(c.value).strip().upper() for c in sh.row(0)]
    col = hdr.index('ACMTP10')
    out = {}
    for r in range(1, sh.nrows):
        c0 = sh.cell(r, 0)
        try:
            if c0.ctype == xlrd.XL_CELL_DATE:
                d = xlrd.xldate_as_datetime(c0.value, wb.datemode).date().isoformat()
            else:
                d = datetime_from(str(c0.value))
            out[d] = float(sh.cell(r, col).value)
        except (ValueError, TypeError):
            pass
    return out


def datetime_from(txt):
    from datetime import datetime
    for f in ('%d-%b-%Y', '%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(txt.strip(), f).date().isoformat()
        except ValueError:
            pass
    raise ValueError(txt)


def save(name, v):
    json.dump(v, open(os.path.join(DIR, f'{name}.json'), 'w'))
    ks = sorted(v)
    print(f'{name:13s} {len(ks):6d} {ks[0] if ks else "-"} .. {ks[-1] if ks else "-"}  last {v[ks[-1]] if ks else "-"}')


def main(only=None):
    status = {}
    jobs = {
        'FINRA': lambda: {'FINRA_DEBIT': parse_xlsx((curl(FINRA, os.path.join(RAW, 'finra_margin.xlsx')), os.path.join(RAW, 'finra_margin.xlsx'))[1])},
        'OFR': lambda: {'OFR_FSI': parse_ofr((curl(OFR, os.path.join(RAW, 'ofr_fsi.csv')), os.path.join(RAW, 'ofr_fsi.csv'))[1])},
        'TREASURY': lambda: (lambda n, r: {'UST_2Y': n['2 YR'], 'UST_10Y': n['10 YR'], 'UST_3M': n['3 MO'], 'TIPS_10Y': r['10 YR']})(
            fetch_treasury('daily_treasury_yield_curve', range(1990, 2027)), fetch_treasury('daily_treasury_real_yield_curve', range(2003, 2027))),
        'ACM': lambda: {'ACM_TP10': fetch_acm()},
        'FRED': lambda: {s_: parse_fred((curl(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={s_}', os.path.join(RAW, f'{s_}.csv')), os.path.join(RAW, f'{s_}.csv'))[1]) for s_ in FRED},
    }
    for name, job in jobs.items():
        if only and name not in only:
            continue
        try:
            for k, v in job().items():
                save(k, v)
            status[name] = 'ok'
        except Exception as ex:   # one dead source never blocks the others
            status[name] = f'FAILED: {str(ex)[:160]}'
            print(name, status[name])
    prev = json.load(open(os.path.join(DIR, 'status.json'))) if os.path.exists(os.path.join(DIR, 'status.json')) else {}
    prev.update(status)
    json.dump(prev, open(os.path.join(DIR, 'status.json'), 'w'), indent=1)
    return status


if __name__ == '__main__':
    main(sys.argv[1:] or None)
