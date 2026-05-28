"""CLI entrypoint that trains all baselines AND tracks them in MLflow.

Each model becomes its own MLflow run with full params/metrics/artifacts,
the sklearn pipeline is logged as a model artifact, and the best PR-AUC
run is registered as ``fraud-detector`` and aliased ``champion``. Use
``promote_model.py`` to flip the ``production`` alias afterwards.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd
from loguru import logger
from sklearn.pipeline import Pipeline

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.core.logging import configure_logging  # noqa: E402
from src.features.constants import TARGET_COLUMN  # noqa: E402
from src.features.pipeline import select_features  # noqa: E402
from src.models.registry import (  # noqa: E402
    CHAMPION_ALIAS,
    MlflowRegistryClient,
)
from src.training.builders import (  # noqa: E402
    RANDOM_STATE,
    BuiltModel,
    build_logistic_regression,
    build_random_forest,
    build_xgboost,
    load_split,
)
from src.training.evaluate import EvaluationResult, evaluate_predictions  # noqa: E402
from src.training.experiment import (  # noqa: E402
    EXPERIMENT_NAME,
    REGISTERED_MODEL_NAME,
    DatasetMeta,
    build_metrics_payload,
    build_params_payload,
    build_run_tags,
    configure_mlflow,
    log_run_artifacts,
    log_sklearn_pipeline,
    resolve_tracking_uri,
    setup_experiment,
    start_run,
)

TRAIN_PATH = _BACKEND_ROOT / "data" / "raw" / "train.parquet"
TEST_PATH = _BACKEND_ROOT / "data" / "raw" / "test.parquet"
REPORTS_DIR = _BACKEND_ROOT / "reports"
SUMMARY_PATH = REPORTS_DIR / "mlflow_training_summary.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train baselines with MLflow tracking + registry"
    )
    parser.add_argument(
        "--tracking-uri",
        default=None,
        help="Override MLflow tracking URI (else $MLFLOW_TRACKING_URI or http://localhost:5000)",
    )
    parser.add_argument(
        "--experiment-name",
        default=EXPERIMENT_NAME,
        help=f"MLflow experiment name (default: {EXPERIMENT_NAME})",
    )
    parser.add_argument(
        "--model-name",
        default=REGISTERED_MODEL_NAME,
        help=f"Registered model name (default: {REGISTERED_MODEL_NAME})",
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Skip model registration (useful for smoke tests)",
    )
    return parser.parse_args()


def _train_one(
    built: BuiltModel,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    dataset_meta: DatasetMeta,
) -> dict[str, Any]:
    """Train + evaluate ``built`` inside a new MLflow run and return a summary."""
    pipeline: Pipeline = built.pipeline
    logger.info("training {} inside MLflow run", built.name)
    start = time.perf_counter()
    pipeline.fit(x_train, y_train)
    train_seconds = time.perf_counter() - start

    inference_start = time.perf_counter()
    y_score = pipeline.predict_proba(x_test)[:, 1]
    inference_seconds = time.perf_counter() - inference_start
    avg_latency_ms = (inference_seconds / max(len(x_test), 1)) * 1_000.0

    eval_result: EvaluationResult = evaluate_predictions(y_test.to_numpy(), y_score)

    tags = build_run_tags(built.name)
    with start_run(run_name=built.name, tags=tags) as run:
        params = build_params_payload(built.params, dataset_meta)
        metrics = build_metrics_payload(
            eval_result,
            training_duration_seconds=train_seconds,
            inference_latency_ms_avg=avg_latency_ms,
        )
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)

        log_run_artifacts(
            model_name=built.name,
            eval_result=eval_result,
            y_true=y_test.to_numpy(),
            y_score=y_score,
            extra_metrics={
                "train_seconds": round(train_seconds, 4),
                "inference_latency_ms_avg": round(avg_latency_ms, 4),
            },
        )
        model_uri = log_sklearn_pipeline(pipeline, x_train)

        run_id = run.info.run_id

    logger.info(
        "{} | pr_auc={:.4f} roc_auc={:.4f} f1={:.4f} run_id={}",
        built.name,
        eval_result["pr_auc"],
        eval_result["roc_auc"],
        eval_result["f1"],
        run_id,
    )

    return {
        "model_type": built.name,
        "run_id": run_id,
        "model_uri": model_uri,
        "pr_auc": float(eval_result["pr_auc"]),
        "roc_auc": float(eval_result["roc_auc"]),
        "f1_score": float(eval_result["f1"]),
        "precision": float(eval_result["precision"]),
        "recall": float(eval_result["recall"]),
        "optimal_threshold": float(eval_result["threshold"]),
        "training_duration_seconds": round(train_seconds, 4),
        "inference_latency_ms_avg": round(avg_latency_ms, 4),
        "metrics": metrics,
        "params": params,
    }


def select_champion(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the run with the highest PR-AUC."""
    if not results:
        raise ValueError("cannot select champion from empty results")
    return max(results, key=lambda r: r["pr_auc"])


