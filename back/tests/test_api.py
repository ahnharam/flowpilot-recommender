"""HTTP contract tests for the FlowPilot FastAPI application."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


@pytest.fixture
def valid_payload() -> dict[str, object]:
    return {
        "goal": "자료구조 과제의 그래프 탐색 구현 완료",
        "available_minutes": 90,
        "energy_level": 5,
        "environment": "quiet",
        "task_type": "coding",
        "interruption_level": "low",
        "preferred_style": "structured",
    }


def test_root_exposes_discovery_links() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "FlowPilot API",
        "docs": "/docs",
        "health": "/health",
        "recommend": "/api/v1/recommend",
    }


def test_health_contract() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "flowpilot-api",
        "version": "1.0.0",
        "routine_count": 8,
    }


def test_recommendation_response_is_complete(valid_payload: dict[str, object]) -> None:
    response = client.post("/api/v1/recommend", json=valid_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"].startswith("fp-")
    assert body["algorithm_version"] == "1.0"
    assert body["recommendation"]["routine_id"] == "deep-focus-flight"
    assert len(body["alternatives"]) == 2
    assert len(body["recommendation"]["why_it_fits"]) == 3
    assert len(body["recommendation"]["timeline"]) >= 3
    assert len(body["recommendation"]["tips"]) >= 2
    assert set(body["recommendation"]["score_breakdown"]) == {
        "task_fit",
        "time_fit",
        "energy_fit",
        "environment_fit",
        "interruption_fit",
        "style_fit",
        "goal_fit",
        "total",
    }
    assert body["generated_at"].endswith("Z")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("goal", "x"),
        ("available_minutes", 9),
        ("available_minutes", 181),
        ("energy_level", 0),
        ("energy_level", 6),
        ("environment", "office"),
        ("task_type", "gaming"),
        ("interruption_level", "constant"),
        ("preferred_style", "random"),
    ],
)
def test_invalid_input_returns_422(
    valid_payload: dict[str, object], field: str, value: object
) -> None:
    valid_payload[field] = value

    response = client.post("/api/v1/recommend", json=valid_payload)

    assert response.status_code == 422
    assert response.json()["detail"]


def test_unknown_input_field_is_rejected(valid_payload: dict[str, object]) -> None:
    valid_payload["hidden_priority"] = 100

    response = client.post("/api/v1/recommend", json=valid_payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


def test_cors_preflight_allows_local_streamlit() -> None:
    response = client.options(
        "/api/v1/recommend",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8501"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_cors_does_not_reflect_unknown_origin() -> None:
    response = client.get(
        "/health", headers={"Origin": "https://untrusted.example"}
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_openapi_documents_recommendation_contract() -> None:
    schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/api/v1/recommend"]["post"]
    assert operation["requestBody"]["required"] is True
    assert "200" in operation["responses"]
    assert "RecommendationRequest" in schema["components"]["schemas"]
    assert "RecommendationResponse" in schema["components"]["schemas"]
