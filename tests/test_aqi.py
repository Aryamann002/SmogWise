import itertools

import pytest

from app.aqi import (
    INDIA_CPCB,
    US_EPA,
    AqiScale,
    Severity,
    compute_aqi,
    scale_for_country,
    sub_index,
)


@pytest.mark.parametrize(
    ("concentration", "expected"),
    [(0.0, 0), (9.0, 50), (9.05, 51), (35.4, 100), (55.5, 151), (325.4, 500), (900.0, 500)],
)
def test_us_pm25_sub_index_matches_epa_breakpoints(concentration: float, expected: int) -> None:
    assert sub_index(concentration, US_EPA.pm25) == expected


def test_india_scale_reports_cpcb_category_for_delhi_winter_smog() -> None:
    result = compute_aqi(INDIA_CPCB, pm25=134.1, pm10=135.5)
    assert result.category == "Very Poor"
    assert result.severity is Severity.VERY_UNHEALTHY
    assert result.scale == "India CPCB"


def test_us_precision_is_applied_before_breakpoint_lookup() -> None:
    assert compute_aqi(US_EPA, pm25=9.09, pm10=54.9).value == 50
    assert compute_aqi(US_EPA, pm25=9.1, pm10=None).value == 51


def test_worst_pollutant_sets_the_index() -> None:
    pm25_only = compute_aqi(US_EPA, pm25=5.0, pm10=None)
    with_dusty_pm10 = compute_aqi(US_EPA, pm25=5.0, pm10=300.0)
    assert pm25_only.severity is Severity.GOOD
    assert with_dusty_pm10.value > pm25_only.value
    assert with_dusty_pm10.severity is Severity.UNHEALTHY


@pytest.mark.parametrize(("country", "scale"), [("IN", INDIA_CPCB), ("GB", US_EPA), (None, US_EPA)])
def test_scale_follows_country(country: str | None, scale: AqiScale) -> None:
    assert scale_for_country(country) is scale


@pytest.mark.parametrize("scale", [US_EPA, INDIA_CPCB])
def test_scales_are_well_formed(scale: AqiScale) -> None:
    assert len(scale.categories) == len(scale.band_ceilings) == len(Severity)
    for table in (scale.pm25, scale.pm10):
        assert all(bp.conc_low < bp.conc_high for bp in table)
        assert all(a.conc_high < b.conc_low + 1 for a, b in itertools.pairwise(table))
        assert table[-1].index_high == scale.band_ceilings[-1]
