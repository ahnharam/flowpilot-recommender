"""Deterministic, explainable multi-score routine recommendation engine."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import (
    Environment,
    InterruptionLevel,
    PreferredStyle,
    RecommendationRequest,
    RecommendationResponse,
    RoutineRecommendation,
    ScoreBreakdown,
    TaskType,
    TimelineStep,
)


@dataclass(frozen=True)
class BlockDefinition:
    title: str
    action: str
    weight: float


@dataclass(frozen=True)
class RoutineDefinition:
    routine_id: str
    title: str
    tagline: str
    summary: str
    min_minutes: int
    ideal_minutes: int
    max_minutes: int
    energies: frozenset[int]
    environments: frozenset[Environment]
    tasks: frozenset[TaskType]
    interruptions: frozenset[InterruptionLevel]
    styles: frozenset[PreferredStyle]
    goal_keywords: tuple[str, ...]
    blocks: tuple[BlockDefinition, ...]
    tips: tuple[str, ...]


ALL_ENVIRONMENTS = frozenset(Environment)
ALL_TASKS = frozenset(TaskType)

ROUTINES: tuple[RoutineDefinition, ...] = (
    RoutineDefinition(
        routine_id="deep-focus-flight",
        title="딥 포커스 플라이트",
        tagline="긴 호흡으로 가장 중요한 한 덩어리를 끝내는 몰입 루틴",
        summary="알림을 차단하고 두 번의 집중 비행 사이에 짧은 회복 구간을 둡니다.",
        min_minutes=50,
        ideal_minutes=90,
        max_minutes=120,
        energies=frozenset({4, 5}),
        environments=frozenset({Environment.QUIET}),
        tasks=frozenset(
            {TaskType.STUDY, TaskType.CODING, TaskType.WRITING, TaskType.READING}
        ),
        interruptions=frozenset({InterruptionLevel.LOW}),
        styles=frozenset({PreferredStyle.STRUCTURED, PreferredStyle.FLEXIBLE}),
        goal_keywords=("완료", "구현", "집중", "보고서", "finish", "implement", "deep"),
        blocks=(
            BlockDefinition("비행 계획", "{goal}의 완료 기준을 한 문장으로 적고 필요한 창만 남기세요.", 0.08),
            BlockDefinition("1차 몰입", "가장 난도가 높은 핵심 작업을 끊지 않고 진행하세요.", 0.40),
            BlockDefinition("활주로 회복", "화면에서 눈을 떼고 물을 마시며 진행 방향만 점검하세요.", 0.10),
            BlockDefinition("2차 몰입", "남은 핵심 작업을 완료 기준까지 밀어붙이세요.", 0.34),
            BlockDefinition("착륙 기록", "결과와 다음 행동을 각각 한 줄로 기록하세요.", 0.08),
        ),
        tips=(
            "집중 구간에는 메신저와 휴대전화 알림을 모두 끄세요.",
            "막힌 지점은 즉시 파고들기보다 메모한 뒤 다음 가능한 작업으로 이동하세요.",
        ),
    ),
    RoutineDefinition(
        routine_id="classic-pomodoro",
        title="포모도로 코어",
        tagline="선명한 집중과 회복을 번갈아 쓰는 안정형 루틴",
        summary="준비, 집중, 회복, 마무리를 분리해 무리 없이 추진력을 유지합니다.",
        min_minutes=25,
        ideal_minutes=50,
        max_minutes=70,
        energies=frozenset({2, 3, 4}),
        environments=frozenset(
            {Environment.QUIET, Environment.SHARED, Environment.CAFE}
        ),
        tasks=ALL_TASKS,
        interruptions=frozenset({InterruptionLevel.LOW, InterruptionLevel.MEDIUM}),
        styles=frozenset({PreferredStyle.STRUCTURED}),
        goal_keywords=("공부", "과제", "정리", "study", "assignment", "review"),
        blocks=(
            BlockDefinition("목표 고정", "{goal}에서 이번 세션에 끝낼 범위를 체크리스트로 고정하세요.", 0.10),
            BlockDefinition("집중 라운드", "타이머가 끝날 때까지 한 작업만 진행하세요.", 0.48),
            BlockDefinition("의도적 휴식", "자리에서 일어나 몸을 움직이고 화면은 보지 마세요.", 0.14),
            BlockDefinition("완성 라운드", "첫 라운드 결과를 다듬고 완료 표시를 남기세요.", 0.22),
            BlockDefinition("회고", "잘된 점 하나와 다음 시작점을 적으세요.", 0.06),
        ),
        tips=(
            "타이머 도중 떠오른 다른 일은 별도 메모에 적고 즉시 돌아오세요.",
            "휴식 시간에 숏폼이나 메신저를 열지 않으면 재진입이 쉬워집니다.",
        ),
    ),
    RoutineDefinition(
        routine_id="micro-launch",
        title="마이크로 런치",
        tagline="부담을 최소화해 지금 바로 시동을 거는 초단기 루틴",
        summary="작은 성공을 빠르게 만든 뒤 다음 행동을 예약해 낮은 에너지에서도 시작합니다.",
        min_minutes=10,
        ideal_minutes=15,
        max_minutes=25,
        energies=frozenset({1, 2, 3}),
        environments=ALL_ENVIRONMENTS,
        tasks=ALL_TASKS,
        interruptions=frozenset({InterruptionLevel.MEDIUM, InterruptionLevel.HIGH}),
        styles=frozenset({PreferredStyle.FLEXIBLE, PreferredStyle.GAMIFIED}),
        goal_keywords=("시작", "조금", "간단", "start", "quick", "small"),
        blocks=(
            BlockDefinition("2분 시동", "{goal}에 필요한 파일을 열고 가장 작은 첫 행동을 고르세요.", 0.16),
            BlockDefinition("미니 질주", "완벽함을 미루고 보이는 결과 하나를 만드세요.", 0.56),
            BlockDefinition("완료 체크", "방금 만든 결과를 확인하고 작은 성공을 표시하세요.", 0.16),
            BlockDefinition("다음 발판", "다음 세션의 첫 행동을 한 문장으로 남기세요.", 0.12),
        ),
        tips=(
            "목표가 커 보이면 결과물이 아니라 첫 동작을 완료 기준으로 삼으세요.",
            "끝난 뒤 여유가 있어도 먼저 기록하고, 새 타이머로 연장하세요.",
        ),
    ),
    RoutineDefinition(
        routine_id="noise-shield",
        title="노이즈 실드",
        tagline="소음과 방해를 흡수하며 재진입 비용을 줄이는 방어형 루틴",
        summary="짧은 집중 단위와 재진입 메모를 사용해 공유 공간에서도 흐름을 지킵니다.",
        min_minutes=20,
        ideal_minutes=40,
        max_minutes=75,
        energies=frozenset({2, 3, 4}),
        environments=frozenset({Environment.SHARED, Environment.CAFE}),
        tasks=frozenset(
            {TaskType.STUDY, TaskType.CODING, TaskType.WRITING, TaskType.READING}
        ),
        interruptions=frozenset({InterruptionLevel.MEDIUM, InterruptionLevel.HIGH}),
        styles=frozenset({PreferredStyle.STRUCTURED, PreferredStyle.FLEXIBLE}),
        goal_keywords=("카페", "소음", "도서관", "cafe", "noise", "interrupt"),
        blocks=(
            BlockDefinition("방어막 설정", "이어폰과 방해 금지 표시를 준비하고 {goal}의 시작점을 적으세요.", 0.12),
            BlockDefinition("집중 버스트", "한 가지 산출물에만 집중하세요.", 0.42),
            BlockDefinition("재진입 표식", "현재 위치와 바로 다음 행동을 짧게 메모하세요.", 0.10),
            BlockDefinition("집중 버스트", "메모에서 즉시 재개해 결과물을 완성하세요.", 0.28),
            BlockDefinition("방어막 해제", "진행 상황을 저장하고 다음 재개 지점을 남기세요.", 0.08),
        ),
        tips=(
            "가사 없는 일정한 배경음이나 노이즈 캔슬링을 활용하세요.",
            "방해를 받으면 설명을 길게 남기지 말고 ‘다음 행동’만 적어 두세요.",
        ),
    ),
    RoutineDefinition(
        routine_id="creative-wave",
        title="크리에이티브 웨이브",
        tagline="발산과 수렴을 분리해 아이디어를 결과물로 바꾸는 창작 루틴",
        summary="판단 없는 아이디어 생성 후 가장 유망한 안을 골라 빠르게 구체화합니다.",
        min_minutes=30,
        ideal_minutes=60,
        max_minutes=100,
        energies=frozenset({3, 4, 5}),
        environments=frozenset({Environment.QUIET, Environment.CAFE}),
        tasks=frozenset({TaskType.WRITING, TaskType.CREATIVE}),
        interruptions=frozenset({InterruptionLevel.LOW, InterruptionLevel.MEDIUM}),
        styles=frozenset({PreferredStyle.FLEXIBLE, PreferredStyle.GAMIFIED}),
        goal_keywords=("아이디어", "기획", "디자인", "글", "idea", "design", "creative"),
        blocks=(
            BlockDefinition("질문 정의", "{goal}을 ‘어떻게 하면 …할 수 있을까?’ 질문으로 바꾸세요.", 0.10),
            BlockDefinition("아이디어 발산", "평가하지 말고 가능한 선택지를 최대한 많이 만드세요.", 0.32),
            BlockDefinition("선택", "효과와 실행 가능성을 기준으로 한 가지를 고르세요.", 0.12),
            BlockDefinition("프로토타입", "선택한 아이디어를 검토 가능한 초안으로 만드세요.", 0.38),
            BlockDefinition("한 줄 피드백", "좋은 점과 다음 개선점을 한 줄씩 적으세요.", 0.08),
        ),
        tips=(
            "발산 구간에는 맞춤법이나 세부 품질을 고치지 마세요.",
            "수렴 구간에는 새 아이디어를 추가하지 말고 선택한 안을 완성하세요.",
        ),
    ),
    RoutineDefinition(
        routine_id="admin-batch",
        title="어드민 배치",
        tagline="자잘한 일을 묶어 인지 전환 비용을 줄이는 처리형 루틴",
        summary="유사한 행정 작업을 한 번에 모아 빠르게 분류하고 처리합니다.",
        min_minutes=15,
        ideal_minutes=35,
        max_minutes=60,
        energies=frozenset({1, 2, 3}),
        environments=ALL_ENVIRONMENTS,
        tasks=frozenset({TaskType.ADMIN}),
        interruptions=frozenset({InterruptionLevel.MEDIUM, InterruptionLevel.HIGH}),
        styles=frozenset({PreferredStyle.STRUCTURED, PreferredStyle.FLEXIBLE}),
        goal_keywords=("메일", "제출", "정리", "신청", "email", "submit", "admin"),
        blocks=(
            BlockDefinition("수집", "{goal}와 관련된 작은 작업을 한 목록에 모두 모으세요.", 0.14),
            BlockDefinition("빠른 분류", "2분 내 처리, 답변 대기, 집중 필요 세 묶음으로 나누세요.", 0.16),
            BlockDefinition("일괄 처리", "2분 내 처리 가능한 항목부터 같은 종류끼리 끝내세요.", 0.52),
            BlockDefinition("위임·예약", "남은 항목의 담당자나 실행 시간을 확정하세요.", 0.12),
            BlockDefinition("인박스 제로", "완료 표시와 후속 알림을 확인하세요.", 0.06),
        ),
        tips=(
            "답장이 필요한 항목은 초안을 한꺼번에 만든 뒤 연속해서 보내세요.",
            "집중이 필요한 일은 억지로 섞지 말고 별도 몰입 세션으로 예약하세요.",
        ),
    ),
    RoutineDefinition(
        routine_id="recovery-ramp",
        title="리커버리 램프",
        tagline="낮은 에너지에서 천천히 집중 속도를 올리는 회복형 루틴",
        summary="몸과 작업 환경을 먼저 정돈하고 쉬운 단계부터 난도를 올립니다.",
        min_minutes=15,
        ideal_minutes=30,
        max_minutes=50,
        energies=frozenset({1, 2}),
        environments=frozenset({Environment.QUIET, Environment.SHARED}),
        tasks=ALL_TASKS,
        interruptions=frozenset({InterruptionLevel.LOW, InterruptionLevel.MEDIUM}),
        styles=frozenset({PreferredStyle.FLEXIBLE, PreferredStyle.GAMIFIED}),
        goal_keywords=("피곤", "회복", "복습", "tired", "recover", "review"),
        blocks=(
            BlockDefinition("상태 리셋", "물과 자세를 정돈하고 {goal}에 필요한 것만 책상에 두세요.", 0.16),
            BlockDefinition("쉬운 진입", "이미 아는 부분이나 단순한 단계부터 시작하세요.", 0.26),
            BlockDefinition("핵심 오르막", "지금 가능한 가장 중요한 한 단계를 진행하세요.", 0.40),
            BlockDefinition("에너지 보존", "성과를 저장하고 무리하지 않을 다음 시작점을 남기세요.", 0.18),
        ),
        tips=(
            "카페인보다 먼저 물, 환기, 자세를 점검하세요.",
            "계획보다 속도가 느려도 범위를 줄일 뿐 세션을 실패로 판단하지 마세요.",
        ),
    ),
    RoutineDefinition(
        routine_id="commute-capsule",
        title="커뮤트 캡슐",
        tagline="이동 중에도 안전하게 완료 가능한 작은 성과를 만드는 루틴",
        summary="오프라인 자료와 짧은 단위를 활용해 연결이 불안정한 이동 환경에 맞춥니다.",
        min_minutes=10,
        ideal_minutes=25,
        max_minutes=45,
        energies=frozenset({1, 2, 3}),
        environments=frozenset({Environment.COMMUTE}),
        tasks=frozenset({TaskType.STUDY, TaskType.READING, TaskType.ADMIN}),
        interruptions=frozenset({InterruptionLevel.MEDIUM, InterruptionLevel.HIGH}),
        styles=frozenset({PreferredStyle.FLEXIBLE, PreferredStyle.GAMIFIED}),
        goal_keywords=("이동", "읽기", "암기", "commute", "read", "memorize"),
        blocks=(
            BlockDefinition("캡슐 선택", "{goal}에서 이동 중 안전하게 할 수 있는 범위만 고르세요.", 0.16),
            BlockDefinition("오프라인 몰입", "다운로드한 자료로 읽기·복습·정리를 진행하세요.", 0.54),
            BlockDefinition("기억 회수", "자료를 덮고 핵심 세 가지를 떠올려 적으세요.", 0.18),
            BlockDefinition("도착 메모", "도착 후 이어서 할 첫 행동을 예약하세요.", 0.12),
        ),
        tips=(
            "출발 전에 자료를 내려받아 네트워크 변화로 인한 중단을 막으세요.",
            "걷거나 환승할 때는 화면을 보지 말고 안전을 최우선으로 하세요.",
        ),
    ),
)


TASK_LABELS = {
    TaskType.STUDY: "학습",
    TaskType.CODING: "코딩",
    TaskType.WRITING: "글쓰기",
    TaskType.CREATIVE: "창작",
    TaskType.READING: "읽기",
    TaskType.ADMIN: "행정",
}
ENVIRONMENT_LABELS = {
    Environment.QUIET: "조용한 개인 공간",
    Environment.SHARED: "공유 공간",
    Environment.CAFE: "카페",
    Environment.COMMUTE: "이동 중",
}
INTERRUPTION_LABELS = {
    InterruptionLevel.LOW: "낮은 방해",
    InterruptionLevel.MEDIUM: "보통 방해",
    InterruptionLevel.HIGH: "높은 방해",
}

SCORE_WEIGHTS = {
    "task_fit": 0.24,
    "time_fit": 0.20,
    "energy_fit": 0.16,
    "environment_fit": 0.14,
    "interruption_fit": 0.10,
    "style_fit": 0.08,
    "goal_fit": 0.08,
}


def _time_fit(routine: RoutineDefinition, minutes: int) -> float:
    if minutes < routine.min_minutes:
        return max(15.0, 100.0 - (routine.min_minutes - minutes) * 5.0)
    if minutes > routine.max_minutes:
        return max(25.0, 100.0 - (minutes - routine.max_minutes) * 1.2)
    distance = abs(minutes - routine.ideal_minutes)
    span = max(
        routine.ideal_minutes - routine.min_minutes,
        routine.max_minutes - routine.ideal_minutes,
        1,
    )
    return max(78.0, 100.0 - (distance / span) * 22.0)


def _energy_fit(routine: RoutineDefinition, energy: int) -> float:
    distance = min(abs(energy - target) for target in routine.energies)
    return max(20.0, 100.0 - distance * 25.0)


def _interruption_fit(
    routine: RoutineDefinition, interruption: InterruptionLevel
) -> float:
    if interruption in routine.interruptions:
        return 100.0
    order = {
        InterruptionLevel.LOW: 1,
        InterruptionLevel.MEDIUM: 2,
        InterruptionLevel.HIGH: 3,
    }
    distance = min(
        abs(order[interruption] - order[target]) for target in routine.interruptions
    )
    return 70.0 if distance == 1 else 40.0


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _goal_fit(routine: RoutineDefinition, goal: str) -> float:
    normalized_goal = _normalize_text(goal)
    return 100.0 if any(keyword in normalized_goal for keyword in routine.goal_keywords) else 65.0


def _score(
    routine: RoutineDefinition, request: RecommendationRequest
) -> ScoreBreakdown:
    component_scores = {
        "task_fit": 100.0 if request.task_type in routine.tasks else 35.0,
        "time_fit": _time_fit(routine, request.available_minutes),
        "energy_fit": _energy_fit(routine, request.energy_level),
        "environment_fit": 100.0
        if request.environment in routine.environments
        else 45.0,
        "interruption_fit": _interruption_fit(
            routine, request.interruption_level
        ),
        "style_fit": 100.0
        if request.preferred_style in routine.styles
        else 55.0,
        "goal_fit": _goal_fit(routine, request.goal),
    }
    total = sum(
        component_scores[name] * weight for name, weight in SCORE_WEIGHTS.items()
    )
    rounded = {name: round(value, 1) for name, value in component_scores.items()}
    return ScoreBreakdown(**rounded, total=round(total, 1))


def _allocate_minutes(total: int, weights: tuple[float, ...]) -> list[int]:
    """Allocate exact integer minutes while guaranteeing one minute per block."""

    remaining = total - len(weights)
    weight_sum = sum(weights)
    raw_extras = [remaining * weight / weight_sum for weight in weights]
    extras = [math.floor(value) for value in raw_extras]
    unassigned = remaining - sum(extras)
    remainder_order = sorted(
        range(len(weights)),
        key=lambda index: (-(raw_extras[index] - extras[index]), index),
    )
    for index in remainder_order[:unassigned]:
        extras[index] += 1
    return [extra + 1 for extra in extras]


def _timeline(
    routine: RoutineDefinition, request: RecommendationRequest
) -> tuple[int, list[TimelineStep]]:
    total = min(request.available_minutes, routine.max_minutes)
    durations = _allocate_minutes(
        total, tuple(block.weight for block in routine.blocks)
    )
    steps: list[TimelineStep] = []
    cursor = 0
    for sequence, (block, duration) in enumerate(
        zip(routine.blocks, durations, strict=True), start=1
    ):
        end = cursor + duration
        steps.append(
            TimelineStep(
                sequence=sequence,
                start_minute=cursor,
                end_minute=end,
                duration_minutes=duration,
                title=block.title,
                action=block.action.format(goal=request.goal),
            )
        )
        cursor = end
    return total, steps


def _reasons(
    request: RecommendationRequest, scores: ScoreBreakdown
) -> list[str]:
    task_reason = (
        f"{TASK_LABELS[request.task_type]} 작업 적합도 {scores.task_fit:.0f}점으로 "
        "핵심 진행 방식이 잘 맞습니다."
        if scores.task_fit >= 80
        else f"{TASK_LABELS[request.task_type]} 전용 루틴은 아니지만, 짧은 실행 단위로 "
        f"보완했습니다(작업 적합도 {scores.task_fit:.0f}점)."
    )
    situation_reason = (
        f"{ENVIRONMENT_LABELS[request.environment]}·{INTERRUPTION_LABELS[request.interruption_level]} "
        f"조건에 잘 맞습니다(환경 {scores.environment_fit:.0f}점, 방해 대응 "
        f"{scores.interruption_fit:.0f}점)."
        if scores.environment_fit >= 80 and scores.interruption_fit >= 80
        else f"{ENVIRONMENT_LABELS[request.environment]}·{INTERRUPTION_LABELS[request.interruption_level]} "
        f"조건에서는 방해 차단 팁을 함께 적용해야 합니다(환경 {scores.environment_fit:.0f}점, "
        f"방해 대응 {scores.interruption_fit:.0f}점)."
    )
    return [
        task_reason,
        f"가용 {request.available_minutes}분과 에너지 {request.energy_level}/5를 반영한 시간·에너지 적합도가 각각 {scores.time_fit:.0f}점, {scores.energy_fit:.0f}점입니다.",
        situation_reason,
    ]


def _tips(
    routine: RoutineDefinition, request: RecommendationRequest
) -> list[str]:
    tips = list(routine.tips)
    if request.interruption_level is InterruptionLevel.HIGH:
        tips.append("중단될 때마다 현재 위치와 다음 행동을 한 줄로 남겨 재진입 시간을 줄이세요.")
    elif request.energy_level <= 2:
        tips.append("에너지가 떨어지면 목표를 포기하지 말고 완료 범위를 절반으로 줄이세요.")
    else:
        tips.append("세션 종료 1분 전에는 새 일을 시작하지 말고 결과를 저장하세요.")
    return tips


def _build_recommendation(
    routine: RoutineDefinition,
    request: RecommendationRequest,
    scores: ScoreBreakdown,
) -> RoutineRecommendation:
    total, timeline = _timeline(routine, request)
    return RoutineRecommendation(
        routine_id=routine.routine_id,
        title=routine.title,
        tagline=routine.tagline,
        summary=routine.summary,
        total_minutes=total,
        score=scores.total,
        why_it_fits=_reasons(request, scores),
        timeline=timeline,
        tips=_tips(routine, request),
        score_breakdown=scores,
    )


def _request_id(request: RecommendationRequest) -> str:
    canonical_json = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:12]
    return f"fp-{digest}"


def recommend(request: RecommendationRequest) -> RecommendationResponse:
    """Rank all routines and return one winner plus two complete alternatives."""

    ranked = sorted(
        ((routine, _score(routine, request)) for routine in ROUTINES),
        key=lambda item: (-item[1].total, item[0].routine_id),
    )
    winning_routine, winning_scores = ranked[0]
    winner = _build_recommendation(winning_routine, request, winning_scores)
    alternatives = [
        _build_recommendation(routine, request, scores)
        for routine, scores in ranked[1:3]
    ]
    rationale = (
        f"{TASK_LABELS[request.task_type]}, {request.available_minutes}분, 에너지 "
        f"{request.energy_level}/5 등 7개 적합도 점수를 가중 합산했습니다. "
        f"동점이면 루틴 ID 순으로 정렬하며, 최고점 {winner.score:.1f}점의 "
        f"‘{winner.title}’을 최종 추천했습니다."
    )
    return RecommendationResponse(
        request_id=_request_id(request),
        recommendation=winner,
        alternatives=alternatives,
        rationale=rationale,
        generated_at=datetime.now(timezone.utc),
    )
