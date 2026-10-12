from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import CONF_TOKEN, DEFAULT_PORT, DOMAIN
from .coordinator import fetch_history

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_TOKEN): str,
    }
)


class NetflixConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The add-on rejected our token (e.g. it was rotated): ask for the new one."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input:
            try:
                await fetch_history(self.hass, entry.data[CONF_HOST], entry.data[CONF_PORT], user_input[CONF_TOKEN])
            except ConfigEntryAuthFailed:
                errors["base"] = "invalid_auth"
            except UpdateFailed:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}), errors=errors
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            try:
                await fetch_history(self.hass, user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_TOKEN])
            except ConfigEntryAuthFailed:
                errors["base"] = "invalid_auth"
            except UpdateFailed:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="Netflix Viewing History", data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input), errors=errors
        )
