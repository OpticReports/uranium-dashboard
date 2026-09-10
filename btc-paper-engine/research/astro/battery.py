"""Run the pre-registered battery. Every test: binary indicator -> next-day
log return. Welch t + stationary block bootstrap. BH-FDR over families A-F.
Families G (known-real controls) and H (known-false nulls) calibrate."""
import csv, json, math, itertools
import numpy as np
from scipy import stats

rng = np.random.default_rng(20260904)
feat = json.load(open("features.json"))
rows = list(csv.DictReader(open("../btc_daily_full.csv")))
close = np.array([float(r["close"]) for r in rows])
ts = np.array([int(r["ts"]) for r in rows])
assert len(feat) == len(rows)

# NEXT-day log return: signal on day i predicts return from close[i] to close[i+1]
ret = np.full(len(close), np.nan)
ret[:-1] = np.diff(np.log(close))
valid = ~np.isnan(ret)

ZODIAC = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio",
          "Sagittarius","Capricorn","Aquarius","Pisces"]
PLANETS = ["sun","moon","mercury","venus","mars","jupiter","saturn"]
ASPECTS = {"conj":0,"sextile":60,"square":90,"trine":120,"opp":180}
ORB = 6.0

tests = {}   # name -> (family, boolean mask)
def add(fam, name, mask):
    m = np.asarray(mask, dtype=bool) & valid
    if 20 <= m.sum() <= valid.sum() - 20:      # need both arms populated
        tests[name] = (fam, m)

F = {k: np.array([f[k] for f in feat]) for k in feat[0]}

# --- A: lunar --------------------------------------------------------------
for k in ("full_moon_day","new_moon_day","full_moon_w1","new_moon_w1",
          "full_moon_w3","new_moon_w3","perigee_w1","apogee_w1",
          "decl_max_w1","decl_min_w1"):
    add("A_lunar", f"A:{k}", F[k] == 1)
add("A_lunar", "A:waxing", F["waxing"] == 1)
add("A_lunar", "A:waning", F["waxing"] == 0)
pa = F["moon_phase_deg"]
for o in range(8):
    add("A_lunar", f"A:phase_octile_{o}", (pa >= o*45) & (pa < (o+1)*45))
add("A_lunar", "A:illum_high", F["moon_illum"] > 0.75)
add("A_lunar", "A:illum_low", F["moon_illum"] < 0.25)

# --- B/C: retrogrades ------------------------------------------------------
for p in ("mercury","venus","mars","jupiter","saturn"):
    r = F[f"retro_{p}"] == 1
    add("B_retro" if p == "mercury" else "C_retro", f"{'B' if p=='mercury' else 'C'}:{p}_retro", r)
    if p == "mercury":
        ri = np.where(r)[0]
        starts = np.zeros(len(r), bool); ends = np.zeros(len(r), bool)
        stat = np.zeros(len(r), bool)
        for i in range(1, len(r)):
            if r[i] and not r[i-1]:
                starts[i:i+3] = True; stat[max(0,i-1):i+2] = True
            if not r[i] and r[i-1]:
                ends[max(0,i-3):i] = True; stat[max(0,i-1):i+2] = True
        add("B_retro","B:mercury_retro_first3",starts)
        add("B_retro","B:mercury_retro_last3",ends)
        add("B_retro","B:mercury_station_w1",stat)
        # shadow periods: 3 weeks before/after
        pre=np.zeros(len(r),bool); post=np.zeros(len(r),bool)
        for i in range(1,len(r)):
            if r[i] and not r[i-1]: pre[max(0,i-21):i]=True
            if not r[i] and r[i-1]: post[i:i+21]=True
        add("B_retro","B:mercury_preshadow",pre)
        add("B_retro","B:mercury_postshadow",post)
        # inferior conjunction (cazimi): retro AND within orb of sun
        sep=np.abs(((F["lon_mercury"]-F["lon_sun"]+180)%360)-180)
        add("B_retro","B:mercury_cazimi",(sep<3)&r)

