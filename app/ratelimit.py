"""Ограничение частоты запросов для публичного сервера.

Скользящее окно в памяти одного процесса: uvicorn запускается одним воркером,
поэтому общий словарь корректен. Ключи — IP и класс эндпоинта, без персональных
данных. В локальном режим limiter выключен, чтобы не мешать одному пользователю.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, limit: int, window: float) -> None:
        self.limit = max(1, int(limit))
        self.window = float(window)
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """(пропущен ли запрос, сколько секунд ждать при отказе)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(0.0, self.window - (now - hits[0]))
            hits.append(now)
            if len(self._hits) > 20000:
                self._prune(now)
            return True, 0.0

    def _prune(self, now: float) -> None:
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if not hits:
                del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()