from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin

import aiohttp


class AirthingsApiError(Exception):
    """Raised when the local Airthings API cannot be used."""


class AirthingsApi:
    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/") + "/"

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                response.raise_for_status()
                data = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise AirthingsApiError(f"API request failed: {err}") from err
        if not isinstance(data, dict):
            raise AirthingsApiError("API returned an unexpected response")
        return data

    async def health(self) -> dict[str, Any]:
        return await self._get("health")

    async def devices(self) -> list[dict[str, Any]]:
        data = await self._get("api/devices")
        devices = data.get("devices")
        if not isinstance(devices, list):
            raise AirthingsApiError("The /api/devices response has no devices list")
        return devices

    async def latest(self, serial: str) -> dict[str, Any]:
        data = await self._get(
            f"api/devices/{serial}/history",
            {"limit": 1, "order": "desc"},
        )
        records = data.get("records", [])
        if not records:
            raise AirthingsApiError(f"No history available for device {serial}")
        return records[0]

    async def history_page(
        self,
        serial: str,
        offset: int,
        limit: int = 10000,
        order: str = "asc",
    ) -> dict[str, Any]:
        return await self._get(
            f"api/devices/{serial}/history",
            {"limit": limit, "offset": offset, "order": order},
        )
