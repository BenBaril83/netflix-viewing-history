"""Run the same scrape through Chromium and Obscura against a local fake Netflix."""
import os
import shutil

import pytest
from playwright.sync_api import sync_playwright

from netflix_history import engine, scraper

from . import fake_netflix

OBSCURA = os.environ.get("OBSCURA_BIN") or shutil.which("obscura")
needs_obscura = pytest.mark.skipif(not OBSCURA, reason="set OBSCURA_BIN to run the Obscura tests")
COOKIE = {"name": "NetflixId", "value": "valid", "domain": "127.0.0.1", "path": "/"}


@pytest.fixture(autouse=True)
def _sockets(socket_enabled):
    pass


@pytest.fixture
def site(monkeypatch):
    fake_netflix.DELETE_HITS.clear()
    srv = fake_netflix.serve()
    monkeypatch.setattr(scraper, "BASE", f"http://127.0.0.1:{srv.server_port}")
    yield srv
    srv.shutdown()
    srv.server_close()


def test_filter_cookies_only_keeps_netflix_hosts():
    cs = [{"domain": ".netflix.com", "name": "a"}, {"domain": "netflix.com", "name": "b"},
          {"domain": ".example.com", "name": "c"}, {"domain": ".notnetflix.com", "name": "d"}]
    assert [c["name"] for c in engine.filter_cookies(cs, "https://www.netflix.com")] == ["a", "b"]


def test_cookie_file_is_private(tmp_path):
    f = tmp_path / "c.json"
    engine.save_cookies(f, [{"domain": "www.netflix.com", "name": "x", "value": "1"}])
    assert oct(f.stat().st_mode)[-3:] == "600" and engine.load_cookies(f)[0]["name"] == "x"


def check(results):
    assert {n: len(es) for n, es in results.items()} == {"Ben": 45, "Kids": 3}  # incl. the locked profile
    assert results["Ben"][44].title == "Ben title 44" and results["Ben"][0].title_id == "1000"
    assert results["Ben"][0].show == "Ben Show"
    assert fake_netflix.DELETE_HITS == []  # only "Show More" is ever clicked, never "Hide from viewing history"


def test_chromium_follows_show_more(site, tmp_path):
    with sync_playwright() as p:
        ctx = scraper.open_context(p, tmp_path / "s", headless=True, args=scraper.CONTAINER_ARGS)
        ctx.add_cookies([COOKIE])
        try:
            check(scraper.scrape_context(ctx, pause=0.1))
        finally:
            ctx.close()


@needs_obscura
def test_obscura_matches_chromium(site, tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text('[{"name":"NetflixId","value":"valid","domain":"127.0.0.1","path":"/"}]')
    with sync_playwright() as p:
        check(engine.scrape_with_obscura(p, OBSCURA, tmp_path / "obs", cookie_file, pause=0.1))


@needs_obscura
def test_obscura_without_cookies_asks_for_login(site, tmp_path):
    with sync_playwright() as p, pytest.raises(scraper.NotLoggedIn):
        engine.scrape_with_obscura(p, OBSCURA, tmp_path / "obs", tmp_path / "none.json")
