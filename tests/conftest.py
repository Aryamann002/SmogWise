"""Shared fixtures: realistic Delhi air data and an API client wired to fakes."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app, get_open_meteo, get_planner
from app.planner import Planner
from app.schemas import AirQualityReport
from tests.factories import FakeOpenMeteo, make_air


@pytest.fixture
def delhi_air() -> AirQualityReport:
    return make_air()


@pytest.fixture
def fake_open_meteo(delhi_air: AirQualityReport) -> FakeOpenMeteo:
    return FakeOpenMeteo(delhi_air)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run without a Gemini key and with fresh settings, restoring the cache afterwards."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(fake_open_meteo: FakeOpenMeteo) -> Iterator[TestClient]:
    app = create_app()
    planner = Planner(None)
    app.dependency_overrides[get_open_meteo] = lambda: fake_open_meteo
    app.dependency_overrides[get_planner] = lambda: planner
    with TestClient(app) as test_client:
        yield test_client
