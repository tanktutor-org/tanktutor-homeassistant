"""HTTP client for POST /devices/readings (contract: docs/spec.md, section 2)."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from .queue import Reading

# Length of the server's fixed rate-limit window; used when a 429 carries no Retry-After.
WINDOW_SECONDS = 300
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class TankTutorError(Exception):
    """Base class for every failure of a send."""


class AuthError(TankTutorError):
    """Missing or revoked device key (401)."""


class Suspended(TankTutorError):
    """The TankTutor account is suspended (403)."""


class BadRequest(TankTutorError):
    """The whole batch was rejected (400); the server does not say which entry."""


class RateLimited(TankTutorError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class ServerError(TankTutorError):
    """5xx, timeout or network failure: keep the queue and retry later."""


@dataclass(frozen=True)
class PostResult:
    saved: int
    ignored: int


async def post_readings(
    session: aiohttp.ClientSession, base_url: str, key: str, readings: list[Reading]
) -> PostResult:
    url = f"{base_url.rstrip('/')}/devices/readings"
    try:
        async with session.post(
            url,
            json={"readings": [r.to_payload() for r in readings]},
            headers={"Authorization": f"Bearer {key}"},
            timeout=REQUEST_TIMEOUT,
        ) as response:
            if response.status == 200:
                data = await response.json()
                return PostResult(saved=int(data.get("saved", 0)), ignored=int(data.get("ignored", 0)))
            if response.status == 401:
                raise AuthError
            if response.status == 403:
                raise Suspended
            if response.status == 400:
                raise BadRequest
            if response.status == 429:
                raise RateLimited(_retry_after(response.headers.get("Retry-After")))
            raise ServerError(f"unexpected status {response.status}")
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise ServerError(str(err)) from err


def _retry_after(header: str | None) -> int:
    try:
        return max(1, int(header)) if header is not None else WINDOW_SECONDS
    except ValueError:
        return WINDOW_SECONDS
