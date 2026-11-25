"""Validated data contracts shared by the browser, the API and the planner."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

MAX_MEMBERS_PER_GROUP = 20


class StrictModel(BaseModel):
    """Base model: unknown fields are rejected and values are immutable once validated."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class CommuteMode(StrEnum):
    """How a household member usually travels to work or school."""

    CAR = "car"
    TWO_WHEELER = "two_wheeler"
    AUTO_RICKSHAW = "auto_rickshaw"
    BUS = "bus"
    METRO = "metro"
    BICYCLE = "bicycle"
    WALK = "walk"
    WORK_FROM_HOME = "work_from_home"


class Fuel(StrEnum):
    """Energy source used for home heating or cooking."""

    NONE = "none"
    ELECTRIC = "electric"
    GAS = "gas"
    KEROSENE = "kerosene"
    WOOD = "wood"
    COAL = "coal"


class HealthCondition(StrEnum):
    """Conditions that make smog exposure more dangerous."""

    ASTHMA = "asthma"
    COPD = "copd"
    HEART_DISEASE = "heart_disease"
    PREGNANCY = "pregnancy"
    ALLERGIES = "allergies"


class Language(StrEnum):
    """Languages the advice can be written in; the member name is the display name."""

    ENGLISH = "en"
    HINDI = "hi"
    BENGALI = "bn"
    MARATHI = "mr"
    TAMIL = "ta"
    TELUGU = "te"
    SPANISH = "es"
    CHINESE = "zh"


class ActionCategory(StrEnum):
    """Groups actions so families can scan what to change at home, on the road and nearby."""

    HEALTH = "health"
    INDOOR = "indoor"
    TRANSPORT = "transport"
    HEATING = "heating"
    COOKING = "cooking"
    COMMUNITY = "community"


def _round_one_decimal(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


RoundedFloat = Annotated[float | None, AfterValidator(_round_one_decimal)]
GroupSize = Annotated[int, Field(ge=0, le=MAX_MEMBERS_PER_GROUP)]


# --- Requests ---------------------------------------------------------------------------


class Location(StrictModel):
    """A place chosen by the user from search results or browser geolocation."""

    name: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


class Household(StrictModel):
    """Who lives in the home; children, elders and health conditions raise the stakes."""

    adults: GroupSize = 1
    children: GroupSize = 0
    elderly: GroupSize = 0
    conditions: tuple[HealthCondition, ...] = Field(default=(), max_length=len(HealthCondition))

    @model_validator(mode="after")
    def _require_someone(self) -> "Household":
        if self.adults + self.children + self.elderly == 0:
            msg = "A household needs at least one member."
            raise ValueError(msg)
        return self

    @property
    def has_sensitive_members(self) -> bool:
        """True when anyone at home is at higher risk from fine particles."""
        return bool(self.children or self.elderly or self.conditions)


class Commute(StrictModel):
    """The household's main daily trip."""

    mode: CommuteMode = CommuteMode.WORK_FROM_HOME
    distance_km: float = Field(default=0, ge=0, le=200, description="One-way distance.")


class Home(StrictModel):
    """Home energy and air-cleaning setup."""

    heating: Fuel = Fuel.NONE
    cooking: Fuel = Fuel.GAS
    has_purifier: bool = False
    room_area_m2: float = Field(default=15, ge=4, le=200, description="Main living room.")


class PlanRequest(StrictModel):
    """Everything needed to tailor a plan to one family's location and lifestyle."""

    location: Location
    household: Household = Field(default_factory=Household)
    commute: Commute = Field(default_factory=Commute)
    home: Home = Field(default_factory=Home)
    exercises_outdoors: bool = False
    community_households: int = Field(default=50, ge=1, le=10_000)
    language: Language = Language.ENGLISH
    notes: str = Field(default="", max_length=300)


# --- Responses --------------------------------------------------------------------------


class Place(StrictModel):
    """A geocoding match the user can pick."""

    name: str
    admin: str | None
    country: str | None
    country_code: str | None
    latitude: float
    longitude: float


class HourlyPm(StrictModel):
    """PM2.5 forecast for one local hour."""

    time: str = Field(description="Local ISO 8601 time, e.g. 2026-11-25T14:00.")
    pm2_5: float = Field(ge=0)


class AirQualityReport(StrictModel):
    """Current air quality plus the next day's PM2.5 forecast for a location."""

    observed_at: str
    pm2_5: float = Field(ge=0)
    pm10: float | None = Field(default=None, ge=0)
    nitrogen_dioxide: float | None = Field(default=None, ge=0)
    ozone: float | None = Field(default=None, ge=0)
    aqi: int = Field(ge=0, le=500)
    aqi_scale: str
    category: str
    level: int = Field(ge=0, le=5, description="Shared severity: 0 best, 5 worst.")
    best_hour: HourlyPm
    worst_hour: HourlyPm
    forecast: tuple[HourlyPm, ...]


class Impact(StrictModel):
    """Quantified effect of one action; any field may be absent when it does not apply."""

    exposure_reduction_pct: RoundedFloat = None
    co2_kg_per_day: RoundedFloat = None
    pm25_g_per_day: RoundedFloat = None


class Action(StrictModel):
    """One recommendation with its impact and the method behind the numbers."""

    id: str
    category: ActionCategory
    title: str
    how: str
    impact: Impact
    explanation: str
    method: str


class RoutineStep(StrictModel):
    """One step in the suggested low-exposure, low-emission day."""

    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    activity: str
    why: str


class CommunityImpact(StrictModel):
    """What the same actions achieve if many neighbouring households adopt them."""

    households: int
    co2_kg_per_day: RoundedFloat
    pm25_g_per_day: RoundedFloat


class PlanResponse(StrictModel):
    """A complete, personalised plan."""

    location: str
    air: AirQualityReport
    summary: str
    routine: tuple[RoutineStep, ...]
    actions: tuple[Action, ...]
    community: CommunityImpact
    source: Literal["gemini", "rules"]


class ErrorBody(StrictModel):
    """Machine-readable error code plus a message that is safe to display."""

    code: str
    message: str


class ErrorResponse(StrictModel):
    """Envelope for every error the API returns."""

    error: ErrorBody
