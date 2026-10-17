import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tracebackai.evidence import LogLevel, parse_jsonl, parse_jsonl_lines

FIXTURE = Path(__file__).parent.parent / "fixtures/incidents/checkout_db_pool/logs.jsonl"


def line(**fields: object) -> str:
    base = {
        "timestamp": "2026-10-05T14:00:00Z",
        "level": "INFO",
        "service": "checkout",
        "message": "hello",
    }
    return json.dumps(base | fields)


# --- sample incident ------------------------------------------------------------------


def test_fixture_parses_without_errors() -> None:
    result = parse_jsonl(FIXTURE)

    assert result.errors == []
    assert len(result.evidence) == 83
    assert {e.service for e in result.evidence} == {
        "api-gateway",
        "checkout",
        "payments",
        "inventory",
    }


def test_fixture_contains_the_deploy_that_causes_the_incident() -> None:
    evidence = parse_jsonl(FIXTURE).evidence

    config = next(e for e in evidence if e.message == "config loaded")
    assert config.attributes["db.pool.max_size"] == 5
    assert config.timestamp == datetime(2026, 10, 5, 14, 1, 45, tzinfo=UTC)


# --- IDs ------------------------------------------------------------------------------


def test_ids_are_stable_across_parses() -> None:
    first = [e.id for e in parse_jsonl(FIXTURE).evidence]
    second = [e.id for e in parse_jsonl(FIXTURE).evidence]

    assert first == second


def test_ids_are_unique_within_a_file() -> None:
    ids = [e.id for e in parse_jsonl(FIXTURE).evidence]

    assert len(ids) == len(set(ids))


def test_ids_do_not_depend_on_file_location(tmp_path: Path) -> None:
    copy = tmp_path / "elsewhere" / FIXTURE.name
    copy.parent.mkdir()
    shutil.copy(FIXTURE, copy)

    assert [e.id for e in parse_jsonl(copy).evidence] == [
        e.id for e in parse_jsonl(FIXTURE).evidence
    ]


def test_id_changes_when_line_content_changes() -> None:
    [a] = parse_jsonl_lines([line(message="one")], "src").evidence
    [b] = parse_jsonl_lines([line(message="two")], "src").evidence

    assert a.id != b.id
    assert a.id.startswith("log-")


def test_identical_lines_get_distinct_ids() -> None:
    # Real logs repeat lines (same timestamp, same message); each is separate evidence.
    a, b = parse_jsonl_lines([line(), line()], "src").evidence

    assert a.id != b.id


def test_source_name_defaults_to_file_name() -> None:
    first = parse_jsonl(FIXTURE).evidence[0]

    assert first.source.name == "logs.jsonl"
    assert first.source.line == 1


# --- normalisation --------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["2026-10-05T16:00:00+02:00", "2026-10-05T14:00:00Z", "2026-10-05T09:00:00-05:00"],
)
def test_timestamps_are_normalised_to_utc(raw: str) -> None:
    [e] = parse_jsonl_lines([line(timestamp=raw)], "src").evidence

    assert e.timestamp == datetime(2026, 10, 5, 14, 0, tzinfo=UTC)
    assert e.timestamp.utcoffset() is not None
    assert e.timestamp.utcoffset().total_seconds() == 0


def test_epoch_timestamp_is_accepted() -> None:
    epoch = datetime(2026, 10, 5, 14, 0, tzinfo=UTC).timestamp()

    [e] = parse_jsonl_lines([line(timestamp=epoch)], "src").evidence

    assert e.timestamp == datetime(2026, 10, 5, 14, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("info", LogLevel.INFO),
        ("warn", LogLevel.WARNING),
        ("Warning", LogLevel.WARNING),
        ("err", LogLevel.ERROR),
        ("fatal", LogLevel.CRITICAL),
        ("trace", LogLevel.DEBUG),
    ],
)
def test_level_aliases(raw: str, expected: LogLevel) -> None:
    [e] = parse_jsonl_lines([line(level=raw)], "src").evidence

    assert e.level is expected


def test_field_aliases_and_extra_attributes() -> None:
    raw = json.dumps(
        {"ts": "2026-10-05T14:00:00Z", "lvl": "warn", "app": "inventory", "msg": "hi", "sku": 7}
    )

    [e] = parse_jsonl_lines([raw], "src").evidence

    assert (e.service, e.level, e.message) == ("inventory", LogLevel.WARNING, "hi")
    assert e.attributes == {"sku": 7}


# --- errors ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "reason_contains"),
    [
        ("{not json", "invalid JSON"),
        ("[1, 2, 3]", "expected a JSON object"),
        (
            json.dumps({"timestamp": "2026-10-05T14:00:00Z", "level": "INFO", "service": "x"}),
            "missing required field 'message'",
        ),
        (line(timestamp="2026-10-05T14:00:00"), "timezone"),  # naive timestamp
        (line(level="LOUD"), "unknown log level"),
        (line(level=3), "level must be a string"),
    ],
)
def test_bad_lines_become_errors(raw: str, reason_contains: str) -> None:
    result = parse_jsonl_lines([line(), raw, line()], "src")

    assert len(result.evidence) == 2  # parsing continues past the bad line
    [error] = result.errors
    assert error.line == 2
    assert reason_contains in error.reason
    assert error.raw == raw


def test_blank_lines_are_skipped_but_counted() -> None:
    result = parse_jsonl_lines([line(), "\n", "   \n", line()], "src")

    assert result.errors == []
    assert [e.source.line for e in result.evidence] == [1, 4]
