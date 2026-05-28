"""Unit tests for the Evidently drift wrapper.

The Evidently library itself is patched away in most tests so we exercise
*our* logic — threshold evaluation, JSON parsing, defensive guards —
without paying the (substantial) Evidently import + run time.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.core.config import get_settings
from src.core.exceptions import DriftError
from src.monitoring.drift import (
    DriftDetectionResult,
    DriftDetector,
    evaluate_drift_threshold,
    extract_drift_metrics,
    run_drift_detection,
)

# ---------------------------------------------------------------------------
# evaluate_drift_threshold
# ---------------------------------------------------------------------------


def test_evaluate_drift_threshold_returns_true_above() -> None:
    """Drift score strictly above the threshold flags drift."""
    assert evaluate_drift_threshold(0.45, 0.30) is True


def test_evaluate_drift_threshold_returns_false_below() -> None:
    """Drift score below the threshold does NOT flag drift."""
    assert evaluate_drift_threshold(0.15, 0.30) is False


def test_evaluate_drift_threshold_returns_false_on_equality() -> None:
    """Equality intentionally returns False — blueprint uses strict ``>``."""
    assert evaluate_drift_threshold(0.30, 0.30) is False


def test_evaluate_drift_threshold_returns_false_on_none() -> None:
    """``None`` (no measurement) short-circuits to False."""
    assert evaluate_drift_threshold(None, 0.30) is False


# ---------------------------------------------------------------------------
# extract_drift_metrics
# ---------------------------------------------------------------------------


def _evidently_dict(num_drifted: int, total: int, share: float) -> dict:
    """Build a minimal Evidently-shaped ``dict()`` payload for tests."""
    metrics = [
        {
            "id": "drifted-count",
            "metric_name": f"DriftedColumnsCount(drift_share={share})",
            "config": {"type": "evidently:metric_v2:DriftedColumnsCount"},
            "value": {"count": num_drifted, "share": share},
        }
    ]
    for i in range(total):
        metrics.append(
            {
                "id": f"value-drift-{i}",
                "metric_name": f"ValueDrift(column=col_{i},method=K-S,threshold=0.05)",
                "config": {
                    "type": "evidently:metric_v2:ValueDrift",
                    "column": f"col_{i}",
                },
                "value": 0.01 if i < num_drifted else 0.5,
            }
        )
    return {"metrics": metrics, "tests": []}


def test_extract_drift_metrics_happy_path() -> None:
    """Parse a well-formed Evidently dict — pulls share + count + per-col."""
    payload = _evidently_dict(num_drifted=3, total=10, share=0.30)
    out = extract_drift_metrics(payload)
    assert out["drift_score"] == pytest.approx(0.30)
    assert out["num_drifted_features"] == 3
    assert out["total_features"] == 10
    assert "col_0" in out["per_column_drift"]


def test_extract_drift_metrics_handles_none() -> None:
    """``None`` payload returns the all-None default shape, no crash."""
    out = extract_drift_metrics(None)
    assert out["drift_score"] is None
    assert out["num_drifted_features"] is None
    assert out["total_features"] is None
    assert out["per_column_drift"] == {}


def test_extract_drift_metrics_handles_missing_metrics_key() -> None:
    """A dict without ``metrics`` returns defaults (defensive parse)."""
    out = extract_drift_metrics({"tests": []})
    assert out["drift_score"] is None


def test_extract_drift_metrics_handles_value_as_scalar() -> None:
    """Older Evidently versions returned a plain float instead of a dict."""
    payload = {
        "metrics": [
            {
                "metric_name": "DriftedColumnsCount(drift_share=0.5)",
                "value": 0.42,
            }
        ]
    }
    out = extract_drift_metrics(payload)
    assert out["drift_score"] == pytest.approx(0.42)


def test_extract_drift_metrics_handles_garbage_metric_entries() -> None:
    """Non-dict entries in ``metrics`` are skipped, not exploded."""
    payload = {
        "metrics": [
            "garbage",
            123,
            {
                "metric_name": "DriftedColumnsCount",
                "value": {"share": 0.10, "count": 1},
            },
        ]
    }
    out = extract_drift_metrics(payload)
    assert out["drift_score"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# DriftDetector.run / run_drift_detection — Evidently mocked away
# ---------------------------------------------------------------------------


def _fake_snapshot(
    num_drifted: int = 4, total: int = 10, share: float = 0.4
) -> MagicMock:
    """Mock object that quacks like an Evidently Snapshot."""
    snap = MagicMock()
    snap.dict.return_value = _evidently_dict(num_drifted, total, share)
    return snap


def test_drift_detector_run_raises_on_empty_inputs() -> None:
    """Empty reference or current frame is a programmer error → DriftError."""
    detector = DriftDetector(get_settings())
    with pytest.raises(DriftError):
        detector.run(pd.DataFrame(), pd.DataFrame({"a": [1]}))


def test_run_drift_detection_uses_threshold(monkeypatch) -> None:
    """``run_drift_detection`` evaluates drift against settings.DRIFT_THRESHOLD."""
    detector = MagicMock(spec=DriftDetector)
    detector.run.return_value = _fake_snapshot(share=0.40)

    settings = get_settings()
    settings_high = settings.model_copy(update={"DRIFT_THRESHOLD": 0.30})
    result, _ = run_drift_detection(
        pd.DataFrame({"a": [1]}),
        pd.DataFrame({"a": [2]}),
        settings=settings_high,
        detector=detector,
    )
    assert result.drift_detected is True
    assert result.drift_score == pytest.approx(0.40)
    assert result.num_drifted_features == 4
    assert result.total_features == 10


def test_run_drift_detection_below_threshold(monkeypatch) -> None:
    """Drift score below threshold leaves drift_detected=False."""
    detector = MagicMock(spec=DriftDetector)
    detector.run.return_value = _fake_snapshot(share=0.10)

    settings = get_settings().model_copy(update={"DRIFT_THRESHOLD": 0.30})
    result, _ = run_drift_detection(
        pd.DataFrame({"a": [1]}),
        pd.DataFrame({"a": [2]}),
        settings=settings,
        detector=detector,
    )
    assert result.drift_detected is False


# ---------------------------------------------------------------------------
# DriftDetectionResult helpers
# ---------------------------------------------------------------------------


def test_drift_detection_result_skipped_shape() -> None:
    """The "skipped" result shape is what the API returns on insufficient data."""
    result = DriftDetectionResult(
        status="skipped",
        num_samples=42,
        reason="insufficient_prediction_logs",
    )
    payload = result.to_dict()
    assert payload["status"] == "skipped"
    assert payload["drift_detected"] is False
    assert payload["reason"] == "insufficient_prediction_logs"
    assert payload["num_samples"] == 42
