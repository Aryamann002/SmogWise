from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app, get_open_meteo
from app.schemas import AirQualityReport
from tests.factories import FakeOpenMeteo

PLAN_BODY: dict[str, Any] = {
    "location": {"name": "Delhi", "latitude": 28.65, "longitude": 77.23, "country_code": "IN"},
    "household": {"adults": 2, "children": 1, "elderly": 0, "conditions": ["asthma"]},
    "commute": {"mode": "car", "distance_km": 12},
    "home": {"heating": "wood", "cooking": "gas", "has_purifier": False, "room_area_m2": 15},
    "exercises_outdoors": True,
    "language": "en",
}


def test_frontend_is_served_with_security_headers(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "<main" in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_self_hosted_font_has_font_mime_type(client: TestClient) -> None:
    response = client.get("/fonts/bricolage-grotesque-latin.woff2")
    assert response.status_code == 200
    assert response.headers["content-type"] == "font/woff2"


def test_health_check(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_geocode_returns_places(client: TestClient) -> None:
    response = client.get("/api/geocode", params={"q": "delhi"})
    assert response.status_code == 200
    assert response.json()[0]["country_code"] == "IN"


def test_geocode_rejects_too_short_queries(client: TestClient) -> None:
    response = client.get("/api/geocode", params={"q": "d"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_plan_returns_quantified_rule_based_plan(client: TestClient) -> None:
    response = client.post("/api/plan", json=PLAN_BODY)
    assert response.status_code == 200
    plan = response.json()
    assert plan["source"] == "rules"
    assert plan["air"]["aqi_scale"] == "India CPCB"
    assert plan["actions"][0]["id"] == "heating-switch"
    assert plan["community"]["households"] == 50


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"location": {**PLAN_BODY["location"], "latitude": 999}}, "location.latitude"),
        ({"commute": {"mode": "rocket", "distance_km": 1}}, "commute.mode"),
        ({"notes": "x" * 301}, "notes"),
        ({"is_admin": True}, "is_admin"),
        ({"household": {"adults": 0, "children": 0, "elderly": 0}}, "household"),
    ],
)
def test_invalid_plans_are_rejected_without_echoing_input(
    client: TestClient, patch: dict[str, Any], field: str
) -> None:
    response = client.post("/api/plan", json={**PLAN_BODY, **patch})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert field in error["message"]
    assert "999" not in response.text
    assert "rocket" not in response.text


def test_upstream_failure_returns_friendly_502(
    client: TestClient, delhi_air: AirQualityReport
) -> None:
    app: Any = client.app
    app.dependency_overrides[get_open_meteo] = lambda: FakeOpenMeteo(delhi_air, fail=True)
    response = client.post("/api/plan", json=PLAN_BODY)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_unavailable"


def test_api_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch, fake_open_meteo: FakeOpenMeteo
) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_open_meteo] = lambda: fake_open_meteo
    with TestClient(app) as test_client:
        statuses = [test_client.get("/api/geocode?q=delhi").status_code for _ in range(3)]
        assert statuses == [200, 200, 429]
        limited = test_client.get("/api/geocode?q=delhi")
        assert limited.headers["retry-after"] == "60"
        assert limited.json()["error"]["code"] == "rate_limited"
        assert test_client.get("/").status_code == 200


def test_app_starts_with_gemini_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        assert test_client.get("/healthz").status_code == 200
