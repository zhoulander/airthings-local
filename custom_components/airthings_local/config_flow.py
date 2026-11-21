
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
    CONF_BACKFILL_LOOKBACK_HOURS,
    DEFAULT_AUTO_BACKFILL,
    DEFAULT_BACKFILL_INTERVAL_HOURS,
    DEFAULT_BACKFILL_LOOKBACK_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class AirthingsLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up the Airthings Local API."""

    VERSION = 1

    async def _validate(self, url: str) -> tuple[str, list[dict]]:
        normalized = url.strip().rstrip("/") + "/"
        parsed = urlparse(normalized)

        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise AirthingsApiError(
                "Enter a valid http:// or https:// address"
            )

        api = AirthingsApi(
            async_get_clientsession(self.hass),
            normalized,
        )
        await api.health()
        devices = await api.devices()

        if not devices:
            raise AirthingsApiError(
                "The API did not report any enabled Airthings devices"
            )

        return normalized.rstrip("/"), devices

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                url, _devices = await self._validate(
                    user_input[CONF_URL]
                )
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Airthings Local",
                    data={CONF_URL: url},
                )

            except AirthingsApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception(
                    "Unexpected error validating Airthings API"
                )
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_URL,
                    default="http://192.168.1.100:8000",
                ): str
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info):
        """Handle the API's optional mDNS announcement."""

        properties = discovery_info.properties
        scheme = properties.get(b"scheme", b"http").decode()
        path = properties.get(b"path", b"/").decode()
        url = (
            f"{scheme}://{discovery_info.host}:"
            f"{discovery_info.port}{path}"
        )

        try:
            normalized, _devices = await self._validate(url)
        except AirthingsApiError:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(normalized)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {
            "name": "Airthings Local"
        }

        return self.async_create_entry(
            title="Airthings Local",
            data={CONF_URL: normalized},
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return AirthingsLocalOptionsFlow(config_entry)


class AirthingsLocalOptionsFlow(config_entries.OptionsFlow):
    """Configure Airthings Local options."""

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

                vol.Optional(
                    CONF_BACKFILL_LOOKBACK_HOURS,
                    default=options.get(
                        CONF_BACKFILL_LOOKBACK_HOURS,
                        DEFAULT_BACKFILL_LOOKBACK_HOURS,
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=336),
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
