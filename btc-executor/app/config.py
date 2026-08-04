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
    cb_product_id: str = "BTC-PERP-INTX"
    cb_portfolio: str = ""                # INTX portfolio uuid (auto-detected if empty)

    # sizing: leg exposure fraction = kelly_m * blend_lev * leg_weight
    kelly_m: float = 0.56                 # Kelly-recommended multiplier on S5
    max_notional_usd: float = 25_000.0    # hard cap, whole account
    max_account_lev: float = 2.0          # notional / equity ceiling

    # safety rails
    dry_run: bool = True                  # log intended orders, send nothing
    daily_loss_halt_pct: float = 0.06     # flatten + halt if day loss exceeds
    dd_halt_pct: float = 0.25             # flatten + halt below high-water mark
    stale_bars_max: int = 2               # engine this stale -> entries blocked
    drift_tol_frac: float = 0.02          # |venue - ledger| notional tolerance
    stop_replace_bps: float = 5.0         # move stop only if >5bp from current
    stop_limit_offset_pct: float = 0.5    # stop-limit band below/above trigger

    poll_seconds: int = 20
    state_path: str = "./data/executor_state.json"
    log_level: str = "INFO"


settings = Settings()
