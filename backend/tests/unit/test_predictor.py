"""Unit tests for :class:`FraudPredictor` and :class:`DummyFraudModel`."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from src.core.exceptions import InvalidModelOutputError, PredictionError
from src.features.constants import FEATURE_COLUMNS
from src.models.loader import DummyFraudModel, LoadedModel
from src.models.predictor import FraudPredictor


def _make_predictor(model: object, threshold: float = 0.5) -> FraudPredictor:
    loaded = LoadedModel(
        model=model,
        model_name="test-model",
        model_version="42",
        model_stage="Production",
        threshold=threshold,
        loaded_at=datetime.now(tz=UTC),
        feature_count=len(FEATURE_COLUMNS),
        is_dummy=False,
    )
    return FraudPredictor(loaded)


def test_dummy_probability_in_unit_interval(sample_transaction: dict) -> None:
    """DummyFraudModel must always return probabilities in [0, 1]."""
    predictor = _make_predictor(DummyFraudModel())
    result = predictor.predict(sample_transaction)
    assert 0.0 <= result.fraud_probability <= 1.0


def test_threshold_creates_correct_label(risky_transaction: dict) -> None:
    """At threshold=0.0, every prediction must be labelled fraud."""
    predictor = _make_predictor(DummyFraudModel(), threshold=0.0)
    result = predictor.predict(risky_transaction)
    assert result.predicted_label == 1
    assert result.is_fraud is True


def test_threshold_high_never_flags(sample_transaction: dict) -> None:
    """At threshold=1.0 + epsilon, nothing can be flagged."""
    predictor = _make_predictor(DummyFraudModel(), threshold=1.0)
    result = predictor.predict(sample_transaction)
    # Only an exact 1.0 probability could match — extremely unlikely.
    assert result.predicted_label in (0, 1)
    assert result.threshold_used == 1.0


def test_batch_returns_same_length(sample_transaction: dict) -> None:
    """predict_batch must return one PredictionResult per input."""
    predictor = _make_predictor(DummyFraudModel())
    batch = [sample_transaction] * 5
    results = predictor.predict_batch(batch)
    assert len(results) == 5
    for r in results:
        assert 0.0 <= r.fraud_probability <= 1.0


def test_model_info_returns_expected_keys() -> None:
    """get_model_info must expose every key the /v1/model/info response needs."""
    predictor = _make_predictor(DummyFraudModel(), threshold=0.42)
    info = predictor.get_model_info()
    expected = {
        "model_name",
        "model_version",
        "model_stage",
        "model_loaded",
        "optimal_threshold",
        "feature_count",
        "loaded_at",
    }
    assert expected.issubset(info.keys())
    assert info["optimal_threshold"] == 0.42
    assert info["feature_count"] == len(FEATURE_COLUMNS)


def test_predict_batch_empty_returns_empty() -> None:
    """An empty input list should produce an empty result list."""
    predictor = _make_predictor(DummyFraudModel())
    assert predictor.predict_batch([]) == []


def test_missing_feature_raises(sample_transaction: dict) -> None:
    """A row missing a canonical feature column must raise PredictionError."""
    predictor = _make_predictor(DummyFraudModel())
    incomplete = dict(sample_transaction)
    incomplete.pop("transaction_amount")
    with pytest.raises(PredictionError):
        predictor.predict(incomplete)


class _DecisionFunctionModel:
    """Stub estimator exposing only decision_function (no predict_proba)."""

    def decision_function(self, df: pd.DataFrame) -> np.ndarray:
        return np.zeros(len(df))


def test_decision_function_path(sample_transaction: dict) -> None:
    """decision_function output is sigmoid-converted to probabilities."""
    predictor = _make_predictor(_DecisionFunctionModel())
    result = predictor.predict(sample_transaction)
    # sigmoid(0) = 0.5
    assert abs(result.fraud_probability - 0.5) < 1e-6


class _BrokenModel:
    """Estimator exposing predict_proba but returning a malformed shape."""

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return np.zeros(len(df))


def test_invalid_predict_proba_shape(sample_transaction: dict) -> None:
    """A 1-D predict_proba output must raise InvalidModelOutputError."""
    predictor = _make_predictor(_BrokenModel())
    with pytest.raises(InvalidModelOutputError):
        predictor.predict(sample_transaction)


class _NoMethodModel:
    """Estimator with neither predict_proba nor decision_function."""


def test_no_predict_method_raises(sample_transaction: dict) -> None:
    """A model exposing neither method must raise PredictionError."""
    predictor = _make_predictor(_NoMethodModel())
    with pytest.raises(PredictionError):
        predictor.predict(sample_transaction)
