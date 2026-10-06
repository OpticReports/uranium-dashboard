"""YAML book schema: positions, stream definitions, assumptions, totals.

    name: My book
    as_of: 2026-10-06
    assumptions:                       # named, referenced elsewhere as "@key"
      equity_mu: {value: 0.065, source: "...", confidence: medium}
    settings:
      risk_free: {value: 0.04, source: "...", confidence: high}   # or "fred:DTB3"
      target_vol: 0.10
      ...
    streams:
      SPY: {type: market, symbol: SPY, asset_class: equity, expected_return: "@equity_mu"}
      loan: {type: parametric, expected_return: {...}, vol: {...}, factor_correlations: {HYG: {...}}}
      tqqq: {type: composite, components: {QQQ: 1.0}, leverage: 3, financing_spread: {...}, fee: {...}}
      symphony: {type: series, path: nav.csv, date_col: date, value_col: nav, source: "Composer export"}
      cash: {type: cash}
    positions:
      - {name: Brokerage SPY, value_usd: 100000, stream: SPY, sleeve: core,
         liquidity: liquid, mark_basis: market, tags: [taxable], investable: true}
    totals: {total_usd: 100000, sleeves: {core: 100000}, tolerance_usd: 1.0}

Validation fails loudly: unknown stream -> UnknownStreamError; totals that do
not reconcile -> ReconciliationError; a bare number where an assumption is
expected -> AssumptionError; negative values only with ``liability: true``.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from .errors import AssumptionError, ReconciliationError, UnknownStreamError, ValidationError
from .streams import (LIQUIDITY, MARK_BASIS, Assumption, CashStream, CompositeStream, DefaultModel, MarketStream,
                      ParametricStream, ProxySpec, SeriesStream, Universe)

_STREAM_KEYS = {
    "market": {"symbol", "proxies"},
    "series": {"path", "date_col", "value_col", "kind", "source"},
    "parametric": {"vol", "factor_loadings", "factor_correlations", "idio_vol", "default"},
    "cash": {"rate"},
    "composite": {"components", "leverage", "financing_spread", "fee", "allow_cash_remainder"},
}
_COMMON = {"type", "description", "asset_class", "environments", "expected_return", "liquidity", "mark_basis"}


@dataclass
class Position:
    """One holding.  liquidity / mark_basis default to the stream's."""
    name: str
    value_usd: float
    stream: str
    sleeve: str = "unassigned"
    liquidity: str = "liquid"
    mark_basis: str = "market"
    tags: tuple = ()
    investable: bool = True
    liability: bool = False
    note: str = ""


@dataclass
class BookView:
    """A filtered slice of the book.  ``weights`` are stream weights as a
    fraction of the view's NAV (positions on the same stream aggregated)."""
    label: str
    positions: list
    total_usd: float

    def stream_values(self) -> dict:
        """USD per stream in the view: sum of value_usd of positions on each stream."""
        out: dict[str, float] = {}
        for p in self.positions:
            out[p.stream] = out.get(p.stream, 0.0) + p.value_usd
        return out

    @property
    def streams(self) -> list:
        """Stream names in the view, in first-appearance order."""
        return list(self.stream_values())

    def weights(self) -> dict:
        """Stream weights w_s = USD_s / view NAV (sum = 1)."""
        return {k: v / self.total_usd for k, v in self.stream_values().items()}

    def look_through_usd(self, universe: Universe) -> dict:
        """USD exposure to each leaf stream (composites expanded, leverage
        included), plus '__rf__' for the implicit cash/borrowing leg."""
        out: dict[str, float] = {}
        for s, v in self.stream_values().items():
            e = universe.exposure(s)
            for leaf, a in e.coefs.items():
                out[leaf] = out.get(leaf, 0.0) + v * a
            if e.rf_coef:
                out["__rf__"] = out.get("__rf__", 0.0) + v * e.rf_coef
        return out


