"""Config flow for Disk Monitor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DiskAgentAuthError, DiskAgentClient, DiskAgentError
from .const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SETUP_TOKEN,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def user_schema(defaults: dict[str, Any]) -> vol.Schema:
    """The one form of the flow."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(CONF_USE_SSL, default=defaults.get(CONF_USE_SSL, DEFAULT_USE_SSL)): bool,
            vol.Required(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)): bool,
            vol.Optional(CONF_SETUP_TOKEN, default=defaults.get(CONF_SETUP_TOKEN, "")): str,
            vol.Optional(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): str,
        }
    )


class DiskMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Disk Monitor."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Collect the agent address and either its setup token or an API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            scheme = "https" if user_input[CONF_USE_SSL] else "http"
            url = f"{scheme}://{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            session = async_get_clientsession(self.hass, verify_ssl=user_input[CONF_VERIFY_SSL])
            client = DiskAgentClient(session, url, user_input.get(CONF_API_KEY) or None)
            try:
                status = await client.status()
                hostname = status.get("hostname") or user_input[CONF_HOST]
                if not client.api_key:
                    if not user_input.get(CONF_SETUP_TOKEN):
                        errors["base"] = "credential_required"
                    else:
                        await client.bootstrap(user_input[CONF_SETUP_TOKEN], f"home-assistant-{self.hass.config.location_name}")
                if not errors:
                    await client.report()
                    await self.async_set_unique_id(hostname)
                    self._abort_if_unique_id_configured()
                    data = {
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_USE_SSL: user_input[CONF_USE_SSL],
                        CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                        CONF_API_KEY: client.api_key,
                    }
                    return self.async_create_entry(title=hostname, data=data)
            except DiskAgentAuthError:
                errors["base"] = "invalid_auth"
            except DiskAgentError as err:
                _LOGGER.error("disk-agent at %s: %s", url, err)
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", data_schema=user_schema(user_input or {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The options flow."""
        return DiskMonitorOptionsFlow()


class DiskMonitorOptionsFlow(OptionsFlow):
    """The poll interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Set the poll interval in seconds."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL))}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
