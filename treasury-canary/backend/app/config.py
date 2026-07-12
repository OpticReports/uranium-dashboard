"""Central configuration — env-driven, no hardcoded secrets.

Everything tunable (series IDs, refresh cadence, display tz, alert webhook) lives
here or in DB-backed config; thresholds/weights live in scoring/thresholds.py and
scoring/composite.py so they can be retuned without touching logic.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Storage ---
    database_url: str = "sqlite:///./data/canary.db"

    # --- Keys (all optional; core needs only FRED) ---
    fred_api_key: str | None = None          # free: fredaccount.stlouisfed.org/apikeys
    fmp_api_key: str | None = None           # optional: gold (GLD) for the flow compass
    move_api_key: str | None = None          # optional licensed MOVE override
    alert_webhook_url: str | None = None     # POST target on regime-change events

    # --- HTTP / caching ---
    http_timeout_seconds: float = 30.0
    cache_dir: str = "./data/cache"
    cache_ttl_seconds: int = 3600            # respect FRED etc.; daily data is stable

    # --- Scheduling ---
    run_scheduler: bool = True
    refresh_interval_minutes: int = 720      # twice daily; data is EOD anyway
    backfill_on_startup: bool = True

    # --- Display ---
    display_tz: str = "America/Puerto_Rico"  # storage is always UTC

    # --- App ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    frontend_dist: str | None = None         # set in the single-service deploy image
    log_level: str = "INFO"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()


# --- FRED series catalog (the backbone). Confirmed at fetch; 404s are logged. ---
# Constant-maturity nominal yields (daily), used to build any tenor-pair spread.
FRED_TENORS: dict[str, str] = {
    "1mo": "DGS1MO", "3mo": "DGS3MO", "6mo": "DGS6MO", "1y": "DGS1",
    "2y": "DGS2", "3y": "DGS3", "5y": "DGS5", "7y": "DGS7",
    "10y": "DGS10", "20y": "DGS20", "30y": "DGS30",
}
# Published spreads (prefer these where they exist; else difference the tenors).
FRED_SPREADS: dict[str, str] = {"2s10s": "T10Y2Y", "3m10y": "T10Y3M"}
FRED_REAL_YIELDS: dict[str, str] = {
    "5y": "DFII5", "7y": "DFII7", "10y": "DFII10", "20y": "DFII20", "30y": "DFII30",
}
FRED_BREAKEVENS: dict[str, str] = {"5y": "T5YIE", "10y": "T10YIE", "5y5y": "T5YIFR"}
FRED_FUNDING: dict[str, str] = {"effr": "EFFR", "sofr": "SOFR", "iorb": "IORB"}
FRED_VOL: dict[str, str] = {"vix": "VIXCLS"}
FRED_CREDIT: dict[str, str] = {"ig_oas": "BAMLC0A0CM", "hy_oas": "BAMLH0A0HYM2"}
FRED_MACRO: dict[str, str] = {
    "recession": "USREC", "sp500": "SP500", "nfci": "NFCI", "acm_tp10": "THREEFYTP10",
}
# Labor / real-economy. Note: the unemployment RATE is lagging; the Sahm Rule
# (rate-of-change) and initial jobless claims are the useful forward signals.
FRED_LABOR: dict[str, str] = {
    "unrate": "UNRATE",            # lagging context
    "claims_4wk": "IC4WSA",        # initial jobless claims, 4-week MA (leading)
    "sahm": "SAHMREALTIME",        # official real-time Sahm recession indicator
}
# Flow-compass discriminators: where money hides when the stock-bond hedge breaks.
# (Gold comes from FMP — FRED's LBMA gold series were discontinued.)
FRED_FLOWS: dict[str, str] = {
    "usd": "DTWEXBGS",             # nominal broad dollar index (daily)
    "oil": "DCOILWTICO",           # WTI crude (daily)
    "btc": "CBBTCUSD",             # Coinbase BTC-USD (daily)
}
# Leading stack (K): independent, individually-validated leading indicators.
# Deliberately NOT jointly fitted (≈8 recessions of history -> joint weights
# would overfit); each is scored vs its OWN historical threshold and the UI
# reports transparent breadth across whichever the user includes.
FRED_LEADING: dict[str, str] = {
    "permits": "PERMIT",           # building permits (monthly) — housing leads the cycle
    "sloos": "DRTSCILM",           # SLOOS net % tightening C&I standards (quarterly)
    "temp_help": "TEMPHELPS",      # temp-help employment (monthly)
    "heavy_trucks": "HTRUCKSSAAR", # heavy truck sales SAAR (monthly)
    "core_capex": "NEWORDER",      # nondefense capital goods ex-aircraft orders (monthly)
    "cfnai": "CFNAI",              # Chicago Fed National Activity Index (monthly)
    "gdpnow": "GDPNOW",            # Atlanta Fed GDPNow nowcast
    "cp_prob": "RECPROUSM156N",    # Chauvet-Piger smoothed recession probability
}
# Pin board (trigger channels) — the measurable proxies for what historically
# "pricks the bubble". (Oil/EFFR/HY/term premium/SOFR-IORB already in bundle.)
FRED_PINS: dict[str, str] = {
    "epu": "USEPUINDXD",           # daily Economic Policy Uncertainty index
    "discount_window": "WLCFLPCL", # primary-credit borrowing (weekly; SVB tell)
    "reserves": "WRESBAL",         # reserve balances (weekly)
    "rrp": "RRPONTSYD",            # overnight reverse repo (daily; the cushion)
    "interest_gdp": "FYOIGDA188S", # federal interest outlays as % of GDP (annual)
}
