"""Sensitivities on my own replay: things that would only matter if a halt fired,
plus the builder's declared sensitivity runs (XBTUSD proxy funding, engine halts off)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify as V

def head(m):
    b = m["balances"]
    return (f"3m {b[91]:>10,.0f} 6m {b[182]:>10,.0f} 9m {b[273]:>10,.0f} 12m {b[365]:>10,.0f} "
            f"maxDD {m['max_dd']:.4f} intra {m['max_dd_intrabar']:.4f} halts {[(h['kind'], h['date']) for h in m['halts']]} "
            f"ddmargin {m['margins']['dd'][0]:,.0f} dlmargin {m['margins']['dl'][0]:,.0f} hw_end {m['hw_end']:,.0f}")

for s in ("COVID", "2008", "1999"):
    for K in (0.75, 0.30):
        base, R = V.run(s, K)
        print(f"== {s} K{K:g}")
        print("   A intrabar (base)      ", head(base))
        for label, kw in (("HW from intrabar highs ", dict(hw_intrabar=True)),
                          ("worst = per-pos adverse", dict(worst_mode="adverse")),
                          ("variant B              ", dict(variant="B")),
                          ("close-only             ", dict(intrabar=False))):
            m, _ = V.run(s, K, **kw)
            same = all(abs(m["balances"][d] - base["balances"][d]) < 0.01 for d in (91, 182, 273, 365))
            print(f"   {label}", head(m), "| balances identical to base" if same else "| DIFFERS")
        if K == 0.75:
            if s != "1999":
                m, Rx = V.run(s, K, funding_src="XBTUSD")
                fn = os.path.join(V.STRESS, "runs", f"{s}_xbtfund_K0.75_off_0_A_intra_eh_first_cross_carry.json")
                Rx = json.load(open(fn))
                print(f"   XBTUSD proxy funding   ", head(m), f"| theirs 12m {Rx['balances']['365']['equity']:,.0f} maxDD {Rx['max_dd']:.4f} carry_final {Rx['carry_value'][-1]:,.0f} mine carry_final {m['carry']['final']:,.0f} flips mine {len(m['carry']['flips'])}")
            m, Rn = V.run(s, K, engine_halts=False)
            fn = os.path.join(V.STRESS, "runs", f"{s}_noeh_K0.75_off_0_A_intra_noeh_first_cross_carry.json")
            Rn = json.load(open(fn))
            print(f"   engine halts OFF       ", head(m), f"| theirs 12m {Rn['balances']['365']['equity']:,.0f} maxDD {Rn['max_dd']:.4f} fees {Rn['fees']:,.0f} mine fees {m['fees']:,.0f}")
