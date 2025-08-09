import httpx
from typing import Dict, Any

async def _forward_geocode(city: str) -> tuple[float | None, float | None, str | None]:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://nominatim.openstreetmap.org/search",
                            params={"q": city, "format": "json", "limit": 1},
                            headers={"User-Agent": "PuchWeather/1.0"})
            if r.status_code == 200 and r.json():
                j = r.json()[0]
                return float(j["lat"]), float(j["lon"]), j.get("display_name", city)
    except Exception:
        pass
    return None, None, None

async def _coords(city: str | None, lat: float | None, lon: float | None):
    if lat is not None and lon is not None:
        return lat, lon, city
    if city:
        return await _forward_geocode(city)
    return None, None, None

async def weather_now_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    lat, lon, label = await _coords(args.get("city"), args.get("lat"), args.get("lon"))
    if lat is None or lon is None:
        return {"error": "Please provide a city or share location."}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://api.open-meteo.com/v1/forecast",
                            params={"latitude": lat, "longitude": lon, "current_weather": "true", "timezone": "auto"})
            r.raise_for_status()
            cw = r.json().get("current_weather", {})
        return {"where": label or f"{lat},{lon}", "current": cw}
    except Exception as e:
        return {"error": f"Weather API error: {e}"}

async def weather_forecast_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    lat, lon, label = await _coords(args.get("city"), args.get("lat"), args.get("lon"))
    if lat is None or lon is None:
        return {"error": "Please provide a city or share location."}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://api.open-meteo.com/v1/forecast",
                            params={"latitude": lat, "longitude": lon,
                                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_mean",
                                    "timezone": "auto", "forecast_days": 3})
            r.raise_for_status()
            daily = r.json().get("daily", {})
        return {"where": label or f"{lat},{lon}", "daily": daily}
    except Exception as e:
        return {"error": f"Weather API error: {e}"}