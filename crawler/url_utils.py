"""URL resolution, normalization, and scope checks."""

from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlsplit, urlunsplit

from config import ALLOWED_HOST, TRACKING_PARAMS


def _strip_tracking(query: str) -> str:
    """Drop volatile query parameters so equivalent URLs normalize identically."""
    kept = [(key, value) for key, value in parse_qsl(query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMS]
    return urlencode(kept)


def normalize(url: str, base: str | None = None) -> str:
    """Resolve a relative URL, drop its fragment, and strip tracking params."""
    resolved = urljoin(base, url) if base else url
    without_fragment, _ = urldefrag(resolved.strip())
    parts = urlsplit(without_fragment)
    return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path or "/",
                       _strip_tracking(parts.query), ""))


def is_in_scope(url: str) -> bool:
    """Return whether URL uses HTTP(S) and the exact challenge host."""
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and parts.hostname == ALLOWED_HOST


def make_absolute(base_url: str, relative: str) -> str | None:
    """Resolve a discovered reference and reject non-challenge URLs."""
    reference = relative.strip()
    if not reference or reference.startswith(("#", "mailto:", "javascript:", "data:")):
        return None
    absolute = normalize(reference, base_url)
    return absolute if is_in_scope(absolute) else None


def clean_url(url: str, base: str | None = None) -> str:
    """Compatibility wrapper for normalized URLs."""
    return normalize(url, base)
