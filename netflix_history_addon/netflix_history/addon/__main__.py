import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web

from .manager import Manager, Options, get_or_create_token
from .server import build_api_app, build_ingress_app

INGRESS_PORT, API_PORT = 8099, 8100


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    data = Path(os.environ.get("DATA_DIR", "/data"))
    data.mkdir(parents=True, exist_ok=True)
    mgr = Manager(data, Options.load(data / "options.json"))
    token = get_or_create_token(data)
    dev = bool(os.environ.get("DEV"))
    runners = []
    for app, port in ((build_ingress_app(mgr, token, dev), INGRESS_PORT), (build_api_app(mgr, token), API_PORT)):
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
        runners.append(runner)
    await mgr.schedule_forever()


asyncio.run(main())
