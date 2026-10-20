"""Config flow, options flow and reauth."""

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tanktutor.const import (
    CONF_KEY,
    CONF_TEMPERATURE_ENTITY,
    CONF_URL,
    DOMAIN,
)

KEY = "ttk_" + "a" * 32
URL = "https://tanktutor.test/api"


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_user_flow_creates_an_entry(hass):
    result = await start(hass)
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL, CONF_KEY: KEY})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_URL: URL, CONF_KEY: KEY}
    assert KEY not in result["title"]


async def test_a_malformed_key_is_refused(hass):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_KEY: "not-a-key"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_KEY: "invalid_key"}


async def test_the_same_key_cannot_be_added_twice(hass):
    first = await start(hass)
    await hass.config_entries.flow.async_configure(first["flow_id"], {CONF_URL: URL, CONF_KEY: KEY})
    second = await start(hass)
    result = await hass.config_entries.flow.async_configure(second["flow_id"], {CONF_URL: URL, CONF_KEY: KEY})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_the_unique_id_does_not_contain_the_key(hass):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL, CONF_KEY: KEY})
    entry = result["result"]
    assert KEY not in entry.unique_id


async def test_options_flow_maps_the_temperature_sensor(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: URL, CONF_KEY: KEY})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TEMPERATURE_ENTITY: "sensor.tank_water"}
    )
    assert result["step_id"] == "events"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TEMPERATURE_ENTITY] == "sensor.tank_water"


async def test_reauth_replaces_the_key(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: URL, CONF_KEY: KEY})
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] == FlowResultType.FORM
    new_key = "ttk_" + "b" * 32
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_KEY: new_key})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_KEY] == new_key


# --- options flow: all sensors and events ---------------------------------------------------------

async def options_entry(hass, options=None):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: URL, CONF_KEY: KEY}, options=options or {})
    entry.add_to_hass(hass)
    return entry


async def open_options(hass, entry):
    return await hass.config_entries.options.async_init(entry.entry_id)


async def submit(hass, result, data):
    return await hass.config_entries.options.async_configure(result["flow_id"], data)


async def test_every_sensor_type_can_be_mapped(hass):
    entry = await options_entry(hass)
    result = await open_options(hass, entry)
    result = await submit(hass, result, {
        CONF_TEMPERATURE_ENTITY: "sensor.water",
        "ambient_temperature_entity": "sensor.room",
        "ambient_humidity_entity": "sensor.humidity",
        "ph_entity": "sensor.ph",
        "conductivity_entity": "sensor.ec",
        "salinity_entity": "sensor.sal",
        "salinity_unit": "SG",
        "ammonia_entity": "sensor.nh3",
        "ammonia_basis": "total",
    })
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "events"
    result = await submit(hass, result, {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["salinity_unit"] == "SG"
    assert entry.options["ammonia_basis"] == "total"
    assert entry.options["ph_entity"] == "sensor.ph"
    assert entry.options["events"] == []


async def test_salinity_needs_its_unit(hass):
    entry = await options_entry(hass)
    result = await open_options(hass, entry)
    result = await submit(hass, result, {"salinity_entity": "sensor.sal"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {"salinity_unit": "salinity_unit_required"}


async def test_ammonia_needs_its_basis(hass):
    entry = await options_entry(hass)
    result = await open_options(hass, entry)
    result = await submit(hass, result, {"ammonia_entity": "sensor.nh3"})
    assert result["errors"] == {"ammonia_basis": "ammonia_basis_required"}


async def add_event(hass, result, entity, name, invert=False):
    return await submit(hass, result, {"new_entity": entity, "new_name": name, "new_invert": invert})


async def test_events_can_be_added_one_after_another(hass):
    entry = await options_entry(hass)
    result = await open_options(hass, entry)
    result = await submit(hass, result, {})
    result = await add_event(hass, result, "binary_sensor.leak", "leak")
    assert result["step_id"] == "events"  # the form comes back for another one
    result = await add_event(hass, result, "binary_sensor.float", "level_low", invert=True)
    result = await submit(hass, result, {"keep": ["leak", "level_low"]})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["events"] == [
        {"entity": "binary_sensor.leak", "name": "leak", "invert": False},
        {"entity": "binary_sensor.float", "name": "level_low", "invert": True},
    ]


async def test_an_existing_event_can_be_removed(hass):
    entry = await options_entry(hass, {"events": [
        {"entity": "binary_sensor.leak", "name": "leak", "invert": False},
        {"entity": "binary_sensor.high", "name": "level_high", "invert": False},
    ]})
    result = await open_options(hass, entry)
    result = await submit(hass, result, {})
    result = await submit(hass, result, {"keep": ["leak"]})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert [e["name"] for e in entry.options["events"]] == ["leak"]


async def test_existing_events_are_kept_by_default(hass):
    entry = await options_entry(hass, {"events": [
        {"entity": "binary_sensor.leak", "name": "leak", "invert": False},
    ]})
    result = await open_options(hass, entry)
    result = await submit(hass, result, {})
    keep_field = next(k for k in result["data_schema"].schema if k == "keep")
    assert keep_field.default() == ["leak"]


@pytest.mark.parametrize("name", ["Leak", "has space", "x" * 41, "caf\u00e9"])
async def test_event_names_follow_the_api_rule(hass, name):
    entry = await options_entry(hass)
    result = await open_options(hass, entry)
    result = await submit(hass, result, {})
    result = await add_event(hass, result, "binary_sensor.x", name)
    assert result["errors"] == {"new_name": "invalid_event_name"}


async def test_an_event_name_cannot_be_used_twice(hass):
    entry = await options_entry(hass, {"events": [
        {"entity": "binary_sensor.leak", "name": "leak", "invert": False},
    ]})
    result = await open_options(hass, entry)
    result = await submit(hass, result, {})
    result = await add_event(hass, result, "binary_sensor.other", "leak")
    assert result["errors"] == {"new_name": "event_name_in_use"}


async def test_an_event_sensor_cannot_be_used_twice(hass):
    entry = await options_entry(hass, {"events": [
        {"entity": "binary_sensor.leak", "name": "leak", "invert": False},
    ]})
    result = await open_options(hass, entry)
    result = await submit(hass, result, {})
    result = await add_event(hass, result, "binary_sensor.leak", "level_low")
    assert result["errors"] == {"new_entity": "event_entity_in_use"}


async def test_no_more_than_ten_custom_event_names(hass):
    events = [{"entity": f"binary_sensor.c{i}", "name": f"custom_{i}", "invert": False} for i in range(10)]
    entry = await options_entry(hass, {"events": events})
    result = await open_options(hass, entry)
    result = await submit(hass, result, {})
    result = await add_event(hass, result, "binary_sensor.c10", "custom_10")
    assert result["errors"] == {"new_name": "too_many_custom_events"}


async def test_builtin_names_do_not_count_against_the_custom_limit(hass):
    events = [{"entity": f"binary_sensor.c{i}", "name": f"custom_{i}", "invert": False} for i in range(10)]
    entry = await options_entry(hass, {"events": events})
    result = await open_options(hass, entry)
    result = await submit(hass, result, {})
    result = await add_event(hass, result, "binary_sensor.l", "leak")
    assert not result.get("errors")
