import threading
import time

from app.core.cache import ScheduleCache


class FakeRedis:
    """Minimal in-memory stand-in for the subset of redis-py used by ScheduleCache."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and expires_at < time.monotonic():
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False, px: int | None = None):
        with self._lock:
            if nx:
                existing = self._store.get(key)
                if existing is not None:
                    existing_value, expires_at = existing
                    if expires_at is None or expires_at >= time.monotonic():
                        return None
            ttl = None
            if ex is not None:
                ttl = time.monotonic() + ex
            elif px is not None:
                ttl = time.monotonic() + px / 1000
            self._store[key] = (value, ttl)
            return True

    def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        with self._lock:
            entry = self._store.get(key)
            if entry is not None and entry[0] == token:
                del self._store[key]
                return 1
            return 0

    def delete(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._store.pop(key, None)


def _make_cache(**kwargs) -> ScheduleCache:
    cache = ScheduleCache(redis_url=None, **kwargs)
    cache._client = FakeRedis()
    return cache


def test_get_or_set_returns_cached_value_without_calling_factory():
    cache = _make_cache()
    calls = []
    cache.get_or_set("group", 1, 7, lambda: calls.append(1) or {"value": "first"})
    assert calls == [1]

    result = cache.get_or_set("group", 1, 7, lambda: calls.append(2) or {"value": "second"})

    assert result == {"value": "first"}
    assert calls == [1]


def test_single_flight_only_calls_factory_once_under_concurrent_miss():
    cache = _make_cache(lock_timeout_seconds=2.0, wait_poll_interval_seconds=0.01)
    call_count = 0
    call_count_lock = threading.Lock()

    def factory():
        nonlocal call_count
        with call_count_lock:
            call_count += 1
        time.sleep(0.1)
        return {"value": "computed"}

    results: list[dict] = []
    results_lock = threading.Lock()

    def worker():
        result = cache.get_or_set("teacher", 5, 7, factory)
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert call_count == 1
    assert len(results) == 20
    assert all(result == {"value": "computed"} for result in results)


def test_waiter_falls_back_to_factory_if_lock_holder_never_finishes():
    cache = _make_cache(lock_timeout_seconds=0.2, wait_poll_interval_seconds=0.02)
    # Simulate a lock acquired by a holder that never sets the value or releases.
    cache._client.set(f"{cache._key('group', 1, 7)}:lock", "stuck-token", nx=True, px=100000)

    calls = []
    result = cache.get_or_set("group", 1, 7, lambda: calls.append(1) or {"value": "fallback"})

    assert result == {"value": "fallback"}
    assert calls == [1]


def test_no_client_always_calls_factory_directly():
    cache = ScheduleCache(redis_url=None)
    calls = []

    cache.get_or_set("group", 1, 7, lambda: calls.append(1) or {"value": "a"})
    cache.get_or_set("group", 1, 7, lambda: calls.append(2) or {"value": "b"})

    assert calls == [1, 2]
