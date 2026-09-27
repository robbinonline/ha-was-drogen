"""Coördinator: live-score uit het weerstation en de uurverwachting."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import (
    DistanceConverter,
    PressureConverter,
    SpeedConverter,
    TemperatureConverter,
)

from .const import (
    CONF_DEW_POINT,
    CONF_FORECAST_PRIMARY,
    CONF_FORECAST_SECONDARY,
    CONF_HUMIDITY,
    CONF_RAIN_HOURLY,
    CONF_RAIN_RATE,
    CONF_SOLAR,
    CONF_TEMPERATURE,
    CONF_VPD,
    CONF_WIND_GUST,
    CONF_WIND_SPEED,
    DEFAULTS,
    DOMAIN,
    FORECAST_DAYS,
    FORECAST_INTERVAL,
    STATION_KEYS,
)
from .scoring import (
    Conditions,
    ScoreResult,
    Thresholds,
    build_forecast,
    calculate,
    merge_forecasts,
)

_LOGGER = logging.getLogger(__name__)

type WasDrogenConfigEntry = ConfigEntry[WasDrogenCoordinator]


def merged_config(entry: ConfigEntry) -> dict[str, Any]:
    """Wizard-gegevens + opties; opties winnen, ook als ze leeg zijn gemaakt."""
    return {**DEFAULTS, **entry.data, **entry.options}


# --------------------------------------------------------------------------
# Eenheden
# --------------------------------------------------------------------------

_SPEED_ALIASES = {"km/u": UnitOfSpeed.KILOMETERS_PER_HOUR, "kmh": UnitOfSpeed.KILOMETERS_PER_HOUR}


def _convert(value: float, unit: str | None, converter: Any, target: str) -> float:
    if not unit or unit == target:
        return value
    unit = _SPEED_ALIASES.get(unit, unit)
    try:
        return converter.convert(value, unit, target)
    except HomeAssistantError:
        _LOGGER.debug("Onbekende eenheid %s, waarde ongewijzigd gebruikt", unit)
        return value


def _to_celsius(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    return _convert(value, unit, TemperatureConverter, UnitOfTemperature.CELSIUS)


def _to_kmh(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    return _convert(value, unit, SpeedConverter, UnitOfSpeed.KILOMETERS_PER_HOUR)


def _to_hpa(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    return _convert(value, unit, PressureConverter, UnitOfPressure.HPA)


def _to_mm(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    # in/h en mm/h: alleen de lengte-eenheid telt
    base = (unit or "").split("/")[0] or UnitOfPrecipitationDepth.MILLIMETERS
    return _convert(value, base, DistanceConverter, UnitOfPrecipitationDepth.MILLIMETERS)


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Coördinator
# --------------------------------------------------------------------------


class WasDrogenCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Houdt de live-score bij en haalt elk uur de verwachting op.

    `data` = de verwachting (ververst per uur).
    `live` = de score van nu (opnieuw berekend bij elke stationsmeting).
    """

    config_entry: WasDrogenConfigEntry

    def __init__(self, hass: HomeAssistant, entry: WasDrogenConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=FORECAST_INTERVAL,
        )
        self.config = merged_config(entry)
        self.thresholds = Thresholds.from_mapping(self.config)
        self.live: ScoreResult = ScoreResult(score=None, level="unknown")
        self.live_updated: datetime | None = None

    # ---- live ------------------------------------------------------------

    @property
    def station_entities(self) -> list[str]:
        return [self.config[k] for k in STATION_KEYS if self.config.get(k)]

    def _read(self, key: str) -> tuple[float | None, str | None]:
        entity_id = self.config.get(key)
        if not entity_id:
            return None, None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None, None
        return _num(state.state), state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)

    def compute_live(self) -> None:
        t, t_unit = self._read(CONF_TEMPERATURE)
        rh, _ = self._read(CONF_HUMIDITY)
        td, td_unit = self._read(CONF_DEW_POINT)
        vpd, vpd_unit = self._read(CONF_VPD)
        wind, wind_unit = self._read(CONF_WIND_SPEED)
        gust, gust_unit = self._read(CONF_WIND_GUST)
        rain_rate, rr_unit = self._read(CONF_RAIN_RATE)
        rain_hour, rh_unit = self._read(CONF_RAIN_HOURLY)
        solar, _ = self._read(CONF_SOLAR)

        conditions = Conditions(
            temperature=_to_celsius(t, t_unit),
            humidity=rh,
            dew_point=_to_celsius(td, td_unit),
            vpd=_to_hpa(vpd, vpd_unit),
            wind_speed=_to_kmh(wind, wind_unit),
            wind_gust=_to_kmh(gust, gust_unit),
            rain_rate=_to_mm(rain_rate, rr_unit),
            rain_hour=_to_mm(rain_hour, rh_unit),
            solar=solar,
        )
        self.live = calculate(conditions, self.thresholds)
        self.live_updated = dt_util.utcnow()

    @callback
    def _handle_station_change(self, event: Event[EventStateChangedData]) -> None:
        self.compute_live()
        # Alleen de entiteiten bijwerken, zonder de uurlijkse verversing te verschuiven.
        self.async_update_listeners()

    @callback
    def async_start_tracking(self) -> None:
        self.compute_live()
        self.config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self.station_entities, self._handle_station_change
            )
        )

    # ---- verwachting -----------------------------------------------------

    async def _fetch(self, entity_id: str) -> list[dict[str, Any]]:
        """Uurverwachting van één weerentiteit, genormaliseerd naar vaste eenheden."""
        response = await self.hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": entity_id, "type": "hourly"},
            blocking=True,
            return_response=True,
        )
        rows = (response or {}).get(entity_id, {}).get("forecast") or []

        state = self.hass.states.get(entity_id)
        attrs = state.attributes if state else {}
        t_unit = attrs.get("temperature_unit")
        w_unit = attrs.get("wind_speed_unit")
        p_unit = attrs.get("precipitation_unit")

        result: list[dict[str, Any]] = []
        for row in rows:
            when = dt_util.parse_datetime(str(row.get("datetime", "")))
            if when is None:
                continue
            slot = dt_util.as_local(when).replace(minute=0, second=0, microsecond=0)
            result.append(
                {
                    "time": slot,
                    "temperature": _to_celsius(_num(row.get("temperature")), t_unit),
                    "dew_point": _to_celsius(_num(row.get("dew_point")), t_unit),
                    "humidity": _num(row.get("humidity")),
                    "wind_speed": _to_kmh(_num(row.get("wind_speed")), w_unit),
                    "wind_gust_speed": _to_kmh(_num(row.get("wind_gust_speed")), w_unit),
                    "precipitation": _to_mm(_num(row.get("precipitation")), p_unit),
                    "uv_index": _num(row.get("uv_index")),
                    "cloud_coverage": _num(row.get("cloud_coverage")),
                    "solar_irradiance": _num(row.get("solar_irradiance")),
                }
            )
        return result

    async def _async_update_data(self) -> dict[str, Any]:
        primary_id = self.config.get(CONF_FORECAST_PRIMARY)
        secondary_id = self.config.get(CONF_FORECAST_SECONDARY)

        primary: list[dict[str, Any]] = []
        secondary: list[dict[str, Any]] = []
        errors: list[str] = []

        for entity_id, target in ((primary_id, primary), (secondary_id, secondary)):
            if not entity_id:
                continue
            try:
                target.extend(await self._fetch(entity_id))
            except HomeAssistantError as err:
                errors.append(f"{entity_id}: {err}")
                _LOGGER.warning("Verwachting van %s ophalen mislukt: %s", entity_id, err)

        if not primary and not secondary:
            raise UpdateFailed("Geen weersverwachting beschikbaar: " + "; ".join(errors))

        merged = merge_forecasts(primary, secondary)
        forecast = build_forecast(merged, self.thresholds, dt_util.now(), FORECAST_DAYS)
        forecast["fouten"] = errors
        forecast["bijgewerkt"] = dt_util.utcnow()
        return forecast
