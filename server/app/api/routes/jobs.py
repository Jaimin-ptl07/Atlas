from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.job import CreateJobRequest, JobResponse
from app.services.job import JobService

router = APIRouter(prefix="/jobs", tags=["Jobs"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_job_service(session: SessionDep) -> JobService:
    return JobService(session)


ServiceDep = Annotated[JobService, Depends(get_job_service)]


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(payload: CreateJobRequest, service: ServiceDep) -> JobResponse:
    """201 Created for now: the resource exists and nothing more will happen.

    This becomes 202 Accepted when the queue milestone lands — "accepted
    for later processing" — at which point the contract discussion (and
    the docs) change with it.
    """
    job = await service.create_job(payload)
    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, service: ServiceDep) -> JobResponse:
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobResponse.model_validate(job)
