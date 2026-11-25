from app.cache import TTLCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_value_expires_after_ttl() -> None:
    clock = FakeClock()
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=10, max_entries=5, clock=clock)
    cache.set("a", 1)
    clock.now = 9.9
    assert cache.get("a") == 1
    clock.now = 10.0
    assert cache.get("a") is None


def test_least_recently_used_entry_is_evicted() -> None:
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=60, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1
    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_missing_key_returns_none() -> None:
    assert TTLCache[str, int](ttl_seconds=1, max_entries=1).get("nope") is None
