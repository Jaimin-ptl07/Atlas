from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.document import DocumentRepository
from app.schemas.document import DocumentCreate, DocumentUpdate


class DocumentService:
    """Application-level operations on documents.

    Owns the transaction boundary: commit on success; on failure the
    session dependency (get_db) rolls back and the error propagates.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = DocumentRepository(session)

    def create_document(self, data: DocumentCreate) -> Document:
        document = Document(title=data.title, source=data.source, content=data.content)
        self._repository.add(document)
        self._session.commit()  # transaction boundary
        self._session.refresh(document)  # reload server-generated columns
        return document

    def get_document(self, document_id: int) -> Document | None:
        return self._repository.get_by_id(document_id)

    def list_documents(self, limit: int = 100, offset: int = 0) -> Sequence[Document]:
        return self._repository.list(limit=limit, offset=offset)

    def update_document(self, document_id: int, data: DocumentUpdate) -> Document | None:
        document = self._repository.get_by_id(document_id)
        if document is None:
            return None

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(document, field, value)

        self._repository.flush()
        self._session.commit()  # transaction boundary
        self._session.refresh(document)
        return document
