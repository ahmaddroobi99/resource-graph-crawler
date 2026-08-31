"""Vercel Python entrypoint. Re-exports the FastAPI application."""

from service.app import app

__all__ = ["app"]
