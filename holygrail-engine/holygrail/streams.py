"""Return streams and the joint moment model.

A Stream is anything with a return distribution:
  MarketStream      ticker -> adjusted total-return series (data.py), with
                    DECLARED proxies only (explicit splice dates)
  SeriesStream      user-supplied NAV / P&L series (Composer symphony, executor)
  ParametricStream  private asset: expected return, vol, factor loadings or
                    correlations to named market streams, idiosyncratic vol,
                    optional default/jump model; every number is an Assumption
                    {value, source, confidence}
  CashStream        zero-vol stream earning rf (or its own stated rate)
  CompositeStream   look-through: weights over other streams, optional leverage
                    multiplier (financed at rf + spread) and fee

Every stream reduces to a LINEAR EXPOSURE over leaf streams:
    r_s = sum_j a_sj r_j + a_rf * rf + const
For a composite with weights w_j, leverage L and gross G = L sum_j w_j:
    r_c = sum_j L w_j r_j + (1 - G) rf - max(G - 1, 0) spread - fee
which is the daily-reset leveraged-ETF model when applied per period.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Iterable

import numpy as np
import pandas as pd

from .core import validate_covariance
from .errors import AssumptionError, UnknownStreamError, ValidationError

CONFIDENCE = ("high", "medium", "low", "placeholder")
LIQUIDITY = ("liquid", "semi", "illiquid")
MARK_BASIS = ("market", "model", "appraisal", "cost", "round")
ENVIRONMENT_BOXES = ("growth_up", "growth_down", "inflation_up", "inflation_down")


# --------------------------------------------------------------------------- #
# assumptions
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Assumption:
    """A number that is NOT measured: value + where it came from + how much we
    trust it.  confidence in {'high','medium','low','placeholder'}."""
    value: float
    source: str
    confidence: str

    def __post_init__(self):
        if not isinstance(self.value, (int, float)) or not math.isfinite(float(self.value)):
            raise AssumptionError(f"assumption value must be a finite number, got {self.value!r}")
        if not isinstance(self.source, str) or not self.source.strip():
            raise AssumptionError("assumption needs a non-empty source")
        if self.confidence not in CONFIDENCE:
            raise AssumptionError(f"assumption confidence must be one of {CONFIDENCE}, got {self.confidence!r}")
        object.__setattr__(self, "value", float(self.value))

    @classmethod
    def parse(cls, obj, what: str = "assumption") -> "Assumption":
        """Accept an Assumption or a mapping {value, source, confidence}; a bare
        number is REJECTED (every assumption must carry a source and confidence)."""
        if isinstance(obj, Assumption):
            return obj
        if isinstance(obj, dict):
            missing = {"value", "source", "confidence"} - set(obj)
            if missing:
                raise AssumptionError(f"{what}: missing {sorted(missing)} (need value, source, confidence)")
            try:
                return cls(obj["value"], obj["source"], obj["confidence"])
            except AssumptionError as e:
                raise AssumptionError(f"{what}: {e}") from None
        raise AssumptionError(f"{what}: every assumption needs {{value, source, confidence}}; got bare {obj!r}")

    def to_dict(self) -> dict:
        """{value, source, confidence}."""
        return {"value": self.value, "source": self.source, "confidence": self.confidence}


def _opt(obj, what):
    return None if obj is None else Assumption.parse(obj, what)


@dataclass(frozen=True)
class ProxySpec:
    """Declared proxy: use ``symbol``'s returns strictly BEFORE ``until``; the
    stream's own series from ``until`` on.  Never inferred."""
    symbol: str
    until: pd.Timestamp
    note: str = ""

    def __post_init__(self):
        object.__setattr__(self, "until", pd.Timestamp(self.until).normalize())


