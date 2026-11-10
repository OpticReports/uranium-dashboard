"""How much rides on the S3 seam discrepancy (CSV: LONG from 84,121.28; live: PENDING)?
CF1: drop the seam trade from the pullback list (paper book + executor).
CF2: pullback book FLAT at t0 (leg_trades from t0 on the spliced bars; its own seam-free list)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import verify as V
import harness as H
from app.engine.core import Bar

for scen in ("COVID", "2008", "1999"):
    for K in (0.75,):
        base, R = V.run(scen, K, verbose=False)
        t0 = R["t0"]
        now = R["now_used"]
        btc = V.read_bars(os.path.join(V.CAGR, "data", "bars_4h_btcusd.csv"), now)
        hist, path, scale, today_close = V.splice(btc, R["anchor_ts"], t0, R["n_path_bars"], R["last_real_ts"])
        closes_all = {b[0]: b[4] for b in hist}; closes_all.update({b[0]: b[4] for b in path})
        eth = V.read_bars(os.path.join(V.CAGR, "data", "bars_4h_ethusd.csv"), now)
        _, epath, _, _ = V.splice(eth, R["anchor_ts"], t0, R["n_path_bars"], R["last_real_ts"])
        src = R["carry_funding_source"]
        fr = V.carry_sleeve.load_funding(os.path.join(V.STRESS, "data", f"funding_bitmex_{src}.csv"),
                                         lo_ms=(R["anchor_ts"] - 31 * V.DAY) * 1000, hi_ms=(R["anchor_ts"] + R["n_path_bars"] * V.BAR) * 1000)
        shift = (t0 - R["anchor_ts"]) * 1000
        cr = V.carry_sleeve.simulate_carry({b[0]: b[4] for b in epath}, {k + shift: v for k, v in fr.items()}, V.CARRY_START)
        eng = R["engine_trades"]
        bars = [Bar(ts=b[0], open=b[1], high=b[2], low=b[3], close=b[4], volume=b[5]) for b in hist + path]
        flat = [dict(leg="pullback", side=t.side, entry_ts=t.entry_ts, entry_price=t.entry_price, exit_ts=t.exit_ts,
                     exit_price=t.exit_price, reason=t.reason) for t in H.leg_trades(bars, "pullback", leg="pullback", start_ts=t0)]
        variants = {"base (CSV seam: S3 long 84,121)": eng["pullback"],
                    "CF1 seam trade dropped": eng["pullback"][1:],
                    "CF2 S3 flat at t0 (fresh book)": flat}
        print(f"== {scen} K{K:g}")
        for label, pl in variants.items():
            pb = V.paper_book(pl, V.PAPER_SEED["pullback"])
            tb = V.paper_book(eng["trend"], V.PAPER_SEED["trend"])
            res = V.replay(path, closes_all, {"pullback": pb["published"], "trend": tb["published"]}, K, cr.value, today_close=today_close)
            idx = {t: i for i, t in enumerate(res["ts"])}
            i12 = idx.get(t0 + 365 * V.DAY, len(res["ts"]) - 1)
            print(f"   {label:34s} S3 halt {pb['halted']} {pb['halt_date']} eq@halt {str(pb['equity_at_halt'] and round(pb['equity_at_halt'])):>7} "
                  f"(line {0.7*107860:,.0f}) S3 end {pb['equity_end']:,.0f} min S3 eq {min([p[1] for p in pb['path']] or [0]):,.0f} | "
                  f"12m {res['equity_total'][i12]:,.0f} maxDD {V.max_dd(res['equity_total'], 100000.0):.4f} halts {len(res['halts'])} first pb trade {pl[0]['entry_date'] if 'entry_date' in pl[0] else V.utc(pl[0]['entry_ts'])} @ {pl[0]['entry_price']:,.0f}")
