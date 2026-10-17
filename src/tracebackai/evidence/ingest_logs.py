"""Parse JSON-lines log files into LogEvidence.

Bad lines never abort a file and are never silently dropped: each one becomes an
IngestError with its line number and reason.
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from tracebackai.evidence.models import LogEvidence, LogLevel, SourceRef, make_evidence_id

# Canonical field -> keys accepted for it, in priority order. The first key present wins;
# any other alias present stays in attributes.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "@timestamp", "ts", "time"),
    "level": ("level", "severity", "lvl"),
    "message": ("message", "msg"),
    "service": ("service", "service.name", "app"),
}


class IngestError(BaseModel):
    line: int
    reason: str
    raw: str


class IngestResult(BaseModel):
    evidence: list[LogEvidence]
    errors: list[IngestError]


def parse_jsonl(path: Path, source_name: str | None = None) -> IngestResult:
    """Parse a JSON-lines log file. `source_name` defaults to the file name."""
    with path.open(encoding="utf-8") as f:
        return parse_jsonl_lines(f, source_name or path.name)


def parse_jsonl_lines(lines: Iterable[str], source_name: str) -> IngestResult:
    """Parse JSON-lines log records. Line numbers are 1-based and count blank lines."""
    evidence: list[LogEvidence] = []
    errors: list[IngestError] = []

    for line_no, raw_line in enumerate(lines, start=1):
        raw = raw_line.rstrip("\r\n")
        if not raw.strip():
            continue
        try:
            evidence.append(_parse_record(raw, line_no, source_name))
        except ValueError as exc:  # ValidationError and JSONDecodeError are ValueErrors
            errors.append(IngestError(line=line_no, reason=_describe(exc), raw=raw))

    return IngestResult(evidence=evidence, errors=errors)


def _parse_record(raw: str, line_no: int, source_name: str) -> LogEvidence:
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise ValueError(f"expected a JSON object, got {type(record).__name__}")

    attributes: dict[str, Any] = dict(record)
    fields: dict[str, Any] = {}
    for field, aliases in FIELD_ALIASES.items():
        key = next((k for k in aliases if k in attributes), None)
        if key is None:
            raise ValueError(f"missing required field {field!r} (accepted keys: {aliases})")
        fields[field] = attributes.pop(key)

    if not isinstance(fields["level"], str):
        raise ValueError(f"level must be a string, got {fields['level']!r}")
    fields["level"] = LogLevel.from_raw(fields["level"])

    return LogEvidence(
        id=make_evidence_id(source_name, line_no, raw),
        attributes=attributes,
        source=SourceRef(name=source_name, line=line_no),
        **fields,
    )


def _describe(exc: ValueError) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return f"invalid JSON: {exc.msg}"
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
    return str(exc)
