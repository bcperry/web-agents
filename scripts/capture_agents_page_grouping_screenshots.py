"""Capture screenshots of the agents page with grouped/paginated layout."""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--out-dir", default="screenshots/009-agents-page-grouping")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.chrome)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Navigate to the app
        page.goto(args.base_url, wait_until="networkidle")

        # Try to dismiss any disclaimer overlay if present (click ACKNOWLEDGE/ACCEPT button)
        try:
            page.wait_for_selector("button", timeout=3000)
            for label in ["ACKNOWLEDGE", "ACCEPT", "AGREE", "CONTINUE", "I AGREE"]:
                btn = page.query_selector(f"button:has-text('{label}')")
                if btn:
                    btn.click()
                    page.wait_for_timeout(500)
                    break
        except Exception:
            pass

        # Wait for profile selector to render
        page.wait_for_selector(".profile-selector", timeout=10000)
        page.wait_for_timeout(500)

        # 1. Initial grouped view
        page.screenshot(path=str(out_dir / "01-grouped-default.png"), full_page=True)
        print(f"Saved {out_dir / '01-grouped-default.png'}")

        # 2. Collapse the General Staff group
        toggle = page.query_selector("button.profile-selector-group-toggle:has-text('GENERAL STAFF')")
        if toggle:
            toggle.click()
            page.wait_for_timeout(300)
            page.screenshot(path=str(out_dir / "02-general-staff-collapsed.png"), full_page=True)
            print(f"Saved {out_dir / '02-general-staff-collapsed.png'}")
            toggle.click()  # re-expand
            page.wait_for_timeout(300)

        # 3. Hover state on first card (best effort)
        first_card = page.query_selector(".profile-card")
        if first_card:
            first_card.hover()
            page.wait_for_timeout(300)
            page.screenshot(path=str(out_dir / "03-card-hover.png"), full_page=True)
            print(f"Saved {out_dir / '03-card-hover.png'}")

        browser.close()


if __name__ == "__main__":
    main()
