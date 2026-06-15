import logging

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

FETCH_TIMEOUT = 8
MAX_SUMMARY_CHARS = 1500
USER_AGENT = "Mozilla/5.0 (compatible; tb-dlp/1.0)"


async def fetch_page_summary(url: str) -> str | None:
    """Fetch a non-video URL and extract title/description/excerpt for AI context.

    Returns None on any failure (timeout, non-HTML response, paywalled or
    JS-heavy pages with no usable text) so callers can just skip the context.
    """
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
    except Exception:
        log.info("Failed to fetch page %s", url, exc_info=True)
        return None

    if "text/html" not in resp.headers.get("content-type", ""):
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""

    description = ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if meta:
        description = (meta.get("content") or "").strip()

    paragraph = ""
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 40:
            paragraph = text
            break

    parts = []
    if title:
        parts.append(f"Title: {title}")
    if description:
        parts.append(f"Description: {description}")
    if paragraph:
        parts.append(f"Excerpt: {paragraph}")

    if not parts:
        return None

    return "\n".join(parts)[:MAX_SUMMARY_CHARS]
