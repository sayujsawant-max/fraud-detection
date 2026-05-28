"""Integration tests for the ``/v1/admin/*`` endpoints.

The retraining + monitoring flow callables are monkey-patched at the
admin-router import boundary so no Prefect server, MLflow tracking
server, or PostgreSQL is required.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import src.api.routers.admin as admin_router_module
from src.core.config import get_settings


@pytest.fixture(autouse=True)
def _admin_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Force a known API key for the duration of the test."""
    monkeypatch.setenv("API_KEY", "test-admin-key")
    get_settings.cache_clear()
    yield "test-admin-key"
    get_settings.cache_clear()


@pytest.fixture()
def _patch_background_flows(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace the background flow runners with awaitable no-ops."""
    record: dict = {"retrain_calls": [], "monitoring_calls": 0}

    async def _fake_retrain(trigger_reason: str) -> None:
        record["retrain_calls"].append(trigger_reason)

    async def _fake_monitoring() -> None:
        record["monitoring_calls"] += 1

    monkeypatch.setattr(
        admin_router_module, "_run_retraining_in_background", _fake_retrain
    )
    monkeypatch.setattr(
        admin_router_module, "_run_monitoring_in_background", _fake_monitoring
    )
    return record


# ---------------------------------------------------------------------------
# /v1/admin/retrain
# ---------------------------------------------------------------------------


def test_retrain_with_valid_key_returns_200(
    client: TestClient,
    _admin_api_key: str,
    _patch_background_flows: dict,
) -> None:
    """Valid API key + body → 200 triggered."""
    response = client.post(
        "/v1/admin/retrain",
        headers={"X-API-Key": _admin_api_key},
        json={"trigger_reason": "manual"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "triggered"
    assert payload["trigger_reason"] == "manual"
    # Background task should have been queued (TestClient runs them on exit).
    assert _patch_background_flows["retrain_calls"] == ["manual"]


def test_retrain_with_empty_body_defaults_to_manual(
    client: TestClient,
    _admin_api_key: str,
    _patch_background_flows: dict,
) -> None:
    """Missing body → trigger_reason defaults to 'manual'."""
    response = client.post("/v1/admin/retrain", headers={"X-API-Key": _admin_api_key})
    assert response.status_code == 200
    assert response.json()["trigger_reason"] == "manual"


def test_retrain_with_invalid_key_returns_403(
    client: TestClient,
    _patch_background_flows: dict,
) -> None:
    """Wrong API key → 403."""
    response = client.post(
        "/v1/admin/retrain",
        headers={"X-API-Key": "wrong-key"},
        json={"trigger_reason": "manual"},
    )
    assert response.status_code == 403
    assert _patch_background_flows["retrain_calls"] == []


def test_retrain_with_missing_key_returns_403(
    client: TestClient,
    _patch_background_flows: dict,
) -> None:
    """No API key → 403."""
    response = client.post("/v1/admin/retrain", json={"trigger_reason": "manual"})
    assert response.status_code == 403


def test_retrain_rejects_invalid_trigger_reason(
    client: TestClient,
    _admin_api_key: str,
    _patch_background_flows: dict,
) -> None:
    """Unknown ``trigger_reason`` value → 422 from Pydantic."""
    response = client.post(
        "/v1/admin/retrain",
        headers={"X-API-Key": _admin_api_key},
        json={"trigger_reason": "bogus"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /v1/admin/reload-model
# ---------------------------------------------------------------------------


def test_reload_model_with_valid_key_returns_200(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    _admin_api_key: str,
) -> None:
    """Mocked loader → 200 with model info."""
    from src.features.constants import FEATURE_COLUMNS
    from src.models.loader import (
        DUMMY_MODEL_NAME,
        DUMMY_MODEL_STAGE,
        DUMMY_MODEL_VERSION,
        DummyFraudModel,
        LoadedModel,
    )

    def _fake_load(settings=None):
        return LoadedModel(
            model=DummyFraudModel(),
            model_name=DUMMY_MODEL_NAME,
            model_version=DUMMY_MODEL_VERSION,
            model_stage=DUMMY_MODEL_STAGE,
            threshold=0.5,
            loaded_at=datetime.now(tz=UTC),
            feature_count=len(FEATURE_COLUMNS),
            is_dummy=True,
        )

    monkeypatch.setattr(admin_router_module, "load_model_safely", _fake_load)
    response = client.post(
        "/v1/admin/reload-model", headers={"X-API-Key": _admin_api_key}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "reloaded"
    assert payload["model_name"] == DUMMY_MODEL_NAME
    assert payload["is_dummy"] is True


def test_reload_model_returns_503_when_load_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    _admin_api_key: str,
) -> None:
    """Loader returns None → 503."""
    monkeypatch.setattr(
        admin_router_module, "load_model_safely", lambda settings=None: None
    )
    response = client.post(
        "/v1/admin/reload-model", headers={"X-API-Key": _admin_api_key}
    )
    assert response.status_code == 503


def test_reload_model_invalid_key_returns_403(client: TestClient) -> None:
    """Wrong key → 403, loader not called."""
    response = client.post("/v1/admin/reload-model", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# /v1/admin/monitoring/run
# ---------------------------------------------------------------------------


def test_monitoring_run_with_valid_key_returns_200(
    client: TestClient,
    _admin_api_key: str,
    _patch_background_flows: dict,
) -> None:
    """Valid API key → 200 triggered."""
    response = client.post(
        "/v1/admin/monitoring/run", headers={"X-API-Key": _admin_api_key}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "triggered"
    assert _patch_background_flows["monitoring_calls"] == 1


def test_monitoring_run_invalid_key_returns_403(
    client: TestClient,
    _patch_background_flows: dict,
) -> None:
    """Wrong key → 403, flow not called."""
    response = client.post(
        "/v1/admin/monitoring/run", headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 403
    assert _patch_background_flows["monitoring_calls"] == 0
