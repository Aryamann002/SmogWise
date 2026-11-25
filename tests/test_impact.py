import pytest

from app.impact import (
    COMMUTE_CO2_KG_PER_KM,
    COOKING_FUEL_KG_PER_DAY,
    FUEL_PM25_G_PER_KG,
    HEATING_FUEL_KG_PER_DAY,
    SEALED_INFILTRATION_ACH,
    commute_co2_kg_per_day,
    commute_co2_saved_kg_per_day,
    exposure_reduction_pct,
    fuel_switch_pm25_saved_g_per_day,
    indoor_outdoor_ratio,
    recommended_cadr_m3h,
)
from app.schemas import CommuteMode, Fuel


def test_every_mode_and_fuel_has_a_factor() -> None:
    assert set(COMMUTE_CO2_KG_PER_KM) == set(CommuteMode)
    for table in (FUEL_PM25_G_PER_KG, HEATING_FUEL_KG_PER_DAY, COOKING_FUEL_KG_PER_DAY):
        assert set(table) == set(Fuel)


def test_commute_emissions_count_both_directions() -> None:
    assert commute_co2_kg_per_day(10, CommuteMode.CAR) == pytest.approx(3.32)


def test_commute_switch_saving() -> None:
    saved = commute_co2_saved_kg_per_day(10, CommuteMode.CAR, CommuteMode.METRO)
    assert saved == pytest.approx(2 * 10 * (0.166 - 0.028))


def test_commute_saving_is_never_negative() -> None:
    assert commute_co2_saved_kg_per_day(10, CommuteMode.BICYCLE, CommuteMode.CAR) == 0


def test_indoor_ratio_without_purifier_uses_infiltration_and_deposition() -> None:
    assert indoor_outdoor_ratio(15) == pytest.approx(0.5 / 0.7)


def test_purifier_and_sealing_both_lower_indoor_pm() -> None:
    baseline = indoor_outdoor_ratio(15)
    assert indoor_outdoor_ratio(15, cadr_m3h=250) < baseline
    assert indoor_outdoor_ratio(15, infiltration_ach=SEALED_INFILTRATION_ACH) < baseline


def test_same_purifier_helps_less_in_a_bigger_room() -> None:
    assert indoor_outdoor_ratio(10, cadr_m3h=250) < indoor_outdoor_ratio(40, cadr_m3h=250)


@pytest.mark.parametrize(
    ("baseline", "improved", "expected"),
    [(100, 25, 75.0), (100, 100, 0.0), (50, 80, 0.0), (0, 10, 0.0)],
)
def test_exposure_reduction(baseline: float, improved: float, expected: float) -> None:
    assert exposure_reduction_pct(baseline, improved) == pytest.approx(expected)


def test_recommended_cadr_gives_five_air_changes() -> None:
    assert recommended_cadr_m3h(15) == pytest.approx(15 * 2.7 * 5)


def test_wood_heating_to_electric_saves_all_stove_pm() -> None:
    saved = fuel_switch_pm25_saved_g_per_day(Fuel.WOOD, Fuel.ELECTRIC, HEATING_FUEL_KG_PER_DAY)
    assert saved == pytest.approx(10.0 * 6.0)


def test_switching_to_a_dirtier_fuel_saves_nothing() -> None:
    assert fuel_switch_pm25_saved_g_per_day(Fuel.GAS, Fuel.WOOD, COOKING_FUEL_KG_PER_DAY) == 0
