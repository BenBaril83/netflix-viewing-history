import pytest
from aiohttp.test_utils import TestClient, TestServer
from playwright.sync_api import sync_playwright

from netflix_history import probe, scraper
from netflix_history.addon.manager import Manager, Options
from netflix_history.addon.server import build_api_app, build_ingress_app

from . import fake_netflix

COOKIE = {"name": "NetflixId", "value": "valid", "domain": "127.0.0.1", "path": "/"}


@pytest.fixture(autouse=True)
def _sockets(socket_enabled):
    pass


@pytest.mark.parametrize("bad", ["https://evil.example/x", "//evil.example", "/\\evil", "evil", "/a@evil", "", None, 5])
def test_check_path_rejects_anything_but_plain_netflix_paths(bad):
    with pytest.raises(probe.ProbeError):
        probe.check_path(bad)


def test_check_path_accepts_plain_paths():
    assert probe.check_path("/account/profiles") == "/account/profiles"


def test_sanitize_html_keeps_structure_and_drops_the_rest():
    html = (
        '<div class="profile" role="button" data-uia="pick" style="background:url(secret)" onclick="x()">'
        '<a href="/SwitchProfile?tkn=SECRET">Ben</a><img src="/pic.png?sig=1"><script>steal()</script></div>'
    )
    out = probe.sanitize_html(html)
    assert 'role="button"' in out and 'data-uia="pick"' in out and 'href="/SwitchProfile"' in out
    for leaked in ("SECRET", "steal", "style=", "onclick", "<img", "sig=1"):
        assert leaked not in out
    assert len(probe.sanitize_html("<p>" + "x" * 50000 + "</p>")) == probe.MAX_HTML


def test_run_reads_a_page_and_rejects_bad_steps(monkeypatch, tmp_path):
    srv = fake_netflix.serve()
    monkeypatch.setattr(scraper, "BASE", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(fake_netflix, "BROKEN_GATE", True)
    try:
        with sync_playwright() as p:
            ctx = scraper.open_context(p, tmp_path / "s", headless=True, args=scraper.CONTAINER_ARGS)
            try:
                ctx.add_cookies([COOKIE])
                out = probe.run(ctx, [
                    {"goto": "/ProfilesGate", "wait_ms": 100},
                    {"html": "a"},
                    {"html": ".nothing-here"},
                    {"links": True},
                    {"text": True},
                ])
                assert out[0]["url"].endswith("/ProfilesGate") and out[0]["title"] == "Who is watching"
                assert out[1]["matches"] == 1 and "profile=1" not in out[1]["first"] and 'href="/browse"' in out[1]["first"]
                assert out[2] == {"html": ".nothing-here", "matches": 0, "first": None}
                assert out[3]["links"]["links"] == ["/browse"]
                assert out[4]["text"] == "Ben"
                for bad in ([{"click": "x"}], [{"goto": "https://evil.example"}], [{}] * 13, "nope"):
                    with pytest.raises(probe.ProbeError):
                        probe.run(ctx, bad)
            finally:
                ctx.close()
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def mgr(tmp_path):
    m = Manager(tmp_path, Options())
    m.status.logged_in = True
    yield m
    m.close()


AUTH = {"Authorization": "Bearer t"}


async def test_probe_is_off_by_default(mgr):
    with pytest.raises(PermissionError):
        await mgr.probe([{"text": True}])
    async with TestClient(TestServer(build_api_app(mgr, "t"))) as c:
        assert (await c.post("/api/debug/probe", headers=AUTH, json={"steps": [{"text": True}]})).status == 403


async def test_probe_endpoint_when_enabled(mgr, monkeypatch):
    mgr.options.debug_probe = True
    monkeypatch.setattr(mgr, "_probe", lambda steps: [{"echo": steps}])
    async with TestClient(TestServer(build_api_app(mgr, "t"))) as c:
        r = await c.post("/api/debug/probe", headers=AUTH, json={"steps": [{"text": True}]})
        assert r.status == 200 and (await r.json())["results"] == [{"echo": [{"text": True}]}]
        assert mgr.status.state == "idle"
        monkeypatch.setattr(mgr, "_probe", lambda steps: probe.run(None, steps))  # real validation, no browser needed
        assert (await c.post("/api/debug/probe", headers=AUTH, json={"steps": "nope"})).status == 400
        assert (await c.post("/api/debug/probe", headers=AUTH, data="not json")).status == 400
    mgr.status.logged_in = False
    with pytest.raises(RuntimeError):
        await mgr.probe([])


async def test_probe_requires_the_api_token_and_is_not_on_ingress(mgr):
    mgr.options.debug_probe = True
    async with TestClient(TestServer(build_api_app(mgr, "t"))) as c:
        assert (await c.post("/api/debug/probe", json={"steps": []})).status == 401
        assert (await c.post("/api/debug/probe", headers={"Authorization": "Bearer nope"}, json={"steps": []})).status == 401
    async with TestClient(TestServer(build_ingress_app(mgr, "t", dev=True))) as c:
        assert (await c.post("/debug/probe", json={"steps": []})).status in (404, 405)
