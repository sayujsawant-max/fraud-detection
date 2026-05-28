"""Integration tests for the /health, /, and /ready endpoints.

These tests run without any external dependency — no Docker, no PostgreSQL,
no MLflow, no model files required.
"""

from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    """The health endpoint must respond with HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_payload_contains_ok(client: TestClient) -> None:
    """The health response body must include status=ok."""
    response = client.get("/health")
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload


def test_root_returns_metadata(client: TestClient) -> None:
    """The root endpoint must return project metadata."""
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "FraudShield API"
    assert payload["docs"] == "/docs"
    assert "version" in payload


def test_ready_returns_ready(client: TestClient) -> None:
    """The readiness endpoint must report ready in Phase 0."""
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_metrics_endpoint_exposed(client: TestClient) -> None:
    """Prometheus metrics endpoint must be exposed and return text."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
