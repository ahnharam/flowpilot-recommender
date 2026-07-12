"""FastAPI entry point for the FlowPilot backend."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .models import HealthResponse, RecommendationRequest, RecommendationResponse
from .recommender import ROUTINES, recommend


def _cors_origins() -> list[str]:
    raw_origins = os.getenv(
        "FLOWPILOT_CORS_ORIGINS",
        "http://localhost:8501,http://127.0.0.1:8501",
    )
    return list(dict.fromkeys(origin.strip() for origin in raw_origins.split(",") if origin.strip()))


app = FastAPI(
    title="FlowPilot API",
    version=__version__,
    description=(
        "상황, 에너지, 시간과 작업 특성을 함께 점수화해 설명 가능한 몰입 루틴을 "
        "추천하는 API"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)


@app.get("/", tags=["meta"])
def api_info() -> dict[str, str]:
    """Return discoverable links without duplicating the health endpoint."""

    return {
        "service": "FlowPilot API",
        "docs": "/docs",
        "health": "/health",
        "recommend": "/api/v1/recommend",
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """A dependency-free liveness probe suitable for Docker health checks."""

    return HealthResponse(version=__version__, routine_count=len(ROUTINES))


@app.post(
    "/api/v1/recommend",
    response_model=RecommendationResponse,
    response_model_exclude_none=True,
    tags=["recommendation"],
    summary="상황 기반 몰입 루틴 추천",
)
def create_recommendation(
    request: RecommendationRequest,
) -> RecommendationResponse:
    """Return the top deterministic recommendation and two alternatives."""

    return recommend(request)
