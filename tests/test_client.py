"""The client against a fake TankTutor server that mirrors the contract in docs/spec.md."""

from datetime import datetime, timezone

import aiohttp
import pytest
from aiohttp import web

from custom_components.tanktutor.client import (
    AuthError,
    BadRequest,
    RateLimited,
    ServerError,
    Suspended,
    post_readings,
)
from custom_components.tanktutor.queue import Reading

READING = Reading(
    type="temperature",
    value=24.5,
    unit="C",
    measured_at=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
)


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as client_session:
        yield client_session


async def serve(aiohttp_server, handler):
    app = web.Application()
    app.router.add_post("/devices/readings", handler)
    server = await aiohttp_server(app)
    return str(server.make_url(""))


async def test_success_sends_bearer_key_and_batch(allow_sockets, aiohttp_server, session):
    seen = {}

    async def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = await request.json()
        return web.json_response({"saved": 1})

    base = await serve(aiohttp_server, handler)
    result = await post_readings(session, base, "ttk_secret", [READING])
    assert result.saved == 1
    assert result.ignored == 0
    assert seen["auth"] == "Bearer ttk_secret"
    assert seen["body"] == {"readings": [READING.to_payload()]}


async def test_ignored_count_is_reported(allow_sockets, aiohttp_server, session):
    async def handler(request):
        return web.json_response({"saved": 1, "ignored": 2})

    base = await serve(aiohttp_server, handler)
    result = await post_readings(session, base, "k", [READING])
    assert (result.saved, result.ignored) == (1, 2)


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, {"error": "invalid_device_key"}, AuthError),
        (401, {"error": "authentication_required"}, AuthError),
        (403, {"error": "account_suspended"}, Suspended),
        (400, {"error": "invalid_device_readings"}, BadRequest),
        (500, {"error": "boom"}, ServerError),
        (502, {}, ServerError),
    ],
)
async def test_error_statuses_map_to_exceptions(allow_sockets, aiohttp_server, session, status, body, error):
    async def handler(request):
        return web.json_response(body, status=status)

    base = await serve(aiohttp_server, handler)
    with pytest.raises(error):
        await post_readings(session, base, "k", [READING])


async def test_429_carries_retry_after(allow_sockets, aiohttp_server, session):
    async def handler(request):
        return web.json_response({"error": "rate_limited"}, status=429, headers={"Retry-After": "123"})

    base = await serve(aiohttp_server, handler)
    with pytest.raises(RateLimited) as caught:
        await post_readings(session, base, "k", [READING])
    assert caught.value.retry_after == 123


async def test_429_without_header_falls_back_to_a_window(allow_sockets, aiohttp_server, session):
    async def handler(request):
        return web.json_response({"error": "rate_limited"}, status=429)

    base = await serve(aiohttp_server, handler)
    with pytest.raises(RateLimited) as caught:
        await post_readings(session, base, "k", [READING])
    assert caught.value.retry_after == 300


async def test_unreachable_server_is_a_server_error(allow_sockets, session):
    with pytest.raises(ServerError):
        await post_readings(session, "http://127.0.0.1:9", "k", [READING])


async def test_base_url_trailing_slash_is_tolerated(allow_sockets, aiohttp_server, session):
    async def handler(request):
        return web.json_response({"saved": 1})

    base = await serve(aiohttp_server, handler)
    assert (await post_readings(session, base.rstrip("/") + "/", "k", [READING])).saved == 1
