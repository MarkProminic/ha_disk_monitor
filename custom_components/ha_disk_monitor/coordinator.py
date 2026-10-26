"""Holds one disk-agent's report, keeps the device registry in step with it and raises problem notifications."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import DiskAgentClient, DiskAgentError
from .const import (
    CONF_NOTIFY_DEVICES,
    CONF_PERSISTENT,
    DATA_COLLECTED_AT,
    DATA_DISKS,
    DATA_HOSTNAME,
    DATA_POOLS,
    DATA_UNREADABLE,
    DOMAIN,
    RECONNECT_FIRST_SECONDS,
    RECONNECT_MAX_SECONDS,
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
    """Receives the agent's reports over its event stream.

    data holds hostname, collected_at, disks keyed by serial, pools keyed by
    name and the unreadable device list. The first report is fetched once at
    setup; every later one arrives on the stream the agent pushes to, which
    is reopened with exponential backoff when it drops. Devices for disks and
    pools that left a report whose collection succeeded are removed from the
    device registry; a report carrying disk_error or pool_error changes
    nothing. A disk or pool that becomes a problem raises a persistent
    notification and a message to the configured mobile devices once, until
    it clears and fails again.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: DiskAgentClient) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN} {entry.title}", update_interval=None)
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

    async def async_seed(self) -> None:
        """Fetch the current report once so the entities exist before the stream opens."""
        report = await self.client.report()
        self.async_set_updated_data(await self._handle_report(report))

    async def async_run(self) -> None:
        """Consume the event stream until cancelled, reopening it with backoff when it drops."""
        delay = RECONNECT_FIRST_SECONDS
        while True:
            try:
                async for report in self.client.events():
                    delay = RECONNECT_FIRST_SECONDS
                    self.async_set_updated_data(await self._handle_report(report))
                raise DiskAgentError("stream closed")
            except DiskAgentError as err:
                _LOGGER.warning("%s: event stream lost (%s), reconnecting in %ss", self.name, err, delay)
                self.async_set_update_error(err)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_SECONDS)

    async def _handle_report(self, report: dict) -> dict:
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
        if report.get("disk_error") is None:
            self._remove_departed(self.known_disks - set(disks), disk_device_id)
            self.known_disks = set(disks)
        if report.get("pool_error") is None:
            self._remove_departed(self.known_pools - set(pools), pool_device_id)
            self.known_pools = set(pools)
        await self._notify_problems(hostname, disks, pools)
        return data

    def _remove_departed(self, departed: set[str], device_id) -> None:
        registry = dr.async_get(self.hass)
        for key in departed:
            device = registry.async_get_device(identifiers={(DOMAIN, device_id(self.entry.entry_id, key))})
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
