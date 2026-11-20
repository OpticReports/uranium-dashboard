"""Gate G4 of PREREG.md: three variants backtested on Composer itself (read-only POST /backtest of an
ad-hoc tree: nothing is saved, no symphony is touched) against this study's simulator. Also the approved
tree, as a control on the request itself. Writes out/g4.json."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "zvol_2026-11"))
import data  # noqa: E402
import ksim as ks  # noqa: E402
import lib  # noqa: E402

API = os.path.join(HERE, "..", "..", "scripts", "composer-api.py")
SCR = data.SCRATCH + "/kmlm/g4"
START, END = "2023-04-19", "2026-11-17"
os.makedirs(SCR, exist_ok=True)
tree = ks.approved()
P = data.panel_ab("2026-11-20")
x = P["XLK"]
sm, em = ks.sma_series(x, 50), ks.ema_series(x, 50)
cases = {
    "approved": (tree, tree, None),
    "rsi14": (ks.v_switch_rsi(tree, 14), ks.v_switch_rsi(tree, 14), None),
    "sma50": (ks.v_switch_form(tree, ("current-price", "XLK", None), ("moving-average-price", "XLK", 50)),
              ks.v_switch_flag(tree), {d: (None if sm[d] is None else x[d] > sm[d]) for d in x}),
    "ema50": (ks.v_switch_form(tree, ("current-price", "XLK", None), ("exponential-moving-average-price", "XLK", 50)),
              ks.v_switch_flag(tree), {d: (None if em[d] is None else x[d] > em[d]) for d in x}),
}
out = {}
for name, (send, simtree, flag) in cases.items():
    f, o = f"{SCR}/{name}.tree.json", f"{SCR}/{name}.bt.json"
    json.dump(send, open(f, "w"))
    if not os.path.exists(o) or "--force" in sys.argv:
        r = subprocess.run([sys.executable, API, "backtest-def", "-f", f, "--start", START, "--end", END, "-o", o],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(o):
            out[name] = {"error": (r.stdout + r.stderr)[-400:]}
            print(name, "COMPOSER REFUSED:", out[name]["error"][-200:])
            continue
    try:
        bt = lib.load_bt(o)
    except Exception as e:  # noqa: BLE001
        out[name] = {"error": f"unreadable backtest: {e!r}"[:300]}
        print(name, out[name]["error"])
        continue
    s = ks.simulate(simtree, P, START, END, flags=[flag] if flag else None)
    days = [d for d in s["days"] if d in bt["ret"]]
    mine, theirs = [s["ret"][s["days"].index(d)] for d in days], [bt["ret"][d] for d in days]
    ok = tot = 0
    for d in days[:-1]:
        h, w = s["held"].get(d), {t: bt["w"][t].get(d, 0.0) for t in bt["w"]}
        if h is None:
            continue
        tot += 1
        ok += 0.5 * sum(abs(h.get(t, 0) - w.get(t, 0)) for t in set(h) | set(w)) <= 0.015
    c = ks.corr(mine, theirs)
    out[name] = {"sessions": len(days), "corr": c, "holdings_same": [ok, tot], "sim": ks.stats(mine), "composer": ks.stats(theirs),
                 "pass": bool(c >= 0.999 and ok >= 0.97 * tot)}
    print(f"{name:9s} {'PASS' if out[name]['pass'] else 'FAIL'}: {len(days)} sessions, corr {c:.5f}, holdings {ok}/{tot}, "
          f"sim {out[name]['sim']['cagr']:+.1%} DD {out[name]['sim']['maxdd']:.1%} vs Composer {out[name]['composer']['cagr']:+.1%} "
          f"DD {out[name]['composer']['maxdd']:.1%}")
json.dump(out, open(os.path.join(HERE, "out", "g4.json"), "w"), indent=1)
