"""Phase-aware allocation study — implementation of PHASE_BARBELL_SPEC.md.

Everything decision-relevant was frozen in the spec (commit 36c9b6d)
BEFORE this file produced a number: mapping table, tiers, costs,
benchmarks, metrics, honesty items. This module only implements it.

Self-contained on purpose: barbell-lab deploys without treasury-canary,
so the phase rules are REPLICATED here and a gate asserts parity with
`treasury-canary...business_cycle.phase_of` on the overlapping era.

Data (fetched once, frozen to research/fixtures/phase_data.json for the
gates): datahub/Shiller monthly SPX price+dividend+CPI+long-rate 1871->,
FRED INDPRO/PAYEMS/TB3MS/USREC + the tier-C members, datahub gold
monthly, Damodaran annual 10y T-bond returns for synthetic-bond
validation.
"""
from __future__ import annotations

import json
import math
import os

import httpx

HERE = os.path.dirname(__file__)
FIXTURE = os.path.join(HERE, "fixtures", "phase_data.json")
FRED = "https://api.stlouisfed.org/fred/series/observations"
SHILLER_CSV = ("https://raw.githubusercontent.com/datasets/s-and-p-500/"
               "main/data/data.csv")
GOLD_CSV = ("https://raw.githubusercontent.com/datasets/gold-prices/"
            "main/data/monthly.csv")

Z_MIN_FULL = 120        # tier C warmup (matches the shipped tracker)
Z_MIN_SYNTH = 90        # tier B warmup (disclosed in the spec)
TIER_C_FROM = "1960-01"
COST_BP = 10.0          # one-way, per rebalance trade
RISK_LEVELS = {"defensive": 0.5, "balanced": 1.0, "aggressive": 1.5}

# spec table — the gate re-parses PHASE_BARBELL_SPEC.md and asserts equality
MAPPING = {
    "EXPANSION":   {"stocks": 70, "bonds": 20, "gold": 5,  "cash": 5},
    "LATE_CYCLE":  {"stocks": 55, "bonds": 30, "gold": 10, "cash": 5},
    "STALL":       {"stocks": 45, "bonds": 35, "gold": 10, "cash": 10},
    "SLOWDOWN":    {"stocks": 30, "bonds": 45, "gold": 15, "cash": 10},
    "CONTRACTION": {"stocks": 20, "bonds": 50, "gold": 15, "cash": 15},
}
GOLD_FROM = "1971-08"   # post-Bretton Woods only; earlier gold weight -> cash


# ---------------- data ----------------

def _fred(series: str, key: str) -> list[tuple[str, float]]:
    r = httpx.get(FRED, params={"series_id": series, "api_key": key,
                                "file_type": "json", "observation_start":
                                "1900-01-01"}, timeout=60)
    r.raise_for_status()
    out = []
    for o in r.json()["observations"]:
        if o["value"] not in (".", ""):
            out.append((o["date"][:7], float(o["value"])))
    return out


