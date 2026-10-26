"""Sensors of every disk and pool a disk-agent reports."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COLLECTED_AT, DATA_DISKS, DATA_POOLS, DATA_UNREADABLE, DOMAIN
from .coordinator import DiskMonitorCoordinator
from .entity import DiskEntity, HostEntity, PoolEntity


@dataclass(frozen=True, kw_only=True)
class RowSensorDescription(SensorEntityDescription):
    """A sensor read from one key of a report row."""

    source: str


DISK_SENSORS: tuple[RowSensorDescription, ...] = (
    RowSensorDescription(key="temperature", source="temperature_c", translation_key="temperature", device_class=SensorDeviceClass.TEMPERATURE, native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT),
    RowSensorDescription(key="power_on_hours", source="power_on_hours", translation_key="power_on_hours", device_class=SensorDeviceClass.DURATION, native_unit_of_measurement=UnitOfTime.HOURS, state_class=SensorStateClass.TOTAL_INCREASING, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="reallocated_sectors", source="reallocated_sectors", translation_key="reallocated_sectors", state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="pending_sectors", source="pending_sectors", translation_key="pending_sectors", state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="offline_uncorrectable", source="offline_uncorrectable", translation_key="offline_uncorrectable", state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="reported_uncorrect", source="reported_uncorrect", translation_key="reported_uncorrect", state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="grown_defects", source="grown_defects", translation_key="grown_defects", state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="uncorrected_read_errors", source="uncorrected_read_errors", translation_key="uncorrected_read_errors", state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="uncorrected_write_errors", source="uncorrected_write_errors", translation_key="uncorrected_write_errors", state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="percentage_used", source="percentage_used", translation_key="percentage_used", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT),
    RowSensorDescription(key="media_errors", source="media_errors", translation_key="media_errors", state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="unsafe_shutdowns", source="unsafe_shutdowns", translation_key="unsafe_shutdowns", state_class=SensorStateClass.TOTAL_INCREASING, entity_category=EntityCategory.DIAGNOSTIC),
)

POOL_SENSORS: tuple[RowSensorDescription, ...] = (
    RowSensorDescription(key="health", source="health", translation_key="health"),
    RowSensorDescription(key="capacity", source="capacity_pct", translation_key="capacity", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT),
    RowSensorDescription(key="fragmentation", source="fragmentation_pct", translation_key="fragmentation", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="size", source="size_bytes", translation_key="size", device_class=SensorDeviceClass.DATA_SIZE, native_unit_of_measurement=UnitOfInformation.BYTES, suggested_unit_of_measurement=UnitOfInformation.TERABYTES, suggested_display_precision=2, entity_category=EntityCategory.DIAGNOSTIC),
    RowSensorDescription(key="allocated", source="alloc_bytes", translation_key="allocated", device_class=SensorDeviceClass.DATA_SIZE, native_unit_of_measurement=UnitOfInformation.BYTES, suggested_unit_of_measurement=UnitOfInformation.TERABYTES, suggested_display_precision=2, state_class=SensorStateClass.MEASUREMENT),
    RowSensorDescription(key="free", source="free_bytes", translation_key="free", device_class=SensorDeviceClass.DATA_SIZE, native_unit_of_measurement=UnitOfInformation.BYTES, suggested_unit_of_measurement=UnitOfInformation.TERABYTES, suggested_display_precision=2, state_class=SensorStateClass.MEASUREMENT),
    RowSensorDescription(key="scan", source="scan", translation_key="scan", entity_category=EntityCategory.DIAGNOSTIC),
)


class DiskSensor(DiskEntity, SensorEntity):
    """One SMART value of one disk."""

    entity_description: RowSensorDescription

    def __init__(self, coordinator: DiskMonitorCoordinator, serial: str, description: RowSensorDescription) -> None:
        super().__init__(coordinator, serial, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        disk = self.disk
        return None if disk is None else disk.get(self.entity_description.source)


class PoolSensor(PoolEntity, SensorEntity):
    """One value of one pool."""

    entity_description: RowSensorDescription

    def __init__(self, coordinator: DiskMonitorCoordinator, name: str, description: RowSensorDescription) -> None:
        super().__init__(coordinator, name, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        pool = self.pool
        return None if pool is None else pool.get(self.entity_description.source)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.key != "health" or self.pool is None:
            return None
        return {
            "errors": self.pool.get("errors"),
            "status": self.pool.get("status"),
            "members": [
                {"name": m["name"], "state": m["state"], "read": m["read_errors"], "write": m["write_errors"], "cksum": m["cksum_errors"], "note": m["note"]}
                for m in self.pool.get("members", [])
            ],
        }


class UnreadableSensor(HostEntity, SensorEntity):
    """How many scanned devices answered no serial, with their paths and errors."""

    _attr_translation_key = "unreadable_devices"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DiskMonitorCoordinator) -> None:
        super().__init__(coordinator, "unreadable_devices")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data[DATA_UNREADABLE])

    @property
    def extra_state_attributes(self) -> dict:
        return {"devices": self.coordinator.data[DATA_UNREADABLE], "collected_at": self.coordinator.data[DATA_COLLECTED_AT]}


def disk_sensors(coordinator: DiskMonitorCoordinator, serial: str) -> list[SensorEntity]:
    """The sensors a disk's row carries a value for."""
    row = coordinator.data[DATA_DISKS][serial]
    return [DiskSensor(coordinator, serial, d) for d in DISK_SENSORS if row.get(d.source) is not None]


def pool_sensors(coordinator: DiskMonitorCoordinator, name: str) -> list[SensorEntity]:
    """The sensors of one pool."""
    return [PoolSensor(coordinator, name, d) for d in POOL_SENSORS]


def track_new_rows(coordinator: DiskMonitorCoordinator, async_add_entities: AddEntitiesCallback, build_disk: Callable, build_pool: Callable) -> Callable[[], None]:
    """Add entities for the current rows, then for every row that appears or returns later."""
    seen_disks: set[str] = set()
    seen_pools: set[str] = set()

    @callback
    def add_new() -> None:
        disks = set(coordinator.data[DATA_DISKS])
        pools = set(coordinator.data[DATA_POOLS])
        new = []
        for serial in disks - seen_disks:
            new.extend(build_disk(coordinator, serial))
        for name in pools - seen_pools:
            new.extend(build_pool(coordinator, name))
        seen_disks.intersection_update(disks)
        seen_disks.update(disks)
        seen_pools.intersection_update(pools)
        seen_pools.update(pools)
        if new:
            async_add_entities(new)

    add_new()
    return coordinator.async_add_listener(add_new)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the sensors of one agent."""
    coordinator: DiskMonitorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UnreadableSensor(coordinator)])
    entry.async_on_unload(track_new_rows(coordinator, async_add_entities, disk_sensors, pool_sensors))
