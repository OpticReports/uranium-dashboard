import csv, sys, os, numpy as np
RAW = sys.argv[1]
rows = list(csv.reader(open(os.path.join(RAW, "49_Industry_Portfolios.csv"))))
hi = next(i for i, r in enumerate(rows) if r and "Average Value Weighted Returns -- Monthly" in r[0])
names = [h.strip() for h in rows[hi + 1][1:]]; data = {}
for r in rows[hi + 2:]:
    if not r or len(r[0].strip()) != 6 or not r[0].strip().isdigit(): break
    data[r[0].strip()] = [float(x) for x in r[1:]]
months = sorted(data); R = np.array([data[m] for m in months]) / 100; R[R <= -0.99] = np.nan
frows = list(csv.reader(open(os.path.join(RAW, "F-F_Research_Data_Factors.csv"))))
fi = next(i for i, r in enumerate(frows) if r and r[0].strip() == "" and "Mkt-RF" in r[1])
mkt = {}
for r in frows[fi + 1:]:
    if not r or len(r[0].strip()) != 6 or not r[0].strip().isdigit(): break
    mkt[r[0].strip()] = (float(r[1]) + float(r[4])) / 100
idx = {m: i for i, m in enumerate(months)}
def path(ind, m0, m1):
    j = names.index(ind); s, e = idx[m0], idx[m1]; p = np.cumprod(1 + np.nan_to_num(R[s + 1:e + 1, j])); return np.concatenate([[1.0], p])
def mpath(m0, m1):
    s, e = idx[m0], idx[m1]; p = np.cumprod([1 + mkt[months[k]] for k in range(s + 1, e + 1)]); return np.concatenate([[1.0], p])
# (sector, equity peak, capex peak month, trough)  capex peaks per finder A: Telcm real comm-eq Q4-2000; Oil rig count Dec-1981; Util construction 1929 / electric 1930 (use 1929-12 and 1930-06); Oil 2014 FY2014 -> 2014-12
cases = [("Telcm", "200003", "200012", "200209"), ("Chips", "200003", "200012", "200209"), ("Oil", "198011", "198112", "198207"), ("Util", "192909", "192912", "193205"), ("Util", "192909", "193006", "193205"), ("ElcEq", "192908", "193006", "193205"), ("Oil", "201406", "201412", "201602")]
print("share of sector peak-to-trough LOSS that occurred AFTER the capex peak; and same for market")
for ind, pk, cp, tr in cases:
    p = path(ind, pk, tr); c = p[idx[cp] - idx[pk]]; t = p[-1]
    m = mpath(pk, tr); mc = m[idx[cp] - idx[pk]]; mt = m[-1]
    print(f"{ind:6s} eq peak {pk} capex peak {cp} trough {tr}: sector at capex peak {c:.2f}, at trough {t:.2f} -> {(c - t) / (1 - t):.0%} of the loss after capex peak; remaining drawdown from capex-peak level {1 - t / c:.0%} | market at capex peak {mc:.2f}, trough {mt:.2f} -> {(mc - mt) / (1 - mt) if mt < 1 else float('nan'):.0%} of mkt loss after")
