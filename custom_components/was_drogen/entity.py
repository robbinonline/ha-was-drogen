"""Gedeelde basis voor alle Was drogen-entiteiten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WasDrogenCoordinator


class WasDrogenEntity(CoordinatorEntity[WasDrogenCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: WasDrogenCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Was drogen",
            model="Droogscore",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        # De live-score werkt ook als de verwachting even niet lukt.
        return True
