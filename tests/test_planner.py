import pytest

from app.actions import build_routine, generate_actions
from app.advisor import Advice, AdviceNote, AdviceStep
from app.planner import Planner
from app.schemas import AirQualityReport
from tests.factories import FakeAdvisor, make_request


def _advice(note_ids: list[str], routine_time: str = "15:00") -> Advice:
    return Advice(
        summary="Model summary.",
        routine=[AdviceStep(time=routine_time, activity="Air out.", why="Cleanest hour.")],
        actions=[
            AdviceNote(id=i, title=f"Title {i}", how="", explanation=f"Model says {i}.")
            for i in note_ids
        ],
    )


@pytest.mark.anyio
async def test_without_advisor_the_plan_is_rule_based(delhi_air: AirQualityReport) -> None:
    request = make_request()
    plan = await Planner(None).create_plan(request, delhi_air)
    assert plan.source == "rules"
    assert plan.actions == generate_actions(request, delhi_air)
    assert plan.routine == build_routine(request, delhi_air)
    assert plan.community.households == request.community_households


@pytest.mark.anyio
async def test_model_reorders_and_rewords_but_cannot_change_numbers(
    delhi_air: AirQualityReport,
) -> None:
    request = make_request()
    rule_actions = generate_actions(request, delhi_air)
    advisor = FakeAdvisor(_advice(["no-open-burning", "invented-action", "n95-mask"]))
    plan = await Planner(advisor).create_plan(request, delhi_air)

    assert plan.source == "gemini"
    assert [a.id for a in plan.actions][:2] == ["no-open-burning", "n95-mask"]
    assert {a.id for a in plan.actions} == {a.id for a in rule_actions}
    assert plan.actions[0].explanation == "Model says no-open-burning."
    assert plan.actions[0].title == "Title no-open-burning"
    rule_how = {a.id: a.how for a in rule_actions}
    assert plan.actions[0].how == rule_how["no-open-burning"]
    rule_impacts = {a.id: a.impact for a in rule_actions}
    assert all(a.impact == rule_impacts[a.id] for a in plan.actions)
    assert plan.summary == "Model summary."


@pytest.mark.anyio
async def test_invalid_model_routine_falls_back_to_rules(delhi_air: AirQualityReport) -> None:
    request = make_request()
    plan = await Planner(FakeAdvisor(_advice([], routine_time="7am"))).create_plan(
        request, delhi_air
    )
    assert plan.routine == build_routine(request, delhi_air)


@pytest.mark.anyio
async def test_advisor_failure_falls_back_to_rules(delhi_air: AirQualityReport) -> None:
    plan = await Planner(FakeAdvisor(None)).create_plan(make_request(), delhi_air)
    assert plan.source == "rules"


@pytest.mark.anyio
async def test_model_plans_are_cached(delhi_air: AirQualityReport) -> None:
    advisor = FakeAdvisor(_advice(["n95-mask"]))
    planner = Planner(advisor)
    first = await planner.create_plan(make_request(), delhi_air)
    second = await planner.create_plan(make_request(), delhi_air)
    assert first == second
    assert advisor.calls == 1
