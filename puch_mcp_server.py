import asyncio
import os
from typing import Annotated

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict

from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from mcp.server.auth.provider import AccessToken

# ──────────────────────────────────────────────────────────────────────────────
# Load env
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()

TOKEN = os.environ.get("AUTH_TOKEN")
MY_NUMBER = os.environ.get("MY_NUMBER")
PREFS_PATH = os.environ.get("PREFS_PATH", "prefs.json")

assert TOKEN, "Please set AUTH_TOKEN in your .env file"
assert MY_NUMBER, "Please set MY_NUMBER in your .env file"

# ──────────────────────────────────────────────────────────────────────────────
# Auth Provider (Bearer)
# ──────────────────────────────────────────────────────────────────────────────
class SimpleBearerAuthProvider(BearerAuthProvider):
    def __init__(self, token: str):
        k = RSAKeyPair.generate()
        super().__init__(public_key=k.public_key, jwks_uri=None, issuer=None, audience=None)
        self.token = token

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token == self.token:
            return AccessToken(token=token, client_id="puch-client", scopes=["*"], expires_at=None)
        return None

# ──────────────────────────────────────────────────────────────────────────────
# Helper: rich descriptions for Puch tooltips
# ──────────────────────────────────────────────────────────────────────────────
class RichToolDescription(BaseModel):
    description: str
    use_when: str
    side_effects: str | None = None

# ──────────────────────────────────────────────────────────────────────────────
# Tiny prefs store (JSON on disk)
# ──────────────────────────────────────────────────────────────────────────────
def _load_prefs():
    import json, os
    if not os.path.exists(PREFS_PATH):
        return {}
    try:
        with open(PREFS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_prefs(prefs):
    import json
    tmp = PREFS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PREFS_PATH)

# ──────────────────────────────────────────────────────────────────────────────
# Import handlers
# ──────────────────────────────────────────────────────────────────────────────
from tools.movies_tools import (
    recommend_movies_handler,
    fetch_showtimes_handler,
    quick_book_handler,
    generate_booking_card_handler,
    ott_where_to_watch_handler,
)
from tools.music_tools import music_vibe_recs_handler
from tools.weather_tools import weather_now_handler, weather_forecast_handler
from tools.trending_tools import trending_topics_handler

# ──────────────────────────────────────────────────────────────────────────────
# MCP Server
# ──────────────────────────────────────────────────────────────────────────────
mcp = FastMCP("Puch MCP Server", auth=SimpleBearerAuthProvider(TOKEN))

# ──────────────────────────────────────────────────────────────────────────────
# Required by Puch: validate → returns your phone (E.164-like)
# ──────────────────────────────────────────────────────────────────────────────
@mcp.tool
async def validate() -> str:
    return MY_NUMBER

# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────
class RecommendMoviesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str | None = Field(default=None, description="City (optional)")
    language: str | None = Field(default=None, description="Preferred language (optional)")
    genre: str | None = Field(default=None, description="Optional genre(s)")
    limit: int = Field(default=5, ge=1, le=10, description="How many suggestions")

class FetchShowtimesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str | None = Field(default=None, description="City (optional if lat/lon provided)")
    movie_title: str | None = Field(default=None, description="Movie title (optional: browse all)")
    date: str | None = Field(default=None, description="YYYY-MM-DD; defaults to today")
    radius_km: int = Field(default=20, ge=1, description="Reserved for future")
    lat: float | None = Field(default=None, description="Latitude (optional)")
    lon: float | None = Field(default=None, description="Longitude (optional)")

class ShowtimeItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    theatre: str
    address: str | None = None
    times: list[str] = []
    booking_link: str
    source: str | None = None

class GenerateBookingCardArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    city: str | None
    movie_title: str | None
    date: str
    showtimes: list[ShowtimeItem]
    trailer_url: str | None = None
    city_picker: list[dict] | None = None

class QuickBookArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    movie_title: str | None = Field(default=None, description="Movie name (optional)")
    date: str | None = Field(default=None, description="YYYY-MM-DD; default today")
    city: str | None = Field(default=None, description="City (optional if lat/lon provided)")
    lat: float | None = Field(default=None, description="Latitude (optional)")
    lon: float | None = Field(default=None, description="Longitude (optional)")

class OTTWhereArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(description="Movie/series title")
    language: str | None = Field(default=None, description="Optional language")

class MusicVibeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vibe: str = Field(description="e.g., chill, workout, focus, party")
    language: str | None = Field(default=None, description="Optional hint word like 'bollywood', 'punjabi', 'tamil'")
    limit: int = Field(default=10, ge=1, le=50)
    user_text: str | None = Field(default=None, description="Original user message for script/genre hints")

class WeatherArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str | None = Field(default=None)
    lat: float | None = Field(default=None)
    lon: float | None = Field(default=None)

