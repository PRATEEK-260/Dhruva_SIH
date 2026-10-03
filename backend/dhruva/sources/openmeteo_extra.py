"""Three small Open-Meteo reads for the brief's remaining queries.

- thunder: the forecast weather code (WMO 95, 96, 99 = thunderstorm) and CAPE
  over the next hours. A forecast, never observed lightning: there is no
  lightning feed, and the answer says so.
- tide: the marine model's hourly sea level above mean sea level, whose turning
  points give high and low water. Open-Meteo itself warns this is not for
  navigation near coasts; so does the answer.
- waves: significant wave height at several points at once, for a straight-line
  route check.

Every value keeps the grid cell that answered and the hour it is for. A failed
call returns None and the answer says it could not check; it never reads as
calm.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx

FORECAST = "https://api.open-meteo.com/v1/forecast"
MARINE = "https://marine-api.open-meteo.com/v1/marine"
THUNDER_CODES = {95, 96, 99}
# How far ahead a thunderstorm counts: one fishing trip.
THUNDER_HOURS = 12
TIMEOUT = 15.0


def _hours(times: list[str]) -> list[dt.datetime]:
    return [dt.datetime.fromisoformat(t).replace(tzinfo=dt.UTC) for t in times]


async def thunder(lat: float, lon: float, when: dt.datetime) -> dict[str, Any] | None:
    """The first forecast thunderstorm hour within THUNDER_HOURS of `when`, or
    {"from": None} for none forecast. None when the forecast could not be read."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "weather_code,cape",
        "timezone": "UTC",
        "forecast_days": 3,
        "past_days": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(FORECAST, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None
    hourly = data.get("hourly") or {}
    hours = _hours(hourly.get("time") or [])
    codes = hourly.get("weather_code") or []
    capes = hourly.get("cape") or []
    end = when + dt.timedelta(hours=THUNDER_HOURS)
    out: dict[str, Any] = {
        "from": None,
        "code": None,
        "cape": None,
        "window_end": end.isoformat(),
        "cell_lat": data.get("latitude"),
        "cell_lon": data.get("longitude"),
        "dataset_id": "open_meteo_forecast",
    }
    if not hours or hours[-1] < end:
        return None  # the forecast does not reach far enough to say "none"
    for t, code, cape in zip(hours, codes, capes, strict=False):
        if when - dt.timedelta(minutes=59) <= t <= end and code in THUNDER_CODES:
            out.update({"from": t.isoformat(), "code": code, "cape": cape})
            break
    return out


async def tide(lat: float, lon: float, when: dt.datetime) -> dict[str, Any] | None:
    """The next high and low water after `when` (within 26 h) from hourly sea
    level, or None if the model gave no series."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "sea_level_height_msl",
        "timezone": "UTC",
        "forecast_days": 3,
        "past_days": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(MARINE, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None
    hourly = data.get("hourly") or {}
    hours = _hours(hourly.get("time") or [])
    levels = hourly.get("sea_level_height_msl") or []
    turns = turning_points(hours, levels)
    later = [p for p in turns if when <= p["at"] <= when + dt.timedelta(hours=26)]
    high = next((p for p in later if p["kind"] == "high"), None)
    low = next((p for p in later if p["kind"] == "low"), None)
    if high is None or low is None:
        return None
    return {
        "high": {**high, "at": high["at"].isoformat()},
        "low": {**low, "at": low["at"].isoformat()},
        "cell_lat": data.get("latitude"),
        "cell_lon": data.get("longitude"),
        "dataset_id": "open_meteo_marine",
    }


def turning_points(hours: list[dt.datetime], levels: list[float | None]) -> list[dict[str, Any]]:
    """Hourly local maxima and minima. Hourly resolution: a turning time is
    good to about half an hour, which is why the answer says "around"."""
    out = []
    for i in range(1, len(levels) - 1):
        a, b, c = levels[i - 1], levels[i], levels[i + 1]
        if a is None or b is None or c is None:
            continue
        if b > a and b >= c:
            out.append({"kind": "high", "at": hours[i], "level_m": b})
        elif b < a and b <= c:
            out.append({"kind": "low", "at": hours[i], "level_m": b})
    return out


async def waves_at(
    points: list[tuple[float, float]], when: dt.datetime
) -> list[float | None] | None:
    """Significant wave height at each point for the hour nearest `when`, one
    call for all points. None for a point the model has no sea for."""
    params = {
        "latitude": ",".join(f"{p[0]:.4f}" for p in points),
        "longitude": ",".join(f"{p[1]:.4f}" for p in points),
        "hourly": "wave_height",
        "timezone": "UTC",
        "forecast_days": 3,
        "past_days": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(MARINE, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None
    rows = data if isinstance(data, list) else [data]
    out: list[float | None] = []
    for row in rows:
        hourly = row.get("hourly") or {}
        hours = _hours(hourly.get("time") or [])
        values = hourly.get("wave_height") or []
        if not hours:
            out.append(None)
            continue
        i = min(range(len(hours)), key=lambda k: abs(hours[k] - when))
        v = values[i] if i < len(values) else None
        out.append(float(v) if v is not None else None)
    return out
