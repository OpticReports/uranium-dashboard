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

    # blend3070 (H13 30/70 R2-A sleeve + SPY core; OFFLINE scaffold).
    # BLEND_ENABLED=false is the default: the service boots exactly as today.
    blend_enabled: bool = False           # BLEND_ENABLED
    tracker_url: str = ""                 # TRACKER_URL (genomics tracker base URL)
    # The tracker's login gate is HTTP Basic (its DASHBOARD_USER/PASSWORD).
    # These are DASHBOARD credentials for polling a keyless decision brain —
    # no broker credential is ever read by the blend path.
    tracker_user: str = ""                # TRACKER_USER
    tracker_password: str = ""            # TRACKER_PASSWORD
    # Preferred: a dedicated READ-ONLY intents token (the tracker's
    # BLEND_API_TOKEN) so the executor never holds the dashboard password.
    # When set, the poll authenticates with X-API-Token instead of Basic.
    tracker_api_token: str = ""           # TRACKER_API_TOKEN
    blend_budget: float = 0.0             # BLEND_BUDGET cap in USD; 0 = disabled
    blend_book_usd: float = 10_000.0      # BLEND_BOOK_USD initial paper book
    blend_state_path: str = "./data/blend_state.json"


settings = Settings()