@dataclass(frozen=True)
class DefaultModel:
    """Two-point annual default model for a loan-like stream: no default ->
    return = coupon; default (prob p) -> return = -lgd (no coupon).
        E[r]   = (1 - p) c - p lgd
        Var(r) = p (1 - p) (c + lgd)^2          (lgd^2 if coupon is unknown)
    Jump size per default event = c + lgd (or lgd)."""
    prob: Assumption
    lgd: Assumption
    coupon: Assumption | None = None

    def __post_init__(self):
        if not 0 <= self.prob.value < 1:
            raise AssumptionError(f"default prob must be in [0, 1), got {self.prob.value}")
        if not 0 <= self.lgd.value <= 1:
            raise AssumptionError(f"lgd must be in [0, 1], got {self.lgd.value}")

    @property
    def loss(self) -> float:
        """Return shortfall in a default year vs the no-default year."""
        return self.lgd.value + (self.coupon.value if self.coupon else 0.0)

    @property
    def jump_variance(self) -> float:
        """p (1 - p) loss^2, loss = lgd + coupon (or lgd)."""
        p = self.prob.value
        return p * (1 - p) * self.loss ** 2

    def expected_return(self) -> float:
        """(1 - p) coupon - p lgd (requires a coupon)."""
        if self.coupon is None:
            raise AssumptionError("expected return from a default model needs a coupon")
        p = self.prob.value
        return (1 - p) * self.coupon.value - p * self.lgd.value


# --------------------------------------------------------------------------- #
# streams
# --------------------------------------------------------------------------- #
@dataclass(kw_only=True)
class Stream:
    """Base: name + metadata shared by every stream."""
    name: str
    description: str = ""
    asset_class: str | None = None
    environments: tuple | None = None      # manual All Weather box mapping
    expected_return: Assumption | None = None
    liquidity: str = "liquid"
    mark_basis: str = "market"
    kind: ClassVar[str] = "base"
    empirical: ClassVar[bool] = False

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValidationError("stream name must be a non-empty string")
        if self.liquidity not in LIQUIDITY:
            raise ValidationError(f"{self.name}: liquidity must be one of {LIQUIDITY}")
        if self.mark_basis not in MARK_BASIS:
            raise ValidationError(f"{self.name}: mark_basis must be one of {MARK_BASIS}")
        if self.environments is not None:
            env = tuple(self.environments)
            bad = [e for e in env if e not in ENVIRONMENT_BOXES]
            if bad:
                raise ValidationError(f"{self.name}: unknown environments {bad}; use {ENVIRONMENT_BOXES}")
            self.environments = env
        self.expected_return = _opt(self.expected_return, f"{self.name}.expected_return")


@dataclass(kw_only=True)
class MarketStream(Stream):
    """Listed instrument: Yahoo adjusted close (split + dividend adjusted)."""
    symbol: str
    proxies: tuple = ()
    kind: ClassVar[str] = "market"
    empirical: ClassVar[bool] = True

    def __post_init__(self):
        super().__post_init__()
        if not self.symbol:
            raise ValidationError(f"{self.name}: symbol required")
        self.proxies = tuple(p if isinstance(p, ProxySpec) else ProxySpec(**p) for p in self.proxies)


def _check_level_series(s: pd.Series, what: str) -> pd.Series:
    if not isinstance(s, pd.Series) or not isinstance(s.index, pd.DatetimeIndex):
        raise ValidationError(f"{what}: levels must be a Series with a DatetimeIndex")
    s = s.astype(float).sort_index()
    if s.index.has_duplicates:
        raise ValidationError(f"{what}: duplicate dates")
    if s.isna().any() or np.isinf(s).any():
        raise ValidationError(f"{what}: NaN/inf in levels")
    if (s <= 0).any():
        raise ValidationError(f"{what}: levels must be > 0")
    if len(s) < 3:
        raise ValidationError(f"{what}: need at least 3 observations")
    return s


