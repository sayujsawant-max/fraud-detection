"""Unit tests for :func:`retraining_flow` and its compare helper.

These tests stub MLflow, the registry, training, and DB writes via
``monkeypatch`` so the suite runs with neither MLflow nor a Prefect
server. The DB stubs replace the session-providing tasks rather than
hitting SQLite — which keeps the test surface minimal.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.workflows.retraining_flow as retraining_flow_module
from src.workflows.retraining_flow import (
    compare_challenger_to_champion_task,
)


def _settings(min_delta: float = 0.01):
    """Return a Settings-shaped object the flow can use."""
    return SimpleNamespace(
        MODEL_PROMOTION_MIN_DELTA=min_delta,
        MLFLOW_TRACKING_URI="http://mlflow:5000",
        API_BASE_URL="http://api:8000",
        API_KEY="test-key",
    )


# ---------------------------------------------------------------------------
# Comparison task — pure function, no patching needed
# ---------------------------------------------------------------------------


def test_compare_promotes_when_delta_exceeds_threshold() -> None:
    """Challenger improves PR-AUC by >= min_delta → should_promote True."""
    settings = _settings(min_delta=0.01)
    result = compare_challenger_to_champion_task(
        {"pr_auc": 0.88},
        {"pr_auc": 0.86, "version": "1", "run_id": "abc"},
        settings=settings,
    )
    assert result["should_promote"] is True
    assert result["delta"] == pytest.approx(0.02)
    assert result["challenger_pr_auc"] == pytest.approx(0.88)
    assert result["champion_pr_auc"] == pytest.approx(0.86)


def test_compare_rejects_when_delta_too_small() -> None:
    """Challenger improvement below threshold → should_promote False."""
    settings = _settings(min_delta=0.05)
    result = compare_challenger_to_champion_task(
        {"pr_auc": 0.872},
        {"pr_auc": 0.870, "version": "1", "run_id": "abc"},
        settings=settings,
    )
    assert result["should_promote"] is False
    assert result["delta"] == pytest.approx(0.002)


def test_compare_promotes_when_no_champion_exists() -> None:
    """No champion → first model wins automatically."""
    settings = _settings(min_delta=0.01)
    result = compare_challenger_to_champion_task(
        {"pr_auc": 0.71},
        None,
        settings=settings,
    )
    assert result["should_promote"] is True
    assert result["champion_pr_auc"] is None
    assert "No champion" in result["reason"]


def test_compare_rejects_when_champion_has_no_pr_auc() -> None:
    """Champion exists but missing PR-AUC → reject (cannot compare safely)."""
    settings = _settings(min_delta=0.01)
    result = compare_challenger_to_champion_task(
        {"pr_auc": 0.95},
        {"pr_auc": None, "version": "1", "run_id": "abc"},
        settings=settings,
    )
    assert result["should_promote"] is False


# ---------------------------------------------------------------------------
# Flow-level tests with stubs
# ---------------------------------------------------------------------------


def _patch_flow_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    train_should_raise: bool = False,
    challenger_pr_auc: float = 0.88,
    champion_pr_auc: float | None = 0.85,
    reload_status: str = "reloaded",
) -> dict:
    """Replace every flow task with a synchronous fake.

    Returns a dict capturing the final ``log_retraining_end`` call args so
    the test can assert on what was persisted.
    """
    captured: dict = {"end_call": None, "start_called": False, "promote_called": False}

    async def _fake_start(trigger_reason):
        captured["start_called"] = True
        from uuid import uuid4

        return uuid4()

    def _fake_prepare_data(_settings=None):
        return {"train_path": "train.parquet", "test_path": "test.parquet"}

    def _fake_train(_data_paths, *, settings=None, register_model=True):
        if train_should_raise:
            raise RuntimeError("simulated training failure")
        return {
            "challenger_run_id": "run-challenger",
            "challenger_model_uri": "models:/fraud-detector/2",
            "challenger_model_version": "2",
            "challenger_metrics": {"pr_auc": challenger_pr_auc},
            "model_type": "xgboost",
        }

    def _fake_get_champion(_settings=None):
        if champion_pr_auc is None:
            return None
        return {"version": "1", "run_id": "run-champion", "pr_auc": champion_pr_auc}

    def _fake_promote(_challenger, _comparison, *, settings=None):
        captured["promote_called"] = True
        return {"version": "2", "archived_versions": ["1"], "promoted_at": "now"}

    def _fake_reload(_settings=None):
        return reload_status

    async def _fake_end(run_id, **kwargs):
        captured["end_call"] = {"run_id": run_id, **kwargs}

    monkeypatch.setattr(
        retraining_flow_module, "log_retraining_start_task", _fake_start
    )
    monkeypatch.setattr(
        retraining_flow_module, "prepare_training_data_task", _fake_prepare_data
    )
    monkeypatch.setattr(
        retraining_flow_module, "train_challenger_model_task", _fake_train
    )
    monkeypatch.setattr(
        retraining_flow_module, "get_champion_metrics_task", _fake_get_champion
    )
    monkeypatch.setattr(
        retraining_flow_module, "promote_challenger_task", _fake_promote
    )
    monkeypatch.setattr(retraining_flow_module, "reload_api_model_task", _fake_reload)
    monkeypatch.setattr(retraining_flow_module, "log_retraining_end_task", _fake_end)
    return captured


@pytest.mark.asyncio
async def test_flow_promotes_challenger_when_delta_clears_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Challenger 0.88 vs champion 0.85 with delta=0.01 → promoted."""
    captured = _patch_flow_dependencies(
        monkeypatch, challenger_pr_auc=0.88, champion_pr_auc=0.85
    )
    result = await retraining_flow_module.retraining_flow(
        trigger_reason="manual", settings=_settings(min_delta=0.01)
    )
    assert result["status"] == "promoted"
    assert result["promoted"] is True
    assert result["challenger_pr_auc"] == pytest.approx(0.88)
    assert result["champion_pr_auc"] == pytest.approx(0.85)
    assert captured["promote_called"] is True
    assert captured["end_call"]["status"] == "promoted"


