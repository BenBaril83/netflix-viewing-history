from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_TOKEN, DOMAIN, SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)

type NetflixConfigEntry = ConfigEntry["NetflixCoordinator"]


def count_since(entries: list[dict], days: int, today: date) -> int:
    """Entries whose ISO date is within the last `days` days (undated entries never count)."""
    cutoff = (today - timedelta(days=days)).isoformat()
    return sum(1 for e in entries if e.get("date") and e["date"] >= cutoff)


async def fetch_history(hass: HomeAssistant, host: str, port: int, token: str) -> dict[str, Any]:
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            f"http://{host}:{port}/api/history",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            if r.status == 401:
                raise ConfigEntryAuthFailed("Invalid add-on token")
            r.raise_for_status()
            return await r.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise UpdateFailed(f"Cannot reach the add-on: {err}") from err


class NetflixCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, config_entry=entry,
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
        )

    @property
    def _conn(self) -> tuple[str, int, str]:
        d = self.config_entry.data
        return d[CONF_HOST], d[CONF_PORT], d[CONF_TOKEN]

    async def _async_update_data(self) -> dict[str, Any]:
        return await fetch_history(self.hass, *self._conn)

    async def async_request_scrape(self) -> None:
        host, port, token = self._conn
        session = async_get_clientsession(self.hass)
        async with session.post(
            f"http://{host}:{port}/api/scrape", headers={"Authorization": f"Bearer {token}"}
        ) as r:
            if r.status not in (202, 409):  # 409: already running, which is fine
                r.raise_for_status()
        await self.async_request_refresh()
