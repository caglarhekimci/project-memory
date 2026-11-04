"""Exercise actual SQLite, cookies and HTTP routes; no mocked application services."""

import pytest
from fastapi.testclient import TestClient

from project_memory.settings import Settings
from project_memory.web.app import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        demo_mode=True,
        model_backend="extractive",
        origin="http://testserver",
    )
    with TestClient(create_app(settings)) as client:
        yield client


def login(client):
    result = client.post(
        "/api/login",
        json={"password": "project-memory-demo"},
        headers={"Origin": "http://testserver"},
    )
    assert result.status_code == 200


def test_private_api_requires_owner_session(client):
    assert client.get("/api/projects").status_code == 401
    assert client.get("/healthz").status_code == 200


def test_login_requires_same_origin_and_revocation_is_immediate(client):
    assert (
        client.post(
            "/api/login",
            json={"password": "project-memory-demo"},
            headers={"Origin": "https://evil.test"},
        ).status_code
        == 403
    )
    login(client)
    cookie = client.cookies.get("pm_session")
    assert (
        "HttpOnly"
        in client.post(
            "/api/login",
            json={"password": "project-memory-demo"},
            headers={"Origin": "http://testserver"},
        ).headers["set-cookie"]
    )
    assert client.get("/api/projects").status_code == 200
    client.post("/api/logout", headers={"Origin": "http://testserver"})
    client.cookies.set("pm_session", cookie)
    assert client.get("/api/projects").status_code == 401


def test_full_note_search_answer_feedback_and_delete_flow(client):
    login(client)
    headers = {"Origin": "http://testserver"}
    response = client.post(
        "/api/projects",
        json={"name": "Kişisel", "repository": "", "workflows": []},
        headers=headers,
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    created = client.post(
        f"/api/projects/{project_id}/notes",
        json={"title": "Atlas kararı", "body": "Atlas verileri Ankara bölgesinde tutulur."},
        headers=headers,
    )
    assert created.status_code == 201
    source_id = created.json()["source_id"]
    answer = client.post(
        f"/api/projects/{project_id}/answer",
        json={"question": "Atlas verileri nerede tutulur?"},
        headers=headers,
    )
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["mode"] == "extractive"
    assert "Ankara" in payload["claims"][0]["text"]
    assert payload["claims"][0]["citations"][0] == payload["evidence"][0]["chunk"]["id"]
    assert (
        client.post(
            f"/api/projects/{project_id}/feedback",
            json={"answer_id": payload["id"], "vote": 1},
            headers=headers,
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/projects/{project_id}/sources/{source_id}", headers=headers
        ).status_code
        == 204
    )
    assert client.get(f"/api/projects/{project_id}/sources").json() == []


def test_note_update_removes_stale_answer_evidence(client):
    login(client)
    headers = {"Origin": "http://testserver"}
    project_id = client.get("/api/projects").json()[0]["id"]
    saved = client.post(
        f"/api/projects/{project_id}/notes",
        json={"title": "Bölge", "body": "Kutup istasyonu İzmir."},
        headers=headers,
    ).json()
    result = client.put(
        f"/api/projects/{project_id}/notes/{saved['source_id']}",
        json={"title": "Bölge", "body": "Kutup istasyonu Ankara."},
        headers=headers,
    )
    assert result.status_code == 200
    answer = client.post(
        f"/api/projects/{project_id}/answer", json={"question": "Kutup istasyonu"}, headers=headers
    ).json()
    assert "Ankara" in answer["claims"][0]["text"]
    assert all("İzmir" not in e["chunk"]["text"] for e in answer["evidence"])


def test_oversized_body_and_cross_site_mutation_are_rejected(client):
    login(client)
    assert (
        client.post(
            "/api/projects", json={"name": "Injected"}, headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/projects",
            content=b"x" * 300_000,
            headers={"Origin": "http://testserver", "Content-Type": "application/json"},
        ).status_code
        == 413
    )


def test_bad_repository_cannot_be_used_to_access_arbitrary_urls(client):
    login(client)
    result = client.post(
        "/api/projects",
        json={"name": "Bad", "repository": "http://169.254.169.254/metadata"},
        headers={"Origin": "http://testserver"},
    )
    assert result.status_code == 422


def test_unknown_project_and_empty_question_fail_explicitly(client):
    login(client)
    assert client.get("/api/projects/missing/sources").status_code == 404
    project_id = client.get("/api/projects").json()[0]["id"]
    assert (
        client.post(
            f"/api/projects/{project_id}/answer",
            json={"question": ""},
            headers={"Origin": "http://testserver"},
        ).status_code
        == 422
    )


def test_security_headers_and_explicit_demo_metadata(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]
    login(client)
    assert client.get("/api/meta").json()["demo_mode"] is True


def test_live_mode_refuses_missing_or_demo_password(tmp_path):
    for password in ["", "short", "project-memory-demo"]:
        with pytest.raises(ValueError):
            Settings(
                database_url=f"sqlite:///{tmp_path / 'x.db'}",
                demo_mode=False,
                app_password=password,
            )


def test_repeated_bad_logins_are_throttled(client):
    headers = {"Origin": "http://testserver"}
    for _ in range(5):
        assert (
            client.post("/api/login", json={"password": "wrong"}, headers=headers).status_code
            == 401
        )
    assert client.post("/api/login", json={"password": "wrong"}, headers=headers).status_code == 429
