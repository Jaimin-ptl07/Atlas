from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import DocumentCreate, DocumentResponse, DocumentUpdate
from app.services.document import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])

SessionDep = Annotated[Session, Depends(get_db)]


def get_document_service(session: SessionDep) -> DocumentService:
    return DocumentService(session)


ServiceDep = Annotated[DocumentService, Depends(get_document_service)]


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(payload: DocumentCreate, service: ServiceDep) -> DocumentResponse:
    """Sync handler on purpose: with a sync engine, FastAPI's threadpool keeps this correct."""
    document = service.create_document(payload)
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentResponse]:
    documents = service.list_documents(limit=limit, offset=offset)
    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, service: ServiceDep) -> DocumentResponse:
    document = service.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(document)


@router.put("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: int, payload: DocumentUpdate, service: ServiceDep
) -> DocumentResponse:
    document = service.update_document(document_id, payload)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(document)
