"""Rules engine: turns live air quality and a household profile into ranked, quantified actions.

The output is complete on its own (it is the offline fallback) and it is the only source of
impact numbers. The LLM may reorder and re-explain these actions, but never alter them.
"""

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Final

from app.aqi import INDIA_COUNTRY_CODE, Severity
from app.impact import (
    ASSUMED_BURNING_KG_PER_DAY,
    CEILING_HEIGHT_M,
    COMMUTE_CO2_KG_PER_KM,
    COOKING_FUEL_KG_PER_DAY,
    DIY_BOX_FILTER_CADR_M3H,
    FUEL_PM25_G_PER_KG,
    HEATING_FUEL_KG_PER_DAY,
    INFILTRATION_ACH,
    N95_REAL_WORLD_EFFICIENCY,
    OPEN_BURNING_PM25_G_PER_KG,
    PM25_DEPOSITION_PER_HOUR,
    SEALED_INFILTRATION_ACH,
    TYPICAL_PURIFIER_CADR_M3H,
    commute_co2_kg_per_day,
    commute_co2_saved_kg_per_day,
    exposure_reduction_pct,
    fuel_switch_pm25_saved_g_per_day,
    indoor_outdoor_ratio,
    recommended_cadr_m3h,
)
from app.schemas import (
    Action,
    ActionCategory,
    AirQualityReport,
    CommunityImpact,
    CommuteMode,
    Fuel,
    Impact,
    PlanRequest,
    RoutineStep,
)

PRIVATE_MOTOR_MODES: Final = frozenset(
    {CommuteMode.CAR, CommuteMode.TWO_WHEELER, CommuteMode.AUTO_RICKSHAW}
)
POLLUTING_FUELS: Final = frozenset({Fuel.KEROSENE, Fuel.WOOD, Fuel.COAL})
SHORT_TRIP_KM: Final = 5.0
COMMUTE_DAYS_PER_YEAR: Final = 220
MORNING_HOURS: Final = range(6, 10)
MIN_USEFUL_REDUCTION_PCT: Final = 10.0
AIRING_MINUTES: Final = 15
MORNING_TIME: Final = "07:00"
COMMUTE_TIME: Final = "08:30"
BEDTIME: Final = "21:00"
SENSITIVE_BOOST: Final = 10


class Priority(IntEnum):
    """Ranking used when no LLM is available: safety first, then the biggest wins."""

    LOW = 30
    MEDIUM = 50
    HIGH = 70
    CRITICAL = 90


@dataclass(frozen=True, slots=True)
class RankedAction:
    """An action paired with the priority the rules engine gave it."""

    priority: int
    action: Action


Rule = Callable[[PlanRequest, AirQualityReport], RankedAction | None]


def clock_time(iso_time: str) -> str:
    """Format a local ISO 8601 timestamp as HH:MM."""
    return datetime.fromisoformat(iso_time).strftime("%H:%M")


def _morning_pm25(air: AirQualityReport) -> float:
    values = [p.pm2_5 for p in air.forecast if datetime.fromisoformat(p.time).hour in MORNING_HOURS]
    return statistics.fmean(values) if values else air.pm2_5


def _label(value: str) -> str:
    return value.replace("_", " ")


def _boost(request: PlanRequest) -> int:
    return SENSITIVE_BOOST if request.household.has_sensitive_members else 0


def _clean_air_device(request: PlanRequest) -> str:
    return "purifier" if request.home.has_purifier else "DIY air filter"


# --- Rules: each returns one ranked action, or None when it does not apply. ----------------


def heating_rule(request: PlanRequest, _air: AirQualityReport) -> RankedAction | None:
    """Swap smoky heating for electric heat; also warns about carbon monoxide."""
    fuel = request.home.heating
    if fuel not in POLLUTING_FUELS:
        return None
    kg = HEATING_FUEL_KG_PER_DAY[fuel]
    saved = fuel_switch_pm25_saved_g_per_day(fuel, Fuel.ELECTRIC, HEATING_FUEL_KG_PER_DAY)
    action = Action(
        id="heating-switch",
        category=ActionCategory.HEATING,
        title=f"Replace {fuel} heating with electric heat",
        how=(
            "Heat one room with an oil-filled electric heater, hang thick curtains and layer "
            "clothes. Never burn coal, charcoal or wood in a closed room: it can cause deadly "
            "carbon monoxide poisoning."
        ),
        impact=Impact(pm25_g_per_day=saved),
        explanation=(
            f"Burning about {kg:g} kg of {fuel} a day releases roughly {saved:.0f} g of PM2.5 "
            "into your home and street. Electric heat releases none where you live."
        ),
        method=(
            f"{FUEL_PM25_G_PER_KG[fuel]:g} g PM2.5/kg x {kg:g} kg/day (assumed winter use). "
            "Emission factor: EMEP/EEA Guidebook 2023, 1.A.4 small combustion."
        ),
    )
    return RankedAction(Priority.CRITICAL, action)


