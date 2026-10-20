"""The running integration: sensor changes in Home Assistant end up in TankTutor requests."""

import json
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState, SOURCE_REAUTH
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.tanktutor.const import (
    CONF_KEY,
    CONF_TEMPERATURE_ENTITY,
    CONF_URL,
    DOMAIN,
)

KEY = "ttk_" + "a" * 32
URL = "https://tanktutor.test/api"
ENDPOINT = f"{URL}/devices/readings"
SENSOR = "sensor.tank_water"


async def setup_entry(hass, aioclient_mock, status=200, **kwargs):
    aioclient_mock.post(ENDPOINT, json={"saved": 1}, status=status, **kwargs)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: URL, CONF_KEY: KEY},
        options={CONF_TEMPERATURE_ENTITY: SENSOR},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def tick(hass, minutes=1):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=minutes))
    await hass.async_block_till_done()


def sent_readings(aioclient_mock):
    return [json.loads(call[2]) if isinstance(call[2], str) else call[2] for call in aioclient_mock.mock_calls]


async def test_a_temperature_change_is_sent_in_celsius(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    hass.states.async_set(SENSOR, "24.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await tick(hass)
    (body,) = sent_readings(aioclient_mock)
    (reading,) = body["readings"]
    assert reading["type"] == "temperature"
    assert reading["value"] == 24.5
    assert reading["unit"] == "C"
    assert "measuredAt" in reading
    # nothing but the reading leaves Home Assistant: no entity id, no friendly name
    assert SENSOR not in json.dumps(body)


async def test_fahrenheit_is_sent_with_its_unit(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    hass.states.async_set(SENSOR, "76.1", {"unit_of_measurement": "°F"})
    await hass.async_block_till_done()
    await tick(hass)
    (body,) = sent_readings(aioclient_mock)
    assert body["readings"][0]["unit"] == "F"


@pytest.mark.parametrize("state", ["unavailable", "unknown", "abc"])
async def test_unusable_states_are_never_sent(hass, aioclient_mock, state):
    await setup_entry(hass, aioclient_mock)
    hass.states.async_set(SENSOR, state, {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await tick(hass)
    assert sent_readings(aioclient_mock) == []


async def test_an_unsupported_unit_is_never_sent(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    hass.states.async_set(SENSOR, "297", {"unit_of_measurement": "K"})
    await hass.async_block_till_done()
    await tick(hass)
    assert sent_readings(aioclient_mock) == []


async def test_the_key_is_sent_as_a_bearer_token(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock)
    hass.states.async_set(SENSOR, "24.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await tick(hass)
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["Authorization"] == f"Bearer {KEY}"


async def test_a_revoked_key_starts_reauth(hass, aioclient_mock):
    entry = await setup_entry(hass, aioclient_mock, status=401)
    hass.states.async_set(SENSOR, "24.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await tick(hass)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
    assert entry.state is ConfigEntryState.LOADED


async def test_unsent_readings_are_stored_for_the_next_start(hass, aioclient_mock, hass_storage):
    await setup_entry(hass, aioclient_mock, status=429, headers={"Retry-After": "300"})
    hass.states.async_set(SENSOR, "24.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await tick(hass)
    stored = next(v for k, v in hass_storage.items() if k.startswith("tanktutor"))
    assert stored["data"]["readings"][0]["value"] == 24.5


async def test_the_unload_leaves_no_listener_behind(hass, aioclient_mock):
    entry = await setup_entry(hass, aioclient_mock)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set(SENSOR, "24.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await tick(hass)
    assert sent_readings(aioclient_mock) == []


async def test_a_reading_not_yet_queued_survives_a_restart(hass, aioclient_mock, hass_storage):
    entry = await setup_entry(hass, aioclient_mock)
    hass.states.async_set(SENSOR, "24.5", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    stored = next(v for k, v in hass_storage.items() if k.startswith("tanktutor"))
    assert stored["data"]["readings"][0]["value"] == 24.5
