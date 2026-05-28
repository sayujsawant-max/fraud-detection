"""Phase 6 retraining flow — train challenger, compare, promote, reload.

The flow reuses the Phase 2 building blocks (``builders``, ``evaluate``,
``experiment``) and the Phase 2 ``MlflowRegistryClient`` rather than
duplicating any training code. Every retraining run materialises one
``retraining_runs`` row so the API and dashboard have a durable history.

The flow returns a plain ``dict`` with the headline outcome so callers
that don't want to import Prefect — the admin router, scripts, tests —
can treat it like a regular async function.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from loguru import logger

from src.core.config import Settings, get_settings
from src.core.exceptions import RetrainingError
from src.core.metrics import record_retraining_run
from src.db.repositories import RetrainingRunRepository
from src.db.repositories.retraining_runs import (
    STATUS_PROMOTED,
    STATUS_REJECTED,
)
from src.db.session import get_sessionmaker
from src.workflows.tasks import flow, task

RETRAINING_FLOW_NAME: str = "fraud-retraining"

ALLOWED_TRIGGERS: tuple[str, ...] = ("manual", "drift", "scheduled")


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@task(name="log_retraining_start")
async def log_retraining_start_task(trigger_reason: str) -> UUID:
    """Insert a ``running`` row and return its UUID."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        repo = RetrainingRunRepository(session)
        run = await repo.create_run(trigger_reason)
        logger.info("retraining run started | id={} trigger={}", run.id, trigger_reason)
        return run.id


@task(name="prepare_training_data")
def prepare_training_data_task(settings: Settings | None = None) -> dict[str, Any]:
    """Ensure train/test parquet files exist; (re)generate when missing.

    Returns the resolved paths so the trainer task doesn't have to redo
    the resolution. Splitting the I/O out of training keeps the trainer
    swappable in tests.
    """
    from pathlib import Path

    settings = settings or get_settings()

    backend_root = Path(__file__).resolve().parents[2]
    train_path = backend_root / "data" / "raw" / "train.parquet"
    test_path = backend_root / "data" / "raw" / "test.parquet"

    if not train_path.exists() or not test_path.exists():
        logger.info(
            "training data missing (train={} test={}) — running generator",
            train_path.exists(),
            test_path.exists(),
        )
        # Lazy import: generate_data is a script-level entrypoint that
        # pulls in numpy/pandas only when actually needed.
        from scripts.generate_data import main as generate_main  # type: ignore

        generate_main()

    return {
        "train_path": str(train_path),
        "test_path": str(test_path),
    }


