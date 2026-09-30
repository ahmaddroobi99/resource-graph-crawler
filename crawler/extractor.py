"""Match extraction from response bodies and binary payloads.

The active search pattern defaults to the challenge password shape
(``VISUALPING{16-hex}``) but can be reconfigured at runtime — via the CLI
``--pattern`` flag, the ``RGC_PATTERN`` environment variable, or the GUI's
"Search pattern" field — so the same crawler can hunt for *any* regular
expression, not just that one password. Call :func:`configure_pattern` once
before a crawl; every extraction path below reads the same module-level pattern.
"""

import base64
import binascii
import re

import config


# Single source of truth for what a crawl is looking for. ``_EXAMPLE`` is one
# match to always discard (the challenge's documented placeholder); it is empty
# for custom patterns, where no such placeholder exists.
_PATTERN: "re.Pattern[str]" = config.COMPILED_PATTERN_RE
_EXAMPLE: str = config.EXAMPLE_PASSWORD if config.PATTERN_REGEX == config.PASSWORD_REGEX else ""


def configure_pattern(regex, example: str = "") -> "re.Pattern[str]":
    """Set the regex every extractor scans for, returning the compiled pattern.

    ``regex`` is a pattern string or an already-compiled pattern; ``example`` is
    an optional single match to exclude from results.
    """
    global _PATTERN, _EXAMPLE
    _PATTERN = re.compile(regex) if isinstance(regex, str) else regex
    _EXAMPLE = example or ""
    return _PATTERN


def active_pattern() -> "re.Pattern[str]":
    """Return the currently configured search pattern."""
    return _PATTERN


def extract_passwords(text: str) -> set[str]:
    """Return distinct full matches of the active pattern, minus the example.

    Uses ``finditer``/``group(0)`` rather than ``findall`` so results stay whole
    matches even when a user-supplied regex contains capturing groups.
    """
    return {m.group(0) for m in _PATTERN.finditer(text) if m.group(0) != _EXAMPLE}


def extract_passwords_from_response(response) -> set[str]:
    """Extract from the body only; headers are deliberately never inspected."""
    return extract_passwords(response.text)


# Matches are "not always stored the way you'd first expect": some sit in
# UTF-16 image metadata, so a single UTF-8 pass is not enough. Try the encodings
# a server realistically uses for embedded text before giving up.
_BYTE_ENCODINGS = ("utf-8", "utf-16-le", "utf-16-be", "latin-1")


def extract_passwords_from_bytes(data: bytes) -> set[str]:
    """Scan arbitrary response bytes for matches under several text encodings."""
    found: set[str] = set()
    for encoding in _BYTE_ENCODINGS:
        found |= extract_passwords(data.decode(encoding, errors="ignore"))
    return found


# A JavaScript character-code array such as ``[86, 73, 83, ...]`` (fed to
# ``String.fromCharCode``) hides the literal match from a plain regex; so does a
# Base64 blob. Recover both without inventing false positives.
_CHARCODE_ARRAY_RE = re.compile(r"\[\s*(\d{1,3}(?:\s*,\s*\d{1,3}){6,})\s*\]")
_BASE64_TOKEN_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def extract_encoded_passwords(text: str) -> set[str]:
    """Recover matches assembled or obfuscated inside page or script text."""
    found: set[str] = set()
    for match in _CHARCODE_ARRAY_RE.finditer(text):
        try:
            decoded = "".join(chr(int(code)) for code in match.group(1).split(","))
        except ValueError:
            continue
        found |= extract_passwords(decoded)
    for token in _BASE64_TOKEN_RE.findall(text):
        try:
            decoded = base64.b64decode(token, validate=True)
        except (ValueError, binascii.Error):
            continue
        found |= extract_passwords_from_bytes(decoded)
    return found
