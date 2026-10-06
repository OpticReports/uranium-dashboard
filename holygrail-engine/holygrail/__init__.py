"""Dalio Holy Grail engine (forward + backtest).

Framework: Ray Dalio's "Holy Grail of investing" - 15 good, uncorrelated,
risk-balanced return streams geared to a desired volatility.  Unrelated to
the Composer HG symphony (a 3x-momentum strategy that happens to share the
name).

Modules: core (math), estimate (covariances), streams (return streams +
joint moments), data (Yahoo/FRED + cache), book (YAML book), allocate,
backtest, forward, robustness, environments, scorecard, report, cli.
"""
__version__ = "0.1.0"
