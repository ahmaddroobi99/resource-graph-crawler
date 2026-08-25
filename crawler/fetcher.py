"""Authenticated HTTP access for crawler resources."""

import logging
import time

import requests

from config import PASSWORD, PROXY, REQUEST_TIMEOUT, USERNAME, USER_AGENT
from crawler.url_utils import is_in_scope, make_absolute


LOGGER = logging.getLogger(__name__)


# All fetches share one proxy mapping so ``fetch`` keeps its single-argument
# shape (``executor.map(fetch, batch)`` in the engine passes only the URL).
# ``None`` means fetch directly; ``configure_proxy`` swaps it at runtime.
_PROXIES: dict[str, str] | None = {"http": PROXY, "https": PROXY} if PROXY else None


def configure_proxy(proxy_url: str | None) -> None:
    """Route every subsequent fetch through an HTTP/SOCKS proxy (or disable)."""
    global _PROXIES
    _PROXIES = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    if proxy_url:
        LOGGER.info("Routing requests through proxy %s", proxy_url)


def get_content_type(response: requests.Response) -> str:
    """Return a normalized response content type."""
    return response.headers.get("Content-Type", "").lower()


def fetch(url: str, retries: int = 3) -> requests.Response | None:
    """Fetch one in-scope URL with Basic Auth and bounded redirects."""
    if not is_in_scope(url):
        return None
    current_url = url
    try:
        for _ in range(6):
            response = None
            for attempt in range(retries + 1):
                try:
                    response = requests.get(
                        current_url,
                        auth=(USERNAME, PASSWORD),
                        headers={"User-Agent": USER_AGENT},
                        timeout=REQUEST_TIMEOUT,
                        allow_redirects=False,
                        proxies=_PROXIES,
                    )
                    break
                except requests.RequestException as exc:
                    if attempt == retries:
                        raise
                    LOGGER.warning("Retrying %s after request failure: %s", current_url, exc)
                    time.sleep(0.25 * (attempt + 1))
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                next_url = make_absolute(current_url, location or "")
                if next_url is None:
                    LOGGER.warning("Rejected out-of-scope redirect from %s", current_url)
                    return None
                current_url = next_url
                continue
            if not 200 <= response.status_code < 300:
                LOGGER.warning("%s returned HTTP %s", current_url, response.status_code)
            return response
        LOGGER.warning("Too many redirects for %s", url)
    except requests.RequestException as exc:
        LOGGER.warning("Request failed for %s: %s", url, exc)
    return None
