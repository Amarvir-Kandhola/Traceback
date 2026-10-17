# Architecture

Traceback turns an incident description plus raw evidence into a root-cause hypothesis
whose claims cite evidence IDs. Deterministic code collects, stores and narrows the
evidence; the LLM only interprets what it is given.

## Data flow

```
log file (JSONL)
  │  evidence.parse_jsonl            per-line errors reported, never dropped
  ▼
LogEvidence (id = content hash)
  │  storage.Store.add_log_evidence  idempotent per (incident, evidence id)
  ▼
SQLite: incidents, log_evidence
  │  retrieval      (planned)        narrow to relevant candidates
  │  timeline       (planned)        order, group, find onset
  │  llm + analysis (planned)        structured hypothesis, citations validated
  ▼
Hypothesis with evidence-backed claims
```

## Modules (`src/tracebackai/`)

| Module | Responsibility |
| --- | --- |
| `config.py` | `Settings` from environment variables (`TRACEBACK_DB_PATH`). |
| `incidents.py` | `Incident` model. |
| `evidence/models.py` | `LogEvidence`, `LogLevel`, `SourceRef`, `make_evidence_id`. |
| `evidence/ingest_logs.py` | JSON-lines parser → `IngestResult(evidence, errors)`. |
| `storage/store.py` | `Store`: SQLite repository for incidents and log evidence. |
| `main.py` | FastAPI app (`/health` so far). |
| `retrieval/`, `llm/`, `analysis/` | Empty; see the roadmap in CLAUDE.md. |

## Storage

Two tables. `incidents(id, title, description, created_at)` and
`log_evidence(incident_id, id, timestamp, service, level, message, attributes,
source_name, source_line)` with primary key `(incident_id, id)` and an index on
`(incident_id, timestamp)`.

- Timestamps are stored as fixed-width UTC strings (`2026-10-05T14:00:00.000000Z`) so
  that SQL string ordering equals chronological ordering.
- `attributes` is a JSON string.
- The schema version lives in `PRAGMA user_version`. A database with an unknown version
  is refused; there are no migrations yet.
- Each `add_log_evidence` call is one transaction.

## Invariants

- Evidence IDs are deterministic: the same source name, line number and content always
  give the same ID.
- Re-ingesting a file into an incident never creates duplicates.
- No input line is silently discarded: it becomes evidence or an `IngestError`.
- Timestamps are timezone-aware and normalised to UTC everywhere.
