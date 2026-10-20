"""Unit tests for the persistent reading queue (pure Python, no Home Assistant)."""

from datetime import datetime, timedelta, timezone

from custom_components.tanktutor.queue import Reading, ReadingQueue

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def temp(value: float, minutes_ago: int = 0, unit: str | None = "C") -> Reading:
    return Reading(
        type="temperature",
        value=value,
        unit=unit,
        measured_at=NOW - timedelta(minutes=minutes_ago),
    )


def test_payload_has_only_the_fields_the_api_accepts():
    payload = temp(24.5).to_payload()
    assert payload == {
        "type": "temperature",
        "value": 24.5,
        "unit": "C",
        "measuredAt": "2026-10-20T12:00:00+00:00",
    }


def test_payload_omits_unit_when_none():
    assert "unit" not in temp(24.5, unit=None).to_payload()


def test_batch_is_oldest_first():
    queue = ReadingQueue()
    queue.add(temp(25.0, minutes_ago=5))
    queue.add(temp(24.0, minutes_ago=10))
    batch = queue.next_batch(NOW)
    assert [r.value for r in batch] == [24.0, 25.0]


def test_batch_is_capped_at_60_readings():
    queue = ReadingQueue()
    for i in range(70):
        queue.add(temp(20.0 + i / 100, minutes_ago=i))
    assert len(queue.next_batch(NOW)) == 60


def test_batch_never_repeats_type_name_and_timestamp():
    queue = ReadingQueue()
    queue.add(temp(24.0, minutes_ago=3))
    queue.add(temp(24.1, minutes_ago=3))
    batch = queue.next_batch(NOW)
    assert len(batch) == 1
    # the later value for the same instant wins
    assert batch[0].value == 24.1


def test_readings_older_than_six_days_23_hours_are_dropped():
    queue = ReadingQueue()
    queue.add(temp(20.0, minutes_ago=(6 * 24 + 23) * 60 + 1))
    queue.add(temp(21.0, minutes_ago=60))
    batch = queue.next_batch(NOW)
    assert [r.value for r in batch] == [21.0]
    assert len(queue) == 1


def test_confirm_removes_only_the_sent_readings():
    queue = ReadingQueue()
    queue.add(temp(24.0, minutes_ago=10))
    queue.add(temp(25.0, minutes_ago=5))
    batch = queue.next_batch(NOW)
    queue.add(temp(26.0, minutes_ago=1))
    queue.confirm(batch)
    assert [r.value for r in queue.next_batch(NOW)] == [26.0]


def test_cap_drops_the_oldest_readings_first():
    queue = ReadingQueue(max_size=3)
    for i, minutes in enumerate([40, 30, 20, 10]):
        queue.add(temp(float(i), minutes_ago=minutes))
    assert [r.value for r in queue.next_batch(NOW)] == [1.0, 2.0, 3.0]


def test_cap_keeps_events_over_numeric_readings():
    queue = ReadingQueue(max_size=2)
    queue.add(Reading(type="event", value=1, name="leak", measured_at=NOW - timedelta(minutes=50)))
    queue.add(temp(24.0, minutes_ago=40))
    queue.add(temp(25.0, minutes_ago=30))
    values = [(r.type, r.value) for r in queue.next_batch(NOW)]
    assert ("event", 1) in values
    assert ("temperature", 24.0) not in values


def test_round_trip_through_storage_format():
    queue = ReadingQueue()
    queue.add(temp(24.0, minutes_ago=10))
    queue.add(Reading(type="event", value=1, name="leak", measured_at=NOW))
    restored = ReadingQueue.from_dict(queue.to_dict())
    assert [r.to_payload() for r in restored.next_batch(NOW)] == [
        r.to_payload() for r in queue.next_batch(NOW)
    ]


def test_from_dict_ignores_malformed_entries():
    restored = ReadingQueue.from_dict({"readings": [{"type": "temperature"}, "junk"]})
    assert len(restored) == 0
