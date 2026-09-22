import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Text, Uuid, func
from sqlalchemy import Enum as SaEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobStatus(str, Enum):
    """Job lifecycle states. v1 only ever writes QUEUED — the others exist
    so the API contract is stable when the worker milestone lands."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    """A unit of asynchronous work, persisted before anything processes it.

    v1 columns only (id, job_type, status, timestamps) — payload/result/
    error arrive with the milestones that need them.
    """

    __tablename__ = "jobs"

    # UUID (client-generated): externally visible ids must not be enumerable,
    # and idempotency keys will map onto this shape later.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)

    # native_enum=False + create_constraint=True -> VARCHAR + CHECK
    # constraint: database-level status validity without PostgreSQL native
    # ENUM's ALTER TYPE pain when the state machine evolves. (create_constraint
    # defaults to False since SQLAlchemy 1.4 — without it there is NO check.)
    # Stored as lowercase values ("queued").
    status: Mapped[JobStatus] = mapped_column(
        SaEnum(
            JobStatus,
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda e: [member.value for member in e],
        ),
        default=JobStatus.QUEUED,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
