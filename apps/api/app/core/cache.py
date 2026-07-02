from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_cache: ScheduleCache | None = None

# Releases the lock only if it's still held by the caller (token match) —
# avoids deleting a lock acquired by someone else after ours expired.
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class ScheduleCache:
    """Redis-backed cache for public schedule reads.

    Key format: ``schedule:{entity_type}:{entity_id}:{week}``
    When Redis is unavailable (redis_url is None) every call falls through
    to the factory — behaviour is correct, just uncached.

    On a cache miss, concurrent callers for the same key would otherwise all
    recompute ``factory()`` at once (a "thundering herd"), which for
    DB-backed factories can exhaust the connection pool under load. A short
    distributed lock ensures only one caller recomputes per key; the rest
    wait for the winner's result and fall back to computing directly only if
    the lock holder doesn't finish within ``lock_timeout_seconds``.
    """

    def __init__(
        self,
        redis_url: str | None,
        ttl_seconds: int = 45,
        lock_timeout_seconds: float = 10.0,
        wait_poll_interval_seconds: float = 0.05,
    ) -> None:
        self._ttl = ttl_seconds
        self._lock_timeout_seconds = lock_timeout_seconds
        self._wait_poll_interval_seconds = wait_poll_interval_seconds
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
        return self._recompute_single_flight(key, factory)

    def _recompute_single_flight(self, key: str, factory: Callable[[], Any]) -> Any:
        lock_key = f"{key}:lock"
        token = str(uuid.uuid4())
        acquired = self._client.set(lock_key, token, nx=True, px=int(self._lock_timeout_seconds * 1000))
        if acquired:
            try:
                # Someone may have finished computing between our GET and
                # acquiring the lock — check once more before hitting the DB.
                cached = self._client.get(key)
                if cached is not None:
                    return json.loads(cached)
                value = factory()
                self._client.set(key, json.dumps(value, default=str), ex=self._ttl)
                return value
            finally:
                self._client.eval(_RELEASE_LOCK_SCRIPT, 1, lock_key, token)
        return self._wait_for_result(key, factory)

    def _wait_for_result(self, key: str, factory: Callable[[], Any]) -> Any:
        deadline = time.monotonic() + self._lock_timeout_seconds
        while time.monotonic() < deadline:
            cached = self._client.get(key)
            if cached is not None:
                return json.loads(cached)
            time.sleep(self._wait_poll_interval_seconds)
        # Lock holder took too long (or died holding it) — compute directly
        # rather than waiting forever; this bounds the worst case at
        # lock_timeout_seconds instead of the old unbounded pool-exhaustion stall.
        return factory()

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
