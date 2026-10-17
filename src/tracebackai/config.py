"""Application settings, read from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = "traceback.db"


@dataclass(frozen=True)
class Settings:
    db_path: Path


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from `env` (defaults to the process environment)."""
    env = os.environ if env is None else env
    return Settings(db_path=Path(env.get("TRACEBACK_DB_PATH", DEFAULT_DB_PATH)))
