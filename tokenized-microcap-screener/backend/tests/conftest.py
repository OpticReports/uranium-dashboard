"""Test env must be set BEFORE app.config is imported: it binds settings at
import time. Scheduler off and a throwaway SQLite file so no test ever touches the
network or the real database."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile

os.environ.setdefault("RUN_SCHEDULER", "false")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{tempfile.mkdtemp(prefix='tms-db-')}/test.db")
os.environ.setdefault("CACHE_DIR", tempfile.mkdtemp(prefix="tms-cache-"))

import pytest  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="session")
def universe() -> dict[str, str]:
    from app.lanes.equity import parse_sec_universe
    return parse_sec_universe(load("sec_company_tickers.json"))


@pytest.fixture(scope="session")
def cfg() -> dict:
    import yaml
    from app.config import CONFIG_DIR
    return yaml.safe_load((CONFIG_DIR / "screener.yaml").read_text())


@pytest.fixture(scope="session")
def markers(cfg):
    from app.engine.registry import markers_from_config
    return markers_from_config(cfg["issuer_markers"])


@pytest.fixture(scope="session")
def base_assets(cfg) -> set[str]:
    return {s.upper() for s in cfg["base_assets"]}


@pytest.fixture(scope="session")
def fami_pairs():
    return load("robinhood_fami_token_pairs.json")


@pytest.fixture(scope="session")
def nvda_pairs():
    return load("search_nvda.json")["pairs"]


@pytest.fixture(scope="session")
def mu_pairs():
    return load("search_mu.json")["pairs"]
