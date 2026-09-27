"""Sensoren: droogscore, verwachting, volgend droogvenster en eerste regen."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import WasDrogenConfigEntry, WasDrogenCoordinator
from .entity import WasDrogenEntity
from .scoring import MAX_SCORE

DAY_NAMES = ["ma", "di", "wo", "do", "vr", "za", "zo"]


def _iso(value: Any) -> Any:
    """Datetimes in attributen als ISO-tekst, handig in templates."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _iso(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_iso(v) for v in value]
    return value


def _day_label(date_iso: str) -> str:
    d = datetime.fromisoformat(date_iso).date()
    today = dt_util.now().date()
    delta = (d - today).days
    if delta == 0:
        return "Vandaag"
    if delta == 1:
        return "Morgen"
    return f"{DAY_NAMES[d.weekday()]} {d.day}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WasDrogenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ScoreSensor(coordinator),
            ForecastSensor(coordinator),
            NextWindowSensor(coordinator),
            FirstRainSensor(coordinator),
        ]
    )


class ScoreSensor(WasDrogenEntity, SensorEntity):
    """Live droogscore 0 tot 8, met de onderbouwing als attributen."""

    _attr_icon = "mdi:tshirt-crew"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = f"/{MAX_SCORE}"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: WasDrogenCoordinator) -> None:
        super().__init__(coordinator, "score")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.live.score

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = self.coordinator.live.as_attributes()
        attrs["hang_grens"] = int(self.coordinator.thresholds.hang_threshold)
        return attrs


class _ForecastEntity(WasDrogenEntity):
    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def forecast(self) -> dict[str, Any]:
        return self.coordinator.data or {}


class ForecastSensor(_ForecastEntity, SensorEntity):
    """Samenvatting van de verwachting; alle uren en dagen als attributen."""

    _attr_icon = "mdi:weather-partly-cloudy"
    # Grote lijsten niet in de database opslaan
    _unrecorded_attributes = frozenset({"uren", "dagen"})

    def __init__(self, coordinator: WasDrogenCoordinator) -> None:
        super().__init__(coordinator, "forecast")

    @property
    def native_value(self) -> str | None:
        days = self.forecast.get("dagen") or []
        for day in days[:2]:
            window = day.get("beste_venster")
            if window:
                return (
                    f"{_day_label(day['datum'])} "
                    f"{window['start']:%H:%M}–{window['einde']:%H:%M}"
                )
        if days:
            return "Geen goed droogvenster"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        f = self.forecast
        days = []
        for day in f.get("dagen") or []:
            days.append({**_iso(day), "label": _day_label(day["datum"])})
        hours = [
            {
                "tijd": h["time"].strftime("%Y-%m-%d %H:%M"),
                "score": h["score"],
                "reden": h["reden"],
                "temp": h["temperatuur"],
                "rv": h["luchtvochtigheid"],
                "wind": h["wind"],
                "regen": h["neerslag"],
            }
            for h in f.get("uren") or []
        ]
        return {
            "dagen": days,
            "uren": hours,
            "dag_start": int(self.coordinator.thresholds.day_start),
            "dag_einde": int(self.coordinator.thresholds.day_end),
            "hang_grens": int(self.coordinator.thresholds.hang_threshold),
            "bijgewerkt": _iso(f.get("bijgewerkt")),
            "fouten": f.get("fouten") or [],
        }


class NextWindowSensor(_ForecastEntity, SensorEntity):
    """Begin van het eerstvolgende goede droogvenster."""

    _attr_icon = "mdi:hanger"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: WasDrogenCoordinator) -> None:
        super().__init__(coordinator, "next_window")

    @property
    def native_value(self) -> datetime | None:
        window = self.forecast.get("volgend_venster")
        return window["start"] if window else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        window = self.forecast.get("volgend_venster")
        if not window:
            return {}
        return {
            "einde": window["einde"].isoformat(),
            "uren": window["uren"],
            "max_score": window["max_score"],
        }


class FirstRainSensor(_ForecastEntity, SensorEntity):
    """Eerste uur met neerslag in de verwachting."""

    _attr_icon = "mdi:weather-rainy"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: WasDrogenCoordinator) -> None:
        super().__init__(coordinator, "first_rain")

    @property
    def native_value(self) -> datetime | None:
        rain = self.forecast.get("eerste_regen")
        return rain["time"] if rain else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rain = self.forecast.get("eerste_regen")
        return {"mm": rain["mm"]} if rain else {}
