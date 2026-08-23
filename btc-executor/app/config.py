"""Executor settings. Secrets (API key, exec token) come from env only —
never from the repo. DRY_RUN defaults ON: a fresh deploy can never trade."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # signal source (the paper engine)
    engine_url: str = "https://btc-paper-engine.onrender.com"
    exec_token: str = ""                  # must match the engine's EXEC_TOKEN

    # venue (Coinbase Advanced Trade / INTX perps)
    cb_api_key_name: str = ""             # CDP key name ("organizations/...")
    cb_api_private_key: str = ""          # CDP EC private key PEM
    cb_product_id: str = "BIP-20DEC30-CDE"   # US perp-style BTC future (CDE)
    cb_portfolio: str = ""                # INTX portfolio uuid (auto-detected if empty)

    # sizing: leg exposure fraction = kelly_m * blend_lev * leg_weight
    kelly_m: float = 0.05                 # FAIL-SAFE token size; the
    # ramp target lives in the Render env, never here (a missing env
    # must under-size, never over-size). Ramp: EXECUTOR.md v3.
    # Fixed capital base for position sizing (USD). 0 = size on live account
    # equity. Set (e.g. 128000) to run the small-deposit construction: a
    # ~$40k USDC account trading positions sized to a $128k base. Halt
    # percentages re-anchor to this base so routine strategy swings against
    # a small account don't false-trigger.
    sizing_base_usd: float = 0.0
    max_notional_usd: float = 25_000.0    # hard cap, whole account
    max_account_lev: float = 2.0          # notional / sizing-base ceiling

    # safety rails
    dry_run: bool = True                  # log intended orders, send nothing
    daily_loss_halt_pct: float = 0.06     # flatten + halt if day loss exceeds
    dd_halt_pct: float = 0.25             # flatten + halt below high-water mark
    stale_bars_max: int = 2               # engine this stale -> entries blocked
    # |venue - ledger| notional tolerance. 0.01 of $50k = $500, BELOW one CDE
    # contract (~$640): a single-contract divergence must alert. The old 0.02
    # ($1,000) sat above it and swallowed the 2026-08-10 ledger overstatement.
    drift_tol_frac: float = 0.01
    stop_replace_bps: float = 5.0         # move stop only if >5bp from current
    stop_limit_offset_pct: float = 0.5    # stop-limit band below/above trigger

    poll_seconds: int = 20
    state_path: str = "./data/executor_state.json"
    # RAMP v4 drills (RAMP_V4.md): min-size test round trips
    drill_max_per_day: int = 6
    drill_cooldown_s: int = 300
    # stopfill redesign (2026-08-23): Coinbase maps a SELL stop to STOP_DOWN
    # and preview-rejects an ABOVE-market trigger, so the original
    # fires-immediately design failed deterministically. A trigger just BELOW
    # market is venue-legal and fires on the next downtick, which needs a
    # longer poll budget than an instant fill did.
    # 3bp, not 10: the counter-agent measured first-passage probability for a
    # 10bp move inside the 60s budget at 4-23% depending on vol, i.e. ~90% of
    # drills would fail, each one a RED page burning a daily drill slot. 3bp
    # gives 53-72%.
    drill_stopfill_bps: float = 3.0       # trigger this far BELOW mid
    drill_stopfill_poll: int = 30         # x2s => up to 60s waiting for the fill
    # limit-path entry drills: rest INSIDE the spread so post-only is
    # accepted, then chase at market if unfilled - the same shape the real
    # pullback entry runs.
    # 0.5bp: EXECUTOR.md measures the book's spread at 1.54bp, so the old 5bp
    # rested ~4bp BEHIND the best bid - outside the spread, behind the whole
    # level-1 queue, so every limit drill degenerated into a market chase.
    drill_limit_bps: float = 0.5          # rest this far inside mid
    drill_limit_poll: int = 15            # x2s => up to 30s before chasing
    # post-only-cross drill: deliberately price THROUGH the spread so the
    # venue rejects the post-only order as marketable.
    drill_cross_bps: float = 25.0
    # Auto-drill (RAMP_V4.md amendment 2026-08-17): the executor runs its own
    # drills in flat windows until drill coverage is met. Default OFF - a
    # fresh deploy never self-trades drills; Casey arms it in the Render env.
    auto_drill: bool = False
    auto_drill_spacing_s: int = 3600
    log_level: str = "INFO"


settings = Settings()
