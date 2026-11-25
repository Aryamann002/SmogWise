import pytest

from app import security
from app.security import SlidingWindowRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_limit_blocks_extra_requests_until_window_slides() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(limit=2, window_s=60, clock=clock)
    assert limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4")
    assert not limiter.allow("1.2.3.4")
    assert limiter.allow("5.6.7.8")
    clock.now = 60.0
    assert limiter.allow("1.2.3.4")


def test_tracked_clients_are_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "MAX_TRACKED_CLIENTS", 2)
    limiter = SlidingWindowRateLimiter(limit=1)
    for client in ("a", "b", "c"):
        assert limiter.allow(client)
    assert limiter.allow("a")
