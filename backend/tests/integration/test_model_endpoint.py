"""Integration tests for /v1/model/info and the readiness probe."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.features.constants import FEATURE_COLUMNS


def test_model_info_returns_200(client: TestClient) -> None:
    """The endpoint must respond with HTTP 200 when a predictor is loaded."""
    response = client.get("/v1/model/info")
    assert response.status_code == 200, response.text


def test_model_info_response_shape(client: TestClient) -> None:
    """Response must include the contract fields."""
    response = client.get("/v1/model/info")
    payload = response.json()
    expected = {
        "model_name",
        "model_version",
        "model_stage",
        "model_loaded",
        "optimal_threshold",
        "feature_count",
        "loaded_at",
    }
    assert expected.issubset(payload.keys())
    assert payload["model_loaded"] is True
    assert payload["feature_count"] == len(FEATURE_COLUMNS)


def test_model_info_503_when_no_model(client_without_model: TestClient) -> None:
    """/v1/model/info must return 503 when the predictor is absent."""
    response = client_without_model.get("/v1/model/info")
    assert response.status_code == 503


def test_ready_200_when_model_loaded(client: TestClient) -> None:
    """/ready returns 200 + model_loaded=true when the predictor is set."""
    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["model_loaded"] is True
    assert payload["status"] == "ready"


def test_ready_503_when_no_model(client_without_model: TestClient) -> None:
    """/ready returns 503 + model_loaded=false when the predictor is absent."""
    response = client_without_model.get("/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["model_loaded"] is False
