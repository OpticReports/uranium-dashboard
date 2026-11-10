"""How often are the S3 (pullback) and S4 (trend) legs on OPPOSITE sides?

Context: Hyperliquid nets both legs into one venue position. Two halts in five
days (2026-09-10, 2026-09-14) came from the executor's leg-vs-net mismatch
when the legs opposed each other. Any fix that changes WHEN the legs may
coexist is a strategy change; this script prices it instead of guessing.

Method
  * Same fixture, same engine code path (compute_indicators, resolve_open_exit,
    process_closed_bar, accrue_cash_yield) as app.engine.replay.run_replay,
    with the loop replicated here ONLY so the per-bar leg state can be read
    after each bar. The replicated loop's trade list is asserted identical to
    run_replay's (entry_ts, exit_ts, side, equity_after) before anything is
    reported.
  * Bar state = book.position.side of S3 and S4 AFTER the bar is processed,
    i.e. what the executor would be holding from that bar's close until the
    next bar's open. Classes: both_flat / one_leg / same_side / opposite_side.
  * An opposite-side EPISODE is a maximal run of consecutive opposite bars.
  * Blend P&L share: blend steps replicated VERBATIM from backend/app/main.py
    lines 501-513 (the shipped /kelly/compare consumer; NOT bench_blend's NAV,
    which drops the first step). Each step is a closed trade booked at its
    exit_ts (trade-close basis). A step's log-return log(1+step) is attributed
    to opposite-side bars PRO RATA to the fraction of its held bars
    [entry_ts, exit_ts) on which the other leg was on the opposite side.
    Two stricter attributions are reported alongside (whole step counted if
    ANY held bar was opposite; whole step by the state on its LAST held bar).

Basis: trade-close (exit-step) equity, in-sample over the fixture window,
cash_apy 0, harness fees (S3 6 bps round trip via Position default; S4 12 bps
because core.py:246 sets fee_bps=2*taker_fee_bps explicitly — a known
conservative bias on S4 that the fee-study Position patch does not override).

    python3 research/netting/leg_overlap.py [bars_csv] [out_dir]
"""
from __future__ import annotations
import csv, json, math, os, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)

from app.engine.core import (Bar, Book, BAR_SECONDS, eval_donchian,   # noqa: E402
                             eval_signal, process_closed_bar,
                             resolve_open_exit)
from app.engine.replay import (accrue_cash_yield, compute_indicators,  # noqa: E402
                               run_replay)
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,               # noqa: E402
                        RESEARCH_TRADE)

BARS_CSV = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
OUT = sys.argv[2] if len(sys.argv) > 2 else HERE
FULL_T0 = 1640995200            # 2022-01-01, the study window
CASH_APY = 0.0
W_TREND = 0.25                  # shipped blend: 75% S3 + 25% S4
LEVS = (1.0, 1.5, 2.0)          # 1.0 = unlevered share; 1.5 = S5; 2.0 = S6


def load(path):
    with open(path) as fh:
        return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                    high=float(r["high"]), low=float(r["low"]),
                    close=float(r["close"]), volume=float(r["volume"]))
                for r in csv.DictReader(fh)]


def replay_with_states(bars, books_cfg, scfg, tcfg, start_ts, cash_apy,
                       warmup_bars=210):
    """run_replay's loop, verbatim, plus a per-bar snapshot of each book's
    position side after the bar is processed."""
    inds = compute_indicators(bars)
    books = {c.name: Book(cfg=c) for c in books_cfg}
    states = []                                  # (ts, {book: side|None})
    for i, bar in enumerate(bars):
        if i < warmup_bars:
            continue
        if bar.ts < start_ts:
            continue
        ind = inds[i]
        for book in books.values():
            resolve_open_exit(book, bar, tcfg)
        sigs = {"pullback": eval_signal(bar, ind, scfg),
                "donchian": eval_donchian(bar, ind)}
        for book in books.values():
            process_closed_bar(book, bar, ind, scfg, tcfg,
                               sigs[book.cfg.strategy])
            accrue_cash_yield(book, cash_apy)
        states.append((bar.ts, {n: (b.position.side if b.position else None)
                                for n, b in books.items()}))
    return books, states


