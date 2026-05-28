"""Unit tests for :mod:`src.monitoring.data_loader`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from src.core.config import get_settings
from src.core.exceptions import DriftDataError
from src.db.models.prediction import PredictionLog
from src.features.constants import FEATURE_COLUMNS, TARGET_COLUMN
from src.monitoring.data_loader import (
    build_current_dataset,
    load_reference_dataset,
)


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def test_load_reference_dataset_reads_parquet(tmp_path: Path) -> None:
    """Loader reads the configured parquet file."""
    ref_path = tmp_path / "reference.parquet"
    _write_parquet(
        ref_path,
        pd.DataFrame({"transaction_amount": [10.0, 20.0], TARGET_COLUMN: [0, 1]}),
    )
    settings = get_settings().model_copy(update={"REFERENCE_DATA_PATH": str(ref_path)})
    df = load_reference_dataset(settings)
    assert len(df) == 2
    # Target column must be stripped — prediction logs do not carry it.
    assert TARGET_COLUMN not in df.columns


def test_load_reference_dataset_raises_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing reference + missing fallback → DriftDataError with hint.

    We chdir into a fresh tmp_path so the loader's project-root walk can't
    rediscover the real ``backend/data/raw/train.parquet`` shipped in the
    repo.
    """
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    monkeypatch.chdir(isolated)
    settings = get_settings().model_copy(
        update={"REFERENCE_DATA_PATH": "nope/missing.parquet"}
    )
    # Override the fallback constant so the loader can't pick up the real one.
    monkeypatch.setattr(
        "src.monitoring.data_loader.REFERENCE_FALLBACK_PATH",
        "nope/also-missing-train.parquet",
    )
    with pytest.raises(DriftDataError) as exc_info:
        load_reference_dataset(settings)
    assert "make generate-data" in str(exc_info.value)


def _make_log(input_features: dict) -> PredictionLog:
    return PredictionLog(
        id=uuid.uuid4(),
        transaction_id="tx",
        timestamp=datetime.now(tz=UTC),
        input_features=input_features,
        fraud_probability=0.5,
        predicted_label=0,
        model_name="fraud-detector",
        model_version="1",
        model_stage="Production",
        optimal_threshold=0.5,
        latency_ms=10.0,
    )


def test_build_current_dataset_from_logs() -> None:
    """``build_current_dataset`` unpacks JSONB into a DataFrame."""
    logs = [
        _make_log({"transaction_amount": 100.0, "ip_risk_score": 0.1}),
        _make_log({"transaction_amount": 200.0, "ip_risk_score": 0.4}),
    ]
    df = build_current_dataset(logs)
    assert len(df) == 2
    assert "transaction_amount" in df.columns


def test_build_current_dataset_aligns_to_reference_columns() -> None:
    """When reference columns are given, extra columns are dropped + missing filled."""
    logs = [
        _make_log({"transaction_amount": 100.0, "extra_col": "should-be-dropped"}),
    ]
    df = build_current_dataset(
        logs, reference_columns=["transaction_amount", "ip_risk_score"]
    )
    assert list(df.columns) == ["transaction_amount", "ip_risk_score"]
    # Missing column is filled with NA.
    assert pd.isna(df.loc[0, "ip_risk_score"])


def test_build_current_dataset_skips_non_dict_features() -> None:
    """Rows with non-dict ``input_features`` are skipped, not crashed on."""
    bad = _make_log({"transaction_amount": 100.0})
    bad.input_features = None  # type: ignore[assignment]
    good = _make_log({"transaction_amount": 200.0})
    df = build_current_dataset([bad, good])
    assert len(df) == 1


def test_build_current_dataset_empty_returns_empty_frame() -> None:
    """No rows → empty frame with the right column shape (no crash)."""
    df = build_current_dataset([])
    assert df.empty
    assert list(df.columns) == FEATURE_COLUMNS


def test_build_current_dataset_drops_target_when_no_reference_cols() -> None:
    """When reference columns aren't given, the target column is removed."""
    logs = [_make_log({"transaction_amount": 1.0, TARGET_COLUMN: 0})]
    df = build_current_dataset(logs)
    assert TARGET_COLUMN not in df.columns
