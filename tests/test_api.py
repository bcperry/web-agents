"""Tests for FastAPI API endpoints."""

import os
from types import SimpleNamespace

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("AZURE_SQL_CONNECTIONSTRING", "")

from main import _sessions
from prompt_config import load_agents_yaml


def faa_profile_name() -> str:
    return str(load_agents_yaml()["profiles"]["faa"].get("name", "faa"))


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


def test_get_builtin_profile_definition_success(client):
    resp = client.get("/api/profiles/faa/definition")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "faa"
    assert data["name"] == faa_profile_name()
    assert data["source"] == "builtin"
    assert data["systemPrompt"]
    assert isinstance(data["tools"], list)
    assert isinstance(data["mcpServers"], list)


def test_get_builtin_profile_definition_not_found(client):
    resp = client.get("/api/profiles/nope/definition")

    assert resp.status_code == 404


def test_get_builtin_profile_definition_does_not_expose_secret_fields(client):
    resp = client.get("/api/profiles/faa/definition")

    assert resp.status_code == 200
    payload = resp.text.lower()
    assert "api_key" not in payload
    assert "authorization" not in payload
    assert "bearer" not in payload
    assert "connectionstring" not in payload


def test_create_session_invalid_profile(client):
    resp = client.post("/api/sessions", json={"profile_id": "nonexistent_xyz"})
    # Should fail with 400 or 500 depending on profile resolution
    assert resp.status_code in (400, 500)


