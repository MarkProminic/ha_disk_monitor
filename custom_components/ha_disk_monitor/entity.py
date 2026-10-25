"""Device and entity bases shared by the platforms."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_DISKS, DATA_HOSTNAME, DATA_POOLS, DOMAIN, MANUFACTURER
from .coordinator import DiskMonitorCoordinator, disk_device_id, host_device_id, pool_device_id


def host_device_info(coordinator: DiskMonitorCoordinator) -> DeviceInfo:
    """The host device every disk and pool hangs under."""
    return DeviceInfo(
        identifiers={(DOMAIN, host_device_id(coordinator.entry.entry_id))},
        name=coordinator.data[DATA_HOSTNAME],
        manufacturer=MANUFACTURER,
        model="disk-agent host",
    )


class DiskEntity(CoordinatorEntity[DiskMonitorCoordinator]):
    """An entity of one disk, keyed by serial."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DiskMonitorCoordinator, serial: str, key: str) -> None:
        super().__init__(coordinator)
        self.serial = serial
        self.key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_disk_{serial}_{key}"

    @property
    def disk(self) -> dict | None:
        """This disk's row of the latest report."""
        return self.coordinator.data[DATA_DISKS].get(self.serial)

    @property
    def available(self) -> bool:
        return super().available and self.disk is not None

    @property
    def device_info(self) -> DeviceInfo:
        disk = self.disk or {}
        return DeviceInfo(
            identifiers={(DOMAIN, disk_device_id(self.coordinator.entry.entry_id, self.serial))},
            name=f"{self.coordinator.data[DATA_HOSTNAME]} {disk.get('model', 'Disk')} {self.serial}",
            manufacturer=MANUFACTURER,
            model=disk.get("model"),
            serial_number=self.serial,
            sw_version=disk.get("firmware"),
            via_device=(DOMAIN, host_device_id(self.coordinator.entry.entry_id)),
        )


class PoolEntity(CoordinatorEntity[DiskMonitorCoordinator]):
    """An entity of one pool, keyed by name."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DiskMonitorCoordinator, name: str, key: str) -> None:
        super().__init__(coordinator)
        self.pool_name = name
        self.key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_pool_{name}_{key}"

    @property
    def pool(self) -> dict | None:
        """This pool's row of the latest report."""
        return self.coordinator.data[DATA_POOLS].get(self.pool_name)

    @property
    def available(self) -> bool:
        return super().available and self.pool is not None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, pool_device_id(self.coordinator.entry.entry_id, self.pool_name))},
            name=f"{self.coordinator.data[DATA_HOSTNAME]} {self.pool_name}",
            manufacturer=MANUFACTURER,
            model="ZFS pool",
            via_device=(DOMAIN, host_device_id(self.coordinator.entry.entry_id)),
        )


class HostEntity(CoordinatorEntity[DiskMonitorCoordinator]):
    """An entity of the host itself."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DiskMonitorCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_host_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return host_device_info(self.coordinator)
