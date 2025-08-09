import os, httpx, unicodedata, re, time
from typing import Dict, Any, List, Tuple
from urllib.parse import quote

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# ──────────────────────────────────────────────────────────────────────────────
# Small cache
# ──────────────────────────────────────────────────────────────────────────────
_cache: Dict[str, tuple[float, Any]] = {}
def _cache_get(key: str, ttl: int = 3600):
    now = time.time()
    if key in _cache:
        t, v = _cache[key]
        if now - t < ttl:
            return v
    return None
def _cache_set(key: str, val: Any):
    _cache[key] = (time.time(), val)

# ──────────────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────────────
async def _spotify_token() -> str | None:
    try:
        tok = _cache_get("spotify_token", ttl=3000)
        if tok: return tok
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            return None
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
            )
            r.raise_for_status()
            tok = r.json().get("access_token")
            if tok:
                _cache_set("spotify_token", tok)
            return tok
    except Exception:
        return None

# ──────────────────────────────────────────────────────────────────────────────
# Helpers: script detection + vibe features
# ──────────────────────────────────────────────────────────────────────────────
def _dominant_script_label(text: str | None) -> str:
    """Return a coarse Unicode script label (LATIN, DEVANAGARI, TAMIL, TELUGU, etc.)."""
    if not text:
        return "LATIN"
    counts = {}
    for ch in text:
        if ch.isalpha():
            try:
                name = unicodedata.name(ch)
            except ValueError:
                continue
            lbl = name.split(" ", 1)[0]
            counts[lbl] = counts.get(lbl, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0] if counts else "LATIN"

def _script_pref_fn(script_label: str):
    """Return a predicate that checks if a string contains any char of the target script."""
    def _match(s: str) -> bool:
        try:
            for ch in s:
                if ch.isalpha():
                    name = unicodedata.name(ch)
                    if name.startswith(script_label + " "):
                        return True
        except Exception:
            pass
        return False
    return _match

def _vibe_to_audio_features(vibe: str) -> Dict[str, float]:
    v = (vibe or "").lower()
    if "chill" in v:   return {"target_valence": 0.5, "target_energy": 0.3}
    if "focus" in v:   return {"target_valence": 0.3, "target_energy": 0.2, "min_instrumentalness": 0.5}
    if "workout" in v or "gym" in v: return {"target_valence": 0.6, "target_energy": 0.8}
    if "party" in v:   return {"target_valence": 0.8, "target_energy": 0.8, "min_danceability": 0.6}
    if "romance" in v or "love" in v: return {"target_valence": 0.7, "target_energy": 0.4}
    return {"target_valence": 0.5, "target_energy": 0.5}

# ──────────────────────────────────────────────────────────────────────────────
# Dynamic seeds: genres & tracks
# ──────────────────────────────────────────────────────────────────────────────
async def _available_genre_seeds(token: str) -> List[str]:
    seeds = _cache_get("genre_seeds", ttl=24*3600)
    if seeds: return seeds
    async with httpx.AsyncClient(timeout=10, headers={"Authorization": f"Bearer {token}"}) as c:
        r = await c.get("https://api.spotify.com/v1/recommendations/available-genre-seeds")
        r.raise_for_status()
        seeds = r.json().get("genres", [])
        _cache_set("genre_seeds", seeds)
        return seeds

def _pick_genre_seeds(available: List[str], user_text: str | None, language_hint: str | None, fallback_n: int = 3) -> List[str]:
    """Match words from user_text + language hint to available genres; otherwise use generic set."""
    tokens = set()
    for src in (user_text or "", language_hint or ""):
        for w in re.findall(r"[A-Za-z][A-Za-z+-]*", src.lower()):
            tokens.add(w)

    matched = [g for g in available if any(tok in g.lower() for tok in tokens)]
    if not matched:
        common = [x for x in ["pop", "indie", "rock", "electronic", "dance"] if x in available]
        matched = common[:fallback_n] if common else available[:fallback_n]
    return matched[:5] if matched else available[:5]

async def _search_seed_tracks(token: str, queries: List[str], script_label: str, want_n: int = 5) -> List[str]:
    """Search Spotify tracks for given queries; prefer matches in the user's script; return up to want_n track IDs."""
    seen, seeds = set(), []
    prefers = _script_pref_fn(script_label)
    async with httpx.AsyncClient(timeout=12, headers={"Authorization": f"Bearer {token}"}) as c:
        for q in queries:
            if not q.strip():
                continue
            try:
                r = await c.get("https://api.spotify.com/v1/search",
                                params={"q": q, "type": "track", "limit": 15, "market": "IN"})
                r.raise_for_status()
                items = (r.json().get("tracks") or {}).get("items", [])
            except Exception:
                items = []

            # sort with script-match first
            def score(item) -> Tuple[int, int]:
                name = item.get("name") or ""
                artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
                s = name + " " + artists
                return (1 if prefers(s) else 0, len(s))  # prefer script match, then shorter strings a bit

            items.sort(key=score, reverse=True)

            for it in items:
                tid = it.get("id")
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                seeds.append(tid)
                if len(seeds) >= want_n:
                    return seeds
    return seeds

