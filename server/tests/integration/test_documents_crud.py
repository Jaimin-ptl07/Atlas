"""Document CRUD against real PostgreSQL: create, read, list, update, 404."""


def test_create_document_returns_201_with_payload(client):
    response = client.post(
        "/documents",
        json={"title": "Atlas Guide", "source": "manual", "content": "How Atlas works."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["title"] == "Atlas Guide"
    assert body["source"] == "manual"
    assert body["content"] == "How Atlas works."
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


def test_get_document_by_id(client):
    client.post("/documents", json={"title": "Doc A", "source": "api", "content": "aaa"})
    created_id = 1

    response = client.get(f"/documents/{created_id}")

    assert response.status_code == 200
    assert response.json()["title"] == "Doc A"


def test_list_documents_returns_all(client):
    for i in range(3):
        client.post("/documents", json={"title": f"Doc {i}", "source": "api", "content": "c"})

    response = client.get("/documents")

    assert response.status_code == 200
    assert [doc["id"] for doc in response.json()] == [1, 2, 3]


def test_list_documents_pagination(client):
    for i in range(5):
        client.post("/documents", json={"title": f"Doc {i}", "source": "api", "content": "c"})

    response = client.get("/documents", params={"limit": 2, "offset": 3})

    assert response.status_code == 200
    assert [doc["id"] for doc in response.json()] == [4, 5]


def test_update_document_changes_fields(client):
    client.post("/documents", json={"title": "Old", "source": "api", "content": "old body"})

    response = client.put("/documents/1", json={"title": "New", "content": "new body"})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New"
    assert body["content"] == "new body"
    assert body["source"] == "api"  # untouched by partial update
    assert body["updated_at"] >= body["created_at"]


def test_get_nonexistent_document_returns_404(client):
    response = client.get("/documents/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


def test_update_nonexistent_document_returns_404(client):
    response = client.put("/documents/9999", json={"title": "Ghost"})

    assert response.status_code == 404