@task(name="train_challenger_model")
def train_challenger_model_task(
    data_paths: dict[str, Any],
    *,
    settings: Settings | None = None,
    register_model: bool = True,
) -> dict[str, Any]:
    """Train a challenger model and (optionally) register it in MLflow.

    Returns a dict with ``challenger_run_id``, ``challenger_model_uri``,
    ``challenger_model_version`` (None when ``register_model=False``),
    and ``challenger_metrics`` (with ``pr_auc`` mandatory).
    """
    settings = settings or get_settings()

    # Imports kept inside the function: training depends on heavy ML libs
    # that we don't want at module-import time on the API/router path.
    import mlflow

    from src.features.constants import TARGET_COLUMN
    from src.features.pipeline import select_features
    from src.models.registry import CHAMPION_ALIAS, MlflowRegistryClient
    from src.training.builders import (
        RANDOM_STATE,
        build_logistic_regression,
        build_random_forest,
        build_xgboost,
        load_split,
    )
    from src.training.evaluate import evaluate_predictions
    from src.training.experiment import (
        EXPERIMENT_NAME,
        REGISTERED_MODEL_NAME,
        build_metrics_payload,
        build_params_payload,
        build_run_tags,
        configure_mlflow,
        log_run_artifacts,
        log_sklearn_pipeline,
        setup_experiment,
        start_run,
    )

    configure_mlflow(settings.MLFLOW_TRACKING_URI)
    setup_experiment(EXPERIMENT_NAME)

    train_df = load_split(data_paths["train_path"])
    test_df = load_split(data_paths["test_path"])

    x_train = select_features(train_df)
    y_train = train_df[TARGET_COLUMN]
    x_test = select_features(test_df)
    y_test = test_df[TARGET_COLUMN]

    n_pos = int(y_train.sum())
    n_neg = int(len(y_train) - n_pos)
    scale_pos_weight = (n_neg / n_pos) if n_pos else 1.0

    # Prefer XGBoost; fall back to RF or LR if XGBoost is unavailable.
    xgb = build_xgboost(scale_pos_weight)
    candidate = xgb or build_random_forest() or build_logistic_regression()

    dataset_meta = {
        "train_size": int(len(y_train)),
        "test_size": int(len(y_test)),
        "fraud_rate_train": float(y_train.mean()),
        "fraud_rate_test": float(y_test.mean()),
        "random_state": RANDOM_STATE,
    }

    logger.info("training challenger model: {}", candidate.name)
    start = time.perf_counter()
    candidate.pipeline.fit(x_train, y_train)
    train_seconds = time.perf_counter() - start
    y_score = candidate.pipeline.predict_proba(x_test)[:, 1]
    eval_result = evaluate_predictions(y_test.to_numpy(), y_score)

    tags = build_run_tags(candidate.name)
    tags["role"] = "challenger"

    with start_run(run_name=f"{candidate.name}-challenger", tags=tags) as run:
        mlflow.log_params(build_params_payload(candidate.params, dataset_meta))
        mlflow.log_metrics(
            build_metrics_payload(eval_result, training_duration_seconds=train_seconds)
        )
        log_run_artifacts(
            model_name=candidate.name,
            eval_result=eval_result,
            y_true=y_test.to_numpy(),
            y_score=y_score,
        )
        model_uri = log_sklearn_pipeline(candidate.pipeline, x_train)
        challenger_run_id = run.info.run_id

    challenger_version: str | None = None
    if register_model:
        registry = MlflowRegistryClient(tracking_uri=settings.MLFLOW_TRACKING_URI)
        version = registry.register_model(model_uri, REGISTERED_MODEL_NAME)
        challenger_version = str(version.version)
        registry.client.set_registered_model_alias(
            name=REGISTERED_MODEL_NAME,
            alias=CHAMPION_ALIAS,
            version=challenger_version,
        )

    return {
        "challenger_run_id": challenger_run_id,
        "challenger_model_uri": model_uri,
        "challenger_model_version": challenger_version,
        "challenger_metrics": {
            "pr_auc": float(eval_result["pr_auc"]),
            "roc_auc": float(eval_result["roc_auc"]),
            "f1": float(eval_result["f1"]),
            "precision": float(eval_result["precision"]),
            "recall": float(eval_result["recall"]),
            "threshold": float(eval_result["threshold"]),
        },
        "model_type": candidate.name,
    }


