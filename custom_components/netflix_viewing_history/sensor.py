from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import RECENT_COUNT
from .coordinator import NetflixConfigEntry, count_since
from .entity import NetflixProfileEntity


@dataclass(frozen=True, kw_only=True)
class Desc(SensorEntityDescription):
    value: Callable[[list[dict]], Any]
    attrs: Callable[[list[dict]], dict[str, Any]] = lambda _: {}


DESCRIPTIONS = (
    Desc(
        key="last_watched",
        translation_key="last_watched",
        value=lambda es: es[0]["title"] if es else None,
        attrs=lambda es: {
            "date": es[0].get("date") or es[0]["date_raw"] if es else None,
            "show": es[0].get("show") if es else None,
            "title_id": es[0].get("title_id") if es else None,
            "recent": [
                {"title": e["title"], "date": e.get("date") or e["date_raw"]} for e in es[:RECENT_COUNT]
            ],
        },
    ),
    Desc(
        key="total_watched",
        translation_key="total_watched",
        state_class=SensorStateClass.TOTAL,
        value=len,
    ),
    Desc(
        key="watched_7_days",
        translation_key="watched_7_days",
        state_class=SensorStateClass.MEASUREMENT,
        # None (unknown) when no entry has an ISO date, i.e. date_format isn't configured.
        value=lambda es: count_since(es, 7, date.today()) if any(e.get("date") for e in es) else None,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: NetflixConfigEntry, add: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new_profiles() -> None:
        new = set(coordinator.data["profiles"]) - known
        known.update(new)
        add(NetflixSensor(coordinator, p, d) for p in sorted(new) for d in DESCRIPTIONS)

    add_new_profiles()
    entry.async_on_unload(coordinator.async_add_listener(add_new_profiles))


class NetflixSensor(NetflixProfileEntity, SensorEntity):
    entity_description: Desc

    def __init__(self, coordinator, profile: str, description: Desc) -> None:
        super().__init__(coordinator, profile)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{profile}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.entries)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs(self.entries)
