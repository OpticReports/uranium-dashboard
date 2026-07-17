"""Multiple-testing corrections across the trial registry.

Holm (1979) step-down Bonferroni: sort p-values ascending; adjusted
p_(i) = max over j<=i of (m - j + 1) * p_(j), clipped to 1. Controls FWER at
level α with strictly more power than plain Bonferroni.
"""
from __future__ import annotations

import numpy as np


def holm_bonferroni(p_values: list[float] | np.ndarray) -> np.ndarray:
    """Adjusted p-values (same order as the input)."""
    p = np.asarray(p_values, dtype=float)
    if p.size == 0:
        return p
    if np.any((p < 0) | (p > 1) | ~np.isfinite(p)):
        raise ValueError("p-values must be finite and in [0, 1]")
    m = p.size
    order = np.argsort(p)
    adj_sorted = np.clip(np.maximum.accumulate((m - np.arange(m)) * p[order]), 0, 1)
    out = np.empty(m)
    out[order] = adj_sorted
    return out
