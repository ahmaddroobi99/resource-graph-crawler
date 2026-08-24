"""Password extraction from response bodies and binary payloads."""

import base64
import binascii
import re

from config import COMPILED_PASSWORD_RE, EXAMPLE_PASSWORD


def extract_passwords(text: str) -> set[str]:
    """Return exact non-example password matches from text."""
    return {match for match in COMPILED_PASSWORD_RE.findall(text) if match != EXAMPLE_PASSWORD}


def extract_passwords_from_response(response) -> set[str]:
    """Extract from the body only; headers are deliberately never inspected."""
    return extract_passwords(response.text)


# Passwords are "not always stored the way you'd first expect": some sit in
# UTF-16 image metadata, so a single UTF-8 pass is not enough. Try the encodings
# a server realistically uses for embedded text before giving up.
_BYTE_ENCODINGS = ("utf-8", "utf-16-le", "utf-16-be", "latin-1")


def extract_passwords_from_bytes(data: bytes) -> set[str]:
    """Scan arbitrary response bytes for passwords under several text encodings."""
    found: set[str] = set()
    for encoding in _BYTE_ENCODINGS:
        found |= extract_passwords(data.decode(encoding, errors="ignore"))
    return found


# A JavaScript character-code array such as ``[86, 73, 83, ...]`` (fed to
# ``String.fromCharCode``) hides the literal password from a plain regex; so does
# a Base64 blob. Recover both without inventing false positives.
_CHARCODE_ARRAY_RE = re.compile(r"\[\s*(\d{1,3}(?:\s*,\s*\d{1,3}){6,})\s*\]")
_BASE64_TOKEN_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def extract_encoded_passwords(text: str) -> set[str]:
    """Recover passwords assembled or obfuscated inside page or script text."""
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
