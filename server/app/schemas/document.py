from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """Payload for POST /documents."""

    title: str = Field(min_length=1, max_length=512)
    source: str = Field(min_length=1, max_length=255)
    content: str


class DocumentUpdate(BaseModel):
    """Payload for PUT /documents/{id} — partial, only set fields are applied."""

    title: str | None = Field(default=None, min_length=1, max_length=512)
    source: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = None


class DocumentResponse(BaseModel):
    """API representation of a Document — never leaks SQLAlchemy internals."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source: str
    content: str
    created_at: datetime
    updated_at: datetime
