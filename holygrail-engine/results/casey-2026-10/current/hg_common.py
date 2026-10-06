"""Shared helpers for Analysis A (Casey's current book through the Dalio Holy Grail lens).

Everything numerical goes through the holygrail public API (book_from_dict,
prepare_moments, scorecard, allocate, backtest, forward).  Local helpers here
only edit the parsed YAML (variants), splice the Composer series, and group
streams into reporting sleeves.  Parameters: predeclared_params.json.
"""
from __future__ import annotations

import copy
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

OUT = Path(__file__).resolve().parent
ENGINE = OUT.parents[2]
sys.path.insert(0, str(ENGINE))

from holygrail.book import BookView, Position, book_from_dict  # noqa: E402
from holygrail.data import DataLoader  # noqa: E402
from holygrail.scorecard import ScoreSettings, prepare_moments, scorecard  # noqa: E402

P = json.loads((OUT / "predeclared_params.json").read_text())
BOOK_PATH = ENGINE / "books" / "casey-2026-10.yaml"
BOOK_DIR = BOOK_PATH.parent
END = "2026-09-30"
TARGET = 0.15
PRIOR_SHARPE = 0.30
SPREAD = P["A6_proposed"]["financing_spread_base"]
loader = DataLoader(offline=os.environ.get("HG_OFFLINE") == "1")  # HG_OFFLINE=1: cache only (reproducible re-runs)

COMPOSER_LIVE_START = {"hg": "2025-12-05", "kmlm": "2026-07-07", "crash": "2026-07-07", "vixhyg": "2026-07-22"}

# IBKR Pro USD margin card, ibkr.com/en/trading/margin-rates.php fetched 2026-10-06 (scratchpad ibkr_margin.html):
# 0-100k 5.380% (BM+1.5%), 100k-1M 4.880% (BM+1%), 1M-50M 4.630% (BM+0.75%), 50M+ 4.380% (BM+0.5%); BM = 3.88%.
# IBKR blends: the first 100k at tier I, the next 900k at tier II, and so on.
IBKR_TIERS = [(100_000.0, 0.0538), (1_000_000.0, 0.0488), (50_000_000.0, 0.0463), (math.inf, 0.0438)]
IBKR_CARD = ("IBKR Pro USD card fetched 2026-10-06 (ibkr.com margin-rates): 5.380% to $100k, 4.880% $100k-1M, "
             "4.630% $1M-50M (BM 3.88% + 1.5/1.0/0.75), blended by tier")


def ibkr_interest(borrow_usd: float) -> float:
    """Annual IBKR Pro USD interest ($) on a margin loan of ``borrow_usd``, blended by tier."""
    out, lo = 0.0, 0.0
    for hi, rate in IBKR_TIERS:
        if borrow_usd <= lo:
            break
        out += (min(borrow_usd, hi) - lo) * rate
        lo = hi
    return out


def ibkr_spread_over_rf(borrow_usd: float, rf: float) -> float:
    """Blended IBKR rate minus rf on a loan of ``borrow_usd`` (0 if nothing is borrowed)."""
    return ibkr_interest(borrow_usd) / borrow_usd - rf if borrow_usd > 0 else 0.0
SLEEVES = P["sleeves_for_reporting"]
STREAM_SLEEVE = {s: k for k, v in SLEEVES.items() for s in v}


def settings(**kw) -> ScoreSettings:
    base = dict(freq="D", window_years=3.0, end=END, estimator="lw_cc", history="common", target_vol=TARGET,
                max_leverage=3.0, position_flag=0.10, stream_risk_flag=0.25, good_sharpe=0.2, min_obs=52)
    base.update(kw)
    return ScoreSettings(**base)


