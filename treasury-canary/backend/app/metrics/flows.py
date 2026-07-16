"""F. Flow compass — where is the money actually going?

When the stock-bond hedge breaks (positive correlation), the DESTINATION of the
haven bid discriminates the regime:

  GROWTH_SCARE   stocks down, bonds UP                 -> money into Treasuries/USD
  RATES_SHOCK    stocks down, bonds down, USD up,
                 gold not bid                          -> money into front-end cash
  DEBASEMENT     stocks down, bonds down, USD DOWN,
                 gold UP                               -> money leaving USD assets
                                                          (gold/foreign/crypto) — the
                                                          worst regime for Treasuries
  LIQUIDITY_CRUNCH stocks down, bonds down, USD up,
                 gold ALSO down                        -> dash-for-cash, forced selling
  RISK_ON        stocks up                             -> no stress rotation

Classification is deliberately rule-based and transparent (auditable thresholds in
the docstring of classify_regime), computed over a ~20-trading-day window.
"""
from __future__ import annotations

from datetime import date

WINDOW = 20  # trading observations (~1 month)

# Thresholds (pct over the window unless noted). Kept mild: we classify the
# PREVAILING drift, not single-day noise.
STOCKS_DOWN = -2.0
STOCKS_UP = 2.0
YIELD_MOVE_BPS = 10.0   # 10y move that counts as a real bond move
USD_MOVE = 1.0
GOLD_UP = 2.0
GOLD_DOWN = -2.0


def pct_return(vals: list[float | None], window: int = WINDOW) -> float | None:
    clean = [v for v in vals if v is not None]
    if len(clean) <= window or not clean[-1 - window]:
        return None
    return round((clean[-1] - clean[-1 - window]) / clean[-1 - window] * 100.0, 2)


def change_bps(vals: list[float | None], window: int = WINDOW) -> float | None:
    clean = [v for v in vals if v is not None]
    if len(clean) <= window:
        return None
    return round((clean[-1] - clean[-1 - window]) * 100.0, 1)


def classify_regime(
    stocks_pct: float | None,
    dy10_bps: float | None,
    usd_pct: float | None,
    gold_pct: float | None,
    btc_pct: float | None,
) -> dict:
    """Rule-based regime call from ~20d drifts. Returns id/label/description/
    destinations + the inputs it actually used (auditable)."""
    used = {"stocks_pct": stocks_pct, "dy10_bps": dy10_bps, "usd_pct": usd_pct,
            "gold_pct": gold_pct, "btc_pct": btc_pct}
    missing = [k for k, v in used.items() if v is None]

    def result(rid: str, label: str, desc: str, dests: list[str], severity: str) -> dict:
        return {"id": rid, "label": label, "description": desc, "destinations": dests,
                "severity": severity, "inputs": used, "missing_inputs": missing,
                "window_days": WINDOW}

    if stocks_pct is None or dy10_bps is None:
        return result("UNKNOWN", "Insufficient data",
                      "Need at least stock and 10y series to classify.", [], "INFO")

    if stocks_pct >= STOCKS_UP:
        return result("RISK_ON", "Risk-on",
                      "Equities rising — no stress rotation underway. Money is in risk assets.",
                      ["equities"], "INFO")

    if stocks_pct > STOCKS_DOWN:
        return result("NEUTRAL", "No decisive rotation",
                      "Equities roughly flat over the window; flow signals are weak.",
                      [], "INFO")

    # --- stocks are down: where did the money go? ---
    if dy10_bps <= -YIELD_MOVE_BPS:
        return result(
            "GROWTH_SCARE", "Growth scare — hedge intact",
            "Stocks down with Treasuries RALLYING: the classic flight-to-quality. "
            "Money is rotating into duration (and typically the dollar).",
            ["treasuries_10y", "usd"], "WARN")

    if dy10_bps >= YIELD_MOVE_BPS:
        usd_up = usd_pct is not None and usd_pct >= USD_MOVE
        usd_down = usd_pct is not None and usd_pct <= -USD_MOVE
        gold_up = gold_pct is not None and gold_pct >= GOLD_UP
        gold_down = gold_pct is not None and gold_pct <= GOLD_DOWN

        if usd_down and gold_up:
            dests = ["gold", "foreign_assets"]
            if btc_pct is not None and btc_pct > 0:
                dests.append("crypto")
            return result(
                "DEBASEMENT", "Debasement / sell-USD-assets",
                "Stocks AND bonds down while the DOLLAR falls and GOLD is bid: the haven "
                "bid is leaving U.S. assets entirely. Historically the most dangerous "
                "configuration for Treasuries (fiscal/credibility premium).",
                dests, "CRITICAL")
        if usd_up and gold_down:
            return result(
                "LIQUIDITY_CRUNCH", "Liquidity crunch — dash for cash",
                "Everything sold — even gold — while the dollar spikes: forced "
                "deleveraging; money is going to literal cash/T-bills only (March-2020 style).",
                ["cash_tbills", "usd"], "CRITICAL")
        if usd_up:
            return result(
                "RATES_SHOCK", "Rates/inflation shock",
                "Stocks and bonds down together with a firm dollar and no gold bid: "
                "rates are the problem (2022-style). Money is hiding at the FRONT END "
                "(bills/money-market) rather than in duration.",
                ["cash_tbills", "usd"], "RED")
        return result(
            "HEDGE_BROKEN", "Hedge broken — mixed flows",
            "Stocks and bonds down together but dollar/gold signals are mixed or missing; "
            "regime not yet decisive. Watch USD and gold for the tiebreak.",
            ["cash_tbills"], "RED")

    return result(
        "MIXED", "Stocks down, bonds flat",
        "Equity weakness without a decisive bond move; rotation destination unclear.",
        [], "WARN")


