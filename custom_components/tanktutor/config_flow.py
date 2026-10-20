"""Config flow: device key, optional sensor mapping, reauth."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    AMMONIA_BASES,
    BUILTIN_EVENTS,
    CONF_EVENTS,
    CONF_KEY,
    CONF_TEMPERATURE_ENTITY,
    CONF_URL,
    DEFAULT_URL,
    DOMAIN,
    EVENT_NAME_RE,
    MAX_CUSTOM_EVENTS,
    SALINITY_UNITS,
)

# Keys are "ttk_" plus 32 base64url characters (apps/api/src/devices/keys.ts).
KEY_RE = re.compile(r"^ttk_[A-Za-z0-9_-]{20,}$")

KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _unique_id(key: str) -> str:
    """Stable id derived from the key: the key itself must never be used as an id."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class TankTutorConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            key = user_input[CONF_KEY].strip()
            if not url.startswith(("https://", "http://")):
                errors[CONF_URL] = "invalid_url"
            elif not KEY_RE.match(key):
                errors[CONF_KEY] = "invalid_key"
            else:
                await self.async_set_unique_id(_unique_id(key))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"TankTutor ({key[:8]}…)", data={CONF_URL: url, CONF_KEY: key}
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default=DEFAULT_URL): str,
                vol.Required(CONF_KEY): KEY_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_KEY].strip()
            if KEY_RE.match(key):
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_KEY: key}
                )
            errors[CONF_KEY] = "invalid_key"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_KEY): KEY_SELECTOR}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> TankTutorOptionsFlow:
        return TankTutorOptionsFlow()


class TankTutorOptionsFlow(OptionsFlowWithReload):
    """Step 1: the sensors. Step 2: the events, repeated until nothing new is added."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._events: list[dict[str, Any]] = []

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get("salinity_entity") and not user_input.get("salinity_unit"):
                errors["salinity_unit"] = "salinity_unit_required"
            if user_input.get("ammonia_entity") and not user_input.get("ammonia_basis"):
                errors["ammonia_basis"] = "ammonia_basis_required"
            if not errors:
                self._options = {k: v for k, v in user_input.items() if v not in (None, "")}
                # A unit or a basis without its sensor means nothing.
                if "salinity_entity" not in self._options:
                    self._options.pop("salinity_unit", None)
                if "ammonia_entity" not in self._options:
                    self._options.pop("ammonia_basis", None)
                self._events = list(self.config_entry.options.get(CONF_EVENTS, []))
                return await self.async_step_events()
        schema = vol.Schema(
            {
                vol.Optional(CONF_TEMPERATURE_ENTITY): _sensor("temperature"),
                vol.Optional("ambient_temperature_entity"): _sensor("temperature"),
                vol.Optional("ambient_humidity_entity"): _sensor("humidity"),
                vol.Optional("ph_entity"): _sensor("ph"),
                vol.Optional("conductivity_entity"): _sensor("conductivity"),
                vol.Optional("salinity_entity"): _sensor(None),
                vol.Optional("salinity_unit"): SelectSelector(SelectSelectorConfig(options=list(SALINITY_UNITS))),
                vol.Optional("ammonia_entity"): _sensor(None),
                vol.Optional("ammonia_basis"): SelectSelector(SelectSelectorConfig(options=list(AMMONIA_BASES))),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or self.config_entry.options),
            errors=errors,
        )

    async def async_step_events(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            kept = [e for e in self._events if e["name"] in user_input.get("keep", [e["name"] for e in self._events])]
            entity = user_input.get("new_entity")
            name = (user_input.get("new_name") or "").strip()
            if not entity and not name:
                return self.async_create_entry(data={**self._options, CONF_EVENTS: kept})
            if not entity:
                errors["new_entity"] = "event_entity_required"
            elif not name:
                errors["new_name"] = "event_name_required"
            elif not EVENT_NAME_RE.match(name):
                errors["new_name"] = "invalid_event_name"
            elif any(e["name"] == name for e in kept):
                errors["new_name"] = "event_name_in_use"
            elif any(e["entity"] == entity for e in kept):
                errors["new_entity"] = "event_entity_in_use"
            elif name not in BUILTIN_EVENTS and sum(e["name"] not in BUILTIN_EVENTS for e in kept) >= MAX_CUSTOM_EVENTS:
                errors["new_name"] = "too_many_custom_events"
            if not errors:
                self._events = kept + [{"entity": entity, "name": name, "invert": bool(user_input.get("new_invert"))}]
                user_input = None
            else:
                self._events = kept  # a removal is not lost because the new event had a typo

        fields: dict[Any, Any] = {}
        names = [e["name"] for e in self._events]
        if names:
            fields[vol.Optional("keep", default=names)] = SelectSelector(
                SelectSelectorConfig(options=names, multiple=True)
            )
        fields[vol.Optional("new_entity")] = EntitySelector(EntitySelectorConfig(domain="binary_sensor"))
        fields[vol.Optional("new_name")] = SelectSelector(
            SelectSelectorConfig(options=list(BUILTIN_EVENTS), custom_value=True)
        )
        fields[vol.Optional("new_invert", default=False)] = bool
        return self.async_show_form(step_id="events", data_schema=vol.Schema(fields), errors=errors)


def _sensor(device_class: str | None) -> EntitySelector:
    config = EntitySelectorConfig(domain="sensor", device_class=device_class) if device_class else EntitySelectorConfig(domain="sensor")
    return EntitySelector(config)