def mask_rule(request: PlanRequest, air: AirQualityReport) -> RankedAction | None:
    """Recommend a fitted N95 once air is unhealthy for sensitive groups."""
    if air.level < Severity.SENSITIVE:
        return None
    pct = N95_REAL_WORLD_EFFICIENCY * 100
    action = Action(
        id="n95-mask",
        category=ActionCategory.HEALTH,
        title="Wear a well-fitted N95 outdoors",
        how=(
            "Choose an N95, FFP2 or KN95 and press the nose clip so there are no gaps. Cloth and "
            "surgical masks do little against smog. Masks are not for children under 2."
        ),
        impact=Impact(exposure_reduction_pct=pct),
        explanation=(
            f"Air is {air.category} (AQI {air.aqi}). A snug N95 blocks about {pct:.0f}% of the "
            "fine particles you would otherwise breathe outdoors."
        ),
        method="Real-world N95 protection with typical face-seal leaks (70-80%), not the lab 95%.",
    )
    return RankedAction(Priority.HIGH + _boost(request), action)


def purifier_rule(request: PlanRequest, air: AirQualityReport) -> RankedAction:
    """Create a clean room with a purifier, or a cheap DIY filter when there is none."""
    area = request.home.room_area_m2
    cadr = TYPICAL_PURIFIER_CADR_M3H if request.home.has_purifier else DIY_BOX_FILTER_CADR_M3H
    before = indoor_outdoor_ratio(area) * air.pm2_5
    after = indoor_outdoor_ratio(area, cadr) * air.pm2_5
    if request.home.has_purifier:
        action_id, title = "purifier-clean-room", "Make one clean room with your purifier"
        how = (
            "Run it on high in the room where the family sleeps, with doors and windows shut. "
            "Replace the HEPA filter as the maker advises."
        )
    else:
        action_id, title = "diy-air-filter", "Build a DIY box-fan air filter"
        how = (
            "Tape four MERV-13 (or better) filters into a cube with a box fan on top blowing "
            "outwards. It costs a fraction of a purifier; run it where the family sleeps."
        )
    action = Action(
        id=action_id,
        category=ActionCategory.INDOOR,
        title=title,
        how=how,
        impact=Impact(exposure_reduction_pct=exposure_reduction_pct(before, after)),
        explanation=(
            f"In a {area:g} m² room, indoor PM2.5 falls from about {before:.0f} to {after:.0f} "
            f"µg/m³. Aim for a clean air delivery rate of at least "
            f"{recommended_cadr_m3h(area):.0f} m³/h for this room."
        ),
        method=(
            "Indoor/outdoor ratio = ACH / (ACH + deposition + CADR / room volume), with ACH "
            f"{INFILTRATION_ACH}, deposition {PM25_DEPOSITION_PER_HOUR}/h, CADR {cadr:.0f} m³/h, "
            f"ceiling {CEILING_HEIGHT_M} m. Target CADR = 5 air changes/hour (AHAM 2/3 rule)."
        ),
    )
    return RankedAction(Priority.HIGH + _boost(request), action)


