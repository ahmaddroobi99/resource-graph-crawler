"""Optional image processing with a cheap byte scan and optional OCR."""

from crawler.extractor import extract_passwords_from_bytes, extract_passwords

try:
    from io import BytesIO
    from PIL import Image
    import pytesseract
except ImportError:  # OCR is intentionally optional.
    HAS_OCR = False
else:
    HAS_OCR = True


def process_image(url: str, content: bytes) -> set[str]:
    """Extract embedded text, then use OCR when optional dependencies exist."""
    passwords = extract_passwords_from_bytes(content)
    if passwords or not HAS_OCR:
        return passwords
    try:
        text = pytesseract.image_to_string(Image.open(BytesIO(content)))
    except Exception:
        return set()
    return extract_passwords(text)
