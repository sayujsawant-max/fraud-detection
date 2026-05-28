"""Prefect 3 deployment helpers.

Two ways to run the flows on a schedule against the Prefect server bundled
in the Docker stack:

1. **``flow.serve(...)``** — the simplest, recommended for local-dev
   deployments. It registers the flow + cron with the API and stays
   resident in the foreground, running flow runs as they're scheduled.
   Used by ``scripts/deploy_prefect_flows.py``.

2. **``flow.to_deployment(...)`` + ``serve(...)``** — same end state, but
   lets us register multiple deployments in one process.

Both paths return a list of (flow_name, deployment_object) tuples so the
script can log a friendly summary.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.core.config import Settings, get_settings
from src.workflows.monitoring_flow import MONITORING_FLOW_NAME, monitoring_flow
from src.workflows.retraining_flow import RETRAINING_FLOW_NAME, retraining_flow

DEFAULT_MONITORING_CRON: str = "0 */6 * * *"
DEFAULT_RETRAINING_CRON: str = "0 2 * * 0"


def _build_cron_schedule(cron: str, timezone: str = "UTC") -> Any:
    """Return a Prefect 3 cron schedule object.

    Prefect 3 ships two equivalent class names depending on which submodule
    you reach for; ``CronSchedule`` lives under
    :mod:`prefect.client.schemas.schedules`. We import lazily so the rest
    of the codebase doesn't take a Prefect import hit.
    """
    from prefect.client.schemas.schedules import CronSchedule

    return CronSchedule(cron=cron, timezone=timezone)


def build_monitoring_deployment(
    cron: str | None = None,
    *,
    settings: Settings | None = None,
) -> Any:
    """Return a :class:`Deployment` for the monitoring flow on ``cron``."""
    settings = settings or get_settings()
    cron_expr = cron or settings.PREFECT_MONITORING_CRON or DEFAULT_MONITORING_CRON
    schedule = _build_cron_schedule(cron_expr)
    return monitoring_flow.to_deployment(
        name="fraud-monitoring-every-6h",
        schedule=schedule,
        description=(
            "Runs Evidently drift detection on a schedule and triggers "
            "retraining when drift is detected."
        ),
        tags=["fraudshield", "monitoring", "phase-6"],
    )


def build_retraining_deployment(
    cron: str | None = None,
    *,
    settings: Settings | None = None,
) -> Any:
    """Return a :class:`Deployment` for the retraining flow on ``cron``."""
    settings = settings or get_settings()
    cron_expr = cron or settings.PREFECT_RETRAINING_CRON or DEFAULT_RETRAINING_CRON
    schedule = _build_cron_schedule(cron_expr)
    return retraining_flow.to_deployment(
        name="fraud-retraining-weekly",
        schedule=schedule,
        parameters={"trigger_reason": "scheduled"},
        description=(
            "Trains a challenger model on a weekly cadence and promotes "
            "it when PR-AUC improves by MODEL_PROMOTION_MIN_DELTA."
        ),
        tags=["fraudshield", "retraining", "phase-6"],
    )


def serve_all_flows(
    *,
    settings: Settings | None = None,
    monitoring_cron: str | None = None,
    retraining_cron: str | None = None,
) -> None:
    """Block in ``serve()`` running both flows on their cron schedules.

    The function never returns under normal operation — Prefect's
    ``serve()`` is intended to be the long-running foreground process.
    """
    from prefect import serve

    settings = settings or get_settings()
    monitoring = build_monitoring_deployment(monitoring_cron, settings=settings)
    retraining = build_retraining_deployment(retraining_cron, settings=settings)

    logger.info(
        "serving Prefect flows | monitoring={} {} | retraining={} {}",
        MONITORING_FLOW_NAME,
        monitoring_cron or settings.PREFECT_MONITORING_CRON,
        RETRAINING_FLOW_NAME,
        retraining_cron or settings.PREFECT_RETRAINING_CRON,
    )
    serve(monitoring, retraining)
