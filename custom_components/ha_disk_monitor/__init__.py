"""Disk Monitor: SMART and ZFS pool state from a disk-agent."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DiskAgentClient
from .const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_USE_SSL, CONF_VERIFY_SSL, DOMAIN
from .coordinator import DiskMonitorCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


def base_url(data: dict) -> str:
    """The agent's origin from the entry data."""
    scheme = "https" if data[CONF_USE_SSL] else "http"
    return f"{scheme}://{data[CONF_HOST]}:{data[CONF_PORT]}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one agent."""
    session = async_get_clientsession(hass, verify_ssl=entry.data[CONF_VERIFY_SSL])
    client = DiskAgentClient(session, base_url(entry.data), entry.data[CONF_API_KEY])
    coordinator = DiskMonitorCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one agent."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
