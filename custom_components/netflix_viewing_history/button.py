from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NetflixConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: NetflixConfigEntry, add: AddEntitiesCallback) -> None:
    add([RefreshButton(entry)])


class RefreshButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "refresh"

    def __init__(self, entry: NetflixConfigEntry) -> None:
        self._coordinator = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="Netflix Viewing History", manufacturer="Netflix"
        )

    async def async_press(self) -> None:
        await self._coordinator.async_request_scrape()
