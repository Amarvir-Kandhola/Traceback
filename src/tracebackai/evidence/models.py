"""Evidence models: the facts the LLM may cite, each with a stable ID."""

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_raw(cls, raw: str) -> "LogLevel":
        """Map a level string from any common logging library to a LogLevel.

        Raises ValueError for unknown levels.
        """
        key = raw.strip().upper()
        aliases = {
            "TRACE": cls.DEBUG,
            "WARN": cls.WARNING,
            "ERR": cls.ERROR,
            "FATAL": cls.CRITICAL,
            "CRIT": cls.CRITICAL,
        }
        if key in aliases:
            return aliases[key]
        try:
            return cls(key)
        except ValueError:
            raise ValueError(f"unknown log level {raw!r}") from None


class SourceRef(BaseModel):
    """Where a piece of evidence came from: a logical source name and 1-based line."""

    model_config = ConfigDict(frozen=True)

    name: str
    line: int


class LogEvidence(BaseModel):
    """A single log line, normalised."""

    model_config = ConfigDict(frozen=True)

    id: str
    timestamp: AwareDatetime
    service: str
    level: LogLevel
    message: str
    attributes: dict[str, Any] = {}
    source: SourceRef

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


def make_evidence_id(source_name: str, line: int, raw_line: str) -> str:
    """Deterministic ID for a log line.

    Hashing the source name, line number and raw content means re-ingesting the same file
    gives the same IDs (so citations stay valid), the ID does not depend on where the file
    lives on disk, and editing a line changes its ID rather than silently re-pointing old
    citations at new content.
    """
    digest = hashlib.sha256(f"{source_name}\x00{line}\x00{raw_line}".encode()).hexdigest()
    return f"log-{digest[:12]}"
