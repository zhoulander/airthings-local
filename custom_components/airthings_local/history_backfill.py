
from __future__ import annotations
from functools import partial

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder import statistics as recorder_statistics
from homeassistant.components.recorder.db_schema import StatisticsShortTerm

import asyncio
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import API_TIMEOUT, DOMAIN
from .coordinator import AirthingsCoordinator
from .sensor import SPECS
from .api import AirthingsApiError

_LOGGER = logging.getLogger(__name__)

DEFAULT_BACKFILL_HOURS = 7
MAX_BACKFILL_HOURS = 336

PAGE_SIZE = 100
MAX_RECORDS_PER_DEVICE = 5000
PAUSE_BETWEEN_RECORDS = 0.5


def _valid_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )

STATISTICS_INTERVAL_SECONDS = 300


def _build_short_term_statistics(
    records: list[dict[str, Any]],
    key: str,
    first_bucket: int,
    last_bucket: int,
) -> list[dict[str, Any]]:
    """Build Home Assistant-compatible five-minute measurement statistics."""

    # Keep the latest valid value for each timestamp.
    point_map: dict[float, float] = {}

    for record in records:
        timestamp = record.get("timestamp")
        value = record.get(key)

        if not _valid_number(timestamp) or not _valid_number(value):
            continue

        point_map[float(timestamp)] = float(value)

    points = sorted(point_map.items())

    if not points:
        return []

    result = []
    index = 0
    previous_value = None

    for bucket_start in range(
        first_bucket,
        last_bucket,
        STATISTICS_INTERVAL_SECONDS,
    ):
        bucket_end = bucket_start + STATISTICS_INTERVAL_SECONDS

        # Find the latest reading at or before this interval's start.
        while index < len(points) and points[index][0] <= bucket_start:
            previous_value = points[index][1]
            index += 1

        # Without a known starting value, we cannot calculate a complete
        # five-minute interval.
        if previous_value is None:
            continue

        cursor = float(bucket_start)
        weighted_total = 0.0
        interval_values = [previous_value]

        # Apply each reading until the end of this interval.
        while index < len(points) and points[index][0] < bucket_end:
            timestamp, value = points[index]

            weighted_total += previous_value * (timestamp - cursor)

            cursor = timestamp
            previous_value = value
            interval_values.append(value)

            index += 1

        # The last reading remains in effect until the interval ends.
        weighted_total += previous_value * (bucket_end - cursor)

        result.append(
            {
                "start": datetime.fromtimestamp(
                    bucket_start,
                    timezone.utc,
                ),
                "mean": weighted_total / STATISTICS_INTERVAL_SECONDS,
                "min": min(interval_values),
                "max": max(interval_values),
            }
        )

    return result

def _sample_attributes(
    base: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any]:
    attrs = dict(base)
    timestamp = record.get("timestamp")

    attrs.update(
        {
            "measurement_timestamp": timestamp,
            "measurement_timestamp_utc": (
                record.get("timestamp_utc")
                or datetime.fromtimestamp(
                    float(timestamp), timezone.utc
                ).isoformat()
            ),
            "collected_at_utc": record.get("collected_at_utc"),
            "sample_index": record.get("index"),
            "sample_number": record.get("sample"),
        }
    )
    return attrs


