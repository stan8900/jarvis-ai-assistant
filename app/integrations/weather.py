from __future__ import annotations

import logging

import httpx


logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


async def get_weather(lat: float = 51.5074, lon: float = -0.1278) -> str:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["temperature_2m", "weather_code", "wind_speed_10m"],
        "timezone": "Europe/London",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            data = response.json()

        current = data["current"]
        temp = current["temperature_2m"]
        code = current["weather_code"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.error("Weather lookup failed: %s", exc)
        return "Weather service is temporarily unavailable, sir."

    condition = weather_code_to_text(int(code))
    return f"{condition}, {round(temp)} degrees, sir."


def weather_code_to_text(code: int) -> str:
    descriptions = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snowfall",
        73: "Moderate snowfall",
        75: "Heavy snowfall",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return descriptions.get(code, "Unclassified conditions")
