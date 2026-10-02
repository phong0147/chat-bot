"""Read public articles from the Zendesk Help Center API."""
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

LOG = logging.getLogger("scraper")
DEFAULT_SOURCE = "https://support.optisigns.com"


class ZendeskClient:
    def __init__(self, source=DEFAULT_SOURCE, locale="en-us", timeout=30):
        self.source = source.rstrip("/")
        self.locale = locale
        self.timeout = timeout

    def get(self, url: str) -> dict:
        # Pagination URLs must stay on the public Help Center being scraped.
        if urlsplit(url)[:2] != urlsplit(self.source)[:2]:
            raise ValueError(f"Unexpected pagination origin: {url}")
        for attempt in range(4):
            try:
                request = Request(url, headers={
                    "Accept": "application/json",
                    "User-Agent": "HelpCenterMarkdownIngest/1.0",
                })
                with urlopen(request, timeout=self.timeout) as response:
                    data = json.load(response)
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object from Zendesk")
                return data
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise
                retry_after = exc.headers.get("Retry-After", "")
                delay = min(int(retry_after), 60) if retry_after.isdigit() else 2 ** attempt
                LOG.warning("HTTP %s; retrying in %ss", exc.code, delay)
                time.sleep(delay)
            except (URLError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("Retry limit reached")

    def articles(self, include_query="YouTube"):
        seen_ids = set()
        if include_query:
            # Seed the corpus with a relevant article for the brief's demo question.
            query = urlencode({"query": include_query, "locale": self.locale, "per_page": 10})
            result = self.get(f"{self.source}/api/v2/help_center/articles/search.json?{query}")
            matches = [a for a in result["results"] if not a.get("draft")]
            if not matches:
                raise ValueError(f"No public article found for {include_query!r}")
            match = next((a for a in matches if include_query.casefold() in a["title"].casefold()), matches[0])
            article_id = int(match["id"])
            detail = self.get(f"{self.source}/api/v2/help_center/{self.locale}/articles/{article_id}.json")
            yield detail["article"]
            seen_ids.add(article_id)
        query = urlencode({"per_page": 100, "sort_by": "created_at", "sort_order": "asc"})
        url = f"{self.source}/api/v2/help_center/{self.locale}/articles.json?{query}"
        seen_pages = set()
        while url:
            if url in seen_pages:
                raise ValueError("Zendesk returned a repeated pagination URL")
            seen_pages.add(url)
            data = self.get(url)
            for article in data["articles"]:
                article_id = int(article["id"])
                if article_id not in seen_ids and not article.get("draft"):
                    seen_ids.add(article_id)
                    yield article
            next_page = data.get("next_page")
            url = urljoin(url, next_page) if next_page else None