def fetch_all(fred_key: str) -> dict:
    """Fetch + freeze every input series. Run once; gates use the fixture."""
    data: dict = {}
    r = httpx.get(SHILLER_CSV, timeout=60, follow_redirects=True)
    r.raise_for_status()
    shl = {"px": [], "div": [], "cpi": [], "gs10": []}
    for line in r.text.strip().splitlines()[1:]:
        p = line.split(",")
        m = p[0][:7]
        for i, k in ((1, "px"), (2, "div"), (4, "cpi"), (5, "gs10")):
            try:
                v = float(p[i])
            except (ValueError, IndexError):
                continue
            if v > 0:
                shl[k].append((m, v))
    data["shiller"] = shl
    r = httpx.get(GOLD_CSV, timeout=60, follow_redirects=True)
    gold = []
    for line in r.text.strip().splitlines()[1:]:
        p = line.split(",")
        try:
            gold.append((p[0][:7], float(p[1])))
        except (ValueError, IndexError):
            pass
    data["gold"] = gold
    for s in ("INDPRO", "PAYEMS", "TB3MS", "USREC", "W875RX1", "CMRMTSPL",
              "PERMIT", "ICSA", "AWHMAN", "UMCSENT", "T10Y3M", "BAA10YM",
              "GS10", "CPIAUCSL"):
        data[s] = _fred(s, fred_key)
    # Damodaran annual 10y T-bond total returns for validation: parse the
    # "Returns by year" sheet's T.Bond column (xls; pandas+xlrd)
    try:
        import pandas as pd
        xls = httpx.get("https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
                        "histretSP.xls", timeout=60).content
        import io
        df = pd.read_excel(io.BytesIO(xls), sheet_name="Returns by year",
                           header=None)
        col_year = col_bond = None
        hdr_row = None
        for ri in range(min(30, len(df))):
            row = [str(x) for x in df.iloc[ri].tolist()]
            if "Year" in row:
                hdr_row = ri
                col_year = row.index("Year")
                for ci, cell in enumerate(row):
                    if "T. Bond" in cell or "T.Bond" in cell:
                        col_bond = ci
                        break
                break
        bonds = []
        if hdr_row is not None and col_bond is not None:
            for ri in range(hdr_row + 1, len(df)):
                y, v = df.iloc[ri, col_year], df.iloc[ri, col_bond]
                try:
                    bonds.append((int(y), float(v)))
                except (ValueError, TypeError):
                    continue
        data["damodaran_tbond_annual"] = bonds
    except Exception as exc:  # noqa: BLE001
        data["damodaran_tbond_annual"] = []
        data["damodaran_error"] = str(exc)
    os.makedirs(os.path.dirname(FIXTURE), exist_ok=True)
    json.dump(data, open(FIXTURE, "w"))
    return data


def load() -> dict:
    return json.load(open(FIXTURE))


# ---------------- shared math (parity-gated vs treasury-canary) ----------

def g6(xs):
    out = [None] * len(xs)
    for i in range(6, len(xs)):
        a, b = xs[i], xs[i - 6]
        if a and b and a > 0 and b > 0:
            out[i] = (math.log(a) - math.log(b)) * 2 * 100
    return out


def zs(xs, z_min):
    out = [None] * len(xs)
    hist: list[float] = []
    for i, x in enumerate(xs):
        if x is not None:
            hist.append(x)
        if x is not None and len(hist) >= z_min:
            mu = sum(hist) / len(hist)
            sd = (sum((h - mu) ** 2 for h in hist) / len(hist)) ** 0.5
            out[i] = (x - mu) / (sd + 1e-9)
    return out


def mean_rows(rows):
    out = []
    for vals in zip(*rows):
        vs = [v for v in vals if v is not None]
        out.append(sum(vs) / len(vs) if vs else None)
    return out


def phase_of(coin, lead):
    if coin is None:
        return None
    if coin < -0.75:
        return "CONTRACTION"
    if coin < 0 and lead is not None and lead < -0.3:
        return "SLOWDOWN"
    if coin < 0:
        return "STALL"
    if lead is not None and lead < -0.5:
        return "LATE_CYCLE"
    return "EXPANSION"


# ---------------- series assembly ----------------

def _monthly_map(pairs):
    return {m: v for m, v in pairs}


