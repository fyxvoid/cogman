"""Web tools: search, fetch, weather."""
import logging
import urllib.parse
import urllib.request
import json
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell

log = logging.getLogger("cogman.tools.web")


def web_search(query: str) -> str:
    """Open a DuckDuckGo search in the browser."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://duckduckgo.com/?q={encoded}"
    run_shell(f"xdg-open '{url}'")
    return f"Opened browser: DuckDuckGo search for '{query}'"


def fetch_url(url: str) -> str:
    """Fetch plain text content from a URL (no JS)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cogman/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(50_000).decode("utf-8", errors="replace")
            # Strip HTML tags roughly
            import re
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:3000] + ("..." if len(text) > 3000 else "")
    except Exception as e:
        return f"Fetch error: {e}"


def get_weather(city: str = "") -> str:
    """Get weather via wttr.in (no API key needed)."""
    location = urllib.parse.quote_plus(city) if city else ""
    url = f"https://wttr.in/{location}?format=3"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception as e:
        return f"Weather fetch error: {e}"


def register_web_tools(registry: ToolRegistry):
    registry.register(
        "web_search",
        web_search,
        "Search the web using DuckDuckGo (opens browser)",
        {"query": {"type": "string", "description": "Search query", "required": True}},
    )
    registry.register(
        "fetch_url",
        fetch_url,
        "Fetch and return text content from a URL",
        {"url": {"type": "string", "description": "URL to fetch", "required": True}},
    )
    registry.register(
        "get_weather",
        get_weather,
        "Get current weather for a city",
        {"city": {"type": "string", "description": "City name (default: auto-detect by IP)"}},
    )
