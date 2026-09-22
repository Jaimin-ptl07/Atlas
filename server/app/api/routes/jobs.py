from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.job import CreateJobRequest, JobResponse
from app.services.job import JobService

router = APIRouter(prefix="/jobs", tags=["Jobs"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def get_job_service(session: SessionDep) -> JobService:
    return JobService(session)


ServiceDep = Annotated[JobService, Depends(get_job_service)]


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: CreateJobRequest, service: ServiceDep, idempotency_key: IdempotencyKey = None
) -> Response:
    """201 Created: the resource exists and nothing more will happen.

    A replayed Idempotency-Key returns 200 with the original job — same
    resource, not a duplicate. Both codes become 202-accepted semantics
    when the queue milestone lands.
    """
    job, created = await service.create_job(payload, idempotency_key)
    body = JobResponse.model_validate(job).model_dump(mode="json")
    if not created:
        return JSONResponse(status_code=status.HTTP_200_OK, content=body)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, service: ServiceDep) -> JobResponse:
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobResponse.model_validate(job)
