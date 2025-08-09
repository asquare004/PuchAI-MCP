import httpx
import xml.etree.ElementTree as ET
from typing import Dict, Any, List

RSS_URL = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"

async def _fetch_rss(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(url, headers={"User-Agent": "PuchTrending/1.0"})
            if r.status_code == 200:
                return r.text
    except Exception:
        return None
    return None

def _parse_rss(xml_text: str, limit: int) -> List[dict]:
    out: List[dict] = []
    try:
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            return out
        for item in channel.findall("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            if title_el is not None and link_el is not None:
                title = (title_el.text or "").strip()
                link = (link_el.text or "").strip()
                if title and link and "Top stories" not in title:
                    out.append({"title": title, "link": link, "source": "Google News IN"})
            if len(out) >= limit:
                break
    except Exception:
        return out
    return out

async def trending_topics_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    region = (args.get("region") or "IN").upper()
    limit = int(args.get("limit") or 10)
    xml_text = await _fetch_rss(RSS_URL)
    if not xml_text:
        return {"region": region, "topics": [], "error": "Unable to fetch headlines right now."}
    items = _parse_rss(xml_text, limit)
    if not items:
        return {"region": region, "topics": [], "error": "No headlines parsed. Try again later."}
    return {"region": region, "topics": items[:limit]}