# --------------------------------------------------------------------------- #
# Composer splice: backtest levels before the live start, live deposit-adjusted after
# --------------------------------------------------------------------------- #
def composer_spliced(slug: str) -> Path:
    d = ENGINE / "data" / "casey"
    b = pd.read_csv(d / f"composer_{slug}_backtest.csv", parse_dates=["date"]).set_index("date")["value"].astype(float)
    l = pd.read_csv(d / f"composer_{slug}_live.csv", parse_dates=["date"]).set_index("date")["deposit_adjusted_value"].astype(float)
    t0 = pd.Timestamp(COMPOSER_LIVE_START[slug])
    pre = b.loc[:t0]
    lr = l.loc[t0:].pct_change().dropna()
    lv = pre.iloc[-1] * (1 + lr).cumprod()
    s = pd.concat([pre, lv])
    s = s[~s.index.duplicated(keep="first")]
    p = OUT / "data" / f"composer_{slug}_spliced.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": s.index.strftime("%Y-%m-%d"), "value": s.to_numpy()}).to_csv(p, index=False)
    return p


def base_raw(spliced: bool = True) -> dict:
    raw = yaml.safe_load(BOOK_PATH.read_text())
    st = raw["streams"]
    for slug in ("hg", "kmlm", "crash", "vixhyg"):
        k = f"composer_{slug}"
        if spliced:
            st[k]["path"] = str(composer_spliced(slug))
            st[k]["source"] = (st[k]["source"] + f" | SPLICED: backtest (IN-SAMPLE) before {COMPOSER_LIVE_START[slug]}, "
                               "live deposit-adjusted returns from that date (Analysis A)")
        else:
            st[k]["path"] = str((BOOK_DIR / st[k]["path"]).resolve())
    for k, v in st.items():
        if v.get("type") == "series" and not Path(v["path"]).is_absolute():
            v["path"] = str((BOOK_DIR / v["path"]).resolve())
    add_streams(raw)
    return raw


def A(value, source, confidence="low"):
    return {"value": float(value), "source": source, "confidence": confidence}


def add_streams(raw: dict) -> None:
    """Streams used by the moves / proposal (no positions yet)."""
    st = raw["streams"]
    st["TLT"] = {"type": "market", "symbol": "TLT", "asset_class": "nominal_bond", "description": "iShares 20+y Treasury (long Treasuries)"}
    st["TIP"] = {"type": "market", "symbol": "TIP", "asset_class": "ilb", "description": "iShares TIPS"}
    st["DBC"] = {"type": "market", "symbol": "DBC", "asset_class": "commodity", "description": "Invesco DB Commodity Index (broad commodities, futures)"}
    st["IEF"] = {"type": "market", "symbol": "IEF", "asset_class": "nominal_bond", "description": "iShares 7-10y Treasury"}
    st["EFA"] = {"type": "market", "symbol": "EFA", "asset_class": "equity", "description": "iShares MSCI EAFE"}
    st["VEIEX"] = {"type": "market", "symbol": "VEIEX", "asset_class": "equity", "description": "Vanguard EM index fund"}
    st["QQQ"] = {"type": "market", "symbol": "QQQ", "asset_class": "equity", "description": "Nasdaq-100 (overlap check only)"}
    comps = {"IEF": 0.695, "SPY": 0.25, "EFA": 0.12, "VEIEX": 0.0665, "TIP": 0.4119, "DBC": 0.3269}
    g = sum(comps.values())
    st["allw_replica"] = {
        "type": "composite", "components": {k: v / g for k, v in comps.items()}, "leverage": g,
        "environments": ["growth_up", "growth_down", "inflation_up", "inflation_down"],
        "financing_spread": A(0.003, "judgement: futures-embedded financing inside the fund (Treasury futures ~repo, equity futures ~SOFR+0.4-0.8%); not opened"),
        "fee": A(0.0085, "SSGA ALLW summary prospectus 497K 2025-03-05: total expense 0.85% (dalio_canon s6, factcheck C6 CONFIRMED)", "high"),
        "description": "ALLW replica: SSGA-published exposures 2026-10-05 (nominal bonds 69.50, equities 43.65, ILB 41.19, commodities 32.69 = 1.87x gross) mapped to IEF / SPY+EFA+VEIEX / TIP / DBC"}
    st["margin_loan"] = {"type": "cash", "rate": None, "description": "margin loan (liability), rf + IBKR spread"}