async def _fetch_recent_history(
    coordinator: AirthingsCoordinator,
    serial: str,
    cutoff: float,
) -> list[dict[str, Any]] | None:
    """Fetch recent records in bounded pages, newest first."""

    collected: list[dict[str, Any]] = []
    offset = 0

    while True:
        page = await coordinator.api.history_page(
            serial,
            offset,
            PAGE_SIZE,
            order="desc",
        )

        records = page.get("records", [])

        if not isinstance(records, list):
            raise ValueError(
                f"Unexpected history response for device {serial}"
            )

        if not records:
            break

        valid_records = [
            record
            for record in records
            if isinstance(record, dict)
            and _valid_number(record.get("timestamp"))
        ]

        collected.extend(valid_records)

        if len(collected) > MAX_RECORDS_PER_DEVICE:
            _LOGGER.error(
                "Backfill safety limit of %s records reached for %s; "
                "skipping this device",
                MAX_RECORDS_PER_DEVICE,
                serial,
            )
            return None

        if valid_records:
            oldest_timestamp = min(
                float(record["timestamp"])
                for record in valid_records
            )

            if oldest_timestamp <= cutoff:
                break

        offset += len(records)

        if len(records) < PAGE_SIZE:
            break

        await asyncio.sleep(0)

    collected.sort(
        key=lambda record: float(record["timestamp"])
    )

    older_records = [
        record
        for record in collected
        if float(record["timestamp"]) < cutoff
    ]

    recent_records = [
        record
        for record in collected
        if float(record["timestamp"]) >= cutoff
    ]

    # Retain one reading before the requested window to seed the first
    # five-minute statistics interval.
    seed_record = (
        max(
            older_records,
            key=lambda record: float(record["timestamp"]),
        )
        if older_records
        else None
    )

    if seed_record is not None:
        return [seed_record, *recent_records]

    return recent_records


