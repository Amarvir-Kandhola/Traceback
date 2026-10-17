from pathlib import Path

from tracebackai.config import DEFAULT_DB_PATH, load_settings


def test_db_path_defaults_when_unset() -> None:
    assert load_settings({}).db_path == Path(DEFAULT_DB_PATH)


def test_db_path_read_from_environment() -> None:
    assert load_settings({"TRACEBACK_DB_PATH": "/data/tb.db"}).db_path == Path("/data/tb.db")
