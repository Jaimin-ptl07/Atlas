"""API contract validation for /documents — no database required."""


async def test_create_rejects_empty_title(api_client):
    response = await api_client.post(
        "/documents", json={"title": "", "source": "api", "content": "x"}
    )

    assert response.status_code == 422


async def test_create_rejects_missing_fields(api_client):
    response = await api_client.post("/documents", json={"title": "only-title"})

    assert response.status_code == 422


async def test_create_rejects_overlong_title(api_client):
    response = await api_client.post(
        "/documents", json={"title": "x" * 513, "source": "api", "content": "x"}
    )

    assert response.status_code == 422


async def test_list_rejects_invalid_pagination(api_client):
    response = await api_client.get("/documents", params={"limit": 0})

    assert response.status_code == 422