@dataclass(kw_only=True)
class SeriesStream(Stream):
    """User-supplied NAV/level series (e.g. a Composer symphony's NAV, an
    executor's equity).  ``source`` records where it came from."""
    levels: pd.Series
    source: str
    kind: ClassVar[str] = "series"
    empirical: ClassVar[bool] = True

    def __post_init__(self):
        super().__post_init__()
        if not self.source:
            raise ValidationError(f"{self.name}: source required for a series stream")
        self.levels = _check_level_series(self.levels, self.name)

    @classmethod
    def from_returns(cls, name: str, returns: pd.Series, source: str, **kw) -> "SeriesStream":
        """Build from simple returns: level 1.0 one period before the first
        return, then L_t = prod (1 + r)."""
        r = pd.Series(returns, dtype=float).dropna().sort_index()
        if (r <= -1).any():
            raise ValidationError(f"{name}: return <= -100%")
        step = pd.Series(r.index).diff().median()
        lv = pd.concat([pd.Series([1.0], index=[r.index[0] - step]), (1 + r).cumprod()])
        return cls(name=name, levels=lv, source=source, **kw)

    @classmethod
    def from_csv(cls, name: str, path: str | Path, *, date_col: str = "date", value_col: str = "value",
                 kind: str = "levels", source: str | None = None, **kw) -> "SeriesStream":
        """Load a CSV with a date column and a level (or return) column."""
        p = Path(path)
        if not p.exists():
            raise ValidationError(f"{name}: series file {p} not found")
        df = pd.read_csv(p)
        for col in (date_col, value_col):
            if col not in df.columns:
                raise ValidationError(f"{name}: column {col!r} not in {p} (have {list(df.columns)})")
        s = pd.Series(pd.to_numeric(df[value_col], errors="raise").to_numpy(),
                      index=pd.DatetimeIndex(pd.to_datetime(df[date_col])).normalize())
        src = source or f"csv:{p}"
        if kind == "levels":
            return cls(name=name, levels=s, source=src, **kw)
        if kind == "returns":
            return cls.from_returns(name, s, src, **kw)
        raise ValidationError(f"{name}: kind must be 'levels' or 'returns'")


