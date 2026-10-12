"""Optional Obscura engine (https://github.com/h4ckf0r0day/obscura).

Obscura is a headless-only browser with a CDP server, so it can't host the
interactive sign-in. Login stays in Chromium; the session cookies are copied
across and Obscura only does the scraping.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from . import scraper

DEFAULT_BINARY = "/usr/local/bin/obscura"


def filter_cookies(cookies: list[dict], base_url: str | None = None) -> list[dict]:
    """Keep only cookies that belong to the Netflix host, never anything else in the jar."""
    host = urlparse(base_url or scraper.BASE).hostname or ""
    return [
        c for c in cookies
        if c.get("domain") and (host == c["domain"].lstrip(".") or host.endswith("." + c["domain"].lstrip(".")))
    ]


def save_cookies(path: Path, cookies: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(filter_cookies(cookies), f)
    tmp.replace(path)


def load_cookies(path: Path) -> list[dict]:
    try:
        return filter_cookies(json.loads(path.read_text()))
    except (OSError, ValueError):
        return []


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def obscura_server(binary: str, storage_dir: Path, allow_private: bool = False) -> Iterator[str]:
    """Run `obscura serve` on loopback and yield its CDP endpoint."""
    port = _free_port()
    storage_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        ready = Path(tmp) / "ready"
        cmd = [binary, "serve", "--host", "127.0.0.1", "--port", str(port),
               "--storage-dir", str(storage_dir), "--ready-file", str(ready), "--quiet"]
        if allow_private:
            cmd.append("--allow-private-network")
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.time() + 30
            while not ready.exists():
                if proc.poll() is not None:
                    raise RuntimeError(f"obscura exited early: {proc.stderr.read().decode(errors='replace')[:500]}")
                if time.time() > deadline:
                    raise RuntimeError("obscura did not become ready in 30s")
                time.sleep(0.1)
            yield f"ws://127.0.0.1:{port}"
        finally:
            proc.terminate()  # SIGTERM: Obscura flushes its cookie jar on clean exit
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def scrape_with_obscura(
    p, binary: str, storage_dir: Path, cookie_file: Path, **scrape_kwargs
) -> dict:
    """Scrape through Obscura using cookies from the Chromium login.

    Cookies Netflix rotates during the run are written back to `cookie_file`.
    """
    allow_private = urlparse(scraper.BASE).hostname in ("127.0.0.1", "localhost")
    with obscura_server(binary, storage_dir, allow_private) as endpoint:
        browser = p.chromium.connect_over_cdp(endpoint)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            cookies = load_cookies(cookie_file)
            if not cookies:
                raise scraper.NotLoggedIn("No saved Netflix cookies; sign in again.")
            ctx.add_cookies(cookies)
            try:
                return scraper.scrape_context(ctx, **scrape_kwargs)
            finally:
                fresh = filter_cookies(ctx.cookies())
                if fresh:
                    save_cookies(cookie_file, fresh)
        finally:
            browser.close()
