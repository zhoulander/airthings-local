
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_AUTO_BACKFILL,
    CONF_BACKFILL_INTERVAL_HOURS,
    CONF_BACKFILL_LOOKBACK_HOURS,
    DEFAULT_AUTO_BACKFILL,
    DEFAULT_BACKFILL_INTERVAL_HOURS,
    DEFAULT_BACKFILL_LOOKBACK_HOURS,
    DOMAIN,
)
from .coordinator import AirthingsCoordinator
from .history_backfill import async_backfill_entity_history
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    coordinator = AirthingsCoordinator(
        hass,
        entry.data[CONF_URL],
    )

    try:
        await coordinator.async_setup()
    except Exception as err:
        raise ConfigEntryNotReady(
            f"Unable to connect to Airthings API: {err}"
        ) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(
        entry.add_update_listener(async_reload_entry)
    )

    await async_setup_services(hass)

    # Set up the recurring backfill if enabled.
    auto_backfill = entry.options.get(
        CONF_AUTO_BACKFILL,
        DEFAULT_AUTO_BACKFILL,
    )

    if auto_backfill:
        interval_hours = entry.options.get(
            CONF_BACKFILL_INTERVAL_HOURS,
            DEFAULT_BACKFILL_INTERVAL_HOURS,
        )

        lookback_hours = entry.options.get(
            CONF_BACKFILL_LOOKBACK_HOURS,
            DEFAULT_BACKFILL_LOOKBACK_HOURS,
        )

        async def run_scheduled_backfill(now) -> None:
            _LOGGER.info(
                "Starting scheduled Airthings %s-hour backfill",
                lookback_hours,
            )

            try:
                result = await async_backfill_entity_history(
                    hass,
                    coordinator,
                    entry.entry_id,
                    lookback_hours,
                )

                _LOGGER.info(
                    "Scheduled Airthings backfill finished: %s",
                    result,
                )

            except Exception:
                _LOGGER.exception(
                    "Scheduled Airthings backfill failed"
                )

        @callback
        def schedule_backfill(now) -> None:
            hass.async_create_task(
                run_scheduled_backfill(now)
            )

        cancel_interval = async_track_time_interval(
            hass,
            schedule_backfill,
            timedelta(hours=interval_hours),
        )

        entry.async_on_unload(cancel_interval)

        _LOGGER.info(
            "Automatic Airthings backfill enabled: every %s hours, "
            "looking back %s hours",
            interval_hours,
            lookback_hours,
        )
    else:
        _LOGGER.info("Automatic Airthings backfill is disabled")

    await hass.config_entries.async_forward_entry_setups(
        entry,
        [Platform.SENSOR],
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    if await hass.config_entries.async_unload_platforms(
        entry,
        [Platform.SENSOR],
    ):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True

    return False


async def async_reload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
