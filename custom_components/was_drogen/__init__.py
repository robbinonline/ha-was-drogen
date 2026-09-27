"""Was drogen: droogscore voor de was aan de lijn, live en als verwachting."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import WasDrogenConfigEntry, WasDrogenCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: WasDrogenConfigEntry) -> bool:
    coordinator = WasDrogenCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_start_tracking()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WasDrogenConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: WasDrogenConfigEntry) -> None:
    """Opties gewijzigd: alles opnieuw opbouwen met de nieuwe instellingen."""
    await hass.config_entries.async_reload(entry.entry_id)
