
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPressure,
    UnitOfRatio,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AirthingsCoordinator


@dataclass(frozen=True)
class SensorSpec:
    key: str
    name: str
    unit: str
    device_class: SensorDeviceClass | None
    icon: str


SPECS = {
    "temperature_c": SensorSpec(
        "temperature_c",
        "Temperature",
        UnitOfTemperature.CELSIUS,
        SensorDeviceClass.TEMPERATURE,
        "mdi:thermometer",
    ),
    "humidity_pct": SensorSpec(
        "humidity_pct",
        "Humidity",
        PERCENTAGE,
        SensorDeviceClass.HUMIDITY,
        "mdi:water-percent",
    ),
    "pressure_hpa": SensorSpec(
        "pressure_hpa",
        "Pressure",
        UnitOfPressure.HPA,
        SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        "mdi:gauge",
    ),
    "illuminance_lux": SensorSpec(
        "illuminance_lux",
        "Illuminance",
        "lx",
        SensorDeviceClass.ILLUMINANCE,
        "mdi:brightness-5",
    ),
    "voc_ppb": SensorSpec(
        "voc_ppb",
        "VOC",
        "ppb",
        None,
        "mdi:air-filter",
    ),
    "co2_ppm": SensorSpec(
        "co2_ppm",
        "CO₂",
        UnitOfRatio.PARTS_PER_MILLION,
        SensorDeviceClass.CO2,
        "mdi:molecule-co2",
    ),
    "radon_st": SensorSpec(
        "radon_st",
        "Radon short-term",
        "Bq/m³",
        None,
        "mdi:radioactive",
    ),
    "radon_lt": SensorSpec(
        "radon_lt",
        "Radon long-term",
        "Bq/m³",
        None,
        "mdi:radioactive",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    coordinator: AirthingsCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for device in coordinator.devices:
        model_id = int(device.get("model_id", 0))

        for key, spec in SPECS.items():
            # CO2 and radon are Wave Plus (2930) measurements.
            if key in ("co2_ppm", "radon_st", "radon_lt") and model_id != 2930:
                continue

            entities.append(AirthingsSensor(coordinator, device, spec))

    async_add_entities(entities)


class AirthingsSensor(CoordinatorEntity[AirthingsCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: AirthingsCoordinator,
        device: dict[str, Any],
        spec: SensorSpec,
    ) -> None:
        super().__init__(coordinator)

        self._serial = str(device["serial"])
        self._spec = spec

        self._attr_unique_id = f"{self._serial}_{spec.key}"
        self._attr_name = spec.name
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_device_class = spec.device_class
        self._attr_icon = spec.icon

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=device.get("name") or device.get("model") or f"Airthings {self._serial}",
            manufacturer="Airthings",
            model=device.get("model", "Wave"),
            serial_number=self._serial,
        )

    @property
    def available(self) -> bool:
        record = self.coordinator.data.get(self._serial, {})
        value = record.get(self._spec.key)
        return super().available and isinstance(value, (int, float))

    @property
    def native_value(self):
        record = self.coordinator.data.get(self._serial, {})
        value = record.get(self._spec.key)
        return value if isinstance(value, (int, float)) else None

    @property
    def extra_state_attributes(self):
        record = self.coordinator.data.get(self._serial, {})
        return {
            "measurement_timestamp": record.get("timestamp"),
            "measurement_timestamp_utc": record.get("timestamp_utc"),
            "collected_at_utc": record.get("collected_at_utc"),
            "sample_index": record.get("index"),
            "sample_number": record.get("sample"),
        }
