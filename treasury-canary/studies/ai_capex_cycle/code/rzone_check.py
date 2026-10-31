import csv, sys
R=sys.argv[1]
def rd(f):
    out={}
    for r in csv.DictReader(open(f)):
        k=[c for c in r if c!="observation_date"][0]
        if r[k] not in (".",""): out[r["observation_date"]]=float(r[k])
    return out
gdp=rd(R+"/fred_GDP.csv"); tb=rd(R+"/fred_TBSDODNS.csv"); bis=rd(R+"/fred_QUSNAM770A.csv"); bc=rd(R+"/fred_BCNSDODNS.csv")
def d3(series, dates, scale):
    for d in dates:
        y=str(int(d[:4])-3)+d[4:]
        cur=series[d]*scale/gdp[d]*100 if scale else series[d]; prev=series[y]*scale/gdp[y]*100 if scale else series[y]
        print(f"   {d}: ratio {cur:6.2f}  3y-ago {prev:6.2f}  change {cur-prev:+.2f} pp")
dates=["2000-01-01","2008-10-01","2026-04-01"]
print("TBSDODNS (Z.1 total nonfinancial business debt sec+loans, $mn) / GDP ($bn SAAR):"); d3(tb,dates,1/1000)
print("BCNSDODNS (nonfinancial CORPORATE) / GDP:"); d3(bc,dates,1/1000)
print("QUSNAM770A (BIS credit to NFCs, % of GDP per FRED units? check):")
print("   last obs", sorted(bis)[-1], bis[sorted(bis)[-1]], " 2000Q1", bis.get("2000-01-01"), " sample 2008-10-01", bis.get("2008-10-01"))
# BIS series on FRED QUSNAM770A: units Billions of USD per page title -> compute %GDP
print("QUSNAM770A as level ($bn) / GDP:"); d3(bis,[d for d in dates if d in bis],1.0)
print("latest TBSDODNS", sorted(tb)[-1], "latest GDP", sorted(gdp)[-1], "latest BIS", sorted(bis)[-1])
# whole-history max of 3y change for TBSDODNS/GDP and count of quarters > 8.99
r={d: tb[d]/1000/gdp[d]*100 for d in tb if d in gdp}
ch=[(d, r[d]-r[str(int(d[:4])-3)+d[4:]]) for d in sorted(r) if str(int(d[:4])-3)+d[4:] in r]
print("max 3y change", max(ch,key=lambda x:x[1]), "quarters>8.99:", [d for d,v in ch if v>8.99])
