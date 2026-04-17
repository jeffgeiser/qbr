"""
News fetcher via Google News RSS.

No API key required. Fetches recent news articles mentioning
a company name and returns structured results.
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from html import unescape
import re

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    title: str
    url: str
    source: str
    published: str
    snippet: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published": self.published,
            "snippet": self.snippet,
        }


async def fetch_company_news(company_name: str, max_results: int = 5) -> list[NewsArticle]:
    """Fetch recent news for a company via Google News RSS."""
    import httpx

    query = company_name.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    articles: list[NewsArticle] = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        channel = root.find("channel")
        if channel is None:
            return articles

        for item in channel.findall("item")[:max_results]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source_el = item.find("source")
            source = source_el.text if source_el is not None else ""
            desc = item.findtext("description", "")
            snippet = unescape(re.sub(r"<[^>]+>", "", desc))[:200]

            articles.append(NewsArticle(
                title=unescape(title),
                url=link,
                source=source,
                published=pub_date,
                snippet=snippet,
            ))
    except Exception as e:
        logger.warning(f"News fetch failed for '{company_name}': {e}")

    return articles
