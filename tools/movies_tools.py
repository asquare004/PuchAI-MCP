from __future__ import annotations

import os
import re
import time
import math
from datetime import datetime
from typing import Any, Dict, Tuple
from urllib.parse import quote

import httpx

AFFILIATE_PREFIX = os.getenv("AFFILIATE_PREFIX", "").strip()
AFFILIATE_SUFFIX = os.getenv("AFFILIATE_SUFFIX", "").strip()
HTTP_TIMEOUT = 8.0

_cache: Dict[str, Tuple[float, Any]] = {}
def cache_get(key: str, ttl: int = 1800):
    now = time.time()
    if key in _cache:
        ts, val = _cache[key]
        if now - ts < ttl:
            return val
    return None
def cache_set(key: str, val: Any):
    _cache[key] = (time.time(), val)

CITY_MAP = {
    "mumbai": ("Mumbai", "mumbai"),
    "bombay": ("Mumbai", "mumbai"),
    "delhi": ("Delhi-NCR", "delhi"),
    "new delhi": ("Delhi-NCR", "delhi"),
    "ncr": ("Delhi-NCR", "delhi"),
    "bengaluru": ("Bengaluru", "bengaluru"),
    "bangalore": ("Bengaluru", "bengaluru"),
    "chennai": ("Chennai", "chennai"),
    "hyderabad": ("Hyderabad", "hyderabad"),
    "pune": ("Pune", "pune"),
    "kolkata": ("Kolkata", "kolkata"),
    "ahmedabad": ("Ahmedabad", "ahmedabad"),
    "kochi": ("Kochi", "kochi"),
    "cochin": ("Kochi", "kochi"),
    "jaipur": ("Jaipur", "jaipur"),
    "surat": ("Surat", "surat"),
    "lucknow": ("Lucknow", "lucknow"),
    "coimbatore": ("Coimbatore", "coimbatore"),
    "indore": ("Indore", "indore"),
    "bhopal": ("Bhopal", "bhopal"),
    "visakhapatnam": ("Visakhapatnam", "visakhapatnam"),
    "vizag": ("Visakhapatnam", "visakhapatnam"),
    "tiruchirappalli": ("Tiruchirappalli", "tiruchirappalli"),
    "trichy": ("Tiruchirappalli", "tiruchirappalli"),
    "madurai": ("Madurai", "madurai"),
    "nagpur": ("Nagpur", "nagpur"),
    "chandigarh": ("Chandigarh", "chandigarh"),
    "mysuru": ("Mysuru", "mysuru"),
    "mysore": ("Mysuru", "mysuru"),
}

BMS_CITY_CENTERS = {
    "mumbai":        (19.0760, 72.8777),
    "delhi":         (28.6139, 77.2090),
    "bengaluru":     (12.9716, 77.5946),
    "chennai":       (13.0827, 80.2707),
    "hyderabad":     (17.3850, 78.4867),
    "pune":          (18.5204, 73.8567),
    "kolkata":       (22.5726, 88.3639),
    "ahmedabad":     (23.0225, 72.5714),
    "kochi":         (9.9312, 76.2673),
    "jaipur":        (26.9124, 75.7873),
    "surat":         (21.1702, 72.8311),
    "lucknow":       (26.8467, 80.9462),
    "coimbatore":    (11.0168, 76.9558),
    "indore":        (22.7196, 75.8577),
    "bhopal":        (23.2599, 77.4126),
    "visakhapatnam": (17.6868, 83.2185),
    "tiruchirappalli": (10.7905, 78.7047),
    "madurai":       (9.9252, 78.1198),
    "nagpur":        (21.1458, 79.0882),
    "chandigarh":    (30.7333, 76.7794),
    "mysuru":        (12.2958, 76.6394),
}

