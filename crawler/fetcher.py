"""Authenticated HTTP access for crawler resources."""

import logging

import requests

from config import PASSWORD, REQUEST_TIMEOUT, USERNAME, USER_AGENT
from crawler.url_utils import is_in_scope, make_absolute


LOGGER = logging.getLogger(__name__)


def get_content_type(response: requests.Response) -> str:
    """Return a normalized response content type."""
    return response.headers.get("Content-Type", "").lower()


def fetch(url: str) -> requests.Response | None:
    """Fetch one in-scope URL with Basic Auth and bounded redirects."""
    if not is_in_scope(url):
        return None
    current_url = url
    try:
        for _ in range(6):
            response = requests.get(
                current_url,
                auth=(USERNAME, PASSWORD),
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
            )
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
