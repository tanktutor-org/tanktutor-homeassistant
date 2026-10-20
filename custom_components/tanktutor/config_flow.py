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
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_KEY, CONF_TEMPERATURE_ENTITY, CONF_URL, DEFAULT_URL, DOMAIN

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
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Optional(CONF_TEMPERATURE_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain="sensor", device_class="temperature")
                )
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
