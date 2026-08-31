"""Executor settings. Secrets (API key, exec token) come from env only —
never from the repo. DRY_RUN defaults ON: a fresh deploy can never trade."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # signal source (the paper engine)
    engine_url: str = "https://btc-paper-engine.onrender.com"
    exec_token: str = ""                  # must match the engine's EXEC_TOKEN

    # READ-ONLY companion to exec_token. Satisfies GET /status and NOTHING
    # else - not /drill, not /coverage/attest, not /kill, not /resume.
    # It exists because EXEC_TOKEN is a WRITE credential: /drill places real
    # orders. Anything that only needs to answer "what is the executor
    # doing" - an assistant, a dashboard, a monitor - gets this instead, so
    # read access never comes bundled with the authority to trade.
    # Unset = the endpoint behaves exactly as it did before.
    exec_read_token: str = ""

    # WHICH VENUE. Defaults to coinbase: an unset or misspelled env must
    # keep the behaviour that is already deployed, never silently move a
    # live book to a different exchange. Validated at boot - an unknown
    # value raises rather than falling through to a default (a typo here
    # would otherwise route real orders somewhere nobody intended).
    venue: str = "coinbase"               # coinbase | hyperliquid

    # venue: Coinbase Advanced Trade / INTX perps
    cb_api_key_name: str = ""             # CDP key name ("organizations/...")
    cb_api_private_key: str = ""          # CDP EC private key PEM
    cb_product_id: str = "BIP-20DEC30-CDE"   # US perp-style BTC future (CDE)
    cb_portfolio: str = ""                # INTX portfolio uuid (auto-detected if empty)

    # venue: Hyperliquid. The AGENT (API) wallet signs trades and CANNOT
    # withdraw - the same separation of powers as the Coinbase trade-only
    # key, except enforced by the venue instead of by our own care. Approve
    # one from the HL UI (API -> generate agent wallet); the main account
    # address it trades for goes in hl_account_address.
    hl_secret_key: str = ""               # agent wallet PRIVATE KEY (0x...)
    # REQUIRED, and NOT the agent's address. An agent wallet signs for a main
    # account but holds nothing itself, and HL reads positions by the MAIN
    # account's public address - defaulting to the signer would report the
    # book permanently FLAT. Construction refuses if this is blank.
    hl_account_address: str = ""
    hl_coin: str = "BTC"
    hl_testnet: bool = False

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
    # Auto-drill (RAMP_V4.md amendment 2026-08-17): the executor runs its own
    # drills in flat windows until drill coverage is met. Default OFF - a
    # fresh deploy never self-trades drills; Casey arms it in the Render env.
    auto_drill: bool = False
    auto_drill_spacing_s: int = 3600
    log_level: str = "INFO"


settings = Settings()
