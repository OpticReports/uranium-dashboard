"""How calm was the calm window, and does depth thin when vol rises?

The honest weakness of any live book sample is that it characterises the regime
it was taken in. This script does two things about that:

  1. Ranks the sampling window's realised 1m volatility against the last 10 days
     of Hyperliquid 1m candles -> a PERCENTILE for "how calm was calm".
  2. Inside the sample, regresses available depth and the $1m slip on trailing
     60s realised vol -> a measured ELASTICITY of liquidity to volatility, which
     is the only defensible way to extrapolate toward a stressed book from a
     calm one. The extrapolation is reported with its own caveat: the vol range
     inside a calm 22-minute window is a rounding error next to a liquidation
     cascade, so the elasticity is a direction, not a forecast.

READ-ONLY. Usage: python3 stress.py <out_dir>
"""
from __future__ import annotations
import datetime as dt, json, math, os, statistics, subprocess, sys, time

INFO = "https://api.hyperliquid.xyz/info"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else HERE


def post(b, tries=4):
    for a in range(tries):
        r = subprocess.run(["curl", "-sS", "--max-time", "30", "-X", "POST", INFO,
                            "-H", "Content-Type: application/json", "-d", json.dumps(b)],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            try:
                return json.loads(r.stdout)
            except Exception:
                pass
        time.sleep(1.5 * (a + 1))
    raise RuntimeError("info failed")


def pctl(xs, p):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * p / 100.0
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def rank_pct(xs, v):
    return 100.0 * sum(1 for x in xs if x <= v) / len(xs)


def corr(a, b):
    n = len(a)
    if n < 10:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def ols(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    den = sum((a - mx) ** 2 for a in x)
    if den == 0:
        return None, None
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / den
    return b, my - b * mx


def main():
    rows = []
    with open(os.path.join(OUT, "book_calm.jsonl")) as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    res = {"n_book_samples": len(rows)}

    # ---- 1. how calm was the window, vs 10 days of 1m candles ----
    end = int(time.time() * 1000)
    cs = sorted(post({"type": "candleSnapshot",
                      "req": {"coin": "BTC", "interval": "1m",
                              "startTime": end - 10 * 86400 * 1000, "endTime": end}}),
                key=lambda c: c["t"])
    px = [(int(c["t"]), float(c["c"]), float(c["h"]), float(c["l"])) for c in cs]
    rets_1m = [abs(px[i + 1][1] / px[i][1] - 1) * 1e4 for i in range(len(px) - 1)]
    ranges_1m = [(h - l) / c * 1e4 for _, c, h, l in px]

    t0, t1 = rows[0]["t"], rows[-1]["t"]
    win = [(t, c, h, l) for t, c, h, l in px if t0 <= t <= t1]
    win_rets = [abs(win[i + 1][1] / win[i][1] - 1) * 1e4 for i in range(len(win) - 1)]
    win_ranges = [(h - l) / c * 1e4 for _, c, h, l in win]
    res["how_calm_was_calm"] = {
        "window_utc": [dt.datetime.utcfromtimestamp(t0 / 1000).isoformat() + "Z",
                       dt.datetime.utcfromtimestamp(t1 / 1000).isoformat() + "Z"],
        "n_1m_candles_in_window": len(win),
        "window_mean_abs_1m_move_bp": (sum(win_rets) / len(win_rets)) if win_rets else None,
        "window_mean_1m_hl_range_bp": (sum(win_ranges) / len(win_ranges)) if win_ranges else None,
        "ten_day_1m_abs_move_bp": {f"p{p}": pctl(rets_1m, p) for p in (10, 50, 90, 99)},
        "ten_day_1m_hl_range_bp": {f"p{p}": pctl(ranges_1m, p) for p in (10, 50, 90, 99)},
        "window_percentile_vs_10d_by_abs_move":
            rank_pct(rets_1m, sum(win_rets) / len(win_rets)) if win_rets else None,
        "window_percentile_vs_10d_by_hl_range":
            rank_pct(ranges_1m, sum(win_ranges) / len(win_ranges)) if win_ranges else None,
        "worst_1m_move_in_10d_bp": max(rets_1m),
        "worst_1m_hl_range_in_10d_bp": max(ranges_1m),
    }

    # ---- 2. depth / slip vs trailing 60s vol, inside the sample ----
    vol, dep, slip1m, spr = [], [], [], []
    for i, r in enumerate(rows):
        back = [q for q in rows[max(0, i - 20):i + 1]]
        if len(back) < 5:
            continue
        lr = [abs(b["mid"] / a["mid"] - 1) * 1e4 for a, b in zip(back, back[1:])]
        v = sum(lr) / len(lr)
        s = r["buy"]["1000000"]
        if not s or not s["complete"]:
            continue
        vol.append(v)
        dep.append(r["ask_depth_usd"])
        slip1m.append(s["slip_bp"])
        spr.append(r["spread_bp"])
    b_d, a_d = ols(vol, dep)
    b_s, a_s = ols(vol, slip1m)
    res["liquidity_vs_vol_within_sample"] = {
        "n": len(vol),
        "trailing_60s_abs_move_bp": {"p10": pctl(vol, 10), "p50": pctl(vol, 50),
                                     "p90": pctl(vol, 90), "max": pctl(vol, 100)},
        "corr_vol_vs_ask_depth": corr(vol, dep),
        "corr_vol_vs_1m_buy_slip": corr(vol, slip1m),
        "corr_vol_vs_spread": corr(vol, spr),
        "ols_ask_depth_usd_per_bp_of_60s_vol": b_d,
        "ols_1m_slip_bp_per_bp_of_60s_vol": b_s,
        "extrapolation_illustrative": None if b_s is None else {
            "slip_1m_bp_at_10d_p99_1m_vol": (a_s or 0) + (b_s or 0) *
                (res["how_calm_was_calm"]["ten_day_1m_abs_move_bp"]["p99"]),
            "slip_1m_bp_at_10d_worst_1m_vol": (a_s or 0) + (b_s or 0) *
                res["how_calm_was_calm"]["worst_1m_move_in_10d_bp"],
            "caveat": "LINEAR extrapolation far outside the sampled vol range. In a "
                      "real cascade makers pull entirely and the relation is not "
                      "linear -- treat as a direction and a lower bound, not a number "
                      "to size on.",
        },
    }

    res["what_would_actually_characterise_a_stressed_book"] = [
        "L2 snapshots recorded THROUGH a stress event: HL publishes raw historical "
        "L2 book data to the hyperliquid-archive S3 bucket (requester-pays). Pull "
        "the book for known cascades and recompute the same $1m walk. This is the "
        "only direct answer and it needs an AWS requester-pays account.",
        "A standing sampler: run book_sampler.py continuously (1/min) and keep the "
        "worst decile by concurrent 1m vol. After one month there is a real thin-book "
        "sample and it costs nothing but uptime.",
        "The executor's OWN fills: log realised slip vs mid on every entry/exit at "
        "live size. That is the measurement that actually governs, and it is free.",
        "NOT a substitute: extrapolating a calm-window elasticity, which is what "
        "section 2 above does. It is reported to bound the direction, not to size on.",
    ]
    json.dump(res, open(os.path.join(OUT, "stress.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