def build_frames(data: dict) -> dict:
    """Aligned monthly arrays 1900-01 .. last common month."""
    shl = data["shiller"]
    px, div = _monthly_map(shl["px"]), _monthly_map(shl["div"])
    cpi_s, gs10_s = _monthly_map(shl["cpi"]), _monthly_map(shl["gs10"])
    fred = {k: _monthly_map(data[k]) for k in data
            if k not in ("shiller", "gold", "damodaran_tbond_annual",
                         "damodaran_error")}
    gold = _monthly_map(data["gold"])
    last = min(max(px), max(fred["INDPRO"]), max(fred["TB3MS"]))
    months = []
    y, m = 1900, 1
    while f"{y:04d}-{m:02d}" <= last:
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1

    def a(src):
        return [src.get(mo) for mo in months]

    # long yield: FRED GS10 from 1953, Shiller before
    long_y = [fred["GS10"].get(mo) or gs10_s.get(mo) for mo in months]
    cpi = [fred["CPIAUCSL"].get(mo) or cpi_s.get(mo) for mo in months]
    return {"months": months, "px": a(px), "div": a(div), "cpi": cpi,
            "long_y": long_y, "gold": a(gold),
            **{k.lower(): a(fred[k]) for k in
               ("INDPRO", "PAYEMS", "TB3MS", "USREC", "W875RX1", "CMRMTSPL",
                "PERMIT", "ICSA", "AWHMAN", "UMCSENT", "T10Y3M", "BAA10YM")}}


# ---------------- asset returns ----------------

def stock_returns(F) -> list:
    """S&P TOTAL monthly return: price change + dividend/12 yield.
    Shiller Dividend is a trailing ANNUAL rate at monthly frequency."""
    px, div = F["px"], F["div"]
    out = [None] * len(px)
    for i in range(1, len(px)):
        if px[i] and px[i - 1]:
            d = (div[i] or 0.0) / 12.0
            out[i] = (px[i] + d) / px[i - 1] - 1
    return out


def bond_returns(F) -> list:
    """Synthetic 10y constant-maturity total return from yields:
    r_m = y_{t-1}/12 - D_mod * dy + 0.5 * C * dy^2   (decimal yields)."""
    y = F["long_y"]
    out = [None] * len(y)
    for i in range(1, len(y)):
        if y[i] is None or y[i - 1] is None:
            continue
        y0, y1 = y[i - 1] / 100.0, y[i] / 100.0
        dy = y1 - y0
        n = 10
        dmac = (1 + y0) / y0 * (1 - (1 + y0) ** -n) + n * (1 + y0) ** -n \
            if y0 > 0 else n
        # Macaulay of a par bond above simplifies; use modified duration
        dmod = dmac / (1 + y0) if y0 > 0 else n
        conv = dmod * dmod * 1.1          # par-bond convexity approximation
        out[i] = y0 / 12.0 - dmod * dy + 0.5 * conv * dy * dy
    return out


def cash_returns(F) -> list:
    tb = F["tb3ms"]
    return [None] + [None if tb[i - 1] is None else tb[i - 1] / 1200.0
                     for i in range(1, len(tb))]


def gold_returns(F) -> list:
    g, months = F["gold"], F["months"]
    out = [None] * len(g)
    for i in range(1, len(g)):
        if months[i] >= GOLD_FROM and g[i] and g[i - 1]:
            out[i] = g[i] / g[i - 1] - 1
    return out


def validate_bonds(data: dict, F) -> dict:
    """Annual synthetic returns vs Damodaran actual 10y T-bond returns.
    Spec bounds: corr >= 0.95 and |CAGR gap| <= 50bp/yr on 1953->."""
    dam = {y: v for y, v in data.get("damodaran_tbond_annual", [])}
    br = bond_returns(F)
    months = F["months"]
    ann: dict[int, float] = {}
    acc, yr, n = 1.0, None, 0
    for i, m in enumerate(months):
        if br[i] is None:
            continue
        y = int(m[:4])
        if yr is None:
            yr = y
        if y != yr:
            if n == 12:
                ann[yr] = acc - 1
            acc, yr, n = 1.0, y, 0
        acc *= 1 + br[i]
        n += 1
    common = sorted(y for y in ann if y in dam and y >= 1953)
    if len(common) < 30:
        return {"ok": False, "reason": f"only {len(common)} common years"}
    xs = [ann[y] for y in common]
    ys = [dam[y] for y in common]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs)
    vy = sum((b - my) ** 2 for b in ys)
    corr = cov / math.sqrt(vx * vy)
    cagr_s = math.prod(1 + a for a in xs) ** (1 / len(xs)) - 1
    cagr_d = math.prod(1 + b for b in ys) ** (1 / len(ys)) - 1
    gap_bp = (cagr_s - cagr_d) * 1e4
    return {"ok": bool(corr >= 0.95 and abs(gap_bp) <= 50),
            "corr": round(corr, 4), "cagr_gap_bp": round(gap_bp, 1),
            "years": [common[0], common[-1]], "n_years": len(common)}


