from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from .parse import Entry, parse_entries, parse_profiles

# Overridable so tests can point the scraper at a local fake site.
BASE = os.environ.get("NETFLIX_BASE_URL", "https://www.netflix.com")
SHOW_MORE = re.compile(r"show more", re.I)
# Chromium refuses to start as root (i.e. in a container) without this.
CONTAINER_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]


# Cookies that mean "this browser is signed in" (names only; values are never logged).
LOGIN_COOKIES = ("NetflixId", "SecureNetflixId")


class NotLoggedIn(Exception):
    """The saved session has no usable Netflix login."""


class ProfilesNotFound(Exception):
    """Signed in, but the profile picker didn't look like we expected (markup changed?)."""


def describe_page(page: Page, limit: int = 15) -> dict:
    """What the browser is looking at, for diagnostics. Query strings are dropped (they hold tokens)."""
    try:
        hrefs = page.eval_on_selector_all(
            "a[href]", "els => els.map(a => a.getAttribute('href'))"
        )
        text = page.inner_text("body")[:300]
    except Exception:
        hrefs, text = [], ""
    seen, links = set(), []
    for h in hrefs:
        h = (h or "").split("?")[0]
        if h and h not in seen:
            seen.add(h)
            links.append(h)
    return {"url": page.url.split("?")[0], "title": page.title(), "text": " ".join(text.split()), "links": links[:limit]}


def open_context(p: Playwright, session_dir: Path, headless: bool, args: list[str] | None = None) -> BrowserContext:
    # A persistent profile keeps the login cookies between runs.
    return p.chromium.launch_persistent_context(
        str(session_dir),
        headless=headless,
        args=args or [],
        locale="en-US",
        no_viewport=not headless,
        executable_path=os.environ.get("NETFLIX_CHROMIUM_PATH") or None,
    )


def login(session_dir: Path) -> None:
    """Open a visible browser so the user can sign in themselves (MFA, captcha, etc.)."""
    with sync_playwright() as p:
        ctx = open_context(p, session_dir, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{BASE}/login")
        print("Sign in to Netflix in the browser window, then press Enter here...")
        input()
        ctx.close()


PROFILES_TIMEOUT_MS = 15000


def list_profiles(page: Page) -> list[tuple[str, str]]:
    page.goto(f"{BASE}/ProfilesGate", wait_until="domcontentloaded")
    if "/login" in page.url:  # logged out: no point waiting for a picker that won't come
        raise NotLoggedIn("Netflix sent us to the login page.")
    try:
        page.wait_for_selector("a[href*='tkn=']", timeout=PROFILES_TIMEOUT_MS)
    except Exception:
        info = describe_page(page)
        if "/login" in info["url"]:
            raise NotLoggedIn("Netflix sent us to the login page.") from None
        raise ProfilesNotFound(
            f"Signed in, but found no profiles on {info['url']} (title {info['title']!r}). "
            f"Links seen: {info['links']}"
        ) from None
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


def scrape_context(
    ctx: BrowserContext,
    only: list[str] | None = None,
    date_format: str | None = None,
    pause: float = 1.0,
    on_progress: Callable[[str], None] = print,
) -> dict[str, list[Entry]]:
    results: dict[str, list[Entry]] = {}
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    profiles = list_profiles(page)
    wanted = {n.lower() for n in only} if only else None
    todo = [(n, t) for n, t in profiles if not wanted or n.lower() in wanted]
    for i, (name, token) in enumerate(todo, 1):
        on_progress(f"[{name}] switching profile ({i}/{len(todo)})")
        page.goto(f"{BASE}/SwitchProfile?tkn={token}", wait_until="domcontentloaded")
        page.goto(f"{BASE}/viewingactivity", wait_until="domcontentloaded")
        page.wait_for_selector("li.retableRow, .structural", timeout=20000)
        _expand_all(page, pause)
        entries = parse_entries(page.content(), name, date_format)
        on_progress(f"[{name}] {len(entries)} entries")
        results[name] = entries
    return results


def scrape(
    session_dir: Path,
    only: list[str] | None = None,
    headless: bool = True,
    date_format: str | None = None,
    pause: float = 1.0,
) -> dict[str, list[Entry]]:
    with sync_playwright() as p:
        ctx = open_context(p, session_dir, headless)
        try:
            return scrape_context(ctx, only, date_format, pause)
        finally:
            ctx.close()
