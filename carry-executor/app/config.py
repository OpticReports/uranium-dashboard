"""carry-executor settings. Secrets come from env only. DRY_RUN defaults ON:
a fresh deploy can never trade. The sleeve's size lives in the Render env;
CARRY_MAX_NOTIONAL_USD in carry.py is the repo ceiling it cannot exceed."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # the decision brain: btc-paper-engine's funding monitor (keyless)
    engine_url: str = "https://btc-paper-engine.onrender.com"
    exec_token: str = ""                 # must match the engine's EXEC_TOKEN
    exec_read_token: str = ""            # read-only: GET /status only

    # Hyperliquid: an AGENT (API) wallet of its own - not btc-executor's.
    # Agents cannot withdraw, and a separate signer keeps the two services'
    # nonces apart (HL recommends one agent per process).
    hl_secret_key: str = ""
    hl_account_address: str = ""         # the MAIN account (same as btc-executor)
    hl_testnet: bool = False

    dry_run: bool = True                 # fail-safe: a fresh deploy sends nothing
    carry_enabled: bool = True           # False = unwind the sleeve and stay flat

    perp_coin: str = "ETH"
    spot_token: str = "UETH"             # HL's bridged ETH spot token
    carry_notional_usd: float = 0.0      # FAIL-SAFE 0 = never open; Render sets 30000
    max_slip_bps: float = 15.0           # IOC limit distance from mid
    resize_drift: float = 0.25           # monthly re-size when |notional/target - 1| > this
    cross_leverage: int = 5              # ETH perp set to CROSS margin at this leverage
    liq_buffer: float = 0.15             # unwind when mid is within 15% of the short's liq px

    poll_seconds: int = 300
    state_path: str = "data/carry_state.json"
    log_level: str = "INFO"


settings = Settings()
