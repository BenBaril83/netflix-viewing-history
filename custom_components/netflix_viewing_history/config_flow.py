from __future__ import annotations

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
