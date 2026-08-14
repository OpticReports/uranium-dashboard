"""Indicator stack — pure Python, no pandas at runtime.

Numerical contract (spec §1.2): SMA = rolling mean; RSI(14) and ATR(14) use the
EMA recursion avg = avg_prev + (x - avg_prev)/n, seeded with the FIRST
observation — exactly pandas ewm(alpha=1/n, adjust=False). Unit tests assert
parity with pandas to 1e-9. The seed convention is load-bearing for those
tests (a Wilder SMA-seed passes eyeball checks and fails parity); the 210-bar
warmup makes the economic difference nil either way.
"""
from __future__ import annotations


def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= n:
            run -= values[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def _ewm(values: list[float | None], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    avg: float | None = None
    for i, v in enumerate(values):
        if v is None:
            out[i] = avg
            continue
        avg = v if avg is None else avg + (v - avg) / n
        out[i] = avg
    return out


def rsi(closes: list[float], n: int = 14) -> list[float | None]:
    ups: list[float | None] = [None]
    dns: list[float | None] = [None]
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        ups.append(max(d, 0.0))
        dns.append(max(-d, 0.0))
    au, ad = _ewm(ups, n), _ewm(dns, n)
    out: list[float | None] = []
    for u, d in zip(au, ad):
        if u is None or d is None:
            out.append(None)
        elif d == 0:
            out.append(100.0 if u > 0 else 50.0)
        else:
            out.append(100.0 - 100.0 / (1.0 + u / d))
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], n: int = 14
        ) -> list[float | None]:
    trs: list[float | None] = [None]
    for i in range(1, len(highs)):
        pc = closes[i - 1]
        trs.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    return _ewm(trs, n)
