"""Test data builders and fakes for external services."""

from collections.abc import Sequence
from typing import Any

from app.advisor import Advice
from app.air_quality import parse_air_quality
from app.errors import AdvisorError, UpstreamError
from app.schemas import Action, AirQualityReport, Place, PlanRequest

# Real Open-Meteo hourly PM2.5 for Delhi on a November day: dirty mornings and nights,
# cleanest mid-afternoon (15:00), smoggiest at the 08:00 rush.
DELHI_HOURLY_PM25 = [
    103.6, 103.1, 104.1, 105.5, 107.1, 107.1, 115.9, 139.2, 159.7, 132.2, 112.7, 101.0,
    84.1, 69.2, 62.6, 60.1, 69.8, 92.2, 113.2, 126.7, 134.1, 137.4, 140.2, 140.2,
]  # fmt: skip
CLEAN_HOURLY_PM25 = [5.0] * 24


def air_payload(
    hourly: Sequence[float | None] = DELHI_HOURLY_PM25,
    current_pm25: float | None = 134.1,
    current_time: str = "2026-11-25T00:00",
) -> dict[str, Any]:
    """Build an Open-Meteo air-quality payload with one day of hourly values."""
    return {
        "current": {
            "time": current_time,
            "pm2_5": current_pm25,
            "pm10": 135.5,
            "nitrogen_dioxide": 96.1,
            "ozone": 13.0,
        },
        "hourly": {
            "time": [f"2026-11-25T{hour:02d}:00" for hour in range(len(hourly))],
            "pm2_5": list(hourly),
        },
    }


def make_air(
    hourly: Sequence[float] = DELHI_HOURLY_PM25,
    current_pm25: float = 134.1,
    country_code: str | None = "IN",
) -> AirQualityReport:
    """Parse a payload through the real parser so tests exercise production code paths."""
    return parse_air_quality(air_payload(hourly, current_pm25), country_code)


def make_request(**overrides: Any) -> PlanRequest:
    """A Delhi family request; keyword overrides replace top-level sections."""
    data: dict[str, Any] = {
        "location": {"name": "Delhi", "latitude": 28.65, "longitude": 77.23, "country_code": "IN"},
        "household": {"adults": 2, "children": 1, "elderly": 1, "conditions": ["asthma"]},
        "commute": {"mode": "car", "distance_km": 12},
        "home": {"heating": "wood", "cooking": "gas", "has_purifier": False, "room_area_m2": 15},
        "exercises_outdoors": True,
    }
    data.update(overrides)
    return PlanRequest.model_validate(data)


class FakeOpenMeteo:
    """Stands in for OpenMeteoClient; can be told to fail like the real upstream."""

    def __init__(self, air: AirQualityReport, *, fail: bool = False) -> None:
        self.air = air
        self.fail = fail

    async def search_places(self, query: str) -> tuple[Place, ...]:
        if self.fail:
            raise UpstreamError
        return (
            Place(
                name=query.title(),
                admin="National Capital Territory of Delhi",
                country="India",
                country_code="IN",
                latitude=28.65,
                longitude=77.23,
            ),
        )

    async def air_quality(self, *_: object) -> AirQualityReport:
        if self.fail:
            raise UpstreamError
        return self.air


class FakeAdvisor:
    """Returns canned advice (or fails) and records how often it was asked."""

    def __init__(self, advice: Advice | None = None) -> None:
        self.advice = advice
        self.calls = 0

    async def advise(
        self, request: PlanRequest, air: AirQualityReport, actions: Sequence[Action]
    ) -> Advice:
        self.calls += 1
        if self.advice is None:
            raise AdvisorError
        return self.advice
