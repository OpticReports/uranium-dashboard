"""Adapters for the foundation forecasters.

TORCH IS NOT A DEPENDENCY OF THIS SERVICE AND MUST NOT BECOME ONE. Every
import here is lazy and every adapter fails with an instruction rather than
an ImportError traceback. The paper engine decides trades; a container that
executes or informs trades does not get a 2GB machine-learning stack added
to it so a research script can run. Install requirements-research.txt in a
separate environment.

WHAT WE FEED THEM, AND WHY IT IS NOT CLOSES. Stage 1a found that the whole
baseline ranking was explained by the INPUT: the same EWMA recursion moved
from +3.7% to +0.1% against ATR when fed a range estimate instead of
closes. A model handed a series of closes therefore starts ~3.6% behind
before it forecasts anything. So these adapters are fed the per-bar
Parkinson volatility series and asked to forecast it forward; the window
forecast is the RMS of the predicted path, because variance is what
aggregates over a window, not volatility.

WHAT THIS DISCARDS, STATED PLAINLY. Aggregating H steps into one window
number means the model's native nine quantiles cannot be carried through -
quantiles of a sum are not the sum of quantiles. So the median path is
taken as the point forecast and the SAME TRAIN-fitted spread every baseline
gets is applied on top. That makes the comparison fair and it throws away
the models' own uncertainty estimate, which is one of the two things they
are actually selling. `native_quantiles_1step` exists to score that part
separately rather than pretend it was tested.
"""
from __future__ import annotations

import numpy as np

from .models import parkinson_sigma

CHRONOS_ID = "amazon/chronos-2"
TIMESFM_ID = "google/timesfm-3.0-pytorch"


class AdapterUnavailable(RuntimeError):
    """Raised with what to install, not what went wrong internally."""


class FMAdapter:
    """Interface every candidate implements.

    predict_sigma(series, idx, horizon) -> array aligned with idx, giving
    the forecast window volatility made using data up to and INCLUDING each
    index. No adapter may look past its index; that is asserted in tests
    with a fake, because it is the one bug that would make the whole study
    a fiction."""

    name = "abstract"

    def predict_sigma(self, series: np.ndarray, idx: np.ndarray,
                      horizon: int) -> np.ndarray:
        raise NotImplementedError


def _rms(path: np.ndarray) -> float:
    """Variance aggregates over a window; volatility does not."""
    return float(np.sqrt(np.mean(np.square(path))))


class _HFAdapter(FMAdapter):
    """Shared context-window handling and batching for both HuggingFace
    models. Context is capped so a forecast late in the sample does not get
    a 10,000-point history while an early one gets 200 - a difference in
    context length is a difference in model, and it would confound the
    comparison across the sample."""

    context = 512

    def _forecast(self, ctx_batch: list, horizon: int) -> np.ndarray:
        raise NotImplementedError

    def predict_sigma(self, series: np.ndarray, idx: np.ndarray,
                      horizon: int) -> np.ndarray:
        out = np.full(idx.size, np.nan)
        batch, rows = [], []
        for j, t in enumerate(idx):
            lo = max(0, t - self.context + 1)
            ctx = series[lo:t + 1]          # INCLUSIVE of t, never beyond
            ctx = ctx[np.isfinite(ctx)]
            if ctx.size < 32:
                continue
            batch.append(ctx)
            rows.append(j)
            if len(batch) >= 32:
                out[rows] = [_rms(p) for p in self._forecast(batch, horizon)]
                batch, rows = [], []
        if batch:
            out[rows] = [_rms(p) for p in self._forecast(batch, horizon)]
        return out


class Chronos2(_HFAdapter):
    """Amazon Chronos-2, 120M, Apache 2.0. The one with no licence
    restriction, and the one that fits a 2GB box."""

    name = "Chronos-2"

    def __init__(self, device: str = "cpu") -> None:
        try:
            from chronos import BaseChronosPipeline
        except ImportError as exc:      # pragma: no cover - env dependent
            raise AdapterUnavailable(
                "chronos-forecasting is not installed. pip install -r "
                "research/forecast_fm/requirements-research.txt in a "
                "SEPARATE environment - not into any deployed service."
            ) from exc
        self.pipe = BaseChronosPipeline.from_pretrained(CHRONOS_ID,
                                                        device_map=device)

    def _forecast(self, ctx_batch, horizon):  # pragma: no cover - needs weights
        import torch
        q, _ = self.pipe.predict_quantiles(
            context=[torch.tensor(c, dtype=torch.float32) for c in ctx_batch],
            prediction_length=horizon, quantile_levels=[0.5])
        return [x[:, 0].numpy() for x in q]


class TimesFM3(_HFAdapter):
    """Google TimesFM-3, 330M. Non-commercial licence - see the study doc
    section 8; recorded there, not re-argued here."""

    name = "TimesFM-3"

    def __init__(self, device: str = "cpu") -> None:
        try:
            import timesfm
        except ImportError as exc:      # pragma: no cover - env dependent
            raise AdapterUnavailable(
                "timesfm is not installed. pip install -r "
                "research/forecast_fm/requirements-research.txt in a "
                "SEPARATE environment - not into any deployed service."
            ) from exc
        self.model = timesfm.TimesFM_3p0_330M(backend=device)

    def _forecast(self, ctx_batch, horizon):  # pragma: no cover - needs weights
        point, _ = self.model.forecast(inputs=list(ctx_batch),
                                       freq=[0] * len(ctx_batch))
        return [p[:horizon] for p in point]


def input_series(bars: dict) -> np.ndarray:
    """The series every adapter is fed: per-bar Parkinson volatility.

    Not closes, and not returns. Stage 1a finding 2 is the reason, and
    handing these models the same handicapped input the losing baselines
    had would have measured the input and reported it as a model result."""
    return parkinson_sigma(bars)


def available(device: str = "cpu") -> list:
    """Whichever adapters this environment can actually construct. An
    absent model is skipped and NAMED, never silently dropped - a bake-off
    that quietly ran fewer models than it printed would be worse than one
    that failed."""
    out, missing = [], []
    for cls in (Chronos2, TimesFM3):
        try:
            out.append(cls(device=device))
        except AdapterUnavailable as exc:
            missing.append(f"{cls.name}: {exc}")
    if missing:
        print("SKIPPED (not installed):\n  " + "\n  ".join(missing))
    return out
