"""Integration tests for ``GET /metrics`` and the Prometheus middleware.

The tests drive the TestClient against the real FastAPI app with the
SQLite-backed ``client`` fixture from ``conftest.py``. No real Prometheus
or Grafana required.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_metrics_endpoint_returns_200(client: TestClient) -> None:
    """``GET /metrics`` is exposed by the instrumentator and returns 200."""
    response = client.get("/metrics")
    assert response.status_code == 200


def test_metrics_response_is_prometheus_compatible(client: TestClient) -> None:
    """Content-type must satisfy the Prometheus exposition format spec."""
    response = client.get("/metrics")
    content_type = response.headers.get("content-type", "")
    # Prometheus accepts ``text/plain`` with the ``version=0.0.4`` parameter
    # (the default) or the OpenMetrics ``application/openmetrics-text``
    # variant. Both are valid.
    assert content_type.startswith("text/plain") or "openmetrics" in content_type, (
        content_type
    )


def test_metrics_payload_contains_fraudshield_and_process_metrics(
    client: TestClient,
) -> None:
    """Payload contains both our custom and the default process metrics."""
    response = client.get("/metrics")
    body = response.text
    # Custom collectors registered at import time should always be visible
    # even before any traffic — Prometheus shows ``_created`` / declared
    # metric lines for unused counters.
    assert "fraudshield_predictions_total" in body
    assert "fraudshield_request_duration_seconds" in body
    assert "fraudshield_latest_drift_score" in body
    # The default instrumentator + prometheus_client also export Python
    # process metrics. Their presence confirms the registry is wired up.
    assert "python_info" in body or "process_cpu_seconds_total" in body


def test_predict_request_increments_fraudshield_counters(
    client: TestClient, sample_transaction: dict
) -> None:
    """After a successful prediction the metrics text reflects it."""
    response = client.post("/v1/predict", json=sample_transaction)
    assert response.status_code == 200

    metrics_body = client.get("/metrics").text
    # The label may resolve to either ``fraud`` or ``legitimate`` depending
    # on the dummy model's score — assert that at least one counter line
    # for the predictions metric is now non-zero.
    has_observation = any(
        line.startswith("fraudshield_predictions_total{")
        and not line.strip().endswith("0.0")
        for line in metrics_body.splitlines()
    )
    assert has_observation, "expected fraudshield_predictions_total to be incremented"

    # The score histogram should also have at least one observation now.
    assert "fraudshield_prediction_score_count" in metrics_body


def test_request_total_increments_per_call(client: TestClient) -> None:
    """The custom HTTP request counter ticks for every served request."""
    # Hit the health endpoint to seed something the middleware doesn't
    # skip — /v1/model/info goes through the middleware path even when
    # the predictor is the dummy. Skip /health and /metrics which the
    # middleware excludes.
    response = client.get("/v1/model/info")
    assert response.status_code == 200

    body = client.get("/metrics").text
    matches = [
        line
        for line in body.splitlines()
        if line.startswith("fraudshield_requests_total{") and "/v1/model/info" in line
    ]
    assert matches, "expected a fraudshield_requests_total sample for /v1/model/info"


def test_in_progress_gauge_is_zero_after_request_completes(
    client: TestClient, sample_transaction: dict
) -> None:
    """``fraudshield_requests_in_progress`` should drop back to 0 after a call."""
    client.post("/v1/predict", json=sample_transaction)
    body = client.get("/metrics").text
    # Pull only the lines for the in-progress gauge and assert they sum to 0.
    in_progress_lines = [
        line
        for line in body.splitlines()
        if line.startswith("fraudshield_requests_in_progress{")
    ]
    if in_progress_lines:
        total = 0.0
        for line in in_progress_lines:
            try:
                value = float(line.rsplit(" ", 1)[-1])
            except ValueError:
                continue
            total += value
        assert total == 0.0, f"in-progress gauge non-zero after request: {total}"
