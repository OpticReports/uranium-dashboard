"""Empirical check of each leveraged ETF against candidate 1x versions, 2025-12-01..2026-10-15:
r_lev ~ a + b * r_1x ; implied = L*r_1x - (L-1)*rf (long) ; corr, slope, annualised drag."""
import json, math
LEV = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/lev'
def px(t):
    o = json.load(open(f"{LEV}/yh/{t.replace('^', '_')}.json")); return dict(zip(o['dates'], o['adjclose' if t != '^IRX' else 'close']))
def rets(t):
    p = px(t); ds = sorted(p); return {ds[i]: p[ds[i]]/p[ds[i-1]]-1 for i in range(1, len(ds))}
irx = px('^IRX'); days = sorted(px('SPY')); rf = {days[i]: irx[days[i-1]]/100/252 for i in range(1, len(days))}
W = [d for d in days if '2025-12-01' <= d <= '2026-10-15' and d in rf]
def fit(lev, base, L, inv_synth=False):
    a = rets(lev); b = rets(base)
    ds = [d for d in W if d in a and d in b]
    y = [a[d] for d in ds]; x = [b[d] for d in ds]
    n = len(ds); mx = sum(x)/n; my = sum(y)/n
    sxy = sum((xi-mx)*(yi-my) for xi, yi in zip(x, y)); sxx = sum((xi-mx)**2 for xi in x); syy = sum((yi-my)**2 for yi in y)
    slope = sxy/sxx; corr = sxy/math.sqrt(sxx*syy)
    imp = [L*xi - (L-1)*rf[d] for xi, d in zip(x, ds)]
    drag = (sum(yi-ii for yi, ii in zip(y, imp))/n)*252
    te = math.sqrt(sum((yi-ii-(drag/252))**2 for yi, ii in zip(y, imp))/(n-1))*math.sqrt(252)
    return n, corr, slope, drag, te
C = [('TQQQ', 'QQQ', 3), ('QLD', 'QQQ', 2), ('UPRO', 'SPY', 3), ('SPXL', 'SPY', 3), ('SSO', 'SPY', 2), ('UDOW', 'DIA', 3), ('TNA', 'IWM', 3),
     ('TECL', 'XLK', 3), ('SOXL', 'SOXX', 3), ('SOXL', 'SMH', 3), ('USD', 'SOXX', 2), ('USD', 'SMH', 2), ('LABU', 'XBI', 3), ('UGE', 'XLP', 2),
     ('UGL', 'GLD', 2), ('TMF', 'TLT', 3), ('UVXY', 'VIXY', 1.5),
     ('SQQQ', 'QQQ', -3), ('SQQQ', 'PSQ', 3), ('PSQ', 'QQQ', -1), ('SH', 'SPY', -1), ('TBF', 'TLT', -1), ('TMV', 'TLT', -3), ('TMV', 'TBF', 3),
     ('LABD', 'XBI', -3), ('SOXS', 'SOXX', -3), ('SOXS', 'SMH', -3), ('SVIX', 'VIXY', -1), ('SVXY', 'VIXY', -0.5), ('ZVOL', 'VXZ', -1), ('VIXM', 'VXZ', 1)]
print(f"{'lev':5s} {'1x':5s} {'L':>5s} {'n':>4s} {'corr':>7s} {'slope':>6s} {'drag/yr':>8s} {'TE/yr':>6s}")
for lev, base, L in C:
    n, c, s, dr, te = fit(lev, base, L)
    print(f"{lev:5s} {base:5s} {L:5.1f} {n:4d} {c:7.4f} {s:6.2f} {dr:+8.2%} {te:6.2%}")
