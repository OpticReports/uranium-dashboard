"""CANDIDATE C, step 6: THE NET-OF-FUNDING ANSWER.

candC_portfolio.py's k values are GROSS of funding. candC_funding.py showed the
donchian legs pay 15-28 bp of funding per round trip -- 2-3x the entire 8.64 bp
fee -- because they hold 200-340 hours. The trend leg IS the diversifier, so
the diversification benefit is partly paid for in funding and the headline has
to be restated net.

This does it exactly rather than by subtracting an average: the replay is
re-run with a hook that records, for every 4h bar, the leg's position SIDE and
its notional/equity ratio. Each bar's realised funding is then the sum of the
HL hourly stamps inside that bar, signed by side and scaled by leverage, and it
is subtracted from that bar's return before any Kelly or drawdown statistic is
computed.

Run: python3 research/scale/candC_net.py
"""
from __future__ import annotations
import bisect, dataclasses, json, os, time, urllib.request

import numpy as np
# candC_lib puts backend/ on sys.path; import it BEFORE any app.* import
from candC_lib import (BARS_PER_YEAR, EQUITY, FEE_TAKER_RT, HERE, ann_stats,
                       asset_path, boot_stats, dd_constrained, load_bars)
import app.engine.core as core                                    # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)
from app.engine.replay import run_replay                          # noqa: E402

API = "https://api.hyperliquid.xyz/info"
FETCH = json.load(open(os.path.join(HERE, "candC_fetch.json")))
UNIVERSE = FETCH["eligible"]
BAR = 4 * 3600


