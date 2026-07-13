"""Focused browser coverage for optional creation-tool grants in Agent Builder."""

from __future__ import annotations

import json
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


def test_agent_builder_renders_and_preserves_independent_creation_tools():
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

    def route_api(route):
        request = route.request
        path = request.url.split("/api/", 1)[-1]
        if request.method == "PUT":
            writes.append((path, request.post_data_json))
            route.fulfill(status=200, content_type="application/json", body=request.post_data or "{}")
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
            "conversations": {"conversations": []},
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
            page = browser.new_page()
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

            page.get_by_title("Customize built-in agent").click()
            page.get_by_role("checkbox", name=re.compile("create agent", re.I)).check()
            page.get_by_role("button", name="SAVE CUSTOMIZATION").click()
            override_write = next(payload for path, payload in writes if path.startswith("agent-customizations/"))
            assert override_write["tools"] == ["create_agent"]
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)