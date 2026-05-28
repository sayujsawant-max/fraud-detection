"""Fraud-detection predictor used by the FastAPI serving layer.

The predictor wraps a :class:`LoadedModel` and is the single place that
knows how to:

* convert a transaction dict into a single-row DataFrame with the canonical
  feature column order;
* extract the fraud probability from either ``predict_proba`` or
  ``decision_function``;
* apply the configured decision threshold to derive a label;
* stamp the response with model metadata and latency.

Keeping all of this in one class lets the routers stay tiny: each endpoint
does input validation, calls the predictor, and returns the response model.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from src.core.exceptions import InvalidModelOutputError, PredictionError
from src.features.constants import FEATURE_COLUMNS
from src.models.loader import LoadedModel


@dataclass
class PredictionResult:
    """In-process result of a single prediction.

    Mirrors :class:`src.api.schemas.response.PredictionResponse` so the
    router layer can build the response model with a simple ``dict()``
    expansion.
    """

    transaction_id: str
    fraud_probability: float
    predicted_label: int
    is_fraud: bool
    model_name: str
    model_version: str
    model_stage: str
    threshold_used: float
    latency_ms: float
    timestamp: datetime

    def as_dict(self) -> dict[str, Any]:
        """Dict view suitable for ``PredictionResponse(**result.as_dict())``."""
        return {
            "transaction_id": self.transaction_id,
            "fraud_probability": self.fraud_probability,
            "predicted_label": self.predicted_label,
            "is_fraud": self.is_fraud,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_stage": self.model_stage,
            "threshold_used": self.threshold_used,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }


def _sigmoid(values: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid for converting decision scores to probs."""
    return 1.0 / (1.0 + np.exp(-values))


def _frame_from_transactions(transactions: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame restricted to the canonical training-time columns.

    Extra keys (e.g. ``transaction_id``) are silently dropped — they are not
    inputs to the sklearn pipeline.
    """
    df = pd.DataFrame(transactions)
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise PredictionError(f"input is missing required features: {missing}")
    return df.loc[:, FEATURE_COLUMNS].copy()


class FraudPredictor:
    """Scores fraud transactions using a loaded sklearn pipeline."""

    def __init__(self, loaded_model: LoadedModel) -> None:
        self._loaded = loaded_model

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, transaction: dict[str, Any]) -> PredictionResult:
        """Score a single transaction."""
        results = self.predict_batch([transaction])
        return results[0]

    def predict_batch(
        self, transactions: list[dict[str, Any]]
    ) -> list[PredictionResult]:
        """Score a batch of transactions and return one result per row."""
        if not transactions:
            return []

        # Capture transaction_ids before stripping them off the DataFrame.
        transaction_ids = [
            str(tx.get("transaction_id") or uuid.uuid4()) for tx in transactions
        ]

        df = _frame_from_transactions(transactions)

        start = time.perf_counter()
        probabilities = self._score(df)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        per_item_ms = (
            elapsed_ms / len(probabilities) if probabilities.size else elapsed_ms
        )

        threshold = self._loaded.threshold
        now = datetime.now(tz=UTC)
        results: list[PredictionResult] = []
        for tx_id, prob in zip(transaction_ids, probabilities, strict=True):
            label = 1 if prob >= threshold else 0
            results.append(
                PredictionResult(
                    transaction_id=tx_id,
                    fraud_probability=float(prob),
                    predicted_label=label,
                    is_fraud=bool(label),
                    model_name=self._loaded.model_name,
                    model_version=self._loaded.model_version,
                    model_stage=self._loaded.model_stage,
                    threshold_used=float(threshold),
                    latency_ms=float(per_item_ms),
                    timestamp=now,
                )
            )

        logger.info(
            "scored batch | size={} model={}@v{} avg_latency_ms={:.2f}",
            len(results),
            self._loaded.model_name,
            self._loaded.model_version,
            per_item_ms,
        )
        return results

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_model_info(self) -> dict[str, Any]:
        """Return a JSON-serialisable view of the loaded model's identity."""
        return {
            "model_name": self._loaded.model_name,
            "model_version": self._loaded.model_version,
            "model_stage": self._loaded.model_stage,
            "model_loaded": True,
            "optimal_threshold": self._loaded.threshold,
            "feature_count": self._loaded.feature_count,
            "loaded_at": self._loaded.loaded_at,
        }

    @property
    def loaded_model(self) -> LoadedModel:
        """Expose the underlying loaded model (used by dependency injection)."""
        return self._loaded

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _score(self, df: pd.DataFrame) -> np.ndarray:
        """Return the per-row fraud probability as a 1-D numpy array."""
        estimator = self._loaded.model

        if hasattr(estimator, "predict_proba"):
            try:
                proba = estimator.predict_proba(df)
            except Exception as exc:  # noqa: BLE001
                logger.exception("predict_proba failed")
                raise PredictionError("model failed during predict_proba") from exc
            return self._extract_fraud_column(proba)

        if hasattr(estimator, "decision_function"):
            try:
                scores = np.asarray(estimator.decision_function(df))
            except Exception as exc:  # noqa: BLE001
                logger.exception("decision_function failed")
                raise PredictionError("model failed during decision_function") from exc
            if scores.ndim != 1:
                raise InvalidModelOutputError(
                    f"decision_function returned unexpected shape {scores.shape}"
                )
            return _sigmoid(scores)

        raise PredictionError(
            "loaded model exposes neither predict_proba nor decision_function"
        )

    @staticmethod
    def _extract_fraud_column(proba: Any) -> np.ndarray:
        """Slice the positive-class column from a (n, 2) probability matrix."""
        array = np.asarray(proba)
        if array.ndim != 2 or array.shape[1] < 2:
            raise InvalidModelOutputError(
                f"predict_proba returned unexpected shape {array.shape}"
            )
        positive = array[:, 1]
        if np.any(np.isnan(positive)) or np.any(
            (positive < -1e-6) | (positive > 1 + 1e-6)
        ):
            raise InvalidModelOutputError(
                "predict_proba returned non-probability values"
            )
        # Clamp tiny floating-point overshoot back into [0, 1].
        clipped = np.clip(positive, 0.0, 1.0)
        if np.any([math.isnan(float(v)) for v in clipped]):
            raise InvalidModelOutputError("predict_proba produced NaN")
        return clipped
