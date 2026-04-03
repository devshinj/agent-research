# src/runtime/scheduler.py
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Any

logger = logging.getLogger(__name__)

Task = Callable[[], Coroutine[Any, Any, None]]


class Scheduler:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []

    def schedule_interval(self, name: str, func: Task, interval_seconds: float) -> None:
        async def _loop() -> None:
            while True:
                try:
                    await func()
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("Error in scheduled task: %s", name)
                await asyncio.sleep(interval_seconds)

        task = asyncio.create_task(_loop(), name=name)
        self._tasks.append(task)
        logger.info("Scheduled '%s' every %.1fs", name, interval_seconds)

    async def cancel_all(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
