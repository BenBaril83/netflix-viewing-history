"""Incremental scraping: read only what's new, against the fake Netflix, through both engines."""
import os
import shutil

import pytest
from playwright.sync_api import sync_playwright

from netflix_history import engine, scraper

from . import fake_netflix

OBSCURA = os.environ.get("OBSCURA_BIN") or shutil.which("obscura")
COOKIE = {"name": "NetflixId", "value": "valid", "domain": "127.0.0.1", "path": "/"}


@pytest.fixture(autouse=True)
def _sockets(socket_enabled):
    pass


@pytest.fixture
def site(monkeypatch):
    fake_netflix.DELETE_HITS.clear()
    fake_netflix.MORE_HITS.clear()
    fake_netflix.NEW.clear()
    srv = fake_netflix.serve()
    monkeypatch.setattr(scraper, "BASE", f"http://127.0.0.1:{srv.server_port}")
    yield srv
    srv.shutdown()
    srv.server_close()


def run(tmp_path, known=None):
    with sync_playwright() as p:
        ctx = scraper.open_context(p, tmp_path / "s", headless=True, args=scraper.CONTAINER_ARGS)
        try:
            ctx.add_cookies([COOKIE])
            return scraper.scrape_context(ctx, pause=0.1, known=known, date_format="%y-%m-%d")
        finally:
            ctx.close()


def as_known(results):
    return {n: [e.asdict() for e in es] for n, es in results.items()}


def test_second_run_reads_only_what_is_new(site, tmp_path):
    first = run(tmp_path)
    assert {n: len(es) for n, es in first.items()} == {"Ben": 45, "Kids": 3}
    full_clicks = len(fake_netflix.MORE_HITS)
    assert full_clicks == 2  # 45 entries = first page of 20 + two "Show More"

    fake_netflix.NEW["AAA"] = 3  # three entries watched since
    fake_netflix.MORE_HITS.clear()
    second = run(tmp_path, known=as_known(first))

    assert len(second["Ben"]) == 48 and [e.title for e in second["Ben"][:3]] == ["Ben NEW 3", "Ben NEW 2", "Ben NEW 1"]
    assert [e.title for e in second["Ben"][3:]] == [e.title for e in first["Ben"]]  # old entries intact, no duplicates
    assert len(second["Kids"]) == 3
    assert fake_netflix.MORE_HITS == []  # the join was on the first page: no "Show More" needed at all
    assert fake_netflix.DELETE_HITS == []


def test_many_new_entries_page_until_the_join_appears(site, tmp_path):
    first = run(tmp_path)
    fake_netflix.NEW["AAA"] = 25  # more than one page of new entries
    fake_netflix.MORE_HITS.clear()
    second = run(tmp_path, known=as_known(first))
    assert len(second["Ben"]) == 70
    assert len(fake_netflix.MORE_HITS) == 1  # one extra page was enough to reach the join, not all three


def test_nothing_new_keeps_everything(site, tmp_path):
    first = run(tmp_path)
    fake_netflix.MORE_HITS.clear()
    second = run(tmp_path, known=as_known(first))
    assert [e.title for e in second["Ben"]] == [e.title for e in first["Ben"]] and fake_netflix.MORE_HITS == []


def test_falls_back_to_a_full_read_when_the_join_is_missing(site, tmp_path):
    first = run(tmp_path)
    stale = as_known(first)
    for e in stale["Ben"][:12]:
        e["title"] += " (changed)"  # stored history no longer matches what Netflix shows
    fake_netflix.MORE_HITS.clear()
    again = run(tmp_path, known=stale)
    assert len(again["Ben"]) == 45 and again["Ben"][0].title == first["Ben"][0].title  # replaced by a full read
    assert len(fake_netflix.MORE_HITS) == 2


@pytest.mark.skipif(not OBSCURA, reason="set OBSCURA_BIN to run the Obscura tests")
def test_obscura_incremental_matches(site, tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text('[{"name":"NetflixId","value":"valid","domain":"127.0.0.1","path":"/"}]')
    with sync_playwright() as p:
        first = engine.scrape_with_obscura(p, OBSCURA, tmp_path / "o1", cookie_file, pause=0.1)
        fake_netflix.NEW["AAA"] = 2
        fake_netflix.MORE_HITS.clear()
        second = engine.scrape_with_obscura(p, OBSCURA, tmp_path / "o2", cookie_file, pause=0.1, known=as_known(first))
    assert len(second["Ben"]) == 47 and fake_netflix.MORE_HITS == []
