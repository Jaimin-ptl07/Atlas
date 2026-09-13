"""Experiment routes must exist only when the flag is enabled."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.session import get_db


def _fresh_app(monkeypatch, enabled: bool) -> FastAPI:
    from app.main import create_app

    monkeypatch.setenv("ATLAS_EXPERIMENTS_ENABLED", str(enabled).lower())
    get_settings.cache_clear()
    get_engine = __import__(
        "app.db.session", fromlist=["get_engine"]
    ).get_engine
    get_engine.cache_clear()
    app = create_app()
    app.dependency_overrides.clear()
    return app


def _client_with_session(app: FastAPI, db_session: Session) -> TestClient:
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def test_experiment_routes_absent_when_disabled(monkeypatch, db_session):
    app = _fresh_app(monkeypatch, enabled=False)

    response = _client_with_session(app, db_session).get("/experiment/metrics")

    assert response.status_code == 404


def test_instrumented_read_records_all_timings(monkeypatch, db_session):
    from app.experiments.metrics import attach_instrumentation, experiment_metrics
    from app.models.document import Document

    # The get_db override bypasses get_engine(); attach listeners to the
    # engine the fixture session actually uses.
    attach_instrumentation(db_session.get_bind(), experiment_metrics)
    app = _fresh_app(monkeypatch, enabled=True)
    db_session.add(Document(title="T", source="test", content="c"))
    db_session.commit()
    experiment_metrics.reset()

    client = _client_with_session(app, db_session)
    read = client.get("/experiment/read/1")

    assert read.status_code == 200
    assert read.json()["title"] == "T"

    snapshot = experiment_metrics.snapshot()
    assert snapshot["requests"]["count"] == 1
    assert snapshot["timings"]["acquisition_ms"]["count"] == 1
    assert snapshot["timings"]["query_ms"]["count"] >= 1  # SELECT emitted
    assert snapshot["requests"]["latency_ms"]["count"] == 1


def test_metrics_endpoint_returns_snapshot(monkeypatch, db_session):
    app = _fresh_app(monkeypatch, enabled=True)

    response = _client_with_session(app, db_session).get("/experiment/metrics")

    assert response.status_code == 200
    body = response.json()
    assert "requests" in body and "pool" in body and "timings" in body


def test_reset_endpoint_zeroes_registry(monkeypatch, db_session):
    from app.experiments.metrics import experiment_metrics

    app = _fresh_app(monkeypatch, enabled=True)
    experiment_metrics.observe_request(0.01, ok=True)

    response = _client_with_session(app, db_session).post("/experiment/reset")

    assert response.status_code == 200
    assert experiment_metrics.snapshot()["requests"]["count"] == 0
