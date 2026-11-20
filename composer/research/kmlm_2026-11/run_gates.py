"""Gates G1-G3 of PREREG.md, plus the two internal equalities the study rests on. Prints PASS/FAIL per
gate and writes out/gates.json. No result of the study is read here: only the live rule against
Composer's own backtest, and builders against each other."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "zvol_2026-11"))
import data  # noqa: E402
import ksim as ks  # noqa: E402
import lib  # noqa: E402

sr = ks.sr
END = "2026-11-17"            # Composer's frozen backtest ends here
out = {}
tree = ks.approved()
P = data.panel_ab(END)

# ---- G1: the live rule against Composer's own backtest
bt = lib.load_bt(os.path.join(HERE, "..", "zvol_2026-11", "data", "bt_KMLM.json"))
t0 = time.time()
r = ks.simulate(tree, P, "2023-04-19", END)
dt_fast = time.time() - t0
days = [d for d in r["days"] if d in bt["ret"]]
mine = [r["ret"][r["days"].index(d)] for d in days]
theirs = [bt["ret"][d] for d in days]
hold_ok = n_h = 0
worst = (0, None)
for d in [r["days"][0]] + days[:-1] if False else days[:-1]:
    w = {t: bt["w"][t].get(d, 0.0) for t in bt["w"]}
    h = r["held"].get(d)
    if h is None:
        continue
    dist = 0.5 * sum(abs(h.get(t, 0) - w.get(t, 0)) for t in set(h) | set(w))
    n_h += 1
    hold_ok += dist <= 0.015
    worst = max(worst, (dist, d))
c = ks.corr(mine, theirs)
sm, st = ks.stats(mine), ks.stats(theirs)
out["G1"] = {"sessions": len(days), "corr": c, "holdings_within_1.5pct": [hold_ok, n_h], "worst": worst,
             "sim": sm, "composer": st, "mean_abs_daily_diff_bp": 1e4 * sum(abs(a - b) for a, b in zip(mine, theirs)) / len(days),
             "pass": bool(c >= 0.9999 and hold_ok == n_h)}
print(f"G1 {'PASS' if out['G1']['pass'] else 'FAIL'}: {len(days)} sessions, corr {c:.5f}, holdings {hold_ok}/{n_h} "
      f"(worst {worst[0]:.4f} on {worst[1]}), sim CAGR {sm['cagr']:+.1%} DD {sm['maxdd']:.1%} vs Composer "
      f"{st['cagr']:+.1%} DD {st['maxdd']:.1%}; mean |diff| {out['G1']['mean_abs_daily_diff_bp']:.2f} bp")

# ---- fast RSI cache equals the evaluator's own
slow = ks.simulate(tree, P, "2026-06-01", END, fast=False)
fast = ks.simulate(tree, P, "2026-06-01", END)
same = sum(slow["target"][d] == fast["target"][d] for d in slow["target"])
out["fast_cache"] = {"identical_targets": [same, len(slow["target"])], "pass": same == len(slow["target"])}
print(f"fast RSI cache {'PASS' if out['fast_cache']['pass'] else 'FAIL'}: identical targets {same}/{len(slow['target'])}")

# ---- G2/G3: builders touch only what they name
base_sha = sr.tree_sha1(tree)
sleeve = lambda t: sr.sha1_of(sr.canonical([g for g in ks.nodes(t, lambda n: n.get("step") == "group"   # noqa: E731
                                            and (n.get("name") or "").strip() == "VIX sleeve")][0]))
pops10 = {n["lhs-val"]: float(n["rhs-val"]) for n in ks.pop_nodes(tree)}
dips10 = {n["lhs-val"]: float(n["rhs-val"]) for n in ks.dip_nodes(tree)}
same10 = {"switch": ks.v_switch_rsi(tree, 10), "switch+picks": ks.v_switch_rsi(tree, 10, picks=True),
          "thresholds": ks.v_thresholds(tree, 10, pops=pops10, dips=dips10),
          "form": ks.v_switch_form(tree, ("relative-strength-index", "XLK", 10), ("relative-strength-index", "KMLM", 10))}
g2 = {k: sr.tree_sha1(v) == base_sha for k, v in same10.items()}
others = {"switch14": ks.v_switch_rsi(tree, 14), "both14": ks.v_switch_rsi(tree, 14, picks=True),
          "thr14": ks.v_thresholds(tree, 14, pops=pops10, dips=dips10), "flag": ks.v_switch_flag(tree),
          "sma50": ks.v_switch_form(tree, ("current-price", "XLK", None), ("moving-average-price", "XLK", 50)),
          "split": ks.v_split(tree, (8, 10, 12))}
g2s = {k: sleeve(v) == sleeve(tree) for k, v in {**same10, **others}.items()}
changed = {k: sr.tree_sha1(v) != base_sha for k, v in others.items()}
g3 = True
for v in others.values():
    for n in ks.nodes(v, lambda n: True):
        for side in ("lhs", "rhs", "sort-by"):
            try:
                sr.window(n, side)
            except sr.Unsupported:
                g3 = False
out["G2"] = {"n10_equals_approved": g2, "sleeve_unchanged": g2s, "variants_differ": changed,
             "pass": all(g2.values()) and all(g2s.values()) and all(changed.values())}
out["G3"] = {"pass": g3}
print(f"G2 {'PASS' if out['G2']['pass'] else 'FAIL'}: N=10 equals approved {g2}; sleeve unchanged {all(g2s.values())}; "
      f"variants differ {all(changed.values())}")
print(f"G3 {'PASS' if g3 else 'FAIL'}: no window conflict in any variant")

# ---- an injected flag equals the tree's own condition, at three windows and for two other forms
eq = {}
for n in (5, 10, 20):
    a = ks.simulate(ks.v_switch_rsi(tree, n), P, "2023-04-19", END)
    rx, rk = ks.rsi_series(P["XLK"], n), ks.rsi_series(P["KMLM"], n)
    flag = {d: (None if rx.get(d) is None or rk.get(d) is None else rx[d] > rk[d]) for d in P["XLK"]}
    b = ks.simulate(ks.v_switch_flag(tree), P, "2023-04-19", END, flags=[flag])
    eq[f"rsi{n}"] = [sum(a["target"][d] == b["target"][d] for d in a["target"]), len(a["target"])]
a = ks.simulate(others["sma50"], P, "2023-04-19", END)
sm50 = ks.sma_series(P["XLK"], 50)
b = ks.simulate(ks.v_switch_flag(tree), P, "2023-04-19", END,
                flags=[{d: (None if sm50[d] is None else P["XLK"][d] > sm50[d]) for d in P["XLK"]}])
eq["sma50"] = [sum(a["target"][d] == b["target"][d] for d in a["target"]), len(a["target"])]
a = ks.simulate(ks.v_switch_form(tree, ("cumulative-return", "XLK", 20), ("cumulative-return", "KMLM", 20)), P, "2023-04-19", END)
cx, ck = ks.ret_series(P["XLK"], 20), ks.ret_series(P["KMLM"], 20)
b = ks.simulate(ks.v_switch_flag(tree), P, "2023-04-19", END,
                flags=[{d: (None if cx.get(d) is None or ck.get(d) is None else cx[d] > ck[d]) for d in P["XLK"]}])
eq["mom20"] = [sum(a["target"][d] == b["target"][d] for d in a["target"]), len(a["target"])]
out["flag_equals_tree"] = {"cells": eq, "pass": all(x == y for x, y in eq.values())}
print(f"flag = tree {'PASS' if out['flag_equals_tree']['pass'] else 'FAIL'}: {eq}")
out["seconds_per_run"] = dt_fast
os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
json.dump(out, open(os.path.join(HERE, "out", "gates.json"), "w"), indent=1, default=str)
print("ALL GATES PASS" if all(v.get("pass", True) for v in out.values() if isinstance(v, dict)) else "A GATE FAILED")