def exercise_rule(request: PlanRequest, air: AirQualityReport) -> RankedAction | None:
    """Move workouts to the cleanest hour, or indoors when the air is very unhealthy."""
    if not request.exercises_outdoors:
        return None
    if air.level >= Severity.VERY_UNHEALTHY:
        return _indoor_exercise(request, air)
    morning, best = _morning_pm25(air), air.best_hour
    reduction = exposure_reduction_pct(morning, best.pm2_5)
    if reduction < MIN_USEFUL_REDUCTION_PCT:
        return None
    action = Action(
        id="exercise-timing",
        category=ActionCategory.HEALTH,
        title=f"Move outdoor exercise to {clock_time(best.time)}",
        how=(
            "Skip early-morning walks and runs. In winter, cold air traps smog near the ground "
            "until the sun warms it."
        ),
        impact=Impact(exposure_reduction_pct=reduction),
        explanation=(
            f"PM2.5 averages {morning:.0f} µg/m³ between 6 and 10 am but falls to "
            f"{best.pm2_5:.0f} µg/m³ at {clock_time(best.time)}, so the same workout puts "
            f"{reduction:.0f}% less smog in your lungs."
        ),
        method=(
            "1 - (PM2.5 at the cleanest daytime hour / average PM2.5 06:00-10:00), from the "
            "Open-Meteo hourly forecast. At equal effort, inhaled dose scales with concentration."
        ),
    )
    return RankedAction(Priority.HIGH + _boost(request), action)


def _indoor_exercise(request: PlanRequest, air: AirQualityReport) -> RankedAction:
    cadr = TYPICAL_PURIFIER_CADR_M3H if request.home.has_purifier else 0.0
    reduction = exposure_reduction_pct(1.0, indoor_outdoor_ratio(request.home.room_area_m2, cadr))
    action = Action(
        id="exercise-indoors",
        category=ActionCategory.HEALTH,
        title="Exercise indoors today",
        how="Do yoga, stretching or a bodyweight workout with the windows shut.",
        impact=Impact(exposure_reduction_pct=reduction),
        explanation=(
            f"Outdoor air is {air.category} right now, and hard breathing pulls in far more "
            f"particles. Indoors with windows shut you breathe about {reduction:.0f}% less PM2.5."
        ),
        method=(
            f"Indoor/outdoor ratio = {INFILTRATION_ACH} / ({INFILTRATION_ACH} + "
            f"{PM25_DEPOSITION_PER_HOUR} + CADR {cadr:.0f} m³/h / room volume) for a "
            f"{request.home.room_area_m2:g} m² room."
        ),
    )
    return RankedAction(Priority.HIGH + _boost(request), action)


def commute_rule(request: PlanRequest, air: AirQualityReport) -> RankedAction | None:
    """Shift private motor trips to active travel or rail, quantified in CO2 avoided."""
    mode, distance = request.commute.mode, request.commute.distance_km
    if mode not in PRIVATE_MOTOR_MODES or distance == 0:
        return None
    active = distance <= SHORT_TRIP_KM and air.level < Severity.VERY_UNHEALTHY
    alternative = CommuteMode.BICYCLE if active else CommuteMode.METRO
    current = commute_co2_kg_per_day(distance, mode)
    saved = commute_co2_saved_kg_per_day(distance, mode, alternative)
    action = Action(
        id="commute-switch",
        category=ActionCategory.TRANSPORT,
        title=(
            f"Walk or cycle your {distance:g} km trip"
            if active
            else "Take the metro, train or a shared bus"
        ),
        how=(
            "Choose quieter side streets, away from traffic exhaust."
            if active
            else "Walk the last stretch, and on the worst days wear an N95 on the platform."
        ),
        impact=Impact(co2_kg_per_day=saved),
        explanation=(
            f"Your {_label(mode)} trip emits about {current:.1f} kg of CO2 a day. Switching "
            f"avoids {saved:.1f} kg a day, about {saved * COMMUTE_DAYS_PER_YEAR:.0f} kg a year, "
            "and one less vehicle means less exhaust on the street."
        ),
        method=(
            f"({COMMUTE_CO2_KG_PER_KM[mode]} - {COMMUTE_CO2_KG_PER_KM[alternative]} kg CO2e/km) "
            f"x {distance:g} km x 2 trips. Factors: UK DESNZ 2024; India GHG Program 2015 for "
            "auto-rickshaws."
        ),
    )
    return RankedAction(Priority.HIGH, action)


