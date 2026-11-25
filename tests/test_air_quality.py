from collections.abc import Callable

import httpx
import pytest

from app.air_quality import FORECAST_HOURS, OpenMeteoClient, parse_air_quality, parse_places
from app.errors import UpstreamError
from tests.factories import DELHI_HOURLY_PM25, air_payload

GEO_PAYLOAD = {
    "results": [
        {
            "name": "Delhi",
            "latitude": 28.65195,
            "longitude": 77.23149,
            "country": "India",
            "country_code": "IN",
            "admin1": "National Capital Territory of Delhi",
            "population": 11034555,
        }
    ]
}


def test_parse_air_quality_finds_cleanest_daytime_and_smoggiest_hour() -> None:
    report = parse_air_quality(air_payload(), "IN")
    assert report.aqi_scale == "India CPCB"
    assert report.category == "Very Poor"
    assert report.best_hour.time == "2026-11-25T15:00"
    assert report.best_hour.pm2_5 == 60.1
    assert report.worst_hour.time == "2026-11-25T08:00"
    assert len(report.forecast) == FORECAST_HOURS


def test_forecast_starts_at_the_current_hour() -> None:
    payload = air_payload(hourly=DELHI_HOURLY_PM25 * 2, current_time="2026-11-25T05:30")
    payload["hourly"]["time"] = [f"2026-11-{25 + h // 24}T{h % 24:02d}:00" for h in range(48)]
    report = parse_air_quality(payload, None)
    assert report.forecast[0].time == "2026-11-25T05:00"
    assert len(report.forecast) == FORECAST_HOURS
    assert report.aqi_scale == "US EPA"


def test_missing_hours_do_not_extend_forecast_into_the_following_day() -> None:
    payload = air_payload()
    payload["hourly"]["time"].append("2026-11-26T00:00")
    payload["hourly"]["pm2_5"][1] = None
    payload["hourly"]["pm2_5"].append(999)
    report = parse_air_quality(payload, "IN")
    assert len(report.forecast) == 23
    assert report.worst_hour.pm2_5 < 999


def test_missing_hours_are_skipped() -> None:
    hourly: list[float | None] = list(DELHI_HOURLY_PM25)
    hourly[15] = None
    report = parse_air_quality(air_payload(hourly=hourly), "IN")
    assert all(point.time != "2026-11-25T15:00" for point in report.forecast)


@pytest.mark.parametrize(
    "payload",
    [
        air_payload(current_pm25=None),
        air_payload(current_time="yesterday"),
        air_payload(current_pm25=float("inf")),
        air_payload(hourly=[-1]),
        air_payload(hourly=[float("nan")]),
        air_payload(hourly=[None] * 24),
        {"current": {"time": "2026-11-25T00:00"}},
        {"current": {"time": "x", "pm2_5": -5}, "hourly": {"time": [], "pm2_5": []}},
        {"current": {"time": "x", "pm2_5": 5}, "hourly": {"time": ["a"], "pm2_5": [1, 2]}},
        "not json object",
    ],
)
def test_unusable_payloads_raise_upstream_error(payload: object) -> None:
    with pytest.raises(UpstreamError):
        parse_air_quality(payload, "IN")


def test_parse_places_keeps_only_needed_fields() -> None:
    (place,) = parse_places(GEO_PAYLOAD)
    assert place.name == "Delhi"
    assert place.admin == "National Capital Territory of Delhi"
    assert place.country_code == "IN"


def test_parse_places_handles_no_results() -> None:
    assert parse_places({}) == ()


def test_upstream_place_must_be_usable_in_a_plan() -> None:
    with pytest.raises(UpstreamError):
        parse_places({"results": [{**GEO_PAYLOAD["results"][0], "longitude": 200}]})


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> OpenMeteoClient:
    return OpenMeteoClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.anyio
async def test_place_search_is_cached() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=GEO_PAYLOAD)

    client = _client(handler)
    first = await client.search_places("Delhi")
    second = await client.search_places("delhi")
    assert first == second
    assert len(requests) == 1
    assert requests[0].url.params["name"] == "Delhi"


@pytest.mark.anyio
async def test_air_quality_rounds_coordinates_and_caches() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=air_payload())

    client = _client(handler)
    await client.air_quality(28.65195, 77.23149, "IN")
    await client.air_quality(28.6512, 77.2321, "IN")
    assert len(requests) == 1
    assert requests[0].url.params["latitude"] == "28.65"
    assert requests[0].url.params["longitude"] == "77.23"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, content=b"<html>oops</html>")],
)
async def test_upstream_failures_raise_upstream_error(response: httpx.Response) -> None:
    client = _client(lambda _: response)
    with pytest.raises(UpstreamError):
        await client.air_quality(28.65, 77.23, "IN")


@pytest.mark.anyio
async def test_network_errors_raise_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(UpstreamError):
        await _client(handler).search_places("Delhi")
