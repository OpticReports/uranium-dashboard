#!/usr/bin/env python3
"""Run the registered crash-stress grid (PREREG.md, 2026-10-07) end to end.

For each scenario (COVID 2020-02-13, 2008-like 2021-11-09, dot-com-like
2017-12-17; 12 months) x K in (0.75, 0.30) x offset in (-28, -14, 0, 14, 28)
days:

  1. splice the BTC and ETH analogue paths onto today's grid (stress.build_spliced,
     same anchor + offset for both, as-of instant pinned to stress.SEED_NOW);
  2. run the carry sleeve (carry_sleeve.simulate_carry) on the ETH path with
     BitMEX 8h funding for the analogue window plus its trailing 30 days (so the
     gate reads a full window from day 1), shifted onto today's grid.
     HEADLINE funding = BitMEX XBTUSD, the proxy for the live HL linear ETH perp
     (review finding, BLOCKING: BitMEX ETHUSD is a QUANTO whose funding is
     structurally positive in every regime - 2022-06 +98.5%/yr while ETH fell
     45%, 2020-03 +69%/yr - so it is a different instrument, not an upper
     bound). The ETHUSD quanto grid is run beside it where its data exists
     (2018-08-02 on) and printed as a labelled second column, never as the
     headline;
  3. feed the sleeve's per-bar value into stress.run_path (BTC book + executor
     guards + engine paper-book halts) WITH the BTC book's own perp funding
     (same XBTUSD series on every held position at each 8h stamp; review
     finding, SERIOUS: a directional cost on a crash path, previously omitted);
     variant A intrabar; at offset 0 also variant B and close-only;
  4. at offset 0: sensitivities - no BTC funding, no engine-book halts, the two
     S3 seam variants (live PENDING snapshot; seam trade dropped), and the
     ETHUSD quanto column;
  5. post-check the carry margin guard against the ACCOUNT's USDC path: the
     BTC book's equity (cash + MTM P&L, what backs the perps) plus the sleeve's
     own net cash flows; recompute liq_px and flag any bar whose ETH close came
     within 15% of it (and the literal 'usdc = equity_btc' variant).

Writes results.json (summaries + offset-0 curves + the honesty box), fig_<scenario>.png
and fig_summary.png next to this file, and prints the table. Research only:
nothing here touches production code or live config.

    python3 run_all.py            # full grid (~3 min)
    python3 run_all.py --charts   # charts + table only, from results.json
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stress                                                   # noqa: E402
import carry_sleeve as cs                                       # noqa: E402
import harness                                                  # noqa: E402
from stress import BAR, DAY, build_spliced, run_path, _date, _day  # noqa: E402

NOW = stress.SEED_NOW                      # pin the seam to the seed's 08:00Z bar
SCENARIOS = [("COVID", "2020-02-13"), ("2008", "2021-11-09"), ("1999", "2017-12-17")]
SCEN_LABEL = {"COVID": "COVID-like", "2008": "2008-like", "1999": "1999/2000-like"}
KS = (0.75, 0.30)
OFFSETS = (-28, -14, 0, 14, 28)
MONTHS = 12
LIVE_CARRY = {"on": True, "qty": 11.096, "entry_px": 2703.9}
CARRY_NOTIONAL = 30_000.0
USDC_BACKING = 70_000.0
PRE_WINDOW_S = 30 * DAY
LIQ_BUFFER = 0.15
FUNDING_FILES = {"ETHUSD": os.path.join(cs.DATA, "funding_bitmex_ETHUSD.csv"),
                 "XBTUSD": os.path.join(cs.DATA, "funding_bitmex_XBTUSD.csv")}
HEADLINE_FUNDING = "XBTUSD"      # proxy for the live HL linear ETH perp AND for HL BTC
QUANTO_FUNDING = "ETHUSD"        # BitMEX quanto: shown beside the headline, labelled
QUANTO_LABEL = "BitMEX ETHUSD quanto - not the live venue's instrument"
CRASH_DEPTH_FRAC = 0.5           # an offset keeps the scenario's crash when its BTC low is at
#                                  least half as deep as the offset-0 low; shallower = "not a
#                                  crash path" (1999 off-28: -31% vs -84%)
KNIFE_EDGE_FRAC = 0.02           # an engine-book halt within 2% of its peak is a knife-edge
RESULTS = os.path.join(HERE, "results.json")
BAL_KEYS = ("91", "182", "273", "365")
BAL_LABEL = {"91": "3m", "182": "6m", "273": "9m", "365": "12m"}
SEAM_SENS = ("pending_live", "drop_seam")


def kkey(K: float) -> str:
    return f"K{K:g}"


def okey(off: int) -> str:
    return f"off{off:+d}"


# --------------------------------------------------------------------------
# funding + carry
# --------------------------------------------------------------------------
_FUND_FIRST: dict[str, int] = {}


def funding_first_stamp(src: str) -> int:
    if src not in _FUND_FIRST:
        _FUND_FIRST[src] = min(cs.load_funding(FUNDING_FILES[src])) // 1000
    return _FUND_FIRST[src]


def funding_covers(src: str, anchor_ts: int) -> bool:
    """True when `src` has stamps from the pre-window (anchor - 30d) on."""
    return funding_first_stamp(src) <= anchor_ts - PRE_WINDOW_S


def funding_for(anchor_ts: int, n_bars: int, t0: int, src: str = HEADLINE_FUNDING,
                force: str | None = None) -> tuple[dict, dict]:
    """BitMEX 8h funding of `src` for [anchor - 30d, last close], shifted onto
    today's grid (t0 - anchor_ts). The default is the HEADLINE source
    (XBTUSD) for every window; `force` is kept for callers that spell the
    source that way. Raises if the source does not cover the window."""
    src = force or src
    lo = anchor_ts - PRE_WINDOW_S
    hi = anchor_ts + n_bars * BAR
    if not funding_covers(src, anchor_ts):
        raise ValueError(f"{src} funding starts {_date(funding_first_stamp(src))}, "
                         f"after the window's pre-window {_date(lo)}")
    raw = cs.load_funding(FUNDING_FILES[src], lo_ms=lo * 1000, hi_ms=hi * 1000)
    shift_ms = (t0 - anchor_ts) * 1000
    fund = {k + shift_ms: v for k, v in raw.items()}
    exp = (hi - lo) // (8 * 3600)
    rates = list(raw.values())
    meta = dict(source=src, n_stamps=len(raw), expected_stamps=int(exp),
                coverage=round(len(raw) / exp, 4), window_lo=_date(lo), window_hi=_date(hi),
                pre_window_days=PRE_WINDOW_S // DAY, shift_days=(t0 - anchor_ts) / DAY,
                mean_ann_pct=round(float(np.mean(rates)) * cs.ANNUALISE * 100.0, 2),
                neg_stamps_pct=round(100.0 * sum(1 for r in rates if r < 0) / len(rates), 1),
                quanto=(src == QUANTO_FUNDING))
    return fund, meta


def btc_funding_from(fund_ms: dict) -> dict[int, float]:
    """{stamp ts (s): rate_8h} for stress.Executor from a funding_for() dict."""
    return {int(k) // 1000: float(v) for k, v in fund_ms.items()}


def run_carry(bars_eth, fund: dict) -> cs.CarryResult:
    eth_closes = {b.ts: b.close for b in bars_eth.path}
    cr = cs.simulate_carry(eth_closes, fund, dict(LIVE_CARRY), notional=CARRY_NOTIONAL,
                           usdc_backing=USDC_BACKING, liq_buffer=LIQ_BUFFER)
    assert cr.ts == [b.ts for b in bars_eth.path]
    return cr


def carry_summary(cr: cs.CarryResult, r: dict | None, eth_closes: list[float]) -> dict:
    idx = {t: i for i, t in enumerate(cr.ts)}
    flips = []
    for T, kind, d in cr.events:
        j = idx[T]
        flips.append(dict(ts=int(d["close_ts"]), date=d["utc"], kind=kind, px=round(d["px"], 2),
                          qty=round(d["qty"], 4), gate_pct=(None if d["mean_ann_pct"] != d["mean_ann_pct"]
                                                            else round(d["mean_ann_pct"], 2)),
                          sleeve_value=round(d["value"], 2),
                          account_equity=(round(r["equity_total"][j], 2) if r else None),
                          note=d.get("note", "")))
    gm = [g for g in cr.gate_mean if g == g]
    n = len(cr.ts)
    liq_on = [x for x in cr.liq_px if x == x]
    return dict(flips=[f for f in flips if f["kind"] in ("gate_on", "gate_off", "margin_guard")],
                resizes=[f for f in flips if f["kind"] == "resize"],
                n_flips=len(cr.flips()),
                n_resizes=sum(1 for e in cr.events if e[1] == "resize"),
                guard_events_internal=sum(1 for e in cr.events if e[1] == "margin_guard"),
                funding_total=round(cr.funding_cum[-1], 2), fees=round(cr.fees_cum[-1], 2),
                final_value=round(cr.value[-1], 2),
                value_at={k: round(cr.value[min(n - 1, int(k) * 6)], 2) for k in BAL_KEYS},
                bars_on_pct=round(100.0 * sum(cr.on) / n, 1),
                gate_first=(round(gm[0], 2) if gm else None),
                gate_min=(round(min(gm), 2) if gm else None),
                gate_max=(round(max(gm), 2) if gm else None),
                liq_min_internal=(round(min(liq_on), 2) if liq_on else None),
                eth_close_max=round(max(eth_closes), 2), eth_close_min=round(min(eth_closes), 2))


def margin_post_check(r: dict, cr: cs.CarryResult, eth_closes: list[float]) -> dict:
    """Recompute the short's liquidation price per bar with the ACCOUNT's USDC:
    equity_btc (cash + MTM P&L of the BTC book) + the sleeve's own net cash
    flows (usdc_eff - 70k). Also the literal 'usdc = equity_btc' reading."""
    eq_btc = r["equity_btc"]
    out = {}
    for label, usdc_fn in (("account", lambda j: eq_btc[j] + (cr.usdc_eff[j] - USDC_BACKING)),
                           ("literal_equity_btc", lambda j: eq_btc[j])):
        worst_ratio, worst_j, min_liq, first_flag = 0.0, None, math.inf, None
        n_on = 0
        for j, on in enumerate(cr.on):
            if not on or cr.qty[j] <= 0:
                continue
            n_on += 1
            liq = cs.liq_px_short(usdc_fn(j), cr.qty[j], cr.entry_px[j])
            ratio = eth_closes[j] / liq if liq > 0 else math.inf
            min_liq = min(min_liq, liq)
            if ratio > worst_ratio:
                worst_ratio, worst_j = ratio, j
            if ratio >= 1.0 - LIQ_BUFFER and first_flag is None:
                first_flag = j
        out[label] = dict(
            flagged=first_flag is not None,
            first_flag_date=(_date(r["ts"][first_flag]) if first_flag is not None else None),
            first_flag_eth_close=(round(eth_closes[first_flag], 2) if first_flag is not None else None),
            first_flag_usdc=(round(usdc_fn(first_flag), 2) if first_flag is not None else None),
            closest_ratio=round(worst_ratio, 4),
            closest_date=(_date(r["ts"][worst_j]) if worst_j is not None else None),
            closest_usdc=(round(usdc_fn(worst_j), 2) if worst_j is not None else None),
            min_liq_px=(round(min_liq, 2) if n_on else None), bars_on=n_on)
    out["rule"] = f"flag when ETH close >= liq_px x (1 - {LIQ_BUFFER}); liq = (usdc/qty + entry)/1.02"
    return out


# --------------------------------------------------------------------------
# run summaries
# --------------------------------------------------------------------------
def summarize(r: dict, cr: cs.CarryResult, eth_closes: list[float], fmeta: dict) -> dict:
    eh = {}
    for leg in stress.LEGS:
        e = r["engine_halts_info"][leg]
        eh[leg] = dict(halted=e["halted"], date=e["halt_date"],
                       paper_equity=(round(e["equity_at_halt"], 2) if e["equity_at_halt"] else None),
                       line_at_halt=e["line_at_halt"], margin_at_halt=e["margin_at_halt"],
                       min_margin=e["min_margin"], min_margin_date=e["min_margin_date"],
                       line_seed=e["line_seed"], min_equity=e["min_equity"],
                       dropped_trades=e["dropped"], paper_equity_end=round(e["equity_end"], 2),
                       paper_peak_end=round(e["peak_end"], 2),
                       account_equity=(round(r["equity_total"][r["ts"].index(e["halt_ts"])], 2)
                                       if e["halted"] else None))
    halts = [dict(kind=h["kind"], date=h["date"], equity=h["equity_after"], line=h["line"],
                  fill_px=h["fill_px"], how=h["how"], relabelled=h.get("relabelled"),
                  rearm_date=(_date(h["rearm_ts"]) if h.get("rearm_ts") else None))
             for h in r["halts"]]
    post = margin_post_check(r, cr, eth_closes)
    bal = lambda d: {k: (d[k]["equity"] if d[k] else None) for k in BAL_KEYS}  # noqa: E731
    return dict(
        name=r["name"], K=r["K"], offset=r["offset_days"], variant=r["dd_variant"],
        intrabar=r["intrabar"], engine_halts=r["engine_halts"], halt_rule=r["halt_rule"],
        daily_loss_pct=r["daily_loss_pct"], seam_variant=r["seam_variant"],
        balances=bal(r["balances"]), balances_btc=bal(r["balances_btc"]),
        balances_bench=bal(r["balances_bench"]),
        balance_365_exact=r["balances"]["365"]["exact"],
        balance_365_shortfall_h=r["balances"]["365"]["shortfall_s"] / 3600.0,
        final_equity=r["final_equity"], max_dd=r["max_dd"], max_dd_intrabar=r["max_dd_intrabar"],
        max_dd_btc_book=r["max_dd_btc_book"], max_dd_bench=r["max_dd_bench"],
        worst_day=dict(date=r["worst_day"]["date"], pct=round(r["worst_day"]["pct"], 4),
                       usd=round(r["worst_day"]["usd"], 2)),
        worst_day_intrabar=dict(date=r["worst_day_intrabar"]["date"],
                                pct=round(r["worst_day_intrabar"]["pct"], 4),
                                usd=round(r["worst_day_intrabar"]["usd"], 2)),
        rail_use=r["rail_use"],
        btc_funding=dict(modelled=r["btc_funding_modelled"], total=r["btc_funding_total"],
                         by_leg=r["btc_funding_by_leg"], stamps=r["btc_funding_stamps"],
                         source=(HEADLINE_FUNDING if r["btc_funding_modelled"] else None)),
        halts=halts, halts_count=len(halts), engine_halts_info=eh,
        n_engine_halts=sum(1 for leg in eh if eh[leg]["halted"]),
        carry=dict(funding_source=fmeta["source"], funding_quanto=fmeta["quanto"],
                   window_mean_ann_pct=fmeta["mean_ann_pct"], **carry_summary(cr, r, eth_closes)),
        margin_check=post,
        fees=r["fees"], n_trades=r["n_trades"], n_entries=r["n_entries"], n_open=r["n_open"],
        hw_end=r["hw_end"], events=[(e[0], _date(e[0]), e[1], e[2], e[3]) for e in r["events"]],
        file=os.path.relpath(r["file"], HERE) if r.get("file") else None)


def path_moves(bars) -> dict:
    c = [b.close for b in bars.path]
    c0 = c[0]
    j_lo = int(np.argmin(c))
    return dict(first_close=round(c0, 2), low=round(min(c), 2), low_pct=round(min(c) / c0 - 1, 4),
                low_day=round(j_lo * BAR / DAY, 1), high_pct=round(max(c) / c0 - 1, 4),
                end_pct=round(c[-1] / c0 - 1, 4), end=round(c[-1], 2))


def dd_curve(start: float, eq: list[float]) -> list[float]:
    p = np.concatenate([[start], np.asarray(eq, dtype=float)])
    peak = np.maximum.accumulate(p)
    return [round(float(x), 5) for x in (p / peak - 1.0)[1:]]


def seam_disclosure(real_btc) -> dict:
    """What the seam does to each live leg, from the CSV itself."""
    full = harness.load_bars("btcusd")
    nxt = next((b for b in full if b.ts == real_btc[-1].ts + BAR), None)
    s4 = dict(entry=stress.SEED_TREND_ENTRY, trail=stress.SEED_TREND_TRAIL,
              real_next_bar=(None if nxt is None else dict(
                  ts=nxt.ts, date=_date(nxt.ts), open=nxt.open, high=nxt.high, low=nxt.low,
                  close=nxt.close, closed_at_run=(nxt.ts + BAR <= NOW))),
              stopped_on_real_path=(nxt is not None and nxt.low < stress.SEED_TREND_TRAIL))
    s4["note"] = ("the live S4 long is stopped on today's REAL path too (the 12:00Z bar's low "
                  f"{nxt.low:,.2f} < trail {stress.SEED_TREND_TRAIL:,.2f}); only the fill level "
                  "(open vs trail) is a splice choice - not a splice artefact"
                  if s4["stopped_on_real_path"] else
                  "the real next bar did not reach the trail; the stop at t0 is a splice effect")
    s3 = dict(csv=dict(state="LONG", entry_price=84_121.28, entry_date="2026-10-07 04:00",
                       why="the 04:00Z bar's low 84,010.77 sits $110 under the 00:00Z-close limit 84,121.28"),
              live=dict(state="PENDING", limit=real_btc[-1].close, signal_date=_date(real_btc[-1].ts),
                        why="the live engine reported PENDING at the 08:00Z close: its feed did not fill that limit"),
              status="OPEN KEY INPUT (P1), narrowed to one datum: the S3 book's 2026-10-07 04:00Z bar LOW as the "
                     "live engine saw it. Its own /bars endpoint shows low 84,010.77, identical to the CSV, yet the "
                     "live book did not fill the 84,121.28 limit - an open ENGINE-SIDE question, not a data "
                     "question; the harness runs the CSV as the headline and the live snapshot as a seam variant",
              variants=dict(csv="engine on the CSV as is (headline)",
                            pending_live="production Book continued from the live snapshot: S3 flat, long limit "
                                         "resting at the 08:00Z close",
                            drop_seam="seam trade removed, every later CSV trade kept (counterfactual, "
                                      "not an engine path)"))
    return dict(s4=s4, s3=s3)


# --------------------------------------------------------------------------
# the grid
# --------------------------------------------------------------------------
def run_grid() -> dict:
    t_start = time.time()
    real_btc = stress.load_closed_bars("btcusd", NOW)
    real_eth = stress.load_closed_bars("ethusd", NOW)
    res = dict(meta=dict(
        generated=_date(time.time()), now_used=NOW, now_used_date=_date(NOW),
        last_closed_bar=_date(real_btc[-1].ts), t0=real_btc[-1].ts + BAR,
        t0_date=_date(real_btc[-1].ts + BAR),
        today_close_btc=real_btc[-1].close, today_close_eth=real_eth[-1].close,
        start_equity=stress.START_EQUITY, carry_start=CARRY_NOTIONAL, usdc_backing=USDC_BACKING,
        live_carry=LIVE_CARRY, Ks=list(KS), offsets=list(OFFSETS), months=MONTHS,
        balance_days=list(stress.BALANCE_DAYS), engine_halts=True, halt_rule="first_cross",
        headline_funding=HEADLINE_FUNDING, quanto_funding=QUANTO_FUNDING, quanto_label=QUANTO_LABEL,
        btc_funding_modelled=True, btc_funding_source=HEADLINE_FUNDING,
        constants=dict(BASE=stress.BASE, LEV=stress.LEV, W_TREND=stress.W_TREND,
                       KELLY_M_CAP=stress.KELLY_M_CAP, MAX_NOTIONAL=stress.MAX_NOTIONAL,
                       MAX_ACCOUNT_LEV=stress.MAX_ACCOUNT_LEV, DD_HALT_PCT=stress.DD_HALT_PCT,
                       DAILY_LOSS_PCT=stress.DAILY_LOSS_PCT, FEE_BPS=stress.FEE_BPS,
                       PAPER_FEE_BPS_SIDE=stress.PAPER_FEE_BPS_SIDE,
                       paper_seed=stress.PAPER_SEED, carry_fee_spot_bps=7.0,
                       carry_fee_perp_bps=4.5, carry_arm=8.0, carry_disarm=5.0,
                       carry_resize_drift=0.25, carry_liq_buffer=LIQ_BUFFER),
        funding_pre_window_days=PRE_WINDOW_S // DAY,
        seam=seam_disclosure(real_btc),
        notes=["funding stamps shifted onto today's grid by (t0 - anchor_ts)",
               "carry value added 1:1 to BTC-book equity before every halt check",
               "all fills at the line / level, no slippage (upper bound, PREREG honesty)",
               f"headline carry funding = BitMEX {HEADLINE_FUNDING} (proxy for the live HL linear ETH perp); "
               f"the {QUANTO_FUNDING} column is the {QUANTO_LABEL}",
               "BTC perp funding on the book's own positions modelled from the same XBTUSD series "
               "(long pays a positive rate at each 8h stamp on the held qty x close)"]),
        scenarios={})
    for scen, anchor in SCENARIOS:
        S = dict(label=SCEN_LABEL[scen], anchor=anchor, runs={}, runs_quanto={}, curves={},
                 sensitivity={}, carry_by_offset={}, paths={})
        res["scenarios"][scen] = S
        for off in OFFSETS:
            bars_btc = build_spliced("btcusd", anchor, MONTHS, off, now=NOW)
            bars_eth = build_spliced("ethusd", anchor, MONTHS, off, now=NOW)
            assert bars_btc.t0 == bars_eth.t0 and len(bars_btc.path) == len(bars_eth.path), \
                "BTC/ETH path grids differ"
            n = len(bars_btc.path)
            fund_h, fmeta_h = funding_for(bars_btc.anchor_ts, n, bars_btc.t0, HEADLINE_FUNDING)
            bf = btc_funding_from(fund_h)
            cr = run_carry(bars_eth, fund_h)
            quanto_ok = funding_covers(QUANTO_FUNDING, bars_btc.anchor_ts)
            if quanto_ok:
                fund_q, fmeta_q = funding_for(bars_btc.anchor_ts, n, bars_btc.t0, QUANTO_FUNDING)
                cr_q = run_carry(bars_eth, fund_q)
            else:
                fund_q, fmeta_q, cr_q = None, None, None
            eth_closes = [b.close for b in bars_eth.path]
            S["paths"][okey(off)] = dict(
                anchor_date=_date(bars_btc.anchor_ts), window_end=_date(bars_btc.anchor_ts + n * BAR),
                n_bars=n, btc_scale=bars_btc.scale, eth_scale=bars_eth.scale,
                btc=path_moves(bars_btc), eth=path_moves(bars_eth),
                funding=fmeta_h, funding_quanto=fmeta_q)
            S["carry_by_offset"][okey(off)] = dict(
                headline=dict(funding_source=fmeta_h["source"], **carry_summary(cr, None, eth_closes)),
                quanto=(dict(funding_source=fmeta_q["source"], **carry_summary(cr_q, None, eth_closes))
                        if cr_q is not None else None))
            variants = [("A", True)]
            if off == 0:
                variants += [("B", True), ("A", False)]
            common = dict(offset_days=off, anchor_input=scen, anchor_date_input=anchor, months=MONTHS)
            for K in KS:
                for var, intra in variants:
                    r = run_path(scen, bars_btc, K, carry_value=cr.value, dd_variant=var,
                                 intrabar=intra, engine_halts=True, halt_rule="first_cross",
                                 save=True, btc_funding=bf,
                                 extra=dict(common, carry_funding_source=fmeta_h["source"]))
                    summ = summarize(r, cr, eth_closes, fmeta_h)
                    tag = okey(off) + ("" if (var == "A" and intra) else
                                       ("_B" if var == "B" else "_close"))
                    S["runs"].setdefault(kkey(K), {})[tag] = summ
                    print(f"  {scen:5s} K{K:<4g} {tag:12s} final {r['final_equity']:>9,.0f}  "
                          f"maxDD {r['max_dd']:7.2%}  halts {len(r['halts'])}  "
                          f"eng.halts {summ['n_engine_halts']}  carry flips {summ['carry']['n_flips']} "
                          f"({fmeta_h['source']})  BTC funding {r['btc_funding_total']:+,.0f}  "
                          f"marginflag {summ['margin_check']['account']['flagged']}", flush=True)
                    if off == 0 and var == "A" and intra:
                        S["curves"][kkey(K)] = dict(
                            ts=r["ts"], total=r["equity_total"], btc=r["equity_btc"],
                            carry=r["carry_value"], hold=r["bench_hold_btc"],
                            worst_intrabar=r["worst_intrabar_equity"],
                            eth_close=[round(x, 2) for x in eth_closes],
                            btc_close=[round(c, 2) for _, c in r["spliced_closes"]],
                            dd_total=dd_curve(stress.START_EQUITY, r["equity_total"]),
                            dd_hold=dd_curve(stress.START_EQUITY, r["bench_hold_btc"]),
                            dd_carry=dd_curve(CARRY_NOTIONAL, r["carry_value"]),
                            carry_on=[bool(x) for x in cr.on],
                            btc_funding_cum=r["btc_funding_cum"],
                            # the DRAWDOWN line each bar was tested on, in equity
                            # units: worst intrabar equity minus its margin to the
                            # line = HW (as tested on the bar) - 30% of base
                            dd_halt_line=[round(w - m, 2) for w, m in
                                          zip(r["worst_intrabar_equity"], r["margin_drawdown"])],
                            carry_quanto=([round(float(v), 2) for v in cr_q.value]
                                          if cr_q is not None else None))
                    if cr_q is not None and var == "A" and intra:
                        rq = run_path(scen, bars_btc, K, carry_value=cr_q.value, save=True,
                                      btc_funding=bf,
                                      extra=dict(common, carry_funding_source=fmeta_q["source"]))
                        S["runs_quanto"].setdefault(kkey(K), {})[okey(off)] = \
                            summarize(rq, cr_q, eth_closes, fmeta_q)
                        if off == 0:
                            S["curves"][kkey(K)]["total_quanto"] = rq["equity_total"]
            if off == 0:
                sens = {}
                for K in KS:
                    r = run_path(scen, bars_btc, K, carry_value=cr.value, save=True,
                                 btc_funding=None,
                                 extra=dict(common, carry_funding_source=fmeta_h["source"]))
                    sens.setdefault("no_btc_funding", {})[kkey(K)] = summarize(r, cr, eth_closes, fmeta_h)
                    print(f"  {scen:5s} K{K:<4g} off+0 no-BTC-funding sensitivity: 12m "
                          f"{r['balances']['365']['equity']:,.0f}", flush=True)
                    for sv in SEAM_SENS:
                        r = run_path(scen, bars_btc, K, carry_value=cr.value, save=True,
                                     btc_funding=bf, seam_variant=sv,
                                     extra=dict(common, carry_funding_source=fmeta_h["source"]))
                        sens.setdefault("seam_" + sv, {})[kkey(K)] = summarize(r, cr, eth_closes, fmeta_h)
                        e = r["engine_halts_info"]["pullback"]
                        print(f"  {scen:5s} K{K:<4g} off+0 seam {sv:13s}: 12m "
                              f"{r['balances']['365']['equity']:,.0f}  maxDD {r['max_dd']:.2%}  "
                              f"S3 halt {e['halt_date']} (margin {e['min_margin']:+,.0f})", flush=True)
                r = run_path(scen, bars_btc, 0.75, carry_value=cr.value, engine_halts=False,
                             save=True, btc_funding=bf,
                             extra=dict(common, carry_funding_source=fmeta_h["source"]))
                sens["no_engine_book_halts"] = summarize(r, cr, eth_closes, fmeta_h)
                sens["no_engine_book_halts"]["curve_total"] = r["equity_total"]
                print(f"  {scen:5s} K0.75 off+0 no-engine-halts diagnostic: final "
                      f"{r['final_equity']:,.0f}  maxDD {r['max_dd']:.2%}", flush=True)
                S["sensitivity"] = sens
                # seam range at the headline offset
                S["seam_range"] = {}
                for K in KS:
                    vals = {"csv": S["runs"][kkey(K)]["off+0"]["balances"]["365"]}
                    for sv in SEAM_SENS:
                        vals[sv] = sens["seam_" + sv][kkey(K)]["balances"]["365"]
                    S["seam_range"][kkey(K)] = dict(by_variant=vals, min=min(vals.values()),
                                                    max=max(vals.values()),
                                                    s3_halt={v: S["runs"][kkey(K)]["off+0"]["engine_halts_info"]["pullback"]["date"]
                                                             if v == "csv" else
                                                             sens["seam_" + v][kkey(K)]["engine_halts_info"]["pullback"]["date"]
                                                             for v in vals})
        # offset range per K (headline; and without the non-crash offsets)
        S["range_12m"] = {}
        S["range_12m_quanto"] = {}
        low0 = S["paths"]["off+0"]["btc"]["low_pct"]
        for o in OFFSETS:
            p = S["paths"][okey(o)]
            p["crash_path"] = p["btc"]["low_pct"] <= CRASH_DEPTH_FRAC * low0
        excluded = {okey(o): (f"BTC low only {S['paths'][okey(o)]['btc']['low_pct']:+.0%} vs {low0:+.0%} at "
                              f"offset 0, 12m {S['paths'][okey(o)]['btc']['end_pct']:+.0%}: not a crash path")
                    for o in OFFSETS if not S["paths"][okey(o)]["crash_path"]}
        for K in KS:
            vals = {okey(o): S["runs"][kkey(K)][okey(o)]["balances"]["365"] for o in OFFSETS}
            dd = {okey(o): S["runs"][kkey(K)][okey(o)]["max_dd"] for o in OFFSETS}
            crash = {k: v for k, v in vals.items() if k not in excluded}
            S["range_12m"][kkey(K)] = dict(
                min=min(vals.values()), min_offset=min(vals, key=vals.get),
                max=max(vals.values()), max_offset=max(vals, key=vals.get), by_offset=vals,
                max_dd_by_offset=dd, excluded=excluded,
                crash_only=dict(min=min(crash.values()), min_offset=min(crash, key=crash.get),
                                max=max(crash.values()), max_offset=max(crash, key=crash.get),
                                max_dd_min=min(dd[k] for k in crash), max_dd_max=max(dd[k] for k in crash)))
            if S["runs_quanto"]:
                vq = {okey(o): S["runs_quanto"][kkey(K)][okey(o)]["balances"]["365"] for o in OFFSETS}
                dq = {okey(o): S["runs_quanto"][kkey(K)][okey(o)]["max_dd"] for o in OFFSETS}
                S["range_12m_quanto"][kkey(K)] = dict(min=min(vq.values()), max=max(vq.values()),
                                                      by_offset=vq, max_dd_by_offset=dq)
    res["meta"]["elapsed_s"] = round(time.time() - t_start, 1)
    res["honesty"] = honesty_lines(res)
    return res


# --------------------------------------------------------------------------
# honesty box
# --------------------------------------------------------------------------
HONESTY_STATIC = [
    "Mark-to-market basis; every fill at the line / the engine level with no slippage; a stress "
    "test of three spliced paths is not a distribution and the splice is a construction, not a "
    "forecast. Every number is an upper bound on what the live book would do.",
    "Fit windows: the pullback (S3) was fitted on 2024-26, so it is out-of-sample on all three "
    "analogues. The trend leg (S4) was fitted on 2013-2021 (RESEARCH_S4.md: TRAIN 2013-2021, "
    "VALIDATE 2022-2024H1): the COVID (2020) and 1999-like (2017-18) analogues sit inside its fit "
    "window; the 2008-like window (2021-11-09..2022-11-09) is 10 of 12 months inside its "
    "VALIDATION window, quasi-out-of-sample. (PREREG.md placed the 2008 analogue inside the fit "
    "window; corrected in ADDENDUM.md.)",
    f"Carry funding: no linear-ETH perp funding history for 2020 or 2022 was reachable (Hyperliquid "
    f"launched in 2023). BitMEX ETHUSD is a QUANTO contract whose funding is structurally positive "
    f"in every regime (2022-06 +98.5%/yr while ETH fell 45%, 2022 full year +38.6%, 2020-03 "
    f"+69%/yr; XBTUSD in the same months -6.2% / -3.4% / -54%), so it is a different instrument, "
    f"not an upper bound. HEADLINE = BitMEX {HEADLINE_FUNDING} as the proxy for the live HL linear "
    f"ETH perp (its funding turns negative in a crash); the {QUANTO_FUNDING} column is printed beside "
    f"it, labelled '{QUANTO_LABEL}'.",
    "BTC perp funding on the book's own positions IS modelled (review finding): BitMEX XBTUSD 8h "
    "rates of the analogue window on every held position at each stamp, as the proxy for HL BTC "
    "(hourly, venue-specific). Funding follows the trend, so the trend leg pays on both sides "
    "(1999: shorts held through stamps averaging -31.6%/yr, longs through +27.8%/yr).",
    "High-water ratchet: the drawdown line's high-water ratchets on a bar's favourable extreme "
    "BEFORE the same bar's adverse extreme is tested (stress.py step 3), so a high that may print "
    "after the low raises the line against that low. Conservative (toward more halts; none fires "
    "either way); hw_end is therefore the intrabar high-water (the verifier measured it on the "
    "pre-review quanto-funded COVID K0.75 path: 139,255 vs 138,714 from closes; drawdown margin "
    "9,681 vs 12,089).",
    "Variant B ('Casey resumes after 7 days') assumes the re-anchor: when equity is still below "
    "the drawdown line at the resume, the emulation applies /resume?reanchor=1 semantics (a plain "
    "/resume is refused while the breach is live, mirror.py L2026-2057), i.e. HW and day_start are "
    "moved to equity. Never exercised: no DRAWDOWN halt fires in any run.",
    "Executor mechanics NOT modelled, each favouring the harness: (a) HALT_CONFIRM_POLLS = 3 "
    "(mirror.py L424, ~60 s debounce at 20 s polls): the harness halts on any intrabar touch and "
    "fills at the line, earlier and better than a live fill in a cascade (0 halts in every run, so "
    "unexercised); (b) pullback entries are post_only limits (L2770): a limit that would cross is "
    "rejected, while the harness fills every engine limit at the engine price (4 of 4 crossed "
    "live); (c) stop-market slippage in a cascade (2020-03-12 4h ranges of 10-15%) and HL "
    "mark-price triggers vs Bitstamp last: not modelled; (d) _reconcile_transfers (L1688-1727) "
    "treats any >= $200 flat-book equity move with no BTC fills as a transfer and shifts "
    "HW/day_start - the sleeve's funding, flip fees and spot/perp basis can trigger it while the "
    "BTC book is flat (no effect here: no halts).",
    "Seam: a real discontinuity in volume regime (20-bar mean volume 211 BTC before the seam vs "
    "x5.3 / x1.8 / x13.8 on the first 20 path bars of COVID / 2008 / 1999), so the pullback's "
    "volume filter passes trivially for ~3 days; tested by rescaling the analogue volume to "
    "today's level: COVID and 2008 identical to the cent, 1999 12m -0.5k (< 0.5k effect).",
    "S4 at t0: the live S4 long (80,702.77, trail 83,274.67) is stopped at the first path bar in "
    "every scenario. That is what the live book faces today, not a splice artefact: the real "
    "2026-10-07 12:00Z bar (unclosed at run time) printed a low of 82,733.94 under the trail. Only "
    "the fill level (open vs trail) is a splice choice (seam round trip -29 COVID/2008, -419 1999).",
    "The 'no DRAWDOWN halt' result does not depend on the carry sleeve: the 2.5/5-ATR engine stops "
    "keep the book above HW - 30k with or without it. The rail's closest approach is quoted on ONE "
    "basis only - the harness's own intrabar reading, in the computed DRAWDOWN-rail line below; the "
    "earlier mixed-basis margins ($5.8k no-carry / $7.0k pre-funding) are withdrawn. The guards did "
    "not fire; the stops did the work.",
    "Carry sleeve: price P&L of the pair is zero by construction (spot and perp marked at one "
    "price; basis not modelled); the margin guard is post-checked against the account's USDC path.",
]


def honesty_lines(res: dict) -> list[str]:
    """Static caveats + the computed ones (S3 seam / knife-edge, 12m column,
    non-crash offsets, daily-rail consumption)."""
    L = list(HONESTY_STATIC)
    seam = res["meta"]["seam"]["s3"]
    peak = stress.PAPER_SEED["pullback"]["peak"]
    parts = []
    for scen, _ in SCENARIOS:
        S = res["scenarios"][scen]
        for K in KS:
            sr = S["seam_range"][kkey(K)]
            e = S["runs"][kkey(K)]["off+0"]["engine_halts_info"]["pullback"]
            if e["halted"]:
                frac = abs(e["margin_at_halt"]) / peak
                how = ("a KNIFE-EDGE" if frac < KNIFE_EDGE_FRAC else "firm")
                tail = (f"; S3 halt {e['date'][5:10]} is {how}: paper equity {e['paper_equity']:,.0f} vs line "
                        f"{e['line_at_halt']:,.0f} ({e['margin_at_halt']:+,.0f}, {frac:.1%} of the {peak:,.0f} peak)")
            else:
                tail = f"; S3 closest to its line {e['min_margin']:+,.0f}"
            parts.append(f"{SCEN_LABEL[scen]} K{K:g}: csv {sr['by_variant']['csv']:,.0f} / live-pending "
                         f"{sr['by_variant']['pending_live']:,.0f} / seam-dropped {sr['by_variant']['drop_seam']:,.0f}"
                         + tail)
    L.append("S3 seam - " + seam["status"] + ". 12m sensitivity at offset 0 (headline funding): "
             + "; ".join(parts) + ". The improvement-candidate question on the S3 paper-book halt "
             "cannot be settled on this path: the COVID halt rides on sub-1% of paper equity.")
    b365 = {s: res["scenarios"][s]["runs"]["K0.75"]["off+0"] for s, _ in SCENARIOS}
    exact = [SCEN_LABEL[s] for s in b365 if b365[s]["balance_365_exact"]]
    after = [SCEN_LABEL[s] for s in b365
             if not b365[s]["balance_365_exact"] and b365[s]["balance_365_shortfall_h"] < 0]
    before = [f"{SCEN_LABEL[s]} ({b365[s]['balance_365_shortfall_h']:.0f}h before)" for s in b365
              if not b365[s]["balance_365_exact"] and b365[s]["balance_365_shortfall_h"] > 0]
    L.append("12m column: exactness is judged on the bar's CLOSE timestamp (close == t0 + 365 d). "
             + (f"For {', '.join(exact)} the 365-day balance IS the exact day-365 close (365-day analogue "
                f"windows, 2,190 bars: the last path bar closes on the instant). " if exact else "")
             + (f"For {', '.join(after)} it is the close of the bar OPENING on the day-365 instant, i.e. "
                f"one bar (4h) after it (the COVID window spans a leap year, 2,196 bars). " if after else "")
             + (f"For {', '.join(before)} the path ends before the instant. " if before else "")
             + "The 3m/6m/9m columns are likewise the close of the bar opening on day 91/182/273, 4h after "
             "the instant, in every scenario. No number moves; a 12m cell that is not the exact close is "
             "labelled 12m*. (The review's '4h short of day 365' reading judged exactness on the bar's "
             "open; corrected here.)")
    for scen, _ in SCENARIOS:
        rg = res["scenarios"][scen]["range_12m"]["K0.75"]
        for k, why in rg["excluded"].items():
            run = res["scenarios"][scen]["runs"]["K0.75"][k]
            s3 = run["engine_halts_info"]["pullback"]
            role = (f"it sets the K0.75 12m minimum ({rg['by_offset'][k]:,.0f})" if k == rg["min_offset"]
                    else f"its K0.75 12m is {rg['by_offset'][k]:,.0f}")
            role += (f" and carries an S3 paper-book halt on {s3['date'][5:10]}" if s3["halted"] else "")
            L.append(f"{SCEN_LABEL[scen]} {k} is not a crash path ({why}; rule: BTC low shallower than "
                     f"{CRASH_DEPTH_FRAC:.0%} of the offset-0 low); {role}. The range without it is "
                     f"{rg['crash_only']['min']:,.0f}..{rg['crash_only']['max']:,.0f}.")
    # daily-rail consumption on the worst intrabar day, across every offset
    for K in KS:
        worst = max(((res["scenarios"][s]["runs"][kkey(K)][okey(o)]["rail_use"]["daily_loss"], s, o)
                     for s, _ in SCENARIOS for o in OFFSETS), key=lambda t: t[0]["used_pct"])
        ru, s, o = worst
        L.append(f"Daily-loss rail at K{K:g} ({ru['budget']:,.0f}): up to {ru['used_pct']:.0%} consumed on "
                 f"the worst intrabar day ({SCEN_LABEL[s]} {okey(o)}, {ru['date']}, closest approach "
                 f"{ru['min_margin']:,.0f}) - what mirror._breach_for would have read at a 20 s poll. "
                 "No line was crossed.")
    # DRAWDOWN-rail consumption on ONE basis - the harness's own intrabar reading
    # (re-verification, SERIOUS: the earlier text quoted mixed-basis margins)
    fmt = lambda r: f"{r['min_margin']:,.0f} ({r['used_pct']:.0%})"              # noqa: E731
    for K in KS:
        cands = [(res["scenarios"][s]["runs"][kkey(K)][okey(o)]["rail_use"]["drawdown"], s, o)
                 for s, _ in SCENARIOS for o in OFFSETS]
        ru, s, o = max(cands, key=lambda t: t[0]["used_pct"])
        S = res["scenarios"][s]
        nf = S["sensitivity"]["no_btc_funding"][kkey(K)]["rail_use"]["drawdown"]
        ds = S["sensitivity"]["seam_drop_seam"][kkey(K)]["rail_use"]["drawdown"]
        ru2, o2 = max(((S["runs"][kkey(K)][okey(x)]["rail_use"]["drawdown"], x) for x in OFFSETS if x != o),
                      key=lambda t: t[0]["used_pct"])
        L.append(f"DRAWDOWN rail at K{K:g} ({ru['budget']:,.0f}), one basis - the harness's own intrabar reading: "
                 f"closest approach to the DRAWDOWN line {ru['min_margin']:,.0f} of {ru['budget']:,.0f} "
                 f"({ru['used_pct']:.0%} used) on {ru['date']} at {SCEN_LABEL[s]} K{K:g} {okey(o)} with BTC "
                 f"funding; {fmt(nf)} without BTC funding; {fmt(ds)} with the seam trade dropped"
                 + ("" if o == 0 else " (both at offset 0)")
                 + f"; {fmt(ru2)} at {okey(o2)}. The 2.5/5-ATR engine stops keep the book above the line "
                 "with or without the carry sleeve. No line was crossed.")
    return L


# --------------------------------------------------------------------------
# table
# --------------------------------------------------------------------------
def table_lines(res: dict) -> list[str]:
    L = []
    hdr = (f"{'scenario':<15}|{'K':>5} |{'3m':>8} |{'6m':>8} |{'9m':>8} |{'12m*':>8} |{'maxDD':>7} |"
           f"{'worst day c2c':>14} |{'intrabar':>9} |{'daily rail':>10} |{'DD rail (margin, date)':>24} |{'halts':>5} |"
           f"{'eng.halts (margin)':>28} |{'carry flips':>11} |{'BTC fund':>8} |{'hold-BTC 12m':>12}")
    L.append("HEADLINE: offset 0, variant A (DRAWDOWN stays flat), intrabar halt checks, start 100,000; "
             f"carry funded by BitMEX {HEADLINE_FUNDING} (proxy for the live HL linear ETH perp); "
             "BTC perp funding on the book's positions modelled (same series)")
    L.append(hdr)
    L.append("-" * len(hdr))
    for scen, _ in SCENARIOS:
        S = res["scenarios"][scen]
        for K in KS:
            s = S["runs"][kkey(K)]["off+0"]
            b = s["balances"]
            halts = ",".join(f"{h['kind'][:2]}@{h['date'][5:10]}" for h in s["halts"]) or "none"
            eh_cells = []
            for leg, e in s["engine_halts_info"].items():
                if e["halted"]:
                    knife = abs(e["margin_at_halt"]) < KNIFE_EDGE_FRAC * stress.PAPER_SEED[leg]["peak"]
                    eh_cells.append(f"{'S3' if leg == 'pullback' else 'S4'}@{e['date'][5:10]} "
                                    f"({e['margin_at_halt'] / 1e3:+.1f}k{', KNIFE-EDGE' if knife else ''})")
            eh = ",".join(eh_cells) or "none"
            dd = s["rail_use"]["drawdown"]
            ddc = f"{dd['used_pct']:.0%} ({dd['min_margin']:,.0f}, {dd['date'][5:10]})"
            star = "" if s["balance_365_exact"] else "*"
            L.append(f"{S['label']:<15}|{K:>5g} |{b['91']:>8,.0f} |{b['182']:>8,.0f} |{b['273']:>8,.0f} |"
                     f"{b['365']:>7,.0f}{star:1s} |{s['max_dd']:>7.1%} |{s['worst_day']['usd']:>+14,.0f} |"
                     f"{s['worst_day_intrabar']['usd']:>+9,.0f} |{s['rail_use']['daily_loss']['used_pct']:>10.0%} |"
                     f"{ddc:>24} |{halts:>5} |{eh:>28} |{s['carry']['n_flips']:>11d} |{s['btc_funding']['total']:>+8,.0f} |"
                     f"{s['balances_bench']['365']:>12,.0f}")
    ex = {SCEN_LABEL[s]: res["scenarios"][s]["runs"]["K0.75"]["off+0"] for s, _ in SCENARIOS}
    exact_names = [n for n, s in ex.items() if s["balance_365_exact"]]
    star_names = [f"{n} ({-s['balance_365_shortfall_h']:+.0f}h)" for n, s in ex.items() if not s["balance_365_exact"]]
    L.append("  12m*: exactness judged on the bar's CLOSE. Exact day-365 close: " + (", ".join(exact_names) or "none")
             + " (365-day windows, 2,190 bars: the last path bar closes ON day 365). Labelled *: "
             + (", ".join(star_names) or "none") + " (leap-year window, 2,196 bars: the bar opening on day 365, "
             "closing 4h after it). The 3m/6m/9m columns are the close 4h after day 91/182/273 in every scenario.")
    L.append("  worst day: close-to-close vs the executor's intrabar reading (bar's worst equity vs the day_start in force); "
             "daily rail = share of the daily-loss budget (15% of base at K0.75, 6% at K0.30) consumed on that day; "
             f"DD rail = share of the {stress.DD_HALT_PCT * stress.BASE:,.0f} DRAWDOWN budget (HW - 30% of base) consumed "
             "at the worst intrabar reading (min margin to the line, date).")
    peak_s3 = stress.PAPER_SEED["pullback"]["peak"]
    L.append("  eng.halts (margin): the engine's own paper-book halt and how far the paper book crossed its line "
             f"(-30% of the S3 book's {peak_s3:,.0f} peak = {(1 - stress.DD_HALT_PCT) * peak_s3:,.0f}); KNIFE-EDGE = crossed "
             f"by less than {KNIFE_EDGE_FRAC:.0%} of that peak ({KNIFE_EDGE_FRAC * peak_s3:,.0f} for S3): a property of the "
             "splice, not of the path.")
    L.append("")
    L.append(f"BitMEX {QUANTO_FUNDING} quanto column ({QUANTO_LABEL}), same cells, side by side with the headline:")
    hq = (f"{'scenario':<15}|{'K':>5} |{'12m headline':>13} |{'12m quanto':>11} |{'maxDD headline':>14} |"
          f"{'maxDD quanto':>12} |{'carry 12m headline':>18} |{'carry 12m quanto':>16} |{'flips h/q':>9}")
    L.append(hq)
    L.append("-" * len(hq))
    for scen, _ in SCENARIOS:
        S = res["scenarios"][scen]
        for K in KS:
            s = S["runs"][kkey(K)]["off+0"]
            q = S["runs_quanto"].get(kkey(K), {}).get("off+0")
            if q is None:
                L.append(f"{S['label']:<15}|{K:>5g} |{s['balances']['365']:>13,.0f} |{'n/a':>11} |{s['max_dd']:>14.1%} |"
                         f"{'n/a':>12} |{s['carry']['final_value']:>18,.0f} |{'n/a':>16} |{s['carry']['n_flips']:>4d}/-   "
                         f"  ({QUANTO_FUNDING} data starts 2018-08-02: the 1999 window has no quanto series)")
            else:
                L.append(f"{S['label']:<15}|{K:>5g} |{s['balances']['365']:>13,.0f} |{q['balances']['365']:>11,.0f} |"
                         f"{s['max_dd']:>14.1%} |{q['max_dd']:>12.1%} |{s['carry']['final_value']:>18,.0f} |"
                         f"{q['carry']['final_value']:>16,.0f} |{s['carry']['n_flips']:>4d}/{q['carry']['n_flips']:<4d}")
    L.append("")
    L.append("S3 seam sensitivity at offset 0 (12m balance; S3 paper-book halt date): the CSV fills the S3 long limit "
             "84,121.28 on the 04:00Z bar (low 84,010.77 - the live engine's own /bars shows the same low), yet the live "
             "book reported PENDING - open ENGINE-SIDE question (P1), not a data question:")
    for scen, _ in SCENARIOS:
        S = res["scenarios"][scen]
        for K in KS:
            sr = S["seam_range"][kkey(K)]
            v, h = sr["by_variant"], sr["s3_halt"]
            L.append(f"  {S['label']:<15} K {K:<5g} csv {v['csv']:>9,.0f} (S3 {h['csv'] or 'none':16s})  "
                     f"live-pending {v['pending_live']:>9,.0f} (S3 {h['pending_live'] or 'none':16s})  "
                     f"seam-dropped {v['drop_seam']:>9,.0f} (S3 {h['drop_seam'] or 'none':16s})  "
                     f"range {sr['min']:,.0f}..{sr['max']:,.0f}")
    L.append("")
    L.append("12-month balance across start offsets (-28,-14,0,+14,+28 days), headline funding, variant A intrabar:")
    for scen, _ in SCENARIOS:
        S = res["scenarios"][scen]
        for K in KS:
            rg = S["range_12m"][kkey(K)]
            dd = rg["max_dd_by_offset"]
            line = (f"  {S['label']:<15} K {K:<5g} 12m min {rg['min']:>9,.0f} ({rg['min_offset']})  "
                    f"max {rg['max']:>9,.0f} ({rg['max_offset']})   maxDD range "
                    f"{min(dd.values()):.1%} .. {max(dd.values()):.1%}")
            if rg["excluded"]:
                c = rg["crash_only"]
                line += (f"   | crash paths only (excl. {', '.join(rg['excluded'])}): "
                         f"{c['min']:,.0f}..{c['max']:,.0f}, maxDD {c['max_dd_min']:.1%} .. {c['max_dd_max']:.1%}")
            L.append(line)
            rq = S["range_12m_quanto"].get(kkey(K))
            if rq:
                L.append(f"  {'':<15}   {'':<5}   quanto column: 12m {rq['min']:,.0f}..{rq['max']:,.0f}, "
                         f"maxDD {min(rq['max_dd_by_offset'].values()):.1%} .. {max(rq['max_dd_by_offset'].values()):.1%}")
    L.append("")
    L.append("BTC perp funding on the book's positions (offset 0, headline): total (pullback / trend), and the 12m balance without it:")
    for scen, _ in SCENARIOS:
        S = res["scenarios"][scen]
        for K in KS:
            s = S["runs"][kkey(K)]["off+0"]
            nf = S["sensitivity"]["no_btc_funding"][kkey(K)]
            f = s["btc_funding"]
            L.append(f"  {S['label']:<15} K {K:<5g} funding {f['total']:>+8,.0f} (pullback {f['by_leg']['pullback']:>+7,.0f} / "
                     f"trend {f['by_leg']['trend']:>+7,.0f}; {f['stamps']} position-stamps)   12m with {s['balances']['365']:,.0f} "
                     f"/ without {nf['balances']['365']:,.0f}")
    return L


# --------------------------------------------------------------------------
# charts
# --------------------------------------------------------------------------
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
C_K75, C_K30, C_HOLD, C_CARRY, C_CASH = "#2a78d6", "#4a3aa7", "#eb6834", "#1baf7a", "#8a8884"


def usd(x: float, _pos=None) -> str:
    """Plain-string dollar label; the $ is escaped so mathtext never sees it."""
    if abs(x) >= 1_000_000:
        return r"\$" + f"{x / 1e6:.1f}M"
    if abs(x) >= 1000:
        return r"\$" + f"{x / 1e3:.0f}k"
    return r"\$" + f"{x:.0f}"


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.ticker import FuncFormatter, FixedLocator, NullLocator, PercentFormatter
    plt.rcParams.update({
        "text.usetex": False, "font.family": "DejaVu Sans", "font.size": 10,
        "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
        "ytick.color": INK2, "text.color": INK, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.8, "grid.linestyle": "-", "axes.spines.top": False,
        "axes.spines.right": False, "legend.frameon": False, "axes.titlecolor": INK,
        "axes.titleweight": "semibold", "axes.titlesize": 12,
        "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9,
    })
    return plt, mdates, FuncFormatter, FixedLocator, NullLocator, PercentFormatter


def _dates(ts) -> np.ndarray:
    """Epoch seconds -> matplotlib date numbers (UTC)."""
    import matplotlib.dates as mdates
    from datetime import datetime, timezone
    arr = np.atleast_1d(np.asarray(ts, dtype=float))
    return mdates.date2num([datetime.fromtimestamp(float(t), tz=timezone.utc) for t in arr])


def _style_axes(ax, mdates):
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    ax.tick_params(length=0)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%y"))


def _log_ticks(ax, lo: float, hi: float, FixedLocator, NullLocator, FuncFormatter):
    cand = [10e3, 15e3, 20e3, 30e3, 40e3, 50e3, 70e3, 100e3, 150e3, 200e3, 300e3, 400e3,
            500e3, 700e3, 1e6]
    ticks = [t for t in cand if lo * 0.98 <= t <= hi * 1.02]
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(usd))
    ax.set_ylim(lo, hi)


def _spread(vals: list[float], min_gap: float, lo: float, hi: float) -> list[float]:
    """Push label positions apart (in whatever units) by at least min_gap,
    keeping the group within [lo, hi]."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = list(vals)
    for a, b in zip(order, order[1:]):
        if out[b] - out[a] < min_gap:
            out[b] = out[a] + min_gap
    over = out[order[-1]] - hi
    if over > 0:
        for i in order:
            out[i] -= over
    for a, b in zip(order, order[1:]):            # second pass after the shift
        if out[b] - out[a] < min_gap:
            out[b] = out[a] + min_gap
    return out


