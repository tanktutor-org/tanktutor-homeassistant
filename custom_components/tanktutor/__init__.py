"""TankTutor integration for Home Assistant: sends the sensors you map to TankTutor."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .client import AuthError, post_readings
from .collector import Collector
from .const import CONF_KEY, CONF_URL, DOMAIN, STORAGE_VERSION, TICK_INTERVAL_SECONDS
from .mapping import Mapping, build_mappings, reading_for
from .queue import Reading, ReadingQueue
from .sender import Sender

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    saved = await store.async_load() or {}
    queue = ReadingQueue.from_dict(saved)
    collector = Collector()
    session = async_get_clientsession(hass)
    lock = asyncio.Lock()  # a tick and an urgent flush must never send the same batch twice

    async def post(readings: list[Reading]):
        return await post_readings(session, entry.data[CONF_URL], entry.data[CONF_KEY], readings)

    sender = Sender(queue, post)

    async def tick(now: datetime) -> None:
        async with lock:
            collector.drain(now, queue)
            try:
                await sender.flush(now)
            except AuthError:
                _LOGGER.warning("TankTutor rejected the device key; asking for a new one")
                entry.async_start_reauth(hass)
            await store.async_save(snapshot())

    mappings = build_mappings(dict(entry.options))
    by_entity: dict[str, list[Mapping]] = defaultdict(list)
    for mapping in mappings:
        by_entity[mapping.entity_id].append(mapping)
    # Last state offered per event, kept across restarts: after a restart an unchanged event
    # (e.g. "leak off") is not sent again, so it adds no line to the tank's log.
    last_event: dict[str, float] = {
        str(k): float(v) for k, v in (saved.get("events") or {}).items() if isinstance(v, (int, float))
    }

    def snapshot() -> dict:
        return {**queue.to_dict(), "events": dict(last_event)}

    def offer(mapping: Mapping, state) -> bool:
        """Queue the reading for a state; True when it is an active event that should go out at once."""
        reading = reading_for(mapping, state)
        if reading is None:
            return False
        if mapping.type == "event":
            if last_event.get(mapping.name) == reading.value:
                return False  # the same state again (an attribute changed): nothing new to say
            last_event[mapping.name] = reading.value
            collector.offer(reading)
            return reading.value == 1.0
        collector.offer(reading)
        return False

    @callback
    def on_state_change(event: Event[EventStateChangedData]) -> None:
        state = event.data["new_state"]
        urgent = False
        for mapping in by_entity.get(event.data["entity_id"], []):
            urgent = offer(mapping, state) or urgent
        if urgent:
            # Not eager: events arriving in the same loop iteration share one request.
            hass.async_create_task(tick(dt_util.utcnow()), eager_start=False)

    for mapping in mappings:
        offer(mapping, hass.states.get(mapping.entity_id))
    if by_entity:
        entry.async_on_unload(async_track_state_change_event(hass, list(by_entity), on_state_change))

    entry.async_on_unload(
        async_track_time_interval(hass, tick, timedelta(seconds=TICK_INTERVAL_SECONDS))
    )

    async def save_on_unload() -> None:
        collector.drain(dt_util.utcnow(), queue)
        await store.async_save(snapshot())

    entry.async_on_unload(save_on_unload)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