async def async_backfill_entity_history(
    hass: HomeAssistant,
    coordinator: AirthingsCoordinator,
    entry_id: str,
    hours: int = DEFAULT_BACKFILL_HOURS,
) -> dict[str, int]:
    """Import a requested number of recent hours into Recorder."""

    if (
        isinstance(hours, bool)
        or not isinstance(hours, int)
        or not 1 <= hours <= MAX_BACKFILL_HOURS
    ):
        raise ValueError(
            f"Backfill hours must be between 1 and {MAX_BACKFILL_HOURS}"
        )

    async with coordinator.history_backfill_lock:
        registry = er.async_get(hass)

        entity_map: dict[str, dict[str, str]] = {}
        initial_states: dict[str, Any] = {}
        attribute_templates: dict[str, dict[str, Any]] = {}

        for device in coordinator.devices:
            serial = str(device["serial"])
            entity_map[serial] = {}

            for key in SPECS:
                entity_id = registry.async_get_entity_id(
                    "sensor", DOMAIN, f"{serial}_{key}"
                )

                if entity_id is None:
                    continue

                current = hass.states.get(entity_id)
                if current is None:
                    _LOGGER.warning(
                        "Skipping %s: no current state",
                        entity_id,
                    )
                    continue

                entity_map[serial][key] = entity_id
                initial_states[entity_id] = current
                attribute_templates[entity_id] = dict(current.attributes)

        if not any(entity_map.values()):
            _LOGGER.warning("No enabled Airthings sensor entities found")
            return {"imported": 0, "skipped": 0}

        statistic_ids = {
            entity_id
            for entities in entity_map.values()
            for entity_id in entities.values()
        }

        statistics_metadata = {}
        recorder_instance = None

        try:
            statistics_metadata = await hass.async_add_executor_job(
                partial(
                    recorder_statistics.get_metadata,
                    hass,
                    statistic_ids=statistic_ids,
                )
            )

            recorder_instance = get_instance(hass)

        except Exception:
            _LOGGER.exception(
                "Could not prepare Airthings short-term statistics import"
            )

        store = Store(
            hass,
            1,
            f"{DOMAIN}_{entry_id}_entity_history_{hours}_hours",
        )

        stored = await store.async_load()
        checkpoints: dict[str, float] = (
            {
                str(entity_id): float(timestamp)
                for entity_id, timestamp in stored.items()
                if _valid_number(timestamp)
            }
            if isinstance(stored, dict)
            else {}
        )

        backfill_now = time.time()
        cutoff = backfill_now - timedelta(hours=hours).total_seconds()

        first_bucket = (
            math.ceil(cutoff / STATISTICS_INTERVAL_SECONDS)
            * STATISTICS_INTERVAL_SECONDS
        )

        last_bucket = (
            int(backfill_now // STATISTICS_INTERVAL_SECONDS)
            * STATISTICS_INTERVAL_SECONDS
        )

        _LOGGER.info(
            "Starting Airthings entity-history backfill for the last %s hours",
            hours,
        )

        imported = 0
        skipped = 0
        statistics_imported = 0
        statistics_skipped = 0

        try:
            for device in coordinator.devices:
                serial = str(device["serial"])
                entities = entity_map.get(serial, {})

                if not entities:
                    continue

                records = await _fetch_recent_history(
                    coordinator,
                    serial,
                    cutoff,
                )

                if records is None:
                    continue

                device_imported = 0

                for record in records:
                    sample_ts = float(record["timestamp"])

                    if sample_ts < cutoff:
                        continue

                    if sample_ts > backfill_now + 60:
                        skipped += 1
                        continue

                    for key, entity_id in entities.items():
                        if sample_ts <= checkpoints.get(entity_id, 0):
                            continue

                        value = record.get(key)
                        checkpoints[entity_id] = sample_ts

                        if not _valid_number(value):
                            skipped += 1
                            continue

                        hass.states.async_set(
                            entity_id,
                            str(value),
                            _sample_attributes(
                                attribute_templates[entity_id],
                                record,
                            ),
                            force_update=True,
                            timestamp=sample_ts,
                        )

                        imported += 1
                        device_imported += 1

                    await store.async_save(checkpoints)
                    await asyncio.sleep(PAUSE_BETWEEN_RECORDS)

                # Import five-minute short-term statistics.
                if recorder_instance is not None:
                    for key, entity_id in entities.items():
                        metadata_entry = statistics_metadata.get(entity_id)

                        if metadata_entry is None:
                            statistics_skipped += 1

                            _LOGGER.warning(
                                "No Recorder statistics metadata found for %s",
                                entity_id,
                            )
                            continue

                        statistics = _build_short_term_statistics(
                            records,
                            key,
                            first_bucket,
                            last_bucket,
                        )

                        if not statistics:
                            statistics_skipped += 1
                            continue

                        try:
                            recorder_instance.async_import_statistics(
                                metadata_entry[1],
                                statistics,
                                StatisticsShortTerm,
                            )

                            statistics_imported += len(statistics)

                            _LOGGER.info(
                                "Airthings statistics for %s: "
                                "queued %s five-minute periods",
                                entity_id,
                                len(statistics),
                            )

                        except Exception:
                            statistics_skipped += 1

                            _LOGGER.exception(
                                "Could not import five-minute statistics for %s",
                                entity_id,
                            )
                else:
                    statistics_skipped += len(entities)

                _LOGGER.info(
                    "Airthings backfill for %s: imported %s states",
                    serial,
                    device_imported,
                )

        finally:
            # Fetch fresh readings so the current sensor states do not
            # remain stuck on the oldest backfilled measurement.
            for device in coordinator.devices:
                serial = str(device["serial"])

                try:
                    latest = await asyncio.wait_for(
                        coordinator.api.latest(serial),
                        timeout=API_TIMEOUT,
                    )
                    _LOGGER.debug(
                        "Fetched fresh Airthings readings for %s after backfill",
                        serial,
                    )
                except (AirthingsApiError, asyncio.TimeoutError):
                    _LOGGER.warning(
                        "Could not fetch fresh readings for %s after backfill; "
                        "using cached coordinator data",
                        serial,
                    )
                    latest = coordinator.data.get(serial, {})

                for key, entity_id in entity_map.get(serial, {}).items():
                    value = latest.get(key)
                    original_state = initial_states[entity_id]
                    attrs = dict(attribute_templates[entity_id])

                    if _valid_number(value):
                        attrs = _sample_attributes(attrs, latest)
                        state_value = str(value)
                    else:
                        state_value = original_state.state

                    hass.states.async_set(
                        entity_id,
                        state_value,
                        attrs,
                        force_update=True,
                    )

            await store.async_save(checkpoints)

        _LOGGER.info(
            "Airthings entity-history backfill complete for %s hours: "
            "imported %s states, skipped %s values, "
            "queued %s five-minute statistics, skipped %s sensors",
            hours,
            imported,
            skipped,
            statistics_imported,
            statistics_skipped,
        )

        return {
            "imported": imported,
            "skipped": skipped,
            "statistics_imported": statistics_imported,
            "statistics_skipped": statistics_skipped,
        }