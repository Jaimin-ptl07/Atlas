from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job


class JobRepository:
    """Database access for Job entities.

    Receives an AsyncSession; never creates or commits one — transaction
    boundaries belong to the service layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, job: Job) -> Job:
        self._session.add(job)
        await self._session.flush()  # assign server defaults, no commit
        return job

    async def get_by_id(self, job_id: object) -> Job | None:
        return await self._session.get(Job, job_id)
