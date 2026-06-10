"""Simple in-memory LRU cache for query results.

Cached at the `(sql, db_url)` granularity, with a short TTL.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

from backend.utils import get_logger

log = get_logger(__name__)


class QueryCache:
    """Thread-safe LRU+TTL cache."""

    def __init__(self, max_size: int = 128, ttl_seconds: int = 60):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def make_key(sql: str, db_url: str, max_rows: int) -> str:
        h = hashlib.sha256()
        h.update(sql.strip().encode("utf-8"))
        h.update(b"|")
        h.update(db_url.encode("utf-8"))
        h.update(b"|")
        h.update(str(max_rows).encode("utf-8"))
        return h.hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._store:
                return None
            ts, value = self._store[key]
            if time.time() - ts > self.ttl:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (time.time(), value)
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Module-level singleton
_cache = QueryCache()


def get_cache() -> QueryCache:
    return _cache
