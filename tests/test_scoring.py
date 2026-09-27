"""Tests voor de rekenlogica (zonder Home Assistant)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PKG = Path(__file__).parents[1] / "custom_components" / "was_drogen"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const")
s = _load("scoring")
TH = s.Thresholds.from_mapping(const.DEFAULTS)
TZ = timezone(timedelta(hours=2))


# ---- natuurkunde ---------------------------------------------------------

def test_magnus_roundtrip():
    td = s.dew_point(18.7, 76)
    assert td == pytest.approx(14.4, abs=0.15)  # WS2900 meldt 14.4
    assert s.humidity_from_dew_point(18.7, td) == pytest.approx(76, abs=0.01)
    assert s.vapour_pressure_deficit(18.7, 76) == pytest.approx(5.18, abs=0.05)  # WS2900: 5.18


# ---- live-score ----------------------------------------------------------

def test_live_now_matches_template_sensor():
    """Stationswaarden van 27-09 20:50; de template-sensor gaf 1."""
    r = s.calculate(
        s.Conditions(temperature=18.7, humidity=76, dew_point=14.4, vpd=5.18,
                     wind_speed=0, wind_gust=0, rain_rate=0, rain_hour=0, solar=0),
        TH,
    )
    assert r.score == 1
    assert r.factors["vpd"].points == 1
    assert r.factors["spread"].points == 0
    assert r.level == "bad"
    assert r.brake in {"wind", "vpd", "spread"}


def test_good_afternoon():
    """Vanmiddag ~16:00: 22,5 °C, 60 %, wind 12 km/h, zon."""
    r = s.calculate(s.Conditions(temperature=22.5, humidity=60, wind_speed=12, solar=300), TH)
    assert r.factors["vpd"].points == 3  # VPD 10,9 hPa
    assert r.score == 8
    assert r.level == "good"


def test_stops():
    base = dict(temperature=20, humidity=50, wind_speed=15, solar=400)
    assert s.calculate(s.Conditions(**base, rain_rate=0.3), TH).stops == ["rain"]
    assert s.calculate(s.Conditions(**base, rain_hour=0.5), TH).stops == ["rain"]
    assert s.calculate(s.Conditions(**base, rain_hour=0.1), TH).stops == []
    assert "gust" in s.calculate(s.Conditions(**base, wind_gust=70), TH).stops
    r = s.calculate(s.Conditions(temperature=15, humidity=90), TH)
    assert r.stops == ["dew"] and r.score == 0


def test_missing_humidity_is_unknown():
    r = s.calculate(s.Conditions(temperature=20), TH)
    assert r.score is None and r.level == "unknown"


def test_dew_point_only():
    r = s.calculate(s.Conditions(temperature=20, dew_point=8, wind_speed=10), TH)
    assert r.factors["spread"].points == 2
    assert r.score is not None


def test_wind_bands():
    def f(w):
        return s.calculate(s.Conditions(temperature=20, humidity=50, wind_speed=w), TH).factors["wind"].points

    assert (f(0), f(3), f(8), f(38), f(45)) == (0, 1, 2, 2, 1)


def test_sun_proxy_from_uv():
    h = {"temperature": 20, "humidity": 50, "uv_index": 2, "cloud_coverage": 30}
    assert s._conditions_from_hour(h).sunny is True
    h["cloud_coverage"] = 80
    assert s._conditions_from_hour(h).sunny is False
    h["solar_irradiance"] = 300
    assert s._conditions_from_hour(h).sunny is None


# ---- samenvoegen en verwachting -----------------------------------------

def _t(day, hour):
    return datetime(2026, 9, day, hour, tzinfo=TZ)


# Echte uren van morgen (28-09, lokale tijd), zoals opgehaald op 27-09 20:50
KNMI = [  # uur, temp, wind, neerslag, instraling
    (7, 18, 7, 0, 3), (8, 18, 7, 0, 14), (9, 18, 7, 0, 69), (10, 18, 7, 0, 100),
    (11, 18, 10, 0, 211), (12, 19, 7, 0, 211), (13, 19, 7, 0, 260), (14, 19, 10, 0, 152),
    (15, 19, 10, 0.5, 86), (16, 18, 10, 1.3, 17), (17, 18, 10, 0.6, 17), (18, 17, 14, 0.2, 8),
    (19, 17, 10, 0, 3),
]
MET = [  # uur, temp, rv, wind, neerslag, uv, bewolking
    (7, 16.0, 95, 9.4, 0, 0.1, 98.4), (8, 16.5, 95, 8.6, 0, 0.4, 99.2), (9, 17.7, 92, 7.9, 0, 1, 72.7),
    (10, 19.1, 85, 10.1, 0.1, 1.8, 91.4), (11, 19.7, 81, 11.5, 0, 2.5, 96.9), (12, 19.9, 81, 12.6, 0, 3, 100),
    (13, 19.5, 82, 14.8, 0, 2.9, 100), (14, 18.5, 84, 15.8, 0, 2.4, 100), (15, 18.1, 84, 17.6, 0, 1.6, 100),
    (16, 17.8, 85, 18.4, 0, 0.8, 95.3), (17, 18.2, 86, 18.4, 0.9, 0.3, 93.7), (18, 17.5, 92, 19.4, 0.4, 0, 93.7),
    (19, 16.5, 93, 20.5, 0.4, 0, 96.9), (20, 15.8, 94, 18.4, 0.5, 0, 100),
]


def _knmi():
    return [{"time": _t(28, h), "temperature": t, "wind_speed": w, "precipitation": p,
             "solar_irradiance": sol} for h, t, w, p, sol in KNMI]


def _met():
    return [{"time": _t(28, h), "temperature": t, "humidity": rh, "wind_speed": w,
             "precipitation": p, "uv_index": uv, "cloud_coverage": c} for h, t, rh, w, p, uv, c in MET]


def test_merge_primary_wins_and_fills_humidity():
    merged = s.merge_forecasts(_knmi(), _met())
    noon = next(h for h in merged if h["time"] == _t(28, 12))
    assert noon["temperature"] == 19  # KNMI
    assert noon["humidity"] == 81  # Met.no
    assert noon["solar_irradiance"] == 211  # KNMI
    assert noon["bronnen"]["temperature"] == "primair"
    assert noon["bronnen"]["humidity"] == "secundair"
    # 20:00 alleen in Met.no -> telt mee
    assert any(h["time"] == _t(28, 20) for h in merged)


def test_forecast_real_tomorrow():
    merged = s.merge_forecasts(_knmi(), _met())
    now = _t(27, 20).replace(minute=50)
    fc = s.build_forecast(merged, TH, now, 3)
    tomorrow = fc["dagen"][1]
    print("morgen:", tomorrow["scores"])
    assert len(tomorrow["scores"]) == 14
    assert tomorrow["scores"][8:12] == "0000"  # 15-18 uur: regen bij KNMI
    assert tomorrow["beste_venster"] is None  # RV 81-95 %: geen 6+
    assert fc["dagen"][0]["scores"] == "-" * 14  # vandaag is voorbij/onbekend
    assert tomorrow["scores"] == "00003320000000"
    # KNMI zegt 0 mm om 10:00 en wint van Met.no (0,1 mm): 0 is een echte waarde
    assert fc["eerste_regen"]["time"] == _t(28, 15)


def test_best_window_and_next():
    rows = [{"time": _t(29, h), "temperature": 22, "humidity": 45, "wind_speed": 15,
             "precipitation": 0, "solar_irradiance": 400} for h in range(10, 15)]
    rows += [{"time": _t(29, 15), "temperature": 18, "humidity": 90, "precipitation": 1}]
    fc = s.build_forecast(s.merge_forecasts(rows, []), TH, _t(28, 12), 3)
    day = fc["dagen"][1]
    assert day["beste_venster"]["start"] == _t(29, 10)
    assert day["beste_venster"]["einde"] == _t(29, 15)
    assert fc["volgend_venster"]["uren"] == 5
    assert fc["eerste_regen"]["time"] == _t(29, 15)


def test_past_hours_are_skipped():
    rows = [{"time": _t(28, h), "temperature": 22, "humidity": 45, "wind_speed": 15,
             "precipitation": 0, "solar_irradiance": 400} for h in range(7, 21)]
    fc = s.build_forecast(rows, TH, _t(28, 14).replace(minute=30), 1)
    assert fc["dagen"][0]["scores"].startswith("-------")
    assert fc["dagen"][0]["beste_venster"]["start"] == _t(28, 14)
