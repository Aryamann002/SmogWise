"""Builds the final plan: rule-based actions first, then optional Gemini personalisation."""

import hashlib
import logging
from typing import Final

from app.actions import build_routine, community_impact, generate_actions, summarise
from app.advisor import Advice, AdviceNote, Advisor
from app.cache import TTLCache
from app.errors import AdvisorError
from app.schemas import Action, AirQualityReport, PlanRequest, PlanResponse, RoutineStep

logger = logging.getLogger(__name__)

PLAN_CACHE_TTL_S: Final = 15 * 60
PLAN_CACHE_MAX_ENTRIES: Final = 256


def merge_advice(fallback: PlanResponse, advice: Advice) -> PlanResponse:
    """Apply the model's ranking and wording to the rule-based plan, keeping its numbers.

    Unknown action IDs are ignored, actions the model skipped keep their rule-based text and
    order, and an unusable routine falls back to the rule-based one.
    """
    by_id = {action.id: action for action in fallback.actions}
    notes = {note.id: note for note in advice.actions if note.id in by_id}
    ranked_ids = list(notes) + [action_id for action_id in by_id if action_id not in notes]
    actions = tuple(_reworded(by_id[action_id], notes.get(action_id)) for action_id in ranked_ids)
    return fallback.model_copy(
        update={
            "summary": advice.summary or fallback.summary,
            "routine": _valid_routine(advice) or fallback.routine,
            "actions": actions,
            "source": "gemini",
        }
    )


def _reworded(action: Action, note: AdviceNote | None) -> Action:
    if note is None:
        return action
    return action.model_copy(
        update={
            "title": note.title or action.title,
            "how": note.how or action.how,
            "explanation": note.explanation or action.explanation,
        }
    )


def _valid_routine(advice: Advice) -> tuple[RoutineStep, ...]:
    try:
        steps = [RoutineStep(time=s.time, activity=s.activity, why=s.why) for s in advice.routine]
    except ValueError:
        logger.info("Discarded model routine with invalid times")
        return ()
    return tuple(sorted(steps, key=lambda step: step.time))


def _cache_key(request: PlanRequest, air: AirQualityReport) -> str:
    raw = request.model_dump_json() + air.model_dump_json()
    return hashlib.sha256(raw.encode()).hexdigest()


class Planner:
    """Produces plans and caches model-written ones to save latency and API cost."""

    def __init__(self, advisor: Advisor | None) -> None:
        self._advisor = advisor
        self._cache: TTLCache[str, PlanResponse] = TTLCache(
            PLAN_CACHE_TTL_S, PLAN_CACHE_MAX_ENTRIES
        )

    async def create_plan(self, request: PlanRequest, air: AirQualityReport) -> PlanResponse:
        """Return a plan, preferring Gemini's wording and falling back to rules on failure."""
        key = _cache_key(request, air)
        if (cached := self._cache.get(key)) is not None:
            return cached
        actions = generate_actions(request, air)
        fallback = PlanResponse(
            location=request.location.name,
            air=air,
            summary=summarise(request, air, actions),
            routine=build_routine(request, air),
            actions=actions,
            community=community_impact(actions, request.community_households),
            source="rules",
        )
        if self._advisor is None:
            return fallback
        try:
            advice = await self._advisor.advise(request, air, actions)
        except AdvisorError:
            return fallback
        plan = merge_advice(fallback, advice)
        self._cache.set(key, plan)
        return plan