# ──────────────────────────────────────────────────────────────────────────────
# Main handler
# ──────────────────────────────────────────────────────────────────────────────
async def music_vibe_recs_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Robust, generic, *no hardcoded language maps*:
      1) Build queries from (language hint + vibe + user_text)
      2) Find up to 5 seed tracks via Spotify Search (script-aware)
      3) Else fall back to dynamic genre seeds
      4) Request extra recs; bias to user's script; backfill to meet limit
    """
    vibe      = args.get("vibe") or "chill"
    language  = (args.get("language") or "").strip()
    user_text = args.get("user_text") or ""
    limit     = int(args.get("limit") or 10)

    token = await _spotify_token()
    if not token:
        return {
            "error": "Spotify credentials missing.",
            "fix": "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env.",
            "example_env": "SPOTIFY_CLIENT_ID=xxxxxxxx\nSPOTIFY_CLIENT_SECRET=xxxxxxxx",
            "tracks": []
        }

    script_label = _dominant_script_label(user_text or language)
    prefers = _script_pref_fn(script_label)

    # 1) Build smart search queries (no hardcoding)
    #    Examples: "tamil workout", "bollywood party", "punjabi chill", plus raw vibe & any quoted phrase from user_text
    quoted = re.findall(r'"([^"]+)"', user_text)
    tokens = " ".join(re.findall(r"[A-Za-z][A-Za-z+-]*", user_text))
    queries = []
    if language: queries.append(f"{language} {vibe}")
    if language: queries.append(f"{language}")
    queries.append(vibe)
    for q in quoted:
        queries.append(q)
    if tokens and tokens.lower() not in [q.lower() for q in queries]:
        queries.append(tokens)

    # 2) Try to get seed tracks dynamically
    seed_tracks = await _search_seed_tracks(token, queries, script_label, want_n=5)

    # 3) If no seed tracks, use genre seeds
    used_genre_seeds = []
    rec_params = {"limit": str(min(50, max(10, limit * 3))), "market": "IN"}
    if seed_tracks:
        rec_params["seed_tracks"] = ",".join(seed_tracks[:5])
    else:
        try:
            seeds_available = await _available_genre_seeds(token)
        except Exception:
            seeds_available = ["pop", "rock", "indie", "electronic", "dance"]
        used_genre_seeds = _pick_genre_seeds(seeds_available, user_text, language)
        rec_params["seed_genres"] = ",".join(used_genre_seeds)

    # 4) Add vibe tuning
    for k, v in _vibe_to_audio_features(vibe).items():
        rec_params[k] = str(v)

    # 5) Hit recommendations
    try:
        async with httpx.AsyncClient(timeout=12, headers={"Authorization": f"Bearer {token}"}) as c:
            r = await c.get("https://api.spotify.com/v1/recommendations", params=rec_params)
            r.raise_for_status()
            items = r.json().get("tracks", [])
    except Exception as e:
        # As a last resort, if we had any seed tracks, just return them as "tracks"
        if seed_tracks:
            tracks = []
            async with httpx.AsyncClient(timeout=12, headers={"Authorization": f"Bearer {token}"}) as c:
                for tid in seed_tracks[:limit]:
                    try:
                        tr = await c.get(f"https://api.spotify.com/v1/tracks/{tid}", params={"market": "IN"})
                        if tr.status_code == 200:
                            t = tr.json()
                            name = t.get("name", "Track")
                            artists = ", ".join(a.get("name", "") for a in t.get("artists", [])) or "—"
                            url_spotify = (t.get("external_urls") or {}).get("spotify", "https://open.spotify.com/")
                            q = quote(f"{name} {artists}")
                            tracks.append({
                                "title": name,
                                "artists": artists,
                                "spotify": url_spotify,
                                "apple_music_search": f"https://music.apple.com/in/search?term={q}",
                                "jiosaavn_search": f"https://www.jiosaavn.com/search/{q}",
                                "youtube": f"https://www.youtube.com/results?search_query={q}",
                            })
                    except Exception:
                        continue
            return {
                "vibe": vibe,
                "language_hint": language or None,
                "dominant_script": script_label,
                "used_seed_tracks": seed_tracks,
                "used_genre_seeds": used_genre_seeds,
                "note": f"Spotify recommendations errored: {e}. Returned seed tracks instead.",
                "tracks": tracks[:limit],
            }
        return {
            "error": f"Spotify recommendations error: {e}",
            "used_seed_tracks": seed_tracks,
            "used_genre_seeds": used_genre_seeds,
            "tracks": []
        }

    # 6) Script-aware ranking + backfill
    filtered, backfill = [], []
    for t in items:
        name = t.get("name", "")
        artists = ", ".join(a.get("name", "") for a in t.get("artists", []))
        url_spotify = (t.get("external_urls") or {}).get("spotify", "https://open.spotify.com/")
        q = quote(f"{name} {artists}") if (name or artists) else "music"
        rec = {
            "title": name or "Track",
            "artists": artists or "—",
            "spotify": url_spotify,
            "apple_music_search": f"https://music.apple.com/in/search?term={q}",
            "jiosaavn_search": f"https://www.jiosaavn.com/search/{q}",
            "youtube": f"https://www.youtube.com/results?search_query={q}",
        }
        (filtered if (prefers(name) or prefers(artists)) else backfill).append(rec)
        if len(filtered) >= limit:
            break

    tracks = (filtered + backfill)[:limit] or backfill[:limit]
    return {
        "vibe": vibe,
        "language_hint": language or None,
        "dominant_script": script_label,
        "used_seed_tracks": seed_tracks,
        "used_genre_seeds": used_genre_seeds,
        "tracks": tracks,
        "hint": "You can add words like 'bollywood', 'punjabi', 'tamil', 'telugu', 'k-pop' or pass language='...' to steer results.",
    }