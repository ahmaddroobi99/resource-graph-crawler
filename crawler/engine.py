"""Breadth-first crawl orchestration."""

import logging
from concurrent.futures import ThreadPoolExecutor

from config import BASE_URL, MAX_PAGES
from crawler.discovery import discover_resources
from crawler.extractor import (
    extract_encoded_passwords,
    extract_passwords,
    extract_passwords_from_bytes,
)
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
        self.failed: set[str] = set()
        self.pages_fetched = 0
        self.verbose = verbose
        self.frontier.add(self.base_url)
        self.discovered.add(self.base_url)

    def run(self, max_pages: int | None = None, workers: int = 1) -> Results:
        """Run BFS in bounded fetch batches, returning body-derived results."""
        page_limit = MAX_PAGES if max_pages is None else max_pages
        workers = max(1, workers)
        while not self.frontier.empty and self.pages_fetched < page_limit:
            batch: list[str] = []
            while not self.frontier.empty and len(batch) < workers and self.pages_fetched + len(batch) < page_limit:
                url = self.frontier.get()
                if url is not None and url not in self.visited:
                    self.visited.add(url)
                    batch.append(url)
            if workers == 1:
                responses = [(batch[0], fetch(batch[0]))] if batch else []
            else:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    responses = list(zip(batch, executor.map(fetch, batch)))
            self.pages_fetched += len(batch)
            for url, response in responses:
                self._process_response(url, response)
        return self.results

    def _process_response(self, url: str, response) -> None:
        """Process one fetched response and enqueue only discovered URLs."""
        if response is None:
            self.failed.add(url)
            return

        content_type = get_content_type(response)

        # A raw-byte scan runs for every resource so passwords embedded in binary
        # payloads (e.g. UTF-16 image metadata) are caught regardless of type.
        self.results.update(extract_passwords_from_bytes(response.content))

        if content_type.startswith("image/"):
            self.results.update(process_image(url, response.content))
        else:
            content = self._decode_text(response)
            body_passwords = extract_passwords(content)
            encoded_passwords = extract_encoded_passwords(content)
            self.results.update(body_passwords)
            self.results.update(encoded_passwords)
            self._record_credential_context(content, body_passwords | encoded_passwords)
            for discovered_url in discover_resources(content, url, content_type):
                self._enqueue(discovered_url)

        if self.verbose or self.pages_fetched % 10 == 0:
            LOGGER.info("visited=%d frontier=%d results=%d", len(self.visited),
                        len(self.frontier), len(self.results))

    @staticmethod
    def _decode_text(response) -> str:
        """Return the response body as text, tolerating undecodable bytes."""
        try:
            return response.text
        except (UnicodeDecodeError, AttributeError):
            return response.content.decode("utf-8", errors="ignore")

    def _enqueue(self, url: str) -> None:
        if is_in_scope(url):
            normalized = normalize(url)
            self.discovered.add(normalized)
            self.frontier.add(normalized)

    def _record_credential_context(self, body: str, passwords: set[str]) -> None:
        lowered = body.lower()
        for password in passwords:
            position = lowered.find(password.lower())
            if position == -1:
                continue
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
            "failed_fetches": len(self.failed),
            "complete": (self.frontier.empty and not self.failed and
                          self.discovered.issubset(self.visited.as_set())),
        }
