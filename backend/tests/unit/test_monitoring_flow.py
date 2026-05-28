"""Unit tests for :func:`monitoring_flow`.

The tests stub out Prefect-managed tasks via monkeypatch so they never
touch a real Prefect server, MLflow, or PostgreSQL. The DB session in
the flow is replaced by the in-memory SQLite engine from ``conftest.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import src.workflows.monitoring_flow as monitoring_flow_module
from src.monitoring import DriftDetectionResult


def _settings_with(
    threshold: float = 0.30, min_samples: int = 200, lookback: int = 1000
):
    """Return a ``Settings``-shaped object for the flow under test."""
    return SimpleNamespace(
        DRIFT_THRESHOLD=threshold,
        DRIFT_MIN_SAMPLES=min_samples,
        DRIFT_LOOKBACK_LIMIT=lookback,
        REFERENCE_DATA_PATH="backend/data/reference/reference.parquet",
    )


def _patch_tasks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rows,
    drift_detected: bool,
    drift_score: float,
    persist_should_raise: bool = False,
) -> dict:
    """Install monkey-patched stand-ins for every flow task.

    Returns a dict that records whether each side-effect ran, so the
    test can assert on the call graph.
    """
    record: dict = {
        "retraining_triggered": False,
        "persisted": False,
    }

    async def _fake_fetch(_settings=None):
        return rows

    def _fake_reference(_settings=None):
        import pandas as pd

        return pd.DataFrame({"amount": [1.0, 2.0]})

    def _fake_run_drift(_ref, _cur, *, settings=None, save_report=True):
        return DriftDetectionResult(
            status="complete",
            drift_detected=drift_detected,
            drift_score=drift_score,
            num_drifted_features=4 if drift_detected else 0,
            total_features=28,
            num_samples=len(rows),
            report_id="drift_test_id" if save_report else None,
            generated_at=datetime.now(tz=UTC),
        )

    def _fake_evaluate(result, _settings=None):
        return bool(result.drift_detected)

    async def _fake_trigger(detected, trigger_reason="drift"):
        if not detected:
            return None
        record["retraining_triggered"] = True
        return {
            "status": "promoted",
            "retraining_run_id": "fake-run-id",
        }

    async def _fake_persist(result, _settings=None, *, triggered_retrain=False):
        if persist_should_raise:
            raise RuntimeError("simulated persist failure")
        record["persisted"] = True
        record["persist_triggered_retrain"] = triggered_retrain

    monkeypatch.setattr(
        monitoring_flow_module, "fetch_recent_predictions_task", _fake_fetch
    )
    monkeypatch.setattr(
        monitoring_flow_module, "load_reference_dataset_task", _fake_reference
    )
    monkeypatch.setattr(
        monitoring_flow_module, "run_drift_detection_task", _fake_run_drift
    )
    monkeypatch.setattr(monitoring_flow_module, "evaluate_drift_task", _fake_evaluate)
    monkeypatch.setattr(
        monitoring_flow_module, "trigger_retraining_task", _fake_trigger
    )
    monkeypatch.setattr(
        monitoring_flow_module, "persist_drift_report_task", _fake_persist
    )

    def _fake_build_current(*_args, **_kwargs):
        import pandas as pd

        return pd.DataFrame({"amount": [1.0]})

    monkeypatch.setattr(
        monitoring_flow_module, "build_current_dataset", _fake_build_current
    )
    return record


def _make_row(ts: datetime):
    """Cheap PredictionLog stand-in: only ``.timestamp`` is read by the flow."""
    return SimpleNamespace(timestamp=ts)


@pytest.mark.asyncio
async def test_monitoring_flow_skipped_when_insufficient_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fewer rows than ``DRIFT_MIN_SAMPLES`` → status='skipped'."""
    settings = _settings_with(min_samples=100)
    _patch_tasks(
        monkeypatch,
        rows=[_make_row(datetime.now(tz=UTC))] * 10,
        drift_detected=False,
        drift_score=0.05,
    )

    result = await monitoring_flow_module.monitoring_flow(settings)
    assert result["status"] == "skipped"
    assert result["reason"] == "insufficient_prediction_logs"
    assert result["num_samples"] == 10
    assert result["drift_detected"] is False
    assert result["retraining_triggered"] is False


@pytest.mark.asyncio
async def test_monitoring_flow_no_retrain_when_no_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``drift_detected=False`` → ``retraining_triggered=False``."""
    settings = _settings_with(min_samples=5)
    rows = [_make_row(datetime.now(tz=UTC))] * 10
    record = _patch_tasks(
        monkeypatch, rows=rows, drift_detected=False, drift_score=0.10
    )

    result = await monitoring_flow_module.monitoring_flow(settings)
    assert result["status"] == "complete"
    assert result["drift_detected"] is False
    assert result["retraining_triggered"] is False
    assert record["retraining_triggered"] is False
    assert record["persisted"] is True


@pytest.mark.asyncio
async def test_monitoring_flow_triggers_retrain_on_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``drift_detected=True`` → retraining task is invoked."""
    settings = _settings_with(min_samples=5)
    rows = [_make_row(datetime.now(tz=UTC))] * 10
    record = _patch_tasks(monkeypatch, rows=rows, drift_detected=True, drift_score=0.55)

    result = await monitoring_flow_module.monitoring_flow(settings)
    assert result["status"] == "complete"
    assert result["drift_detected"] is True
    assert result["retraining_triggered"] is True
    assert result.get("retraining_run_id") == "fake-run-id"
    assert record["retraining_triggered"] is True
    assert record["persist_triggered_retrain"] is True


@pytest.mark.asyncio
async def test_monitoring_flow_swallows_persist_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persistence failure does not crash the flow — best-effort log only."""
    settings = _settings_with(min_samples=5)
    rows = [_make_row(datetime.now(tz=UTC))] * 10
    _patch_tasks(
        monkeypatch,
        rows=rows,
        drift_detected=False,
        drift_score=0.10,
        persist_should_raise=True,
    )

    result = await monitoring_flow_module.monitoring_flow(settings)
    assert result["status"] == "complete"
    assert result["drift_detected"] is False
