"""Importing this package registers all ORM models on Base.metadata."""

from app.models.document import Document

__all__ = ["Document"]
