"""Custom Prometheus metrics for the FraudShield observability layer.

All FraudShield-specific metrics are declared in this module so the rest
of the codebase imports them by name rather than reaching for the global
``prometheus_client`` registry. Two important consequences:

1. **Idempotent registration.** ``_get_or_create`` consults the registry
   first and re-uses an existing collector instead of raising
   ``Duplicated timeseries``. That's what lets the FastAPI process reload
   modules in tests (which import the metrics package multiple times)
   without crashing.

2. **No high-cardinality labels.** Every collector below uses a small,
   bounded label set (model_name/version/stage, status, trigger_reason,
   predicted label, HTTP method/endpoint/status). We **never** push
   per-request identifiers (``transaction_id``, ``user_id``,
   ``request_id``, raw input feature values) into a label — that would
   blow up Prometheus cardinality and leak PII into the time-series DB.

Metric naming follows the Prometheus convention (`<namespace>_<name>_<unit>`)
plus the project prefix ``fraudshield_``. Histograms keep their default
``_bucket``, ``_sum``, ``_count`` suffixes so the recommended PromQL
``histogram_quantile`` and ``rate()`` queries Just Work.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Idempotent metric constructors
# ---------------------------------------------------------------------------


def _get_or_create(
    metric_cls: type,
    name: str,
    documentation: str,
    *,
    labelnames: tuple[str, ...] = (),
    buckets: tuple[float, ...] | None = None,
    registry: CollectorRegistry | None = None,
) -> Any:
    """Return an existing collector by name, or register a new one.

    Without this, importing the metrics module twice (which happens
    naturally under pytest's import-hook + ``importlib.reload`` paths)
    raises ``Duplicated timeseries in CollectorRegistry: ...`` and brings
    the whole API down on reload.
    """
    target_registry = registry or REGISTRY

    existing = target_registry._names_to_collectors.get(name)  # noqa: SLF001
    if existing is not None:
        return existing

    kwargs: dict[str, Any] = {"name": name, "documentation": documentation}
    if labelnames:
        kwargs["labelnames"] = labelnames
    if buckets is not None:
        kwargs["buckets"] = buckets
    if registry is not None:
        kwargs["registry"] = registry
    return metric_cls(**kwargs)


# ---------------------------------------------------------------------------
# Request metrics (1-3)
# ---------------------------------------------------------------------------

REQUESTS_TOTAL: Counter = _get_or_create(
    Counter,
    "fraudshield_requests_total",
    "Total number of API requests",
    labelnames=("method", "endpoint", "http_status"),
)

REQUEST_DURATION_SECONDS: Histogram = _get_or_create(
    Histogram,
    "fraudshield_request_duration_seconds",
    "API request duration in seconds",
    labelnames=("endpoint",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

REQUESTS_IN_PROGRESS: Gauge = _get_or_create(
    Gauge,
    "fraudshield_requests_in_progress",
    "Currently active API requests",
    labelnames=("endpoint",),
)


# ---------------------------------------------------------------------------
# Model metrics (4-8)
# ---------------------------------------------------------------------------

PREDICTIONS_TOTAL: Counter = _get_or_create(
    Counter,
    "fraudshield_predictions_total",
    "Total number of predictions served, partitioned by predicted label",
    labelnames=("label",),
)

PREDICTION_SCORE: Histogram = _get_or_create(
    Histogram,
    "fraudshield_prediction_score",
    "Distribution of fraud probability scores",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

BATCH_SIZE: Histogram = _get_or_create(
    Histogram,
    "fraudshield_batch_size",
    "Distribution of batch prediction sizes",
    buckets=(1, 5, 10, 25, 50, 100),
)

MODEL_LOAD_TIMESTAMP: Gauge = _get_or_create(
    Gauge,
    "fraudshield_model_load_timestamp",
    "Unix timestamp when the production model was last loaded",
)

MODEL_VERSION_INFO: Gauge = _get_or_create(
    Gauge,
    "fraudshield_model_version_info",
    "Static gauge (value=1) carrying current model metadata as labels",
    labelnames=("model_name", "model_version", "model_stage"),
)


# ---------------------------------------------------------------------------
# Drift metrics (9-11)
# ---------------------------------------------------------------------------

LATEST_DRIFT_SCORE: Gauge = _get_or_create(
    Gauge,
    "fraudshield_latest_drift_score",
    "Latest drift score computed by the Phase 5 detector",
)

DRIFT_DETECTED_TOTAL: Counter = _get_or_create(
    Counter,
    "fraudshield_drift_detected_total",
    "Total number of drift events detected (drift_detected=True)",
)

DRIFT_CHECKS_TOTAL: Counter = _get_or_create(
    Counter,
    "fraudshield_drift_checks_total",
    "Total number of drift checks, by status",
    labelnames=("status",),
)


# ---------------------------------------------------------------------------
# Retraining metrics (12-15)
# ---------------------------------------------------------------------------

RETRAINING_RUNS_TOTAL: Counter = _get_or_create(
    Counter,
    "fraudshield_retraining_runs_total",
    "Total number of retraining runs, by status + trigger",
    labelnames=("status", "trigger_reason"),
)

LATEST_CHALLENGER_PR_AUC: Gauge = _get_or_create(
    Gauge,
    "fraudshield_latest_challenger_pr_auc",
    "PR-AUC of the most recently trained challenger model",
)

LATEST_CHAMPION_PR_AUC: Gauge = _get_or_create(
    Gauge,
    "fraudshield_latest_champion_pr_auc",
    "PR-AUC of the current production champion model",
)

MODEL_PROMOTIONS_TOTAL: Counter = _get_or_create(
    Counter,
    "fraudshield_model_promotions_total",
    "Total number of successful champion-promotion events",
)


# ---------------------------------------------------------------------------
# Recording helpers — single entry points so callers don't have to know
# which collector to touch. Each helper is wrapped in a try/except so a
# metrics-side bug can never break the user-facing path.
# ---------------------------------------------------------------------------


def _label_for_predicted(predicted_label: int) -> str:
    """Map the 0/1 prediction to a human-readable label string."""
    return "fraud" if int(predicted_label) == 1 else "legitimate"


def record_prediction(predicted_label: int, fraud_probability: float) -> None:
    """Record one prediction's contribution to the model-behavior metrics."""
    try:
        PREDICTIONS_TOTAL.labels(label=_label_for_predicted(predicted_label)).inc()
        PREDICTION_SCORE.observe(float(fraud_probability))
    except Exception as exc:  # noqa: BLE001 — metrics are best-effort
        logger.warning("record_prediction failed: {}", exc)


def record_batch(predictions: list[tuple[int, float]]) -> None:
    """Record a whole batch of predictions in one go."""
    try:
        BATCH_SIZE.observe(len(predictions))
        for predicted_label, fraud_probability in predictions:
            record_prediction(predicted_label, fraud_probability)
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_batch failed: {}", exc)


def record_model_loaded(
    *,
    model_name: str,
    model_version: str,
    model_stage: str,
    loaded_at_epoch: float,
) -> None:
    """Stamp the loaded-at timestamp and the version-info labels."""
    try:
        MODEL_LOAD_TIMESTAMP.set(float(loaded_at_epoch))
        # Clear stale label combinations so /metrics never shows two
        # versions live at the same time after a hot-reload.
        MODEL_VERSION_INFO.clear()
        MODEL_VERSION_INFO.labels(
            model_name=str(model_name),
            model_version=str(model_version),
            model_stage=str(model_stage),
        ).set(1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_model_loaded failed: {}", exc)


def record_drift_check(
    *,
    status: str,
    drift_score: float | None,
    drift_detected: bool,
) -> None:
    """Record one drift check's contribution to the drift metrics."""
    try:
        DRIFT_CHECKS_TOTAL.labels(status=str(status)).inc()
        if drift_score is not None:
            LATEST_DRIFT_SCORE.set(float(drift_score))
        if drift_detected:
            DRIFT_DETECTED_TOTAL.inc()
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_drift_check failed: {}", exc)


def record_retraining_run(
    *,
    status: str,
    trigger_reason: str,
    promoted: bool,
    challenger_pr_auc: float | None,
    champion_pr_auc: float | None,
) -> None:
    """Record one retraining run's contribution to the retraining metrics.

    Called from the Phase 6 retraining flow after each terminal status.
    """
    try:
        RETRAINING_RUNS_TOTAL.labels(
            status=str(status), trigger_reason=str(trigger_reason)
        ).inc()
        if challenger_pr_auc is not None:
            LATEST_CHALLENGER_PR_AUC.set(float(challenger_pr_auc))
        if champion_pr_auc is not None:
            LATEST_CHAMPION_PR_AUC.set(float(champion_pr_auc))
        if promoted:
            MODEL_PROMOTIONS_TOTAL.inc()
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_retraining_run failed: {}", exc)
