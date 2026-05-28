"""Tests for ``src.training.experiment``.

Runs against a temporary file-based MLflow tracking store so the suite
does not require Docker or a live MLflow server.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import pytest

from src.training.experiment import (
    EXPERIMENT_NAME,
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


@pytest.fixture
def local_tracking_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    uri = (tmp_path / "mlruns").as_uri()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    configure_mlflow(uri)
    yield uri
    mlflow.set_tracking_uri("")


def test_setup_experiment_creates_named_experiment(local_tracking_uri: str) -> None:
    experiment_id = setup_experiment("phase2-unit-test")
    assert experiment_id
    fetched = mlflow.get_experiment_by_name("phase2-unit-test")
    assert fetched is not None
    assert fetched.experiment_id == experiment_id


def test_setup_experiment_is_idempotent(local_tracking_uri: str) -> None:
    first = setup_experiment("phase2-idempotent")
    second = setup_experiment("phase2-idempotent")
    assert first == second


def test_build_params_payload_has_required_keys() -> None:
    payload = build_params_payload(
        model_params={"model_type": "logistic_regression", "max_iter": 1_000},
        dataset_meta={
            "train_size": 100,
            "test_size": 25,
            "fraud_rate_train": 0.04,
            "fraud_rate_test": 0.05,
            "random_state": 42,
        },
    )
    for key in (
        "model_type",
        "feature_set_version",
        "dataset_version",
        "train_size",
        "test_size",
        "fraud_rate_train",
        "fraud_rate_test",
        "random_state",
    ):
        assert key in payload, f"missing key {key}"


def test_build_metrics_payload_has_required_keys() -> None:
    eval_result = {
        "roc_auc": 0.83,
        "pr_auc": 0.31,
        "precision": 0.4,
        "recall": 0.35,
        "f1": 0.37,
        "threshold": 0.72,
        "confusion_matrix": {"tn": 100, "fp": 5, "fn": 6, "tp": 9},
        "n_samples": 120,
        "n_positive": 15,
    }
    payload = build_metrics_payload(eval_result, training_duration_seconds=4.2)
    required = {
        "roc_auc",
        "pr_auc",
        "precision",
        "recall",
        "f1_score",
        "optimal_threshold",
        "training_duration_seconds",
    }
    assert required.issubset(payload.keys())


def test_build_run_tags_contains_core_metadata() -> None:
    tags = build_run_tags("xgboost")
    assert tags["model_type"] == "xgboost"
    assert tags["feature_set_version"]
    assert tags["python_version"]


def test_resolve_tracking_uri_prefers_cli_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://from-env:5000")
    assert resolve_tracking_uri("http://from-cli:9999") == "http://from-cli:9999"


def test_resolve_tracking_uri_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://from-env:5000")
    assert resolve_tracking_uri(None) == "http://from-env:5000"


def test_log_run_artifacts_uploads_expected_files(local_tracking_uri: str) -> None:
    setup_experiment("phase2-artifacts")
    eval_result = {
        "roc_auc": 0.9,
        "pr_auc": 0.5,
        "precision": 0.6,
        "recall": 0.4,
        "f1": 0.48,
        "threshold": 0.65,
        "confusion_matrix": {"tn": 50, "fp": 3, "fn": 4, "tp": 7},
        "n_samples": 64,
        "n_positive": 11,
    }
    y_true = np.array([0, 1, 0, 1, 1, 0])
    y_score = np.array([0.1, 0.8, 0.3, 0.7, 0.6, 0.2])

    with start_run("artifact-smoke") as run:
        log_run_artifacts(
            model_name="logistic_regression",
            eval_result=eval_result,
            y_true=y_true,
            y_score=y_score,
            extra_metrics={"train_seconds": 1.0},
        )
        run_id = run.info.run_id

    client = mlflow.tracking.MlflowClient()
    listed = {item.path for item in client.list_artifacts(run_id)}
    expected = {
        "logistic_regression_metrics.json",
        "confusion_matrix.json",
        "classification_report.txt",
        "feature_names.json",
        "optimal_threshold.json",
        "model_summary.json",
    }
    assert expected.issubset(listed)


def test_log_sklearn_pipeline_returns_model_uri(local_tracking_uri: str) -> None:
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    setup_experiment("phase2-model-log")
    rng = np.random.default_rng(0)
    x = pd.DataFrame(
        {
            "a": rng.normal(size=120),
            "b": rng.normal(size=120),
            "c": rng.normal(size=120),
        }
    )
    y = pd.Series((rng.random(120) < 0.4).astype(int))

    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=500)),
        ]
    )
    pipeline.fit(x, y)

    with start_run("model-log-smoke"):
        uri = log_sklearn_pipeline(pipeline, x_sample=x.head(20))

    assert uri.startswith("runs:/") or uri.startswith("models:/")
    loaded = mlflow.sklearn.load_model(uri)
    assert hasattr(loaded, "predict_proba")


def test_experiment_name_constant() -> None:
    assert EXPERIMENT_NAME == "fraud-detection"