def _end_labels(ax, series: list[tuple], log: bool, min_gap_frac: float = 0.055):
    """Direct end labels (value + name) at the right edge, collision-spread,
    in text ink with a short leader in the series colour."""
    xs = [s[0][-1] for s in series]
    ys = [s[1][-1] for s in series]
    y0, y1 = ax.get_ylim()
    if log:
        f, finv = np.log10, lambda v: 10 ** v
    else:
        f, finv = (lambda v: v), (lambda v: v)
    rng = f(y1) - f(y0)
    pos = _spread([f(y) for y in ys], min_gap_frac * rng, f(y0) + 0.02 * rng, f(y1) - 0.02 * rng)
    x_right = max(xs)
    for (x, y, name, col), p in zip(series, pos):
        yl = finv(p)
        ax.annotate(f"{name}  {usd(y[-1])}", xy=(x[-1], y[-1]), xytext=(x_right + 4, yl),
                    textcoords="data", fontsize=8.5, color=INK2, va="center", ha="left",
                    arrowprops=dict(arrowstyle="-", color=col, lw=0.8, shrinkA=0, shrinkB=2),
                    annotation_clip=False)


def _event_marks(ax, curves: dict, S: dict, log: bool):
    """Executor halts (triangles) and engine-book halts (x) with short labels."""
    import matplotlib.dates as mdates
    y0, y1 = ax.get_ylim()
    f = np.log10 if log else (lambda v: v)
    finv = (lambda v: 10 ** v) if log else (lambda v: v)
    rng = f(y1) - f(y0)
    labels = []                                  # (x, y, text, marker, colour)
    seen_eng = set()
    for K in KS:
        s = S["runs"][kkey(K)]["off+0"]
        c = curves[kkey(K)]
        ts = np.asarray(c["ts"])
        for h in s["halts"]:
            j = int(np.argmin(np.abs(ts - _ts_of_date(h["date"]))))
            labels.append((ts[j], c["total"][j], f"{'DD' if h['kind'] == 'DRAWDOWN' else 'daily-loss'} halt "
                           f"K{K:g} {h['date'][5:10]}", "v", C_K75 if K == 0.75 else C_K30))
        for leg, e in s["engine_halts_info"].items():
            if e["halted"] and leg not in seen_eng:
                seen_eng.add(leg)
                j = int(np.argmin(np.abs(ts - _ts_of_date(e["date"]))))
                cc = curves[kkey(0.75)]
                knife = abs(e["margin_at_halt"]) < KNIFE_EDGE_FRAC * stress.PAPER_SEED[leg]["peak"]
                labels.append((ts[j], cc["total"][j], f"{'S3' if leg == 'pullback' else 'S4'} paper-book "
                               f"halt {e['date'][5:10]}\n({e['margin_at_halt'] / 1e3:+.1f}k vs its line"
                               f"{': knife-edge' if knife else ''})", "x", INK2))
    # place labels: above the point when it sits in the lower 2/3 of the axes,
    # below when it is high up; alternate when two markers are close in time
    labels.sort(key=lambda t: t[0])
    last_x = -1e18
    up = True
    for (x, y, text, mk, col) in labels:
        xd = float(_dates([x])[0])
        ax.plot([xd], [y], marker=mk, ms=9 if mk == "v" else 8, color=col, mec=SURF if mk == "v" else col,
                mew=1.2 if mk == "v" else 2.0, ls="none", zorder=6, clip_on=False)
        if x - last_x < 20 * DAY:
            up = not up
        else:
            up = (f(y) - f(y0)) / rng < 0.66
        last_x = x
        dy = (0.16 if up else -0.16) * rng
        yl = finv(min(max(f(y) + dy, f(y0) + 0.03 * rng), f(y1) - 0.03 * rng))
        ax.annotate(text, xy=(xd, y), xytext=(xd, yl), fontsize=8, color=INK2, ha="center",
                    va="bottom" if up else "top",
                    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.6, shrinkA=0, shrinkB=4),
                    bbox=dict(boxstyle="round,pad=0.2", fc=SURF, ec="none", alpha=0.9), zorder=7)