def _normalize_city_maybe(city: str | None) -> tuple[str | None, str | None]:
    if not city:
        return None, None
    key = re.sub(r"[^a-z]+", " ", city.lower()).strip()
    return CITY_MAP.get(key, (city.strip().title(), None))

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    from math import radians, sin, cos, asin, sqrt
    dlat = radians(lat2-lat1)
    dlon = radians(lon2-lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2*R*asin(sqrt(a))

def _nearest_bms_city(lat: float, lon: float, max_km: float = 75.0) -> tuple[str | None, str | None]:
    best = (None, None, 1e9)
    for slug, (clat, clon) in BMS_CITY_CENTERS.items():
        d = _haversine_km(lat, lon, clat, clon)
        if d < best[2]:
            disp = CITY_MAP.get(slug, (slug.title(), slug))[0]
            best = (disp, slug, d)
    if best[2] <= max_km:
        return best[0], best[1]
    return None, None

def _affiliate_wrap(url: str) -> str:
    if not AFFILIATE_PREFIX and not AFFILIATE_SUFFIX:
        return url
    return f"{AFFILIATE_PREFIX}{quote(url, safe='')}{AFFILIATE_SUFFIX}"

async def _reverse_geocode(lat: float, lon: float) -> str | None:
    key = f"revgeo:{lat:.4f},{lon:.4f}"
    cached = cache_get(key, ttl=3600)
    if cached is not None:
        return cached
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10, "addressdetails": 1}
    headers = {"User-Agent": "PuchMovies/1.0 (MCP Server)"}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as c:
            r = await c.get(url, params=params)
            if r.status_code == 200:
                data = r.json()
                addr = data.get("address", {})
                city = addr.get("city") or addr.get("town") or addr.get("municipality") or addr.get("county")
                if city:
                    cache_set(key, city)
                    return city
    except Exception:
        pass
    return None

def _bms_urls(display_city: str | None, bms_slug: str | None, movie_title: str | None) -> Dict[str, str]:
    if bms_slug:
        base_explore = f"https://in.bookmyshow.com/explore/movies-{bms_slug}"
        if movie_title:
            q = quote(movie_title)
            search = f"https://in.bookmyshow.com/explore/c/{bms_slug}?q={q}"
            return {"explore": _affiliate_wrap(base_explore), "search": _affiliate_wrap(search)}
        return {"explore": _affiliate_wrap(base_explore), "search": _affiliate_wrap(base_explore)}
    home = "https://in.bookmyshow.com/"
    return {"explore": _affiliate_wrap(home), "search": _affiliate_wrap(home)}

def _paytm_urls(movie_title: str | None) -> Dict[str, str]:
    base = "https://paytm.com/movies"
    if movie_title:
        q = quote(movie_title)
        return {"home": _affiliate_wrap(f"{base}?q={q}")}
    return {"home": _affiliate_wrap(base)}

def _top_city_links() -> list[Dict[str, str]]:
    popular = ["Mumbai", "Delhi-NCR", "Bengaluru", "Chennai", "Hyderabad", "Pune", "Kolkata", "Ahmedabad"]
    items = []
    for p in popular:
        disp, slug = _normalize_city_maybe(p)
        if slug:
            items.append({
                "city": disp,
                "bms": f"https://in.bookmyshow.com/explore/movies-{slug}",
                "paytm": "https://paytm.com/movies"
            })
    return items

# ──────────────────────────────────────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────────────────────────────────────
async def recommend_movies_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    # Keep empty to avoid stale lists; rely on booking deeplinks for live data
    return {"movies": []}

