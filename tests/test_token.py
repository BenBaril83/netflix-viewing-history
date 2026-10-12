import pytest
from aiohttp.test_utils import TestClient, TestServer

from netflix_history.addon.manager import Manager, Options, TokenStore, get_or_create_token
from netflix_history.addon.server import build_api_app, build_ingress_app


@pytest.fixture(autouse=True)
def _sockets(socket_enabled):
    pass


@pytest.fixture
def mgr(tmp_path):
    m = Manager(tmp_path, Options())
    yield m
    m.close()


def test_store_creates_loads_and_rotates_privately(tmp_path):
    store = TokenStore.load(tmp_path)
    assert len(store.value) > 30 and oct((tmp_path / "api_token").stat().st_mode)[-3:] == "600"
    assert TokenStore.load(tmp_path).value == store.value == get_or_create_token(tmp_path)  # stable across restarts

    old = store.value
    new = store.rotate()
    assert new != old and store.value == new
    assert (tmp_path / "api_token").read_text() == new and oct((tmp_path / "api_token").stat().st_mode)[-3:] == "600"
    assert TokenStore.load(tmp_path).value == new  # survives a restart


def test_failed_write_leaves_the_old_token_in_force(tmp_path):
    store = TokenStore.load(tmp_path)
    old = store.value
    (tmp_path / "api_token").unlink()
    (tmp_path / "api_token").mkdir()  # makes the replace fail
    with pytest.raises(OSError):
        store.rotate()
    assert store.value == old


async def test_rotation_takes_effect_immediately_on_the_running_api(mgr, tmp_path):
    store = TokenStore.load(tmp_path)
    old = store.value
    async with TestClient(TestServer(build_api_app(mgr, store))) as api, \
            TestClient(TestServer(build_ingress_app(mgr, store, dev=True))) as ingress:
        assert (await api.get("/api/history", headers={"Authorization": f"Bearer {old}"})).status == 200

        r = await ingress.post("/token/rotate")
        new = (await r.json())["token"]
        assert r.status == 200 and new != old

        assert (await api.get("/api/history", headers={"Authorization": f"Bearer {old}"})).status == 401
        assert (await api.get("/api/history", headers={"Authorization": f"Bearer {new}"})).status == 200
        assert new in await (await ingress.get("/")).text() and old not in await (await ingress.get("/")).text()


async def test_rotation_is_ingress_only(mgr):
    store = TokenStore("secret")
    async with TestClient(TestServer(build_api_app(mgr, store))) as api:
        r = await api.post("/api/token/rotate", headers={"Authorization": "Bearer secret"})
        assert r.status in (404, 405) and store.value == "secret"  # not reachable with the token itself
    async with TestClient(TestServer(build_ingress_app(mgr, store, dev=False))) as ingress:
        assert (await ingress.post("/token/rotate")).status == 403 and store.value == "secret"
