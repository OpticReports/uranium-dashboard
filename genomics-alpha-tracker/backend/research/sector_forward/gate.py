"""The gate (DESIGN_SECTOR_FORWARD_TEST.md, "The gate (frozen now)"), source 1.

Run ONLY after the two-reviewer spot-check has passed. Exposure on day P: a
press-release catalyst window (press_catalysts.json.gz) overlapping
[P-7d, P+30d], from a release published at or before 16:00 New York on P and
no more than 365 days before P. Universe: genomics-labelled, non-core, listed,
$300M <= cap < $10B. Events de-clustered, M&A excluded. K = 10.

Pass iff (1) Mantel-Haenszel OR lower 90% bound > 1.0; (2) H1' beats B1x at
K=10 with exact sign-test power >= 80% within 12 months on half the in-sample
paired edge (discordance held fixed); (3) H1' no worse than B1x at K=25 and 40.

    cd genomics-alpha-tracker/backend && python -m research.sector_forward.gate
"""
from __future__ import annotations

import bisect
import gzip
import json
import math
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from research.sector_forward import calibrate as K1  # noqa: E402
from research.sector_forward import calibrate2 as C2  # noqa: E402
from research.sector_tier import build_population as P  # noqa: E402
from research.sector_tier import measure as M  # noqa: E402

OUT = HERE / "gate_source1.json"
K_PRIMARY = 10
KS = (10, 25, 40)
SEED = 20261006
STALE_DAYS = 365


