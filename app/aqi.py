"""Air Quality Index scales computed from PM concentrations (µg/m³).

Indian users see the national CPCB index they hear on the news; everyone else sees US EPA.
ponytail: both scales are defined on 24-hour averages; we apply them to the current hourly
value so the index reacts to today's smog. Swap in rolling averages for regulatory use.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Final

INDIA_COUNTRY_CODE: Final = "IN"


class Severity(IntEnum):
    """Six severity bands shared by both scales, so rules work the same everywhere."""

    GOOD = 0
    MODERATE = 1
    SENSITIVE = 2
    UNHEALTHY = 3
    VERY_UNHEALTHY = 4
    HAZARDOUS = 5


@dataclass(frozen=True, slots=True)
class Breakpoint:
    """One linear segment of an AQI scale: a concentration range mapped onto an index range."""

    conc_low: float
    conc_high: float
    index_low: int
    index_high: int


@dataclass(frozen=True, slots=True)
class AqiScale:
    """A national AQI definition: band labels, band ceilings and PM breakpoint tables."""

    name: str
    categories: tuple[str, ...]
    band_ceilings: tuple[int, ...]
    pm25: tuple[Breakpoint, ...]
    pm10: tuple[Breakpoint, ...]


@dataclass(frozen=True, slots=True)
class AqiResult:
    """An index value with its human-readable band."""

    value: int
    category: str
    severity: Severity
    scale: str


# US EPA AQI; PM2.5 breakpoints from the 2024 PM NAAQS revision (40 CFR Part 58, App. G).
US_EPA: Final = AqiScale(
    name="US EPA",
    categories=(
        "Good",
        "Moderate",
        "Unhealthy for Sensitive Groups",
        "Unhealthy",
        "Very Unhealthy",
        "Hazardous",
    ),
    band_ceilings=(50, 100, 150, 200, 300, 500),
    pm25=(
        Breakpoint(0.0, 9.0, 0, 50),
        Breakpoint(9.1, 35.4, 51, 100),
        Breakpoint(35.5, 55.4, 101, 150),
        Breakpoint(55.5, 125.4, 151, 200),
        Breakpoint(125.5, 225.4, 201, 300),
        Breakpoint(225.5, 325.4, 301, 500),
    ),
    pm10=(
        Breakpoint(0, 54, 0, 50),
        Breakpoint(55, 154, 51, 100),
        Breakpoint(155, 254, 101, 150),
        Breakpoint(255, 354, 151, 200),
        Breakpoint(355, 424, 201, 300),
        Breakpoint(425, 604, 301, 500),
    ),
)

# India National AQI (CPCB, 2014). The Severe band is open-ended; we cap it at 500 µg/m³.
INDIA_CPCB: Final = AqiScale(
    name="India CPCB",
    categories=("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"),
    band_ceilings=(50, 100, 200, 300, 400, 500),
    pm25=(
        Breakpoint(0, 30, 0, 50),
        Breakpoint(31, 60, 51, 100),
        Breakpoint(61, 90, 101, 200),
        Breakpoint(91, 120, 201, 300),
        Breakpoint(121, 250, 301, 400),
        Breakpoint(251, 500, 401, 500),
    ),
    pm10=(
        Breakpoint(0, 50, 0, 50),
        Breakpoint(51, 100, 51, 100),
        Breakpoint(101, 250, 101, 200),
        Breakpoint(251, 350, 201, 300),
        Breakpoint(351, 430, 301, 400),
        Breakpoint(431, 500, 401, 500),
    ),
)


def scale_for_country(country_code: str | None) -> AqiScale:
    """Pick the AQI scale people in that country are used to."""
    return INDIA_CPCB if country_code == INDIA_COUNTRY_CODE else US_EPA


def sub_index(concentration: float, table: tuple[Breakpoint, ...]) -> int:
    """Linearly interpolate one pollutant concentration onto a breakpoint table."""
    for bp in table:
        if concentration <= bp.conc_high:
            clamped = max(concentration, bp.conc_low)
            slope = (bp.index_high - bp.index_low) / (bp.conc_high - bp.conc_low)
            return int(bp.index_low + slope * (clamped - bp.conc_low) + 0.5)
    return table[-1].index_high


def compute_aqi(scale: AqiScale, pm25: float, pm10: float | None) -> AqiResult:
    """Return the AQI as the worst of the PM2.5 and PM10 sub-indices, as both agencies do."""
    if scale == US_EPA:
        pm25 = int(min(pm25, scale.pm25[-1].conc_high) * 10) / 10
        pm10 = int(pm10) if pm10 is not None else None
    value = sub_index(pm25, scale.pm25)
    if pm10 is not None:
        value = max(value, sub_index(pm10, scale.pm10))
    band = next(i for i, ceiling in enumerate(scale.band_ceilings) if value <= ceiling)
    return AqiResult(
        value=value,
        category=scale.categories[band],
        severity=Severity(band),
        scale=scale.name,
    )
