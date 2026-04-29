"""
Browser / web tools — inspired by Hermes Agent tools/browser_tool.py + OpenClaw web-fetch.

Tools:
  screenshot_url   — capture a URL as PNG
  fetch_page       — fetch and extract readable text from URL
  extract_links    — extract links from URL
  search_duckduckgo — web search via DuckDuckGo (no API key needed)
  search_brave     — web search via Brave Search API
  check_url        — check if URL is accessible (status code, redirect)
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

log = logging.getLogger("cogman.browser")


def _http_get(url: str, headers: Dict = None, timeout: int = 15) -> tuple[int, str]:
    """Simple HTTP GET. Returns (status_code, body_text)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        **(headers or {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            try:
                body = resp.read().decode(charset, errors="replace")
            except Exception:
                body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)


def _html_to_text(html: str, max_chars: int = 8000) -> str:
    """Convert HTML to readable text (no deps needed)."""
    # Try trafilatura first (best quality)
    try:
        import trafilatura
        text = trafilatura.extract(html, include_comments=False, include_tables=True)
        if text:
            return text[:max_chars]
    except ImportError:
        pass

    # Try BeautifulSoup
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "meta", "link"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]
    except ImportError:
        pass

    # Fallback: strip tags with regex
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars].strip()


def fetch_page(url: str, raw_html: bool = False) -> str:
    """Fetch a URL and return readable text content."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    status, body = _http_get(url)
    if status == 0:
        return f"Error fetching {url}: {body}"
    if status >= 400:
        return f"HTTP {status} from {url}"
    if raw_html:
        return body[:10000]
    text = _html_to_text(body)
    return f"[{url}]\n\n{text}" if text else f"Could not extract text from {url}"


def extract_links(url: str, filter_domain: str = "") -> str:
    """Extract all links from a URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    status, body = _http_get(url)
    if status == 0 or status >= 400:
        return f"Error: HTTP {status}"

    links = re.findall(r'href=["\']([^"\'#]+)["\']', body, re.IGNORECASE)
    base = "/".join(url.split("/")[:3])

    cleaned = []
    for link in links:
        if link.startswith("//"):
            link = "https:" + link
        elif link.startswith("/"):
            link = base + link
        elif not link.startswith("http"):
            continue
        if filter_domain and filter_domain not in link:
            continue
        cleaned.append(link)

    unique = list(dict.fromkeys(cleaned))[:50]
    return "\n".join(unique) if unique else "No links found."


