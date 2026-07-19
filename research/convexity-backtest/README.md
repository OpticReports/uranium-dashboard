# Long-horizon reconstruction harness (convexity sleeve)

Composer can only backtest to the tradable ETF's inception (~2021 for the vol
sleeve). This harness rebuilds each holding **synthetically from the index it
tracks** so a strategy can be tested across decades more of regimes — with an
automated **overfitting/error watchdog** that tries to prove any promising
result is a false positive before we believe it.

> **This is research/simulation only.** It does not connect to Composer, touch
> the live symphony, or move capital. It is additive to the repo.

## Two tiers of trust (kept strictly separate)

| Tier | What | Trust | Horizon |
|------|------|-------|---------|
| **1 — data-grounded** | Leveraged equity ETF from its real index (e.g. `TQQQ = 3× NDX`) | Defensible | NDX → **1986** |
| **2 — modelled** | Vol-futures ETF (UVXY/VIXY) from **VIX spot** + a contango/roll model | **Illustrative only — do NOT quote** | VIX spot → 1990 |

Tier 2 exists because this environment has VIX **spot** (FRED) but **not** VIX
futures / the SPVXSTR index that vol ETFs actually track. A spot-derived vol ETF
captures the *shape* (crash spikes, calm-market bleed) but the magnitudes are
model artefacts. Replace with real futures/SPVXSTR before any vol-sleeve claim.

## Files

```
data.py       FRED loaders (NASDAQ100, VIXCLS, DGS3MO), cached under data/
synth.py      daily-reset leveraged/vol ETF reconstruction (+ era-correct leverage)
watchdog.py   the skeptic: PSR, deflated Sharpe, block bootstrap, leave-one-year-out,
              walk-forward degradation, look-ahead probe, assumption sensitivity
run.py        orchestrator -> out/results.json + console summary
out/          run outputs (results.json)
```

## Run

```bash
pip install -r requirements.txt
python3 run.py        # fetches FRED (cached), builds series, runs watchdog, writes out/results.json
```

## The watchdog (why a result isn't a false positive)

Each check targets a specific way a backtest lies:

- **Probabilistic Sharpe (PSR)** — is Sharpe even statistically > 0 given sample
  length + skew/kurtosis? (Sharpe flatters fat-tailed / convex payoffs.)
- **Deflated Sharpe (DSR)** — corrects Sharpe for the *number of variants tried*;
  keeping the best of many runs manufactures Sharpe from noise.
- **Block bootstrap CI** — is the edge distinguishable from luck?
- **Leave-one-year-out** — is the whole result carried by one lucky regime?
- **Walk-forward degradation** — how much Sharpe evaporates out of sample.
- **Look-ahead probe** — corrupts data *after* date `t` and asserts the position
  *at* `t` is unchanged; any change = future-peeking. (Demonstrated live: it
  passes a causal 200-day gate and fails a leaky centered one.)
- **Assumption sensitivity** — sweeps the soft inputs (financing, fees, roll);
  a conclusion that flips across plausible inputs is a modelling artefact.

An independent auditor agent also re-runs the harness and adversarially reviews
the math/stats — see `AUDIT.md`.

## What this harness does NOT yet prove

1. **The actual crash-convexity sleeve** — needs the real symphony definition
   (Composer Step D, not yet run). The strategies in `run.py` are transparent
   examples that exist only to exercise the look-ahead probe.
2. **The vol sleeve's real numbers** — needs real VIX-futures / SPVXSTR data.

The intended workflow closes both gaps, then adds the credibility keystone:
**reproduce Composer's 2021+ backtest on the overlap window first** — if the
reimplementation matches Composer where both have data, the pre-2021 extension
is trustworthy; if not, we're measuring our own bugs.
