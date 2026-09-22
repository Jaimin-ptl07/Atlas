"""Job lifecycle API — the public seam for Atlas' async processing foundation.

Slice 1: POST /jobs persists a job and returns it as it will be polled.
"""

from uuid import UUID


async def test_create_job_returns_201_queued_with_uuid(client):
    response = await client.post("/jobs", json={"job_type": "document.ingest"})

    assert response.status_code == 201
    body = response.json()
    assert body["job_type"] == "document.ingest"
    assert body["status"] == "queued"
    UUID(body["id"])  # parseable UUID, not an integer sequence
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


async def test_get_job_round_trips_state(client):
    created = (await client.post("/jobs", json={"job_type": "document.ocr"})).json()

    response = await client.get(f"/jobs/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created  # nothing happens yet: state is stable


async def test_get_unknown_job_returns_404(client):
    from uuid import uuid4

    response = await client.get(f"/jobs/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


async def test_status_check_constraint_rejects_invalid_value(db_session):
    """The DB itself enforces status validity — the reason for native_enum=False."""
    import pytest
    from sqlalchemy.exc import DBAPIError

    from app.models.job import Job

    db_session.add(Job(job_type="t", status="bogus"))  # type: ignore[arg-type]
    with pytest.raises(DBAPIError):
        await db_session.flush()
    await db_session.rollback()