# ---------------- phase labels (tiered, publication-lagged) --------------

def labels(F) -> list:
    """Phase label usable for month t's allocation decision: computed from
    series values through t-1 (publication lag), tier by availability."""
    months = F["months"]
    n = len(months)

    def neg(xs):
        return [-x if x is not None else None for x in xs]

    dsent = [None] + [
        (b - a) if a is not None and b is not None else None
        for a, b in zip(F["umcsent"], F["umcsent"][1:])]
    curve_c = [(a if a is not None else
                ((g - t) if g is not None and t is not None else None))
               for a, g, t in zip(F["t10y3m"], F["long_y"], F["tb3ms"])]
    mom12 = [None] * 12 + [
        (math.log(F["px"][i] / F["px"][i - 12]) * 100)
        if F["px"][i] and F["px"][i - 12] else None for i in range(12, n)]
    cpi_yoy = [None] * 12 + [
        (math.log(F["cpi"][i] / F["cpi"][i - 12]) * 100)
        if F["cpi"][i] and F["cpi"][i - 12] else None for i in range(12, n)]

    coin_c = mean_rows([zs(g6(F[k]), Z_MIN_FULL)
                        for k in ("payems", "indpro", "w875rx1", "cmrmtspl")])
    lead_raw = mean_rows([
        zs(curve_c, Z_MIN_FULL), zs(g6(F["permit"]), Z_MIN_FULL),
        zs(neg(g6(F["icsa"])), Z_MIN_FULL), zs(F["awhman"], Z_MIN_FULL),
        zs(dsent, Z_MIN_FULL), zs(neg(F["baa10ym"]), Z_MIN_FULL)])
    lead_c = [None] * n
    for i in range(n):
        w = [x for x in lead_raw[max(0, i - 2):i + 1] if x is not None]
        lead_c[i] = sum(w) / len(w) if w else None

    # tier B: what existed pre-1960 - indpro, payems (1939->), curve
    # (long - tb3ms), cpi yoy, spx momentum. Composite = mean of z's;
    # lead proxy = curve z alone (the only leading member alive).
    curve_b = [(g - t) if g is not None and t is not None else None
               for g, t in zip(F["long_y"], F["tb3ms"])]
    coin_b = mean_rows([zs(g6(F["indpro"]), Z_MIN_SYNTH),
                        zs(g6(F["payems"]), Z_MIN_SYNTH),
                        zs(mom12, Z_MIN_SYNTH),
                        zs(neg(cpi_yoy), Z_MIN_SYNTH)])
    lead_b = zs(curve_b, Z_MIN_SYNTH)

    out: list = [None] * n
    for t in range(1, n):
        i = t - 1                              # publication lag
        if months[t] >= TIER_C_FROM and coin_c[i] is not None:
            out[t] = ("C", phase_of(coin_c[i], lead_c[i]))
        elif coin_b[i] is not None:
            out[t] = ("B", phase_of(coin_b[i], lead_b[i]))
    return out


# ---------------- backtest ----------------

