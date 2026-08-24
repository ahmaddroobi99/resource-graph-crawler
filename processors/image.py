"""Optional image processing: a cheap byte scan plus OCR when available.

The core crawler works without OCR. When Pillow, pytesseract, and a Tesseract
engine are all present, this module additionally reads passwords that are only
rendered as pixels (e.g. a scanned whiteboard).
"""

import os
import shutil

from config import COMPILED_PASSWORD_RE
from crawler.extractor import extract_passwords, extract_passwords_from_bytes

try:
    from io import BytesIO

    import pytesseract
    from PIL import Image
except ImportError:  # OCR is intentionally optional.
    HAS_OCR = False
else:
    HAS_OCR = True


def _locate_tesseract() -> bool:
    """Point pytesseract at a Tesseract binary; return whether one was found."""
    if not HAS_OCR:
        return False
    if shutil.which("tesseract"):
        return True
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return True
    return False


_TESSERACT_READY = _locate_tesseract()

# Constrain OCR to the exact password alphabet so lookalikes (l/1, o/0) cannot
# turn a valid hex password into a rejected non-hex string. --psm 7 treats the
# image as a single text line.
_OCR_CONFIG = "--psm 7 -c tessedit_char_whitelist=VISUALPING{}0123456789abcdefABCDEF"


def process_image(url: str, content: bytes) -> set[str]:
    """Scan image bytes for embedded text, then OCR the pixels when possible."""
    passwords = extract_passwords_from_bytes(content)
    if passwords or not _TESSERACT_READY:
        return passwords
    try:
        text = pytesseract.image_to_string(Image.open(BytesIO(content)), config=_OCR_CONFIG)
    except Exception:  # A missing engine or unreadable image must not crash the crawl.
        return set()
    if not COMPILED_PASSWORD_RE.search(text):
        # Retry once at 2x scale, which helps Tesseract on small renderings.
        try:
            image = Image.open(BytesIO(content)).convert("L")
            image = image.resize((image.width * 2, image.height * 2))
            text += "\n" + pytesseract.image_to_string(image, config=_OCR_CONFIG)
        except Exception:
            pass
    return extract_passwords(text)
