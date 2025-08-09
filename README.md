# PuchAI-MCP 
> Movies • OTT • Music • Weather • Trending Topics

MCP server that helps users book movie tickets in nearby theatres, recommends music based on their vibe, offers multilingual support, informs users about current weather, predicts weather in the near future and displays current trending topics.

**Live MCP Endpoint:** https://puchai-mcp.onrender.com/mcp/

## ✨ Features
- 🎬 **Movie Booking** — BookMyShow + Paytm Movies handoff
  - Auto-detect nearest city from `lat/lon`
  - Clean fallback to single-city selection
  - One-tap booking links (BMS + Paytm)
- 📺 **OTT Availability** — smart deeplinks (Netflix, Prime, Hotstar/JioCinema, SonyLIV, YouTube Movies)
- 🎧 **Music Recommendations** — Spotify (Client Credentials), dynamic genre seeds + Unicode script biasing (no hardcoded language→artist lists)
- ☁️ **Weather** — current & 3-day forecast (Open-Meteo)
- 🔥 **Trending Topics** — Google News RSS
- 🧭 **Preferences** — set/get preferred city
- 🩺 **Health Check** — `ping()`
- ✅ **Puch Validate** — `validate()` returns your WhatsApp number (required by Puch)

## 🔌 Connect from PuchAI
### Connection Prompts
~~~text
/mcp connect https://puchai-mcp.onrender.com/mcp YOUR_AUTH_TOKEN
/mcp status
/mcp tools
~~~

### Smoke Tests
~~~text
/mcp call ping {}
/mcp call weather_now {"city":"Chennai"}
/mcp call music {"vibe":"workout","language":"tamil","limit":8,"user_text":"workout tamil songs"}
/mcp call quick_book {}