@dataclass
class Book:
    """A validated book: settings, stream universe, positions, declared totals, named assumptions."""
    name: str
    as_of: str | None
    settings: dict
    universe: Universe
    positions: list
    totals: dict
    assumptions: dict
    source_path: str | None = None
    warnings: list = field(default_factory=list)

    @property
    def total_usd(self) -> float:
        """Sum of value_usd over every position (liabilities negative)."""
        return float(sum(p.value_usd for p in self.positions))

    def view(self, kind: str = "whole", *, include_tags=None, exclude_tags=None, sleeves=None,
             liquidity=None) -> BookView:
        """Filter positions.  kind: 'whole' (all), 'investable' (investable:
        true), 'liquid' (liquidity == liquid).  Then optional tag/sleeve/
        liquidity filters (all must pass).  Raises if the view is empty or has
        non-positive NAV."""
        if kind not in ("whole", "investable", "liquid"):
            raise ValidationError(f"unknown view {kind!r}; use whole, investable or liquid")
        ps = list(self.positions)
        if kind == "investable":
            ps = [p for p in ps if p.investable]
        elif kind == "liquid":
            ps = [p for p in ps if p.liquidity == "liquid"]
        if include_tags:
            inc = set(include_tags)
            ps = [p for p in ps if inc & set(p.tags)]
        if exclude_tags:
            exc = set(exclude_tags)
            ps = [p for p in ps if not exc & set(p.tags)]
        if sleeves:
            ps = [p for p in ps if p.sleeve in set(sleeves)]
        if liquidity:
            ps = [p for p in ps if p.liquidity in set(liquidity)]
        label = kind + "".join([f" +tags{sorted(include_tags)}" if include_tags else "",
                                f" -tags{sorted(exclude_tags)}" if exclude_tags else "",
                                f" sleeves{sorted(sleeves)}" if sleeves else "",
                                f" liq{sorted(liquidity)}" if liquidity else ""])
        if not ps:
            raise ValidationError(f"view {label!r} has no positions")
        tot = float(sum(p.value_usd for p in ps))
        if tot <= 0:
            raise ValidationError(f"view {label!r} has non-positive NAV {tot}")
        return BookView(label, ps, tot)


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def _resolve_refs(obj, named: dict, where: str):
    """Replace "@key" strings by the named assumption dict (recursively)."""
    if isinstance(obj, str) and obj.startswith("@"):
        key = obj[1:]
        if key not in named:
            raise AssumptionError(f"{where}: reference {obj!r} to undefined assumption (have {sorted(named)})")
        return named[key].to_dict()
    if isinstance(obj, dict):
        return {k: _resolve_refs(v, named, f"{where}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_refs(v, named, f"{where}[{i}]") for i, v in enumerate(obj)]
    return obj


def _parse_proxies(name: str, raw) -> tuple:
    """Validate declared proxies: a list of {symbol, until (a date), note?}."""
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValidationError(f"stream {name!r}: proxies must be a list of {{symbol, until, note}} mappings")
    out = []
    for i, p in enumerate(raw):
        where = f"stream {name!r} proxies[{i}]"
        if not isinstance(p, dict):
            raise ValidationError(f"{where}: must be a mapping {{symbol, until, note}}")
        unknown = set(p) - {"symbol", "until", "note"}
        if unknown:
            raise ValidationError(f"{where}: unknown keys {sorted(unknown)}")
        for k in ("symbol", "until"):
            if k not in p or p[k] in (None, ""):
                raise ValidationError(f"{where}: missing {k!r} (a proxy needs an explicit splice date)")
        try:
            until = pd.Timestamp(p["until"])
        except (ValueError, TypeError):
            raise ValidationError(f"{where}: until {p['until']!r} is not a date") from None
        if pd.isna(until):
            raise ValidationError(f"{where}: until {p['until']!r} is not a date")
        out.append(ProxySpec(str(p["symbol"]), until, str(p.get("note", ""))))
    return tuple(out)


def parse_stream(name: str, spec: dict, base_dir: Path | None = None):
    """Build one Stream from its YAML mapping (unknown keys are rejected)."""
    if not isinstance(spec, dict) or "type" not in spec:
        raise ValidationError(f"stream {name!r}: needs a mapping with 'type'")
    t = spec["type"]
    if t not in _STREAM_KEYS:
        raise ValidationError(f"stream {name!r}: unknown type {t!r}; use {sorted(_STREAM_KEYS)}")
    unknown = set(spec) - _COMMON - _STREAM_KEYS[t]
    if unknown:
        raise ValidationError(f"stream {name!r} ({t}): unknown keys {sorted(unknown)}")
    common = {k: spec[k] for k in ("description", "asset_class", "environments", "expected_return",
                                   "liquidity", "mark_basis") if k in spec}
    if t == "market":
        return MarketStream(name=name, symbol=spec.get("symbol", name), proxies=_parse_proxies(name, spec.get("proxies")),
                            **common)
    if t == "series":
        if "path" not in spec:
            raise ValidationError(f"stream {name!r}: series needs 'path'")
        p = Path(spec["path"])
        if not p.is_absolute() and base_dir is not None:
            p = base_dir / p
        return SeriesStream.from_csv(name, p, date_col=spec.get("date_col", "date"),
                                     value_col=spec.get("value_col", "value"), kind=spec.get("kind", "levels"),
                                     source=spec.get("source"), **common)
    if t == "parametric":
        d = spec.get("default")
        dm = None
        if d is not None:
            dm = DefaultModel(Assumption.parse(d.get("prob"), f"{name}.default.prob"),
                              Assumption.parse(d.get("lgd"), f"{name}.default.lgd"),
                              Assumption.parse(d["coupon"], f"{name}.default.coupon") if "coupon" in d else None)
        return ParametricStream(name=name, vol=spec.get("vol"), factor_loadings=spec.get("factor_loadings") or {},
                                factor_correlations=spec.get("factor_correlations") or {},
                                idio_vol=spec.get("idio_vol"), default=dm, **common)
    if t == "cash":
        return CashStream(name=name, rate=spec.get("rate"), **common)
    return CompositeStream(name=name, components=spec["components"], leverage=float(spec.get("leverage", 1.0)),
                           financing_spread=spec.get("financing_spread"), fee=spec.get("fee"),
                           allow_cash_remainder=bool(spec.get("allow_cash_remainder", False)), **common)


def _parse_position(i: int, p: dict, universe: Universe) -> Position:
    where = f"positions[{i}]"
    if not isinstance(p, dict):
        raise ValidationError(f"{where}: must be a mapping")
    allowed = {"name", "value_usd", "stream", "sleeve", "liquidity", "mark_basis", "tags", "investable",
               "liability", "note"}
    unknown = set(p) - allowed
    if unknown:
        raise ValidationError(f"{where}: unknown keys {sorted(unknown)}")
    for k in ("name", "value_usd", "stream"):
        if k not in p:
            raise ValidationError(f"{where}: missing {k!r}")
    name = str(p["name"])
    try:
        v = float(p["value_usd"])
    except (TypeError, ValueError):
        raise ValidationError(f"{where} ({name}): value_usd {p['value_usd']!r} is not a number") from None
    if not math.isfinite(v):
        raise ValidationError(f"{where} ({name}): value_usd is not finite")
    liab = bool(p.get("liability", False))
    if v < 0 and not liab:
        raise ValidationError(f"{where} ({name}): negative value_usd requires liability: true")
    stream = str(p["stream"])
    if stream not in universe:
        raise UnknownStreamError(f"{where} ({name}): unknown stream {stream!r}; defined: {sorted(universe.names)}")
    s = universe[stream]
    liq = p.get("liquidity", s.liquidity)
    mb = p.get("mark_basis", s.mark_basis)
    if liq not in LIQUIDITY:
        raise ValidationError(f"{where} ({name}): liquidity {liq!r} not in {LIQUIDITY}")
    if mb not in MARK_BASIS:
        raise ValidationError(f"{where} ({name}): mark_basis {mb!r} not in {MARK_BASIS}")
    tags = p.get("tags") or []
    if not isinstance(tags, (list, tuple)) or not all(isinstance(t, str) for t in tags):
        raise ValidationError(f"{where} ({name}): tags must be a list of strings")
    return Position(name, v, stream, str(p.get("sleeve", "unassigned")), liq, mb, tuple(tags),
                    bool(p.get("investable", True)), liab, str(p.get("note", "")))


def reconcile(positions: list, totals: dict) -> list:
    """Check declared totals against the positions.  totals.total_usd must
    equal sum(value_usd) and each totals.sleeves[s] the sleeve sum, within
    tolerance_usd (default 1.0).  When sleeves are declared, every sleeve with
    positions must be declared.  Raises ReconciliationError listing every
    mismatch; returns informational notes."""
    if not totals:
        return ["no declared totals: nothing to reconcile against (add totals.total_usd)"]
    if not isinstance(totals, dict):
        raise ValidationError("totals must be a mapping {total_usd, sleeves, tolerance_usd}")
    unknown = set(totals) - {"total_usd", "sleeves", "tolerance_usd"}
    if unknown:
        raise ValidationError(f"totals: unknown keys {sorted(unknown)} (allowed: total_usd, sleeves, tolerance_usd)")
    if "total_usd" not in totals and "sleeves" not in totals:
        raise ReconciliationError("totals declares neither total_usd nor sleeves: nothing to reconcile against "
                                  "(add totals.total_usd)")
    tol = float(totals.get("tolerance_usd", 1.0))
    errs = []
    tot = float(sum(p.value_usd for p in positions))
    if "total_usd" in totals:
        decl = float(totals["total_usd"])
        if abs(decl - tot) > tol:
            errs.append(f"total: declared {decl:,.2f} vs positions {tot:,.2f} (diff {tot - decl:+,.2f})")
    if "sleeves" in totals:
        decl_s = {k: float(v) for k, v in (totals["sleeves"] or {}).items()}
        actual: dict[str, float] = {}
        for p in positions:
            actual[p.sleeve] = actual.get(p.sleeve, 0.0) + p.value_usd
        for s in sorted(set(decl_s) | set(actual)):
            if s not in decl_s:
                errs.append(f"sleeve {s!r}: positions sum {actual[s]:,.2f} but sleeve not declared")
            elif abs(decl_s[s] - actual.get(s, 0.0)) > tol:
                errs.append(f"sleeve {s!r}: declared {decl_s[s]:,.2f} vs positions {actual.get(s, 0.0):,.2f} "
                            f"(diff {actual.get(s, 0.0) - decl_s[s]:+,.2f})")
    if errs:
        raise ReconciliationError("book totals do not reconcile:\n  " + "\n  ".join(errs))
    return []


def book_from_dict(raw: dict, base_dir: Path | None = None, source_path: str | None = None) -> Book:
    """Validate and build a Book from the parsed YAML mapping."""
    if not isinstance(raw, dict):
        raise ValidationError("book must be a mapping")
    unknown = set(raw) - {"name", "as_of", "assumptions", "settings", "streams", "positions", "totals", "notes"}
    if unknown:
        raise ValidationError(f"book: unknown top-level keys {sorted(unknown)}")
    named = {k: Assumption.parse(v, f"assumptions.{k}") for k, v in (raw.get("assumptions") or {}).items()}
    streams_raw = _resolve_refs(copy.deepcopy(raw.get("streams") or {}), named, "streams")
    if not streams_raw:
        raise ValidationError("book defines no streams")
    universe = Universe([parse_stream(n, s, base_dir) for n, s in streams_raw.items()])
    pos_raw = raw.get("positions") or []
    if not pos_raw:
        raise ValidationError("book has no positions")
    positions = [_parse_position(i, p, universe) for i, p in enumerate(pos_raw)]
    names = [p.name for p in positions]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValidationError(f"duplicate position names {dup}")
    totals = raw.get("totals") or {}
    warnings = reconcile(positions, totals)
    settings = _resolve_refs(copy.deepcopy(raw.get("settings") or {}), named, "settings")
    for key in ("risk_free", "financing_spread"):
        val = settings.get(key)
        if val is not None and not (isinstance(val, str) and val.startswith("fred:")):
            settings[key] = Assumption.parse(val, f"settings.{key}")
    return Book(str(raw.get("name", "book")), str(raw["as_of"]) if raw.get("as_of") else None, settings, universe,
                positions, totals, named, source_path, warnings)


def load_book(path: str | Path) -> Book:
    """Load and validate a YAML book; relative series paths resolve against
    the YAML file's directory."""
    p = Path(path)
    if not p.exists():
        raise ValidationError(f"book file {p} not found")
    raw = yaml.safe_load(p.read_text())
    return book_from_dict(raw, base_dir=p.parent, source_path=str(p))
