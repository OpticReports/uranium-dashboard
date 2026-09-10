"""Compute astrological state for each BTC daily bar (00:00 UTC).

LOOKAHEAD DISCIPLINE: every feature is evaluated at the bar's OPEN timestamp
and is used to predict that bar's close-to-next-close return. Ephemeris is
deterministic and known years ahead, so there is no information leakage by
construction - but the return alignment still has to be right.
"""
import csv, json, math
import ephem
import numpy as np

BODIES = {"sun": ephem.Sun, "moon": ephem.Moon, "mercury": ephem.Mercury,
          "venus": ephem.Venus, "mars": ephem.Mars, "jupiter": ephem.Jupiter,
          "saturn": ephem.Saturn, "uranus": ephem.Uranus,
          "neptune": ephem.Neptune, "pluto": ephem.Pluto}

rows = list(csv.DictReader(open("../btc_daily_full.csv")))
ts = np.array([int(r["ts"]) for r in rows])
close = np.array([float(r["close"]) for r in rows])

feat = []
prev_lon = {}
for i, t in enumerate(ts):
    d = ephem.Date(ephem.Date(0) + (t / 86400.0) - (ephem.Date(0) - ephem.Date("1970/1/1")))
    d = ephem.Date("1970/1/1") + t / 86400.0
    rec = {"ts": int(t)}
    lons = {}
    for name, cls in BODIES.items():
        b = cls()
        b.compute(d)
        lon = math.degrees(ephem.Ecliptic(b).lon) % 360.0
        lons[name] = lon
        rec[f"lon_{name}"] = lon
        # geocentric apparent motion -> retrograde detection (deg/day)
        b2 = cls(); b2.compute(ephem.Date(d + 1.0))
        lon2 = math.degrees(ephem.Ecliptic(b2).lon) % 360.0
        dl = ((lon2 - lon + 180.0) % 360.0) - 180.0
        rec[f"retro_{name}"] = 1 if dl < 0 else 0
        rec[f"speed_{name}"] = dl
    # lunar phase angle: 0 = new, 180 = full
    pa = (lons["moon"] - lons["sun"]) % 360.0
    rec["moon_phase_deg"] = pa
    rec["moon_illum"] = (1 - math.cos(math.radians(pa))) / 2.0
    rec["waxing"] = 1 if pa < 180 else 0
    m = ephem.Moon(); m.compute(d)
    rec["moon_dist_km"] = m.earth_distance * ephem.meters_per_au / 1000.0
    rec["moon_decl_deg"] = math.degrees(m.dec)
    feat.append(rec)

# --- derived event windows -------------------------------------------------
pa = np.array([f["moon_phase_deg"] for f in feat])
def _cross(target):
    """days where the phase angle crosses `target` (event day = the bar whose
    interval contains the exact syzygy)."""
    rel = (pa - target + 180) % 360 - 180
    out = np.zeros(len(pa), dtype=int)
    for i in range(1, len(pa)):
        if rel[i-1] < 0 <= rel[i] or (rel[i-1] < 0 and rel[i] > 0 and abs(rel[i]-rel[i-1]) < 90):
            out[i] = 1
    return out
full_d = _cross(180.0); new_d = _cross(0.0)
def _win(ev, k):
    o = np.zeros(len(ev), dtype=int)
    idx = np.where(ev == 1)[0]
    for j in idx:
        o[max(0, j-k):min(len(ev), j+k+1)] = 1
    return o
dist = np.array([f["moon_dist_km"] for f in feat])
decl = np.array([f["moon_decl_deg"] for f in feat])
def _local_extreme(arr, mode, k=3):
    o = np.zeros(len(arr), dtype=int)
    for i in range(k, len(arr)-k):
        w = arr[i-k:i+k+1]
        if (mode == "min" and arr[i] == w.min()) or (mode == "max" and arr[i] == w.max()):
            o[i] = 1
    return o
for i, f in enumerate(feat):
    f["full_moon_day"] = int(full_d[i]); f["new_moon_day"] = int(new_d[i])
    for k in (1, 3):
        f[f"full_moon_w{k}"] = int(_win(full_d, k)[i])
        f[f"new_moon_w{k}"] = int(_win(new_d, k)[i])
    f["perigee_w1"] = int(_win(_local_extreme(dist, "min"), 1)[i])
    f["apogee_w1"] = int(_win(_local_extreme(dist, "max"), 1)[i])
    f["decl_max_w1"] = int(_win(_local_extreme(decl, "max"), 1)[i])
    f["decl_min_w1"] = int(_win(_local_extreme(decl, "min"), 1)[i])

json.dump(feat, open("features.json", "w"))
print(f"{len(feat)} days of ephemeris")
print("full moons:", int(full_d.sum()), "| new moons:", int(new_d.sum()))
print("mercury retro days:", sum(f["retro_mercury"] for f in feat),
      f"({100*sum(f['retro_mercury'] for f in feat)/len(feat):.1f}%)")
for p in ("venus","mars","jupiter","saturn"):
    n=sum(f[f"retro_{p}"] for f in feat)
    print(f"  {p} retro: {n} ({100*n/len(feat):.1f}%)")