def test_standard_profile_session_preserves_runtime_request_and_response(client, monkeypatch):
    import session_orchestration

    calls: dict[str, object] = {}

    class DummySession:
        def to_dict(self):
            return {"items": []}

    def fake_create_chat_runtime(**kwargs):
        calls["runtime"] = kwargs
        return SimpleNamespace(
            agent=object(),
            session=DummySession(),
            tools=kwargs.get("function_tools", []),
            prompt_manifest={},
            prompt_logical_profile="search",
        )

    async def fake_connect_mcp_servers(configs, *, user_token=None):
        calls["mcp_configs"] = configs
        calls["user_token"] = user_token
        return [], []

    monkeypatch.setattr(session_orchestration, "create_chat_runtime", fake_create_chat_runtime)
    monkeypatch.setattr(session_orchestration, "connect_mcp_servers", fake_connect_mcp_servers)

    resp = client.post(
        "/api/sessions",
        json={
            "profile_id": "search",
            "user_profile": {"name": "Avery", "preferences": "brief", "notes": "pilot"},
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["profile_id"] == "search"
    assert data["profile_name"] == "Search Agent"
    assert data["tools_loaded"] == ["get_user_profile", "save_user_profile"]
    assert data["skills_loaded"] == []
    assert data["search_context"] is True
    assert data["mcp_results"] == []
    assert data["used_profile_override"] is False
    assert data["override_updated_at"] is None

    runtime_kwargs = calls["runtime"]
    assert runtime_kwargs["chat_profile"] == "Search Agent"
    assert "Known User Profile" in runtime_kwargs["extra_instructions"]
    assert runtime_kwargs["mcp_servers"] == []
    assert data["session_id"] in _sessions


def test_custom_session_preserves_runtime_request_and_response(client, monkeypatch):
    import session_orchestration

    calls: dict[str, object] = {}

    class DummySession:
        def to_dict(self):
            return {"items": []}

    def fake_create_chat_runtime(**kwargs):
        calls["runtime"] = kwargs
        return SimpleNamespace(
            agent=object(),
            session=DummySession(),
            tools=kwargs.get("function_tools", []),
            prompt_manifest={},
            prompt_logical_profile="custom",
        )

    async def fake_connect_mcp_servers(configs, *, user_token=None):
        return [], []

    monkeypatch.setattr(session_orchestration, "create_chat_runtime", fake_create_chat_runtime)
    monkeypatch.setattr(session_orchestration, "connect_mcp_servers", fake_connect_mcp_servers)

    resp = client.post(
        "/api/sessions",
        json={
            "profile_id": "custom",
            "custom_name": "Planner",
            "custom_prompt": "Plan carefully.",
            "custom_tools": ["get_user_profile"],
            "custom_search_context": True,
            "custom_temperature": 0.7,
            "custom_skills": [],
            "mcp_servers": [],
            "user_profile": {"name": "Avery", "preferences": "brief", "notes": "pilot"},
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["profile_id"] == "custom"
    assert data["profile_name"] == "Planner"
    assert data["tools_loaded"] == ["get_user_profile"]
    assert data["skills_loaded"] == []
    assert data["search_context"] is True
    assert data["mcp_results"] == []

    runtime_kwargs = calls["runtime"]
    assert runtime_kwargs["custom_name"] == "Planner"
    assert runtime_kwargs["custom_instructions"] == "Plan carefully."
    assert runtime_kwargs["temperature"] == 0.7
    assert runtime_kwargs["enable_search_context"] is True
    assert runtime_kwargs["custom_skills"] is None
    assert "Known User Profile" in runtime_kwargs["extra_instructions"]


def test_builtin_profile_override_session_preserves_canonical_name(client, monkeypatch):
    import session_orchestration

    class DummySession:
        def to_dict(self):
            return {"items": []}

    def fake_create_chat_runtime(**kwargs):
        assert kwargs["custom_name"] == faa_profile_name()
        assert kwargs["custom_instructions"] == "Override prompt"
        return SimpleNamespace(
            agent=object(),
            session=DummySession(),
            tools=kwargs.get("function_tools", []),
            prompt_manifest={},
            prompt_logical_profile="custom",
        )

    async def fake_connect_mcp_servers(configs, *, user_token=None):
        return [], []

    monkeypatch.setattr(session_orchestration, "create_chat_runtime", fake_create_chat_runtime)
    monkeypatch.setattr(session_orchestration, "connect_mcp_servers", fake_connect_mcp_servers)

    resp = client.post(
        "/api/sessions",
        json={
            "profile_id": "faa",
            "profile_override": {
                "description": "Local FAA tuning",
                "custom_prompt": "Override prompt",
                "custom_tools": ["get_user_profile"],
                "custom_search_context": False,
                "custom_skills": [],
                "mcp_servers": [],
                "override_updated_at": "2026-05-06T12:00:00.000Z",
            },
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["profile_id"] == "faa"
    assert data["profile_name"] == faa_profile_name()
    assert data["used_profile_override"] is True
    assert data["override_updated_at"] == "2026-05-06T12:00:00.000Z"

    history_resp = client.get(f"/api/sessions/{data['session_id']}/history")
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    assert history_data["used_profile_override"] is True
    assert history_data["override_updated_at"] == "2026-05-06T12:00:00.000Z"


def test_builtin_profile_override_rejects_name_change(client):
    resp = client.post(
        "/api/sessions",
        json={
            "profile_id": "faa",
            "profile_override": {
                "name": "Renamed FAA",
                "custom_prompt": "Override prompt",
                "custom_tools": [],
                "custom_search_context": False,
            },
        },
    )

    assert resp.status_code == 400
    assert "cannot change the agent name" in resp.json()["detail"]


def test_custom_session_drops_unknown_skills(client, monkeypatch, caplog):
    """Regression: deleting a skill referenced by a saved custom agent must not
    block the session from loading. Unknown skills are silently dropped with a
    warning so the agent remains usable."""
    import logging

    import session_orchestration

    calls: dict[str, object] = {}

    class DummySession:
        def to_dict(self):
            return {"items": []}

    def fake_create_chat_runtime(**kwargs):
        calls["runtime"] = kwargs
        return SimpleNamespace(
            agent=object(),
            session=DummySession(),
            tools=kwargs.get("function_tools", []),
            prompt_manifest={},
            prompt_logical_profile="custom",
        )

    async def fake_connect_mcp_servers(configs, *, user_token=None):
        return [], []

    monkeypatch.setattr(session_orchestration, "create_chat_runtime", fake_create_chat_runtime)
    monkeypatch.setattr(session_orchestration, "connect_mcp_servers", fake_connect_mcp_servers)

    with caplog.at_level(logging.WARNING):
        resp = client.post(
            "/api/sessions",
            json={
                "profile_id": "custom",
                "custom_name": "Planner",
                "custom_prompt": "Plan carefully.",
                "custom_tools": [],
                "custom_search_context": False,
                "custom_skills": ["__deleted_skill__"],
                "mcp_servers": [],
            },
        )

    assert resp.status_code == 201
    assert resp.json()["skills_loaded"] == []
    assert calls["runtime"]["custom_skills"] is None
    assert any("__deleted_skill__" in record.message for record in caplog.records)


def test_builtin_profile_override_drops_unknown_skills(client, monkeypatch, caplog):
    """Regression: a built-in override that still references a deleted skill
    must load — the unknown skill is dropped with a warning."""
    import logging

    import session_orchestration

    calls: dict[str, object] = {}

    class DummySession:
        def to_dict(self):
            return {"items": []}

    def fake_create_chat_runtime(**kwargs):
        calls["runtime"] = kwargs
        return SimpleNamespace(
            agent=object(),
            session=DummySession(),
            tools=kwargs.get("function_tools", []),
            prompt_manifest={},
            prompt_logical_profile="custom",
        )

    async def fake_connect_mcp_servers(configs, *, user_token=None):
        return [], []

    monkeypatch.setattr(session_orchestration, "create_chat_runtime", fake_create_chat_runtime)
    monkeypatch.setattr(session_orchestration, "connect_mcp_servers", fake_connect_mcp_servers)

    with caplog.at_level(logging.WARNING):
        resp = client.post(
            "/api/sessions",
            json={
                "profile_id": "faa",
                "profile_override": {
                    "description": "Local FAA tuning",
                    "custom_prompt": "Override prompt",
                    "custom_tools": [],
                    "custom_search_context": False,
                    "custom_skills": ["__deleted_skill__"],
                    "mcp_servers": [],
                    "override_updated_at": "2026-05-06T12:00:00.000Z",
                },
            },
        )

    assert resp.status_code == 201
    assert calls["runtime"]["custom_skills"] is None
    assert any("__deleted_skill__" in record.message for record in caplog.records)


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
    response_data = resp.json()
    assert {
        "session_id",
        "profile_id",
        "profile_name",
        "tools_loaded",
        "skills_loaded",
        "search_context",
        "mcp_results",
    }.issubset(response_data)
    assert response_data["profile_id"] == "custom"
    assert response_data["profile_name"] == "All Tools Custom"
    assert response_data["tools_loaded"] == ["get_user_profile", "save_user_profile"]
    assert response_data["skills_loaded"] == []
    assert response_data["search_context"] is False
    assert response_data["mcp_results"] == []
    session_id = response_data["session_id"]
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

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unknown tools: sql_read_query"


# ---------------------------------------------------------------------------
# T028 — agents_as_tools wire format & validation through /api/sessions
# ---------------------------------------------------------------------------


def _stub_runtime(monkeypatch):
    """Patch session_orchestration to bypass real LLM client + MCP init."""
    import session_orchestration

    captured: dict[str, object] = {}

    class _DummySession:
        def to_dict(self):
            return {"items": []}

    def fake_create_chat_runtime(**kwargs):
        captured["runtime"] = kwargs
        return SimpleNamespace(
            agent=object(),
            session=_DummySession(),
            tools=kwargs.get("function_tools", []),
            prompt_manifest={},
            prompt_logical_profile="custom",
            sub_agent_tool_names=[],
        )

    async def fake_connect_mcp_servers(configs, *, user_token=None):
        return [], []

    monkeypatch.setattr(session_orchestration, "create_chat_runtime", fake_create_chat_runtime)
    monkeypatch.setattr(session_orchestration, "connect_mcp_servers", fake_connect_mcp_servers)
    return captured


def test_custom_session_with_valid_custom_sub_agent_succeeds(client, monkeypatch):
    captured = _stub_runtime(monkeypatch)

    payload = {
        "profile_id": "custom",
        "custom_name": "Parent",
        "custom_id": "parent-1",
        "custom_prompt": "Coordinate.",
        "custom_tools": [],
        "custom_search_context": False,
        "agentsAsTools": [
            {
                "agentRef": {
                    "kind": "custom",
                    "customAgentId": "child-1",
                    "definition": {
                        "id": "child-1",
                        "name": "Child Agent",
                        "description": "Child does things.",
                        "systemPrompt": "You are the child.",
                    },
                }
            }
        ],
    }
    resp = client.post("/api/sessions", json=payload)
    assert resp.status_code == 201, resp.json()
    runtime_kwargs = captured["runtime"]
    refs = runtime_kwargs["agents_as_tools"]
    assert len(refs) == 1
    assert refs[0].agent_ref.kind == "custom"
    assert refs[0].agent_ref.custom_agent_id == "child-1"


def test_custom_session_self_reference_returns_400(client, monkeypatch):
    _stub_runtime(monkeypatch)
    payload = {
        "profile_id": "custom",
        "custom_name": "Parent",
        "custom_id": "parent-1",
        "custom_prompt": "x",
        "agentsAsTools": [
            {
                "agentRef": {
                    "kind": "custom",
                    "customAgentId": "parent-1",
                    "definition": {
                        "id": "parent-1",
                        "name": "Parent",
                        "systemPrompt": "x",
                    },
                }
            }
        ],
    }
    resp = client.post("/api/sessions", json=payload)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    codes = {e["code"] for e in detail["errors"]}
    assert "self_reference" in codes


def test_custom_session_duplicate_target_returns_400(client, monkeypatch):
    _stub_runtime(monkeypatch)
    dup = {
        "agentRef": {
            "kind": "custom",
            "customAgentId": "child",
            "definition": {"id": "child", "name": "Child", "systemPrompt": "x"},
        }
    }
    resp = client.post(
        "/api/sessions",
        json={
            "profile_id": "custom",
            "custom_name": "Parent",
            "custom_prompt": "x",
            "agentsAsTools": [dup, dup],
        },
    )
    assert resp.status_code == 400
    codes = {e["code"] for e in resp.json()["detail"]["errors"]}
    assert "duplicate_target" in codes


def test_custom_session_definition_id_mismatch_returns_400(client, monkeypatch):
    _stub_runtime(monkeypatch)
    resp = client.post(
        "/api/sessions",
        json={
            "profile_id": "custom",
            "custom_name": "Parent",
            "custom_prompt": "x",
            "agentsAsTools": [
                {
                    "agentRef": {
                        "kind": "custom",
                        "customAgentId": "child-1",
                        "definition": {
                            "id": "child-mismatch",
                            "name": "Child",
                            "systemPrompt": "x",
                        },
                    }
                }
            ],
        },
    )
    assert resp.status_code == 400
    codes = {e["code"] for e in resp.json()["detail"]["errors"]}
    assert "definition_id_mismatch" in codes


def test_builtin_profile_definition_response_includes_agents_as_tools_field(client):
    """The /definition endpoint MUST always include the new field."""
    # Use the first available built-in profile id.
    profiles_resp = client.get("/api/profiles")
    assert profiles_resp.status_code == 200
    profile_ids = [p["id"] for p in profiles_resp.json()["profiles"] if not p.get("isCustom")]
    assert profile_ids, "Expected at least one built-in profile in test fixtures"
    resp = client.get(f"/api/profiles/{profile_ids[0]}/definition")
    assert resp.status_code == 200
    data = resp.json()
    assert "agentsAsTools" in data
    assert isinstance(data["agentsAsTools"], list)