def check_url(url: str) -> str:
    """Check if a URL is accessible."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    status, body = _http_get(url, timeout=10)
    if status == 0:
        return f"Unreachable: {body}"
    if 200 <= status < 300:
        return f"✓ {status} OK — {url}"
    elif 300 <= status < 400:
        return f"→ {status} Redirect — {url}"
    else:
        return f"✗ {status} Error — {url}"


def screenshot_url(url: str, output_path: str = "") -> str:
    """Take a screenshot of a URL. Requires chromium or firefox."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    if not output_path:
        output_path = tempfile.mktemp(suffix=".png")

    # Try chromium-based screenshot
    for browser in ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"]:
        try:
            result = subprocess.run(
                [browser, "--headless", "--disable-gpu", "--no-sandbox",
                 f"--screenshot={output_path}", f"--window-size=1280,800", url],
                capture_output=True, timeout=30,
            )
            if result.returncode == 0 and os.path.exists(output_path):
                size = os.path.getsize(output_path)
                return f"Screenshot saved: {output_path} ({size} bytes)"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # Try wkhtmltoimage
    try:
        result = subprocess.run(
            ["wkhtmltoimage", url, output_path],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            return f"Screenshot saved: {output_path}"
    except FileNotFoundError:
        pass

    return (
        "Screenshot failed. Install chromium: sudo apt install chromium\n"
        f"Or install wkhtmltopdf: sudo apt install wkhtmltopdf"
    )


def search_duckduckgo(query: str, max_results: int = 8) -> str:
    """Search DuckDuckGo and return results (no API key needed)."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    status, body = _http_get(url, headers={"Accept-Language": "en-US"})
    if status == 0 or status >= 400:
        return f"Search failed: HTTP {status}"

    # Parse results from HTML
    results = []
    # Title + URL pattern in DuckDuckGo HTML
    snippets = re.findall(
        r'<a class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?'
        r'<a class="result__snippet"[^>]*>([^<]+)</a>',
        body, re.DOTALL,
    )
    for url, title, snippet in snippets[:max_results]:
        # DDG wraps URLs in redirects — extract actual URL
        if "uddg=" in url:
            try:
                url = urllib.parse.unquote(re.search(r"uddg=([^&]+)", url).group(1))
            except Exception:
                pass
        results.append(f"• {title.strip()}\n  {url}\n  {snippet.strip()}")

    if not results:
        # Fallback to simpler extraction
        titles = re.findall(r'class="result__title">.*?<a[^>]+href="([^"]+)"[^>]*>(.+?)</a>', body, re.DOTALL)
        for url, title in titles[:max_results]:
            results.append(f"• {re.sub('<[^>]+>', '', title).strip()}\n  {url}")

    return f"DuckDuckGo results for '{query}':\n\n" + "\n\n".join(results) if results else f"No results for: {query}"


def search_brave(query: str, max_results: int = 8) -> str:
    """Search via Brave Search API. Requires BRAVE_API_KEY."""
    api_key = os.getenv("BRAVE_API_KEY", "")
    if not api_key:
        return search_duckduckgo(query, max_results)  # fallback

    encoded = urllib.parse.quote_plus(query)
    url = f"https://api.search.brave.com/res/v1/web/search?q={encoded}&count={max_results}"
    status, body = _http_get(url, headers={"Accept": "application/json", "X-Subscription-Token": api_key})
    if status != 200:
        return f"Brave Search failed: {status}"
    try:
        data = json.loads(body)
        results = data.get("web", {}).get("results", [])
        lines = [f"Brave results for '{query}':\n"]
        for r in results:
            lines.append(f"• {r.get('title', '')}\n  {r.get('url', '')}\n  {r.get('description', '')}")
        return "\n\n".join(lines)
    except json.JSONDecodeError:
        return "Failed to parse Brave Search response."


def web_search_auto(query: str, max_results: int = 8) -> str:
    """Auto-select the best available search engine."""
    if os.getenv("BRAVE_API_KEY"):
        return search_brave(query, max_results)
    return search_duckduckgo(query, max_results)


def read_pdf(path: str, max_pages: int = 10) -> str:
    """Extract text from a PDF file."""
    try:
        import pypdf
        with open(path, "rb") as f:
            reader = pypdf.PdfReader(f)
            pages = []
            for i, page in enumerate(reader.pages[:max_pages]):
                pages.append(f"[Page {i+1}]\n{page.extract_text()}")
        return "\n\n".join(pages)
    except ImportError:
        pass
    try:
        result = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return result.stdout[:20000]
    except FileNotFoundError:
        pass
    return f"Cannot read PDF: install pypdf (pip install pypdf) or pdftotext (sudo apt install poppler-utils)"


def register_browser_tools(registry):
    registry.register(
        "fetch_page",
        fetch_page,
        "Fetch and extract readable text from a URL",
        parameters={
            "url": {"type": "string", "description": "URL to fetch", "required": True},
            "raw_html": {"type": "boolean", "description": "Return raw HTML instead of text"},
        },
    )
    registry.register(
        "extract_links",
        extract_links,
        "Extract all links from a URL",
        parameters={
            "url": {"type": "string", "description": "URL to extract links from", "required": True},
            "filter_domain": {"type": "string", "description": "Only links containing this domain"},
        },
    )
    registry.register(
        "check_url",
        check_url,
        "Check if a URL is accessible and return its HTTP status",
        parameters={"url": {"type": "string", "description": "URL to check", "required": True}},
    )
    registry.register(
        "screenshot_url",
        screenshot_url,
        "Take a screenshot of a webpage (requires chromium)",
        parameters={
            "url": {"type": "string", "description": "URL to screenshot", "required": True},
            "output_path": {"type": "string", "description": "Where to save the PNG"},
        },
    )
    registry.register(
        "web_search",
        web_search_auto,
        "Search the web using DuckDuckGo or Brave (auto-selected)",
        parameters={
            "query": {"type": "string", "description": "Search query", "required": True},
            "max_results": {"type": "integer", "description": "Max results (default 8)"},
        },
    )
    registry.register(
        "read_pdf",
        read_pdf,
        "Extract text from a PDF file",
        parameters={
            "path": {"type": "string", "description": "Path to PDF file", "required": True},
            "max_pages": {"type": "integer", "description": "Max pages to read (default 10)"},
        },
    )
