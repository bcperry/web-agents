"""Tests for FastAPI API endpoints."""

import os
import pytest

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("AZURE_SQL_CONNECTIONSTRING", "")

from fastapi.testclient import TestClient
from main import _sessions, app


@pytest.fixture
def client():
    _sessions.clear()
    with TestClient(app) as test_client:
        yield test_client
    _sessions.clear()


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


def test_auth_config_branding_defaults(client, monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_TAGLINE", raising=False)

    resp = client.get("/api/auth/config")

    assert resp.status_code == 200
    data = resp.json()
    assert data["appName"] == "Web-Agents"
    assert data["appTagline"] == "AI Agent Framework"


def test_auth_config_branding_overrides(client, monkeypatch):
    monkeypatch.setenv("APP_NAME", "Custom Runtime Name")
    monkeypatch.setenv("APP_TAGLINE", "Custom Runtime Tagline")

    resp = client.get("/api/auth/config")

    assert resp.status_code == 200
    data = resp.json()
    assert data["appName"] == "Custom Runtime Name"
    assert data["appTagline"] == "Custom Runtime Tagline"


def test_get_profiles(client):
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert "profiles" in data
    assert isinstance(data["profiles"], list)
    assert "unavailable" in data
    assert isinstance(data["unavailable"], list)
    # All profiles should be in either profiles or unavailable
    total = len(data["profiles"]) + len(data["unavailable"])
    assert total > 0
    # Verify profile structure for healthy profiles
    for profile in data["profiles"]:
        assert "id" in profile
        assert "name" in profile
        assert "description" in profile
        assert "starters" in profile
        assert isinstance(profile["starters"], list)
    # Verify unavailable structure
    for entry in data["unavailable"]:
        assert "id" in entry
        assert "name" in entry
        assert "reason" in entry


def test_create_session_invalid_profile(client):
    resp = client.post("/api/sessions", json={"profile_id": "nonexistent_xyz"})
    # Should fail with 400 or 500 depending on profile resolution
    assert resp.status_code in (400, 500)


def test_delete_session_not_found(client):
    resp = client.delete("/api/sessions/nonexistent-session-id")
    assert resp.status_code == 404


def test_send_message_no_session(client):
    resp = client.post(
        "/api/sessions/nonexistent-session-id/messages",
        json={"content": "Hello"},
    )
    assert resp.status_code == 404


def test_openapi_docs(client):
    resp = client.get("/api/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "paths" in data
    assert "/api/health" in data["paths"]


def test_custom_session_binds_all_selected_tools(client):
    resp = client.post(
        "/api/sessions",
        json={
            "profile_id": "custom",
            "custom_name": "All Tools Custom",
            "custom_prompt": "Use any selected tool when needed.",
            "custom_tools": [
                "get_user_profile",
                "save_user_profile",
            ],
            "custom_search_context": False,
        },
    )

    assert resp.status_code == 201
    session_id = resp.json()["session_id"]
    session_data = _sessions[session_id]
    tool_names = {getattr(tool, "name", None) or getattr(tool, "__name__", None) for tool in session_data.tools}
    assert {"get_user_profile", "save_user_profile"}.issubset(tool_names)


def test_custom_session_rejects_sql_when_database_is_unconfigured(client, monkeypatch):
    monkeypatch.setenv("AZURE_SQL_CONNECTIONSTRING", "")

    resp = client.post(
        "/api/sessions",
        json={
            "profile_id": "custom",
            "custom_name": "SQL Custom",
            "custom_prompt": "Use sql_read_query when needed.",
            "custom_tools": ["sql_read_query"],
            "custom_search_context": False,
        },
    )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "sql_read_query tool requires AZURE_SQL_CONNECTIONSTRING"
