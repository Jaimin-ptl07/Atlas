from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.repositories.job import JobRepository
from app.schemas.job import CreateJobRequest


class JobService:
    """Application-level operations on jobs.

    Owns the transaction boundary. Creation is deliberately tiny: one
    INSERT inside a short transaction, commit, refresh, release the
    connection — the request never waits on processing work.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = JobRepository(session)

    async def create_job(self, request: CreateJobRequest) -> Job:
        job = Job(job_type=request.job_type)  # status defaults to QUEUED
        await self._repository.add(job)
        await self._session.commit()  # transaction boundary
        await self._session.refresh(job)  # reload server-generated columns
        return job

    async def get_job(self, job_id: object) -> Job | None:
        return await self._repository.get_by_id(job_id)
