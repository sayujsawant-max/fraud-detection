"""Unit tests for the evaluation metrics helper."""

from __future__ import annotations

import numpy as np
import pytest

from src.training.evaluate import evaluate_predictions

EXPECTED_KEYS = {
    "roc_auc",
    "pr_auc",
    "precision",
    "recall",
    "f1",
    "threshold",
    "confusion_matrix",
    "n_samples",
    "n_positive",
}


def test_evaluate_predictions_returns_expected_keys() -> None:
    rng = np.random.default_rng(0)
    y_true = rng.integers(0, 2, size=200)
    y_score = rng.random(size=200)
    if y_true.sum() in (0, y_true.size):
        y_true[0], y_true[1] = 0, 1

    result = evaluate_predictions(y_true, y_score)
    assert set(result.keys()) == EXPECTED_KEYS
    assert set(result["confusion_matrix"].keys()) == {"tn", "fp", "fn", "tp"}


def test_evaluate_predictions_rewards_perfect_classifier() -> None:
    y_true = np.array([0, 0, 0, 1, 1, 1, 1])
    y_score = np.array([0.05, 0.1, 0.2, 0.7, 0.8, 0.9, 0.95])
    result = evaluate_predictions(y_true, y_score)
    assert result["roc_auc"] == pytest.approx(1.0)
    assert result["pr_auc"] == pytest.approx(1.0)
    assert result["f1"] == pytest.approx(1.0)
    assert result["confusion_matrix"] == {"tn": 3, "fp": 0, "fn": 0, "tp": 4}


def test_evaluate_predictions_rejects_single_class() -> None:
    y_true = np.zeros(50, dtype=int)
    y_score = np.linspace(0, 1, num=50)
    with pytest.raises(ValueError):
        evaluate_predictions(y_true, y_score)


def test_evaluate_predictions_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        evaluate_predictions(np.array([0, 1, 1]), np.array([0.1, 0.5]))


def test_evaluate_predictions_metrics_are_bounded() -> None:
    rng = np.random.default_rng(7)
    y_true = (rng.random(500) < 0.3).astype(int)
    y_score = rng.random(500)
    if y_true.sum() in (0, y_true.size):
        y_true[0], y_true[1] = 0, 1
    result = evaluate_predictions(y_true, y_score)
    for key in ("roc_auc", "pr_auc", "precision", "recall", "f1", "threshold"):
        assert 0.0 <= result[key] <= 1.0, f"{key} out of [0, 1]"
    assert result["n_samples"] == 500