def set_prior(raw: dict, vols: dict, rf: float, sharpe: float = PRIOR_SHARPE, haircut: set | None = None) -> None:
    """mu = rf + sharpe x base-window vol on every market/series stream (BOXX/BIL = rf)."""
    st = raw["streams"]
    for k, v in st.items():
        if v["type"] not in ("market", "series"):
            continue
        if k in ("BOXX", "BIL"):
            v["expected_return"] = A(rf, "FRED DTB3 latest (rf)", "high")
            continue
        if k not in vols:
            continue
        s = 0.0 if (haircut and k in haircut) else sharpe
        v["expected_return"] = A(rf + s * vols[k], f"NEUTRAL PRIOR rf {rf:.2%} + {s:.2f} x daily 3y vol {vols[k]:.1%} (Analysis A); NOT a forecast")
    st["margin_loan"]["rate"] = A(rf + SPREAD, "IBKR Pro USD blended ~$1M loan 4.93% (rf + 0.92%), ibkr.com margin-rates 2026-10-06; "
                                  "predeclared scalar, kept: the tiered cost at each book's actual loan size is in A6_routes", "medium")


def fix_totals(raw: dict) -> None:
    pos = raw["positions"]
    tot = sum(float(p["value_usd"]) for p in pos)
    sl = {}
    for p in pos:
        sl[p.get("sleeve", "unassigned")] = sl.get(p.get("sleeve", "unassigned"), 0.0) + float(p["value_usd"])
    raw["totals"] = {"total_usd": tot, "tolerance_usd": 1.0, "sleeves": sl}


def pos(raw, name):
    for p in raw["positions"]:
        if p["name"] == name:
            return p
    raise KeyError(name)


def build(raw):
    r = copy.deepcopy(raw)
    fix_totals(r)
    return book_from_dict(r, base_dir=BOOK_DIR)


# --------------------------------------------------------------------------- #
# funding: buys draw BOXX, then cash lines, then a margin loan; sales go to BOXX
# --------------------------------------------------------------------------- #
CASH_LINES = ["Cash/stables ex-Hyperliquid", "U26 settled cash"]


def _boxx(raw):
    return pos(raw, "U84 BOXX")


def fund(raw, amount: float) -> None:
    """Take ``amount`` USD out of BOXX -> cash lines -> margin loan."""
    need = amount
    b = _boxx(raw)
    take = min(need, b["value_usd"])
    b["value_usd"] -= take
    need -= take
    for n in CASH_LINES:
        if need <= 1e-9:
            break
        p = pos(raw, n)
        take = min(need, p["value_usd"])
        p["value_usd"] -= take
        need -= take
    if need > 1e-9:
        try:
            ml = pos(raw, "Margin loan")
            ml["value_usd"] -= need
        except KeyError:
            raw["positions"].append({"name": "Margin loan", "value_usd": -need, "stream": "margin_loan", "sleeve": "stocks",
                                     "liquidity": "liquid", "mark_basis": "market", "tags": ["margin"], "investable": True,
                                     "liability": True, "note": "Analysis A move funding"})


def receive(raw, amount: float) -> None:
    try:
        ml = pos(raw, "Margin loan")
        pay = min(amount, -ml["value_usd"])
        ml["value_usd"] += pay
        amount -= pay
    except KeyError:
        pass
    _boxx(raw)["value_usd"] += amount


def buy(raw, stream: str, usd: float, name: str | None = None, sleeve: str = "stocks") -> None:
    fund(raw, usd)
    name = name or f"NEW {stream}"
    try:
        p = pos(raw, name)
        p["value_usd"] += usd
    except KeyError:
        raw["positions"].append({"name": name, "value_usd": usd, "stream": stream, "sleeve": sleeve, "liquidity": "liquid",
                                 "mark_basis": "market", "tags": ["analysis_a_move"], "investable": True})