@pytest.mark.asyncio
async def test_flow_rejects_challenger_when_delta_too_small(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Challenger 0.860 vs champion 0.859 with delta=0.01 → rejected."""
    captured = _patch_flow_dependencies(
        monkeypatch, challenger_pr_auc=0.860, champion_pr_auc=0.859
    )
    result = await retraining_flow_module.retraining_flow(
        trigger_reason="manual", settings=_settings(min_delta=0.01)
    )
    assert result["status"] == "rejected"
    assert result["promoted"] is False
    assert captured["promote_called"] is False
    assert captured["end_call"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_flow_promotes_when_no_champion_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No champion → challenger auto-promoted regardless of metric."""
    captured = _patch_flow_dependencies(
        monkeypatch, challenger_pr_auc=0.65, champion_pr_auc=None
    )
    result = await retraining_flow_module.retraining_flow(
        trigger_reason="manual", settings=_settings(min_delta=0.05)
    )
    assert result["status"] == "promoted"
    assert result["promoted"] is True
    assert captured["promote_called"] is True


@pytest.mark.asyncio
async def test_flow_marks_failed_when_training_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any unhandled exception → status='failed' + DB row updated."""
    captured = _patch_flow_dependencies(monkeypatch, train_should_raise=True)
    result = await retraining_flow_module.retraining_flow(
        trigger_reason="manual", settings=_settings(min_delta=0.01)
    )
    assert result["status"] == "failed"
    assert result["promoted"] is False
    assert "retraining_run_id" in result
    assert captured["end_call"]["status"] == "failed"
    assert "simulated training failure" in captured["end_call"]["error_message"]


@pytest.mark.asyncio
async def test_flow_rejects_invalid_trigger_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid trigger surfaces via the flow's outer error guard."""
    _patch_flow_dependencies(monkeypatch)

    from src.core.exceptions import RetrainingError

    with pytest.raises(RetrainingError):
        await retraining_flow_module.retraining_flow(
            trigger_reason="bogus", settings=_settings(min_delta=0.01)
        )
