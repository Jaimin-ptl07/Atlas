"""Experiment routes must exist only when the flag is enabled."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.session import get_db


def _fresh_app(monkeypatch, enabled: bool):
    from app.db import session as db_session
    from app.main import create_app

    monkeypatch.setenv("ATLAS_EXPERIMENTS_ENABLED", str(enabled).lower())
    get_settings.cache_clear()
    db_session.get_async_engine.cache_clear()
    db_session.get_async_session_factory.cache_clear()
    return create_app()


def _client_for(app, db_session: AsyncSession) -> httpx.AsyncClient:
    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_experiment_routes_absent_when_disabled(monkeypatch, db_session):
    app = _fresh_app(monkeypatch, enabled=False)

    async with _client_for(app, db_session) as client:
        response = await client.get("/experiment/metrics")

    assert response.status_code == 404


async def test_instrumented_read_records_all_timings(monkeypatch, db_session):
    from app.experiments.metrics import attach_instrumentation, experiment_metrics
    from app.models.document import Document

    # The get_db override bypasses get_async_engine(); attach listeners to
    # the engine the fixture session actually uses.
    attach_instrumentation(db_session.bind, experiment_metrics)
    app = _fresh_app(monkeypatch, enabled=True)

    db_session.add(Document(title="T", source="test", content="c"))
    await db_session.commit()
    experiment_metrics.reset()

    async with _client_for(app, db_session) as client:
        read = await client.get("/experiment/read/1")

    assert read.status_code == 200
    assert read.json()["title"] == "T"

    snapshot = experiment_metrics.snapshot()
    assert snapshot["requests"]["count"] == 1
    assert snapshot["timings"]["acquisition_ms"]["count"] == 1
    assert snapshot["timings"]["query_ms"]["count"] >= 1  # SELECT emitted
    assert snapshot["requests"]["latency_ms"]["count"] == 1


async def test_metrics_endpoint_returns_snapshot(monkeypatch, db_session):
    app = _fresh_app(monkeypatch, enabled=True)

    async with _client_for(app, db_session) as client:
        response = await client.get("/experiment/metrics")

    assert response.status_code == 200
    body = response.json()
    assert "requests" in body and "pool" in body and "timings" in body


async def test_reset_endpoint_zeroes_registry(monkeypatch, db_session):
    from app.experiments.metrics import experiment_metrics

    app = _fresh_app(monkeypatch, enabled=True)
    experiment_metrics.observe_request(0.01, ok=True)

    async with _client_for(app, db_session) as client:
        response = await client.post("/experiment/reset")

    assert response.status_code == 200
    assert experiment_metrics.snapshot()["requests"]["count"] == 0
