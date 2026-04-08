# src/runtime/event_bus.py
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

Handler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: object, timeout: float = 30.0) -> None:
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        async def _safe_call(handler: Handler) -> None:
            try:
                await asyncio.wait_for(handler(event), timeout=timeout)
            except TimeoutError:
                logger.error(
                    "Handler %s for %s timed out after %.1fs",
                    handler.__name__, event_type.__name__, timeout,
                )
            except Exception:
                logger.exception(
                    "Error in handler %s for %s",
                    handler.__name__, event_type.__name__,
                )

        await asyncio.gather(*(_safe_call(h) for h in handlers))
