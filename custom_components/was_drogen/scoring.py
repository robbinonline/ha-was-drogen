"""Rekenlogica voor de droogscore.

Dit bestand gebruikt bewust geen Home Assistant-imports, zodat de logica
los te testen is. Alle waarden komen hier al in vaste eenheden binnen:
°C, %, hPa, km/h, mm en W/m².
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from datetime import date, datetime, timedelta
from typing import Any

MAX_POINTS = {"vpd": 3, "spread": 2, "wind": 2, "sun": 1}
MAX_SCORE = sum(MAX_POINTS.values())

FACTOR_UNITS = {"vpd": "hPa", "spread": "°C", "wind": "km/h", "sun": "W/m²"}

BRAKE_TEXT = {
    "vpd": "de lucht zit vol vocht (laag dampdrukdeficit)",
    "spread": "het is dicht bij het dauwpunt",
    "wind": "er staat te weinig wind",
    "sun": "er is geen zon",
}

STOP_TEXT = {
    "rain": "het regent (of heeft net geregend)",
    "dew": "de temperatuur zit bijna op het dauwpunt, vocht slaat neer",
    "gust": "te harde windstoten",
}

LEVEL_TEXT = {
    "good": "Hang de was buiten",
    "moderate": "Kan, maar droogt traag",
    "bad": "Niet buiten hangen",
    "unknown": "Onbekend",
}


# --------------------------------------------------------------------------
# Natuurkunde (Magnus-formule, Sonntag 1990)
# --------------------------------------------------------------------------

_A = 17.62
_B = 243.12


def saturation_vapour_pressure(temp_c: float) -> float:
    """Verzadigingsdampdruk in hPa."""
    return 6.112 * math.exp(_A * temp_c / (_B + temp_c))


def dew_point(temp_c: float, humidity: float) -> float:
    """Dauwpunt in °C uit temperatuur en relatieve luchtvochtigheid."""
    rh = min(max(humidity, 1.0), 100.0)
    g = math.log(rh / 100.0) + _A * temp_c / (_B + temp_c)
    return _B * g / (_A - g)


def humidity_from_dew_point(temp_c: float, dew_c: float) -> float:
    """Relatieve luchtvochtigheid in % uit temperatuur en dauwpunt."""
    rh = 100.0 * saturation_vapour_pressure(dew_c) / saturation_vapour_pressure(temp_c)
    return min(max(rh, 0.0), 100.0)


def vapour_pressure_deficit(temp_c: float, humidity: float) -> float:
    """Dampdrukdeficit in hPa."""
    return saturation_vapour_pressure(temp_c) * (1.0 - min(max(humidity, 0.0), 100.0) / 100.0)


# --------------------------------------------------------------------------
# Drempels en invoer
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    """Alle instelbare grenzen. Veldnamen = sleutels in de opties."""

    vpd_1: float
    vpd_2: float
    vpd_3: float
    spread_1: float
    spread_2: float
    spread_stop: float
    wind_min: float
    wind_good_min: float
    wind_good_max: float
    gust_stop: float
    sun_min: float
    rain_hour_stop: float
    hang_threshold: float
    day_start: float
    day_end: float

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> Thresholds:
        return cls(**{f.name: float(values[f.name]) for f in fields(cls)})


@dataclass
class Conditions:
    """Weersomstandigheden voor één moment (live of een verwachtingsuur)."""

    temperature: float | None
    humidity: float | None = None
    dew_point: float | None = None
    vpd: float | None = None
    wind_speed: float | None = None
    wind_gust: float | None = None
    rain_rate: float | None = None
    rain_hour: float | None = None
    solar: float | None = None
    sunny: bool | None = None  # alleen als er geen instraling bekend is


@dataclass
class Factor:
    key: str
    value: float | None
    points: int
    max_points: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "waarde": None if self.value is None else round(self.value, 1),
            "eenheid": FACTOR_UNITS[self.key],
            "punten": self.points,
            "max": self.max_points,
        }


@dataclass
class ScoreResult:
    score: int | None
    level: str
    factors: dict[str, Factor] = field(default_factory=dict)
    stops: list[str] = field(default_factory=list)
    brake: str | None = None

    @property
    def reason(self) -> str | None:
        """Korte reden in woorden: stopfactor of grootste rem."""
        if self.stops:
            return ", ".join(STOP_TEXT[s] for s in self.stops)
        if self.brake:
            return BRAKE_TEXT[self.brake]
        return None

    def as_attributes(self) -> dict[str, Any]:
        return {
            "advies": LEVEL_TEXT[self.level],
            "niveau": self.level,
            "reden": self.reason,
            "stopfactoren": list(self.stops),
            "grootste_rem": self.brake,
            "factoren": {k: f.as_dict() for k, f in self.factors.items()},
            "max_score": MAX_SCORE,
        }


# --------------------------------------------------------------------------
# Score
# --------------------------------------------------------------------------


def _level(score: int | None, th: Thresholds) -> str:
    if score is None:
        return "unknown"
    if score >= th.hang_threshold:
        return "good"
    if score >= th.hang_threshold - 2:
        return "moderate"
    return "bad"


def calculate(c: Conditions, th: Thresholds) -> ScoreResult:
    """Bereken de droogscore (0 tot 8) voor één moment."""
    t = c.temperature
    if t is None:
        return ScoreResult(score=None, level="unknown")

    rh = c.humidity
    td = c.dew_point
    if rh is None and td is not None:
        rh = humidity_from_dew_point(t, td)
    if td is None and rh is not None:
        td = dew_point(t, rh)
    if rh is None or td is None:
        return ScoreResult(score=None, level="unknown")

    vpd = c.vpd if c.vpd is not None else vapour_pressure_deficit(t, rh)
    spread = t - td
    wind = c.wind_speed

    # Punten per factor
    p_vpd = 3 if vpd >= th.vpd_3 else 2 if vpd >= th.vpd_2 else 1 if vpd >= th.vpd_1 else 0
    p_spread = 2 if spread >= th.spread_2 else 1 if spread >= th.spread_1 else 0
    if wind is None:
        p_wind = 0
    elif th.wind_good_min <= wind <= th.wind_good_max:
        p_wind = 2
    elif wind >= th.wind_min:
        p_wind = 1
    else:
        p_wind = 0
    if c.solar is not None:
        p_sun = 1 if c.solar >= th.sun_min else 0
    else:
        p_sun = 1 if c.sunny else 0

    factors = {
        "vpd": Factor("vpd", vpd, p_vpd, MAX_POINTS["vpd"]),
        "spread": Factor("spread", spread, p_spread, MAX_POINTS["spread"]),
        "wind": Factor("wind", wind, p_wind, MAX_POINTS["wind"]),
        "sun": Factor("sun", c.solar, p_sun, MAX_POINTS["sun"]),
    }

    # Stopfactoren
    stops: list[str] = []
    if (c.rain_rate or 0) > 0 or (c.rain_hour or 0) > th.rain_hour_stop:
        stops.append("rain")
    if spread < th.spread_stop:
        stops.append("dew")
    if c.wind_gust is not None and c.wind_gust > th.gust_stop:
        stops.append("gust")

    score = 0 if stops else p_vpd + p_spread + p_wind + p_sun

    brake = None
    if not stops:
        lost = max(factors.values(), key=lambda f: f.max_points - f.points)
        if lost.max_points - lost.points > 0:
            brake = lost.key

    return ScoreResult(
        score=score,
        level=_level(score, th),
        factors=factors,
        stops=stops,
        brake=brake,
    )


# --------------------------------------------------------------------------
# Verwachting
# --------------------------------------------------------------------------

FORECAST_FIELDS = (
    "temperature",
    "humidity",
    "dew_point",
    "wind_speed",
    "wind_gust_speed",
    "precipitation",
    "uv_index",
    "cloud_coverage",
    "solar_irradiance",
)


def merge_forecasts(
    primary: list[dict[str, Any]], secondary: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Voeg twee uurverwachtingen samen op het hele uur ('time').

    Per uur wint de primaire bron; velden die daar ontbreken komen uit de
    secundaire bron. Uren die alleen de secundaire bron heeft, doen ook mee.
    """
    by_time: dict[datetime, dict[str, Any]] = {}
    for src_name, rows in (("secundair", secondary), ("primair", primary)):
        for row in rows:
            slot = by_time.setdefault(row["time"], {"time": row["time"], "bronnen": {}})
            for key in FORECAST_FIELDS:
                value = row.get(key)
                if value is None:
                    continue
                slot[key] = value
                slot["bronnen"][key] = src_name
    return [by_time[t] for t in sorted(by_time)]


