"""Serve the small browser UI for local document processing."""

from pathlib import Path


def document_html() -> str:
    template = Path(__file__).parent / "templates" / "documents.html"
    return template.read_text(encoding="utf-8")