"""Constanten voor Was drogen."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "was_drogen"
PLATFORMS = ["sensor", "binary_sensor"]

CONF_NAME = "name"

# Stationssensoren (live)
CONF_TEMPERATURE = "temperature"
CONF_HUMIDITY = "humidity"
CONF_DEW_POINT = "dew_point"
CONF_VPD = "vpd"
CONF_WIND_SPEED = "wind_speed"
CONF_WIND_GUST = "wind_gust"
CONF_RAIN_RATE = "rain_rate"
CONF_RAIN_HOURLY = "rain_hourly"
CONF_SOLAR = "solar"

STATION_KEYS = (
    CONF_TEMPERATURE,
    CONF_HUMIDITY,
    CONF_DEW_POINT,
    CONF_VPD,
    CONF_WIND_SPEED,
    CONF_WIND_GUST,
    CONF_RAIN_RATE,
    CONF_RAIN_HOURLY,
    CONF_SOLAR,
)

# Weersverwachting
CONF_FORECAST_PRIMARY = "forecast_primary"
CONF_FORECAST_SECONDARY = "forecast_secondary"
FORECAST_KEYS = (CONF_FORECAST_PRIMARY, CONF_FORECAST_SECONDARY)

# Drempels (opties)
CONF_VPD_1 = "vpd_1"
CONF_VPD_2 = "vpd_2"
CONF_VPD_3 = "vpd_3"
CONF_SPREAD_1 = "spread_1"
CONF_SPREAD_2 = "spread_2"
CONF_SPREAD_STOP = "spread_stop"
CONF_WIND_MIN = "wind_min"
CONF_WIND_GOOD_MIN = "wind_good_min"
CONF_WIND_GOOD_MAX = "wind_good_max"
CONF_GUST_STOP = "gust_stop"
CONF_SUN_MIN = "sun_min"
CONF_RAIN_HOUR_STOP = "rain_hour_stop"
CONF_HANG_THRESHOLD = "hang_threshold"
CONF_DAY_START = "day_start"
CONF_DAY_END = "day_end"

DEFAULT_NAME = "Was drogen"

DEFAULTS: dict[str, float] = {
    CONF_VPD_1: 4.0,
    CONF_VPD_2: 6.0,
    CONF_VPD_3: 10.0,
    CONF_SPREAD_1: 5.0,
    CONF_SPREAD_2: 8.0,
    CONF_SPREAD_STOP: 3.0,
    CONF_WIND_MIN: 3.0,
    CONF_WIND_GOOD_MIN: 8.0,
    CONF_WIND_GOOD_MAX: 38.0,
    CONF_GUST_STOP: 60.0,
    CONF_SUN_MIN: 150.0,
    CONF_RAIN_HOUR_STOP: 0.2,
    CONF_HANG_THRESHOLD: 6,
    CONF_DAY_START: 7,
    CONF_DAY_END: 20,
}

THRESHOLD_KEYS = tuple(DEFAULTS)

FORECAST_DAYS = 3
FORECAST_INTERVAL = timedelta(minutes=60)
