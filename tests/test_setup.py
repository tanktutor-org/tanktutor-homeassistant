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


# --- all types -------------------------------------------------------------------------------

ALL_OPTIONS = {
    CONF_TEMPERATURE_ENTITY: SENSOR,
    "ambient_temperature_entity": "sensor.room",
    "ambient_humidity_entity": "sensor.humidity",
    "ph_entity": "sensor.ph",
    "conductivity_entity": "sensor.ec",
    "salinity_entity": "sensor.salinity",
    "salinity_unit": "ppt",
    "ammonia_entity": "sensor.nh3",
    "ammonia_basis": "free",
}


async def setup_with(hass, aioclient_mock, options, status=200):
    aioclient_mock.post(ENDPOINT, json={"saved": 1}, status=status)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: URL, CONF_KEY: KEY}, options=options)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_every_mapped_type_goes_out_in_one_batch(hass, aioclient_mock):
    await setup_with(hass, aioclient_mock, ALL_OPTIONS)
    hass.states.async_set(SENSOR, "24.5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.room", "22", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.humidity", "55", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.ph", "7.4")
    hass.states.async_set("sensor.ec", "1.2", {"unit_of_measurement": "mS/cm"})
    hass.states.async_set("sensor.salinity", "35", {"unit_of_measurement": "ppt"})
    hass.states.async_set("sensor.nh3", "0.01", {"unit_of_measurement": "mg/L"})
    await hass.async_block_till_done()
    await tick(hass)
    (body,) = sent_readings(aioclient_mock)
    by_type = {r["type"]: r for r in body["readings"]}
    assert set(by_type) == {
        "temperature", "ambient_temperature", "ambient_humidity", "ph",
        "conductivity", "salinity", "ammonia",
    }
    assert by_type["conductivity"]["value"] == pytest.approx(1200.0)
    assert by_type["salinity"]["unit"] == "ppt"
    assert by_type["ammonia"]["basis"] == "free"
    dumped = json.dumps(body)
    assert "sensor." not in dumped


async def test_a_state_present_at_startup_is_sent(hass, aioclient_mock):
    hass.states.async_set("sensor.ph", "7.2")
    await setup_with(hass, aioclient_mock, {"ph_entity": "sensor.ph"})
    await tick(hass)
    (body,) = sent_readings(aioclient_mock)
    assert body["readings"][0]["value"] == 7.2


# --- events ---------------------------------------------------------------------------------------

LEAK = {"events": [{"entity": "binary_sensor.leak", "name": "leak", "invert": False}]}


async def test_an_active_event_is_sent_at_once_without_waiting_for_the_tick(hass, aioclient_mock):
    await setup_with(hass, aioclient_mock, LEAK)
    hass.states.async_set("binary_sensor.leak", "on")
    await hass.async_block_till_done()
    (body,) = sent_readings(aioclient_mock)
    assert body["readings"][0]["type"] == "event"
    assert body["readings"][0]["name"] == "leak"
    assert body["readings"][0]["value"] == 1.0


async def test_an_event_going_back_to_normal_waits_for_the_tick(hass, aioclient_mock):
    await setup_with(hass, aioclient_mock, LEAK)
    hass.states.async_set("binary_sensor.leak", "off")
    await hass.async_block_till_done()
    assert sent_readings(aioclient_mock) == []
    await tick(hass)
    assert sent_readings(aioclient_mock)[0]["readings"][0]["value"] == 0.0


async def test_an_inverted_event_is_active_when_the_sensor_is_off(hass, aioclient_mock):
    options = {"events": [{"entity": "binary_sensor.float", "name": "level_low", "invert": True}]}
    await setup_with(hass, aioclient_mock, options)
    hass.states.async_set("binary_sensor.float", "off")
    await hass.async_block_till_done()
    assert sent_readings(aioclient_mock)[0]["readings"][0]["value"] == 1.0


async def test_a_repeated_event_state_is_collapsed(hass, aioclient_mock):
    await setup_with(hass, aioclient_mock, LEAK)
    hass.states.async_set("binary_sensor.leak", "on", {"attempt": 1})
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.leak", "on", {"attempt": 2})
    await hass.async_block_till_done()
    await tick(hass)
    readings = [r for body in sent_readings(aioclient_mock) for r in body["readings"]]
    assert len(readings) == 1


async def test_events_in_the_same_moment_share_one_request(hass, aioclient_mock):
    options = {
        "events": [
            {"entity": "binary_sensor.leak", "name": "leak", "invert": False},
            {"entity": "binary_sensor.high", "name": "level_high", "invert": False},
        ]
    }
    await setup_with(hass, aioclient_mock, options)
    hass.states.async_set("binary_sensor.leak", "on")
    hass.states.async_set("binary_sensor.high", "on")
    await hass.async_block_till_done()
    bodies = sent_readings(aioclient_mock)
    assert len(bodies) == 1
    assert {r["name"] for r in bodies[0]["readings"]} == {"leak", "level_high"}


async def test_an_event_does_not_break_the_five_minute_window(hass, aioclient_mock):
    await setup_with(hass, aioclient_mock, LEAK)
    hass.states.async_set("binary_sensor.leak", "on")
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.leak", "off")
    hass.states.async_set("binary_sensor.leak", "on")
    await hass.async_block_till_done()
    assert len(sent_readings(aioclient_mock)) == 1  # the second one waits for the next window


async def test_an_unchanged_event_is_not_sent_again_after_a_restart(hass, aioclient_mock):
    entry = await setup_with(hass, aioclient_mock, LEAK)
    hass.states.async_set("binary_sensor.leak", "off")
    await hass.async_block_till_done()
    await tick(hass)
    assert len(sent_readings(aioclient_mock)) == 1
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await tick(hass, minutes=10)
    assert len(sent_readings(aioclient_mock)) == 1  # the same "off" is not repeated


async def test_an_event_that_changed_while_home_assistant_was_down_is_sent(hass, aioclient_mock):
    entry = await setup_with(hass, aioclient_mock, LEAK)
    hass.states.async_set("binary_sensor.leak", "off")
    await hass.async_block_till_done()
    await tick(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.leak", "on")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await tick(hass, minutes=10)
    assert sent_readings(aioclient_mock)[-1]["readings"][0]["value"] == 1.0
