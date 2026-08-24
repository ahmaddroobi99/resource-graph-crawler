"""Password extraction from response bodies and binary payloads."""

from config import COMPILED_PASSWORD_RE, EXAMPLE_PASSWORD


def extract_passwords(text: str) -> set[str]:
    """Return exact non-example password matches from text."""
    return {match for match in COMPILED_PASSWORD_RE.findall(text) if match != EXAMPLE_PASSWORD}


def extract_passwords_from_response(response) -> set[str]:
    """Extract from the body only; headers are deliberately never inspected."""
    return extract_passwords(response.text)


def extract_passwords_from_bytes(data: bytes) -> set[str]:
    """Perform a cheap ASCII-compatible scan of arbitrary response bytes."""
    return extract_passwords(data.decode("utf-8", errors="ignore"))
