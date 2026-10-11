import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from netflix_history import scraper
from netflix_history.addon.manager import Manager, Options, get_or_create_token
from netflix_history.addon.server import build_api_app, build_ingress_app
from netflix_history.parse import Entry


@pytest.fixture(autouse=True)
def _sockets(socket_enabled):
    pass


def entry(title, date="2026-10-09"):
    return Entry("Ben", "10/9/26", date, title, "1", None)


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    m = Manager(tmp_path, Options())
    m.status.logged_in = True
    monkeypatch.setattr(m, "_scrape", lambda: {"Ben": [entry("A"), entry("B")], "Kids": []})
    yield m
    m.close()


async def test_scrape_persists_and_reloads(mgr, tmp_path):
    assert await mgr.scrape()
    assert mgr.status.profiles == ["Ben", "Kids"] and mgr.status.last_error is None
    saved = json.loads((tmp_path / "history.json").read_text())
    assert [e["title"] for e in saved["profiles"]["Ben"]] == ["A", "B"]
    m2 = Manager(tmp_path, Options())
    assert m2.status.profiles == ["Ben", "Kids"]
    m2.close()


async def test_scrape_requires_login(mgr):
    mgr.status.logged_in = False
    assert not await mgr.scrape() and mgr.status.needs_login


async def test_expired_session_flags_relogin(mgr, monkeypatch):
    def boom():
        raise scraper.NotLoggedIn()
    monkeypatch.setattr(mgr, "_scrape", boom)
    await mgr.scrape()
    assert mgr.status.needs_login and "expired" in mgr.status.last_error
    assert mgr.status.state == "idle"


async def test_other_failure_keeps_old_history(mgr, monkeypatch):
    await mgr.scrape()
    monkeypatch.setattr(mgr, "_scrape", lambda: (_ for _ in ()).throw(RuntimeError("netflix broke")))
    await mgr.scrape()
    assert "netflix broke" in mgr.status.last_error and len(mgr.history["profiles"]["Ben"]) == 2


async def test_api_requires_token(mgr):
    async with TestClient(TestServer(build_api_app(mgr, "secret"))) as c:
        assert (await c.get("/api/history")).status == 401
        assert (await c.get("/api/history", headers={"Authorization": "Bearer nope"})).status == 401
        r = await c.get("/api/history", headers={"Authorization": "Bearer secret"})
        assert r.status == 200 and (await r.json())["status"]["logged_in"]


async def test_api_scrape_is_async_and_rejects_overlap(mgr, monkeypatch):
    gate = asyncio.Event()
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(mgr, "_scrape", lambda: asyncio.run_coroutine_threadsafe(gate.wait(), loop).result() or {})
    h = {"Authorization": "Bearer t"}
    async with TestClient(TestServer(build_api_app(mgr, "t"))) as c:
        assert (await c.post("/api/scrape", headers=h)).status == 202
        await asyncio.sleep(0.05)
        assert (await c.post("/api/scrape", headers=h)).status == 409
        gate.set()
        await mgr._task


async def test_ingress_rejects_non_supervisor_and_shows_token(mgr):
    async with TestClient(TestServer(build_ingress_app(mgr, "tok123", dev=False))) as c:
        assert (await c.get("/")).status == 403  # peer is 127.0.0.1, not the Supervisor
    async with TestClient(TestServer(build_ingress_app(mgr, "tok123", dev=True))) as c:
        assert "tok123" in await (await c.get("/")).text()


def test_token_is_stable_and_private(tmp_path):
    t = get_or_create_token(tmp_path)
    assert t == get_or_create_token(tmp_path) and len(t) > 30
    assert oct((tmp_path / "api_token").stat().st_mode)[-3:] == "600"
