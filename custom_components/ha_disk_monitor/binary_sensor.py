"""Problem binary sensors of every disk and pool a disk-agent reports."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DiskMonitorCoordinator
from .entity import DiskEntity, PoolEntity
from .sensor import track_new_rows


class DiskProblemSensor(DiskEntity, BinarySensorEntity):
    """On when SMART does not report the disk as passed or smartctl could not read it."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "smart_problem"

    def __init__(self, coordinator: DiskMonitorCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "smart_problem")

    @property
    def is_on(self) -> bool | None:
        disk = self.disk
        if disk is None:
            return None
        return disk.get("passed") is not True or disk.get("error") is not None

    @property
    def extra_state_attributes(self) -> dict | None:
        disk = self.disk
        if disk is None:
            return None
        return {"device": disk.get("device"), "protocol": disk.get("protocol"), "passed": disk.get("passed"), "error": disk.get("error")}


class PoolProblemSensor(PoolEntity, BinarySensorEntity):
    """On when the pool is not ONLINE or any member carries errors or is not ONLINE."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "pool_problem"

    def __init__(self, coordinator: DiskMonitorCoordinator, name: str) -> None:
        super().__init__(coordinator, name, "pool_problem")

    @property
    def is_on(self) -> bool | None:
        pool = self.pool
        if pool is None:
            return None
        if pool.get("health") != "ONLINE":
            return True
        for member in pool.get("members", []):
            if member["state"] != "ONLINE" or member["read_errors"] or member["write_errors"] or member["cksum_errors"]:
                return True
        return False

    @property
    def extra_state_attributes(self) -> dict | None:
        pool = self.pool
        if pool is None:
            return None
        return {"health": pool.get("health"), "errors": pool.get("errors"), "status": pool.get("status")}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the problem sensors of one agent."""
    coordinator: DiskMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    entry.async_on_unload(
        track_new_rows(
            coordinator,
            async_add_entities,
            lambda c, serial: [DiskProblemSensor(c, serial)],
            lambda c, name: [PoolProblemSensor(c, name)],
        )
    )
