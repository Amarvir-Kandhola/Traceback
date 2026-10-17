# Decisions

## 2026-10-12 — Package name `tracebackai`
`traceback` is a stdlib module used by logging, pytest and FastAPI's error handling; a
package with that name would shadow it. The import package is `tracebackai`, the
distribution name `traceback-ai`.

## 2026-10-12 — src/ layout
Code lives in `src/tracebackai/`. With a flat layout, tests can import the package straight
from the working directory even if packaging is broken. With src/, tests only pass against
the installed package, so packaging mistakes surface immediately.

## 2026-10-12 — hatchling as build backend
Minimal config in `pyproject.toml`, no `setup.py`. Alternatives: setuptools (more legacy
configuration surface), poetry/uv build backends (tie the project to a specific tool).

## 2026-10-12 — ruff rules E, F, I, UP, B
pycodestyle errors, pyflakes, import sorting, pyupgrade (modern 3.12 syntax) and bugbear
(likely bugs). A small, uncontroversial set; widen later if useful.

## 2026-10-12 — Pydantic models for evidence
Evidence is a Pydantic model rather than a dataclass. We get validation (tz-aware
timestamps, level enum) and JSON schema for free, and the LLM output schema will be Pydantic
anyway, so one modelling approach covers both. Cost: a dependency we already had via FastAPI.

## 2026-10-12 — Deterministic evidence IDs
`log-` + 12 hex chars of sha256(source name, line number, raw line). The alternatives were
UUIDs (different on every ingest, so a saved citation breaks when logs are re-ingested) and
database autoincrement (ties IDs to insertion order and to storage). Hashing the content
means an edited line gets a new ID instead of silently re-pointing old citations. The source
name, not the absolute path, is hashed so IDs are the same on any machine. 48 bits makes
collisions negligible at the scale of one investigation.

The line number is hashed so that identical lines (common in real logs) get distinct IDs.
This assumes log files are append-only: appending keeps existing IDs stable, but inserting a
line would change the IDs of every line after it. The alternative, content plus an
occurrence counter, survives insertions but is harder to reason about; revisit if a source
turns out not to be append-only.

## 2026-10-12 — Reject naive timestamps
A log timestamp without a timezone is an ingest error rather than being assumed to be UTC.
Guessing wrong would shift one service's events by hours and silently corrupt the timeline,
which is exactly what the tool exists to reconstruct. An explicit "assume timezone" option
can be added when a real source needs it.

## 2026-10-12 — JSON-lines as the first log format
Structured JSON logs are the common case for modern services and need no per-format
parsing. Field aliases cover the usual shapes (`ts`/`@timestamp`, `msg`, `severity`,
`service.name`). Plain-text formats (regex per format) are deferred.

## 2026-10-17 — stdlib `sqlite3`, no ORM
Storage uses Python's built-in `sqlite3` behind a small `Store` class. The alternatives
were SQLAlchemy (Core or ORM) and SQLModel. With two tables and a handful of queries an
ORM adds a dependency and a layer of indirection without removing much code, and plain
SQL is easier to explain and debug. All SQL lives in `storage/store.py`, so moving to
SQLAlchemy (e.g. for PostgreSQL) later means rewriting one module.

## 2026-10-17 — Evidence keyed by (incident_id, evidence id)
Evidence IDs come from content, not from the incident, so the same log file attached to
two incidents produces the same IDs. A composite primary key lets each incident hold its
own copy, and `INSERT OR IGNORE` on that key makes re-ingesting idempotent. The
alternative, one global evidence table plus a join table, avoids duplicate rows but adds
a table and a join for little gain at this scale. Because the ID hashes the content, an
ID collision with different content is not a realistic concern, so ignoring on conflict
does not hide changed data.

## 2026-10-17 — Fixed-width UTC timestamp strings in SQLite
SQLite has no datetime type. Timestamps are stored as `%Y-%m-%dT%H:%M:%S.%fZ` in UTC.
Fixed width makes `ORDER BY timestamp` chronological; `datetime.isoformat()` drops
`.000000` when microseconds are zero and would not be safe to sort as text in general.
The alternative, epoch floats, sorts correctly but is unreadable when inspecting the
database and loses microsecond precision for current dates.

## 2026-10-17 — Schema versioning via `PRAGMA user_version`
The schema is created with `CREATE TABLE IF NOT EXISTS` and stamped with a version
number. Opening a database with a different version raises instead of guessing. A
migration tool (e.g. Alembic) is not justified until the schema changes after real data
exists.
