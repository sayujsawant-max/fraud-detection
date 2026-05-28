"""MLflow experiment-tracking helpers for the FraudShield trainer.

Centralises every MLflow side-effect (setup, run start, parameter/metric
logging, artifact dumping, model logging) so the orchestration code in
``scripts/train_with_mlflow.py`` and the unit tests can both use them
without duplication.

Design notes:
    * The sklearn ``Pipeline`` (preprocessor + classifier) is logged as a
      single artifact with ``mlflow.sklearn.log_model`` — this is what
      eliminates training/serving skew once the FastAPI service loads it
      back in Phase 3.
    * Helpers accept an optional ``MlflowClient`` so tests can inject a
      mock; production code uses the module-level ``mlflow`` API.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypedDict

import mlflow
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline

from src.features.constants import FEATURE_COLUMNS
from src.training.evaluate import EvaluationResult

EXPERIMENT_NAME: str = "fraud-detection"
REGISTERED_MODEL_NAME: str = "fraud-detector"
FEATURE_SET_VERSION: str = "v1"
DATASET_VERSION: str = "v1"
MLFLOW_MODEL_ARTIFACT_PATH: str = "model"


class DatasetMeta(TypedDict):
    """Aggregate metadata about the train/test splits used by a run."""

    train_size: int
    test_size: int
    fraud_rate_train: float
    fraud_rate_test: float
    random_state: int


def configure_mlflow(tracking_uri: str) -> None:
    """Point the MLflow client + ``log_*`` helpers at ``tracking_uri``."""
    mlflow.set_tracking_uri(tracking_uri)
    logger.info("MLflow tracking URI set to {}", tracking_uri)


def setup_experiment(name: str = EXPERIMENT_NAME) -> str:
    """Ensure the experiment exists and return its ``experiment_id``."""
    experiment = mlflow.get_experiment_by_name(name)
    if experiment is None:
        experiment_id = mlflow.create_experiment(name)
        logger.info("created MLflow experiment {!r} (id={})", name, experiment_id)
    else:
        experiment_id = experiment.experiment_id
        logger.info(
            "using existing MLflow experiment {!r} (id={})", name, experiment_id
        )
    mlflow.set_experiment(name)
    return experiment_id


def build_params_payload(
    model_params: dict[str, Any], dataset_meta: DatasetMeta
) -> dict[str, Any]:
    """Combine model hyperparams + dataset metadata into a flat params dict."""
    return {
        **model_params,
        "feature_set_version": FEATURE_SET_VERSION,
        "dataset_version": DATASET_VERSION,
        "train_size": dataset_meta["train_size"],
        "test_size": dataset_meta["test_size"],
        "fraud_rate_train": round(dataset_meta["fraud_rate_train"], 6),
        "fraud_rate_test": round(dataset_meta["fraud_rate_test"], 6),
        "random_state": dataset_meta["random_state"],
    }


def build_metrics_payload(
    eval_result: EvaluationResult,
    training_duration_seconds: float,
    inference_latency_ms_avg: float | None = None,
) -> dict[str, float]:
    """Translate an ``EvaluationResult`` into MLflow metric scalars."""
    payload: dict[str, float] = {
        "roc_auc": float(eval_result["roc_auc"]),
        "pr_auc": float(eval_result["pr_auc"]),
        "precision": float(eval_result["precision"]),
        "recall": float(eval_result["recall"]),
        "f1_score": float(eval_result["f1"]),
        "optimal_threshold": float(eval_result["threshold"]),
        "training_duration_seconds": float(training_duration_seconds),
    }
    if inference_latency_ms_avg is not None:
        payload["inference_latency_ms_avg"] = float(inference_latency_ms_avg)
    return payload


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return None
    return out.stdout.strip() or None


def build_run_tags(model_type: str) -> dict[str, str]:
    """Return a small dict of MLflow tags applied to every run."""
    tags: dict[str, str] = {
        "model_type": model_type,
        "host": platform.node() or "unknown",
        "python_version": platform.python_version(),
        "feature_set_version": FEATURE_SET_VERSION,
        "dataset_version": DATASET_VERSION,
    }
    sha = _git_sha()
    if sha:
        tags["git_sha"] = sha
    return tags


@contextmanager
def start_run(
    run_name: str, tags: dict[str, str] | None = None
) -> Iterator[mlflow.ActiveRun]:
    """Context manager wrapping ``mlflow.start_run`` with a friendly name."""
    with mlflow.start_run(run_name=run_name, tags=tags) as active_run:
        logger.info("started MLflow run {} (id={})", run_name, active_run.info.run_id)
        yield active_run


def _confusion_matrix_artifact(eval_result: EvaluationResult) -> dict[str, Any]:
    cm = eval_result["confusion_matrix"]
    return {
        "labels": [0, 1],
        "matrix": [[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]],
        "tn": cm["tn"],
        "fp": cm["fp"],
        "fn": cm["fn"],
        "tp": cm["tp"],
    }


def _classification_report_text(
    y_true: np.ndarray, y_score: np.ndarray, threshold: float
) -> str:
    y_pred = (np.asarray(y_score, dtype=float) >= threshold).astype(int)
    return classification_report(
        np.asarray(y_true).astype(int),
        y_pred,
        labels=[0, 1],
        target_names=["legit", "fraud"],
        digits=4,
        zero_division=0,
    )


def log_run_artifacts(
    *,
    model_name: str,
    eval_result: EvaluationResult,
    y_true: np.ndarray,
    y_score: np.ndarray,
    extra_metrics: dict[str, Any] | None = None,
) -> None:
    """Dump per-run JSON/text artifacts and attach them to the active run."""
    extras = extra_metrics or {}

    with tempfile.TemporaryDirectory() as raw_dir:
        tmp_dir = Path(raw_dir)

        metrics_path = tmp_dir / f"{model_name}_metrics.json"
        metrics_path.write_text(json.dumps(eval_result, indent=2), encoding="utf-8")

        cm_path = tmp_dir / "confusion_matrix.json"
        cm_path.write_text(
            json.dumps(_confusion_matrix_artifact(eval_result), indent=2),
            encoding="utf-8",
        )

        report_path = tmp_dir / "classification_report.txt"
        report_path.write_text(
            _classification_report_text(y_true, y_score, eval_result["threshold"]),
            encoding="utf-8",
        )

        features_path = tmp_dir / "feature_names.json"
        features_path.write_text(
            json.dumps({"feature_columns": FEATURE_COLUMNS}, indent=2),
            encoding="utf-8",
        )

        threshold_path = tmp_dir / "optimal_threshold.json"
        threshold_path.write_text(
            json.dumps(
                {
                    "threshold": float(eval_result["threshold"]),
                    "selection_metric": "f1",
                    "model_type": model_name,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        summary_path = tmp_dir / "model_summary.json"
        summary = {
            "model_type": model_name,
            "n_samples": eval_result["n_samples"],
            "n_positive": eval_result["n_positive"],
            "pr_auc": eval_result["pr_auc"],
            "roc_auc": eval_result["roc_auc"],
            "f1": eval_result["f1"],
            **extras,
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        for path in (
            metrics_path,
            cm_path,
            report_path,
            features_path,
            threshold_path,
            summary_path,
        ):
            mlflow.log_artifact(str(path))


def log_sklearn_pipeline(
    pipeline: Pipeline,
    x_sample: pd.DataFrame,
    artifact_path: str = MLFLOW_MODEL_ARTIFACT_PATH,
) -> str:
    """Log the full sklearn pipeline as an MLflow model and return its URI."""
    signature = mlflow.models.infer_signature(
        x_sample.head(50),
        pipeline.predict_proba(x_sample.head(50))[:, 1],
    )
    info = mlflow.sklearn.log_model(
        sk_model=pipeline,
        name=artifact_path,
        signature=signature,
        input_example=x_sample.head(5),
    )
    model_uri = info.model_uri
    logger.info("logged sklearn pipeline as model artifact: {}", model_uri)
    return model_uri


def resolve_tracking_uri(cli_override: str | None = None) -> str:
    """Pick a tracking URI from (CLI override -> env -> sensible default)."""
    if cli_override:
        return cli_override
    env_val = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if env_val:
        return env_val
    return "http://localhost:5000"
