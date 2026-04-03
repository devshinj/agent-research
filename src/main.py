from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import uvicorn

from src.config.settings import Settings
from src.runtime.app import App
from src.ui.api.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    settings = Settings.from_yaml(Path("config/settings.yaml"))
    app = App(settings)
    await app.start()

    fastapi_app = create_app()
    # 앱 상태를 FastAPI에 주입
    fastapi_app.state.app = app

    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
