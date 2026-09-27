"""Binaire sensor: nu buiten hangen, ja of nee."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import WasDrogenConfigEntry, WasDrogenCoordinator
from .entity import WasDrogenEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WasDrogenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([HangOutsideBinarySensor(entry.runtime_data)])


class HangOutsideBinarySensor(WasDrogenEntity, BinarySensorEntity):
    _attr_icon = "mdi:hanger"

    def __init__(self, coordinator: WasDrogenCoordinator) -> None:
        super().__init__(coordinator, "hang_outside")

    @property
    def is_on(self) -> bool | None:
        score = self.coordinator.live.score
        if score is None:
            return None
        return score >= self.coordinator.thresholds.hang_threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "score": self.coordinator.live.score,
            "hang_grens": int(self.coordinator.thresholds.hang_threshold),
            "reden": self.coordinator.live.reason,
        }