def cooking_rule(request: PlanRequest, _air: AirQualityReport) -> RankedAction | None:
    """Move smoky cooking fuels to LPG or induction, the biggest indoor source in many homes."""
    fuel = request.home.cooking
    if fuel not in POLLUTING_FUELS:
        return None
    kg = COOKING_FUEL_KG_PER_DAY[fuel]
    saved = fuel_switch_pm25_saved_g_per_day(fuel, Fuel.GAS, COOKING_FUEL_KG_PER_DAY)
    subsidy = (
        " In India, low-income households can get a subsidised LPG connection under PMUY."
        if request.location.country_code == INDIA_COUNTRY_CODE
        else ""
    )
    action = Action(
        id="cooking-switch",
        category=ActionCategory.COOKING,
        title="Cook with LPG or induction",
        how=(
            "Until you switch, cook with a lid on, open the kitchen window and keep children "
            f"away from the smoke.{subsidy}"
        ),
        impact=Impact(pm25_g_per_day=saved),
        explanation=(
            f"A {fuel} stove burns about {kg:g} kg a day and puts roughly {saved:.0f} g of "
            "PM2.5 into your kitchen air. LPG cuts that to almost nothing."
        ),
        method=(
            f"({FUEL_PM25_G_PER_KG[fuel]:g} g/kg x {kg:g} kg/day) - (LPG "
            f"{FUEL_PM25_G_PER_KG[Fuel.GAS]:g} g/kg x {COOKING_FUEL_KG_PER_DAY[Fuel.GAS]:g} "
            "kg/day). Emission factors: EMEP/EEA Guidebook 2023, 1.A.4 small combustion."
        ),
    )
    return RankedAction(Priority.HIGH + _boost(request), action)


def ventilation_rule(request: PlanRequest, air: AirQualityReport) -> RankedAction | None:
    """Time window-opening to the cleanest hour instead of airing out in peak smog."""
    best, worst = air.best_hour, air.worst_hour
    reduction = exposure_reduction_pct(worst.pm2_5, best.pm2_5)
    if reduction < MIN_USEFUL_REDUCTION_PCT:
        return None
    action = Action(
        id="ventilation-timing",
        category=ActionCategory.INDOOR,
        title=f"Air out at {clock_time(best.time)}, shut windows by {clock_time(worst.time)}",
        how=(
            f"Open windows wide for {AIRING_MINUTES} minutes at the cleanest hour to clear "
            "cooking fumes and stale air, then keep them shut through the smoggiest hours."
        ),
        impact=Impact(exposure_reduction_pct=reduction),
        explanation=(
            f"Fresh air at {clock_time(best.time)} carries {reduction:.0f}% less PM2.5 than at "
            f"{clock_time(worst.time)} ({best.pm2_5:.0f} vs {worst.pm2_5:.0f} µg/m³)."
        ),
        method=(
            "1 - (PM2.5 at the cleanest daytime hour / PM2.5 at the smoggiest hour in the next "
            "24 h), from the Open-Meteo forecast."
        ),
    )
    return RankedAction(Priority.MEDIUM + _boost(request), action)


def seal_gaps_rule(request: PlanRequest, air: AirQualityReport) -> RankedAction:
    """Reduce leaks and indoor smoke sources: a free fix for every home."""
    area = request.home.room_area_m2
    before = indoor_outdoor_ratio(area)
    after = indoor_outdoor_ratio(area, infiltration_ach=SEALED_INFILTRATION_ACH)
    reduction = exposure_reduction_pct(before, after)
    action = Action(
        id="seal-gaps",
        category=ActionCategory.INDOOR,
        title="Seal gaps and cut indoor smoke",
        how=(
            "Weather-strip windows, add a door draught stopper and wet-mop instead of sweeping. "
            "Skip incense and mosquito coils, and run the kitchen exhaust while frying."
        ),
        impact=Impact(exposure_reduction_pct=reduction),
        explanation=(
            f"Tighter windows let in less outdoor smog: indoor PM2.5 drops about "
            f"{reduction:.0f}% even without a purifier, at around {air.pm2_5 * after:.0f} µg/m³."
        ),
        method=(
            f"Indoor/outdoor ratio with infiltration cut from {INFILTRATION_ACH} to "
            f"{SEALED_INFILTRATION_ACH} air changes/hour (deposition {PM25_DEPOSITION_PER_HOUR}/h)."
        ),
    )
    return RankedAction(Priority.MEDIUM, action)