def blend_steps(b3, b4, w_trend, lev):
    """VERBATIM from backend/app/main.py:501-513 (the shipped consumer),
    extended only to also return the trade each step came from."""
    evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity, t)
                  for t in b3.trades]
                 + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity, t)
                    for t in b4.trades], key=lambda e: e[:3])
    p3 = p4 = 1.0
    steps = []
    for _, which, ratio, t in evs:
        if which == "P":
            steps.append((lev * (ratio / p3 - 1) * (1 - w_trend), t)); p3 = ratio
        else:
            steps.append((lev * (ratio / p4 - 1) * w_trend, t)); p4 = ratio
    return steps


def classify(s3, s4):
    if s3 is None and s4 is None:
        return "both_flat"
    if s3 is None or s4 is None:
        return "one_leg"
    return "same_side" if s3 == s4 else "opposite_side"


def episodes(flags):
    """Lengths of maximal runs of True."""
    out, run = [], 0
    for f in flags:
        if f:
            run += 1
        elif run:
            out.append(run); run = 0
    if run:
        out.append(run)
    return out


def median(xs):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def main():
    bars = load(BARS_CSV)

    # --- reference run (the harness everyone else uses) -------------------
    ref = run_replay(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL, RESEARCH_TRADE,
                     start_ts=FULL_T0, cash_apy=CASH_APY)
    books, states = replay_with_states(bars, RESEARCH_BOOKS, RESEARCH_SIGNAL,
                                       RESEARCH_TRADE, FULL_T0, CASH_APY)
    for n in ("S3", "S4"):
        a = [(t.entry_ts, t.exit_ts, t.side, round(t.equity_after, 6))
             for t in ref.books[n].trades]
        b = [(t.entry_ts, t.exit_ts, t.side, round(t.equity_after, 6))
             for t in books[n].trades]
        assert a == b, f"replicated loop diverged from run_replay on {n}"
    assert len(states) == ref.n_bars
    b3, b4 = books["S3"], books["S4"]

    # --- per-bar classification --------------------------------------------
    ts = [s[0] for s in states]
    s3 = [s[1]["S3"] for s in states]
    s4 = [s[1]["S4"] for s in states]
    cls = [classify(a, b) for a, b in zip(s3, s4)]
    n = len(cls)
    cnt = Counter(cls)
    frac = {k: cnt.get(k, 0) / n for k in
            ("both_flat", "one_leg", "same_side", "opposite_side")}
    opp = [c == "opposite_side" for c in cls]
    same = [c == "same_side" for c in cls]
    opp_eps = episodes(opp)
    same_eps = episodes(same)
    # which leg is long when they oppose
    opp_mix = Counter(f"S3 {a} / S4 {b}" for a, b, o in zip(s3, s4, opp) if o)

    # sanity: per-trade held bars == bars with that book positioned
    idx = {t: i for i, t in enumerate(ts)}
    for book, sides in (("S3", s3), ("S4", s4)):
        held = sum(1 for x in sides if x is not None)
        from_trades = sum((t.exit_ts - t.entry_ts) // BAR_SECONDS
                          for t in books[book].trades)
        open_tail = ((ts[-1] - books[book].position.entry_ts) // BAR_SECONDS + 1
                     if books[book].position else 0)
        assert held == from_trades + open_tail, (book, held, from_trades, open_tail)

    # --- blend P&L attribution ------------------------------------------------
    def held_range(t):
        i0 = idx[t.entry_ts]
        i1 = idx.get(t.exit_ts, n)          # exit bar itself is NOT held
        return i0, i1

    attrib = {}
    for lev in LEVS:
        steps = blend_steps(b3, b4, W_TREND, lev)
        assert len(steps) == len(b3.trades) + len(b4.trades)
        tot_log = tot_simple = 0.0
        opp_log_prorata = opp_log_any = opp_log_last = 0.0
        opp_simple_prorata = 0.0
        pos_log = neg_log = 0.0
        opp_pos_log = opp_neg_log = 0.0
        per_step = []
        for step, t in steps:
            i0, i1 = held_range(t)
            held = max(1, i1 - i0)
            f_opp = sum(opp[i0:i1]) / held
            any_opp = any(opp[i0:i1])
            last_opp = opp[i1 - 1] if i1 > i0 else False
            lr = math.log1p(step)
            tot_log += lr; tot_simple += step
            opp_log_prorata += lr * f_opp
            opp_simple_prorata += step * f_opp
            opp_log_any += lr * any_opp
            opp_log_last += lr * last_opp
            if lr >= 0:
                pos_log += lr; opp_pos_log += lr * f_opp
            else:
                neg_log += lr; opp_neg_log += lr * f_opp
            per_step.append((t.book, t.exit_ts, step, f_opp))
        attrib[lev] = {
            "n_steps": len(steps),
            "blend_total_log_return": tot_log,
            "blend_final_multiple": math.exp(tot_log),
            "share_opposite_prorata_log": opp_log_prorata / tot_log if tot_log else float("nan"),
            "share_opposite_prorata_simple": opp_simple_prorata / tot_simple if tot_simple else float("nan"),
            "share_opposite_any_held_bar": opp_log_any / tot_log if tot_log else float("nan"),
            "share_opposite_last_held_bar": opp_log_last / tot_log if tot_log else float("nan"),
            "gross_gains_log": pos_log, "gross_losses_log": neg_log,
            "share_of_gross_gains_opposite": opp_pos_log / pos_log if pos_log else float("nan"),
            "share_of_gross_losses_opposite": opp_neg_log / neg_log if neg_log else float("nan"),
            "steps_with_any_opposite_bar": sum(1 for s in per_step if s[3] > 0),
        }

    # per-leg view: of each leg's held bars, how many face an opposed other leg
    per_leg = {}
    for name, mine, other in (("S3", s3, s4), ("S4", s4, s3)):
        held = [(a, b) for a, b in zip(mine, other) if a is not None]
        per_leg[name] = {
            "held_bars": len(held),
            "frac_of_held_with_other_opposite": (sum(1 for a, b in held if b and b != a) / len(held)) if held else 0,
            "frac_of_held_with_other_same": (sum(1 for a, b in held if b == a) / len(held)) if held else 0,
            "trades": len(books[name].trades),
            "trades_touching_opposite": sum(
                1 for t in books[name].trades if any(opp[slice(*held_range(t))])),
        }

    # per-year breakdown of opposite fraction
    import datetime as dt
    by_year = Counter(); by_year_n = Counter()
    for t_, o in zip(ts, opp):
        y = dt.datetime.utcfromtimestamp(t_).year
        by_year_n[y] += 1; by_year[y] += o

    result = {
        "window": f"{dt.datetime.utcfromtimestamp(ts[0]):%Y-%m-%d} .. "
                  f"{dt.datetime.utcfromtimestamp(ts[-1]):%Y-%m-%d} (4h bars, fixture, "
                  f"trading gated to >= 2022-01-01 after 210-bar warmup)",
        "bars_total": n,
        "bar_counts": dict(cnt),
        "bar_fractions": frac,
        "opposite_episodes": {
            "n": len(opp_eps), "median_bars": median(opp_eps),
            "mean_bars": (sum(opp_eps) / len(opp_eps)) if opp_eps else 0,
            "max_bars": max(opp_eps) if opp_eps else 0,
            "total_bars": sum(opp_eps),
            "lengths": opp_eps,
        },
        "same_side_episodes": {
            "n": len(same_eps), "median_bars": median(same_eps),
            "max_bars": max(same_eps) if same_eps else 0,
        },
        "opposite_mix": dict(opp_mix),
        "per_leg": per_leg,
        "per_year_frac_opposite": {str(y): by_year[y] / by_year_n[y] for y in sorted(by_year_n)},
        "blend_attribution": {str(k): v for k, v in attrib.items()},
        "leg_final_multiples": {"S3": b3.equity / b3.cfg.start_equity,
                                "S4": b4.equity / b4.cfg.start_equity},
        "fees": {"S3_round_trip_bps": 6.0,
                 "S4_round_trip_bps": 2 * RESEARCH_TRADE.taker_fee_bps},
    }
    with open(os.path.join(OUT, "leg_overlap.json"), "w") as fh:
        json.dump(result, fh, indent=1)

    # --- text report ------------------------------------------------------------
    lines = []
    P = lines.append
    P("LEG OVERLAP STUDY — S3 pullback vs S4 trend on a netted venue")
    P(f"window: {result['window']}")
    P(f"bars: {n}   basis: trade-close (exit-step), IN-SAMPLE, cash_apy 0, "
      f"S3 fee 6 bps / S4 fee 12 bps (core.py:246, conservative)")
    P("")
    P("BAR CLASSIFICATION (state after each bar = what the venue holds until next open)")
    for k in ("both_flat", "one_leg", "same_side", "opposite_side"):
        P(f"  {k:<14} {cnt.get(k, 0):>6} bars  {100 * frac[k]:6.2f}%")
    P("")
    P("OPPOSITE-SIDE EPISODES (maximal runs of consecutive opposite bars)")
    e = result["opposite_episodes"]
    P(f"  n={e['n']}  median {e['median_bars']:.1f} bars ({e['median_bars'] * 4:.0f}h)  "
      f"mean {e['mean_bars']:.1f}  max {e['max_bars']} bars ({e['max_bars'] * 4 / 24:.1f}d)  "
      f"total {e['total_bars']} bars")
    P(f"  mix while opposed: " + ", ".join(f"{k}: {v}" for k, v in sorted(opp_mix.items())))
    s = result["same_side_episodes"]
    P(f"  (same-side episodes for scale: n={s['n']} median {s['median_bars']:.1f} max {s['max_bars']})")
    P("")
    P("PER LEG: of the bars a leg is held, how often the other leg opposes it")
    for name, d in per_leg.items():
        P(f"  {name}: held {d['held_bars']} bars; other leg OPPOSITE {100 * d['frac_of_held_with_other_opposite']:.1f}% "
          f"/ SAME {100 * d['frac_of_held_with_other_same']:.1f}%; "
          f"{d['trades_touching_opposite']}/{d['trades']} trades touch an opposite bar")
    P("")
    P("PER YEAR fraction of bars opposite: " + "  ".join(
        f"{y}: {100 * v:.1f}%" for y, v in result["per_year_frac_opposite"].items()))
    P("")
    P("BLEND P&L SHARE ON OPPOSITE-SIDE BARS (steps verbatim main.py:501-513, 75/25)")
    P("  attribution: step's log(1+r) x fraction of its held bars that were opposite (primary)")
    for lev in LEVS:
        a = attrib[lev]
        P(f"  lev {lev}: blend x{a['blend_final_multiple']:.3f} over {a['n_steps']} steps | "
          f"opposite share: prorata {100 * a['share_opposite_prorata_log']:.1f}% "
          f"(simple-sum {100 * a['share_opposite_prorata_simple']:.1f}%) | "
          f"any-held-bar {100 * a['share_opposite_any_held_bar']:.1f}% | "
          f"last-held-bar {100 * a['share_opposite_last_held_bar']:.1f}% | "
          f"steps touching opposite {a['steps_with_any_opposite_bar']}/{a['n_steps']}")
    a = attrib[1.0]
    P(f"  gross split (lev 1.0, log): gains {a['gross_gains_log']:.3f} of which "
      f"{100 * a['share_of_gross_gains_opposite']:.1f}% on opposite bars; losses "
      f"{a['gross_losses_log']:.3f} of which {100 * a['share_of_gross_losses_opposite']:.1f}% on opposite bars")
    P("")
    P("CAVEATS")
    P("  - trade-close basis: P&L is booked at exit_ts and spread pro rata over held bars; MTM would differ.")
    P("  - in-sample: same fixture the strategies were selected on; not a forecast.")
    P("  - S4 fee is 12 bps round trip in this harness (core.py sets fee_bps=2*taker explicitly); known conservative bias.")
    P("  - 'share of P&L' is a share of a compounded log return; when the blend total is small the ratio is unstable.")
    P("  - a NEGATIVE share means opposite bars carried net losses in-sample. It is an ATTRIBUTION of the")
    P("    realized path, NOT a counterfactual: forbidding coexistence would change entries, exits and the")
    P("    equity each leg sizes from. Pricing a specific coexistence rule needs its own replay.")
    P("  - a bar is 'opposite' only while BOTH legs hold; the executor's exposure to netting also includes")
    P("    the one_leg->opposite transition bars (entries/exits), which this bar count does not single out.")
    txt = "\n".join(lines)
    print(txt)
    with open(os.path.join(OUT, "results.txt"), "w") as fh:
        fh.write(txt + "\n")

    # --- chart ----------------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        dts = [dt.datetime.utcfromtimestamp(t_) for t_ in ts]
        code = {"both_flat": 0, "one_leg": 1, "same_side": 2, "opposite_side": 3}
        c = np.array([code[x] for x in cls])
        fig = plt.figure(figsize=(14, 9))
        gs = fig.add_gridspec(3, 1, height_ratios=[2, 1, 1.4])
        axes = [fig.add_subplot(gs[0])]
        axes.append(fig.add_subplot(gs[1], sharex=axes[0]))
        axes.append(fig.add_subplot(gs[2]))       # histogram: integer x, not dates
        ax = axes[0]
        cols = {0: "#d9d9d9", 1: "#9ecae1", 2: "#31a354", 3: "#e6550d"}
        # blend curve at lev 1.0 (verbatim steps compounded) for context
        steps = blend_steps(b3, b4, W_TREND, 1.0)
        eq, curve = 1.0, []
        for step, t in steps:
            eq *= 1 + step; curve.append((dt.datetime.utcfromtimestamp(t.exit_ts), eq))
        ax.plot([x[0] for x in curve], [x[1] for x in curve], color="k", lw=1.2,
                label="blend 75/25, lev 1.0 (trade-close steps)")
        ax.set_yscale("log")
        ymin, ymax = ax.get_ylim()
        for k, colr in cols.items():
            if k == 0:
                continue
            m = c == k
            ax.fill_between(dts, ymin, ymax, where=m, color=colr, alpha=0.35 if k == 3 else 0.18,
                            lw=0, label={1: "one leg", 2: "same side", 3: "OPPOSITE side"}[k])
        ax.set_ylim(ymin, ymax)
        ax.set_title("S3 x S4 leg overlap — shaded by bar class; blend equity for context")
        ax.legend(loc="upper left", fontsize=8)
        ax = axes[1]
        sd = {None: 0, "L": 1, "S": -1}
        ax.step(dts, [sd[x] for x in s3], where="post", color="#1f77b4", lw=1, label="S3 pullback")
        ax.step(dts, [sd[x] for x in s4], where="post", color="#ff7f0e", lw=1, label="S4 trend", alpha=0.8)
        ax.set_yticks([-1, 0, 1]); ax.set_yticklabels(["short", "flat", "long"])
        ax.legend(loc="upper left", fontsize=8)
        ax = axes[2]
        ax.hist(opp_eps, bins=range(1, (max(opp_eps) if opp_eps else 1) + 2), color="#e6550d")
        ax.set_xlabel("opposite-side episode length (4h bars)")
        ax.set_ylabel("episodes")
        ax.set_title(f"{len(opp_eps)} opposite episodes; median {median(opp_eps):.0f} bars; "
                     f"{100 * frac['opposite_side']:.1f}% of all bars")
        axes[2].set_xlim(left=0)
        # the histogram axis is not a date axis; detach sharex for it
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "leg_overlap.png"), dpi=110)
        print(f"\nwrote {OUT}/leg_overlap.png")
    except Exception as ex:  # noqa: BLE001
        print(f"\n(chart skipped: {ex})")
    print(f"wrote {OUT}/results.txt and leg_overlap.json")


if __name__ == "__main__":
    main()
