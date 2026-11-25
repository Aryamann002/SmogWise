"""Runtime configuration, read once from environment variables."""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

DEFAULT_GEMINI_MODEL: Final = "gemini-3.8-flash"
DEFAULT_GEMINI_TIMEOUT_S: Final = 15.0
DEFAULT_RATE_LIMIT_PER_MINUTE: Final = 20


@dataclass(frozen=True, slots=True)
class Settings:
    """Application settings. Secrets come only from the environment, never from code."""

    gemini_api_key: str | None
    gemini_model: str
    gemini_timeout_s: float
    rate_limit_per_minute: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process-wide settings, so every component sees the same configuration."""
    return Settings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        gemini_timeout_s=float(os.environ.get("GEMINI_TIMEOUT_S", DEFAULT_GEMINI_TIMEOUT_S)),
        rate_limit_per_minute=int(
            os.environ.get("RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE)
        ),
    )
