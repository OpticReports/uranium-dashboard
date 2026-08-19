"""Central configuration.

Two kinds of config (same split as the genomics tracker):
  1. Environment  -> pydantic-settings -> `settings`. NO API keys exist here
     by design: this service is a KEYLESS decision brain (CLAUDE.md
     separation-of-powers law). Every data lane is keyless and degrades
     gracefully when dark.
  2. Tunables     -> YAML under config/ -> radar_config() / engine_config(),
     hot-reloaded on file mtime change.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BACKEND_DIR / "config"

# Browser UA: stockanalysis.com and api.nasdaq.com refuse default httpx UAs.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class Settings(BaseSettings):
    """Environment-driven settings. Deliberately keyless — no secrets."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'options.db'}"
    cache_dir: str = str(BACKEND_DIR / "data" / "cache")
    cache_ttl_seconds: int = 3600
    http_timeout_seconds: int = 30

    run_scheduler: bool = True
    log_level: str = "INFO"


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
    """Load a YAML config file, hot-reloading when it changes on disk."""
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    return _load_yaml_cached(name, path.stat().st_mtime)


def radar_config() -> dict[str, Any]:
    return load_yaml_config("radar.yaml")


def engine_config() -> dict[str, Any]:
    return load_yaml_config("engine.yaml")
