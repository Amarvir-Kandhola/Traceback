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
