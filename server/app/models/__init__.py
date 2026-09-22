"""Importing this package registers all ORM models on Base.metadata."""

from app.models.document import Document
from app.models.job import Job

__all__ = ["Document", "Job"]
