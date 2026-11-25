"""A small in-process TTL + LRU cache, so repeat lookups skip slow upstream calls."""

import time
from collections import OrderedDict
from collections.abc import Callable, Hashable


class TTLCache[K: Hashable, V]:
    """Keeps up to `max_entries` values for `ttl_seconds`, evicting the least recently used.

    ponytail: per-instance memory; move to Memorystore/Redis if Cloud Run scales out widely.
    """

    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        """Return the cached value, or None when it is missing or expired."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key: K, value: V) -> None:
        """Store a value, evicting the oldest entries once the size cap is reached."""
        self._entries[key] = (self._clock() + self._ttl, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