@dataclass(kw_only=True)
class ParametricStream(Stream):
    """Private / non-marked asset described by assumptions.

    Exactly one risk mode:
      loadings     factor_loadings {factor: beta} + idio_vol  -> vol derived
      correlations vol + factor_correlations {factor: rho}    -> betas solved,
                   idio vol = residual (fails if the rhos imply R^2 > 1)
      standalone   vol only -> uncorrelated with every other stream (stated)
    ``vol`` is TOTAL vol including the default jump; ``default`` adds the jump
    variance in loadings mode.  Factors must be empirical streams."""
    vol: Assumption | None = None
    factor_loadings: dict = field(default_factory=dict)
    factor_correlations: dict = field(default_factory=dict)
    idio_vol: Assumption | None = None
    default: DefaultModel | None = None
    liquidity: str = "illiquid"
    mark_basis: str = "model"
    kind: ClassVar[str] = "parametric"

    def __post_init__(self):
        super().__post_init__()
        n = self.name
        self.vol = _opt(self.vol, f"{n}.vol")
        self.idio_vol = _opt(self.idio_vol, f"{n}.idio_vol")
        self.factor_loadings = {k: Assumption.parse(v, f"{n}.factor_loadings.{k}") for k, v in self.factor_loadings.items()}
        self.factor_correlations = {k: Assumption.parse(v, f"{n}.factor_correlations.{k}")
                                    for k, v in self.factor_correlations.items()}
        if self.default is not None and not isinstance(self.default, DefaultModel):
            d = self.default
            self.default = DefaultModel(Assumption.parse(d.get("prob"), f"{n}.default.prob"),
                                        Assumption.parse(d.get("lgd"), f"{n}.default.lgd"),
                                        _opt(d.get("coupon"), f"{n}.default.coupon"))
        if self.factor_loadings and self.factor_correlations:
            raise AssumptionError(f"{n}: give factor_loadings OR factor_correlations, not both")
        if self.factor_loadings:
            if self.idio_vol is None or self.vol is not None:
                raise AssumptionError(f"{n}: loadings mode needs idio_vol and no vol (vol is derived)")
        else:
            if self.vol is None or self.idio_vol is not None:
                raise AssumptionError(f"{n}: correlations/standalone mode needs vol and no idio_vol")
            if self.vol.value < 0:
                raise AssumptionError(f"{n}: vol must be >= 0")
        for k, a in self.factor_correlations.items():
            if not -1 <= a.value <= 1:
                raise AssumptionError(f"{n}: correlation to {k} = {a.value} outside [-1, 1]")
        if self.idio_vol is not None and self.idio_vol.value < 0:
            raise AssumptionError(f"{n}: idio_vol must be >= 0")
        if self.expected_return is None:
            if self.default is not None and self.default.coupon is not None:
                self.expected_return = Assumption(
                    self.default.expected_return(),
                    f"derived: (1-p)*coupon - p*lgd from {n}.default", self._weakest_conf())
            else:
                raise AssumptionError(f"{n}: parametric stream needs expected_return (or default with coupon)")

    def _weakest_conf(self) -> str:
        d = self.default
        confs = [d.prob.confidence, d.lgd.confidence] + ([d.coupon.confidence] if d.coupon else [])
        return max(confs, key=CONFIDENCE.index)

    @property
    def mode(self) -> str:
        """'loadings' | 'correlations' | 'standalone'."""
        return "loadings" if self.factor_loadings else "correlations" if self.factor_correlations else "standalone"

    @property
    def factors(self) -> list:
        """Sorted factor stream names referenced by loadings or correlations."""
        return sorted(self.factor_loadings or self.factor_correlations)

    def assumptions(self) -> dict:
        """Flat {label: Assumption} for the honesty block."""
        out = {"expected_return": self.expected_return}
        if self.vol: out["vol"] = self.vol
        if self.idio_vol: out["idio_vol"] = self.idio_vol
        for k, a in self.factor_loadings.items(): out[f"beta[{k}]"] = a
        for k, a in self.factor_correlations.items(): out[f"rho[{k}]"] = a
        if self.default:
            out["default.prob"] = self.default.prob
            out["default.lgd"] = self.default.lgd
            if self.default.coupon: out["default.coupon"] = self.default.coupon
        return out


@dataclass(kw_only=True)
class CashStream(Stream):
    """Cash: zero volatility, earns ``rate`` if given, else the universe rf."""
    rate: Assumption | None = None
    kind: ClassVar[str] = "cash"

    def __post_init__(self):
        super().__post_init__()
        self.rate = _opt(self.rate, f"{self.name}.rate")


@dataclass(kw_only=True)
class CompositeStream(Stream):
    """Look-through blend of other streams with optional leverage and fees.
    Weights must sum to 1 (or <= 1 with allow_cash_remainder: the rest earns
    rf).  Borrowing (L * sum w > 1) REQUIRES a financing_spread assumption."""
    components: dict
    leverage: float = 1.0
    financing_spread: Assumption | None = None
    fee: Assumption | None = None
    allow_cash_remainder: bool = False
    kind: ClassVar[str] = "composite"

    def __post_init__(self):
        super().__post_init__()
        n = self.name
        if not self.components:
            raise ValidationError(f"{n}: composite needs components")
        comps = {}
        for k, v in self.components.items():
            v = float(v)
            if not math.isfinite(v):
                raise ValidationError(f"{n}: weight of {k} is not finite")
            comps[str(k)] = v
        self.components = comps
        s = sum(comps.values())
        if self.allow_cash_remainder:
            if s > 1 + 1e-9:
                raise ValidationError(f"{n}: component weights sum to {s:.6f} > 1")
        elif abs(s - 1) > 1e-9:
            raise ValidationError(f"{n}: component weights sum to {s:.9f}, expected 1 (set allow_cash_remainder)")
        if not (math.isfinite(self.leverage) and self.leverage > 0):
            raise ValidationError(f"{n}: leverage must be finite and > 0")
        self.financing_spread = _opt(self.financing_spread, f"{n}.financing_spread")
        self.fee = _opt(self.fee, f"{n}.fee")
        if self.leverage * s > 1 + 1e-12 and self.financing_spread is None:
            raise AssumptionError(f"{n}: borrows (gross {self.leverage * s:.2f}x) but has no financing_spread assumption")


