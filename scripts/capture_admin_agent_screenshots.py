from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


DEFAULT_CUSTOM_AGENT = {
    "id": "custom_visual_check",
    "name": "Blaine Bot",
    "description": "Be me",
    "systemPrompt": "You are a concise assistant.",
    "tools": [],
    "skills": [],
    "mcpServers": [],
    "useSearchContext": False,
    "icon": "/icons/custom.svg",
    "starters": [],
    "agentsAsTools": [],
    "source": "custom",
    "createdAt": "2026-05-06T12:00:00.000Z",
    "updatedAt": "2026-05-06T12:00:00.000Z",
}

SECONDARY_CUSTOM_AGENT = {
    "id": "custom_helper_bot",
    "name": "Helper Bot",
    "description": "A second custom agent used to demonstrate the Agents-as-Tools picker.",
    "systemPrompt": "You assist the parent agent.",
    "tools": [],
    "skills": [],
    "mcpServers": [],
    "useSearchContext": False,
    "icon": "/icons/custom.svg",
    "starters": [],
    "agentsAsTools": [],
    "source": "custom",
    "createdAt": "2026-05-07T12:00:00.000Z",
    "updatedAt": "2026-05-07T12:00:00.000Z",
}

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
            route.fulfill(json={"skills": [{"name": "visual-skill", "description": "Screenshot skill"}]})
        elif "/api/skills/visual-skill" in url and method == "GET":
            route.fulfill(json={"name": "visual-skill", "description": "Screenshot skill", "content": "# Visual Skill\n\nScreenshot skill instructions."})
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
                "session_id": "visual-session",
                "profile_id": "visual-agent",
                "profile_name": "Visual Agent",
                "tools_loaded": [],
                "skills_loaded": [],
                "search_context": False,
                "mcp_results": [],
            })
        elif url.endswith("/api/sessions/visual-session/messages") and method == "POST":
            route.fulfill(
                status=200,
                headers={"content-type": "text/event-stream"},
                body=(
                    'event: text\ndata: {"content":"Visual verification response."}\n\n'
                    'event: usage\ndata: {"input_token_count":4,"output_token_count":5,"total_token_count":9}\n\n'
                    'event: done\ndata: {}\n\n'
                ),
            )
        elif url.endswith("/api/sessions/visual-session/history"):
            route.fulfill(json={"session_id": "visual-session", "profile_id": "visual-agent", "profile_name": "Visual Agent", "session_data": {}})
        elif url.endswith("/api/mcp/test"):
            route.fulfill(json={"results": []})
        elif url.endswith("/api/skills/generate"):
            route.fulfill(json={"content": "# Visual Skill\n\nGenerated screenshot content."})
        else:
            route.continue_()

    page.route("**/api/**", handler)


def accept_disclaimer(page: Page) -> None:
    button = page.get_by_role("button", name="I UNDERSTAND AND AGREE")
    if button.count() > 0:
        button.click()


def capture_disclaimer_states(page: Page, output_dir: Path) -> None:
    content = page.locator(".disclaimer-content")
    if content.count() == 0:
        return
    page.screenshot(path=str(output_dir / "007-disclaimer-top.png"), full_page=True)
    content.evaluate("element => { element.scrollTop = element.scrollHeight; }")
    page.screenshot(path=str(output_dir / "007-disclaimer-bottom.png"), full_page=True)


def open_admin(page: Page) -> None:
    admin_button = page.locator("button.sidebar-advanced-btn").filter(has_text="ADMIN")
    admin_button.click(timeout=5_000)
    page.get_by_role("button", name="BUILT-IN AGENTS").wait_for(timeout=5_000)


def open_skills(page: Page) -> None:
    page.get_by_role("button", name="SKILLS").click(timeout=5_000)
    page.get_by_text("SAVED SKILLS").wait_for(timeout=5_000)


def capture_profile_and_chat_states(page: Page, output_dir: Path) -> None:
    page.get_by_text("SELECT YOUR AGENT").wait_for(timeout=5_000)
    page.screenshot(path=str(output_dir / "007-profile-selection.png"), full_page=True)

    page.locator(".profile-card").first.click(timeout=5_000)
    page.locator(".chat-input-textarea").wait_for(timeout=5_000)
    page.screenshot(path=str(output_dir / "007-empty-chat-starters.png"), full_page=True)

    page.locator(".chat-input-textarea").fill("Hello from visual verification")
    page.get_by_role("button", name="TRANSMIT").click(timeout=5_000)
    page.get_by_text("Visual verification response.").wait_for(timeout=5_000)
    page.screenshot(path=str(output_dir / "007-chat-one-turn.png"), full_page=True)


def ensure_expanded(page: Page, section_index: int) -> None:
    toggle = page.locator(".agent-builder-section-toggle").nth(section_index)
    if toggle.get_attribute("aria-expanded") == "false":
        toggle.click()


def ensure_collapsed(page: Page, section_index: int) -> None:
    toggle = page.locator(".agent-builder-section-toggle").nth(section_index)
    if toggle.get_attribute("aria-expanded") == "true":
        toggle.click()


