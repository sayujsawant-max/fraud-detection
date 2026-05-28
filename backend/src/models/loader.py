"""Production-model loader for the FraudShield serving layer.

This module is responsible for materialising the registered ``fraud-detector``
model from MLflow at FastAPI startup, alongside its optimal decision
threshold. It encapsulates three concerns:

1. **Stage/alias compatibility.** MLflow 3.x removed the legacy ``Stage``
   taxonomy in favour of mutable *aliases*. We try the Stage URI first
   (``models:/<name>/<Stage>``) and fall back to alias URIs
   (``models:/<name>@<alias>``) so the same loader works against MLflow 2.x
   and 3.x without code changes.
2. **Threshold resolution.** Tries the run's ``optimal_threshold.json``
   artifact, then a logged metric named ``optimal_threshold``, then the
   ``DEFAULT_THRESHOLD`` setting.
3. **Dummy fallback.** When ``ALLOW_DUMMY_MODEL=True`` and the registry call
   fails, returns a deterministic :class:`DummyFraudModel` so the API can be
   exercised end-to-end before a real model is registered. In production
   (``ALLOW_DUMMY_MODEL=False``) the failure propagates and readiness flips
   to 503.

The legacy alias-only helper :func:`load_production_model` is retained for
Phase 2 callers (scripts and notebooks) — Phase 3 should prefer
:func:`load_model`.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import pandas as pd
from loguru import logger

# Cap MLflow's HTTP timeout and retry budget so unreachable tracking servers
# fail fast and the dummy-model fallback kicks in promptly during local dev.
# Without these the urllib3 retry policy waits ~5 minutes before giving up.
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_BACKOFF_FACTOR", "0")

from src.core.config import Settings, get_settings
from src.core.exceptions import ModelNotLoadedError
from src.features.constants import FEATURE_COLUMNS
from src.models.registry import (
    CHAMPION_ALIAS,
    PRODUCTION_ALIAS,
    MlflowRegistryClient,
    ProductionModelInfo,
)

# Sentinels for the dummy model identity.
DUMMY_MODEL_NAME: str = "dummy-fraud-model"
DUMMY_MODEL_VERSION: str = "dev"
DUMMY_MODEL_STAGE: str = "development"


@dataclass(frozen=True)
class LoadedProductionModel:
    """Sklearn pipeline + decision threshold + registry metadata.

    Retained for Phase 2 callers that already import this dataclass.
    """

    model: Any
    threshold: float
    info: ProductionModelInfo


@dataclass
class LoadedModel:
    """Phase 3 serving-side view of the currently-loaded model.

    Unlike :class:`LoadedProductionModel`, this dataclass is the unit of
    truth for the predictor, dependency-injection container, and
    ``/v1/model/info`` endpoint.
    """

    model: Any
    model_name: str
    model_version: str
    model_stage: str
    threshold: float
    loaded_at: datetime
    feature_count: int
    is_dummy: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


class DummyFraudModel:
    """Deterministic stand-in for the real sklearn pipeline.

    Produces a fraud probability in [0, 1] derived from a handful of risk
    features. Exists purely to keep the API serviceable for local dev,
    smoke tests, and CI without requiring an MLflow tracking server.
    """

    # Mirrors sklearn's API so the predictor does not need to special-case it.
    classes_ = np.array([0, 1])

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:  # noqa: D401
        """Return an (n, 2) array of [P(legit), P(fraud)]."""
        # Each component is clipped to [0, 1] and weights chosen to give a
        # plausible spread over the synthetic dataset.
        amount_signal = np.clip(
            df.get("amount_to_avg_ratio", 0).astype(float) / 5.0, 0, 1
        )
        velocity_signal = df.get("is_high_velocity", 0).astype(float).clip(0, 1)
        foreign_signal = df.get("is_foreign_transaction", 0).astype(float).clip(0, 1)
        risky_country = df.get("is_high_risk_country", 0).astype(float).clip(0, 1)
        ip_signal = df.get("ip_risk_score", 0).astype(float).clip(0, 1)
        late_night = df.get("is_late_night", 0).astype(float).clip(0, 1)
        new_account = df.get("is_new_account", 0).astype(float).clip(0, 1)

        fraud_score = (
            0.30 * amount_signal
            + 0.20 * velocity_signal
            + 0.15 * foreign_signal
            + 0.15 * risky_country
            + 0.10 * ip_signal
            + 0.05 * late_night
            + 0.05 * new_account
        ).to_numpy()

        fraud_score = np.clip(fraud_score, 0.0, 1.0)
        return np.column_stack([1.0 - fraud_score, fraud_score])


# ---------------------------------------------------------------------------
# Phase 2 helper — retained so Phase 2 callers keep working.
# ---------------------------------------------------------------------------


def _read_threshold_artifact(run_id: str) -> float:
    """Best-effort read of ``optimal_threshold.json`` from the run artifacts."""
    client = mlflow.tracking.MlflowClient()
    try:
        local_dir = Path(
            client.download_artifacts(
                run_id, "optimal_threshold.json", dst_path=tempfile.mkdtemp()
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("could not load optimal_threshold.json: {}", exc)
        return 0.5
    payload = json.loads(local_dir.read_text(encoding="utf-8"))
    return float(payload.get("threshold", 0.5))


def load_production_model(
    model_name: str,
    tracking_uri: str,
) -> LoadedProductionModel:
    """Phase 2 alias-only loader (retained for scripts and notebooks).

    Raises:
        LookupError: If no version of ``model_name`` is aliased ``production``.
    """
    mlflow.set_tracking_uri(tracking_uri)
    registry = MlflowRegistryClient(tracking_uri=tracking_uri)
    info = registry.get_production_model_info(model_name)
    if info is None:
        raise LookupError(
            f"no version of {model_name!r} is aliased {PRODUCTION_ALIAS!r}; "
            "run promote_model.py after training first"
        )

    model_uri = f"models:/{model_name}@{PRODUCTION_ALIAS}"
    logger.info("loading production model from {}", model_uri)
    model = mlflow.sklearn.load_model(model_uri)

    threshold = 0.5
    if info.run_id:
        threshold = _read_threshold_artifact(info.run_id)

    return LoadedProductionModel(model=model, threshold=threshold, info=info)


# ---------------------------------------------------------------------------
# Phase 3 serving-side loader.
# ---------------------------------------------------------------------------


def _try_load_stage(model_name: str, stage: str) -> Any | None:
    """Try the legacy ``models:/<name>/<Stage>`` URI. Returns model or None.

    MLflow 3.x raises if no version has the given stage; we treat that as
    "stage not available" and fall back to aliases.
    """
    uri = f"models:/{model_name}/{stage}"
    try:
        logger.info("attempting to load model from stage URI {}", uri)
        return mlflow.sklearn.load_model(uri)
    except Exception as exc:  # noqa: BLE001 - mlflow surfaces many exception classes
        logger.warning("stage URI {} unavailable: {}", uri, exc)
        return None


def _try_load_alias(model_name: str, alias: str) -> Any | None:
    """Try ``models:/<name>@<alias>`` (MLflow 3.x). Returns model or None."""
    uri = f"models:/{model_name}@{alias}"
    try:
        logger.info("attempting to load model from alias URI {}", uri)
        return mlflow.sklearn.load_model(uri)
    except Exception as exc:  # noqa: BLE001
        logger.warning("alias URI {} unavailable: {}", uri, exc)
        return None


def _resolve_threshold(
    registry: MlflowRegistryClient,
    info: ProductionModelInfo | None,
    fallback: float,
) -> float:
    """Resolve the decision threshold.

    Tries the artifact first (most authoritative — written by training),
    then a logged metric, then the configured fallback.
    """
    if info is None or not info.run_id:
        return fallback

    # Artifact attempt.
    try:
        threshold = _read_threshold_artifact(info.run_id)
        logger.info("optimal threshold from artifact: {:.4f}", threshold)
        return threshold
    except Exception as exc:  # noqa: BLE001
        logger.warning("threshold artifact lookup failed: {}", exc)

    # Metric attempt.
    try:
        run = registry.client.get_run(info.run_id)
        metric_value = run.data.metrics.get("optimal_threshold")
        if metric_value is not None:
            logger.info("optimal threshold from metric: {:.4f}", metric_value)
            return float(metric_value)
    except Exception as exc:  # noqa: BLE001
        logger.warning("threshold metric lookup failed: {}", exc)

    logger.warning("falling back to default threshold {:.4f}", fallback)
    return fallback


def _load_dummy(settings: Settings, reason: str) -> LoadedModel:
    """Return a :class:`LoadedModel` wrapping the dummy estimator."""
    logger.warning("loading DummyFraudModel (ALLOW_DUMMY_MODEL=True): {}", reason)
    return LoadedModel(
        model=DummyFraudModel(),
        model_name=DUMMY_MODEL_NAME,
        model_version=DUMMY_MODEL_VERSION,
        model_stage=DUMMY_MODEL_STAGE,
        threshold=settings.DEFAULT_THRESHOLD,
        loaded_at=datetime.now(tz=UTC),
        feature_count=len(FEATURE_COLUMNS),
        is_dummy=True,
        extras={"reason": reason},
    )


def load_model(settings: Settings | None = None) -> LoadedModel:
    """Load the currently-deployed fraud-detector model.

    Resolution order:

    1. ``models:/<name>/<Stage>`` — legacy MLflow 2.x stage taxonomy.
    2. ``models:/<name>@production`` — MLflow 3.x alias.
    3. ``models:/<name>@champion`` — fallback alias used during training
       before promotion.

    Args:
        settings: Override settings (mainly for tests). Falls back to the
            cached :func:`get_settings` when omitted.

    Returns:
        :class:`LoadedModel`. If MLflow loading fails and
        ``ALLOW_DUMMY_MODEL`` is True, returns a dummy-backed
        :class:`LoadedModel`.

    Raises:
        ModelNotLoadedError: If MLflow loading fails and
            ``ALLOW_DUMMY_MODEL`` is False.
    """
    settings = settings or get_settings()
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    name = settings.MLFLOW_MODEL_NAME
    stage = settings.MLFLOW_MODEL_STAGE

    model: Any | None = None
    resolved_stage = stage
    registry_info: ProductionModelInfo | None = None

    # 1. Stage URI.
    model = _try_load_stage(name, stage)

    # 2. Alias URI (canonical for MLflow 3.x).
    if model is None:
        model = _try_load_alias(name, PRODUCTION_ALIAS)
        if model is not None:
            resolved_stage = "Production"

    # 3. Champion alias fallback.
    if model is None:
        model = _try_load_alias(name, CHAMPION_ALIAS)
        if model is not None:
            resolved_stage = "Champion"

    if model is None:
        msg = (
            f"could not resolve any URI for model {name!r} "
            f"(tried stage={stage!r}, aliases={PRODUCTION_ALIAS!r}/{CHAMPION_ALIAS!r})"
        )
        if settings.ALLOW_DUMMY_MODEL:
            return _load_dummy(settings, reason=msg)
        raise ModelNotLoadedError(msg)

    # Fetch registry metadata (best-effort — failure here is non-fatal).
    try:
        registry = MlflowRegistryClient(tracking_uri=settings.MLFLOW_TRACKING_URI)
        registry_info = registry.get_production_model_info(name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("registry metadata lookup failed: {}", exc)
        registry = None  # type: ignore[assignment]

    threshold = (
        _resolve_threshold(registry, registry_info, settings.DEFAULT_THRESHOLD)
        if registry is not None
        else settings.DEFAULT_THRESHOLD
    )

    version = registry_info.version if registry_info else "unknown"
    logger.info(
        "model loaded | name={} version={} stage={} threshold={:.4f}",
        name,
        version,
        resolved_stage,
        threshold,
    )

    return LoadedModel(
        model=model,
        model_name=name,
        model_version=version,
        model_stage=resolved_stage,
        threshold=threshold,
        loaded_at=datetime.now(tz=UTC),
        feature_count=len(FEATURE_COLUMNS),
        is_dummy=False,
        extras={"run_id": registry_info.run_id if registry_info else None},
    )


def load_model_safely(settings: Settings | None = None) -> LoadedModel | None:
    """Like :func:`load_model` but never raises.

    Used at FastAPI startup so the application boots even when MLflow is
    unreachable and dummy mode is disabled — readiness probes then report
    503 until the operator fixes the registry.
    """
    settings = settings or get_settings()
    try:
        return load_model(settings)
    except ModelNotLoadedError as exc:
        logger.error("startup model load failed: {}", exc)
        return None
