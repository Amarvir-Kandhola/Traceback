"""SQLite persistence for incidents and their evidence.

Evidence is keyed by (incident_id, evidence id). Evidence IDs are content hashes, so
re-ingesting the same file into the same incident inserts nothing new.
"""

import json
import sqlite3
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from tracebackai.evidence.models import LogEvidence, LogLevel, SourceRef
from tracebackai.incidents import Incident

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS log_evidence (
    incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    id          TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    service     TEXT NOT NULL,
    level       TEXT NOT NULL,
    message     TEXT NOT NULL,
    attributes  TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_line INTEGER NOT NULL,
    PRIMARY KEY (incident_id, id)
);

CREATE INDEX IF NOT EXISTS log_evidence_by_time
    ON log_evidence (incident_id, timestamp);
"""

# Fixed-width UTC format so that string order in SQL equals chronological order.
# (datetime.isoformat() omits microseconds when they are zero, which breaks that.)
_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class IncidentNotFoundError(LookupError):
    def __init__(self, incident_id: str) -> None:
        super().__init__(f"incident {incident_id!r} not found")
        self.incident_id = incident_id


class Store:
    """Repository over one SQLite connection. Use as a context manager to close it."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    @classmethod
    def open(cls, path: Path | str) -> Self:
        """Open (creating if needed) the database at `path`. ":memory:" works too."""
        return cls(sqlite3.connect(path))

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # --- incidents --------------------------------------------------------------------

    def create_incident(self, title: str, description: str) -> Incident:
        incident = Incident(
            id=f"inc-{uuid.uuid4().hex[:12]}",
            title=title,
            description=description,
            created_at=datetime.now(UTC),
        )
        with self._conn:
            self._conn.execute(
                "INSERT INTO incidents (id, title, description, created_at) VALUES (?, ?, ?, ?)",
                (incident.id, incident.title, incident.description, _ts(incident.created_at)),
            )
        return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        row = self._conn.execute(
            "SELECT id, title, description, created_at FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()
        if row is None:
            return None
        return Incident(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # --- evidence ---------------------------------------------------------------------

    def add_log_evidence(self, incident_id: str, evidence: Iterable[LogEvidence]) -> int:
        """Attach evidence to an incident. Returns how many rows were new.

        Evidence already attached (same ID) is skipped, so re-ingesting a file is safe.
        The whole batch is one transaction: on error nothing is written.
        """
        rows = [
            (
                incident_id,
                e.id,
                _ts(e.timestamp),
                e.service,
                e.level.value,
                e.message,
                json.dumps(e.attributes),
                e.source.name,
                e.source.line,
            )
            for e in evidence
        ]
        with self._conn:
            self._require_incident(incident_id)
            before = self._conn.total_changes
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO log_evidence (
                    incident_id, id, timestamp, service, level, message,
                    attributes, source_name, source_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return self._conn.total_changes - before

    def list_log_evidence(self, incident_id: str) -> list[LogEvidence]:
        """All evidence for an incident, in chronological order (ties: source, line)."""
        self._require_incident(incident_id)
        rows = self._conn.execute(
            """
            SELECT id, timestamp, service, level, message, attributes, source_name, source_line
            FROM log_evidence
            WHERE incident_id = ?
            ORDER BY timestamp, source_name, source_line
            """,
            (incident_id,),
        ).fetchall()
        return [_row_to_log_evidence(row) for row in rows]

    def _require_incident(self, incident_id: str) -> None:
        exists = self._conn.execute(
            "SELECT 1 FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        if exists is None:
            raise IncidentNotFoundError(incident_id)

    def _init_schema(self) -> None:
        (version,) = self._conn.execute("PRAGMA user_version").fetchone()
        if version not in (0, SCHEMA_VERSION):
            raise RuntimeError(
                f"database schema version {version} is not supported (expected "
                f"{SCHEMA_VERSION}); there are no migrations yet"
            )
        with self._conn:
            self._conn.executescript(SCHEMA)
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _ts(value: datetime) -> str:
    return value.astimezone(UTC).strftime(_TS_FORMAT)


def _row_to_log_evidence(row: sqlite3.Row) -> LogEvidence:
    return LogEvidence(
        id=row["id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        service=row["service"],
        level=LogLevel(row["level"]),
        message=row["message"],
        attributes=json.loads(row["attributes"]),
        source=SourceRef(name=row["source_name"], line=row["source_line"]),
    )
