
from __future__ import annotations

import logging
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AirthingsApi, AirthingsApiError
from .const import (
    CONF_AUTO_BACKFILL,
    CONF_BACKFILL_INTERVAL_HOURS,
    DEFAULT_AUTO_BACKFILL,
    DEFAULT_BACKFILL_INTERVAL_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class AirthingsLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, url: str) -> tuple[bool, str | None]:
        url = url.strip().rstrip("/")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False, "invalid_url"

        api = AirthingsApi(
            async_get_clientsession(self.hass),
            url,
        )

        try:
            await api.health()
            await api.devices()
        except AirthingsApiError:
            return False, "cannot_connect"

        return True, None

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            valid, error = await self._validate(url)

            if valid:
                return self.async_create_entry(
                    title=url,
                    data={CONF_URL: url},
                )

            errors["base"] = error or "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL): str,
                }
            ),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info):
        url = str(discovery_info[CONF_URL]).rstrip("/")

        await self.async_set_unique_id(url)
        self._abort_if_unique_id_configured()

        valid, error = await self._validate(url)

        if not valid:
            return self.async_abort(reason=error or "cannot_connect")

        return self.async_create_entry(
            title=url,
            data={CONF_URL: url},
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return AirthingsLocalOptionsFlow(config_entry)


class AirthingsLocalOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=user_input,
            )

        options = self.config_entry.options

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AUTO_BACKFILL,
                    default=options.get(
                        CONF_AUTO_BACKFILL,
                        DEFAULT_AUTO_BACKFILL,
                    ),
                ): selector.BooleanSelector(),

                vol.Optional(
                    CONF_BACKFILL_INTERVAL_HOURS,
                    default=options.get(
                        CONF_BACKFILL_INTERVAL_HOURS,
                        DEFAULT_BACKFILL_INTERVAL_HOURS,
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": 1, "label": "1 hour"},
                            {"value": 2, "label": "2 hours"},
                            {"value": 3, "label": "3 hours"},
                            {"value": 6, "label": "6 hours"},
                            {"value": 12, "label": "12 hours"},
                            {"value": 24, "label": "24 hours"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
