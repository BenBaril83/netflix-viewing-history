"""The post-login check, against a local fake Netflix and a real Chromium."""
import pytest
from playwright.sync_api import sync_playwright

from netflix_history import engine, scraper
from netflix_history.addon.manager import Manager, Options

from . import fake_netflix

COOKIE = {"name": "NetflixId", "value": "valid", "domain": "127.0.0.1", "path": "/"}


@pytest.fixture(autouse=True)
def _sockets(socket_enabled):
    pass


@pytest.fixture
def site(monkeypatch):
    srv = fake_netflix.serve()
    monkeypatch.setattr(scraper, "BASE", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(fake_netflix, "BROKEN_GATE", False)
    monkeypatch.setattr(scraper, "PROFILES_TIMEOUT_MS", 1500)
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def mgr(tmp_path):
    m = Manager(tmp_path, Options())
    yield m
    m.close()


async def sign_in(mgr, tmp_path, cookies):
    """Do what start_login does, minus the visible window: a browser holding the given cookies."""
    def begin():
        mgr._pw = sync_playwright().start()
        mgr._login_ctx = scraper.open_context(mgr._pw, tmp_path / "session", headless=True, args=scraper.CONTAINER_ARGS)
        if cookies:
            mgr._login_ctx.add_cookies(cookies)

    await mgr._run(begin)
    mgr._set("login")
    await mgr._busy.acquire()


def page_for(site, path):
    return f"http://127.0.0.1:{site.server_port}{path}"


def test_list_profiles_distinguishes_logged_out_from_changed_markup(site, tmp_path, monkeypatch):
    with sync_playwright() as p:
        ctx = scraper.open_context(p, tmp_path / "s", headless=True, args=scraper.CONTAINER_ARGS)
        try:
            page = ctx.new_page()
            with pytest.raises(scraper.NotLoggedIn):
                scraper.list_profiles(page)  # redirected to /login

            ctx.add_cookies([COOKIE])
            monkeypatch.setattr(fake_netflix, "BROKEN_GATE", True)
            with pytest.raises(scraper.ProfilesNotFound) as e:
                scraper.list_profiles(page)
            assert "/browse" in str(e.value) and "Links seen" in str(e.value)  # URL + links, no query strings
            assert "profile=1" not in str(e.value)
        finally:
            ctx.close()


async def test_login_check_succeeds_and_keeps_cookies(site, mgr, tmp_path):
    await sign_in(mgr, tmp_path, [COOKIE])
    await mgr.finish_login()
    assert mgr.status.logged_in and mgr.status.last_error is None and mgr.status.warning is None
    assert (tmp_path / "diag" / "login.png").exists()
    assert mgr.status.diagnostics["login"]["url"].endswith("/browse")  # /ProfilesGate redirects here
    assert oct(mgr.cookie_file.stat().st_mode)[-3:] == "600"
    assert [c["name"] for c in engine.load_cookies(mgr.cookie_file)] == ["NetflixId"]


async def test_login_check_survives_unrecognised_profile_picker(site, mgr, tmp_path, monkeypatch):
    monkeypatch.setattr(fake_netflix, "BROKEN_GATE", True)
    await sign_in(mgr, tmp_path, [COOKIE])
    await mgr.finish_login()
    assert mgr.status.logged_in  # signed in; only the profile discovery is off
    assert "found no profiles" in mgr.status.warning


async def test_login_check_reports_not_signed_in(site, mgr, tmp_path):
    await sign_in(mgr, tmp_path, [])
    await mgr.finish_login()
    assert not mgr.status.logged_in and "Login not detected" in mgr.status.last_error
    assert mgr.status.diagnostics["login"]["url"].endswith("/login")  # shows where Netflix sent us
    assert mgr.status.state == "idle" and not mgr._busy.locked()


async def test_saved_cookies_restore_a_fresh_browser(site, mgr, tmp_path):
    """Session-only cookies die with the browser; the saved copy must be enough to sign a new one in."""
    await sign_in(mgr, tmp_path, [COOKIE])
    await mgr.finish_login()

    def fresh_browser():
        with sync_playwright() as p:
            ctx = scraper.open_context(p, tmp_path / "brand-new-profile", headless=True, args=scraper.CONTAINER_ARGS)
            try:
                ctx.add_cookies(engine.load_cookies(mgr.cookie_file))
                return scraper.list_profiles(ctx.new_page())
            finally:
                ctx.close()

    assert [n for n, _ in await mgr._run(fresh_browser)] == ["Ben", "Kids"]