# --------------------------------------------------------------------------- #
# universe and exposures
# --------------------------------------------------------------------------- #
@dataclass
class Exposure:
    """r_s = sum_j coefs[j] r_j + rf_coef * rf + const (annual)."""
    coefs: dict
    rf_coef: float = 0.0
    const: float = 0.0


class Universe:
    """A validated set of streams: unique names, every reference (composite
    component, parametric factor) defined, no composite cycles, parametric
    factors resolve to empirical leaves only."""

    def __init__(self, streams: Iterable[Stream]):
        self._s: dict[str, Stream] = {}
        for s in streams:
            if not isinstance(s, Stream):
                raise ValidationError(f"not a Stream: {s!r}")
            if s.name in self._s:
                raise ValidationError(f"duplicate stream name {s.name!r}")
            self._s[s.name] = s
        self._exp: dict[str, Exposure] = {}
        for s in self._s.values():
            if isinstance(s, CompositeStream):
                for c in s.components:
                    self[c]
            if isinstance(s, ParametricStream):
                for f in s.factors:
                    self[f]
        for name in self._s:
            self.exposure(name)
        for s in self._s.values():
            if isinstance(s, ParametricStream):
                for f in s.factors:
                    bad = [l for l in self.exposure(f).coefs if not self._s[l].empirical]
                    if bad:
                        raise ValidationError(f"{s.name}: factor {f!r} must be empirical; it contains {bad}")

    def __getitem__(self, name: str) -> Stream:
        try:
            return self._s[name]
        except KeyError:
            raise UnknownStreamError(f"unknown stream {name!r}; defined streams: {sorted(self._s)}") from None

    def __contains__(self, name) -> bool:
        return name in self._s

    @property
    def names(self) -> list:
        """All stream names."""
        return list(self._s)

    def exposure(self, name: str, _stack: tuple = ()) -> Exposure:
        """Linear exposure of ``name`` over leaf streams (see module docstring)."""
        if name in self._exp:
            return self._exp[name]
        if name in _stack:
            raise ValidationError(f"composite cycle: {' -> '.join(_stack + (name,))}")
        s = self[name]
        if isinstance(s, CashStream):
            e = Exposure({}, 0.0, s.rate.value) if s.rate else Exposure({}, 1.0, 0.0)
        elif isinstance(s, CompositeStream):
            coefs: dict[str, float] = {}
            rf_coef = const = 0.0
            for c, wc in s.components.items():
                sub = self.exposure(c, _stack + (name,))
                k = s.leverage * wc
                for leaf, a in sub.coefs.items():
                    coefs[leaf] = coefs.get(leaf, 0.0) + k * a
                rf_coef += k * sub.rf_coef
                const += k * sub.const
            gross = s.leverage * sum(s.components.values())
            rf_coef += 1.0 - gross
            if gross > 1:
                const -= (gross - 1.0) * s.financing_spread.value
            if s.fee:
                const -= s.fee.value
            e = Exposure(coefs, rf_coef, const)
        else:
            e = Exposure({name: 1.0})
        self._exp[name] = e
        return e

    def leaves(self, names: Iterable[str]) -> tuple[list, list]:
        """(empirical_leaves, parametric_leaves) needed to model ``names``,
        including the factor streams of parametric leaves."""
        emp, par = [], []
        for n in names:
            for leaf in self.exposure(n).coefs:
                s = self[leaf]
                if s.empirical and leaf not in emp:
                    emp.append(leaf)
                elif isinstance(s, ParametricStream) and leaf not in par:
                    par.append(leaf)
        for p in par:
            for f in self[p].factors:
                for leaf in self.exposure(f).coefs:
                    if leaf not in emp:
                        emp.append(leaf)
        return emp, par

    def series_returns(self, name: str, leaf_returns: pd.DataFrame, rf_period: pd.Series | float,
                       periods_per_year: float, *, year_fraction: pd.Series | None = None) -> pd.Series:
        """Per-period return series of any non-parametric stream from its
        leaves' per-period returns: r_t = sum a_j r_jt + a_rf rf_t + const * tau_t
        with tau_t = 1/q, or the period's length in years when
        ``year_fraction`` is given (calendar-day accrual: a fee or financing
        spread then costs its annual rate per calendar year on any calendar).
        On DAILY inputs this is the daily-reset leveraged-fund model."""
        e = self.exposure(name)
        missing = [l for l in e.coefs if l not in leaf_returns.columns]
        if missing:
            par = [l for l in missing if isinstance(self[l], ParametricStream)]
            if par:
                raise ValidationError(f"{name}: parametric leaves {par} have no history; cannot build a series")
            raise ValidationError(f"{name}: leaf returns missing for {missing}")
        r = pd.Series(0.0, index=leaf_returns.index)
        for leaf, a in e.coefs.items():
            r = r + a * leaf_returns[leaf]
        rf = rf_period if isinstance(rf_period, pd.Series) else pd.Series(float(rf_period), index=leaf_returns.index)
        rf = rf.reindex(leaf_returns.index)
        if e.rf_coef != 0 and rf.isna().any():
            raise ValidationError(f"{name}: rf series missing dates")
        if year_fraction is not None:
            tau = pd.Series(year_fraction, dtype=float).reindex(leaf_returns.index)
            if tau.isna().any():
                raise ValidationError(f"{name}: year_fraction missing dates")
        else:
            tau = 1.0 / periods_per_year
        r = r + e.rf_coef * rf.fillna(0.0) + e.const * tau
        return r.rename(name)


