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
    wait for the winner's result.

    Two independent timeouts (deliberately decoupled — a single value would
    tie "how long the holder may compute" to "how long waiters block"):

    - ``lock_ttl_seconds`` — the lock's Redis auto-expiry, so a holder that
      dies mid-compute can't wedge the key forever. Should be ≥ the factory's
      expected worst-case runtime.
    - ``wait_timeout_seconds`` — how long a waiter blocks before giving up and
      computing directly. Waiters re-attempt to acquire the lock on each poll,
      so if the holder dies exactly one waiter takes over the recompute rather
      than the whole herd stampeding the DB. This bounds the worst case.
    """

    def __init__(
        self,
        redis_url: str | None,
        ttl_seconds: int = 45,
        lock_ttl_seconds: float = 10.0,
        wait_timeout_seconds: float = 10.0,
        wait_poll_interval_seconds: float = 0.05,
    ) -> None:
        self._ttl = ttl_seconds
        self._lock_ttl_seconds = lock_ttl_seconds
        self._wait_timeout_seconds = wait_timeout_seconds
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
        deadline = time.monotonic() + self._wait_timeout_seconds
        while True:
            token = str(uuid.uuid4())
            acquired = self._client.set(lock_key, token, nx=True, px=int(self._lock_ttl_seconds * 1000))
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
            # Another caller holds the lock: wait for their result, but keep
            # re-trying acquisition each interval so a dead holder (expired
            # lock) is picked up by exactly one waiter rather than all of them.
            cached = self._client.get(key)
            if cached is not None:
                return json.loads(cached)
            if time.monotonic() >= deadline:
                # Waited long enough — compute directly. Bounds the worst case
                # at wait_timeout_seconds instead of an unbounded stall.
                return factory()
            time.sleep(self._wait_poll_interval_seconds)

    def invalidate(self, entity_type: str, entity_id: int, week: int) -> None:
        if self._client is None:
            return
        self._client.delete(self._key(entity_type, entity_id, week))

    def invalidate_all(self) -> None:
        """Invalidate every schedule cache key. Used when the whole schedule
        changes (e.g. a full re-import). Uses non-blocking ``SCAN`` rather than
        ``KEYS`` so it never stalls the single-threaded Redis under load."""
        if self._client is None:
            return
        batch: list[str] = []
        for key in self._client.scan_iter(match="schedule:*", count=500):
            batch.append(key)
            if len(batch) >= 500:
                self._client.delete(*batch)
                batch = []
        if batch:
            self._client.delete(*batch)


def init_cache(redis_url: str | None) -> None:
    global _cache
    _cache = ScheduleCache(redis_url)


def get_cache() -> ScheduleCache:
    if _cache is None:
        raise RuntimeError("Cache not initialized; call init_cache() first")
    return _cache