def post(body, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except Exception:                                          # noqa: BLE001
            if a == tries - 1:
                raise
            time.sleep(1.5 * (a + 1))


def funding_series(coin, start_ms, end_ms):
    out, cur = [], start_ms
    while cur < end_ms:
        chunk = post({"type": "fundingHistory", "coin": coin,
                      "startTime": cur, "endTime": end_ms})
        if not chunk:
            break
        out.extend(chunk)
        nxt = chunk[-1]["time"] + 1
        if nxt <= cur:
            break
        cur = nxt
    seen, ded = set(), []
    for r in sorted(out, key=lambda r: r["time"]):
        if r["time"] not in seen:
            seen.add(r["time"])
            ded.append((r["time"] // 1000, float(r["fundingRate"])))
    ts = np.array([x[0] for x in ded])
    rt = np.array([x[1] for x in ded])
    return ts, np.concatenate([[0.0], np.cumsum(rt)])


WARMUP = 210


def replay_with_state(bars, rt_bps=FEE_TAKER_RT):
    """Per-bar (ts, mtm_equity, side, notional/equity) for every book.

    Bar timestamps are DERIVED, not captured: run_replay imports
    process_closed_bar by name (`from .core import process_closed_bar`), so
    monkeypatching core.process_closed_bar does not reach replay's reference --
    a first cut did exactly that and every ts came back None. _mark_to_market
    IS reached, because core.process_closed_bar looks it up as a module global.
    With no start_ts/end_ts the processed bars are exactly bars[WARMUP:], in
    order, one mark each; asserted below rather than assumed."""
    trace: dict[str, list] = {}
    orig = core._mark_to_market

    def traced(book, close):
        orig(book, close)
        p = book.position
        sd = 0 if p is None else (1 if p.side == "L" else -1)
        lev = 0.0 if p is None else (p.notional / book.equity if book.equity > 0 else 0.0)
        trace.setdefault(book.cfg.name, []).append((book.mtm_equity, sd, lev))

    core._mark_to_market = traced
    try:
        run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL,
                   dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=rt_bps / 2.0),
                   warmup_bars=WARMUP, cash_apy=0.0)
    finally:
        core._mark_to_market = orig
    ts = [b.ts for b in bars[WARMUP:]]
    out = {}
    for name, rows in trace.items():
        assert len(rows) == len(ts), (name, len(rows), len(ts))
        out[name] = [(ts[i], *rows[i]) for i in range(len(ts))]
    return out


def main():
    bars0 = load_bars(asset_path("BTC"))
    t0, t1 = bars0[0].ts * 1000, (bars0[-1].ts + BAR) * 1000
    print("=" * 100)
    print("EXACT PER-BAR FUNDING, applied to each leg's own per-bar return")
    print("=" * 100)
    GROSS, NET = {}, {}
    for coin in UNIVERSE:
        fts, fcum = funding_series(coin, t0, t1)
        tr = replay_with_state(load_bars(asset_path(coin)))
        for leg in ("S3", "S4"):
            rows = tr[leg]
            ts = np.array([r[0] for r in rows])
            eq = np.array([r[1] for r in rows])
            sd = np.array([r[2] for r in rows], float)
            lv = np.array([r[3] for r in rows], float)
            # funding accrued during bar j = stamps in (ts[j], ts[j]+4h]
            lo = np.searchsorted(fts, ts, side="right")
            hi = np.searchsorted(fts, ts + BAR, side="right")
            f_bar = fcum[hi] - fcum[lo]
            # sign: long pays positive funding
            drag = -sd * lv * f_bar
            r_gross = np.diff(eq) / eq[:-1]
            # the position held DURING bar j+1 is the one recorded at bar j's
            # close, so the drag that hits return j is drag[j] (state at j-1's
            # close carried into j). Align to the same convention as r_gross.
            r_net = r_gross + drag[:-1]
            GROSS[(coin, leg)] = r_gross
            NET[(coin, leg)] = r_net
            ann_drag = drag[:-1].mean() * BARS_PER_YEAR * 100
            print(f"  {coin:<6} {leg:<4} in-market {(lv>0).mean()*100:>5.1f}%  "
                  f"funding drag {ann_drag:>+7.3f}%/yr of EQUITY at 1.0x  "
                  f"ann.SR {ann_stats(r_gross)['ann_SR']:>+6.2f} -> "
                  f"{ann_stats(r_net)['ann_SR']:>+6.2f}")

    def blend(d, coins, w=0.75):
        n = len(coins)
        return sum((w / n) * d[(c, "S3")] + ((1 - w) / n) * d[(c, "S4")] for c in coins)

    print()
    print("=" * 100)
    print("THE HEADLINE, GROSS vs NET OF FUNDING")
    print("=" * 100)
    OUT = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "universe": UNIVERSE, "cases": {}}
    print(f"  {'case':<30} {'basis':<6} {'annSR':>7} {'k':>6} {'gross $':>11} "
          f"{'eq for $1m':>12} {'mult':>7}")
    res = {}
    for lbl, coins in (("BTC only (today)", ["BTC"]), ("6 assets", UNIVERSE)):
        for basis, d in (("gross", GROSS), ("NET", NET)):
            s = blend(d, coins)
            k = dd_constrained(s)
            st = ann_stats(s)
            p10, p50, pneg = boot_stats(s)
            res[(lbl, basis)] = {"k": k, "gross_usd": k * EQUITY,
                                 "equity_for_1m": 1_000_000 / k if k else None,
                                 "equity_for_100k": 100_000 / k if k else None,
                                 "kstar_p10": p10, "prob_neg_edge": pneg, **st}
    for lbl in ("BTC only (today)", "6 assets"):
        for basis in ("gross", "NET"):
            r = res[(lbl, basis)]
            r["mult_vs_btc_same_basis"] = r["k"] / res[("BTC only (today)", basis)]["k"] \
                if res[("BTC only (today)", basis)]["k"] else None
            OUT["cases"][f"{lbl} | {basis}"] = r
            print(f"  {lbl:<30} {basis:<6} {r['ann_SR']:>+7.2f} {r['k']:>6.3f} "
                  f"${r['gross_usd']:>10,.0f} "
                  f"${r['equity_for_1m']:>11,.0f} "
                  f"{r['mult_vs_btc_same_basis']:>6.2f}x")
    mg = res[("6 assets", "gross")]["mult_vs_btc_same_basis"]
    mn = res[("6 assets", "NET")]["mult_vs_btc_same_basis"]
    print(f"\n  DIVERSIFICATION MULTIPLE: {mg:.2f}x gross -> {mn:.2f}x net of funding")
    OUT["multiple_gross"] = mg
    OUT["multiple_net"] = mn

    # within-mix net: does funding kill the trend leg's contribution?
    print()
    print("=" * 100)
    print("NET OF FUNDING, WITHIN-ASSET MIX — funding hits the trend leg hardest")
    print("  (200-340h holds), so the optimal pullback share should RISE net.")
    print("=" * 100)
    print(f"  {'pullback share':>15} {'k gross':>9} {'k NET':>8} {'gross $ NET':>13}")
    OUT["within_mix_net"] = {}
    for wp in (1.00, 0.90, 0.85, 0.75, 0.60, 0.50):
        kg = dd_constrained(blend(GROSS, UNIVERSE, wp))
        kn = dd_constrained(blend(NET, UNIVERSE, wp))
        OUT["within_mix_net"][f"{wp:.2f}"] = {"k_gross": kg, "k_net": kn,
                                             "gross_usd_net": kn * EQUITY}
        print(f"  {wp:>15.2f} {kg:>9.3f} {kn:>8.3f} ${kn*EQUITY:>12,.0f}"
              + ("   <- shipped S5 mix" if abs(wp - 0.75) < 1e-9 else ""))

    np.savez_compressed(os.path.join(HERE, "candC_net_streams.npz"),
                        assets=np.array(UNIVERSE),
                        **{f"net_{c}_{l}": NET[(c, l)] for c in UNIVERSE for l in ("S3", "S4")})
    json.dump(OUT, open(os.path.join(HERE, "candC_net.json"), "w"), indent=1, default=str)
    print("\nfrozen -> candC_net.json")


if __name__ == "__main__":
    main()