@task(name="get_champion_metrics")
def get_champion_metrics_task(
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Look up the current production champion and return its PR-AUC.

    Tries both the legacy ``Production`` stage path and the modern
    ``production``/``champion`` alias path so this works against MLflow
    2.x and 3.x. Returns ``None`` when no champion exists yet — the
    flow then auto-promotes the challenger.
    """
    settings = settings or get_settings()
    import mlflow

    from src.models.registry import MlflowRegistryClient
    from src.training.experiment import REGISTERED_MODEL_NAME

    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    registry = MlflowRegistryClient(tracking_uri=settings.MLFLOW_TRACKING_URI)
    info = registry.get_production_model_info(REGISTERED_MODEL_NAME)
    if info is None or not info.run_id:
        logger.info("no production champion found")
        return None

    try:
        run = registry.client.get_run(info.run_id)
        pr_auc = run.data.metrics.get("pr_auc")
        if pr_auc is None:
            logger.warning("champion run {} has no pr_auc metric", info.run_id)
            return {"version": info.version, "run_id": info.run_id, "pr_auc": None}
        return {
            "version": info.version,
            "run_id": info.run_id,
            "pr_auc": float(pr_auc),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not load champion metrics: {}", exc)
        return None


@task(name="compare_challenger_to_champion")
def compare_challenger_to_champion_task(
    challenger_metrics: dict[str, Any],
    champion_metrics: dict[str, Any] | None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Return ``{"should_promote": bool, "reason": str, ...}``.

    Promotion rule:
        * No champion -> promote (first-ever model wins by default).
        * Champion exists but has no PR-AUC -> reject (we can't measure).
        * Otherwise: promote iff
          ``challenger_pr_auc - champion_pr_auc >= MODEL_PROMOTION_MIN_DELTA``.
    """
    settings = settings or get_settings()
    min_delta = float(settings.MODEL_PROMOTION_MIN_DELTA)
    challenger_pr_auc = float(challenger_metrics["pr_auc"])

    if champion_metrics is None:
        return {
            "should_promote": True,
            "reason": "No champion found; promoting first trained model.",
            "challenger_pr_auc": challenger_pr_auc,
            "champion_pr_auc": None,
            "delta": None,
            "min_delta": min_delta,
        }

    champion_pr_auc = champion_metrics.get("pr_auc")
    if champion_pr_auc is None:
        return {
            "should_promote": False,
            "reason": "Champion has no PR-AUC metric; cannot compare safely.",
            "challenger_pr_auc": challenger_pr_auc,
            "champion_pr_auc": None,
            "delta": None,
            "min_delta": min_delta,
        }

    champion_pr_auc = float(champion_pr_auc)
    delta = challenger_pr_auc - champion_pr_auc
    should_promote = delta >= min_delta
    reason = (
        f"Challenger PR-AUC {challenger_pr_auc:.4f} vs champion "
        f"{champion_pr_auc:.4f} (delta={delta:+.4f}, threshold>={min_delta:+.4f})"
    )
    return {
        "should_promote": bool(should_promote),
        "reason": reason,
        "challenger_pr_auc": challenger_pr_auc,
        "champion_pr_auc": champion_pr_auc,
        "delta": delta,
        "min_delta": min_delta,
    }


@task(name="promote_challenger")
def promote_challenger_task(
    challenger: dict[str, Any],
    comparison: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Flip the production alias and tag the new version.

    Returns the registry metadata for the now-promoted version.
    """
    settings = settings or get_settings()

    from src.models.registry import MlflowRegistryClient
    from src.training.experiment import REGISTERED_MODEL_NAME

    version = challenger.get("challenger_model_version")
    if version is None:
        raise RetrainingError(
            "cannot promote challenger without a registered model version"
        )

    registry = MlflowRegistryClient(tracking_uri=settings.MLFLOW_TRACKING_URI)
    registry.promote_model_to_production(REGISTERED_MODEL_NAME, version)
    archived = registry.archive_old_versions(
        REGISTERED_MODEL_NAME, exclude_version=version
    )

    promoted_at = datetime.now(tz=UTC).isoformat()
    tags = {
        "champion": "true",
        "promoted_at": promoted_at,
        "trigger_reason": comparison.get("trigger_reason", "manual"),
        "pr_auc": f"{comparison.get('challenger_pr_auc', 0.0):.6f}",
    }
    for key, value in tags.items():
        try:
            registry.client.set_model_version_tag(
                name=REGISTERED_MODEL_NAME,
                version=str(version),
                key=key,
                value=value,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("set_model_version_tag({}={}) failed: {}", key, value, exc)

    logger.info("promoted version {} | archived previous: {}", version, archived)
    return {
        "version": str(version),
        "archived_versions": archived,
        "promoted_at": promoted_at,
    }


@task(name="reload_api_model")
def reload_api_model_task(settings: Settings | None = None) -> str:
    """Best-effort call to the API ``/v1/admin/reload-model`` endpoint.

    Returns ``"reloaded"`` | ``"skipped_or_failed"``. We do not raise: a
    promotion that succeeded inside MLflow should not be reverted just
    because the live API is temporarily down.
    """
    settings = settings or get_settings()
    try:
        # urllib avoids a hard dep on ``httpx`` / ``requests`` for what is
        # a single best-effort POST. The API key header is the same one
        # the admin router expects.
        import urllib.error
        import urllib.request

        url = f"{settings.API_BASE_URL.rstrip('/')}/v1/admin/reload-model"
        req = urllib.request.Request(
            url,
            method="POST",
            headers={"X-API-Key": settings.API_KEY},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.status < 300:
                logger.info("API model reload succeeded")
                return "reloaded"
            logger.warning("API model reload returned HTTP {}", resp.status)
            return "skipped_or_failed"
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning("API model reload failed (continuing): {}", exc)
        return "skipped_or_failed"


@task(name="log_retraining_end")
async def log_retraining_end_task(
    run_id: UUID,
    *,
    status: str,
    promoted: bool,
    challenger_run_id: str | None,
    challenger_model_uri: str | None,
    challenger_model_version: str | None,
    challenger_pr_auc: float | None,
    champion_pr_auc: float | None,
    api_reload_status: str | None,
    outcome_notes: str | None,
    error_message: str | None = None,
) -> None:
    """Update the ``retraining_runs`` row with the final outcome."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        repo = RetrainingRunRepository(session)
        if status in (STATUS_PROMOTED, STATUS_REJECTED):
            await repo.update_run_success(
                run_id,
                status=status,
                promoted=promoted,
                challenger_run_id=challenger_run_id,
                challenger_model_uri=challenger_model_uri,
                challenger_model_version=challenger_model_version,
                challenger_pr_auc=challenger_pr_auc,
                champion_pr_auc=champion_pr_auc,
                api_reload_status=api_reload_status,
                outcome_notes=outcome_notes,
            )
        else:
            await repo.update_run_failure(
                run_id,
                error_message=error_message or "unknown failure",
                outcome_notes=outcome_notes,
            )


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


def _validate_trigger(trigger_reason: str) -> str:
    """Coerce + validate the trigger string."""
    cleaned = (trigger_reason or "manual").strip().lower()
    if cleaned not in ALLOWED_TRIGGERS:
        raise RetrainingError(
            f"invalid trigger_reason {trigger_reason!r}; "
            f"allowed values: {ALLOWED_TRIGGERS}"
        )
    return cleaned


@flow(name=RETRAINING_FLOW_NAME, validate_parameters=False)
async def retraining_flow(
    trigger_reason: str = "manual",
    *,
    settings: Settings | None = None,
    register_model: bool = True,
    perform_reload: bool = True,
) -> dict[str, Any]:
    """Train a challenger and promote/reject based on PR-AUC delta.

    Returns a dict with keys ``status``, ``trigger_reason``,
    ``challenger_pr_auc``, ``champion_pr_auc``, ``promoted`` and
    ``retraining_run_id``.
    """
    settings = settings or get_settings()
    trigger = _validate_trigger(trigger_reason)

    run_id = await log_retraining_start_task(trigger)

    try:
        data_paths = prepare_training_data_task(settings)
        challenger = train_challenger_model_task(
            data_paths, settings=settings, register_model=register_model
        )
        champion = get_champion_metrics_task(settings)
        comparison = compare_challenger_to_champion_task(
            challenger["challenger_metrics"], champion, settings=settings
        )
        comparison["trigger_reason"] = trigger

        challenger_pr_auc = float(challenger["challenger_metrics"]["pr_auc"])
        champion_pr_auc = (
            float(champion["pr_auc"])
            if champion is not None and champion.get("pr_auc") is not None
            else None
        )

        api_reload_status: str | None = None
        if comparison["should_promote"]:
            promote_challenger_task(challenger, comparison, settings=settings)
            if perform_reload:
                api_reload_status = reload_api_model_task(settings)
            status = STATUS_PROMOTED
            promoted = True
        else:
            status = STATUS_REJECTED
            promoted = False

        await log_retraining_end_task(
            run_id,
            status=status,
            promoted=promoted,
            challenger_run_id=challenger.get("challenger_run_id"),
            challenger_model_uri=challenger.get("challenger_model_uri"),
            challenger_model_version=challenger.get("challenger_model_version"),
            challenger_pr_auc=challenger_pr_auc,
            champion_pr_auc=champion_pr_auc,
            api_reload_status=api_reload_status,
            outcome_notes=comparison.get("reason"),
        )

        record_retraining_run(
            status=status,
            trigger_reason=trigger,
            promoted=promoted,
            challenger_pr_auc=challenger_pr_auc,
            champion_pr_auc=champion_pr_auc,
        )

        return {
            "status": status,
            "trigger_reason": trigger,
            "challenger_pr_auc": challenger_pr_auc,
            "champion_pr_auc": champion_pr_auc,
            "promoted": promoted,
            "retraining_run_id": str(run_id),
            "comparison_reason": comparison.get("reason"),
            "challenger_model_version": challenger.get("challenger_model_version"),
            "api_reload_status": api_reload_status,
        }

    except Exception as exc:  # noqa: BLE001 — flow-wide guard
        logger.exception("retraining flow failed: {}", exc)
        try:
            await log_retraining_end_task(
                run_id,
                status="failed",
                promoted=False,
                challenger_run_id=None,
                challenger_model_uri=None,
                challenger_model_version=None,
                challenger_pr_auc=None,
                champion_pr_auc=None,
                api_reload_status=None,
                outcome_notes=None,
                error_message=str(exc),
            )
        except Exception as inner:  # noqa: BLE001
            logger.error("failed to log retraining failure: {}", inner)
        record_retraining_run(
            status="failed",
            trigger_reason=trigger,
            promoted=False,
            challenger_pr_auc=None,
            champion_pr_auc=None,
        )
        return {
            "status": "failed",
            "trigger_reason": trigger,
            "promoted": False,
            "retraining_run_id": str(run_id),
            "error": str(exc),
        }
