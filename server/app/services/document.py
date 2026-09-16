from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.repositories.document import DocumentRepository
from app.schemas.document import DocumentCreate, DocumentUpdate


class DocumentService:
    """Application-level operations on documents.

    Owns the transaction boundary: commit on success; on failure the
    session dependency (get_db) rolls back and the error propagates.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = DocumentRepository(session)

    async def create_document(self, data: DocumentCreate) -> Document:
        document = Document(title=data.title, source=data.source, content=data.content)
        await self._repository.add(document)
        await self._session.commit()  # transaction boundary
        await self._session.refresh(document)  # reload server-generated columns
        return document

    async def get_document(self, document_id: int) -> Document | None:
        return await self._repository.get_by_id(document_id)

    async def list_documents(self, limit: int = 100, offset: int = 0) -> Sequence[Document]:
        return await self._repository.list(limit=limit, offset=offset)

    async def update_document(self, document_id: int, data: DocumentUpdate) -> Document | None:
        document = await self._repository.get_by_id(document_id)
        if document is None:
            return None

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(document, field, value)

        await self._repository.flush()
        await self._session.commit()  # transaction boundary
        await self._session.refresh(document)
        return document
