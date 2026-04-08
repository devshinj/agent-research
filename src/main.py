from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import uvicorn

from src.config.settings import Settings
from src.runtime.app import App
from src.ui.api.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _load_dotenv(path: str = ".env") -> None:
    """Load .env file into os.environ (only sets missing keys)."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


async def main() -> None:
    _load_dotenv()
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
