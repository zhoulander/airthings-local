
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_BACKFILL_INTERVAL_HOURS,
    DEFAULT_BACKFILL_INTERVAL_HOURS,
    DOMAIN,
)
from .history import async_import_device_history
from .history_backfill import (
    MAX_BACKFILL_HOURS,
    async_backfill_entity_history,
)

_LOGGER = logging.getLogger(__name__)

BACKFILL_SCHEMA = vol.Schema(
    {
        vol.Optional("hours"): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=MAX_BACKFILL_HOURS),
        )
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    async def import_history(call: ServiceCall) -> None:
        results = {}

        for coordinator in hass.data.get(DOMAIN, {}).values():
            results.update(
                await async_import_device_history(coordinator)
            )

        _LOGGER.info(
            "Airthings history import finished: %s",
            results,
        )

    async def backfill_entity_history(call: ServiceCall) -> None:
        coordinators = hass.data.get(DOMAIN, {})

        _LOGGER.warning(
            "Starting Airthings entity-history backfill"
        )

        try:
            for entry_id, coordinator in coordinators.items():
                entry = hass.config_entries.async_get_entry(entry_id)

                interval_hours = (
                    int(
                        entry.options.get(
                            CONF_BACKFILL_INTERVAL_HOURS,
                            DEFAULT_BACKFILL_INTERVAL_HOURS,
                        )
                    )
                    if entry
                    else DEFAULT_BACKFILL_INTERVAL_HOURS
                )

                default_hours = interval_hours + 1

                hours = call.data.get("hours", default_hours)

                result = await async_backfill_entity_history(
                    hass,
                    coordinator,
                    entry_id,
                    hours,
                )

                _LOGGER.warning(
                    "Finished Airthings %s-hour backfill: %s",
                    hours,
                    result,
                )

        except Exception:
            _LOGGER.exception(
                "Airthings entity-history backfill failed"
            )
            raise

        _LOGGER.warning(
            "Airthings entity-history backfill completed"
        )

    if not hass.services.has_service(DOMAIN, "import_history"):
        hass.services.async_register(
            DOMAIN,
            "import_history",
            import_history,
            schema=vol.Schema({}),
        )

    if hass.services.has_service(DOMAIN, "backfill_entity_history"):
        hass.services.async_remove(
            DOMAIN,
            "backfill_entity_history",
        )

    hass.services.async_register(
        DOMAIN,
        "backfill_entity_history",
        backfill_entity_history,
        schema=BACKFILL_SCHEMA,
    )
