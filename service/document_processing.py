"""Document validation, computer-vision preprocessing, and structured OCR."""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

import cv2
import fitz
import numpy as np
from PIL import Image, UnidentifiedImageError

from config import DOCUMENT_MAX_OCR_SECONDS, DOCUMENT_MAX_PAGES, DOCUMENT_MAX_PIXELS


class DocumentInputError(ValueError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class OCRUnavailable(RuntimeError):
    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def detect_media_type(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise DocumentInputError("UNSUPPORTED_FILE_TYPE", "Only PDF, PNG, and JPEG files are supported.", 415)


def validate_document(content: bytes) -> tuple[str, int | None]:
    """Validate actual file signatures and parseability, ignoring client MIME claims."""
    if not content:
        raise DocumentInputError("EMPTY_FILE", "The uploaded file is empty.", 400)
    media_type = detect_media_type(content)
    if media_type == "application/pdf":
        try:
            with fitz.open(stream=content, filetype="pdf") as pdf:
                page_count = pdf.page_count
                if pdf.is_encrypted or page_count == 0:
                    raise ValueError("PDF is encrypted or contains no pages.")
                if page_count > DOCUMENT_MAX_PAGES:
                    raise DocumentInputError(
                        "FILE_TOO_LARGE", "The PDF exceeds the configured page limit.", 413
                    )
                for page in pdf:
                    width = int(page.rect.width * 2)
                    height = int(page.rect.height * 2)
                    if width < 1 or height < 1 or width * height > DOCUMENT_MAX_PIXELS:
                        raise DocumentInputError(
                            "FILE_TOO_LARGE", "A PDF page exceeds the configured pixel limit.", 413
                        )
        except DocumentInputError:
            raise
        except Exception:
            raise DocumentInputError("CORRUPTED_DOCUMENT", "The PDF could not be opened.", 422) from None
        return media_type, page_count

    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            if width < 1 or height < 1 or width * height > DOCUMENT_MAX_PIXELS:
                raise DocumentInputError(
                    "FILE_TOO_LARGE", "The image exceeds the configured pixel limit.", 413
                )
    except DocumentInputError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise DocumentInputError("CORRUPTED_DOCUMENT", "The image could not be opened.", 422) from None
    return media_type, 1


def safe_filename(filename: str | None) -> str:
    candidate = (filename or "upload").replace("\\", "/").split("/")[-1]
    candidate = "".join(char for char in candidate if char.isprintable() and char not in "\r\n\0")
    return candidate[:255] or "upload"


def iter_document_pages(content: bytes, media_type: str) -> Iterator[tuple[int, Image.Image]]:
    if media_type == "application/pdf":
        with fitz.open(stream=content, filetype="pdf") as pdf:
            for index, page in enumerate(pdf, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
                yield index, image
    else:
        with Image.open(io.BytesIO(content)) as image:
            yield 1, image.convert("RGB")


def preprocess_image(image: Image.Image) -> Image.Image:
    """Denoise, normalize contrast, deskew, and bound OCR image dimensions."""
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    largest_edge = max(width, height)
    scale = min(2.0 if largest_edge < 1200 else 1.0, 3000.0 / largest_edge)
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.medianBlur(gray, 3)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

    threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coordinates = np.column_stack(np.where(threshold > 0))
    if len(coordinates) > 20:
        angle = cv2.minAreaRect(coordinates)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if 0.15 < abs(angle) < 12:
            center = (gray.shape[1] / 2, gray.shape[0] / 2)
            matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            gray = cv2.warpAffine(gray, matrix, (gray.shape[1], gray.shape[0]),
                                  flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(gray)


def ocr_page(
    image: Image.Image, document_id: str, page_number: int, preprocessed: bool = False
) -> dict[str, Any]:
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise OCRUnavailable("OCR engine bindings are unavailable.") from exc

    prepared = image if preprocessed else preprocess_image(image)
    try:
        data = pytesseract.image_to_data(
            prepared, output_type=Output.DICT, config="--psm 3",
            timeout=DOCUMENT_MAX_OCR_SECONDS,
        )
    except Exception as exc:
        retryable = "timeout" in str(exc).casefold() or "timed out" in str(exc).casefold()
        raise OCRUnavailable("OCR could not process this page.", retryable=retryable) from exc

    lines: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, value in enumerate(data.get("text", [])):
        if str(value).strip():
            lines[(str(data["block_num"][index]), str(data["par_num"][index]),
                   str(data["line_num"][index]))].append(index)

    blocks = []
    for line_key, indexes in lines.items():
        words = [str(data["text"][index]).strip() for index in indexes]
        text = " ".join(word for word in words if word)
        if not text:
            continue
        left = min(int(data["left"][index]) for index in indexes)
        top = min(int(data["top"][index]) for index in indexes)
        right = max(int(data["left"][index]) + int(data["width"][index]) for index in indexes)
        bottom = max(int(data["top"][index]) + int(data["height"][index]) for index in indexes)
        confidences = []
        for index in indexes:
            try:
                confidence = float(data["conf"][index])
                if confidence >= 0:
                    confidences.append(confidence / 100.0)
            except (ValueError, TypeError):
                continue
        stable_key = f"{document_id}:{page_number}:{line_key}:{text}"
        block_id = "blk_" + hashlib.sha256(stable_key.encode()).hexdigest()[:24]
        blocks.append({
            "id": block_id,
            "text": text,
            "bbox": {"x": max(0, left), "y": max(0, top),
                     "width": max(0, right - left), "height": max(0, bottom - top)},
            "confidence": sum(confidences) / len(confidences) if confidences else None,
        })
    return {"blocks": blocks, "text": "\n".join(block["text"] for block in blocks),
            "width": prepared.width, "height": prepared.height}


_ENTITY_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "URL": re.compile(r"\b(?:https?://|www\.)[A-Z0-9.-]+(?:/[^\s<>]*)?", re.I),
    "DATE": re.compile(
        r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{4})\b", re.I),
}
_SKILLS = (
    "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "SQL", "HTML", "CSS",
    "React", "Node.js", "Django", "Flask", "FastAPI", "AWS", "Azure", "GCP",
    "Docker", "Kubernetes", "Git", "Linux", "Pandas", "NumPy", "PyTorch", "TensorFlow",
    "Machine Learning", "Data Analysis", "Project Management", "Communication",
)
_ORG_RE = re.compile(
    r"\b(?:at|company|employer|organization)\s*[:,-]?\s*([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4})",
    re.I,
)
_LOCATION_RE = re.compile(
    r"\b(?:location|based in|address)\s*[:,-]?\s*([A-Z][\w.'-]*(?:[ ,]+[A-Z][\w.'-]*){0,4})",
    re.I,
)


def extract_entities(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract conservative rule-based entities with exact OCR-block evidence."""
    entities: dict[tuple[str, str, int], dict[str, Any]] = {}
    first_name_candidate = True
    for page in pages:
        page_number = page["page"]
        for block in page.get("blocks", []):
            text = block["text"]
            evidence = {"page": page_number, "text": text, "bbox": block.get("bbox")}

            def add(entity_type: str, value: str) -> None:
                cleaned = value.strip(" \t.,;:")
                if not cleaned:
                    return
                key = (entity_type, cleaned.casefold(), page_number)
                stable_key = f"{entity_type}:{cleaned.casefold()}:{page_number}:{block.get('id', text)}"
                entities.setdefault(key, {
                    "id": "ent_" + hashlib.sha256(stable_key.encode()).hexdigest()[:24],
                    "text": cleaned, "type": entity_type, "confidence": None,
                    "evidence": evidence,
                })

            for entity_type in ("EMAIL", "URL", "DATE"):
                for match in _ENTITY_PATTERNS[entity_type].finditer(text):
                    add(entity_type, match.group(0))
            for skill in _SKILLS:
                if re.search(rf"(?<!\w){re.escape(skill)}(?!\w)", text, re.I):
                    add("SKILL", skill)
            for match in _ORG_RE.finditer(text):
                add("ORGANIZATION", match.group(1))
            for match in _LOCATION_RE.finditer(text):
                add("LOCATION", match.group(1))

            # Resume headings often put the candidate's name on the first text line.
            name_heading = re.split(r"[|•·]", text, maxsplit=1)[0].strip()
            name = re.fullmatch(
                r"([A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?(?:\s+[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?){1,3})",
                name_heading,
                re.I,
            )
            if first_name_candidate and name and not any(char.isdigit() for char in name_heading):
                add("PERSON", name.group(1))
                first_name_candidate = False
            elif text.strip() and not text.strip().lower().startswith(("resume", "curriculum vitae")):
                first_name_candidate = False
    return list(entities.values())


def file_fingerprint(content: bytes, filename: str, metadata: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(content)
    digest.update(b"\0")
    digest.update(Path(filename).name.encode("utf-8", errors="replace"))
    digest.update(b"\0")
    digest.update(json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False).encode("utf-8", errors="replace"))
    return digest.hexdigest()