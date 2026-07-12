"""Pydantic contracts shared by the FlowPilot API and recommendation engine."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Environment(str, Enum):
    """Where the user will run the routine."""

    QUIET = "quiet"
    SHARED = "shared"
    CAFE = "cafe"
    COMMUTE = "commute"


class TaskType(str, Enum):
    """The dominant kind of work to complete."""

    STUDY = "study"
    CODING = "coding"
    WRITING = "writing"
    CREATIVE = "creative"
    READING = "reading"
    ADMIN = "admin"


class InterruptionLevel(str, Enum):
    """Expected frequency of interruptions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PreferredStyle(str, Enum):
    """How tightly the user wants the session to be guided."""

    STRUCTURED = "structured"
    FLEXIBLE = "flexible"
    GAMIFIED = "gamified"


class ApiModel(BaseModel):
    """Strict base model that keeps the public JSON contract predictable."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RecommendationRequest(ApiModel):
    """Situation data used to select a focus routine."""

    goal: str = Field(
        min_length=2,
        max_length=120,
        description="A concrete outcome for this session.",
        examples=["자료구조 과제의 그래프 탐색 구현 완료"],
    )
    available_minutes: int = Field(
        ge=10,
        le=180,
        description="Minutes available for the complete routine.",
        examples=[50],
    )
    energy_level: int = Field(
        ge=1,
        le=5,
        description="Current energy from 1 (very low) to 5 (very high).",
        examples=[4],
    )
    environment: Environment = Field(description="Current working environment.")
    task_type: TaskType = Field(description="Primary type of work.")
    interruption_level: InterruptionLevel = Field(
        description="Expected interruption frequency."
    )
    preferred_style: PreferredStyle = Field(
        description="Preferred amount of structure for the routine."
    )

    @field_validator("goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        """Collapse whitespace so hashing and output remain deterministic."""

        return " ".join(value.split())


class TimelineStep(ApiModel):
    """One contiguous block in a recommended routine."""

    sequence: int = Field(ge=1)
    start_minute: int = Field(ge=0)
    end_minute: int = Field(ge=1)
    duration_minutes: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_interval(self) -> "TimelineStep":
        if self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be greater than start_minute")
        if self.end_minute - self.start_minute != self.duration_minutes:
            raise ValueError("duration_minutes must match the interval")
        return self


class ScoreBreakdown(ApiModel):
    """Normalized component scores used by the deterministic ranker."""

    task_fit: float = Field(ge=0, le=100)
    time_fit: float = Field(ge=0, le=100)
    energy_fit: float = Field(ge=0, le=100)
    environment_fit: float = Field(ge=0, le=100)
    interruption_fit: float = Field(ge=0, le=100)
    style_fit: float = Field(ge=0, le=100)
    goal_fit: float = Field(ge=0, le=100)
    total: float = Field(ge=0, le=100)


class RoutineRecommendation(ApiModel):
    """A fully usable routine, including explanation and execution details."""

    routine_id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=1, max_length=80)
    tagline: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=300)
    total_minutes: int = Field(ge=1, le=180)
    score: float = Field(ge=0, le=100)
    why_it_fits: list[str] = Field(min_length=3, max_length=4)
    timeline: list[TimelineStep] = Field(min_length=3, max_length=6)
    tips: list[str] = Field(min_length=2, max_length=4)
    score_breakdown: ScoreBreakdown


class RecommendationResponse(ApiModel):
    """Stable response consumed by the Streamlit client."""

    request_id: str = Field(pattern=r"^fp-[0-9a-f]{12}$")
    algorithm_version: Literal["1.0"] = "1.0"
    recommendation: RoutineRecommendation
    alternatives: list[RoutineRecommendation] = Field(min_length=2, max_length=2)
    rationale: str = Field(min_length=1, max_length=400)
    generated_at: datetime


class HealthResponse(ApiModel):
    """Container and load-balancer health response."""

    status: Literal["ok"] = "ok"
    service: Literal["flowpilot-api"] = "flowpilot-api"
    version: str
    routine_count: int = Field(ge=1)
