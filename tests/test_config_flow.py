"""Config flow, options flow and reauth."""

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
