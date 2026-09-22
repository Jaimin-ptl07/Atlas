from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.repositories.job import JobRepository
from app.schemas.job import CreateJobRequest

UNIQUE_VIOLATION = "23505"


def _sqlstate(error: IntegrityError) -> str:
    orig = getattr(error, "orig", None)
    return getattr(orig, "sqlstate", "") or ""


class JobService:
    """Application-level operations on jobs.

    Owns the transaction boundary. Creation is deliberately tiny: one
    INSERT inside a short transaction, commit, refresh, release the
    connection — the request never waits on processing work.

    Idempotency: a retried create with the same Idempotency-Key hits the
    unique index (the loser's INSERT blocks until the winner commits,
    then fails 23505), rolls back, and returns the winner's job.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = JobRepository(session)

    async def create_job(
        self, request: CreateJobRequest, idempotency_key: str | None = None
    ) -> tuple[Job, bool]:
        """Returns (job, created) — created is False on idempotent replay."""
        job = Job(job_type=request.job_type, idempotency_key=idempotency_key)
        try:
            await self._repository.add(job)
            await self._session.commit()  # transaction boundary
        except IntegrityError as exc:
            if idempotency_key is None or _sqlstate(exc) != UNIQUE_VIOLATION:
                raise  # a different integrity problem — not ours to absorb
            await self._session.rollback()  # clear the failed transaction
            existing = await self._repository.get_by_idempotency_key(idempotency_key)
            if existing is None:  # pragma: no cover - defensive
                raise
            return existing, False
        await self._session.refresh(job)  # reload server-generated columns
        return job, True

    async def get_job(self, job_id: object) -> Job | None:
        return await self._repository.get_by_id(job_id)
