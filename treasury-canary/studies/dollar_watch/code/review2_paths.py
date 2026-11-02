import csv, numpy as np
D='<scratch>/dxy/'
spx={r['date']:float(r['close']) for r in csv.DictReader(open(D+'finderA/data/spx_daily.csv'))}
gold={r['date']:float(r['close']) for r in csv.DictReader(open(D+'finderA/data/gold_daily.csv')) if r['close']}
dxy={r['date']:float(r['close']) for r in csv.DictReader(open(D+'finderA/data/dxy_daily.csv')) if r['close']}
def at(s,d):
    ks=sorted(k for k in s if k<=d); return s[ks[-1]], ks[-1]
def path(label,d0,d1):
    a,_=at(spx,d0); b,_=at(spx,d1); g0,_=at(gold,d0); g1,_=at(gold,d1); x0,_=at(dxy,d0); x1,_=at(dxy,d1)
    # min S&P between
    mn=min((v,k) for k,v in spx.items() if d0<=k<=d1)
    gm=min((v,k) for k,v in gold.items() if d0<=k<=d1) if any(d0<=k<=d1 for k in gold) else (None,None)
    print(f"{label}: {d0}->{d1} S&P {a:.0f}->{b:.0f} ({100*(b/a-1):+.1f}%), S&P min {mn[0]:.0f} on {mn[1]} ({100*(mn[0]/a-1):+.1f}%); gold {g0:.0f}->{g1:.0f} ({100*(g1/g0-1):+.1f}%) min {gm[0]:.0f} {gm[1]}; DXY {x0:.1f}->{x1:.1f} ({100*(x1/x0-1):+.1f}%)")
path("2008 first-wave fire",      "2008-09-22","2009-03-09")
path("2008 rearm fire",           "2008-11-06","2009-03-09")
path("2008 funding-normalised",   "2008-10-17","2009-03-09")
path("2008 gold trough",          "2008-11-12","2009-03-09")
path("2008 gold trough->+120d",   "2008-11-12","2009-05-01")
path("2022 July fire",            "2022-07-28","2022-10-12")
path("2022 gold/dxy peak",        "2022-09-26","2023-03-31")
path("2020 fire",                 "2020-04-09","2020-07-09")
path("2018 gold trough",          "2018-08-16","2018-12-24")
path("2015 gold trough",          "2015-12-17","2016-02-11")
path("2026 gold YTD",             "2026-01-29","2026-11-02")
# gold vs dxy in 2026: dxy move
