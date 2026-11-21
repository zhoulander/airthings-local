from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean

from homeassistant.components.recorder.statistics import (
    STATISTIC_UNIT_TO_UNIT_CONVERTER,
    StatisticMeanType,
    async_add_external_statistics,
)
from homeassistant.const import UnitOfTemperature, PERCENTAGE, UnitOfPressure, CONCENTRATION_PARTS_PER_MILLION

from .const import DOMAIN
from .coordinator import AirthingsCoordinator
from .sensor import SPECS

_LOGGER = logging.getLogger(__name__)

# Use only completed UTC hours with at least six 5-minute samples.
MIN_SAMPLES_PER_HOUR = 6


async def async_import_device_history(coordinator: AirthingsCoordinator) -> dict[str, int]:
    """Import hourly means/min/max derived from the API's original 5-minute records."""
    imported: dict[str, int] = {}
    for device in coordinator.devices:
        serial = str(device["serial"])
        offset = 0
        records = []
        while True:
            page = await coordinator.api.history_page(serial, offset)
            batch = page.get("records", [])
            records.extend(batch)
            next_offset = page.get("next_offset")
            if next_offset is None or not batch:
                break
            offset = int(next_offset)

        buckets: dict[str, dict[datetime, list[float]]] = defaultdict(lambda: defaultdict(list))
        now_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for record in records:
            ts = record.get("timestamp")
            if not isinstance(ts, (int, float)):
                continue
            hour = datetime.fromtimestamp(ts, timezone.utc).replace(minute=0, second=0, microsecond=0)
            if hour >= now_hour:
                continue
            for key in SPECS:
                value = record.get(key)
                if isinstance(value, (int, float)):
                    buckets[key][hour].append(float(value))

        count_for_device = 0
        for key, hours in buckets.items():
            spec = SPECS[key]
            stats = []
            for hour, values in sorted(hours.items()):
                if len(values) < MIN_SAMPLES_PER_HOUR:
                    continue
                stats.append({
                    "start": hour,
                    "mean": mean(values),
                    "min": min(values),
                    "max": max(values),
                })
            if not stats:
                continue
            statistic_id = f"{DOMAIN}:device_{serial}_{key}"
            unit_converter = STATISTIC_UNIT_TO_UNIT_CONVERTER.get(spec.unit)
            metadata = {
                "mean_type": StatisticMeanType.ARITHMETIC,
                "has_sum": False,
                "name": f"{device.get('name', serial)} {spec.name}",
                "source": DOMAIN,
                "statistic_id": statistic_id,
                "unit_of_measurement": spec.unit,
                "unit_class": unit_converter.UNIT_CLASS if unit_converter else None,
            }
            async_add_external_statistics(coordinator.hass, metadata, stats)
            count_for_device += len(stats)
        imported[serial] = count_for_device
    return imported
