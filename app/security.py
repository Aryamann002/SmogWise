"""HTTP hardening: security headers on every response and a per-client API rate limit."""

import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.schemas import ErrorBody, ErrorResponse

API_PREFIX: Final = "/api/"
RATE_WINDOW_S: Final = 60.0
MAX_TRACKED_CLIENTS: Final = 10_000

CONTENT_SECURITY_POLICY: Final = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SECURITY_HEADERS: Final = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class SlidingWindowRateLimiter:
    """Allows `limit` requests per client in any rolling `window_s` seconds.

    ponytail: in-memory and per instance; put Cloud Armor in front for multi-instance limits.
    """

    def __init__(
        self,
        limit: int,
        window_s: float = RATE_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, client: str) -> bool:
        """Record a request and report whether the client is still under its limit."""
        now = self._clock()
        hits = self._hits.setdefault(client, deque())
        self._hits.move_to_end(client)
        while hits and now - hits[0] >= self._window_s:
            hits.popleft()
        if len(self._hits) > MAX_TRACKED_CLIENTS:
            self._hits.popitem(last=False)
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Build the single error envelope the frontend knows how to display."""
    body = ErrorResponse(error=ErrorBody(code=code, message=message))
    return JSONResponse(body.model_dump(), status_code=status_code)


def install_security(app: FastAPI, limiter: SlidingWindowRateLimiter) -> None:
    """Attach the rate limit and security headers to every request the app serves."""

    @app.middleware("http")
    async def harden(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        client = request.client.host if request.client else "unknown"
        if request.url.path.startswith(API_PREFIX) and not limiter.allow(client):
            response: Response = error_response(
                429, "rate_limited", "Too many requests. Please wait a minute and try again."
            )
            response.headers["Retry-After"] = str(int(RATE_WINDOW_S))
        else:
            response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response
