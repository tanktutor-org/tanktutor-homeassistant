"""Keeps the latest value per mapped type and hands it to the queue once per window."""

from __future__ import annotations

from datetime import datetime, timedelta

from .queue import Reading, ReadingQueue

DRAIN_INTERVAL = timedelta(minutes=5)


class Collector:
    def __init__(self) -> None:
        self._latest: dict[tuple[str, str | None], Reading] = {}
        self._events: list[Reading] = []
        self._last_drain: datetime | None = None

    def offer(self, reading: Reading) -> None:
        if reading.type == "event":
            # Every transition matters: when it happened is part of the information.
            self._events.append(reading)
        else:
            self._latest[(reading.type, reading.name)] = reading

    def drain(self, now: datetime, queue: ReadingQueue) -> None:
        if self._events:
            for event in self._events:
                queue.add(event)
            self._events = []
        if self._last_drain is not None and now - self._last_drain < DRAIN_INTERVAL:
            return
        self._last_drain = now
        for reading in self._latest.values():
            queue.add(reading)
        self._latest = {}
