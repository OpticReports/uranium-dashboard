"""Central configuration.

Two kinds of config:
  1. Secrets / environment  -> .env (pydantic-settings)  -> `settings`
  2. Tunable model/universe -> YAML under config/        -> load_yaml_config()

Nothing here ever hardcodes a key. Missing optional keys are fine: the owning
module degrades gracefully (logs a warning, skips) — see ingestion modules.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BACKEND_DIR / "config"


class Settings(BaseSettings):
    """Environment-driven settings. All API keys are OPTIONAL."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Storage ---
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'genomics.db'}"

    # --- Market data provider selection ---
    # One of: yfinance | polygon | fmp | tiingo. yfinance needs no key.
    market_provider: str = "yfinance"
    polygon_api_key: str | None = None
    fmp_api_key: str | None = None
    tiingo_api_key: str | None = None

    # --- Analyst data (FMP gives estimates/PT revisions on free-ish tier) ---
    analyst_provider: str = "fmp"  # falls back to yfinance recommendations

    # --- Social / hype ---
    x_bearer_token: str | None = None       # official X API (pay-per-use); skip if absent
    # twitterapi.io: 3rd-party X data, ~97% cheaper. Preferred for X when set and no
    # official bearer token. Cost is bounded by max_posts x lookback x cadence.
    twitterapi_io_key: str | None = None
    # Posts pulled per symbol per DAY (0 = uncapped — true volume for megacaps).
    # X is fetched at most once/UTC-day/symbol regardless of the 2h social cadence,
    # so this bounds DAILY spend, not per-run: cost ~= names x this x 30 x $0.00015.
    twitterapi_io_max_posts: int = 300
    twitterapi_io_lookback_days: int = 2    # only recent posts feed the daily hype series
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "genomics-alpha-tracker/0.1"
    stocktwits_enabled: bool = True          # public endpoint, no key (rate-limited)
    apewisdom_enabled: bool = True           # free, no key: ~15 subreddits, real counts
    fmp_social_enabled: bool = True          # uses FMP key; legacy endpoint, best-effort

    # --- Optional LLM sentiment ---
    anthropic_api_key: str | None = None
    sentiment_engine: str = "lexicon"        # lexicon | anthropic

    # --- Chat analyst (grounded LLM over the dashboard's data) ---
    chat_model_default: str = "claude-sonnet-4-6"   # fast/cheap default
    chat_model_deep: str = "claude-opus-4-8"        # "Deep analysis" toggle
    chat_max_tokens: int = 4096
    chat_max_tool_iters: int = 6

    # --- Science layer (NCBI rewards a key with higher rate limits) ---
    ncbi_api_key: str | None = None
    ncbi_email: str | None = None

    # --- Caching / HTTP ---
    cache_dir: str = str(BACKEND_DIR / "data" / "cache")
    cache_ttl_seconds: int = 3600
    http_timeout_seconds: int = 30

    # --- App ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    run_scheduler: bool = True
    log_level: str = "INFO"
    # When set to a built frontend dir, the API also serves the SPA at "/"
    # (single-service deployment). Left empty for local dev (Vite serves the UI).
    frontend_dist: str = ""
    # Run a one-shot backfill on startup if the DB is empty (useful on hosts
    # with ephemeral disks so the dashboard isn't blank on first load).
    backfill_on_startup: bool = False
    # Optional HTTP Basic auth gate. When BOTH are set, every request (except
    # /health) requires these credentials — protects a publicly-hosted instance.
    # Leave unset for local dev (no auth).
    dashboard_user: str | None = None
    dashboard_password: str | None = None


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


@functools.lru_cache(maxsize=None)
def _load_yaml_cached(name: str, mtime: float) -> dict[str, Any]:
    path = CONFIG_DIR / name
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_yaml_config(name: str) -> dict[str, Any]:
    """Load a YAML config file, hot-reloading when the file changes on disk."""
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    return _load_yaml_cached(name, path.stat().st_mtime)


# Convenience accessors -------------------------------------------------------

def scoring_config() -> dict[str, Any]:
    return load_yaml_config("scoring.yaml")


def flags_config() -> dict[str, Any]:
    return load_yaml_config("flags.yaml").get("flags", {})


def intervals_config() -> dict[str, Any]:
    return load_yaml_config("intervals.yaml").get("jobs", {})


def watchlist_config() -> dict[str, Any]:
    return load_yaml_config("watchlist.yaml")


def calls_config() -> dict[str, Any]:
    return load_yaml_config("calls.yaml").get("calls", {})
