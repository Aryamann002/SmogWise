"""Open-Meteo client: place search and air-quality forecasts, validated and cached.

Open-Meteo needs no API key, so there is no secret to leak on this path. Upstream payloads
are treated as untrusted and validated before use.
"""

import logging
from datetime import datetime
from typing import Final, Self

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.aqi import compute_aqi, scale_for_country
from app.cache import TTLCache
from app.errors import UpstreamError
from app.schemas import AirQualityReport, HourlyPm, Place

logger = logging.getLogger(__name__)

GEOCODING_URL: Final = "https://geocoding-api.open-meteo.com/v1/search"
AIR_QUALITY_URL: Final = "https://air-quality-api.open-meteo.com/v1/air-quality"
CURRENT_POLLUTANTS: Final = "pm2_5,pm10,nitrogen_dioxide,ozone"
FORECAST_DAYS: Final = 2
FORECAST_HOURS: Final = 24
DAYTIME_HOURS: Final = range(8, 19)  # outdoor-activity window, local time
MAX_PLACES: Final = 5
COORDINATE_DECIMALS: Final = 2  # ~1 km: shares cache entries and avoids storing exact homes
AIR_CACHE_TTL_S: Final = 30 * 60
PLACES_CACHE_TTL_S: Final = 24 * 60 * 60
CACHE_MAX_ENTRIES: Final = 512


class _GeoResult(BaseModel):
    name: str
    latitude: float
    longitude: float
    country: str | None = None
    country_code: str | None = None
    admin1: str | None = None


class _GeoPayload(BaseModel):
    results: list[_GeoResult] = []


class _Current(BaseModel):
    time: str
    pm2_5: float | None = Field(default=None, ge=0)
    pm10: float | None = Field(default=None, ge=0)
    nitrogen_dioxide: float | None = Field(default=None, ge=0)
    ozone: float | None = Field(default=None, ge=0)


class _Hourly(BaseModel):
    time: list[str]
    pm2_5: list[float | None]

    @model_validator(mode="after")
    def _same_length(self) -> Self:
        if len(self.time) != len(self.pm2_5):
            msg = "hourly arrays differ in length"
            raise ValueError(msg)
        return self


class _AirPayload(BaseModel):
    current: _Current
    hourly: _Hourly


def _validate[M: BaseModel](model: type[M], payload: object) -> M:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        logger.warning("Rejected malformed upstream payload for %s", model.__name__)
        raise UpstreamError from exc


def _local_hour(iso_time: str) -> int:
    return datetime.fromisoformat(iso_time).hour


def parse_places(payload: object) -> tuple[Place, ...]:
    """Convert an Open-Meteo geocoding payload into places the user can choose from."""
    data = _validate(_GeoPayload, payload)
    return tuple(
        Place(
            name=r.name,
            admin=r.admin1,
            country=r.country,
            country_code=r.country_code,
            latitude=r.latitude,
            longitude=r.longitude,
        )
        for r in data.results[:MAX_PLACES]
    )


def _upcoming_hours(hourly: _Hourly, current_time: str) -> tuple[HourlyPm, ...]:
    """Return the next day of hourly PM2.5 values, starting with the current hour."""
    current_hour = current_time[:13] + ":00"  # ISO strings in one zone sort chronologically
    points = (
        HourlyPm(time=t, pm2_5=value)
        for t, value in zip(hourly.time, hourly.pm2_5, strict=True)
        if value is not None and t >= current_hour
    )
    return tuple(points)[:FORECAST_HOURS]


def parse_air_quality(payload: object, country_code: str | None) -> AirQualityReport:
    """Turn an Open-Meteo air-quality payload into a report with AQI and best/worst hours."""
    data = _validate(_AirPayload, payload)
    current = data.current
    forecast = _upcoming_hours(data.hourly, current.time)
    if current.pm2_5 is None or not forecast:
        logger.warning("Upstream air-quality payload had no usable PM2.5 data")
        raise UpstreamError
    daytime = [p for p in forecast if _local_hour(p.time) in DAYTIME_HOURS] or list(forecast)
    aqi = compute_aqi(scale_for_country(country_code), current.pm2_5, current.pm10)
    return AirQualityReport(
        observed_at=current.time,
        pm2_5=current.pm2_5,
        pm10=current.pm10,
        nitrogen_dioxide=current.nitrogen_dioxide,
        ozone=current.ozone,
        aqi=aqi.value,
        aqi_scale=aqi.scale,
        category=aqi.category,
        level=aqi.severity,
        best_hour=min(daytime, key=lambda p: p.pm2_5),
        worst_hour=max(forecast, key=lambda p: p.pm2_5),
        forecast=forecast,
    )


class OpenMeteoClient:
    """Fetches places and air quality, caching results to keep responses fast."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._places: TTLCache[str, tuple[Place, ...]] = TTLCache(
            PLACES_CACHE_TTL_S, CACHE_MAX_ENTRIES
        )
        self._air: TTLCache[tuple[float, float, str | None], AirQualityReport] = TTLCache(
            AIR_CACHE_TTL_S, CACHE_MAX_ENTRIES
        )

    async def search_places(self, query: str) -> tuple[Place, ...]:
        """Find up to five places matching a city or town name."""
        key = query.casefold()
        if (cached := self._places.get(key)) is not None:
            return cached
        params: dict[str, str | int | float] = {
            "name": query,
            "count": MAX_PLACES,
            "language": "en",
            "format": "json",
        }
        places = parse_places(await self._get_json(GEOCODING_URL, params))
        self._places.set(key, places)
        return places

    async def air_quality(
        self, latitude: float, longitude: float, country_code: str | None
    ) -> AirQualityReport:
        """Return current air quality and the 24-hour forecast near a point."""
        lat, lon = round(latitude, COORDINATE_DECIMALS), round(longitude, COORDINATE_DECIMALS)
        key = (lat, lon, country_code)
        if (cached := self._air.get(key)) is not None:
            return cached
        params: dict[str, str | int | float] = {
            "latitude": lat,
            "longitude": lon,
            "current": CURRENT_POLLUTANTS,
            "hourly": "pm2_5",
            "forecast_days": FORECAST_DAYS,
            "timezone": "auto",
        }
        report = parse_air_quality(await self._get_json(AIR_QUALITY_URL, params), country_code)
        self._air.set(key, report)
        return report

    async def _get_json(self, url: str, params: dict[str, str | int | float]) -> object:
        try:
            response = await self._http.get(url, params=params)
            response.raise_for_status()
            payload: object = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Upstream request to %s failed: %s", url, type(exc).__name__)
            raise UpstreamError from exc
        return payload