def _conditions_from_hour(h: dict[str, Any]) -> Conditions:
    sunny = None
    if h.get("solar_irradiance") is None and h.get("uv_index") is not None:
        cloud = h.get("cloud_coverage")
        sunny = h["uv_index"] >= 1 and (cloud is None or cloud < 60)
    return Conditions(
        temperature=h.get("temperature"),
        humidity=h.get("humidity"),
        dew_point=h.get("dew_point"),
        wind_speed=h.get("wind_speed"),
        wind_gust=h.get("wind_gust_speed"),
        rain_rate=h.get("precipitation"),
        solar=h.get("solar_irradiance"),
        sunny=sunny,
    )


def _runs(hours: list[dict[str, Any]], th: Thresholds) -> list[list[dict[str, Any]]]:
    """Aaneengesloten reeksen uren met een score vanaf de hang-grens."""
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    prev: datetime | None = None
    for h in hours:
        good = h["score"] is not None and h["score"] >= th.hang_threshold
        contiguous = prev is not None and h["time"] - prev == timedelta(hours=1)
        if good and (current and contiguous):
            current.append(h)
        elif good:
            if current:
                runs.append(current)
            current = [h]
        else:
            if current:
                runs.append(current)
            current = []
        prev = h["time"]
    if current:
        runs.append(current)
    return runs


