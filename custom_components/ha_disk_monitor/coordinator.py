"""Polls one disk-agent, keeps the device registry in step with its report and raises problem notifications."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DiskAgentClient, DiskAgentError
from .const import (
    CONF_NOTIFY_DEVICES,
    CONF_PERSISTENT,
    CONF_SCAN_INTERVAL,
    DATA_COLLECTED_AT,
    DATA_DISKS,
    DATA_HOSTNAME,
    DATA_POOLS,
    DATA_UNREADABLE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def disk_device_id(entry_id: str, serial: str) -> str:
    """The device identifier of one disk."""
    return f"{entry_id}_disk_{serial}"


def pool_device_id(entry_id: str, name: str) -> str:
    """The device identifier of one pool."""
    return f"{entry_id}_pool_{name}"


def host_device_id(entry_id: str) -> str:
    """The device identifier of the host."""
    return f"{entry_id}_host"


def disk_problem(disk: dict) -> bool:
    """Whether a disk row is a problem: not passed or unreadable."""
    return disk.get("passed") is not True or disk.get("error") is not None


def pool_problem(pool: dict) -> bool:
    """Whether a pool row is a problem: not ONLINE, or a member not ONLINE or carrying errors."""
    if pool.get("health") != "ONLINE":
        return True
    for member in pool.get("members", []):
        if member["state"] != "ONLINE" or member["read_errors"] or member["write_errors"] or member["cksum_errors"]:
            return True
    return False


class DiskMonitorCoordinator(DataUpdateCoordinator[dict]):
    """Fetches the agent report on the configured interval.

    data holds hostname, collected_at, disks keyed by serial, pools keyed by
    name and the unreadable device list. Devices for disks and pools that
    left the report are removed from the device registry. A disk or pool
    that becomes a problem raises a persistent notification and a message to
    the configured mobile devices once, until it clears and fails again.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: DiskAgentClient) -> None:
        interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(hass, _LOGGER, name=f"{DOMAIN} {entry.title}", update_interval=timedelta(seconds=interval))
        self.entry = entry
        self.client = client
        self.known_disks: set[str] = set()
        self.known_pools: set[str] = set()
        self.notified: set[str] = set()
        self.store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_problems")

    async def async_load_state(self) -> None:
        """Load the problems already notified."""
        data = await self.store.async_load()
        if data:
            self.notified = set(data.get("problems", []))

    async def _async_update_data(self) -> dict:
        try:
            report = await self.client.report()
        except DiskAgentError as err:
            raise UpdateFailed(str(err)) from err
        disks = {disk["serial"]: disk for disk in report.get("disks", [])}
        pools = {pool["name"]: pool for pool in report.get("pools", [])}
        hostname = report.get("hostname", self.entry.title)
        data = {
            DATA_HOSTNAME: hostname,
            DATA_COLLECTED_AT: report.get("collected_at"),
            DATA_DISKS: disks,
            DATA_POOLS: pools,
            DATA_UNREADABLE: report.get("unreadable", []),
        }
        self._remove_departed(set(disks), set(pools))
        self.known_disks = set(disks)
        self.known_pools = set(pools)
        await self._notify_problems(hostname, disks, pools)
        return data

    def _remove_departed(self, disks: set[str], pools: set[str]) -> None:
        if not self.known_disks and not self.known_pools:
            return
        registry = dr.async_get(self.hass)
        for serial in self.known_disks - disks:
            device = registry.async_get_device(identifiers={(DOMAIN, disk_device_id(self.entry.entry_id, serial))})
            if device:
                registry.async_remove_device(device.id)
        for name in self.known_pools - pools:
            device = registry.async_get_device(identifiers={(DOMAIN, pool_device_id(self.entry.entry_id, name))})
            if device:
                registry.async_remove_device(device.id)

    async def _notify_problems(self, hostname: str, disks: dict, pools: dict) -> None:
        current: dict[str, str] = {}
        for serial, disk in disks.items():
            if disk_problem(disk):
                detail = disk.get("error") or f"SMART passed: {disk.get('passed')}"
                current[f"disk:{serial}"] = f"{hostname} {disk.get('model', 'disk')} {serial}: {detail}"
        for name, pool in pools.items():
            if pool_problem(pool):
                bad = [f"{m['name']} {m['state']} {m['read_errors']}/{m['write_errors']}/{m['cksum_errors']}" for m in pool.get("members", []) if m["state"] != "ONLINE" or m["read_errors"] or m["write_errors"] or m["cksum_errors"]]
                detail = f"health {pool.get('health')}" + (f", members: {', '.join(bad)}" if bad else "") + f", {pool.get('errors', '')}"
                current[f"pool:{name}"] = f"{hostname} pool {name}: {detail}"
        new = set(current) - self.notified
        for key in sorted(new):
            await self._send(current[key], key)
        if set(current) != self.notified:
            self.notified = set(current)
            await self.store.async_save({"problems": sorted(self.notified)})

    async def _send(self, message: str, key: str) -> None:
        title = f"Storage: {message.split(':', 1)[0]}"
        if self.entry.data.get(CONF_PERSISTENT, True):
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {"title": title, "message": message, "notification_id": f"{DOMAIN}_{self.entry.entry_id}_{key}"},
            )
        devices = self.entry.data.get(CONF_NOTIFY_DEVICES, [])
        if not devices:
            return
        try:
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {"title": title, "message": message},
                target={"device_id": devices},
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error("notify.send_message to %s failed: %s", devices, err)
