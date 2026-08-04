"""Settings (env) + strategy config (YAML, hot-reloadable).

Strategy values default to the VALIDATED research configuration (spec §7).
Changing any of them invalidates the §6 acceptance expectations — the replay
endpoint emits a warning when the active config differs from research defaults.
"""
from __future__ import annotations

import os
from dataclasses import asdict

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

from .engine.core import BookCfg, SignalCfg, TradeCfg


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/paperengine.db"
    cache_dir: str = "./data/cache"
    strategy_file: str = ""              # optional YAML override path

    run_engine: bool = True
    poll_seconds: int = 60
    stale_seconds: int = 600
    price_sanity_pct: float = 5.0        # Bitstamp-vs-Kraken deviation halt
    warmup_bars: int = 210
    cash_apy: float = 0.04           # idle capital earns T-bill-ish yield
    history_bars: int = 800              # indicator window kept in memory/DB

    frontend_dist: str | None = None
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    log_level: str = "INFO"
    # Shared secret for /exec/target (the live-executor signal feed). Empty =
    # endpoint open (dev); set in production so book state isn't public.
    exec_token: str = ""

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

RESEARCH_BOOKS = [
    BookCfg(name="S1", sizing="vol_target", risk=0.055, long_mult=0.75, cap=3.0,
            start_equity=100_000.0, dd_halt=0.30),
    BookCfg(name="S2", sizing="fixed", leverage=1.95, long_mult=0.75, cap=2.5,
            start_equity=100_000.0, dd_halt=0.45),
    BookCfg(name="S3", sizing="fixed", leverage=1.0, long_mult=1.0, cap=1.0,
            start_equity=100_000.0, dd_halt=0.30),
    # S4: Donchian-20 trend book (RESEARCH_S4.md) — the diversifier. 12y of
    # validated trend edge, corr -0.15 to the pullback; expected to bleed in
    # chop and print in sustained trends. dd_halt is wide by design (trend
    # strategies live through -40% book drawdowns).
    BookCfg(name="S4", sizing="fixed", strategy="donchian", trail_atr=5.0,
            leverage=1.0, long_mult=1.0, cap=1.0,
            start_equity=100_000.0, dd_halt=0.50),
]
RESEARCH_SIGNAL = SignalCfg()
RESEARCH_TRADE = TradeCfg()


def load_strategy() -> tuple[list[BookCfg], SignalCfg, TradeCfg, bool]:
    """(books, signal_cfg, trade_cfg, is_research_default). YAML override via
    STRATEGY_FILE; absent/invalid -> research defaults."""
    path = settings.strategy_file
    if not path or not os.path.exists(path):
        return RESEARCH_BOOKS, RESEARCH_SIGNAL, RESEARCH_TRADE, True
    try:
        raw = yaml.safe_load(open(path)) or {}
        scfg = SignalCfg(**raw.get("signal", {}))
        tcfg = TradeCfg(**raw.get("trade", {}))
        books = [BookCfg(name=k, **v) for k, v in raw.get("books", {}).items()] \
            or RESEARCH_BOOKS
        is_default = (asdict(scfg) == asdict(RESEARCH_SIGNAL)
                      and asdict(tcfg) == asdict(RESEARCH_TRADE)
                      and [asdict(b) for b in books] == [asdict(b) for b in RESEARCH_BOOKS])
        return books, scfg, tcfg, is_default
    except Exception:  # noqa: BLE001
        return RESEARCH_BOOKS, RESEARCH_SIGNAL, RESEARCH_TRADE, True