def _window(run: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "start": run[0]["time"],
        "einde": run[-1]["time"] + timedelta(hours=1),
        "uren": len(run),
        "max_score": max(h["score"] for h in run),
    }


def build_forecast(
    merged: list[dict[str, Any]],
    th: Thresholds,
    now: datetime,
    days: int,
) -> dict[str, Any]:
    """Score per uur, per dag het beste venster, het volgende venster en de eerste regen.

    `merged[*]['time']` en `now` moeten in dezelfde (lokale) tijdzone zijn.
    """
    start_h, end_h = int(th.day_start), int(th.day_end)
    current_hour = now.replace(minute=0, second=0, microsecond=0)

    hours: list[dict[str, Any]] = []
    for h in merged:
        if h["time"] < current_hour:
            continue
        res = calculate(_conditions_from_hour(h), th)
        hours.append(
            {
                "time": h["time"],
                "score": res.score,
                "niveau": res.level,
                "reden": res.stops[0] if res.stops else res.brake,
                "temperatuur": h.get("temperature"),
                "luchtvochtigheid": h.get("humidity"),
                "wind": h.get("wind_speed"),
                "neerslag": h.get("precipitation"),
                "instraling": h.get("solar_irradiance"),
                "bronnen": h.get("bronnen", {}),
            }
        )

    in_window = [h for h in hours if start_h <= h["time"].hour <= end_h]
    by_time = {h["time"]: h for h in in_window}

    day_list: list[dict[str, Any]] = []
    first_day: date = now.date()
    for offset in range(days):
        d = first_day + timedelta(days=offset)
        scores = ""
        day_hours: list[dict[str, Any]] = []
        for hour in range(start_h, end_h + 1):
            slot = current_hour.replace(year=d.year, month=d.month, day=d.day, hour=hour)
            h = by_time.get(slot)
            if h is None:
                scores += "-"
            elif h["score"] is None:
                scores += "?"
            else:
                scores += str(h["score"])
                day_hours.append(h)
        runs = _runs(day_hours, th)
        best = max(runs, key=len) if runs else None
        known = [h["score"] for h in day_hours]
        day_list.append(
            {
                "datum": d.isoformat(),
                "scores": scores,
                "max_score": max(known) if known else None,
                "beste_venster": _window(best) if best else None,
            }
        )

    runs_all = _runs(in_window, th)
    next_window = _window(runs_all[0]) if runs_all else None

    first_rain = None
    for h in hours:
        if (h["neerslag"] or 0) > 0:
            first_rain = {"time": h["time"], "mm": h["neerslag"]}
            break

    return {
        "uren": hours,
        "dagen": day_list,
        "volgend_venster": next_window,
        "eerste_regen": first_rain,
    }
