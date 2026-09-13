from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    """Database access for Document entities.

    Receives a Session; never creates or commits one. Transaction
    boundaries (commit/rollback) belong to the service layer — this is
    what will let us experiment with isolation and locking later.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, document: Document) -> Document:
        self._session.add(document)
        self._session.flush()  # assign id / server defaults, no commit
        return document

    def get_by_id(self, document_id: int) -> Document | None:
        return self._session.get(Document, document_id)

    def list(self, limit: int = 100, offset: int = 0) -> Sequence[Document]:
        statement = select(Document).order_by(Document.id).limit(limit).offset(offset)
        return self._session.scalars(statement).all()

    def flush(self) -> None:
        """Push pending changes to the DB inside the current transaction."""
        self._session.flush()
