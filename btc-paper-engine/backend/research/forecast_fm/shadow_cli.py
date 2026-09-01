"""Daily forward-shadow run. Nobody executes this by hand - a timer does.

    python -m research.forecast_fm.shadow_cli --log ~/fm-shadow/forecasts.jsonl

Three things happen, in this order and for a reason:

  1. RESOLVE first. Windows that have closed since the last run get their
     outcome filled in. Doing this before forecasting means the file on
     disk is always as complete as the data allows, even if the forecast
     step then fails.
  2. FORECAST at the most recent bar whose window has NOT yet closed. That
     is the only honest place to stand: forecasting at an older bar whose
     outcome is already knowable would be scoring a memory.
  3. SCORE and print what has accumulated.

Bars come from the paper engine's public /bars - the same series the books
trade on, so the shadow is measured against the data the decision would
have used, not a different vendor's version of BTC.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

import numpy as np

from . import data as D
from . import models as Mod
from . import shadow as S

ENGINE = os.environ.get("ENGINE_URL", "https://btc-paper-engine.onrender.com")


def fetch_bars(limit: int = 900, url: str | None = None) -> dict:
    """Recent 4h bars from the engine. 900 bars ~ 5 months, comfortably more
    than any adapter's 512-bar context."""
    u = f"{(url or ENGINE).rstrip('/')}/bars?limit={limit}"
    with urllib.request.urlopen(u, timeout=60) as r:
        rows = json.loads(r.read())
    if not rows:
        raise RuntimeError(f"{u} returned no bars")
    out = {k: np.array([float(x[k]) for x in rows]) for k in
           ("open", "high", "low", "close")}
    out["ts"] = np.array([int(x["ts"]) for x in rows], dtype=np.int64)
    if np.any(np.diff(out["ts"]) <= 0):
        raise RuntimeError("engine returned bars out of order")
    return out


def latest_open_index(bars: dict, horizon: int, now: int) -> int:
    """The newest bar whose forecast window has NOT closed yet.

    Forecasting at a bar whose outcome is already determined is not a
    forecast, and it is the single easiest way for a shadow record to
    quietly become a backtest."""
    end = bars["ts"] + horizon * D.BAR_SECONDS
    open_ = np.flatnonzero(end > now)
    if open_.size == 0:
        raise RuntimeError("every bar's window has already closed; the feed "
                           "is stale")
    return int(open_[0] if open_[0] == 0 else open_[0])


def forecasts_at(bars: dict, i: int, horizon: int, device: str = "cpu") -> dict:
    """{model name: nine quantiles} for the bar at index i.

    The incumbent is always included. A shadow record of only the
    challengers could not answer the question that matters, which is not
    "is the model good" but "is it better than what we already run"."""
    out = {}
    series = None
    atr = D.trailing_atr_frac(bars)
    r = D.log_returns(bars["close"])
    y = D.forward_realized_vol(bars["close"], horizon)

    # The spread is fitted on this window's OWN history, which is all a live
    # job has. It is refitted every run by design: a spread frozen months
    # ago would silently drift out of calibration and the score would blame
    # the model.
    def dressed(sig, name):
        ok = np.isfinite(y) & np.isfinite(sig) & (sig > 0)
        idx = D.eval_index(np.ones(sig.size, dtype=bool), ok, horizon)
        # THE TARGET MUST HAVE CLOSED BY BAR i, not merely started before
        # it. idx < i is not enough: y[i-4] is built from returns at
        # i-3..i+4, so fitting on it would pull four bars of the future
        # into a LIVE forecast. Found by a surviving mutant; the same rule
        # resolve() enforces, for the same reason.
        idx = idx[idx + horizon <= i]
        if idx.size < 30:
            return None
        d = Mod.QuantileDressing().fit(y[idx], sig[idx])
        return d.apply(sig[i:i + 1])[0]

    for name, sig in (("ATR14 (incumbent)", atr),
                      ("EWMA(0.94) range", Mod.ewma_sigma(Mod.parkinson_sigma(bars)))):
        q = dressed(sig, name)
        if q is not None:
            out[name] = q

    try:
        from . import fm as FM
    except Exception:                            # pragma: no cover
        return out
    adapters = FM.available(device=device)
    if adapters:
        series = FM.input_series(bars)
        for ad in adapters:
            sig = np.full(bars["close"].shape, np.nan)
            hist = np.arange(64, i + 1)
            sig[hist] = ad.predict_sigma(series, hist, horizon)
            q = dressed(sig, ad.name)
            if q is not None:
                out[ad.name] = q
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", default=os.path.expanduser("~/fm-shadow/forecasts.jsonl"))
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--engine", default=None)
    args = ap.parse_args(argv)

    now = int(time.time())
    bars = fetch_bars(url=args.engine)

    filled = S.resolve(args.log, bars, now=now)
    print(f"resolved {filled} forecast(s)")

    i = latest_open_index(bars, D.HORIZON_BARS, now)
    ts_made = int(bars["ts"][i])
    already = {r["model"] for r in S.load(args.log) if r["ts_made"] == ts_made}

    made = 0
    for name, q in forecasts_at(bars, i, D.HORIZON_BARS, args.device).items():
        if name in already:
            continue                    # idempotent: a re-run adds nothing
        S.append_forecast(args.log, name, ts_made, np.sort(q), D.HORIZON_BARS)
        made += 1
    print(f"logged {made} forecast(s) at bar {ts_made}")

    for name in sorted({r["model"] for r in S.load(args.log)}):
        s = S.score(args.log, name)
        if s["n"]:
            print(f"  {name:22} n={s['n']:4d} pending={s['pending']:3d} "
                  f"coverage={s['coverage']:.3f} pinball={s['pinball']:.3e} "
                  f"weeks={s['weeks_spanned']}")
        else:
            print(f"  {name:22} nothing resolved yet "
                  f"(pending={s['pending']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
