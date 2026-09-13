"""API contract validation for /documents — no database required."""

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from app.main import app

    return TestClient(app)


def test_create_rejects_empty_title():
    response = _client().post("/documents", json={"title": "", "source": "api", "content": "x"})

    assert response.status_code == 422


def test_create_rejects_missing_fields():
    response = _client().post("/documents", json={"title": "only-title"})

    assert response.status_code == 422


def test_create_rejects_overlong_title():
    response = _client().post(
        "/documents", json={"title": "x" * 513, "source": "api", "content": "x"}
    )

    assert response.status_code == 422


def test_list_rejects_invalid_pagination():
    response = _client().get("/documents", params={"limit": 0})

    assert response.status_code == 422