def _ts_of_date(d: str) -> int:
    import calendar
    return calendar.timegm(time.strptime(d, "%Y-%m-%d %H:%M"))


def chart_scenario(res: dict, scen: str) -> str:
    plt, mdates, FuncFormatter, FixedLocator, NullLocator, PercentFormatter = _mpl()
    S = res["scenarios"][scen]
    cv = S["curves"]
    c75, c30 = cv["K0.75"], cv["K0.3"]
    x = _dates(c75["ts"])
    fig, (ax, axd) = plt.subplots(2, 1, figsize=(13, 9.6), sharex=True,
                                  gridspec_kw=dict(height_ratios=[3.0, 1.5], hspace=0.08))
    fig.subplots_adjust(left=0.07, right=0.81, top=0.805, bottom=0.07)
    p = S["paths"]["off+0"]
    btc, eth = p["btc"], p["eth"]
    fund = p["funding"]["source"]
    s75, s30 = S["runs"]["K0.75"]["off+0"], S["runs"]["K0.3"]["off+0"]
    has_q = c75.get("carry_quanto") is not None
    fig.suptitle(f"{S['label']} crash starting today (2026-10-07): account equity, start "
                 + r"\$100k" + " (BTC book " + r"\$70k" + " + carry " + r"\$30k" + ")",
                 x=0.07, ha="left", fontsize=13, fontweight="semibold", color=INK, y=0.975)
    fig.text(0.07, 0.937,
             f"Analogue: BTC {p['anchor_date'][:10]} to {p['window_end'][:10]} spliced onto today's "
             f"prices  |  BTC low {btc['low_pct']:+.0%} (day {btc['low_day']:.0f}), 12 months "
             f"{btc['end_pct']:+.0%}  |  ETH low {eth['low_pct']:+.0%}, 12 months {eth['end_pct']:+.0%}",
             fontsize=9.2, color=INK2, ha="left")
    fig.text(0.07, 0.915,
             f"Carry funding: BitMEX {fund}, proxy for the live HL linear ETH perp"
             + (" (dotted: BitMEX ETHUSD quanto, not the live instrument)" if has_q else
                " (no ETHUSD series for this window)")
             + f"  |  BTC perp funding on the book: {s75['btc_funding']['total']:+,.0f} at K 0.75 (modelled)",
             fontsize=9.2, color=INK2, ha="left")
    fig.text(0.07, 0.893,
             "K 0.75 = live size, K 0.30 = tripwire fallback  |  fills at the line, no slippage (upper bound)"
             "  |  x = engine paper-book halt (margin to its line); v = executor halt (none fired)",
             fontsize=9.2, color=INK2, ha="left")
    # top: equity
    ax.plot(x, c75["total"], color=C_K75, lw=2.6, label="account, K 0.75 (live)", zorder=5)
    ax.plot(x, c30["total"], color=C_K30, lw=1.8, ls=(0, (5, 3)), label="account, K 0.30 (fallback)", zorder=4)
    ax.plot(x, c75["hold"], color=C_HOLD, lw=1.8, label="hold " + r"\$100k" + " BTC", zorder=3)
    ax.plot(x, c75["carry"], color=C_CARRY, lw=1.8, label=f"carry sleeve value (from " + r"\$30k" + f", {fund})", zorder=3)
    if has_q:
        ax.plot(x, c75["carry_quanto"], color=C_CARRY, lw=1.2, ls=(0, (1.5, 2.5)), alpha=0.9,
                label="carry if funded like the ETHUSD quanto", zorder=3)
    ax.axhline(stress.START_EQUITY, color=C_CASH, lw=1.2, ls=(0, (1.5, 2.5)), label="cash " + r"\$100k", zorder=2)
    # carry gate flips as small ticks on the carry line
    flips = s75["carry"]["flips"]
    if flips:
        fx = _dates([f["ts"] - BAR for f in flips])
        fy = [f["sleeve_value"] for f in flips]
        ax.plot(fx, fy, ls="none", marker="o", ms=6, mfc=SURF, mec=C_CARRY, mew=1.6,
                label=f"carry gate flip ({len(flips)})", zorder=6)
    allv = c75["total"] + c30["total"] + c75["hold"] + c75["carry"] + (c75["carry_quanto"] if has_q else [])
    lo = min(allv) * 0.85
    hi = max(allv) * 1.25
    _log_ticks(ax, lo, hi, FixedLocator, NullLocator, FuncFormatter)
    _style_axes(ax, mdates)
    ax.set_ylabel("equity (log scale)", color=INK2)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=4, handlelength=2.4,
              columnspacing=1.4, labelcolor=INK2, borderaxespad=0.0)
    _event_marks(ax, cv, S, log=True)
    ends = [(x, c75["total"], "K 0.75", C_K75), (x, c30["total"], "K 0.30", C_K30),
            (x, c75["hold"], "hold BTC", C_HOLD), (x, c75["carry"], "carry", C_CARRY)]
    if has_q:
        ends.append((x, c75["carry_quanto"], "carry (quanto)", C_CARRY))
    _end_labels(ax, ends, log=True)
    # bottom: drawdown
    axd.plot(x, np.asarray(c75["dd_total"]) * 100, color=C_K75, lw=2.0, zorder=5)
    axd.plot(x, np.asarray(c30["dd_total"]) * 100, color=C_K30, lw=1.5, ls=(0, (5, 3)), zorder=4)
    axd.plot(x, np.asarray(c75["dd_hold"]) * 100, color=C_HOLD, lw=1.5, zorder=3)
    axd.plot(x, np.asarray(c75["dd_carry"]) * 100, color=C_CARRY, lw=1.5, zorder=3)
    # the TRUE drawdown-halt line per bar, (HW_t - 30% of base) / peak_t - 1, in the
    # panel's own units: HW_t is the executor's high-water as tested on the bar,
    # peak_t the running peak of close equity the drawdown curves are measured from
    def _halt_line_pct(c):
        peak = np.maximum.accumulate(np.concatenate([[stress.START_EQUITY],
                                                     np.asarray(c["total"], dtype=float)]))[1:]
        return (np.asarray(c["dd_halt_line"], dtype=float) / peak - 1.0) * 100
    hl75, hl30 = _halt_line_pct(c75), _halt_line_pct(c30)
    axd.plot(x, hl75, color=C_K75, lw=1.0, ls=(0, (1.5, 2.5)), zorder=2)
    axd.plot(x, hl30, color=C_K30, lw=0.9, ls=(0, (1.5, 2.5)), alpha=0.9, zorder=2)
    axd.text(x[-1], float(min(hl75[-1], hl30[-1])) - 1.0,
             "executor drawdown halt line (HW - " + r"\$30k" + "), per K",
             fontsize=8, color=INK2, va="top", ha="right",
             bbox=dict(boxstyle="round,pad=0.15", fc=SURF, ec="none", alpha=0.85))
    _style_axes(axd, mdates)
    axd.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    axd.set_ylabel("drawdown from running peak", color=INK2)
    dmin = min(min(c75["dd_total"]), min(c30["dd_total"]), min(c75["dd_hold"]), min(c75["dd_carry"])) * 100
    axd.set_ylim(min(-35, dmin * 1.12), 4)
    d75, d30 = s75["rail_use"]["drawdown"], s30["rail_use"]["drawdown"]
    axd.text(1.012, 0.97, f"max DD\nK 0.75  {s75['max_dd']:.1%}\nK 0.30  {s30['max_dd']:.1%}\n"
             f"hold BTC  {s75['max_dd_bench']:.1%}\ncarry  {min(c75['dd_carry']):.1%}\n\n"
             f"daily rail used\nK 0.75  {s75['rail_use']['daily_loss']['used_pct']:.0%}    "
             f"K 0.30  {s30['rail_use']['daily_loss']['used_pct']:.0%}\n"
             f"DD rail used (min margin, date)\n"
             f"K 0.75  {d75['used_pct']:.0%}  ({d75['min_margin']:,.0f}, {d75['date'][5:10]})\n"
             f"K 0.30  {d30['used_pct']:.0%}  ({d30['min_margin']:,.0f}, {d30['date'][5:10]})",
             transform=axd.transAxes, fontsize=8.5, color=INK2, va="top", ha="left", linespacing=1.35)
    axd.set_xlim(x[0], x[-1] + 2)
    out = os.path.join(HERE, f"fig_{scen}.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def chart_summary(res: dict) -> str:
    plt, mdates, FuncFormatter, FixedLocator, NullLocator, PercentFormatter = _mpl()
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.subplots_adjust(left=0.06, right=0.98, top=0.82, bottom=0.06, hspace=0.5, wspace=0.22)
    fig.suptitle("Crash stress of the live book from 2026-10-07: account equity vs holding "
                 + r"\$100k" + " of BTC (12 months, spliced analogues)",
                 x=0.06, ha="left", fontsize=13.5, fontweight="semibold", color=INK, y=0.975)
    fig.text(0.06, 0.937, "Each panel: K 0.75 account (BTC book + carry) against hold-BTC on the same "
             "analogue path. Fourth panel: 12-month balance for K 0.75 / K 0.30 / hold BTC. "
             "Fills at the line, no slippage: upper bounds.", fontsize=9.2, color=INK2, ha="left")
    fig.text(0.06, 0.917, f"Carry funded by BitMEX {HEADLINE_FUNDING} (proxy for the live HL linear ETH perp); "
             "BTC perp funding on the book's positions modelled from the same series.",
             fontsize=9.2, color=INK2, ha="left")
    fig.text(0.06, 0.897, "Hollow marker in the fourth panel: the same cell if the carry were funded like the "
             "BitMEX ETHUSD quanto (not the live instrument; no series for the 1999 window).",
             fontsize=9.2, color=INK2, ha="left")
    for ax, (scen, _) in zip(axes.flat[:3], SCENARIOS):
        S = res["scenarios"][scen]
        c = S["curves"]["K0.75"]
        x = _dates(c["ts"])
        p = S["paths"]["off+0"]
        ax.plot(x, c["total"], color=C_K75, lw=2.4, label="account, K 0.75", zorder=5)
        ax.plot(x, c["hold"], color=C_HOLD, lw=1.8, label="hold BTC", zorder=3)
        ax.axhline(stress.START_EQUITY, color=C_CASH, lw=1.0, ls=(0, (1.5, 2.5)), label="cash", zorder=2)
        allv = c["total"] + c["hold"]
        _log_ticks(ax, min(allv) * 0.85, max(allv) * 1.3, FixedLocator, NullLocator, FuncFormatter)
        _style_axes(ax, mdates)
        s = S["runs"]["K0.75"]["off+0"]
        eh = ", ".join(f"{'S3' if leg == 'pullback' else 'S4'} {e['margin_at_halt'] / 1e3:+.1f}k vs its line"
                       + (", knife-edge" if abs(e["margin_at_halt"]) < KNIFE_EDGE_FRAC * stress.PAPER_SEED[leg]["peak"]
                          else "")
                       for leg, e in s["engine_halts_info"].items() if e["halted"])
        ax.set_title(f"{S['label']}: BTC {p['anchor_date'][:10]} to {p['window_end'][:10]} "
                     f"(low {p['btc']['low_pct']:+.0%}, 12m {p['btc']['end_pct']:+.0%})\n"
                     f"max DD {s['max_dd']:.1%} vs hold {s['max_dd_bench']:.1%}  |  executor halts "
                     f"{len(s['halts'])}  |  carry flips {s['carry']['n_flips']}\n"
                     f"engine-book halts {s['n_engine_halts']}{(' (' + eh + ')') if eh else ''}",
                     loc="left", fontsize=9.5)
        ax.legend(loc="upper left", ncol=3, labelcolor=INK2, bbox_to_anchor=(0.0, 1.0))
        ax.set_xlim(x[0], x[-1] + 0.16 * (x[-1] - x[0]))
        ax.xaxis.set_major_locator(FixedLocator([t for t in mdates.MonthLocator().tick_values(mdates.num2date(x[0]), mdates.num2date(x[-1]))
                                                 if x[0] <= t <= x[-1]]))
        _end_labels(ax, [(x, c["total"], "K 0.75", C_K75), (x, c["hold"], "hold BTC", C_HOLD)],
                    log=True, min_gap_frac=0.07)
        ax.tick_params(axis="x", pad=2)
    # fourth: 12-month balances
    ax = axes.flat[3]
    names = [SCEN_LABEL[s] for s, _ in SCENARIOS]
    series = [("K 0.75", C_K75, [res["scenarios"][s]["runs"]["K0.75"]["off+0"]["balances"]["365"] for s, _ in SCENARIOS]),
              ("K 0.30", C_K30, [res["scenarios"][s]["runs"]["K0.3"]["off+0"]["balances"]["365"] for s, _ in SCENARIOS]),
              ("hold BTC", C_HOLD, [res["scenarios"][s]["runs"]["K0.75"]["off+0"]["balances_bench"]["365"] for s, _ in SCENARIOS])]
    xpos = np.arange(len(names))
    w = 0.22
    for i, (name, col, vals) in enumerate(series):
        xs = xpos + (i - 1) * (w + 0.04)
        ax.bar(xs, vals, width=w, color=col, label=name, zorder=3)
        for xx, v in zip(xs, vals):
            # value inside the bar's top (the space above is for the quanto tick)
            ax.text(xx, v / 1.04, usd(v), ha="center", va="top", fontsize=8.5, color=SURF, zorder=4)
    # the quanto column as a hollow tick above the K 0.75 / K 0.30 bars
    qx, qy, qc = [], [], []
    for i, K in enumerate(KS):
        for j, (s, _) in enumerate(SCENARIOS):
            q = res["scenarios"][s]["runs_quanto"].get(kkey(K), {}).get("off+0")
            if q:
                qx.append(j + (i - 1) * (w + 0.04))
                qy.append(q["balances"]["365"])
                qc.append(C_K75 if K == 0.75 else C_K30)
    for xx, yy, cc in zip(qx, qy, qc):
        ax.plot([xx], [yy], marker="o", ms=7, mfc=SURF, mec=cc, mew=1.6, ls="none", zorder=5)
        ax.text(xx, yy * 1.06, usd(yy), ha="center", va="bottom", fontsize=8, color=INK2)
    if qx:
        ax.plot([], [], marker="o", ms=7, mfc=SURF, mec=INK2, mew=1.6, ls="none",
                label="if funded like the ETHUSD quanto")
    ax.axhline(stress.START_EQUITY, color=C_CASH, lw=1.0, ls=(0, (1.5, 2.5)), zorder=2,
               label="start " + r"\$100k")
    ax.set_xticks(xpos)
    ax.set_xticklabels(names)
    ax.set_yscale("log")
    vals_all = [v for _, _, vs in series for v in vs] + qy
    _log_ticks(ax, min(vals_all) * 0.7, max(vals_all) * 1.6, FixedLocator, NullLocator, FuncFormatter)
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    ax.tick_params(length=0)
    ax.set_title("Balance after 12 months (offset 0; start " + r"\$100k" + ", log scale)",
                 loc="left", fontsize=10, pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, labelcolor=INK2, fontsize=8.5,
              borderaxespad=0.0)
    out = os.path.join(HERE, "fig_summary.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def make_charts(res: dict) -> list[str]:
    outs = [chart_scenario(res, scen) for scen, _ in SCENARIOS]
    outs.append(chart_summary(res))
    return outs


# --------------------------------------------------------------------------
def main() -> None:
    charts_only = "--charts" in sys.argv
    if charts_only:
        with open(RESULTS) as fh:
            res = json.load(fh)
    else:
        print(f"run_all: now={NOW} ({_date(NOW)}) grid {len(SCENARIOS)} scenarios x {KS} x {OFFSETS}; "
              f"headline funding {HEADLINE_FUNDING}, quanto column {QUANTO_FUNDING}, BTC funding modelled")
        res = run_grid()
        res["table"] = table_lines(res)
        with open(RESULTS, "w") as fh:
            json.dump(res, fh)
        print(f"saved {RESULTS} ({os.path.getsize(RESULTS) / 1e6:.1f} MB) in {res['meta']['elapsed_s']} s")
    outs = make_charts(res)
    print("\n".join(table_lines(res)))
    print("\nHONESTY")
    print("\n".join(f"  - {l}" for l in res["honesty"]))
    print("charts:", *outs, sep="\n  ")


if __name__ == "__main__":
    main()
