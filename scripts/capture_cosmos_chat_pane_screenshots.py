"""Capture chat-pane visual-verification screenshots for the Cosmos memory feature.

Mocks the backend API (including the new ``/api/conversations`` endpoints) so the
server-sourced conversation list renders deterministically without a live backend,
LLM, or Cosmos account. Saves PNGs under ``screenshots/011-cosmos-agent-memory/``.

Usage:
    uv run python scripts/capture_cosmos_chat_pane_screenshots.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


DEFAULT_PROFILE = {
    "id": "visual-agent",
    "name": "Visual Agent",
    "description": "Screenshot verification profile",
    "icon": "/favicon.png",
    "starters": [
        {"label": "Summarize", "message": "Summarize the latest status."},
        {"label": "Plan", "message": "Make a concise plan."},
    ],
}

CONVERSATIONS = [
    {
        "id": "conv-1",
        "profileId": "visual-agent",
        "profileName": "Visual Agent",
        "description": "Help me plan the offsite agenda",
        "createdAt": "2026-06-18T14:03:11Z",
        "lastActivityAt": "2026-06-18T14:25:02Z",
    },
    {
        "id": "conv-2",
        "profileId": "visual-agent",
        "profileName": "Visual Agent",
        "description": "Draft a status update for the readiness review",
        "createdAt": "2026-06-17T09:12:00Z",
        "lastActivityAt": "2026-06-17T09:40:00Z",
    },
    {
        "id": "conv-3",
        "profileId": "visual-agent",
        "profileName": "Visual Agent",
        "description": "Summarize yesterday's maintenance logs",
        "createdAt": "2026-06-16T16:01:00Z",
        "lastActivityAt": "2026-06-16T16:20:00Z",
    },
]

RESUMED_MESSAGES = {
    "id": "conv-1",
    "profileId": "visual-agent",
    "profileName": "Visual Agent",
    "messages": [
        {"role": "user", "content": "Help me plan the offsite agenda"},
        {"role": "assistant", "content": "Here is a draft agenda: 1) Goals, 2) Roadmap, 3) Breakouts, 4) Wrap-up."},
    ],
}


def setup_mock_api(page: Page, *, empty_conversations: bool = False) -> None:
    def handler(route) -> None:
        request = route.request
        url = request.url
        method = request.method
        path = url.split("?", 1)[0]

        if url.endswith("/api/auth/config"):
            route.fulfill(json={
                "authDisabled": True,
                "tenantId": "",
                "clientId": "",
                "authority": "https://login.microsoftonline.us",
                "classificationBanner": "UNCLASSIFIED",
                "appName": "Web-Agents",
                "appTagline": "AI Agent Framework",
                "appLogo": "/Microsoft.png",
            })
        elif url.endswith("/api/profiles"):
            route.fulfill(json={"profiles": [DEFAULT_PROFILE], "unavailable": []})
        elif url.endswith("/api/tools"):
            route.fulfill(json={"tools": [], "unavailable": [], "search_context_available": True, "search_context_reason": None})
        elif url.endswith("/api/skills") and method == "GET":
            route.fulfill(json={"skills": []})
        elif path.endswith("/messages") and "/api/conversations/" in path:
            route.fulfill(json=RESUMED_MESSAGES)
        elif path.endswith("/api/conversations") and method == "GET":
            conversations = [] if empty_conversations else CONVERSATIONS
            route.fulfill(json={"conversations": conversations, "nextCursor": None})
        elif "/api/conversations/" in path and method == "DELETE":
            route.fulfill(status=204, body="")
        elif "/api/profiles/" in url and url.endswith("/definition"):
            route.fulfill(json={
                **DEFAULT_PROFILE,
                "systemPrompt": "You are a visual verification agent.",
                "tools": [],
                "skills": [],
                "mcpServers": [],
                "useSearchContext": False,
                "temperature": 0.2,
            })
        elif url.endswith("/api/sessions") and method == "POST":
            route.fulfill(json={
                "session_id": "conv-1",
                "profile_id": "visual-agent",
                "profile_name": "Visual Agent",
                "tools_loaded": [],
                "skills_loaded": [],
                "search_context": False,
                "mcp_results": [],
            })
        elif "/api/sessions/" in url and url.endswith("/messages") and method == "POST":
            route.fulfill(
                status=200,
                headers={"content-type": "text/event-stream"},
                body=(
                    'event: text\ndata: {"content":"Durable memory response."}\n\n'
                    'event: usage\ndata: {"input_token_count":4,"output_token_count":5,"total_token_count":9}\n\n'
                    'event: done\ndata: {}\n\n'
                ),
            )
        elif "/api/sessions/" in url and method == "DELETE":
            route.fulfill(status=204, body="")
        else:
            route.continue_()

    page.route("**/api/**", handler)


def accept_disclaimer(page: Page) -> None:
    button = page.get_by_role("button", name="I UNDERSTAND AND AGREE")
    if button.count() > 0:
        button.click()


def capture(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.chrome_path)

        # 1) Populated conversation list + profile selection.
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        setup_mock_api(page)
        page.goto(args.base_url, wait_until="networkidle")
        accept_disclaimer(page)
        page.get_by_text("SELECT YOUR AGENT").wait_for(timeout=8_000)
        page.screenshot(path=str(output_dir / "011-conversations-list-populated.png"), full_page=True)

        # 2) Resume a conversation — prior messages render from the server mock.
        page.locator(".sidebar-entry").first.click(timeout=8_000)
        page.get_by_text("Here is a draft agenda", exact=False).wait_for(timeout=8_000)
        page.screenshot(path=str(output_dir / "011-conversation-resumed.png"), full_page=True)

        page.close()

        # 3) Empty state — new user with no conversations.
        page_empty = browser.new_page(viewport={"width": args.width, "height": args.height})
        setup_mock_api(page_empty, empty_conversations=True)
        page_empty.goto(args.base_url, wait_until="networkidle")
        accept_disclaimer(page_empty)
        page_empty.get_by_text("SELECT YOUR AGENT").wait_for(timeout=8_000)
        page_empty.screenshot(path=str(output_dir / "011-conversations-empty.png"), full_page=True)

        # 4) Empty-state at mobile width.
        page_empty.set_viewport_size({"width": 360, "height": 640})
        page_empty.screenshot(path=str(output_dir / "011-conversations-empty-mobile.png"), full_page=True)
        page_empty.close()

        browser.close()
    print(f"Saved chat-pane screenshots to {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Cosmos chat-pane screenshots.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output-dir", default="screenshots/011-cosmos-agent-memory")
    parser.add_argument("--chrome-path", default="/usr/bin/google-chrome")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    return parser.parse_args()


if __name__ == "__main__":
    capture(parse_args())
