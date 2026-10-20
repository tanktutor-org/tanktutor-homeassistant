"""Keeping the latest value per type and moving it to the queue once per window."""

from datetime import datetime, timedelta, timezone

from custom_components.tanktutor.collector import Collector
from custom_components.tanktutor.queue import Reading, ReadingQueue

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def temp(value: float, seconds: int = 0) -> Reading:
    return Reading(type="temperature", value=value, unit="C", measured_at=T0 + timedelta(seconds=seconds))


def values(queue: ReadingQueue) -> list[float]:
    return [r.value for r in queue.next_batch(T0 + timedelta(hours=1))]


def test_only_the_latest_value_is_kept():
    queue, collector = ReadingQueue(), Collector()
    collector.offer(temp(24.0, 0))
    collector.offer(temp(24.5, 30))
    collector.drain(T0 + timedelta(seconds=40), queue)
    assert values(queue) == [24.5]


def test_first_drain_is_immediate():
    queue, collector = ReadingQueue(), Collector()
    collector.offer(temp(24.0))
    collector.drain(T0, queue)
    assert len(queue) == 1


def test_drain_happens_once_per_five_minutes():
    queue, collector = ReadingQueue(), Collector()
    collector.offer(temp(24.0, 0))
    collector.drain(T0, queue)
    collector.offer(temp(25.0, 60))
    collector.drain(T0 + timedelta(minutes=2), queue)
    assert values(queue) == [24.0]  # the newer value is still waiting
    collector.drain(T0 + timedelta(minutes=5), queue)
    assert values(queue) == [24.0, 25.0]


def test_a_value_is_not_queued_twice():
    queue, collector = ReadingQueue(), Collector()
    collector.offer(temp(24.0))
    collector.drain(T0, queue)
    collector.drain(T0 + timedelta(minutes=10), queue)
    assert values(queue) == [24.0]


def test_events_are_all_kept():
    queue, collector = ReadingQueue(), Collector()
    collector.offer(Reading(type="event", name="leak", value=1, measured_at=T0))
    collector.offer(Reading(type="event", name="leak", value=0, measured_at=T0 + timedelta(seconds=20)))
    collector.drain(T0 + timedelta(seconds=30), queue)
    assert [r.value for r in queue.next_batch(T0 + timedelta(hours=1))] == [1, 0]
