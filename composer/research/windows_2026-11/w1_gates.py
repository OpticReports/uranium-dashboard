"""Gates G1-G4 of PREREG.md. G1: the live trees in this simulator against Composer's stored backtests.
G2: three variants per engine backtested on Composer itself (read-only ad-hoc backtest, nothing saved).
G3: a tree form and a flag form of the same variant agree. G4: stale closes. Writes out/gates.json."""
import copy
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "zvol_2026-11"))
import wsim as w  # noqa: E402
import lib  # noqa: E402

ks = w.ks
API = os.path.join(HERE, "..", "..", "scripts", "composer-api.py")
SCR = w.CACHE + "/g2"
BT_END = "2026-11-17"
os.makedirs(SCR, exist_ok=True)


def compare(sim, bt):
    days = [d for d in sim["days"] if d in bt["ret"]]
    mine, theirs = [sim["ret"][sim["days"].index(d)] for d in days], [bt["ret"][d] for d in days]
    ok = tot = 0
    worst = []
    for d in days[:-1]:
        h = sim["held"].get(d)
        if h is None:
            continue
        wt = {t: bt["w"][t].get(d, 0.0) for t in bt["w"]}
        gap = 0.5 * sum(abs(h.get(t, 0) - wt.get(t, 0)) for t in set(h) | set(wt))
        tot += 1
        ok += gap <= 0.015
        if gap > 0.015 and len(worst) < 6:
            worst.append([d, {t: round(v, 3) for t, v in h.items()}, {t: round(v, 3) for t, v in wt.items() if v > 1e-6}])
    c = ks.corr(mine, theirs)
    return {"sessions": len(days), "corr": c, "holdings_same": [ok, tot], "share": ok / tot, "sim": ks.stats(mine), "composer": ks.stats(theirs),
            "pass": bool(ok / tot >= 0.98 and c >= 0.999), "first_differences": worst}


def composer_bt(name, tree, start):
    f, o = f"{SCR}/{name}.tree.json", f"{SCR}/{name}.bt.json"
    json.dump(tree, open(f, "w"))
    if not os.path.exists(o) or "--force" in sys.argv:
        r = subprocess.run([sys.executable, API, "backtest-def", "-f", f, "--start", start, "--end", BT_END, "-o", o], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(o):
            return None, (r.stdout + r.stderr)[-300:]
    try:
        return lib.load_bt(o), None
    except Exception as e:  # noqa: BLE001
        return None, f"unreadable backtest: {e!r}"[:300]


out = {"G1": {}, "G2": {}, "G3": {}, "G4": {}}
PL = w.long_panel()
for eng, cells_of in (("HG", w.hg_cells), ("SLEEVE", w.sleeve_cells)):
    base, cells = cells_of(PL)
    PR = w.real_panel(eng)
    a0, a1 = w.SPAN[eng]["A"]
    # G1
    bt = lib.load_bt(os.path.join(HERE, "..", "zvol_2026-11", "data", f"bt_{eng}.json"))
    out["G1"][eng] = compare(w.simulate(base, PR, a0, a1), bt)
    print("G1", eng, {k: v for k, v in out["G1"][eng].items() if k != "first_differences"})
    # G2
    if eng == "HG":
        ema = copy.deepcopy(base)
        for g in w.HG(ema).gate:
            g["rhs-fn"] = "exponential-moving-average-price"
            ks.set_window(g, "rhs", 100)
        send = {"HA.sma10x50": cells["HA.sma10x50"][2], "HD.ema100": ema, "HF.picks14": cells["HF.picks14"][2]}
    else:
        send = {c: cells[c][2] for c in ("SA.ief14", "SD.hold30", "SGp.rank3")}
    for c, tree in send.items():
        bt, err = composer_bt(c, tree, a0)
        if bt is None:
            out["G2"][c] = {"not_run": err}
            print("G2", c, "NOT RUN:", err[-160:])
            continue
        out["G2"][c] = compare(w.simulate(cells[c][2], PR, a0, a1, cells[c][3]), bt)
        print("G2", c, {k: v for k, v in out["G2"][c].items() if k != "first_differences"})
    # G3
    if eng == "HG":
        for c, mk in (("HA.sma10x50", w.cross_flag("TQQQ", 10, 50, "sma")), ("HB.sma50", w.price_flag("TQQQ", 50, "sma", True)), ("HD.sma100", w.price_flag("SPY", 100, "sma", False))):
            t = copy.deepcopy(base)
            h = w.HG(t)
            for node in ([h.trend] if c.startswith("HA") else [h.cash] if c.startswith("HB") else h.gate):
                w.to_flag(node, 0)
            res = []
            for P, (lo, hi) in ((PR, (a0, a1)), (PL, (w.SPAN[eng]["M"][0], w.SPAN[eng]["R"][1]))):
                x, y = w.simulate(cells[c][2], P, lo, hi), w.simulate(t, P, lo, hi, [mk])
                res.append([sum(set(x["target"][d]) == set(y["target"][d]) for d in x["target"]), len(x["target"]), max(abs(p - q) for p, q in zip(x["ret"], y["ret"]))])
            out["G3"][c] = {"real": res[0], "long": res[1], "pass": all(r[0] == r[1] and r[2] < 1e-12 for r in res)}
            print("G3", c, out["G3"][c])
    # G4
    stale = {}
    for t, s in PR.items():
        ds = [d for d in sorted(s) if a0 <= d <= a1]
        run = best = 0
        where = None
        for p, q in zip(ds, ds[1:]):
            run = run + 1 if s[p] == s[q] else 0
            if run > best:
                best, where = run, q
        if best > 5:
            stale[t] = [best, where]
    out["G4"][eng] = {"more_than_5_unchanged_closes": stale, "pass": not stale}
    print("G4", eng, out["G4"][eng])
json.dump(out, open(os.path.join(HERE, "out", "gates.json"), "w"), indent=1)
