"""Config loading + canonical config hashing.

All results must be reproducible from (config hash, data snapshot). The hash
is a sha256 over the canonical (sorted-key, stringified) YAML content of the
config mapping actually used for a run — not the file bytes — so cosmetic
edits (comments, key order) don't change identity but any semantic change does.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# Repo layout: <root>/config/*.yaml, <root>/data/, <root>/src/barbell/config.py
ROOT = Path(os.environ.get("BARBELL_ROOT", Path(__file__).resolve().parents[2]))
CONFIG_DIR = ROOT / "config"
DATA_DIR = Path(os.environ.get("BARBELL_DATA_DIR", ROOT / "data"))
PARQUET_DIR = DATA_DIR / "parquet"
REPORT_DIR = Path(os.environ.get("BARBELL_REPORT_DIR", DATA_DIR / "reports"))


def load(name: str) -> dict[str, Any]:
    """Load config/<name>.yaml. Missing file is a hard error (fail loudly)."""
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"required config missing: {path}")
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return cfg


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def config_hash(cfg: dict[str, Any]) -> str:
    """sha256 of the canonicalized config mapping (first 16 hex chars)."""
    canon = json.dumps(_jsonable(cfg), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def ensure_dirs() -> None:
    for d in (DATA_DIR, PARQUET_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)
