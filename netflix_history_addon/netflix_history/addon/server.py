"""Two HTTP apps: the ingress UI (sidebar panel) and the token-protected API."""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import socket
from dataclasses import asdict
from pathlib import Path

import aiohttp
from aiohttp import web

from .. import probe
from .manager import Manager

INGRESS_PEER = ipaddress.ip_address("172.30.32.2")  # the Supervisor
VNC_PORT = 5900
NOVNC_DIR = Path("/usr/share/novnc")
UI = Path(__file__).with_name("ui.html")


@web.middleware
async def ingress_only(request: web.Request, handler):
    peer = request.transport.get_extra_info("peername") if request.transport else None
    if not request.app["dev"] and (not peer or ipaddress.ip_address(peer[0]) != INGRESS_PEER):
        raise web.HTTPForbidden()
    return await handler(request)


def build_ingress_app(mgr: Manager, token: str, dev: bool = False) -> web.Application:
    app = web.Application(middlewares=[ingress_only])
    app["dev"] = dev

    async def index(_):
        html = UI.read_text().replace("__TOKEN__", token).replace("__HOST__", socket.gethostname())
        return web.Response(text=html, content_type="text/html")

    async def status(_):
        return web.json_response(asdict(mgr.status))

    async def action(fn):
        try:
            await fn()
        except RuntimeError as e:
            raise web.HTTPConflict(text=str(e))
        return web.json_response(asdict(mgr.status))

    async def diag_png(request: web.Request):
        path = mgr.data_dir / "diag" / f"{request.match_info['name']}.png"
        if request.match_info["name"] != "login" or not path.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Cache-Control": "no-store"})

    async def login_start(_):
        return await action(mgr.start_login)

    async def login_finish(_):
        return await action(mgr.finish_login)

    async def scrape(_):
        return web.json_response({"started": await mgr.scrape_in_background()})

    async def websockify(request: web.Request):
        """Bridge the noVNC websocket to the local x11vnc TCP socket."""
        ws = web.WebSocketResponse(protocols=["binary"])
        await ws.prepare(request)
        reader, writer = await asyncio.open_connection("127.0.0.1", VNC_PORT)

        async def to_client():
            while data := await reader.read(65536):
                await ws.send_bytes(data)
            await ws.close()

        pump = asyncio.create_task(to_client())
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    writer.write(msg.data)
                    await writer.drain()
        finally:
            pump.cancel()
            writer.close()
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/status", status)
    app.router.add_get("/diag/{name}.png", diag_png)
    app.router.add_post("/login/start", login_start)
    app.router.add_post("/login/finish", login_finish)
    app.router.add_post("/scrape", scrape)
    app.router.add_get("/websockify", websockify)
    if NOVNC_DIR.is_dir():
        app.router.add_static("/novnc/", NOVNC_DIR)
    return app


def build_api_app(mgr: Manager, token: str) -> web.Application:
    @web.middleware
    async def auth(request: web.Request, handler):
        given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given, token):
            raise web.HTTPUnauthorized()
        return await handler(request)

    app = web.Application(middlewares=[auth])

    async def history(_):
        return web.json_response({"status": asdict(mgr.status), **mgr.history})

    async def scrape(_):
        started = await mgr.scrape_in_background()
        return web.json_response({"started": started}, status=202 if started else 409)

    async def debug_probe(request: web.Request):
        try:
            body = await request.json()
            return web.json_response({"results": await mgr.probe(body.get("steps"))})
        except PermissionError as e:
            raise web.HTTPForbidden(text=str(e))
        except RuntimeError as e:
            raise web.HTTPConflict(text=str(e))
        except (probe.ProbeError, ValueError, AttributeError) as e:
            raise web.HTTPBadRequest(text=str(e))

    app.router.add_get("/api/history", history)
    app.router.add_post("/api/scrape", scrape)
    app.router.add_post("/api/debug/probe", debug_probe)
    return app
