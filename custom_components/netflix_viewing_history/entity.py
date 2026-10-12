from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NetflixCoordinator


class NetflixProfileEntity(CoordinatorEntity[NetflixCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: NetflixCoordinator, profile: str) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_{profile}")},
            name=f"Netflix: {profile}",
            manufacturer="Netflix",
        )

    @property
    def entries(self) -> list[dict]:
        return self.coordinator.data["profiles"].get(self.profile, [])
