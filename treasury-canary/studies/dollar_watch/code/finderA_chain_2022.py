#!/usr/bin/env python3 -I
"""The 2022 chain: DXY daily (Yahoo DX-Y.NYB) on each dated event, % change from the 28-Feb-2022 reserve freeze and from
the 3-Jan-2022 S&P peak / 16-Mar-2022 first Fed hike. Also the 1-Jul-2008 -> 3-Mar-2009 and 2014-07 -> 2015-03 comparators.
Output data/chain_2022.csv. Run from finderA/: python3 -I scripts/chain_2022.py"""
import csv, os, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D = os.path.join(ROOT, 'data')
px = {}
for r in csv.DictReader(open(os.path.join(D, 'dxy_daily.csv'))): px[dt.date.fromisoformat(r['date'])] = (float(r['close']), float(r['high']))
days = sorted(px)
def on_or_before(d):
    c = None
    for x in days:
        if x <= d: c = x
        else: break
    return c
events = [
    ('2022-01-03', 'S&P 500 all-time high (pre-bear)', 'market record'),
    ('2022-02-24', 'Russia invades Ukraine', 'public record'),
    ('2022-02-28', 'US Treasury/OFAC Directive 4: CBR, NWF, MinFin transactions prohibited (reserves immobilised)', 'https://home.treasury.gov/news/press-releases/jy0612'),
    ('2022-03-16', 'First Fed hike (+25bp) of the cycle', 'https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm'),
    ('2022-04-12', 'Sri Lanka suspends external debt payments', 'https://eastmojo.com/news/2022/04/12/crisis-hit-sri-lanka-announces-debt-default/'),
    ('2022-05-04', 'Fed +50bp', 'https://www.federalreserve.gov/newsevents/pressreleases/monetary20220504a.htm'),
    ('2022-06-15', 'Fed +75bp (first of four)', 'https://www.federalreserve.gov/newsevents/pressreleases/monetary20220615a.htm'),
    ('2022-07-21', 'ECB announces TPI (+50bp hike)', 'https://www.ecb.europa.eu/press/pr/date/2022/html/ecb.pr220721~973e6e7273.en.html'),
    ('2022-08-28', 'Six months after the reserve freeze', 'computed'),
    ('2022-09-22', 'Japan MoF first yen-buying intervention since 1998', 'https://www.mof.go.jp/english/policy/international_policy/reference/feio/index.html'),
    ('2022-09-23', 'UK mini-budget; gilt selloff begins', 'public record'),
    ('2022-09-28', 'BoE announces temporary gilt purchases; DXY intraday high 114.78', 'https://www.bankofengland.co.uk/news/2022/september/bank-of-england-announces-gilt-market-operation'),
    ('2022-10-12', 'S&P 500 bear-market low', 'market record'),
    ('2022-10-14', 'BoE gilt operations end', 'BoE (end-date page 404 on probe; UNVERIFIED URL)'),
    ('2022-10-21', 'Japan MoF second intervention (USDJPY ~151.9)', 'https://www.mof.go.jp/english/policy/international_policy/reference/feio/index.html'),
    ('2022-11-11', 'FTX bankruptcy', 'public record'),
    ('2022-12-19', 'Ghana suspends external debt service', 'https://modeldiplomat.com/learn/glossary/ghana-default-2022'),
    ('2022-12-20', 'BoJ widens YCC band to +/-50bp', 'https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2022/k221220a.pdf'),
]
ref = {'freeze_2022-02-28': px[on_or_before(dt.date(2022, 2, 28))][0], 'spx_peak_2022-01-03': px[on_or_before(dt.date(2022, 1, 3))][0], 'fed_hike_2022-03-16': px[on_or_before(dt.date(2022, 3, 16))][0]}
rows = []
for d, name, src in events:
    dd = on_or_before(dt.date.fromisoformat(d)); c, h = px[dd]
    rows.append({'date': d, 'event': name, 'dxy_close': f"{c:.2f}", 'dxy_high': f"{h:.2f}", 'pct_from_freeze_2022-02-28': f"{100*(c/ref['freeze_2022-02-28']-1):+.1f}",
                 'pct_from_2022-01-03': f"{100*(c/ref['spx_peak_2022-01-03']-1):+.1f}", 'pct_from_first_hike_2022-03-16': f"{100*(c/ref['fed_hike_2022-03-16']-1):+.1f}", 'source': src})
with open(os.path.join(D, 'chain_2022.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for r in rows: print(f"{r['date']} {r['dxy_close']:>7} {r['pct_from_freeze_2022-02-28']:>6} {r['pct_from_2022-01-03']:>6} {r['pct_from_first_hike_2022-03-16']:>6}  {r['event']}")
# the DXY path in 2022: peak and the 6-month windows
pk = max((px[d][1], d) for d in days if dt.date(2022, 1, 1) <= d <= dt.date(2022, 12, 31)); print('2022 intraday high', pk)
pkc = max((px[d][0], d) for d in days if dt.date(2022, 1, 1) <= d <= dt.date(2022, 12, 31)); print('2022 closing high', pkc)
print('freeze->closing high %:', round(100 * (pkc[0] / ref['freeze_2022-02-28'] - 1), 1), '| 2021-05-25 (2021 low ~89.5) -> peak %:', round(100 * (pkc[0] / px[on_or_before(dt.date(2021, 5, 25))][0] - 1), 1))
# pre-freeze rise: 2021-06-01 -> 2022-02-28
print('2021-06-01 -> 2022-02-28 %:', round(100 * (ref['freeze_2022-02-28'] / px[on_or_before(dt.date(2021, 6, 1))][0] - 1), 1))
for a, b, lab in [((2008, 7, 15), (2009, 3, 4), 'GFC run 2008-07-15->2009-03-04'), ((2014, 7, 1), (2015, 3, 13), 'oil/EM run 2014-07-01->2015-03-13'), ((2020, 3, 9), (2020, 3, 20), 'COVID 2020-03-09->03-20'), ((1980, 7, 1), (1985, 2, 25), 'Volcker 1980-07->1985-02-25'), ((1998, 8, 17), (1998, 10, 8), 'Russia/LTCM 1998-08-17->1998-10-08 (dollar FELL)')]:
    A = px[on_or_before(dt.date(*a))][0]; B = px[on_or_before(dt.date(*b))][0]; print(f"{lab}: {A:.2f} -> {B:.2f} = {100*(B/A-1):+.1f}%")
