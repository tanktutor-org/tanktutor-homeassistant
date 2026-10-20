"""Persistent queue of readings waiting to be sent to TankTutor.

Pure Python on purpose: no Home Assistant import, so it is fast to test.
Limits mirror the TankTutor API (see docs/spec.md, section 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

MAX_BATCH = 60
# The server accepts readings up to 7 days old; stay one hour inside that limit.
MAX_AGE = timedelta(days=6, hours=23)
DEFAULT_MAX_SIZE = 2000


@dataclass(frozen=True)
class Reading:
    type: str
    value: float
    measured_at: datetime
    unit: str | None = None
    name: str | None = None

    @property
    def identity(self) -> tuple[str, str | None, datetime]:
        return (self.type, self.name, self.measured_at)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "value": self.value,
            "measuredAt": self.measured_at.isoformat(),
        }
        if self.unit is not None:
            payload["unit"] = self.unit
        if self.name is not None:
            payload["name"] = self.name
        return payload

    def to_dict(self) -> dict[str, Any]:
        return self.to_payload()

    @classmethod
    def from_dict(cls, data: Any) -> Reading | None:
        try:
            measured_at = datetime.fromisoformat(data["measuredAt"])
            if measured_at.tzinfo is None:
                measured_at = measured_at.replace(tzinfo=timezone.utc)
            return cls(
                type=str(data["type"]),
                value=float(data["value"]),
                measured_at=measured_at,
                unit=data.get("unit"),
                name=data.get("name"),
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            return None


class ReadingQueue:
    def __init__(self, max_size: int = DEFAULT_MAX_SIZE) -> None:
        self._max_size = max_size
        self._readings: list[Reading] = []

    def __len__(self) -> int:
        return len(self._readings)

    def add(self, reading: Reading) -> None:
        # A later value for the same (type, name, instant) replaces the earlier one.
        self._readings = [r for r in self._readings if r.identity != reading.identity]
        self._readings.append(reading)
        self._enforce_cap()

    def _enforce_cap(self) -> None:
        while len(self._readings) > self._max_size:
            # Events are rarer and matter more: drop the oldest numeric reading first.
            numeric = [r for r in self._readings if r.type != "event"]
            pool = numeric or self._readings
            self._readings.remove(min(pool, key=lambda r: r.measured_at))

    def next_batch(self, now: datetime) -> list[Reading]:
        self._readings = [r for r in self._readings if now - r.measured_at <= MAX_AGE]
        return sorted(self._readings, key=lambda r: r.measured_at)[:MAX_BATCH]

    def confirm(self, sent: list[Reading]) -> None:
        self._readings = [r for r in self._readings if r not in sent]

    def to_dict(self) -> dict[str, Any]:
        return {"readings": [r.to_dict() for r in self._readings]}

    @classmethod
    def from_dict(cls, data: dict[str, Any], max_size: int = DEFAULT_MAX_SIZE) -> ReadingQueue:
        queue = cls(max_size)
        for item in data.get("readings", []):
            reading = Reading.from_dict(item)
            if reading is not None:
                queue.add(reading)
        return queue