def sell(raw, name: str, usd: float) -> None:
    p = pos(raw, name)
    usd = min(usd, p["value_usd"])
    p["value_usd"] -= usd
    receive(raw, usd)


def revert_loans(raw) -> None:
    p = pos(raw, "Short-term 16% loans (out of BOXX)")
    v = p["value_usd"]
    p["value_usd"] = 0.0
    _boxx(raw)["value_usd"] += v


def drop_zero(raw) -> None:
    raw["positions"] = [p for p in raw["positions"] if abs(float(p["value_usd"])) > 1e-6 or "Venture" in p["name"]]


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #
def score(raw, view="liquid", st: ScoreSettings | None = None, exclude=None, return_moments=False):
    raw = copy.deepcopy(raw)
    drop_zero(raw)
    if exclude:
        raw["positions"] = [p for p in raw["positions"] if p["name"] not in exclude]
    book = build(raw)
    st = st or settings()
    v = book.view(view)
    m, prov, rf_info, sp_info, rets = prepare_moments(book, v, loader, st)
    sc = scorecard(book, v, m, st, rf_info=rf_info, spread_info=sp_info, provenance=prov)
    if return_moments:
        return sc, m, rets, book, v
    return sc


def sleeve_table(sc) -> list:
    out = {}
    for r in sc["streams"]:
        k = STREAM_SLEEVE.get(r["stream"], r["stream"])
        d = out.setdefault(k, {"sleeve": k, "usd": 0.0, "dollar_share": 0.0, "risk_share": 0.0})
        d["usd"] += r["usd"]; d["dollar_share"] += r["dollar_share"]; d["risk_share"] += r["risk_share"]
    return sorted(out.values(), key=lambda d: -d["risk_share"])


def neff_rows(sc) -> dict:
    return {r["label"]: {"value": r["value"], "family": r["class"], "flag": r["flag"]} for r in sc["effective_bets"]["rows"]}


def summary_row(label, sc) -> dict:
    eb, g, env = sc["effective_bets"], sc["gearing"], sc["environment"]
    rs = env["risk_share"]
    return {"view": label, "nav_usd": sc["nav_usd"], "vol": sc["portfolio"]["vol"], "dr2": eb["dr2"],
            "n_risky_streams": eb["n_streams_with_risk"], "implied_avg_corr": eb["implied_avg_corr"],
            **{f"neff_{k}": v["value"] for k, v in neff_rows(sc).items()},
            "top1": sc["streams"][0]["stream"], "top1_risk": sc["streams"][0]["risk_share"],
            "top2": sc["streams"][1]["stream"], "top2_risk": sc["streams"][1]["risk_share"],
            "top3": sc["streams"][2]["stream"], "top3_risk": sc["streams"][2]["risk_share"],
            **{f"box_{b}": rs[b] for b in env["boxes"]}, "box_unmapped": env["unmapped_risk_share"],
            "balance_score": env["balance_score"], "leverage_to_15": g["leverage_to_target"],
            "cash_share": g["cash_share"],
            "exp_return_prior": sc["portfolio"]["exp_return"], "sharpe_prior": sc["portfolio"]["sharpe"],
            "exp_return_at_15_prior": g["exp_return_at_target"]}


LABELS = {"composer_hg": "Composer HG symphony (not Dalio)", "composer_kmlm": "Composer KMLM switcher",
          "composer_crash": "Composer Crash Convexity", "composer_vixhyg": "Composer VIX Harvester",
          "composer_momentum": "Composer HG symphony + KMLM switcher", "KMLM": "KMLM trend ETF",
          "physical_metals": "physical gold/silver", "gold_silver": "gold & silver (phys+PHYS+PSLV)",
          "core_equity": "equity beta core", "single_names": "single names", "eth_carry": "HL ETH carry",
          "usdc_idle": "HL USDC (idle)", "TIP": "TIPS (TIP)", "TLT": "long Treasuries (TLT)", "DBC": "commodities (DBC)"}


def lab(n):
    return LABELS.get(n, n)
