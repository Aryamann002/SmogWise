"""Pure impact formulas. Every number a user sees comes from here, never from the LLM.

Constants are rounded, deliberately conservative published figures. Each one names its
source and unit, so anyone can check the maths behind a recommendation.
"""

from collections.abc import Mapping
from typing import Final

from app.schemas import CommuteMode, Fuel

ROUND_TRIP: Final = 2

# kg CO2e per passenger-km. UK DESNZ GHG Conversion Factors 2024, except the CNG
# auto-rickshaw (India GHG Program, India-specific road transport factors, 2015).
COMMUTE_CO2_KG_PER_KM: Final[Mapping[CommuteMode, float]] = {
    CommuteMode.CAR: 0.166,
    CommuteMode.TWO_WHEELER: 0.113,
    CommuteMode.AUTO_RICKSHAW: 0.107,
    CommuteMode.BUS: 0.102,
    CommuteMode.METRO: 0.028,
    CommuteMode.BICYCLE: 0.0,
    CommuteMode.WALK: 0.0,
    CommuteMode.WORK_FROM_HOME: 0.0,
}

# Single-zone indoor mass balance inputs.
INFILTRATION_ACH: Final = 0.5  # air changes/hour, closed windows; typical homes span 0.3-1.0
SEALED_INFILTRATION_ACH: Final = 0.3  # after weather-stripping windows and doors
PM25_DEPOSITION_PER_HOUR: Final = 0.2  # indoor settling rate (Riley et al., EST 2002)
CEILING_HEIGHT_M: Final = 2.7
TYPICAL_PURIFIER_CADR_M3H: Final = 250.0  # entry-level HEPA purifier, ~150 cfm
DIY_BOX_FILTER_CADR_M3H: Final = 500.0  # conservative; Corsi-Rosenthal lab tests report more
TARGET_PURIFIER_ACH: Final = 5.0  # equals the AHAM "2/3 rule" at 8-ft ceilings

# Inhaled-dose reduction of an N95/FFP2 in everyday use. Lab filtration is 95%, but
# face-seal leaks in real-world fit studies typically leave 70-80%.
N95_REAL_WORLD_EFFICIENCY: Final = 0.75

# g PM2.5 per kg of fuel in household stoves. EMEP/EEA Air Pollutant Emission Inventory
# Guidebook 2023, 1.A.4 small combustion (Tier 1), converted with typical heating values.
FUEL_PM25_G_PER_KG: Final[Mapping[Fuel, float]] = {
    Fuel.NONE: 0.0,
    Fuel.ELECTRIC: 0.0,
    Fuel.GAS: 0.1,
    Fuel.KEROSENE: 1.0,
    Fuel.WOOD: 10.0,
    Fuel.COAL: 10.0,
}

# kg of fuel a household burns on a winter day (stated as assumptions in each method).
# Cooking LPG: a 14.2 kg cylinder lasting ~35 days is ~0.4 kg/day.
HEATING_FUEL_KG_PER_DAY: Final[Mapping[Fuel, float]] = {
    Fuel.NONE: 0.0,
    Fuel.ELECTRIC: 0.0,
    Fuel.GAS: 2.0,
    Fuel.KEROSENE: 1.5,
    Fuel.WOOD: 6.0,
    Fuel.COAL: 4.0,
}
COOKING_FUEL_KG_PER_DAY: Final[Mapping[Fuel, float]] = {
    Fuel.NONE: 0.0,
    Fuel.ELECTRIC: 0.0,
    Fuel.GAS: 0.4,
    Fuel.KEROSENE: 0.5,
    Fuel.WOOD: 4.0,
    Fuel.COAL: 2.0,
}

# Open burning of leaves and yard waste: ~19 g PM2.5 per kg (US EPA AP-42, section 2.5).
OPEN_BURNING_PM25_G_PER_KG: Final = 19.0
ASSUMED_BURNING_KG_PER_DAY: Final = 1.0


def commute_co2_kg_per_day(distance_km: float, mode: CommuteMode) -> float:
    """CO2 emitted by one person's daily round trip."""
    return ROUND_TRIP * distance_km * COMMUTE_CO2_KG_PER_KM[mode]


def commute_co2_saved_kg_per_day(
    distance_km: float, current: CommuteMode, alternative: CommuteMode
) -> float:
    """CO2 avoided per day by making the same round trip with a cleaner mode."""
    saved = commute_co2_kg_per_day(distance_km, current) - commute_co2_kg_per_day(
        distance_km, alternative
    )
    return max(0.0, saved)


def indoor_outdoor_ratio(
    room_area_m2: float,
    cadr_m3h: float = 0.0,
    infiltration_ach: float = INFILTRATION_ACH,
) -> float:
    """Steady-state indoor/outdoor PM2.5 ratio for one room with closed windows.

    C_in / C_out = ACH_inf / (ACH_inf + k_deposition + CADR / volume)
    """
    volume_m3 = room_area_m2 * CEILING_HEIGHT_M
    return infiltration_ach / (infiltration_ach + PM25_DEPOSITION_PER_HOUR + cadr_m3h / volume_m3)


def exposure_reduction_pct(baseline: float, improved: float) -> float:
    """Percentage less PM2.5 breathed when the concentration falls from baseline to improved."""
    if baseline <= 0:
        return 0.0
    return max(0.0, 1 - improved / baseline) * 100


def recommended_cadr_m3h(room_area_m2: float) -> float:
    """Clean air delivery rate needed for about five clean air changes an hour."""
    return room_area_m2 * CEILING_HEIGHT_M * TARGET_PURIFIER_ACH


def fuel_pm25_g_per_day(fuel: Fuel, kg_per_day: Mapping[Fuel, float]) -> float:
    """PM2.5 a household stove emits per day when burning the given fuel."""
    return FUEL_PM25_G_PER_KG[fuel] * kg_per_day[fuel]


def fuel_switch_pm25_saved_g_per_day(
    current: Fuel, alternative: Fuel, kg_per_day: Mapping[Fuel, float]
) -> float:
    """PM2.5 avoided per day by switching a stove or heater to a cleaner fuel."""
    saved = fuel_pm25_g_per_day(current, kg_per_day) - fuel_pm25_g_per_day(alternative, kg_per_day)
    return max(0.0, saved)