def weights_for(phase: str, risk: float, month: str) -> dict:
    row = MAPPING[phase]
    # bonds absorb the risk tilt but can never go short: cap the equity
    # boost at what the bond sleeve can give up (gate find, 2026-08-11 -
    # EXPANSION x1.5 produced bonds = -5%)
    eq = min(95.0, max(0.0, row["stocks"] * risk),
             row["stocks"] + row["bonds"])
    bonds = row["bonds"] + (row["stocks"] - eq)
    gold = row["gold"] if month >= GOLD_FROM else 0.0
    cash = row["cash"] + (row["gold"] - gold)
    tot = eq + bonds + gold + cash
    return {"stocks": eq / tot, "bonds": bonds / tot,
            "gold": gold / tot, "cash": cash / tot}


def run(F, labs, risk: float = 1.0, start: str = "1935-01") -> dict:
    months = F["months"]
    R = {"stocks": stock_returns(F), "bonds": bond_returns(F),
         "gold": gold_returns(F), "cash": cash_returns(F)}
    i0 = next(i for i, m in enumerate(months)
              if m >= start and labs[i] is not None
              and all(R[k][i] is not None for k in ("stocks", "bonds",
                                                    "cash")))
    eq, hist = 1.0, []
    w_prev: dict | None = None
    phase_series = []
    for t in range(i0, len(months)):
        if labs[t] is None or R["stocks"][t] is None or \
                R["bonds"][t] is None or R["cash"][t] is None:
            break
        tier, ph = labs[t]
        w = weights_for(ph, risk, months[t])
        turn = (sum(abs(w[k] - w_prev[k]) for k in w) if w_prev else
                sum(w.values()))
        cost = turn * COST_BP / 1e4
        r = sum(w[k] * (R[k][t] or 0.0) for k in w) - cost
        eq *= 1 + r
        hist.append((months[t], eq, r))
        phase_series.append((months[t], tier, ph))
        w_prev = w
    return {"start": months[i0], "end": hist[-1][0], "curve": hist,
            "phases": phase_series}


def run_benchmark(F, kind: str, start_i: int, end_m: str) -> list:
    months = F["months"]
    R = {"stocks": stock_returns(F), "bonds": bond_returns(F),
         "cash": cash_returns(F)}
    eq, hist = 1.0, []
    for t in range(start_i, len(months)):
        if months[t] > end_m or R["stocks"][t] is None or \
                R["bonds"][t] is None:
            break
        r = R["stocks"][t] if kind == "spx" else \
            0.6 * R["stocks"][t] + 0.4 * R["bonds"][t] - \
            (0.02 * COST_BP / 1e4)      # 60/40 monthly rebalance turnover
        eq *= 1 + r
        hist.append((months[t], eq, r))
    return hist


# ---------------- metrics ----------------

def metrics(hist, cash_hist=None) -> dict:
    rets = [r for _, _, r in hist]
    n = len(rets)
    yrs = n / 12.0
    eq_end = hist[-1][1]
    cagr = eq_end ** (1 / yrs) - 1
    peak, mdd, uz = 0.0, 0.0, 0.0
    eqs = [e for _, e, _ in hist]
    for e in eqs:
        peak = max(peak, e)
        dd = e / peak - 1
        mdd = min(mdd, dd)
        uz += dd * dd
    ulcer = math.sqrt(uz / n) * 100
    rf = [r for _, _, r in cash_hist] if cash_hist else [0.0] * n
    ex = [a - b for a, b in zip(rets, rf[:n])]
    mu = sum(ex) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in ex) / n)
    sharpe = mu / sd * math.sqrt(12) if sd else None
    worst36 = min((eqs[i + 36] / eqs[i] - 1 for i in range(len(eqs) - 36)),
                  default=None)
    return {"cagr_pct": round(cagr * 100, 2),
            "max_dd_pct": round(mdd * 100, 1),
            "sharpe": round(sharpe, 2) if sharpe else None,
            "ulcer": round(ulcer, 2),
            "worst_36m_pct": round(worst36 * 100, 1)
            if worst36 is not None else None,
            "years": round(yrs, 1)}