# --------------------------------------------------------------------------- #
# joint moments
# --------------------------------------------------------------------------- #
@dataclass
class Moments:
    """Annualised joint moments of ``names`` plus the leaf ("base") model they
    are built from.  cov = A base_cov A';  mu = A base_mu + rf_coef rf + const
    (overridden by a stream's own expected_return assumption)."""
    names: list
    mu: np.ndarray
    cov: np.ndarray
    rf: float
    mu_basis: dict
    base_names: list
    base_mu: np.ndarray
    base_cov: np.ndarray
    A: np.ndarray
    rf_coef: np.ndarray
    const: np.ndarray
    jumps: list
    estimate: object
    parametric: dict
    notes: list

    @property
    def vol(self) -> np.ndarray:
        """sqrt(diag(cov)), annual."""
        return np.sqrt(np.clip(np.diag(self.cov), 0, None))

    def corr(self) -> np.ndarray:
        """Correlation matrix cov_ij / (vol_i vol_j); zero-vol rows/cols set to 0 (unit diagonal)."""
        v = self.vol
        with np.errstate(invalid="ignore", divide="ignore"):
            C = self.cov / np.outer(v, v)
        C[~np.isfinite(C)] = 0.0
        np.fill_diagonal(C, 1.0)
        return C

    def index(self, name: str) -> int:
        """Position of ``name`` in names (UnknownStreamError if absent)."""
        try:
            return self.names.index(name)
        except ValueError:
            raise UnknownStreamError(f"{name!r} not in moments ({self.names})") from None

    def look_through(self, w) -> tuple[np.ndarray, float]:
        """Map stream weights w to base (leaf) weights x = A'w and the constant
        annual drift c = w'(rf_coef rf + const)."""
        w = np.asarray(w, float)
        return self.A.T @ w, float(w @ (self.rf_coef * self.rf + self.const))

    def base_diffusive_cov(self) -> np.ndarray:
        """base_cov minus the default-jump variances p(1-p) loss^2 (for
        jump-diffusion MC).  forward.simulate_returns draws at most one default
        per year, whose annual variance is exactly this term, so diffusive +
        jump variance equals the declared vol."""
        S = self.base_cov.copy()
        for j in self.jumps:
            S[j["base_index"], j["base_index"]] -= j["jump_variance"]
        return S


