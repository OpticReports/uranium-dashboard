"""IBKR executor settings. Credentials only via env (Render secrets).
No creds -> OFFLINE dry mode: full decision loop, no gateway, no orders."""
from __future__ import annotations

from pydantic import field_validator
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
    # IB market-data type. reqMarketDataType was NEVER called, so IB served
    # LIVE data (type 1); a paper account without market-data subscriptions
    # returns nan, spot() raised "no market price", every price went absent,
    # and the book could not seed the SPY core, sweep BIL, or rebalance -
    # silently, forever (found 2026-08-24: SPY=None, BIL=None).
    #   1 live · 2 frozen · 3 delayed · 4 delayed-frozen
    # Default 1: ALWAYS ask for real-time first. When live returns nothing
    # and ib_allow_delayed is set, spot() escalates per-call to delayed and
    # says so - so delayed data is a visible, deliberate degradation, never
    # a silent one.
    ib_market_data_type: int = 1
    # Delayed quotes are ~15 minutes stale. Fine for a daily 30/70 weight
    # decision on a PAPER book; NOT something to price live orders with
    # unnoticed. Allowed by default so paper works out of the box; the
    # go-live checklist turns it OFF once real subscriptions are attached.
    ib_allow_delayed: bool = True
    # seconds to wait for a first tick before giving up on a quote
    ib_quote_wait_s: float = 6.0

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

    # Composer mirror (composer/IBKR_MIRROR.md; app/mirror.py). MIRROR_ENABLED
    # =false is the default and leaves the service byte-for-byte as before:
    # no manager, no polling, no /status section, no state file.
    # Enabled, every engine runs in a PAPER book (a private DryAdapter: no
    # venue, no account reads) until it is named in MIRROR_LIVE_ENGINES - and
    # even then only when this service itself trades for real (TWS
    # credentials, DRY_RUN=false). The staged rollout is: paper for at least
    # ten sessions, then one engine at a time.
    mirror_enabled: bool = False          # MIRROR_ENABLED
    # The keyless brain (composer/scripts/mirror_brain.py --serve) and its
    # READ-ONLY intents token (the brain's MIRROR_API_TOKEN). No broker
    # credential is ever read by the mirror path.
    mirror_brain_url: str = ""            # MIRROR_BRAIN_URL (https only, or
                                          # http://localhost / 127.0.0.1: the
                                          # token is never sent over plain http)
    mirror_api_token: str = ""            # MIRROR_API_TOKEN
    # The capital the mirror runs, split across the sleeves by
    # MIRROR_WEIGHTS (POLICY.md's targets). 0 = no sleeve can be seeded. A
    # LIVE sleeve is seeded only from cash the account really holds beyond
    # what the book already claims.
    mirror_capital_usd: float = 0.0       # MIRROR_CAPITAL_USD
    # The most capital a LIVE book takes in seeds plus operator credits
    # (POST /mirror/credit) without "force": true. 0 = MIRROR_CAPITAL_USD is
    # the cap: scaling the book up by a credit then needs this raised first
    # (or force), so a slipped decimal cannot scale a real book tenfold.
    mirror_max_book_usd: float = 0.0      # MIRROR_MAX_BOOK_USD
    mirror_weights: str = "HG:0.29,KMLM:0.29,SLEEVE:0.27,HARV:0.15"
    mirror_live_engines: str = ""         # MIRROR_LIVE_ENGINES e.g. "HARV"
    # On Render both are overridden onto the mounted disk (/app/data): the
    # default is the ephemeral container layer, where a deploy would forget
    # a live book's positions.
    mirror_state_path: str = "./data/mirror_state.json"
    mirror_dry_state_path: str = "./data/mirror_dry_state.json"
    # The brain's decide_utc is the END of the decision bar (15:54:00 ET on a
    # full day); FMP publishes that bar 10-25 s after it ends, so the book
    # asks 25 s later. The three are clamped at build to the range the book
    # is made for (offset 0..120 s, cancel lead 20..120 s, band 0.1%..5%),
    # with a log line: a value outside it used to disable the book silently.
    mirror_decide_offset_s: float = 25.0  # act this long after the decision bar
    mirror_cancel_before_close_s: float = 60.0   # leftovers cancelled then
    mirror_quote_band: float = 0.015      # venue quote vs the brain's price
    # Dividends the brain lists become a receivable per sleeve (shares held
    # at the close before the ex-date), credited from the pay date.
    # "composer": only a sleeve that still holds the payer then is credited,
    # else the cash stays unallocated in the account (what Composer's
    # symphonies do); "holder": whoever held the shares is always credited.
    mirror_dividend_rule: str = "composer"   # MIRROR_DIVIDEND_RULE
    # A TRANSFER-ONLY credential for POST /mirror/transfer (X-Transfer-Token
    # header, constant-time compare): the daily POLICY routine mirrors a
    # Composer capital move without holding EXEC_TOKEN. It opens no other
    # route. Empty (default) = off; honoured only when at least 24 characters
    # and different from EXEC_TOKEN and READ_TOKEN.
    mirror_transfer_token: str = ""       # MIRROR_TRANSFER_TOKEN
    # The most that transfers authorised by that token may move in one ET
    # calendar day, as a fraction of the book's equity (clamped to 0..1).
    # Transfers under EXEC_TOKEN are not counted and not capped.
    mirror_transfer_max_frac: float = 0.25   # MIRROR_TRANSFER_MAX_FRAC

    @field_validator("mirror_capital_usd", "mirror_max_book_usd",
                     "mirror_transfer_max_frac", mode="before")
    @classmethod
    def _blank_is_default(cls, v, info):
        """A dashboard field saved BLANK arrives as KEY='' and float('')
        raised at import, stopping the WHOLE executor (blend included) for
        one empty mirror setting. Blank means "not set": the default."""
        if isinstance(v, str) and not v.strip():
            return cls.model_fields[info.field_name].default
        return v

    @field_validator("mirror_transfer_max_frac", mode="after")
    @classmethod
    def _frac_in_range(cls, v):
        """clamped to 0..1: a fraction of the book, never more than all of it"""
        return min(max(v, 0.0), 1.0) if v == v else 0.0


settings = Settings()
