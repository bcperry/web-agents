from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


DEFAULT_PROFILE = {
    "id": "settings-visual-agent",
    "name": "Settings Visual Agent",
    "description": "Profile used for settings page screenshot verification",
    "icon": "/favicon.png",
    "starters": [
        {"label": "Status", "message": "Give me the current status."},
        {"label": "Plan", "message": "Make a concise plan."},
    ],
}

CONVERSATION_INDEX = [
    {
        "id": "visual-conversation",
        "profileId": "settings-visual-agent",
        "profileName": "Settings Visual Agent",
        "description": "Existing visual verification conversation",
        "lastActivityAt": "2026-05-29T12:00:00.000Z",
    }
]


def setup_mock_api(page: Page) -> None:
    def handler(route) -> None:
        request = route.request
        url = request.url
        method = request.method

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
            route.fulfill(json={"skills": [{"name": "settings-skill", "description": "Screenshot skill"}]})
        elif "/api/skills/settings-skill" in url and method == "GET":
            route.fulfill(json={"name": "settings-skill", "description": "Screenshot skill", "content": "# Settings Skill\n\nScreenshot skill instructions."})
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
                "session_id": "settings-visual-session",
                "profile_id": "settings-visual-agent",
                "profile_name": "Settings Visual Agent",
                "tools_loaded": [],
                "skills_loaded": [],
                "search_context": False,
                "mcp_results": [],
            })
        elif url.endswith("/api/sessions/settings-visual-session/messages") and method == "POST":
            route.fulfill(
                status=200,
                headers={"content-type": "text/event-stream"},
                body=(
                    'event: text\ndata: {"content":"Settings visual verification response."}\n\n'
                    'event: usage\ndata: {"input_token_count":4,"output_token_count":5,"total_token_count":9}\n\n'
                    'event: done\ndata: {}\n\n'
                ),
            )
        elif url.endswith("/api/sessions/settings-visual-session/history"):
            route.fulfill(json={"session_id": "settings-visual-session", "profile_id": "settings-visual-agent", "profile_name": "Settings Visual Agent", "session_data": {}})
        elif url.endswith("/api/mcp/test"):
            route.fulfill(json={"results": []})
        elif url.endswith("/api/skills/generate"):
            route.fulfill(json={"content": "# Settings Skill\n\nGenerated screenshot content."})
        else:
            route.continue_()

    page.route("**/api/**", handler)


def seed_storage(page: Page) -> None:
    page.evaluate(
        """
        conversationIndex => {
          localStorage.setItem('webagents_conversation_index', JSON.stringify(conversationIndex));
                    localStorage.setItem('webagents_theme', 'light');
                    sessionStorage.setItem('disclaimer_acknowledged', 'true');
        }
        """,
        CONVERSATION_INDEX,
    )


def open_settings_menu(page: Page) -> None:
    page.get_by_role("button", name="Open settings").click(timeout=5_000)
    page.get_by_role("menu", name="Settings menu").wait_for(timeout=5_000)


def open_admin(page: Page) -> None:
    open_settings_menu(page)
    page.get_by_role("menuitem", name="ADMIN").click(timeout=5_000)
    page.get_by_role("button", name="SETTINGS").wait_for(timeout=5_000)


def open_responsive_sidebar(page: Page) -> None:
    page.locator(".header-sidebar-toggle").click(timeout=5_000)
    page.wait_for_function("() => (document.querySelector('.sidebar')?.getBoundingClientRect().width || 0) > 200")


def close_responsive_sidebar(page: Page) -> None:
    page.locator(".sidebar-toggle").click(timeout=5_000)
    page.wait_for_function("() => (document.querySelector('.sidebar')?.getBoundingClientRect().width || 0) < 20")


def capture_for_viewport(page: Page, output_dir: Path, label: str, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(page.url, wait_until="networkidle")
    seed_storage(page)
    page.reload(wait_until="networkidle")

    page.get_by_text("SELECT YOUR AGENT").wait_for(timeout=5_000)
    open_settings_menu(page)
    page.screenshot(path=str(output_dir / f"010-{label}-profile-settings-menu.png"), full_page=True)

    page.keyboard.press("Escape")
    page.locator(".profile-card").first.click(timeout=5_000)
    page.locator(".chat-input-textarea").wait_for(timeout=5_000)
    open_settings_menu(page)
    page.screenshot(path=str(output_dir / f"010-{label}-chat-settings-menu.png"), full_page=True)

    page.keyboard.press("Escape")
    if width <= 768:
        open_responsive_sidebar(page)
    page.screenshot(path=str(output_dir / f"010-{label}-sidebar-conversations.png"), full_page=True)
    if width <= 768:
        close_responsive_sidebar(page)

    open_admin(page)
    page.locator(".admin-theme-option").filter(has=page.locator(".admin-theme-option-label", has_text="LIGHT")).click(timeout=5_000)
    page.screenshot(path=str(output_dir / f"010-{label}-admin-settings-light.png"), full_page=True)
    page.locator(".admin-theme-option").filter(has=page.locator(".admin-theme-option-label", has_text="DARK")).click(timeout=5_000)
    page.screenshot(path=str(output_dir / f"010-{label}-admin-settings-dark.png"), full_page=True)
    page.get_by_role("button", name="AGENTS").click(timeout=5_000)
    page.screenshot(path=str(output_dir / f"010-{label}-admin-agents.png"), full_page=True)
    page.get_by_role("button", name="SKILLS").click(timeout=5_000)
    page.screenshot(path=str(output_dir / f"010-{label}-admin-skills.png"), full_page=True)


def capture(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.chrome_path)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        if args.mock_api:
            setup_mock_api(page)
        page.goto(args.base_url, wait_until="networkidle")
        seed_storage(page)

        for label, width, height in [
            ("desktop", 1440, 900),
            ("tablet", 768, 1024),
            ("mobile", 360, 640),
        ]:
            capture_for_viewport(page, output_dir, label, width, height)

        browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Admin settings page screenshots.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output-dir", default="screenshots/010-admin-settings-page")
    parser.add_argument("--chrome-path", default="/usr/bin/google-chrome")
    parser.add_argument("--mock-api", action="store_true", help="Mock API responses for deterministic visual captures.")
    return parser.parse_args()


if __name__ == "__main__":
    capture(parse_args())