def main() -> int:
    """Run all baselines through MLflow + register the champion."""
    configure_logging()
    args = _parse_args()

    tracking_uri = resolve_tracking_uri(args.tracking_uri)
    configure_mlflow(tracking_uri)
    setup_experiment(args.experiment_name)

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

    dataset_meta: DatasetMeta = {
        "train_size": int(len(y_train)),
        "test_size": int(len(y_test)),
        "fraud_rate_train": float(y_train.mean()),
        "fraud_rate_test": float(y_test.mean()),
        "random_state": RANDOM_STATE,
    }
    logger.info(
        "dataset meta: train={} test={} fraud_train={:.4f} fraud_test={:.4f}",
        dataset_meta["train_size"],
        dataset_meta["test_size"],
        dataset_meta["fraud_rate_train"],
        dataset_meta["fraud_rate_test"],
    )

    candidates: list[BuiltModel] = [build_logistic_regression(), build_random_forest()]
    xgb = build_xgboost(scale_pos_weight)
    if xgb is not None:
        candidates.append(xgb)

    results: list[dict[str, Any]] = []
    for built in candidates:
        try:
            result = _train_one(built, x_train, y_train, x_test, y_test, dataset_meta)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("model {} failed inside MLflow run: {}", built.name, exc)
            continue
        results.append(result)

    if not results:
        logger.error("no models trained successfully — nothing to register")
        return 1

    champion = select_champion(results)
    logger.info(
        "champion model: {} pr_auc={:.4f} run_id={}",
        champion["model_type"],
        champion["pr_auc"],
        champion["run_id"],
    )

    registered_version: str | None = None
    if not args.no_register:
        registry = MlflowRegistryClient(tracking_uri=tracking_uri)
        version = registry.register_model(champion["model_uri"], args.model_name)
        registered_version = str(version.version)
        registry.client.set_registered_model_alias(
            name=args.model_name,
            alias=CHAMPION_ALIAS,
            version=registered_version,
        )
        logger.info(
            "registered {!r} version {} (alias {!r})",
            args.model_name,
            registered_version,
            CHAMPION_ALIAS,
        )
        logger.info(
            "to promote run: python backend/scripts/promote_model.py "
            "--version {} --stage Production",
            registered_version,
        )

    summary: dict[str, Any] = {
        "experiment_name": args.experiment_name,
        "tracking_uri": tracking_uri,
        "best_model_type": champion["model_type"],
        "best_run_id": champion["run_id"],
        "best_model_uri": champion["model_uri"],
        "best_pr_auc": champion["pr_auc"],
        "registered_model_name": args.model_name if not args.no_register else None,
        "registered_model_version": registered_version,
        "dataset": dataset_meta,
        "all_model_results": results,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("wrote MLflow training summary -> {}", SUMMARY_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
