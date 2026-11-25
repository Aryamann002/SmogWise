import pytest

from app.actions import (
    build_routine,
    community_impact,
    generate_actions,
    summarise,
)
from app.schemas import Action, AirQualityReport, PlanRequest
from tests.factories import CLEAN_HOURLY_PM25, make_air, make_request

WFH_ELECTRIC = {
    "commute": {"mode": "work_from_home"},
    "home": {"heating": "electric", "cooking": "electric"},
    "exercises_outdoors": False,
}


def _ids(actions: tuple[Action, ...]) -> list[str]:
    return [action.id for action in actions]


def _by_id(actions: tuple[Action, ...], action_id: str) -> Action:
    return next(action for action in actions if action.id == action_id)


def test_delhi_family_gets_safety_first_then_quantified_actions(
    delhi_air: AirQualityReport,
) -> None:
    actions = generate_actions(make_request(), delhi_air)
    ids = _ids(actions)
    assert ids[0] == "heating-switch"
    assert {"n95-mask", "diy-air-filter", "commute-switch", "no-open-burning"} <= set(ids)
    assert len(ids) == len(set(ids))


def test_every_action_is_explained_and_quantified(delhi_air: AirQualityReport) -> None:
    for action in generate_actions(make_request(), delhi_air):
        assert action.method
        assert action.explanation
        impact = action.impact
        assert any(
            value is not None
            for value in (
                impact.exposure_reduction_pct,
                impact.co2_kg_per_day,
                impact.pm25_g_per_day,
            )
        )


def test_long_car_commute_switches_to_rail(delhi_air: AirQualityReport) -> None:
    action = _by_id(generate_actions(make_request(), delhi_air), "commute-switch")
    assert action.title.startswith("Take the metro")
    assert action.impact.co2_kg_per_day == pytest.approx(round(2 * 12 * (0.166 - 0.028), 1))


def test_short_commute_on_a_moderate_day_suggests_cycling() -> None:
    air = make_air(hourly=[30.0] * 24, current_pm25=30.0, country_code=None)
    request = make_request(commute={"mode": "two_wheeler", "distance_km": 3})
    action = _by_id(generate_actions(request, air), "commute-switch")
    assert action.title == "Walk or cycle your 3 km trip"


def test_very_unhealthy_air_moves_exercise_indoors(delhi_air: AirQualityReport) -> None:
    ids = _ids(generate_actions(make_request(), delhi_air))
    assert "exercise-indoors" in ids
    assert "exercise-timing" not in ids


def test_moderate_smog_shifts_exercise_to_the_cleanest_hour() -> None:
    hourly = [20.0] * 24
    hourly[7] = 45.0
    hourly[15] = 10.0
    air = make_air(hourly=hourly, current_pm25=20.0, country_code=None)
    action = _by_id(generate_actions(make_request(), air), "exercise-timing")
    assert action.title == "Move outdoor exercise to 15:00"
    assert action.impact.exposure_reduction_pct is not None
    assert action.impact.exposure_reduction_pct > 0


def test_clean_air_and_clean_home_skip_irrelevant_actions() -> None:
    air = make_air(hourly=CLEAN_HOURLY_PM25, current_pm25=5.0, country_code=None)
    ids = _ids(generate_actions(make_request(**WFH_ELECTRIC), air))
    for skipped in ("n95-mask", "commute-switch", "heating-switch", "cooking-switch"):
        assert skipped not in ids
    assert "ventilation-timing" not in ids


def test_purifier_owners_get_a_clean_room_plan(delhi_air: AirQualityReport) -> None:
    request = make_request(home={"has_purifier": True, "room_area_m2": 12})
    ids = _ids(generate_actions(request, delhi_air))
    assert "purifier-clean-room" in ids
    assert "diy-air-filter" not in ids


def test_india_specific_help_only_for_indian_locations() -> None:
    biomass = {"heating": "none", "cooking": "wood"}
    india = generate_actions(make_request(home=biomass), make_air())
    abroad_request = make_request(
        home=biomass,
        location={"name": "Lahore", "latitude": 31.5, "longitude": 74.3, "country_code": "PK"},
    )
    abroad = generate_actions(abroad_request, make_air(country_code="PK"))
    assert "PMUY" in _by_id(india, "cooking-switch").how
    assert "PMUY" not in _by_id(abroad, "cooking-switch").how
    assert "Sameer" in _by_id(india, "no-open-burning").how
    assert "Sameer" not in _by_id(abroad, "no-open-burning").how


def test_routine_is_time_ordered_and_includes_commute(delhi_air: AirQualityReport) -> None:
    routine = build_routine(make_request(), delhi_air)
    times = [step.time for step in routine]
    assert times == sorted(times)
    assert "15:00" in times
    assert "08:30" in times


def test_routine_skips_commute_for_home_workers(delhi_air: AirQualityReport) -> None:
    routine = build_routine(make_request(**WFH_ELECTRIC), delhi_air)
    assert "08:30" not in [step.time for step in routine]


def test_community_impact_scales_emission_savings(delhi_air: AirQualityReport) -> None:
    actions = generate_actions(make_request(), delhi_air)
    single = community_impact(actions, 1)
    street = community_impact(actions, 50)
    assert single.co2_kg_per_day is not None
    assert street.co2_kg_per_day == pytest.approx(single.co2_kg_per_day * 50, abs=0.1)
    assert street.households == 50


def test_summary_names_place_and_category(delhi_air: AirQualityReport) -> None:
    request: PlanRequest = make_request()
    summary = summarise(request, delhi_air, generate_actions(request, delhi_air))
    assert "Delhi" in summary
    assert "Very Poor" in summary