# ──────────────────────────────────────────────────────────────────────────────
# City preference tools
# ──────────────────────────────────────────────────────────────────────────────
SET_CITY_DESC = RichToolDescription(
    description="Set your preferred default city for bookings.",
    use_when="User says 'set my city to X'.",
)
@mcp.tool(description=SET_CITY_DESC.model_dump_json())
async def set_preferred_city(
    city: Annotated[str, Field(description="City name, e.g., 'Bengaluru'")]
) -> dict:
    prefs = _load_prefs()
    prefs["preferred_city"] = city.strip()
    _save_prefs(prefs)
    return {"status": "ok", "message": f"Saved preferred city as {city.strip()}."}

GET_CITY_DESC = RichToolDescription(
    description="Get your saved preferred city, if any.",
    use_when="Use before booking when city is not provided.",
)
@mcp.tool(description=GET_CITY_DESC.model_dump_json())
async def get_preferred_city() -> dict:
    prefs = _load_prefs()
    return {"city": prefs.get("preferred_city")}

# ──────────────────────────────────────────────────────────────────────────────
# Movies / Booking tools
# ──────────────────────────────────────────────────────────────────────────────
RECOMMEND_MOVIES_DESCRIPTION = RichToolDescription(
    description="Light movie ideas (live booking handled via BMS/Paytm links).",
    use_when="User asks for ideas; not essential for booking.",
)
@mcp.tool(description=RECOMMEND_MOVIES_DESCRIPTION.model_dump_json())
async def recommend_movies(
    city: Annotated[str | None, Field(description="City, optional")] = None,
    language: Annotated[str | None, Field(description="Preferred language, optional")] = None,
    genre: Annotated[str | None, Field(description="Optional genre(s)")] = None,
    limit: Annotated[int, Field(ge=1, le=10, description="Max suggestions")] = 5,
) -> dict:
    args = RecommendMoviesArgs(city=city, language=language, genre=genre, limit=limit).model_dump()
    return await recommend_movies_handler(args)

FETCH_SHOWTIMES_DESCRIPTION = RichToolDescription(
    description="Book via BookMyShow + Paytm deeplinks. Uses nearest BMS city from lat/lon; else single normalized city; else city picker.",
    use_when="User says 'book movie' or asks showtimes.",
)
@mcp.tool(description=FETCH_SHOWTIMES_DESCRIPTION.model_dump_json())
async def fetch_showtimes(
    city: Annotated[str | None, Field(description="City, optional if lat/lon provided")] = None,
    movie_title: Annotated[str | None, Field(description="Movie title (optional)")] = None,
    date: Annotated[str | None, Field(description="YYYY-MM-DD; default today")] = None,
    radius_km: Annotated[int, Field(ge=1, description="Reserved")] = 20,
    lat: Annotated[float | None, Field(description="Latitude")] = None,
    lon: Annotated[float | None, Field(description="Longitude")] = None,
) -> dict:
    if not city and lat is None and lon is None:
        prefs = _load_prefs()
        city = prefs.get("preferred_city")
    args = FetchShowtimesArgs(city=city, movie_title=movie_title, date=date, radius_km=radius_km, lat=lat, lon=lon).model_dump()
    return await fetch_showtimes_handler(args)

QUICK_BOOK_DESCRIPTION = RichToolDescription(
    description="One-tap booking handoff. Provide zero/minimal info; shares BMS/Paytm links and city picker if needed.",
    use_when="Default entry point for booking.",
)
@mcp.tool(description=QUICK_BOOK_DESCRIPTION.model_dump_json())
async def quick_book(
    movie_title: Annotated[str | None, Field(description="Movie name (optional)")] = None,
    date: Annotated[str | None, Field(description="YYYY-MM-DD; default today")] = None,
    city: Annotated[str | None, Field(description="City (optional if lat/lon provided)")] = None,
    lat: Annotated[float | None, Field(description="Latitude")] = None,
    lon: Annotated[float | None, Field(description="Longitude")] = None,
) -> dict:
    if not city and lat is None and lon is None:
        prefs = _load_prefs()
        city = prefs.get("preferred_city")
    args = QuickBookArgs(movie_title=movie_title, date=date, city=city, lat=lat, lon=lon).model_dump()
    return await quick_book_handler(args)