# --- D: aspects ------------------------------------------------------------
for a, b in itertools.combinations(PLANETS, 2):
    sep = np.abs(((F[f"lon_{a}"] - F[f"lon_{b}"] + 180) % 360) - 180)
    for an, ad in ASPECTS.items():
        add("D_aspect", f"D:{a}_{b}_{an}", np.abs(sep - ad) <= ORB)

# --- E: eclipses (syzygy near lunar nodes -> proxy: |moon decl| small at syzygy)
syz_f = F["full_moon_w1"] == 1; syz_n = F["new_moon_w1"] == 1
near_node = np.abs(F["moon_decl_deg"]) < 1.5
add("E_eclipse", "E:lunar_eclipse_w1", syz_f & near_node)
add("E_eclipse", "E:solar_eclipse_w1", syz_n & near_node)

# --- F: zodiac -------------------------------------------------------------
for i, z in enumerate(ZODIAC):
    add("F_zodiac", f"F:sun_in_{z}", (F["lon_sun"] // 30).astype(int) == i)
    add("F_zodiac", f"F:moon_in_{z}", (F["lon_moon"] // 30).astype(int) == i)

# --- G: known-real calendar controls --------------------------------------
import datetime
dts = [datetime.datetime.utcfromtimestamp(int(t)) for t in ts]
dow = np.array([d.weekday() for d in dts]); mon = np.array([d.month for d in dts])
for i, n in enumerate(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]):
    add("G_control", f"G:dow_{n}", dow == i)
for i in range(1, 13):
    add("G_control", f"G:month_{i:02d}", mon == i)

# --- H: synthetic nulls (known-false) -------------------------------------
for j in range(30):
    period = rng.uniform(7, 400); phase = rng.uniform(0, 2*np.pi)
    wave = np.sin(2*np.pi*np.arange(len(ret))/period + phase)
    add("H_null", f"H:synth_{j:02d}", wave > 0.5)

print(f"{len(tests)} tests registered")
fam_counts = {}
for n,(f,_) in tests.items(): fam_counts[f]=fam_counts.get(f,0)+1
print(json.dumps(fam_counts, indent=1))

# --- statistics ------------------------------------------------------------
r = ret[valid]
NREP, BLOCK = 4000, 20
_n = len(r); _nb = int(np.ceil(_n/BLOCK))
print(f"building {NREP}x{_n} block-bootstrap matrix (block={BLOCK}d)...")
_starts = rng.integers(0, _n, (NREP, _nb))
_idx = (_starts[:,:,None] + np.arange(BLOCK)[None,None,:]).reshape(NREP,-1)[:,:_n] % _n
RS = r[_idx]                      # NREP x n resampled return paths
print("  matrix built:", RS.shape)

def block_boot_p(mask, r):
    """Stationary block bootstrap: resample contiguous blocks of the RETURN
    series (preserving volatility clustering) while holding the calendar mask
    fixed. Null = the labels carry no information."""
    obs = r[mask].mean() - r[~mask].mean()
    non = mask.sum(); noff = (~mask).sum()
    d = (RS @ mask) / non - (RS @ (~mask)) / noff
    return obs, (np.sum(np.abs(d) >= abs(obs)) + 1) / (NREP + 1)
res = []
for name,(fam,m) in tests.items():
    mm = m[valid]
    a, b = r[mm], r[~mm]
    t, p = stats.ttest_ind(a, b, equal_var=False)
    obs, pb = block_boot_p(mm.astype(float) if False else mm, r)
    res.append({"test":name,"family":fam,"n_on":int(mm.sum()),
                "mean_on_bps":float(a.mean()*1e4),"mean_off_bps":float(b.mean()*1e4),
                "edge_bps":float(obs*1e4),"t":float(t),"p_welch":float(p),
                "p_boot":float(pb)})
json.dump(res, open("battery_results.json","w"), indent=1)
print("done ->", len(res), "results")