def main() -> None:
    labels = json.loads((K1.ST / "labels.json").read_text())
    aliases = json.loads((HERE / "aliases.json").read_text())
    cats = json.loads(gzip.decompress((HERE / "press_catalysts.json.gz").read_bytes()))["records"]
    by_sym = defaultdict(list)
    for c in cats:
        pub = datetime.fromisoformat(c["published"][:19])
        by_sym[c["symbol"]].append((pub, date.fromisoformat(c["start"]), date.fromisoformat(c["end"])))

    def exposed(s: str, p: date) -> bool:
        cutoff = datetime.combine(p, datetime.min.time()).replace(hour=16)   # 16:00 New York on P
        lo, hi = p - timedelta(days=7), p + timedelta(days=30)
        return any(pub <= cutoff and (p - pub.date()).days <= STALE_DAYS and a <= hi and b >= lo
                   for pub, a, b in by_sym.get(s, []))

    pop = {x["symbol"]: x for x in json.loads(P.OUT_POP.read_text())}
    series = {s: M.Series(s) for s in aliases}
    core = M.Core({})
    review = json.loads((K1.ST / "ma_review.json").read_text())
    moves = [m for m in json.loads(P.OUT_MOVES.read_text()) if not m.get("flag_artifact")]
    for m in moves:
        r = review.get(f"{m['symbol']}|{m['date']}")
        if r and r.get("ma") is not None:
            m["flag_ma"] = bool(r["ma"])
    gm = [m for m in moves if not m["flag_ma"] and (labels.get(m["symbol"]) or {}).get("genomics") and m["symbol"] in aliases]

    follow, quiet = set(), defaultdict(list)
    for s in {m["symbol"] for m in gm}:
        bd, last = series[s].bdates, None
        for m in sorted((m for m in gm if m["symbol"] == s), key=lambda m: m["date"]):
            i = bisect.bisect_left(bd, M.d(m["date"]))
            if last is not None and i - last <= C2.DECLUSTER:
                follow.add((s, m["prior_date"]))
                continue
            last = i
            quiet[s].append((bd[min(i + 1, len(bd) - 1)], bd[min(len(bd) - 1, i + C2.DECLUSTER)]))
    ev = {(m["symbol"], m["prior_date"]) for m in gm}

    def listed(s, t):
        fb = series[s].first_bar()
        dd = M.d(pop[s].get("delisted_date"))
        return fb is not None and fb <= t and (dd is None or t < dd)

    ref = max(series.values(), key=lambda x: len(x.bdates)).bdates
    days = [ref[i] for i in range(len(ref) - 1) if M.WIN0 <= ref[i + 1] <= M.WIN1]
    rows = []
    for p in days:
        cs = core.symbols(p)
        for s in aliases:
            if s in cs or not listed(s, p):
                continue
            cap = series[s].cap(p) or 0
            if not (M.CAP_MIN <= cap < C2.BIG):
                continue
            ser = series[s]
            j = bisect.bisect_right(ser.bdates, p)
            nxt = ser.bdates[j] if j < len(ser.bdates) else None
            is_ev = (s, p.isoformat()) in ev
            fol = (s, p.isoformat()) in follow
            q = (not is_ev) and nxt is not None and any(lo <= nxt <= hi for lo, hi in quiet.get(s, []))
            rows.append({"p": p, "s": s, "vol": K1.vol60(ser, p), "volx": C2.vol60x(ser, p), "cap": cap,
                         "ro": exposed(s, p), "ev": is_ev and not fol, "drop": fol or q})
    panel = [r for r in rows if not r["drop"]]
    n_ev = sum(r["ev"] for r in panel)

    # (1) Mantel-Haenszel with name bootstrap
    vols, caps = sorted(r["vol"] for r in panel), sorted(r["cap"] for r in panel)
    vq = [vols[int(len(vols) * k / 5)] for k in range(1, 5)]
    ct = [caps[int(len(caps) * k / 3)] for k in range(1, 3)]

    def table(rs):
        t = defaultdict(lambda: [0, 0, 0, 0])
        for r in rs:
            t[(bisect.bisect_right(vq, r["vol"]), bisect.bisect_right(ct, r["cap"]))][(0 if r["ro"] else 2) + (0 if r["ev"] else 1)] += 1
        return t
    est = C2.mh_or(table(panel))
    by_name = defaultdict(list)
    for r in panel:
        by_name[r["s"]].append(r)
    names = sorted(by_name)
    rng = random.Random(SEED)
    boots = []
    for _ in range(C2.BOOT):
        o = C2.mh_or(table([r for s in (rng.choice(names) for _ in names) for r in by_name[s]]))
        if o is not None and math.isfinite(o):
            boots.append(o)
    boots.sort()
    ci = [boots[int(0.05 * len(boots))], boots[int(0.95 * len(boots)) - 1]] if boots else [None, None]

    # (2)/(3) H1' vs B1x, paired, per K
    by_day = defaultdict(list)
    for r in panel:
        by_day[r["p"]].append(r)
    hits = {k: defaultdict(int) for k in KS}
    pair = {k: [0, 0, 0] for k in KS}
    rnd = {k: 0.0 for k in KS}
    n = 0
    for p, u in by_day.items():
        evs = [r for r in u if r["ev"]]
        if not evs:
            continue
        dv = {r["s"]: series[r["s"]].dollar_vol_20(p) for r in u}
        h1 = sorted(u, key=lambda r: (not r["ro"], -r["volx"], -dv[r["s"]]))
        bx = sorted(u, key=lambda r: (-r["volx"], -dv[r["s"]]))
        rh, rb = {r["s"]: i + 1 for i, r in enumerate(h1)}, {r["s"]: i + 1 for i, r in enumerate(bx)}
        for e in evs:
            n += 1
            for k in KS:
                a, b = rh[e["s"]] <= k, rb[e["s"]] <= k
                hits[k]["H1p"] += a
                hits[k]["B1x"] += b
                rnd[k] += min(1.0, k / len(u))
                pair[k][0] += a and not b
                pair[k][1] += b and not a
                pair[k][2] += a and b
    per_k = {}
    for k in KS:
        b, c, both = pair[k]
        blk = {"H1p": round(hits[k]["H1p"] / n, 3), "B1x": round(hits[k]["B1x"] / n, 3), "random": round(rnd[k] / n, 3),
               "H1p_only_vs_B1x_only_both": pair[k], "sign_p": round(C2.sign_p(b, c), 4)}
        if b > c:
            hb, hc = C2.half_edge(b / n, c / n)
            blk["months_to_80pct_power_half_edge"] = C2.months_to_power(hb, hc, n / 12, cap_months=12)
            blk["power_12mo_half_edge"] = round(C2.power(hb, hc, round(n)), 3)
        per_k[str(k)] = blk
    c1 = ci[0] is not None and ci[0] > 1.0
    kp = per_k[str(K_PRIMARY)]
    c2 = kp.get("months_to_80pct_power_half_edge") is not None
    c3 = all(per_k[str(k)]["H1p"] >= per_k[str(k)]["B1x"] for k in KS if k != K_PRIMARY)
    res = {"source": "FMP press releases (headline + snippet)", "catalyst_records": len(cats),
           "names_with_catalysts": len(by_sym), "panel_name_days": len(panel), "events": n_ev,
           "exposed_name_days": sum(r["ro"] for r in panel), "events_exposed": sum(r["ro"] and r["ev"] for r in panel),
           "mh_odds_ratio": round(est, 3) if est else None, "mh_ci90": [round(x, 3) for x in ci] if ci[0] else ci,
           "per_k": per_k, "conditions": {"1_or_lower_bound_above_1": c1, "2_power_80pct_within_12mo_at_K10": c2,
                                          "3_no_worse_at_25_40": c3},
           "gate": "PASS" if (c1 and c2 and c3) else "FAIL"}
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