def build_moments(universe: Universe, names: list, *, returns: pd.DataFrame | None, periods_per_year: float,
                  rf: float, method: str = "lw_cc", history: str = "common", halflife: float | None = None,
                  lags: int = 0, mu_mode: str = "assumption_or_history", min_periods: int = 20) -> Moments:
    """Annualised (mu, cov) for ``names``.

    Empirical leaves: covariance from ``returns`` (per-period simple returns of
    the empirical leaves, already windowed) via estimate.estimate_cov; mean =
    the stream's expected_return assumption if present (basis 'assumption'),
    else the historical mean x periods_per_year (basis 'historical_in_sample',
    NOT a forecast).  mu_mode 'history' ignores assumptions, 'assumption'
    requires them.
    Parametric leaves (factor model, F = factor returns):
      loadings:     r_p = alpha + beta'F + e;  var = beta'S_FF beta + idio^2 + jump
      correlations: Cov(F, p) = rho sigma_p sigma_F;  beta = S_FF^{-1} Cov(F, p);
                    idio^2 = sigma_p^2 - beta'S_FF beta - jump  (must be >= 0)
      standalone:   uncorrelated, var = sigma_p^2
    Cov(p, j) = beta' Cov(F, j); idiosyncratic terms independent across streams."""
    from .estimate import estimate_cov  # local import keeps module graph flat

    if mu_mode not in ("assumption_or_history", "history", "assumption"):
        raise ValidationError(f"unknown mu_mode {mu_mode!r}")
    for n in names:
        universe[n]
    emp, par = universe.leaves(names)
    est = None
    notes = []
    if emp:
        if returns is None:
            raise ValidationError(f"history needed for empirical streams {emp}")
        missing = [e for e in emp if e not in returns.columns]
        if missing:
            raise ValidationError(f"returns missing columns for empirical streams {missing}")
        est = estimate_cov(returns[emp], method, history=history, periods_per_year=periods_per_year,
                           halflife=halflife, lags=lags, min_periods=min_periods)
        S_E = est.annual
        hist_mu = est.annual_mean
    else:
        S_E = np.zeros((0, 0))
        hist_mu = np.zeros(0)
    base = emp + par
    nb = len(base)
    ne = len(emp)
    S = np.zeros((nb, nb))
    S[:ne, :ne] = S_E
    G = np.zeros((len(par), ne))  # factor loadings expressed on empirical leaves
    idio = np.zeros(len(par))
    jumps = []
    pinfo = {}
    for k, p in enumerate(par):
        s: ParametricStream = universe[p]
        jv = s.default.jump_variance if s.default else 0.0
        if s.mode == "standalone":
            idio2 = s.vol.value ** 2 - jv
            betas = {}
        else:
            Arows = np.zeros((len(s.factors), ne))
            for r_i, f in enumerate(s.factors):
                for leaf, a in universe.exposure(f).coefs.items():
                    Arows[r_i, emp.index(leaf)] += a
            S_FF = Arows @ S_E @ Arows.T
            if s.mode == "loadings":
                beta = np.array([s.factor_loadings[f].value for f in s.factors])
                idio2 = s.idio_vol.value ** 2
            else:
                sF = np.sqrt(np.diag(S_FF))
                rho = np.array([s.factor_correlations[f].value for f in s.factors])
                cFp = rho * s.vol.value * sF
                try:
                    beta = np.linalg.solve(S_FF, cFp)
                except np.linalg.LinAlgError:
                    raise AssumptionError(f"{p}: factor covariance is singular; cannot solve betas") from None
                idio2 = s.vol.value ** 2 - float(beta @ S_FF @ beta) - jv
                r2 = float(beta @ S_FF @ beta) / s.vol.value ** 2 if s.vol.value > 0 else float("inf")
                if idio2 < -1e-12:
                    jshare = jv / s.vol.value ** 2 if s.vol.value > 0 else float("inf")
                    raise AssumptionError(
                        f"{p}: inconsistent assumptions - factor R^2 {r2:.3f} (from correlations "
                        f"{dict(zip(s.factors, rho.tolist()))}) + default-jump share {jshare:.3f} of the stated "
                        f"variance = {r2 + jshare:.3f} > 1; raise vol or lower the correlations/default risk")
            G[k] = Arows.T @ beta
            betas = dict(zip(s.factors, beta.tolist()))
        if idio2 < -1e-12:
            raise AssumptionError(f"{p}: vol {s.vol.value} is below the default-jump vol {math.sqrt(jv):.4f}")
        idio[k] = max(idio2, 0.0)
        if s.default:
            jumps.append({"name": p, "base_index": ne + k, "prob": s.default.prob.value,
                          "loss": s.default.loss, "jump_variance": jv})
        pinfo[p] = {"mode": s.mode, "betas_on_factors": betas, "idio_vol": math.sqrt(idio[k]),
                    "jump_vol": math.sqrt(jv)}
    if par:
        S[ne:, :ne] = G @ S_E
        S[:ne, ne:] = S[ne:, :ne].T
        S[ne:, ne:] = G @ S_E @ G.T + np.diag(idio + np.array([universe[p].default.jump_variance if universe[p].default else 0.0
                                                               for p in par]))
    S = validate_covariance(S, name="base covariance")
    mu_b = np.zeros(nb)
    basis = {}
    for i, e in enumerate(emp):
        a = universe[e].expected_return
        if mu_mode == "history" or (a is None and mu_mode == "assumption_or_history"):
            mu_b[i] = hist_mu[i]
            basis[e] = "historical_in_sample"
        elif a is None:
            raise AssumptionError(f"{e}: mu_mode='assumption' but no expected_return assumption")
        else:
            mu_b[i] = a.value
            basis[e] = "assumption"
    for k, p in enumerate(par):
        mu_b[ne + k] = universe[p].expected_return.value
        basis[p] = "assumption"
    A = np.zeros((len(names), nb))
    rfc = np.zeros(len(names))
    const = np.zeros(len(names))
    mu = np.zeros(len(names))
    mu_basis = {}
    for r_i, n in enumerate(names):
        e = universe.exposure(n)
        for leaf, a in e.coefs.items():
            A[r_i, base.index(leaf)] = a
        rfc[r_i], const[r_i] = e.rf_coef, e.const
        own = universe[n].expected_return
        if own is not None and mu_mode != "history":
            mu[r_i] = own.value
            mu_basis[n] = "assumption"
        else:
            mu[r_i] = A[r_i] @ mu_b + rfc[r_i] * rf + const[r_i]
            leaf_b = {basis[l] for l in e.coefs}
            if not e.coefs:
                mu_basis[n] = "cash (rf)" if e.rf_coef else "assumption"
            elif len(e.coefs) == 1 and next(iter(e.coefs)) == n:
                mu_basis[n] = basis[n]
            else:
                mu_basis[n] = "look-through of " + "/".join(sorted(leaf_b))
    cov = validate_covariance(A @ S @ A.T, name="stream covariance")
    if any(v == "historical_in_sample" for v in mu_basis.values()) or any(
            "historical" in v for v in mu_basis.values()):
        notes.append("some expected returns are historical in-sample means, not forecasts")
    return Moments(list(names), mu, cov, float(rf), mu_basis, base, mu_b, S, A, rfc, const, jumps, est, pinfo, notes)
