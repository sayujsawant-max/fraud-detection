"""Phase 6 — Prefect 3 orchestration workflows for FraudShield.

Two flows live in this package:

* :mod:`src.workflows.monitoring_flow` — scheduled drift checks. Triggers
  the retraining flow when drift is detected.
* :mod:`src.workflows.retraining_flow` — challenger training + champion
  comparison + MLflow promotion. Callable manually, by the monitoring
  flow, or on a weekly cron.

All Prefect-decorated functions are imported lazily through this package
so backend modules that don't need orchestration (e.g. the FastAPI router
layer) never pay the Prefect import cost.

The compat wrapper :mod:`src.workflows.tasks` shields the rest of the
codebase from minor Prefect 3 API churn — we only import ``flow``/``task``
from there.
"""

from src.workflows.tasks import flow, task

__all__ = ["flow", "task"]
