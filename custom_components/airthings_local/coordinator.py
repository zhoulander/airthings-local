from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AirthingsApi, AirthingsApiError
from .const import API_TIMEOUT, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class AirthingsCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch all configured device readings in one coordinated update."""

    def __init__(self, hass: HomeAssistant, base_url: str) -> None:
        self.api = AirthingsApi(async_get_clientsession(hass), base_url)
        self.devices: list[dict[str, Any]] = []
        self.history_backfill_lock = asyncio.Lock()
        super().__init__(
            hass,
            _LOGGER,
            name="Airthings Local",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def async_setup(self) -> None:
        try:
            self.devices = await self.api.devices()
            await self.async_config_entry_first_refresh()
        except AirthingsApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            async def fetch(device: dict[str, Any]):
                serial = str(device["serial"])
                try:
                    return serial, await asyncio.wait_for(self.api.latest(serial), timeout=API_TIMEOUT)
                except AirthingsApiError as err:
                    _LOGGER.warning("Could not update Airthings device %s: %s", serial, err)
                    return serial, {}

            results = await asyncio.gather(*(fetch(d) for d in self.devices))
            return dict(results)
        except (KeyError, TypeError, asyncio.TimeoutError) as err:
            raise UpdateFailed(f"Unable to update Airthings data: {err}") from err
