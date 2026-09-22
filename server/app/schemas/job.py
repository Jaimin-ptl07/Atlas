from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus


class CreateJobRequest(BaseModel):
    """Payload for POST /jobs — deliberately just a type for now."""

    job_type: str = Field(min_length=1, max_length=100)


class JobResponse(BaseModel):
    """API representation of a Job — the polling contract."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_type: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
