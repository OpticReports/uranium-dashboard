"""The registered variant grid (PREREG.md section 3). Changing this file after
PREREG.md is committed is a protocol amendment and must be logged as one."""
import dataclasses
import random

from harness import V

ROUND1 = (
    # F1 full take-profit: resting limit at entry -/+ k x ATR(signal bar)
    [V(name=f"F1_tp{k}", tp_k=k) for k in (3, 5, 8, 12, 16)]
    # F2 partial take-profit: take fraction f at k x ATR, trail the rest
    + [V(name=f"F2_ptp{k}_f{int(f * 100)}", ptp_k=k, ptp_f=f)
       for f in (1 / 3, 1 / 2) for k in (3, 5, 8)]
    # F3 profit lock: after k x ATR of close-MFE, trail multiple 5 -> m
    + [V(name=f"F3_lock{k}_m{m}", lock_k=k, lock_m=m)
       for k in (4, 8) for m in (2.5, 3.5)]
    # F4 breakeven stop after k x ATR of close-MFE
    + [V(name=f"F4_be{k}", be_k=k) for k in (2, 4)]
    # F5a overextension: favorable |close - SMA50| / ATR >= z, exit next open
    + [V(name=f"F5a_ext{z}", ext_z=z) for z in (4, 6, 8)]
    # F5b RSI extreme in the trade's favor, exit next open
    + [V(name=f"F5b_rsi{l}", rsi_l=l) for l in (15, 20, 25)]
    # F6 time exit after n bars held
    + [V(name=f"F6_time{n}", time_n=n) for n in (30, 60, 120)]
    # F7 opposite-channel stop (Turtle exit) at the prior n-bar high/low
    + [V(name=f"F7_chan{n}", chan_n=n) for n in (10, 20)]
    # F8 climax bar: favorable open->close >= k x prior-bar ATR, exit next open
    + [V(name=f"F8_climax{k}", climax_k=k) for k in (2.5, 3.5)]
)
assert len(ROUND1) == 30

ROUND3 = (
    # F9 trend-efficiency fade: in profit >= k x ATR and ER20 < x, exit next open
    [V(name=f"F9_er{k}_x{x}", er_k=k, er_x=x) for k in (3, 6) for x in (0.15, 0.30)]
    # F10 volume climax: favorable bar >= 1.5 x ATR(prev) on volume >= v x SMA20
    + [V(name=f"F10_volx{v}", volx_v=v) for v in (2.5, 4.0)]
)
assert len(ROUND3) == 6

# AMENDMENT 1 (registered before it ran): every full-exit rule of rounds 1
# and 3, with a 30-bar (5-day) same-side stand-aside after it takes profit.
FULL_EXIT = ("tp_k", "ext_z", "rsi_l", "time_n", "climax_k", "er_k", "volx_v")
ROUND4 = [dataclasses.replace(v, name=v.name + "_sa30", cool_n=30)
          for v in ROUND1 + ROUND3
          if any(getattr(v, f) is not None for f in FULL_EXIT)]
assert len(ROUND4) == 22, len(ROUND4)

FIELDS = ("tp_k", "ptp_k", "ptp_f", "lock_k", "lock_m", "be_k", "ext_z",
          "rsi_l", "time_n", "chan_n", "climax_k", "er_k", "er_x", "volx_v")


def family(v):
    return v.name.split("_")[0]


def combine(*vs):
    """Union of the hooks of several variants (each hook keeps its own
    parameters). Raises if two variants set the same hook differently."""
    kw = {}
    for v in vs:
        for f in FIELDS:
            val = getattr(v, f)
            if val is None or (f == "ptp_f" and val == 0.0) or (f == "lock_m" and val == 5.0):
                continue
            if f in kw and kw[f] != val:
                raise ValueError(f"conflict on {f}")
            kw[f] = val
    return V(name="+".join(v.name for v in vs), **kw)


def round2(best_by_family):
    """PREREG 3.2: the best config of each of the top-3 families (ranked by
    criterion A exit-step delta), all pairs plus the triple."""
    top = best_by_family[:3]
    a, b, c = top
    return [combine(a, b), combine(a, c), combine(b, c), combine(a, b, c)]


def placebos(n, rep):
    """PREREG 4: n random-exit rules for repetition `rep`. Hazard q is
    log-uniform on [0.003, 0.08] per bar (expected exit 12..330 bars after
    the fill bar); half close the whole position, half one third / one half."""
    rng = random.Random(1_000_003 * rep + 17)
    out = []
    for j in range(n):
        q = 10 ** rng.uniform(-2.5229, -1.0969)
        f = 1.0 if j % 2 == 0 else rng.choice((1 / 3, 1 / 2))
        out.append(V(name=f"PLC{rep}_{j}", placebo_q=q, placebo_f=f,
                     seed=rng.randrange(1 << 30)))
    return out


def placebos_sa(n, rep):
    """AMENDMENT 1 null draws: full random exits with the same 30-bar
    stand-aside as ROUND4 (log-uniform hazard as above)."""
    rng = random.Random(7_000_003 * rep + 29)
    return [V(name=f"PLCSA{rep}_{j}", placebo_q=10 ** rng.uniform(-2.5229, -1.0969),
              placebo_f=1.0, seed=rng.randrange(1 << 30), cool_n=30)
            for j in range(n)]
