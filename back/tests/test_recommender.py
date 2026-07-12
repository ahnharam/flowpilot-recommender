"""Recommendation ranking, explanation, and timeline invariants."""

from __future__ import annotations

import pytest

from app.models import RecommendationRequest
from app.recommender import SCORE_WEIGHTS, recommend


def make_request(**overrides: object) -> RecommendationRequest:
    data: dict[str, object] = {
        "goal": "전공 공부 시작",
        "available_minutes": 50,
        "energy_level": 3,
        "environment": "quiet",
        "task_type": "study",
        "interruption_level": "low",
        "preferred_style": "structured",
    }
    data.update(overrides)
    return RecommendationRequest.model_validate(data)


@pytest.mark.parametrize(
    ("expected", "overrides"),
    [
        (
            "deep-focus-flight",
            {
                "goal": "알고리즘 구현 완료",
                "available_minutes": 90,
                "energy_level": 5,
                "task_type": "coding",
            },
        ),
        (
            "classic-pomodoro",
            {"goal": "시험 공부", "available_minutes": 50},
        ),
        (
            "micro-launch",
            {
                "goal": "코딩 과제 시작",
                "available_minutes": 15,
                "energy_level": 1,
                "environment": "commute",
                "task_type": "coding",
                "interruption_level": "high",
                "preferred_style": "gamified",
            },
        ),
        (
            "noise-shield",
            {
                "goal": "카페 소음 속 코드 리뷰",
                "available_minutes": 40,
                "environment": "cafe",
                "task_type": "coding",
                "interruption_level": "high",
            },
        ),
        (
            "creative-wave",
            {
                "goal": "서비스 아이디어 기획",
                "available_minutes": 60,
                "energy_level": 4,
                "task_type": "creative",
                "preferred_style": "flexible",
            },
        ),
        (
            "admin-batch",
            {
                "goal": "메일 답장과 서류 제출",
                "available_minutes": 35,
                "energy_level": 2,
                "environment": "shared",
                "task_type": "admin",
                "interruption_level": "high",
            },
        ),
        (
            "recovery-ramp",
            {
                "goal": "피곤하지만 강의 복습",
                "available_minutes": 30,
                "energy_level": 1,
                "environment": "quiet",
                "interruption_level": "medium",
                "preferred_style": "flexible",
            },
        ),
        (
            "commute-capsule",
            {
                "goal": "이동 중 전공책 읽기",
                "available_minutes": 25,
                "energy_level": 2,
                "environment": "commute",
                "task_type": "reading",
                "interruption_level": "high",
                "preferred_style": "flexible",
            },
        ),
    ],
)
def test_each_signature_situation_selects_its_routine(
    expected: str, overrides: dict[str, object]
) -> None:
    response = recommend(make_request(**overrides))

    assert response.recommendation.routine_id == expected


def test_same_normalized_input_is_deterministic() -> None:
    first = recommend(make_request(goal="  시험   공부  "))
    second = recommend(make_request(goal="시험 공부"))

    first_data = first.model_dump(mode="json", exclude={"generated_at"})
    second_data = second.model_dump(mode="json", exclude={"generated_at"})
    assert first_data == second_data
    assert first.request_id == second.request_id


@pytest.mark.parametrize("minutes", [10, 11, 25, 50, 90, 180])
def test_timeline_is_contiguous_and_never_exceeds_available_time(minutes: int) -> None:
    response = recommend(make_request(available_minutes=minutes))

    for routine in [response.recommendation, *response.alternatives]:
        assert routine.total_minutes <= minutes
        assert routine.timeline[0].start_minute == 0
        assert routine.timeline[-1].end_minute == routine.total_minutes
        assert sum(step.duration_minutes for step in routine.timeline) == routine.total_minutes
        for previous, current in zip(routine.timeline, routine.timeline[1:]):
            assert previous.end_minute == current.start_minute
        for index, step in enumerate(routine.timeline, start=1):
            assert step.sequence == index
            assert step.end_minute - step.start_minute == step.duration_minutes


def test_weighted_score_total_matches_public_breakdown() -> None:
    response = recommend(make_request(goal="시험 공부"))

    for routine in [response.recommendation, *response.alternatives]:
        breakdown = routine.score_breakdown
        expected = sum(
            getattr(breakdown, name) * weight
            for name, weight in SCORE_WEIGHTS.items()
        )
        assert breakdown.total == pytest.approx(round(expected, 1), abs=0.1)
        assert routine.score == breakdown.total


def test_result_contains_distinct_score_ordered_routines() -> None:
    response = recommend(make_request())
    routines = [response.recommendation, *response.alternatives]

    assert len({routine.routine_id for routine in routines}) == 3
    assert [routine.score for routine in routines] == sorted(
        (routine.score for routine in routines), reverse=True
    )


@pytest.mark.parametrize(
    "environment",
    ["quiet", "shared", "cafe", "commute"],
)
@pytest.mark.parametrize(
    "task_type",
    ["study", "coding", "writing", "creative", "reading", "admin"],
)
def test_all_public_enum_combinations_produce_valid_response(
    environment: str, task_type: str
) -> None:
    response = recommend(
        make_request(environment=environment, task_type=task_type)
    )

    assert response.recommendation.score >= response.alternatives[0].score
    assert response.alternatives[0].score >= response.alternatives[1].score
    assert response.recommendation.timeline
