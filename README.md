# PuchAI-MCP (Movies • Bookings • OTT • Music • Weather • Trending)

Production-ready MCP server for **PuchAI** with tools for:
- 🎬 Movie booking handoff (BookMyShow + Paytm Movies): nearest city from `lat/lon`, single-city fallback, friendly city picker
- 📺 Where-to-watch OTT deeplinks (Netflix, Prime, Hotstar/JioCinema, SonyLIV, YouTube Movies)
- 🎧 Music recommendations by vibe (Spotify Client Credentials). Dynamic genre seeds + Unicode script biasing; **no hardcoded language→artist lists**
- ☁️ Weather (Open-Meteo)
- 🔥 Trending topics (Google News RSS)
- 🧭 Preference helpers (set/get preferred city)
- 🩺 Ping (health check)
- ✅ `validate` (required by Puch; returns your WhatsApp number)

---

## Quick start (with `uv`)

> `uv` is a fast Python package/dependency manager. Install:  
> **Windows/macOS/Linux:** follow https://docs.astral.sh/uv/getting-started/ or run:
> ```bash
> curl -LsSf https://astral.sh/uv/install.sh | sh
> ```
> (On Windows PowerShell: `irm https://astral.sh/uv/install.ps1 | iex`)

```bash
# 1) Clone
git clone https://github.com/<you>/<repo>.git
cd <repo>

# 2) Create & activate a virtual env managed by uv
uv venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
# .\.venv\Scripts\activate

# 3) Sync dependencies from pyproject.toml
uv sync

# 4) Create your .env (see ".env.example" below)
cp .env.example .env
# edit .env with your values

# 5) Run the server (PORT is auto-respected if set; defaults to 8086)
python puch_mcp_server.py
