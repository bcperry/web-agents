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
    "source": "custom",
    "createdAt": "2026-05-06T12:00:00.000Z",
    "updatedAt": "2026-05-06T12:00:00.000Z",
}


def accept_disclaimer(page: Page) -> None:
    button = page.get_by_role("button", name="I UNDERSTAND AND AGREE")
    if button.count() > 0:
        button.click()


def open_admin(page: Page) -> None:
    admin_button = page.locator("button.sidebar-advanced-btn").filter(has_text="ADMIN")
    admin_button.click(timeout=5_000)
    page.get_by_text("BUILT-IN AGENTS").wait_for(timeout=5_000)


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


def capture(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    custom_agents = json.dumps([DEFAULT_CUSTOM_AGENT])

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=args.chrome_path,
        )
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.goto(args.base_url, wait_until="networkidle")
        page.evaluate(
            "value => localStorage.setItem('webagents_custom_agents', value)",
            custom_agents,
        )
        page.reload(wait_until="networkidle")
        accept_disclaimer(page)
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

        browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Admin agent builder screenshots.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output-dir", default="screenshots")
    parser.add_argument("--chrome-path", default="/usr/bin/google-chrome")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    return parser.parse_args()


if __name__ == "__main__":
    capture(parse_args())