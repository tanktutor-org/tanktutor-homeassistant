"""TankTutor integration for Home Assistant: sends the sensors you map to TankTutor."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .client import AuthError, post_readings
from .collector import Collector
from .const import (
    CONF_KEY,
    CONF_TEMPERATURE_ENTITY,
    CONF_URL,
    DOMAIN,
    STORAGE_VERSION,
    TICK_INTERVAL_SECONDS,
)
from .queue import Reading, ReadingQueue
from .sender import Sender

_LOGGER = logging.getLogger(__name__)

# Home Assistant unit -> unit the TankTutor API accepts for water temperature.
TEMPERATURE_UNITS = {"°C": "C", "°F": "F"}


def temperature_reading(state: State | None) -> Reading | None:
    """A reading for a usable state, or None (unknown, unavailable, not a number, unsupported unit)."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    unit = TEMPERATURE_UNITS.get(state.attributes.get("unit_of_measurement"))
    if unit is None:
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return Reading(type="temperature", value=value, unit=unit, measured_at=state.last_updated)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    queue = ReadingQueue.from_dict(await store.async_load() or {})
    collector = Collector()
    session = async_get_clientsession(hass)

    async def post(readings: list[Reading]):
        return await post_readings(session, entry.data[CONF_URL], entry.data[CONF_KEY], readings)

    sender = Sender(queue, post)

    async def tick(now: datetime) -> None:
        collector.drain(now, queue)
        try:
            await sender.flush(now)
        except AuthError:
            _LOGGER.warning("TankTutor rejected the device key; asking for a new one")
            entry.async_start_reauth(hass)
        await store.async_save(queue.to_dict())

    @callback
    def on_state_change(event: Event[EventStateChangedData]) -> None:
        reading = temperature_reading(event.data["new_state"])
        if reading is not None:
            collector.offer(reading)

    entity_id = entry.options.get(CONF_TEMPERATURE_ENTITY)
    if entity_id:
        initial = temperature_reading(hass.states.get(entity_id))
        if initial is not None:
            collector.offer(initial)
        entry.async_on_unload(async_track_state_change_event(hass, [entity_id], on_state_change))

    entry.async_on_unload(
        async_track_time_interval(hass, tick, timedelta(seconds=TICK_INTERVAL_SECONDS))
    )

    async def save_on_unload() -> None:
        collector.drain(dt_util.utcnow(), queue)
        await store.async_save(queue.to_dict())

    entry.async_on_unload(save_on_unload)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
