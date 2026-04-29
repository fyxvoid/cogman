# skill: translate
# description: Translate text to any language using LibreTranslate or LLM fallback
# tags: language, utility, translation
# version: 1.0
# created: 2026-04-28

def run(text: str = "", target: str = "en", source: str = "auto", **kwargs) -> str:
    if not text:
        return "Usage: skill_translate text=<text> target=<lang_code> e.g. target=es"
    import urllib.request, urllib.parse, json

    # Try LibreTranslate (free, self-hostable)
    lt_url = "https://libretranslate.com/translate"
    payload = json.dumps({"q": text, "source": source, "target": target, "format": "text"}).encode()
    try:
        req = urllib.request.Request(
            lt_url, data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            if "translatedText" in result:
                return result["translatedText"]
    except Exception:
        pass

    # Fallback: MyMemory free API (no key needed)
    try:
        encoded = urllib.parse.quote(text[:500])
        src = "" if source == "auto" else source
        url = f"https://api.mymemory.translated.net/get?q={encoded}&langpair={src}|{target}"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            translated = data.get("responseData", {}).get("translatedText", "")
            if translated:
                return translated
    except Exception as e:
        return f"Translation failed: {e}"

    return "Translation service unavailable."
