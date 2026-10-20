"""Send scheduling: windows, backoff and error handling (no network, no Home Assistant)."""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.tanktutor.client import (
    AuthError,
    BadRequest,
    PostResult,
    RateLimited,
    ServerError,
    Suspended,
)
from custom_components.tanktutor.queue import Reading, ReadingQueue
from custom_components.tanktutor.sender import Sender

# 12:02:30 UTC: inside the 12:00-12:05 window.
NOW = datetime(2026, 10, 20, 12, 2, 30, tzinfo=timezone.utc)
NEXT_WINDOW = datetime(2026, 10, 20, 12, 5, 5, tzinfo=timezone.utc)  # boundary + 5 s margin


def temp(value: float, minutes_ago: int = 1) -> Reading:
    return Reading(type="temperature", value=value, unit="C", measured_at=NOW - timedelta(minutes=minutes_ago))


class FakePost:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[list[Reading]] = []

    async def __call__(self, readings):
        self.calls.append(list(readings))
        outcome = self.outcomes.pop(0) if self.outcomes else PostResult(saved=len(readings), ignored=0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make(*outcomes, readings=(temp(24.0),)):
    queue = ReadingQueue()
    for reading in readings:
        queue.add(reading)
    post = FakePost(*outcomes)
    return Sender(queue, post), queue, post


async def test_empty_queue_sends_nothing():
    sender, _, post = make(readings=())
    await sender.flush(NOW)
    assert post.calls == []


async def test_success_empties_the_queue_and_waits_for_the_next_window():
    sender, queue, post = make()
    await sender.flush(NOW)
    assert len(post.calls) == 1
    assert len(queue) == 0
    assert sender.next_allowed == NEXT_WINDOW


async def test_no_send_before_next_allowed():
    sender, queue, post = make()
    await sender.flush(NOW)
    queue.add(temp(25.0, minutes_ago=0))
    await sender.flush(NOW + timedelta(minutes=1))
    assert len(post.calls) == 1
    await sender.flush(NEXT_WINDOW)
    assert len(post.calls) == 2


async def test_429_keeps_the_queue_and_honours_retry_after():
    sender, queue, post = make(RateLimited(120))
    await sender.flush(NOW)
    assert len(queue) == 1
    assert sender.next_allowed == NOW + timedelta(seconds=120)


async def test_server_error_backs_off_exponentially_and_resets_on_success():
    sender, queue, post = make(ServerError("x"), ServerError("x"), ServerError("x"))
    now = NOW
    delays = []
    for _ in range(3):
        await sender.flush(now)
        delays.append((sender.next_allowed - now).total_seconds())
        now = sender.next_allowed
    assert delays == [60, 120, 240]
    assert len(queue) == 1
    await sender.flush(now)  # success
    assert len(queue) == 0
    assert sender.backoff_seconds == 60


async def test_backoff_is_capped_at_one_hour():
    sender, _, _ = make(*[ServerError("x")] * 12)
    now = NOW
    for _ in range(12):
        await sender.flush(now)
        now = sender.next_allowed
    assert sender.backoff_seconds == 3600


async def test_auth_error_stops_sending_and_keeps_the_queue():
    sender, queue, post = make(AuthError())
    with pytest.raises(AuthError):
        await sender.flush(NOW)
    assert len(queue) == 1
    # Until the key is replaced nothing more is sent.
    await sender.flush(NOW + timedelta(days=1))
    assert len(post.calls) == 1


async def test_resume_after_a_new_key_sends_again():
    sender, queue, post = make(AuthError())
    with pytest.raises(AuthError):
        await sender.flush(NOW)
    sender.resume()
    await sender.flush(NOW + timedelta(minutes=1))
    assert len(post.calls) == 2
    assert len(queue) == 0


async def test_suspended_account_retries_in_an_hour():
    sender, queue, _ = make(Suspended())
    await sender.flush(NOW)
    assert len(queue) == 1
    assert sender.next_allowed == NOW + timedelta(hours=1)


async def test_bad_request_on_a_single_reading_drops_it():
    sender, queue, _ = make(BadRequest())
    await sender.flush(NOW)
    assert len(queue) == 0


async def test_bad_request_on_a_batch_halves_the_next_batch():
    readings = [temp(20.0 + i, minutes_ago=10 + i) for i in range(4)]
    sender, queue, post = make(BadRequest(), readings=readings)
    await sender.flush(NOW)
    assert len(queue) == 4  # nothing dropped yet
    await sender.flush(NOW)  # a 400 does not use the window: retry straight away
    assert [len(call) for call in post.calls] == [4, 2]
    assert len(queue) == 2


async def test_a_success_restores_the_full_batch_size():
    readings = [temp(20.0 + i, minutes_ago=10 + i) for i in range(4)]
    sender, queue, post = make(BadRequest(), readings=readings)
    await sender.flush(NOW)
    await sender.flush(NOW)  # 2 accepted
    await sender.flush(sender.next_allowed)
    assert [len(call) for call in post.calls] == [4, 2, 2]
    assert len(queue) == 0
