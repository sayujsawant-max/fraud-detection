"""Baseline local training pipeline for FraudShield (Phase 1).

Trains Logistic Regression, Random Forest, and (if available) XGBoost on the
synthetic dataset produced by :mod:`backend.scripts.generate_data`, evaluates
each model with :mod:`src.training.evaluate`, and writes a JSON summary to
``backend/reports/baseline_metrics.json``.

MLflow tracking is intentionally NOT used here — the Phase 2 entrypoint at
:mod:`backend.scripts.train_with_mlflow` adds experiment tracking + registry.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from sklearn.pipeline import Pipeline

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.logging import configure_logging  # noqa: E402
from src.features.constants import TARGET_COLUMN  # noqa: E402
from src.features.pipeline import select_features  # noqa: E402
from src.training.builders import (  # noqa: E402
    build_logistic_regression,
    build_random_forest,
    build_xgboost,
    load_split,
)
from src.training.evaluate import EvaluationResult, evaluate_predictions  # noqa: E402

TRAIN_PATH = _BACKEND_ROOT / "data" / "raw" / "train.parquet"
TEST_PATH = _BACKEND_ROOT / "data" / "raw" / "test.parquet"
REPORTS_DIR = _BACKEND_ROOT / "reports"
METRICS_PATH = REPORTS_DIR / "baseline_metrics.json"


def _train_and_evaluate(
    name: str,
    pipeline: Pipeline,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_test: pd.DataFrame,
    y_test: pd.Series,
) -> tuple[EvaluationResult, float]:
    logger.info("training model: {}", name)
    start = time.perf_counter()
    pipeline.fit(x_train, y_train)
    train_seconds = time.perf_counter() - start
    logger.info("trained {} in {:.2f}s", name, train_seconds)

    y_score = pipeline.predict_proba(x_test)[:, 1]
    result = evaluate_predictions(y_test.to_numpy(), y_score)
    logger.info(
        "{} | roc_auc={:.4f} pr_auc={:.4f} f1={:.4f} threshold={:.4f}",
        name,
        result["roc_auc"],
        result["pr_auc"],
        result["f1"],
        result["threshold"],
    )
    return result, train_seconds


def main() -> int:
    """Train and evaluate baseline models, persisting metrics to JSON."""
    configure_logging()

    logger.info("loading train split: {}", TRAIN_PATH)
    train_df = load_split(TRAIN_PATH)
    logger.info("loading test split:  {}", TEST_PATH)
    test_df = load_split(TEST_PATH)

    x_train = select_features(train_df)
    y_train = train_df[TARGET_COLUMN]
    x_test = select_features(test_df)
    y_test = test_df[TARGET_COLUMN]

    n_pos = int(y_train.sum())
    n_neg = int(len(y_train) - n_pos)
    scale_pos_weight = (n_neg / n_pos) if n_pos else 1.0
    logger.info(
        "train rows={} | positives={} | negatives={} | scale_pos_weight={:.2f}",
        len(y_train),
        n_pos,
        n_neg,
        scale_pos_weight,
    )

    candidates = [build_logistic_regression(), build_random_forest()]
    xgb = build_xgboost(scale_pos_weight)
    if xgb is not None:
        candidates.append(xgb)

    results: dict[str, dict[str, Any]] = {}
    for built in candidates:
        try:
            metrics, seconds = _train_and_evaluate(
                built.name, built.pipeline, x_train, y_train, x_test, y_test
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("model {} failed to train: {}", built.name, exc)
            continue
        results[built.name] = {**metrics, "train_seconds": round(seconds, 4)}

    if not results:
        logger.error("no baseline models trained successfully")
        return 1

    best_name = max(results, key=lambda n: results[n]["pr_auc"])
    payload: dict[str, Any] = {
        "best_model": best_name,
        "train_rows": int(len(y_train)),
        "test_rows": int(len(y_test)),
        "train_fraud_rate": float(y_train.mean()),
        "test_fraud_rate": float(y_test.mean()),
        "models": results,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("wrote baseline metrics -> {}", METRICS_PATH)
    logger.info("best baseline model by PR-AUC: {}", best_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
