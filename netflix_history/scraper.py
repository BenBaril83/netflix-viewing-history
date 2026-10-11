from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from .parse import Entry, parse_entries, parse_profiles

BASE = "https://www.netflix.com"
SHOW_MORE = re.compile(r"show more", re.I)


def _context(p, session_dir: Path, headless: bool):
    # A persistent profile keeps the login cookies between runs.
    return p.chromium.launch_persistent_context(str(session_dir), headless=headless)


def login(session_dir: Path) -> None:
    """Open a visible browser so the user can sign in themselves (MFA, captcha, etc.)."""
    with sync_playwright() as p:
        ctx = _context(p, session_dir, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{BASE}/login")
        print("Sign in to Netflix in the browser window, then press Enter here...")
        input()
        ctx.close()


def _list_profiles(page: Page) -> list[tuple[str, str]]:
    page.goto(f"{BASE}/ProfilesGate", wait_until="domcontentloaded")
    try:
        page.wait_for_selector("a[href*='tkn=']", timeout=15000)
    except Exception:
        raise SystemExit(
            "Could not find any profiles. You're probably not logged in "
            "(run `netflix-history login`) or Netflix changed its markup."
        )
    return parse_profiles(page.content())


def _expand_all(page: Page, pause: float) -> None:
    while True:
        btn = page.get_by_role("button", name=SHOW_MORE)
        if btn.count() == 0 or not btn.first.is_enabled():
            return
        before = page.locator("li.retableRow").count()
        btn.first.click()
        # Wait for new rows, but give up quietly if the list didn't grow.
        deadline = time.time() + 10
        while time.time() < deadline and page.locator("li.retableRow").count() == before:
            time.sleep(0.25)
        time.sleep(pause)
        if page.locator("li.retableRow").count() == before:
            return


def scrape(
    session_dir: Path,
    only: list[str] | None = None,
    headless: bool = True,
    date_format: str | None = None,
    pause: float = 1.0,
) -> dict[str, list[Entry]]:
    results: dict[str, list[Entry]] = {}
    with sync_playwright() as p:
        ctx = _context(p, session_dir, headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        profiles = _list_profiles(page)
        wanted = {n.lower() for n in only} if only else None
        for name, token in profiles:
            if wanted and name.lower() not in wanted:
                continue
            print(f"[{name}] switching profile")
            page.goto(f"{BASE}/SwitchProfile?tkn={token}", wait_until="domcontentloaded")
            page.goto(f"{BASE}/viewingactivity", wait_until="domcontentloaded")
            page.wait_for_selector("li.retableRow, .structural", timeout=20000)
            _expand_all(page, pause)
            entries = parse_entries(page.content(), name, date_format)
            print(f"[{name}] {len(entries)} entries")
            results[name] = entries
        ctx.close()
    return results
