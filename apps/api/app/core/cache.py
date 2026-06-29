from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_cache: ScheduleCache | None = None


class ScheduleCache:
    """Redis-backed cache for public schedule reads.

    Key format: ``schedule:{entity_type}:{entity_id}:{week}``
    When Redis is unavailable (redis_url is None) every call falls through
    to the factory — behaviour is correct, just uncached.
    """

    def __init__(self, redis_url: str | None, ttl_seconds: int = 45) -> None:
        self._ttl = ttl_seconds
        self._client = None
        if redis_url is not None:
            import redis as redis_lib

            self._client = redis_lib.from_url(redis_url, decode_responses=True)

    def _key(self, entity_type: str, entity_id: int, week: int) -> str:
        return f"schedule:{entity_type}:{entity_id}:{week}"

    def get_or_set(
        self,
        entity_type: str,
        entity_id: int,
        week: int,
        factory: Callable[[], Any],
    ) -> Any:
        if self._client is None:
            return factory()
        key = self._key(entity_type, entity_id, week)
        cached = self._client.get(key)
        if cached is not None:
            return json.loads(cached)
        value = factory()
        self._client.set(key, json.dumps(value, default=str), ex=self._ttl)
        return value

    def invalidate(self, entity_type: str, entity_id: int, week: int) -> None:
        if self._client is None:
            return
        self._client.delete(self._key(entity_type, entity_id, week))

    def invalidate_all(self) -> None:
        """Invalidate every schedule cache key (used on any lesson mutation
        when entity mapping is not yet per-group/teacher)."""
        if self._client is None:
            return
        keys = self._client.keys("schedule:*")
        if keys:
            self._client.delete(*keys)


def init_cache(redis_url: str | None) -> None:
    global _cache
    _cache = ScheduleCache(redis_url)


def get_cache() -> ScheduleCache:
    if _cache is None:
        raise RuntimeError("Cache not initialized; call init_cache() first")
    return _cache