def build_flow_snapshot(bundle: dict[str, tuple[list[date], list]]) -> dict:
    """Assemble the /flows/destinations payload from the shared bundle."""
    sp = bundle.get("sp500", ([], []))[1]
    y10 = bundle.get("10y", ([], []))[1]
    y3m = bundle.get("3mo", ([], []))[1]
    usd = bundle.get("usd", ([], []))[1]
    oil = bundle.get("oil", ([], []))[1]
    btc = bundle.get("btc", ([], []))[1]
    gold = bundle.get("gold", ([], []))[1]

    stocks_pct = pct_return(sp)
    dy10 = change_bps(y10)
    dy3m = change_bps(y3m)
    usd_pct = pct_return(usd)
    oil_pct = pct_return(oil)
    btc_pct = pct_return(btc)
    gold_pct = pct_return(gold)

    regime = classify_regime(stocks_pct, dy10, usd_pct, gold_pct, btc_pct)

    assets = {
        "stocks": {"label": "S&P 500", "ret_pct": stocks_pct, "unit": "%",
                   "role": "risk asset — the thing being fled (or not)"},
        "treasuries_10y": {"label": "10y Treasury", "chg_bps": dy10, "unit": "bps yield",
                           "role": "duration haven; yield DOWN = bond bid"},
        "bills_3m": {"label": "3m T-bill", "chg_bps": dy3m, "unit": "bps yield",
                     "role": "front-end cash; yield down while stocks fall = bill bid"},
        "usd": {"label": "Dollar (broad)", "ret_pct": usd_pct, "unit": "%",
                "role": "haven currency; falling in stress = confidence problem"},
        "gold": {"label": "Gold (GLD)", "ret_pct": gold_pct, "unit": "%",
                 "role": "the anti-USD haven; bid when trust in paper assets fades"},
        "oil": {"label": "WTI crude", "ret_pct": oil_pct, "unit": "%",
                "role": "inflation impulse; up in a selloff = supply/inflation shock"},
        "btc": {"label": "Bitcoin", "ret_pct": btc_pct, "unit": "%",
                "role": "debasement/risk hybrid; corroborates gold in sell-USD regimes"},
    }
    return {"window_days": WINDOW, "assets": assets, "regime": regime}
