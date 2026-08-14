"""Capture agent dynamic UI pane screenshots for the Visual Verification Protocol.

Runs against a mocked API so the captures are deterministic and no model call is
needed: the mocked chat stream emits a real ``agent_view`` SSE event, and the
mocked view endpoints return either a demo dashboard or the isolation probe from
scripts/agent_view_isolation_probe.html.

    uv run python scripts/capture_agent_view_screenshots.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

PROFILE = {
    "id": "visual-agent",
    "name": "Visual Agent",
    "description": "Screenshot verification profile",
    "icon": "/favicon.png",
    "starters": [{"label": "Show a view", "message": "Show me a readiness view."}],
}

DEMO_VIEW_HTML = """
<h3 style="margin:0 0 12px">Unit readiness</h3>
<table style="width:100%;border-collapse:collapse">
  <thead>
    <tr style="text-align:left;border-bottom:1px solid var(--border)">
      <th style="padding:6px 4px">Unit</th><th style="padding:6px 4px">Status</th><th style="padding:6px 4px">Open items</th>
    </tr>
  </thead>
  <tbody>
    <tr><td style="padding:6px 4px">Alpha</td><td style="padding:6px 4px;color:#107c10">READY</td><td style="padding:6px 4px">0</td></tr>
    <tr><td style="padding:6px 4px">Bravo</td><td style="padding:6px 4px;color:#8a6d00">PARTIAL</td><td style="padding:6px 4px">3</td></tr>
    <tr><td style="padding:6px 4px">Charlie</td><td style="padding:6px 4px;color:#a4262c">NOT READY</td><td style="padding:6px 4px">7</td></tr>
  </tbody>
</table>
<button id="refresh" style="margin-top:16px;padding:6px 12px">Refresh</button>
<pre id="out" style="margin-top:12px;color:var(--muted)"></pre>
<script>
  document.getElementById('refresh').addEventListener('click', function () {
    window.agentData('get_user_profile', {})
      .then(function (d) { document.getElementById('out').textContent = 'data: ' + d; })
      .catch(function (e) { document.getElementById('out').textContent = 'refused: ' + e.code; });
  });
