"""IBKR executor settings. Credentials only via env (Render secrets).
No creds -> OFFLINE dry mode: full decision loop, no gateway, no orders."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # IB Gateway (containerized alongside; gnzsnz/ib-gateway convention)
    tws_userid: str = ""                  # TWS_USERID (paper user first!)
    tws_password: str = ""                # TWS_PASSWORD
    trading_mode: str = "paper"           # paper | live
    ib_host: str = "127.0.0.1"
    ib_port: int = 4002                   # 4002 paper, 4001 live (in-container)
    ib_client_id: int = 17

    # safety
    dry_run: bool = True                  # log intents, never place orders
    exec_token: str = ""                  # /status /kill /resume auth

    # ladder economics (manager cfg)
    leg_budget_usd: float = 10_000.0
    compound: bool = False
    max_concurrent_legs: int = 2

    poll_seconds: int = 300               # options ladder: 5-min cadence is plenty
    state_path: str = "./data/ladder_state.json"
    log_level: str = "INFO"


settings = Settings()