def no_burning_rule(request: PlanRequest, _air: AirQualityReport) -> RankedAction:
    """Community action against open burning, a major winter smog source."""
    pm25 = OPEN_BURNING_PM25_G_PER_KG * ASSUMED_BURNING_KG_PER_DAY
    channel = (
        "the CPCB Sameer app"
        if request.location.country_code == INDIA_COUNTRY_CODE
        else "your local environment agency"
    )
    action = Action(
        id="no-open-burning",
        category=ActionCategory.COMMUNITY,
        title="Stop open burning on your street",
        how=(
            "Compost leaves, never burn rubbish, skip bonfires and firecrackers, and report open "
            f"burning through {channel}. Ask your neighbours to do the same."
        ),
        impact=Impact(pm25_g_per_day=pm25),
        explanation=(
            f"Every kilogram of leaves or waste that is not burned keeps about {pm25:.0f} g of "
            "PM2.5 out of the air your neighbours breathe."
        ),
        method=(
            f"{OPEN_BURNING_PM25_G_PER_KG:g} g PM2.5 per kg of leaves (US EPA AP-42, section 2.5) "
            f"x {ASSUMED_BURNING_KG_PER_DAY:g} kg/day not burned."
        ),
    )
    return RankedAction(Priority.MEDIUM, action)


RULES: Final[tuple[Rule, ...]] = (
    heating_rule,
    mask_rule,
    purifier_rule,
    exercise_rule,
    commute_rule,
    cooking_rule,
    ventilation_rule,
    seal_gaps_rule,
    no_burning_rule,
)


def generate_actions(request: PlanRequest, air: AirQualityReport) -> tuple[Action, ...]:
    """Run every rule and return the actions that apply, most important first."""
    ranked = [result for rule in RULES if (result := rule(request, air)) is not None]
    ranked.sort(key=lambda r: r.priority, reverse=True)
    return tuple(r.action for r in ranked)


def build_routine(request: PlanRequest, air: AirQualityReport) -> tuple[RoutineStep, ...]:
    """Lay out the day around the forecast's cleanest and smoggiest hours."""
    best, worst, device = air.best_hour, air.worst_hour, _clean_air_device(request)
    outdoor_ok = request.exercises_outdoors and air.level < Severity.VERY_UNHEALTHY
    steps = [
        RoutineStep(
            time=MORNING_TIME,
            activity=f"Keep windows shut and run the {device} while everyone gets ready.",
            why=f"Cold mornings trap smog near the ground (about {_morning_pm25(air):.0f} µg/m³).",
        ),
        RoutineStep(
            time=clock_time(best.time),
            activity=f"Open windows for {AIRING_MINUTES} minutes"
            + ("; this is the hour for outdoor exercise." if outdoor_ok else "."),
            why=f"Cleanest hour of the day ({best.pm2_5:.0f} µg/m³).",
        ),
        RoutineStep(
            time=clock_time(worst.time),
            activity="Keep windows shut and keep children and elders indoors.",
            why=f"Smoggiest hour of the day ({worst.pm2_5:.0f} µg/m³).",
        ),
        RoutineStep(
            time=BEDTIME,
            activity=f"Run the {device} on high in the bedroom with the door closed.",
            why="You spend about a third of the day asleep, so bedroom air matters most.",
        ),
    ]
    if request.commute.mode is not CommuteMode.WORK_FROM_HOME:
        steps.append(
            RoutineStep(
                time=COMMUTE_TIME,
                activity="Wear an N95 for the commute and avoid the busiest roads.",
                why="Rush-hour traffic corridors carry the day's highest street-level PM2.5.",
            )
        )
    return tuple(sorted(steps, key=lambda step: step.time))


def community_impact(actions: Sequence[Action], households: int) -> CommunityImpact:
    """Scale emission savings to a street or building, so families see their shared effect."""
    co2 = sum(a.impact.co2_kg_per_day or 0.0 for a in actions)
    pm25 = sum(a.impact.pm25_g_per_day or 0.0 for a in actions)
    return CommunityImpact(
        households=households,
        co2_kg_per_day=co2 * households,
        pm25_g_per_day=pm25 * households,
    )


def summarise(request: PlanRequest, air: AirQualityReport, actions: Sequence[Action]) -> str:
    """One-line overview used when the LLM is unavailable."""
    return (
        f"Air in {request.location.name} is {air.category} right now (AQI {air.aqi}, "
        f"{air.aqi_scale}). Here are {len(actions)} steps, ranked for your household, to cut "
        "your family's smog exposure and emissions today."
    )