</script>
"""

SECOND_VIEW_HTML = '<h3 style="margin:0">Open items by owner</h3><p>Three items assigned to Bravo.</p>'

VIEW_SUMMARIES = [
    {"viewId": "view-1", "title": "Unit readiness", "createdAt": "2026-08-14T10:00:00Z", "chars": 900, "source": "chat"},
    {"viewId": "view-2", "title": "Open items by owner", "createdAt": "2026-08-14T10:05:00Z", "chars": 120, "source": "autonomous"},
]

SSE_WITH_VIEW = (
    'event: text\ndata: {"content":"Here is the readiness view."}\n\n'
    'event: function_call\ndata: {"call_id":"call-1","name":"render_agent_view","arguments":"{}"}\n\n'
    'event: function_result\ndata: {"call_id":"call-1","result":"{\\"status\\": \\"rendered\\", '
    '\\"view_id\\": \\"view-1\\", \\"title\\": \\"Unit readiness\\", \\"chars\\": 900}"}\n\n'
    'event: agent_view\ndata: {"view_id":"view-1","title":"Unit readiness","call_id":"call-1",'
    '"created_at":"2026-08-14T10:00:00Z"}\n\n'
    'event: usage\ndata: {"input_token_count":4,"output_token_count":5,"total_token_count":9}\n\n'
    'event: done\ndata: {}\n\n'
)


def setup_mock_api(page: Page, probe_html: str, mode: dict) -> None:
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
            route.fulfill(json={"profiles": [PROFILE], "unavailable": []})
        elif url.endswith("/api/tools"):
            route.fulfill(json={
                "tools": [{"name": "render_agent_view", "description": "Show a rich HTML view."}],
                "unavailable": [],
                "search_context_available": True,
                "search_context_reason": None,
            })
        elif url.endswith("/api/skills") and method == "GET":
            route.fulfill(json={"skills": []})
        elif url.endswith("/api/conversations"):
            route.fulfill(json={"conversations": [], "nextCursor": None})
        elif "/api/autonomous/directives" in url and method == "GET":
            route.fulfill(json={
                "enabled": True,
                "schedulerEnabled": True,
                "profileId": "visual-agent",
                "directives": [{
                    "id": "duty-officer",
                    "name": "Duty Officer",
                    "profileId": "visual-agent",
                    "prompt": "Report anything that needs attention.",
                    "schedule": "0 7 * * *",
                    "enabled": True,
                    "notify": [],
                    "source": "config",
                }],
            })
        elif "/api/autonomous/runs" in url:
            route.fulfill(json={"runs": []})
        elif url.endswith("/api/sessions") and method == "POST":
            route.fulfill(json={
                "session_id": "visual-session",
                "profile_id": "visual-agent",
                "profile_name": "Visual Agent",
                "tools_loaded": ["render_agent_view"],
                "skills_loaded": [],
                "search_context": False,
                "mcp_results": [],
            })
        elif url.endswith("/api/sessions/visual-session/messages") and method == "POST":
            route.fulfill(
                status=200,
                headers={"content-type": "text/event-stream"},
                body=SSE_WITH_VIEW,
            )
        elif url.endswith("/api/sessions/visual-session/views"):
            route.fulfill(json={"views": VIEW_SUMMARIES})
        elif "/views/view-1" in url and url.endswith("/data"):
            route.fulfill(
                status=403,
                json={"ok": False, "error": {"code": "not_permitted", "message": "That data is not available to this view."}},
            )
        elif url.endswith("/views/view-1"):
            if mode["view"] == "error":
                route.fulfill(status=500, json={"detail": "boom"})
            else:
                html = probe_html if mode["view"] == "probe" else DEMO_VIEW_HTML
                route.fulfill(json={
                    "viewId": "view-1", "title": "Unit readiness",
                    "createdAt": "2026-08-14T10:00:00Z", "chars": len(html),
                    "source": "chat", "html": html,
                })
        elif url.endswith("/views/view-2"):
            route.fulfill(json={
                "viewId": "view-2", "title": "Open items by owner",
                "createdAt": "2026-08-14T10:05:00Z", "chars": len(SECOND_VIEW_HTML),
                "source": "autonomous", "html": SECOND_VIEW_HTML,
            })
        else:
            route.continue_()

    page.route("**/api/**", handler)


def accept_disclaimer(page: Page) -> None:
    button = page.get_by_role("button", name="I UNDERSTAND AND AGREE")
    if button.count() > 0:
        button.click()


def start_chat_and_render(page: Page) -> None:
    page.get_by_text("SELECT YOUR AGENT").wait_for(timeout=5_000)
    # Not `.profile-card` first: the Duty Officer sentinel card sorts ahead of it
    # and routes to the autonomous console instead of a chat session.
    page.locator(".profile-card").filter(has_text="Visual Agent").first.click(timeout=5_000)
    page.locator(".chat-input-textarea").wait_for(timeout=5_000)
    page.locator(".chat-input-textarea").fill("Show me a readiness view")
    page.get_by_role("button", name="TRANSMIT").click(timeout=5_000)
    page.locator(".agent-view-pane").wait_for(timeout=5_000)


def capture_duty_officer(page: Page, output_dir: Path) -> None:
    """The Duty Officer console renders views too, so unattended output is visible there."""
    page.get_by_text("SELECT YOUR AGENT").wait_for(timeout=5_000)
    page.locator(".profile-card").filter(has_text="Duty Officer").first.click(timeout=5_000)
    page.locator(".auto-chat").wait_for(timeout=5_000)
    page.locator(".chat-input-textarea").fill("What happened overnight?")
    page.get_by_role("button", name="TRANSMIT").click(timeout=5_000)
    page.locator(".agent-view-pane").wait_for(timeout=5_000)
    page.wait_for_timeout(800)
    page.screenshot(path=str(output_dir / "016-agent-view-duty-officer.png"))


def capture(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    probe_html = Path(__file__).with_name("agent_view_isolation_probe.html").read_text()
    mode = {"view": "demo"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.chrome_path)
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        setup_mock_api(page, probe_html, mode)
        page.goto(args.base_url, wait_until="networkidle")
        accept_disclaimer(page)

        start_chat_and_render(page)
        page.wait_for_timeout(600)
        page.screenshot(path=str(output_dir / "016-agent-view-pane-open.png"))

        # View switcher (two stored views, one from an unattended run).
        page.locator(".agent-view-tab").nth(1).click(timeout=5_000)
        page.wait_for_timeout(400)
        page.screenshot(path=str(output_dir / "016-agent-view-switcher.png"))
        page.locator(".agent-view-tab").nth(0).click(timeout=5_000)
        page.wait_for_timeout(400)

        # Refusal surfaced inside the view.
        frame = page.frame_locator(".agent-view-frame")
        frame.locator("#refresh").click(timeout=5_000)
        page.wait_for_timeout(600)
        page.screenshot(path=str(output_dir / "016-agent-view-refusal.png"))

        # Collapsed pane with the reopen affordance.
        page.locator(".agent-view-close").click(timeout=5_000)
        page.wait_for_timeout(300)
        page.screenshot(path=str(output_dir / "016-agent-view-pane-closed.png"))
        page.locator(".agent-view-reopen").click(timeout=5_000)
        page.wait_for_timeout(400)

        # Isolation probes.
        mode["view"] = "probe"
        page.locator(".agent-view-tab").nth(1).click(timeout=5_000)
        page.locator(".agent-view-tab").nth(0).click(timeout=5_000)
        page.wait_for_timeout(1_200)
        page.screenshot(path=str(output_dir / "016-agent-view-isolation-probes.png"))
        probes = page.frame_locator(".agent-view-frame").locator("[data-probe]")
        results = {
            probes.nth(i).get_attribute("data-probe"): probes.nth(i).get_attribute("data-blocked")
            for i in range(probes.count())
        }
        print(json.dumps({"isolationProbes": results}, indent=2))

        # Error state.
        mode["view"] = "error"
        page.locator(".agent-view-tab").nth(1).click(timeout=5_000)
        page.locator(".agent-view-tab").nth(0).click(timeout=5_000)
        page.wait_for_timeout(600)
        page.screenshot(path=str(output_dir / "016-agent-view-error-state.png"))

        # Responsive layouts. The app decides sidebar state at mount, so each
        # viewport is reloaded rather than resized, which is what a real user at
        # that size actually sees.
        mode["view"] = "demo"
        for name, size in (
            ("tablet", {"width": 768, "height": 1024}),
            ("mobile", {"width": 360, "height": 640}),
        ):
            page.set_viewport_size(size)
            page.goto(args.base_url, wait_until="networkidle")
            accept_disclaimer(page)
            start_chat_and_render(page)
            page.wait_for_timeout(800)
            page.screenshot(path=str(output_dir / f"016-agent-view-{name}.png"))

        page.set_viewport_size({"width": args.width, "height": args.height})
        page.goto(args.base_url, wait_until="networkidle")
        accept_disclaimer(page)
        capture_duty_officer(page, output_dir)
        browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture agent dynamic UI pane screenshots.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output-dir", default="screenshots")
    parser.add_argument("--chrome-path", default="/usr/bin/google-chrome")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    return parser.parse_args()


if __name__ == "__main__":
    capture(parse_args())
