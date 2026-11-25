"""Domain errors with stable public codes; they are mapped to HTTP responses in one place."""


class SmogWiseError(Exception):
    """Base class for expected failures whose message is safe to show to users."""

    status_code: int = 500
    code: str = "internal_error"
    public_message: str = "Something went wrong. Please try again."


class UpstreamError(SmogWiseError):
    """An external data provider failed or returned data we cannot trust."""

    status_code = 502
    code = "upstream_unavailable"
    public_message = "Air quality data is temporarily unavailable. Please try again shortly."


class AdvisorError(SmogWiseError):
    """The language model failed; callers recover by serving rule-based advice."""

    code = "advisor_unavailable"