GENERATE_BOOKING_CARD_DESCRIPTION = RichToolDescription(
    description="Create a WhatsApp-friendly, shareable booking card (BMS + Paytm).",
    use_when="After quick_book/fetch_showtimes.",
)
@mcp.tool(description=GENERATE_BOOKING_CARD_DESCRIPTION.model_dump_json())
async def generate_booking_card(
    date: Annotated[str, Field(description="YYYY-MM-DD")],
    showtimes: Annotated[list[ShowtimeItem], Field(description="Showtimes list from fetch_showtimes/quick_book")],
    city: Annotated[str | None, Field(description="City (optional)")] = None,
    movie_title: Annotated[str | None, Field(description="Movie title (optional)")] = None,
    trailer_url: Annotated[str | None, Field(description="Optional trailer URL")] = None,
    city_picker: Annotated[list[dict] | None, Field(description="Internal: pass city_picker if present")] = None,
) -> dict:
    payload = GenerateBookingCardArgs(
        city=city,
        movie_title=movie_title,
        date=date,
        showtimes=showtimes,
        trailer_url=trailer_url,
        city_picker=city_picker,
    ).model_dump()
    return await generate_booking_card_handler(payload)

OTT_DESC = RichToolDescription(
    description="Find where to watch a title across OTTs (Netflix, Prime, Hotstar/JioCinema/etc.).",
    use_when="User asks 'Where can I watch <title>?'",
)
@mcp.tool(description=OTT_DESC.model_dump_json())
async def ott_where_to_watch(
    title: Annotated[str, Field(description="Title")],
    language: Annotated[str | None, Field(description="Optional")] = None,
) -> dict:
    return await ott_where_to_watch_handler({"title": title, "language": language})

# ──────────────────────────────────────────────────────────────────────────────
# Music (robust + generic)
# ──────────────────────────────────────────────────────────────────────────────
MUSIC_DESC = RichToolDescription(
    description="Music recommendations by vibe. Dynamic Spotify genres, script biasing, and graceful fallbacks.",
    use_when="User asks for songs for a mood/activity.",
)
@mcp.tool(description=MUSIC_DESC.model_dump_json())
async def music_vibe_recommendations(
    vibe: Annotated[str, Field(description="Mood/activity, e.g., chill, workout")],
    language: Annotated[str | None, Field(description="Optional hint word like 'bollywood', 'punjabi', 'tamil'")] = None,
    limit: Annotated[int, Field(ge=1, le=50, description="How many tracks")] = 10,
    user_text: Annotated[str | None, Field(description="Original user message for script/genre hints")] = None,
) -> dict:
    return await music_vibe_recs_handler({
        "vibe": vibe,
        "language": language,
        "limit": limit,
        "user_text": user_text
    })

MUSIC_ALIAS_DESC = RichToolDescription(
    description=(
        "Recommend songs by vibe/language keywords. Triggers: music, song(s), track(s), playlist(s), "
        "workout, gym, party, chill, focus, romance, bollywood, punjabi, tamil, telugu, hindi, k-pop."
    ),
    use_when=(
        "User asks for songs/music/playlists or names a mood/language/genre (e.g., 'workout tamil songs')."
    ),
)
@mcp.tool(description=MUSIC_ALIAS_DESC.model_dump_json())
async def music(
    vibe: Annotated[str, Field(description="Mood/activity")],
    language: Annotated[str | None, Field(description="Optional hint like 'bollywood','punjabi','tamil'")] = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
    user_text: Annotated[str | None, Field(description="Original user message")] = None,
) -> dict:
    from tools.music_tools import music_vibe_recs_handler
    return await music_vibe_recs_handler({"vibe": vibe, "language": language, "limit": limit, "user_text": user_text})
# ──────────────────────────────────────────────────────────────────────────────
# Weather
# ──────────────────────────────────────────────────────────────────────────────
@mcp.tool(description="Current weather by city or lat/lon (Open-Meteo).")
async def weather_now(
    city: Annotated[str | None, Field(description="City")] = None,
    lat: Annotated[float | None, Field(description="Latitude")] = None,
    lon: Annotated[float | None, Field(description="Longitude")] = None,
) -> dict:
    return await weather_now_handler({"city": city, "lat": lat, "lon": lon})

@mcp.tool(description="3-day forecast by city or lat/lon (Open-Meteo).")
async def weather_forecast(
    city: Annotated[str | None, Field(description="City")] = None,
    lat: Annotated[float | None, Field(description="Latitude")] = None,
    lon: Annotated[float | None, Field(description="Longitude")] = None,
) -> dict:
    return await weather_forecast_handler({"city": city, "lat": lat, "lon": lon})

# ──────────────────────────────────────────────────────────────────────────────
# Trending topics (IN)
# ──────────────────────────────────────────────────────────────────────────────
@mcp.tool(description="Trending topics in India (free headlines approximation).")
async def trending_topics(
    region: Annotated[str, Field(description="Region code, default IN")] = "IN",
    limit: Annotated[int, Field(ge=1, le=20, description="Items to return")] = 10,
) -> dict:
    return await trending_topics_handler({"region": region, "limit": limit})

# ──────────────────────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────────────────────
async def main():
    import os
    port = int(os.getenv("PORT", "8086"))
    print("🚀 Starting MCP server on http://0.0.0.0:8086")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8086)

if __name__ == "__main__":
    asyncio.run(main())