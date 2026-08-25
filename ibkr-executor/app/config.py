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
    # READ-ONLY feed token for GET /blend/feed (X-Read-Token header,
    # constant-time compare). SEPARATE from EXEC_TOKEN by design: the feed
    # holder can see the book but can never kill/resume/see exec surfaces.
    # Empty (default) = the feed endpoint is disabled (404).
    read_token: str = ""                  # READ_TOKEN

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
    # El Nino ladder: OPT-IN, same doctrine as the blend (Casey 2026-08-24:
    # "forget the el nino ladder, turn that off for now"). Disabled = the
    # manager is still built (state preserved, /status renders, /kill can
    # flatten any open leg) but step() is never called: no entries, no
    # closes, no decisions. Re-enable via LADDER_ENABLED=true in Render
    # before the Nov 2026 window if the trade is back on.
    ladder_enabled: bool = False          # LADDER_ENABLED
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
    # Persisted gateway-outage ledger + the supervisor's restart records.
    # Without these there is NO downtime history at all, so "how much of our
    # downtime is IBKR vs our own container" is unanswerable rather than
    # merely unanswered (2026-08-24).
    # Defaults match the OTHER state paths' style, but on Render these are
    # overridden to /app/data (the mounted disk). ./data is the ephemeral
    # container layer: history there dies on every deploy.
    outage_log_path: str = "./data/gateway_outages.json"
    gateway_restart_log: str = "./data/gateway_restarts.jsonl"


settings = Settings()
