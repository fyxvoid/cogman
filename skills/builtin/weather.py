# skill: weather
# description: Get current weather for any city (no API key needed via wttr.in)
# tags: weather, info, utility
# version: 1.0
# created: 2026-04-28

def run(city: str = "auto", format: str = "4", **kwargs) -> str:
    import urllib.request, urllib.parse
    location = urllib.parse.quote_plus(city) if city != "auto" else ""
    url = f"https://wttr.in/{location}?format={format}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read().decode().strip()
    except Exception as e:
        return f"Weather unavailable: {e}"
