"""When and how the queue is flushed (policy: docs/spec.md, sections 5.2 and 5.3)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from .client import (
    WINDOW_SECONDS,
    AuthError,
    BadRequest,
    PostResult,
    RateLimited,
    ServerError,
    Suspended,
)
from .queue import Reading, ReadingQueue

PostFn = Callable[[list[Reading]], Awaitable[PostResult]]

# After a 200, wait for the next fixed server window, plus a margin for clock skew.
WINDOW_MARGIN = timedelta(seconds=5)
INITIAL_BACKOFF = 60
MAX_BACKOFF = 3600
SUSPENDED_RETRY = timedelta(hours=1)


def _next_window(now: datetime) -> datetime:
    """Start of the next 5-minute window (the server aligns them to the epoch), plus the margin."""
    epoch = now.astimezone(timezone.utc).timestamp()
    boundary = (int(epoch // WINDOW_SECONDS) + 1) * WINDOW_SECONDS
    return datetime.fromtimestamp(boundary, tz=timezone.utc) + WINDOW_MARGIN


class Sender:
    def __init__(self, queue: ReadingQueue, post: PostFn) -> None:
        self._queue = queue
        self._post = post
        self.next_allowed: datetime | None = None
        self.backoff_seconds = INITIAL_BACKOFF
        self._batch_limit: int | None = None
        self._auth_failed = False

    def resume(self) -> None:
        """Called once the user has entered a new key."""
        self._auth_failed = False
        self.next_allowed = None

    async def flush(self, now: datetime) -> None:
        if self._auth_failed:
            return
        if self.next_allowed is not None and now < self.next_allowed:
            return
        batch = self._queue.next_batch(now)
        if self._batch_limit is not None:
            batch = batch[: self._batch_limit]
        if not batch:
            return

        try:
            await self._post(batch)
        except AuthError:
            self._auth_failed = True
            raise
        except Suspended:
            self.next_allowed = now + SUSPENDED_RETRY
        except RateLimited as err:
            self.next_allowed = now + timedelta(seconds=err.retry_after)
        except ServerError:
            self.next_allowed = now + timedelta(seconds=self.backoff_seconds)
            self.backoff_seconds = min(self.backoff_seconds * 2, MAX_BACKOFF)
        except BadRequest:
            # The server does not say which entry is wrong: drop a lone reading, otherwise halve the batch.
            # A 400 does not use the window, so the next flush may retry straight away.
            if len(batch) == 1:
                self._queue.confirm(batch)
                self._batch_limit = None
            else:
                self._batch_limit = max(1, len(batch) // 2)
        else:
            self._queue.confirm(batch)
            self.backoff_seconds = INITIAL_BACKOFF
            self._batch_limit = None
            self.next_allowed = _next_window(now)
