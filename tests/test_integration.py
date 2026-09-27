"""Integratietest: wizard, opties, entiteiten en live-updates in een echte HA-kern."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

DOMAIN = "was_drogen"

STATION = {
    "sensor.t": ("22.5", "°C"),
    "sensor.rh": ("60", "%"),
    "sensor.wind": ("3.3", "m/s"),  # = 11,9 km/h -> moet omgerekend worden
    "sensor.gust": ("5", "m/s"),
    "sensor.rain": ("0", "mm/h"),
    "sensor.rain_h": ("0", "mm"),
    "sensor.sun": ("300", "W/m²"),
}


def _set_station(hass: HomeAssistant, **override):
    for eid, (val, unit) in STATION.items():
        hass.states.async_set(eid, override.get(eid, val), {"unit_of_measurement": unit})


@pytest.fixture
def forecast_calls(hass: HomeAssistant):
    """Nep-service weather.get_forecasts met een KNMI- en een Met.no-achtige bron."""
    calls: list[str] = []
    base = dt_util.now().replace(minute=0, second=0, microsecond=0)

    def rows(entity_id):
        out = []
        for i in range(0, 48):
            t = base + timedelta(hours=i)
            if entity_id == "weather.knmi":
                if i >= 24:
                    break
                out.append({"datetime": t.isoformat(), "temperature": 22, "wind_speed": 15,
                            "precipitation": 0, "solar_irradiance": 400})
            else:
                out.append({"datetime": dt_util.as_utc(t).isoformat(), "temperature": 20,
                            "humidity": 45, "wind_speed": 12, "precipitation": 0.5 if i == 30 else 0,
                            "uv_index": 2, "cloud_coverage": 20})
        return out

    async def handler(call: ServiceCall):
        ids = call.data["entity_id"]
        ids = [ids] if isinstance(ids, str) else ids
        calls.extend(ids)
        return {eid: {"forecast": rows(eid)} for eid in ids}

    for eid in ("weather.knmi", "weather.met"):
        hass.states.async_set(eid, "cloudy", {"temperature_unit": "°C", "wind_speed_unit": "km/h",
                                              "precipitation_unit": "mm"})
    hass.services.async_register("weather", "get_forecasts", handler,
                                 supports_response=SupportsResponse.ONLY)
    return calls


def _state(hass: HomeAssistant, entry, domain: str, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, key
    return hass.states.get(entity_id)


async def _create(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

    # Zonder luchtvochtigheid of dauwpunt -> fout
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Was drogen", "temperature": "sensor.t"})
    assert bad["errors"] == {"base": "need_humidity"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Was drogen", "temperature": "sensor.t", "humidity": "sensor.rh",
         "wind_speed": "sensor.wind", "wind_gust": "sensor.gust", "rain_rate": "sensor.rain",
         "rain_hourly": "sensor.rain_h", "solar": "sensor.sun"},
    )
    assert result["step_id"] == "forecast"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"forecast_primary": "weather.knmi", "forecast_secondary": "weather.met"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]


async def test_full_flow(hass: HomeAssistant, forecast_calls):
    _set_station(hass)
    entry = await _create(hass)
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert set(forecast_calls) == {"weather.knmi", "weather.met"}

    score = _state(hass, entry, "sensor", "score")
    # 22,5 °C / 60 % -> VPD 10,9 (3), spreiding 8,1 (2), wind 11,9 km/h (2), zon 300 (1) = 8
    assert score.state == "8"
    assert score.attributes["factoren"]["wind"]["waarde"] == pytest.approx(11.9, abs=0.1)
    assert _state(hass, entry, "binary_sensor", "hang_outside").state == "on"

    fc = _state(hass, entry, "sensor", "forecast")
    assert fc.state not in ("unavailable", "unknown")
    assert len(fc.attributes["dagen"]) == 3
    assert _state(hass, entry, "sensor", "first_rain").state not in ("unknown", "unavailable")

    # Live-update: regen -> score 0, zonder nieuwe verwachtingsaanroep
    n = len(forecast_calls)
    _set_station(hass, **{"sensor.rain": "1.2"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "sensor", "score").state == "0"
    assert _state(hass, entry, "sensor", "score").attributes["stopfactoren"] == ["rain"]
    assert _state(hass, entry, "binary_sensor", "hang_outside").state == "off"
    assert len(forecast_calls) == n

    # Na een uur: verwachting opnieuw opgehaald
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=61))
    await hass.async_block_till_done()
    assert len(forecast_calls) > n


async def test_options(hass: HomeAssistant, forecast_calls):
    _set_station(hass)
    entry = await _create(hass)

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["type"] is FlowResultType.MENU

    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "thresholds"})
    data = {k: v for k, v in entry.options.items()}
    wrong = await hass.config_entries.options.async_configure(form["flow_id"], {**data, "vpd_1": 20})
    assert wrong["errors"] == {"vpd_3": "order_vpd"}
    done = await hass.config_entries.options.async_configure(
        form["flow_id"], {**data, "hang_threshold": 8, "sun_min": 500})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    # Zon 300 < 500 -> score 7, onder de nieuwe grens 8
    assert _state(hass, entry, "sensor", "score").state == "7"
    assert _state(hass, entry, "binary_sensor", "hang_outside").state == "off"

    # Secundaire bron leegmaken via opties
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "forecast"})
    done = await hass.config_entries.options.async_configure(form["flow_id"], {"forecast_primary": "weather.knmi"})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["forecast_secondary"] is None
    assert entry.options["hang_threshold"] == 8  # eerdere wijziging blijft staan
    assert entry.state is config_entries.ConfigEntryState.LOADED
