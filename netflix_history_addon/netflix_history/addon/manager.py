"""Owns the browser, the stored history and the refresh schedule.

Playwright's sync API is bound to the thread that created it, and a login
session spans several HTTP requests, so every browser action is funnelled
through one dedicated worker thread.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from .. import engine, probe, scraper

log = logging.getLogger(__name__)

IDLE, LOGIN, SCRAPING = "idle", "login", "scraping"


@dataclass
class Options:
    scrape_interval_hours: int = 24
    date_format: str = ""
    engine: str = "chromium"
    debug_probe: bool = False

    @classmethod
    def load(cls, path: Path) -> "Options":
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
        return cls(
            scrape_interval_hours=int(raw.get("scrape_interval_hours", 24)),
            date_format=raw.get("date_format") or "",
            engine=raw.get("engine") or "chromium",
            debug_probe=bool(raw.get("debug_probe", False)),
        )


@dataclass
class Status:
    state: str = IDLE
    message: str = ""
    logged_in: bool = False
    needs_login: bool = False
    last_success: str | None = None
    last_error: str | None = None
    warning: str | None = None
    last_new: dict = field(default_factory=dict)  # entries added per profile by the last scrape
    diagnostics: dict = field(default_factory=dict)
    profiles: list[str] = field(default_factory=list)


def _write_private(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    tmp.replace(path)


class TokenStore:
    """The API bearer token. Rotating takes effect immediately, with no restart."""

    def __init__(self, value: str, path: Path | None = None):
        self.value = value
        self._path = path

    @classmethod
    def load(cls, data_dir: Path) -> "TokenStore":
        path = data_dir / "api_token"
        if path.exists() and path.read_text().strip():
            return cls(path.read_text().strip(), path)
        store = cls(secrets.token_urlsafe(32), path)
        _write_private(path, store.value)
        return store

    def rotate(self) -> str:
        new = secrets.token_urlsafe(32)
        if self._path:
            _write_private(self._path, new)  # persist first: a failed write must not leave a token only in memory
        self.value = new
        return new


def get_or_create_token(data_dir: Path) -> str:
    return TokenStore.load(data_dir).value


class Manager:
    def __init__(self, data_dir: Path, options: Options):
        self.data_dir = data_dir
        self.options = options
        self.session_dir = data_dir / "session"
        self.history_path = data_dir / "history.json"
        self.cookie_file = data_dir / "cookies.json"
        self.status = Status(logged_in=(data_dir / "logged_in").exists())
        self.history: dict = {"updated": None, "profiles": {}}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
        self._pw = None
        self._login_ctx = None
        self._busy = asyncio.Lock()
        if self.history_path.exists():
            try:
                self.history = json.loads(self.history_path.read_text())
                self.status.profiles = sorted(self.history["profiles"])
            except (OSError, ValueError, KeyError):
                log.warning("Ignoring unreadable %s", self.history_path)

    def close(self) -> None:
        self._pool.shutdown(wait=True)

    # -- helpers -----------------------------------------------------------
    def _run(self, fn, *a):
        return asyncio.get_running_loop().run_in_executor(self._pool, fn, *a)

    def _set(self, state: str, message: str = "") -> None:
        self.status.state, self.status.message = state, message

    # -- login -------------------------------------------------------------
    def _start_login(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._login_ctx = scraper.open_context(
            self._pw, self.session_dir, headless=False, args=scraper.CONTAINER_ARGS
        )
        page = self._login_ctx.pages[0] if self._login_ctx.pages else self._login_ctx.new_page()
        page.goto(f"{scraper.BASE}/login")

    def _snapshot(self, page, name: str) -> None:
        """Save what the browser saw (screenshot + page summary) so failures can be diagnosed."""
        diag_dir = self.data_dir / "diag"
        diag_dir.mkdir(exist_ok=True)
        try:
            page.screenshot(path=str(diag_dir / f"{name}.png"))
        except Exception:
            log.warning("Could not take %s screenshot", name, exc_info=True)
        self.status.diagnostics[name] = scraper.describe_page(page)

    def _finish_login(self) -> str | None:
        """Verify the login inside the browser the user just used, and keep our own copy of the cookies.

        Raises NotLoggedIn when there's no sign-in. Returns a warning when signed in but the profile
        picker wasn't recognised (so a markup change doesn't masquerade as a failed login).
        """
        ctx = self._login_ctx
        warning = None
        try:
            page = ctx.new_page()
            try:
                scraper.list_profiles(page)
            except scraper.ProfilesNotFound as e:
                warning = str(e)
            finally:
                self._snapshot(page, "login")
            cookies = ctx.cookies()
            if not any(c["name"] in scraper.LOGIN_COOKIES for c in engine.filter_cookies(cookies)):
                raise scraper.NotLoggedIn("No Netflix login cookie found.")
            # Session-only cookies would vanish when this browser closes, so keep our own copy.
            engine.save_cookies(self.cookie_file, cookies)
        finally:
            try:
                ctx.close()
            finally:
                self._login_ctx = None
                self._pw.stop()
                self._pw = None
        return warning

    async def start_login(self) -> None:
        if self._busy.locked():
            raise RuntimeError(f"Busy ({self.status.state})")
        await self._busy.acquire()
        try:
            self._set(LOGIN, "Sign in to Netflix in the browser below, then press Done.")
            await self._run(self._start_login)
        except BaseException:
            self._set(IDLE)
            self._busy.release()
            raise

    async def finish_login(self) -> None:
        if self.status.state != LOGIN:
            raise RuntimeError("No login in progress")
        try:
            self._set(LOGIN, "Checking login...")
            self.status.warning = await self._run(self._finish_login)
            (self.data_dir / "logged_in").touch()
            self.status.logged_in, self.status.needs_login, self.status.last_error = True, False, None
            self._set(IDLE, "Logged in.")
        except scraper.NotLoggedIn as e:
            (self.data_dir / "logged_in").unlink(missing_ok=True)
            self.status.logged_in = False
            self.status.last_error = f"Login not detected ({e}). See what the browser saw below."
            self._set(IDLE)
        except BaseException as e:
            self.status.last_error = f"Login check failed: {e}"
            self._set(IDLE)
        finally:
            self._busy.release()

    # -- scraping ----------------------------------------------------------
    def _scrape(self, known: dict | None = None) -> dict:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        kwargs = dict(
            date_format=self.options.date_format or None,
            on_progress=lambda m: self._set(SCRAPING, m),
            known=known,
        )
        with sync_playwright() as p:
            if self.options.engine == "obscura":
                return engine.scrape_with_obscura(
                    p, os.environ.get("OBSCURA_BIN", engine.DEFAULT_BINARY),
                    self.data_dir / "obscura", self.cookie_file, **kwargs,
                )
            # Same setup as the sign-in (visible browser on the virtual display) when one exists:
            # it's the configuration known to be accepted, and avoids the "HeadlessChrome" user agent.
            ctx = scraper.open_context(
                p, self.session_dir, headless=not os.environ.get("DISPLAY"), args=scraper.CONTAINER_ARGS
            )
            try:
                saved = engine.load_cookies(self.cookie_file)
                if saved:
                    ctx.add_cookies(saved)
                try:
                    return scraper.scrape_context(ctx, **kwargs)
                finally:
                    fresh = engine.filter_cookies(ctx.cookies())
                    if fresh:
                        engine.save_cookies(self.cookie_file, fresh)
            finally:
                ctx.close()

    def _probe(self, steps: list[dict]) -> list[dict]:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            ctx = scraper.open_context(
                p, self.session_dir, headless=not os.environ.get("DISPLAY"), args=scraper.CONTAINER_ARGS
            )
            try:
                saved = engine.load_cookies(self.cookie_file)
                if saved:
                    ctx.add_cookies(saved)
                return probe.run(ctx, steps)
            finally:
                ctx.close()

    async def probe(self, steps: list[dict]) -> list[dict]:
        """Read-only page inspection with the saved login (see probe.py). Needs `debug_probe` on."""
        if not self.options.debug_probe:
            raise PermissionError("Set the add-on option debug_probe to true to use this.")
        if not self.status.logged_in:
            raise RuntimeError("Not logged in")
        if self._busy.locked():
            raise RuntimeError(f"Busy ({self.status.state})")
        async with self._busy:
            self._set(SCRAPING, "Inspecting pages...")
            try:
                return await self._run(self._probe, steps)
            finally:
                self._set(IDLE)

    async def scrape(self, full: bool = False) -> bool:
        """Read what's new since the last scrape (everything on the first run or when `full`).

        Returns False if something else is already running.
        """
        if not self.status.logged_in:
            self.status.needs_login = True
            return False
        if self._busy.locked():
            return False
        async with self._busy:
            try:
                self._set(SCRAPING, "Starting...")
                known = None if full else (self.history.get("profiles") or None)
                before = {n: len(es) for n, es in (known or {}).items()}
                results = await self._run(self._scrape, known)
                self.status.last_new = {n: max(0, len(es) - before[n]) for n, es in results.items() if n in before}
                self.history = {
                    "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "profiles": {n: [e.asdict() for e in es] for n, es in results.items()},
                }
                tmp = self.history_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.history, ensure_ascii=False))
                tmp.replace(self.history_path)
                self.status.profiles = sorted(results)
                self.status.last_success, self.status.last_error = self.history["updated"], None
            except scraper.NotLoggedIn:
                self.status.needs_login = True
                self.status.last_error = "Netflix session expired. Open the add-on and sign in again."
            except scraper.ProfilesNotFound as e:
                self.status.last_error = str(e)
            except Exception as e:  # keep the schedule alive whatever Netflix does
                log.exception("Scrape failed")
                self.status.last_error = f"Scrape failed: {e}"
            finally:
                self._set(IDLE)
        return True

    async def scrape_in_background(self, full: bool = False) -> bool:
        if self._busy.locked() or not self.status.logged_in:
            return False
        self._task = asyncio.create_task(self.scrape(full))
        return True

    async def schedule_forever(self) -> None:
        interval = max(1, self.options.scrape_interval_hours) * 3600
        # Resume the cadence after a restart instead of scraping immediately every time.
        last = self.history.get("updated")
        wait = 0.0
        if last:
            age = time.time() - datetime.fromisoformat(last).timestamp()
            wait = max(0.0, interval - age)
        while True:
            await asyncio.sleep(wait)
            if self.status.logged_in:
                await self.scrape()
            wait = interval
