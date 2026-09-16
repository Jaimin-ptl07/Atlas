from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    """Database access for Document entities.

    Receives an AsyncSession; never creates or commits one. Transaction
    boundaries (commit/rollback) belong to the service layer — this is
    what will let us experiment with isolation and locking later.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: Document) -> Document:
        self._session.add(document)
        await self._session.flush()  # assign id / server defaults, no commit
        return document

    async def get_by_id(self, document_id: int) -> Document | None:
        return await self._session.get(Document, document_id)

    async def list(self, limit: int = 100, offset: int = 0) -> Sequence[Document]:
        statement = select(Document).order_by(Document.id).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def flush(self) -> None:
        """Push pending changes to the DB inside the current transaction."""
        await self._session.flush()
