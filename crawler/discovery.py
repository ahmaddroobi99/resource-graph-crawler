"""Extract browser-reachable references from HTML and text resources."""

import re

from bs4 import BeautifulSoup

from crawler.url_utils import make_absolute


CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")\s]+)", re.IGNORECASE)
QUOTED_REF_RE = re.compile(r"(['\"])([^'\"\r\n]+)\1")


def _add_reference(found: set[str], base_url: str, reference: str) -> None:
    absolute = make_absolute(base_url, reference)
    if absolute:
        found.add(absolute)


def extract_from_html(html: str, base_url: str) -> set[str]:
    """Extract standard resource attributes, data attributes, and CSS URLs."""
    soup = BeautifulSoup(html, "lxml")
    found: set[str] = set()
    attributes = {"a": "href", "img": "src", "script": "src", "link": "href",
                  "iframe": "src", "form": "action", "source": "src", "video": "src",
                  "audio": "src"}
    for tag_name, attribute in attributes.items():
        for tag in soup.find_all(tag_name):
            reference = tag.get(attribute)
            if isinstance(reference, str):
                _add_reference(found, base_url, reference)
    for tag in soup.find_all(True):
        for name, value in tag.attrs.items():
            if name.startswith("data-"):
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if isinstance(item, str):
                        _add_reference(found, base_url, item)
            elif name == "style" and isinstance(value, str):
                for match in CSS_URL_RE.finditer(value):
                    _add_reference(found, base_url, match.group(1))
    for style in soup.find_all("style"):
        for match in CSS_URL_RE.finditer(style.get_text()):
            _add_reference(found, base_url, match.group(1))
    return found


def extract_paths_from_text(text: str, base_url: str) -> set[str]:
    """Extract quoted path-like strings and CSS url values from text."""
    found: set[str] = set()
    candidates = [match.group(2) for match in QUOTED_REF_RE.finditer(text)]
    candidates.extend(match.group(1) for match in CSS_URL_RE.finditer(text))
    for candidate in candidates:
        if candidate.startswith(("/", "./", "../", "http://", "https://")):
            _add_reference(found, base_url, candidate)
    return found


def discover_resources(content: str, base_url: str, content_type: str) -> set[str]:
    """Select HTML or generic text discovery based on response content type."""
    if "html" in content_type.lower():
        return extract_from_html(content, base_url)
    return extract_paths_from_text(content, base_url)