async def fetch_showtimes_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inputs: city? / lat+lon?, movie_title?, date?
    Returns: showtimes[], and if city unknown → city_picker[]
    Always returns at least 2 working links (BMS home + Paytm Movies) if we cannot resolve a specific city.
    """
    city_raw = (args.get("city") or "").strip()
    lat = args.get("lat")
    lon = args.get("lon")
    movie_title = (args.get("movie_title") or "").strip()
    date = args.get("date") or datetime.now().strftime("%Y-%m-%d")

    display_city, bms_slug = (None, None)
    if (lat is not None) and (lon is not None):
        display_city, bms_slug = _nearest_bms_city(float(lat), float(lon))
        if not display_city:
            resolved = await _reverse_geocode(float(lat), float(lon))
            if resolved:
                display_city, bms_slug = _normalize_city_maybe(resolved)

    if (not display_city) and city_raw:
        display_city, bms_slug = _normalize_city_maybe(city_raw)

    payload: Dict[str, Any] = {
        "movie": movie_title or (f"Now Showing in {display_city}" if display_city else "Now Showing"),
        "date": date,
        "showtimes": [],
    }

    bms = _bms_urls(display_city, bms_slug, movie_title or None)
    paytm = _paytm_urls(movie_title or None)

    if not display_city or not bms_slug:
        # Friendly picker + guaranteed working links
        payload["city_picker"] = _top_city_links()
        payload["showtimes"].append({
            "theatre": "Book on BookMyShow (choose your city in-site)",
            "address": "",
            "times": [],
            "booking_link": bms["explore"],
            "source": "bookmyshow",
        })
        payload["showtimes"].append({
            "theatre": "Book on Paytm Movies (choose city in-site)",
            "address": "",
            "times": [],
            "booking_link": paytm["home"],
            "source": "paytm",
        })
        return payload

    # City resolved → single-city links
    payload["showtimes"].append({
        "theatre": f"All theatres in {display_city}",
        "address": "",
        "times": [],
        "booking_link": bms["search"],
        "source": "bookmyshow",
    })
    payload["showtimes"].append({
        "theatre": "Paytm Movies",
        "address": "",
        "times": [],
        "booking_link": paytm["home"],
        "source": "paytm",
    })
    return payload

async def quick_book_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    return await fetch_showtimes_handler(args)

async def generate_booking_card_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    city = (args.get("city") or "").strip()
    movie = (args.get("movie_title") or "").strip() or (f"Now Showing in {city}" if city else "Now Showing")
    date = args.get("date") or datetime.now().strftime("%Y-%m-%d")
    showtimes = args.get("showtimes") or []
    trailer = args.get("trailer_url")
    city_picker = args.get("city_picker", [])

    lines = [f"🎬 *{movie}* — {city or 'Nearby'} ({date})"]
    for s in showtimes[:6]:
        theatre = s.get("theatre") or "Showtimes"
        times_list = s.get("times") or []
        times_str = ", ".join(times_list[:6]) if times_list else "Showtimes →"
        link = s.get("booking_link") or ""
        src = s.get("source") or ""
        prefix = "•"
        if src == "paytm":
            prefix = "• (Paytm)"
        elif src == "bookmyshow":
            prefix = "• (BMS)"
        lines.append(f"{prefix} {theatre}: {times_str}\n  Book: {link}")

    if trailer:
        lines.append(f"Trailer: {trailer}")

    if city_picker:
        lines.append("📍 Quick city links:")
        for item in city_picker:
            lines.append(f"• {item['city']}:")
            lines.append(f"  BMS: {item['bms']}")
            lines.append(f"  Paytm: {item['paytm']}")
        lines.append("Tip: Share your live location to auto-detect the city next time, or run: set_preferred_city.")

    lines.append("↪️ Forward this in your group to pick a show.")
    return {"share_text": "\n".join(lines)}

# ──────────────────────────────────────────────────────────────────────────────
# OTT helper
# ──────────────────────────────────────────────────────────────────────────────
def _ott_search_link(title: str) -> str:
    q = quote(f"{title} watch online site:netflix.com OR site:primevideo.com OR site:hotstar.com OR site:jiocinema.com OR site:sonyliv.com")
    return f"https://www.google.com/search?q={q}"

async def ott_where_to_watch_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    title = (args.get("title") or "").strip()
    if not title:
        return {"links": [], "hint": "Please provide a title."}
    return {
        "links": [
            {"name": "Netflix", "url": f"https://www.netflix.com/search?q={quote(title)}"},
            {"name": "Prime Video", "url": f"https://www.primevideo.com/search?phrase={quote(title)}"},
            {"name": "Disney+ Hotstar", "url": f"https://www.hotstar.com/in/search?q={quote(title)}"},
            {"name": "JioCinema", "url": f"https://www.jiocinema.com/search/{quote(title)}"},
            {"name": "Sony LIV", "url": f"https://www.sonyliv.com/search/{quote(title)}"},
            {"name": "YouTube Movies", "url": f"https://www.youtube.com/results?search_query={quote(title+' full movie')}"},
            {"name": "Smart Search", "url": _ott_search_link(title)},
        ]
    }