"""Config flow for Disk Monitor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import DeviceSelector, DeviceSelectorConfig, EntityFilterSelectorConfig

from .api import DiskAgentAuthError, DiskAgentClient, DiskAgentError
from .const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_NOTIFY_DEVICES,
    CONF_PERSISTENT,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
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


def form_schema(defaults: dict[str, Any], key_required: bool) -> vol.Schema:
    """The one form of the flow, filled from defaults."""
    key_field = vol.Required(CONF_API_KEY) if key_required else vol.Optional(CONF_API_KEY, default="")
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(CONF_USE_SSL, default=defaults.get(CONF_USE_SSL, DEFAULT_USE_SSL)): bool,
            vol.Required(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)): bool,
            key_field: str,
            vol.Required(CONF_SCAN_INTERVAL, default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL)),
            vol.Required(CONF_PERSISTENT, default=defaults.get(CONF_PERSISTENT, True)): bool,
            vol.Optional(CONF_NOTIFY_DEVICES, default=defaults.get(CONF_NOTIFY_DEVICES, [])): DeviceSelector(
                DeviceSelectorConfig(multiple=True, entity=[EntityFilterSelectorConfig(integration="mobile_app")])
            ),
        }
    )


def base_url(data: dict) -> str:
    """The agent's origin from the form data."""
    scheme = "https" if data[CONF_USE_SSL] else "http"
    return f"{scheme}://{data[CONF_HOST]}:{data[CONF_PORT]}"


class DiskMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Disk Monitor."""

    VERSION = 1

    async def _validate(self, user_input: dict[str, Any], current_key: str | None) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Reach the agent, settle the key, answer the entry data or the errors."""
        errors: dict[str, str] = {}
        credential = user_input.get(CONF_API_KEY) or current_key
        if not credential:
            return None, {"base": "credential_required"}
        session = async_get_clientsession(self.hass, verify_ssl=user_input[CONF_VERIFY_SSL])
        client = DiskAgentClient(session, base_url(user_input), credential)
        try:
            status = await client.status()
            await client.report()
            key = credential
        except DiskAgentAuthError:
            return None, {"base": "invalid_auth"}
        except DiskAgentError as err:
            _LOGGER.error("disk-agent at %s: %s", base_url(user_input), err)
            return None, {"base": "cannot_connect"}
        data = {
            CONF_HOST: user_input[CONF_HOST],
            CONF_PORT: user_input[CONF_PORT],
            CONF_USE_SSL: user_input[CONF_USE_SSL],
            CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
            CONF_API_KEY: key,
            CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
            CONF_PERSISTENT: user_input[CONF_PERSISTENT],
            CONF_NOTIFY_DEVICES: user_input.get(CONF_NOTIFY_DEVICES, []),
            "hostname": status.get("hostname") or user_input[CONF_HOST],
        }
        return data, errors

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Add one agent."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._validate(user_input, None)
            if data:
                hostname = data.pop("hostname")
                await self.async_set_unique_id(hostname)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=hostname, data=data)
        return self.async_show_form(step_id="user", data_schema=form_schema(user_input or {}, True), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Change one agent's address, key, interval or notifications."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._validate(user_input, entry.data.get(CONF_API_KEY))
            if data:
                hostname = data.pop("hostname")
                await self.async_set_unique_id(hostname)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data=data, title=hostname)
        defaults = dict(entry.data)
        defaults.pop(CONF_API_KEY, None)
        if user_input:
            defaults.update(user_input)
        return self.async_show_form(step_id="reconfigure", data_schema=form_schema(defaults, False), errors=errors)
