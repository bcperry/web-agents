"""Focused browser coverage for optional creation-tool grants in Agent Builder."""

from __future__ import annotations

import json
import asyncio
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 1000}, {"width": 390, "height": 844}])
def test_agent_builder_renders_and_preserves_independent_creation_tools(viewport, client, monkeypatch):
    import user_data

    monkeypatch.setattr("api_routes.user_data.load_agents_yaml", lambda: {
        "profiles": {"builtin": {"name": "Built In"}},
    })
    asyncio.run(user_data.get_user_skills_repository().create("dev-user", "tool-created-skill", {
        "id": "tool-created-skill", "name": "tool-created-skill",
        "description": "Created from chat", "content": "Help the user.",
    }))
    playwright = pytest.importorskip("playwright.sync_api")
    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        pytest.skip("frontend/dist is required; run npm run build first")

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(_QuietHandler, directory=str(dist))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    writes: list[tuple[str, dict]] = []
    fail_writes = False
    pending_messages = []
    created_sessions = []
    deleted_sessions = []
    pending_starts = []
    resume_operations = []

    def route_api(route):
        request = route.request
        path = request.url.split("/api/", 1)[-1].split("?", 1)[0]
        if path == "sessions" and request.method == "POST":
            if request.post_data_json.get("conversation_id") == "shared":
                resume_operations.append("create")
                if not pending_starts:
                    pending_starts.append(route)
                    return
                route.fulfill(json={"session_id": "shared", "profile_id": "builtin", "profile_name": "Built In"})
                return
            session_id = f"chat-{len(created_sessions)}"
            created_sessions.append(session_id)
            route.fulfill(json={"session_id": session_id, "profile_id": "builtin", "profile_name": "Built In"})
            return
        if path.startswith("sessions/") and request.method == "DELETE":
            if path == "sessions/shared":
                resume_operations.append("delete")
            deleted_sessions.append(path.split("/")[1])
            route.fulfill(status=204)
            return
        if path.endswith("/messages") and request.method == "POST":
            pending_messages.append(route)
            return
        if path.endswith("/views") and request.method == "GET":
            route.fulfill(json={"views": []})
            return
        if request.method == "PUT":
            if fail_writes:
                route.fulfill(status=503, json={"detail": "Test store unavailable"})
                return
            response = client.put(f"/api/{path}", json=request.post_data_json)
            assert response.status_code == 200, response.text
            writes.append((path, request.post_data_json))
            route.fulfill(status=response.status_code, content_type="application/json", body=response.text)
            return
        responses = {
            "auth/config": {"authDisabled": True, "classificationBanner": "UNCLASSIFIED"},
            "custom-agents": {"agents": [{
                "id": "tool-created-agent", "name": "Tool Created Agent",
                "description": "Created from chat", "systemPrompt": "Help the user.",
                "tools": [], "skills": ["tool-created-skill"], "mcpServers": [],
                "useSearchContext": False, "icon": "/favicon.png", "starters": [{
                    "label": "Original label", "message": "Original message",
                }],
                "temperature": 0.2, "agentsAsTools": [],
                "createdAt": "2026-07-10T00:00:00Z", "updatedAt": "2026-07-10T00:00:00Z",
            }]},
            "agent-customizations": {"overrides": []},
            "conversations": {"conversations": [], "nextCursor": None},
            "conversations/shared/messages": {"messages": []},
            "profiles": {"profiles": [{
                "id": "builtin", "name": "Built In", "description": "Built-in test agent",
                "icon": "/favicon.png", "group": "Test", "starters": [], "skills": [],
                "mcp_server_count": 0,
            }], "unavailable": []},
            "profiles/builtin/definition": {
                "id": "builtin", "name": "Built In", "description": "Built-in test agent",
                "systemPrompt": "Built-in prompt", "tools": [], "skills": [], "mcpServers": [],
                "useSearchContext": False, "icon": "/favicon.png", "starters": [],
                "agentsAsTools": [], "source": "builtin",
            },
            "tools": {
                "tools": [
                    {"name": "create_skill", "description": "Create a durable user-owned skill without overwriting existing work."},
                    {"name": "create_agent", "description": "Create a durable user-owned custom agent without overwriting existing work."},
                    {"name": "edit_skill", "description": "Edit an existing user-owned skill."},
                    {"name": "edit_agent", "description": "Edit an existing user-owned custom agent using its complete definition."},
                ],
                "unavailable": [], "search_context_available": False, "search_context_reason": "test",
            },
            "skills": {"skills": [{
                "name": "tool-created-skill", "description": "Created from chat",
            }]},
        }
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(responses.get(path, {})),
        )

    try:
        with playwright.sync_playwright() as manager:
            try:
                browser = manager.chromium.launch(headless=True)
            except playwright.Error as exc:
                pytest.skip(f"Playwright Chromium is unavailable: {exc}")
            page = browser.new_page(viewport=viewport)
            page.route("**/api/**", route_api)
            page.goto(f"http://127.0.0.1:{server.server_port}")
            page.get_by_role("button", name="I UNDERSTAND AND AGREE").click()
            page.get_by_role("button", name="Open settings").click()
            page.get_by_role("menuitem", name="ADMIN").click()
            page.get_by_role("button", name="AGENTS").click()

            page.get_by_title("Edit custom agent").click()
            page.get_by_role("button", name=re.compile("SKILLS.*1 selected", re.I)).click()
            assert page.get_by_role(
                "checkbox", name=re.compile("tool created skill", re.I)
            ).is_checked()
            page.get_by_role("textbox", name="Starter 1 button label").fill("Updated label")
            page.get_by_role("textbox", name="Starter 1 message").fill("Updated message")
            page.get_by_role("button", name="UPDATE AGENT").click()
            edited_write = next(
                payload for path, payload in writes
                if path == "custom-agents/tool-created-agent"
            )
            assert edited_write["starters"] == [{
                "label": "Updated label", "message": "Updated message",
            }]
            stored_agents = client.get("/api/custom-agents").json()["agents"]
            assert stored_agents[0]["starters"] == edited_write["starters"]

            page.get_by_role("button", name=re.compile(r"^TOOLS\s+0 selected", re.I)).click()
            skill_checkbox = page.get_by_role("checkbox", name=re.compile("create skill", re.I))
            agent_checkbox = page.get_by_role("checkbox", name=re.compile("create agent", re.I))
            assert skill_checkbox.is_visible()
            assert agent_checkbox.is_visible()
            assert page.get_by_role("checkbox", name=re.compile("edit skill", re.I)).is_visible()
            assert page.get_by_role("checkbox", name=re.compile("edit agent", re.I)).is_visible()
            assert page.locator('label[title^="Create a durable user-owned skill"]').is_visible()
            assert page.locator('label[title^="Create a durable user-owned custom agent"]').is_visible()

            skill_checkbox.check()
            agent_checkbox.check()
            page.get_by_placeholder("e.g. Data Analyst").fill("Created In UI")
            page.get_by_placeholder("You are a specialized agent that...").fill("Help the user.")
            page.get_by_role("button", name="SAVE AGENT").click()
            custom_write = next(
                payload for path, payload in writes
                if path.startswith("custom-agents/") and path != "custom-agents/tool-created-agent"
            )
            assert custom_write["tools"] == ["create_skill", "create_agent"]
            stored_custom = next(agent for agent in client.get("/api/custom-agents").json()["agents"]
                                 if agent["id"] == custom_write["id"])
            assert stored_custom["tools"] == custom_write["tools"]
            assert stored_custom["systemPrompt"] == custom_write["systemPrompt"]

            page.get_by_title("Customize built-in agent").click()
            page.get_by_role("checkbox", name=re.compile("create agent", re.I)).check()
            page.get_by_role("button", name="SAVE CUSTOMIZATION").click()
            override_write = next(payload for path, payload in writes if path.startswith("agent-customizations/"))
            assert override_write["tools"] == ["create_agent"]
            assert override_write["baseProfileName"] == "Built In"
            stored_override = client.get("/api/agent-customizations").json()["overrides"][0]
            assert stored_override["baseProfileName"] == "Built In"
            assert stored_override["systemPrompt"] == override_write["systemPrompt"]
            assert stored_override["tools"] == override_write["tools"]
            assert "temperature" not in override_write
            assert stored_override["temperature"] == 0.2

            fail_writes = True
            page.get_by_placeholder("e.g. Data Analyst").fill("Unsaved draft")
            page.get_by_placeholder("You are a specialized agent that...").fill("Keep this prompt.")
            page.get_by_role("button", name="SAVE AGENT").click()
            playwright.expect(page.get_by_text("Test store unavailable", exact=True)).to_be_visible()
            playwright.expect(page.get_by_placeholder("e.g. Data Analyst")).to_have_value("Unsaved draft")
            playwright.expect(page.get_by_placeholder("You are a specialized agent that...")).to_have_value("Keep this prompt.")
            playwright.expect(page.get_by_text("Agent saved successfully", exact=False)).to_have_count(0)
            assert not any(payload.get("name") == "Unsaved draft" for _, payload in writes)

            page.get_by_title("Customize built-in agent").click()
            playwright.expect(page.get_by_placeholder("You are a specialized agent that...")).to_have_value("Built-in prompt")
            playwright.expect(page.get_by_role("spinbutton")).to_have_value("0.2")
            page.get_by_placeholder("You are a specialized agent that...").fill("Retain failed override.")
            page.get_by_role("button", name="SAVE CUSTOMIZATION").click()
            playwright.expect(page.get_by_placeholder("You are a specialized agent that...")).to_have_value("Retain failed override.")
            playwright.expect(page.locator('.agent-builder-form')).not_to_have_attribute('inert', '')
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

            page.get_by_role("button", name="BACK TO CHAT").click()
            page.locator('.profile-card').filter(has_text="Built In").click()
            composer = page.get_by_placeholder("Type your message...")
            composer.fill("Alpha question")
            page.get_by_role("button", name="TRANSMIT").click()
            playwright.expect(composer).to_be_disabled()
            if viewport["width"] <= 768:
                page.locator('.header-sidebar-toggle').click()
            page.get_by_role("button", name="+ NEW CHAT").click()
            page.locator('.profile-card').filter(has_text="Built In").click()
            playwright.expect(composer).to_be_enabled()
            assert "chat-0" in deleted_sessions
            pending_messages[0].fulfill(content_type="text/event-stream", body='event: text\ndata: {"content":"STALE ALPHA RESPONSE"}\n\nevent: done\ndata: {}\n\n')
            composer.fill("Beta question")
            page.get_by_role("button", name="TRANSMIT").click()
            playwright.expect(composer).to_be_disabled()
            pending_messages[1].fulfill(content_type="text/event-stream", body='event: text\ndata: {"content":"Beta partial response"}\n\n')
            playwright.expect(page.get_by_text("Beta partial response", exact=True)).to_be_visible()
            playwright.expect(composer).to_be_enabled()
            playwright.expect(page.get_by_text("The response ended before completion. Please try again.", exact=True)).to_be_visible()
            playwright.expect(page.get_by_text("STALE ALPHA RESPONSE", exact=True)).to_have_count(0)
            composer.fill("Malformed response")
            page.get_by_role("button", name="TRANSMIT").click()
            playwright.expect(composer).to_be_disabled()
            pending_messages[2].fulfill(content_type="text/event-stream", body='event: text\ndata: not-json\n\n')
            playwright.expect(composer).to_be_enabled()
            composer.fill("Tool results")
            page.get_by_role("button", name="TRANSMIT").click()
            playwright.expect(composer).to_be_disabled()
            events = [
                ("function_call", {"call_id": "first", "name": "lookup", "arguments": '{"id":'}),
                ("function_call", {"call_id": "first", "name": "lookup", "arguments": '{"id":1}'}),
                ("function_call", {"call_id": "second", "name": "fallback", "arguments": '{}'}),
                ("function_result", {"call_id": "first", "result": "Matched result", "arguments": ""}),
                ("function_result", {"call_id": "unknown", "result": "Fallback result"}),
                ("usage", {"input_token_count": 2, "output_token_count": 3, "total_token_count": 5}),
                ("text", {"content": "Tools complete"}),
                ("done", {}),
            ]
            pending_messages[3].fulfill(content_type="text/event-stream", body="".join(
                f"event: {kind}\ndata: {json.dumps(payload)}\n\n" for kind, payload in events
            ))
            playwright.expect(composer).to_be_enabled()
            playwright.expect(page.get_by_text("Tools complete", exact=True)).to_be_visible()
            for name, result in [("lookup", "Matched result"), ("fallback", "Fallback result")]:
                page.get_by_role("button", name=re.compile(rf"\[TOOL\] {name}")).click()
                playwright.expect(page.get_by_text(result, exact=True)).to_be_visible()
            playwright.expect(page.locator(".tool-step-code").filter(has_text='"id": 1')).to_have_count(1)
            page.route("**/api/conversations?*", lambda route: route.fulfill(json={
                "conversations": [{"id": "shared", "profileId": "builtin", "profileName": "Built In",
                    "description": "Resume race", "lastActivityAt": "2026-09-10T00:00:00Z"}],
                "nextCursor": None,
            }))
            if viewport["width"] <= 768:
                page.locator('.header-sidebar-toggle').click()
            page.get_by_role("button", name="+ NEW CHAT").click()
            if viewport["width"] <= 768:
                page.locator('.header-sidebar-toggle').click()
            with page.expect_request(lambda request: request.method == "POST" and request.url.endswith("/api/sessions")):
                page.locator('.sidebar-entry').filter(has_text="Resume race").click()
            if viewport["width"] <= 768:
                page.locator('.header-sidebar-toggle').click()
            page.locator('.sidebar-entry').filter(has_text="Resume race").click()
            with page.expect_response(lambda response: response.request.method == "DELETE" and response.url.endswith("/sessions/shared")):
                pending_starts[0].fulfill(json={"session_id": "shared", "profile_id": "builtin", "profile_name": "Built In"})
            playwright.expect(composer).to_be_enabled()
            assert resume_operations == ["create", "delete", "create"]
            page.screenshot(path=str(dist.parent / "screenshots" / f"remediation-{viewport['width']}.png"), full_page=True)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)