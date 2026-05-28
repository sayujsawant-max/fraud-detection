"""Fraud-appropriate evaluation metrics.

Provides a single :func:`evaluate_predictions` entry point that returns a
dictionary suitable for JSON serialization, including ROC-AUC, PR-AUC,
precision/recall/F1 at the F1-optimal threshold, and the corresponding
confusion matrix.
"""

from __future__ import annotations

from typing import TypedDict

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


class ConfusionMatrixDict(TypedDict):
    """Plain dict view of a 2x2 confusion matrix."""

    tn: int
    fp: int
    fn: int
    tp: int


class EvaluationResult(TypedDict):
    """Result returned by :func:`evaluate_predictions`."""

    roc_auc: float
    pr_auc: float
    precision: float
    recall: float
    f1: float
    threshold: float
    confusion_matrix: ConfusionMatrixDict
    n_samples: int
    n_positive: int


def _optimal_f1_threshold(
    y_true: np.ndarray, y_score: np.ndarray
) -> tuple[float, float]:
    """Return ``(threshold, f1)`` that maximises F1 on the PR curve."""
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    denom = precision + recall
    f1_curve = np.where(
        denom > 0, 2 * precision * recall / np.where(denom == 0, 1, denom), 0.0
    )
    # precision_recall_curve returns len(thresholds) == len(precision) - 1;
    # align by dropping the trailing recall=0 point.
    f1_curve = f1_curve[:-1]
    if f1_curve.size == 0:
        return 0.5, 0.0
    best_idx = int(np.argmax(f1_curve))
    return float(thresholds[best_idx]), float(f1_curve[best_idx])


def evaluate_predictions(y_true: np.ndarray, y_score: np.ndarray) -> EvaluationResult:
    """Compute the FraudShield evaluation bundle.

    Args:
        y_true: Ground-truth binary labels (0/1).
        y_score: Predicted positive-class probabilities in [0, 1].

    Returns:
        ``EvaluationResult`` dict containing ROC-AUC, PR-AUC, precision,
        recall, F1, optimal threshold, and the confusion matrix.
    """
    y_true_arr = np.asarray(y_true).astype(int)
    y_score_arr = np.asarray(y_score, dtype=float)

    if y_true_arr.shape != y_score_arr.shape:
        raise ValueError(
            f"y_true and y_score shape mismatch: {y_true_arr.shape} vs {y_score_arr.shape}"
        )
    if y_true_arr.size == 0:
        raise ValueError("empty input: y_true is length 0")

    n_positive = int(y_true_arr.sum())
    if n_positive in (0, y_true_arr.size):
        raise ValueError(
            "evaluation requires both classes; got "
            f"n_positive={n_positive}, n_samples={y_true_arr.size}"
        )

    roc_auc = float(roc_auc_score(y_true_arr, y_score_arr))
    pr_auc = float(average_precision_score(y_true_arr, y_score_arr))
    threshold, f1 = _optimal_f1_threshold(y_true_arr, y_score_arr)
    y_pred = (y_score_arr >= threshold).astype(int)

    precision = float(precision_score(y_true_arr, y_pred, zero_division=0))
    recall = float(recall_score(y_true_arr, y_pred, zero_division=0))
    # Recompute F1 from the chosen threshold to keep all numbers self-consistent.
    f1 = float(f1_score(y_true_arr, y_pred, zero_division=0))

    cm = confusion_matrix(y_true_arr, y_pred, labels=[0, 1])
    cm_dict: ConfusionMatrixDict = {
        "tn": int(cm[0, 0]),
        "fp": int(cm[0, 1]),
        "fn": int(cm[1, 0]),
        "tp": int(cm[1, 1]),
    }

    return {
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "threshold": threshold,
        "confusion_matrix": cm_dict,
        "n_samples": int(y_true_arr.size),
        "n_positive": n_positive,
    }
