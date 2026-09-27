"""Wizard en opties voor Was drogen."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    CONF_DAY_END,
    CONF_DAY_START,
    CONF_DEW_POINT,
    CONF_FORECAST_PRIMARY,
    CONF_FORECAST_SECONDARY,
    CONF_GUST_STOP,
    CONF_HANG_THRESHOLD,
    CONF_HUMIDITY,
    CONF_NAME,
    CONF_RAIN_HOUR_STOP,
    CONF_RAIN_HOURLY,
    CONF_RAIN_RATE,
    CONF_SOLAR,
    CONF_SPREAD_1,
    CONF_SPREAD_2,
    CONF_SPREAD_STOP,
    CONF_SUN_MIN,
    CONF_TEMPERATURE,
    CONF_VPD,
    CONF_VPD_1,
    CONF_VPD_2,
    CONF_VPD_3,
    CONF_WIND_GOOD_MAX,
    CONF_WIND_GOOD_MIN,
    CONF_WIND_GUST,
    CONF_WIND_MIN,
    CONF_WIND_SPEED,
    DEFAULT_NAME,
    DEFAULTS,
    DOMAIN,
    FORECAST_KEYS,
    STATION_KEYS,
    THRESHOLD_KEYS,
)
from .coordinator import merged_config

_SENSOR = EntitySelector(EntitySelectorConfig(domain="sensor"))
_WEATHER = EntitySelector(EntitySelectorConfig(domain="weather"))


def _opt(key: str, values: dict[str, Any]) -> vol.Optional:
    """Optioneel veld dat de huidige waarde voorstelt maar leeg gemaakt kan worden."""
    return vol.Optional(key, description={"suggested_value": values.get(key)})


def _station_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_TEMPERATURE, default=values.get(CONF_TEMPERATURE, vol.UNDEFINED)): _SENSOR,
            _opt(CONF_HUMIDITY, values): _SENSOR,
            _opt(CONF_DEW_POINT, values): _SENSOR,
            _opt(CONF_VPD, values): _SENSOR,
            _opt(CONF_WIND_SPEED, values): _SENSOR,
            _opt(CONF_WIND_GUST, values): _SENSOR,
            _opt(CONF_RAIN_RATE, values): _SENSOR,
            _opt(CONF_RAIN_HOURLY, values): _SENSOR,
            _opt(CONF_SOLAR, values): _SENSOR,
        }
    )


def _forecast_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_FORECAST_PRIMARY, default=values.get(CONF_FORECAST_PRIMARY, vol.UNDEFINED)
            ): _WEATHER,
            _opt(CONF_FORECAST_SECONDARY, values): _WEATHER,
        }
    )


def _num(minimum: float, maximum: float, step: float, unit: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


_THRESHOLD_SELECTORS: dict[str, NumberSelector] = {
    CONF_VPD_1: _num(0, 50, 0.5, "hPa"),
    CONF_VPD_2: _num(0, 50, 0.5, "hPa"),
    CONF_VPD_3: _num(0, 50, 0.5, "hPa"),
    CONF_SPREAD_1: _num(0, 30, 0.5, "°C"),
    CONF_SPREAD_2: _num(0, 30, 0.5, "°C"),
    CONF_SPREAD_STOP: _num(0, 15, 0.5, "°C"),
    CONF_WIND_MIN: _num(0, 100, 1, "km/h"),
    CONF_WIND_GOOD_MIN: _num(0, 100, 1, "km/h"),
    CONF_WIND_GOOD_MAX: _num(0, 150, 1, "km/h"),
    CONF_GUST_STOP: _num(0, 200, 1, "km/h"),
    CONF_SUN_MIN: _num(0, 1200, 10, "W/m²"),
    CONF_RAIN_HOUR_STOP: _num(0, 10, 0.1, "mm"),
    CONF_HANG_THRESHOLD: _num(1, 8, 1),
    CONF_DAY_START: _num(0, 23, 1, "uur"),
    CONF_DAY_END: _num(0, 23, 1, "uur"),
}


def _threshold_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(key, default=values.get(key, DEFAULTS[key])): selector
            for key, selector in _THRESHOLD_SELECTORS.items()
        }
    )


def _validate_station(user_input: dict[str, Any]) -> dict[str, str]:
    if not user_input.get(CONF_HUMIDITY) and not user_input.get(CONF_DEW_POINT):
        return {"base": "need_humidity"}
    return {}


def _validate_thresholds(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not user_input[CONF_VPD_1] <= user_input[CONF_VPD_2] <= user_input[CONF_VPD_3]:
        errors[CONF_VPD_3] = "order_vpd"
    if not user_input[CONF_SPREAD_1] <= user_input[CONF_SPREAD_2]:
        errors[CONF_SPREAD_2] = "order_spread"
    if not user_input[CONF_WIND_GOOD_MIN] <= user_input[CONF_WIND_GOOD_MAX]:
        errors[CONF_WIND_GOOD_MAX] = "order_wind"
    if not user_input[CONF_DAY_START] < user_input[CONF_DAY_END]:
        errors[CONF_DAY_END] = "order_day"
    return errors


def _only(keys: tuple[str, ...], user_input: dict[str, Any]) -> dict[str, Any]:
    """Alle sleutels van een stap, ook de leeggemaakte (als None)."""
    return {key: user_input.get(key) or None for key in keys}


class WasDrogenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Wizard: naam en weerstation, daarna de weersverwachting."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_station(user_input)
            if not errors:
                self._data[CONF_NAME] = user_input.pop(CONF_NAME)
                self._data.update(_only(STATION_KEYS, user_input))
                return await self.async_step_forecast()

        schema = vol.Schema(
            {vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector()}
        ).extend(_station_schema(user_input or {}).schema)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_forecast(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(_only(FORECAST_KEYS, user_input))
            name = self._data.pop(CONF_NAME)
            return self.async_create_entry(title=name, data=self._data, options=dict(DEFAULTS))

        return self.async_show_form(step_id="forecast", data_schema=_forecast_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WasDrogenOptionsFlow()


class WasDrogenOptionsFlow(OptionsFlow):
    """Alles achteraf aanpassen vanuit één menu."""

    def _current(self) -> dict[str, Any]:
        return merged_config(self.config_entry)

    def _save(self, changes: dict[str, Any]) -> ConfigFlowResult:
        current = {
            key: value
            for key, value in self._current().items()
            if key in STATION_KEYS + FORECAST_KEYS + THRESHOLD_KEYS
        }
        return self.async_create_entry(data={**current, **changes})

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["station", "forecast", "thresholds"])

    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_station(user_input)
            if not errors:
                return self._save(_only(STATION_KEYS, user_input))
        return self.async_show_form(
            step_id="station",
            data_schema=_station_schema(user_input or self._current()),
            errors=errors,
        )

    async def async_step_forecast(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(_only(FORECAST_KEYS, user_input))
        return self.async_show_form(step_id="forecast", data_schema=_forecast_schema(self._current()))

    async def async_step_thresholds(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_thresholds(user_input)
            if not errors:
                return self._save(user_input)
        return self.async_show_form(
            step_id="thresholds",
            data_schema=_threshold_schema(user_input or self._current()),
            errors=errors,
        )
