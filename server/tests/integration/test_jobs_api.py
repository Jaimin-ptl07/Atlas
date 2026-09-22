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


async def test_idempotent_replay_returns_same_job(client):
    headers = {"Idempotency-Key": "abc123"}
    first = await client.post("/jobs", json={"job_type": "document.ingest"}, headers=headers)

    second = await client.post("/jobs", json={"job_type": "document.ingest"}, headers=headers)

    assert first.status_code == 201  # created
    assert second.status_code == 200  # replayed
    assert second.json() == first.json()  # same job, byte-for-byte


async def test_keyless_posts_create_distinct_jobs(client):
    first = await client.post("/jobs", json={"job_type": "document.ingest"})
    second = await client.post("/jobs", json={"job_type": "document.ingest"})

    assert first.status_code == 201
    assert second.status_code == 201  # NULL keys never collide
    assert first.json()["id"] != second.json()["id"]


async def test_concurrent_same_key_creates_exactly_one_job(pg_engine, db_session):
    """The race that matters: two simultaneous retries, one job.

    Uses a production-like get_db override (fresh session per request) so
    the two inserts genuinely contend on the unique index.
    """
    import asyncio

    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.session import get_db
    from app.main import app

    factory = async_sessionmaker(bind=pg_engine, expire_on_commit=False)

    async def _override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Idempotency-Key": "race-1"}
            payload = {"job_type": "document.ingest"}
            first, second = await asyncio.gather(
                client.post("/jobs", json=payload, headers=headers),
                client.post("/jobs", json=payload, headers=headers),
            )
    finally:
        app.dependency_overrides.clear()

    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 201]  # one winner, one replay — never two creates

    assert first.json()["id"] == second.json()["id"]

    from sqlalchemy import text

    count = (await db_session.execute(text("SELECT count(*) FROM jobs"))).scalar_one()
    assert count == 1