def scroll_agent_layout(page: Page, position: str) -> None:
    page.evaluate(
        """
        position => {
          const layout = document.querySelector('.agent-builder-layout');
          if (!layout) return;
          layout.scrollTop = position === 'bottom' ? layout.scrollHeight : 0;
        }
        """,
        position,
    )


def panel_metrics(page: Page) -> dict[str, int]:
    return page.evaluate(
        """
        () => {
          const panel = document.querySelector('.agent-builder-saved');
          const toggle = document.querySelector('.agent-builder-section-toggle');
          return {
            panelHeight: Math.round(panel?.getBoundingClientRect().height || 0),
            toggleHeight: Math.round(toggle?.getBoundingClientRect().height || 0),
            panelWidth: Math.round(panel?.getBoundingClientRect().width || 0),
          };
        }
        """
    )


def capture_skills_states(page: Page, output_dir: Path) -> None:
    open_skills(page)
    page.screenshot(path=str(output_dir / "006-admin-skills-list.png"), full_page=True)

    page.get_by_role("button", name="NEW SKILL").click(timeout=5_000)
    page.screenshot(path=str(output_dir / "006-admin-skills-create.png"), full_page=True)

    edit_button = page.locator(".agent-builder-saved-entry").first.get_by_role("button", name="EDIT")
    if edit_button.count() > 0:
        edit_button.click(timeout=5_000)
        page.locator("#skill-content").wait_for(timeout=5_000)
        page.screenshot(path=str(output_dir / "006-admin-skills-edit.png"), full_page=True)

    delete_button = page.locator(".agent-builder-saved-entry").first.get_by_role("button", name="DELETE")
    if delete_button.count() > 0:
        delete_button.click(timeout=5_000)
        page.screenshot(path=str(output_dir / "006-admin-skills-delete-confirm.png"), full_page=True)
        page.locator(".skill-delete-confirm").get_by_role("button", name="CANCEL").click(timeout=5_000)

    page.set_viewport_size({"width": 768, "height": 1024})
    page.screenshot(path=str(output_dir / "006-admin-skills-tablet.png"), full_page=True)

    page.set_viewport_size({"width": 360, "height": 640})
    page.screenshot(path=str(output_dir / "006-admin-skills-mobile.png"), full_page=True)

    page.set_viewport_size({"width": 1440, "height": 900})


def capture(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    custom_agents = json.dumps([DEFAULT_CUSTOM_AGENT, SECONDARY_CUSTOM_AGENT])

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=args.chrome_path,
        )
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        if args.mock_api:
            setup_mock_api(page)
        page.goto(args.base_url, wait_until="networkidle")
        capture_disclaimer_states(page, output_dir)
        page.evaluate(
            "value => localStorage.setItem('webagents_custom_agents', value)",
            custom_agents,
        )
        page.reload(wait_until="networkidle")
        accept_disclaimer(page)
        capture_profile_and_chat_states(page, output_dir)
        open_admin(page)

        ensure_expanded(page, 0)
        ensure_expanded(page, 1)
        scroll_agent_layout(page, "bottom")
        page.screenshot(path=str(output_dir / "005-admin-custom-agents-expanded.png"))

        scroll_agent_layout(page, "top")
        ensure_collapsed(page, 0)
        page.screenshot(path=str(output_dir / "005-admin-builtins-collapsed-compact.png"), full_page=True)
        print({"builtInCollapsed": panel_metrics(page)})

        ensure_expanded(page, 0)
        ensure_collapsed(page, 1)
        scroll_agent_layout(page, "bottom")
        page.screenshot(path=str(output_dir / "005-admin-agents-custom-collapsed.png"), full_page=True)

        capture_agents_as_tools_states(page, output_dir)

        capture_skills_states(page, output_dir)

        browser.close()


def capture_agents_as_tools_states(page: Page, output_dir: Path) -> None:
    """Capture the new Agents-as-Tools section and the full subheader frame (T031)."""
    # The customs section may be collapsed by previous captures — expand both lists.
    ensure_expanded(page, 0)
    ensure_expanded(page, 1)
    edit_btn = page.locator(".agent-builder-saved-entry").filter(has_text="Blaine Bot").first.get_by_role("button", name="EDIT")
    if edit_btn.count() == 0:
        return
    edit_btn.click(timeout=5_000)
    page.wait_for_selector(".agent-builder-form", timeout=5_000)

    # (a) Scroll to the Agents-as-Tools section and capture it.
    page.evaluate(
        """
        () => {
          const headers = Array.from(document.querySelectorAll('.agent-builder-section-title'));
          const target = headers.find(h => h.textContent && h.textContent.trim() === 'AGENTS AS TOOLS');
          if (target) target.scrollIntoView({ block: 'center' });
        }
        """
    )
    page.screenshot(path=str(output_dir / "008-agent-builder-agents-as-tools-section.png"), full_page=False)

    # (b) Full-page capture so the seven subsection headers can be visually compared.
    page.screenshot(path=str(output_dir / "008-agent-builder-all-subheaders.png"), full_page=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Admin agent builder screenshots.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output-dir", default="screenshots")
    parser.add_argument("--chrome-path", default="/usr/bin/google-chrome")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--mock-api", action="store_true", help="Mock API responses for deterministic visual captures.")
    return parser.parse_args()


if __name__ == "__main__":
    capture(parse_args())