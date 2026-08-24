"""Breadth-first crawl orchestration."""

import logging

from config import BASE_URL, MAX_PAGES
from crawler.discovery import discover_resources
from crawler.extractor import extract_passwords_from_bytes, extract_passwords_from_response
from crawler.fetcher import fetch, get_content_type
from crawler.frontier import Frontier, Results, Visited
from crawler.url_utils import is_in_scope, normalize
from processors.image import process_image


LOGGER = logging.getLogger(__name__)


class Crawler:
    """Traverse discovered same-host resources until the frontier is empty."""

    def __init__(self, base_url: str = BASE_URL, verbose: bool = False) -> None:
        self.base_url = normalize(base_url)
        self.visited = Visited()
        self.frontier = Frontier(self.visited)
        self.results = Results()
        self.discovered: set[str] = set()
        self.credential_leaks: set[str] = set()
        self.pages_fetched = 0
        self.verbose = verbose
        self.frontier.add(self.base_url)
        self.discovered.add(self.base_url)

    def run(self, max_pages: int | None = None) -> Results:
        """Run BFS, returning body-derived password results."""
        page_limit = MAX_PAGES if max_pages is None else max_pages
        while not self.frontier.empty and self.pages_fetched < page_limit:
            url = self.frontier.get()
            if url is None or url in self.visited:
                continue
            self.visited.add(url)
            response = fetch(url)
            self.pages_fetched += 1
            if response is None:
                continue

            content_type = get_content_type(response)
            body_passwords = extract_passwords_from_response(response)
            self.results.update(body_passwords)
            self._record_credential_context(response.text, body_passwords)

            if content_type.startswith("image/"):
                passwords = process_image(url, response.content)
                self.results.update(passwords)
            else:
                try:
                    content = response.text
                except (UnicodeDecodeError, AttributeError):
                    content = response.content.decode("utf-8", errors="ignore")
                for discovered_url in discover_resources(content, url, content_type):
                    self._enqueue(discovered_url)

            if self.verbose or self.pages_fetched % 10 == 0:
                LOGGER.info("visited=%d frontier=%d results=%d", len(self.visited),
                            len(self.frontier), len(self.results))
        return self.results

    def _enqueue(self, url: str) -> None:
        if is_in_scope(url):
            normalized = normalize(url)
            self.discovered.add(normalized)
            self.frontier.add(normalized)

    def _record_credential_context(self, body: str, passwords: set[str]) -> None:
        lowered = body.lower()
        for password in passwords:
            position = lowered.find(password.lower())
            context = lowered[max(0, position - 160):position + len(password) + 160]
            if "admin_password" in context or "fixme" in context:
                self.credential_leaks.add(password)

    def get_stats(self) -> dict[str, int | bool]:
        """Return crawl counters and the explicit completeness condition."""
        return {
            "pages_visited": len(self.visited),
            "pages_fetched": self.pages_fetched,
            "unique_urls_discovered": len(self.discovered),
            "passwords_found": len(self.results),
            "frontier_remaining": len(self.frontier),
            "complete": self.frontier.empty and self.discovered.issubset(self.visited.as_set()),
        }
