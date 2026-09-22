"""API contract validation for /jobs — no database required."""


async def test_create_rejects_missing_job_type(api_client):
    response = await api_client.post("/jobs", json={})

    assert response.status_code == 422


async def test_create_rejects_empty_job_type(api_client):
    response = await api_client.post("/jobs", json={"job_type": ""})

    assert response.status_code == 422


async def test_get_rejects_malformed_uuid(api_client):
    response = await api_client.get("/jobs/not-a-uuid")

    assert response.status_code == 422
