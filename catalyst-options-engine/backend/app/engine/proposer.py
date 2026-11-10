"""Turn a scored setup into a concrete paper proposal. Pure, ORM-free.

Rules (engine.yaml drives the numbers):
  * Only setups with score >= min_score (default 55) and a DATED event.
  * Default structure: ATM_STRADDLE — direction-agnostic; we are betting the
    move is bigger than priced, not on its sign. CALL_ONLY (or PUT_ONLY) is
    proposed ONLY when the catalyst carries an operator-set direction_lean —
    never inferred automatically.
  * Sizing: premium budget = max_premium_bps (default 50bps) of paper equity;
    contracts = floor(budget / per-contract premium), minimum 1 contract
    (the minimum tradable unit may exceed the bps budget — flagged, allowed).
  * Entry pricing honesty: real chain ASK on every leg when the chain lane is
    live ("chain_ask"); otherwise Black-Scholes at the engine's scenario IV
    ("bs_scenario") — the basis is recorded on EVERY proposal.
  * Max loss = premium paid. Always. Long-premium structures only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .bs import bs_price
from .signals import ChainRowView, atm_row, expiry_after

# When the chain lane is dark we still need a listed-ish expiry for the
# synthetic (BS) structure: first Friday-ish date >= event + this many days.
SYNTHETIC_EXPIRY_DAYS_AFTER_EVENT = 7


@dataclass
class Proposal:
    symbol: str
    structure: str               # ATM_STRADDLE | CALL_ONLY | PUT_ONLY
    strike: float
    expiry: date
    event_date: date
    contracts: int
    unit_premium: float          # per-share price of the whole structure
    cost: float                  # unit_premium * 100 * contracts
    max_loss: float              # == cost (long premium only)
    pricing_basis: str           # chain_ask | bs_scenario
    entry_iv: float | None       # scenario IV when bs_scenario, else None
    spot: float
    direction_lean: str | None = None
    score: float | None = None
    flags: list[str] = field(default_factory=list)


def _leg_kinds(structure: str) -> list[str]:
    if structure == "ATM_STRADDLE":
        return ["call", "put"]
    if structure == "CALL_ONLY":
        return ["call"]
    if structure == "PUT_ONLY":
        return ["put"]
    raise ValueError(f"unknown structure {structure!r}")


def _structure_for_lean(direction_lean: str | None) -> str:
    if direction_lean is None:
        return "ATM_STRADDLE"
    lean = direction_lean.strip().lower()
    if lean in ("bullish", "long", "up"):
        return "CALL_ONLY"
    if lean in ("bearish", "short", "down"):
        return "PUT_ONLY"
    return "ATM_STRADDLE"


def _chain_ask_premium(row: ChainRowView, structure: str) -> float | None:
    """Sum of leg ASKs; None if any leg lacks a real ask (no partial honesty)."""
    total = 0.0
    for kind in _leg_kinds(structure):
        ask = row.c_ask if kind == "call" else row.p_ask
        if ask is None or ask <= 0:
            return None
        total += ask
    return total


def propose(symbol: str, *, score: float | None, event_date: date | None,
            asof: date, spot: float | None,
            chain_rows: list[ChainRowView] | None,
            paper_equity: float,
            direction_lean: str | None = None,
            min_score: float = 55.0,
            max_premium_bps: float = 50.0,
            scenario_iv: float = 1.0) -> Proposal | None:
    """Build a proposal, or None when the setup does not qualify."""
    if score is None or score < min_score:
        return None
    if event_date is None or spot is None or spot <= 0:
        return None

    structure = _structure_for_lean(direction_lean)
    flags: list[str] = []

    # --- expiry + strike + entry premium -------------------------------------
    unit_premium: float | None = None
    pricing_basis = "bs_scenario"
    entry_iv: float | None = None
    strike: float | None = None
    expiry: date | None = None

    if chain_rows:
        exp = expiry_after(chain_rows, event_date)
        if exp is not None:
            at_exp = [r for r in chain_rows if r.expiry == exp]
            row = atm_row(at_exp, spot)
            if row is not None:
                prem = _chain_ask_premium(row, structure)
                if prem is not None:
                    unit_premium = prem
                    pricing_basis = "chain_ask"
                    strike = row.strike
                    expiry = exp

    if unit_premium is None:
        # Chain lane dark (or no usable quote): Black-Scholes at scenario IV.
        strike = round(spot)
        expiry = event_date + timedelta(days=SYNTHETIC_EXPIRY_DAYS_AFTER_EVENT)
        T = (expiry - asof).days / 365.0
        if T <= 0:
            return None
        unit_premium = sum(bs_price(spot, strike, T, scenario_iv, kind=k)
                           for k in _leg_kinds(structure))
        pricing_basis = "bs_scenario"
        entry_iv = scenario_iv
        flags.append(f"chain dark: priced at scenario IV {scenario_iv:.2f}")

    assert strike is not None and expiry is not None
    if unit_premium <= 0:
        return None

    # --- sizing ---------------------------------------------------------------
    budget = (max_premium_bps / 10_000.0) * paper_equity
    per_contract = unit_premium * 100.0
    contracts = max(1, math.floor(budget / per_contract))
    cost = per_contract * contracts
    if contracts == 1 and cost > budget:
        flags.append("1-contract minimum exceeds bps budget")

    return Proposal(symbol=symbol, structure=structure, strike=strike,
                    expiry=expiry, event_date=event_date, contracts=contracts,
                    unit_premium=round(unit_premium, 4), cost=round(cost, 2),
                    max_loss=round(cost, 2), pricing_basis=pricing_basis,
                    entry_iv=entry_iv, spot=spot, direction_lean=direction_lean,
                    score=score, flags=flags)
