"""Central configuration.

Two kinds of config (catalyst-options-engine split):
  1. Environment -> pydantic-settings -> `settings`. KEYLESS by design: every
     lane (DEX Screener, SEC, stockanalysis) is a public endpoint. FMP is the
     one OPTIONAL enrichment (shares outstanding / float); when its key is
     absent the market-cap gate degrades to price+RVOL and says so.
  2. Tunables    -> YAML under config/ -> screener_config(), hot-reloaded on
     file mtime change.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BACKEND_DIR / "config"

# stockanalysis.com refuses default httpx UAs.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
# sec.gov's fair-access policy requires a User-Agent carrying a CONTACT
# ADDRESS, and enforces it: a UA without one is answered with 403, verified
# 2026-09-02. Built from SEC_CONTACT so the address is configurable per deploy
# and no personal address is baked into the repo.
def sec_user_agent(contact: str) -> str:
    return f"OpticReports Research {contact}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'screener.db'}"
    cache_dir: str = str(BACKEND_DIR / "data" / "cache")
    log_level: str = "INFO"
    # Contact address sent to sec.gov per its fair-access policy. Point this at
    # a mailbox that is actually monitored before running at any volume.
    sec_contact: str = "research@opticreports.com"
    http_timeout_seconds: float = 20.0
    run_scheduler: bool = True

    # Optional enrichment only. Absent => market-cap gate degrades, never fails.
    fmp_api_key: str | None = None

    # Optional push target for alerts (Discord/Slack/ntfy webhook). Absent =>
    # alerts are persisted and shown on the dashboard only.
    alert_webhook_url: str | None = None

    # Optional basic-auth gate, same convention as the other dashboards.
    dashboard_user: str | None = None
    dashboard_password: str | None = None


settings = Settings()


def _load_yaml(path: Path, mtime: float) -> dict[str, Any]:  # noqa: ARG001
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


@functools.lru_cache(maxsize=8)
def _cached_yaml(path_str: str, mtime: float) -> dict[str, Any]:
    return _load_yaml(Path(path_str), mtime)


def screener_config() -> dict[str, Any]:
    """Tunables, re-read whenever config/screener.yaml changes on disk."""
    path = CONFIG_DIR / "screener.yaml"
    return _cached_yaml(str(path), path.stat().st_mtime)
