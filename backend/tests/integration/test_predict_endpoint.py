"""Integration tests for POST /v1/predict and POST /v1/predict/batch."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.core.config import get_settings


def test_predict_returns_200(client: TestClient, sample_transaction: dict) -> None:
    """The endpoint must respond with HTTP 200 for a valid transaction."""
    response = client.post("/v1/predict", json=sample_transaction)
    assert response.status_code == 200, response.text


def test_predict_response_shape(client: TestClient, sample_transaction: dict) -> None:
    """Response must include every contract field."""
    response = client.post("/v1/predict", json=sample_transaction)
    payload = response.json()
    expected = {
        "transaction_id",
        "fraud_probability",
        "predicted_label",
        "is_fraud",
        "model_name",
        "model_version",
        "model_stage",
        "threshold_used",
        "latency_ms",
        "timestamp",
    }
    assert expected.issubset(payload.keys())
    assert 0.0 <= payload["fraud_probability"] <= 1.0
    assert payload["predicted_label"] in (0, 1)
    assert payload["latency_ms"] >= 0


def test_predict_invalid_payload_returns_422(client: TestClient) -> None:
    """A payload missing required fields must produce HTTP 422."""
    response = client.post("/v1/predict", json={"transaction_amount": 10.0})
    assert response.status_code == 422


def test_predict_negative_amount_returns_422(
    client: TestClient, sample_transaction: dict
) -> None:
    """Negative transaction_amount must trip Pydantic validation."""
    payload = dict(sample_transaction, transaction_amount=-1.0)
    response = client.post("/v1/predict", json=payload)
    assert response.status_code == 422


def test_predict_batch_returns_200(
    client: TestClient, sample_transaction: dict
) -> None:
    """Batch endpoint must return one prediction per transaction."""
    response = client.post(
        "/v1/predict/batch",
        json={"transactions": [sample_transaction, sample_transaction]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["batch_size"] == 2
    assert len(payload["predictions"]) == 2
    assert payload["batch_latency_ms"] >= 0


def test_predict_batch_over_limit_returns_422(
    client: TestClient, sample_transaction: dict
) -> None:
    """A batch larger than MAX_BATCH_SIZE must be rejected with 422."""
    cap = get_settings().MAX_BATCH_SIZE
    response = client.post(
        "/v1/predict/batch",
        json={"transactions": [sample_transaction] * (cap + 1)},
    )
    assert response.status_code == 422


def test_predict_503_when_no_model(
    client_without_model: TestClient, sample_transaction: dict
) -> None:
    """When the predictor is not loaded, /v1/predict must return 503."""
    response = client_without_model.post("/v1/predict", json=sample_transaction)
    assert response.status_code == 503
