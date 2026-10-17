import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tracebackai.evidence import SourceRef, parse_jsonl, parse_jsonl_lines
from tracebackai.storage import IncidentNotFoundError, Store

FIXTURE = Path(__file__).parent.parent / "fixtures/incidents/checkout_db_pool/logs.jsonl"


@pytest.fixture
def store() -> Iterator[Store]:
    with Store.open(":memory:") as s:
        yield s


def line(timestamp: str, message: str = "hello") -> str:
    return json.dumps(
        {"timestamp": timestamp, "level": "INFO", "service": "checkout", "message": message}
    )


# --- incidents ------------------------------------------------------------------------


def test_create_and_get_incident(store: Store) -> None:
    created = store.create_incident("Checkout 500s", "Checkout failing since 14:02 UTC")

    assert created.id.startswith("inc-")
    assert created.created_at.tzinfo is not None
    assert store.get_incident(created.id) == created


def test_get_unknown_incident_returns_none(store: Store) -> None:
    assert store.get_incident("inc-missing") is None


def test_incident_ids_are_unique(store: Store) -> None:
    ids = {store.create_incident("t", "d").id for _ in range(50)}

    assert len(ids) == 50


# --- evidence round trip --------------------------------------------------------------


def test_fixture_round_trips_unchanged(store: Store) -> None:
    parsed = parse_jsonl(FIXTURE).evidence
    incident = store.create_incident("t", "d")

    assert store.add_log_evidence(incident.id, parsed) == len(parsed)

    stored = store.list_log_evidence(incident.id)
    expected = sorted(parsed, key=lambda e: (e.timestamp, e.source.name, e.source.line))
    assert stored == expected


def test_evidence_is_listed_in_chronological_order(store: Store) -> None:
    # Out of file order, and with sub-second times either side of a whole second: a
    # variable-width timestamp format would sort these wrongly as strings.
    lines = [
        line("2026-10-05T14:00:01Z", "c"),
        line("2026-10-05T14:00:00.500Z", "b"),
        line("2026-10-05T14:00:00Z", "a"),
        line("2026-10-05T15:59:59+02:00", "first"),  # 13:59:59 UTC
    ]
    incident = store.create_incident("t", "d")
    store.add_log_evidence(incident.id, parse_jsonl_lines(lines, "src").evidence)

    assert [e.message for e in store.list_log_evidence(incident.id)] == [
        "first",
        "a",
        "b",
        "c",
    ]


def test_timestamps_come_back_as_utc(store: Store) -> None:
    incident = store.create_incident("t", "d")
    evidence = parse_jsonl_lines([line("2026-10-05T16:00:00.123456+02:00")], "src").evidence
    store.add_log_evidence(incident.id, evidence)

    [e] = store.list_log_evidence(incident.id)

    assert e.timestamp == datetime(2026, 10, 5, 14, 0, 0, 123456, tzinfo=UTC)
    assert e.timestamp.utcoffset().total_seconds() == 0


# --- idempotency and isolation --------------------------------------------------------


def test_reingesting_the_same_file_adds_nothing(store: Store) -> None:
    incident = store.create_incident("t", "d")
    store.add_log_evidence(incident.id, parse_jsonl(FIXTURE).evidence)

    assert store.add_log_evidence(incident.id, parse_jsonl(FIXTURE).evidence) == 0
    assert len(store.list_log_evidence(incident.id)) == 83


def test_appended_lines_are_the_only_new_rows(store: Store) -> None:
    lines = [line("2026-10-05T14:00:00Z", "a"), line("2026-10-05T14:00:01Z", "b")]
    incident = store.create_incident("t", "d")
    store.add_log_evidence(incident.id, parse_jsonl_lines(lines, "src").evidence)

    lines.append(line("2026-10-05T14:00:02Z", "c"))
    added = store.add_log_evidence(incident.id, parse_jsonl_lines(lines, "src").evidence)

    assert added == 1
    assert [e.message for e in store.list_log_evidence(incident.id)] == ["a", "b", "c"]


def test_same_evidence_can_belong_to_two_incidents(store: Store) -> None:
    evidence = parse_jsonl(FIXTURE).evidence
    first = store.create_incident("first", "d")
    second = store.create_incident("second", "d")

    store.add_log_evidence(first.id, evidence)

    assert store.add_log_evidence(second.id, evidence) == 83
    assert store.list_log_evidence(first.id) == store.list_log_evidence(second.id)


def test_evidence_does_not_leak_between_incidents(store: Store) -> None:
    with_logs = store.create_incident("with logs", "d")
    empty = store.create_incident("empty", "d")
    store.add_log_evidence(with_logs.id, parse_jsonl(FIXTURE).evidence)

    assert store.list_log_evidence(empty.id) == []


# --- errors ---------------------------------------------------------------------------


def test_adding_evidence_to_unknown_incident_raises(store: Store) -> None:
    with pytest.raises(IncidentNotFoundError) as exc_info:
        store.add_log_evidence("inc-missing", parse_jsonl(FIXTURE).evidence)

    assert exc_info.value.incident_id == "inc-missing"


def test_listing_evidence_of_unknown_incident_raises(store: Store) -> None:
    with pytest.raises(IncidentNotFoundError):
        store.list_log_evidence("inc-missing")


def test_failed_batch_writes_nothing(store: Store) -> None:
    incident = store.create_incident("t", "d")
    good = parse_jsonl_lines([line("2026-10-05T14:00:00Z")], "src").evidence
    # Fails inside executemany, after the first row was inserted: SQLite integers are
    # 64-bit, so binding this line number overflows. Only rollback keeps `good` out.
    bad = good[0].model_copy(update={"id": "log-bad", "source": SourceRef(name="src", line=2**70)})

    with pytest.raises(OverflowError):
        store.add_log_evidence(incident.id, [*good, bad])

    assert store.list_log_evidence(incident.id) == []


# --- persistence and schema -----------------------------------------------------------


def test_data_survives_reopening_the_file(tmp_path: Path) -> None:
    db = tmp_path / "traceback.db"
    with Store.open(db) as s:
        incident = s.create_incident("t", "d")
        s.add_log_evidence(incident.id, parse_jsonl(FIXTURE).evidence)

    with Store.open(db) as s:
        assert s.get_incident(incident.id) == incident
        assert len(s.list_log_evidence(incident.id)) == 83


def test_unknown_schema_version_is_refused(tmp_path: Path) -> None:
    db = tmp_path / "future.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 99")
    conn.close()

    with pytest.raises(RuntimeError, match="schema version 99"):
        Store.open(db)
